"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Brain,
  CalendarDays,
  Check,
  CheckCheck,
  ChevronDown,
  CircleOff,
  Copy,
  Download,
  Flag,
  Forward,
  Info,
  Loader2,
  MoreVertical,
  Pause,
  Paperclip,
  Pin,
  Play,
  Reply,
  Search,
  Send,
  Share2,
  SlidersHorizontal,
  Sparkles,
  Star,
  StickyNote,
  Trash2,
  UserRoundCheck,
  Volume2,
  X,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";

import { ConfirmDialog, EmptyState, RightDrawer, StatusBadge, TemperatureBadge } from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { useOwnerUnitScope } from "@/hooks/use-owner-unit-scope";
import { useSession } from "@/hooks/use-session";
import { api } from "@/lib/api";
import {
  ApiPage,
  AppointmentItem,
  ConversationItem,
  DocumentItem,
  LeadItem,
  MessageItem,
  PatientItem,
  UnitItem,
  UserItem,
} from "@/lib/domain-types";
import { canAccessPage } from "@/lib/page-access";
import {
  formatDateBR,
  formatDateTimeBR,
  formatPhoneBR,
  formatRelativeTime,
  initials,
  STAGE_LABELS,
} from "@/lib/formatters";
import {
  clearDemoWhatsAppEntry,
  markDemoWhatsAppAppointmentReady,
  markDemoWhatsAppAwaitingAppointment,
  readDemoWhatsAppEntry,
  storeDemoEntryTargetPath,
} from "@/lib/demo-session";
import {
  DEMO_WEBCHAT_WORKSPACE_EVENT_NAME,
  DEMO_TOUR_COMMAND_EVENT_NAME,
  DEMO_TOUR_TEST_ACTION_EVENT_NAME,
  DEMO_TOUR_TARGETS,
  dispatchDemoTourEvent,
  type DemoTourCommandDetail,
  type DemoWebchatWorkspaceDetail,
  type DemoTourTestActionDetail,
} from "@/lib/demo-tour";
import { BRAND_NAME } from "@/lib/brand";
import { Badge, Button, Input, cn } from "@odontoflux/ui";

type InboxDataset = {
  conversations: ConversationItem[];
  users: UserItem[];
  patients: PatientItem[];
  units: UnitItem[];
  leads: LeadItem[];
  appointments: AppointmentItem[];
  documents: DocumentItem[];
};

type MessageResponse = { data: MessageItem[] };
type AIDecisionItem = {
  id: string;
  final_decision: string;
  decision_reason: string;
  decision_reason_label: string;
  handoff_required: boolean;
  guardrail_trigger?: string | null;
  confidence?: number | null;
  generated_response?: string | null;
  created_at: string;
};
type AIDecisionResponse = { data: AIDecisionItem[] };
type AISummaryResponse = {
  conversation_id: string;
  summary: string;
  metadata?: Record<string, unknown>;
};

const STATUS_FILTERS = [
  { id: "all", label: "Todas" },
  { id: "aberta", label: "Abertas" },
  { id: "aguardando", label: "Aguardando" },
  { id: "finalizada", label: "Finalizadas" },
  { id: "nao_respondida", label: "Não respondidas" },
] as const;

const QUICK_FILTERS = [
  { id: "all", label: "Tudo" },
  { id: "aguardando", label: "Aguardando" },
  { id: "nao_respondida", label: "Não respondidas" },
] as const;

const DEMO_WEBCHAT_WORKSPACE_SWIPE_THRESHOLD_PX = 84;

type StatusFilterId = (typeof STATUS_FILTERS)[number]["id"];
type PriorityFilter = "all" | "alta" | "media" | "baixa";

function conversationPriority(conversation: ConversationItem): "alta" | "media" | "baixa" {
  if (conversation.status === "aguardando") return "alta";
  if (!conversation.last_message_at) return "media";
  const minutes = (Date.now() - new Date(conversation.last_message_at).getTime()) / (1000 * 60);
  if (minutes > 180) return "alta";
  if (minutes > 60) return "media";
  return "baixa";
}

function priorityBadgeClass(priority: "alta" | "media" | "baixa") {
  if (priority === "alta") return "bg-rose-100 text-rose-700";
  if (priority === "media") return "bg-amber-100 text-amber-800";
  return "bg-emerald-100 text-emerald-700";
}

function aiDecisionLabel(value?: string | null) {
  if (!value) return "Sem decisão";
  if (value === "responded") return "Respondido";
  if (value === "handoff") return "Handoff";
  if (value === "blocked") return "Bloqueado";
  if (value === "ignored") return "Ignorado";
  if (value === "error") return "Erro";
  return value;
}

function aiReasonLabel(value?: string | null) {
  if (!value) return "Sem motivo";
  return value.replaceAll("_", " ");
}

function channelLabel(channel: string) {
  if (channel === "whatsapp") return "WhatsApp";
  return channel.toUpperCase();
}

function normalizePhoneForComparison(value?: string | null) {
  const digits = String(value || "").replace(/\D/g, "");
  if (!digits) return "";
  const normalized = digits.startsWith("55") && digits.length >= 12 ? digits.slice(2) : digits;
  return normalized.slice(-11);
}

function readStoredWebchatSessionIdFromPublicEntryPath(publicEntryPath?: string | null) {
  if (typeof window === "undefined") return null;
  const rawPath = String(publicEntryPath || "").trim();
  if (!rawPath) return null;

  let pathname = rawPath;
  try {
    pathname = rawPath.startsWith("http") ? new URL(rawPath).pathname : rawPath;
  } catch {
    pathname = rawPath;
  }

  const match = pathname.match(/\/agendar\/([^/?#]+)/i);
  const clinicSlug = match?.[1] ? decodeURIComponent(match[1]) : null;
  if (!clinicSlug) return null;

  try {
    const raw = window.localStorage.getItem(`clinicflux.link_flow.webchat.${clinicSlug}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { session_id?: string; cta_mode?: string };
    if (parsed.cta_mode !== "webchat") return null;
    return typeof parsed.session_id === "string" && parsed.session_id.trim() ? parsed.session_id.trim() : null;
  } catch {
    return null;
  }
}

function resolveDemoPublicEntryPath(publicEntryPath?: string | null, tenantSlug?: string | null) {
  const rawPath = String(publicEntryPath || "").trim();
  const normalizedTenantSlug = String(tenantSlug || "").trim();
  const tenantFallback = normalizedTenantSlug ? `/agendar/${encodeURIComponent(normalizedTenantSlug)}` : null;

  if (!rawPath) return tenantFallback;

  let pathname = rawPath;
  try {
    pathname = rawPath.startsWith("http") ? new URL(rawPath).pathname : rawPath;
  } catch {
    pathname = rawPath;
  }

  const match = pathname.match(/\/agendar\/([^/?#]+)/i);
  const pathSlug = match?.[1] ? decodeURIComponent(match[1]) : null;
  if (tenantFallback && pathSlug && pathSlug !== normalizedTenantSlug) {
    return tenantFallback;
  }

  if (tenantFallback && !pathSlug) return tenantFallback;
  return rawPath;
}

function webchatSyntheticContact(sessionId?: string | null) {
  const normalized = String(sessionId || "").replace(/-/g, "").trim().toLowerCase();
  if (!normalized) return null;
  return `webchat${normalized.slice(0, 18)}`;
}

function isNoReplyConversation(conversation: ConversationItem) {
  return (
    ["aberta", "aguardando"].includes(conversation.status) &&
    (!conversation.last_message_at ||
      Date.now() - new Date(conversation.last_message_at).getTime() > 1000 * 60 * 60 * 2)
  );
}

function DetailSection({
  title,
  children,
  tone = "default",
}: {
  title: string;
  children: ReactNode;
  tone?: "default" | "muted" | "accent";
}) {
  return (
    <section
      className={cn(
        "rounded-2xl border p-4",
        tone === "default" && "border-stone-200 bg-white",
        tone === "muted" && "border-stone-200 bg-stone-50",
        tone === "accent" && "border-primary/15 bg-primary/5",
      )}
    >
      <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500">{title}</p>
      <div className="mt-3">{children}</div>
    </section>
  );
}

const AUDIO_MESSAGE_TYPES = new Set(["audio", "voice"]);
const AUDIO_PLACEHOLDER_BODIES = new Set([
  "[audio recebido - transcricao pendente]",
  "[audio recebido - transcricao indisponivel]",
  "[audio recebido - transcricao nao concluida]",
]);

type MessagePayloadRecord = Record<string, unknown>;
type MessageMenuAction = {
  id: string;
  label: string;
  icon: ReactNode;
  onSelect: () => void | Promise<void>;
  destructive?: boolean;
  disabled?: boolean;
  separatorBefore?: boolean;
};

type DemoGuideClientState = {
  active: boolean;
  stepId: string | null;
  stepOrder: number | null;
  placement: "centered" | "docked" | null;
  pagePath: string | null;
  title: string | null;
};

type DemoConversationTourStage =
  | "idle"
  | "suggestion_spotlight"
  | "summary_spotlight"
  | "automation_countdown"
  | "conversation_focus"
  | "simulation_running"
  | "appointment_saved_pause"
  | "finish_countdown"
  | "interrupted"
  | "completed";

type DemoWhatsAppExperienceStage =
  | "idle"
  | "entry"
  | "awaiting_appointment"
  | "appointment_ready";

type DemoSimulationMessage = {
  id: string;
  direction: "inbound" | "outbound";
  body: string;
  delivery: "sent" | "delivered" | "read";
  createdAt: string;
};

type DemoSimulationScriptEntry =
  | {
      id: string;
      kind?: "message";
      direction: "inbound" | "outbound";
      body: string;
      delivery?: "sent" | "delivered" | "read";
      delayMs: number;
    }
  | {
      id: string;
      kind: "pause_after_confirmation";
    };

const DEMO_GUIDE_CONVERSATION_STEP_ID = "conversations_whatsapp";
const DEMO_TOUR_SPOTLIGHT_DURATION_MS = 5_000;
const DEMO_TOUR_COUNTDOWN_STEP_MS = 1_000;
const DEMO_TOUR_CONVERSATION_FOCUS_DURATION_MS = 5_000;
const DEMO_TOUR_APPOINTMENT_PAUSE_DURATION_MS = 5_000;
const DEMO_TOUR_NEXT_STEP_COUNTDOWN_SECONDS = 5;
const DEMO_WHATSAPP_AGENDA_REDIRECT_SECONDS = 5;
const DEMO_APPOINTMENT_AUTO_ORIGINS = new Set([
  "ai_autoresponder",
  "ai_structured",
  "demo_personalizada",
  "whatsapp",
  "whatsapp_demo",
]);

function emptyDemoGuideClientState(): DemoGuideClientState {
  return {
    active: false,
    stepId: null,
    stepOrder: null,
    placement: null,
    pagePath: null,
    title: null,
  };
}

function nextBusinessDays(count: number) {
  const dates: Date[] = [];
  const cursor = new Date();

  while (dates.length < count) {
    cursor.setDate(cursor.getDate() + 1);
    const weekday = cursor.getDay();
    if (weekday === 0 || weekday === 6) continue;
    dates.push(new Date(cursor));
  }

  return dates;
}

function formatDemoDateOption(date: Date) {
  const weekday = date.toLocaleDateString("pt-BR", { weekday: "short" }).replace(".", "");
  const normalizedWeekday = weekday.charAt(0).toUpperCase() + weekday.slice(1);
  return `${normalizedWeekday}, ${formatDateBR(date.toISOString())}`;
}

function buildDemoConversationScript(unitNames: string[], patientName: string): DemoSimulationScriptEntry[] {
  const units = unitNames.filter(Boolean).slice(0, 3);
  while (units.length < 3) {
    units.push(["Unidade Centro", "Unidade Paulista", "Unidade Zona Sul"][units.length] ?? `Unidade ${units.length + 1}`);
  }

  const dateOptions = nextBusinessDays(3).map(formatDemoDateOption);
  const firstName = (patientName || "Paciente").trim().split(/\s+/)[0] || "Paciente";

  return [
    {
      id: "patient-intent",
      direction: "inbound",
      body: "Oi, tudo bem? Quero marcar uma avaliação para a próxima semana.",
      delivery: "delivered",
      delayMs: 1_400,
    },
    {
      id: "ai-units",
      direction: "outbound",
      body: `Claro, ${firstName}. Posso organizar isso agora mesmo.\n\nEscolha a clínica:\n1. ${units[0]}\n2. ${units[1]}\n3. ${units[2]}`,
      delivery: "read",
      delayMs: 1_800,
    },
    {
      id: "patient-unit",
      direction: "inbound",
      body: `Quero a ${units[0]}.`,
      delivery: "delivered",
      delayMs: 1_500,
    },
    {
      id: "ai-service",
      direction: "outbound",
      body: "Perfeito. Agora escolha o serviço:\n1. Avaliação inicial\n2. Limpeza\n3. Clareamento dental",
      delivery: "read",
      delayMs: 1_900,
    },
    {
      id: "patient-service",
      direction: "inbound",
      body: "Pode ser limpeza.",
      delivery: "delivered",
      delayMs: 1_500,
    },
    {
      id: "ai-date",
      direction: "outbound",
      body: `Tenho estas datas disponíveis:\n1. ${dateOptions[0]}\n2. ${dateOptions[1]}\n3. ${dateOptions[2]}`,
      delivery: "read",
      delayMs: 1_900,
    },
    {
      id: "patient-date",
      direction: "inbound",
      body: "A primeira opção funciona para mim.",
      delivery: "delivered",
      delayMs: 1_500,
    },
    {
      id: "ai-time",
      direction: "outbound",
      body: "Ótimo. Escolha o horário:\n1. 09:00\n2. 10:30\n3. 14:00",
      delivery: "read",
      delayMs: 1_900,
    },
    {
      id: "patient-time",
      direction: "inbound",
      body: "Quero às 10:30.",
      delivery: "delivered",
      delayMs: 1_500,
    },
    {
      id: "ai-confirm",
      direction: "outbound",
      body: `Tudo certo. Para confirmar:\n• Clínica: ${units[0]}\n• Serviço: Limpeza\n• Data: ${dateOptions[0]}\n• Hora: 10:30\n\n1. Sim, confirmar\n2. Quero outro horário`,
      delivery: "read",
      delayMs: 2_100,
    },
    {
      id: "patient-confirm",
      direction: "inbound",
      body: "1. Sim, pode confirmar.",
      delivery: "delivered",
      delayMs: 1_500,
    },
    {
      id: "appointment-pause",
      kind: "pause_after_confirmation",
    },
    {
      id: "ai-success",
      direction: "outbound",
      body: `Pronto, ${firstName}. Agendamento confirmado com sucesso.\n\n• Clínica: ${units[0]}\n• Serviço: Limpeza\n• Data: ${dateOptions[0]}\n• Hora: 10:30`,
      delivery: "read",
      delayMs: 1_800,
    },
    {
      id: "patient-thanks",
      direction: "inbound",
      body: "Perfeito, obrigada.",
      delivery: "delivered",
      delayMs: 1_500,
    },
    {
      id: "ai-follow-up",
      direction: "outbound",
      body: "Eu que agradeço. Se quiser, também posso te lembrar desse horário e ajudar com qualquer remarcação por aqui.",
      delivery: "read",
      delayMs: 1_800,
    },
  ];
}

function messagePayloadRecord(message: MessageItem): MessagePayloadRecord {
  return message.payload && typeof message.payload === "object" ? (message.payload as MessagePayloadRecord) : {};
}

function messageMediaPayload(message: MessageItem): MessagePayloadRecord | null {
  const payload = messagePayloadRecord(message);
  return payload.media && typeof payload.media === "object" ? (payload.media as MessagePayloadRecord) : null;
}

function messageAudioTranscriptionPayload(message: MessageItem): MessagePayloadRecord | null {
  const payload = messagePayloadRecord(message);
  return payload.audio_transcription && typeof payload.audio_transcription === "object"
    ? (payload.audio_transcription as MessagePayloadRecord)
    : null;
}

function isAudioMessageType(messageType?: string | null) {
  return AUDIO_MESSAGE_TYPES.has(String(messageType || "").trim().toLowerCase());
}

function isAudioPlaceholderBody(body?: string | null) {
  return AUDIO_PLACEHOLDER_BODIES.has(String(body || "").trim().toLowerCase());
}

function messageReadableContent(message: MessageItem) {
  const transcription = messageAudioTranscriptionPayload(message);
  const transcriptionText = String(transcription?.text || "").trim();
  if (transcriptionText) {
    return transcriptionText;
  }
  return String(message.body || "").trim();
}

function messageCardPreview(message: MessageItem) {
  if (isAudioMessageType(message.message_type)) {
    const transcript = messageReadableContent(message);
    if (transcript && !isAudioPlaceholderBody(transcript)) {
      return transcript;
    }
    return "Mensagem de áudio";
  }
  return messageReadableContent(message) || "Mensagem sem texto";
}

function audioBadgeLabel(message: MessageItem, outbound: boolean) {
  if (outbound) return "Áudio enviado";
  const transcription = messageAudioTranscriptionPayload(message);
  const status = String(transcription?.status || "").trim().toLowerCase();
  if (status === "completed") return "Áudio transcrito";
  if (status === "pending") return "Áudio recebido";
  if (status === "failed") return "Transcrição não concluída";
  if (status === "unavailable") return "Transcrição indisponível";
  return "Mensagem de áudio";
}

function audioTranscriptDescription(message: MessageItem) {
  const transcription = messageAudioTranscriptionPayload(message);
  const status = String(transcription?.status || "").trim().toLowerCase();
  const transcript = String(transcription?.text || "").trim();
  if (transcript) {
    return transcript;
  }
  if (!isAudioMessageType(message.message_type)) {
    return String(message.body || "").trim();
  }
  if (status === "pending") {
    return "Transcrição pendente. Você já pode ouvir o áudio abaixo.";
  }
  if (status === "failed") {
    return "A transcrição desse áudio não foi concluída, mas o arquivo continua disponível para escuta.";
  }
  if (status === "unavailable") {
    return "A transcrição automática está indisponível neste momento, mas o áudio segue disponível.";
  }
  if (!isAudioPlaceholderBody(message.body)) {
    return String(message.body || "").trim();
  }
  return "";
}

function parseDurationSeconds(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return 0;
}

function formatDurationClock(totalSeconds: number) {
  const safeSeconds = Math.max(0, Math.floor(Number.isFinite(totalSeconds) ? totalSeconds : 0));
  const minutes = Math.floor(safeSeconds / 60);
  const seconds = safeSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function messageDeliveryVisualState(message: MessageItem) {
  const normalizedStatus = String(message.status || "").trim().toLowerCase();
  if (message.read_at || normalizedStatus === "read") return "read";
  if (message.delivered_at || normalizedStatus === "delivered") return "delivered";
  if (["sent", "queued"].includes(normalizedStatus) || message.sent_at) return "sent";
  if (normalizedStatus === "failed") return "failed";
  return "sent";
}

function buildTextDownloadFileName(message: MessageItem) {
  return `mensagem-${message.id}.txt`;
}

function buildAudioDownloadFileName(message: MessageItem) {
  const media = messageMediaPayload(message);
  const explicitName = String(media?.file_name || "").trim();
  if (explicitName) return explicitName;
  return `audio-${message.id}.ogg`;
}

async function triggerBlobDownload(blob: Blob, fileName: string) {
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1200);
}

function MessageDeliveryIndicator({ message, outbound }: { message: MessageItem; outbound: boolean }) {
  if (!outbound) return null;

  const visualState = messageDeliveryVisualState(message);
  if (visualState === "failed") {
    return <CircleOff size={13} className="text-rose-300" aria-label="Falha na entrega" />;
  }

  if (visualState === "read") {
    return <CheckCheck size={14} className="text-sky-300" aria-label="Enviada, entregue e visualizada" />;
  }

  if (visualState === "delivered") {
    return (
      <CheckCheck
        size={14}
        className={cn(outbound ? "text-primary-foreground/75" : "text-stone-400")}
        aria-label="Enviada e entregue"
      />
    );
  }

  return (
    <Check
      size={14}
      className={cn(outbound ? "text-primary-foreground/75" : "text-stone-400")}
      aria-label="Enviada aguardando entrega"
    />
  );
}

function MessageActionMenu({
  outbound,
  actions,
}: {
  outbound: boolean;
  actions: MessageMenuAction[];
}) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return undefined;
    const handlePointerDown = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [open]);

  return (
    <div ref={menuRef} className="absolute right-3 top-3 z-20">
      <button
        type="button"
        className={cn(
          "inline-flex h-7 w-7 items-center justify-center rounded-full border transition",
          outbound
            ? "border-white/15 bg-white/10 text-primary-foreground/80 hover:bg-white/20"
            : "border-stone-200 bg-white/90 text-stone-500 hover:bg-stone-100 hover:text-stone-700",
        )}
        onClick={() => setOpen((current) => !current)}
        aria-label="Abrir ações da mensagem"
      >
        <ChevronDown size={15} />
      </button>

      {open ? (
        <div className="absolute right-0 mt-2 w-56 overflow-hidden rounded-[22px] border border-stone-200 bg-white p-2 shadow-[0_20px_60px_rgba(15,23,42,0.18)]">
          {actions.map((action) => (
            <div key={action.id}>
              {action.separatorBefore ? <div className="my-2 border-t border-stone-200" /> : null}
              <button
                type="button"
                className={cn(
                  "flex w-full items-center gap-3 rounded-2xl px-3 py-2.5 text-left text-sm transition",
                  action.destructive
                    ? "text-rose-700 hover:bg-rose-50"
                    : "text-stone-700 hover:bg-stone-50",
                  action.disabled && "cursor-not-allowed opacity-50",
                )}
                disabled={action.disabled}
                onClick={async () => {
                  if (action.disabled) return;
                  try {
                    await action.onSelect();
                    setOpen(false);
                  } catch {
                    toast.error("Não foi possível concluir essa ação para a mensagem.");
                  }
                }}
              >
                <span className="shrink-0">{action.icon}</span>
                <span>{action.label}</span>
              </button>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function AudioMessagePlayer({
  message,
  outbound,
}: {
  message: MessageItem;
  outbound: boolean;
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(
    parseDurationSeconds(messageAudioTranscriptionPayload(message)?.duration_seconds),
  );

  useEffect(() => {
    let objectUrl: string | null = null;
    let active = true;

    const loadAudio = async () => {
      try {
        setIsLoading(true);
        setLoadError("");
        const response = await api.get<Blob>(`/messages/${message.id}/media`, { responseType: "blob" });
        if (!active) return;
        const blob = response.data instanceof Blob ? response.data : new Blob([response.data]);
        objectUrl = URL.createObjectURL(blob);
        setAudioUrl(objectUrl);
      } catch {
        if (!active) return;
        setLoadError("Não foi possível carregar o áudio desta mensagem.");
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    };

    void loadAudio();

    return () => {
      active = false;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [message.id]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return undefined;

    const syncTime = () => {
      setCurrentTime(audio.currentTime || 0);
      if (Number.isFinite(audio.duration) && audio.duration > 0) {
        setDuration(audio.duration);
      }
    };
    const syncPlayState = () => setIsPlaying(!audio.paused);

    audio.addEventListener("loadedmetadata", syncTime);
    audio.addEventListener("timeupdate", syncTime);
    audio.addEventListener("play", syncPlayState);
    audio.addEventListener("pause", syncPlayState);
    audio.addEventListener("ended", syncPlayState);
    return () => {
      audio.removeEventListener("loadedmetadata", syncTime);
      audio.removeEventListener("timeupdate", syncTime);
      audio.removeEventListener("play", syncPlayState);
      audio.removeEventListener("pause", syncPlayState);
      audio.removeEventListener("ended", syncPlayState);
    };
  }, [audioUrl]);

  const description = audioTranscriptDescription(message);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Badge
          className={cn(
            "rounded-full px-2.5 py-0.5 text-[10px] uppercase tracking-[0.22em]",
            outbound
              ? "border-white/20 bg-white/12 text-primary-foreground/90"
              : "border-emerald-200 bg-emerald-50 text-emerald-700",
          )}
        >
          {audioBadgeLabel(message, outbound)}
        </Badge>
      </div>

      <div
        className={cn(
          "rounded-[20px] border px-3 py-3",
          outbound ? "border-white/15 bg-white/10" : "border-stone-200 bg-stone-50/85",
        )}
      >
        <div className="flex items-center gap-3">
          <button
            type="button"
            className={cn(
              "inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition",
              outbound
                ? "bg-white text-primary hover:bg-white/90"
                : "bg-emerald-500 text-white hover:bg-emerald-600",
              (isLoading || !!loadError) && "cursor-not-allowed opacity-70",
            )}
            onClick={() => {
              if (isLoading || loadError) return;
              const audio = audioRef.current;
              if (!audio) return;
              if (audio.paused) {
                void audio.play();
              } else {
                audio.pause();
              }
            }}
            disabled={isLoading || Boolean(loadError)}
            aria-label={isPlaying ? "Pausar áudio" : "Reproduzir áudio"}
          >
            {isLoading ? <Loader2 size={16} className="animate-spin" /> : isPlaying ? <Pause size={16} /> : <Play size={16} />}
          </button>

          <div className="min-w-0 flex-1">
            <div className="relative overflow-hidden rounded-full border border-transparent px-1 py-1">
              <div
                className={cn(
                  "pointer-events-none absolute inset-0 opacity-55",
                  outbound
                    ? "bg-[repeating-linear-gradient(90deg,rgba(255,255,255,0.2),rgba(255,255,255,0.2)_4px,transparent_4px,transparent_8px)]"
                    : "bg-[repeating-linear-gradient(90deg,rgba(21,128,61,0.16),rgba(21,128,61,0.16)_4px,transparent_4px,transparent_8px)]",
                )}
              />
              <input
                type="range"
                min={0}
                max={Math.max(duration, 1)}
                step={0.1}
                value={Math.min(currentTime, Math.max(duration, 1))}
                onChange={(event) => {
                  const audio = audioRef.current;
                  if (!audio) return;
                  const nextValue = Number(event.target.value);
                  audio.currentTime = Number.isFinite(nextValue) ? nextValue : 0;
                  setCurrentTime(Number.isFinite(nextValue) ? nextValue : 0);
                }}
                className="relative z-10 h-2 w-full cursor-pointer appearance-none bg-transparent"
                aria-label="Barra de reprodução do áudio"
                disabled={isLoading || Boolean(loadError)}
              />
            </div>

            <div className={cn("mt-2 flex items-center justify-between text-[11px]", outbound ? "text-primary-foreground/80" : "text-stone-500")}>
              <span>{formatDurationClock(currentTime)}</span>
              <span>{formatDurationClock(duration)}</span>
            </div>
          </div>
        </div>

        {audioUrl ? <audio ref={audioRef} src={audioUrl} preload="metadata" className="hidden" /> : null}

        {loadError ? (
          <p className={cn("mt-3 text-xs", outbound ? "text-primary-foreground/80" : "text-rose-700")}>{loadError}</p>
        ) : null}
      </div>

      {description ? (
        <div
          className={cn(
            "rounded-[18px] border px-3 py-2.5 text-sm leading-6",
            outbound
              ? "border-white/12 bg-white/8 text-primary-foreground/95"
              : "border-stone-200 bg-white/80 text-stone-700",
          )}
        >
          <div className="mb-1 flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] opacity-75">
            <Volume2 size={12} />
            <span>Transcrição</span>
          </div>
          <p className="whitespace-pre-wrap">{description}</p>
        </div>
      ) : null}
    </div>
  );
}

function DemoDeliveryIndicator({ state, outbound }: { state: DemoSimulationMessage["delivery"]; outbound: boolean }) {
  if (!outbound) return null;

  if (state === "read") {
    return <CheckCheck size={14} className="text-sky-300" aria-label="Enviada, entregue e visualizada" />;
  }

  if (state === "delivered") {
    return <CheckCheck size={14} className="text-primary-foreground/75" aria-label="Enviada e entregue" />;
  }

  return <Check size={14} className="text-primary-foreground/75" aria-label="Enviada aguardando entrega" />;
}

function DemoSimulationMessageBubble({ message }: { message: DemoSimulationMessage }) {
  const outbound = message.direction === "outbound";

  return (
    <div className={cn("flex", outbound ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[88%] rounded-[22px] px-4 py-3 text-sm shadow-sm",
          outbound ? "bg-primary text-primary-foreground" : "border border-stone-200 bg-white text-stone-800",
        )}
      >
        <p className="whitespace-pre-wrap leading-6">{message.body}</p>
        <div
          className={cn(
            "mt-2 flex items-center justify-end gap-1.5 text-[11px]",
            outbound ? "text-primary-foreground/80" : "text-stone-500",
          )}
        >
          <span>{formatDateTimeBR(message.createdAt)}</span>
          <DemoDeliveryIndicator state={message.delivery} outbound={outbound} />
        </div>
      </div>
    </div>
  );
}

function DemoGuideSpotlightOverlay({
  rect,
  title,
  description,
  badge,
  icon,
  align = "above-start",
  tone = "standard",
}: {
  rect: DOMRect | null;
  title: string;
  description: ReactNode;
  badge: string;
  icon: ReactNode;
  align?: "above-start" | "top-center" | "left-center";
  tone?: "standard" | "focus";
}) {
  if (!rect) return null;

  const padding = tone === "focus" ? 16 : 10;
  const top = Math.max(10, rect.top - padding);
  const left = Math.max(10, rect.left - padding);
  const width = rect.width + padding * 2;
  const height = rect.height + padding * 2;
  const veilColor = tone === "focus" ? "rgba(2, 6, 23, 0.28)" : "rgba(15, 23, 42, 0.22)";
  const bubbleWidth = 352;
  const bubbleStyle: CSSProperties =
    align === "left-center"
      ? {
          top: `clamp(1rem, ${top + height / 2 - 132}px, calc(100vh - 18rem))`,
          left: `clamp(1rem, ${left - bubbleWidth - 22}px, calc(100vw - 23rem))`,
        }
      : align === "top-center"
        ? {
            top: Math.max(18, top + 24),
            left: `clamp(1rem, ${left + width / 2 - bubbleWidth / 2}px, calc(100vw - 23rem))`,
          }
        : {
            top: Math.max(18, top - 194),
            left: `clamp(1rem, ${left}px, calc(100vw - 23rem))`,
          };

  return (
    <div className="pointer-events-none fixed inset-0 z-[76]">
      <div className="fixed left-0 right-0 top-0" style={{ height: top, backgroundColor: veilColor }} />
      <div className="fixed left-0" style={{ top, width: left, height, backgroundColor: veilColor }} />
      <div className="fixed right-0" style={{ top, left: left + width, height, backgroundColor: veilColor }} />
      <div className="fixed bottom-0 left-0 right-0" style={{ top: top + height, backgroundColor: veilColor }} />

      <div
        className="fixed rounded-[28px] border border-emerald-200/90 bg-transparent transition-all duration-300"
        style={{
          top,
          left,
          width,
          height,
          boxShadow: "0 0 0 1px rgba(255,255,255,0.42), 0 0 24px rgba(16,185,129,0.2)",
        }}
      />

      <div
        className="pointer-events-auto fixed z-[77] w-[min(22rem,calc(100vw-2rem))] rounded-[26px] border border-emerald-200 bg-white p-4 shadow-[0_24px_60px_rgba(15,23,42,0.22)]"
        style={bubbleStyle}
      >
        {align === "left-center" ? (
          <span className="absolute right-[-10px] top-1/2 h-5 w-5 -translate-y-1/2 rotate-45 border-r border-t border-emerald-200 bg-white" />
        ) : null}
        {align === "top-center" ? (
          <span className="absolute bottom-[-10px] left-1/2 h-5 w-5 -translate-x-1/2 rotate-45 border-b border-r border-emerald-200 bg-white" />
        ) : null}
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-emerald-100 text-emerald-700">
            {icon}
          </div>
          <div className="min-w-0">
            <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-emerald-700">
              {badge}
            </span>
            <h3 className="mt-2 text-sm font-semibold text-slate-950">{title}</h3>
            <div className="mt-2 text-sm leading-6 text-slate-700">{description}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ConversasPage() {
  const queryClient = useQueryClient();
  const ownerUnitScope = useOwnerUnitScope();
  const selectedOwnerUnitId =
    ownerUnitScope.canSwitchUnits && ownerUnitScope.selectedUnitId !== "all"
      ? ownerUnitScope.selectedUnitId
      : null;
  const sessionQuery = useSession();
  const router = useRouter();
  const searchParams = useSearchParams();
  const focusConversationId = searchParams.get("focus");
  const [focusHandled, setFocusHandled] = useState(false);
  const currentUserPermissions = sessionQuery.data?.resolved_page_permissions;
  const isDemoUser = (sessionQuery.data?.roles ?? []).includes("demo_client");
  const canCreateConversations = canAccessPage(currentUserPermissions, "conversas", "create");
  const canEditConversations = canAccessPage(currentUserPermissions, "conversas", "edit");
  const canDeleteConversations = canAccessPage(currentUserPermissions, "conversas", "delete");

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilterId>("all");
  const [unitFilter, setUnitFilter] = useState("all");
  const [ownerFilter, setOwnerFilter] = useState("all");
  const [priorityFilter, setPriorityFilter] = useState<PriorityFilter>("all");

  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [draftMessage, setDraftMessage] = useState("");
  const [internalNote, setInternalNote] = useState("");
  const [selectedAttachment, setSelectedAttachment] = useState<File | null>(null);
  const [replyingToMessage, setReplyingToMessage] = useState<MessageItem | null>(null);
  const [pinnedMessageIds, setPinnedMessageIds] = useState<string[]>([]);
  const [favoriteMessageIds, setFavoriteMessageIds] = useState<string[]>([]);
  const [selectedMessageIds, setSelectedMessageIds] = useState<string[]>([]);

  const [closeDialogOpen, setCloseDialogOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [actionsOpen, setActionsOpen] = useState(false);
  const [aiAssistOpen, setAiAssistOpen] = useState(false);
  const [aiSummaryOpen, setAiSummaryOpen] = useState(false);
  const [aiSummaryMode, setAiSummaryMode] = useState<"viewer" | "composer">("viewer");
  const [internalNoteOpen, setInternalNoteOpen] = useState(false);
  const [aiSuggestion, setAiSuggestion] = useState("");
  const [aiIntent, setAiIntent] = useState("");
  const [aiSuggestionPrompt, setAiSuggestionPrompt] = useState("");
  const [aiSummaryPrompt, setAiSummaryPrompt] = useState("");
  const [aiSummaryPreview, setAiSummaryPreview] = useState("");
  const [isDesktopLayout, setIsDesktopLayout] = useState(false);
  const [demoWhatsAppExperienceStage, setDemoWhatsAppExperienceStage] = useState<DemoWhatsAppExperienceStage>("idle");
  const [demoWhatsAppEntryPhone, setDemoWhatsAppEntryPhone] = useState<string | null>(null);
  const [demoWhatsAppEntryLink, setDemoWhatsAppEntryLink] = useState<string | null>(null);
  const [demoEntryChannel, setDemoEntryChannel] = useState<"whatsapp" | "webchat" | null>(null);
  const [demoPublicEntryPath, setDemoPublicEntryPath] = useState<string | null>(null);
  const [demoWorkspacePanel, setDemoWorkspacePanel] = useState<"whatsapp" | "webchat">("whatsapp");
  const [demoWorkspaceDragOffset, setDemoWorkspaceDragOffset] = useState(0);
  const [demoWebchatLaunchToken, setDemoWebchatLaunchToken] = useState(0);
  const [demoWhatsAppStartedAt, setDemoWhatsAppStartedAt] = useState<string | null>(null);
  const [demoWhatsAppTrackedConversationId, setDemoWhatsAppTrackedConversationId] = useState<string | null>(null);
  const [demoWhatsAppTrackedPatientId, setDemoWhatsAppTrackedPatientId] = useState<string | null>(null);
  const [demoWhatsAppBaselineAppointmentIds, setDemoWhatsAppBaselineAppointmentIds] = useState<string[]>([]);
  const [demoAgendaRedirectCountdown, setDemoAgendaRedirectCountdown] = useState<number | null>(null);
  const [demoGuideState, setDemoGuideState] = useState<DemoGuideClientState>(emptyDemoGuideClientState);
  const [demoConversationStage, setDemoConversationStage] = useState<DemoConversationTourStage>("idle");
  const [demoConversationCountdown, setDemoConversationCountdown] = useState<number | null>(null);
  const [demoSimulationMessages, setDemoSimulationMessages] = useState<DemoSimulationMessage[]>([]);
  const [demoEntryShortcutStyle, setDemoEntryShortcutStyle] = useState<CSSProperties | null>(null);

  const messageListRef = useRef<HTMLDivElement | null>(null);
  const demoWorkspaceViewportRef = useRef<HTMLDivElement | null>(null);
  const draftMessageRef = useRef<HTMLTextAreaElement | null>(null);
  const actionsMenuRef = useRef<HTMLDivElement | null>(null);
  const aiAssistPanelRef = useRef<HTMLDivElement | null>(null);
  const aiSummaryPanelRef = useRef<HTMLDivElement | null>(null);
  const notePanelRef = useRef<HTMLDivElement | null>(null);
  const conversationListPanelRef = useRef<HTMLElement | null>(null);
  const conversationPanelRef = useRef<HTMLElement | null>(null);
  const conversationCardRef = useRef<HTMLDivElement | null>(null);
  const composerCardRef = useRef<HTMLDivElement | null>(null);
  const demoEntryShortcutAnchorRef = useRef<HTMLDivElement | null>(null);
  const seenMessageIdsRef = useRef<Map<string, Set<string>>>(new Map());
  const bootstrappedConversationsRef = useRef<Set<string>>(new Set());
  const demoGuideSequenceStartedRef = useRef(false);
  const demoGuideSequenceFinishedRef = useRef(false);
  const demoGuideSequenceTimersRef = useRef<number[]>([]);
  const demoTrackedAppointmentHandledRef = useRef(false);
  const demoSimulationIndexRef = useRef(0);
  const demoSimulationRunningRef = useRef(false);
  const demoLaunchButtonPointerHandledRef = useRef(false);
  const startDemoConversationSequenceRef = useRef<() => void>(() => undefined);
  const stopDemoConversationSequenceRef = useRef<(nextStage: DemoConversationTourStage) => void>(() => undefined);
  const demoWorkspaceSwipeRef = useRef<{ startX: number; panel: "whatsapp" | "webchat" } | null>(null);

  const aiSettingsQuery = useQuery<{ global?: { enabled?: boolean } }>({
    queryKey: ["ai-autoresponder-settings"],
    queryFn: async () => (await api.get("/settings/ai-autoresponder/config")).data,
  });

  const inboxQuery = useQuery<InboxDataset>({
    queryKey: ["inbox-dataset", selectedOwnerUnitId ?? "all", focusConversationId ?? "default"],
    queryFn: async () => {
      const [
        conversationsResponse,
        usersResponse,
        patientsResponse,
        unitsResponse,
        leadsResponse,
        appointmentsResponse,
        documentsResponse,
      ] = await Promise.all([
        api.get<ApiPage<ConversationItem>>("/conversations", {
          params: { limit: 300, offset: 0, unit_id: selectedOwnerUnitId ?? undefined },
        }),
        api.get<ApiPage<UserItem>>("/users", { params: { limit: 100, offset: 0 } }),
        api.get<ApiPage<PatientItem>>("/patients", {
          params: { limit: 100, offset: 0, unit_id: selectedOwnerUnitId ?? undefined },
        }),
        api.get<ApiPage<UnitItem>>("/units", { params: { limit: 100, offset: 0 } }),
        api.get<ApiPage<LeadItem>>("/leads", {
          params: { limit: 100, offset: 0, unit_id: selectedOwnerUnitId ?? undefined },
        }),
        api.get<ApiPage<AppointmentItem>>("/appointments", {
          params: { limit: 100, offset: 0, unit_id: selectedOwnerUnitId ?? undefined },
        }),
        api.get<ApiPage<DocumentItem>>("/documents", {
          params: { limit: 100, offset: 0, unit_id: selectedOwnerUnitId ?? undefined },
        }),
      ]);

      return {
        conversations: conversationsResponse.data.data ?? [],
        users: usersResponse.data.data ?? [],
        patients: patientsResponse.data.data ?? [],
        units: unitsResponse.data.data ?? [],
        leads: leadsResponse.data.data ?? [],
        appointments: appointmentsResponse.data.data ?? [],
        documents: documentsResponse.data.data ?? [],
      };
    },
    refetchInterval: 7000,
    refetchOnWindowFocus: true,
  });

  const messagesQuery = useQuery<MessageResponse>({
    queryKey: ["conversation-messages", selectedConversationId],
    queryFn: async () =>
      (
        await api.get<MessageResponse>("/messages", {
          params: { conversation_id: selectedConversationId, limit: 200, offset: 0 },
        })
      ).data,
    enabled: Boolean(selectedConversationId),
    refetchInterval: selectedConversationId ? 2500 : false,
    refetchOnWindowFocus: true,
  });

  const aiDecisionsQuery = useQuery<AIDecisionResponse>({
    queryKey: ["conversation-ai-decisions", selectedConversationId],
    queryFn: async () =>
      (
        await api.get<AIDecisionResponse>(`/conversations/${selectedConversationId}/ai-autoresponder/decisions`, {
          params: { limit: 20 },
        })
      ).data,
    enabled: Boolean(selectedConversationId),
    refetchInterval: selectedConversationId ? 5000 : false,
    refetchOnWindowFocus: true,
  });

  const toggleMessageCollection = (
    current: string[],
    messageId: string,
  ) => (current.includes(messageId) ? current.filter((id) => id !== messageId) : [...current, messageId]);

  const handleReplyToMessage = (message: MessageItem) => {
    setReplyingToMessage(message);
    draftMessageRef.current?.focus();
  };

  const handleCopyMessage = async (message: MessageItem) => {
    const content = messageReadableContent(message);
    if (!content) {
      toast.info("Essa mensagem não tem texto disponível para copiar.");
      return;
    }
    await navigator.clipboard.writeText(content);
    toast.success("Conteúdo copiado.");
  };

  const fetchMessageAudioBlob = async (message: MessageItem) => {
    const response = await api.get<Blob>(`/messages/${message.id}/media`, { responseType: "blob" });
    const blob = response.data instanceof Blob ? response.data : new Blob([response.data]);
    return { blob, fileName: buildAudioDownloadFileName(message) };
  };

  const handleSaveMessage = async (message: MessageItem) => {
    if (isAudioMessageType(message.message_type)) {
      const { blob, fileName } = await fetchMessageAudioBlob(message);
      await triggerBlobDownload(blob, fileName);
      toast.success("Áudio salvo com sucesso.");
      return;
    }

    const content = messageReadableContent(message) || "Mensagem sem texto.";
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    await triggerBlobDownload(blob, buildTextDownloadFileName(message));
    toast.success("Mensagem salva em arquivo.");
  };

  const handleShareMessage = async (message: MessageItem) => {
    const content = messageReadableContent(message) || "Mensagem sem texto.";

    if (isAudioMessageType(message.message_type)) {
      const { blob, fileName } = await fetchMessageAudioBlob(message);
      const shareApi = navigator as Navigator & {
        canShare?: (payload?: ShareData) => boolean;
      };
      const audioFile = new File([blob], fileName, { type: blob.type || "audio/ogg" });

      if (navigator.share && shareApi.canShare?.({ files: [audioFile] })) {
        await navigator.share({
          files: [audioFile],
          title: fileName,
          text: content && !isAudioPlaceholderBody(content) ? content : `Audio recebido no ${BRAND_NAME}`,
        });
        return;
      }
    }

    if (navigator.share) {
      await navigator.share({ text: content });
      return;
    }

    await navigator.clipboard.writeText(content);
    toast.success("Mensagem copiada para compartilhamento.");
  };

  const handleForwardMessage = (message: MessageItem) => {
    const content = messageReadableContent(message);
    if (!content) {
      toast.info("Essa mensagem não tem conteúdo disponível para encaminhar.");
      return;
    }
    setDraftMessage((current) => (current ? `${current}\n\n${content}` : content));
    draftMessageRef.current?.focus();
    toast.success("Conteúdo inserido no campo de mensagem para encaminhamento.");
  };

  useEffect(() => {
    setReplyingToMessage(null);
    setSelectedMessageIds([]);
  }, [selectedConversationId]);

  const sendMessageMutation = useMutation({
    mutationFn: async () => {
      if (!canCreateConversations) {
        throw new Error("Seu perfil nao pode enviar mensagens nesta pagina.");
      }
      const attachmentLabel = selectedAttachment ? `\n\n[Anexo enviado: ${selectedAttachment.name}]` : "";
      return api.post("/messages", {
        conversation_id: selectedConversationId,
        body: `${draftMessage.trim()}${attachmentLabel}`,
        message_type: "text",
      });
    },
    onSuccess: () => {
      setDraftMessage("");
      setSelectedAttachment(null);
      setReplyingToMessage(null);
      toast.success("Mensagem enviada para a fila de entrega.");
      queryClient.invalidateQueries({ queryKey: ["conversation-messages", selectedConversationId] });
      queryClient.invalidateQueries({ queryKey: ["inbox-dataset"] });
    },
    onError: (error: unknown) => {
      const apiMessage =
        typeof error === "object" &&
        error &&
        "response" in error &&
        typeof (error as { response?: { data?: { error?: { message?: string } } } }).response?.data?.error?.message === "string"
          ? (error as { response?: { data?: { error?: { message?: string } } } }).response?.data?.error?.message
          : null;
      toast.error(apiMessage || "Não foi possível enviar a mensagem.");
    },
  });

  const assignMutation = useMutation({
    mutationFn: async (assignedUserId: string | null) => {
      if (!canEditConversations) {
        throw new Error("Seu perfil nao pode editar conversas nesta pagina.");
      }
      return api.patch(`/conversations/${selectedConversationId}`, { assigned_user_id: assignedUserId });
    },
    onSuccess: () => {
      toast.success("Responsável atualizado.");
      queryClient.invalidateQueries({ queryKey: ["inbox-dataset"] });
    },
    onError: () => toast.error("Não foi possível atualizar o responsável."),
  });

  const closeConversationMutation = useMutation({
    mutationFn: async () => {
      if (!canDeleteConversations) {
        throw new Error("Seu perfil nao pode encerrar conversas nesta pagina.");
      }
      return api.patch(`/conversations/${selectedConversationId}`, { status: "finalizada" });
    },
    onSuccess: () => {
      toast.success("Conversa encerrada.");
      setCloseDialogOpen(false);
      queryClient.invalidateQueries({ queryKey: ["inbox-dataset"] });
    },
    onError: () => toast.error("Não foi possível encerrar a conversa."),
  });

  const summarizeMutation = useMutation({
    mutationFn: async ({
      additionalContext,
    }: {
      additionalContext?: string;
      revealPanel?: boolean;
    } = {}) => {
      if (!canEditConversations) {
        throw new Error("Seu perfil nao pode atualizar o resumo desta conversa.");
      }
      const trimmedContext = additionalContext?.trim();
      return (
        await api.post<AISummaryResponse>(
          `/conversations/${selectedConversationId}/summarize`,
          trimmedContext ? { additional_context: trimmedContext } : {},
        )
      ).data;
    },
    onSuccess: (data, variables) => {
      const nextSummary = typeof data?.summary === "string" ? data.summary.trim() : "";
      if (nextSummary) {
        setAiSummaryPreview(nextSummary);
      }
      setAiSummaryPrompt("");
      setAiSummaryMode("viewer");
      if (variables?.revealPanel) {
        setAiSummaryOpen(true);
      }
      toast.success("Resumo IA atualizado.");
      queryClient.invalidateQueries({ queryKey: ["inbox-dataset"] });
    },
    onError: () => toast.error("Falha ao gerar resumo IA."),
  });

  const suggestionMutation = useMutation({
    mutationFn: async () => {
      if (!canEditConversations) {
        throw new Error("Seu perfil nao pode gerar sugestões nesta conversa.");
      }
      const prompt = aiSuggestionPrompt.trim();
      return (await api.post(`/messages/${selectedConversationId}/ai-suggestion`, prompt ? { prompt } : {})).data;
    },
    onSuccess: (data) => {
      const suggestedReply = typeof data?.suggested_reply === "string" ? data.suggested_reply.trim() : "";
      if (!suggestedReply) {
        toast.error("A IA nao retornou uma sugestao valida para esta conversa.");
        return;
      }

      setDraftMessage(suggestedReply);
      setAiSuggestion("");
      setAiIntent("");
      setAiSuggestionPrompt("");
      setAiAssistOpen(false);
      draftMessageRef.current?.focus();
      toast.success("Sugestao IA inserida no campo de mensagem.");
      return;
    },
    onError: () => toast.error("Não foi possível obter a sugestão IA."),
  });

  const toggleAiMutation = useMutation({
    mutationFn: async (enabled: boolean) => {
      if (!canEditConversations) {
        throw new Error("Seu perfil nao pode alterar a IA desta conversa.");
      }
      return api.put(`/conversations/${selectedConversationId}/ai-autoresponder`, { enabled });
    },
    onSuccess: (_, enabled) => {
      toast.success(enabled ? "IA ativada para esta conversa." : "IA desativada para esta conversa.");
      queryClient.invalidateQueries({ queryKey: ["inbox-dataset"] });
      queryClient.invalidateQueries({ queryKey: ["conversation-ai-decisions", selectedConversationId] });
    },
    onError: () => toast.error("Não foi possível alterar o modo IA da conversa."),
  });

  const convertLeadMutation = useMutation({
    mutationFn: async () => {
      if (!canEditConversations) {
        throw new Error("Seu perfil nao pode converter lead nesta pagina.");
      }
      const conversation = (inboxQuery.data?.conversations ?? []).find((item) => item.id === selectedConversationId);
      if (!conversation?.lead_id) throw new Error("Conversa sem lead vinculado.");

      const lead = (inboxQuery.data?.leads ?? []).find((item) => item.id === conversation.lead_id);
      if (!lead) throw new Error("Lead não encontrado para conversão.");
      if (lead.patient_id) {
        await api.patch(`/leads/${lead.id}`, { stage: "qualificado" });
        return;
      }
      if (!lead.phone) throw new Error("Lead sem telefone para conversão.");

      const patient = await api.post<{ id: string }>("/patients", {
        full_name: lead.name,
        phone: lead.phone,
        email: lead.email || null,
        status: "ativo",
        origin: lead.origin || "whatsapp",
        tags: ["lead_convertido"],
      });

      await api.patch(`/leads/${lead.id}`, { patient_id: patient.data.id, stage: "qualificado" });
      await api.patch(`/conversations/${conversation.id}`, { patient_id: patient.data.id });
    },
    onSuccess: () => {
      toast.success("Lead convertido em paciente com sucesso.");
      queryClient.invalidateQueries({ queryKey: ["inbox-dataset"] });
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : "Não foi possível converter o lead.";
      toast.error(message);
    },
  });

  const dataset = inboxQuery.data;
  const usersById = useMemo(
    () => new Map((dataset?.users ?? []).map((item) => [item.id, item.full_name])),
    [dataset?.users],
  );
  const patientsById = useMemo(
    () => new Map((dataset?.patients ?? []).map((item) => [item.id, item])),
    [dataset?.patients],
  );
  const unitsById = useMemo(
    () => new Map((dataset?.units ?? []).map((item) => [item.id, item.name])),
    [dataset?.units],
  );
  const leadsById = useMemo(
    () => new Map((dataset?.leads ?? []).map((item) => [item.id, item])),
    [dataset?.leads],
  );

  const filteredConversations = useMemo(() => {
    const items = dataset?.conversations ?? [];
    const term = search.toLowerCase().trim();

    return items.filter((conversation) => {
      const patient = conversation.patient_id ? patientsById.get(conversation.patient_id) : null;
      const lead = conversation.lead_id ? leadsById.get(conversation.lead_id) : null;
      const ownerName = conversation.assigned_user_id ? usersById.get(conversation.assigned_user_id) ?? "" : "";
      const priority = conversationPriority(conversation);

      const haystack = `${patient?.full_name ?? ""} ${lead?.name ?? ""} ${ownerName} ${conversation.channel} ${
        conversation.ai_summary ?? ""
      }`.toLowerCase();

      const byStatus =
        statusFilter === "all" ||
        conversation.status === statusFilter ||
        (statusFilter === "nao_respondida" && isNoReplyConversation(conversation));
      const bySearch = !term || haystack.includes(term);
      const byUnit = unitFilter === "all" || conversation.unit_id === unitFilter;
      const byOwner = ownerFilter === "all" || conversation.assigned_user_id === ownerFilter;
      const byPriority = priorityFilter === "all" || priority === priorityFilter;

      return byStatus && bySearch && byUnit && byOwner && byPriority;
    });
  }, [dataset?.conversations, leadsById, ownerFilter, patientsById, priorityFilter, search, statusFilter, unitFilter, usersById]);

  const advancedFilterCount =
    Number(statusFilter !== "all" && !QUICK_FILTERS.some((item) => item.id === statusFilter)) +
    Number(unitFilter !== "all") +
    Number(ownerFilter !== "all") +
    Number(priorityFilter !== "all");

  const filteredByQuickCounts = useMemo(() => {
    const items = (dataset?.conversations ?? []).filter((conversation) => {
      const patient = conversation.patient_id ? patientsById.get(conversation.patient_id) : null;
      const lead = conversation.lead_id ? leadsById.get(conversation.lead_id) : null;
      const ownerName = conversation.assigned_user_id ? usersById.get(conversation.assigned_user_id) ?? "" : "";
      const priority = conversationPriority(conversation);
      const term = search.toLowerCase().trim();
      const haystack = `${patient?.full_name ?? ""} ${lead?.name ?? ""} ${ownerName} ${conversation.channel} ${
        conversation.ai_summary ?? ""
      }`.toLowerCase();

      return (
        (!term || haystack.includes(term)) &&
        (unitFilter === "all" || conversation.unit_id === unitFilter) &&
        (ownerFilter === "all" || conversation.assigned_user_id === ownerFilter) &&
        (priorityFilter === "all" || priority === priorityFilter)
      );
    });

    return {
      all: items.length,
      aguardando: items.filter((item) => item.status === "aguardando").length,
      nao_respondida: items.filter((item) => isNoReplyConversation(item)).length,
    };
  }, [dataset?.conversations, leadsById, ownerFilter, patientsById, priorityFilter, search, unitFilter, usersById]);

  useEffect(() => {
    if (!ownerUnitScope.canSwitchUnits) return;
    setUnitFilter(ownerUnitScope.selectedUnitId);
  }, [ownerUnitScope.canSwitchUnits, ownerUnitScope.selectedUnitId]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const media = window.matchMedia("(min-width: 1024px)");
    const syncLayout = () => setIsDesktopLayout(media.matches);
    const handleMediaChange = (event: MediaQueryListEvent) => setIsDesktopLayout(event.matches);

    syncLayout();
    media.addEventListener("change", handleMediaChange);
    return () => media.removeEventListener("change", handleMediaChange);
  }, []);

  useEffect(() => {
    if (!isDemoUser) {
      setDemoWhatsAppExperienceStage("idle");
      setDemoWhatsAppEntryPhone(null);
      setDemoWhatsAppEntryLink(null);
      setDemoEntryChannel(null);
      setDemoPublicEntryPath(null);
      setDemoWhatsAppStartedAt(null);
      setDemoWhatsAppTrackedConversationId(null);
      setDemoWhatsAppTrackedPatientId(null);
      setDemoWhatsAppBaselineAppointmentIds([]);
      setDemoAgendaRedirectCountdown(null);
      demoTrackedAppointmentHandledRef.current = false;
      return;
    }

    const entry = readDemoWhatsAppEntry();
    setDemoWhatsAppEntryPhone(entry.testPhoneNumber);
    setDemoWhatsAppEntryLink(entry.whatsappLink);
    setDemoEntryChannel(entry.entryChannel || (entry.whatsappLink ? "whatsapp" : null));
    setDemoPublicEntryPath(entry.publicEntryPath);
    setDemoWhatsAppStartedAt(entry.startedAt);
    setDemoWhatsAppTrackedConversationId(entry.trackedConversationId);
    setDemoWhatsAppTrackedPatientId(entry.trackedPatientId);
    setDemoWhatsAppBaselineAppointmentIds(entry.baselineAppointmentIds);
    demoTrackedAppointmentHandledRef.current = false;

    if (entry.stage === "appointment_ready") {
      setDemoWhatsAppExperienceStage("appointment_ready");
      setDemoAgendaRedirectCountdown(DEMO_WHATSAPP_AGENDA_REDIRECT_SECONDS);
      return;
    }

    if (entry.stage === "awaiting_appointment") {
      setDemoWhatsAppExperienceStage("awaiting_appointment");
      setDemoAgendaRedirectCountdown(null);
      return;
    }

    if (!entry.active) {
      setDemoWhatsAppExperienceStage("idle");
      setDemoAgendaRedirectCountdown(null);
      return;
    }

    setDemoWhatsAppExperienceStage("entry");
    setDemoAgendaRedirectCountdown(null);
  }, [isDemoUser]);

  useEffect(() => {
    if (demoWhatsAppExperienceStage !== "appointment_ready" || demoAgendaRedirectCountdown === null) return;

    const timerId = window.setTimeout(() => {
      if ((demoAgendaRedirectCountdown ?? 0) <= 1) {
        redirectDemoToAgenda();
        return;
      }
      setDemoAgendaRedirectCountdown((current) => (current === null ? current : current - 1));
    }, DEMO_TOUR_COUNTDOWN_STEP_MS);

    return () => window.clearTimeout(timerId);
  }, [demoAgendaRedirectCountdown, demoWhatsAppExperienceStage]);


  useEffect(() => {
    const focusedFromStorage = localStorage.getItem("odontoflux_focus_conversation");
    const preferredConversationId = focusHandled ? null : focusConversationId || focusedFromStorage;

    if (preferredConversationId) {
      const foundInFiltered = filteredConversations.some((item) => item.id === preferredConversationId);
      if (foundInFiltered) {
        if (selectedConversationId !== preferredConversationId) {
          setSelectedConversationId(preferredConversationId);
        }
        localStorage.removeItem("odontoflux_focus_conversation");
        setFocusHandled(true);
        return;
      }

      const existsInDataset = (dataset?.conversations ?? []).some((item) => item.id === preferredConversationId);
      if (existsInDataset) {
        if (
          search !== "" ||
          statusFilter !== "all" ||
          unitFilter !== "all" ||
          ownerFilter !== "all" ||
          priorityFilter !== "all"
        ) {
          setSearch("");
          setStatusFilter("all");
          setUnitFilter("all");
          setOwnerFilter("all");
          setPriorityFilter("all");
        }
        if (selectedConversationId !== preferredConversationId) {
          setSelectedConversationId(preferredConversationId);
        }
        localStorage.removeItem("odontoflux_focus_conversation");
        setFocusHandled(true);
        return;
      }
    }

    const selectedStillVisible = selectedConversationId
      ? filteredConversations.some((item) => item.id === selectedConversationId)
      : false;

    if (filteredConversations.length === 0) {
      if (selectedConversationId) setSelectedConversationId(null);
      return;
    }

    if (selectedConversationId && !selectedStillVisible) {
      if (isDesktopLayout) {
        setSelectedConversationId(filteredConversations[0].id);
      } else {
        setSelectedConversationId(null);
      }
      return;
    }

    if (!selectedConversationId && isDesktopLayout) {
      setSelectedConversationId(filteredConversations[0].id);
    }
  }, [
    dataset?.conversations,
    filteredConversations,
    focusConversationId,
    focusHandled,
    isDesktopLayout,
    ownerFilter,
    priorityFilter,
    search,
    selectedConversationId,
    statusFilter,
    unitFilter,
  ]);

  useEffect(() => {
    setFocusHandled(false);
  }, [focusConversationId]);

  useEffect(() => {
    setAiSuggestion("");
    setAiIntent("");
    setAiSuggestionPrompt("");
    setAiSummaryPrompt("");
    setAiSummaryPreview("");
    setActionsOpen(false);
    setAiAssistOpen(false);
    setAiSummaryOpen(false);
    setAiSummaryMode("viewer");
    setInternalNoteOpen(false);
  }, [selectedConversationId]);

  useEffect(() => {
    if (!selectedConversationId) {
      setDetailsOpen(false);
      return;
    }

    const messages = messagesQuery.data?.data ?? [];
    const currentIds = new Set(messages.map((message) => message.id));

    if (!bootstrappedConversationsRef.current.has(selectedConversationId)) {
      bootstrappedConversationsRef.current.add(selectedConversationId);
      seenMessageIdsRef.current.set(selectedConversationId, currentIds);
    } else {
      const previousIds = seenMessageIdsRef.current.get(selectedConversationId) ?? new Set<string>();
      const newInboundCount = messages.filter(
        (message) => !previousIds.has(message.id) && message.direction === "inbound",
      ).length;
      if (newInboundCount > 0) {
        toast.info(
          newInboundCount === 1
            ? "Nova mensagem recebida na conversa."
            : `${newInboundCount} novas mensagens recebidas na conversa.`,
        );
      }
      seenMessageIdsRef.current.set(selectedConversationId, currentIds);
    }

    const container = messageListRef.current;
    if (container) {
      container.scrollTop = container.scrollHeight;
    }
  }, [messagesQuery.data?.data, selectedConversationId]);

  useEffect(() => {
    if (!actionsOpen && !aiAssistOpen && !aiSummaryOpen && !internalNoteOpen) return;

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (actionsOpen && !actionsMenuRef.current?.contains(target)) {
        setActionsOpen(false);
      }
      if (aiAssistOpen && !aiAssistPanelRef.current?.contains(target)) {
        setAiAssistOpen(false);
      }
      if (aiSummaryOpen && !aiSummaryPanelRef.current?.contains(target)) {
        setAiSummaryOpen(false);
      }
      if (internalNoteOpen && !notePanelRef.current?.contains(target)) {
        setInternalNoteOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setActionsOpen(false);
      setAiAssistOpen(false);
      setAiSummaryOpen(false);
      setInternalNoteOpen(false);
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [actionsOpen, aiAssistOpen, aiSummaryOpen, internalNoteOpen]);

  const selectedConversation = useMemo(
    () => filteredConversations.find((item) => item.id === selectedConversationId) ?? null,
    [filteredConversations, selectedConversationId],
  );

  const demoTrackedPhoneDigits = useMemo(
    () => normalizePhoneForComparison(demoWhatsAppEntryPhone),
    [demoWhatsAppEntryPhone],
  );
  const demoResolvedPublicEntryPath = useMemo(
    () => resolveDemoPublicEntryPath(demoPublicEntryPath, sessionQuery.data?.tenant_slug),
    [demoPublicEntryPath, sessionQuery.data?.tenant_slug],
  );
  const demoWorkspaceWebchatSrc = useMemo(() => {
    const rawPath = String(demoResolvedPublicEntryPath || "").trim();
    if (!rawPath) return null;
    const embeddedPath = `${rawPath}${rawPath.includes("?") ? "&" : "?"}embed=demo-webchat`;
    if (demoWebchatLaunchToken <= 0) return embeddedPath;
    return `${embeddedPath}&demo_session_reset=${demoWebchatLaunchToken}`;
  }, [demoResolvedPublicEntryPath, demoWebchatLaunchToken]);
  const canResolveDemoConversationFromPhone =
    demoWhatsAppExperienceStage === "awaiting_appointment" || demoWhatsAppExperienceStage === "appointment_ready";

  const demoTrackedConversation = useMemo(() => {
    const conversations = dataset?.conversations ?? [];
    if (!conversations.length) return null;

    if (demoWhatsAppTrackedConversationId) {
      return conversations.find((item) => item.id === demoWhatsAppTrackedConversationId) ?? null;
    }

    if (!canResolveDemoConversationFromPhone) return null;

    if (demoEntryChannel === "webchat") {
      const webchatSessionId = readStoredWebchatSessionIdFromPublicEntryPath(demoResolvedPublicEntryPath);
      const linkedThreadId = webchatSessionId ? `link_flow:${webchatSessionId}` : null;
      if (linkedThreadId) {
        const directMatch = conversations.find((item) => item.external_thread_id === linkedThreadId) ?? null;
        if (directMatch) return directMatch;
      }

      const syntheticContact = webchatSyntheticContact(webchatSessionId);
      if (syntheticContact) {
        const syntheticPatientMatch =
          conversations.find((conversation) => {
            if (!conversation.patient_id) return false;
            const patientPhone = patientsById.get(conversation.patient_id)?.phone;
            return patientPhone === syntheticContact;
          }) ?? null;
        if (syntheticPatientMatch) return syntheticPatientMatch;
      }

      const startedAtMs = demoWhatsAppStartedAt ? new Date(demoWhatsAppStartedAt).getTime() : null;
      const webchatMatches = conversations.filter((conversation) => {
        if (conversation.channel !== "webchat") return false;
        if (!conversation.tags.includes("entry_webchat")) return false;
        if (startedAtMs === null || !conversation.last_message_at) return true;
        return new Date(conversation.last_message_at).getTime() >= startedAtMs - 60_000;
      });
      if (webchatMatches.length) {
        return webchatMatches.sort((left, right) => {
          const leftTime = left.last_message_at ? new Date(left.last_message_at).getTime() : 0;
          const rightTime = right.last_message_at ? new Date(right.last_message_at).getTime() : 0;
          return rightTime - leftTime;
        })[0];
      }
    }

    if (!demoTrackedPhoneDigits) return null;

    const matches = conversations.filter((conversation) => {
      const patientPhone = conversation.patient_id ? patientsById.get(conversation.patient_id)?.phone : null;
      const leadPhone = conversation.lead_id ? leadsById.get(conversation.lead_id)?.phone : null;
      return (
        normalizePhoneForComparison(patientPhone) === demoTrackedPhoneDigits ||
        normalizePhoneForComparison(leadPhone) === demoTrackedPhoneDigits
      );
    });

    if (!matches.length) return null;

    return matches.sort((left, right) => {
      const leftTime = left.last_message_at ? new Date(left.last_message_at).getTime() : 0;
      const rightTime = right.last_message_at ? new Date(right.last_message_at).getTime() : 0;
      return rightTime - leftTime;
    })[0];
  }, [
    demoEntryChannel,
    demoResolvedPublicEntryPath,
    canResolveDemoConversationFromPhone,
    dataset?.conversations,
    demoTrackedPhoneDigits,
    demoWhatsAppStartedAt,
    demoWhatsAppTrackedConversationId,
    leadsById,
    patientsById,
  ]);

  const globalAiEnabled = Boolean(aiSettingsQuery.data?.global?.enabled);
  const aiEnabledForConversation = (conversation: ConversationItem) =>
    conversation.ai_autoresponder_enabled ?? globalAiEnabled;

  const selectedPriority = selectedConversation ? conversationPriority(selectedConversation) : "baixa";
  const selectedPatient = selectedConversation?.patient_id
    ? patientsById.get(selectedConversation.patient_id) ?? null
    : null;
  const selectedLead = selectedConversation?.lead_id ? leadsById.get(selectedConversation.lead_id) ?? null : null;
  const selectedAiEnabled = selectedConversation ? aiEnabledForConversation(selectedConversation) : false;
  const selectedAiLastDecision = selectedConversation?.ai_autoresponder_last_decision ?? null;
  const selectedAiLastReason = selectedConversation?.ai_autoresponder_last_reason ?? null;
  const selectedAiDecisions = aiDecisionsQuery.data?.data ?? [];
  const selectedConversationName =
    selectedPatient?.full_name ?? selectedLead?.name ?? (selectedConversation ? "Contato sem identificação" : "");
  const selectedConversationPhone = selectedPatient?.phone ?? selectedLead?.phone ?? null;
  const effectiveAiSummary = (aiSummaryPreview || selectedConversation?.ai_summary || "").trim();
  const latestOutboundMessageId = useMemo(() => {
    const messages = messagesQuery.data?.data ?? [];
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      if (messages[index]?.direction === "outbound") {
        return messages[index]?.id ?? null;
      }
    }
    return null;
  }, [messagesQuery.data?.data]);
  const demoWhatsAppEntryPhoneLabel = demoWhatsAppEntryPhone ? formatPhoneBR(demoWhatsAppEntryPhone) : null;
  const demoUsesWebchatEntry = demoEntryChannel === "webchat";
  const demoWorkspaceEnabled = isDemoUser && demoUsesWebchatEntry && Boolean(demoResolvedPublicEntryPath);
  const demoWorkspaceOpen = demoWorkspaceEnabled && demoWorkspacePanel === "webchat";
  const showDemoEntryShortcut =
    isDemoUser &&
    ["entry", "awaiting_appointment"].includes(demoWhatsAppExperienceStage) &&
    !demoWorkspaceOpen &&
    Boolean(demoWhatsAppEntryLink || (demoUsesWebchatEntry && demoResolvedPublicEntryPath));
  const demoEntryShortcutLabel = demoUsesWebchatEntry
    ? demoWhatsAppExperienceStage === "entry"
      ? "Testar chat do site"
      : "Reabrir chat do site"
    : demoWhatsAppExperienceStage === "entry"
      ? "Abrir WhatsApp da demo"
      : "Reabrir WhatsApp";

  useEffect(() => {
    if (!showDemoEntryShortcut) {
      setDemoEntryShortcutStyle(null);
      return;
    }

    let frameId = 0;
    const updateShortcutPosition = () => {
      const anchor = demoEntryShortcutAnchorRef.current;
      if (!anchor) return;

      const rect = anchor.getBoundingClientRect();
      setDemoEntryShortcutStyle({
        top: Math.max(12, rect.top - 52),
        right: Math.max(12, window.innerWidth - rect.right),
      });
    };

    const scheduleShortcutPositionUpdate = () => {
      window.cancelAnimationFrame(frameId);
      frameId = window.requestAnimationFrame(updateShortcutPosition);
    };

    scheduleShortcutPositionUpdate();

    const anchor = demoEntryShortcutAnchorRef.current;
    const resizeObserver =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(() => {
            scheduleShortcutPositionUpdate();
          });

    if (anchor && resizeObserver) {
      resizeObserver.observe(anchor);
    }

    window.addEventListener("resize", scheduleShortcutPositionUpdate);
    window.addEventListener("scroll", scheduleShortcutPositionUpdate, true);

    return () => {
      window.cancelAnimationFrame(frameId);
      resizeObserver?.disconnect();
      window.removeEventListener("resize", scheduleShortcutPositionUpdate);
      window.removeEventListener("scroll", scheduleShortcutPositionUpdate, true);
    };
  }, [showDemoEntryShortcut, demoEntryShortcutLabel, selectedConversationId]);

  const demoTourConversationId =
    demoTrackedConversation?.id ??
    demoWhatsAppTrackedConversationId ??
    (isDemoUser && demoWhatsAppExperienceStage !== "idle" ? selectedConversationId : null);
  const demoTrackedPatient =
    demoTrackedConversation?.patient_id
      ? patientsById.get(demoTrackedConversation.patient_id) ?? null
      : demoWhatsAppTrackedPatientId
        ? patientsById.get(demoWhatsAppTrackedPatientId) ?? null
        : null;
  const showDemoAiInsight =
    isDemoUser &&
    selectedConversationId === demoTourConversationId &&
    Boolean(selectedAiLastDecision || selectedAiLastReason);
  const demoTrackedPatientAppointments = useMemo(() => {
    if (!demoTrackedPatient) return [];
    return (dataset?.appointments ?? [])
      .filter((item) => item.patient_id === demoTrackedPatient.id)
      .sort((left, right) => new Date(left.starts_at).getTime() - new Date(right.starts_at).getTime());
  }, [dataset?.appointments, demoTrackedPatient]);
  const demoTrackedThreadRect = messageListRef.current?.getBoundingClientRect() ?? null;

  useEffect(() => {
    if (!isDemoUser) return;
    if (!demoWhatsAppEntryLink && !(demoUsesWebchatEntry && demoResolvedPublicEntryPath)) return;
    if (!["entry", "awaiting_appointment"].includes(demoWhatsAppExperienceStage)) return;

    dispatchDemoTourEvent({
      type: "whatsapp_cta_ready",
      whatsappLink: demoWhatsAppEntryLink,
      phoneLabel: demoWhatsAppEntryPhoneLabel,
      entryChannel: demoEntryChannel,
      publicEntryPath: demoResolvedPublicEntryPath,
    });
  }, [
    demoEntryChannel,
    demoResolvedPublicEntryPath,
    demoUsesWebchatEntry,
    demoWhatsAppEntryLink,
    demoWhatsAppEntryPhoneLabel,
    demoWhatsAppExperienceStage,
    isDemoUser,
  ]);

  useEffect(() => {
    if (demoWorkspaceEnabled) return;
    setDemoWorkspacePanel("whatsapp");
    setDemoWorkspaceDragOffset(0);
    demoWorkspaceSwipeRef.current = null;
  }, [demoWorkspaceEnabled]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const detail: DemoWebchatWorkspaceDetail = { open: demoWorkspaceOpen };
    const scopedWindow = window as Window & { __odontofluxDemoWebchatWorkspaceOpen?: boolean };
    if (demoWorkspaceOpen) {
      document.documentElement.dataset.demoWebchatWorkspaceOpen = "true";
    } else {
      delete document.documentElement.dataset.demoWebchatWorkspaceOpen;
    }
    scopedWindow.__odontofluxDemoWebchatWorkspaceOpen = demoWorkspaceOpen;
    window.dispatchEvent(new CustomEvent(DEMO_WEBCHAT_WORKSPACE_EVENT_NAME, { detail }));
    return () => {
      delete document.documentElement.dataset.demoWebchatWorkspaceOpen;
      scopedWindow.__odontofluxDemoWebchatWorkspaceOpen = false;
      window.dispatchEvent(new CustomEvent(DEMO_WEBCHAT_WORKSPACE_EVENT_NAME, { detail: { open: false } }));
    };
  }, [demoWorkspaceOpen]);

  useEffect(() => {
    if (!isDemoUser) return;
    if (!demoTrackedConversation?.id) return;
    if (selectedConversationId !== demoTrackedConversation.id) return;

    dispatchDemoTourEvent({
      type: "conversation_detected",
      conversationId: demoTrackedConversation.id,
      patientId: demoTrackedPatient?.id ?? null,
    });
  }, [demoTrackedConversation?.id, demoTrackedPatient?.id, isDemoUser, selectedConversationId]);

  useEffect(() => {
    if (!showDemoAiInsight) return;

    dispatchDemoTourEvent({
      type: "ai_intent_detected",
      conversationId: demoTourConversationId ?? selectedConversationId ?? null,
    });
  }, [demoTourConversationId, selectedConversationId, showDemoAiInsight]);

  useEffect(() => {
    if (!isDemoUser) return;
    if (!latestOutboundMessageId) return;
    if (selectedConversationId !== demoTourConversationId) return;

    dispatchDemoTourEvent({
      type: "ai_response_detected",
      conversationId: demoTourConversationId ?? null,
    });
  }, [demoTourConversationId, isDemoUser, latestOutboundMessageId, selectedConversationId]);
  const demoConversationScript = useMemo(
    () => buildDemoConversationScript((dataset?.units ?? []).map((unit) => unit.name), selectedConversationName),
    [dataset?.units, selectedConversationName],
  );
  // The docked guide should support free exploration of the WhatsApp workspace,
  // not take over the screen with automatic spotlight/simulation overlays.
  const allowAutoDockedConversationSequence = false;
  const demoGuideDockedSequenceActive =
    allowAutoDockedConversationSequence &&
    isDemoUser &&
    demoGuideState.active &&
    demoGuideState.stepId === DEMO_GUIDE_CONVERSATION_STEP_ID &&
    demoGuideState.placement === "docked";

  const patientAppointments = useMemo(() => {
    if (!selectedPatient) return [];
    return (dataset?.appointments ?? [])
      .filter((item) => item.patient_id === selectedPatient.id)
      .sort((a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime());
  }, [dataset?.appointments, selectedPatient]);

  const patientDocuments = useMemo(() => {
    if (!selectedPatient) return [];
    return (dataset?.documents ?? [])
      .filter((item) => item.patient_id === selectedPatient.id)
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  }, [dataset?.documents, selectedPatient]);

  const nextAppointment =
    patientAppointments.find((item) => new Date(item.starts_at).getTime() >= Date.now()) ?? patientAppointments[0] ?? null;

  useEffect(() => {
    if (!isDemoUser) return;

    const handleDemoTourTestAction = (event: Event) => {
      const detail = (event as CustomEvent<DemoTourTestActionDetail>).detail;
      if (!detail) return;

      const conversation = demoTrackedConversation ?? selectedConversation ?? filteredConversations[0] ?? null;
      if (!conversation) {
        toast.error("Nenhuma conversa está disponível para testar a demo agora.");
        return;
      }

      const resolvedPatientId = conversation.patient_id ?? demoTrackedPatient?.id ?? selectedPatient?.id ?? null;
      setDemoWhatsAppTrackedConversationId(conversation.id);
      setDemoWhatsAppTrackedPatientId(resolvedPatientId);
      if (selectedConversationId !== conversation.id) {
        setSelectedConversationId(conversation.id);
      }

      dispatchDemoTourEvent({
        type: "conversation_detected",
        conversationId: conversation.id,
        patientId: resolvedPatientId,
      });
      dispatchDemoTourEvent({
        type: "ai_intent_detected",
        conversationId: conversation.id,
      });
      dispatchDemoTourEvent({
        type: "ai_response_detected",
        conversationId: conversation.id,
      });

      if (detail.action === "simulate_message") {
        toast.success("Mensagem simulada para teste da demo.");
        return;
      }

      const simulatedAppointments = (dataset?.appointments ?? [])
        .filter((item) => item.patient_id === resolvedPatientId)
        .filter((item) => !["cancelada", "falta"].includes(String(item.status || "").trim().toLowerCase()))
        .sort((left, right) => new Date(left.starts_at).getTime() - new Date(right.starts_at).getTime());
      const simulatedAppointment =
        simulatedAppointments.find((item) => new Date(item.starts_at).getTime() >= Date.now()) ??
        simulatedAppointments[0] ??
        nextAppointment;

      if (!simulatedAppointment) {
        toast.error("Nenhum agendamento disponível para concluir o teste completo da demo.");
        return;
      }

      dispatchDemoTourEvent({
        type: "appointment_detected",
        conversationId: conversation.id,
        patientId: resolvedPatientId,
        appointmentId: simulatedAppointment.id,
      });
      toast.success("Conversa completa e agendamento simulados para teste.");
    };

    window.addEventListener(DEMO_TOUR_TEST_ACTION_EVENT_NAME, handleDemoTourTestAction as EventListener);
    return () =>
      window.removeEventListener(DEMO_TOUR_TEST_ACTION_EVENT_NAME, handleDemoTourTestAction as EventListener);
  }, [
    dataset?.appointments,
    demoTrackedConversation,
    demoTrackedPatient?.id,
    filteredConversations,
    isDemoUser,
    nextAppointment,
    selectedConversation,
    selectedConversationId,
    selectedPatient?.id,
  ]);

  const openDemoWebchatWorkspace = useCallback(() => {
    const rawPath = String(demoResolvedPublicEntryPath || "").trim();
    if (rawPath) {
      try {
        const demoUrl = new URL(rawPath, window.location.origin);
        const [, clinicSlug] = demoUrl.pathname.split("/");
        if (clinicSlug) {
          window.localStorage.removeItem(`clinicflux.link_flow.webchat.${clinicSlug}`);
        }
      } catch {
        // Ignore malformed demo paths and let the embedded page recover normally.
      }
    }
    setDemoWebchatLaunchToken((current) => current + 1);
    setDemoWorkspacePanel("webchat");
    setDemoWorkspaceDragOffset(0);
  }, [demoResolvedPublicEntryPath]);

  const closeDemoWebchatWorkspace = useCallback(() => {
    setDemoWorkspacePanel("whatsapp");
    setDemoWorkspaceDragOffset(0);
  }, []);

  const launchDemoWhatsAppRedirect = useCallback((options?: { popup?: Window | null; openInWorkspace?: boolean }) => {
    if (demoUsesWebchatEntry) {
      if (!demoResolvedPublicEntryPath) {
        if (options?.popup && !options.popup.closed) {
          options.popup.close();
        }
        toast.error("Esta demo ainda nao tem uma landing publica de webchat configurada.");
        return;
      }

      const startedAt = new Date().toISOString();
      const baselineAppointmentIds = demoTrackedPatientAppointments.map((item) => item.id);

      markDemoWhatsAppAwaitingAppointment({
        startedAt,
        trackedConversationId: demoTrackedConversation?.id ?? null,
        trackedPatientId: demoTrackedPatient?.id ?? null,
        baselineAppointmentIds,
      });

      setDemoWhatsAppStartedAt(startedAt);
      setDemoWhatsAppTrackedConversationId(demoTrackedConversation?.id ?? null);
      setDemoWhatsAppTrackedPatientId(demoTrackedPatient?.id ?? null);
      setDemoWhatsAppBaselineAppointmentIds(baselineAppointmentIds);
      setDemoWhatsAppExperienceStage("awaiting_appointment");
      setDemoAgendaRedirectCountdown(null);
      demoTrackedAppointmentHandledRef.current = false;

      dispatchDemoTourEvent({
        type: "whatsapp_clicked",
        whatsappLink: null,
        phoneLabel: demoWhatsAppEntryPhoneLabel,
        entryChannel: demoEntryChannel,
        publicEntryPath: demoResolvedPublicEntryPath,
      });

      if (options?.popup && !options.popup.closed) {
        options.popup.close();
      }
      if (options?.openInWorkspace) {
        openDemoWebchatWorkspace();
        return;
      }

      if (options?.popup && !options.popup.closed) {
        options.popup.location.href = demoResolvedPublicEntryPath;
        return;
      }

      const popup = window.open(demoResolvedPublicEntryPath, "_blank", "noopener,noreferrer");
      if (!popup) {
        toast.error("Nao foi possivel abrir a landing publica da demo. Libere pop-ups para esta demo.");
      }
      return;
    }

    if (!demoWhatsAppEntryLink) {
      if (options?.popup && !options.popup.closed) {
        options.popup.close();
      }
      toast.error("Esta demo ainda nao tem um numero real de WhatsApp da clinica conectado.");
      return;
    }

    const startedAt = new Date().toISOString();
    const baselineAppointmentIds = demoTrackedPatientAppointments.map((item) => item.id);

    markDemoWhatsAppAwaitingAppointment({
      startedAt,
      trackedConversationId: demoTrackedConversation?.id ?? null,
      trackedPatientId: demoTrackedPatient?.id ?? null,
      baselineAppointmentIds,
    });

    setDemoWhatsAppStartedAt(startedAt);
    setDemoWhatsAppTrackedConversationId(demoTrackedConversation?.id ?? null);
    setDemoWhatsAppTrackedPatientId(demoTrackedPatient?.id ?? null);
    setDemoWhatsAppBaselineAppointmentIds(baselineAppointmentIds);
    setDemoWhatsAppExperienceStage("awaiting_appointment");
    setDemoAgendaRedirectCountdown(null);
    demoTrackedAppointmentHandledRef.current = false;

    dispatchDemoTourEvent({
      type: "whatsapp_clicked",
      whatsappLink: demoWhatsAppEntryLink,
      phoneLabel: demoWhatsAppEntryPhoneLabel,
      entryChannel: demoEntryChannel,
      publicEntryPath: demoResolvedPublicEntryPath,
    });

    if (options?.popup && !options.popup.closed) {
      options.popup.location.href = demoWhatsAppEntryLink;
      return;
    }

    const popup = window.open(demoWhatsAppEntryLink, "_blank", "noopener,noreferrer");
    if (!popup) {
      toast.error("Nao foi possivel abrir uma nova aba do WhatsApp. Libere pop-ups para esta demo.");
    }
  }, [
    demoEntryChannel,
    demoResolvedPublicEntryPath,
    demoUsesWebchatEntry,
    demoTrackedConversation?.id,
    demoTrackedPatient?.id,
    demoTrackedPatientAppointments,
    demoWhatsAppEntryLink,
    demoWhatsAppEntryPhoneLabel,
    openDemoWebchatWorkspace,
  ]);

  useEffect(() => {
    if (!isDemoUser) return;

    const handleDemoTourCommand = (event: Event) => {
      const detail = (event as CustomEvent<DemoTourCommandDetail>).detail;
      if (!detail) return;

      if (detail.type === "open_whatsapp") {
        launchDemoWhatsAppRedirect({
          popup: detail.popup ?? null,
          openInWorkspace: demoUsesWebchatEntry,
        });
        return;
      }

      if (detail.type === "close_webchat_workspace") {
        closeDemoWebchatWorkspace();
        return;
      }

      if (detail.type === "check_message") {
        if (demoTrackedConversation?.id) {
          setDemoWhatsAppTrackedConversationId(demoTrackedConversation.id);
          setDemoWhatsAppTrackedPatientId(demoTrackedPatient?.id ?? null);
          if (selectedConversationId !== demoTrackedConversation.id) {
            setSelectedConversationId(demoTrackedConversation.id);
          }
          dispatchDemoTourEvent({
            type: "conversation_detected",
            conversationId: demoTrackedConversation.id,
            patientId: demoTrackedPatient?.id ?? null,
          });
          return;
        }

        void inboxQuery.refetch();
      }
    };

    window.addEventListener(DEMO_TOUR_COMMAND_EVENT_NAME, handleDemoTourCommand as EventListener);
    return () =>
      window.removeEventListener(DEMO_TOUR_COMMAND_EVENT_NAME, handleDemoTourCommand as EventListener);
  }, [
    closeDemoWebchatWorkspace,
    demoUsesWebchatEntry,
    demoTrackedConversation?.id,
    demoTrackedPatient?.id,
    inboxQuery,
    isDemoUser,
    launchDemoWhatsAppRedirect,
    selectedConversationId,
  ]);

  function redirectDemoToAgenda() {
    clearDemoWhatsAppEntry();
    storeDemoEntryTargetPath("/agenda");
    setDemoWhatsAppExperienceStage("idle");
    setDemoAgendaRedirectCountdown(null);
    window.location.replace("/agenda");
  }

  useEffect(() => {
    if (!isDemoUser || !demoTrackedConversation) return;
    if (!["entry", "awaiting_appointment", "appointment_ready"].includes(demoWhatsAppExperienceStage)) return;
    if (selectedConversationId === demoTrackedConversation.id) return;
    setSelectedConversationId(demoTrackedConversation.id);
  }, [demoTrackedConversation, demoWhatsAppExperienceStage, isDemoUser, selectedConversationId]);

  useEffect(() => {
    if (demoWhatsAppExperienceStage !== "awaiting_appointment") return;
    if (demoTrackedAppointmentHandledRef.current) return;
    if (!demoTrackedConversation || !demoTrackedPatient) return;

    const startedAtMs = demoWhatsAppStartedAt ? new Date(demoWhatsAppStartedAt).getTime() : null;
    const lastMessageAtMs = demoTrackedConversation.last_message_at
      ? new Date(demoTrackedConversation.last_message_at).getTime()
      : null;
    const conversationFresh =
      startedAtMs === null || (lastMessageAtMs !== null && lastMessageAtMs >= startedAtMs - 60_000);
    const baselineIds = new Set(demoWhatsAppBaselineAppointmentIds);
    const activeDemoAppointments = demoTrackedPatientAppointments.filter((item) => {
      const origin = String(item.origin || "").trim().toLowerCase();
      return DEMO_APPOINTMENT_AUTO_ORIGINS.has(origin) && !["cancelada", "falta"].includes(item.status);
    });
    const newDemoAppointments = activeDemoAppointments.filter((item) => !baselineIds.has(item.id));
    const trackedAppointment = newDemoAppointments[0] ?? activeDemoAppointments[0] ?? null;
    const readyForAgenda =
      demoTrackedConversation.status === "finalizada" &&
      conversationFresh &&
      (newDemoAppointments.length > 0 || (baselineIds.size === 0 && activeDemoAppointments.length > 0));

    if (!readyForAgenda) return;

    demoTrackedAppointmentHandledRef.current = true;
    markDemoWhatsAppAppointmentReady();
    setDemoWhatsAppExperienceStage("appointment_ready");
    setDemoAgendaRedirectCountdown(null);
    setSelectedConversationId(demoTrackedConversation.id);
    dispatchDemoTourEvent({
      type: "appointment_detected",
      conversationId: demoTrackedConversation.id,
      patientId: demoTrackedPatient.id,
      appointmentId: trackedAppointment?.id ?? null,
    });
    void router.prefetch("/agenda");
    toast.success("Conversa finalizada com agendamento salvo. Vamos abrir a agenda.");
  }, [
    demoTrackedConversation,
    demoTrackedPatient,
    demoTrackedPatientAppointments,
    demoWhatsAppBaselineAppointmentIds,
    demoWhatsAppExperienceStage,
    demoWhatsAppStartedAt,
    router,
  ]);

  const unitOptions = ownerUnitScope.canSwitchUnits ? dataset?.units ?? [] : dataset?.units ?? [];

  const clearDemoGuideSequenceTimers = () => {
    for (const timerId of demoGuideSequenceTimersRef.current) {
      window.clearTimeout(timerId);
    }
    demoGuideSequenceTimersRef.current = [];
  };

  const scheduleDemoGuideSequenceStep = (callback: () => void, delayMs: number) => {
    const timerId = window.setTimeout(callback, delayMs);
    demoGuideSequenceTimersRef.current.push(timerId);
  };

  const dispatchDemoGuideNextStep = (source: string) => {
    window.dispatchEvent(
      new CustomEvent("odontoflux:demo-guide-complete-step", {
        detail: { stepId: DEMO_GUIDE_CONVERSATION_STEP_ID, source },
      }),
    );
  };

  const buildDemoSimulationMessage = (entry: Extract<DemoSimulationScriptEntry, { direction: "inbound" | "outbound" }>) => ({
    id: entry.id,
    direction: entry.direction,
    body: entry.body,
    delivery: entry.delivery ?? (entry.direction === "outbound" ? "read" : "delivered"),
    createdAt: new Date().toISOString(),
  });

  const scrollConversationToBottom = () => {
    const container = messageListRef.current;
    if (!container) return;
    container.scrollTop = container.scrollHeight;
  };

  const stopDemoConversationSequence = (nextStage: DemoConversationTourStage) => {
    clearDemoGuideSequenceTimers();
    demoSimulationRunningRef.current = false;
    setDemoConversationCountdown(null);
    setDemoConversationStage(nextStage);
  };

  const startDemoGuideFinishCountdown = (value: number) => {
    setDemoConversationStage("finish_countdown");
    setDemoConversationCountdown(value);

    if (value <= 1) {
      scheduleDemoGuideSequenceStep(() => {
        demoGuideSequenceFinishedRef.current = true;
        dispatchDemoGuideNextStep("demo_whatsapp_sequence_auto");
      }, DEMO_TOUR_COUNTDOWN_STEP_MS);
      return;
    }

    scheduleDemoGuideSequenceStep(() => startDemoGuideFinishCountdown(value - 1), DEMO_TOUR_COUNTDOWN_STEP_MS);
  };

  const continueDemoConversationSimulation = () => {
    if (!demoSimulationRunningRef.current) return;
    const nextEntry = demoConversationScript[demoSimulationIndexRef.current];

    if (!nextEntry) {
      startDemoGuideFinishCountdown(DEMO_TOUR_NEXT_STEP_COUNTDOWN_SECONDS);
      return;
    }

    if (nextEntry.kind === "pause_after_confirmation") {
      demoSimulationIndexRef.current += 1;
      demoSimulationRunningRef.current = false;
      setDemoConversationStage("appointment_saved_pause");
      scheduleDemoGuideSequenceStep(() => {
        demoSimulationRunningRef.current = true;
        setDemoConversationStage("simulation_running");
        continueDemoConversationSimulation();
      }, DEMO_TOUR_APPOINTMENT_PAUSE_DURATION_MS);
      return;
    }

    scheduleDemoGuideSequenceStep(() => {
      if (!demoSimulationRunningRef.current) return;
      setDemoSimulationMessages((current) => [...current, buildDemoSimulationMessage(nextEntry)]);
      demoSimulationIndexRef.current += 1;
      scheduleDemoGuideSequenceStep(scrollConversationToBottom, 80);
      continueDemoConversationSimulation();
    }, nextEntry.delayMs);
  };

  const startDemoConversationSimulation = () => {
    clearDemoGuideSequenceTimers();
    setDemoConversationCountdown(null);
    setDemoConversationStage("simulation_running");
    demoSimulationRunningRef.current = true;
    continueDemoConversationSimulation();
  };

  const startDemoConversationFocus = () => {
    clearDemoGuideSequenceTimers();
    setDemoConversationStage("conversation_focus");
    scheduleDemoGuideSequenceStep(startDemoConversationSimulation, DEMO_TOUR_CONVERSATION_FOCUS_DURATION_MS);
  };

  const startDemoConversationCountdown = (value: number) => {
    setDemoConversationStage("automation_countdown");
    setDemoConversationCountdown(value);

    if (value <= 1) {
      scheduleDemoGuideSequenceStep(() => {
        setDemoConversationCountdown(null);
        startDemoConversationFocus();
      }, DEMO_TOUR_COUNTDOWN_STEP_MS);
      return;
    }

    scheduleDemoGuideSequenceStep(() => startDemoConversationCountdown(value - 1), DEMO_TOUR_COUNTDOWN_STEP_MS);
  };

  const startDemoConversationSequence = () => {
    clearDemoGuideSequenceTimers();
    demoSimulationRunningRef.current = false;
    demoSimulationIndexRef.current = 0;
    setDemoSimulationMessages([]);
    setDemoConversationCountdown(null);
    setAiAssistOpen(false);
    setAiSummaryOpen(false);
    setAiSummaryMode("viewer");
    setInternalNoteOpen(false);
    setDemoConversationStage("suggestion_spotlight");

    scheduleDemoGuideSequenceStep(() => {
      setAiAssistOpen(false);
      setDemoConversationStage("summary_spotlight");
      scheduleDemoGuideSequenceStep(() => {
        setAiSummaryOpen(false);
        startDemoConversationCountdown(3);
      }, DEMO_TOUR_SPOTLIGHT_DURATION_MS);
    }, DEMO_TOUR_SPOTLIGHT_DURATION_MS);
  };

  startDemoConversationSequenceRef.current = startDemoConversationSequence;
  stopDemoConversationSequenceRef.current = stopDemoConversationSequence;

  useEffect(() => {
    if (typeof window === "undefined") return;

    const scopedWindow = window as Window & { __odontofluxDemoGuideState?: DemoGuideClientState };
    if (scopedWindow.__odontofluxDemoGuideState) {
      setDemoGuideState(scopedWindow.__odontofluxDemoGuideState);
    }

    const handleGuideStateUpdate = (event: Event) => {
      setDemoGuideState((event as CustomEvent<DemoGuideClientState>).detail ?? emptyDemoGuideClientState());
    };

    window.addEventListener("odontoflux:demo-guide-state", handleGuideStateUpdate as EventListener);
    return () => window.removeEventListener("odontoflux:demo-guide-state", handleGuideStateUpdate as EventListener);
  }, []);

  useEffect(() => {
    return () => clearDemoGuideSequenceTimers();
  }, []);

  useEffect(() => {
    if (!demoGuideDockedSequenceActive || !selectedConversationId) {
      if (demoConversationStage !== "idle" && demoConversationStage !== "completed" && demoConversationStage !== "interrupted") {
        stopDemoConversationSequenceRef.current("idle");
        setDemoSimulationMessages([]);
      }
      if (!demoGuideDockedSequenceActive) {
        demoGuideSequenceStartedRef.current = false;
        demoGuideSequenceFinishedRef.current = false;
      }
      return;
    }

    if (demoGuideSequenceStartedRef.current || demoGuideSequenceFinishedRef.current) return;
    demoGuideSequenceStartedRef.current = true;
    startDemoConversationSequenceRef.current();
  }, [demoConversationStage, demoGuideDockedSequenceActive, selectedConversationId]);

  useEffect(() => {
    if (!demoSimulationMessages.length) return;
    scrollConversationToBottom();
  }, [demoSimulationMessages.length]);

  const resolveDemoSpotlightRect = () => {
    if (demoConversationStage === "suggestion_spotlight") {
      return aiAssistPanelRef.current?.querySelector("button")?.getBoundingClientRect() ?? null;
    }
    if (demoConversationStage === "summary_spotlight") {
      return aiSummaryPanelRef.current?.querySelector("button")?.getBoundingClientRect() ?? null;
    }
    if (demoConversationStage === "conversation_focus") {
      return conversationPanelRef.current?.getBoundingClientRect() ?? null;
    }
    return null;
  };

  const demoSpotlightRect = resolveDemoSpotlightRect();
  const showDemoSuggestionSpotlight = demoConversationStage === "suggestion_spotlight" && Boolean(demoSpotlightRect);
  const showDemoSummarySpotlight = demoConversationStage === "summary_spotlight" && Boolean(demoSpotlightRect);
  const showDemoConversationFocus = demoConversationStage === "conversation_focus" && Boolean(demoSpotlightRect);

  const handleUnitFilterChange = (nextValue: string) => {
    setUnitFilter(nextValue);
    if (ownerUnitScope.canSwitchUnits) {
      ownerUnitScope.setSelectedUnitId(nextValue);
    }
  };

  const handleResetFilters = () => {
    setSearch("");
    setStatusFilter("all");
    setOwnerFilter("all");
    setPriorityFilter("all");
    handleUnitFilterChange("all");
  };

  const handleSendMessage = () => {
    if (!draftMessage.trim() && !selectedAttachment) {
      toast.error("Digite uma mensagem ou anexe um arquivo antes de enviar.");
      return;
    }
    sendMessageMutation.mutate();
  };

  const handleRegisterInternalNote = () => {
    if (!internalNote.trim()) {
      toast.error("Digite uma nota interna para registrar.");
      return;
    }
    toast.success("Nota interna registrada no contexto do atendimento.");
    setInternalNote("");
    setInternalNoteOpen(false);
  };

  const handleAiSummaryToggle = () => {
    setAiAssistOpen(false);
    setInternalNoteOpen(false);
    setAiSummaryOpen((current) => {
      const next = !current;
      if (next) {
        setAiSummaryMode(effectiveAiSummary ? "viewer" : "composer");
      }
      return next;
    });
  };

  const handleAiSummaryComposeOpen = () => {
    setAiSummaryMode("composer");
    setAiSummaryOpen(true);
  };

  const handleAiSummaryComposeClose = () => {
    if (effectiveAiSummary) {
      setAiSummaryMode("viewer");
      return;
    }
    setAiSummaryOpen(false);
  };

  const handleComposerKeyDown = (event: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    if (!canCreateConversations || sendMessageMutation.isPending) return;
    handleSendMessage();
  };

  const handleDemoWorkspacePointerDown = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (!demoWorkspaceEnabled) return;
    if (event.pointerType === "mouse" && event.button !== 0) return;
    const target = event.target as HTMLElement | null;
    if (target?.closest('[data-demo-workspace-ignore-swipe="true"]')) return;
    demoWorkspaceSwipeRef.current = {
      startX: event.clientX,
      panel: demoWorkspacePanel,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }, [demoWorkspaceEnabled, demoWorkspacePanel]);

  const handleDemoWorkspacePointerMove = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const gesture = demoWorkspaceSwipeRef.current;
    const viewport = demoWorkspaceViewportRef.current;
    if (!gesture || !viewport || viewport.clientWidth <= 0) return;

    const rawDelta = event.clientX - gesture.startX;
    const clampedDelta = Math.max(Math.min(rawDelta, viewport.clientWidth * 0.35), -viewport.clientWidth * 0.35);
    if (gesture.panel === "whatsapp" && clampedDelta > 0) {
      setDemoWorkspaceDragOffset(clampedDelta * 0.16);
      return;
    }
    if (gesture.panel === "webchat" && clampedDelta < 0) {
      setDemoWorkspaceDragOffset(clampedDelta * 0.16);
      return;
    }
    setDemoWorkspaceDragOffset(clampedDelta);
  }, []);

  const finishDemoWorkspaceGesture = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const gesture = demoWorkspaceSwipeRef.current;
    if (!gesture) return;

    const deltaX = event.clientX - gesture.startX;
    if (gesture.panel === "whatsapp" && deltaX <= -DEMO_WEBCHAT_WORKSPACE_SWIPE_THRESHOLD_PX) {
      openDemoWebchatWorkspace();
    } else if (gesture.panel === "webchat" && deltaX >= DEMO_WEBCHAT_WORKSPACE_SWIPE_THRESHOLD_PX) {
      closeDemoWebchatWorkspace();
    }

    setDemoWorkspaceDragOffset(0);
    demoWorkspaceSwipeRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }, [closeDemoWebchatWorkspace, openDemoWebchatWorkspace]);

  const cancelDemoWorkspaceGesture = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    demoWorkspaceSwipeRef.current = null;
    setDemoWorkspaceDragOffset(0);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }, []);

  const handleOpenDemoWhatsApp = () => {
    launchDemoWhatsAppRedirect({ openInWorkspace: demoUsesWebchatEntry });
  };

  const handleOpenDemoWhatsAppPointerDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    demoLaunchButtonPointerHandledRef.current = true;
    handleOpenDemoWhatsApp();
  };

  const handleOpenDemoWhatsAppClick = () => {
    if (demoLaunchButtonPointerHandledRef.current) {
      demoLaunchButtonPointerHandledRef.current = false;
      return;
    }
    handleOpenDemoWhatsApp();
  };

  const demoWorkspaceWhatsAppTransform = demoWorkspaceOpen
    ? `translate3d(calc(-100% + ${demoWorkspaceDragOffset}px), 0, 0)`
    : `translate3d(${demoWorkspaceDragOffset}px, 0, 0)`;
  const demoWorkspaceWebchatTransform = demoWorkspaceOpen
    ? `translate3d(${demoWorkspaceDragOffset}px, 0, 0)`
    : `translate3d(calc(100% + ${demoWorkspaceDragOffset}px), 0, 0)`;

  if (inboxQuery.isLoading) return <LoadingState message="Carregando inbox operacional..." />;
  if (inboxQuery.isError || !dataset) return <ErrorState message="Não foi possível carregar o inbox." />;

  return (
    <div
      ref={demoWorkspaceViewportRef}
      data-demo-webchat-workspace="true"
      data-demo-webchat-workspace-panel={demoWorkspaceOpen ? "webchat" : "whatsapp"}
      className="relative h-full min-h-0 flex-1 overflow-hidden"
      onPointerDown={handleDemoWorkspacePointerDown}
      onPointerMove={handleDemoWorkspacePointerMove}
      onPointerUp={finishDemoWorkspaceGesture}
      onPointerCancel={cancelDemoWorkspaceGesture}
      style={{ touchAction: demoWorkspaceEnabled ? "pan-y" : "auto" }}
    >
      <div className="relative h-full w-full overflow-hidden">
        <div
          className={cn(
            "absolute inset-0 min-w-0 overflow-hidden will-change-transform transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]",
            demoWorkspaceOpen ? "pointer-events-none" : "pointer-events-auto",
          )}
          style={{ transform: demoWorkspaceWhatsAppTransform }}
        >
          <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.96),_rgba(242,247,245,0.92)_46%,_rgba(237,241,239,0.95))]">
        <div className="flex min-h-0 flex-1 overflow-hidden md:p-3 lg:p-4">
          <div className="flex min-h-0 flex-1 overflow-hidden border border-white/60 bg-white/88 shadow-[0_22px_70px_rgba(15,23,42,0.10)] backdrop-blur md:rounded-[32px]">
            <aside
              ref={conversationListPanelRef}
              className={cn(
                "flex min-h-0 w-full flex-col border-b border-stone-200 bg-white/90 lg:w-[340px] lg:min-w-[340px] lg:border-b-0 lg:border-r",
                selectedConversation && "hidden lg:flex",
              )}
            >
              <div className="shrink-0 border-b border-stone-200 px-4 pb-4 pt-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-emerald-700/80">
                      Inbox operacional
                    </p>
                    <div className="mt-1 flex items-center gap-2">
                      <h1 className="truncate text-2xl font-semibold text-stone-900">WhatsApp</h1>
                      <span className="rounded-full bg-stone-100 px-2.5 py-1 text-xs font-semibold text-stone-600">
                        {filteredConversations.length}
                      </span>
                    </div>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    className="h-10 shrink-0 rounded-full px-3 text-stone-700"
                    onClick={() => setFiltersOpen(true)}
                  >
                    <SlidersHorizontal size={15} />
                    Filtros
                    {advancedFilterCount ? (
                      <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] text-primary">
                        {advancedFilterCount}
                      </span>
                    ) : null}
                  </Button>
                </div>

                <div className="relative mt-4">
                  <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
                  <Input
                    className="h-11 rounded-full border-stone-200 bg-white pl-10"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Pesquisar ou encontrar conversa"
                  />
                </div>

                <div className="mt-4 flex gap-2 overflow-x-auto pb-1">
                  {QUICK_FILTERS.map((filter) => {
                    const active = statusFilter === filter.id;
                    const counter =
                      filter.id === "all"
                        ? filteredByQuickCounts.all
                        : filter.id === "aguardando"
                          ? filteredByQuickCounts.aguardando
                          : filteredByQuickCounts.nao_respondida;

                    return (
                      <button
                        key={filter.id}
                        type="button"
                        onClick={() => setStatusFilter(filter.id)}
                        className={cn(
                          "inline-flex h-9 shrink-0 items-center gap-2 rounded-full border px-3 text-sm font-semibold transition",
                          active
                            ? "border-emerald-300 bg-emerald-100 text-emerald-900"
                            : "border-stone-200 bg-white text-stone-600 hover:border-stone-300 hover:bg-stone-50",
                        )}
                      >
                        <span>{filter.label}</span>
                        <span className={cn("text-xs", active ? "text-emerald-800" : "text-stone-500")}>{counter}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 py-3 sm:px-3">
                {filteredConversations.length ? (
                  <div className="space-y-2">
                    {filteredConversations.map((item) => {
                      const patient = item.patient_id ? patientsById.get(item.patient_id) : null;
                      const lead = item.lead_id ? leadsById.get(item.lead_id) : null;
                      const ownerName = item.assigned_user_id ? usersById.get(item.assigned_user_id) ?? "" : "";
                      const isActive = item.id === selectedConversationId;
                      const priority = conversationPriority(item);
                      const aiEnabled = aiEnabledForConversation(item);
                      const preview =
                        item.ai_summary || lead?.interest || patient?.operational_notes || "Sem contexto automático disponível.";

                      return (
                        <button
                          key={item.id}
                          type="button"
                          data-tour-id={
                            item.id === demoTourConversationId
                              ? DEMO_TOUR_TARGETS.conversationItem
                              : undefined
                          }
                          onClick={() => setSelectedConversationId(item.id)}
                          className={cn(
                            "w-full rounded-[24px] border px-3 py-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
                            isActive
                              ? "border-primary/30 bg-primary/5 shadow-[0_12px_30px_rgba(15,23,42,0.08)]"
                              : "border-transparent bg-white hover:border-stone-200 hover:bg-stone-50",
                          )}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex min-w-0 items-center gap-3">
                              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-stone-100 text-sm font-semibold text-stone-700">
                                {initials(patient?.full_name ?? lead?.name ?? "Paciente")}
                              </div>
                              <div className="min-w-0">
                                <p className="truncate text-sm font-semibold text-stone-900">
                                  {patient?.full_name ?? lead?.name ?? "Contato sem identificação"}
                                </p>
                                <p className="truncate text-xs text-stone-500">
                                  {ownerName || channelLabel(item.channel)}
                                </p>
                              </div>
                            </div>
                            <div className="shrink-0 text-right">
                              <p className="text-[11px] text-stone-500">{formatRelativeTime(item.last_message_at)}</p>
                              <div className="mt-1 flex justify-end">
                                <StatusBadge value={item.status} />
                              </div>
                            </div>
                          </div>

                          <p className="mt-3 line-clamp-2 text-sm leading-5 text-stone-600">{preview}</p>

                          <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs">
                            <Badge className={priorityBadgeClass(priority)}>
                              {priority === "alta" ? "Alta" : priority === "media" ? "Média" : "Baixa"}
                            </Badge>
                            {aiEnabled ? <Badge className="bg-emerald-100 text-emerald-700">IA ativa</Badge> : null}
                            {item.tags?.slice(0, 2).map((tag) => (
                              <Badge key={tag} className="bg-stone-100 text-stone-600">
                                {tag}
                              </Badge>
                            ))}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <div className="px-2 py-10">
                    <EmptyState title="Nenhuma conversa no filtro" description="Ajuste os filtros para visualizar atendimentos." />
                  </div>
                )}
              </div>
            </aside>

            <section
              ref={conversationPanelRef}
              data-tour-id={
                selectedConversationId === demoTourConversationId ? DEMO_TOUR_TARGETS.conversationPanel : undefined
              }
              className={cn(
                "flex min-h-0 flex-1 flex-col overflow-hidden bg-white/72",
                !selectedConversation && "hidden lg:flex",
              )}
            >
              {selectedConversation ? (
                <>
                  <header className="shrink-0 border-b border-stone-200 bg-white/95 px-3 py-3 backdrop-blur sm:px-4">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex min-w-0 items-center gap-3">
                        <Button
                          type="button"
                          variant="ghost"
                          className="h-10 w-10 shrink-0 rounded-full px-0 lg:hidden"
                          onClick={() => {
                            setSelectedConversationId(null);
                            setDetailsOpen(false);
                          }}
                        >
                          <ArrowLeft size={17} />
                        </Button>
                        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-stone-100 text-sm font-semibold text-stone-700">
                          {initials(selectedConversationName || "Paciente")}
                        </div>
                        <div className="min-w-0">
                          <h2 className="truncate text-base font-semibold text-stone-900">{selectedConversationName}</h2>
                          <p className="truncate text-xs text-stone-500">
                            {channelLabel(selectedConversation.channel)} - Última atividade{" "}
                            {selectedConversation.last_message_at
                              ? formatRelativeTime(selectedConversation.last_message_at)
                              : "sem registro"}
                          </p>
                        </div>
                      </div>

                      <div className="flex shrink-0 items-center gap-2">
                        <div className="hidden sm:flex">
                          <StatusBadge value={selectedConversation.status} />
                        </div>
                        <div ref={demoEntryShortcutAnchorRef} className="relative flex shrink-0 items-center">
                          <Button
                            type="button"
                            variant="outline"
                            className="h-10 rounded-full px-3"
                            onClick={() => setDetailsOpen(true)}
                          >
                            <Info size={15} />
                            <span className="hidden sm:inline">Detalhes</span>
                          </Button>
                        </div>
                        <div className="relative" ref={actionsMenuRef}>
                          <Button
                            type="button"
                            variant="ghost"
                            className="h-10 w-10 rounded-full px-0"
                            onClick={() => setActionsOpen((current) => !current)}
                            aria-label="Abrir ações da conversa"
                          >
                            <MoreVertical size={16} />
                          </Button>

                          {actionsOpen ? (
                            <div className="absolute right-0 top-full z-30 mt-2 w-64 rounded-2xl border border-stone-200 bg-white p-2 shadow-[0_20px_50px_rgba(15,23,42,0.15)]">
                              <button
                                type="button"
                                className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-stone-700 transition hover:bg-stone-50"
                                onClick={() => {
                                  setActionsOpen(false);
                                  toggleAiMutation.mutate(!selectedAiEnabled);
                                }}
                                disabled={toggleAiMutation.isPending || !canEditConversations}
                              >
                                <Brain size={15} />
                                {selectedAiEnabled ? "Desativar IA" : "Ativar IA"}
                              </button>
                              <button
                                type="button"
                                className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-stone-700 transition hover:bg-stone-50"
                                onClick={() => {
                                  setActionsOpen(false);
                                  summarizeMutation.mutate({ revealPanel: false });
                                }}
                                disabled={summarizeMutation.isPending || !canEditConversations}
                              >
                                <Brain size={15} />
                                Atualizar resumo IA
                              </button>
                              {selectedLead && !selectedPatient ? (
                                <button
                                  type="button"
                                  className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-stone-700 transition hover:bg-stone-50"
                                  onClick={() => {
                                    setActionsOpen(false);
                                    convertLeadMutation.mutate();
                                  }}
                                  disabled={convertLeadMutation.isPending || !canEditConversations}
                                >
                                  <UserRoundCheck size={15} />
                                  Converter em paciente
                                </button>
                              ) : null}
                              <button
                                type="button"
                                className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-stone-700 transition hover:bg-stone-50"
                                onClick={() => {
                                  setActionsOpen(false);
                                  setDetailsOpen(true);
                                }}
                                disabled={!canEditConversations}
                              >
                                <Info size={15} />
                                Atribuir responsável
                              </button>
                              <button
                                type="button"
                                className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-stone-700 transition hover:bg-stone-50"
                                onClick={() => {
                                  setActionsOpen(false);
                                  setInternalNoteOpen(true);
                                  setAiAssistOpen(false);
                                  setAiSummaryOpen(false);
                                }}
                                disabled={!canCreateConversations}
                              >
                                <StickyNote size={15} />
                                Registrar nota interna
                              </button>
                              <button
                                type="button"
                                className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-rose-700 transition hover:bg-rose-50"
                                onClick={() => {
                                  setActionsOpen(false);
                                  setCloseDialogOpen(true);
                                }}
                                disabled={!canDeleteConversations}
                              >
                                <CircleOff size={15} />
                                Encerrar conversa
                              </button>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  </header>

                  <div className="min-h-0 flex-1 overflow-hidden bg-[linear-gradient(180deg,rgba(248,250,249,0.98),rgba(241,245,243,0.96))]">
                    <div className="flex h-full min-h-0 flex-col">
                      <div ref={conversationCardRef} className="min-h-0 flex-1 overflow-hidden px-2 pb-3 pt-3 sm:px-4 sm:pb-4">
                        <div
                          ref={messageListRef}
                          data-tour-id={
                            selectedConversationId === demoTourConversationId
                              ? DEMO_TOUR_TARGETS.conversationThread
                              : undefined
                          }
                          className="whatsapp-chat-surface h-full overflow-y-auto overscroll-contain rounded-[28px] border border-stone-200/80 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.75)]"
                        >
                          {messagesQuery.isLoading ? (
                            <p className="text-sm text-stone-500">Carregando mensagens...</p>
                          ) : messagesQuery.isError ? (
                            <p className="text-sm text-rose-700">Não foi possível carregar o histórico de mensagens.</p>
                          ) : (messagesQuery.data?.data ?? []).length ? (
                            <div className="space-y-3">
                              {(messagesQuery.data?.data ?? []).map((message) => {
                                const outbound = message.direction === "outbound";
                                const isAudioMessage = isAudioMessageType(message.message_type);
                                const isPinned = pinnedMessageIds.includes(message.id);
                                const isFavorite = favoriteMessageIds.includes(message.id);
                                const isSelected = selectedMessageIds.includes(message.id);
                                const messageActions: MessageMenuAction[] = [
                                  {
                                    id: "reply",
                                    label: "Responder",
                                    icon: <Reply size={16} />,
                                    onSelect: () => handleReplyToMessage(message),
                                  },
                                  {
                                    id: "copy",
                                    label: "Copiar",
                                    icon: <Copy size={16} />,
                                    onSelect: async () => handleCopyMessage(message),
                                  },
                                  {
                                    id: "forward",
                                    label: "Encaminhar",
                                    icon: <Forward size={16} />,
                                    onSelect: () => handleForwardMessage(message),
                                  },
                                  {
                                    id: "pin",
                                    label: isPinned ? "Desafixar" : "Fixar",
                                    icon: <Pin size={16} className={cn(isPinned && "fill-current")} />,
                                    onSelect: () => {
                                      setPinnedMessageIds((current) => toggleMessageCollection(current, message.id));
                                      toast.success(isPinned ? "Mensagem desafixada." : "Mensagem fixada nesta tela.");
                                    },
                                  },
                                  {
                                    id: "favorite",
                                    label: isFavorite ? "Desfavoritar" : "Favoritar",
                                    icon: <Star size={16} className={cn(isFavorite && "fill-current")} />,
                                    onSelect: () => {
                                      setFavoriteMessageIds((current) => toggleMessageCollection(current, message.id));
                                      toast.success(isFavorite ? "Mensagem removida dos favoritos." : "Mensagem favoritada.");
                                    },
                                  },
                                  {
                                    id: "select",
                                    label: isSelected ? "Desselecionar" : "Selecionar",
                                    icon: <Check size={16} />,
                                    separatorBefore: true,
                                    onSelect: () => {
                                      setSelectedMessageIds((current) => toggleMessageCollection(current, message.id));
                                      toast.success(isSelected ? "Mensagem removida da seleção." : "Mensagem selecionada.");
                                    },
                                  },
                                  {
                                    id: "save",
                                    label: "Salvar como",
                                    icon: <Download size={16} />,
                                    onSelect: async () => handleSaveMessage(message),
                                  },
                                  {
                                    id: "share",
                                    label: "Compartilhar",
                                    icon: <Share2 size={16} />,
                                    onSelect: async () => handleShareMessage(message),
                                  },
                                  {
                                    id: "report",
                                    label: "Denunciar",
                                    icon: <Flag size={16} />,
                                    separatorBefore: true,
                                    onSelect: () => {
                                      toast.info("O fluxo de denúncia ainda não está disponível nesta tela.");
                                    },
                                  },
                                  {
                                    id: "delete",
                                    label: "Apagar",
                                    icon: <Trash2 size={16} />,
                                    destructive: true,
                                    onSelect: () => {
                                      toast.info("A exclusão individual de mensagens ainda não está disponível.");
                                    },
                                  },
                                ];
                                return (
                                  <div key={message.id} className={cn("flex", outbound ? "justify-end" : "justify-start")}>
                                    <div
                                      className={cn(
                                        "relative max-w-[88%] rounded-[22px] px-4 py-3 pr-12 text-sm shadow-sm transition",
                                        outbound
                                          ? "bg-primary text-primary-foreground"
                                          : "border border-stone-200 bg-white text-stone-800",
                                        isSelected && "ring-2 ring-primary/20",
                                      )}
                                    >
                                      <MessageActionMenu outbound={outbound} actions={messageActions} />

                                      {isPinned || isFavorite ? (
                                        <div className="mb-2 flex items-center gap-2">
                                          {isPinned ? (
                                            <span
                                              className={cn(
                                                "inline-flex items-center gap-1 rounded-full px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.18em]",
                                                outbound
                                                  ? "bg-white/12 text-primary-foreground/90"
                                                  : "bg-stone-100 text-stone-600",
                                              )}
                                            >
                                              <Pin size={11} className="fill-current" />
                                              Fixada
                                            </span>
                                          ) : null}
                                          {isFavorite ? (
                                            <span
                                              className={cn(
                                                "inline-flex items-center gap-1 rounded-full px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.18em]",
                                                outbound
                                                  ? "bg-white/12 text-primary-foreground/90"
                                                  : "bg-amber-100 text-amber-700",
                                              )}
                                            >
                                              <Star size={11} className="fill-current" />
                                              Favorita
                                            </span>
                                          ) : null}
                                        </div>
                                      ) : null}

                                      {isAudioMessage ? (
                                        <AudioMessagePlayer message={message} outbound={outbound} />
                                      ) : (
                                        <p className="whitespace-pre-wrap leading-6">{message.body}</p>
                                      )}

                                      <div
                                        className={cn(
                                          "mt-2 flex items-center justify-end gap-1.5 text-[11px]",
                                          outbound ? "text-primary-foreground/80" : "text-stone-500",
                                        )}
                                      >
                                        <span>{formatDateTimeBR(message.sent_at || message.created_at)}</span>
                                        <MessageDeliveryIndicator message={message} outbound={outbound} />
                                      </div>
                                    </div>
                                  </div>
                                );
                              })}
                              {demoSimulationMessages.map((message) => (
                                <DemoSimulationMessageBubble key={`demo-sim-${message.id}`} message={message} />
                              ))}
                            </div>
                          ) : (
                            <div className="space-y-3">
                              {(demoSimulationMessages.length ? demoSimulationMessages : []).map((message) => (
                                <DemoSimulationMessageBubble key={`demo-sim-${message.id}`} message={message} />
                              ))}
                              {!demoSimulationMessages.length ? (
                                <p className="text-sm text-stone-500">Sem mensagens registradas nesta conversa.</p>
                              ) : null}
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="shrink-0 border-t border-stone-200 bg-white/96 px-2 pb-20 pt-3 backdrop-blur sm:px-4 sm:pb-4">
                        <div className="mx-auto w-full max-w-5xl">
                          <div className="mb-2 flex flex-wrap items-center gap-2">
                            <div className="relative" ref={aiAssistPanelRef}>
                              <Button
                                type="button"
                                variant={demoConversationStage === "suggestion_spotlight" ? "ghost" : aiAssistOpen || aiSuggestion ? "outline" : "ghost"}
                                className="h-9 rounded-full px-3 text-xs"
                                onClick={() => {
                                  setAiAssistOpen((current) => !current);
                                  setAiSummaryOpen(false);
                                  setInternalNoteOpen(false);
                                }}
                                disabled={!canEditConversations}
                              >
                                <Sparkles size={14} />
                                Sugestão IA
                              </Button>

                              {aiAssistOpen ? (
                                <div className="absolute bottom-full left-0 z-30 mb-3 w-[min(92vw,430px)] rounded-[24px] border border-stone-200 bg-white p-4 shadow-[0_22px_60px_rgba(15,23,42,0.16)]">
                                  <div className="flex items-start justify-between gap-3">
                                    <div>
                                      <p className="text-sm font-semibold text-stone-900">Apoio de resposta</p>
                                      <p className="text-xs leading-5 text-stone-500">
                                        Adicione contexto extra para a IA sugerir a próxima mensagem.
                                      </p>
                                    </div>
                                    <button
                                      type="button"
                                      className="rounded-full p-1 text-stone-400 transition hover:bg-stone-100 hover:text-stone-600"
                                      onClick={() => setAiAssistOpen(false)}
                                    >
                                      <X size={14} />
                                    </button>
                                  </div>

                                  <textarea
                                    className="mt-3 min-h-[104px] w-full rounded-2xl border border-stone-200 bg-stone-50 px-3 py-2 text-sm text-stone-800 outline-none transition placeholder:text-stone-400 focus:border-primary focus:ring-2 focus:ring-primary/20"
                                    placeholder="Opcional: explique o tom desejado, objetivo da resposta ou alguma orientação adicional para a IA."
                                    value={aiSuggestionPrompt}
                                    onChange={(event) => setAiSuggestionPrompt(event.target.value)}
                                  />

                                  {(aiIntent || aiSuggestion) && (
                                    <div className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 p-3">
                                      {aiIntent ? (
                                        <p className="text-xs font-semibold text-amber-800">Intenção detectada: {aiIntent}</p>
                                      ) : null}
                                      {aiSuggestion ? (
                                        <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-amber-950">{aiSuggestion}</p>
                                      ) : null}
                                    </div>
                                  )}

                                  <div className="mt-3 flex items-center justify-between gap-2">
                                    <Button
                                      type="button"
                                      variant="outline"
                                      className="h-9 rounded-full px-3 text-xs"
                                      onClick={() => {
                                        setAiSuggestion("");
                                        setAiIntent("");
                                        setAiSuggestionPrompt("");
                                      }}
                                    >
                                      Limpar
                                    </Button>
                                    <div className="flex items-center gap-2">
                                      {aiSuggestion ? (
                                        <Button
                                          type="button"
                                          variant="outline"
                                          className="h-9 rounded-full px-3 text-xs"
                                          onClick={() => {
                                            setDraftMessage(aiSuggestion);
                                            setAiAssistOpen(false);
                                            draftMessageRef.current?.focus();
                                          }}
                                        >
                                          Usar na mensagem
                                        </Button>
                                      ) : null}
                                      <Button
                                        type="button"
                                        className="h-9 rounded-full px-3 text-xs"
                                        onClick={() => suggestionMutation.mutate()}
                                        disabled={suggestionMutation.isPending || !canEditConversations}
                                      >
                                        <Sparkles size={14} />
                                        {suggestionMutation.isPending ? "Gerando..." : "Gerar"}
                                      </Button>
                                    </div>
                                  </div>
                                </div>
                              ) : null}
                            </div>

                            <div className="relative" ref={aiSummaryPanelRef}>
                              <Button
                                type="button"
                                variant={demoConversationStage === "summary_spotlight" ? "ghost" : aiSummaryOpen ? "outline" : "ghost"}
                                className="h-9 rounded-full px-3 text-xs"
                                onClick={handleAiSummaryToggle}
                                disabled={!canEditConversations}
                              >
                                <Brain size={14} />
                                Resumo IA
                              </Button>

                              {aiSummaryOpen ? (
                                <div className="absolute bottom-full left-0 z-30 mb-3 w-[min(92vw,430px)] rounded-[24px] border border-stone-200 bg-white p-4 shadow-[0_22px_60px_rgba(15,23,42,0.16)]">
                                  <div className="flex items-start justify-between gap-3">
                                    <div>
                                      <p className="text-sm font-semibold text-stone-900">
                                        {aiSummaryMode === "viewer" ? "Resumo IA" : effectiveAiSummary ? "Atualizar resumo IA" : "Gerar resumo IA"}
                                      </p>
                                      <p className="text-xs leading-5 text-stone-500">
                                        {aiSummaryMode === "viewer"
                                          ? "Use esse contexto rápido para entender a conversa antes de responder."
                                          : "Escreva algo opcional para complementar o que a IA deve considerar no resumo."}
                                      </p>
                                    </div>
                                    <button
                                      type="button"
                                      className="rounded-full p-1 text-stone-400 transition hover:bg-stone-100 hover:text-stone-600"
                                      onClick={() => setAiSummaryOpen(false)}
                                    >
                                      <X size={14} />
                                    </button>
                                  </div>

                                  {aiSummaryMode === "viewer" ? (
                                    <div className="mt-3 rounded-2xl border border-emerald-200 bg-emerald-50 px-3 py-3">
                                      <p className="whitespace-pre-wrap text-sm leading-6 text-emerald-950">
                                        {effectiveAiSummary || "Sem resumo disponível para esta conversa."}
                                      </p>
                                    </div>
                                  ) : (
                                    <textarea
                                      className="mt-3 min-h-[104px] w-full rounded-2xl border border-stone-200 bg-stone-50 px-3 py-2 text-sm text-stone-800 outline-none transition placeholder:text-stone-400 focus:border-primary focus:ring-2 focus:ring-primary/20"
                                      placeholder="Opcional: informe o foco desejado, prioridade, risco ou algum contexto extra para a IA considerar no resumo."
                                      value={aiSummaryPrompt}
                                      onChange={(event) => setAiSummaryPrompt(event.target.value)}
                                    />
                                  )}

                                  <div className="mt-3 flex items-center justify-between gap-2">
                                    {aiSummaryMode === "viewer" ? (
                                      <>
                                        <Button
                                          type="button"
                                          variant="outline"
                                          className="h-9 rounded-full px-3 text-xs"
                                          onClick={() => setAiSummaryOpen(false)}
                                        >
                                          Fechar
                                        </Button>
                                        <Button
                                          type="button"
                                          className="h-9 rounded-full px-3 text-xs"
                                          onClick={handleAiSummaryComposeOpen}
                                          disabled={!canEditConversations}
                                        >
                                          <Brain size={14} />
                                          Atualizar
                                        </Button>
                                      </>
                                    ) : (
                                      <>
                                        <Button
                                          type="button"
                                          variant="outline"
                                          className="h-9 rounded-full px-3 text-xs"
                                          onClick={handleAiSummaryComposeClose}
                                        >
                                          {effectiveAiSummary ? "Voltar ao resumo" : "Fechar"}
                                        </Button>
                                        <Button
                                          type="button"
                                          className="h-9 rounded-full px-3 text-xs"
                                          onClick={() =>
                                            summarizeMutation.mutate({
                                              additionalContext: aiSummaryPrompt,
                                              revealPanel: true,
                                            })
                                          }
                                          disabled={summarizeMutation.isPending || !canEditConversations}
                                        >
                                          <Brain size={14} />
                                          {summarizeMutation.isPending ? "Gerando..." : "Gerar"}
                                        </Button>
                                      </>
                                    )}
                                  </div>
                                </div>
                              ) : null}
                            </div>

                            <div className="relative" ref={notePanelRef}>
                              <Button
                                type="button"
                                variant={internalNoteOpen ? "outline" : "ghost"}
                                className="h-9 rounded-full px-3 text-xs"
                                onClick={() => {
                                  setInternalNoteOpen((current) => !current);
                                  setAiAssistOpen(false);
                                  setAiSummaryOpen(false);
                                }}
                                disabled={!canCreateConversations}
                              >
                                <StickyNote size={14} />
                                Nota interna
                              </Button>

                              {internalNoteOpen ? (
                                <div className="absolute bottom-full left-0 z-30 mb-3 w-[min(92vw,360px)] rounded-[24px] border border-stone-200 bg-white p-4 shadow-[0_22px_60px_rgba(15,23,42,0.16)]">
                                  <div className="flex items-start justify-between gap-3">
                                    <div>
                                      <p className="text-sm font-semibold text-stone-900">Nota interna</p>
                                      <p className="text-xs leading-5 text-stone-500">
                                        Esse texto não é enviado ao paciente.
                                      </p>
                                    </div>
                                    <button
                                      type="button"
                                      className="rounded-full p-1 text-stone-400 transition hover:bg-stone-100 hover:text-stone-600"
                                      onClick={() => setInternalNoteOpen(false)}
                                    >
                                      <X size={14} />
                                    </button>
                                  </div>

                                  <textarea
                                    className="mt-3 min-h-[110px] w-full rounded-2xl border border-stone-200 bg-stone-50 px-3 py-2 text-sm text-stone-800 outline-none transition placeholder:text-stone-400 focus:border-primary focus:ring-2 focus:ring-primary/20"
                                    placeholder="Escreva uma observação rápida para a equipe."
                                    value={internalNote}
                                    onChange={(event) => setInternalNote(event.target.value)}
                                  />

                                  <div className="mt-3 flex justify-end gap-2">
                                    <Button
                                      type="button"
                                      variant="outline"
                                      className="h-9 rounded-full px-3 text-xs"
                                      onClick={() => {
                                        setInternalNote("");
                                        setInternalNoteOpen(false);
                                      }}
                                    >
                                      Cancelar
                                    </Button>
                                    <Button
                                      type="button"
                                      className="h-9 rounded-full px-3 text-xs"
                                      onClick={handleRegisterInternalNote}
                                      disabled={!canCreateConversations}
                                    >
                                      Registrar
                                    </Button>
                                  </div>
                                </div>
                              ) : null}
                            </div>

                            {selectedAttachment ? (
                              <span className="inline-flex items-center gap-2 rounded-full bg-stone-100 px-3 py-1 text-xs font-medium text-stone-600">
                                {selectedAttachment.name}
                                <button
                                  type="button"
                                  className="rounded-full p-0.5 text-stone-400 transition hover:bg-stone-200 hover:text-stone-700"
                                  onClick={() => setSelectedAttachment(null)}
                                  aria-label="Remover anexo"
                                >
                                  <X size={12} />
                                </button>
                              </span>
                            ) : null}
                          </div>

                          {showDemoAiInsight ? (
                            <div
                              data-tour-id={DEMO_TOUR_TARGETS.aiIntent}
                              className="mb-3 rounded-[24px] border border-[color:var(--tenant-primary)]/18 bg-[linear-gradient(135deg,rgba(0,168,132,0.08),rgba(0,212,255,0.08))] px-4 py-3"
                            >
                              <div className="flex flex-wrap items-center gap-2">
                                <Badge className="bg-white text-[color:var(--tenant-primary)]">IA operacional</Badge>
                                {selectedAiLastDecision ? (
                                  <Badge className="border border-white/80 bg-white/80 text-[color:var(--text-primary)]">
                                    {aiDecisionLabel(selectedAiLastDecision)}
                                  </Badge>
                                ) : null}
                              </div>
                              <p className="mt-2 text-sm font-semibold text-[color:var(--text-primary)]">
                                A IA já entendeu o contexto e organizou a próxima ação.
                              </p>
                              {selectedAiLastReason ? (
                                <p className="mt-1 text-sm text-[color:var(--text-secondary)]">
                                  Motivo: {aiReasonLabel(selectedAiLastReason)}
                                </p>
                              ) : null}
                            </div>
                          ) : null}

                          {aiSuggestion ? (
                            <div className="mb-3 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2">
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <div className="min-w-0">
                                  {aiIntent ? (
                                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-800">
                                      {aiIntent}
                                    </p>
                                  ) : null}
                                  <p className="line-clamp-2 text-sm text-amber-950">{aiSuggestion}</p>
                                </div>
                                <div className="flex shrink-0 items-center gap-2">
                                  <Button
                                    type="button"
                                    variant="outline"
                                    className="h-8 rounded-full px-3 text-xs"
                                    onClick={() => {
                                      setDraftMessage(aiSuggestion);
                                      draftMessageRef.current?.focus();
                                    }}
                                  >
                                    Usar
                                  </Button>
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    className="h-8 rounded-full px-3 text-xs text-amber-900 hover:bg-amber-100"
                                    onClick={() => {
                                      setAiSuggestion("");
                                      setAiIntent("");
                                    }}
                                  >
                                    Fechar
                                  </Button>
                                </div>
                              </div>
                            </div>
                          ) : null}

                          {replyingToMessage ? (
                            <div className="mb-3 rounded-2xl border border-primary/15 bg-primary/5 px-3 py-2">
                              <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0">
                                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-primary/80">
                                    Respondendo a {replyingToMessage.direction === "inbound" ? "paciente" : "mensagem enviada"}
                                  </p>
                                  <p className="mt-1 line-clamp-2 text-sm text-stone-700">{messageCardPreview(replyingToMessage)}</p>
                                </div>
                                <button
                                  type="button"
                                  className="rounded-full p-1 text-stone-400 transition hover:bg-white hover:text-stone-600"
                                  onClick={() => setReplyingToMessage(null)}
                                  aria-label="Cancelar resposta"
                                >
                                  <X size={14} />
                                </button>
                              </div>
                            </div>
                          ) : null}

                          {!canCreateConversations ? (
                            <div className="mb-3 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                              Seu perfil está em modo leitura para envio de mensagens e notas nesta página.
                            </div>
                          ) : null}

                          <div
                            ref={composerCardRef}
                            className="flex items-end gap-2 rounded-[28px] border border-stone-200 bg-white p-2 shadow-sm"
                          >
                            <label className="inline-flex h-11 w-11 shrink-0 cursor-pointer items-center justify-center rounded-full text-stone-500 transition hover:bg-stone-100 hover:text-stone-700">
                              <Paperclip size={16} />
                              <input
                                type="file"
                                className="hidden"
                                onChange={(event) => setSelectedAttachment(event.target.files?.[0] ?? null)}
                              />
                            </label>

                            <textarea
                              ref={draftMessageRef}
                              className="min-h-[52px] max-h-40 flex-1 resize-none bg-transparent px-1 py-2 text-sm text-stone-900 outline-none placeholder:text-stone-400"
                              placeholder="Digite uma mensagem"
                              value={draftMessage}
                              onChange={(event) => setDraftMessage(event.target.value)}
                              onKeyDown={handleComposerKeyDown}
                              disabled={!canCreateConversations}
                            />

                            <Button
                              type="button"
                              className="h-11 w-11 shrink-0 rounded-full px-0"
                              onClick={handleSendMessage}
                              disabled={sendMessageMutation.isPending || !canCreateConversations}
                              aria-label="Enviar mensagem"
                            >
                              <Send size={16} />
                            </Button>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </>
              ) : (
                <div className="flex min-h-0 flex-1 items-center justify-center px-6">
                  <div className="w-full max-w-lg">
                    <EmptyState
                      title="Escolha uma conversa"
                      description="Selecione um atendimento na coluna esquerda para abrir o histórico e responder sem sair da operação."
                    />
                  </div>
                </div>
              )}
            </section>
          </div>
        </div>
      </div>

      {showDemoEntryShortcut && demoEntryShortcutStyle ? (
        <div className="pointer-events-none fixed inset-0 z-[130]">
          <div className="absolute" style={demoEntryShortcutStyle}>
            <Button
              type="button"
              data-tour-id={DEMO_TOUR_TARGETS.whatsappButton}
              data-demo-entry-shortcut="true"
              className="pointer-events-auto h-11 whitespace-nowrap rounded-full px-4 shadow-[0_24px_50px_rgba(6,37,31,0.22)]"
              onPointerDown={handleOpenDemoWhatsAppPointerDown}
              onClick={handleOpenDemoWhatsAppClick}
            >
              <Share2 size={16} />
              {demoEntryShortcutLabel}
            </Button>
          </div>
        </div>
      ) : null}

      {showDemoSuggestionSpotlight ? (
        <DemoGuideSpotlightOverlay
          rect={demoSpotlightRect}
          badge="Passo guiado"
          title="Clique em Sugestão IA"
          description={
            <>
              <strong className="font-semibold text-slate-950">A IA gera uma sugestão de resposta</strong> baseada no
              histórico da conversa para acelerar o atendimento.
            </>
          }
          icon={<Sparkles size={18} />}
        />
      ) : null}

      {showDemoSummarySpotlight ? (
        <DemoGuideSpotlightOverlay
          rect={demoSpotlightRect}
          badge="Passo guiado"
          title="Clique em Resumo IA"
          description={
            <>
              <strong className="font-semibold text-slate-950">Aqui a equipe entende o contexto rapidamente</strong>{" "}
              antes de responder, sem precisar reler toda a conversa.
            </>
          }
          icon={<Brain size={18} />}
        />
      ) : null}

      {demoConversationStage === "automation_countdown" ? (
        <div className="fixed inset-0 z-[76] flex items-center justify-center bg-slate-950/74 px-4">
          <div className="w-full max-w-lg rounded-[30px] border border-emerald-200 bg-white p-6 text-center shadow-[0_32px_90px_rgba(15,23,42,0.28)]">
            <span className="rounded-full bg-emerald-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-emerald-700">
              Simulação com IA
            </span>
            <h3 className="mt-4 text-2xl font-semibold text-slate-950">{demoConversationCountdown ?? 3}</h3>
            <p className="mt-3 text-sm leading-6 text-slate-700">
              Em instantes, a IA vai simular um atendimento automático completo para mostrar como conduz o paciente até
              o agendamento.
            </p>
          </div>
        </div>
      ) : null}

      {showDemoConversationFocus ? (
        <DemoGuideSpotlightOverlay
          rect={demoSpotlightRect}
          badge="Olhe a conversa"
          title="É aqui que a conversa acontece"
          description={
            <>
              <strong className="font-semibold text-slate-950">Observe esta área.</strong> A simulação vai aparecer
              neste card para mostrar o fluxo completo do WhatsApp com IA.
            </>
          }
          icon={<Info size={18} />}
          align="left-center"
          tone="focus"
        />
      ) : null}

      {demoConversationStage === "simulation_running" ? (
        <div className="fixed bottom-6 right-6 z-[76] w-[min(24rem,calc(100vw-2rem))] rounded-[28px] border border-emerald-200 bg-white/96 p-4 shadow-[0_24px_70px_rgba(15,23,42,0.2)] backdrop-blur">
          <div className="flex items-start justify-between gap-3">
            <div>
              <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-emerald-700">
                Simulação rodando
              </span>
              <p className="mt-2 text-sm leading-6 text-slate-700">
                A conversa está sendo simulada em tempo real, incluindo as listas em texto de clínica, serviço, data,
                horário e confirmação.
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              className="rounded-full border-slate-300 bg-white"
              onClick={() => {
                demoGuideSequenceFinishedRef.current = true;
                stopDemoConversationSequence("interrupted");
              }}
            >
              <Pause size={14} />
              Interromper
            </Button>
          </div>
        </div>
      ) : null}

      {demoConversationStage === "appointment_saved_pause" ? (
        <div className="fixed inset-0 z-[76] flex items-center justify-center bg-slate-950/58 px-4">
          <div className="w-full max-w-xl rounded-[30px] border border-emerald-200 bg-white p-6 shadow-[0_32px_90px_rgba(15,23,42,0.28)]">
            <span className="rounded-full bg-emerald-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-emerald-700">
              Agendamento salvo
            </span>
            <h3 className="mt-4 text-xl font-semibold text-slate-950">A confirmação já virou operação real</h3>
            <p className="mt-3 text-sm leading-6 text-slate-700">
              Assim que o paciente confirma, o sistema já salva o atendimento na agenda, atualiza o paciente e registra
              o contexto da conversa automaticamente.
            </p>
          </div>
        </div>
      ) : null}

      {demoConversationStage === "finish_countdown" ? (
        <div className="fixed inset-0 z-[76] flex items-center justify-center bg-slate-950/56 px-4">
          <div className="w-full max-w-xl rounded-[30px] border border-emerald-200 bg-white p-6 shadow-[0_32px_90px_rgba(15,23,42,0.28)]">
            <span className="rounded-full bg-emerald-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-emerald-700">
              Simulação concluída
            </span>
            <h3 className="mt-4 text-xl font-semibold text-slate-950">
              Vamos seguir para a próxima etapa em {demoConversationCountdown ?? DEMO_TOUR_NEXT_STEP_COUNTDOWN_SECONDS}s
            </h3>
            <p className="mt-3 text-sm leading-6 text-slate-700">
              Você pode avançar agora ou continuar vendo essa tela livremente. Se não escolher nada, o guia segue
              automaticamente.
            </p>
            <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:justify-end">
              <Button
                type="button"
                variant="outline"
                className="rounded-full border-slate-300 bg-white"
                onClick={() => {
                  demoGuideSequenceFinishedRef.current = true;
                  clearDemoGuideSequenceTimers();
                  setDemoConversationCountdown(null);
                  setDemoConversationStage("completed");
                }}
              >
                Continuar vendo
              </Button>
              <Button
                type="button"
                className="rounded-full"
                onClick={() => {
                  demoGuideSequenceFinishedRef.current = true;
                  clearDemoGuideSequenceTimers();
                  dispatchDemoGuideNextStep("demo_whatsapp_sequence_manual");
                }}
              >
                Ir imediatamente
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {demoConversationStage === "interrupted" ? (
        <div className="fixed bottom-6 right-6 z-[76] w-[min(22rem,calc(100vw-2rem))] rounded-[28px] border border-amber-200 bg-white/96 p-4 shadow-[0_24px_70px_rgba(15,23,42,0.18)] backdrop-blur">
          <span className="rounded-full bg-amber-50 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-amber-700">
            Simulação interrompida
          </span>
          <p className="mt-2 text-sm leading-6 text-slate-700">
            A conversa ficou livre para exploração manual. O guia lateral continua disponível para você seguir quando
            quiser.
          </p>
        </div>
      ) : null}

      <RightDrawer
        open={filtersOpen}
        onOpenChange={setFiltersOpen}
        title="Filtros avançados"
        description="Ajuste unidade, responsável, prioridade e status sem ocupar espaço do chat."
        widthClassName="w-full sm:max-w-md"
      >
        <div className="space-y-4">
          <DetailSection title="Status" tone="muted">
            <select
              className="h-11 w-full rounded-xl border border-stone-300 bg-white px-3 text-sm text-stone-800"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as StatusFilterId)}
            >
              {STATUS_FILTERS.map((status) => (
                <option key={status.id} value={status.id}>
                  {status.label}
                </option>
              ))}
            </select>
          </DetailSection>

          <DetailSection title="Unidade" tone="muted">
            <select
              className="h-11 w-full rounded-xl border border-stone-300 bg-white px-3 text-sm text-stone-800"
              value={unitFilter}
              onChange={(event) => handleUnitFilterChange(event.target.value)}
            >
              <option value="all">Todas as unidades</option>
              {unitOptions.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  {unit.name}
                </option>
              ))}
            </select>
          </DetailSection>

          <DetailSection title="Responsável" tone="muted">
            <select
              className="h-11 w-full rounded-xl border border-stone-300 bg-white px-3 text-sm text-stone-800"
              value={ownerFilter}
              onChange={(event) => setOwnerFilter(event.target.value)}
            >
              <option value="all">Todos os responsáveis</option>
              {dataset.users.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.full_name}
                </option>
              ))}
            </select>
          </DetailSection>

          <DetailSection title="Prioridade" tone="muted">
            <select
              className="h-11 w-full rounded-xl border border-stone-300 bg-white px-3 text-sm text-stone-800"
              value={priorityFilter}
              onChange={(event) => setPriorityFilter(event.target.value as PriorityFilter)}
            >
              <option value="all">Todas</option>
              <option value="alta">Alta</option>
              <option value="media">Média</option>
              <option value="baixa">Baixa</option>
            </select>
          </DetailSection>

          <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" variant="outline" className="rounded-full" onClick={handleResetFilters}>
              Limpar filtros
            </Button>
            <Button type="button" className="rounded-full" onClick={() => setFiltersOpen(false)}>
              Aplicar
            </Button>
          </div>
        </div>
      </RightDrawer>

      <RightDrawer
        open={detailsOpen}
        onOpenChange={setDetailsOpen}
        title={selectedConversationName || "Detalhes da conversa"}
        description="Contexto completo do paciente, IA e operação sem poluir a área principal."
        widthClassName="w-full sm:max-w-xl"
      >
        {selectedConversation ? (
          <div className="space-y-4">
            <DetailSection title="Contato" tone="accent">
              <div className="space-y-2">
                <p className="text-lg font-semibold text-stone-900">{selectedConversationName}</p>
                <p className="text-sm text-stone-600">{formatPhoneBR(selectedConversationPhone)}</p>
                <p className="text-sm text-stone-600">{selectedPatient?.email ?? selectedLead?.email ?? "Sem e-mail cadastrado"}</p>
                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <StatusBadge value={selectedConversation.status} />
                  <Badge className={priorityBadgeClass(selectedPriority)}>
                    {selectedPriority === "alta" ? "Alta" : selectedPriority === "media" ? "Média" : "Baixa"}
                  </Badge>
                  <Badge className={selectedAiEnabled ? "bg-emerald-100 text-emerald-700" : "bg-stone-200 text-stone-700"}>
                    IA {selectedAiEnabled ? "ativa" : "inativa"}
                  </Badge>
                </div>
                <div className="pt-2 text-sm text-stone-600">
                  <p>
                    Unidade:{" "}
                    <span className="font-medium text-stone-800">
                      {selectedConversation.unit_id ? unitsById.get(selectedConversation.unit_id) ?? "Unidade não identificada" : "Omnicanal"}
                    </span>
                  </p>
                  <p className="mt-1">
                    Responsável atual:{" "}
                    <span className="font-medium text-stone-800">
                      {selectedConversation.assigned_user_id ? usersById.get(selectedConversation.assigned_user_id) ?? "Equipe" : "Sem responsável"}
                    </span>
                  </p>
                  {selectedPatient?.operational_notes ? (
                    <p className="mt-3 rounded-2xl border border-primary/10 bg-white/70 px-3 py-2 text-sm leading-6 text-stone-700">
                      {selectedPatient.operational_notes}
                    </p>
                  ) : null}
                </div>
              </div>
            </DetailSection>

            <DetailSection title="Resumo IA" tone="default">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <p className="text-sm leading-6 text-stone-700">
                  {effectiveAiSummary || "Sem resumo disponível. Atualize o resumo IA quando precisar de contexto automático."}
                </p>
                <Button
                  type="button"
                  variant="outline"
                  className="h-9 shrink-0 rounded-full px-3 text-xs"
                  onClick={handleAiSummaryToggle}
                  disabled={summarizeMutation.isPending || !canEditConversations}
                >
                  <Brain size={14} />
                  {effectiveAiSummary ? "Abrir resumo" : "Gerar resumo"}
                </Button>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-stone-600">
                <Badge className="border border-stone-200 bg-white text-stone-700">
                  Última decisão: {aiDecisionLabel(selectedAiLastDecision)}
                </Badge>
                {selectedAiLastReason ? (
                  <span className="rounded-full border border-stone-200 bg-white px-2.5 py-1">
                    Motivo: {aiReasonLabel(selectedAiLastReason)}
                  </span>
                ) : null}
              </div>
            </DetailSection>

            <DetailSection title="Atribuição" tone="muted">
              <select
                className="h-11 w-full rounded-xl border border-stone-300 bg-white px-3 text-sm text-stone-800"
                value={selectedConversation.assigned_user_id ?? ""}
                onChange={(event) => assignMutation.mutate(event.target.value || null)}
                disabled={!canEditConversations}
              >
                <option value="">Sem responsável</option>
                {dataset.users.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.full_name}
                  </option>
                ))}
              </select>
            </DetailSection>

            <DetailSection title="Lead" tone="default">
              {selectedLead ? (
                <div className="space-y-2">
                  <p className="text-sm font-semibold text-stone-900">{selectedLead.name}</p>
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge value={STAGE_LABELS[selectedLead.stage] ?? selectedLead.stage} />
                    <TemperatureBadge value={selectedLead.temperature} />
                  </div>
                  <p className="text-sm text-stone-600">Interesse: {selectedLead.interest ?? "Não informado"}</p>
                </div>
              ) : (
                <p className="text-sm text-stone-500">Sem lead vinculado.</p>
              )}
            </DetailSection>

            <DetailSection title="Agenda" tone="default">
              {nextAppointment ? (
                <div className="space-y-2 text-sm text-stone-600">
                  <p>
                    Próxima consulta: <span className="font-medium text-stone-900">{formatDateTimeBR(nextAppointment.starts_at)}</span>
                  </p>
                  <p>
                    Status: <StatusBadge value={nextAppointment.status} className="align-middle" />
                  </p>
                  <p>
                    Confirmação: <span className="font-medium text-stone-800">{nextAppointment.confirmation_status}</span>
                  </p>
                </div>
              ) : (
                <p className="text-sm text-stone-500">Paciente sem consultas registradas.</p>
              )}
            </DetailSection>

            <DetailSection title="Documentos recentes" tone="default">
              {patientDocuments.length ? (
                <div className="space-y-2">
                  {patientDocuments.slice(0, 3).map((doc) => (
                    <div key={doc.id} className="rounded-xl border border-stone-200 bg-stone-50 px-3 py-2">
                      <p className="text-sm font-medium text-stone-800">{doc.title}</p>
                      <p className="text-xs text-stone-500">{formatDateBR(doc.created_at)}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-stone-500">Nenhum documento recente.</p>
              )}
            </DetailSection>

            <DetailSection title="Trilha de decisão IA" tone="default">
              {aiDecisionsQuery.isLoading ? (
                <p className="text-sm text-stone-500">Carregando decisões...</p>
              ) : selectedAiDecisions.length ? (
                <div className="space-y-2">
                  {selectedAiDecisions.slice(0, 5).map((decision) => (
                    <div key={decision.id} className="rounded-xl border border-stone-200 bg-stone-50 px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-semibold text-stone-800">{aiDecisionLabel(decision.final_decision)}</span>
                        <span className="text-xs text-stone-500">{formatDateTimeBR(decision.created_at)}</span>
                      </div>
                      <p className="mt-1 text-sm text-stone-600">{decision.decision_reason_label}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-stone-500">Nenhuma decisão IA registrada para esta conversa.</p>
              )}
            </DetailSection>

            <DetailSection title="Tags e automação" tone="muted">
              {(selectedConversation.tags ?? []).length ? (
                <div className="flex flex-wrap gap-2">
                  {selectedConversation.tags.map((tag) => (
                    <Badge key={tag} className="bg-stone-200 text-stone-700">
                      {tag}
                    </Badge>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-stone-500">Sem automações ativas identificadas.</p>
              )}
            </DetailSection>
          </div>
        ) : (
          <EmptyState title="Sem conversa selecionada" description="Abra uma conversa para ver os detalhes do atendimento." />
        )}
      </RightDrawer>

      <ConfirmDialog
        open={closeDialogOpen}
        onOpenChange={setCloseDialogOpen}
        title="Encerrar conversa"
        description="Esta ação finaliza o atendimento atual. Você poderá reabrir depois, se necessário."
        confirmLabel="Encerrar atendimento"
        destructive
        loading={closeConversationMutation.isPending}
        onConfirm={() => closeConversationMutation.mutate()}
      />
        </div>

        <div
          className={cn(
            "absolute inset-0 min-w-0 overflow-hidden border-l border-white/60 bg-[linear-gradient(180deg,#f4f8f7_0%,#ecf2f0_100%)] will-change-transform transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]",
            demoWorkspaceOpen ? "pointer-events-auto" : "pointer-events-none",
          )}
          style={{ transform: demoWorkspaceWebchatTransform }}
        >
          <div className="relative h-full min-h-0 bg-white">
            {demoResolvedPublicEntryPath ? (
              demoWebchatLaunchToken > 0 ? (
                <iframe
                  key={demoWebchatLaunchToken}
                  title="Webchat público da demo"
                  src={demoWorkspaceWebchatSrc || demoResolvedPublicEntryPath}
                  className="h-full w-full border-0 bg-white"
                />
              ) : (
                <div className="flex h-full items-center justify-center px-6 text-center">
                  <div className="max-w-md">
                    <p className="text-lg font-semibold text-stone-900">Abra o webchat da demo para iniciar a simulacao</p>
                    <p className="mt-2 text-sm leading-6 text-stone-600">
                      Quando voce abrir o workspace, a jornada publica vai comecar do zero para mostrar o fluxo completo.
                    </p>
                  </div>
                </div>
              )
            ) : (
              <div className="flex h-full items-center justify-center px-6 text-center">
                <div className="max-w-md">
                  <p className="text-lg font-semibold text-stone-900">Webchat público indisponível</p>
                  <p className="mt-2 text-sm leading-6 text-stone-600">
                    A demo ainda não tem uma landing pública de webchat configurada para este teste.
                  </p>
                </div>
              </div>
            )}

            <div className="pointer-events-none absolute inset-x-0 top-0 z-20 flex justify-end p-3 sm:p-4">
              <button
                type="button"
                data-demo-workspace-ignore-swipe="true"
                className="pointer-events-auto inline-flex h-11 items-center justify-center gap-2 rounded-full border border-white/80 bg-white/94 px-4 text-sm font-medium text-stone-700 shadow-[0_18px_40px_rgba(15,23,42,0.16)] backdrop-blur transition hover:border-stone-300 hover:bg-white"
                onPointerDown={(event) => event.stopPropagation()}
                onClick={closeDemoWebchatWorkspace}
              >
                <ArrowLeft size={15} />
                Voltar para WhatsApp
              </button>
            </div>

            <div
              className="absolute inset-y-0 left-0 z-10 w-7 touch-pan-y"
              onPointerDown={handleDemoWorkspacePointerDown}
              onPointerMove={handleDemoWorkspacePointerMove}
              onPointerUp={finishDemoWorkspaceGesture}
              onPointerCancel={cancelDemoWorkspaceGesture}
            />
          </div>
        </div>
      </div>
    </div>
  );
}


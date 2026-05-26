"use client";

import Link from "next/link";
import { type ChangeEvent, type CSSProperties, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowRight,
  BarChart3,
  Building2,
  CalendarClock,
  CheckCircle2,
  Clipboard,
  Eye,
  FileText,
  Flame,
  KeyRound,
  Lock,
  MapPin,
  MessageSquareText,
  Pencil,
  PhoneCall,
  Plus,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  SlidersHorizontal,
  UserRound,
} from "lucide-react";
import { toast } from "sonner";

import PlatformWhatsAppSettings from "@/components/adm/platform-whatsapp-settings";
import { EmptyState, RightDrawer } from "@/components/premium";
import { api } from "@/lib/api";
import { clearAdminAccessToken, getAdminAccessToken, setAdminAccessToken } from "@/lib/auth";
import { BRAND_MONOGRAM, BRAND_NAME, BRAND_SALES_TEAM, BRAND_TAGLINE } from "@/lib/brand";
import { formatDateTimeBR, formatRelativeTime, initials, numberFormatter } from "@/lib/formatters";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, cn } from "@odontoflux/ui";

type Prospect = {
  id: string;
  slug?: string | null;
  clinic_name: string;
  owner_name?: string | null;
  manager_name?: string | null;
  phone?: string | null;
  whatsapp_phone?: string | null;
  email?: string | null;
  website?: string | null;
  city?: string | null;
  state?: string | null;
  main_address?: string | null;
  notes: string;
  lead_source?: string | null;
  first_contact_channel?: string | null;
  first_contact_at?: string | null;
  uses_whatsapp_heavily: boolean;
  estimated_volume?: number | null;
  main_pain?: string | null;
  score: number;
  temperature: string;
  status: string;
  tags: string[];
  test_phone_number?: string | null;
  do_not_contact: boolean;
  demo_tenant_id?: string | null;
  demo_user_id?: string | null;
  demo_login_email?: string | null;
  demo_sent_at?: string | null;
  demo_first_login_at?: string | null;
  demo_last_login_at?: string | null;
  demo_status: string;
  demo_expires_at?: string | null;
  demo_booking_path?: string | null;
  demo_checklist: Record<string, boolean>;
  last_activity_at?: string | null;
  score_explanation: { points?: Record<string, number>; event_counts?: Record<string, number>; sessions?: number };
  proposal_snapshot: Record<string, unknown>;
  roi_inputs: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  units: Array<{ id: string; unit_name: string; address: string; phone?: string | null; email?: string | null; is_primary: boolean }>;
  services: Array<{ id: string; service_name: string; category?: string | null; duration_minutes: number; price_range?: string | null; description: string }>;
};

type Overview = {
  total_prospects: number;
  demos_created: number;
  demos_accessed: number;
  hot_leads: number;
  meetings_scheduled: number;
  won: number;
  recent_activity: TimelineEvent[];
};

type TimelineEvent = {
  id: string;
  event_type: string;
  event_label: string;
  actor_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

type ActivityEvent = {
  id: string;
  event_name: string;
  page_path?: string | null;
  session_id?: string | null;
  payload: Record<string, unknown>;
  occurred_at: string;
};

type SalesTemplateMessage = {
  key: string;
  label: string;
  body: string;
  is_default: boolean;
};

type SalesTemplate = {
  key: string;
  label: string;
  description: string;
  recommended_for: string[];
  body: string;
  messages: SalesTemplateMessage[];
};

type MessagePreview = {
  prospect: Prospect;
  template_key: string;
  template_label: string;
  message_key: string;
  message_label: string;
  message_text: string;
  demo_login_url?: string | null;
  can_copy: boolean;
  warnings: string[];
};

type OutreachResult = {
  prospect: Prospect;
  step: "reception_intro" | "decision_maker_pitch" | "video_followup" | string;
  destination: string;
  message_text: string;
  demo_login_url?: string | null;
  video_url?: string | null;
  sender_tenant_id: string;
  conversation_id: string;
  outbound_message_id: string;
};

type OutreachSnapshot = {
  automation_active?: boolean;
  automation_mode?: string | null;
  auto_progress?: boolean;
  auto_send_video_after_pitch?: boolean;
  automation_started_at?: string | null;
  automation_completed_at?: string | null;
  automation_stopped_at?: string | null;
  automation_stop_reason?: string | null;
  last_step?: string | null;
  last_sent_at?: string | null;
  last_reply_at?: string | null;
  last_reply_preview?: string | null;
};

type OutreachLabTurn = {
  id: string;
  role: "odontoflux" | "clinic_virtual" | "system" | string;
  label: string;
  text: string;
  step?: string | null;
  meta?: Record<string, unknown>;
};

type OutreachLabLastRun = {
  scenario?: string | null;
  scenario_label?: string | null;
  generated_at?: string | null;
  converted?: boolean;
  outcome?: string | null;
  recommendation?: string | null;
  demo_login_url?: string | null;
  video_url?: string | null;
  metrics?: Record<string, unknown>;
  transcript?: OutreachLabTurn[];
};

type OutreachLabSnapshot = {
  last_run_at?: string | null;
  last_scenario?: string | null;
  last_outcome?: string | null;
  last_converted?: boolean;
  last_run?: OutreachLabLastRun | null;
  scenario_stats?: Record<string, { runs?: number; conversions?: number; last_outcome?: string | null; last_run_at?: string | null }>;
};

type OutreachLabResult = {
  prospect: Prospect;
  scenario: string;
  scenario_label: string;
  status: string;
  outcome: string;
  converted: boolean;
  recommendation?: string | null;
  demo_login_url?: string | null;
  video_url?: string | null;
  transcript: OutreachLabTurn[];
  metrics: Record<string, unknown>;
};

type DemoLinkPayload = {
  demo_login_url?: string | null;
  demo_booking_url?: string | null;
  demo_booking_path?: string | null;
  prospect?: Prospect | null;
};

type ProspectDemoAiSettings = {
  enabled: boolean;
  whatsapp_enabled: boolean;
  max_consecutive_auto_replies: number;
};

type ProspectDemoWhatsAppSettings = {
  account_id: string | null;
};

type ProspectDemoIntakeMode = "official_api" | "link_flow" | "hybrid";
type ProspectDemoLinkFlowCtaMode = "whatsapp_redirect" | "webchat";

type ProspectDemoIntakeSettings = {
  mode: ProspectDemoIntakeMode;
  cta_mode: ProspectDemoLinkFlowCtaMode;
};

type ProspectDemoBackgroundSettings = {
  background_image_url: string;
  background_image_opacity: number;
};

type PlatformWhatsAppAccountItem = {
  id: string;
  provider_name: string;
  phone_number_id: string;
  business_account_id: string;
  display_phone?: string | null;
  is_active: boolean;
};

type ProspectEditFormState = {
  clinic_name: string;
  owner_name: string;
  manager_name: string;
  phone: string;
  whatsapp_phone: string;
  email: string;
  website: string;
  city: string;
  state: string;
  main_address: string;
  main_pain: string;
  lead_source: string;
  status: string;
  test_phone_number: string;
  demo_whatsapp_account_id: string;
  demo_intake_mode: ProspectDemoIntakeMode;
  demo_link_flow_cta_mode: ProspectDemoLinkFlowCtaMode;
  demo_ai_enabled: boolean;
  demo_whatsapp_enabled: boolean;
  demo_max_consecutive_auto_replies: number;
  demo_background_image_url: string;
  demo_background_opacity: number;
  services: Array<{
    id: string;
    service_name: string;
    price_range: string;
    duration_minutes: number;
    description: string;
    category: string;
  }>;
  notes: string;
  do_not_contact: boolean;
};

const DEFAULT_DEMO_BACKGROUND_IMAGE_URL = "/images/dental-floss-smile-background.png";
const DEFAULT_DEMO_BACKGROUND_OPACITY = 0.18;

const STATUS_OPTIONS = [
  "novo",
  "pesquisado",
  "contato_iniciado",
  "respondeu",
  "decisor_identificado",
  "demo_criada",
  "demo_enviada",
  "demo_acessada",
  "testou_whatsapp",
  "visitou_agenda",
  "configurou_dados",
  "followup",
  "reuniao_marcada",
  "proposta_enviada",
  "negociacao",
  "fechado_ganho",
  "fechado_perdido",
];

const PLAYBOOKS = [
  {
    title: "Ligacao inicial",
    text: "Oi, tudo bem? Estou falando porque montei uma demonstracao rapida de como a recepcao da clinica pode organizar WhatsApp, agenda e retornos em um fluxo unico. Posso te mostrar em 7 minutos?",
  },
  {
    title: "WhatsApp curto",
    text: `Oi! Vi que a clinica atende bastante pelo WhatsApp. Eu consigo te mostrar uma demo personalizada da ${BRAND_NAME} com IA, agenda e recuperacao de pacientes. Posso te enviar?`,
  },
  {
    title: "Follow-up apos acesso",
    text: "Vi que voce acessou a demonstracao. A parte mais importante e testar WhatsApp e Agenda, porque ali aparece onde a recepcao ganha tempo. Quer que eu te guie rapidinho?",
  },
  {
    title: "Ja tenho sistema",
    text: "Perfeito. A ideia nao e trocar uma agenda por outra. O ponto e organizar o caminho inteiro: WhatsApp, recepcao, agendamento, comparecimento e retorno.",
  },
];

const OUTREACH_LAB_SCENARIOS = [
  { value: "manager_interested", label: "Gerente pede reuniao" },
  { value: "asks_price", label: "Gerente pede preco" },
  { value: "already_has_system", label: "Ja tem sistema" },
  { value: "reception_blocks", label: "Recepcao bloqueia" },
] as const;

const CRM_PROSPECT_GRID_CLASS = "grid-cols-[minmax(220px,1.2fr)_110px_110px_70px_110px_228px]";

type AdmSection = "crm" | "adm_whatsapp" | "whatsapp_settings";

type AdmWhatsappConversation = {
  id: string;
  source: "demo" | "comercial" | string;
  prospect_id: string;
  prospect_name: string;
  demo_tenant_id?: string | null;
  contact_name?: string | null;
  contact_phone?: string | null;
  patient_id?: string | null;
  lead_id?: string | null;
  channel: string;
  status: string;
  tags: string[];
  ai_summary?: string | null;
  ai_autoresponder_enabled?: boolean | null;
  last_message_at?: string | null;
  last_message_preview?: string | null;
  last_message_direction?: string | null;
  message_count: number;
  simulated_patient_messages: number;
  created_at: string;
};

type AdmWhatsappMessage = {
  id: string;
  tenant_id: string;
  conversation_id: string;
  direction: string;
  provider_message_id?: string | null;
  status: string;
  body: string;
  message_type: string;
  sender_type: string;
  payload?: Record<string, unknown>;
  sent_at?: string | null;
  delivered_at?: string | null;
  read_at?: string | null;
  created_at: string;
};

function resolveBrowserOrigin() {
  if (typeof window === "undefined") return "";
  return window.location.origin;
}

function buildAbsoluteAppUrl(origin: string, rawUrlOrPath?: string | null) {
  const value = `${rawUrlOrPath || ""}`.trim();
  if (!value) return "";
  if (/^https?:\/\//i.test(value)) return value;
  if (!origin) return value;
  try {
    return new URL(value, origin).toString();
  } catch {
    return value;
  }
}

function resolveProspectBookingLink(prospect: Prospect | null, origin: string) {
  if (!prospect) return "";
  return buildAbsoluteAppUrl(origin, prospect.demo_booking_path ?? null);
}

function resolvePayloadBookingLink(payload: DemoLinkPayload | null | undefined, origin: string) {
  if (!payload) return "";
  return buildAbsoluteAppUrl(
    origin,
    payload.demo_booking_url ?? payload.demo_booking_path ?? payload.prospect?.demo_booking_path ?? null,
  );
}

function extractApiErrorMessage(error: unknown, fallback: string): string {
  const response = (
    error as {
      response?: {
        data?: {
          error?: {
            message?: string;
            details?: { rules?: string[]; errors?: Array<{ msg?: string }> };
          };
        };
      };
    }
  ).response;

  const message = response?.data?.error?.message?.trim();
  const rules = response?.data?.error?.details?.rules?.filter(Boolean) ?? [];
  const validationErrors =
    response?.data?.error?.details?.errors?.map((item) => item?.msg?.trim()).filter(Boolean) ?? [];

  if (rules.length) return `${message || fallback}: ${rules.join(", ")}`;
  if (validationErrors.length) return `${message || fallback}: ${validationErrors.join(", ")}`;
  return message || fallback;
}

function humanize(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function nullableText(value: string) {
  const normalized = value.trim();
  return normalized.length ? normalized : null;
}

function resolveOfficialWhatsAppNumber(prospect: Prospect) {
  const rawPhone = `${prospect.whatsapp_phone || prospect.phone || ""}`.trim();
  const digits = rawPhone.replace(/\D/g, "");
  if (!digits) return null;
  return digits.length <= 11 ? `55${digits}` : digits;
}

function resolveOfficialWhatsAppLink(prospect: Prospect) {
  const number = resolveOfficialWhatsAppNumber(prospect);
  return number ? `https://wa.me/${number}` : null;
}

function getDemoAiSettingsSnapshot(prospect: Prospect): ProspectDemoAiSettings {
  const raw = prospect.proposal_snapshot?.demo_ai;
  const value = raw && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
  const parsedMaxConsecutive = Number(value.max_consecutive_auto_replies ?? 3);
  return {
    enabled: value.enabled !== false,
    whatsapp_enabled: value.whatsapp_enabled !== false,
    max_consecutive_auto_replies:
      Number.isFinite(parsedMaxConsecutive) && parsedMaxConsecutive > 0 ? Math.min(Math.max(parsedMaxConsecutive, 1), 20) : 3,
  };
}

function getDemoWhatsAppSettingsSnapshot(prospect: Prospect): ProspectDemoWhatsAppSettings {
  const raw = prospect.proposal_snapshot?.demo_whatsapp;
  const value = raw && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
  const accountId = typeof value.account_id === "string" ? value.account_id.trim() : "";
  return {
    account_id: accountId || null,
  };
}

function getDemoIntakeSettingsSnapshot(prospect: Prospect): ProspectDemoIntakeSettings {
  const raw = prospect.proposal_snapshot?.demo_intake;
  const value = raw && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
  const rawLinkFlow =
    value.link_flow && typeof value.link_flow === "object" && !Array.isArray(value.link_flow)
      ? (value.link_flow as Record<string, unknown>)
      : {};
  const mode =
    value.mode === "official_api" || value.mode === "link_flow" || value.mode === "hybrid"
      ? value.mode
      : "hybrid";
  const ctaMode = rawLinkFlow.cta_mode === "webchat" ? "webchat" : "whatsapp_redirect";
  return {
    mode,
    cta_mode: ctaMode,
  };
}

function clampDemoBackgroundOpacity(value: number) {
  if (!Number.isFinite(value)) return DEFAULT_DEMO_BACKGROUND_OPACITY;
  return Math.min(Math.max(value, 0), 1);
}

function getDemoBackgroundSettingsSnapshot(prospect: Prospect): ProspectDemoBackgroundSettings {
  const raw = prospect.proposal_snapshot?.demo_branding;
  const value = raw && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
  const imageUrl =
    typeof value.background_image_url === "string" && value.background_image_url.trim()
      ? value.background_image_url
      : DEFAULT_DEMO_BACKGROUND_IMAGE_URL;
  const rawOpacity =
    typeof value.background_image_opacity === "number"
      ? value.background_image_opacity
      : Number(value.background_image_opacity);

  return {
    background_image_url: imageUrl,
    background_image_opacity: clampDemoBackgroundOpacity(rawOpacity),
  };
}

function buildDemoBackgroundSnapshot(imageUrl: string, opacity: number) {
  return {
    background_image_url: imageUrl || DEFAULT_DEMO_BACKGROUND_IMAGE_URL,
    background_image_opacity: clampDemoBackgroundOpacity(opacity),
  };
}

function buildDemoBackgroundPreviewStyle(imageUrl: string, opacity: number): CSSProperties {
  const resolvedImageUrl = imageUrl || DEFAULT_DEMO_BACKGROUND_IMAGE_URL;
  const overlayOpacity = 1 - clampDemoBackgroundOpacity(opacity);
  const safeUrl = resolvedImageUrl.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  return {
    backgroundColor: "#f2f4f7",
    backgroundImage: `linear-gradient(135deg, rgba(242, 244, 247, ${overlayOpacity}), rgba(242, 244, 247, ${overlayOpacity})), radial-gradient(circle at 8% 0%, rgba(15, 118, 110, 0.16), transparent 42%), radial-gradient(circle at 94% 100%, rgba(245, 158, 11, 0.14), transparent 38%), url("${safeUrl}")`,
    backgroundPosition: "center center, left top, right bottom, center center",
    backgroundSize: "cover, auto, auto, cover",
    backgroundRepeat: "no-repeat",
  };
}

function readImageFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    if (!file.type.startsWith("image/")) {
      reject(new Error("Selecione um arquivo de imagem."));
      return;
    }
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Nao foi possivel ler a imagem selecionada."));
    reader.onload = () => {
      const dataUrl = typeof reader.result === "string" ? reader.result : null;
      if (!dataUrl) {
        reject(new Error("Nao foi possivel ler a imagem selecionada."));
        return;
      }
      resolve(dataUrl);
    };
    reader.readAsDataURL(file);
  });
}

function platformWhatsAppAccountLabel(account: PlatformWhatsAppAccountItem) {
  const primary = (account.display_phone || "").trim() || account.phone_number_id;
  const provider = humanize(account.provider_name || "numero");
  return `${primary} - ${provider}`;
}

function createEditableProspectService(service?: Prospect["services"][number], index = 0): ProspectEditFormState["services"][number] {
  return {
    id: service?.id ?? `draft-service-${index}-${Date.now()}`,
    service_name: service?.service_name ?? "",
    price_range: service?.price_range ?? "",
    duration_minutes: service?.duration_minutes ?? 60,
    description: service?.description ?? "",
    category: service?.category ?? "",
  };
}

function prospectToEditForm(prospect: Prospect): ProspectEditFormState {
  const demoAi = getDemoAiSettingsSnapshot(prospect);
  const demoWhatsApp = getDemoWhatsAppSettingsSnapshot(prospect);
  const demoIntake = getDemoIntakeSettingsSnapshot(prospect);
  const demoBackground = getDemoBackgroundSettingsSnapshot(prospect);
  return {
    clinic_name: prospect.clinic_name ?? "",
    owner_name: prospect.owner_name ?? "",
    manager_name: prospect.manager_name ?? "",
    phone: prospect.phone ?? "",
    whatsapp_phone: prospect.whatsapp_phone ?? "",
    email: prospect.email ?? "",
    website: prospect.website ?? "",
    city: prospect.city ?? "",
    state: prospect.state ?? "",
    main_address: prospect.main_address ?? "",
    main_pain: prospect.main_pain ?? "",
    lead_source: prospect.lead_source ?? "",
    status: prospect.status || "novo",
    test_phone_number: prospect.test_phone_number ?? "",
    demo_whatsapp_account_id: demoWhatsApp.account_id ?? "",
    demo_intake_mode: demoIntake.mode,
    demo_link_flow_cta_mode: demoIntake.cta_mode,
    demo_ai_enabled: demoAi.enabled,
    demo_whatsapp_enabled: demoAi.whatsapp_enabled,
    demo_max_consecutive_auto_replies: demoAi.max_consecutive_auto_replies,
    demo_background_image_url: demoBackground.background_image_url,
    demo_background_opacity: demoBackground.background_image_opacity,
    services: (prospect.services ?? []).map((service, index) => createEditableProspectService(service, index)),
    notes: prospect.notes ?? "",
    do_not_contact: Boolean(prospect.do_not_contact),
  };
}

function buildDemoIntakeSnapshot(
  mode: ProspectDemoIntakeMode,
  ctaMode: ProspectDemoLinkFlowCtaMode,
) {
  return {
    mode,
    link_flow: {
      enabled: mode !== "official_api",
      cta_mode: ctaMode,
    },
  };
}

function DemoBackgroundFieldset({
  imageUrl,
  opacity,
  disabled,
  helper,
  onUpload,
  onResetToDefault,
  onOpacityChange,
}: {
  imageUrl: string;
  opacity: number;
  disabled?: boolean;
  helper: string;
  onUpload: (event: ChangeEvent<HTMLInputElement>) => void;
  onResetToDefault: () => void;
  onOpacityChange: (opacity: number) => void;
}) {
  const opacityPercent = Math.round(clampDemoBackgroundOpacity(opacity) * 100);
  const isDefaultBackground = imageUrl === DEFAULT_DEMO_BACKGROUND_IMAGE_URL;
  const previewStyle = buildDemoBackgroundPreviewStyle(imageUrl, opacity);

  return (
    <Field
      label="Fundo da demo"
      helper={helper}
      className="lg:col-span-4"
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="space-y-4 rounded-2xl border border-stone-200 bg-white p-4">
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
            <div>
              <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Imagem personalizada</label>
              <Input type="file" accept="image/*" onChange={onUpload} disabled={disabled} className="mt-2" data-testid="demo-background-file-input" />
              <p className="mt-2 text-xs text-stone-500">
                {isDefaultBackground
                  ? "Usando a imagem padrao atual do sistema."
                  : "Uma imagem personalizada foi carregada para esta demo."}
              </p>
            </div>
            <Button type="button" variant="outline" onClick={onResetToDefault} disabled={disabled}>
              Usar imagem padrao
            </Button>
          </div>
          <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Transparencia da imagem</p>
                <p className="mt-1 text-sm text-stone-600">Ajuste quanto do fundo aparece na demo.</p>
              </div>
              <div className="rounded-full border border-stone-200 bg-white px-3 py-1 text-sm font-semibold text-stone-700">
                {opacityPercent}%
              </div>
            </div>
            <input
              type="range"
              min={0}
              max={100}
              step={1}
              data-testid="demo-background-opacity-slider"
              value={opacityPercent}
              onChange={(event) => onOpacityChange(Number(event.target.value) / 100)}
              disabled={disabled}
              className="mt-4 w-full accent-emerald-600"
            />
          </div>
        </div>
        <div className="overflow-hidden rounded-[28px] border border-white/70 bg-white shadow-[0_18px_48px_rgba(15,23,42,0.08)]">
          <div className="border-b border-white/60 px-5 py-4">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-700">Previa real da demo</p>
            <p className="mt-1 text-sm text-stone-600">Esse fundo vai aparecer na area interna da clinica demo.</p>
          </div>
          <div className="p-4">
            <div
              data-testid="demo-background-preview"
              className="rounded-[24px] border border-white/70 shadow-[0_18px_40px_rgba(15,23,42,0.10)]"
              style={previewStyle}
            >
              <div className="space-y-4 rounded-[24px] p-4">
                <div className="rounded-2xl border border-white/80 bg-white/92 p-4 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Clinica ativa</p>
                  <p className="mt-2 text-xl font-black text-stone-950">Clinica demo</p>
                  <p className="mt-1 text-sm leading-6 text-stone-600">
                    Assim o fundo vai aparecer por tras do painel interno da demonstracao.
                  </p>
                </div>
                <div className="rounded-2xl border border-white/80 bg-white/88 p-4 shadow-sm">
                  <p className="text-sm font-semibold text-stone-900">WhatsApp, agenda e operacao</p>
                  <p className="mt-1 text-sm leading-6 text-stone-600">
                    Mantemos a mesma legibilidade do sistema, so trocando a imagem de fundo por clinica demo.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Field>
  );
}

function getOutreachSnapshot(prospect: Prospect): OutreachSnapshot {
  const raw = prospect.proposal_snapshot?.outreach;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  return raw as OutreachSnapshot;
}

function getOutreachLabSnapshot(prospect: Prospect): OutreachLabSnapshot {
  const raw = prospect.proposal_snapshot?.outreach_lab;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  return raw as OutreachLabSnapshot;
}

function outreachAutomationLabel(snapshot: OutreachSnapshot) {
  if (snapshot.automation_active) return "Automacao ativa";
  if (snapshot.automation_completed_at) return "Fluxo inicial concluido";
  if (snapshot.automation_stop_reason === "video_url_missing") return "Parou sem video";
  if (snapshot.automation_stopped_at) return "Automacao pausada";
  return "Pronto para iniciar";
}

function temperatureClass(value: string) {
  if (value === "muito_quente") return "bg-red-100 text-red-700";
  if (value === "quente") return "bg-orange-100 text-orange-700";
  if (value === "morno") return "bg-amber-100 text-amber-800";
  return "bg-stone-200 text-stone-700";
}

function statusClass(value: string) {
  if (["fechado_ganho", "demo_acessada", "testou_whatsapp"].includes(value)) return "bg-emerald-100 text-emerald-700";
  if (["negociacao", "proposta_enviada", "reuniao_marcada"].includes(value)) return "bg-blue-100 text-blue-700";
  if (["fechado_perdido"].includes(value)) return "bg-rose-100 text-rose-700";
  return "bg-stone-200 text-stone-700";
}

function sessionId() {
  if (typeof window === "undefined") return "adm-session";
  const key = "odontoflux_adm_session_id";
  const current = window.sessionStorage.getItem(key);
  if (current) return current;
  const generated = crypto.randomUUID();
  window.sessionStorage.setItem(key, generated);
  return generated;
}

function LoginPanel({ onLogged }: { onLogged: (forceChange: boolean) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const loginMutation = useMutation({
    mutationFn: async () => (await api.post("/admin/auth/login", { email, password })).data,
    onSuccess: (data) => {
      setAdminAccessToken(data.access_token, data.refresh_token);
      toast.success(data.force_password_change ? "Troque a senha inicial para continuar." : "Acesso administrativo liberado.");
      onLogged(Boolean(data.force_password_change));
    },
    onError: (error) => toast.error(extractApiErrorMessage(error, "Nao foi possivel entrar no /adm.")),
  });

  return (
    <main className="grid min-h-screen place-items-center bg-stone-950 px-4 py-10 text-white">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-lg bg-white text-sm font-black text-stone-950">{BRAND_MONOGRAM}</div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-white/45">Admin comercial</p>
            <h1 className="text-xl font-bold">{BRAND_NAME} /adm</h1>
          </div>
        </div>
        <Card className="border-white/10 bg-white text-stone-950">
          <CardHeader>
            <CardTitle>Entrar no CRM de demos</CardTitle>
            <p className="text-sm text-stone-600">{BRAND_TAGLINE}</p>
            <p className="text-xs leading-5 text-stone-500">
              Use exatamente as credenciais configuradas em <code>ADM_BOOTSTRAP_EMAIL</code> e <code>ADM_BOOTSTRAP_PASSWORD</code>.
            </p>
          </CardHeader>
          <CardContent>
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                loginMutation.mutate();
              }}
            >
              <div className="space-y-1">
                <label className="text-sm font-medium">E-mail</label>
                <Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium">Senha</label>
                <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
              </div>
              <Button className="w-full" disabled={loginMutation.isPending}>
                <Lock size={16} />
                {loginMutation.isPending ? "Entrando..." : "Entrar"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}

function ChangePasswordPanel({ onDone }: { onDone: () => void }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const mutation = useMutation({
    mutationFn: async () =>
      (await api.post("/admin/auth/change-initial-password", { current_password: currentPassword, new_password: newPassword })).data,
    onSuccess: () => {
      toast.success("Senha inicial trocada. Pode operar o /adm.");
      onDone();
    },
    onError: (error: unknown) => {
      const response = (error as { response?: { data?: { error?: { message?: string; details?: { rules?: string[] } } } } }).response;
      const message = response?.data?.error?.message ?? "Nao foi possivel trocar a senha inicial.";
      const rules = response?.data?.error?.details?.rules;
      toast.error(rules?.length ? `${message}: ${rules.join(", ")}` : message);
    },
  });

  return (
    <main className="grid min-h-screen place-items-center bg-stone-950 px-4 py-10 text-white">
      <Card className="w-full max-w-md border-white/10 bg-white text-stone-950">
        <CardHeader>
          <CardTitle>Trocar senha inicial</CardTitle>
          <p className="text-sm text-stone-600">Para liberar o painel, defina uma senha propria antes de continuar.</p>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (newPassword !== confirmPassword) {
                toast.error("A confirmacao da senha nao confere.");
                return;
              }
              mutation.mutate();
            }}
          >
            <div className="space-y-1">
              <label className="text-sm font-medium">Senha inicial recebida</label>
              <Input type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} placeholder="Senha atual" />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium">Nova senha</label>
              <Input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} placeholder="Nova senha forte" />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium">Confirmar nova senha</label>
              <Input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} placeholder="Repita a nova senha" />
            </div>
            <p className="text-xs leading-5 text-stone-500">
              Use ao menos 10 caracteres, com letra maiuscula, minuscula, numero e simbolo. A senha inicial precisa ser exatamente a senha temporaria do login.
            </p>
            <Button className="w-full" disabled={mutation.isPending}>
              <KeyRound size={16} />
              {mutation.isPending ? "Atualizando..." : "Atualizar senha"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}

function admWhatsappSourceLabel(source: string) {
  if (source === "demo") return "Demo";
  if (source === "comercial") return "Comercial";
  return humanize(source);
}

function messageAuthorLabel(message: AdmWhatsappMessage, conversationSource: string, simulated: boolean) {
  if (message.direction === "inbound") {
    if (message.sender_type === "patient") {
      if (simulated) return "Paciente simulado";
      return conversationSource === "comercial" ? "Cliente" : "Paciente";
    }
    return "Cliente";
  }
  if (message.sender_type === "ai") return "IA";
  if (message.sender_type === "automation") return "Automacao";
  return "Atendimento";
}

function AdmWhatsAppInbox({
  selectedProspectId,
  onClearProspectFilter,
}: {
  selectedProspectId: string | null;
  onClearProspectFilter: () => void;
}) {
  const threadRef = useRef<HTMLDivElement | null>(null);
  const [search, setSearch] = useState("");
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);

  useEffect(() => {
    setSelectedConversationId(null);
  }, [selectedProspectId]);

  const conversationsQuery = useQuery<{ data: AdmWhatsappConversation[]; meta: { total: number } }>({
    queryKey: ["adm-whatsapp-conversations", selectedProspectId, search],
    queryFn: async () =>
      (
        await api.get("/admin/whatsapp/conversations", {
          params: {
            prospect_id: selectedProspectId || undefined,
            q: search || undefined,
            limit: 300,
          },
        })
      ).data,
    retry: false,
  });

  const conversations = useMemo(() => conversationsQuery.data?.data ?? [], [conversationsQuery.data?.data]);
  const selectedConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === selectedConversationId) ?? conversations[0] ?? null,
    [conversations, selectedConversationId],
  );

  useEffect(() => {
    if (!selectedConversationId && selectedConversation) setSelectedConversationId(selectedConversation.id);
  }, [selectedConversation, selectedConversationId]);

  const messagesQuery = useQuery<{ data: AdmWhatsappMessage[]; conversation: AdmWhatsappConversation }>({
    queryKey: ["adm-whatsapp-messages", selectedConversation?.id],
    queryFn: async () =>
      (await api.get(`/admin/whatsapp/conversations/${selectedConversation?.id}/messages`, { params: { limit: 300 } })).data,
    enabled: Boolean(selectedConversation?.id),
    retry: false,
  });

  const messages = messagesQuery.data?.data ?? [];

  useEffect(() => {
    const node = threadRef.current;
    if (!node) return;
    node.scrollTo({ top: node.scrollHeight });
  }, [messages.length, selectedConversation?.id]);

  return (
    <Card className="overflow-hidden border-stone-200 bg-white">
      <CardContent className="p-0">
        <div className="grid min-h-[720px] lg:grid-cols-[360px_1fr]">
          <aside className="border-b border-stone-200 bg-stone-50/70 lg:border-b-0 lg:border-r">
            <div className="space-y-3 border-b border-stone-200 bg-white p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-emerald-700">Inbox /adm</p>
                  <h2 className="mt-1 text-2xl font-black text-stone-950">WhatsApp</h2>
                </div>
                <Badge className="bg-emerald-100 text-emerald-800">{conversationsQuery.data?.meta?.total ?? conversations.length}</Badge>
              </div>

              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" />
                <Input
                  className="pl-9"
                  placeholder="Pesquisar conversa"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </div>

              {selectedProspectId ? (
                <div className="flex items-center justify-between gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
                  <span className="font-semibold">Clinica selecionada</span>
                  <Button className="h-8 px-3 text-xs" variant="outline" onClick={onClearProspectFilter}>
                    Ver todos
                  </Button>
                </div>
              ) : null}
            </div>

            <div className="max-h-[610px] space-y-2 overflow-y-auto p-3">
              {conversationsQuery.isLoading ? (
                <div className="rounded-lg border border-stone-200 bg-white p-4 text-sm text-stone-500">Carregando conversas...</div>
              ) : conversations.length ? (
                conversations.map((conversation) => {
                  const active = selectedConversation?.id === conversation.id;
                  return (
                    <button
                      key={conversation.id}
                      type="button"
                      className={cn(
                        "w-full rounded-lg border bg-white p-3 text-left transition hover:border-emerald-200 hover:bg-emerald-50/60",
                        active ? "border-emerald-300 bg-emerald-50 shadow-sm" : "border-stone-200",
                      )}
                      onClick={() => setSelectedConversationId(conversation.id)}
                    >
                      <div className="flex items-start gap-3">
                        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-stone-100 text-xs font-black text-stone-700">
                          {initials(conversation.contact_name || conversation.prospect_name)}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <p className="truncate text-sm font-bold text-stone-950">{conversation.contact_name || conversation.prospect_name}</p>
                              <p className="truncate text-xs text-stone-500">{conversation.prospect_name}</p>
                            </div>
                            <span className="shrink-0 text-[11px] text-stone-500">
                              {conversation.last_message_at ? formatRelativeTime(conversation.last_message_at) : "sem data"}
                            </span>
                          </div>
                          <p className="mt-2 line-clamp-2 text-xs leading-5 text-stone-600">
                            {conversation.last_message_preview || conversation.ai_summary || "Sem mensagens ainda."}
                          </p>
                          <div className="mt-2 flex flex-wrap gap-1">
                            <Badge className={conversation.source === "demo" ? "bg-cyan-100 text-cyan-800" : "bg-emerald-100 text-emerald-800"}>
                              {admWhatsappSourceLabel(conversation.source)}
                            </Badge>
                            <Badge className="bg-white text-stone-600">{humanize(conversation.status)}</Badge>
                            {conversation.simulated_patient_messages ? (
                              <Badge className="bg-violet-100 text-violet-800">Paciente simulado</Badge>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    </button>
                  );
                })
              ) : (
                <div className="rounded-lg border border-dashed border-stone-300 bg-white p-6">
                  <EmptyState title="Nenhuma conversa" description="As conversas das demos e do comercial aparecem aqui." />
                </div>
              )}
            </div>
          </aside>

          <section className="flex min-h-[720px] flex-col bg-[#f7f8f5]">
            {selectedConversation ? (
              <>
                <div className="flex flex-col gap-3 border-b border-stone-200 bg-white p-4 md:flex-row md:items-center md:justify-between">
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-stone-100 text-sm font-black text-stone-700">
                      {initials(selectedConversation.contact_name || selectedConversation.prospect_name)}
                    </div>
                    <div className="min-w-0">
                      <h3 className="truncate text-base font-black text-stone-950">
                        {selectedConversation.contact_name || selectedConversation.prospect_name}
                      </h3>
                      <p className="truncate text-xs text-stone-500">
                        {selectedConversation.prospect_name}
                        {selectedConversation.contact_phone ? ` - ${selectedConversation.contact_phone}` : ""}
                      </p>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge className={selectedConversation.source === "demo" ? "bg-cyan-100 text-cyan-800" : "bg-emerald-100 text-emerald-800"}>
                      {admWhatsappSourceLabel(selectedConversation.source)}
                    </Badge>
                    <Badge className="bg-white text-stone-700">{numberFormatter.format(selectedConversation.message_count)} mensagens</Badge>
                    <Badge className="bg-white text-stone-700">{humanize(selectedConversation.status)}</Badge>
                  </div>
                </div>

                {selectedConversation.ai_summary ? (
                  <div className="border-b border-emerald-100 bg-emerald-50 px-5 py-3 text-sm leading-6 text-emerald-950">
                    <strong>Resumo IA:</strong> {selectedConversation.ai_summary}
                  </div>
                ) : null}

                <div ref={threadRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-5 md:px-8">
                  {messagesQuery.isLoading ? (
                    <div className="rounded-lg border border-stone-200 bg-white p-4 text-sm text-stone-500">Carregando mensagens...</div>
                  ) : messages.length ? (
                    messages.map((message) => {
                      const outbound = message.direction === "outbound";
                      const simulated = Boolean(message.payload?.simulated_patient);
                      return (
                        <div key={message.id} className={cn("flex", outbound ? "justify-end" : "justify-start")}>
                          <div
                            className={cn(
                              "max-w-[min(760px,88%)] rounded-2xl px-4 py-3 text-sm shadow-sm",
                              outbound
                                ? "rounded-br-md bg-emerald-600 text-white"
                                : "rounded-bl-md border border-stone-200 bg-white text-stone-800",
                            )}
                          >
                            <div className={cn("mb-1 text-[11px] font-bold uppercase tracking-wide", outbound ? "text-white/75" : "text-stone-500")}>
                              {messageAuthorLabel(message, selectedConversation.source, simulated)}
                            </div>
                            <p className="whitespace-pre-wrap leading-6">{message.body}</p>
                            <div className={cn("mt-2 text-right text-[11px]", outbound ? "text-white/75" : "text-stone-500")}>
                              {formatDateTimeBR(message.created_at)}
                            </div>
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <div className="rounded-lg border border-dashed border-stone-300 bg-white p-8">
                      <EmptyState title="Sem mensagens" description="Quando houver troca no WhatsApp da demo, ela aparece neste painel." />
                    </div>
                  )}
                </div>

                <div className="border-t border-stone-200 bg-white p-4">
                  <div className="flex items-center gap-2 rounded-lg border border-stone-200 bg-stone-50 px-3 py-3 text-sm text-stone-500">
                    <MessageSquareText size={16} />
                    Visualizacao do /adm. O envio continua sendo feito nos fluxos comerciais e nas demos das clinicas.
                  </div>
                </div>
              </>
            ) : (
              <div className="grid flex-1 place-items-center p-8">
                <EmptyState title="Selecione uma conversa" description="Abra uma conversa da lista para acompanhar o historico." />
              </div>
            )}
          </section>
        </div>
      </CardContent>
    </Card>
  );
}

function CreateProspectForm({
  onCreated,
  platformAccounts,
  platformAccountUsage,
}: {
  onCreated: (prospect: Prospect) => void;
  platformAccounts: PlatformWhatsAppAccountItem[];
  platformAccountUsage: Record<string, { prospectId: string; clinicName: string }>;
}) {
  const [open, setOpen] = useState(false);
  const [clinicName, setClinicName] = useState("");
  const [ownerName, setOwnerName] = useState("");
  const [whatsappPhone, setWhatsappPhone] = useState("");
  const [email, setEmail] = useState("");
  const [website, setWebsite] = useState("");
  const [city, setCity] = useState("");
  const [state, setState] = useState("");
  const [address, setAddress] = useState("");
  const [mainPain, setMainPain] = useState("");
  const [leadSource, setLeadSource] = useState("Google/Maps manual");
  const [testPhoneNumber, setTestPhoneNumber] = useState("");
  const [demoWhatsAppAccountId, setDemoWhatsAppAccountId] = useState("");
  const [demoIntakeMode, setDemoIntakeMode] = useState<ProspectDemoIntakeMode>("hybrid");
  const [demoLinkFlowCtaMode, setDemoLinkFlowCtaMode] = useState<ProspectDemoLinkFlowCtaMode>("whatsapp_redirect");
  const [demoAiEnabled, setDemoAiEnabled] = useState(true);
  const [demoWhatsappEnabled, setDemoWhatsappEnabled] = useState(true);
  const [demoMaxConsecutiveAutoReplies, setDemoMaxConsecutiveAutoReplies] = useState(10);
  const [demoBackgroundImageUrl, setDemoBackgroundImageUrl] = useState(DEFAULT_DEMO_BACKGROUND_IMAGE_URL);
  const [demoBackgroundOpacity, setDemoBackgroundOpacity] = useState(DEFAULT_DEMO_BACKGROUND_OPACITY);
  const [services, setServices] = useState("Consulta inicial, Avaliacao clinica, Retorno");
  const [notes, setNotes] = useState("");

  const handleCreateDemoBackgroundUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      const dataUrl = await readImageFileAsDataUrl(file);
      setDemoBackgroundImageUrl(dataUrl);
      toast.success("Imagem da demo carregada na previa.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Nao foi possivel carregar a imagem da demo.");
    }
  };

  const mutation = useMutation({
    mutationFn: async () => {
      const serviceItems = services
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean)
        .map((service_name) => ({ service_name, duration_minutes: service_name.toLowerCase().includes("clareamento") ? 75 : 60 }));
      return (
        await api.post("/admin/prospects", {
          clinic_name: clinicName,
          owner_name: ownerName || null,
          whatsapp_phone: whatsappPhone || null,
          email: email || null,
          website: website || null,
          city: city || null,
          state: state || null,
          main_address: address || null,
          main_pain: mainPain || null,
          lead_source: leadSource || "prospeccao_manual",
          first_contact_channel: "ligacao_whatsapp_manual",
          uses_whatsapp_heavily: true,
          test_phone_number: testPhoneNumber || null,
          proposal_snapshot: {
            demo_whatsapp: {
              account_id: demoWhatsAppAccountId || null,
            },
            demo_intake: buildDemoIntakeSnapshot(demoIntakeMode, demoLinkFlowCtaMode),
            demo_ai: {
              enabled: demoAiEnabled,
              whatsapp_enabled: demoWhatsappEnabled,
              max_consecutive_auto_replies: Math.min(Math.max(demoMaxConsecutiveAutoReplies, 1), 20),
            },
            demo_branding: buildDemoBackgroundSnapshot(demoBackgroundImageUrl, demoBackgroundOpacity),
          },
          notes,
          services: serviceItems,
        })
      ).data as Prospect;
    },
    onSuccess: (data) => {
      toast.success("Clinica cadastrada.");
      setOpen(false);
      setClinicName("");
      setOwnerName("");
      setWhatsappPhone("");
      setEmail("");
      setWebsite("");
      setCity("");
      setState("");
      setAddress("");
      setMainPain("");
      setLeadSource("Google/Maps manual");
      setTestPhoneNumber("");
      setDemoWhatsAppAccountId("");
      setDemoIntakeMode("hybrid");
      setDemoLinkFlowCtaMode("whatsapp_redirect");
      setDemoAiEnabled(true);
      setDemoWhatsappEnabled(true);
      setDemoMaxConsecutiveAutoReplies(10);
      setDemoBackgroundImageUrl(DEFAULT_DEMO_BACKGROUND_IMAGE_URL);
      setDemoBackgroundOpacity(DEFAULT_DEMO_BACKGROUND_OPACITY);
      setNotes("");
      onCreated(data);
    },
    onError: (error) => toast.error(extractApiErrorMessage(error, "Nao foi possivel cadastrar a clinica.")),
  });

  if (!open) {
    return (
      <Card className="overflow-hidden border-stone-200 bg-white">
        <CardContent className="p-0">
          <div className="grid gap-0 lg:grid-cols-[1.15fr_0.85fr]">
            <div className="space-y-5 p-6">
              <div className="inline-flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold uppercase tracking-wide text-emerald-700">
                <ShieldCheck size={14} />
                CRM interno de vendas
              </div>
              <div>
                <h2 className="text-2xl font-black tracking-tight text-stone-950">Cadastrar clinica prospectada</h2>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-stone-600">
                  Salve a clinica que respondeu ao primeiro contato manual, registre dores comerciais e prepare a base para gerar uma demo isolada com dados criveis.
                </p>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <MiniStep number="1" title="Contato" text="Nome, WhatsApp, decisor e origem do lead." />
                <MiniStep number="2" title="Contexto" text="Dor principal, cidade, endereco e observacoes." />
                <MiniStep number="3" title="Demo" text="Servicos iniciais e numero de teste da clinica." />
              </div>
            </div>
            <div className="flex flex-col justify-between border-t border-stone-200 bg-stone-950 p-6 text-white lg:border-l lg:border-t-0">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.18em] text-emerald-300">Operacao rapida</p>
                <h3 className="mt-3 text-xl font-black">Comece com o essencial e refine depois.</h3>
                <p className="mt-2 text-sm leading-6 text-white/65">
                  O cadastro pode nascer simples. Depois voce adiciona unidades, servicos, notas, gera a demo e acompanha o comportamento no painel.
                </p>
              </div>
              <Button className="mt-6 w-full bg-emerald-500 text-stone-950 hover:bg-emerald-400" onClick={() => setOpen(true)}>
                <Plus size={16} />
                Abrir cadastro da clinica
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden border-stone-200 bg-white">
      <CardHeader className="border-b border-stone-200 bg-stone-50/80">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="mb-2 inline-flex items-center gap-2 rounded-full bg-white px-3 py-1 text-xs font-bold uppercase tracking-wide text-stone-500 shadow-sm">
              <Building2 size={14} />
              Novo prospect
            </div>
            <CardTitle className="text-2xl">Cadastrar clinica prospectada</CardTitle>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-stone-600">
              Preencha o suficiente para a {BRAND_NAME} montar uma demo personalizada. Os campos principais ajudam o follow-up, o score comercial e o provisionamento da demo.
            </p>
          </div>
          <Button type="button" variant="outline" onClick={() => setOpen(false)}>
            Cancelar cadastro
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-6 pt-6"
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate();
          }}
        >
          <section className="rounded-2xl border border-stone-200 p-4">
            <SectionIntro
              title="1. Identificacao da clinica"
              text="Dados que aparecem no CRM e ajudam a reconhecer rapidamente quem e o decisor."
            />
            <div className="mt-4 grid gap-3 lg:grid-cols-4">
              <Field label="Nome da clinica" helper="Nome comercial usado no atendimento e na demo." className="lg:col-span-2">
                <Input required placeholder="Ex.: Clinica Sorriso Sul" value={clinicName} onChange={(event) => setClinicName(event.target.value)} />
              </Field>
              <Field label="Dono ou gerente" helper="Opcional, mas ajuda no follow-up.">
                <Input placeholder="Ex.: Dra. Mariana" value={ownerName} onChange={(event) => setOwnerName(event.target.value)} />
              </Field>
              <Field label="Origem do lead" helper="De onde voce encontrou essa clinica.">
                <Input value={leadSource} onChange={(event) => setLeadSource(event.target.value)} />
              </Field>
            </div>
          </section>

          <section className="rounded-2xl border border-stone-200 p-4">
            <SectionIntro
              title="2. Contato e localizacao"
              text="Use o WhatsApp ou telefone do primeiro contato manual. Nada aqui dispara mensagem automatica."
            />
            <div className="mt-4 grid gap-3 lg:grid-cols-4">
              <Field label="WhatsApp principal" helper="Numero usado para falar com a clinica.">
                <Input placeholder="(11) 99999-0000" value={whatsappPhone} onChange={(event) => setWhatsappPhone(event.target.value)} />
              </Field>
              <Field label="E-mail" helper="Opcional para proposta ou acesso futuro.">
                <Input type="email" placeholder="contato@clinica.com.br" value={email} onChange={(event) => setEmail(event.target.value)} />
              </Field>
              <Field label="Cidade" helper="Ajuda a segmentar a prospeccao.">
                <Input placeholder="Osasco" value={city} onChange={(event) => setCity(event.target.value)} />
              </Field>
              <Field label="Estado" helper="UF ou estado.">
                <Input placeholder="SP" value={state} onChange={(event) => setState(event.target.value.toUpperCase())} />
              </Field>
              <Field label="Site ou Instagram" helper="Referencia para revisar depois." className="lg:col-span-2">
                <Input placeholder="https://..." value={website} onChange={(event) => setWebsite(event.target.value)} />
              </Field>
              <Field label="Endereco principal" helper="Se preencher, a demo ja cria uma unidade principal." className="lg:col-span-2">
                <Input placeholder="Rua, numero, bairro" value={address} onChange={(event) => setAddress(event.target.value)} />
              </Field>
            </div>
          </section>

          <section className="rounded-2xl border border-stone-200 p-4">
            <SectionIntro
              title="3. Dor comercial e demo"
              text="Essas informacoes deixam o discurso e a demo mais proximos da realidade da clinica."
            />
            <div className="mt-4 grid gap-3 lg:grid-cols-4">
              <Field label="Principal dor percebida" helper="Ex.: perde paciente no WhatsApp, agenda baguncada, retorno esquecido." className="lg:col-span-2">
                <Input placeholder="WhatsApp desorganizado e perda de pacientes" value={mainPain} onChange={(event) => setMainPain(event.target.value)} />
              </Field>
              <Field label="Numero de teste" helper="Numero que o dono pode usar para testar o fluxo. Se informar sem DDI, assumimos Brasil. Se for internacional, informe com + ou 00.">
                <Input placeholder="(11) 98888-7777 ou +44 7786 004289" value={testPhoneNumber} onChange={(event) => setTestPhoneNumber(event.target.value)} />
              </Field>
              <Field
                label="Numero real da demo"
                helper="Pode ser compartilhado por varias demos. O roteamento usa o numero de teste acima para cair no tenant correto."
                className="lg:col-span-3"
              >
                <select
                  className="h-10 w-full rounded-lg border border-stone-200 bg-white px-3 text-sm"
                  value={demoWhatsAppAccountId}
                  onChange={(event) => setDemoWhatsAppAccountId(event.target.value)}
                >
                  <option value="">Sem numero real vinculado</option>
                  {platformAccounts.map((account) => {
                    const usage = platformAccountUsage[account.id];
                    return (
                      <option key={account.id} value={account.id}>
                        {platformWhatsAppAccountLabel(account)}
                        {account.is_active ? "" : " (inativo)"}
                        {usage ? ` - compartilhado com ${usage.clinicName}` : ""}
                      </option>
                    );
                  })}
                </select>
              </Field>
              <Field label="Controles da demo" helper="Essas chaves valem para o numero de teste da clinica quando a demo for gerada." className="lg:col-span-4">
                <div className="grid gap-3 lg:grid-cols-3">
                  <div className="rounded-xl border border-stone-200 bg-white px-4 py-3">
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Modo da clinica na demo</label>
                    <select
                      className="mt-2 h-10 w-full rounded-lg border border-stone-200 bg-white px-3 text-sm"
                      value={demoIntakeMode}
                      onChange={(event) => setDemoIntakeMode(event.target.value as ProspectDemoIntakeMode)}
                    >
                      <option value="official_api">API oficial</option>
                      <option value="link_flow">Link flow</option>
                      <option value="hybrid">Hybrid</option>
                    </select>
                    <p className="mt-2 text-xs text-stone-500">Escolha como essa clinica vai operar na demonstracao.</p>
                  </div>
                  <div className="rounded-xl border border-stone-200 bg-white px-4 py-3">
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Entrada publica do link flow</label>
                    <select
                      className="mt-2 h-10 w-full rounded-lg border border-stone-200 bg-white px-3 text-sm disabled:opacity-60"
                      value={demoLinkFlowCtaMode}
                      onChange={(event) => setDemoLinkFlowCtaMode(event.target.value as ProspectDemoLinkFlowCtaMode)}
                      disabled={demoIntakeMode === "official_api"}
                    >
                      <option value="whatsapp_redirect">WhatsApp redirect</option>
                      <option value="webchat">Webchat</option>
                    </select>
                    <p className="mt-2 text-xs text-stone-500">Vale quando o modo estiver em link flow ou hybrid.</p>
                  </div>
                  <label className="flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm">
                    <input type="checkbox" checked={demoAiEnabled} onChange={(event) => setDemoAiEnabled(event.target.checked)} />
                    IA da demo ligada
                  </label>
                  <label className="flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm">
                    <input type="checkbox" checked={demoWhatsappEnabled} onChange={(event) => setDemoWhatsappEnabled(event.target.checked)} />
                    WhatsApp de teste ligado
                  </label>
                  <div className="rounded-xl border border-stone-200 bg-white px-4 py-3">
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                      Limite de respostas da IA
                    </label>
                    <Input
                      className="mt-2"
                      type="number"
                      min={1}
                      max={20}
                      value={String(demoMaxConsecutiveAutoReplies)}
                      onChange={(event) => setDemoMaxConsecutiveAutoReplies(Number(event.target.value || 10))}
                    />
                    <p className="mt-2 text-xs text-stone-500">Para teste, 10 costuma evitar handoff cedo demais.</p>
                  </div>
                </div>
              </Field>
              <DemoBackgroundFieldset
                imageUrl={demoBackgroundImageUrl}
                opacity={demoBackgroundOpacity}
                helper="A imagem padrao ja entra carregada. Se quiser, troque por outra do dispositivo e ajuste a transparencia antes de salvar."
                onUpload={handleCreateDemoBackgroundUpload}
                onResetToDefault={() => {
                  setDemoBackgroundImageUrl(DEFAULT_DEMO_BACKGROUND_IMAGE_URL);
                  toast.success("Fundo da demo voltou para a imagem padrao.");
                }}
                onOpacityChange={setDemoBackgroundOpacity}
                disabled={mutation.isPending}
              />
              <Field label="Servicos da clinica" helper="Separe por virgula. A demo usa isso para equipe, agenda e IA." className="lg:col-span-4">
                <textarea
                  className="min-h-[92px] w-full rounded-xl border border-stone-300 bg-white px-4 py-3 text-sm outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15"
                  value={services}
                  onChange={(event) => setServices(event.target.value)}
                />
              </Field>
              <Field label="Observacoes internas" helper="Notas para abordagem, objeções ou contexto da conversa." className="lg:col-span-4">
                <textarea
                  className="min-h-[104px] w-full rounded-xl border border-stone-300 bg-white px-4 py-3 text-sm outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15"
                  placeholder="Ex.: respondeu pelo WhatsApp, quer falar com o gerente, ja usa outro sistema..."
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                />
              </Field>
            </div>
          </section>

          <div className="flex flex-col gap-3 rounded-2xl border border-emerald-100 bg-emerald-50 p-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="font-bold text-emerald-950">Depois de criar, selecione a clinica na tabela.</p>
              <p className="mt-1 text-sm text-emerald-800">Voce podera gerar a demo personalizada, copiar o acesso e acompanhar os eventos comerciais.</p>
            </div>
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Fechar
              </Button>
              <Button disabled={mutation.isPending}>
                <ArrowRight size={16} />
                {mutation.isPending ? "Criando..." : "Criar prospect"}
              </Button>
            </div>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function EditProspectDrawer({
  prospect,
  open,
  onOpenChange,
  onSaved,
  platformAccounts,
  platformAccountUsage,
}: {
  prospect: Prospect | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: (prospect: Prospect) => void;
  platformAccounts: PlatformWhatsAppAccountItem[];
  platformAccountUsage: Record<string, { prospectId: string; clinicName: string }>;
}) {
  const [form, setForm] = useState<ProspectEditFormState>(() =>
    prospect
      ? prospectToEditForm(prospect)
      : {
          clinic_name: "",
          owner_name: "",
          manager_name: "",
          phone: "",
          whatsapp_phone: "",
          email: "",
          website: "",
          city: "",
          state: "",
          main_address: "",
          main_pain: "",
          lead_source: "",
          status: "novo",
          test_phone_number: "",
          demo_whatsapp_account_id: "",
          demo_intake_mode: "hybrid",
          demo_link_flow_cta_mode: "whatsapp_redirect",
          demo_ai_enabled: true,
          demo_whatsapp_enabled: true,
          demo_max_consecutive_auto_replies: 10,
          demo_background_image_url: DEFAULT_DEMO_BACKGROUND_IMAGE_URL,
          demo_background_opacity: DEFAULT_DEMO_BACKGROUND_OPACITY,
          services: [],
          notes: "",
          do_not_contact: false,
        },
  );

  useEffect(() => {
    if (open && prospect) {
      setForm(prospectToEditForm(prospect));
    }
  }, [open, prospect]);

  const updateField = <Key extends keyof ProspectEditFormState>(key: Key, value: ProspectEditFormState[Key]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const updateServiceField = (
    index: number,
    key: keyof ProspectEditFormState["services"][number],
    value: string | number,
  ) => {
    setForm((current) => ({
      ...current,
      services: current.services.map((service, currentIndex) =>
        currentIndex === index ? { ...service, [key]: value } : service,
      ),
    }));
  };

  const addServiceField = () => {
    setForm((current) => ({
      ...current,
      services: [...current.services, createEditableProspectService(undefined, current.services.length)],
    }));
  };

  const removeServiceField = (index: number) => {
    setForm((current) => ({
      ...current,
      services: current.services.filter((_, currentIndex) => currentIndex !== index),
    }));
  };

  const handleEditDemoBackgroundUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      const dataUrl = await readImageFileAsDataUrl(file);
      updateField("demo_background_image_url", dataUrl);
      toast.success("Nova imagem da demo carregada na previa.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Nao foi possivel carregar a imagem da demo.");
    }
  };

  const mutation = useMutation({
    mutationFn: async () => {
      if (!prospect) throw new Error("Prospect nao selecionado.");
      return (
        await api.patch(`/admin/prospects/${prospect.id}`, {
          clinic_name: form.clinic_name.trim(),
          owner_name: nullableText(form.owner_name),
          manager_name: nullableText(form.manager_name),
          phone: nullableText(form.phone),
          whatsapp_phone: nullableText(form.whatsapp_phone),
          email: nullableText(form.email),
          website: nullableText(form.website),
          city: nullableText(form.city),
          state: nullableText(form.state.toUpperCase()),
          main_address: nullableText(form.main_address),
          main_pain: nullableText(form.main_pain),
          lead_source: nullableText(form.lead_source),
          status: form.status,
          test_phone_number: nullableText(form.test_phone_number),
          proposal_snapshot: {
            ...(prospect.proposal_snapshot ?? {}),
            demo_whatsapp: {
              account_id: nullableText(form.demo_whatsapp_account_id),
            },
            demo_intake: buildDemoIntakeSnapshot(form.demo_intake_mode, form.demo_link_flow_cta_mode),
            demo_ai: {
              enabled: form.demo_ai_enabled,
              whatsapp_enabled: form.demo_whatsapp_enabled,
              max_consecutive_auto_replies: Math.min(Math.max(form.demo_max_consecutive_auto_replies, 1), 20),
            },
            demo_branding: buildDemoBackgroundSnapshot(form.demo_background_image_url, form.demo_background_opacity),
          },
          services: form.services
            .map((service) => ({
              service_name: service.service_name.trim(),
              price_range: nullableText(service.price_range),
              duration_minutes: Math.min(Math.max(Number(service.duration_minutes) || 60, 15), 480),
              description: service.description.trim() || service.service_name.trim(),
              category: nullableText(service.category),
            }))
            .filter((service) => service.service_name.length >= 2),
          notes: form.notes,
          do_not_contact: form.do_not_contact,
        })
      ).data as Prospect;
    },
    onSuccess: (updatedProspect) => {
      toast.success("Clinica atualizada.");
      onSaved(updatedProspect);
      onOpenChange(false);
    },
    onError: (error) => toast.error(extractApiErrorMessage(error, "Nao foi possivel atualizar a clinica.")),
  });

  return (
    <RightDrawer
      open={open}
      onOpenChange={onOpenChange}
      title={prospect ? `Editar ${prospect.clinic_name}` : "Editar clinica"}
      description="Atualize os dados comerciais usados no CRM e na demo."
      widthClassName="w-full sm:max-w-3xl"
    >
      {prospect ? (
        <form
          className="space-y-5"
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate();
          }}
        >
          <section className="rounded-2xl border border-stone-200 p-4">
            <SectionIntro title="Identificacao" text="Nome, decisores e origem comercial desta clinica." />
            <div className="mt-4 grid gap-3 lg:grid-cols-4">
              <Field label="Nome da clinica" helper="Nome comercial usado na tabela e na demo." className="lg:col-span-2">
                <Input
                  required
                  value={form.clinic_name}
                  onChange={(event) => updateField("clinic_name", event.target.value)}
                  disabled={mutation.isPending}
                />
              </Field>
              <Field label="Dono" helper="Principal decisor, se ja conhecido.">
                <Input value={form.owner_name} onChange={(event) => updateField("owner_name", event.target.value)} disabled={mutation.isPending} />
              </Field>
              <Field label="Gerente" helper="Contato operacional ou gerente.">
                <Input value={form.manager_name} onChange={(event) => updateField("manager_name", event.target.value)} disabled={mutation.isPending} />
              </Field>
              <Field label="Origem do lead" helper="Canal ou busca que gerou o contato." className="lg:col-span-2">
                <Input value={form.lead_source} onChange={(event) => updateField("lead_source", event.target.value)} disabled={mutation.isPending} />
              </Field>
              <Field label="Status" helper="Etapa atual do pipeline.">
                <select
                  className="h-10 w-full rounded-lg border border-stone-200 bg-white px-3 text-sm disabled:opacity-60"
                  value={form.status}
                  onChange={(event) => updateField("status", event.target.value)}
                  disabled={mutation.isPending}
                >
                  {STATUS_OPTIONS.map((status) => (
                    <option key={status} value={status}>
                      {humanize(status)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Nao contactar" helper="Bloqueia novas abordagens comerciais.">
                <label className="flex h-10 items-center gap-2 rounded-lg border border-stone-200 bg-white px-3 text-sm">
                  <input
                    type="checkbox"
                    checked={form.do_not_contact}
                    onChange={(event) => updateField("do_not_contact", event.target.checked)}
                    disabled={mutation.isPending}
                  />
                  Bloqueado
                </label>
              </Field>
            </div>
          </section>

          <section className="rounded-2xl border border-stone-200 p-4">
            <SectionIntro title="Contato e localizacao" text="Dados usados para abordagem comercial, WhatsApp e proposta." />
            <div className="mt-4 grid gap-3 lg:grid-cols-4">
              <Field label="WhatsApp principal" helper="Numero preferencial para falar com a clinica.">
                <Input value={form.whatsapp_phone} onChange={(event) => updateField("whatsapp_phone", event.target.value)} disabled={mutation.isPending} />
              </Field>
              <Field label="Telefone" helper="Telefone alternativo.">
                <Input value={form.phone} onChange={(event) => updateField("phone", event.target.value)} disabled={mutation.isPending} />
              </Field>
              <Field label="E-mail" helper="Usado em proposta ou follow-up.">
                <Input type="email" value={form.email} onChange={(event) => updateField("email", event.target.value)} disabled={mutation.isPending} />
              </Field>
              <Field label="Numero de teste" helper="Numero que o dono usa para testar a demo.">
                <Input value={form.test_phone_number} onChange={(event) => updateField("test_phone_number", event.target.value)} disabled={mutation.isPending} />
              </Field>
              <Field
                label="Numero real da demo"
                helper="Pode ser compartilhado por varias demos. O roteamento usa o numero de teste acima para cair no tenant correto."
                className="lg:col-span-3"
              >
                <select
                  className="h-10 w-full rounded-lg border border-stone-200 bg-white px-3 text-sm disabled:opacity-60"
                  value={form.demo_whatsapp_account_id}
                  onChange={(event) => updateField("demo_whatsapp_account_id", event.target.value)}
                  disabled={mutation.isPending}
                >
                  <option value="">Sem numero real vinculado</option>
                  {platformAccounts.map((account) => {
                    const usage = platformAccountUsage[account.id];
                    return (
                      <option key={account.id} value={account.id}>
                        {platformWhatsAppAccountLabel(account)}
                        {account.is_active ? "" : " (inativo)"}
                        {usage ? ` - compartilhado com ${usage.clinicName}` : ""}
                      </option>
                    );
                  })}
                </select>
              </Field>
              <Field label="Controles da demo" helper={prospect.demo_tenant_id ? "Ao salvar, atualiza a demo atual desta clinica." : "Sera aplicado quando a demo desta clinica for gerada."} className="lg:col-span-4">
                <div className="grid gap-3 lg:grid-cols-3">
                  <div className="rounded-xl border border-stone-200 bg-white px-4 py-3">
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Modo da clinica na demo</label>
                    <select
                      className="mt-2 h-10 w-full rounded-lg border border-stone-200 bg-white px-3 text-sm disabled:opacity-60"
                      value={form.demo_intake_mode}
                      onChange={(event) => updateField("demo_intake_mode", event.target.value as ProspectDemoIntakeMode)}
                      disabled={mutation.isPending}
                    >
                      <option value="official_api">API oficial</option>
                      <option value="link_flow">Link flow</option>
                      <option value="hybrid">Hybrid</option>
                    </select>
                    <p className="mt-2 text-xs text-stone-500">Defina se a demo usa API oficial, link flow ou coexistencia dos dois.</p>
                  </div>
                  <div className="rounded-xl border border-stone-200 bg-white px-4 py-3">
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Entrada publica do link flow</label>
                    <select
                      className="mt-2 h-10 w-full rounded-lg border border-stone-200 bg-white px-3 text-sm disabled:opacity-60"
                      value={form.demo_link_flow_cta_mode}
                      onChange={(event) =>
                        updateField("demo_link_flow_cta_mode", event.target.value as ProspectDemoLinkFlowCtaMode)
                      }
                      disabled={mutation.isPending || form.demo_intake_mode === "official_api"}
                    >
                      <option value="whatsapp_redirect">WhatsApp redirect</option>
                      <option value="webchat">Webchat</option>
                    </select>
                    <p className="mt-2 text-xs text-stone-500">Use webchat para testar a landing com chat embutido.</p>
                  </div>
                  <label className="flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm">
                    <input
                      type="checkbox"
                      checked={form.demo_ai_enabled}
                      onChange={(event) => updateField("demo_ai_enabled", event.target.checked)}
                      disabled={mutation.isPending}
                    />
                    IA da demo ligada
                  </label>
                  <label className="flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm">
                    <input
                      type="checkbox"
                      checked={form.demo_whatsapp_enabled}
                      onChange={(event) => updateField("demo_whatsapp_enabled", event.target.checked)}
                      disabled={mutation.isPending}
                    />
                    WhatsApp de teste ligado
                  </label>
                  <div className="rounded-xl border border-stone-200 bg-white px-4 py-3">
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                      Limite de respostas da IA
                    </label>
                    <Input
                      className="mt-2"
                      type="number"
                      min={1}
                      max={20}
                      value={String(form.demo_max_consecutive_auto_replies)}
                      onChange={(event) =>
                        updateField("demo_max_consecutive_auto_replies", Number(event.target.value || 10))
                      }
                      disabled={mutation.isPending}
                    />
                    <p className="mt-2 text-xs text-stone-500">Ao atingir esse numero, a conversa vai para handoff humano.</p>
                  </div>
                </div>
              </Field>
              <DemoBackgroundFieldset
                imageUrl={form.demo_background_image_url}
                opacity={form.demo_background_opacity}
                helper={
                  prospect.demo_tenant_id
                    ? "Ao salvar, a imagem e a transparencia passam a valer tambem na demo ja criada."
                    : "Essa configuracao fica pronta e sera aplicada quando a demo desta clinica for gerada."
                }
                onUpload={handleEditDemoBackgroundUpload}
                onResetToDefault={() => {
                  updateField("demo_background_image_url", DEFAULT_DEMO_BACKGROUND_IMAGE_URL);
                  toast.success("Fundo da demo voltou para a imagem padrao.");
                }}
                onOpacityChange={(opacity) => updateField("demo_background_opacity", opacity)}
                disabled={mutation.isPending}
              />
              <Field label="Cidade" helper="Cidade da clinica.">
                <Input value={form.city} onChange={(event) => updateField("city", event.target.value)} disabled={mutation.isPending} />
              </Field>
              <Field label="Estado" helper="UF ou estado.">
                <Input value={form.state} onChange={(event) => updateField("state", event.target.value.toUpperCase())} disabled={mutation.isPending} />
              </Field>
              <Field label="Site ou Instagram" helper="Referencia publica para revisar depois." className="lg:col-span-2">
                <Input value={form.website} onChange={(event) => updateField("website", event.target.value)} disabled={mutation.isPending} />
              </Field>
              <Field label="Endereco principal" helper="Endereco usado na demo e no resumo comercial." className="lg:col-span-4">
                <Input value={form.main_address} onChange={(event) => updateField("main_address", event.target.value)} disabled={mutation.isPending} />
              </Field>
            </div>
          </section>

          <section className="rounded-2xl border border-stone-200 p-4">
            <SectionIntro title="Contexto comercial" text="Dor percebida e observacoes internas para o follow-up." />
            <div className="mt-4 grid gap-3">
              <Field
                label="Servicos da clinica"
                helper="Edite os servicos oficiais e o preco exibido na demo. Ao salvar, isso atualiza a demo atual desta clinica."
              >
                <div className="space-y-3">
                  {form.services.length ? (
                    form.services.map((service, index) => (
                      <div key={service.id} className="rounded-2xl border border-stone-200 bg-stone-50 p-3">
                        <div className="grid gap-3 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_110px]">
                          <div>
                            <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Servico</label>
                            <Input
                              className="mt-2"
                              value={service.service_name}
                              onChange={(event) => updateServiceField(index, "service_name", event.target.value)}
                              disabled={mutation.isPending}
                              placeholder="Ex.: Lente em resina"
                            />
                          </div>
                          <div>
                            <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Preco</label>
                            <Input
                              className="mt-2"
                              value={service.price_range}
                              onChange={(event) => updateServiceField(index, "price_range", event.target.value)}
                              disabled={mutation.isPending}
                              placeholder="Ex.: A partir de R$ 1.200"
                            />
                          </div>
                          <div className="flex items-end">
                            <Button
                              type="button"
                              variant="outline"
                              className="w-full"
                              onClick={() => removeServiceField(index)}
                              disabled={mutation.isPending}
                            >
                              Remover
                            </Button>
                          </div>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="rounded-2xl border border-dashed border-stone-300 bg-stone-50 px-4 py-5 text-sm text-stone-600">
                      Nenhum servico cadastrado ainda. Adicione o primeiro abaixo.
                    </div>
                  )}
                  <Button type="button" variant="outline" onClick={addServiceField} disabled={mutation.isPending}>
                    <Plus size={16} />
                    Adicionar servico
                  </Button>
                </div>
              </Field>
              <Field label="Principal dor percebida" helper="Ex.: perde paciente no WhatsApp, agenda baguncada, retorno esquecido.">
                <Input value={form.main_pain} onChange={(event) => updateField("main_pain", event.target.value)} disabled={mutation.isPending} />
              </Field>
              <Field label="Observacoes internas" helper="Notas para abordagem, objecoes ou contexto da conversa.">
                <textarea
                  className="min-h-[140px] w-full rounded-xl border border-stone-300 bg-white px-4 py-3 text-sm outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15 disabled:opacity-60"
                  value={form.notes}
                  onChange={(event) => updateField("notes", event.target.value)}
                  disabled={mutation.isPending}
                />
              </Field>
            </div>
          </section>

          <div className="sticky bottom-0 -mx-4 border-t border-stone-200 bg-white/95 px-4 py-3 backdrop-blur sm:-mx-5 sm:px-5 lg:-mx-6 lg:px-6">
            <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={mutation.isPending}>
                Cancelar
              </Button>
              <Button disabled={mutation.isPending || !form.clinic_name.trim()}>
                <Pencil size={16} />
                {mutation.isPending ? "Salvando..." : "Salvar alteracoes"}
              </Button>
            </div>
          </div>
        </form>
      ) : null}
    </RightDrawer>
  );
}

function MiniStep({ number, title, text }: { number: string; title: string; text: string }) {
  return (
    <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
      <div className="mb-3 grid h-8 w-8 place-items-center rounded-full bg-stone-950 text-xs font-black text-white">{number}</div>
      <p className="font-bold text-stone-950">{title}</p>
      <p className="mt-1 text-xs leading-5 text-stone-600">{text}</p>
    </div>
  );
}

function SectionIntro({ title, text }: { title: string; text: string }) {
  return (
    <div>
      <h3 className="text-base font-black text-stone-950">{title}</h3>
      <p className="mt-1 text-sm leading-6 text-stone-600">{text}</p>
    </div>
  );
}

function Field({
  label,
  helper,
  className,
  children,
}: {
  label: string;
  helper: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <label className={cn("block space-y-2", className)}>
      <span className="text-xs font-bold uppercase tracking-wide text-stone-500">{label}</span>
      {children}
      <span className="block text-xs leading-5 text-stone-500">{helper}</span>
    </label>
  );
}

export default function AdmPage() {
  const queryClient = useQueryClient();
  const [hasToken, setHasToken] = useState(false);
  const [forcePasswordChange, setForcePasswordChange] = useState(false);
  const [activeSection, setActiveSection] = useState<AdmSection>("crm");
  const [admWhatsappProspectId, setAdmWhatsappProspectId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editingProspect, setEditingProspect] = useState<Prospect | null>(null);
  const [editDrawerOpen, setEditDrawerOpen] = useState(false);
  const [officialWhatsAppProspect, setOfficialWhatsAppProspect] = useState<Prospect | null>(null);
  const [officialTemplateKey, setOfficialTemplateKey] = useState("");
  const [officialMessageKey, setOfficialMessageKey] = useState("");
  const [officialMessagePreview, setOfficialMessagePreview] = useState<MessagePreview | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [appOrigin, setAppOrigin] = useState("");
  const [lastDemoLink, setLastDemoLink] = useState("");
  const [lastBookingLink, setLastBookingLink] = useState("");

  useEffect(() => {
    setHasToken(Boolean(getAdminAccessToken()));
    setAppOrigin(resolveBrowserOrigin());
  }, []);

  const overviewQuery = useQuery<Overview>({
    queryKey: ["adm-overview"],
    queryFn: async () => (await api.get("/admin/prospects/overview")).data,
    enabled: hasToken && !forcePasswordChange,
    retry: false,
  });

  const prospectsQuery = useQuery<{ data: Prospect[]; total: number }>({
    queryKey: ["adm-prospects", statusFilter, search],
    queryFn: async () =>
      (
        await api.get("/admin/prospects", {
          params: { status: statusFilter || undefined, q: search || undefined, limit: 200, offset: 0 },
        })
      ).data,
    enabled: hasToken && !forcePasswordChange,
    retry: false,
  });

  const platformAccountsQuery = useQuery<{ data: PlatformWhatsAppAccountItem[] }>({
    queryKey: ["adm-platform-whatsapp-accounts"],
    queryFn: async () => (await api.get("/admin/platform/whatsapp/accounts")).data,
    enabled: hasToken && !forcePasswordChange,
    retry: false,
  });

  const officialTemplatesQuery = useQuery<SalesTemplate[]>({
    queryKey: ["adm-clinic-message-templates"],
    queryFn: async () => (await api.get("/admin/clinic-messages/templates")).data,
    enabled: hasToken && !forcePasswordChange,
    retry: false,
  });

  const selectedProspect = useMemo(() => {
    const rows = prospectsQuery.data?.data ?? [];
    return rows.find((item) => item.id === selectedId) ?? rows[0] ?? null;
  }, [prospectsQuery.data?.data, selectedId]);

  const platformAccounts = useMemo(
    () =>
      [...(platformAccountsQuery.data?.data ?? [])].sort((left, right) => {
        if (left.is_active !== right.is_active) return left.is_active ? -1 : 1;
        return platformWhatsAppAccountLabel(left).localeCompare(platformWhatsAppAccountLabel(right));
      }),
    [platformAccountsQuery.data?.data],
  );

  const officialTemplates = useMemo(() => officialTemplatesQuery.data ?? [], [officialTemplatesQuery.data]);
  const selectedOfficialTemplate = useMemo(
    () => officialTemplates.find((template) => template.key === officialTemplateKey) ?? officialTemplates[0] ?? null,
    [officialTemplateKey, officialTemplates],
  );
  const selectedOfficialTemplateMessage = useMemo(() => {
    const messages = selectedOfficialTemplate?.messages ?? [];
    return (
      messages.find((message) => message.key === officialMessageKey) ??
      messages.find((message) => message.is_default) ??
      messages[0] ??
      null
    );
  }, [officialMessageKey, selectedOfficialTemplate]);

  const platformAccountUsage = useMemo(() => {
    const usage: Record<string, { prospectId: string; clinicName: string }> = {};
    for (const prospect of prospectsQuery.data?.data ?? []) {
      const accountId = getDemoWhatsAppSettingsSnapshot(prospect).account_id;
      if (!accountId) continue;
      usage[accountId] = {
        prospectId: prospect.id,
        clinicName: prospect.clinic_name,
      };
    }
    return usage;
  }, [prospectsQuery.data?.data]);

  useEffect(() => {
    if (!selectedId && selectedProspect) setSelectedId(selectedProspect.id);
  }, [selectedId, selectedProspect]);

  useEffect(() => {
    setLastDemoLink("");
    setLastBookingLink("");
  }, [selectedId]);

  useEffect(() => {
    if (!officialWhatsAppProspect || !officialTemplates.length) return;
    if (!selectedOfficialTemplate) {
      const fallbackTemplate = officialTemplates[0];
      const fallbackMessage =
        fallbackTemplate.messages.find((message) => message.is_default) ?? fallbackTemplate.messages[0] ?? null;
      setOfficialTemplateKey(fallbackTemplate.key);
      setOfficialMessageKey(fallbackMessage?.key ?? "");
      return;
    }
    if (!selectedOfficialTemplateMessage) {
      const fallbackMessage =
        selectedOfficialTemplate.messages.find((message) => message.is_default) ?? selectedOfficialTemplate.messages[0] ?? null;
      setOfficialMessageKey(fallbackMessage?.key ?? "");
    }
  }, [
    officialTemplates,
    officialWhatsAppProspect,
    selectedOfficialTemplate,
    selectedOfficialTemplateMessage,
  ]);

  const syncLatestDemoLinks = (payload: DemoLinkPayload | null | undefined) => {
    const nextDemoLink = `${payload?.demo_login_url || ""}`.trim();
    const nextBookingLink = resolvePayloadBookingLink(payload, resolveBrowserOrigin() || appOrigin);
    setLastDemoLink(nextDemoLink);
    setLastBookingLink(nextBookingLink);
  };

  const selectedProspectBookingLink = useMemo(
    () => resolveProspectBookingLink(selectedProspect, appOrigin),
    [appOrigin, selectedProspect],
  );

  const timelineQuery = useQuery<TimelineEvent[]>({
    queryKey: ["adm-prospect-timeline", selectedProspect?.id],
    queryFn: async () => (await api.get(`/admin/prospects/${selectedProspect?.id}/timeline`)).data,
    enabled: hasToken && !forcePasswordChange && Boolean(selectedProspect?.id),
  });

  const activityQuery = useQuery<ActivityEvent[]>({
    queryKey: ["adm-prospect-activity", selectedProspect?.id],
    queryFn: async () => (await api.get(`/admin/prospects/${selectedProspect?.id}/activity`)).data,
    enabled: hasToken && !forcePasswordChange && Boolean(selectedProspect?.id),
  });

  const generateDemoMutation = useMutation({
    mutationFn: async (prospectId: string) => (await api.post(`/admin/prospects/${prospectId}/generate-demo`)).data,
    onSuccess: (data) => {
      syncLatestDemoLinks(data);
      navigator.clipboard?.writeText(data.demo_login_url);
      toast.success("Demo gerada. Link da demo copiado e agendamento pronto para copiar.");
      queryClient.invalidateQueries({ queryKey: ["adm-prospects"] });
      queryClient.invalidateQueries({ queryKey: ["adm-overview"] });
      queryClient.invalidateQueries({ queryKey: ["adm-prospect-timeline"] });
      queryClient.invalidateQueries({ queryKey: ["adm-whatsapp-conversations"] });
    },
    onError: () => toast.error("Nao foi possivel gerar a demo."),
  });

  const accessMutation = useMutation({
    mutationFn: async (prospectId: string) => (await api.post(`/admin/prospects/${prospectId}/send-demo-access`)).data,
    onSuccess: (data) => {
      syncLatestDemoLinks(data);
      navigator.clipboard?.writeText(data.demo_login_url);
      toast.success("Link de demo copiado.");
      queryClient.invalidateQueries({ queryKey: ["adm-prospects"] });
      queryClient.invalidateQueries({ queryKey: ["adm-prospect-timeline"] });
      queryClient.invalidateQueries({ queryKey: ["adm-whatsapp-conversations"] });
    },
    onError: () => toast.error("Nao foi possivel emitir acesso."),
  });

  const statusMutation = useMutation({
    mutationFn: async ({ prospectId, status }: { prospectId: string; status: string }) =>
      (await api.post(`/admin/prospects/${prospectId}/mark-status`, { status })).data,
    onSuccess: () => {
      toast.success("Status atualizado.");
      queryClient.invalidateQueries({ queryKey: ["adm-prospects"] });
      queryClient.invalidateQueries({ queryKey: ["adm-overview"] });
      queryClient.invalidateQueries({ queryKey: ["adm-prospect-timeline"] });
      queryClient.invalidateQueries({ queryKey: ["adm-whatsapp-conversations"] });
    },
  });

  const contactMutation = useMutation({
    mutationFn: async (prospectId: string) =>
      (
        await api.post(`/admin/prospects/${prospectId}/record-contact`, {
          channel: "ligacao_whatsapp_manual",
          summary: "Contato manual registrado pelo /adm.",
          next_step: "Enviar ou acompanhar demo personalizada.",
        })
      ).data,
    onSuccess: () => {
      toast.success("Contato registrado.");
      queryClient.invalidateQueries({ queryKey: ["adm-prospects"] });
      queryClient.invalidateQueries({ queryKey: ["adm-prospect-timeline"] });
    },
  });

  const outreachMutation = useMutation({
    mutationFn: async ({
      prospectId,
      step,
      recipientName,
    }: {
      prospectId: string;
      step: "reception_intro" | "decision_maker_pitch" | "video_followup";
      recipientName?: string | null;
    }) =>
      (
        await api.post<OutreachResult>(
          `/admin/prospects/${prospectId}/outreach`,
          {
            step,
            recipient_name: recipientName || null,
          },
        )
      ).data,
    onSuccess: (data) => {
      if (data.demo_login_url) {
        syncLatestDemoLinks(data);
        navigator.clipboard?.writeText(data.demo_login_url);
      }
      const label =
        data.step === "reception_intro"
          ? "Contato com recepção enviado."
          : data.step === "decision_maker_pitch"
            ? "Apresentação com demo enviada."
            : "Follow-up com vídeo enviado.";
      toast.success(label);
      queryClient.invalidateQueries({ queryKey: ["adm-prospects"] });
      queryClient.invalidateQueries({ queryKey: ["adm-overview"] });
      queryClient.invalidateQueries({ queryKey: ["adm-prospect-timeline"] });
      queryClient.invalidateQueries({ queryKey: ["adm-whatsapp-conversations"] });
    },
    onError: (error: unknown) => {
      const response = (error as { response?: { data?: { error?: { message?: string } } } }).response;
      toast.error(response?.data?.error?.message || "Nao foi possivel enviar o outreach comercial.");
    },
  });

  const automationMutation = useMutation({
    mutationFn: async (prospectId: string) =>
      (await api.post<OutreachResult>(`/admin/prospects/${prospectId}/outreach/automation/start`)).data,
    onSuccess: (data) => {
      if (data.demo_login_url) {
        syncLatestDemoLinks(data);
        navigator.clipboard?.writeText(data.demo_login_url);
      }
      toast.success("Automacao comercial iniciada. O WhatsApp vai acompanhar a resposta e avancar para pitch e video.");
      queryClient.invalidateQueries({ queryKey: ["adm-prospects"] });
      queryClient.invalidateQueries({ queryKey: ["adm-overview"] });
      queryClient.invalidateQueries({ queryKey: ["adm-prospect-timeline"] });
      queryClient.invalidateQueries({ queryKey: ["adm-whatsapp-conversations"] });
    },
    onError: (error: unknown) => {
      const response = (error as { response?: { data?: { error?: { message?: string } } } }).response;
      toast.error(response?.data?.error?.message || "Nao foi possivel iniciar a automacao comercial.");
    },
  });

  const outreachLabMutation = useMutation({
    mutationFn: async ({ prospectId, scenario }: { prospectId: string; scenario: string }) =>
      (
        await api.post<OutreachLabResult>(`/admin/prospects/${prospectId}/outreach/lab`, {
          scenario,
        })
      ).data,
    onSuccess: (data) => {
      if (data.demo_login_url) {
        syncLatestDemoLinks(data);
      }
      toast.success(
        data.converted
          ? "IA Lab comercial concluiu a simulacao com proximo passo claro."
          : "IA Lab comercial concluiu a simulacao e mostrou onde o fluxo trava.",
      );
      queryClient.invalidateQueries({ queryKey: ["adm-prospects"] });
      queryClient.invalidateQueries({ queryKey: ["adm-overview"] });
      queryClient.invalidateQueries({ queryKey: ["adm-prospect-timeline"] });
    },
    onError: (error: unknown) => {
      const response = (error as { response?: { data?: { error?: { message?: string } } } }).response;
      toast.error(response?.data?.error?.message || "Nao foi possivel rodar o IA Lab comercial.");
    },
  });

  const officialMessagePreviewMutation = useMutation({
    mutationFn: async ({
      prospectId,
      templateKey,
      messageKey,
    }: {
      prospectId: string;
      templateKey: string;
      messageKey: string;
    }) =>
      (
        await api.post<MessagePreview>("/admin/clinic-messages/preview", {
          prospect_id: prospectId,
          template_key: templateKey || null,
          message_key: messageKey || null,
          issue_demo_access: true,
        })
      ).data,
    onSuccess: (data) => {
      setOfficialMessagePreview(data);
      setOfficialTemplateKey(data.template_key);
      setOfficialMessageKey(data.message_key);
      queryClient.invalidateQueries({ queryKey: ["adm-prospects"] });
      queryClient.invalidateQueries({ queryKey: ["adm-overview"] });
      queryClient.invalidateQueries({ queryKey: ["adm-prospect-timeline"] });
    },
    onError: (error: unknown) => {
      toast.error(extractApiErrorMessage(error, "Nao foi possivel montar a mensagem para o WhatsApp oficial."));
    },
  });

  if (!hasToken) {
    return <LoginPanel onLogged={(forceChange) => {
      setHasToken(true);
      setForcePasswordChange(forceChange);
    }} />;
  }

  if (forcePasswordChange) {
    return <ChangePasswordPanel onDone={() => setForcePasswordChange(false)} />;
  }

  const prospects = prospectsQuery.data?.data ?? [];
  const overview = overviewQuery.data;
  const openAdmWhatsappForProspect = (prospect: Prospect) => {
    setSelectedId(prospect.id);
    setAdmWhatsappProspectId(prospect.id);
    setActiveSection("adm_whatsapp");
  };
  const openOfficialWhatsAppTemplateDrawer = (prospect: Prospect) => {
    setSelectedId(prospect.id);
    setOfficialWhatsAppProspect(prospect);
    setOfficialTemplateKey("");
    setOfficialMessageKey("");
    setOfficialMessagePreview(null);
  };
  const openProspectEditor = (prospect: Prospect) => {
    setSelectedId(prospect.id);
    setEditingProspect(prospect);
    setEditDrawerOpen(true);
  };

  async function generateOfficialWhatsAppPreview() {
    if (!officialWhatsAppProspect || !selectedOfficialTemplate || !selectedOfficialTemplateMessage) return null;
    try {
      return await officialMessagePreviewMutation.mutateAsync({
        prospectId: officialWhatsAppProspect.id,
        templateKey: selectedOfficialTemplate.key,
        messageKey: selectedOfficialTemplateMessage.key,
      });
    } catch {
      return null;
    }
  }

  async function openOfficialWhatsAppWithTemplate() {
    if (!officialWhatsAppProspect) return;
    const number = resolveOfficialWhatsAppNumber(officialWhatsAppProspect);
    if (!number) {
      toast.error("Essa clinica nao tem numero de WhatsApp cadastrado.");
      return;
    }
    const preview = officialMessagePreview ?? (await generateOfficialWhatsAppPreview());
    if (!preview) return;
    if (!preview.can_copy) {
      toast.error(preview.warnings[0] || "Essa mensagem ainda nao pode ser enviada.");
      return;
    }
    const message = encodeURIComponent(preview.message_text);
    window.open(`https://wa.me/${number}?text=${message}`, "_blank", "noopener,noreferrer");
  }

  return (
    <main className="min-h-screen bg-stone-100 text-stone-950">
      <header className="sticky top-0 z-20 border-b border-stone-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4 px-5 py-3">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg bg-stone-950 text-sm font-black text-white">CF</div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Admin comercial</p>
              <h1 className="text-lg font-bold">
                {activeSection === "crm"
                  ? "Prospeccao e demos personalizadas"
                  : activeSection === "adm_whatsapp"
                    ? "WhatsApp do /adm"
                    : "Configuracao do WhatsApp oficial"}
              </h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              onClick={() => {
                clearAdminAccessToken();
                setHasToken(false);
              }}
            >
              Sair
            </Button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-[1600px] space-y-4 px-5 py-5">
        <Card className="border-stone-200 bg-white">
          <CardContent className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Menu do /adm</p>
              <h2 className="mt-1 text-xl font-black text-stone-950">Escolha a area que quer operar agora</h2>
              <p className="mt-1 text-sm text-stone-600">
                Alterne entre o CRM comercial, as conversas das demos e a configuracao do WhatsApp oficial da plataforma.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant={activeSection === "crm" ? "default" : "outline"}
                className={cn(activeSection === "crm" && "bg-emerald-600 text-white hover:bg-emerald-500")}
                onClick={() => setActiveSection("crm")}
              >
                <Building2 size={16} />
                CRM comercial
              </Button>
              <Button
                variant={activeSection === "adm_whatsapp" ? "default" : "outline"}
                className={cn(activeSection === "adm_whatsapp" && "bg-emerald-600 text-white hover:bg-emerald-500")}
                onClick={() => {
                  setAdmWhatsappProspectId(null);
                  setActiveSection("adm_whatsapp");
                }}
              >
                <MessageSquareText size={16} />
                WhatsApp do /adm
              </Button>
              <Button
                variant={activeSection === "whatsapp_settings" ? "default" : "outline"}
                className={cn(activeSection === "whatsapp_settings" && "bg-emerald-600 text-white hover:bg-emerald-500")}
                onClick={() => setActiveSection("whatsapp_settings")}
              >
                <SlidersHorizontal size={16} />
                WhatsApp do sistema
              </Button>
              <Link
                href="/adm/mensagens-para-clinicas"
                className="inline-flex h-10 items-center justify-center gap-1.5 rounded-lg border border-stone-200 bg-white px-4 text-sm font-semibold text-stone-900 transition hover:bg-stone-100 active:translate-y-[1px]"
              >
                <Clipboard size={16} />
                Mensagens prontas
              </Link>
              <Link
                href="/adm/importar-clinicas"
                className="inline-flex h-10 items-center justify-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-4 text-sm font-semibold text-emerald-900 transition hover:bg-emerald-100 active:translate-y-[1px]"
              >
                <MapPin size={16} />
                Importar Places
              </Link>
              <Link
                href="/adm/implementacoes"
                className="inline-flex h-10 items-center justify-center gap-1.5 rounded-lg border border-stone-200 bg-white px-4 text-sm font-semibold text-stone-900 transition hover:bg-stone-100 active:translate-y-[1px]"
              >
                <SlidersHorizontal size={16} />
                Implementacoes
              </Link>
            </div>
          </CardContent>
        </Card>

        {activeSection === "adm_whatsapp" ? (
          <AdmWhatsAppInbox selectedProspectId={admWhatsappProspectId} onClearProspectFilter={() => setAdmWhatsappProspectId(null)} />
        ) : null}

        {activeSection === "whatsapp_settings" ? <PlatformWhatsAppSettings /> : null}

        {activeSection === "crm" ? (
          <>
        <CreateProspectForm
          platformAccounts={platformAccounts}
          platformAccountUsage={platformAccountUsage}
          onCreated={(prospect) => {
            setSelectedId(prospect.id);
            queryClient.invalidateQueries({ queryKey: ["adm-prospects"] });
            queryClient.invalidateQueries({ queryKey: ["adm-overview"] });
          }}
        />

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
          <MetricCard icon={<Building2 size={18} />} label="Prospects" value={overview?.total_prospects ?? 0} />
          <MetricCard icon={<ShieldCheck size={18} />} label="Demos criadas" value={overview?.demos_created ?? 0} />
          <MetricCard icon={<Eye size={18} />} label="Demos acessadas" value={overview?.demos_accessed ?? 0} />
          <MetricCard icon={<Flame size={18} />} label="Quentes" value={overview?.hot_leads ?? 0} />
          <MetricCard icon={<CalendarClock size={18} />} label="Reunioes" value={overview?.meetings_scheduled ?? 0} />
          <MetricCard icon={<CheckCircle2 size={18} />} label="Ganhos" value={overview?.won ?? 0} />
        </div>

        <div className="grid gap-4 xl:grid-cols-[1fr_520px]">
          <section className="space-y-4">
            <div className="flex flex-col gap-3 rounded-lg border border-stone-200 bg-white p-3 lg:flex-row lg:items-center">
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" />
                <Input className="pl-9" placeholder="Buscar clinica, cidade ou telefone" value={search} onChange={(event) => setSearch(event.target.value)} />
              </div>
              <select
                className="h-10 rounded-lg border border-stone-200 bg-white px-3 text-sm"
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
              >
                <option value="">Todos os status</option>
                {STATUS_OPTIONS.map((status) => (
                  <option key={status} value={status}>
                    {humanize(status)}
                  </option>
                ))}
              </select>
              <Button variant="outline" onClick={() => prospectsQuery.refetch()}>
                <RefreshCw size={16} />
                Atualizar
              </Button>
            </div>

            <div className="overflow-hidden rounded-lg border border-stone-200 bg-white">
              <div className={cn("grid gap-3 border-b border-stone-200 bg-stone-50 px-4 py-3 text-xs font-bold uppercase tracking-wide text-stone-500", CRM_PROSPECT_GRID_CLASS)}>
                <span>Clinica</span>
                <span>Status</span>
                <span>Temperatura</span>
                <span>Score</span>
                <span>Demo</span>
                <span>Acoes</span>
              </div>
              <div className="max-h-[620px] overflow-auto">
                {prospectsQuery.isLoading ? (
                  <div className="p-6 text-sm text-stone-500">Carregando prospects...</div>
                ) : prospects.length ? (
                  prospects.map((prospect) => {
                    const officialWhatsAppLink = resolveOfficialWhatsAppLink(prospect);
                    return (
                    <div
                      key={prospect.id}
                      role="button"
                      tabIndex={0}
                      className={cn(
                        "grid w-full gap-3 border-b border-stone-100 px-4 py-3 text-left text-sm transition hover:bg-stone-50",
                        CRM_PROSPECT_GRID_CLASS,
                        selectedProspect?.id === prospect.id && "bg-emerald-50/70",
                      )}
                      onClick={() => setSelectedId(prospect.id)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") setSelectedId(prospect.id);
                      }}
                    >
                      <span className="min-w-0">
                        <strong className="block truncate text-stone-950">{prospect.clinic_name}</strong>
                        <span className="block truncate text-xs text-stone-500">
                          {[prospect.city, prospect.whatsapp_phone || prospect.phone].filter(Boolean).join(" - ") || "Sem contato"}
                        </span>
                        <span className="block truncate text-xs text-stone-400">Criada em {formatDateTimeBR(prospect.created_at)}</span>
                      </span>
                      <span>
                        <Badge className={statusClass(prospect.status)}>{humanize(prospect.status)}</Badge>
                      </span>
                      <span>
                        <Badge className={temperatureClass(prospect.temperature)}>{humanize(prospect.temperature)}</Badge>
                      </span>
                      <span className="font-bold">{prospect.score}</span>
                      <span className="text-xs text-stone-600">{prospect.demo_tenant_id ? humanize(prospect.demo_status) : "Nao criada"}</span>
                      <span className="flex min-w-[228px] gap-1">
                        <Button
                          type="button"
                          className="h-8 w-8 px-0"
                          variant="outline"
                          title="Editar clinica"
                          aria-label={`Editar ${prospect.clinic_name}`}
                          onClick={(event) => {
                            event.stopPropagation();
                            openProspectEditor(prospect);
                          }}
                        >
                          <Pencil size={14} />
                        </Button>
                        <Button
                          type="button"
                          className="h-8 w-8 px-0"
                          variant="outline"
                          title="Gerar demo"
                          aria-label={`Gerar demo para ${prospect.clinic_name}`}
                          onClick={(event) => {
                            event.stopPropagation();
                            generateDemoMutation.mutate(prospect.id);
                          }}
                        >
                          <ShieldCheck size={14} />
                        </Button>
                        <Button
                          type="button"
                          className="h-8 w-8 px-0"
                          variant="outline"
                          title="Abrir WhatsApp /adm"
                          aria-label={`Abrir WhatsApp /adm de ${prospect.clinic_name}`}
                          onClick={(event) => {
                            event.stopPropagation();
                            openAdmWhatsappForProspect(prospect);
                          }}
                        >
                          <MessageSquareText size={14} />
                        </Button>
                        <Button
                          type="button"
                          className="h-8 w-8 px-0"
                          variant="outline"
                          title={officialWhatsAppLink ? "Escolher template para WhatsApp oficial" : "WhatsApp oficial indisponivel"}
                          aria-label={`Escolher template para WhatsApp oficial de ${prospect.clinic_name}`}
                          disabled={!officialWhatsAppLink}
                          onClick={(event) => {
                            event.stopPropagation();
                            if (!officialWhatsAppLink) {
                              toast.error("Essa clinica nao tem numero de WhatsApp cadastrado.");
                              return;
                            }
                            openOfficialWhatsAppTemplateDrawer(prospect);
                          }}
                        >
                          <PhoneCall size={14} />
                        </Button>
                        <Button
                          type="button"
                          className="h-8 w-8 px-0"
                          variant="outline"
                          title="Copiar acesso"
                          aria-label={`Copiar acesso de ${prospect.clinic_name}`}
                          onClick={(event) => {
                            event.stopPropagation();
                            accessMutation.mutate(prospect.id);
                          }}
                        >
                          <Send size={14} />
                        </Button>
                        <Button
                          type="button"
                          className="h-8 w-8 px-0"
                          variant="outline"
                          title="Iniciar automacao"
                          aria-label={`Iniciar automacao para ${prospect.clinic_name}`}
                          onClick={(event) => {
                            event.stopPropagation();
                            automationMutation.mutate(prospect.id);
                          }}
                        >
                          <ArrowRight size={14} />
                        </Button>
                      </span>
                    </div>
                    );
                  })
                ) : (
                  <div className="p-8">
                    <EmptyState title="Nenhuma clinica cadastrada" description="Cadastre o primeiro prospect para gerar uma demo personalizada." />
                  </div>
                )}
              </div>
            </div>
          </section>

          <aside className="space-y-4">
            {selectedProspect ? (
              <ProspectDetail
                prospect={selectedProspect}
                timeline={timelineQuery.data ?? []}
                activity={activityQuery.data ?? []}
                lastDemoLink={lastDemoLink}
                lastBookingLink={lastBookingLink}
                bookingLink={selectedProspectBookingLink}
                onGenerateDemo={() => generateDemoMutation.mutate(selectedProspect.id)}
                onIssueAccess={() => accessMutation.mutate(selectedProspect.id)}
                onRecordContact={() => contactMutation.mutate(selectedProspect.id)}
                onStartAutomation={() => automationMutation.mutate(selectedProspect.id)}
                onSendReceptionOutreach={() =>
                  outreachMutation.mutate({ prospectId: selectedProspect.id, step: "reception_intro" })
                }
                onSendDecisionMakerPitch={() =>
                  outreachMutation.mutate({
                    prospectId: selectedProspect.id,
                    step: "decision_maker_pitch",
                    recipientName: selectedProspect.owner_name || selectedProspect.manager_name,
                  })
                }
                onSendVideoFollowup={() =>
                  outreachMutation.mutate({
                    prospectId: selectedProspect.id,
                    step: "video_followup",
                    recipientName: selectedProspect.owner_name || selectedProspect.manager_name,
                  })
                }
                onRunOutreachLab={(scenario) =>
                  outreachLabMutation.mutate({
                    prospectId: selectedProspect.id,
                    scenario,
                  })
                }
                onStatusChange={(status) => statusMutation.mutate({ prospectId: selectedProspect.id, status })}
                automationPending={automationMutation.isPending}
                outreachLabPending={outreachLabMutation.isPending}
              />
            ) : (
              <Card className="border-stone-200">
                <CardContent className="p-8">
                  <EmptyState title="Selecione uma clinica" description="Os detalhes comerciais aparecem aqui." />
                </CardContent>
              </Card>
            )}
          </aside>
        </div>
          </>
        ) : null}
      </div>
      <EditProspectDrawer
        prospect={editingProspect}
        open={editDrawerOpen}
        platformAccounts={platformAccounts}
        platformAccountUsage={platformAccountUsage}
        onOpenChange={(open) => {
          setEditDrawerOpen(open);
          if (!open) setEditingProspect(null);
        }}
        onSaved={(prospect) => {
          setSelectedId(prospect.id);
          setEditingProspect(prospect);
          queryClient.invalidateQueries({ queryKey: ["adm-prospects"] });
          queryClient.invalidateQueries({ queryKey: ["adm-overview"] });
          queryClient.invalidateQueries({ queryKey: ["adm-prospect-timeline", prospect.id] });
        }}
      />
      <OfficialWhatsAppTemplateDrawer
        open={Boolean(officialWhatsAppProspect)}
        prospect={officialWhatsAppProspect}
        templates={officialTemplates}
        selectedTemplate={selectedOfficialTemplate}
        selectedTemplateMessage={selectedOfficialTemplateMessage}
        preview={officialMessagePreview}
        templatesLoading={officialTemplatesQuery.isLoading}
        previewLoading={officialMessagePreviewMutation.isPending}
        onOpenChange={(open) => {
          if (open) return;
          setOfficialWhatsAppProspect(null);
          setOfficialMessagePreview(null);
        }}
        onTemplateChange={(templateKey) => {
          const nextTemplate = officialTemplates.find((template) => template.key === templateKey) ?? null;
          const nextMessage =
            nextTemplate?.messages.find((message) => message.is_default) ?? nextTemplate?.messages[0] ?? null;
          setOfficialTemplateKey(templateKey);
          setOfficialMessageKey(nextMessage?.key ?? "");
          setOfficialMessagePreview(null);
        }}
        onMessageChange={(messageKey) => {
          setOfficialMessageKey(messageKey);
          setOfficialMessagePreview(null);
        }}
        onGeneratePreview={() => {
          void generateOfficialWhatsAppPreview();
        }}
        onOpenWhatsApp={() => {
          void openOfficialWhatsAppWithTemplate();
        }}
      />
    </main>
  );
}

function MetricCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <Card className="border-stone-200">
      <CardContent className="flex items-center justify-between gap-3 p-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">{label}</p>
          <p className="mt-1 text-2xl font-black text-stone-950">{numberFormatter.format(value)}</p>
        </div>
        <div className="grid h-10 w-10 place-items-center rounded-lg bg-stone-100 text-stone-600">{icon}</div>
      </CardContent>
    </Card>
  );
}

function OfficialWhatsAppTemplateDrawer({
  open,
  prospect,
  templates,
  selectedTemplate,
  selectedTemplateMessage,
  preview,
  templatesLoading,
  previewLoading,
  onOpenChange,
  onTemplateChange,
  onMessageChange,
  onGeneratePreview,
  onOpenWhatsApp,
}: {
  open: boolean;
  prospect: Prospect | null;
  templates: SalesTemplate[];
  selectedTemplate: SalesTemplate | null;
  selectedTemplateMessage: SalesTemplateMessage | null;
  preview: MessagePreview | null;
  templatesLoading: boolean;
  previewLoading: boolean;
  onOpenChange: (open: boolean) => void;
  onTemplateChange: (templateKey: string) => void;
  onMessageChange: (messageKey: string) => void;
  onGeneratePreview: () => void;
  onOpenWhatsApp: () => void;
}) {
  const officialPhone = prospect ? prospect.whatsapp_phone || prospect.phone || "Telefone nao informado" : "Telefone nao informado";

  return (
    <RightDrawer
      open={open}
      onOpenChange={onOpenChange}
      title={prospect ? `WhatsApp oficial - ${prospect.clinic_name}` : "WhatsApp oficial"}
      description="Escolha um template da biblioteca e abra o WhatsApp com a mensagem pronta para envio."
      widthClassName="w-full sm:max-w-2xl"
    >
      {prospect ? (
        <div className="space-y-5">
          <section className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-stone-500">Contato oficial</p>
            <div className="mt-3 flex items-center gap-2 text-sm font-semibold text-stone-900">
              <PhoneCall size={16} />
              {officialPhone}
            </div>
            <p className="mt-1 text-xs leading-5 text-stone-500">
              O link vai abrir no WhatsApp oficial da clínica com a mensagem selecionada já preenchida.
            </p>
          </section>

          <section className="space-y-3">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-stone-500">Biblioteca</p>
              <h3 className="text-xl font-black text-stone-950">Templates</h3>
            </div>

            {templatesLoading ? (
              <div className="rounded-2xl border border-stone-200 bg-white p-5 text-sm text-stone-500">Carregando templates...</div>
            ) : templates.length ? (
              <div className="space-y-3">
                {templates.map((template) => {
                  const selected = template.key === selectedTemplate?.key;
                  return (
                    <button
                      key={template.key}
                      type="button"
                      className={cn(
                        "w-full rounded-[24px] border px-4 py-4 text-left transition",
                        selected
                          ? "border-emerald-300 bg-emerald-50 shadow-[0_10px_26px_rgba(16,185,129,0.12)]"
                          : "border-stone-200 bg-white hover:border-stone-300 hover:bg-stone-50",
                      )}
                      onClick={() => onTemplateChange(template.key)}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <p className="text-lg font-black text-stone-950">{template.label}</p>
                          <p className="mt-2 text-sm leading-6 text-stone-600">{template.description}</p>
                        </div>
                        <span className="shrink-0 rounded-full border border-stone-200 bg-white px-3 py-2 text-xs font-semibold text-stone-600">
                          {template.messages.length} msg
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="rounded-2xl border border-stone-200 bg-white p-5 text-sm text-stone-500">
                Nenhum template cadastrado na biblioteca.
              </div>
            )}
          </section>

          {selectedTemplate ? (
            <>
              {selectedTemplate.messages.length > 1 ? (
                <section className="space-y-3">
                  <p className="text-xs font-bold uppercase tracking-[0.18em] text-stone-500">Mensagem do template</p>
                  <div className="flex flex-wrap gap-2">
                    {selectedTemplate.messages.map((message) => {
                      const selected = message.key === selectedTemplateMessage?.key;
                      return (
                        <button
                          key={message.key}
                          type="button"
                          className={cn(
                            "rounded-full border px-3 py-2 text-sm font-semibold transition",
                            selected
                              ? "border-emerald-300 bg-emerald-100 text-emerald-800"
                              : "border-stone-200 bg-white text-stone-600 hover:border-stone-300 hover:bg-stone-50",
                          )}
                          onClick={() => onMessageChange(message.key)}
                        >
                          {message.label}
                        </button>
                      );
                    })}
                  </div>
                </section>
              ) : null}

              {preview?.warnings?.length ? (
                <div className="space-y-2">
                  {preview.warnings.map((warning) => (
                    <div key={warning} className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                      {warning}
                    </div>
                  ))}
                </div>
              ) : null}

              <section className="space-y-3">
                <p className="text-xs font-bold uppercase tracking-[0.18em] text-stone-500">Preview</p>
                <textarea
                  className="min-h-[260px] w-full resize-none rounded-[24px] border border-stone-200 bg-stone-50 p-4 text-sm leading-6 text-stone-800 outline-none"
                  value={
                    preview?.message_text ||
                    selectedTemplateMessage?.body ||
                    "Selecione um template para preparar a mensagem."
                  }
                  readOnly
                />
                {preview?.demo_login_url ? (
                  <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs text-emerald-900">
                    <p className="font-bold">Link da demo emitido para esta mensagem</p>
                    <p className="mt-1 break-all">{preview.demo_login_url}</p>
                  </div>
                ) : null}
              </section>

              <div className="flex flex-col gap-2 sm:flex-row">
                <Button
                  type="button"
                  variant="outline"
                  className="flex-1"
                  onClick={onGeneratePreview}
                  disabled={templatesLoading || previewLoading || !selectedTemplateMessage}
                >
                  <Send size={16} />
                  {previewLoading ? "Gerando..." : "Gerar preview"}
                </Button>
                <Button
                  type="button"
                  className="flex-1 bg-emerald-600 text-white hover:bg-emerald-500"
                  onClick={onOpenWhatsApp}
                  disabled={templatesLoading || previewLoading || !selectedTemplateMessage}
                >
                  <PhoneCall size={16} />
                  {previewLoading ? "Preparando..." : "Abrir WhatsApp oficial"}
                </Button>
              </div>
            </>
          ) : null}
        </div>
      ) : null}
    </RightDrawer>
  );
}

function ProspectDetail({
  prospect,
  timeline,
  activity,
  lastDemoLink,
  lastBookingLink,
  bookingLink,
  onGenerateDemo,
  onIssueAccess,
  onRecordContact,
  onStartAutomation,
  onSendReceptionOutreach,
  onSendDecisionMakerPitch,
  onSendVideoFollowup,
  onRunOutreachLab,
  onStatusChange,
  automationPending,
  outreachLabPending,
}: {
  prospect: Prospect;
  timeline: TimelineEvent[];
  activity: ActivityEvent[];
  lastDemoLink: string;
  lastBookingLink: string;
  bookingLink: string;
  onGenerateDemo: () => void;
  onIssueAccess: () => void;
  onRecordContact: () => void;
  onStartAutomation: () => void;
  onSendReceptionOutreach: () => void;
  onSendDecisionMakerPitch: () => void;
  onSendVideoFollowup: () => void;
  onRunOutreachLab: (scenario: string) => void;
  onStatusChange: (status: string) => void;
  automationPending: boolean;
  outreachLabPending: boolean;
}) {
  const checklistValues = Object.values(prospect.demo_checklist || {});
  const checklistDone = checklistValues.filter(Boolean).length;
  const checklistTotal = checklistValues.length || 12;
  const proposal = buildProposalText(prospect);
  const outreach = getOutreachSnapshot(prospect);
  const outreachLab = getOutreachLabSnapshot(prospect);
  const lastLabRun = outreachLab.last_run && typeof outreachLab.last_run === "object" ? outreachLab.last_run : null;
  const automationLabel = outreachAutomationLabel(outreach);
  const [labScenario, setLabScenario] = useState<string>("manager_interested");
  const resolvedBookingLink = lastBookingLink || bookingLink;

  useEffect(() => {
    const fallbackScenario = typeof lastLabRun?.scenario === "string" ? lastLabRun.scenario : "manager_interested";
    setLabScenario(fallbackScenario);
  }, [prospect.id, lastLabRun?.scenario]);

  return (
    <>
      <Card className="border-stone-200">
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <CardTitle className="truncate text-xl">{prospect.clinic_name}</CardTitle>
              <p className="mt-1 text-sm text-stone-600">{[prospect.city, prospect.state].filter(Boolean).join(" - ") || "Cidade nao informada"}</p>
            </div>
            <Badge className={temperatureClass(prospect.temperature)}>{humanize(prospect.temperature)}</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-3 gap-3 text-sm">
            <Info label="Score" value={String(prospect.score)} icon={<BarChart3 size={16} />} />
            <Info label="Status" value={humanize(prospect.status)} icon={<Activity size={16} />} />
            <Info label="Demo" value={prospect.demo_tenant_id ? humanize(prospect.demo_status) : "Nao criada"} icon={<ShieldCheck size={16} />} />
          </div>

          <div className="grid gap-2 text-sm">
            <p className="flex items-center gap-2 text-stone-700">
              <PhoneCall size={16} />
              {prospect.whatsapp_phone || prospect.phone || "Telefone nao informado"}
            </p>
            <p className="flex items-center gap-2 text-stone-700">
              <UserRound size={16} />
              {prospect.owner_name || prospect.manager_name || "Decisor ainda nao identificado"}
            </p>
            <p className="flex items-center gap-2 text-stone-700">
              <CalendarClock size={16} />
              Criada em {formatDateTimeBR(prospect.created_at)}
            </p>
            <p className="flex items-center gap-2 text-stone-700">
              <MessageSquareText size={16} />
              {prospect.main_pain || "Dor principal ainda nao preenchida"}
            </p>
          </div>

          <div className="grid gap-2 sm:grid-cols-2">
            <Button onClick={onGenerateDemo}>
              <ShieldCheck size={16} />
              Gerar demo
            </Button>
            <Button variant="outline" onClick={onIssueAccess} disabled={!prospect.demo_tenant_id}>
              <Send size={16} />
              Copiar acesso
            </Button>
            <Button
              variant="outline"
              onClick={() => navigator.clipboard?.writeText(resolvedBookingLink)}
              disabled={!resolvedBookingLink}
            >
              <Clipboard size={16} />
              Copiar agendamento
            </Button>
            <Button variant="outline" onClick={onRecordContact}>
              <PhoneCall size={16} />
              Registrar contato
            </Button>
            <select
              className="h-10 rounded-lg border border-stone-200 bg-white px-3 text-sm"
              value={prospect.status}
              onChange={(event) => onStatusChange(event.target.value)}
            >
              {STATUS_OPTIONS.map((status) => (
                <option key={status} value={status}>
                  {humanize(status)}
                </option>
              ))}
            </select>
          </div>

          <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-950">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="font-semibold">Automacao comercial transparente</p>
                <p className="mt-1 max-w-xl leading-6">
                  Um clique inicia o contato da {BRAND_SALES_TEAM} no WhatsApp. Quando a clinica responder, o sistema registra a resposta, envia o pitch curto com demo e depois o video automaticamente.
                </p>
              </div>
              <Badge className="bg-white text-emerald-800">{automationLabel}</Badge>
            </div>

            <div className="mt-3 grid gap-2 text-xs text-emerald-900/80 sm:grid-cols-2">
              <span>Etapa atual: {outreach.last_step ? humanize(outreach.last_step) : "Ainda nao iniciada"}</span>
              <span>Ultima resposta: {outreach.last_reply_at ? formatDateTimeBR(outreach.last_reply_at) : "Aguardando contato"}</span>
            </div>

            {outreach.last_reply_preview ? (
              <p className="mt-2 rounded-lg border border-emerald-200 bg-white/80 px-3 py-2 text-xs leading-5 text-emerald-900/85">
                Ultima resposta registrada: {outreach.last_reply_preview}
              </p>
            ) : null}

            <Button className="mt-4 w-full bg-emerald-600 text-white hover:bg-emerald-500" onClick={onStartAutomation} disabled={automationPending || outreach.automation_active}>
              <MessageSquareText size={16} />
              {outreach.automation_active ? "Automacao ativa no WhatsApp" : automationPending ? "Iniciando automacao..." : "Iniciar automacao comercial"}
            </Button>
          </div>

          <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
            <p className="font-semibold">Outreach transparente</p>
            <p className="mt-1 leading-6">
              Este fluxo comercial se apresenta como {BRAND_SALES_TEAM}, pede o decisor de forma honesta, envia demo rastreavel e depois o video. Nao usa personificacao de paciente ou urgencia falsa.
            </p>
          </div>

          <div className="grid gap-2 sm:grid-cols-3">
            <Button variant="outline" onClick={onSendReceptionOutreach}>
              <MessageSquareText size={16} />
              Chamar recepção
            </Button>
            <Button variant="outline" onClick={onSendDecisionMakerPitch}>
              <ArrowRight size={16} />
              Enviar pitch + demo
            </Button>
            <Button variant="outline" onClick={onSendVideoFollowup}>
              <Send size={16} />
              Enviar vídeo
            </Button>
          </div>

          <div className="rounded-xl border border-cyan-200 bg-cyan-50 p-4 text-sm text-cyan-950">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="font-semibold">IA Lab comercial</p>
                <p className="mt-1 max-w-xl leading-6">
                  Simule a conversa entre a clinica prospectada e o nosso sistema sem WhatsApp real. A ultima rodada fica salva no historico comercial da clinica.
                </p>
              </div>
              <Badge className={lastLabRun?.converted ? "bg-emerald-100 text-emerald-700" : "bg-white text-cyan-800"}>
                {lastLabRun?.converted ? "Fluxo converteu no lab" : "Sem simulacao convertida"}
              </Badge>
            </div>

            <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_auto]">
              <select
                className="h-10 rounded-lg border border-cyan-200 bg-white px-3 text-sm"
                value={labScenario}
                onChange={(event) => setLabScenario(event.target.value)}
                disabled={outreachLabPending}
              >
                {OUTREACH_LAB_SCENARIOS.map((scenario) => (
                  <option key={scenario.value} value={scenario.value}>
                    {scenario.label}
                  </option>
                ))}
              </select>
              <Button
                className="bg-cyan-700 text-white hover:bg-cyan-600"
                onClick={() => onRunOutreachLab(labScenario)}
                disabled={outreachLabPending}
              >
                <MessageSquareText size={16} />
                {outreachLabPending ? "Rodando simulacao..." : "Rodar IA Lab"}
              </Button>
            </div>

            <div className="mt-3 grid gap-2 text-xs text-cyan-950/85 sm:grid-cols-2">
              <span>Ultimo cenario: {lastLabRun?.scenario_label || "Nenhum"}</span>
              <span>Ultimo resultado: {lastLabRun?.outcome ? humanize(lastLabRun.outcome) : "Sem rodada ainda"}</span>
              <span>Rodadas neste cenario: {Number(outreachLab.scenario_stats?.[labScenario]?.runs || 0)}</span>
              <span>Conversoes neste cenario: {Number(outreachLab.scenario_stats?.[labScenario]?.conversions || 0)}</span>
            </div>

            {lastLabRun?.recommendation ? (
              <p className="mt-3 rounded-lg border border-cyan-200 bg-white/80 px-3 py-2 text-xs leading-5 text-cyan-950/85">
                Recomendacao do lab: {lastLabRun.recommendation}
              </p>
            ) : null}

            {lastLabRun?.transcript?.length ? (
              <div className="mt-3 space-y-2 rounded-xl border border-cyan-100 bg-white/85 p-3">
                <p className="text-xs font-bold uppercase tracking-wide text-cyan-800">Transcricao simulada</p>
                <div className="max-h-[320px] space-y-2 overflow-y-auto pr-1">
                  {lastLabRun.transcript.map((turn) => {
                    const isOdontoFlux = turn.role === "odontoflux";
                    const isClinic = turn.role === "clinic_virtual";
                    return (
                      <div
                        key={turn.id}
                        className={cn(
                          "flex",
                          isOdontoFlux ? "justify-end" : isClinic ? "justify-start" : "justify-center",
                        )}
                      >
                        <div
                          className={cn(
                            "max-w-[88%] rounded-2xl px-3 py-2 text-sm shadow-sm",
                            isOdontoFlux
                              ? "border border-emerald-100 bg-emerald-600 text-white"
                              : isClinic
                                ? "border border-blue-100 bg-blue-50 text-blue-950"
                                : "border border-stone-200 bg-stone-100 text-stone-700",
                          )}
                        >
                          <div className="mb-1 text-[11px] font-bold uppercase tracking-wide opacity-80">{turn.label}</div>
                          <p className="whitespace-pre-wrap leading-relaxed">{turn.text}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : null}
          </div>

          {lastDemoLink || resolvedBookingLink ? (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
              <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">Links da clinica</p>
              {lastDemoLink ? (
                <div className="mt-3 flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700/80">Link da demo</p>
                    <span className="block truncate">{lastDemoLink}</span>
                  </div>
                  <Button className="h-8 px-2" variant="outline" onClick={() => navigator.clipboard?.writeText(lastDemoLink)}>
                    <Clipboard size={14} />
                  </Button>
                </div>
              ) : null}
              {resolvedBookingLink ? (
                <div className="mt-3 flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700/80">Link do agendamento</p>
                    <span className="block truncate">{resolvedBookingLink}</span>
                  </div>
                  <Button className="h-8 px-2" variant="outline" onClick={() => navigator.clipboard?.writeText(resolvedBookingLink)}>
                    <Clipboard size={14} />
                  </Button>
                </div>
              ) : null}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle className="text-base">Checklist da demo</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="mb-3 flex items-center justify-between text-sm">
            <span className="font-medium">{checklistDone}/{checklistTotal} itens prontos</span>
            <span className="text-stone-500">{Math.round((checklistDone / checklistTotal) * 100)}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-stone-200">
            <div className="h-full bg-emerald-600" style={{ width: `${Math.round((checklistDone / checklistTotal) * 100)}%` }} />
          </div>
        </CardContent>
      </Card>

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle className="text-base">Servicos e unidades</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div>
            <p className="mb-2 font-semibold text-stone-700">Servicos</p>
            <div className="flex flex-wrap gap-2">
              {prospect.services.map((service) => (
                <Badge key={service.id} className="bg-stone-100 text-stone-700">{service.service_name}</Badge>
              ))}
            </div>
          </div>
          <div>
            <p className="mb-2 font-semibold text-stone-700">Unidades</p>
            <div className="space-y-2">
              {prospect.units.map((unit) => (
                <div key={unit.id} className="rounded-lg border border-stone-200 p-3">
                  <strong>{unit.unit_name}</strong>
                  <p className="text-xs text-stone-500">{unit.address || "Sem endereco"}</p>
                </div>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle className="text-base">Playbook comercial</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {PLAYBOOKS.map((playbook) => (
            <div key={playbook.title} className="rounded-lg border border-stone-200 p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <strong className="text-sm">{playbook.title}</strong>
                <Button className="h-8 px-2" variant="outline" onClick={() => navigator.clipboard?.writeText(playbook.text)}>
                  <Clipboard size={14} />
                </Button>
              </div>
              <p className="text-sm leading-6 text-stone-600">{playbook.text}</p>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle className="text-base">Proposta e ROI rapido</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="rounded-lg border border-stone-200 bg-stone-50 p-3 text-sm leading-6 text-stone-700">
            <pre className="whitespace-pre-wrap font-sans">{proposal}</pre>
          </div>
          <Button className="mt-3" variant="outline" onClick={() => navigator.clipboard?.writeText(proposal)}>
            <FileText size={16} />
            Copiar proposta
          </Button>
        </CardContent>
      </Card>

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle className="text-base">Atividade da demo</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {activity.length ? (
            activity.slice(0, 8).map((event) => (
              <div key={event.id} className="rounded-lg border border-stone-200 p-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <strong>{humanize(event.event_name)}</strong>
                  <span className="text-xs text-stone-500">{formatDateTimeBR(event.occurred_at)}</span>
                </div>
                <p className="mt-1 text-xs text-stone-500">{event.page_path || "Sem pagina"}</p>
              </div>
            ))
          ) : (
            <p className="text-sm text-stone-500">Nenhuma atividade registrada ainda.</p>
          )}
        </CardContent>
      </Card>

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle className="text-base">Timeline comercial</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {timeline.slice(0, 10).map((event) => (
            <div key={event.id} className="border-l-2 border-stone-200 pl-3 text-sm">
              <strong>{event.event_label}</strong>
              <p className="text-xs text-stone-500">{formatDateTimeBR(event.created_at)}</p>
            </div>
          ))}
        </CardContent>
      </Card>
    </>
  );
}

function Info({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-stone-200 p-3">
      <div className="mb-2 text-stone-500">{icon}</div>
      <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">{label}</p>
      <p className="mt-1 truncate font-bold text-stone-950">{value}</p>
    </div>
  );
}

function buildProposalText(prospect: Prospect) {
  const volume = Number(prospect.estimated_volume || 120);
  const lostRate = 0.18;
  const ticket = 350;
  const estimatedLoss = Math.round(volume * lostRate * ticket);
  return `Proposta inicial ${BRAND_NAME} para ${prospect.clinic_name}

Plano recomendado: Piloto Assistido
Duracao: 30 dias
Implantacao: a partir de R$ 2.500
Mensalidade: a partir de R$ 997

Escopo:
- Configuracao da clinica, servicos, unidades e equipe
- Demo personalizada com fluxo de WhatsApp, agenda e retorno
- Treinamento inicial da recepcao
- Acompanhamento comercial e operacional do piloto

Argumento de ROI:
Com ${volume} oportunidades por mes, uma perda estimada de 18% e ticket medio de R$ ${ticket}, a clinica pode estar deixando perto de R$ ${numberFormatter.format(estimatedLoss)} em oportunidades sem acompanhamento claro.

Proximo passo:
Validar a demo personalizada e marcar reuniao de implantacao.`;
}

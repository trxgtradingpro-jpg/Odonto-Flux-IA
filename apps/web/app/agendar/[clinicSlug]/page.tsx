"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, FormEvent, PointerEvent as ReactPointerEvent } from "react";
import {
  ArrowRight,
  CalendarCheck2,
  CalendarDays,
  ChevronRight,
  CheckCircle2,
  ClipboardList,
  Mail,
  MapPinHouse,
  MessageCircle,
  List,
  PencilLine,
  SendHorizontal,
  ShieldCheck,
  Sparkles,
  UserRound,
  X,
} from "lucide-react";
import Image from "next/image";
import { useParams, useSearchParams } from "next/navigation";
import { cn } from "@odontoflux/ui";

import { publicApiFetch } from "@/lib/public-api";

type PublicBookingProfile = {
  clinic: {
    slug: string;
    name: string;
    logo_data_url: string | null;
  };
  branding: {
    primary_color: string;
    secondary_color: string;
    accent_color: string;
    background_color: string;
    card_color: string;
    text_color: string;
    muted_text_color: string;
    border_color: string;
  };
  link_flow: {
    enabled: boolean;
    operational: boolean;
    cta_mode: "whatsapp_redirect" | "webchat";
    headline: string;
    trust_message: string;
    button_label: string;
    unavailable_message?: string | null;
  };
};

type PublicBookingSession = {
  session_id: string;
  expires_at: string;
  cta_mode: "whatsapp_redirect" | "webchat";
  whatsapp_url: string | null;
  public_access_token?: string | null;
  contact_phone?: string | null;
  contact_phone_required?: boolean;
  clinic: {
    slug: string;
    name: string;
  };
};

type PublicBookingSessionState = {
  session_id: string;
  status: string;
  cta_mode: "webchat";
  channel: "webchat";
  expires_at: string;
  closed_at: string | null;
  has_conversation: boolean;
  completed: boolean;
  contact_phone: string | null;
  contact_phone_required: boolean;
};

type PublicWebchatMessage = {
  id: string;
  role: "patient" | "assistant";
  text: string;
  created_at: string | null;
  status: string;
};

type PublicBookingSummaryField = {
  value: string | null;
  complete: boolean;
  source: string | null;
  unit_id?: string | null;
};

type PublicBookingSummary = {
  session_status: string;
  progress: {
    complete_count: number;
    total_count: number;
  };
  status: {
    label: string;
    tone: "success" | "progress" | "pending";
    appointment_created: boolean;
  };
  fields: {
    patient_name: PublicBookingSummaryField;
    email: PublicBookingSummaryField;
    birth_date: PublicBookingSummaryField;
    unit: PublicBookingSummaryField;
    procedure: PublicBookingSummaryField;
    preferred_date: PublicBookingSummaryField;
    confirmed_slot: PublicBookingSummaryField;
  };
  appointment: {
    id: string | null;
    starts_at: string | null;
    confirmation_status: string | null;
  };
  options: {
    units: Array<{ id: string; name: string }>;
    services?: Array<{ id: string; name: string }>;
    preferred_dates?: Array<{ id: string; date: string; label: string; description?: string | null }>;
    preferred_times?: Array<{ id: string; label: string; time?: string | null }>;
  };
};

type PublicBookingSummaryDraft = {
  full_name: string;
  email: string;
  birth_date: string;
  procedure_type: string;
  unit_id: string;
  preferred_date: string;
  preferred_time: string;
};

function formatPublicMessageTime(value: string | null): string {
  if (!value) return "agora";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "agora";
  return new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatPublicDate(value: string | null): string {
  if (!value) return "Pendente";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    const [year, month, day] = value.split("-");
    return year && month && day ? `${day}/${month}/${year}` : value;
  }
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

function formatPublicDateTime(value: string | null): string {
  if (!value) return "Pendente";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function getBrowserSessionId(): string {
  const storageKey = "clinicflux.link_flow.browser_session_id";
  const existing = window.localStorage.getItem(storageKey);
  if (existing) return existing;
  const value =
    typeof window.crypto?.randomUUID === "function"
      ? window.crypto.randomUUID()
      : `lf_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  window.localStorage.setItem(storageKey, value);
  return value;
}

function getUtmPayload(): Record<string, string> {
  const params = new URLSearchParams(window.location.search);
  const payload: Record<string, string> = {};
  params.forEach((value, key) => {
    if (key.startsWith("utm_") || ["gclid", "fbclid"].includes(key)) {
      payload[key] = value;
    }
  });
  return payload;
}

function webchatSessionStorageKey(clinicSlug: string): string {
  return `clinicflux.link_flow.webchat.${clinicSlug}`;
}

function shouldInvalidatePublicSession(message: string): boolean {
  return /expir/i.test(message) || /encerrad/i.test(message);
}

function publicSessionUnavailableMessage(message: string): string {
  if (/encerrad/i.test(message)) {
    return "Esta conversa foi encerrada. Recarregue a pagina para iniciar um novo atendimento.";
  }
  return "Sua sessao expirou. Recarregue a pagina para iniciar um novo atendimento.";
}

function readStoredWebchatSession(clinicSlug: string): PublicBookingSession | null {
  try {
    const raw = window.localStorage.getItem(webchatSessionStorageKey(clinicSlug));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PublicBookingSession;
    if (!parsed.session_id || !parsed.public_access_token || parsed.cta_mode !== "webchat") return null;
    if (new Date(parsed.expires_at).getTime() <= Date.now()) return null;
    return parsed;
  } catch {
    return null;
  }
}

function storeWebchatSession(clinicSlug: string, session: PublicBookingSession | null) {
  const key = webchatSessionStorageKey(clinicSlug);
  if (!session || session.cta_mode !== "webchat") {
    window.localStorage.removeItem(key);
    return;
  }
  window.localStorage.setItem(key, JSON.stringify(session));
}

function normalizePhoneDraft(value: string): string {
  return value.replace(/[^\d+()\-\s]/g, "").slice(0, 30);
}

function PublicWebchat({
  clinicSlug,
  clinicName,
  session,
  onExpired,
  embedded = false,
}: {
  clinicSlug: string;
  clinicName: string;
  session: PublicBookingSession;
  onExpired: (message?: string) => void;
  embedded?: boolean;
}) {
  const [messages, setMessages] = useState<PublicWebchatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(true);
  const [chatError, setChatError] = useState<string | null>(null);
  const openedRef = useRef(false);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const lastMessageId = messages.length ? messages[messages.length - 1]?.id : undefined;
  const token = session.public_access_token || "";

  const loadMessages = useCallback(async (afterMessageId?: string) => {
    try {
      const suffix = afterMessageId ? `?after_message_id=${encodeURIComponent(afterMessageId)}` : "";
      const response = await publicApiFetch<{ data: PublicWebchatMessage[] }>(
        `/public/booking/sessions/${session.session_id}/chat/messages${suffix}`,
        undefined,
        { publicAccessToken: token },
      );
      setMessages((current) => {
        const seen = new Set(current.map((message) => message.id));
        const next = afterMessageId
          ? [...current, ...response.data.filter((message) => !seen.has(message.id))]
          : response.data;
        return next;
      });
      setChatError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Nao foi possivel atualizar o chat.";
      setChatError(message);
      if (shouldInvalidatePublicSession(message)) {
        onExpired(message);
      }
    } finally {
      setLoadingMessages(false);
    }
  }, [onExpired, session.session_id, token]);

  useEffect(() => {
    if (!token || openedRef.current) return;
    openedRef.current = true;
    void publicApiFetch(
      `/public/booking/sessions/${session.session_id}/events`,
      {
        method: "POST",
        body: JSON.stringify({
          event_name: "webchat_opened",
          page_path: `/agendar/${clinicSlug}`,
          payload: { source: "public_booking_page" },
        }),
      },
      { publicAccessToken: token },
    ).catch(() => undefined);
    void loadMessages();
  }, [clinicSlug, loadMessages, session.session_id, token]);

  useEffect(() => {
    if (!token) return;
    const interval = window.setInterval(() => {
      void loadMessages(lastMessageId);
    }, sending ? 1500 : 4000);
    return () => window.clearInterval(interval);
  }, [lastMessageId, loadMessages, sending, token]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    viewport.scrollTo({ top: viewport.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  async function handleSendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || sending) return;
    setSending(true);
    setChatError(null);
    try {
      const clientMessageId =
        typeof window.crypto?.randomUUID === "function"
          ? window.crypto.randomUUID()
          : `msg_${Date.now()}_${Math.random().toString(36).slice(2)}`;
      const response = await publicApiFetch<{ message: PublicWebchatMessage }>(
        `/public/booking/sessions/${session.session_id}/chat/messages`,
        {
          method: "POST",
          body: JSON.stringify({ text, client_message_id: clientMessageId }),
        },
        { publicAccessToken: token },
      );
      setDraft("");
      setMessages((current) =>
        current.some((message) => message.id === response.message.id)
          ? current
          : [...current, response.message],
      );
      await loadMessages(response.message.id);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Nao foi possivel enviar sua mensagem.";
      setChatError(message);
      if (shouldInvalidatePublicSession(message)) {
        onExpired(message);
      }
    } finally {
      setSending(false);
    }
  }

  return (
    <div
      className={cn(
        "flex h-full min-h-0 flex-1 flex-col overflow-hidden",
        embedded
          ? "bg-white"
          : "rounded-[30px] border border-white/60 bg-white/82 shadow-[0_22px_70px_rgba(15,23,42,0.12)] backdrop-blur",
      )}
    >
      {!embedded ? <div className="flex items-center justify-between gap-3 border-b border-stone-200 bg-white/92 px-4 py-3 sm:px-5">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[var(--booking-primary)] text-white shadow-sm">
            <MessageCircle className="h-5 w-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-stone-900">Atendimento online</p>
            <p className="truncate text-xs text-[var(--booking-muted)]">{clinicName} · canal oficial da clinica</p>
          </div>
        </div>
        <div className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-700">
          Online
        </div>
      </div> : null}

      <div
        ref={viewportRef}
        className={cn(
          "min-h-0 flex-1 space-y-4 overflow-y-auto bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.96),_rgba(242,247,245,0.92)_42%,_rgba(237,241,239,0.95))]",
          embedded ? "px-4 py-4 sm:px-5" : "px-4 py-5 sm:px-5",
        )}
      >
        {loadingMessages ? (
          <div className="max-w-[88%] rounded-[24px] border border-stone-200 bg-white px-4 py-3 text-sm text-[var(--booking-muted)] shadow-sm">
            Carregando conversa...
          </div>
        ) : null}
        {!loadingMessages && messages.length === 0 ? (
          <div className="flex justify-start">
            <div className="max-w-[88%] rounded-[24px] border border-stone-200 bg-white px-4 py-3 text-sm leading-6 text-[var(--booking-text)] shadow-sm">
              <p className="font-medium text-stone-900">Oi, eu sou a assistente de agendamento.</p>
              <p className="mt-1 text-[var(--booking-muted)]">
                Me conte o que voce precisa e eu vou te ajudar por aqui. Exemplo: Quero agendar uma avaliacao esta semana.
              </p>
            </div>
          </div>
        ) : null}
        {messages.map((message) => {
          const isPatient = message.role === "patient";
          return (
            <div key={message.id} className={`flex ${isPatient ? "justify-end" : "justify-start"}`}>
              <div
                className={[
                  "max-w-[88%] rounded-[24px] px-4 py-3 text-sm leading-6 shadow-sm sm:max-w-[78%]",
                  isPatient
                    ? "rounded-br-[10px] bg-[var(--booking-primary)] text-white"
                    : "rounded-bl-[10px] border border-stone-200 bg-white text-[var(--booking-text)]",
                ].join(" ")}
              >
                <p className="whitespace-pre-wrap break-words">{message.text}</p>
                <div
                  className={`mt-2 text-[11px] ${isPatient ? "text-white/80" : "text-[var(--booking-muted)]"}`}
                >
                  {formatPublicMessageTime(message.created_at)}
                </div>
              </div>
            </div>
          );
        })}
        {sending ? (
          <div className="flex justify-start">
            <div className="rounded-[20px] border border-stone-200 bg-white px-4 py-2 text-xs text-[var(--booking-muted)] shadow-sm">
              Recebi sua mensagem. Estou preparando a resposta...
            </div>
          </div>
        ) : null}
      </div>

      <div className={cn("border-t border-stone-200 bg-white/94 px-4 py-3 sm:px-5", embedded && "shadow-[0_-8px_24px_rgba(15,23,42,0.06)]")}>
        {chatError ? (
          <p className="mb-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            {chatError}
          </p>
        ) : null}

        <form onSubmit={handleSendMessage} className="flex items-end gap-3">
          <div className="flex-1 rounded-[28px] border border-stone-200 bg-white px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.85)] transition focus-within:border-[var(--booking-primary)] focus-within:ring-2 focus-within:ring-[color:color-mix(in_srgb,var(--booking-primary)_16%,transparent)]">
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              maxLength={1200}
              placeholder="Digite sua mensagem..."
              className="h-7 w-full border-none bg-transparent text-sm text-[var(--booking-text)] outline-none placeholder:text-stone-400"
            />
          </div>
          <button
            type="submit"
            disabled={!draft.trim() || sending}
            className="inline-flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-[var(--booking-primary)] text-white shadow-sm transition hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-60"
            aria-label="Enviar mensagem"
          >
            <SendHorizontal className="h-5 w-5" aria-hidden="true" />
          </button>
        </form>
      </div>
    </div>
  );
}

function buildSummaryDraft(summary: PublicBookingSummary | null): PublicBookingSummaryDraft {
  return {
    full_name: summary?.fields.patient_name.value || "",
    email: summary?.fields.email.value || "",
    birth_date: summary?.fields.birth_date.value || "",
    procedure_type: summary?.fields.procedure.value || "",
    unit_id: summary?.fields.unit.unit_id || "",
    preferred_date: summary?.fields.preferred_date.value || "",
    preferred_time: summary?.fields.confirmed_slot.source === "manual" ? summary?.fields.confirmed_slot.value || "" : "",
  };
}

function BookingSummaryPanel({
  summary,
  loading,
  saving,
  onSave,
  className,
}: {
  summary: PublicBookingSummary | null;
  loading: boolean;
  saving: boolean;
  onSave: (draft: Partial<PublicBookingSummaryDraft>) => Promise<void>;
  className?: string;
}) {
  const [activeEditor, setActiveEditor] = useState<string | null>(null);
  const [draft, setDraft] = useState<PublicBookingSummaryDraft>(() => buildSummaryDraft(summary));

  useEffect(() => {
    setDraft(buildSummaryDraft(summary));
  }, [summary]);

  const serviceOptions = summary?.options.services || [];
  const preferredDateOptions = summary?.options.preferred_dates || [];
  const preferredTimeOptions = summary?.options.preferred_times || [];

  const cards = [
    {
      key: "patient_name",
      label: "Paciente",
      value: summary?.fields.patient_name.value || "Aguardando nome",
      complete: summary?.fields.patient_name.complete || false,
      icon: UserRound,
      action: "edit" as const,
    },
    {
      key: "email",
      label: "E-mail",
      value: summary?.fields.email.value || "Ainda nao informado",
      complete: summary?.fields.email.complete || false,
      icon: Mail,
      action: "edit" as const,
    },
    {
      key: "birth_date",
      label: "Nascimento",
      value: summary?.fields.birth_date.value ? formatPublicDate(summary.fields.birth_date.value) : "Ainda nao informado",
      complete: summary?.fields.birth_date.complete || false,
      icon: CalendarDays,
      action: null,
    },
    {
      key: "unit",
      label: "Unidade",
      value: summary?.fields.unit.value || "Escolha pendente",
      complete: summary?.fields.unit.complete || false,
      icon: MapPinHouse,
      action: "select" as const,
    },
    {
      key: "procedure",
      label: "Servico",
      value: summary?.fields.procedure.value || "Definir na conversa",
      complete: summary?.fields.procedure.complete || false,
      icon: ClipboardList,
      action: "select" as const,
    },
    {
      key: "preferred_date",
      label: "Data desejada",
      value: summary?.fields.preferred_date.value ? formatPublicDate(summary.fields.preferred_date.value) : "Opcional",
      complete: summary?.fields.preferred_date.complete || false,
      icon: CalendarDays,
      action: "select" as const,
    },
    {
      key: "confirmed_slot",
      label: "Horario",
      value: summary?.fields.confirmed_slot.value
        ? summary?.fields.confirmed_slot.source === "manual"
          ? summary.fields.confirmed_slot.value
          : formatPublicDateTime(summary.fields.confirmed_slot.value)
        : "Aguardando confirmacao",
      complete: summary?.fields.confirmed_slot.complete || false,
      icon: Sparkles,
      action: "select" as const,
    },
  ] as const;

  async function handleQuickSave(nextDraft: Partial<PublicBookingSummaryDraft>, nextEditor: string | null = null) {
    await onSave(nextDraft);
    setActiveEditor(nextEditor);
  }

  const inlineInputClassName =
    "h-9 w-full rounded-xl border border-stone-200 bg-white px-3 text-xs text-stone-900 outline-none transition focus:border-[var(--booking-primary)]";
  const inlineSelectClassName =
    "h-9 w-full rounded-xl border border-stone-200 bg-white px-3 text-xs text-stone-900 outline-none transition focus:border-[var(--booking-primary)]";

  return (
    <aside
      className={cn(
        "flex h-full min-h-0 flex-col overflow-hidden rounded-[28px] border border-white/70 bg-white/84 p-2.5 shadow-[0_18px_48px_rgba(15,23,42,0.08)] backdrop-blur sm:rounded-[30px] sm:p-3.5",
        className,
      )}
    >
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1 pb-[max(0.5rem,env(safe-area-inset-bottom))]">
        <div className="grid grid-cols-2 gap-2">
          {cards.map((card) => {
            const Icon = card.icon;
            const isEditing = activeEditor === card.key;
            return (
              <div
                key={card.key}
                className={[
                  "rounded-[16px] border px-2.5 py-2.5 transition sm:rounded-[18px]",
                  card.complete
                    ? "border-emerald-200 bg-emerald-50/90 shadow-[0_10px_24px_rgba(16,185,129,0.10)]"
                    : "border-stone-200 bg-white/92",
                ].join(" ")}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-start gap-2">
                    <span
                      className={[
                        "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg",
                        card.complete ? "bg-emerald-100 text-emerald-700" : "bg-stone-100 text-stone-500",
                      ].join(" ")}
                    >
                      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                    </span>
                    <div className="min-w-0">
                      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--booking-muted)]">
                        {card.label}
                      </p>
                      <p
                        className={`mt-1 break-words text-[11px] font-medium leading-4 sm:text-[12px] ${card.complete ? "text-emerald-900" : "text-stone-700"}`}
                      >
                        {card.value}
                      </p>
                    </div>
                  </div>
                  {card.action === "edit" ? (
                    <button
                      type="button"
                      aria-label={`Editar ${card.label}`}
                      data-testid={`summary-action-${card.key}`}
                      onClick={() => setActiveEditor((current) => (current === card.key ? null : card.key))}
                      className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-stone-200 bg-white text-stone-500 transition hover:border-stone-300 hover:text-stone-700"
                    >
                      <PencilLine className="h-3.5 w-3.5" aria-hidden="true" />
                    </button>
                  ) : null}
                  {card.action === "select" ? (
                    <button
                      type="button"
                      aria-label={`Escolher ${card.label}`}
                      data-testid={`summary-action-${card.key}`}
                      onClick={() => setActiveEditor((current) => (current === card.key ? null : card.key))}
                      className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-stone-200 bg-white text-stone-500 transition hover:border-stone-300 hover:text-stone-700"
                    >
                      <List className="h-3.5 w-3.5" aria-hidden="true" />
                    </button>
                  ) : null}
                </div>

                {isEditing && card.key === "patient_name" ? (
                  <form
                    className="mt-2 flex gap-2"
                    onSubmit={async (event) => {
                      event.preventDefault();
                      await handleQuickSave({ full_name: draft.full_name }, null);
                    }}
                  >
                    <input
                      value={draft.full_name}
                      onChange={(event) => setDraft((current) => ({ ...current, full_name: event.target.value }))}
                      placeholder="Nome completo"
                      className={inlineInputClassName}
                      data-testid="summary-input-patient_name"
                    />
                    <button
                      type="submit"
                      disabled={saving}
                      className="inline-flex h-9 shrink-0 items-center justify-center rounded-xl bg-[var(--booking-primary)] px-3 text-xs font-semibold text-white disabled:opacity-60"
                    >
                      Salvar
                    </button>
                  </form>
                ) : null}

                {isEditing && card.key === "email" ? (
                  <form
                    className="mt-2 flex gap-2"
                    onSubmit={async (event) => {
                      event.preventDefault();
                      await handleQuickSave({ email: draft.email }, null);
                    }}
                  >
                    <input
                      value={draft.email}
                      onChange={(event) => setDraft((current) => ({ ...current, email: event.target.value }))}
                      placeholder="E-mail"
                      className={inlineInputClassName}
                      data-testid="summary-input-email"
                    />
                    <button
                      type="submit"
                      disabled={saving}
                      className="inline-flex h-9 shrink-0 items-center justify-center rounded-xl bg-[var(--booking-primary)] px-3 text-xs font-semibold text-white disabled:opacity-60"
                    >
                      Salvar
                    </button>
                  </form>
                ) : null}

                {isEditing && card.key === "unit" ? (
                  <select
                    value={draft.unit_id}
                    onChange={async (event) => {
                      const value = event.target.value;
                      setDraft((current) => ({ ...current, unit_id: value, preferred_date: "", preferred_time: "" }));
                      await handleQuickSave({ unit_id: value, preferred_date: "", preferred_time: "" }, null);
                    }}
                    className={`${inlineSelectClassName} mt-2`}
                    data-testid="summary-select-unit"
                    disabled={saving}
                  >
                    <option value="">Selecionar unidade</option>
                    {summary?.options.units.map((unit) => (
                      <option key={unit.id} value={unit.id}>
                        {unit.name}
                      </option>
                    ))}
                  </select>
                ) : null}

                {isEditing && card.key === "procedure" ? (
                  <select
                    value={draft.procedure_type}
                    onChange={async (event) => {
                      const value = event.target.value;
                      setDraft((current) => ({ ...current, procedure_type: value, preferred_date: "", preferred_time: "" }));
                      await handleQuickSave({ procedure_type: value, preferred_date: "", preferred_time: "" }, null);
                    }}
                    className={`${inlineSelectClassName} mt-2`}
                    data-testid="summary-select-procedure"
                    disabled={saving}
                  >
                    <option value="">Selecionar servico</option>
                    {serviceOptions.map((service) => (
                      <option key={service.id} value={service.name}>
                        {service.name}
                      </option>
                    ))}
                  </select>
                ) : null}

                {isEditing && card.key === "preferred_date" ? (
                  <select
                    value={draft.preferred_date}
                    onChange={async (event) => {
                      const value = event.target.value;
                      setDraft((current) => ({ ...current, preferred_date: value, preferred_time: "" }));
                      await handleQuickSave({ preferred_date: value, preferred_time: "" }, null);
                    }}
                    className={`${inlineSelectClassName} mt-2`}
                    data-testid="summary-select-preferred_date"
                    disabled={saving || preferredDateOptions.length === 0}
                  >
                    <option value="">{preferredDateOptions.length ? "Selecionar data" : "Escolha unidade e servico"}</option>
                    {preferredDateOptions.map((option) => (
                      <option key={option.id} value={option.date}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                ) : null}

                {isEditing && card.key === "confirmed_slot" ? (
                  <select
                    value={draft.preferred_time}
                    onChange={async (event) => {
                      const value = event.target.value;
                      setDraft((current) => ({ ...current, preferred_time: value }));
                      await handleQuickSave({ preferred_time: value }, null);
                    }}
                    className={`${inlineSelectClassName} mt-2`}
                    data-testid="summary-select-confirmed_slot"
                    disabled={saving || preferredTimeOptions.length === 0}
                  >
                    <option value="">{preferredTimeOptions.length ? "Selecionar horario" : "Escolha uma data"}</option>
                    {preferredTimeOptions.map((option) => (
                      <option key={option.id} value={option.label}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                ) : null}
              </div>
            );
          })}
        </div>

        {loading && !summary ? (
          <p className="mt-3 text-xs text-[var(--booking-muted)]">Preparando o resumo automatico do agendamento...</p>
        ) : null}
      </div>
    </aside>
  );
}

function WhatsAppOverviewPanel() {
  const items = [
    "Link oficial validado para levar o paciente ao WhatsApp da operacao.",
    "A conversa chega no mesmo inbox usado pela clinica.",
    "A confirmacao do agendamento continua no canal oficial da assistente.",
  ];

  return (
    <aside className="flex min-h-0 flex-col overflow-hidden rounded-[30px] border border-white/70 bg-white/84 p-4 shadow-[0_18px_48px_rgba(15,23,42,0.08)] backdrop-blur sm:p-5">
      <div className="inline-flex w-fit items-center gap-2 rounded-full border border-[var(--booking-border)] bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--booking-muted)]">
        <ShieldCheck className="h-4 w-4 text-[var(--booking-primary)]" aria-hidden="true" />
        Canal protegido
      </div>
      <h2 className="mt-4 text-2xl font-semibold leading-tight text-stone-950">Agendamento oficial da clinica</h2>
      <p className="mt-2 text-sm leading-6 text-[var(--booking-muted)]">
        Essa entrada continua pelo WhatsApp do sistema, com o mesmo padrao operacional usado pela clinica.
      </p>
      <div className="mt-4 space-y-3">
        {items.map((item) => (
          <div key={item} className="flex gap-3">
            <CheckCircle2 className="mt-0.5 h-5 w-5 flex-none text-[var(--booking-primary)]" aria-hidden="true" />
            <p className="text-sm leading-6 text-[var(--booking-muted)]">{item}</p>
          </div>
        ))}
      </div>
    </aside>
  );
}

function WhatsAppCtaPanel({
  loading,
  opening,
  buttonLabel,
  handleOpenWhatsApp,
}: {
  loading: boolean;
  opening: boolean;
  buttonLabel: string;
  handleOpenWhatsApp: () => void;
}) {
  return (
    <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden rounded-[30px] border border-white/60 bg-white/82 shadow-[0_22px_70px_rgba(15,23,42,0.12)] backdrop-blur">
      <div className="flex items-center justify-between gap-3 border-b border-stone-200 bg-white/92 px-4 py-3 sm:px-5">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[var(--booking-primary)] text-white shadow-sm">
            <MessageCircle className="h-5 w-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-stone-900">WhatsApp oficial do sistema</p>
            <p className="truncate text-xs text-[var(--booking-muted)]">A conversa continua no mesmo canal da operacao da clinica</p>
          </div>
        </div>
        <div className="rounded-full border border-stone-200 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-600">
          Direcionamento oficial
        </div>
      </div>

      <div className="flex flex-1 flex-col justify-between bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.96),_rgba(242,247,245,0.92)_42%,_rgba(237,241,239,0.95))] p-5">
        <div className="space-y-4">
          <div className="max-w-[86%] rounded-[24px] rounded-bl-[10px] border border-stone-200 bg-white px-4 py-3 shadow-sm">
            <p className="text-sm font-medium text-stone-900">Seu atendimento esta pronto.</p>
            <p className="mt-1 text-sm leading-6 text-[var(--booking-muted)]">
              Ao tocar no botao abaixo, voce continua no WhatsApp oficial e a clinica recebe sua conversa no mesmo inbox do sistema.
            </p>
          </div>

          <div className="flex justify-end">
            <div className="max-w-[78%] rounded-[24px] rounded-br-[10px] bg-[var(--booking-primary)] px-4 py-3 text-sm text-white shadow-sm">
              Quero falar com a assistente da clinica.
            </div>
          </div>

          <div className="rounded-[24px] border border-dashed border-stone-200 bg-white/78 px-4 py-4 text-sm leading-6 text-[var(--booking-muted)]">
            Essa experiencia espelha o fluxo oficial da clinica: link verificado, conversa rastreada e continuidade da jornada de agendamento.
          </div>
        </div>

        <button
          type="button"
          onClick={handleOpenWhatsApp}
          disabled={loading || opening}
          className="mt-6 inline-flex min-h-14 items-center justify-center gap-2 rounded-full bg-[var(--booking-primary)] px-5 py-3 text-base font-semibold text-white shadow-sm transition hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {opening ? "Abrindo WhatsApp..." : buttonLabel}
          <MessageCircle className="h-5 w-5" aria-hidden="true" />
          <ArrowRight className="h-5 w-5" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

function PublicPhoneGate({
  clinicName,
  phone,
  saving,
  error,
  onPhoneChange,
  onSubmit,
}: {
  clinicName: string;
  phone: string;
  saving: boolean;
  error: string | null;
  onPhoneChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <div className="absolute inset-0 z-40 flex items-center justify-center bg-stone-950/45 px-4 py-6 backdrop-blur-[2px]">
      <div className="w-full max-w-md rounded-[30px] border border-white/70 bg-white/96 p-6 shadow-[0_28px_90px_rgba(15,23,42,0.24)]">
        <div className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-700">
          <ShieldCheck className="h-4 w-4" aria-hidden="true" />
          Atendimento protegido
        </div>
        <h2 className="mt-4 text-2xl font-semibold leading-tight text-stone-950">Antes de continuar, me passe seu celular</h2>
        <p className="mt-2 text-sm leading-6 text-[var(--booking-muted)]">
          Vamos usar esse numero apenas para identificar voce com mais rapidez no agendamento oficial da {clinicName}.
        </p>
        <p className="mt-2 text-sm leading-6 text-[var(--booking-muted)]">
          Pode informar seu celular ou WhatsApp com DDD. Assim a clinica ja aproveita esse dado no restante do atendimento.
        </p>

        <form onSubmit={onSubmit} className="mt-5 space-y-4">
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-stone-800">Celular ou WhatsApp com DDD</span>
            <input
              autoFocus
              type="tel"
              inputMode="tel"
              autoComplete="tel"
              value={phone}
              onChange={(event) => onPhoneChange(event.target.value)}
              placeholder="Ex.: (11) 99999-1111"
              className="h-14 w-full rounded-2xl border border-stone-200 bg-white px-4 text-sm text-stone-900 outline-none transition focus:border-[var(--booking-primary)] focus:ring-2 focus:ring-[color:color-mix(in_srgb,var(--booking-primary)_18%,transparent)]"
            />
          </label>

          {error ? (
            <p className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">{error}</p>
          ) : null}

          <button
            type="submit"
            disabled={!phone.trim() || saving}
            className="inline-flex min-h-14 w-full items-center justify-center gap-2 rounded-full bg-[var(--booking-primary)] px-5 py-3 text-base font-semibold text-white shadow-sm transition hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {saving ? "Confirmando celular..." : "Continuar atendimento"}
            <ArrowRight className="h-5 w-5" aria-hidden="true" />
          </button>
        </form>
      </div>
    </div>
  );
}

export default function PublicBookingPage() {
  const params = useParams<{ clinicSlug: string }>();
  const searchParams = useSearchParams();
  const clinicSlug = String(params.clinicSlug || "").trim();
  const bootstrappedRef = useRef(false);

  const [profile, setProfile] = useState<PublicBookingProfile | null>(null);
  const [session, setSession] = useState<PublicBookingSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<PublicBookingSummary | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [savingSummary, setSavingSummary] = useState(false);
  const [mobileSummaryOpen, setMobileSummaryOpen] = useState(false);
  const [contactPhoneDraft, setContactPhoneDraft] = useState("");
  const [savingContactPhone, setSavingContactPhone] = useState(false);
  const [contactPhoneError, setContactPhoneError] = useState<string | null>(null);
  const mobileSummaryGestureRef = useRef<{ startX: number; action: "open" | "close" } | null>(null);

  useEffect(() => {
    if (!clinicSlug || bootstrappedRef.current) return;
    bootstrappedRef.current = true;

    async function bootstrap() {
      setLoading(true);
      setError(null);
      try {
        const bookingProfile = await publicApiFetch<PublicBookingProfile>(`/public/booking/${clinicSlug}`);
        setProfile(bookingProfile);
        if (!bookingProfile.link_flow.enabled || !bookingProfile.link_flow.operational) {
          setSession(null);
          storeWebchatSession(clinicSlug, null);
          return;
        }

        let bookingSession: PublicBookingSession | null = null;
        if (bookingProfile.link_flow.cta_mode === "webchat") {
          const storedSession = readStoredWebchatSession(clinicSlug);
          if (storedSession?.public_access_token) {
            try {
              const storedSessionState = await publicApiFetch<PublicBookingSessionState>(
                `/public/booking/sessions/${storedSession.session_id}`,
                undefined,
                { publicAccessToken: storedSession.public_access_token },
              );
              bookingSession = {
                ...storedSession,
                contact_phone: storedSessionState.contact_phone,
                contact_phone_required: storedSessionState.contact_phone_required,
              };
              await publicApiFetch(
                `/public/booking/sessions/${storedSession.session_id}/events`,
                {
                  method: "POST",
                  body: JSON.stringify({
                    event_name: "webchat_session_resumed",
                    page_path: `/agendar/${clinicSlug}`,
                    payload: { source: "public_booking_page" },
                  }),
                },
                { publicAccessToken: storedSession.public_access_token },
              ).catch(() => undefined);
            } catch {
              storeWebchatSession(clinicSlug, null);
            }
          }
        }

        if (!bookingSession) {
          bookingSession = await publicApiFetch<PublicBookingSession>(`/public/booking/${clinicSlug}/sessions`, {
            method: "POST",
            body: JSON.stringify({
              browser_session_id: getBrowserSessionId(),
              utm_payload: getUtmPayload(),
              cta_mode: bookingProfile.link_flow.cta_mode,
            }),
          });
        }
        setSession(bookingSession);
        if (bookingSession.cta_mode === "webchat") {
          storeWebchatSession(clinicSlug, bookingSession);
        }

        await publicApiFetch(
          `/public/booking/sessions/${bookingSession.session_id}/events`,
          {
            method: "POST",
            body: JSON.stringify({
              event_name: "landing_viewed",
              page_path: `/agendar/${clinicSlug}`,
              payload: { source: "public_booking_page" },
            }),
          },
          bookingSession.cta_mode === "webchat"
            ? { publicAccessToken: bookingSession.public_access_token }
            : undefined,
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : "Nao foi possivel carregar o agendamento.");
      } finally {
        setLoading(false);
      }
    }

    void bootstrap();
  }, [clinicSlug]);

  useEffect(() => {
    const previousHtmlOverflow = document.documentElement.style.overflow;
    const previousBodyOverflow = document.body.style.overflow;
    const previousHtmlOverscroll = document.documentElement.style.overscrollBehavior;
    const previousBodyOverscroll = document.body.style.overscrollBehavior;

    document.documentElement.style.overflow = "hidden";
    document.body.style.overflow = "hidden";
    document.documentElement.style.overscrollBehavior = "none";
    document.body.style.overscrollBehavior = "none";

    return () => {
      document.documentElement.style.overflow = previousHtmlOverflow;
      document.body.style.overflow = previousBodyOverflow;
      document.documentElement.style.overscrollBehavior = previousHtmlOverscroll;
      document.body.style.overscrollBehavior = previousBodyOverscroll;
    };
  }, []);

  const webchatToken = session?.cta_mode === "webchat" ? session.public_access_token || "" : "";
  const contactPhoneCaptured = Boolean(session?.contact_phone && session.contact_phone.trim());
  const shouldBlockForPhone = Boolean(profile?.link_flow.operational && session && !contactPhoneCaptured);

  const loadSummary = useCallback(async () => {
    if (!session || session.cta_mode !== "webchat" || !webchatToken) return;
    setLoadingSummary(true);
    try {
      const response = await publicApiFetch<PublicBookingSummary>(
        `/public/booking/sessions/${session.session_id}/summary`,
        undefined,
        { publicAccessToken: webchatToken },
      );
      setSummary(response);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Nao foi possivel atualizar o resumo do agendamento.";
      if (shouldInvalidatePublicSession(message)) {
        storeWebchatSession(clinicSlug, null);
        setSession(null);
        setError(publicSessionUnavailableMessage(message));
        return;
      }
    } finally {
      setLoadingSummary(false);
    }
  }, [clinicSlug, session, webchatToken]);

  useEffect(() => {
    if (!session || session.cta_mode !== "webchat" || !webchatToken) {
      setSummary(null);
      return;
    }
    void loadSummary();
  }, [loadSummary, session, webchatToken]);

  useEffect(() => {
    setContactPhoneDraft(session?.contact_phone || "");
    setContactPhoneError(null);
  }, [session?.contact_phone]);

  useEffect(() => {
    if (!session || session.cta_mode !== "webchat" || !webchatToken) return;
    const interval = window.setInterval(() => {
      void loadSummary();
    }, 4000);
    return () => window.clearInterval(interval);
  }, [loadSummary, session, webchatToken]);

  const pageStyle = useMemo(() => {
    const branding = profile?.branding;
    return {
      "--booking-primary": branding?.primary_color ?? "#0f766e",
      "--booking-secondary": branding?.secondary_color ?? "#0ea5a4",
      "--booking-accent": branding?.accent_color ?? "#f59e0b",
      "--booking-background": branding?.background_color ?? "#f2f4f7",
      "--booking-card": branding?.card_color ?? "#ffffff",
      "--booking-text": branding?.text_color ?? "#1c1917",
      "--booking-muted": branding?.muted_text_color ?? "#475569",
      "--booking-border": branding?.border_color ?? "#d6d3d1",
    } as CSSProperties;
  }, [profile]);

  async function handleOpenWhatsApp() {
    if (!session?.whatsapp_url) return;
    setOpening(true);
    try {
      await publicApiFetch(`/public/booking/sessions/${session.session_id}/events`, {
        method: "POST",
        body: JSON.stringify({
          event_name: "cta_whatsapp_clicked",
          page_path: `/agendar/${clinicSlug}`,
          payload: { source: "public_booking_page" },
        }),
      });
    } catch {
      // The CTA should still open; analytics can be retried by the patient starting the chat.
    } finally {
      window.location.href = session.whatsapp_url;
    }
  }

  const clinicName = profile?.clinic.name || session?.clinic.name || "clinica";
  const isWebchat = profile?.link_flow.cta_mode === "webchat";
  const isDemoEmbeddedWebchat = isWebchat && searchParams.get("embed") === "demo-webchat";
  const linkFlowUnavailable =
    profile && (!profile.link_flow.enabled || !profile.link_flow.operational)
      ? profile.link_flow.unavailable_message ||
        "Agendamento por link indisponivel no momento. Entre em contato com a clinica pelo canal oficial."
      : null;

  const handleMobileSummaryGestureStart = useCallback(
    (event: ReactPointerEvent<HTMLElement>, action: "open" | "close") => {
      if (event.pointerType === "mouse" && event.button !== 0) return;
      event.currentTarget.setPointerCapture(event.pointerId);
      mobileSummaryGestureRef.current = { startX: event.clientX, action };
    },
    [],
  );

  const handleMobileSummaryGestureEnd = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      const gesture = mobileSummaryGestureRef.current;
      if (!gesture) return;

      const deltaX = event.clientX - gesture.startX;
      if (gesture.action === "open" && deltaX > 48) {
        setMobileSummaryOpen(true);
      }
      if (gesture.action === "close" && deltaX < -48) {
        setMobileSummaryOpen(false);
      }

      mobileSummaryGestureRef.current = null;
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
    },
    [],
  );

  const handleMobileSummaryGestureCancel = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    mobileSummaryGestureRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }, []);

  useEffect(() => {
    if (!isWebchat) {
      setMobileSummaryOpen(false);
    }
  }, [isWebchat]);

  async function handleSaveSummary(draft: Partial<PublicBookingSummaryDraft>) {
    if (!session || session.cta_mode !== "webchat" || !webchatToken) return;
    setSavingSummary(true);
    try {
      const payload: Record<string, string | undefined> = {};
      if ("full_name" in draft) payload.full_name = draft.full_name || undefined;
      if ("email" in draft) payload.email = draft.email || undefined;
      if ("birth_date" in draft) payload.birth_date = draft.birth_date || undefined;
      if ("procedure_type" in draft) payload.procedure_type = draft.procedure_type ?? "";
      if ("unit_id" in draft) payload.unit_id = draft.unit_id || undefined;
      if ("preferred_date" in draft) payload.preferred_date = draft.preferred_date ?? "";
      if ("preferred_time" in draft) payload.preferred_time = draft.preferred_time ?? "";
      const response = await publicApiFetch<PublicBookingSummary>(
        `/public/booking/sessions/${session.session_id}/summary`,
        {
          method: "PATCH",
          body: JSON.stringify(payload),
        },
        { publicAccessToken: webchatToken },
      );
      setSummary(response);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nao foi possivel salvar os dados do agendamento.");
    } finally {
      setSavingSummary(false);
    }
  }

  async function handleCaptureContactPhone(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session) return;
    setSavingContactPhone(true);
    setContactPhoneError(null);
    try {
      const response = await publicApiFetch<{ session_id: string; contact_phone: string | null; contact_phone_required: boolean }>(
        `/public/booking/sessions/${session.session_id}/contact`,
        {
          method: "POST",
          body: JSON.stringify({ phone: contactPhoneDraft }),
        },
        session.cta_mode === "webchat" ? { publicAccessToken: webchatToken } : undefined,
      );
      setSession((current) =>
        current
          ? {
              ...current,
              contact_phone: response.contact_phone,
              contact_phone_required: response.contact_phone_required,
            }
          : current,
      );
      setContactPhoneDraft(response.contact_phone || contactPhoneDraft);
      if (session.cta_mode === "webchat") {
        void loadSummary();
      }
    } catch (err) {
      setContactPhoneError(err instanceof Error ? err.message : "Nao foi possivel confirmar seu celular.");
    } finally {
      setSavingContactPhone(false);
    }
  }

  return (
    <main
      className={cn(
        "box-border overflow-hidden text-[var(--booking-text)]",
        isDemoEmbeddedWebchat
          ? "h-[100dvh] min-h-0 bg-transparent px-0 py-0"
          : "h-[100dvh] bg-[var(--booking-background)] px-4 py-4 sm:px-6 sm:py-5 lg:px-10",
      )}
      style={pageStyle}
    >
      <div
        className={cn(
          "box-border flex h-full w-full flex-col overflow-hidden",
          isDemoEmbeddedWebchat
            ? "bg-white"
            : "mx-auto max-w-7xl rounded-[34px] border border-white/70 bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.96),_rgba(242,247,245,0.94)_42%,_rgba(233,238,236,0.97))] shadow-[0_28px_90px_rgba(15,23,42,0.12)] backdrop-blur",
        )}
      >
        {!isDemoEmbeddedWebchat ? <header className="border-b border-white/60 px-5 py-5 sm:px-7">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-14 w-14 items-center justify-center overflow-hidden rounded-2xl border border-[var(--booking-border)] bg-[var(--booking-card)] shadow-sm">
                  {profile?.clinic.logo_data_url ? (
                    <Image
                      src={profile.clinic.logo_data_url}
                      alt=""
                      width={56}
                      height={56}
                      unoptimized
                      className="h-full w-full object-contain p-2"
                    />
                  ) : (
                    <CalendarCheck2 className="h-7 w-7 text-[var(--booking-primary)]" aria-hidden="true" />
                  )}
                </div>
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-emerald-700/80">Agendamento oficial</p>
                  <h1 className="truncate text-2xl font-semibold leading-tight sm:text-3xl">{clinicName}</h1>
                </div>
              </div>
            </div>
            <div className="rounded-full border border-stone-200 bg-white/80 px-4 py-2 text-sm font-medium text-[var(--booking-muted)] shadow-sm">
              Link verificado da clinica
            </div>
          </div>
        </header> : null}

        <section
          className={cn(
            "relative flex min-h-0 flex-1 overflow-hidden",
            isDemoEmbeddedWebchat ? "p-0" : "p-4 sm:p-5 lg:grid lg:grid-cols-[360px_minmax(0,1fr)] lg:gap-4 lg:p-6",
          )}
        >
          {isWebchat && !isDemoEmbeddedWebchat ? (
            <>
              <div
                className={cn(
                  "absolute inset-0 z-20 bg-stone-950/18 backdrop-blur-[1px] transition-opacity duration-300 lg:hidden",
                  mobileSummaryOpen ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0",
                )}
                aria-hidden="true"
                onClick={() => setMobileSummaryOpen(false)}
              />

              <div className="pointer-events-none absolute inset-y-4 left-4 z-30 flex lg:hidden">
                <div
                  data-testid="booking-summary-mobile-drawer"
                  data-state={mobileSummaryOpen ? "open" : "closed"}
                  className="pointer-events-auto relative h-full w-[min(88vw,360px)] min-w-0 transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]"
                  style={{
                    transform: mobileSummaryOpen ? "translateX(0)" : "translateX(calc(-100% - 1rem))",
                  }}
                >
                  <button
                    type="button"
                    onClick={() => setMobileSummaryOpen(false)}
                    aria-label="Fechar resumo do atendimento"
                    className="absolute right-3 top-3 z-10 inline-flex h-10 items-center justify-center rounded-full border border-stone-200 bg-white/92 px-3 text-xs font-semibold text-stone-700 shadow-sm transition hover:border-stone-300"
                  >
                    <X className="h-4 w-4" aria-hidden="true" />
                  </button>
                  <div
                    className="absolute inset-x-12 top-3 z-10 flex justify-center touch-pan-y"
                    onPointerDown={(event) => handleMobileSummaryGestureStart(event, "close")}
                    onPointerUp={handleMobileSummaryGestureEnd}
                    onPointerCancel={handleMobileSummaryGestureCancel}
                  >
                    <div className="h-1.5 w-16 rounded-full bg-stone-300/90 shadow-sm" aria-hidden="true" />
                  </div>
                  <BookingSummaryPanel
                    summary={summary}
                    loading={loadingSummary}
                    saving={savingSummary}
                    onSave={handleSaveSummary}
                    className="h-full pt-14"
                  />
                </div>
              </div>

              <button
                type="button"
                data-testid="booking-summary-mobile-handle"
                aria-label="Abrir resumo do atendimento"
                className={cn(
                  "absolute left-0 top-1/2 z-30 -translate-y-1/2 touch-pan-y rounded-r-[26px] border border-white/80 bg-white/92 px-2 py-4 text-[var(--booking-primary)] shadow-[0_18px_40px_rgba(15,23,42,0.16)] backdrop-blur lg:hidden",
                  mobileSummaryOpen ? "pointer-events-none opacity-0" : "opacity-100",
                )}
                onClick={() => setMobileSummaryOpen(true)}
                onPointerDown={(event) => handleMobileSummaryGestureStart(event, "open")}
                onPointerUp={handleMobileSummaryGestureEnd}
                onPointerCancel={handleMobileSummaryGestureCancel}
              >
                <span className="flex items-center gap-2">
                  <ChevronRight className="h-4 w-4 shrink-0" aria-hidden="true" />
                  <span
                    className="text-[10px] font-semibold uppercase tracking-[0.24em] text-[var(--booking-muted)]"
                    style={{ writingMode: "vertical-rl", textOrientation: "mixed" }}
                  >
                    Resumo
                  </span>
                </span>
              </button>

              <div
                className="absolute inset-y-0 left-0 z-10 w-5 touch-pan-y lg:hidden"
                aria-hidden="true"
                onPointerDown={(event) => handleMobileSummaryGestureStart(event, "open")}
                onPointerUp={handleMobileSummaryGestureEnd}
                onPointerCancel={handleMobileSummaryGestureCancel}
              />
            </>
          ) : null}

          {!isDemoEmbeddedWebchat ? <div className="hidden min-h-0 lg:flex">
            {isWebchat ? (
              <BookingSummaryPanel
                summary={summary}
                loading={loadingSummary}
                saving={savingSummary}
                onSave={handleSaveSummary}
                className="h-full"
              />
            ) : (
              <WhatsAppOverviewPanel />
            )}
          </div> : null}

          <div className={cn("flex min-h-0 flex-1", isDemoEmbeddedWebchat && "w-full")}>
            {profile?.link_flow.operational && session && isWebchat ? (
              <PublicWebchat
                clinicSlug={clinicSlug}
                clinicName={clinicName}
                session={session}
                embedded={isDemoEmbeddedWebchat}
                onExpired={(message) => {
                  storeWebchatSession(clinicSlug, null);
                  setSession(null);
                  setError(publicSessionUnavailableMessage(message || ""));
                }}
              />
            ) : null}
            {profile?.link_flow.operational && session && !isWebchat ? (
              <WhatsAppCtaPanel
                loading={loading}
                opening={opening}
                buttonLabel={profile?.link_flow.button_label || "Continuar pelo WhatsApp"}
                handleOpenWhatsApp={handleOpenWhatsApp}
              />
            ) : null}
            {!profile?.link_flow.operational || !session ? (
              <div className="flex h-full min-h-0 w-full items-center justify-center rounded-[30px] border border-white/60 bg-white/82 p-6 text-center shadow-[0_22px_70px_rgba(15,23,42,0.12)] backdrop-blur">
                <div className="max-w-md">
                  <p className="text-lg font-semibold text-stone-900">Nao foi possivel iniciar o atendimento agora.</p>
                  <p className="mt-2 text-sm leading-6 text-[var(--booking-muted)]">
                    {linkFlowUnavailable || error || "Tente novamente em instantes."}
                  </p>
                </div>
              </div>
            ) : null}
          </div>

          {shouldBlockForPhone ? (
            <PublicPhoneGate
              clinicName={clinicName}
              phone={contactPhoneDraft}
              saving={savingContactPhone}
              error={contactPhoneError}
              onPhoneChange={(value) => setContactPhoneDraft(normalizePhoneDraft(value))}
              onSubmit={handleCaptureContactPhone}
            />
          ) : null}
        </section>

        {(linkFlowUnavailable || error) && profile?.link_flow.operational && session ? (
          <div className="px-4 pb-4 sm:px-5 lg:px-6">
            {linkFlowUnavailable ? (
              <p className="rounded-[22px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                {linkFlowUnavailable}
              </p>
            ) : null}
            {error ? (
              <p className="mt-3 rounded-[22px] border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
            ) : null}
          </div>
        ) : null}
      </div>
    </main>
  );
}

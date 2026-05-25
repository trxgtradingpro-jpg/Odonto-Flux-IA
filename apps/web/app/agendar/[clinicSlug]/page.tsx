"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, FormEvent, PointerEvent as ReactPointerEvent } from "react";
import {
  ArrowRight,
  CalendarCheck2,
  CalendarDays,
  ChevronRight,
  CheckCircle2,
  CheckCheck,
  ClipboardList,
  Info,
  Mail,
  MapPinHouse,
  MessageCircle,
  MoreVertical,
  Phone,
  List,
  PencilLine,
  SendHorizontal,
  ShieldCheck,
  Sparkles,
  Video,
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
    contact_phone?: string | null;
    contact_whatsapp_url?: string | null;
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
  patient_name?: string | null;
  clinic: {
    slug: string;
    name: string;
    contact_phone?: string | null;
    contact_whatsapp_url?: string | null;
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
  patient_name?: string | null;
};

type PublicWebchatMessage = {
  id: string;
  role: "patient" | "assistant";
  text: string;
  created_at: string | null;
  status: string;
};

type PublicWebchatMessageVisualState = "pending" | "received";

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
    unit_name?: string | null;
    unit_address?: string | null;
    patient_name?: string | null;
    patient_email?: string | null;
    birth_date?: string | null;
    procedure_type?: string | null;
  };
  options: {
    units: Array<{ id: string; name: string }>;
    services?: Array<{ id: string; name: string }>;
    preferred_dates?: Array<{ id: string; date: string; label: string; description?: string | null }>;
    preferred_times?: Array<{ id: string; label: string; time?: string | null }>;
  };
};

type PublicBookingConfirmationResult = {
  summary: PublicBookingSummary;
  result: {
    status: "created" | "already_created";
    appointment_id: string;
    unit_name: string | null;
    unit_address: string | null;
    procedure_type: string | null;
    starts_at: string | null;
    patient_name: string | null;
    patient_email: string | null;
    birth_date: string | null;
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

function estimateAssistantTypingDelay(messages: PublicWebchatMessage[]): number {
  const totalCharacters = messages.reduce((count, message) => count + message.text.trim().length, 0);
  if (totalCharacters <= 0) return 1200;
  return Math.min(7000, Math.max(1200, 900 + totalCharacters * 45));
}

function getPatientMessageVisualState(status: string): PublicWebchatMessageVisualState {
  return status === "received" ? "received" : "pending";
}

function reconcileIncomingPatientMessages(
  current: PublicWebchatMessage[],
  incoming: PublicWebchatMessage[],
): PublicWebchatMessage[] {
  if (!incoming.length) return current;
  const next = [...current];

  for (const incomingMessage of incoming) {
    if (next.some((message) => message.id === incomingMessage.id)) {
      continue;
    }

    const optimisticIndex = next.findIndex(
      (message) =>
        message.role === "patient"
        && message.status === "pending"
        && message.text.trim() === incomingMessage.text.trim(),
    );

    if (optimisticIndex >= 0) {
      next[optimisticIndex] = incomingMessage;
      continue;
    }

    next.push(incomingMessage);
  }

  return next;
}

function formatPublicDate(value: string | null): string {
  if (!value) return "Pendente";
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [year, month, day] = value.split("-");
    return `${day}/${month}/${year}`;
  }
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

function isTransientPublicSummaryError(message: string): boolean {
  return /carregar o atendimento agora/i.test(message) || /internal server error/i.test(message) || /failed to fetch/i.test(message);
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

function notifyDemoWebchatParent({
  clinicSlug,
  sessionId,
  reason,
}: {
  clinicSlug: string;
  sessionId: string;
  reason: "contact_captured" | "message_sent";
}) {
  if (typeof window === "undefined" || window.parent === window) return;
  window.parent.postMessage(
    {
      type: "clinicflux:webchat-updated",
      clinicSlug,
      sessionId,
      reason,
    },
    window.location.origin,
  );
}

function normalizePhoneDraft(value: string): string {
  return value.replace(/[^\d+()\-\s]/g, "").slice(0, 30);
}

function buildPhoneCallUrl(phone: string | null | undefined): string | null {
  const normalized = String(phone || "").replace(/\D/g, "");
  if (!normalized) return null;
  return `tel:+${normalized}`;
}

function PublicWebchat({
  clinicSlug,
  clinicName,
  session,
  onExpired,
  embedded = false,
  onOpenSummary,
  contactPhone,
  contactWhatsAppUrl,
  patientName,
}: {
  clinicSlug: string;
  clinicName: string;
  session: PublicBookingSession;
  onExpired: (message?: string) => void;
  embedded?: boolean;
  onOpenSummary?: () => void;
  contactPhone?: string | null;
  contactWhatsAppUrl?: string | null;
  patientName?: string | null;
}) {
  const [messages, setMessages] = useState<PublicWebchatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [assistantTyping, setAssistantTyping] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(true);
  const [chatError, setChatError] = useState<string | null>(null);
  const [contactOptionsOpen, setContactOptionsOpen] = useState(false);
  const [keyboardInset, setKeyboardInset] = useState(0);
  const [composerFocused, setComposerFocused] = useState(false);
  const openedRef = useRef(false);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const messagesRef = useRef<PublicWebchatMessage[]>([]);
  const assistantTypingTimeoutRef = useRef<number | null>(null);
  const patientReceiptTimeoutRef = useRef<number | null>(null);
  const pendingAssistantMessageIdsRef = useRef<Set<string>>(new Set());
  const nextAssistantTypingAtRef = useRef<number>(0);
  const lastConfirmedMessageId = [...messages]
    .reverse()
    .find((message) => !(message.role === "patient" && message.status === "pending"))?.id;
  const token = session.public_access_token || "";
  const normalizedPatientName = String(patientName || "").trim();

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  const loadMessages = useCallback(async (afterMessageId?: string) => {
    try {
      const suffix = afterMessageId ? `?after_message_id=${encodeURIComponent(afterMessageId)}` : "";
      const response = await publicApiFetch<{ data: PublicWebchatMessage[] }>(
        `/public/booking/sessions/${session.session_id}/chat/messages${suffix}`,
        undefined,
        { publicAccessToken: token },
      );
      const seen = new Set(messagesRef.current.map((message) => message.id));
      const incoming = afterMessageId
        ? response.data.filter(
            (message) => !seen.has(message.id) && !pendingAssistantMessageIdsRef.current.has(message.id),
          )
        : response.data;
      if (!afterMessageId) {
        pendingAssistantMessageIdsRef.current.clear();
        if (assistantTypingTimeoutRef.current) {
          window.clearTimeout(assistantTypingTimeoutRef.current);
          assistantTypingTimeoutRef.current = null;
        }
        setAssistantTyping(false);
        setMessages(incoming);
        setChatError(null);
        return;
      }

      const immediateMessages = incoming.filter((message) => message.role !== "assistant");
      const delayedAssistantMessages = incoming.filter((message) => message.role === "assistant");

      if (immediateMessages.length) {
        setMessages((current) => reconcileIncomingPatientMessages(current, immediateMessages));
      }

      if (delayedAssistantMessages.length) {
        delayedAssistantMessages.forEach((message) => pendingAssistantMessageIdsRef.current.add(message.id));
        if (assistantTypingTimeoutRef.current) {
          window.clearTimeout(assistantTypingTimeoutRef.current);
        }
        const typingStartDelay = Math.max(0, nextAssistantTypingAtRef.current - Date.now());
        const typingDelay = estimateAssistantTypingDelay(delayedAssistantMessages);
        assistantTypingTimeoutRef.current = window.setTimeout(() => {
          setAssistantTyping(true);
          assistantTypingTimeoutRef.current = window.setTimeout(() => {
            setMessages((latest) => {
              const latestSeen = new Set(latest.map((message) => message.id));
              const nextAssistantMessages = delayedAssistantMessages.filter((message) => !latestSeen.has(message.id));
              return nextAssistantMessages.length ? [...latest, ...nextAssistantMessages] : latest;
            });
            delayedAssistantMessages.forEach((message) => pendingAssistantMessageIdsRef.current.delete(message.id));
            assistantTypingTimeoutRef.current = null;
            setAssistantTyping(false);
          }, typingDelay);
        }, typingStartDelay);
      }

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
    return () => {
      if (assistantTypingTimeoutRef.current) {
        window.clearTimeout(assistantTypingTimeoutRef.current);
      }
      if (patientReceiptTimeoutRef.current) {
        window.clearTimeout(patientReceiptTimeoutRef.current);
      }
    };
  }, []);

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
      if (sending) return;
      void loadMessages(lastConfirmedMessageId);
    }, assistantTyping ? 1500 : 4000);
    return () => window.clearInterval(interval);
  }, [assistantTyping, lastConfirmedMessageId, loadMessages, sending, token]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    viewport.scrollTo({ top: viewport.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const visualViewport = window.visualViewport;
    if (!visualViewport) return;

    const syncKeyboardInset = () => {
      if (!composerFocused) {
        setKeyboardInset(0);
        return;
      }
      const nextInset = Math.max(0, window.innerHeight - (visualViewport.height + visualViewport.offsetTop));
      setKeyboardInset(nextInset > 8 ? nextInset : 0);
    };

    syncKeyboardInset();
    visualViewport.addEventListener("resize", syncKeyboardInset);
    visualViewport.addEventListener("scroll", syncKeyboardInset);
    window.addEventListener("orientationchange", syncKeyboardInset);

    return () => {
      visualViewport.removeEventListener("resize", syncKeyboardInset);
      visualViewport.removeEventListener("scroll", syncKeyboardInset);
      window.removeEventListener("orientationchange", syncKeyboardInset);
    };
  }, [composerFocused]);

  useEffect(() => {
    if (!composerFocused) return;
    const viewport = viewportRef.current;
    const input = inputRef.current;
    if (!viewport || !input) return;

    window.requestAnimationFrame(() => {
      viewport.scrollTo({ top: viewport.scrollHeight, behavior: "smooth" });
      input.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
  }, [composerFocused, keyboardInset]);

  async function handleSendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || sending) return;
    const optimisticCreatedAt = new Date().toISOString();
    const clientMessageId =
      typeof window.crypto?.randomUUID === "function"
        ? window.crypto.randomUUID()
        : `msg_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    const optimisticMessage: PublicWebchatMessage = {
      id: clientMessageId,
      role: "patient",
      text,
      created_at: optimisticCreatedAt,
      status: "pending",
    };
    setDraft("");
    setMessages((current) => [...current, optimisticMessage]);
    setSending(true);
    setAssistantTyping(false);
    setChatError(null);
    nextAssistantTypingAtRef.current = Date.now() + 5000;
    if (patientReceiptTimeoutRef.current) {
      window.clearTimeout(patientReceiptTimeoutRef.current);
    }
    patientReceiptTimeoutRef.current = window.setTimeout(() => {
      setMessages((current) =>
        current.map((message) => (message.id === clientMessageId ? { ...message, status: "received" } : message)),
      );
      patientReceiptTimeoutRef.current = null;
    }, 3000);
    try {
      const response = await publicApiFetch<{ message: PublicWebchatMessage }>(
        `/public/booking/sessions/${session.session_id}/chat/messages`,
        {
          method: "POST",
          body: JSON.stringify({ text, client_message_id: clientMessageId }),
        },
        { publicAccessToken: token },
      );
      setMessages((current) => {
        const withoutOptimistic = current.filter((message) => message.id !== clientMessageId);
        return reconcileIncomingPatientMessages(withoutOptimistic, [{ ...response.message, status: "received" }]);
      });
      await loadMessages(response.message.id);
      notifyDemoWebchatParent({
        clinicSlug,
        sessionId: session.session_id,
        reason: "message_sent",
      });
    } catch (err) {
      setMessages((current) => current.filter((message) => message.id !== clientMessageId));
      setDraft(text);
      const message = err instanceof Error ? err.message : "Nao foi possivel enviar sua mensagem.";
      setChatError(message);
      if (shouldInvalidatePublicSession(message)) {
        onExpired(message);
      }
    } finally {
      setSending(false);
    }
  }

  function handleOpenContactOptions() {
    setContactOptionsOpen(true);
  }

  function handleOpenWhatsAppContact() {
    if (!contactWhatsAppUrl) return;
    window.location.href = contactWhatsAppUrl;
  }

  function handleOpenPhoneContact() {
    const phoneUrl = buildPhoneCallUrl(contactPhone);
    if (!phoneUrl) return;
    window.location.href = phoneUrl;
  }

  return (
    <div
      data-public-webchat-shell="true"
      className={cn(
        "whatsapp-chat-thread-surface-dark relative flex h-full min-h-0 flex-1 flex-col overflow-hidden font-[Roboto,Arial,sans-serif] text-[#e9edef] sm:font-inherit",
        embedded
          ? "sm:bg-white"
          : "sm:rounded-[30px] sm:border sm:border-white/60 sm:bg-white/82 sm:text-[var(--booking-text)] sm:shadow-[0_22px_70px_rgba(15,23,42,0.12)] sm:backdrop-blur",
      )}
    >
      {!embedded ? <div data-public-webchat-header="true" className="flex h-16 shrink-0 items-center justify-between gap-2 border-b border-[#1f2c33] bg-[#111b21] px-2.5 py-2 text-[#e9edef] sm:h-auto sm:border-stone-200 sm:bg-white/92 sm:px-5 sm:py-3 sm:text-stone-900">
        <div className="flex min-w-0 items-center gap-2.5 sm:gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#202c33] text-[#00a884] shadow-sm sm:h-11 sm:w-11 sm:bg-[var(--booking-primary)] sm:text-white">
            <MessageCircle className="h-5 w-5" aria-hidden="true" />
          </span>
          <div className="min-w-0 leading-tight [&>p:nth-child(4)]:hidden sm:[&>p:nth-child(4)]:block">
            <p data-testid="public-webchat-mobile-title" data-public-webchat-mobile-title="true" className="truncate text-[20px] font-normal leading-6 text-[#e9edef] sm:hidden">{clinicName}</p>
            <p data-public-webchat-desktop-title="true" className="hidden truncate text-sm font-semibold text-stone-900 sm:block">Atendimento online</p>
            <p data-public-webchat-mobile-subtitle="true" className="truncate text-[12px] leading-4 text-[#8696a0] sm:hidden">Atendimento online - canal oficial da clinica</p>
            <p data-public-webchat-desktop-subtitle="true" className="truncate text-xs text-[var(--booking-muted)]">{clinicName} · canal oficial da clinica</p>
          </div>
        </div>
        <div data-public-webchat-actions="true" className="flex shrink-0 items-center gap-4 text-[#e9edef] sm:hidden">
          <button
            type="button"
            aria-label="Abrir opcoes de contato"
            onClick={handleOpenContactOptions}
            className="inline-flex items-center justify-center text-current"
          >
            <Video className="h-6 w-6" />
          </button>
          <button
            type="button"
            aria-label="Abrir opcoes de contato"
            onClick={handleOpenContactOptions}
            className="inline-flex items-center justify-center text-current"
          >
            <Phone className="h-6 w-6" />
          </button>
          <button
            type="button"
            aria-label="Abrir resumo do atendimento"
            onClick={() => onOpenSummary?.()}
            className="inline-flex items-center justify-center text-current"
          >
            <MoreVertical className="h-6 w-6" />
          </button>
        </div>
        <div data-public-webchat-online-badge="true" className="hidden rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-700 sm:block">
          Online
        </div>
      </div> : null}

      <div
        ref={viewportRef}
        data-public-webchat-thread="true"
        className={cn(
          "whatsapp-chat-thread-surface-dark min-h-0 flex-1 space-y-1.5 overflow-y-auto px-2 py-2",
          embedded
            ? "sm:space-y-4 sm:px-5 sm:py-4"
            : "sm:space-y-4 sm:px-5 sm:py-5",
        )}
        style={{
          paddingBottom: keyboardInset ? `${keyboardInset + 72}px` : undefined,
        }}
      >
        {loadingMessages ? (
          <div className="w-fit max-w-[80%] rounded-lg bg-[#202c33] px-2.5 py-1.5 text-[13px] leading-5 text-[#8696a0] shadow-sm sm:max-w-[88%] sm:rounded-[24px] sm:border sm:border-stone-200 sm:bg-white sm:px-4 sm:py-3 sm:text-sm sm:text-[var(--booking-muted)]">
            Carregando conversa...
          </div>
        ) : null}
        {!loadingMessages && messages.length === 0 ? (
          <div className="flex justify-start">
            <div className="w-fit max-w-[80%] rounded-lg rounded-bl-[3px] bg-[#202c33] px-2.5 py-1.5 text-[16px] leading-[21px] text-[#e9edef] shadow-sm sm:max-w-[88%] sm:rounded-[24px] sm:rounded-bl-[10px] sm:border sm:border-stone-200 sm:bg-white sm:px-4 sm:py-3 sm:text-sm sm:leading-6 sm:text-[var(--booking-text)]">
              <p className="font-medium text-[#e9edef] sm:text-stone-900">
                {normalizedPatientName ? `Oi ${normalizedPatientName}, eu sou a assistente de agendamento.` : "Oi, eu sou a assistente de agendamento."}
              </p>
              <p className="mt-1 text-[#8696a0] sm:text-[var(--booking-muted)]">
                Me conte o que voce precisa e eu vou te ajudar por aqui. Exemplo: Quero agendar uma avaliacao esta semana.
              </p>
            </div>
          </div>
        ) : null}
        {messages.map((message) => {
          const isPatient = message.role === "patient";
          const patientVisualState = isPatient ? getPatientMessageVisualState(message.status) : null;
          return (
            <div key={message.id} className={`flex ${isPatient ? "justify-end" : "justify-start"}`}>
              <div
                data-testid="public-webchat-message-bubble"
                className={[
                  "w-fit max-w-[80%] rounded-lg px-2.5 py-1.5 text-[16px] leading-[21px] text-[#e9edef] shadow-sm sm:max-w-[78%] sm:rounded-[24px] sm:px-4 sm:py-3 sm:text-sm sm:leading-6",
                  isPatient
                    ? "rounded-br-[3px] bg-[#005c4b] sm:rounded-br-[10px] sm:bg-[var(--booking-primary)] sm:text-white"
                    : "rounded-bl-[3px] bg-[#202c33] sm:rounded-bl-[10px] sm:border sm:border-stone-200 sm:bg-white sm:text-[var(--booking-text)]",
                ].join(" ")}
              >
                <p className="whitespace-pre-wrap break-words">{message.text}</p>
                <div
                  className={`mt-0.5 flex justify-end text-[11px] leading-none sm:mt-2 ${isPatient ? "text-[#aebac1] sm:text-white/80" : "text-[#8696a0] sm:text-[var(--booking-muted)]"}`}
                >
                  <span>{formatPublicMessageTime(message.created_at)}</span>
                  {isPatient ? (
                    <CheckCheck
                      className={cn(
                        "ml-1.5 h-3.5 w-3.5",
                        patientVisualState === "received"
                          ? "text-[#53bdeb] sm:text-[#8fd3ff]"
                          : "text-[#6b7c85] sm:text-white/55",
                      )}
                      aria-hidden="true"
                    />
                  ) : null}
                </div>
              </div>
            </div>
          );
        })}
        {assistantTyping ? (
          <div className="flex justify-start">
            <div className="flex w-fit items-center gap-2 rounded-lg bg-[#202c33] px-2.5 py-2 text-[13px] leading-5 text-[#8696a0] shadow-sm sm:rounded-[20px] sm:border sm:border-stone-200 sm:bg-white sm:px-4 sm:py-2.5 sm:text-xs sm:text-[var(--booking-muted)]">
              <span>Digitando</span>
              <span className="typing-dots" aria-hidden="true">
                <span />
                <span />
                <span />
              </span>
            </div>
          </div>
        ) : null}
      </div>

      {contactOptionsOpen ? (
        <div className="absolute inset-0 z-40 flex items-center justify-center bg-stone-950/45 px-4 py-6 backdrop-blur-[2px]">
          <div className="w-full max-w-sm rounded-[28px] border border-white/15 bg-[#111b21] p-5 text-left text-[#e9edef] shadow-[0_24px_60px_rgba(15,23,42,0.35)]">
            <div className="flex items-start justify-between gap-3">
              <div>
              </div>
              <button
                type="button"
                aria-label="Fechar opcoes de contato"
                onClick={() => setContactOptionsOpen(false)}
                className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-white/10 bg-white/5 text-[#e9edef]"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <div className="mt-5 grid gap-3">
              <button
                type="button"
                onClick={handleOpenWhatsAppContact}
                disabled={!contactWhatsAppUrl}
                className="inline-flex min-h-12 items-center justify-center rounded-2xl bg-[var(--booking-primary)] px-4 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                Continuar pelo WhatsApp
              </button>
              <button
                type="button"
                onClick={handleOpenPhoneContact}
                disabled={!contactPhone}
                className="inline-flex min-h-12 items-center justify-center rounded-2xl border border-white/15 bg-white/5 px-4 py-3 text-sm font-semibold text-[#e9edef] disabled:cursor-not-allowed disabled:opacity-50"
              >
                Ligar para a clinica
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <div
        data-public-webchat-composer="true"
        className={cn("relative z-20 border-t border-transparent bg-transparent px-2 py-1.5 sm:border-stone-200 sm:bg-white/94 sm:px-5 sm:py-3", embedded && "sm:shadow-[0_-8px_24px_rgba(15,23,42,0.06)]")}
        style={{
          paddingBottom: "calc(0.375rem + env(safe-area-inset-bottom))",
          transform: keyboardInset ? `translateY(-${keyboardInset}px)` : undefined,
          transition: "transform 180ms ease-out",
          willChange: keyboardInset ? "transform" : undefined,
        }}
      >
        {chatError ? (
          <p className="mb-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[13px] leading-5 text-amber-100 sm:mb-3 sm:rounded-2xl sm:border-amber-200 sm:bg-amber-50 sm:px-4 sm:py-3 sm:text-sm sm:text-amber-900">
            {chatError}
          </p>
        ) : null}

        <form onSubmit={handleSendMessage} className="flex items-end gap-2 sm:gap-3">
          <div className="flex h-12 flex-1 items-center gap-2 rounded-[24px] border-none bg-[#202c33] px-4 text-[#e9edef] shadow-none transition focus-within:ring-1 focus-within:ring-[#00a884]/40 sm:h-auto sm:rounded-[28px] sm:border sm:border-stone-200 sm:bg-white sm:px-4 sm:py-3 sm:text-[var(--booking-text)] sm:shadow-[inset_0_1px_0_rgba(255,255,255,0.85)] sm:focus-within:border-[var(--booking-primary)] sm:focus-within:ring-2 sm:focus-within:ring-[color:color-mix(in_srgb,var(--booking-primary)_16%,transparent)]">
            <input
              ref={inputRef}
              data-public-webchat-input="true"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onFocus={() => setComposerFocused(true)}
              onBlur={() => setComposerFocused(false)}
              maxLength={1200}
              placeholder="Digite sua mensagem..."
              style={{ fontSize: "16px" }}
              className="h-full min-w-0 flex-1 border-none bg-transparent text-[16px] leading-5 text-[#e9edef] outline-none placeholder:text-[#8696a0] sm:h-7 sm:w-full sm:text-sm sm:text-[var(--booking-text)] sm:placeholder:text-stone-400"
            />
          </div>
          <button
            type="submit"
            disabled={!draft.trim() || sending}
            className="inline-flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-[#00a884] text-[#0b141a] shadow-sm transition hover:brightness-95 disabled:cursor-not-allowed disabled:bg-[#2a3942] disabled:text-[#8696a0] sm:bg-[var(--booking-primary)] sm:text-white sm:disabled:opacity-60"
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
  onConfirmBooking,
  confirmingBooking,
  className,
}: {
  summary: PublicBookingSummary | null;
  loading: boolean;
  saving: boolean;
  onSave: (draft: Partial<PublicBookingSummaryDraft>) => Promise<void>;
  onConfirmBooking: () => Promise<void>;
  confirmingBooking: boolean;
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
      action: "edit" as const,
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
  const canConfirmBooking = Boolean(
    summary?.fields.patient_name.complete
    && summary?.fields.birth_date.complete
    && summary?.fields.unit.complete
    && summary?.fields.procedure.complete
    && summary?.fields.preferred_date.complete
    && summary?.fields.confirmed_slot.complete,
  );

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
                      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-white">
                        {card.label}
                      </p>
                      <p
                        className="mt-1 break-words text-[11px] font-medium leading-4 text-white sm:text-[12px]"
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

                {isEditing && card.key === "birth_date" ? (
                  <form
                    className="mt-2 flex gap-2"
                    onSubmit={async (event) => {
                      event.preventDefault();
                      await handleQuickSave({ birth_date: draft.birth_date }, null);
                    }}
                  >
                    <input
                      type="date"
                      value={draft.birth_date}
                      onChange={(event) => setDraft((current) => ({ ...current, birth_date: event.target.value }))}
                      className={inlineInputClassName}
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
      <div className="mt-3 rounded-[18px] border border-white/65 bg-white/92 p-3 shadow-sm">
        <p className="text-[11px] font-medium text-stone-500">
          Nome, nascimento, unidade, servico, data e horario sao obrigatorios. E-mail continua opcional.
        </p>
        <button
          type="button"
          onClick={() => void onConfirmBooking()}
          disabled={!canConfirmBooking || saving || confirmingBooking}
          className="mt-3 inline-flex w-full items-center justify-center rounded-2xl bg-[var(--booking-primary)] px-4 py-3 text-sm font-semibold text-white transition hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {confirmingBooking ? "Agendando..." : "Agendar agora"}
        </button>
      </div>
    </aside>
  );
}

function WhatsAppOverviewPanel({ className }: { className?: string }) {
  const items = [
    "Link oficial validado para levar o paciente ao WhatsApp da operacao.",
    "A conversa chega no mesmo inbox usado pela clinica.",
    "A confirmacao do agendamento continua no canal oficial da assistente.",
  ];

  return (
    <aside
      className={cn(
        "flex min-h-0 flex-col overflow-hidden rounded-[30px] border border-white/70 bg-white/84 p-4 shadow-[0_18px_48px_rgba(15,23,42,0.08)] backdrop-blur sm:p-5",
        className,
      )}
    >
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

      <div className="whatsapp-chat-thread-surface flex flex-1 flex-col justify-between p-5">
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
  demoMode = false,
  phone,
  saving,
  error,
  onPhoneChange,
  onSubmit,
}: {
  clinicName: string;
  demoMode?: boolean;
  phone: string;
  saving: boolean;
  error: string | null;
  onPhoneChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const badgeLabel = demoMode ? "Simulacao da clinica" : "Atendimento protegido";
  const heading = demoMode ? "Aqui a clinica vai simular um paciente" : "Antes de continuar, me passe seu celular";
  const descriptionPrimary = demoMode
    ? `Informe um celular para testar o fluxo de agendamento e ver como a conversa vai fluir no webchat da ${clinicName}.`
    : `Vamos usar esse numero apenas para identificar voce com mais rapidez no agendamento oficial da ${clinicName}.`;
  const descriptionSecondary = demoMode
    ? "Assim a equipe acompanha, na pratica, cada etapa do atendimento, como se estivesse no lugar do paciente."
    : "Pode informar seu celular ou WhatsApp com DDD. Assim a clinica ja aproveita esse dado no restante do atendimento.";
  const phoneLabel = demoMode ? "Celular ou WhatsApp para a simulacao" : "Celular ou WhatsApp com DDD";
  const submitLabel = saving
    ? demoMode
      ? "Iniciando simulacao..."
      : "Confirmando celular..."
    : demoMode
      ? "Continuar simulacao"
      : "Continuar atendimento";

  return (
    <div className="absolute inset-0 z-40 flex items-center justify-center bg-stone-950/45 px-4 py-6 backdrop-blur-[2px]">
      <div
        data-testid="public-phone-gate-card"
        className="w-full max-w-md rounded-[30px] border border-white/70 bg-white p-6 shadow-[0_28px_90px_rgba(15,23,42,0.24)]"
      >
        <div className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-700">
          <ShieldCheck className="h-4 w-4" aria-hidden="true" />
          {badgeLabel}
        </div>
        <h2 className="mt-4 text-2xl font-semibold leading-tight text-stone-950">{heading}</h2>
        <p className="mt-2 text-sm leading-6 text-[var(--booking-muted)]">{descriptionPrimary}</p>
        <p className="mt-2 text-sm leading-6 text-[var(--booking-muted)]">{descriptionSecondary}</p>

        <form onSubmit={onSubmit} className="mt-5 space-y-4">
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-stone-800">{phoneLabel}</span>
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
            {submitLabel}
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
  const isDemoEmbeddedRequest = searchParams.get("embed") === "demo-webchat";
  const demoSessionResetKey = searchParams.get("demo_session_reset");
  const bootstrappedRef = useRef(false);
  const bootstrapRetryTimeoutRef = useRef<number | null>(null);

  const [profile, setProfile] = useState<PublicBookingProfile | null>(null);
  const [session, setSession] = useState<PublicBookingSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<PublicBookingSummary | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [savingSummary, setSavingSummary] = useState(false);
  const [confirmingSummaryBooking, setConfirmingSummaryBooking] = useState(false);
  const [bookingCompletedModal, setBookingCompletedModal] = useState<PublicBookingConfirmationResult["result"] | null>(null);
  const [mobileSummaryOpen, setMobileSummaryOpen] = useState(false);
  const [contactPhoneDraft, setContactPhoneDraft] = useState("");
  const [savingContactPhone, setSavingContactPhone] = useState(false);
  const [contactPhoneError, setContactPhoneError] = useState<string | null>(null);
  const [bootstrapRetryTick, setBootstrapRetryTick] = useState(0);
  const mobileSummaryGestureRef = useRef<{ startX: number; action: "open" | "close" } | null>(null);
  const summaryFailureCountRef = useRef(0);
  const summaryManualChangesPendingRef = useRef(false);

  const scheduleBootstrapRetry = useCallback(() => {
    if (typeof window === "undefined") return;
    if (bootstrapRetryTimeoutRef.current) {
      window.clearTimeout(bootstrapRetryTimeoutRef.current);
    }
    bootstrapRetryTimeoutRef.current = window.setTimeout(() => {
      setBootstrapRetryTick((current) => current + 1);
    }, 3000);
  }, []);

  useEffect(() => {
    if (!clinicSlug || bootstrappedRef.current) return;
    bootstrappedRef.current = true;
    setBootstrapRetryTick((current) => current + 1);
  }, [clinicSlug]);

  useEffect(() => {
    if (!clinicSlug || bootstrapRetryTick <= 0) return;

    async function bootstrap() {
      setLoading(true);
      setError(null);
      try {
        const bookingProfile = await publicApiFetch<PublicBookingProfile>(`/public/booking/${clinicSlug}`);
        setProfile(bookingProfile);
        if (!bookingProfile.link_flow.enabled || !bookingProfile.link_flow.operational) {
          setSession(null);
          storeWebchatSession(clinicSlug, null);
          setError(
            bookingProfile.link_flow.unavailable_message ||
              "Agendamento por link indisponivel no momento. Entre em contato com a clinica pelo canal oficial.",
          );
          setLoading(false);
          return;
        }

        let bookingSession: PublicBookingSession | null = null;
        if (bookingProfile.link_flow.cta_mode === "webchat") {
          if (isDemoEmbeddedRequest && demoSessionResetKey) {
            storeWebchatSession(clinicSlug, null);
          }
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
                patient_name: storedSessionState.patient_name,
              };
              void publicApiFetch(
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
        setLoading(false);

        void publicApiFetch(
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
        ).catch(() => undefined);
      } catch (err) {
        setSession(null);
        setError(err instanceof Error ? err.message : "Nao foi possivel carregar o agendamento.");
        scheduleBootstrapRetry();
      }
    }

    void bootstrap();
  }, [bootstrapRetryTick, clinicSlug, demoSessionResetKey, isDemoEmbeddedRequest, scheduleBootstrapRetry]);

  useEffect(() => {
    return () => {
      if (bootstrapRetryTimeoutRef.current) {
        window.clearTimeout(bootstrapRetryTimeoutRef.current);
      }
    };
  }, []);

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
      summaryFailureCountRef.current = 0;
      setSummary(response);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Nao foi possivel atualizar o resumo do agendamento.";
      summaryFailureCountRef.current += 1;
      const shouldInvalidate = shouldInvalidatePublicSession(message) && summaryFailureCountRef.current >= 3;
      if (shouldInvalidatePublicSession(message)) {
        if (!shouldInvalidate || isTransientPublicSummaryError(message)) {
          return;
        }
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
    summaryFailureCountRef.current = 0;
    summaryManualChangesPendingRef.current = false;
  }, [session?.contact_phone, session?.session_id]);

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
  const isDemoEmbeddedWebchat = isWebchat && isDemoEmbeddedRequest;
  const useOverviewSidePanel = !isWebchat || isDemoEmbeddedWebchat;
  const sidePanelOpenLabel = useOverviewSidePanel
    ? "Abrir painel do agendamento oficial"
    : "Abrir resumo do atendimento";
  const sidePanelCloseLabel = useOverviewSidePanel
    ? "Fechar painel do agendamento oficial"
    : "Fechar resumo do atendimento";
  const linkFlowUnavailable =
    profile && (!profile.link_flow.enabled || !profile.link_flow.operational)
      ? profile.link_flow.unavailable_message ||
        "Agendamento por link indisponivel no momento. Entre em contato com a clinica pelo canal oficial."
      : null;
  const publicBookingBlockingMessage = linkFlowUnavailable;
  const showPublicBookingLoadingPanel = (loading || !session) && !publicBookingBlockingMessage;

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
        handleCloseSummaryPanel();
      }

      mobileSummaryGestureRef.current = null;
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
    },
    [handleCloseSummaryPanel],
  );

  const handleMobileSummaryGestureCancel = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    mobileSummaryGestureRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }, []);

  function handleCloseSummaryPanel() {
    if (!mobileSummaryOpen) return;
    setMobileSummaryOpen(false);
    if (!summaryManualChangesPendingRef.current || !session || session.cta_mode !== "webchat" || !webchatToken) return;
    summaryManualChangesPendingRef.current = false;
    void publicApiFetch<PublicBookingSummary>(
      `/public/booking/sessions/${session.session_id}/summary/followup`,
      { method: "POST" },
      { publicAccessToken: webchatToken },
    )
      .then((response) => {
        setSummary(response);
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Nao foi possivel continuar o atendimento pelo resumo.");
      });
  }

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
          body: JSON.stringify({ ...payload, dispatch_followup: false }),
        },
        { publicAccessToken: webchatToken },
      );
      setSummary(response);
      summaryManualChangesPendingRef.current = true;
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nao foi possivel salvar os dados do agendamento.");
    } finally {
      setSavingSummary(false);
    }
  }

  async function handleConfirmSummaryBooking() {
    if (!session || session.cta_mode !== "webchat" || !webchatToken) return;
    setConfirmingSummaryBooking(true);
    try {
      const response = await publicApiFetch<PublicBookingConfirmationResult>(
        `/public/booking/sessions/${session.session_id}/summary/confirm`,
        { method: "POST" },
        { publicAccessToken: webchatToken },
      );
      setSummary(response.summary);
      setBookingCompletedModal(response.result);
      summaryManualChangesPendingRef.current = false;
      setMobileSummaryOpen(false);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nao foi possivel concluir o agendamento agora.");
    } finally {
      setConfirmingSummaryBooking(false);
    }
  }

  async function handleCaptureContactPhone(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session) return;
    setSavingContactPhone(true);
    setContactPhoneError(null);
    try {
      const response = await publicApiFetch<{ session_id: string; contact_phone: string | null; contact_phone_required: boolean; patient_name?: string | null }>(
        `/public/booking/sessions/${session.session_id}/contact`,
        {
          method: "POST",
          body: JSON.stringify({ phone: contactPhoneDraft }),
        },
        session.cta_mode === "webchat" ? { publicAccessToken: webchatToken } : undefined,
      );
      setSession((current) => {
        if (!current) return current;
        const nextSession = {
          ...current,
          contact_phone: response.contact_phone,
          contact_phone_required: response.contact_phone_required,
          patient_name: response.patient_name || null,
        };
        if (nextSession.cta_mode === "webchat") {
          storeWebchatSession(clinicSlug, nextSession);
        }
        return nextSession;
      });
      setContactPhoneDraft(response.contact_phone || contactPhoneDraft);
      if (session.cta_mode === "webchat") {
        notifyDemoWebchatParent({
          clinicSlug,
          sessionId: session.session_id,
          reason: "contact_captured",
        });
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
      data-public-webchat-page={isWebchat ? "true" : undefined}
      className={cn(
        "box-border overflow-hidden text-[var(--booking-text)]",
        isWebchat
          ? "h-[100dvh] bg-[#0b141a] p-0 sm:bg-[var(--booking-background)] sm:px-6 sm:py-5 lg:px-10"
          : "h-[100dvh] bg-[var(--booking-background)] px-4 py-4 sm:px-6 sm:py-5 lg:px-10",
      )}
      style={pageStyle}
    >
      <div
        data-public-webchat-page-shell={isWebchat ? "true" : undefined}
        className={cn(
          "box-border flex h-full w-full flex-col overflow-hidden",
          isWebchat
            ? "bg-[#0b141a] sm:mx-auto sm:max-w-7xl sm:rounded-[34px] sm:border sm:border-white/70 sm:bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.96),_rgba(242,247,245,0.94)_42%,_rgba(233,238,236,0.97))] sm:shadow-[0_28px_90px_rgba(15,23,42,0.12)] sm:backdrop-blur"
            : "mx-auto max-w-7xl rounded-[34px] border border-white/70 bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.96),_rgba(242,247,245,0.94)_42%,_rgba(233,238,236,0.97))] shadow-[0_28px_90px_rgba(15,23,42,0.12)] backdrop-blur",
        )}
      >
        <header data-public-webchat-page-header={isWebchat ? "true" : undefined} className={cn("border-b border-white/60 px-5 py-5 sm:px-7", isWebchat && "hidden sm:block")}>
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
        </header>

        <section
          data-public-webchat-section={isWebchat ? "true" : undefined}
          className={cn(
            "relative flex min-h-0 flex-1 overflow-hidden",
            isWebchat ? "p-0 sm:p-5 lg:grid lg:grid-cols-[360px_minmax(0,1fr)] lg:gap-4 lg:p-6" : "p-4 sm:p-5 lg:grid lg:grid-cols-[360px_minmax(0,1fr)] lg:gap-4 lg:p-6",
          )}
        >
          {isWebchat ? (
            <>
              <div
                className={cn(
                  "absolute inset-0 z-20 bg-stone-950/18 backdrop-blur-[1px] transition-opacity duration-300 lg:hidden",
                  mobileSummaryOpen ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0",
                )}
                aria-hidden="true"
                onClick={handleCloseSummaryPanel}
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
                    onClick={handleCloseSummaryPanel}
                    aria-label={sidePanelCloseLabel}
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
                  {useOverviewSidePanel ? (
                    <WhatsAppOverviewPanel className="h-full pt-14" />
                  ) : (
                    <BookingSummaryPanel
                      summary={summary}
                      loading={loadingSummary}
                      saving={savingSummary}
                      onSave={handleSaveSummary}
                      onConfirmBooking={handleConfirmSummaryBooking}
                      confirmingBooking={confirmingSummaryBooking}
                      className="h-full pt-14"
                    />
                  )}
                </div>
              </div>

              <button
                type="button"
                data-testid="booking-summary-mobile-handle"
                aria-label={sidePanelOpenLabel}
                className={cn(
                  "absolute left-0 top-1/2 z-30 -translate-y-1/2 touch-pan-y rounded-r-[14px] border border-white bg-white px-[2px] py-2 text-[var(--booking-primary)] shadow-[0_12px_28px_rgba(15,23,42,0.14)] lg:hidden",
                  mobileSummaryOpen ? "pointer-events-none opacity-0" : "opacity-100",
                )}
                onClick={() => setMobileSummaryOpen(true)}
                onPointerDown={(event) => handleMobileSummaryGestureStart(event, "open")}
                onPointerUp={handleMobileSummaryGestureEnd}
                onPointerCancel={handleMobileSummaryGestureCancel}
              >
                <ChevronRight className="h-3 w-3 shrink-0" aria-hidden="true" />
              </button>

              <div
                className="absolute inset-y-0 left-0 z-10 w-3 touch-pan-y lg:hidden"
                aria-hidden="true"
                onPointerDown={(event) => handleMobileSummaryGestureStart(event, "open")}
                onPointerUp={handleMobileSummaryGestureEnd}
                onPointerCancel={handleMobileSummaryGestureCancel}
              />
            </>
          ) : null}

          <div className="hidden min-h-0 lg:flex">
            {useOverviewSidePanel ? (
              <WhatsAppOverviewPanel className="h-full" />
            ) : (
              <BookingSummaryPanel
                summary={summary}
                loading={loadingSummary}
                saving={savingSummary}
                onSave={handleSaveSummary}
                onConfirmBooking={handleConfirmSummaryBooking}
                confirmingBooking={confirmingSummaryBooking}
                className="h-full"
              />
            )}
          </div>

          <div className="flex min-h-0 flex-1">
            {profile?.link_flow.operational && session && isWebchat ? (
              <PublicWebchat
                clinicSlug={clinicSlug}
                clinicName={clinicName}
                session={session}
                onOpenSummary={() => setMobileSummaryOpen(true)}
                contactPhone={profile?.clinic.contact_phone || session.clinic.contact_phone}
                contactWhatsAppUrl={profile?.clinic.contact_whatsapp_url || session.clinic.contact_whatsapp_url || session.whatsapp_url}
                patientName={session.patient_name}
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
            {showPublicBookingLoadingPanel ? (
              <div className="flex h-full min-h-0 w-full items-center justify-center rounded-[30px] border border-white/10 bg-[#111b21]/95 p-6 text-center shadow-[0_22px_70px_rgba(15,23,42,0.28)] backdrop-blur">
                <div className="max-w-md">
                  <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-white/10 bg-white shadow-sm">
                    <div className="h-5 w-5 animate-spin rounded-full border-2 border-[var(--booking-primary)] border-r-transparent" />
                  </div>
                  <p className="mt-4 text-lg font-semibold text-white">
                    {error ? "Reconectando atendimento..." : "Carregando atendimento..."}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-white/85">
                    {error
                      ? "A conexao oscilou, mas a demo continua tentando abrir o chat automaticamente."
                      : "Preparando a conversa oficial da clinica para voce e tentando novamente automaticamente ate conectar."}
                  </p>
                  {error ? (
                    <button
                      type="button"
                      onClick={() => window.location.reload()}
                      className="mt-4 inline-flex min-h-[44px] items-center justify-center rounded-full border border-white/15 bg-white px-5 text-sm font-semibold text-[#111b21] shadow-sm transition hover:bg-white/90"
                    >
                      Atualizar pagina
                    </button>
                  ) : null}
                </div>
              </div>
            ) : null}
            {publicBookingBlockingMessage ? (
              <div className="flex h-full min-h-0 w-full items-center justify-center rounded-[30px] border border-amber-200 bg-white/88 p-6 text-center shadow-[0_22px_70px_rgba(15,23,42,0.12)] backdrop-blur">
                <div className="max-w-md">
                  <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-amber-200 bg-amber-50 text-amber-700 shadow-sm">
                    <Info size={20} />
                  </div>
                  <p className="mt-4 text-lg font-semibold text-stone-900">Chat do site indisponível agora</p>
                  <p className="mt-2 text-sm leading-6 text-[var(--booking-muted)]">{publicBookingBlockingMessage}</p>
                </div>
              </div>
            ) : null}
          </div>

          {shouldBlockForPhone ? (
            <PublicPhoneGate
              clinicName={clinicName}
              demoMode={isDemoEmbeddedWebchat}
              phone={contactPhoneDraft}
              saving={savingContactPhone}
              error={contactPhoneError}
              onPhoneChange={(value) => setContactPhoneDraft(normalizePhoneDraft(value))}
              onSubmit={handleCaptureContactPhone}
            />
          ) : null}
          {bookingCompletedModal ? (
            <div className="absolute inset-0 z-40 flex items-center justify-center bg-[#0b141a]/72 p-4 backdrop-blur-sm">
              <div className="w-full max-w-md rounded-[28px] border border-white/70 bg-white p-6 shadow-[0_30px_80px_rgba(15,23,42,0.28)]">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-emerald-700">Agendamento concluido</p>
                    <h2 className="mt-2 text-2xl font-semibold text-stone-950">Seu horario foi confirmado.</h2>
                  </div>
                  <button
                    type="button"
                    onClick={() => setBookingCompletedModal(null)}
                    className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-stone-200 text-stone-500 transition hover:text-stone-800"
                    aria-label="Fechar confirmacao"
                  >
                    <X className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
                <div className="mt-5 space-y-2 rounded-[22px] border border-emerald-100 bg-emerald-50/80 p-4 text-sm text-stone-800">
                  <p><span className="font-semibold">Paciente:</span> {bookingCompletedModal.patient_name || "Paciente"}</p>
                  <p><span className="font-semibold">Servico:</span> {bookingCompletedModal.procedure_type || "Agendamento confirmado"}</p>
                  <p><span className="font-semibold">Horario:</span> {formatPublicDateTime(bookingCompletedModal.starts_at)}</p>
                  <p><span className="font-semibold">Unidade:</span> {bookingCompletedModal.unit_name || clinicName}</p>
                  {bookingCompletedModal.unit_address ? (
                    <p><span className="font-semibold">Localizacao:</span> {bookingCompletedModal.unit_address}</p>
                  ) : null}
                  {bookingCompletedModal.patient_email ? (
                    <p><span className="font-semibold">E-mail:</span> {bookingCompletedModal.patient_email}</p>
                  ) : null}
                </div>
                <p className="mt-4 text-sm leading-6 text-[var(--booking-muted)]">
                  Guarde essas informacoes para comparecer no horario combinado. Se precisar de ajuda, fale com a clinica pelo canal oficial.
                </p>
                {profile?.clinic.contact_phone ? (
                  <p className="mt-2 text-sm leading-6 text-[var(--booking-muted)]">
                    Contato da clinica: {profile.clinic.contact_phone}
                  </p>
                ) : null}
                <button
                  type="button"
                  onClick={() => setBookingCompletedModal(null)}
                  className="mt-5 inline-flex w-full items-center justify-center rounded-2xl bg-[var(--booking-primary)] px-4 py-3 text-sm font-semibold text-white"
                >
                  Entendi
                </button>
              </div>
            </div>
          ) : null}
        </section>

      </div>
    </main>
  );
}

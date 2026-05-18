"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, FormEvent } from "react";
import { ArrowRight, CalendarCheck2, CheckCircle2, MessageCircle, SendHorizontal, ShieldCheck } from "lucide-react";
import Image from "next/image";
import { useParams } from "next/navigation";

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
  clinic: {
    slug: string;
    name: string;
  };
};

type PublicWebchatMessage = {
  id: string;
  role: "patient" | "assistant";
  text: string;
  created_at: string | null;
  status: string;
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

function PublicWebchat({
  clinicSlug,
  clinicName,
  session,
  onExpired,
}: {
  clinicSlug: string;
  clinicName: string;
  session: PublicBookingSession;
  onExpired: () => void;
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
      if (/expir/i.test(message) || /sess/i.test(message)) {
        onExpired();
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
      if (/expir/i.test(message) || /sess/i.test(message)) {
        onExpired();
      }
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex min-h-[560px] flex-1 flex-col overflow-hidden rounded-[30px] border border-white/60 bg-white/82 shadow-[0_22px_70px_rgba(15,23,42,0.12)] backdrop-blur">
      <div className="flex items-center justify-between gap-3 border-b border-stone-200 bg-white/92 px-4 py-3 sm:px-5">
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
      </div>

      <div className="border-b border-stone-200 bg-[linear-gradient(180deg,rgba(255,255,255,0.95),rgba(247,250,249,0.92))] px-4 py-3 sm:px-5">
        <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--booking-muted)]">
          <span className="rounded-full border border-stone-200 bg-white px-3 py-1 font-medium">Assistente de agendamento</span>
          <span className="rounded-full border border-stone-200 bg-white px-3 py-1 font-medium">Resposta automatica segura</span>
          <span className="rounded-full border border-stone-200 bg-white px-3 py-1 font-medium">Sem abrir o WhatsApp</span>
        </div>
      </div>

      <div
        ref={viewportRef}
        className="min-h-0 flex-1 space-y-4 overflow-y-auto bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.96),_rgba(242,247,245,0.92)_42%,_rgba(237,241,239,0.95))] px-4 py-5 sm:px-5"
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

      <div className="border-t border-stone-200 bg-white/94 px-4 py-3 sm:px-5">
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
    <div className="flex min-h-[560px] flex-1 flex-col overflow-hidden rounded-[30px] border border-white/60 bg-white/82 shadow-[0_22px_70px_rgba(15,23,42,0.12)] backdrop-blur">
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

export default function PublicBookingPage() {
  const params = useParams<{ clinicSlug: string }>();
  const clinicSlug = String(params.clinicSlug || "").trim();
  const bootstrappedRef = useRef(false);

  const [profile, setProfile] = useState<PublicBookingProfile | null>(null);
  const [session, setSession] = useState<PublicBookingSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
              await publicApiFetch(
                `/public/booking/sessions/${storedSession.session_id}`,
                undefined,
                { publicAccessToken: storedSession.public_access_token },
              );
              bookingSession = storedSession;
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
  const linkFlowUnavailable =
    profile && (!profile.link_flow.enabled || !profile.link_flow.operational)
      ? profile.link_flow.unavailable_message ||
        "Agendamento por link indisponivel no momento. Entre em contato com a clinica pelo canal oficial."
      : null;

  return (
    <main
      className="min-h-screen bg-[var(--booking-background)] px-4 py-5 text-[var(--booking-text)] sm:px-6 sm:py-6 lg:px-10"
      style={pageStyle}
    >
      <div className="mx-auto flex min-h-[calc(100vh-2.5rem)] w-full max-w-7xl flex-col overflow-hidden rounded-[34px] border border-white/70 bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.96),_rgba(242,247,245,0.94)_42%,_rgba(233,238,236,0.97))] shadow-[0_28px_90px_rgba(15,23,42,0.12)] backdrop-blur">
        <header className="border-b border-white/60 px-5 py-5 sm:px-7">
          <div className="flex flex-wrap items-center justify-between gap-4">
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
            <div className="rounded-full border border-stone-200 bg-white/80 px-4 py-2 text-sm font-medium text-[var(--booking-muted)] shadow-sm">
              Link verificado da clinica
            </div>
          </div>
        </header>

        <section className="grid min-h-0 flex-1 gap-4 p-4 sm:p-5 lg:grid-cols-[360px_minmax(0,1fr)] lg:p-6">
          <aside className="flex flex-col justify-between rounded-[30px] border border-white/70 bg-white/84 p-5 shadow-[0_18px_48px_rgba(15,23,42,0.08)] backdrop-blur sm:p-6">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-[var(--booking-border)] bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-[var(--booking-muted)]">
                <ShieldCheck className="h-4 w-4 text-[var(--booking-primary)]" aria-hidden="true" />
                Canal protegido
              </div>
              <h2 className="mt-5 text-3xl font-semibold leading-tight text-stone-950 sm:text-[2rem]">
                {profile?.link_flow.headline || "Agendamento oficial da clinica"}
              </h2>
              <p className="mt-4 text-base leading-7 text-[var(--booking-muted)]">
                {profile?.link_flow.trust_message ||
                  "Continue pelo canal oficial para falar com a assistente de agendamento."}
              </p>

              <div className="mt-6 space-y-3">
                {[
                  isWebchat
                    ? "Converse com a assistente aqui na propria pagina, no mesmo padrao visual do inbox da clinica."
                    : "Entre pelo WhatsApp oficial e continue no mesmo fluxo operacional usado pela clinica.",
                  "A jornada fica vinculada ao tenant correto e protegida por sessao segura.",
                  "Depois da triagem, a assistente segue para disponibilidade e confirmacao do agendamento.",
                ].map((item) => (
                  <div key={item} className="flex gap-3">
                    <CheckCircle2 className="mt-0.5 h-5 w-5 flex-none text-[var(--booking-primary)]" aria-hidden="true" />
                    <p className="text-sm leading-6 text-[var(--booking-muted)]">{item}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-8 rounded-[24px] border border-stone-200 bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(248,250,249,0.92))] p-4 shadow-sm">
              <p className="text-sm font-semibold text-stone-900">Sessao segura</p>
              <p className="mt-2 text-sm leading-6 text-[var(--booking-muted)]">
                {loading
                  ? "Preparando seu atendimento..."
                  : session
                    ? isWebchat
                      ? "Seu chat oficial esta pronto para receber mensagens da assistente."
                      : "Seu link oficial esta pronto para abrir o WhatsApp da operacao."
                    : linkFlowUnavailable || "Nao foi possivel preparar a sessao agora."}
              </p>
            </div>
          </aside>

          <div className="flex min-h-[560px]">
            {profile?.link_flow.operational && session && isWebchat ? (
              <PublicWebchat
                clinicSlug={clinicSlug}
                clinicName={clinicName}
                session={session}
                onExpired={() => {
                  storeWebchatSession(clinicSlug, null);
                  setSession(null);
                  setError("Sua sessao expirou. Recarregue a pagina para iniciar um novo atendimento.");
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
              <div className="flex min-h-[560px] w-full items-center justify-center rounded-[30px] border border-white/60 bg-white/82 p-6 text-center shadow-[0_22px_70px_rgba(15,23,42,0.12)] backdrop-blur">
                <div className="max-w-md">
                  <p className="text-lg font-semibold text-stone-900">Nao foi possivel iniciar o atendimento agora.</p>
                  <p className="mt-2 text-sm leading-6 text-[var(--booking-muted)]">
                    {linkFlowUnavailable || error || "Tente novamente em instantes."}
                  </p>
                </div>
              </div>
            ) : null}
          </div>
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

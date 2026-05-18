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
  session,
  onExpired,
}: {
  clinicSlug: string;
  session: PublicBookingSession;
  onExpired: () => void;
}) {
  const [messages, setMessages] = useState<PublicWebchatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(true);
  const [chatError, setChatError] = useState<string | null>(null);
  const openedRef = useRef(false);
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
    <div className="mt-8 rounded-2xl border border-[var(--booking-border)] bg-white/90 p-3 shadow-sm backdrop-blur">
      <div className="flex items-center gap-2 border-b border-[var(--booking-border)] px-2 pb-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--booking-primary)] text-white">
          <MessageCircle className="h-5 w-5" aria-hidden="true" />
        </span>
        <div>
          <p className="text-sm font-semibold">Atendimento online</p>
          <p className="text-xs text-[var(--booking-muted)]">A assistente responde por aqui, sem abrir o WhatsApp.</p>
        </div>
      </div>

      <div className="mt-3 max-h-[360px] min-h-[260px] space-y-3 overflow-y-auto rounded-xl bg-stone-50/80 p-3">
        {loadingMessages ? (
          <p className="text-sm text-[var(--booking-muted)]">Carregando conversa...</p>
        ) : null}
        {!loadingMessages && messages.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[var(--booking-border)] bg-white p-4 text-sm leading-6 text-[var(--booking-muted)]">
            Envie uma mensagem para comecar. Exemplo: Quero agendar uma avaliacao.
          </div>
        ) : null}
        {messages.map((message) => {
          const isPatient = message.role === "patient";
          return (
            <div key={message.id} className={`flex ${isPatient ? "justify-end" : "justify-start"}`}>
              <div
                className={[
                  "max-w-[82%] rounded-2xl px-4 py-2 text-sm leading-6 shadow-sm",
                  isPatient
                    ? "bg-[var(--booking-primary)] text-white"
                    : "border border-[var(--booking-border)] bg-white text-[var(--booking-text)]",
                ].join(" ")}
              >
                {message.text}
              </div>
            </div>
          );
        })}
        {sending ? <p className="text-xs text-[var(--booking-muted)]">Enviando e aguardando resposta...</p> : null}
      </div>

      {chatError ? (
        <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          {chatError}
        </p>
      ) : null}

      <form onSubmit={handleSendMessage} className="mt-3 flex gap-2">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          maxLength={1200}
          placeholder="Digite sua mensagem..."
          className="min-h-12 flex-1 rounded-xl border border-[var(--booking-border)] bg-white px-4 text-sm outline-none transition focus:border-[var(--booking-primary)]"
        />
        <button
          type="submit"
          disabled={!draft.trim() || sending}
          className="inline-flex min-h-12 items-center justify-center rounded-xl bg-[var(--booking-primary)] px-4 text-white transition hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-60"
          aria-label="Enviar mensagem"
        >
          <SendHorizontal className="h-5 w-5" aria-hidden="true" />
        </button>
      </form>
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
      className="min-h-screen px-5 py-8 text-[var(--booking-text)] sm:px-8 lg:px-12"
      style={pageStyle}
    >
      <div className="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-5xl flex-col justify-center gap-8">
        <header className="flex items-center gap-3">
          <div className="flex h-14 w-14 items-center justify-center overflow-hidden rounded-md border border-[var(--booking-border)] bg-[var(--booking-card)] shadow-sm">
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
          <div>
            <p className="text-sm font-medium text-[var(--booking-muted)]">Agendamento oficial</p>
            <h1 className="text-2xl font-semibold leading-tight sm:text-3xl">{clinicName}</h1>
          </div>
        </header>

        <section className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr] lg:items-stretch">
          <div className="flex flex-col justify-center rounded-md border border-[var(--booking-border)] bg-[var(--booking-card)] p-6 shadow-sm sm:p-8">
            <div className="mb-5 inline-flex w-fit items-center gap-2 rounded-full border border-[var(--booking-border)] px-3 py-1 text-sm text-[var(--booking-muted)]">
              <ShieldCheck className="h-4 w-4 text-[var(--booking-primary)]" aria-hidden="true" />
              Link verificado da clinica
            </div>
            <h2 className="max-w-2xl text-3xl font-semibold leading-tight sm:text-4xl">
              {profile?.link_flow.headline || "Agendamento oficial da clinica"}
            </h2>
            <p className="mt-4 max-w-2xl text-base leading-7 text-[var(--booking-muted)] sm:text-lg">
              {profile?.link_flow.trust_message ||
                "Continue pelo canal oficial para falar com a assistente de agendamento."}
            </p>
            {profile?.link_flow.operational && session && !isWebchat ? (
              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <button
                  type="button"
                  onClick={handleOpenWhatsApp}
                  disabled={!session || loading || opening}
                  className="inline-flex min-h-12 items-center justify-center gap-2 rounded-md bg-[var(--booking-primary)] px-5 py-3 text-base font-semibold text-white shadow-sm transition hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {opening ? "Abrindo WhatsApp..." : profile?.link_flow.button_label || "Continuar pelo WhatsApp"}
                  <ArrowRight className="h-5 w-5" aria-hidden="true" />
                </button>
              </div>
            ) : null}
            {profile?.link_flow.operational && session && isWebchat ? (
              <PublicWebchat
                clinicSlug={clinicSlug}
                session={session}
                onExpired={() => {
                  storeWebchatSession(clinicSlug, null);
                  setSession(null);
                  setError("Sua sessao expirou. Recarregue a pagina para iniciar um novo atendimento.");
                }}
              />
            ) : null}
            {linkFlowUnavailable ? (
              <p className="mt-5 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                {linkFlowUnavailable}
              </p>
            ) : null}
            {error ? (
              <p className="mt-5 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
            ) : null}
          </div>

          <aside className="rounded-md border border-[var(--booking-border)] bg-white/72 p-6 shadow-sm backdrop-blur">
            <div className="flex h-full flex-col justify-between gap-8">
              <div>
                <p className="text-sm font-semibold uppercase tracking-wide text-[var(--booking-primary)]">
                  Como funciona
                </p>
                <div className="mt-5 space-y-4">
                  {[
                    isWebchat
                      ? "Voce conversa com a assistente diretamente nesta pagina."
                      : "Voce abre uma conversa com o WhatsApp oficial do sistema.",
                    isWebchat
                      ? "A sessao publica valida a clinica sem expor dados internos."
                      : "A assistente identifica automaticamente esta clinica.",
                    "O atendimento segue para disponibilidade e confirmacao.",
                  ].map((item) => (
                    <div key={item} className="flex gap-3">
                      <CheckCircle2 className="mt-0.5 h-5 w-5 flex-none text-[var(--booking-primary)]" aria-hidden="true" />
                      <p className="text-sm leading-6 text-[var(--booking-muted)]">{item}</p>
                    </div>
                  ))}
                </div>
              </div>
              <div className="rounded-md border border-[var(--booking-border)] bg-[var(--booking-card)] p-4">
                <p className="text-sm font-medium">Sessao segura</p>
                <p className="mt-1 text-sm leading-6 text-[var(--booking-muted)]">
                  {loading
                    ? "Preparando seu atendimento..."
                    : session
                      ? isWebchat
                        ? "Seu chat seguro esta pronto para continuar."
                        : "Seu link de atendimento esta pronto para continuar."
                      : linkFlowUnavailable || "Nao foi possivel preparar a sessao agora."}
                </p>
              </div>
            </div>
          </aside>
        </section>
      </div>
    </main>
  );
}

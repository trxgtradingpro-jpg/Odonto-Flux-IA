"use client";

import { CSSProperties, FormEvent, useEffect, useLayoutEffect, useRef, useState } from "react";
import { MessageCircle, Send, X } from "lucide-react";
import { usePathname } from "next/navigation";

import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@odontoflux/ui";

import { api } from "@/lib/api";
import { BRAND_NAME, BRAND_SUPPORT_LABEL } from "@/lib/brand";

type SupportMessage = {
  id: string;
  role: "assistant" | "user";
  content: string;
  meta?: {
    mode?: string;
    confidence?: number;
    knowledgeVersion?: string;
    sources?: Array<{ id: string; title: string }>;
  };
};

type SupportAIAnswer = {
  answer: string;
  confidence?: number;
  mode?: string;
  knowledge_version?: string;
  sources?: Array<{ id: string; title: string }>;
};

export function SupportFab() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [fabOffset, setFabOffset] = useState(0);
  const messagesRef = useRef<HTMLDivElement | null>(null);
  const fabRef = useRef<HTMLButtonElement | null>(null);
  const [messages, setMessages] = useState<SupportMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        `Oi. Sou o suporte IA da ${BRAND_NAME}. Tenho contexto do sistema, configuracoes da clinica e base tecnica versionada para responder duvidas operacionais com precisao. Se algo nao estiver documentado, eu aviso em vez de inventar.`,
    },
  ]);

  useEffect(() => {
    if (!open) return;
    messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading, open]);

  const isConversationPage = pathname === "/conversas";
  const cardPositionClass = isConversationPage ? "right-3 sm:right-4 md:right-6" : "right-3 sm:right-4 md:right-6";
  const fabPositionClass = isConversationPage ? "right-3 sm:right-4 md:right-6" : "right-3 sm:right-4 md:right-6";
  const baseFabBottom = isConversationPage ? 28 : 12;
  const baseCardBottom = isConversationPage ? 44 : 32;

  useLayoutEffect(() => {
    const button = fabRef.current;
    if (!button) return;

    const syncOffset = () => {
      const height = button.getBoundingClientRect().height;
      setFabOffset(height * 2);
    };

    syncOffset();

    const observer = new ResizeObserver(syncOffset);
    observer.observe(button);
    window.addEventListener("resize", syncOffset);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", syncOffset);
    };
  }, [pathname]);

  const fabStyle: CSSProperties = {
    bottom: `${baseFabBottom + fabOffset}px`,
  };

  const cardStyle: CSSProperties = {
    bottom: `${baseCardBottom + fabOffset}px`,
  };

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const value = text.trim();
    if (!value || loading) return;

    const userMessage: SupportMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: value,
    };
    const nextMessages = [...messages, userMessage];
    setMessages(nextMessages);
    setText("");
    setLoading(true);

    try {
      const response = await api.post<SupportAIAnswer>("/support/ai-answer", {
        question: value,
        history: nextMessages.slice(-10).map((message) => ({
          role: message.role,
          content: message.content,
        })),
      });
      const data = response.data;
      setMessages((current) => [
        ...current,
        {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: data.answer,
          meta: {
            mode: data.mode,
            confidence: data.confidence,
            knowledgeVersion: data.knowledge_version,
            sources: data.sources ?? [],
          },
        },
      ]);
    } catch {
      setMessages((current) => [
        ...current,
        {
          id: `assistant-error-${Date.now()}`,
          role: "assistant",
          content:
            "Nao consegui consultar a base de suporte IA agora. Tente novamente em alguns segundos ou abra a Central de Suporte para registrar um incidente com print e descricao do modulo.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      {open ? (
        <Card
          className={`fixed z-[80] w-[min(94vw,390px)] overflow-hidden border-emerald-300 shadow-2xl ${cardPositionClass}`}
          style={cardStyle}
        >
          <CardHeader className="space-y-2 bg-emerald-500 pb-3 text-white">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base text-white">{BRAND_SUPPORT_LABEL}</CardTitle>
              <button
                type="button"
                className="rounded-md p-1 text-white/90 transition hover:bg-white/20"
                onClick={() => setOpen(false)}
                aria-label="Fechar suporte"
              >
                <X size={16} />
              </button>
            </div>
            <p className="text-xs text-emerald-50">
              Respostas sobre o sistema, WhatsApp, agenda, IA, configuracoes e implantacoes.
            </p>
          </CardHeader>
          <CardContent className="space-y-3 p-3">
            <div
              ref={messagesRef}
              className="max-h-[360px] space-y-2 overflow-y-auto rounded-md border border-stone-200 bg-stone-50 p-2"
            >
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`rounded-md px-3 py-2 text-sm ${
                    message.role === "assistant"
                      ? "border border-emerald-200 bg-white text-stone-700"
                      : "ml-8 bg-emerald-500 text-white"
                  }`}
                >
                  <p className="whitespace-pre-wrap">{message.content}</p>
                  {message.role === "assistant" && message.meta?.sources?.length ? (
                    <div className="mt-2 rounded-md bg-emerald-50 px-2 py-1 text-[11px] text-emerald-900">
                      <p className="font-semibold">
                        Base: {message.meta.knowledgeVersion ?? "atual"} -{" "}
                        {message.meta.mode === "llm" ? "IA conectada" : "fallback seguro"}
                      </p>
                      <p className="mt-0.5">
                        Fontes: {message.meta.sources.map((source) => source.title).join(", ")}
                      </p>
                    </div>
                  ) : null}
                </div>
              ))}
              {loading ? (
                <div className="rounded-md border border-emerald-200 bg-white px-3 py-2 text-sm text-stone-700">
                  Consultando base atualizada da {BRAND_NAME}...
                </div>
              ) : null}
            </div>
            <form className="flex items-center gap-2" onSubmit={onSubmit}>
              <Input
                placeholder="Digite sua duvida sobre o sistema..."
                value={text}
                onChange={(event) => setText(event.target.value)}
                disabled={loading}
              />
              <Button
                type="submit"
                className="h-10 w-10 rounded-full bg-emerald-500 px-0 text-white hover:bg-emerald-600"
                aria-label="Enviar pergunta"
                disabled={loading || !text.trim()}
              >
                <Send size={16} />
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : null}

      <button
        ref={fabRef}
        data-app-shell-support-fab="true"
        type="button"
        onClick={() => setOpen((current) => !current)}
        className={`fixed z-[70] inline-flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500 text-white shadow-2xl transition hover:scale-105 hover:bg-emerald-600 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-emerald-300 sm:h-14 sm:w-14 ${fabPositionClass}`}
        style={fabStyle}
        aria-label="Abrir suporte IA"
      >
        <MessageCircle size={22} />
      </button>
    </>
  );
}

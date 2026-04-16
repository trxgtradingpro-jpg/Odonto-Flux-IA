"use client";

import { FormEvent, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { MessageCircle, Send, X } from "lucide-react";

import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@odontoflux/ui";

import { api } from "@/lib/api";
import { useLiveNotifications } from "@/hooks/use-live-notifications";
import { useSession } from "@/hooks/use-session";

type SupportMessage = {
  id: string;
  role: "assistant" | "user";
  content: string;
};

type AIKnowledgeBaseSettings = {
  global?: {
    clinic_profile?: {
      clinic_name?: string;
      about?: string;
      differentials?: string[];
    };
    services?: Array<{ name?: string; description?: string }>;
    operational_policies?: {
      booking_rules?: string;
      cancellation_policy?: string;
      reschedule_policy?: string;
      payment_policy?: string;
      documents_required?: string;
    };
    faq?: Array<{ question?: string; answer?: string }>;
  };
};

function normalizedText(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

export function SupportFab() {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [messages, setMessages] = useState<SupportMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Oi. Sou o suporte IA do OdontoFlux. Posso te ajudar com agenda, WhatsApp, IA, automacoes, tema e configuracoes.",
    },
  ]);

  const sessionQuery = useSession();
  const notificationsQuery = useLiveNotifications();
  const knowledgeQuery = useQuery<AIKnowledgeBaseSettings>({
    queryKey: ["support-knowledge"],
    queryFn: async () => (await api.get("/settings/ai-knowledge-base/config")).data,
    staleTime: 60_000,
  });

  const servicesSummary = useMemo(() => {
    const services = knowledgeQuery.data?.global?.services ?? [];
    return services
      .map((item) => item.name?.trim())
      .filter(Boolean)
      .slice(0, 6) as string[];
  }, [knowledgeQuery.data?.global?.services]);

  function buildReply(question: string): string {
    const q = normalizedText(question);
    const tenantName = sessionQuery.data?.tenant_name ?? "sua clinica";
    const badges = notificationsQuery.data?.badges;
    const operationalPolicies = knowledgeQuery.data?.global?.operational_policies;
    const faq = knowledgeQuery.data?.global?.faq ?? [];

    const faqMatch = faq.find((item) => {
      const source = normalizedText(`${item.question ?? ""} ${item.answer ?? ""}`);
      return source && q && (source.includes(q) || q.includes(normalizedText(item.question ?? "")));
    });
    if (faqMatch?.answer) return faqMatch.answer;

    if (q.includes("agenda") || q.includes("agendamento") || q.includes("horario")) {
      const today = badges?.appointmentsToday ?? 0;
      const pending = badges?.pendingConfirmations ?? 0;
      return `Agenda ao vivo: ${today} consultas hoje e ${pending} pendentes de confirmacao. Abra Agenda para ver grade semanal, filtros por profissional, cores e tela cheia.`;
    }

    if (q.includes("whatsapp") || q.includes("infobip") || q.includes("meta") || q.includes("twilio")) {
      return "Para WhatsApp: Configuracoes > WhatsApp. Cadastre conta, teste conexao, confirme webhook e mantenha o worker ativo para processamento automatico.";
    }

    if (q.includes("ia") || q.includes("autoresponder") || q.includes("auto responder")) {
      return "Para IA: Configuracoes > IA Auto-Responder e Conhecimento IA. Ative no tenant/canal, ajuste horario, limite de respostas e base de conhecimento oficial.";
    }

    if (q.includes("tema") || q.includes("logo") || q.includes("cor")) {
      return "Tema e marca: Configuracoes > Tema e Marca. Voce pode mudar cores principais, estilo da interface e subir logo da clinica.";
    }

    if (q.includes("servico") || q.includes("tratamento")) {
      if (servicesSummary.length) {
        return `Servicos cadastrados hoje em ${tenantName}: ${servicesSummary.join(", ")}.`;
      }
      return "Nao encontrei servicos cadastrados na base da IA. Preencha Configuracoes > Conhecimento IA para melhorar respostas.";
    }

    if (q.includes("cancel") || q.includes("remarc")) {
      return (
        operationalPolicies?.cancellation_policy ||
        operationalPolicies?.reschedule_policy ||
        "Configure politicas de cancelamento/remarcacao em Configuracoes > Conhecimento IA."
      );
    }

    if (q.includes("pagamento") || q.includes("parcel")) {
      return operationalPolicies?.payment_policy || "Defina politica de pagamento em Configuracoes > Conhecimento IA.";
    }

    if (q.includes("documento")) {
      return (
        operationalPolicies?.documents_required ||
        "Defina documentos obrigatorios em Configuracoes > Conhecimento IA."
      );
    }

    if (q.includes("menu") || q.includes("notificacao")) {
      const conversations = badges?.conversations ?? 0;
      const leads = badges?.leads ?? 0;
      return `Menu com atualizacao automatica: ${conversations} conversas abertas e ${leads} leads ativos agora.`;
    }

    return "Posso te guiar por modulo. Tente: agenda, WhatsApp, IA, tema/logo, notificacoes, politicas de agendamento.";
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const value = text.trim();
    if (!value) return;

    const userMessage: SupportMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: value,
    };
    const assistantMessage: SupportMessage = {
      id: `assistant-${Date.now()}`,
      role: "assistant",
      content: buildReply(value),
    };
    setMessages((current) => [...current, userMessage, assistantMessage]);
    setText("");
  }

  return (
    <>
      {open ? (
        <Card className="fixed bottom-24 right-3 z-[80] w-[min(94vw,360px)] border-emerald-300 shadow-2xl sm:bottom-24 sm:right-4 md:right-6">
          <CardHeader className="space-y-2 bg-emerald-500 pb-3 text-white">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base text-white">Suporte IA</CardTitle>
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
              Respostas automaticas para duvidas operacionais do sistema.
            </p>
          </CardHeader>
          <CardContent className="space-y-3 p-3">
            <div className="max-h-[340px] space-y-2 overflow-y-auto rounded-md border border-stone-200 bg-stone-50 p-2">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`rounded-md px-3 py-2 text-sm ${
                    message.role === "assistant"
                      ? "border border-emerald-200 bg-white text-stone-700"
                      : "ml-8 bg-emerald-500 text-white"
                  }`}
                >
                  {message.content}
                </div>
              ))}
            </div>
            <form className="flex items-center gap-2" onSubmit={onSubmit}>
              <Input
                placeholder="Digite sua duvida..."
                value={text}
                onChange={(event) => setText(event.target.value)}
              />
              <Button
                type="submit"
                className="h-10 w-10 rounded-full bg-emerald-500 px-0 text-white hover:bg-emerald-600"
                aria-label="Enviar pergunta"
              >
                <Send size={16} />
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : null}

      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="fixed bottom-4 right-3 z-[70] inline-flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500 text-white shadow-2xl transition hover:scale-105 hover:bg-emerald-600 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-emerald-300 sm:bottom-5 sm:right-4 sm:h-14 sm:w-14 md:right-6"
        aria-label="Abrir suporte IA"
      >
        <MessageCircle size={22} />
      </button>
    </>
  );
}

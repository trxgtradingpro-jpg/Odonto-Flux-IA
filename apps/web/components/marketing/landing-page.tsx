import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  BadgeCheck,
  Building2,
  CalendarDays,
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  Handshake,
  LayoutDashboard,
  Mail,
  MessageSquareText,
  PhoneCall,
  PlayCircle,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Users2,
  Workflow,
} from "lucide-react";

import { cn } from "@odontoflux/ui";
import { BRAND_DESCRIPTION, BRAND_MONOGRAM, BRAND_NAME, BRAND_SALES_TEAM, BRAND_TAGLINE } from "@/lib/brand";

const PAIN_POINTS = [
  "WhatsApp da clinica vira uma fila invisivel, sem dono e sem processo.",
  "Agenda, confirmacao, comparecimento e retorno ficam desconectados.",
  "Leads entram, mas a recepcao nao consegue acompanhar tudo com consistencia.",
  "O dono sente que a operacao cresce mais devagar do que o potencial da clinica.",
];

const VALUE_PILLARS = [
  {
    title: "Atendimento 24h com IA",
    description: "Responda pacientes a qualquer hora com contexto, consistencia e uma experiencia premium no WhatsApp.",
    icon: MessageSquareText,
  },
  {
    title: "Qualificacao automatica",
    description: "A IA entende interesse, filtra intencao e prepara a equipe para agir com mais velocidade e conversao.",
    icon: CalendarDays,
  },
  {
    title: "Agendamento inteligente",
    description: "Organize disponibilidade, confirmacoes, comparecimento e retorno em um fluxo operacional unico.",
    icon: Users2,
  },
  {
    title: "Recuperacao de oportunidades",
    description: "Reative pacientes e leads esquecidos sem depender de planilhas, memoria ou mensagens soltas.",
    icon: LayoutDashboard,
  },
];

const RESULTS = [
  {
    metric: "Mais conversoes pelo WhatsApp",
    text: "A clinica ganha processo para responder, qualificar e levar mais pacientes ate a consulta.",
  },
  {
    metric: "Menos mensagens perdidas",
    text: "A equipe deixa de operar no improviso e passa a enxergar o que precisa de resposta, confirmacao e retorno.",
  },
  {
    metric: "Controle em tempo real",
    text: "Gestores acompanham agenda, atendimento e recuperacao de oportunidades em um painel unico.",
  },
];

const JOURNEY = [
  {
    step: "01",
    title: "Lead entra pelo WhatsApp",
    description: "A conversa deixa de ser uma mensagem solta e vira parte do fluxo comercial da clinica.",
  },
  {
    step: "02",
    title: "A IA qualifica e direciona",
    description: "A conversa recebe contexto, triagem e encaminhamento sem perder o tom humano do atendimento.",
  },
  {
    step: "03",
    title: "Agenda, confirma e acompanha",
    description: "O paciente sai do contato inicial para o agendamento com menos ruido entre equipe, servico e profissional.",
  },
  {
    step: "04",
    title: "Recupera e reativa oportunidades",
    description: "O sistema sinaliza faltas, retornos e leads antigos para a clinica vender melhor sem perder timing.",
  },
];

const OFFER_BLOCKS = [
  {
    title: "Piloto Assistido",
    price: "A partir de R$ 997/mes",
    detail: "Implantacao a partir de R$ 2.500",
    highlight: true,
    bullets: [
      "Configuracao inicial da clinica",
      "Cadastro de servicos, equipe e unidades",
      "Treinamento assistido da operacao",
      "Acompanhamento proximo nas primeiras semanas",
    ],
  },
  {
    title: "Growth",
    price: "A partir de R$ 1.790/mes",
    detail: "Implantacao a partir de R$ 4.900",
    highlight: false,
    bullets: [
      "Tudo do Piloto Assistido",
      "Mais apoio para crescimento operacional",
      "Prioridade para ajustes de implantacao",
      "Melhor fit para clinicas com mais volume",
    ],
  },
  {
    title: "Rede ou Multiunidade",
    price: "Sob consulta",
    detail: "Escopo sob medida",
    highlight: false,
    bullets: [
      "Governanca multiunidade",
      "Padronizacao operacional entre equipes",
      "Estrutura consultiva de implantacao",
      "Projeto em fases conforme maturidade",
    ],
  },
];

const FAQS = [
  {
    question: "A ClinicFlux AI deve ser posicionada como software barato de prateleira?",
    answer:
      "Nao. O melhor posicionamento hoje e SaaS premium com implantacao consultiva, porque isso protege a promessa, acelera ativacao e aumenta taxa de fechamento.",
  },
  {
    question: "O que muda para a clinica na pratica?",
    answer:
      "Muda a organizacao da recepcao, o controle das conversas, a disciplina da agenda e a capacidade de acompanhar o paciente do primeiro contato ate o retorno.",
  },
  {
    question: "Por que apresentar como central operacional?",
    answer:
      "Porque o valor nao esta em uma tela isolada. O valor esta em conectar atendimento, agenda, equipe, comparecimento e conversao em um unico fluxo.",
  },
  {
    question: "Quanto tempo leva um piloto assistido?",
    answer:
      "O formato recomendado e um ciclo inicial de 30 dias, com preparacao, implantacao guiada, acompanhamento do uso e revisao comercial no fechamento do piloto.",
  },
  {
    question: "O que a clinica precisa ter para comecar?",
    answer:
      "Uma unidade piloto definida, time responsavel pela recepcao, servicos e profissionais principais cadastrados e disponibilidade para uma demonstracao guiada e treinamento inicial.",
  },
];

const SALES_CONTACT_NAME = process.env.NEXT_PUBLIC_ODONTOFLUX_SALES_CONTACT_NAME?.trim() || BRAND_SALES_TEAM;
const SALES_CONTACT_ROLE =
  process.env.NEXT_PUBLIC_ODONTOFLUX_SALES_ROLE?.trim() || "Especialista em automacao, agenda e conversao para clinicas";
const SALES_CONTACT_REGION =
  process.env.NEXT_PUBLIC_ODONTOFLUX_SALES_REGION?.trim() || "Atendimento consultivo para clinicas em todo o Brasil";
const SALES_WHATSAPP_URL = process.env.NEXT_PUBLIC_ODONTOFLUX_SALES_WHATSAPP_URL?.trim() || "#contato";
const SALES_DEMO_URL = process.env.NEXT_PUBLIC_ODONTOFLUX_SALES_DEMO_URL?.trim() || "#agendar-demo";
const SALES_EMAIL = process.env.NEXT_PUBLIC_ODONTOFLUX_SALES_EMAIL?.trim() || "";
const SALES_EMAIL_URL = SALES_EMAIL ? `mailto:${SALES_EMAIL}` : "#contato";
const SALES_EMAIL_LABEL = SALES_EMAIL || "Contato comercial por e-mail";

const WHO_WE_ARE = [
  {
    title: "SaaS premium para clinicas",
    description:
      "A plataforma atende clinicas de diferentes especialidades que precisam automatizar atendimento, agendamento e recuperacao pelo WhatsApp.",
    icon: Building2,
  },
  {
    title: "Implantacao consultiva",
    description:
      "Entramos com proximidade para configurar a operacao, acompanhar o uso real e acelerar a adocao da equipe.",
    icon: Handshake,
  },
  {
    title: "Fluxo completo de atendimento",
    description:
      "O valor esta em ligar conversa, qualificacao, agenda, comparecimento, retorno e reativacao no mesmo fluxo.",
    icon: Workflow,
  },
  {
    title: "IA aplicada com responsabilidade",
    description:
      "Em vez de prometer automacao vazia, a proposta combina tecnologia, processo, treinamento e controle operacional.",
    icon: ShieldCheck,
  },
];

const PILOT_SCOPE = [
  {
    title: "Diagnostico e preparacao",
    bullets: [
      "Reuniao inicial para entender unidade, equipe e gargalos.",
      "Definicao da unidade piloto e do numero principal de atendimento.",
      "Mapeamento de servicos, agenda, profissionais e rotina da recepcao.",
    ],
  },
  {
    title: "Implantacao guiada",
    bullets: [
      "Configuracao da clinica, unidades, equipe e servicos oficiais.",
      "Ajuste do fluxo de agenda, comparecimento, retorno e leads.",
      "Ambiente preparado para uso real com demonstracao orientada.",
    ],
  },
  {
    title: "Acompanhamento de 30 dias",
    bullets: [
      "Treinamento da recepcao e validacao do fluxo principal.",
      "Revisoes semanais com ajustes prioritarios de implantacao.",
      "Suporte de entrada para destravar uso e padronizar operacao.",
    ],
  },
  {
    title: "Fechamento e proxima etapa",
    bullets: [
      "Revisao do que melhorou na operacao e no atendimento.",
      "Plano de continuidade, expansao ou segunda fase da implantacao.",
      "Base para proposta comercial seguinte com mais confianca.",
    ],
  },
];

const PROOF_SIGNALS = [
  {
    title: "Tempo de primeira resposta",
    text: "Acompanhamos se o paciente esta sendo atendido mais rapido e com menos troca perdida no WhatsApp.",
  },
  {
    title: "Taxa de agendamento",
    text: "Medimos quantas conversas saem do contato inicial e chegam a uma consulta realmente marcada.",
  },
  {
    title: "Faltas e comparecimento",
    text: "A clinica passa a registrar quem veio, quem faltou e o que precisa ser recuperado ou reagendado.",
  },
  {
    title: "Retorno e continuidade",
    text: "O piloto mostra se a operacao esta conseguindo transformar atendimento concluido em proximo passo claro.",
  },
];

const CASE_MODEL_STEPS = [
  "Semana 1: diagnostico da recepcao, da agenda e do fluxo comercial principal.",
  "Semana 2: implantacao guiada com cadastro, configuracao e treinamento do time.",
  "Semana 3: operacao acompanhada com ajustes nas rotinas de atendimento e agenda.",
  "Semana 4: revisao final com baseline, aprendizados e proxima proposta de continuidade.",
];

function ActionLink({
  href,
  children,
  variant = "solid",
  className,
}: {
  href: string;
  children: React.ReactNode;
  variant?: "solid" | "outline";
  className?: string;
}) {
  const classes = cn(
    "inline-flex items-center justify-center rounded-full px-5 py-3 text-sm font-semibold transition",
    variant === "solid"
      ? "bg-white text-stone-950 hover:bg-emerald-50"
      : "border border-white/15 bg-white/5 text-white hover:bg-white/10",
    className,
  );
  const isExternal = href.startsWith("http://") || href.startsWith("https://") || href.startsWith("mailto:");

  if (isExternal) {
    return (
      <a
        href={href}
        className={classes}
        target={href.startsWith("http") ? "_blank" : undefined}
        rel={href.startsWith("http") ? "noreferrer" : undefined}
      >
        {children}
      </a>
    );
  }

  return (
    <Link href={href} className={classes}>
      {children}
    </Link>
  );
}

function SectionTag({ children }: { children: React.ReactNode }) {
  return (
    <p className="inline-flex rounded-full border border-stone-300 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-600">
      {children}
    </p>
  );
}

export function LandingPage() {
  return (
    <div className="min-h-screen bg-[#f6f0e8] text-stone-950">
      <div className="absolute inset-x-0 top-0 h-[720px] bg-[radial-gradient(circle_at_top_left,_rgba(22,163,74,0.2),_transparent_36%),radial-gradient(circle_at_top_right,_rgba(59,130,246,0.16),_transparent_28%),linear-gradient(180deg,#07110d_0%,#0b1720_58%,#f6f0e8_100%)]" />

      <header className="sticky top-0 z-30 border-b border-white/10 bg-stone-950/82 backdrop-blur-xl">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-[18px] bg-gradient-to-br from-emerald-300 via-teal-300 to-cyan-300 text-sm font-black text-stone-950 shadow-[0_10px_30px_rgba(16,185,129,0.25)]">
              {BRAND_MONOGRAM}
            </div>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.24em] text-white/45">{BRAND_NAME}</p>
              <p className="text-sm font-semibold text-white">{BRAND_TAGLINE}</p>
            </div>
          </div>

          <nav className="hidden items-center gap-5 md:flex">
            <Link href="#solucao" className="text-sm font-medium text-white/70 transition hover:text-white">
              Solucao
            </Link>
            <Link href="#quem-somos" className="text-sm font-medium text-white/70 transition hover:text-white">
              Quem somos
            </Link>
            <Link href="#como-funciona" className="text-sm font-medium text-white/70 transition hover:text-white">
              Como funciona
            </Link>
            <Link href="#piloto" className="text-sm font-medium text-white/70 transition hover:text-white">
              Piloto
            </Link>
            <Link href="#planos" className="text-sm font-medium text-white/70 transition hover:text-white">
              Planos
            </Link>
            <Link href="#contato" className="text-sm font-medium text-white/70 transition hover:text-white">
              Contato
            </Link>
            <ActionLink href={SALES_DEMO_URL} className="px-4 py-2">
              Ver demonstracao
            </ActionLink>
            <Link
              href="/login"
              className="inline-flex items-center rounded-full border border-white/15 bg-white/5 px-4 py-2 text-sm font-semibold text-white transition hover:bg-white/10"
            >
              Ativar minha IA
            </Link>
          </nav>

          <div className="flex items-center gap-2 md:hidden">
            <ActionLink href={SALES_DEMO_URL} className="px-4 py-2 text-xs">
              Ver demo
            </ActionLink>
          </div>
        </div>
      </header>

      <main className="relative z-10">
        <section className="mx-auto w-full max-w-7xl px-4 pb-12 pt-12 sm:px-6 lg:px-8 lg:pb-20 lg:pt-16">
          <div className="grid gap-10 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-emerald-300/20 bg-emerald-400/10 px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.24em] text-emerald-100">
                <Sparkles className="h-4 w-4" />
                Plataforma SaaS para clinicas em crescimento
              </div>

              <h1 className="mt-6 max-w-4xl font-heading text-4xl font-black leading-[1.02] text-white sm:text-5xl lg:text-7xl">
                {BRAND_NAME}
              </h1>

              <p className="mt-6 max-w-2xl text-base leading-7 text-white/72 sm:text-lg">
                {BRAND_TAGLINE}
              </p>

              <p className="mt-4 max-w-2xl text-base leading-7 text-white/72 sm:text-lg">
                {BRAND_DESCRIPTION}
              </p>

              <div className="mt-8 flex flex-wrap gap-3">
                <ActionLink href={SALES_DEMO_URL}>
                  Ver demonstracao
                  <ArrowRight className="ml-2 h-4 w-4" />
                </ActionLink>
                <ActionLink href={SALES_WHATSAPP_URL} variant="outline">
                  Falar com especialista
                  <ArrowUpRight className="ml-2 h-4 w-4" />
                </ActionLink>
                <Link
                  href="/login"
                  className="inline-flex items-center justify-center rounded-full border border-white/10 px-5 py-3 text-sm font-semibold text-white/80 transition hover:border-white/20 hover:bg-white/5 hover:text-white"
                >
                  Testar atendimento com IA
                </Link>
              </div>

              <div className="mt-10 grid gap-3 sm:grid-cols-2">
                {PAIN_POINTS.map((pain) => (
                  <div
                    key={pain}
                    className="rounded-[22px] border border-white/10 bg-white/6 p-4 text-sm text-white/82 backdrop-blur"
                  >
                    <div className="flex items-start gap-3">
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" />
                      <span>{pain}</span>
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-8 flex flex-wrap gap-3">
                <div className="rounded-full border border-white/10 bg-white/6 px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-white/72">
                  Atendimento 24h
                </div>
                <div className="rounded-full border border-white/10 bg-white/6 px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-white/72">
                  Qualificacao automatica
                </div>
                <div className="rounded-full border border-white/10 bg-white/6 px-4 py-2 text-xs font-semibold uppercase tracking-[0.14em] text-white/72">
                  Recuperacao de leads antigos
                </div>
              </div>
            </div>

            <div className="relative">
              <div className="absolute -left-10 top-10 h-24 w-24 rounded-full bg-emerald-300/20 blur-3xl" />
              <div className="absolute -right-8 bottom-16 h-28 w-28 rounded-full bg-cyan-300/20 blur-3xl" />

              <div className="relative overflow-hidden rounded-[36px] border border-white/12 bg-white/8 p-4 shadow-[0_40px_120px_rgba(0,0,0,0.35)] backdrop-blur-xl">
                <div className="rounded-[30px] border border-stone-200 bg-[#fcf8f3] p-5 shadow-[0_20px_50px_rgba(15,23,42,0.08)]">
                  <div className="flex items-center justify-between gap-3 rounded-[22px] bg-stone-950 px-4 py-3 text-white">
                    <div>
                      <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-emerald-200/70">
                        Workspace clinico
                      </p>
                      <p className="text-sm font-semibold">Gestao da clinica em tempo real</p>
                    </div>
                    <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-semibold">
                      Unidade Centro
                    </span>
                  </div>

                  <div className="mt-4 grid gap-4 lg:grid-cols-[0.7fr_1.3fr]">
                    <div className="rounded-[24px] border border-stone-200 bg-white p-4">
                      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">Fluxo de atendimento</p>
                      <div className="mt-4 space-y-3">
                        <div className="rounded-2xl bg-emerald-50 p-3">
                          <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">Lead entrou</p>
                          <p className="mt-1 text-sm font-semibold">Paciente chamou no WhatsApp</p>
                        </div>
                        <div className="rounded-2xl bg-amber-50 p-3">
                          <p className="text-xs font-semibold uppercase tracking-wide text-amber-700">Recepcao responde</p>
                          <p className="mt-1 text-sm font-semibold">IA ajuda a manter padrao</p>
                        </div>
                        <div className="rounded-2xl bg-cyan-50 p-3">
                          <p className="text-xs font-semibold uppercase tracking-wide text-cyan-700">Consulta agendada</p>
                          <p className="mt-1 text-sm font-semibold">Agenda e equipe em sincronia</p>
                        </div>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <div className="rounded-[24px] border border-stone-200 bg-white p-5">
                        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">Posicionamento comercial</p>
                        <h2 className="mt-2 text-2xl font-black text-stone-950">
                          Menos caos no dia a dia. Mais previsibilidade para recepcao, dono e equipe.
                        </h2>
                        <p className="mt-3 text-sm leading-6 text-stone-600">
                          A venda certa nao e mostrar uma agenda isolada. E mostrar como a clinica sai de mensagens
                          soltas e passa a operar com atendimento, agendamento, comparecimento e retorno conectados.
                        </p>
                      </div>

                      <div className="grid gap-4 sm:grid-cols-2">
                        <div className="rounded-[22px] border border-stone-200 bg-stone-950 p-4 text-white">
                          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-200/70">Melhor forma de vender</p>
                          <p className="mt-3 text-lg font-bold">Piloto assistido com implantacao premium</p>
                        </div>
                        <div className="rounded-[22px] border border-stone-200 bg-white p-4">
                          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">Cliente ideal</p>
                          <p className="mt-3 text-lg font-bold text-stone-950">
                            Clinica que depende de WhatsApp e precisa organizar a operacao
                          </p>
                        </div>
                      </div>

                      <div className="grid gap-3 sm:grid-cols-3">
                        <div className="rounded-[20px] border border-stone-200 bg-[#f6efe5] p-3">
                          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-stone-500">Recepcao</p>
                          <p className="mt-2 text-sm font-bold text-stone-950">Mais processo</p>
                        </div>
                        <div className="rounded-[20px] border border-stone-200 bg-[#eef6f2] p-3">
                          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-stone-500">Agenda</p>
                          <p className="mt-2 text-sm font-bold text-stone-950">Mais controle</p>
                        </div>
                        <div className="rounded-[20px] border border-stone-200 bg-[#eef3f8] p-3">
                          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-stone-500">Gestao</p>
                          <p className="mt-2 text-sm font-bold text-stone-950">Mais visibilidade</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="solucao" className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
          <div className="rounded-[34px] border border-stone-200 bg-white p-6 shadow-[0_24px_80px_rgba(15,23,42,0.08)] sm:p-8">
            <SectionTag>Solucao</SectionTag>
            <div className="mt-4 grid gap-8 lg:grid-cols-[0.9fr_1.1fr]">
              <div>
                <h2 className="text-3xl font-black text-stone-950 sm:text-4xl">
                  {BRAND_NAME} conecta atendimento, agenda, equipe e recuperacao em uma experiencia unica.
                </h2>
                <p className="mt-4 text-sm leading-7 text-stone-600 sm:text-base">
                  Em vez de vender telas soltas, voce apresenta uma rotina completa para clinicas que querem automatizar atendimento, agendamento e conversao no WhatsApp.
                </p>

                <div className="mt-8 space-y-4">
                  {VALUE_PILLARS.map((pillar) => {
                    const Icon = pillar.icon;
                    return (
                      <div key={pillar.title} className="flex gap-4 rounded-[24px] border border-stone-200 bg-[#fbf7f1] p-4">
                        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-stone-950 text-white">
                          <Icon className="h-5 w-5" />
                        </div>
                        <div>
                          <h3 className="text-lg font-bold text-stone-950">{pillar.title}</h3>
                          <p className="mt-1 text-sm leading-6 text-stone-600">{pillar.description}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-3">
                {RESULTS.map((result, index) => (
                  <div
                    key={result.metric}
                    className={cn(
                      "rounded-[28px] border p-5",
                      index === 0 && "border-emerald-200 bg-emerald-50",
                      index === 1 && "border-cyan-200 bg-cyan-50",
                      index === 2 && "border-amber-200 bg-amber-50",
                    )}
                  >
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Impacto real</p>
                    <h3 className="mt-3 text-xl font-black text-stone-950">{result.metric}</h3>
                    <p className="mt-3 text-sm leading-6 text-stone-600">{result.text}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
          <div className="grid gap-4 lg:grid-cols-4">
            <div className="rounded-[30px] border border-stone-200 bg-stone-950 p-6 text-white shadow-[0_24px_80px_rgba(15,23,42,0.14)]">
              <Clock3 className="h-5 w-5 text-emerald-300" />
              <p className="mt-4 text-xs font-semibold uppercase tracking-[0.2em] text-white/55">Tempo</p>
              <h3 className="mt-2 text-2xl font-black">Menos retrabalho manual</h3>
              <p className="mt-3 text-sm leading-6 text-white/72">
                O time gasta menos energia reconstituindo contexto e mais energia conduzindo o paciente.
              </p>
            </div>
            <div className="rounded-[30px] border border-stone-200 bg-white p-6">
              <TrendingUp className="h-5 w-5 text-stone-950" />
              <p className="mt-4 text-xs font-semibold uppercase tracking-[0.2em] text-stone-500">Crescimento</p>
              <h3 className="mt-2 text-2xl font-black text-stone-950">Mais chance de converter</h3>
              <p className="mt-3 text-sm leading-6 text-stone-600">
                Quando o fluxo comercial fica visivel, a clinica perde menos oportunidades no meio do caminho.
              </p>
            </div>
            <div className="rounded-[30px] border border-stone-200 bg-white p-6">
              <Workflow className="h-5 w-5 text-stone-950" />
              <p className="mt-4 text-xs font-semibold uppercase tracking-[0.2em] text-stone-500">Processo</p>
              <h3 className="mt-2 text-2xl font-black text-stone-950">Equipe com rotina padrao</h3>
              <p className="mt-3 text-sm leading-6 text-stone-600">
                Atendimento, confirmacao, comparecimento e retorno passam a seguir um caminho mais previsivel.
              </p>
            </div>
            <div className="rounded-[30px] border border-stone-200 bg-white p-6">
              <BadgeCheck className="h-5 w-5 text-stone-950" />
              <p className="mt-4 text-xs font-semibold uppercase tracking-[0.2em] text-stone-500">Apresentacao</p>
              <h3 className="mt-2 text-2xl font-black text-stone-950">Produto com cara profissional</h3>
              <p className="mt-3 text-sm leading-6 text-stone-600">
                Voce apresenta uma plataforma organizada, madura e orientada a operacao real da clinica.
              </p>
            </div>
          </div>
        </section>

        <section id="quem-somos" className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
          <div className="grid gap-6 lg:grid-cols-[0.92fr_1.08fr]">
            <div className="rounded-[34px] border border-stone-200 bg-white p-6 shadow-[0_24px_80px_rgba(15,23,42,0.08)] sm:p-8">
              <SectionTag>Quem somos</SectionTag>
              <h2 className="mt-4 text-3xl font-black text-stone-950 sm:text-4xl">
                Uma marca premium para clinicas que querem crescer com processo, IA e mais previsibilidade.
              </h2>
              <p className="mt-4 text-sm leading-7 text-stone-600 sm:text-base">
                A {BRAND_NAME} nasce com um posicionamento claro: ser uma plataforma SaaS moderna para clinicas que precisam atender pacientes com mais velocidade, agendar melhor e recuperar oportunidades sem sobrecarregar a equipe.
              </p>
              <p className="mt-4 text-sm leading-7 text-stone-600 sm:text-base">
                Em vez de ficar presa a um unico nicho, a plataforma atende odontologia, estetica, dermatologia, fisioterapia, psicologia, clinicas populares e outras areas de saude com a mesma base operacional.
              </p>

              <div className="mt-8 rounded-[28px] border border-stone-200 bg-stone-950 p-5 text-white">
                <div className="flex items-start gap-4">
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/10 text-emerald-200">
                    <Building2 className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-white/55">Frente comercial</p>
                    <p className="mt-2 text-xl font-black">{SALES_CONTACT_NAME}</p>
                    <p className="mt-1 text-sm text-white/72">{SALES_CONTACT_ROLE}</p>
                    <p className="mt-3 text-sm text-white/62">{SALES_CONTACT_REGION}</p>
                  </div>
                </div>
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              {WHO_WE_ARE.map((item) => {
                const Icon = item.icon;
                return (
                  <div key={item.title} className="rounded-[28px] border border-stone-200 bg-[#fbf7f1] p-5">
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white text-stone-950 shadow-sm">
                      <Icon className="h-5 w-5" />
                    </div>
                    <h3 className="mt-4 text-lg font-bold text-stone-950">{item.title}</h3>
                    <p className="mt-2 text-sm leading-6 text-stone-600">{item.description}</p>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        <section id="como-funciona" className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
          <div className="rounded-[36px] bg-stone-950 p-6 text-white shadow-[0_32px_100px_rgba(15,23,42,0.18)] sm:p-8">
            <SectionTag>Como funciona</SectionTag>
            <div className="mt-4 max-w-3xl">
              <h2 className="text-3xl font-black sm:text-4xl">Uma narrativa simples para mostrar o sistema na demonstracao.</h2>
              <p className="mt-4 text-sm leading-7 text-white/72 sm:text-base">
                A venda melhora quando a clinica enxerga o caminho completo do paciente. Use esta ordem para apresentar
                o valor da {BRAND_NAME} de um jeito que faca sentido comercial e operacional.
              </p>
            </div>

            <div className="mt-8 grid gap-4 lg:grid-cols-4">
              {JOURNEY.map((item) => (
                <div key={item.step} className="rounded-[28px] border border-white/10 bg-white/6 p-5 backdrop-blur">
                  <p className="text-sm font-black text-emerald-200">{item.step}</p>
                  <h3 className="mt-4 text-xl font-black">{item.title}</h3>
                  <p className="mt-3 text-sm leading-6 text-white/72">{item.description}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="piloto" className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
          <div className="grid gap-6 lg:grid-cols-[1.05fr_0.95fr]">
            <div className="rounded-[34px] border border-stone-200 bg-white p-6 shadow-[0_24px_80px_rgba(15,23,42,0.08)] sm:p-8">
              <SectionTag>Piloto assistido</SectionTag>
              <h2 className="mt-4 text-3xl font-black text-stone-950 sm:text-4xl">
                A melhor forma de comecar e implantar junto, e nao simplesmente entregar login e senha.
              </h2>
              <p className="mt-4 text-sm leading-7 text-stone-600 sm:text-base">
                Piloto assistido significa entrar na clinica, configurar o ambiente, treinar a equipe, acompanhar os
                primeiros dias e ajustar o fluxo com base no uso real. Isso aumenta o valor percebido e reduz o risco
                para o cliente.
              </p>

              <div className="mt-6 grid gap-3 sm:grid-cols-2">
                <div className="rounded-[24px] border border-stone-200 bg-[#f6efe5] p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">Escopo inicial</p>
                  <p className="mt-2 text-sm font-bold text-stone-950">30 dias, 1 unidade piloto e rotina principal de recepcao.</p>
                </div>
                <div className="rounded-[24px] border border-stone-200 bg-[#eef6f2] p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">Entrega comercial</p>
                  <p className="mt-2 text-sm font-bold text-stone-950">Diagnostico, implantacao, treinamento e revisao final.</p>
                </div>
              </div>

              <div className="mt-8 grid gap-4 sm:grid-cols-2">
                <div className="rounded-[24px] border border-stone-200 bg-[#fbf7f1] p-5">
                  <PhoneCall className="h-5 w-5 text-stone-950" />
                  <h3 className="mt-4 text-lg font-bold text-stone-950">Entrada consultiva</h3>
                  <p className="mt-2 text-sm leading-6 text-stone-600">
                    Voce vende implantacao e acompanhamento, nao somente software.
                  </p>
                </div>
                <div className="rounded-[24px] border border-stone-200 bg-[#eef6f2] p-5">
                  <ShieldCheck className="h-5 w-5 text-stone-950" />
                  <h3 className="mt-4 text-lg font-bold text-stone-950">Menor risco para a clinica</h3>
                  <p className="mt-2 text-sm leading-6 text-stone-600">
                    O cliente sente que voce esta junto para fazer a operacao funcionar.
                  </p>
                </div>
                <div className="rounded-[24px] border border-stone-200 bg-[#eef3f8] p-5">
                  <Sparkles className="h-5 w-5 text-stone-950" />
                  <h3 className="mt-4 text-lg font-bold text-stone-950">Aprendizado acelerado</h3>
                  <p className="mt-2 text-sm leading-6 text-stone-600">
                    Cada implantacao mostra onde melhorar o produto para a proxima venda.
                  </p>
                </div>
                <div className="rounded-[24px] border border-stone-200 bg-[#fff5e8] p-5">
                  <TrendingUp className="h-5 w-5 text-stone-950" />
                  <h3 className="mt-4 text-lg font-bold text-stone-950">Base para caso de sucesso</h3>
                  <p className="mt-2 text-sm leading-6 text-stone-600">
                    O piloto ajuda voce a coletar prova real para subir preco e escalar depois.
                  </p>
                </div>
              </div>
            </div>

            <div className="rounded-[34px] border border-stone-200 bg-stone-950 p-6 text-white shadow-[0_24px_80px_rgba(15,23,42,0.18)] sm:p-8">
              <SectionTag>Escopo fechado</SectionTag>
              <h2 className="mt-4 text-3xl font-black sm:text-4xl">O cliente precisa enxergar exatamente o que entra no primeiro ciclo.</h2>

              <div className="mt-6 grid gap-3 sm:grid-cols-2">
                <div className="rounded-[22px] border border-white/10 bg-white/6 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-white/55">Duracao</p>
                  <p className="mt-2 text-lg font-black">30 dias de piloto</p>
                </div>
                <div className="rounded-[22px] border border-white/10 bg-white/6 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-white/55">Cobertura</p>
                  <p className="mt-2 text-lg font-black">1 unidade e 1 fluxo principal</p>
                </div>
                <div className="rounded-[22px] border border-white/10 bg-white/6 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-white/55">Time</p>
                  <p className="mt-2 text-lg font-black">Recepcao, agenda e lideranca</p>
                </div>
                <div className="rounded-[22px] border border-white/10 bg-white/6 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-white/55">Ritmo</p>
                  <p className="mt-2 text-lg font-black">Revisoes semanais</p>
                </div>
              </div>

              <div className="mt-6 space-y-4">
                {PILOT_SCOPE.map((scope) => (
                  <div key={scope.title} className="rounded-[26px] border border-white/10 bg-white/6 p-5">
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-white/10 text-emerald-200">
                        <ClipboardCheck className="h-5 w-5" />
                      </div>
                      <h3 className="text-lg font-bold">{scope.title}</h3>
                    </div>
                    <div className="mt-4 space-y-3 text-sm leading-6 text-white/78">
                      {scope.bullets.map((bullet) => (
                        <div key={bullet} className="flex items-start gap-3">
                          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" />
                          <span>{bullet}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-6">
                <ActionLink href={SALES_DEMO_URL} className="w-full sm:w-auto">
                  Quero automatizar minha clinica
                  <ArrowRight className="ml-2 h-4 w-4" />
                </ActionLink>
              </div>
            </div>
          </div>
        </section>

        <section className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
          <div className="grid gap-6 lg:grid-cols-[0.94fr_1.06fr]">
            <div className="rounded-[34px] border border-stone-200 bg-stone-950 p-6 text-white shadow-[0_24px_80px_rgba(15,23,42,0.18)] sm:p-8">
              <SectionTag>Prova inicial</SectionTag>
              <h2 className="mt-4 text-3xl font-black sm:text-4xl">
                A melhor prova para os primeiros clientes e um plano de medicao claro, nao uma promessa vaga.
              </h2>
              <p className="mt-4 text-sm leading-7 text-white/72 sm:text-base">
                Antes de escalar, a pagina precisa mostrar que existe metodo. Os primeiros pilotos entram com baseline,
                acompanhamento e revisao final para gerar prova operacional documentada.
              </p>

              <div className="mt-8 grid gap-4 sm:grid-cols-2">
                {PROOF_SIGNALS.map((signal) => (
                  <div key={signal.title} className="rounded-[24px] border border-white/10 bg-white/6 p-5 backdrop-blur">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-200/75">Indicador acompanhado</p>
                    <h3 className="mt-3 text-lg font-bold">{signal.title}</h3>
                    <p className="mt-2 text-sm leading-6 text-white/72">{signal.text}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-[34px] border border-stone-200 bg-white p-6 shadow-[0_24px_80px_rgba(15,23,42,0.08)] sm:p-8">
              <SectionTag>Caso modelo</SectionTag>
              <h2 className="mt-4 text-3xl font-black text-stone-950 sm:text-4xl">
                Um caso de 30 dias que voce pode apresentar com clareza desde o primeiro contrato.
              </h2>
              <p className="mt-4 text-sm leading-7 text-stone-600 sm:text-base">
                O cliente entende melhor quando voce mostra o formato do case antes mesmo de acumular dezenas de
                depoimentos. Assim, a venda se apoia em processo, entrega e medicao real.
              </p>

              <div className="mt-8 rounded-[28px] border border-stone-200 bg-[#faf6ef] p-5">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Caso modelo de implantacao</p>
                <p className="mt-3 text-lg font-bold text-stone-950">
                  Clinica com forte dependencia de WhatsApp, agenda fragmentada e necessidade de organizar recepcao e
                  retorno sem parar a operacao.
                </p>
                <div className="mt-5 space-y-3 text-sm leading-6 text-stone-700">
                  {CASE_MODEL_STEPS.map((step) => (
                    <div key={step} className="flex items-start gap-3">
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                      <span>{step}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-6 grid gap-4 sm:grid-cols-2">
                <div className="rounded-[24px] border border-stone-200 bg-white p-5">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">O que a clinica enxerga</p>
                  <p className="mt-2 text-sm leading-6 text-stone-700">
                    Fluxo operacional mais claro, atendimento menos espalhado e proximo passo definido para cada
                    paciente.
                  </p>
                </div>
                <div className="rounded-[24px] border border-stone-200 bg-white p-5">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">O que voce ganha</p>
                  <p className="mt-2 text-sm leading-6 text-stone-700">
                    Material para proposta seguinte, depoimento futuro e argumentos mais fortes para precificar melhor.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="planos" className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
          <div className="rounded-[36px] border border-stone-200 bg-white p-6 shadow-[0_24px_80px_rgba(15,23,42,0.08)] sm:p-8">
            <SectionTag>Oferta comercial</SectionTag>
            <div className="mt-4 max-w-3xl">
              <h2 className="text-3xl font-black text-stone-950 sm:text-4xl">
                Comece com uma oferta forte o suficiente para vender valor, e simples o suficiente para fechar.
              </h2>
              <p className="mt-4 text-sm leading-7 text-stone-600 sm:text-base">
                Neste estagio, a {BRAND_NAME} faz mais sentido como SaaS premium com implantacao consultiva do que
                como software barato de prateleira. Isso te ajuda a vender melhor e aprender mais rapido com os
                primeiros clientes.
              </p>
            </div>

            <div className="mt-8 grid gap-4 xl:grid-cols-3">
              {OFFER_BLOCKS.map((plan) => (
                <div
                  key={plan.title}
                  className={cn(
                    "rounded-[30px] border p-5",
                    plan.highlight
                      ? "border-emerald-300 bg-[linear-gradient(180deg,#0a1611_0%,#0f1f17_100%)] text-white shadow-[0_24px_80px_rgba(16,185,129,0.18)]"
                      : "border-stone-200 bg-[#fbf8f3] text-stone-950",
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p
                        className={cn(
                          "text-xs font-semibold uppercase tracking-[0.18em]",
                          plan.highlight ? "text-emerald-200/80" : "text-stone-500",
                        )}
                      >
                        {plan.highlight ? "Mais indicado para comecar" : "Escala comercial"}
                      </p>
                      <h3 className="mt-2 text-2xl font-black">{plan.title}</h3>
                    </div>
                    {plan.highlight ? (
                      <span className="rounded-full bg-white px-3 py-1 text-[11px] font-black uppercase tracking-[0.18em] text-stone-950">
                        Recomendado
                      </span>
                    ) : null}
                  </div>

                  <div
                    className={cn(
                      "mt-6 rounded-[22px] p-4",
                      plan.highlight ? "bg-white/8" : "bg-white",
                    )}
                  >
                    <p className="text-2xl font-black">{plan.price}</p>
                    <p className={cn("mt-1 text-sm", plan.highlight ? "text-white/68" : "text-stone-500")}>{plan.detail}</p>
                  </div>

                  <div className="mt-6 space-y-3">
                    {plan.bullets.map((bullet) => (
                      <div key={bullet} className={cn("flex items-start gap-3 text-sm", plan.highlight ? "text-white/84" : "text-stone-700")}>
                        <CheckCircle2 className={cn("mt-0.5 h-4 w-4 shrink-0", plan.highlight ? "text-emerald-300" : "text-emerald-600")} />
                        <span>{bullet}</span>
                      </div>
                    ))}
                  </div>

                  <div className="mt-6">
                    <ActionLink
                      href={plan.highlight ? SALES_DEMO_URL : "#contato"}
                      className={cn(
                        "inline-flex items-center rounded-full px-4 py-2.5 text-sm font-semibold transition",
                        plan.highlight
                          ? "bg-white text-stone-950 hover:bg-emerald-50"
                          : "bg-stone-950 text-white hover:bg-stone-800",
                      )}
                    >
                      {plan.highlight ? "Quero automatizar minha clinica" : "Falar com especialista"}
                    </ActionLink>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
          <div className="rounded-[34px] border border-stone-200 bg-white p-6 shadow-[0_24px_80px_rgba(15,23,42,0.08)] sm:p-8">
            <SectionTag>Perguntas comuns</SectionTag>
            <div className="mt-4 grid gap-4 lg:grid-cols-3">
              {FAQS.map((faq) => (
                <div key={faq.question} className="rounded-[26px] border border-stone-200 bg-[#faf6ef] p-5">
                  <h3 className="text-lg font-bold text-stone-950">{faq.question}</h3>
                  <p className="mt-3 text-sm leading-6 text-stone-600">{faq.answer}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="agendar-demo" className="mx-auto w-full max-w-7xl px-4 pb-10 pt-10 sm:px-6 lg:px-8">
          <div className="overflow-hidden rounded-[40px] border border-emerald-200 bg-[radial-gradient(circle_at_top_left,_rgba(16,185,129,0.16),_transparent_36%),linear-gradient(135deg,#ffffff_0%,#f6efe4_100%)] p-8 shadow-[0_28px_90px_rgba(15,23,42,0.1)]">
            <div className="grid gap-8 lg:grid-cols-[1.1fr_0.9fr] lg:items-start">
              <div>
                <p className="inline-flex items-center gap-2 rounded-full border border-emerald-300 bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700">
                  <ShieldCheck className="h-4 w-4" />
                  Proximo passo comercial
                </p>
                <h2 className="mt-4 max-w-3xl text-3xl font-black text-stone-950 sm:text-4xl">
                  Veja como a {BRAND_NAME} organiza o fluxo real da sua clinica e transforma WhatsApp em operacao.
                </h2>
                <p className="mt-4 max-w-2xl text-sm leading-7 text-stone-600 sm:text-base">
                  A demonstracao ideal nao mostra so tela. Ela parte do seu contexto, passa por atendimento, agenda,
                  recuperacao e retorno, e termina com um plano claro para ativar a IA da sua clinica.
                </p>

                <div className="mt-8 grid gap-4 sm:grid-cols-2">
                  <div className="rounded-[26px] border border-stone-200 bg-white/90 p-5 backdrop-blur">
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-stone-950 text-white">
                      <PlayCircle className="h-5 w-5" />
                    </div>
                    <h3 className="mt-4 text-lg font-bold text-stone-950">Ver demonstracao</h3>
                    <p className="mt-2 text-sm leading-6 text-stone-600">
                      Veja o ambiente real, mapeie gargalos do atendimento e entenda como a IA melhora a conversao.
                    </p>
                    <div className="mt-5">
                      <ActionLink href={SALES_DEMO_URL} className="w-full sm:w-auto">
                        Ver demonstracao guiada
                        <ArrowRight className="ml-2 h-4 w-4" />
                      </ActionLink>
                    </div>
                  </div>

                  <div id="contato" className="rounded-[26px] border border-stone-200 bg-white/90 p-5 backdrop-blur">
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-stone-950 text-white">
                      <PhoneCall className="h-5 w-5" />
                    </div>
                    <h3 className="mt-4 text-lg font-bold text-stone-950">Simular conversa no WhatsApp</h3>
                    <p className="mt-2 text-sm leading-6 text-stone-600">
                      Se preferir, fale direto com um especialista e compartilhe volume, equipe e gargalos para acelerar o diagnostico.
                    </p>
                    <div className="mt-5">
                      <ActionLink href={SALES_WHATSAPP_URL} className="w-full sm:w-auto">
                        Falar com especialista
                        <ArrowUpRight className="ml-2 h-4 w-4" />
                      </ActionLink>
                    </div>
                  </div>
                </div>
              </div>

              <div className="rounded-[30px] border border-stone-200 bg-white/92 p-5 backdrop-blur">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Contato e confianca</p>

                <div className="mt-5 rounded-[24px] border border-stone-200 bg-stone-950 p-5 text-white">
                  <p className="text-xl font-black">{SALES_CONTACT_NAME}</p>
                  <p className="mt-1 text-sm text-white/72">{SALES_CONTACT_ROLE}</p>
                  <p className="mt-3 text-sm text-white/62">{SALES_CONTACT_REGION}</p>
                </div>

                <div className="mt-5 space-y-3">
                  <div className="flex items-center justify-between gap-3 rounded-[22px] border border-stone-200 bg-white px-4 py-3">
                    <div className="flex items-center gap-3">
                      <Mail className="h-4 w-4 text-stone-700" />
                      <span className="text-sm font-semibold text-stone-900">{SALES_EMAIL_LABEL}</span>
                    </div>
                    <ActionLink
                      href={SALES_EMAIL_URL}
                      variant="outline"
                      className="border-stone-300 bg-transparent px-4 py-2 text-stone-950 hover:bg-stone-100"
                    >
                      Enviar e-mail
                    </ActionLink>
                  </div>

                  <div className="flex items-center justify-between gap-3 rounded-[22px] border border-stone-200 bg-white px-4 py-3">
                    <div className="flex items-center gap-3">
                      <Handshake className="h-4 w-4 text-stone-700" />
                      <span className="text-sm font-semibold text-stone-900">Piloto assistido com implantacao guiada</span>
                    </div>
                    <Link
                      href="#piloto"
                      className="inline-flex items-center rounded-full border border-stone-300 px-4 py-2 text-sm font-semibold text-stone-900 transition hover:bg-stone-100"
                    >
                      Ver escopo
                    </Link>
                  </div>
                </div>

                <div className="mt-5 rounded-[24px] border border-stone-200 bg-[#faf6ef] p-5">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">O que levar para a demo</p>
                  <div className="mt-4 space-y-3 text-sm leading-6 text-stone-700">
                    <p>1. Qual unidade ou operacao voce quer organizar primeiro.</p>
                    <p>2. Como o WhatsApp e a agenda funcionam hoje.</p>
                    <p>3. Onde a recepcao perde mais tempo, pacientes ou previsibilidade.</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="mx-auto w-full max-w-7xl px-4 pb-14 pt-2 sm:px-6 lg:px-8">
          <footer className="rounded-[36px] border border-stone-200 bg-stone-950 p-6 text-white shadow-[0_24px_80px_rgba(15,23,42,0.18)] sm:p-8">
            <div className="grid gap-8 lg:grid-cols-[1.1fr_0.9fr_0.8fr]">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.24em] text-white/45">{BRAND_NAME}</p>
                <h2 className="mt-3 text-2xl font-black">{BRAND_TAGLINE}</h2>
                <p className="mt-4 max-w-xl text-sm leading-7 text-white/70">
                  Atendimento, qualificacao, agenda, recuperacao e acompanhamento em um mesmo fluxo de operacao real.
                </p>
              </div>

              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-white/45">Acessos rapidos</p>
                <div className="mt-4 space-y-3 text-sm text-white/72">
                  <p>
                    <Link href="#solucao" className="transition hover:text-white">
                      Ver solucao
                    </Link>
                  </p>
                  <p>
                    <Link href="#piloto" className="transition hover:text-white">
                      Revisar piloto assistido
                    </Link>
                  </p>
                  <p>
                    <Link href="#planos" className="transition hover:text-white">
                      Comparar planos
                    </Link>
                  </p>
                  <p>
                    <Link href="/login" className="transition hover:text-white">
                      Ativar minha IA
                    </Link>
                  </p>
                </div>
              </div>

              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-white/45">Sinais de confianca</p>
                <div className="mt-4 space-y-3 text-sm leading-6 text-white/72">
                  <p>Implantacao assistida com escopo inicial claro.</p>
                  <p>Fluxo completo de lead, agenda, comparecimento e retorno.</p>
                  <p>Configuracoes de seguranca, LGPD e operacao ja previstas no produto.</p>
                </div>
              </div>
            </div>
          </footer>
        </section>
      </main>
    </div>
  );
}

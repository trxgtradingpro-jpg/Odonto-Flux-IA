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
import { BRAND_MONOGRAM, BRAND_NAME, BRAND_SALES_TEAM, BRAND_TAGLINE } from "@/lib/brand";
import { InstantDemoHero } from "@/components/marketing/instant-demo-hero";

const VALUE_PILLARS = [
  {
    title: "Atendimento 24h com IA",
    description:
      "Responda pacientes a qualquer hora com contexto, consistencia e uma experiencia premium no WhatsApp.",
    icon: MessageSquareText,
  },
  {
    title: "Qualificacao automatica",
    description:
      "A IA entende interesse, filtra intencao e prepara a equipe para agir com mais velocidade e conversao.",
    icon: CalendarDays,
  },
  {
    title: "Agendamento inteligente",
    description:
      "Organize disponibilidade, confirmacoes, comparecimento e retorno em um fluxo operacional unico.",
    icon: Users2,
  },
  {
    title: "Recuperacao de oportunidades",
    description:
      "Reative pacientes e leads esquecidos sem depender de planilhas, memoria ou mensagens soltas.",
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
    description:
      "A conversa deixa de ser uma mensagem solta e vira parte do fluxo comercial da clinica.",
  },
  {
    step: "02",
    title: "A IA qualifica e direciona",
    description:
      "A conversa recebe contexto, triagem e encaminhamento sem perder o tom humano do atendimento.",
  },
  {
    step: "03",
    title: "Agenda, confirma e acompanha",
    description:
      "O paciente sai do contato inicial para o agendamento com menos ruido entre equipe, servico e profissional.",
  },
  {
    step: "04",
    title: "Recupera e reativa oportunidades",
    description:
      "O sistema sinaliza faltas, retornos e leads antigos para a clinica retomar contato no momento certo.",
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
    question: "A ClinicFlux AI serve para clinicas que querem crescer com mais organizacao?",
    answer:
      "Sim. A plataforma foi desenhada para clinicas que precisam elevar atendimento, agenda e conversao sem depender de improviso na recepcao.",
  },
  {
    question: "O que muda para a clinica na pratica?",
    answer:
      "Muda a organizacao da recepcao, o controle das conversas, a disciplina da agenda e a capacidade de acompanhar o paciente do primeiro contato ate o retorno.",
  },
  {
    question: "Por que a plataforma vai alem de um chatbot?",
    answer:
      "Porque o valor esta em conectar atendimento, agenda, equipe, comparecimento e retorno em um unico fluxo operacional.",
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

const SALES_CONTACT_NAME =
  process.env.NEXT_PUBLIC_ODONTOFLUX_SALES_CONTACT_NAME?.trim() || BRAND_SALES_TEAM;
const SALES_CONTACT_ROLE =
  process.env.NEXT_PUBLIC_ODONTOFLUX_SALES_ROLE?.trim() ||
  "Especialista em automacao, agenda e conversao para clinicas";
const SALES_CONTACT_REGION =
  process.env.NEXT_PUBLIC_ODONTOFLUX_SALES_REGION?.trim() ||
  "Atendimento consultivo para clinicas em todo o Brasil";
const SALES_WHATSAPP_URL =
  process.env.NEXT_PUBLIC_ODONTOFLUX_SALES_WHATSAPP_URL?.trim() || "#contato";
const SALES_DEMO_URL = process.env.NEXT_PUBLIC_ODONTOFLUX_SALES_DEMO_URL?.trim() || "#agendar-demo";
const SALES_EMAIL = process.env.NEXT_PUBLIC_ODONTOFLUX_SALES_EMAIL?.trim() || "";
const SALES_EMAIL_URL = SALES_EMAIL ? `mailto:${SALES_EMAIL}` : "#contato";
const SALES_EMAIL_LABEL = SALES_EMAIL || "Contato comercial por e-mail";

const WHO_WE_ARE = [
  {
    title: "Plataforma premium para clinicas",
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
      "Em vez de prometer automacao vazia, a plataforma combina tecnologia, processo, treinamento e controle operacional.",
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
      "Prioridades claras para a proxima fase da operacao.",
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
  "Semana 4: revisao final com baseline, aprendizados e plano claro de continuidade.",
];

const PREMIUM_SIGNALS = [
  "Mensagem clara para clinicas que precisam atender melhor e organizar a operacao.",
  "Demonstracao com valor perceptivel antes mesmo do primeiro clique no sistema.",
  "Fluxo pensado para transmitir confianca, previsibilidade e cuidado com o paciente.",
];

const EXECUTIVE_PULSE = [
  {
    label: "Posicionamento",
    value: "SaaS premium",
    detail: "Implantacao consultiva, onboarding guiado e entrega com metodo.",
  },
  {
    label: "Percepcao",
    value: "Produto maduro",
    detail: "Visual e discurso que transmitem confianca desde o primeiro contato.",
  },
  {
    label: "Experiencia",
    value: "Demo em minutos",
    detail: "A clinica entende o fluxo e enxerga valor sem depender de explicacao longa.",
  },
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
    "inline-flex items-center justify-center rounded-full px-5 py-3 text-sm font-semibold transition duration-200",
    variant === "solid"
      ? "border border-amber-200/20 bg-[linear-gradient(135deg,#0f2f2a_0%,#10221d_55%,#1b120c_100%)] text-white shadow-[0_22px_55px_rgba(0,0,0,0.22)] hover:brightness-110"
      : "border border-white/12 bg-white/6 text-white hover:bg-white/12",
    className,
  );
  const isExternal =
    href.startsWith("http://") || href.startsWith("https://") || href.startsWith("mailto:");

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
    <p className="inline-flex rounded-full border border-amber-200/20 bg-white/8 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-amber-100">
      {children}
    </p>
  );
}

export function LandingPage() {
  return (
    <div className="min-h-screen bg-[#071311] text-white">
      <div className="absolute inset-x-0 top-0 h-[880px] bg-[radial-gradient(circle_at_top_left,_rgba(45,212,191,0.18),_transparent_22%),radial-gradient(circle_at_88%_8%,_rgba(251,191,36,0.18),_transparent_18%),linear-gradient(180deg,#071311_0%,#0c1816_44%,#eadfce_44%,#f3eadb_100%)]" />

      <header className="sticky top-0 z-30 border-b border-white/10 bg-[#071311]/74 backdrop-blur-xl">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-[18px] bg-gradient-to-br from-emerald-300 via-teal-300 to-amber-200 text-sm font-black text-stone-950 shadow-[0_10px_30px_rgba(16,185,129,0.18)]">
              {BRAND_MONOGRAM}
            </div>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.24em] text-white/45">
                {BRAND_NAME}
              </p>
              <p className="text-sm font-semibold text-white">{BRAND_TAGLINE}</p>
            </div>
          </div>

          <nav className="hidden items-center gap-5 md:flex">
            <Link
              href="#solucao"
              className="text-sm font-medium text-white/66 transition hover:text-white"
            >
              Solucao
            </Link>
            <Link
              href="#quem-somos"
              className="text-sm font-medium text-white/66 transition hover:text-white"
            >
              Quem somos
            </Link>
            <Link
              href="#como-funciona"
              className="text-sm font-medium text-white/66 transition hover:text-white"
            >
              Como funciona
            </Link>
            <Link
              href="#piloto"
              className="text-sm font-medium text-white/66 transition hover:text-white"
            >
              Piloto
            </Link>
            <Link
              href="#planos"
              className="text-sm font-medium text-white/66 transition hover:text-white"
            >
              Planos
            </Link>
            <Link
              href="#contato"
              className="text-sm font-medium text-white/66 transition hover:text-white"
            >
              Contato
            </Link>
            <ActionLink href="#demo-rapida" className="px-4 py-2">
              Criar demo agora
            </ActionLink>
            <Link
              href="/login"
              className="inline-flex items-center rounded-full border border-white/14 bg-white/8 px-4 py-2 text-sm font-semibold text-white transition hover:bg-white/14"
            >
              Entrar
            </Link>
          </nav>

          <div className="flex items-center gap-2 md:hidden">
            <ActionLink href="#demo-rapida" className="px-4 py-2 text-xs">
              Criar demo
            </ActionLink>
          </div>
        </div>
      </header>

      <main className="relative z-10">
        <section className="mx-auto w-full max-w-7xl px-4 pb-4 pt-10 sm:px-6 lg:px-8 lg:pt-14">
          <div className="grid gap-6 lg:grid-cols-[1.08fr_0.92fr]">
            <div className="relative overflow-hidden rounded-[40px] border border-white/10 bg-[linear-gradient(145deg,rgba(5,16,14,0.98)_0%,rgba(10,34,30,0.96)_48%,rgba(32,20,12,0.94)_100%)] p-7 shadow-[0_38px_120px_rgba(0,0,0,0.32)] sm:p-9">
              <div className="pointer-events-none absolute inset-y-0 right-0 w-[42%] bg-[radial-gradient(circle_at_top,_rgba(251,191,36,0.18),_transparent_52%)]" />
              <SectionTag>Experiencia premium para clinicas</SectionTag>
              <h1 className="mt-5 max-w-3xl font-heading text-4xl font-black leading-[0.94] text-white sm:text-5xl lg:text-[4.1rem]">
                Sua clinica enxerga uma operacao mais organizada, mais rapida e mais premium desde a
                primeira visita.
              </h1>
              <p className="mt-5 max-w-2xl text-base leading-7 text-white/72 sm:text-lg">
                A {BRAND_NAME} apresenta atendimento, agenda e recuperacao de pacientes em uma
                experiencia que transmite confianca, metodo e previsibilidade para a rotina da
                clinica.
              </p>

              <div className="mt-8 grid gap-3 sm:grid-cols-3">
                {EXECUTIVE_PULSE.map((item) => (
                  <div
                    key={item.label}
                    className="rounded-[24px] border border-white/10 bg-white/[0.06] p-4 backdrop-blur"
                  >
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-white/45">
                      {item.label}
                    </p>
                    <p className="mt-3 font-heading text-2xl font-black text-[#f6ead4]">
                      {item.value}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-white/68">{item.detail}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="grid gap-4">
              <div className="rounded-[34px] border border-white/10 bg-[#f2e8d9] p-6 text-stone-950 shadow-[0_24px_70px_rgba(0,0,0,0.14)]">
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-stone-500">
                  O que a clinica percebe
                </p>
                <h2 className="mt-4 font-heading text-3xl font-black leading-[0.98]">
                  Mais confianca, mais clareza e menos sensacao de software generico.
                </h2>
                <div className="mt-6 space-y-3">
                  {PREMIUM_SIGNALS.map((signal) => (
                    <div
                      key={signal}
                      className="flex items-start gap-3 rounded-[22px] border border-stone-200/80 bg-white/70 px-4 py-3"
                    >
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-700" />
                      <span className="text-sm leading-6 text-stone-700">{signal}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-[34px] border border-amber-200/20 bg-[linear-gradient(135deg,#1a1410_0%,#0b1715_100%)] p-6 shadow-[0_28px_80px_rgba(0,0,0,0.24)]">
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-amber-100/70">
                  Mensagem central
                </p>
                <p className="mt-4 font-heading text-3xl font-black leading-tight text-white">
                  Atendimento mais rapido, agenda mais organizada e menos oportunidades perdidas no
                  WhatsApp.
                </p>
                <p className="mt-4 text-sm leading-7 text-white/68">
                  A clinica entende com rapidez que a plataforma ajuda a responder melhor, organizar
                  a recepcao e aumentar previsibilidade na operacao.
                </p>
              </div>
            </div>
          </div>
        </section>

        <InstantDemoHero salesWhatsappUrl={SALES_WHATSAPP_URL} loginUrl="/login" />

        <section id="solucao" className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
          <div className="rounded-[38px] border border-white/10 bg-[linear-gradient(145deg,#0a1614_0%,#10211d_60%,#152824_100%)] p-6 text-white shadow-[0_28px_90px_rgba(0,0,0,0.24)] sm:p-8">
            <SectionTag>Solucao</SectionTag>
            <div className="mt-4 grid gap-8 lg:grid-cols-[0.9fr_1.1fr]">
              <div>
                <h2 className="font-heading text-3xl font-black text-white sm:text-5xl">
                  {BRAND_NAME} conecta atendimento, agenda, equipe e recuperacao em uma experiencia
                  unica.
                </h2>
                <p className="mt-4 text-sm leading-7 text-white/70 sm:text-base">
                  Em um unico fluxo, a clinica ganha mais agilidade para atender pacientes,
                  confirmar consultas, acompanhar retornos e recuperar oportunidades.
                </p>

                <div className="mt-8 space-y-4">
                  {VALUE_PILLARS.map((pillar) => {
                    const Icon = pillar.icon;
                    return (
                      <div
                        key={pillar.title}
                        className="flex gap-4 rounded-[26px] border border-white/10 bg-white/[0.06] p-4 backdrop-blur"
                      >
                        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[#f6ead4] text-stone-950">
                          <Icon className="h-5 w-5" />
                        </div>
                        <div>
                          <h3 className="text-lg font-bold text-white">{pillar.title}</h3>
                          <p className="mt-1 text-sm leading-6 text-white/68">
                            {pillar.description}
                          </p>
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
                      "rounded-[30px] border p-5 shadow-[0_18px_45px_rgba(0,0,0,0.14)]",
                      index === 0 &&
                        "border-emerald-200/40 bg-[linear-gradient(180deg,#e9faf4_0%,#d6f5ea_100%)] text-stone-950",
                      index === 1 &&
                        "border-cyan-200/40 bg-[linear-gradient(180deg,#edf8fb_0%,#dff1f8_100%)] text-stone-950",
                      index === 2 &&
                        "border-amber-200/40 bg-[linear-gradient(180deg,#fff5e5_0%,#f9e9cb_100%)] text-stone-950",
                    )}
                  >
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">
                      Impacto real
                    </p>
                    <h3 className="mt-3 font-heading text-2xl font-black text-stone-950">
                      {result.metric}
                    </h3>
                    <p className="mt-3 text-sm leading-6 text-stone-600">{result.text}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
          <div className="grid gap-4 lg:grid-cols-4">
            <div className="rounded-[30px] border border-white/10 bg-stone-950 p-6 text-white shadow-[0_24px_80px_rgba(15,23,42,0.14)]">
              <Clock3 className="h-5 w-5 text-emerald-300" />
              <p className="mt-4 text-xs font-semibold uppercase tracking-[0.2em] text-white/55">
                Tempo
              </p>
              <h3 className="mt-2 font-heading text-3xl font-black">Menos retrabalho manual</h3>
              <p className="mt-3 text-sm leading-6 text-white/72">
                O time gasta menos energia reconstituindo contexto e mais energia conduzindo o
                paciente.
              </p>
            </div>
            <div className="rounded-[30px] border border-stone-200/80 bg-white/92 p-6 backdrop-blur">
              <TrendingUp className="h-5 w-5 text-stone-950" />
              <p className="mt-4 text-xs font-semibold uppercase tracking-[0.2em] text-stone-500">
                Crescimento
              </p>
              <h3 className="mt-2 font-heading text-3xl font-black text-stone-950">
                Mais chance de converter
              </h3>
              <p className="mt-3 text-sm leading-6 text-stone-600">
                Quando atendimento e agenda seguem um fluxo claro, a clinica perde menos
                oportunidades no meio do caminho.
              </p>
            </div>
            <div className="rounded-[30px] border border-stone-200/80 bg-white/92 p-6 backdrop-blur">
              <Workflow className="h-5 w-5 text-stone-950" />
              <p className="mt-4 text-xs font-semibold uppercase tracking-[0.2em] text-stone-500">
                Processo
              </p>
              <h3 className="mt-2 font-heading text-3xl font-black text-stone-950">
                Equipe com rotina padrao
              </h3>
              <p className="mt-3 text-sm leading-6 text-stone-600">
                Atendimento, confirmacao, comparecimento e retorno passam a seguir um caminho mais
                previsivel.
              </p>
            </div>
            <div className="rounded-[30px] border border-stone-200/80 bg-white/92 p-6 backdrop-blur">
              <BadgeCheck className="h-5 w-5 text-stone-950" />
              <p className="mt-4 text-xs font-semibold uppercase tracking-[0.2em] text-stone-500">
                Confianca
              </p>
              <h3 className="mt-2 font-heading text-3xl font-black text-stone-950">
                Plataforma com presenca profissional
              </h3>
              <p className="mt-3 text-sm leading-6 text-stone-600">
                A clinica percebe uma plataforma organizada, madura e orientada a operacao real do
                dia a dia.
              </p>
            </div>
          </div>
        </section>

        <section id="quem-somos" className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
          <div className="grid gap-6 lg:grid-cols-[0.92fr_1.08fr]">
            <div className="rounded-[34px] border border-stone-200 bg-white p-6 shadow-[0_24px_80px_rgba(15,23,42,0.08)] sm:p-8">
              <SectionTag>Quem somos</SectionTag>
              <h2 className="mt-4 text-3xl font-black text-stone-950 sm:text-4xl">
                Uma marca premium para clinicas que querem crescer com processo, IA e mais
                previsibilidade.
              </h2>
              <p className="mt-4 text-sm leading-7 text-stone-600 sm:text-base">
                A {BRAND_NAME} nasce com um posicionamento claro: ser uma plataforma SaaS moderna
                para clinicas que precisam atender pacientes com mais velocidade, agendar melhor e
                recuperar oportunidades sem sobrecarregar a equipe.
              </p>
              <p className="mt-4 text-sm leading-7 text-stone-600 sm:text-base">
                Em vez de ficar presa a um unico nicho, a plataforma atende odontologia, estetica,
                dermatologia, fisioterapia, psicologia, clinicas populares e outras areas de saude
                com a mesma base operacional.
              </p>

              <div className="mt-8 rounded-[28px] border border-stone-200 bg-stone-950 p-5 text-white">
                <div className="flex items-start gap-4">
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/10 text-emerald-200">
                    <Building2 className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-white/55">
                      Frente comercial
                    </p>
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
                  <div
                    key={item.title}
                    className="rounded-[28px] border border-stone-200 bg-[#fbf7f1] p-5"
                  >
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
              <h2 className="text-3xl font-black sm:text-4xl">
                Uma narrativa simples para mostrar o sistema na demonstracao.
              </h2>
              <p className="mt-4 text-sm leading-7 text-white/72 sm:text-base">
                A decisao fica mais facil quando a clinica enxerga o caminho completo do paciente,
                do primeiro contato ao retorno.
              </p>
            </div>

            <div className="mt-8 grid gap-4 lg:grid-cols-4">
              {JOURNEY.map((item) => (
                <div
                  key={item.step}
                  className="rounded-[28px] border border-white/10 bg-white/6 p-5 backdrop-blur"
                >
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
                A melhor forma de comecar e implantar junto, com acompanhamento real da operacao.
              </h2>
              <p className="mt-4 text-sm leading-7 text-stone-600 sm:text-base">
                Piloto assistido significa entrar na clinica, configurar o ambiente, treinar a
                equipe, acompanhar os primeiros dias e ajustar o fluxo com base no uso real. Isso
                reduz risco de implantacao e acelera resultado para a clinica.
              </p>

              <div className="mt-6 grid gap-3 sm:grid-cols-2">
                <div className="rounded-[24px] border border-stone-200 bg-[#f6efe5] p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">
                    Escopo inicial
                  </p>
                  <p className="mt-2 text-sm font-bold text-stone-950">
                    30 dias, 1 unidade piloto e rotina principal de recepcao.
                  </p>
                </div>
                <div className="rounded-[24px] border border-stone-200 bg-[#eef6f2] p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">
                    Entrega comercial
                  </p>
                  <p className="mt-2 text-sm font-bold text-stone-950">
                    Diagnostico, implantacao, treinamento e revisao final.
                  </p>
                </div>
              </div>

              <div className="mt-8 grid gap-4 sm:grid-cols-2">
                <div className="rounded-[24px] border border-stone-200 bg-[#fbf7f1] p-5">
                  <PhoneCall className="h-5 w-5 text-stone-950" />
                  <h3 className="mt-4 text-lg font-bold text-stone-950">Entrada consultiva</h3>
                  <p className="mt-2 text-sm leading-6 text-stone-600">
                    A clinica recebe implantacao acompanhada, e nao apenas acesso a mais uma
                    ferramenta.
                  </p>
                </div>
                <div className="rounded-[24px] border border-stone-200 bg-[#eef6f2] p-5">
                  <ShieldCheck className="h-5 w-5 text-stone-950" />
                  <h3 className="mt-4 text-lg font-bold text-stone-950">
                    Menor risco para a clinica
                  </h3>
                  <p className="mt-2 text-sm leading-6 text-stone-600">
                    A equipe sente mais seguranca porque o fluxo e ajustado com acompanhamento
                    proximo.
                  </p>
                </div>
                <div className="rounded-[24px] border border-stone-200 bg-[#eef3f8] p-5">
                  <Sparkles className="h-5 w-5 text-stone-950" />
                  <h3 className="mt-4 text-lg font-bold text-stone-950">Aprendizado acelerado</h3>
                  <p className="mt-2 text-sm leading-6 text-stone-600">
                    Cada implantacao ajuda a refinar processos, rotina e padrao de atendimento da
                    clinica.
                  </p>
                </div>
                <div className="rounded-[24px] border border-stone-200 bg-[#fff5e8] p-5">
                  <TrendingUp className="h-5 w-5 text-stone-950" />
                  <h3 className="mt-4 text-lg font-bold text-stone-950">
                    Base para caso de sucesso
                  </h3>
                  <p className="mt-2 text-sm leading-6 text-stone-600">
                    O piloto ajuda a construir uma operacao mais previsivel, com indicadores e
                    evolucao visivel.
                  </p>
                </div>
              </div>
            </div>

            <div className="rounded-[34px] border border-stone-200 bg-stone-950 p-6 text-white shadow-[0_24px_80px_rgba(15,23,42,0.18)] sm:p-8">
              <SectionTag>Escopo fechado</SectionTag>
              <h2 className="mt-4 text-3xl font-black sm:text-4xl">
                A clinica precisa enxergar exatamente o que entra no primeiro ciclo.
              </h2>

              <div className="mt-6 grid gap-3 sm:grid-cols-2">
                <div className="rounded-[22px] border border-white/10 bg-white/6 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-white/55">
                    Duracao
                  </p>
                  <p className="mt-2 text-lg font-black">30 dias de piloto</p>
                </div>
                <div className="rounded-[22px] border border-white/10 bg-white/6 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-white/55">
                    Cobertura
                  </p>
                  <p className="mt-2 text-lg font-black">1 unidade e 1 fluxo principal</p>
                </div>
                <div className="rounded-[22px] border border-white/10 bg-white/6 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-white/55">
                    Time
                  </p>
                  <p className="mt-2 text-lg font-black">Recepcao, agenda e lideranca</p>
                </div>
                <div className="rounded-[22px] border border-white/10 bg-white/6 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-white/55">
                    Ritmo
                  </p>
                  <p className="mt-2 text-lg font-black">Revisoes semanais</p>
                </div>
              </div>

              <div className="mt-6 space-y-4">
                {PILOT_SCOPE.map((scope) => (
                  <div
                    key={scope.title}
                    className="rounded-[26px] border border-white/10 bg-white/6 p-5"
                  >
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
                A melhor prova para a clinica e um plano de medicao claro, nao uma promessa vaga.
              </h2>
              <p className="mt-4 text-sm leading-7 text-white/72 sm:text-base">
                Desde o inicio, a clinica consegue entender que atendimento, agenda e retorno serao
                acompanhados com metodo, baseline e revisao final.
              </p>

              <div className="mt-8 grid gap-4 sm:grid-cols-2">
                {PROOF_SIGNALS.map((signal) => (
                  <div
                    key={signal.title}
                    className="rounded-[24px] border border-white/10 bg-white/6 p-5 backdrop-blur"
                  >
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-200/75">
                      Indicador acompanhado
                    </p>
                    <h3 className="mt-3 text-lg font-bold">{signal.title}</h3>
                    <p className="mt-2 text-sm leading-6 text-white/72">{signal.text}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-[34px] border border-stone-200 bg-white p-6 shadow-[0_24px_80px_rgba(15,23,42,0.08)] sm:p-8">
              <SectionTag>Caso modelo</SectionTag>
              <h2 className="mt-4 text-3xl font-black text-stone-950 sm:text-4xl">
                Um caso de 30 dias que ajuda a clinica a enxergar a evolucao com clareza.
              </h2>
              <p className="mt-4 text-sm leading-7 text-stone-600 sm:text-base">
                A jornada fica mais concreta quando a clinica enxerga como o fluxo sera implantado,
                acompanhado e medido nas primeiras semanas.
              </p>

              <div className="mt-8 rounded-[28px] border border-stone-200 bg-[#faf6ef] p-5">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">
                  Caso modelo de implantacao
                </p>
                <p className="mt-3 text-lg font-bold text-stone-950">
                  Clinica com forte dependencia de WhatsApp, agenda fragmentada e necessidade de
                  organizar recepcao e retorno sem parar a operacao.
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
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">
                    O que a clinica enxerga
                  </p>
                  <p className="mt-2 text-sm leading-6 text-stone-700">
                    Fluxo operacional mais claro, atendimento menos espalhado e proximo passo
                    definido para cada paciente.
                  </p>
                </div>
                <div className="rounded-[24px] border border-stone-200 bg-white p-5">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">
                    O que muda no dia a dia
                  </p>
                  <p className="mt-2 text-sm leading-6 text-stone-700">
                    Mais organizacao na recepcao, mais visibilidade da agenda e mais clareza sobre o
                    proximo passo de cada paciente.
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
                Escolha o formato que melhor combina com o momento operacional da sua clinica.
              </h2>
              <p className="mt-4 text-sm leading-7 text-stone-600 sm:text-base">
                A {BRAND_NAME} foi desenhada para clinicas que querem implantar com seguranca,
                organizar a equipe e evoluir atendimento e agenda com acompanhamento real.
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
                    <p
                      className={cn(
                        "mt-1 text-sm",
                        plan.highlight ? "text-white/68" : "text-stone-500",
                      )}
                    >
                      {plan.detail}
                    </p>
                  </div>

                  <div className="mt-6 space-y-3">
                    {plan.bullets.map((bullet) => (
                      <div
                        key={bullet}
                        className={cn(
                          "flex items-start gap-3 text-sm",
                          plan.highlight ? "text-white/84" : "text-stone-700",
                        )}
                      >
                        <CheckCircle2
                          className={cn(
                            "mt-0.5 h-4 w-4 shrink-0",
                            plan.highlight ? "text-emerald-300" : "text-emerald-600",
                          )}
                        />
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
                      {plan.highlight
                        ? "Quero ver a demo da minha clinica"
                        : "Falar com especialista"}
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
                <div
                  key={faq.question}
                  className="rounded-[26px] border border-stone-200 bg-[#faf6ef] p-5"
                >
                  <h3 className="text-lg font-bold text-stone-950">{faq.question}</h3>
                  <p className="mt-3 text-sm leading-6 text-stone-600">{faq.answer}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section
          id="agendar-demo"
          className="mx-auto w-full max-w-7xl px-4 pb-10 pt-10 sm:px-6 lg:px-8"
        >
          <div className="overflow-hidden rounded-[40px] border border-emerald-200 bg-[radial-gradient(circle_at_top_left,_rgba(16,185,129,0.16),_transparent_36%),linear-gradient(135deg,#ffffff_0%,#f6efe4_100%)] p-8 shadow-[0_28px_90px_rgba(15,23,42,0.1)]">
            <div className="grid gap-8 lg:grid-cols-[1.1fr_0.9fr] lg:items-start">
              <div>
                <p className="inline-flex items-center gap-2 rounded-full border border-emerald-300 bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700">
                  <ShieldCheck className="h-4 w-4" />
                  Proximo passo comercial
                </p>
                <h2 className="mt-4 max-w-3xl text-3xl font-black text-stone-950 sm:text-4xl">
                  Veja como a {BRAND_NAME} organiza o fluxo real da sua clinica e transforma
                  WhatsApp em atendimento mais organizado.
                </h2>
                <p className="mt-4 max-w-2xl text-sm leading-7 text-stone-600 sm:text-base">
                  A demonstracao parte da rotina da sua clinica, passa por atendimento, agenda,
                  recuperacao e retorno, e mostra como a operacao pode ganhar mais previsibilidade.
                </p>

                <div className="mt-8 grid gap-4 sm:grid-cols-2">
                  <div className="rounded-[26px] border border-stone-200 bg-white/90 p-5 backdrop-blur">
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-stone-950 text-white">
                      <PlayCircle className="h-5 w-5" />
                    </div>
                    <h3 className="mt-4 text-lg font-bold text-stone-950">Ver demonstracao</h3>
                    <p className="mt-2 text-sm leading-6 text-stone-600">
                      Veja o ambiente real, identifique gargalos do atendimento e entenda como a IA
                      ajuda a responder, agendar e acompanhar melhor.
                    </p>
                    <div className="mt-5">
                      <ActionLink href={SALES_DEMO_URL} className="w-full sm:w-auto">
                        Ver demonstracao guiada
                        <ArrowRight className="ml-2 h-4 w-4" />
                      </ActionLink>
                    </div>
                  </div>

                  <div
                    id="contato"
                    className="rounded-[26px] border border-stone-200 bg-white/90 p-5 backdrop-blur"
                  >
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-stone-950 text-white">
                      <PhoneCall className="h-5 w-5" />
                    </div>
                    <h3 className="mt-4 text-lg font-bold text-stone-950">
                      Simular conversa no WhatsApp
                    </h3>
                    <p className="mt-2 text-sm leading-6 text-stone-600">
                      Se preferir, fale direto com um especialista e compartilhe rotina, equipe e
                      gargalos para acelerar o diagnostico.
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
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">
                  Contato e confianca
                </p>

                <div className="mt-5 rounded-[24px] border border-stone-200 bg-stone-950 p-5 text-white">
                  <p className="text-xl font-black">{SALES_CONTACT_NAME}</p>
                  <p className="mt-1 text-sm text-white/72">{SALES_CONTACT_ROLE}</p>
                  <p className="mt-3 text-sm text-white/62">{SALES_CONTACT_REGION}</p>
                </div>

                <div className="mt-5 space-y-3">
                  <div className="flex items-center justify-between gap-3 rounded-[22px] border border-stone-200 bg-white px-4 py-3">
                    <div className="flex items-center gap-3">
                      <Mail className="h-4 w-4 text-stone-700" />
                      <span className="text-sm font-semibold text-stone-900">
                        {SALES_EMAIL_LABEL}
                      </span>
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
                      <span className="text-sm font-semibold text-stone-900">
                        Piloto assistido com implantacao guiada
                      </span>
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
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">
                    O que levar para a demo
                  </p>
                  <div className="mt-4 space-y-3 text-sm leading-6 text-stone-700">
                    <p>1. Qual unidade ou operacao da clinica precisa ser organizada primeiro.</p>
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
                <p className="text-[10px] font-semibold uppercase tracking-[0.24em] text-white/45">
                  {BRAND_NAME}
                </p>
                <h2 className="mt-3 text-2xl font-black">{BRAND_TAGLINE}</h2>
                <p className="mt-4 max-w-xl text-sm leading-7 text-white/70">
                  Atendimento, qualificacao, agenda, recuperacao e acompanhamento em um mesmo fluxo
                  de operacao real.
                </p>
              </div>

              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-white/45">
                  Acessos rapidos
                </p>
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
                      Entrar na plataforma
                    </Link>
                  </p>
                  <p>
                    <Link href="/politica-de-privacidade" className="transition hover:text-white">
                      Politica de privacidade
                    </Link>
                  </p>
                  <p>
                    <Link href="/termos-de-uso" className="transition hover:text-white">
                      Termos de uso
                    </Link>
                  </p>
                </div>
              </div>

              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-white/45">
                  Sinais de confianca
                </p>
                <div className="mt-4 space-y-3 text-sm leading-6 text-white/72">
                  <p>Implantacao assistida com escopo inicial claro.</p>
                  <p>Fluxo completo de lead, agenda, comparecimento e retorno.</p>
                  <p>Configuracoes de seguranca, LGPD e operacao ja previstas no produto.</p>
                  <p>
                    Documentos legais publicos para consulta:{" "}
                    <Link
                      href="/politica-de-privacidade"
                      className="font-semibold text-white transition hover:text-emerald-200"
                    >
                      privacidade
                    </Link>{" "}
                    e{" "}
                    <Link
                      href="/termos-de-uso"
                      className="font-semibold text-white transition hover:text-emerald-200"
                    >
                      termos
                    </Link>
                    .
                  </p>
                </div>
              </div>
            </div>
          </footer>
        </section>
      </main>
    </div>
  );
}

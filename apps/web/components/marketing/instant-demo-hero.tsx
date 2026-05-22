"use client";

import { type ReactNode, useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  LoaderCircle,
  MessageSquareText,
  PhoneCall,
  PlayCircle,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { cn } from "@odontoflux/ui";

import { api } from "@/lib/api";
import { BRAND_DESCRIPTION, BRAND_NAME } from "@/lib/brand";

type QuickDemoResponse = {
  prospect: {
    clinic_name: string;
    owner_name?: string | null;
  };
  status: "created" | "reused";
  demo_login_url: string;
  demo_booking_path?: string | null;
  demo_booking_url?: string | null;
};

type InstantDemoHeroProps = {
  salesWhatsappUrl: string;
  loginUrl: string;
};

type FormState = {
  clinic_name: string;
  owner_name: string;
  phone: string;
};

const DEFAULT_FORM: FormState = {
  clinic_name: "",
  owner_name: "",
  phone: "",
};

const TRUST_POINTS = [
  "Crie uma demo real da sua clinica em menos de 1 minuto.",
  "Abra a demo pronta e veja o ambiente com agenda, operacao e atendimento.",
  "Acesse o agendamento oficial e simule o fluxo como se fosse um paciente.",
];

const HERO_METRICS = [
  {
    label: "Cadastro rapido",
    value: "< 1 min",
    detail: "Nome da clinica, responsavel e telefone.",
  },
  {
    label: "Entrega imediata",
    value: "2 links",
    detail: "Demo pronta + agendamento para testar na hora.",
  },
  {
    label: "Experiencia real",
    value: "Fluxo vivo",
    detail: "Veja a operacao e simule a jornada do paciente.",
  },
];

function extractApiErrorMessage(error: unknown, fallback: string) {
  const response = (
    error as {
      response?: {
        data?: {
          error?: {
            message?: string;
          };
        };
      };
    }
  ).response;
  return response?.data?.error?.message?.trim() || fallback;
}

function ProgressRing({ value }: { value: number }) {
  const normalizedValue = Math.min(100, Math.max(0, value));
  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  const strokeOffset = circumference - (normalizedValue / 100) * circumference;

  return (
    <div className="relative flex h-36 w-36 items-center justify-center">
      <svg viewBox="0 0 128 128" className="-rotate-90 h-36 w-36">
        <circle cx="64" cy="64" r={radius} stroke="rgba(15,23,42,0.08)" strokeWidth="10" fill="none" />
        <circle
          cx="64"
          cy="64"
          r={radius}
          stroke="url(#instant-demo-progress)"
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={strokeOffset}
          fill="none"
          className="transition-[stroke-dashoffset] duration-300 ease-out"
        />
        <defs>
          <linearGradient id="instant-demo-progress" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#0f766e" />
            <stop offset="55%" stopColor="#14b8a6" />
            <stop offset="100%" stopColor="#f59e0b" />
          </linearGradient>
        </defs>
      </svg>
      <div className="absolute text-center">
        <p className="text-3xl font-black text-stone-950">{Math.round(normalizedValue)}%</p>
        <p className="mt-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">criando demo</p>
      </div>
    </div>
  );
}

function QuickAction({
  href,
  label,
  variant = "solid",
  icon,
}: {
  href: string;
  label: string;
  variant?: "solid" | "outline";
  icon: ReactNode;
}) {
  return (
    <a
      href={href}
      className={cn(
        "inline-flex w-full items-center justify-center gap-2 rounded-full px-5 py-3 text-sm font-semibold transition sm:w-auto",
        variant === "solid"
          ? "bg-stone-950 text-white hover:bg-emerald-900"
          : "border border-stone-300 bg-white text-stone-950 hover:bg-stone-100",
      )}
    >
      {icon}
      {label}
    </a>
  );
}

export function InstantDemoHero({ salesWhatsappUrl, loginUrl }: InstantDemoHeroProps) {
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [errorMessage, setErrorMessage] = useState("");
  const [result, setResult] = useState<QuickDemoResponse | null>(null);

  const canSubmit = useMemo(() => {
    return (
      form.clinic_name.trim().length >= 2 &&
      form.owner_name.trim().length >= 2 &&
      form.phone.trim().length >= 8 &&
      !isSubmitting
    );
  }, [form, isSubmitting]);

  useEffect(() => {
    if (!isSubmitting) return;
    setProgress(14);
    const timer = window.setInterval(() => {
      setProgress((current) => {
        if (current >= 92) return current;
        if (current < 46) return current + 8;
        if (current < 74) return current + 5;
        return current + 2;
      });
    }, 220);
    return () => window.clearInterval(timer);
  }, [isSubmitting]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;

    setErrorMessage("");
    setResult(null);
    setIsSubmitting(true);

    try {
      const response = await api.post<QuickDemoResponse>("/public/site/quick-demo", {
        clinic_name: form.clinic_name.trim(),
        owner_name: form.owner_name.trim(),
        phone: form.phone.trim(),
      });
      setProgress(100);
      setResult(response.data);
    } catch (error) {
      setErrorMessage(extractApiErrorMessage(error, "Nao foi possivel criar sua demo agora."));
      setProgress(0);
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleReset() {
    setForm(DEFAULT_FORM);
    setResult(null);
    setErrorMessage("");
    setProgress(0);
  }

  return (
    <section id="demo-rapida" className="mx-auto w-full max-w-7xl px-4 pb-12 pt-10 sm:px-6 lg:px-8 lg:pb-18 lg:pt-14">
      <div className="relative overflow-hidden rounded-[42px] border border-emerald-300/20 bg-[radial-gradient(circle_at_top_left,_rgba(45,212,191,0.28),_transparent_24%),radial-gradient(circle_at_bottom_left,_rgba(251,191,36,0.22),_transparent_20%),linear-gradient(135deg,#09231d_0%,#0a3a31_44%,#0f172a_100%)] px-5 py-6 shadow-[0_36px_120px_rgba(2,6,23,0.28)] sm:px-7 sm:py-8 lg:px-10 lg:py-10">
        <div className="pointer-events-none absolute -right-12 top-10 h-44 w-44 rounded-full bg-amber-300/20 blur-3xl" />
        <div className="pointer-events-none absolute bottom-6 left-6 h-36 w-36 rounded-full bg-teal-300/18 blur-3xl" />

        <div className="relative grid gap-8 lg:grid-cols-[1.02fr_0.98fr] lg:items-start">
          <div className="pt-2">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/14 bg-white/8 px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.22em] text-emerald-100">
              <Sparkles className="h-4 w-4" />
              Demo imediata para clinicas
            </div>

            <h1 className="mt-6 max-w-4xl font-heading text-4xl font-black leading-[0.98] text-white sm:text-5xl lg:text-[4.6rem]">
              Crie sua demo e teste o agendamento da clinica em menos de 1 minuto.
            </h1>

            <p className="mt-5 max-w-2xl text-base leading-7 text-white/76 sm:text-lg">
              {BRAND_DESCRIPTION}
            </p>

            <p className="mt-4 max-w-2xl text-base leading-7 text-white/76 sm:text-lg">
              Preencha os dados da clinica, gere sua demo agora e saia daqui com dois acessos prontos: a demo do
              sistema e o agendamento oficial para simular a jornada de um paciente.
            </p>

            <div className="mt-8 grid gap-3 sm:grid-cols-3">
              {HERO_METRICS.map((metric) => (
                <div key={metric.label} className="rounded-[26px] border border-white/12 bg-white/8 p-4 backdrop-blur">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-white/56">{metric.label}</p>
                  <p className="mt-2 text-2xl font-black text-white">{metric.value}</p>
                  <p className="mt-2 text-sm leading-6 text-white/72">{metric.detail}</p>
                </div>
              ))}
            </div>

            <div className="mt-8 grid gap-3 sm:grid-cols-3">
              {TRUST_POINTS.map((item) => (
                <div key={item} className="rounded-[22px] border border-white/10 bg-white/6 p-4 text-sm text-white/82">
                  <div className="flex items-start gap-3">
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" />
                    <span>{item}</span>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-8 flex flex-wrap gap-3">
              <a
                href={salesWhatsappUrl}
                className="inline-flex items-center justify-center rounded-full border border-white/14 bg-white/8 px-5 py-3 text-sm font-semibold text-white transition hover:bg-white/14"
              >
                <PhoneCall className="mr-2 h-4 w-4" />
                Falar com especialista
              </a>
              <a
                href={loginUrl}
                className="inline-flex items-center justify-center rounded-full border border-white/14 px-5 py-3 text-sm font-semibold text-white/78 transition hover:border-white/22 hover:bg-white/8 hover:text-white"
              >
                <ShieldCheck className="mr-2 h-4 w-4" />
                Entrar na plataforma
              </a>
            </div>
          </div>

          <div className="relative">
            <div className="rounded-[34px] border border-white/16 bg-white/92 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.2)] backdrop-blur sm:p-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-emerald-700">Ative a sua demo agora</p>
                  <h2 className="mt-2 text-2xl font-black text-stone-950">Crie e acesse em menos de 1 minuto</h2>
                </div>
                <div className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald-700">
                  Demo + agendamento
                </div>
              </div>

              <p className="mt-4 text-sm leading-6 text-stone-600">
                Cadastre sua clinica, gere a demo e teste o fluxo como dono da operacao e tambem como paciente.
              </p>

              {result ? (
                <div className="mt-6 rounded-[28px] border border-emerald-200 bg-[linear-gradient(180deg,#f8fffd_0%,#eefbf7_100%)] p-5">
                  <div className="flex items-start gap-3">
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-stone-950 text-white">
                      <CheckCircle2 className="h-6 w-6 text-emerald-300" />
                    </div>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700">
                        {result.status === "reused" ? "Acesso renovado" : "Demo criada"}
                      </p>
                      <h3 className="mt-2 text-2xl font-black text-stone-950">{result.prospect.clinic_name}</h3>
                      <p className="mt-2 text-sm leading-6 text-stone-600">
                        {result.status === "reused"
                          ? "Encontramos a sua clinica e renovamos o acesso da demo para voce continuar de onde parou."
                          : "Sua demo foi criada com sucesso. Agora voce ja pode abrir o sistema e testar o agendamento como paciente."}
                      </p>
                    </div>
                  </div>

                  <div className="mt-6 grid gap-3 sm:grid-cols-2">
                    <QuickAction
                      href={result.demo_login_url}
                      label="Abrir demo"
                      icon={<PlayCircle className="h-4 w-4" />}
                    />
                    <QuickAction
                      href={result.demo_booking_url || result.demo_booking_path || "#"}
                      label="Acessar agendamento"
                      variant="outline"
                      icon={<CalendarDays className="h-4 w-4" />}
                    />
                  </div>

                  <div className="mt-5 rounded-[22px] border border-emerald-200 bg-white px-4 py-3 text-sm text-stone-700">
                    <div className="flex items-start gap-3">
                      <MessageSquareText className="mt-0.5 h-4 w-4 shrink-0 text-emerald-700" />
                      <span>Use o agendamento para simular o teste como cliente e sentir o fluxo completo da clinica.</span>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={handleReset}
                    className="mt-5 inline-flex items-center rounded-full border border-stone-300 px-4 py-2 text-sm font-semibold text-stone-900 transition hover:bg-stone-100"
                  >
                    Gerar outra demo
                  </button>
                </div>
              ) : isSubmitting ? (
                <div className="mt-6 rounded-[28px] border border-stone-200 bg-[#fffdf9] p-6">
                  <div className="flex flex-col items-center text-center">
                    <ProgressRing value={progress} />
                    <p className="mt-5 text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700">Criando a demo da sua clinica</p>
                    <h3 className="mt-2 text-2xl font-black text-stone-950">Montando acessos, agenda e simulacao</h3>
                    <p className="mt-3 max-w-md text-sm leading-6 text-stone-600">
                      Estamos preparando a demo, o acesso ao sistema e o link direto do agendamento para voce testar a
                      experiencia completa.
                    </p>
                    <div className="mt-4 inline-flex items-center gap-2 rounded-full border border-stone-200 bg-white px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-stone-500">
                      <LoaderCircle className="h-4 w-4 animate-spin text-emerald-700" />
                      isso costuma levar menos de 1 minuto
                    </div>
                  </div>
                </div>
              ) : (
                <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
                  <div className="grid gap-4">
                    <label className="grid gap-2">
                      <span className="text-sm font-semibold text-stone-900">Nome da clinica</span>
                      <input
                        type="text"
                        value={form.clinic_name}
                        onChange={(event) => setForm((current) => ({ ...current, clinic_name: event.target.value }))}
                        placeholder="Ex.: Clinica Sorriso Prime"
                        className="h-14 rounded-2xl border border-stone-200 bg-white px-4 text-sm text-stone-900 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200"
                      />
                    </label>

                    <label className="grid gap-2">
                      <span className="text-sm font-semibold text-stone-900">Responsavel ou dono</span>
                      <input
                        type="text"
                        value={form.owner_name}
                        onChange={(event) => setForm((current) => ({ ...current, owner_name: event.target.value }))}
                        placeholder="Ex.: Dra. Mariana Costa"
                        className="h-14 rounded-2xl border border-stone-200 bg-white px-4 text-sm text-stone-900 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200"
                      />
                    </label>

                    <label className="grid gap-2">
                      <span className="text-sm font-semibold text-stone-900">Telefone para contato</span>
                      <input
                        type="tel"
                        value={form.phone}
                        onChange={(event) => setForm((current) => ({ ...current, phone: event.target.value }))}
                        placeholder="Ex.: (11) 99999-1111"
                        className="h-14 rounded-2xl border border-stone-200 bg-white px-4 text-sm text-stone-900 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200"
                      />
                    </label>
                  </div>

                  <button
                    type="submit"
                    disabled={!canSubmit}
                    className="inline-flex min-h-14 w-full items-center justify-center rounded-full bg-stone-950 px-5 py-3 text-base font-semibold text-white transition hover:bg-emerald-900 disabled:cursor-not-allowed disabled:opacity-55"
                  >
                    Criar demo
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </button>

                  {errorMessage ? (
                    <div className="rounded-[22px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
                      {errorMessage}
                    </div>
                  ) : null}

                  <div className="rounded-[22px] border border-stone-200 bg-[#faf6ef] p-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">O que voce recebe ao clicar</p>
                    <div className="mt-3 space-y-3 text-sm leading-6 text-stone-700">
                      <div className="flex items-start gap-3">
                        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-700" />
                        <span>Um acesso direto para abrir a demo da sua clinica.</span>
                      </div>
                      <div className="flex items-start gap-3">
                        <CalendarDays className="mt-0.5 h-4 w-4 shrink-0 text-emerald-700" />
                        <span>Um link do agendamento para simular o fluxo como paciente.</span>
                      </div>
                    </div>
                  </div>
                </form>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

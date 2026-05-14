"use client";

import { ArrowRight, BadgeCheck, Sparkles } from "lucide-react";
import { Badge, Button } from "@odontoflux/ui";

import { DemoProgress, type DemoPreparationStep } from "@/components/auth/demo-progress";

type DemoPreparationScreenProps = {
  activeStep: number;
  errorMessage?: string | null;
  etaLabel: string;
  onRetry?: () => void;
  onShowManualLogin?: () => void;
  phase: "idle" | "redeeming" | "success" | "error";
  progress: number;
  steps: DemoPreparationStep[];
};

function resolvePhaseCopy(
  phase: DemoPreparationScreenProps["phase"],
  errorMessage?: string | null,
) {
  if (phase === "success") {
    return {
      eyebrow: "Demo pronta",
      title: "Sua demo esta pronta",
      body: "Abrindo o ambiente agora.",
    };
  }

  if (phase === "error") {
    return {
      eyebrow: "Falha na liberacao",
      title: "Nao foi possivel abrir esta demo",
      body: errorMessage || "Tente novamente ou use o login manual.",
    };
  }

  return {
    eyebrow: "Preparando sua demo",
    title: "IA para clinicas odontologicas.",
    body: "Isso leva so alguns segundos.",
  };
}

export function DemoPreparationScreen({
  activeStep,
  errorMessage,
  etaLabel,
  onRetry,
  onShowManualLogin,
  phase,
  progress,
  steps,
}: DemoPreparationScreenProps) {
  const phaseCopy = resolvePhaseCopy(phase, errorMessage);
  const currentStep = steps[Math.min(activeStep, steps.length - 1)];

  return (
    <section
      className="auth-demo-shell auth-reveal relative overflow-hidden rounded-[34px] border border-[#cfe4e7] bg-[#f7fbfb] text-slate-900 shadow-[0_40px_120px_rgba(15,55,72,0.16)]"
      data-testid="demo-preparation-screen"
    >
      <div
        aria-hidden
        className="auth-aurora auth-aurora-primary absolute inset-y-[-18%] left-[-8%] w-[44%] rounded-full blur-3xl"
      />
      <div
        aria-hidden
        className="auth-aurora auth-aurora-secondary absolute bottom-[-30%] right-[-8%] top-[20%] w-[36%] rounded-full blur-3xl"
      />
      <div aria-hidden className="auth-grain pointer-events-none absolute inset-0" />

      <div className="relative mx-auto flex min-h-[560px] max-w-3xl flex-col justify-center px-6 py-10 sm:px-8 sm:py-12">
        <div className="mx-auto w-full max-w-2xl text-center">
          <div className="auth-reveal flex flex-wrap items-center justify-center gap-3">
            <Badge className="border-[#b8d8d7] bg-white/80 px-3 py-1 text-[11px] uppercase tracking-[0.28em] text-[#2b6f73]">
              OdontoFlux
            </Badge>
            <div className="inline-flex items-center gap-2 rounded-full border border-[#cfe4e7] bg-white/80 px-3 py-1 text-xs font-medium text-slate-700 shadow-[0_6px_24px_rgba(34,94,105,0.08)]">
              <Sparkles className="h-3.5 w-3.5 text-[#49a7b5]" />
              <span>{phaseCopy.eyebrow}</span>
            </div>
          </div>

          <div className="auth-reveal mt-6 space-y-4">
            <h1 className="mx-auto max-w-2xl text-4xl font-semibold leading-[1.02] tracking-[-0.03em] text-[#12343a] sm:text-5xl">
              {phaseCopy.title}
            </h1>
            <p className="mx-auto max-w-xl text-base leading-7 text-slate-600 sm:text-lg">
              {phaseCopy.body}
            </p>
          </div>

          <div className="auth-reveal mt-8 rounded-[28px] border border-[#d8ebec] bg-white/84 p-5 shadow-[0_24px_80px_rgba(31,88,102,0.12)] backdrop-blur-xl sm:p-6">
            <div
              key={`${phase}-${activeStep}`}
              className="auth-copy-swap rounded-[24px] border border-[#d2e8eb] bg-[linear-gradient(135deg,rgba(232,247,248,0.96),rgba(245,251,252,0.98))] px-5 py-4 text-left"
            >
              <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-[#4d8f96]">
                Agora
              </p>
              <p className="mt-3 text-2xl font-semibold text-[#15383f]">{currentStep.title}</p>
              <p className="mt-2 text-sm leading-6 text-slate-600">{currentStep.detail}</p>
            </div>

            <div className="mt-5">
              <DemoProgress
                activeStep={activeStep}
                etaLabel={etaLabel}
                phase={phase}
                progress={progress}
                steps={steps}
              />
            </div>
          </div>

          {phase === "error" ? (
            <div className="auth-reveal mt-6 flex flex-col items-center gap-3">
              <p className="max-w-lg text-sm leading-6 text-slate-600">
                O link pode ter expirado ou ja ter sido utilizado. Escolha abaixo como deseja
                continuar.
              </p>
              <div className="flex flex-wrap justify-center gap-3">
                <Button
                  className="bg-[#1f7a86] text-white hover:bg-[#176772]"
                  type="button"
                  onClick={onRetry}
                >
                  Tentar novamente
                </Button>
                <Button
                  className="border-[#c7dde1] bg-white text-slate-700 hover:bg-[#f3f9fa]"
                  type="button"
                  variant="outline"
                  onClick={onShowManualLogin}
                >
                  Abrir login manual
                </Button>
              </div>
            </div>
          ) : (
            <div className="auth-reveal mt-6 inline-flex items-center gap-2 rounded-full border border-[#d0e5e8] bg-white/80 px-4 py-2 text-sm font-medium text-slate-700 shadow-[0_10px_30px_rgba(31,88,102,0.08)]">
              {phase === "success" ? (
                <BadgeCheck className="h-4 w-4 text-[#1f7a86]" />
              ) : (
                <ArrowRight className="h-4 w-4 text-[#1f7a86]" />
              )}
              <span>
                {phase === "success"
                  ? "Redirecionando voce agora."
                  : "Voce sera redirecionado automaticamente assim que a preparacao terminar."}
              </span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

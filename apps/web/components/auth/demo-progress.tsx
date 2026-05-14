"use client";

import { Clock3 } from "lucide-react";

export type DemoPreparationStep = {
  title: string;
  detail: string;
};

type DemoProgressProps = {
  activeStep: number;
  etaLabel: string;
  phase: "idle" | "redeeming" | "success" | "error";
  progress: number;
  steps: DemoPreparationStep[];
};

export function DemoProgress({ activeStep, etaLabel, phase, progress, steps }: DemoProgressProps) {
  const safeProgress = Math.max(6, Math.min(progress, 100));
  const stepLabel =
    phase === "success"
      ? "Demo pronta"
      : phase === "error"
        ? "Aguardando nova tentativa"
        : `Etapa ${Math.min(activeStep + 1, steps.length)} de ${steps.length}`;

  return (
    <div className="rounded-[22px] border border-[#d6e8ea] bg-[#fdfefe] p-4 shadow-[0_12px_36px_rgba(31,88,102,0.08)]">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs font-semibold uppercase tracking-[0.28em] text-[#4d8f96]">
          Progresso
        </p>

        <div className="inline-flex items-center gap-2 rounded-full border border-[#cfe3e6] bg-[#f1f8f9] px-3 py-1 text-xs font-medium text-[#2b6f73]">
          <Clock3 className="h-3.5 w-3.5" />
          <span>{etaLabel}</span>
        </div>
      </div>

      <div className="mt-4">
        <div className="h-2.5 overflow-hidden rounded-full bg-[#dcebed]">
          <div
            className="auth-progress-glow h-full rounded-full bg-gradient-to-r from-[#75d9d5] via-[#4ec6cf] to-[#5aa9d6] transition-[width] duration-700 ease-out"
            style={{ width: `${safeProgress}%` }}
          />
        </div>

        <div className="mt-3 flex items-center justify-between gap-3 text-xs">
          <span className="font-medium text-[#16383f]">{stepLabel}</span>
          <span className="text-slate-500">
            {phase === "success" ? "Concluido" : `${Math.round(safeProgress)}%`}
          </span>
        </div>
      </div>
    </div>
  );
}

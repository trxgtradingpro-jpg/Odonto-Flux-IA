"use client";

import { ArrowRight, CalendarPlus, MessageCircleMore, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";

import { Button } from "@odontoflux/ui";

type FinalCtaCardProps = {
  onPauseToggle?: () => void;
  onRestart?: () => void;
  onSkip?: () => void;
};

export function FinalCtaCard(_: FinalCtaCardProps) {
  const router = useRouter();

  const openPresentation = (intent: string) => {
    router.push(`/apresentacao?origem=demo_guiada&cta=${intent}`);
  };

  return (
    <div className="fixed inset-0 z-[94] flex items-center justify-center bg-[rgba(6,37,31,0.72)] px-4 py-6 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-[36px] border border-white/55 bg-[linear-gradient(180deg,rgba(247,255,252,0.98),rgba(255,255,255,0.96))] p-6 shadow-[0_38px_120px_rgba(6,37,31,0.26)] sm:p-8">
        <div className="inline-flex items-center gap-2 rounded-full border border-[color:var(--tenant-primary)]/18 bg-[color:var(--tenant-primary)]/8 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-[color:var(--tenant-primary)]">
          <Sparkles size={14} />
          Demo concluida
        </div>

        <h2 className="mt-5 text-3xl font-semibold tracking-tight text-[color:var(--text-primary)]">
          Veja como isso funcionaria na sua clínica.
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-7 text-[color:var(--text-secondary)]">
          A operação já mostrou o valor em tempo real. Agora o próximo passo é transformar isso em rotina dentro da sua clínica.
        </p>

        <div className="mt-6 grid gap-3 sm:grid-cols-3">
          <Button className="h-11 rounded-full" onClick={() => openPresentation("agendar_apresentacao")}>
            <CalendarPlus size={16} />
            Agendar apresentacao
          </Button>
          <Button variant="outline" className="h-11 rounded-full" onClick={() => openPresentation("solicitar_implantacao")}>
            <ArrowRight size={16} />
            Solicitar implantacao
          </Button>
          <Button variant="outline" className="h-11 rounded-full" onClick={() => openPresentation("falar_com_especialista")}>
            <MessageCircleMore size={16} />
            Falar com especialista
          </Button>
        </div>
      </div>
    </div>
  );
}

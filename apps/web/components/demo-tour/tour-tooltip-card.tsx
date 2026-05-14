"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Loader2, Sparkles } from "lucide-react";

import { Button, cn } from "@odontoflux/ui";

type TourTooltipAction = {
  label: string;
  onClick: () => void;
};

type TourTooltipCardProps = {
  badge?: string;
  title: string;
  description: ReactNode;
  primaryLabel?: string;
  secondaryLabel?: string;
  statusLabel?: string;
  testActions?: TourTooltipAction[];
  compact?: boolean;
  primaryLoading?: boolean;
  visualState?: "idle" | "exiting";
  onPrimaryAction?: () => void;
  onSecondaryAction?: () => void;
};

export function TourTooltipCard({
  badge = "Demo guiada",
  title,
  description,
  primaryLabel,
  secondaryLabel,
  statusLabel,
  testActions = [],
  compact = false,
  primaryLoading = false,
  visualState = "idle",
  onPrimaryAction,
  onSecondaryAction,
}: TourTooltipCardProps) {
  const [entered, setEntered] = useState(false);

  useEffect(() => {
    setEntered(false);
    const frameId = window.requestAnimationFrame(() => setEntered(true));
    return () => window.cancelAnimationFrame(frameId);
  }, [badge, title]);

  return (
    <div
      className={cn(
        "w-full rounded-[28px] border border-white/60 bg-[linear-gradient(180deg,rgba(247,255,252,0.98),rgba(255,255,255,0.96))] p-4 text-left shadow-[0_28px_90px_rgba(6,37,31,0.18)] backdrop-blur-xl transition-all duration-300 ease-out",
        entered ? "translate-y-0 opacity-100 blur-0" : "translate-y-3 opacity-0 blur-[2px]",
        visualState === "exiting" && "translate-y-2 scale-[0.96] opacity-0 blur-[3px]",
      )}
    >
      <div className="flex items-start gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-[color:var(--tenant-primary)]/10 text-[color:var(--tenant-primary)]">
          <Sparkles size={18} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-[color:var(--tenant-primary)]/20 bg-[color:var(--tenant-primary)]/8 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-[color:var(--tenant-primary)]">
              {badge}
            </span>
          </div>
          <h3 className="mt-3 text-lg font-semibold tracking-tight text-[color:var(--text-primary)]">{title}</h3>
          <div className="mt-2 text-sm leading-6 text-[color:var(--text-secondary)]">{description}</div>
        </div>
      </div>

      {statusLabel ? (
        <div className="mt-4 flex justify-center">
          <span className="rounded-full border border-[color:var(--tenant-primary)]/18 bg-[color:var(--tenant-primary)]/7 px-3 py-1 text-[11px] font-medium tracking-[0.06em] text-[color:var(--text-secondary)]">
            {statusLabel}
          </span>
        </div>
      ) : null}

      <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
        {secondaryLabel && onSecondaryAction ? (
          <Button variant="outline" className="h-9 rounded-full px-3 text-xs" onClick={onSecondaryAction}>
            {secondaryLabel}
          </Button>
        ) : null}
        {primaryLabel && onPrimaryAction ? (
          <Button
            className="h-9 rounded-full px-4 text-xs transition-opacity duration-200 hover:opacity-95"
            onClick={onPrimaryAction}
            disabled={primaryLoading}
          >
            {primaryLoading ? <Loader2 size={14} className="animate-spin" /> : null}
            <span className={cn(primaryLoading && "opacity-75")}>{primaryLabel}</span>
          </Button>
        ) : null}
      </div>

      {testActions.length ? (
        <div className="mt-3 flex flex-wrap items-center justify-center gap-2 border-t border-[color:var(--border-soft)]/55 pt-3">
          {testActions.map((action) => (
            <Button
              key={action.label}
              variant="outline"
              className="h-8 rounded-full px-3 text-[11px] font-medium"
              onClick={action.onClick}
            >
              {action.label}
            </Button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

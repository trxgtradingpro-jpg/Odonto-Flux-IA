"use client";

import { CalendarDays, MessageSquare, UsersRound } from "lucide-react";
import { usePathname } from "next/navigation";

import { cn } from "@odontoflux/ui";

import { QUICK_FOCUS_PAGE_LABELS, QuickFocusPageKey } from "./quick-focus-pages";

const QUICK_ACCESS_ICONS = {
  conversas: MessageSquare,
  agenda: CalendarDays,
  pacientes: UsersRound,
} satisfies Record<QuickFocusPageKey, typeof MessageSquare>;

const QUICK_ACCESS_HREFS: Record<QuickFocusPageKey, string> = {
  conversas: "/conversas",
  agenda: "/agenda",
  pacientes: "/pacientes",
};

export function QuickAccessPill({
  pages,
  onOpen,
  className,
  labels = "responsive",
  tone = "default",
}: {
  pages: QuickFocusPageKey[];
  onOpen: (pageKey: QuickFocusPageKey) => void;
  className?: string;
  labels?: "always" | "responsive";
  tone?: "default" | "floating";
}) {
  const pathname = usePathname();
  if (!pages.length) return null;
  const isFloating = tone === "floating";

  return (
    <div
      className={cn(
        "items-center gap-1.5 rounded-2xl border p-1.5 backdrop-blur-xl",
        isFloating
          ? "border-primary/70 bg-primary/95 shadow-[0_18px_46px_rgba(15,23,42,0.28)] ring-1 ring-white/25"
          : "border-primary/20 bg-[linear-gradient(135deg,rgba(255,255,255,0.98),rgba(240,253,250,0.94))] shadow-[0_14px_34px_rgba(15,23,42,0.08)] ring-1 ring-primary/10",
        className,
      )}
    >
      {pages.map((pageKey) => {
        const Icon = QUICK_ACCESS_ICONS[pageKey];
        const active = pathname === QUICK_ACCESS_HREFS[pageKey];
        return (
          <button
            key={pageKey}
            type="button"
            data-quick-focus-key={pageKey}
            className={cn(
              "inline-flex h-9 items-center gap-2 rounded-xl border px-3 text-xs font-semibold transition duration-150",
              isFloating
                ? active
                  ? "border-white/25 bg-white/18 text-white shadow-[0_10px_24px_rgba(255,255,255,0.16)]"
                  : "border-white/10 text-white/92 hover:bg-white/10 active:bg-white/20"
                : active
                  ? "border-primary/60 text-white shadow-[0_14px_28px_rgba(13,148,136,0.26)]"
                  : "border-primary/10 bg-white/88 text-stone-700 shadow-[0_6px_16px_rgba(15,23,42,0.06)] hover:-translate-y-px hover:border-primary/30 hover:bg-primary/10 hover:text-primary",
            )}
            style={
              isFloating
                ? {
                    color: "rgb(var(--theme-primary-foreground))",
                  }
                : active
                  ? {
                      backgroundImage:
                        "linear-gradient(135deg, var(--tenant-primary), color-mix(in srgb, var(--tenant-secondary) 72%, white 28%))",
                    }
                  : undefined
            }
            onClick={() => onOpen(pageKey)}
            title={`Abrir ${QUICK_FOCUS_PAGE_LABELS[pageKey]} em tela cheia`}
          >
            <span
              className={cn(
                "grid h-5 w-5 place-items-center rounded-full transition",
                isFloating
                  ? active
                    ? "bg-white/20"
                    : "bg-white/10"
                  : active
                    ? "bg-white/18"
                    : "bg-primary/10 text-primary",
              )}
            >
              <Icon size={13} />
            </span>
            <span className={labels === "always" ? "inline" : "hidden xl:inline"}>
              {QUICK_FOCUS_PAGE_LABELS[pageKey]}
            </span>
          </button>
        );
      })}
    </div>
  );
}

import type { PageKey } from "@/lib/page-access";

export const QUICK_FOCUS_PAGE_KEYS = ["conversas", "agenda", "pacientes"] as const satisfies readonly PageKey[];

export type QuickFocusPageKey = (typeof QUICK_FOCUS_PAGE_KEYS)[number];

export const QUICK_FOCUS_PAGE_LABELS: Record<QuickFocusPageKey, string> = {
  conversas: "WhatsApp",
  agenda: "Agenda",
  pacientes: "Pacientes",
};

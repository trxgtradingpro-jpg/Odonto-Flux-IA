"use client";

import { Badge, cn } from "@odontoflux/ui";

const STATUS_VARIANTS: Record<string, string> = {
  aberta: "bg-emerald-100 text-emerald-700",
  aguardando: "bg-amber-100 text-amber-800",
  finalizada: "bg-stone-200 text-stone-700",
  ativa: "bg-emerald-100 text-emerald-700",
  ativo: "bg-emerald-100 text-emerald-700",
  inativa: "bg-stone-200 text-stone-700",
  inativo: "bg-stone-200 text-stone-700",
  agendada: "bg-blue-100 text-blue-700",
  confirmada: "bg-emerald-100 text-emerald-700",
  concluida: "bg-emerald-100 text-emerald-700",
  concluído: "bg-emerald-100 text-emerald-700",
  cancelada: "bg-rose-100 text-rose-700",
  falta: "bg-rose-100 text-rose-700",
  no_show: "bg-rose-100 text-rose-700",
  rascunho: "bg-stone-200 text-stone-700",
  em_execucao: "bg-blue-100 text-blue-700",
  "em execucao": "bg-blue-100 text-blue-700",
  pending: "bg-amber-100 text-amber-800",
  success: "bg-emerald-100 text-emerald-700",
  failed: "bg-rose-100 text-rose-700",
  paid: "bg-emerald-100 text-emerald-700",
  trialing: "bg-sky-100 text-sky-700",
  past_due: "bg-amber-100 text-amber-800",
  blocked: "bg-rose-100 text-rose-700",
  suspended: "bg-stone-300 text-stone-800",
  canceled: "bg-stone-300 text-stone-800",
};

function normalize(value: string) {
  return value
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "");
}

function humanize(value: string) {
  return value
    .replace(/_/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((item) => item[0].toUpperCase() + item.slice(1))
    .join(" ");
}

export function StatusBadge({ value, className }: { value?: string | null; className?: string }) {
  const fallback = "Sem status";
  const safe = value?.trim() || fallback;
  const variant = STATUS_VARIANTS[normalize(safe)] ?? "bg-stone-200 text-stone-700";

  return <Badge className={cn(variant, className)}>{safe === fallback ? fallback : humanize(safe)}</Badge>;
}

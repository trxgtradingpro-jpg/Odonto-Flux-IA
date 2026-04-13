"use client";

import { Badge, cn } from "@odontoflux/ui";

const TEMPERATURE_STYLE: Record<string, string> = {
  frio: "bg-sky-100 text-sky-700",
  morno: "bg-amber-100 text-amber-800",
  quente: "bg-rose-100 text-rose-700",
};

export function TemperatureBadge({
  value,
  className,
}: {
  value?: string | null;
  className?: string;
}) {
  const safe = (value || "morno").toLowerCase();
  const style = TEMPERATURE_STYLE[safe] ?? "bg-stone-200 text-stone-700";
  const label = safe[0]?.toUpperCase() + safe.slice(1);
  return <Badge className={cn(style, className)}>{label}</Badge>;
}

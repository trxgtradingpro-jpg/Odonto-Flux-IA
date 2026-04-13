"use client";

import { ArrowDownRight, ArrowUpRight } from "lucide-react";

import { cn } from "@odontoflux/ui";

import { percentFormatter } from "@/lib/formatters";

export function MetricTrend({
  value,
  invert = false,
  className,
}: {
  value: number;
  invert?: boolean;
  className?: string;
}) {
  const positive = value >= 0;
  const isGood = invert ? !positive : positive;
  const signal = positive ? "+" : "";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold",
        isGood ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700",
        className,
      )}
    >
      {positive ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
      {signal}
      {percentFormatter.format(value)}%
    </span>
  );
}

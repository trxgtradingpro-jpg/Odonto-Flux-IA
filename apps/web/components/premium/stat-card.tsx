"use client";

import { ReactNode } from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle, cn } from "@odontoflux/ui";

import { MetricTrend } from "@/components/premium/metric-trend";

type StatCardProps = {
  title: string;
  value: ReactNode;
  description?: string;
  trend?: number | null;
  invertTrend?: boolean;
  helper?: string;
  icon?: ReactNode;
  className?: string;
};

export function StatCard({
  title,
  value,
  description,
  trend,
  invertTrend,
  helper,
  icon,
  className,
}: StatCardProps) {
  return (
    <Card className={cn("border-stone-200 bg-white/95", className)}>
      <CardHeader className="space-y-3 pb-2">
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardDescription className="text-[11px] font-bold uppercase tracking-wide text-stone-500">
              {title}
            </CardDescription>
            {description ? <CardTitle className="mt-0.5 text-sm font-semibold text-stone-700">{description}</CardTitle> : null}
          </div>
          {icon ? <div className="rounded-lg bg-stone-100 p-2 text-stone-600">{icon}</div> : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-3xl font-extrabold tracking-tight text-stone-900">{value}</p>
        {typeof trend === "number" ? <MetricTrend value={trend} invert={invertTrend} /> : null}
        {helper ? <p className="text-xs text-stone-500">{helper}</p> : null}
      </CardContent>
    </Card>
  );
}

"use client";

import { ReactNode } from "react";

import { cn } from "@odontoflux/ui";

type PageHeaderProps = {
  title: string;
  description?: string;
  actions?: ReactNode;
  eyebrow?: string;
  className?: string;
  meta?: ReactNode;
};

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
  className,
  meta,
}: PageHeaderProps) {
  return (
    <div className={cn("rounded-2xl border border-stone-200 bg-white/90 p-5 shadow-panel", className)}>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-1">
          {eyebrow ? (
            <p className="text-xs font-semibold uppercase tracking-wide text-primary">{eyebrow}</p>
          ) : null}
          <h1 className="text-2xl font-bold tracking-tight text-stone-900 lg:text-3xl">{title}</h1>
          {description ? <p className="text-sm text-stone-600">{description}</p> : null}
        </div>

        <div className="flex w-full flex-col items-start gap-3 lg:w-auto lg:items-end">
          {actions}
          {meta}
        </div>
      </div>
    </div>
  );
}

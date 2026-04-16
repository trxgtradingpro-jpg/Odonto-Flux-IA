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
    <div className={cn("rounded-3xl border border-stone-200 bg-white/95 p-5 shadow-[0_1px_2px_rgba(15,23,42,0.07),0_14px_34px_rgba(15,23,42,0.08)] sm:p-6 lg:p-7", className)}>
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-2">
          {eyebrow ? (
            <p className="inline-flex w-fit rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide text-primary">
              {eyebrow}
            </p>
          ) : null}
          <h1 className="text-2xl font-extrabold tracking-tight text-stone-900 sm:text-[2rem] lg:text-[2.15rem]">{title}</h1>
          {description ? <p className="max-w-4xl text-sm leading-relaxed text-stone-600 sm:text-[15px]">{description}</p> : null}
        </div>

        <div className="flex w-full flex-col items-start gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-start max-sm:[&>*]:w-full lg:w-auto lg:justify-end">
          {actions}
          {meta}
        </div>
      </div>
    </div>
  );
}

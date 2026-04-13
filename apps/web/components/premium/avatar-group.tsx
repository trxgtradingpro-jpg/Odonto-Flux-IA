"use client";

import { cn } from "@odontoflux/ui";

import { initials } from "@/lib/formatters";

export function AvatarGroup({
  names,
  max = 4,
  className,
}: {
  names: string[];
  max?: number;
  className?: string;
}) {
  const visible = names.slice(0, max);
  const hidden = Math.max(0, names.length - visible.length);

  return (
    <div className={cn("flex items-center", className)}>
      {visible.map((name, index) => (
        <div
          key={`${name}-${index}`}
          title={name}
          className="-ml-2 inline-flex h-8 w-8 items-center justify-center rounded-full border-2 border-white bg-stone-200 text-xs font-semibold text-stone-700 first:ml-0"
        >
          {initials(name)}
        </div>
      ))}
      {hidden > 0 ? (
        <div className="-ml-2 inline-flex h-8 w-8 items-center justify-center rounded-full border-2 border-white bg-stone-300 text-xs font-semibold text-stone-700">
          +{hidden}
        </div>
      ) : null}
    </div>
  );
}

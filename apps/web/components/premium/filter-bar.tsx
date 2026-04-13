"use client";

import { ReactNode } from "react";

import { Card, CardContent, Input, cn } from "@odontoflux/ui";

type FilterBarProps = {
  search?: string;
  onSearchChange?: (value: string) => void;
  searchPlaceholder?: string;
  children?: ReactNode;
  className?: string;
};

export function FilterBar({
  search,
  onSearchChange,
  searchPlaceholder = "Buscar...",
  children,
  className,
}: FilterBarProps) {
  return (
    <Card className={cn("border-stone-200", className)}>
      <CardContent className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="w-full lg:max-w-sm">
          <Input
            placeholder={searchPlaceholder}
            value={search ?? ""}
            onChange={(event) => onSearchChange?.(event.target.value)}
          />
        </div>
        <div className="flex w-full flex-wrap items-center gap-2 lg:w-auto">{children}</div>
      </CardContent>
    </Card>
  );
}

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
    <Card className={cn("border-stone-200 bg-white/95", className)}>
      <CardContent className="flex flex-col gap-3 p-4 sm:p-5 lg:flex-row lg:items-center lg:justify-between">
        <div className="w-full lg:max-w-md">
          <Input
            placeholder={searchPlaceholder}
            value={search ?? ""}
            onChange={(event) => onSearchChange?.(event.target.value)}
          />
        </div>
        <div className="flex w-full flex-wrap items-center gap-2 lg:w-auto lg:justify-end [&>*]:min-w-0 [&>select]:h-11 [&>select]:rounded-lg [&>select]:px-3 max-sm:[&>*]:w-full">
          {children}
        </div>
      </CardContent>
    </Card>
  );
}

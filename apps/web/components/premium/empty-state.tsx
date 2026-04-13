"use client";

import { LucideIcon, SearchX } from "lucide-react";

import { Button, Card, CardContent, cn } from "@odontoflux/ui";

type EmptyStateProps = {
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
  icon?: LucideIcon;
  className?: string;
};

export function EmptyState({
  title,
  description,
  actionLabel,
  onAction,
  icon: Icon = SearchX,
  className,
}: EmptyStateProps) {
  return (
    <Card className={cn("border-dashed border-stone-300 bg-stone-50", className)}>
      <CardContent className="flex flex-col items-center justify-center gap-3 py-10 text-center">
        <div className="rounded-full bg-stone-200 p-3 text-stone-600">
          <Icon size={20} />
        </div>
        <div className="space-y-1">
          <p className="text-base font-semibold text-stone-800">{title}</p>
          {description ? <p className="text-sm text-stone-600">{description}</p> : null}
        </div>
        {actionLabel ? (
          <Button variant="outline" onClick={onAction}>
            {actionLabel}
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

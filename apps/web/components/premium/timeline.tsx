"use client";

import { ReactNode } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@odontoflux/ui";

type TimelineItem = {
  id: string;
  title: string;
  description?: string;
  time?: string;
  badge?: ReactNode;
};

export function Timeline({
  title,
  items,
}: {
  title: string;
  items: TimelineItem[];
}) {
  return (
    <Card className="border-stone-200">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {items.map((item) => (
          <div key={item.id} className="relative pl-6">
            <span className="absolute left-0 top-1.5 h-2.5 w-2.5 rounded-full bg-primary" />
            <span className="absolute left-[4px] top-4 h-full w-px bg-stone-200 last:hidden" />
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-stone-800">{item.title}</p>
                {item.description ? <p className="text-xs text-stone-600">{item.description}</p> : null}
              </div>
              {item.badge}
            </div>
            {item.time ? <p className="mt-1 text-xs text-stone-500">{item.time}</p> : null}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

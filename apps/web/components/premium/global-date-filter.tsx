"use client";

import { Button, Input } from "@odontoflux/ui";

type Preset = "today" | "7d" | "30d" | "custom";

const OPTIONS: { id: Preset; label: string }[] = [
  { id: "today", label: "Hoje" },
  { id: "7d", label: "7 dias" },
  { id: "30d", label: "30 dias" },
  { id: "custom", label: "Personalizado" },
];

export type GlobalDateValue = {
  preset: Preset;
  start?: string;
  end?: string;
};

export function GlobalDateFilter({
  value,
  onChange,
}: {
  value: GlobalDateValue;
  onChange: (next: GlobalDateValue) => void;
}) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {OPTIONS.map((option) => (
          <Button
            key={option.id}
            variant={value.preset === option.id ? "default" : "outline"}
            className="h-9"
            onClick={() => onChange({ ...value, preset: option.id })}
          >
            {option.label}
          </Button>
        ))}
      </div>
      {value.preset === "custom" ? (
        <div className="grid gap-2 sm:grid-cols-2">
          <Input
            type="date"
            value={value.start ?? ""}
            onChange={(event) => onChange({ ...value, start: event.target.value })}
          />
          <Input
            type="date"
            value={value.end ?? ""}
            onChange={(event) => onChange({ ...value, end: event.target.value })}
          />
        </div>
      ) : null}
    </div>
  );
}

"use client";

import { Card, CardContent, CardHeader, CardTitle, Input, Table, TBody, TD, TH, THead, TR } from '@odontoflux/ui';
import { useMemo, useState } from 'react';

interface Column {
  key: string;
  label: string;
}

export function DataTableCard({
  title,
  rows,
  columns,
  searchPlaceholder = 'Buscar...',
}: {
  title: string;
  rows: Record<string, unknown>[];
  columns: Column[];
  searchPlaceholder?: string;
}) {
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    if (!search) return rows;
    const term = search.toLowerCase();
    return rows.filter((row) =>
      Object.values(row)
        .join(' ')
        .toLowerCase()
        .includes(term),
    );
  }, [rows, search]);

  return (
    <Card className="border-stone-200 bg-white/95">
      <CardHeader className="flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
        <div>
          <CardTitle>{title}</CardTitle>
          <p className="mt-1 text-xs text-stone-500">{filtered.length} registro(s)</p>
        </div>
        <Input
          className="w-full sm:max-w-xs"
          placeholder={searchPlaceholder}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </CardHeader>
      <CardContent>
        {filtered.length === 0 ? (
          <div className="rounded-md border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
            Nenhum resultado encontrado.
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-stone-200">
            <div className="max-h-[min(72vh,680px)] overflow-y-auto">
              <Table className="min-w-[680px]">
                <THead>
                  <TR>
                    {columns.map((column) => (
                      <TH key={column.key}>{column.label}</TH>
                    ))}
                  </TR>
                </THead>
                <TBody>
                  {filtered.map((row, index) => (
                    <TR key={`${row.id ?? index}`} className={index % 2 ? "bg-white" : "bg-stone-50/40"}>
                      {columns.map((column) => (
                        <TD key={column.key}>{String(row[column.key] ?? '-')}</TD>
                      ))}
                    </TR>
                  ))}
                </TBody>
              </Table>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

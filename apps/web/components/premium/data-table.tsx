"use client";

import { ReactNode, useMemo, useState } from "react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TR,
} from "@odontoflux/ui";

import { EmptyState } from "@/components/premium/empty-state";

export type PremiumColumn<T> = {
  key: string;
  label: string;
  render: (row: T) => ReactNode;
  className?: string;
};

export function DataTable<T>({
  title,
  rows,
  columns,
  getRowId,
  searchPlaceholder = "Buscar...",
  searchBy,
  rightHeader,
  emptyTitle = "Sem resultados",
  emptyDescription = "Ajuste os filtros para visualizar os dados.",
}: {
  title: string;
  rows: T[];
  columns: PremiumColumn<T>[];
  getRowId: (row: T, index: number) => string;
  searchPlaceholder?: string;
  searchBy?: (row: T) => string;
  rightHeader?: ReactNode;
  emptyTitle?: string;
  emptyDescription?: string;
}) {
  const [search, setSearch] = useState("");

  const filteredRows = useMemo(() => {
    if (!search.trim()) return rows;
    const term = search.toLowerCase();
    if (!searchBy) return rows;
    return rows.filter((row) => searchBy(row).toLowerCase().includes(term));
  }, [rows, search, searchBy]);

  return (
    <Card className="border-stone-200 bg-white/95">
      <CardHeader className="flex flex-col gap-3 border-b border-stone-200/80 pb-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="safe-wrap">
          <CardTitle>{title}</CardTitle>
          <p className="mt-1 text-xs text-stone-500">
            {filteredRows.length} registro(s){rows.length !== filteredRows.length ? ` de ${rows.length}` : ""}
          </p>
        </div>
        <div className="flex w-full flex-wrap items-center gap-2 lg:w-auto lg:justify-end max-sm:[&>*]:w-full">
          <Input
            className="w-full sm:flex-1 lg:w-72"
            placeholder={searchPlaceholder}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          {rightHeader}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {filteredRows.length ? (
          <div className="overflow-x-auto rounded-xl border border-stone-200">
            <div className="max-h-[min(72vh,680px)] overflow-y-auto">
              <Table className="min-w-[700px]">
                <THead>
                  <TR>
                    {columns.map((column) => (
                      <TH key={column.key} className={column.className}>
                        {column.label}
                      </TH>
                    ))}
                  </TR>
                </THead>
                <TBody>
                  {filteredRows.map((row, index) => (
                    <TR
                      key={getRowId(row, index)}
                      className={index % 2 ? "bg-white" : "bg-stone-50/40"}
                    >
                      {columns.map((column) => (
                        <TD key={column.key} className={column.className}>
                          {column.render(row)}
                        </TD>
                      ))}
                    </TR>
                  ))}
                </TBody>
              </Table>
            </div>
          </div>
        ) : (
          <EmptyState title={emptyTitle} description={emptyDescription} />
        )}
      </CardContent>
    </Card>
  );
}

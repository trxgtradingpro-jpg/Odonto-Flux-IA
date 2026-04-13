"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";

import { PageHeader, StatCard } from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { api } from "@/lib/api";
import { numberFormatter, percentFormatter } from "@/lib/formatters";
import { Button, Card, CardContent, CardHeader, CardTitle } from "@odontoflux/ui";

type MonthlyReport = {
  period: {
    year: number;
    month: number;
    start_at: string;
    end_at: string;
    label: string;
  };
  kpis: {
    messages_total: number;
    appointments_total: number;
    confirmed_appointments: number;
    canceled_appointments: number;
    no_show_appointments: number;
    leads_created: number;
    leads_converted: number;
    reactivated_patients: number;
    confirmation_rate: number;
    no_show_rate: number;
    cancellation_rate: number;
    budget_conversion_rate: number;
  };
  highlights: string[];
  recommendations: string[];
  generated_at: string;
};

function currentMonthInput() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  return `${now.getFullYear()}-${month}`;
}

export default function RelatoriosPage() {
  const [month, setMonth] = useState(currentMonthInput());

  const reportQuery = useQuery<MonthlyReport>({
    queryKey: ["monthly-report", month],
    queryFn: async () => (await api.get("/reports/monthly", { params: { month } })).data,
  });

  const kpis = reportQuery.data?.kpis;

  const exportUrl = useMemo(() => `${api.defaults.baseURL}/reports/monthly/csv?month=${month}`, [month]);

  if (reportQuery.isLoading) return <LoadingState message="Carregando relatório mensal..." />;
  if (reportQuery.isError || !reportQuery.data || !kpis) {
    return <ErrorState message="Não foi possível carregar o relatório mensal." />;
  }

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Relatórios"
        title="Relatório mensal de valor"
        description="KPIs comerciais e operacionais para apresentar resultado da clínica."
        actions={
          <div className="flex items-center gap-2">
            <input
              type="month"
              value={month}
              onChange={(event) => setMonth(event.target.value)}
              className="h-9 rounded-md border border-stone-300 bg-white px-2 text-sm"
            />
            <a href={exportUrl} target="_blank" rel="noreferrer">
              <Button variant="outline" className="gap-2">
                <Download size={14} />
                Exportar CSV
              </Button>
            </a>
          </div>
        }
      />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard title="Mensagens no mês" value={numberFormatter.format(kpis.messages_total)} />
        <StatCard title="Consultas no mês" value={numberFormatter.format(kpis.appointments_total)} />
        <StatCard
          title="Taxa de confirmação"
          value={`${percentFormatter.format(kpis.confirmation_rate)}%`}
          helper="Consultas confirmadas sobre total do mês."
        />
        <StatCard
          title="Conversão de orçamento"
          value={`${percentFormatter.format(kpis.budget_conversion_rate)}%`}
          helper="Leads convertidos sobre leads criados."
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle>Resumo executivo</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-stone-700">
            <p>Período: {reportQuery.data.period.label}</p>
            <p>Consultas confirmadas: {numberFormatter.format(kpis.confirmed_appointments)}</p>
            <p>No-show: {numberFormatter.format(kpis.no_show_appointments)}</p>
            <p>Cancelamentos: {numberFormatter.format(kpis.canceled_appointments)}</p>
            <p>Pacientes reativados: {numberFormatter.format(kpis.reactivated_patients)}</p>
            <p>Leads criados: {numberFormatter.format(kpis.leads_created)}</p>
            <p>Leads convertidos: {numberFormatter.format(kpis.leads_converted)}</p>
          </CardContent>
        </Card>

        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle>Destaques e recomendações</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <p className="text-sm font-semibold text-stone-800">Destaques</p>
              {reportQuery.data.highlights.map((item) => (
                <p key={item} className="text-sm text-stone-700">
                  • {item}
                </p>
              ))}
            </div>
            <div>
              <p className="text-sm font-semibold text-stone-800">Próximas ações</p>
              {reportQuery.data.recommendations.map((item) => (
                <p key={item} className="text-sm text-stone-700">
                  • {item}
                </p>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

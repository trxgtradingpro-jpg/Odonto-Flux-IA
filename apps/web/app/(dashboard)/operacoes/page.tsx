"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, RefreshCw, ShieldAlert } from "lucide-react";
import { toast } from "sonner";

import { DataTable, PageHeader, StatusBadge } from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { api } from "@/lib/api";
import { formatDateTimeBR } from "@/lib/formatters";
import { Button, Card, CardContent, CardHeader, CardTitle } from "@odontoflux/ui";

type OperationsOverview = {
  outbox: {
    failed: number;
    pending: number;
    dead_letter: number;
  };
  jobs: {
    failed_last_24h: number;
  };
  webhooks: {
    failed: number;
  };
  generated_at: string;
};

type OperationFailure = {
  source: "outbox" | "job" | "webhook";
  id: string;
  status: string;
  summary: string;
  detail: string;
  created_at: string;
  retry_count?: number;
  max_retries?: number;
  event_id?: string;
};

export default function OperacoesPage() {
  const queryClient = useQueryClient();

  const overviewQuery = useQuery<OperationsOverview>({
    queryKey: ["operations-overview"],
    queryFn: async () => (await api.get("/operations/overview")).data,
    refetchInterval: 15_000,
  });

  const failuresQuery = useQuery<{ data: OperationFailure[] }>({
    queryKey: ["operations-failures"],
    queryFn: async () =>
      (await api.get("/operations/failures", { params: { limit: 120, offset: 0 } })).data,
    refetchInterval: 15_000,
  });

  const retryOutboxMutation = useMutation({
    mutationFn: async (id: string) => api.post(`/operations/outbox/${id}/retry`),
    onSuccess: () => {
      toast.success("Item de outbox reenfileirado.");
      queryClient.invalidateQueries({ queryKey: ["operations-overview"] });
      queryClient.invalidateQueries({ queryKey: ["operations-failures"] });
    },
    onError: () => toast.error("Não foi possível reenfileirar o outbox."),
  });

  const retryJobMutation = useMutation({
    mutationFn: async (id: string) => api.post(`/operations/jobs/${id}/retry`),
    onSuccess: () => {
      toast.success("Job reenfileirado.");
      queryClient.invalidateQueries({ queryKey: ["operations-overview"] });
      queryClient.invalidateQueries({ queryKey: ["operations-failures"] });
    },
    onError: () => toast.error("Não foi possível reenfileirar o job."),
  });

  if (overviewQuery.isLoading || failuresQuery.isLoading) {
    return <LoadingState message="Carregando monitoramento operacional..." />;
  }

  if (overviewQuery.isError || failuresQuery.isError || !overviewQuery.data || !failuresQuery.data) {
    return <ErrorState message="Não foi possível carregar o monitoramento operacional." />;
  }

  const failures = failuresQuery.data.data ?? [];
  const totalFailures =
    overviewQuery.data.outbox.failed +
    overviewQuery.data.jobs.failed_last_24h +
    overviewQuery.data.webhooks.failed;

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Operações"
        title="Inbox operacional de falhas"
        description="Visão em tempo real de erros do outbox, webhooks e jobs com ações rápidas de recuperação."
      />

      <div className="grid gap-4 lg:grid-cols-4">
        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertTriangle size={16} />
              Falhas totais
            </CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-bold text-stone-900">{totalFailures}</CardContent>
        </Card>

        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle className="text-base">Outbox falhando</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm text-stone-700">
            <p>Falhas: {overviewQuery.data.outbox.failed}</p>
            <p>Pendentes: {overviewQuery.data.outbox.pending}</p>
            <p>Dead-letter: {overviewQuery.data.outbox.dead_letter}</p>
          </CardContent>
        </Card>

        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle className="text-base">Jobs</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm text-stone-700">
            <p>Falhas (24h): {overviewQuery.data.jobs.failed_last_24h}</p>
            <p>Monitoramento: automático</p>
          </CardContent>
        </Card>

        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ShieldAlert size={16} />
              Webhooks
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm text-stone-700">
            <p>Falhas: {overviewQuery.data.webhooks.failed}</p>
            <p>Atualizado: {formatDateTimeBR(overviewQuery.data.generated_at)}</p>
          </CardContent>
        </Card>
      </div>

      <DataTable<OperationFailure>
        title="Eventos com falha"
        rows={failures}
        getRowId={(row) => `${row.source}-${row.id}`}
        searchBy={(row) => `${row.source} ${row.summary} ${row.detail} ${row.status}`}
        columns={[
          {
            key: "origem",
            label: "Origem",
            render: (row) => row.source.toUpperCase(),
          },
          {
            key: "resumo",
            label: "Resumo",
            render: (row) => row.summary,
          },
          {
            key: "status",
            label: "Status",
            render: (row) => <StatusBadge value={row.status} />,
          },
          {
            key: "erro",
            label: "Erro",
            render: (row) => (
              <span className="line-clamp-2 text-xs text-stone-600">
                {row.detail || "Sem detalhe adicional"}
              </span>
            ),
          },
          {
            key: "quando",
            label: "Quando",
            render: (row) => formatDateTimeBR(row.created_at),
          },
          {
            key: "tentativas",
            label: "Tentativas",
            render: (row) =>
              row.retry_count !== undefined && row.max_retries !== undefined
                ? `${row.retry_count}/${row.max_retries}`
                : "-",
          },
          {
            key: "acoes",
            label: "Ações",
            render: (row) => {
              if (row.source === "outbox") {
                return (
                  <Button
                    variant="outline"
                    className="h-8 px-2 text-xs"
                    onClick={() => retryOutboxMutation.mutate(row.id)}
                    disabled={retryOutboxMutation.isPending}
                  >
                    <RefreshCw size={12} className="mr-1" />
                    Reenfileirar
                  </Button>
                );
              }
              if (row.source === "job") {
                return (
                  <Button
                    variant="outline"
                    className="h-8 px-2 text-xs"
                    onClick={() => retryJobMutation.mutate(row.id)}
                    disabled={retryJobMutation.isPending}
                  >
                    <RefreshCw size={12} className="mr-1" />
                    Reprocessar
                  </Button>
                );
              }
              return <span className="text-xs text-stone-500">Revisar webhook/configuração</span>;
            },
          },
        ]}
        emptyTitle="Sem falhas no momento"
        emptyDescription="Quando houver erro operacional, ele aparece aqui automaticamente."
      />
    </div>
  );
}

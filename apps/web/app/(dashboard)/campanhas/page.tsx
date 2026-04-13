"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Megaphone, PlayCircle, Target } from "lucide-react";
import { toast } from "sonner";

import { DataTable, FilterBar, PageHeader, StatCard, StatusBadge } from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { api } from "@/lib/api";
import { ApiPage, CampaignItem, UnitItem, UserItem } from "@/lib/domain-types";
import { formatDateTimeBR, numberFormatter, percentFormatter } from "@/lib/formatters";
import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@odontoflux/ui";

type CampaignWithMetrics = CampaignItem & {
  segment_label: string;
  estimated_send_rate: number;
  estimated_response_rate: number;
  estimated_conversion_rate: number;
};

export default function CampanhasPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const [name, setName] = useState("");
  const [objective, setObjective] = useState("");
  const [segmentLabel, setSegmentLabel] = useState("Pacientes inativos 6+ meses");
  const [scheduleAt, setScheduleAt] = useState("");
  const [unitId, setUnitId] = useState("");

  const campaignsQuery = useQuery<{ campaigns: CampaignItem[]; units: UnitItem[]; users: UserItem[] }>({
    queryKey: ["campaigns-dataset"],
    queryFn: async () => {
      const [campaignsResponse, unitsResponse, usersResponse] = await Promise.all([
        api.get<ApiPage<CampaignItem>>("/campaigns", { params: { limit: 200, offset: 0 } }),
        api.get<ApiPage<UnitItem>>("/units", { params: { limit: 100, offset: 0 } }),
        api.get<ApiPage<UserItem>>("/users", { params: { limit: 100, offset: 0 } }),
      ]);
      return {
        campaigns: campaignsResponse.data.data ?? [],
        units: unitsResponse.data.data ?? [],
        users: usersResponse.data.data ?? [],
      };
    },
  });

  const createMutation = useMutation({
    mutationFn: async () =>
      api.post("/campaigns", {
        name,
        objective,
        unit_id: unitId || null,
        segment_filter: { segment: segmentLabel },
        scheduled_at: scheduleAt ? new Date(scheduleAt).toISOString() : null,
        status: scheduleAt ? "agendada" : "rascunho",
      }),
    onSuccess: () => {
      toast.success("Campanha criada com sucesso.");
      setName("");
      setObjective("");
      setSegmentLabel("Pacientes inativos 6+ meses");
      setScheduleAt("");
      setUnitId("");
      queryClient.invalidateQueries({ queryKey: ["campaigns-dataset"] });
    },
    onError: () => toast.error("Não foi possível criar a campanha."),
  });

  const startMutation = useMutation({
    mutationFn: async (campaignId: string) => (await api.post(`/campaigns/${campaignId}/start`)).data,
    onSuccess: (data) => {
      toast.success(`Campanha iniciada: ${data.queued_messages ?? 0} mensagens na fila.`);
      queryClient.invalidateQueries({ queryKey: ["campaigns-dataset"] });
    },
    onError: () => toast.error("Não foi possível iniciar a campanha."),
  });

  if (campaignsQuery.isLoading) return <LoadingState message="Carregando campanhas..." />;
  if (campaignsQuery.isError || !campaignsQuery.data) return <ErrorState message="Não foi possível carregar as campanhas." />;

  const campaigns: CampaignWithMetrics[] = campaignsQuery.data.campaigns.map((campaign, index) => ({
    ...campaign,
    segment_label: ["Reativação ortodontia", "Retorno limpeza", "Follow-up avaliação estética"][index % 3],
    estimated_send_rate: 92 - (index % 5) * 3,
    estimated_response_rate: 38 - (index % 4) * 4,
    estimated_conversion_rate: 19 - (index % 3) * 2,
  }));

  const filtered = campaigns.filter((campaign) => {
    const term = search.toLowerCase().trim();
    const haystack = `${campaign.name} ${campaign.objective} ${campaign.segment_label}`.toLowerCase();
    const bySearch = !term || haystack.includes(term);
    const byStatus = statusFilter === "all" || campaign.status === statusFilter;
    return bySearch && byStatus;
  });

  const runningCount = campaigns.filter((item) => item.status === "em_execucao").length;
  const scheduledCount = campaigns.filter((item) => item.status === "agendada").length;
  const avgResponse =
    campaigns.length > 0
      ? campaigns.reduce((sum, item) => sum + item.estimated_response_rate, 0) / campaigns.length
      : 0;

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Comercial"
        title="Campanhas"
        description="Gestão de campanhas multicanal com segmentação, agenda e desempenho."
      />

      <div className="grid gap-4 md:grid-cols-3">
        <StatCard
          title="Campanhas ativas"
          value={numberFormatter.format(runningCount)}
          description="Em execução"
          icon={<PlayCircle size={17} />}
        />
        <StatCard
          title="Campanhas agendadas"
          value={numberFormatter.format(scheduledCount)}
          description="Próximos disparos"
          icon={<CalendarClock size={17} />}
        />
        <StatCard
          title="Taxa média de resposta"
          value={`${percentFormatter.format(avgResponse)}%`}
          description="Indicador de engajamento"
          icon={<Target size={17} />}
        />
      </div>

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle>Nova campanha</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2 md:grid-cols-6">
            <Input placeholder="Nome da campanha" value={name} onChange={(event) => setName(event.target.value)} />
            <Input placeholder="Objetivo" value={objective} onChange={(event) => setObjective(event.target.value)} />
            <Input
              placeholder="Segmentação (ex.: pacientes inativos)"
              value={segmentLabel}
              onChange={(event) => setSegmentLabel(event.target.value)}
            />
            <select
              className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm"
              value={unitId}
              onChange={(event) => setUnitId(event.target.value)}
            >
              <option value="">Todas as unidades</option>
              {campaignsQuery.data.units.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  {unit.name}
                </option>
              ))}
            </select>
            <Input type="datetime-local" value={scheduleAt} onChange={(event) => setScheduleAt(event.target.value)} />
            <Button
              className="gap-1.5"
              onClick={() => {
                if (!name.trim() || !objective.trim()) {
                  toast.error("Preencha nome e objetivo da campanha.");
                  return;
                }
                createMutation.mutate();
              }}
              disabled={createMutation.isPending}
            >
              <Megaphone size={14} />
              {createMutation.isPending ? "Criando..." : "Criar campanha"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <FilterBar search={search} onSearchChange={setSearch} searchPlaceholder="Buscar campanha por nome, objetivo ou segmento...">
        <select
          className="h-9 rounded-md border border-stone-300 bg-white px-2 text-sm"
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value)}
        >
          <option value="all">Todos os status</option>
          <option value="rascunho">Rascunho</option>
          <option value="agendada">Agendada</option>
          <option value="em_execucao">Em execução</option>
          <option value="finalizada">Finalizada</option>
        </select>
      </FilterBar>

      <DataTable<CampaignWithMetrics>
        title="Lista de campanhas"
        rows={filtered}
        getRowId={(item) => item.id}
        searchBy={(item) => `${item.name} ${item.objective} ${item.segment_label}`}
        columns={[
          {
            key: "nome",
            label: "Campanha",
            render: (item) => (
              <div>
                <p className="font-semibold text-stone-800">{item.name}</p>
                <p className="text-xs text-stone-500">{item.objective}</p>
              </div>
            ),
          },
          {
            key: "segmentacao",
            label: "Segmentação",
            render: (item) => item.segment_label,
          },
          {
            key: "status",
            label: "Status",
            render: (item) => <StatusBadge value={item.status} />,
          },
          {
            key: "agendamento",
            label: "Agendada para",
            render: (item) => formatDateTimeBR(item.scheduled_at),
          },
          {
            key: "envio",
            label: "Taxa de envio",
            render: (item) => `${percentFormatter.format(item.estimated_send_rate)}%`,
          },
          {
            key: "resposta",
            label: "Taxa de resposta",
            render: (item) => `${percentFormatter.format(item.estimated_response_rate)}%`,
          },
          {
            key: "conversao",
            label: "Taxa de conversão",
            render: (item) => `${percentFormatter.format(item.estimated_conversion_rate)}%`,
          },
          {
            key: "acoes",
            label: "Ações",
            render: (item) => (
              <div className="flex items-center gap-1">
                <Button
                  variant="outline"
                  className="h-8 px-2 text-xs"
                  onClick={() => toast.info("Abrindo revisão da campanha...")}
                >
                  Revisar
                </Button>
                <Button
                  className="h-8 px-2 text-xs"
                  onClick={() => startMutation.mutate(item.id)}
                  disabled={startMutation.isPending || item.status === "em_execucao"}
                >
                  Iniciar
                </Button>
              </div>
            ),
          },
        ]}
        emptyTitle="Sem campanhas para exibir"
        emptyDescription="Crie uma nova campanha para iniciar ações comerciais."
      />
    </div>
  );
}

"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Play, Pause, Zap } from "lucide-react";
import { toast } from "sonner";

import {
  DataTable,
  FilterBar,
  PageHeader,
  RightDrawer,
  StatCard,
  StatusBadge,
  Timeline,
} from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { api } from "@/lib/api";
import { ApiPage, AutomationItem, AutomationRunItem } from "@/lib/domain-types";
import { formatDateTimeBR, numberFormatter, percentFormatter } from "@/lib/formatters";
import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@odontoflux/ui";

const AUTOMATION_PRESETS = [
  { name: "Confirmação 24h antes", trigger_type: "time", trigger_key: "consulta_24h" },
  { name: "Lembrete 2h antes", trigger_type: "time", trigger_key: "consulta_2h" },
  { name: "Recuperação de faltas", trigger_type: "event", trigger_key: "paciente_faltou" },
  { name: "Follow-up orçamento 2 dias", trigger_type: "event", trigger_key: "orcamento_pendente_2d" },
  { name: "Follow-up orçamento 7 dias", trigger_type: "event", trigger_key: "orcamento_pendente_7d" },
  { name: "Reativação de inativos", trigger_type: "event", trigger_key: "paciente_inativo" },
  { name: "Triagem WhatsApp", trigger_type: "event", trigger_key: "lead_whatsapp_entrada" },
];

type DrawerTab = "editar" | "logs" | "impacto";

export default function AutomacoesPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const [name, setName] = useState("");
  const [triggerType, setTriggerType] = useState<"event" | "time">("event");
  const [triggerKey, setTriggerKey] = useState("");

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>("editar");
  const [selectedAutomationId, setSelectedAutomationId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editTriggerKey, setEditTriggerKey] = useState("");
  const [editConditions, setEditConditions] = useState("{}");
  const [editActionBody, setEditActionBody] = useState("Mensagem automática ajustada pela operação.");

  const automationsQuery = useQuery<{ automations: AutomationItem[]; runs: AutomationRunItem[] }>({
    queryKey: ["automations-dataset"],
    queryFn: async () => {
      const [automationsResponse, runsResponse] = await Promise.all([
        api.get<ApiPage<AutomationItem>>("/automations", { params: { limit: 200, offset: 0 } }),
        api.get<ApiPage<AutomationRunItem>>("/automations/runs", { params: { limit: 200, offset: 0 } }),
      ]);

      return {
        automations: automationsResponse.data.data ?? [],
        runs: runsResponse.data.data ?? [],
      };
    },
  });

  const createMutation = useMutation({
    mutationFn: async () =>
      api.post("/automations", {
        name,
        description: "Automação criada pela operação",
        trigger_type: triggerType,
        trigger_key: triggerKey,
        conditions: {},
        actions: [{ type: "send_message", params: { body: "Mensagem automática da campanha operacional." } }],
        retry_policy: { max_attempts: 3 },
        is_active: true,
      }),
    onSuccess: () => {
      toast.success("Automação criada com sucesso.");
      setName("");
      setTriggerKey("");
      setTriggerType("event");
      queryClient.invalidateQueries({ queryKey: ["automations-dataset"] });
    },
    onError: () => toast.error("Não foi possível criar a automação."),
  });

  const updateMutation = useMutation({
    mutationFn: async (automationId: string) => {
      let parsedConditions: Record<string, unknown> = {};
      try {
        parsedConditions = JSON.parse(editConditions || "{}");
      } catch {
        throw new Error("Condições devem estar em JSON válido.");
      }

      return api.patch(`/automations/${automationId}`, {
        name: editName,
        description: editDescription || null,
        trigger_key: editTriggerKey,
        conditions: parsedConditions,
        actions: [{ type: "send_message", params: { body: editActionBody } }],
      });
    },
    onSuccess: () => {
      toast.success("Automação atualizada com sucesso.");
      queryClient.invalidateQueries({ queryKey: ["automations-dataset"] });
      setDrawerOpen(false);
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : "Não foi possível atualizar a automação.";
      toast.error(message);
    },
  });

  const pauseMutation = useMutation({
    mutationFn: async (automationId: string) => api.post(`/automations/${automationId}/pause`),
    onSuccess: () => {
      toast.success("Automação pausada.");
      queryClient.invalidateQueries({ queryKey: ["automations-dataset"] });
    },
    onError: () => toast.error("Falha ao pausar automação."),
  });

  const resumeMutation = useMutation({
    mutationFn: async (automationId: string) => api.post(`/automations/${automationId}/resume`),
    onSuccess: () => {
      toast.success("Automação reativada.");
      queryClient.invalidateQueries({ queryKey: ["automations-dataset"] });
    },
    onError: () => toast.error("Falha ao reativar automação."),
  });

  if (automationsQuery.isLoading) return <LoadingState message="Carregando motor de automações..." />;
  if (automationsQuery.isError || !automationsQuery.data) return <ErrorState message="Não foi possível carregar automações." />;

  const automations = automationsQuery.data.automations
    .filter((item) => {
      const term = search.toLowerCase().trim();
      const haystack = `${item.name} ${item.trigger_type} ${item.trigger_key}`.toLowerCase();
      const bySearch = !term || haystack.includes(term);
      const byStatus =
        statusFilter === "all" ||
        (statusFilter === "active" && item.is_active) ||
        (statusFilter === "inactive" && !item.is_active);
      return bySearch && byStatus;
    })
    .map((item) => {
      const runs = automationsQuery.data.runs.filter((run) => run.automation_id === item.id);
      const totalRuns = runs.length;
      const successRuns = runs.filter((run) => run.status === "success").length;
      const exceptionQueue = runs.filter((run) => run.status === "failed").length;
      const successRate = totalRuns ? (successRuns / totalRuns) * 100 : 0;
      const lastExecution = runs[0]?.finished_at || runs[0]?.started_at || null;
      return {
        ...item,
        totalRuns,
        successRate,
        lastExecution,
        exceptionQueue,
      };
    });

  const selectedAutomation = automations.find((item) => item.id === selectedAutomationId) ?? null;
  const selectedRuns = selectedAutomation
    ? automationsQuery.data.runs.filter((run) => run.automation_id === selectedAutomation.id)
    : [];

  const activeCount = automationsQuery.data.automations.filter((item) => item.is_active).length;
  const inactiveCount = automationsQuery.data.automations.length - activeCount;
  const avgSuccessRate =
    automations.length > 0
      ? automations.reduce((sum, item) => sum + item.successRate, 0) / automations.length
      : 0;

  const automationNameById = new Map(automationsQuery.data.automations.map((item) => [item.id, item.name]));
  const timelineItems = automationsQuery.data.runs.slice(0, 8).map((run) => ({
    id: run.id,
    title: `Execução ${run.status === "success" ? "concluída" : run.status === "failed" ? "com falha" : run.status}`,
    description: `${automationNameById.get(run.automation_id) ?? "Automação"} • Tentativa operacional`,
    time: formatDateTimeBR(run.finished_at || run.started_at),
    badge: <StatusBadge value={run.status} />,
  }));

  const openDrawer = (item: (typeof automations)[number], tab: DrawerTab) => {
    setSelectedAutomationId(item.id);
    setDrawerTab(tab);
    setEditName(item.name);
    setEditDescription(item.description || "");
    setEditTriggerKey(item.trigger_key);
    setEditConditions(JSON.stringify(item.conditions || {}, null, 2));
    const sendMessageAction = (item.actions || []).find((action) => action.type === "send_message") as
      | { params?: { body?: string } }
      | undefined;
    setEditActionBody(sendMessageAction?.params?.body || "Mensagem automática ajustada pela operação.");
    setDrawerOpen(true);
  };

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Automação"
        title="Motor de automações"
        description="Fluxos inteligentes para confirmação, lembrete, recuperação e follow-up comercial."
      />

      <div className="grid gap-4 md:grid-cols-3">
        <StatCard title="Automações ativas" value={numberFormatter.format(activeCount)} icon={<Play size={16} />} />
        <StatCard title="Automações inativas" value={numberFormatter.format(inactiveCount)} icon={<Pause size={16} />} />
        <StatCard
          title="Taxa média de sucesso"
          value={`${percentFormatter.format(avgSuccessRate)}%`}
          icon={<Zap size={16} />}
        />
      </div>

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle>Nova automação</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2 md:grid-cols-5">
            <Input placeholder="Nome da automação" value={name} onChange={(event) => setName(event.target.value)} />
            <select
              className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm"
              value={triggerType}
              onChange={(event) => setTriggerType(event.target.value as "event" | "time")}
            >
              <option value="event">Evento</option>
              <option value="time">Tempo</option>
            </select>
            <Input placeholder="Gatilho (ex.: consulta_24h)" value={triggerKey} onChange={(event) => setTriggerKey(event.target.value)} />
            <select
              className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm"
              onChange={(event) => {
                const selected = AUTOMATION_PRESETS.find((item) => item.name === event.target.value);
                if (!selected) return;
                setName(selected.name);
                setTriggerType(selected.trigger_type as "event" | "time");
                setTriggerKey(selected.trigger_key);
              }}
              defaultValue=""
            >
              <option value="">Usar preset</option>
              {AUTOMATION_PRESETS.map((preset) => (
                <option key={preset.name} value={preset.name}>
                  {preset.name}
                </option>
              ))}
            </select>
            <Button
              className="gap-1.5"
              onClick={() => {
                if (!name.trim() || !triggerKey.trim()) {
                  toast.error("Preencha nome e gatilho para criar a automação.");
                  return;
                }
                createMutation.mutate();
              }}
              disabled={createMutation.isPending}
            >
              <Bot size={14} />
              {createMutation.isPending ? "Criando..." : "Criar automação"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <FilterBar search={search} onSearchChange={setSearch} searchPlaceholder="Buscar por nome, tipo ou gatilho...">
        <select
          className="h-9 rounded-md border border-stone-300 bg-white px-2 text-sm"
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value)}
        >
          <option value="all">Todas</option>
          <option value="active">Ativas</option>
          <option value="inactive">Inativas</option>
        </select>
      </FilterBar>

      <DataTable<(typeof automations)[number]>
        title="Automações"
        rows={automations}
        getRowId={(item) => item.id}
        searchBy={(item) => `${item.name} ${item.trigger_type} ${item.trigger_key}`}
        columns={[
          {
            key: "nome",
            label: "Automação",
            render: (item) => (
              <div>
                <p className="font-semibold text-stone-800">{item.name}</p>
                <p className="text-xs text-stone-500">{item.trigger_type}:{item.trigger_key}</p>
              </div>
            ),
          },
          {
            key: "condicao",
            label: "Condição",
            render: (item) => (Object.keys(item.conditions ?? {}).length ? "Condição personalizada" : "Padrão"),
          },
          {
            key: "acao",
            label: "Ação",
            render: (item) => `${(item.actions ?? []).length} ação(ões)`,
          },
          {
            key: "ultima_execucao",
            label: "Última execução",
            render: (item) => formatDateTimeBR(item.lastExecution),
          },
          {
            key: "sucesso",
            label: "Taxa de sucesso",
            render: (item) => `${percentFormatter.format(item.successRate)}%`,
          },
          {
            key: "excecoes",
            label: "Fila de exceções",
            render: (item) => numberFormatter.format(item.exceptionQueue),
          },
          {
            key: "status",
            label: "Status",
            render: (item) => <StatusBadge value={item.is_active ? "ativa" : "inativa"} />,
          },
          {
            key: "acoes",
            label: "Ações",
            render: (item) => (
              <div className="flex items-center gap-1">
                <Button variant="outline" className="h-8 px-2 text-xs" onClick={() => openDrawer(item, "editar")}>
                  Editar
                </Button>
                <Button variant="outline" className="h-8 px-2 text-xs" onClick={() => openDrawer(item, "logs")}>
                  Logs
                </Button>
                <Button variant="outline" className="h-8 px-2 text-xs" onClick={() => openDrawer(item, "impacto")}>
                  Impacto
                </Button>
                {item.is_active ? (
                  <Button
                    variant="outline"
                    className="h-8 px-2 text-xs"
                    onClick={() => pauseMutation.mutate(item.id)}
                    disabled={pauseMutation.isPending}
                  >
                    Desligar
                  </Button>
                ) : (
                  <Button
                    className="h-8 px-2 text-xs"
                    onClick={() => resumeMutation.mutate(item.id)}
                    disabled={resumeMutation.isPending}
                  >
                    Ligar
                  </Button>
                )}
              </div>
            ),
          },
        ]}
        emptyTitle="Sem automações no filtro"
        emptyDescription="Crie ou ajuste automações para visualizar o motor operacional."
      />

      <Timeline title="Últimas execuções" items={timelineItems} />

      <RightDrawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        title={selectedAutomation ? selectedAutomation.name : "Automação"}
        description="Edição de regra, logs e impacto operacional da automação selecionada."
      >
        {selectedAutomation ? (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-1">
              <Button variant={drawerTab === "editar" ? "default" : "outline"} className="h-8 text-xs" onClick={() => setDrawerTab("editar")}>Editar</Button>
              <Button variant={drawerTab === "logs" ? "default" : "outline"} className="h-8 text-xs" onClick={() => setDrawerTab("logs")}>Logs</Button>
              <Button variant={drawerTab === "impacto" ? "default" : "outline"} className="h-8 text-xs" onClick={() => setDrawerTab("impacto")}>Impacto</Button>
            </div>

            {drawerTab === "editar" ? (
              <Card className="border-stone-200">
                <CardContent className="space-y-2 p-4">
                  <Input value={editName} onChange={(event) => setEditName(event.target.value)} placeholder="Nome" />
                  <Input value={editDescription} onChange={(event) => setEditDescription(event.target.value)} placeholder="Descrição" />
                  <Input value={editTriggerKey} onChange={(event) => setEditTriggerKey(event.target.value)} placeholder="Gatilho" />
                  <textarea
                    className="min-h-[90px] w-full rounded-md border border-stone-300 bg-white p-2 text-xs"
                    value={editConditions}
                    onChange={(event) => setEditConditions(event.target.value)}
                    placeholder='Condições em JSON (ex.: {"status":"pendente"})'
                  />
                  <Input
                    value={editActionBody}
                    onChange={(event) => setEditActionBody(event.target.value)}
                    placeholder="Mensagem principal da ação"
                  />
                  <div className="flex justify-end gap-2">
                    <Button variant="outline" onClick={() => setDrawerOpen(false)}>Cancelar</Button>
                    <Button
                      onClick={() => updateMutation.mutate(selectedAutomation.id)}
                      disabled={updateMutation.isPending}
                    >
                      {updateMutation.isPending ? "Salvando..." : "Salvar regra"}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ) : null}

            {drawerTab === "logs" ? (
              <Card className="border-stone-200">
                <CardContent className="space-y-2 p-4">
                  {selectedRuns.length ? (
                    selectedRuns.slice(0, 15).map((run) => (
                      <div key={run.id} className="rounded-lg border border-stone-200 bg-stone-50 p-2">
                        <div className="flex items-center justify-between">
                          <StatusBadge value={run.status} />
                          <span className="text-xs text-stone-500">{formatDateTimeBR(run.finished_at || run.started_at)}</span>
                        </div>
                        <pre className="mt-1 overflow-x-auto text-[11px] text-stone-700">{JSON.stringify(run.result_payload || run.trigger_payload || {}, null, 2)}</pre>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-stone-500">Sem logs para esta automação.</p>
                  )}
                </CardContent>
              </Card>
            ) : null}

            {drawerTab === "impacto" ? (
              <Card className="border-stone-200">
                <CardContent className="grid gap-2 p-4 sm:grid-cols-2">
                  <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
                    <p className="text-xs text-stone-500">Execuções totais</p>
                    <p className="text-xl font-bold text-stone-800">{numberFormatter.format(selectedAutomation.totalRuns)}</p>
                  </div>
                  <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
                    <p className="text-xs text-stone-500">Taxa de sucesso</p>
                    <p className="text-xl font-bold text-emerald-700">{percentFormatter.format(selectedAutomation.successRate)}%</p>
                  </div>
                  <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
                    <p className="text-xs text-stone-500">Exceções</p>
                    <p className="text-xl font-bold text-rose-700">{numberFormatter.format(selectedAutomation.exceptionQueue)}</p>
                  </div>
                  <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
                    <p className="text-xs text-stone-500">Última execução</p>
                    <p className="text-sm font-semibold text-stone-800">{formatDateTimeBR(selectedAutomation.lastExecution)}</p>
                  </div>
                </CardContent>
              </Card>
            ) : null}
          </div>
        ) : (
          <p className="text-sm text-stone-500">Selecione uma automação para visualizar detalhes.</p>
        )}
      </RightDrawer>
    </div>
  );
}

"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";

import { DataTable, FilterBar, PageHeader, RightDrawer, StatusBadge } from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { api } from "@/lib/api";
import { ApiPage, AuditItem, UnitItem, UserItem } from "@/lib/domain-types";
import { formatDateTimeBR } from "@/lib/formatters";
import { Button, Card, CardContent } from "@odontoflux/ui";

type AuditDataset = {
  logs: AuditItem[];
  users: UserItem[];
  units: UnitItem[];
};

const ACTION_LABELS: Record<string, string> = {
  "patient.create": "Paciente criado",
  "patient.update": "Paciente atualizado",
  "auth.login": "Login realizado",
  "message.create": "Mensagem enviada",
  "appointment.create": "Consulta criada",
  "appointment.update": "Consulta atualizada",
  "campaign.create": "Campanha criada",
  "campaign.start": "Campanha iniciada",
  "automation.create": "Automação criada",
  "automation.update": "Automação atualizada",
  "automation.pause": "Automação pausada",
  "automation.resume": "Automação reativada",
  "document.create": "Documento criado",
  "document.download": "Documento baixado",
  "whatsapp.account.create": "Conta WhatsApp vinculada",
  "whatsapp.account.test": "Conexão WhatsApp testada",
  "settings.upsert": "Configuração alterada",
  "user.create": "Usuário criado",
  "user.update": "Usuário atualizado",
  "user.invite": "Convite de usuário enviado",
  "automation.run": "Automação executada",
  "seed.init": "Carga inicial de demo",
};

function actionLabel(action: string) {
  return ACTION_LABELS[action] ?? action.replace(/\./g, " ");
}

export default function AuditoriaPage() {
  const [search, setSearch] = useState("");
  const [actionFilter, setActionFilter] = useState("all");
  const [entityFilter, setEntityFilter] = useState("all");
  const [userFilter, setUserFilter] = useState("all");
  const [unitFilter, setUnitFilter] = useState("all");
  const [periodFilter, setPeriodFilter] = useState("30d");
  const [selectedAudit, setSelectedAudit] = useState<AuditItem | null>(null);

  const auditQuery = useQuery<AuditDataset>({
    queryKey: ["audit-dataset"],
    queryFn: async () => {
      const [logsResponse, usersResponse, unitsResponse] = await Promise.all([
        api.get<ApiPage<AuditItem>>("/audit", { params: { limit: 300, offset: 0 } }),
        api.get<ApiPage<UserItem>>("/users", { params: { limit: 100, offset: 0 } }),
        api.get<ApiPage<UnitItem>>("/units", { params: { limit: 100, offset: 0 } }),
      ]);
      return {
        logs: logsResponse.data.data ?? [],
        users: usersResponse.data.data ?? [],
        units: unitsResponse.data.data ?? [],
      };
    },
  });

  if (auditQuery.isLoading) return <LoadingState message="Carregando auditoria..." />;
  if (auditQuery.isError || !auditQuery.data) return <ErrorState message="Não foi possível carregar a trilha de auditoria." />;

  const usersById = new Map(auditQuery.data.users.map((item) => [item.id, item.full_name]));
  const unitsByName = auditQuery.data.units.map((unit) => unit.name);

  const periodDays = periodFilter === "7d" ? 7 : periodFilter === "30d" ? 30 : 90;
  const periodStart = new Date();
  periodStart.setDate(periodStart.getDate() - periodDays);

  const rows = auditQuery.data.logs
    .filter((log) => {
      const term = search.toLowerCase().trim();
      const userName = log.user_id ? usersById.get(log.user_id) ?? "Usuário não identificado" : "Sistema";
      const haystack = `${actionLabel(log.action)} ${log.entity_type} ${userName}`.toLowerCase();
      const bySearch = !term || haystack.includes(term);
      const byAction = actionFilter === "all" || log.action === actionFilter;
      const byEntity = entityFilter === "all" || log.entity_type === entityFilter;
      const byUser = userFilter === "all" || log.user_id === userFilter;
      const byUnit = unitFilter === "all" || JSON.stringify(log.metadata || {}).includes(unitFilter);
      const byPeriod = new Date(log.occurred_at) >= periodStart;
      return bySearch && byAction && byEntity && byUser && byUnit && byPeriod;
    })
    .map((log) => ({
      ...log,
      action_human: actionLabel(log.action),
      user_name: log.user_id ? usersById.get(log.user_id) ?? "Usuário não identificado" : "Sistema",
      entity_human: log.entity_type,
    }));

  const uniqueActions = Array.from(new Set(auditQuery.data.logs.map((item) => item.action)));
  const uniqueEntities = Array.from(new Set(auditQuery.data.logs.map((item) => item.entity_type)));

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Compliance"
        title="Trilha de auditoria"
        description="Rastreabilidade de ações críticas com foco em segurança, governança e histórico operacional."
        actions={
          <Button
            variant="outline"
            onClick={() => {
              if (!rows.length) {
                toast.error("Não há registros para exportar.");
                return;
              }
              const header = ["Ação", "Entidade", "Usuário", "Quando"];
              const lines = rows.map((item) =>
                [
                  item.action_human,
                  item.entity_human,
                  item.user_name,
                  formatDateTimeBR(item.occurred_at),
                ].join(";"),
              );
              const csv = [header.join(";"), ...lines].join("\n");
              const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
              const url = URL.createObjectURL(blob);
              const anchor = document.createElement("a");
              anchor.href = url;
              anchor.download = "auditoria_odontoflux.csv";
              anchor.click();
              URL.revokeObjectURL(url);
              toast.success("CSV exportado com sucesso.");
            }}
          >
            Exportar CSV
          </Button>
        }
      />

      <FilterBar search={search} onSearchChange={setSearch} searchPlaceholder="Buscar ação, entidade ou usuário...">
        <select
          className="h-9 rounded-md border border-stone-300 bg-white px-2 text-sm"
          value={actionFilter}
          onChange={(event) => setActionFilter(event.target.value)}
        >
          <option value="all">Todas as ações</option>
          {uniqueActions.map((action) => (
            <option key={action} value={action}>
              {actionLabel(action)}
            </option>
          ))}
        </select>
        <select
          className="h-9 rounded-md border border-stone-300 bg-white px-2 text-sm"
          value={entityFilter}
          onChange={(event) => setEntityFilter(event.target.value)}
        >
          <option value="all">Todas as entidades</option>
          {uniqueEntities.map((entity) => (
            <option key={entity} value={entity}>
              {entity}
            </option>
          ))}
        </select>
        <select
          className="h-9 rounded-md border border-stone-300 bg-white px-2 text-sm"
          value={userFilter}
          onChange={(event) => setUserFilter(event.target.value)}
        >
          <option value="all">Todos os usuários</option>
          {auditQuery.data.users.map((user) => (
            <option key={user.id} value={user.id}>
              {user.full_name}
            </option>
          ))}
        </select>
        <select
          className="h-9 rounded-md border border-stone-300 bg-white px-2 text-sm"
          value={unitFilter}
          onChange={(event) => setUnitFilter(event.target.value)}
        >
          <option value="all">Todas as unidades</option>
          {unitsByName.map((unitName) => (
            <option key={unitName} value={unitName}>
              {unitName}
            </option>
          ))}
        </select>
        <select
          className="h-9 rounded-md border border-stone-300 bg-white px-2 text-sm"
          value={periodFilter}
          onChange={(event) => setPeriodFilter(event.target.value)}
        >
          <option value="7d">Últimos 7 dias</option>
          <option value="30d">Últimos 30 dias</option>
          <option value="90d">Últimos 90 dias</option>
        </select>
      </FilterBar>

      <DataTable<(typeof rows)[number]>
        title="Eventos auditáveis"
        rows={rows}
        getRowId={(item) => item.id}
        searchBy={(item) => `${item.action_human} ${item.entity_human} ${item.user_name}`}
        columns={[
          { key: "acao", label: "Ação", render: (item) => item.action_human },
          { key: "entidade", label: "Entidade", render: (item) => item.entity_human },
          { key: "usuario", label: "Usuário", render: (item) => item.user_name },
          { key: "quando", label: "Quando", render: (item) => formatDateTimeBR(item.occurred_at) },
          { key: "status", label: "Status", render: () => <StatusBadge value="ativo" /> },
          {
            key: "detalhe",
            label: "Detalhes",
            render: (item) => (
              <Button variant="outline" className="h-8 px-2 text-xs" onClick={() => setSelectedAudit(item)}>
                Visualizar
              </Button>
            ),
          },
        ]}
        emptyTitle="Sem registros na auditoria"
        emptyDescription="Não há eventos no período e filtros selecionados."
      />

      <RightDrawer
        open={Boolean(selectedAudit)}
        onOpenChange={(open) => {
          if (!open) setSelectedAudit(null);
        }}
        title="Detalhes do evento de auditoria"
        description="Informações completas para rastreabilidade e segurança."
      >
        {selectedAudit ? (
          <Card className="border-stone-200">
            <CardContent className="space-y-3 p-4 text-sm">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Ação</p>
                <p className="font-semibold text-stone-800">{actionLabel(selectedAudit.action)}</p>
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Entidade</p>
                <p className="text-stone-800">{selectedAudit.entity_type}</p>
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Usuário</p>
                <p className="text-stone-800">
                  {selectedAudit.user_id ? usersById.get(selectedAudit.user_id) ?? "Usuário não identificado" : "Sistema"}
                </p>
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Data e hora</p>
                <p className="text-stone-800">{formatDateTimeBR(selectedAudit.occurred_at)}</p>
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Metadados</p>
                <pre className="overflow-x-auto rounded-md border border-stone-200 bg-stone-50 p-2 text-xs text-stone-700">
                  {JSON.stringify(selectedAudit.metadata ?? {}, null, 2)}
                </pre>
              </div>
            </CardContent>
          </Card>
        ) : null}
      </RightDrawer>
    </div>
  );
}

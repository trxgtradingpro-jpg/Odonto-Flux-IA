"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  BellRing,
  Building2,
  GaugeCircle,
  MessageSquareText,
  ShieldCheck,
  Users,
} from "lucide-react";
import { useRouter } from "next/navigation";

import { DataTable, PageHeader, PermissionGate, StatCard, StatusBadge } from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { useSession } from "@/hooks/use-session";
import { api } from "@/lib/api";
import { formatDateTimeBR, numberFormatter, percentFormatter } from "@/lib/formatters";
import { Badge, Card, CardContent, CardHeader, CardTitle } from "@odontoflux/ui";

type PlatformMetrics = {
  total_tenants: number;
  total_users: number;
  total_messages: number;
  active_campaigns: number;
};

type TenantItem = {
  id: string;
  trade_name: string;
  legal_name: string;
  slug: string;
  subscription_status: string;
  is_active: boolean;
  trial_ends_at?: string | null;
};

type AdminOverview = {
  generated_at: string;
  platform_status: { api: string; database: string; workers: string };
  plan_distribution: Array<{
    code: string;
    name: string;
    tenants: number;
    limits: { max_users: number; max_units: number; max_monthly_messages: number };
  }>;
  usage_by_tenant: Array<{
    tenant_id: string;
    tenant_name: string;
    plan: string;
    users: number;
    units: number;
    messages: number;
    appointments: number;
    active_campaigns: number;
    feature_flags_enabled: number;
    limits: { users: number | null; units: number | null; monthly_messages: number | null };
  }>;
  feature_flags: Array<{ key: string; enabled_tenants: number }>;
};

type MonitoringSnapshot = {
  generated_at: string;
  uptime_seconds: number;
  services: {
    api: { status: string };
    database: { status: string; latency_ms: number };
    redis: { status: string; latency_ms: number };
    workers: { status: string; failed_jobs_last_hour: number };
  };
  errors: {
    failed_jobs_last_hour: number;
    failed_jobs_24h: number;
    recent_failures: Array<{
      id: string;
      job_type: string;
      error_message: string | null;
      attempts: number;
      finished_at: string | null;
    }>;
  };
  incidents: {
    open: number;
    critical_open: number;
  };
  billing: {
    tenants_past_due: number;
    tenants_blocked: number;
  };
  alerts: Array<{
    severity: "critical" | "warning" | "info";
    title: string;
    description: string;
  }>;
  alert_channels: string[];
};

function percentUsage(current: number, limit: number | null) {
  if (!limit || limit <= 0) return 0;
  return (current / limit) * 100;
}

function formatUptime(seconds: number) {
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3_600);
  const minutes = Math.floor((seconds % 3_600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function severityClass(value: string) {
  if (value === "critical") return "bg-rose-100 text-rose-700";
  if (value === "warning") return "bg-amber-100 text-amber-800";
  return "bg-sky-100 text-sky-700";
}

export default function AdminPage() {
  const router = useRouter();
  const sessionQuery = useSession();
  const isAdmin = sessionQuery.data?.roles?.includes("admin_platform") ?? false;

  const metricsQuery = useQuery<PlatformMetrics>({
    queryKey: ["platform-metrics"],
    queryFn: async () => (await api.get("/admin/platform/metrics")).data,
    enabled: isAdmin,
  });

  const overviewQuery = useQuery<AdminOverview>({
    queryKey: ["platform-overview"],
    queryFn: async () => (await api.get("/admin/platform/overview")).data,
    enabled: isAdmin,
  });

  const monitoringQuery = useQuery<MonitoringSnapshot>({
    queryKey: ["platform-monitoring"],
    queryFn: async () => (await api.get("/admin/platform/monitoring")).data,
    enabled: isAdmin,
    refetchInterval: 60_000,
  });

  const tenantsQuery = useQuery<{ data: TenantItem[] }>({
    queryKey: ["platform-tenants"],
    queryFn: async () => (await api.get("/tenants", { params: { limit: 100, offset: 0 } })).data,
    enabled: isAdmin,
  });

  if (sessionQuery.isLoading) return <LoadingState message="Carregando contexto do usuario..." />;
  if (sessionQuery.isError) return <ErrorState message="Nao foi possivel carregar o contexto da sessao." />;

  if (!isAdmin) {
    return (
      <PermissionGate
        roles={sessionQuery.data?.roles}
        allowedRoles={["admin_platform"]}
        fallbackTitle="Modulo exclusivo da plataforma"
        fallbackDescription="Somente o perfil admin_platform pode acessar o Admin Plataforma."
        helpText="Se voce e owner da clinica, use Relatorios, Faturamento e Suporte para a gestao diaria."
        onBack={() => router.push("/dashboard")}
      >
        {null}
      </PermissionGate>
    );
  }

  if (metricsQuery.isLoading || overviewQuery.isLoading || monitoringQuery.isLoading || tenantsQuery.isLoading) {
    return <LoadingState message="Carregando governanca e monitoramento da plataforma..." />;
  }
  if (
    metricsQuery.isError ||
    overviewQuery.isError ||
    monitoringQuery.isError ||
    tenantsQuery.isError ||
    !metricsQuery.data ||
    !overviewQuery.data ||
    !monitoringQuery.data ||
    !tenantsQuery.data
  ) {
    return <ErrorState message="Nao foi possivel carregar os dados globais da plataforma." />;
  }

  const monitoring = monitoringQuery.data;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Admin Plataforma"
        title="Governanca da plataforma"
        description="Visao global de tenants, planos, limites, faturamento em risco e saude operacional 24x7."
      />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          title="Tenants ativos"
          value={numberFormatter.format(metricsQuery.data.total_tenants)}
          description="Contas cadastradas"
          helper="Total de clinicas na plataforma."
          icon={<Building2 size={18} />}
        />
        <StatCard
          title="Usuarios ativos"
          value={numberFormatter.format(metricsQuery.data.total_users)}
          description="Base de operadores"
          helper="Usuarios com acesso em tenants."
          icon={<Users size={18} />}
        />
        <StatCard
          title="Mensagens processadas"
          value={numberFormatter.format(metricsQuery.data.total_messages)}
          description="Volume operacional"
          helper="Mensagens registradas no acumulado."
          icon={<MessageSquareText size={18} />}
        />
        <StatCard
          title="Campanhas em execucao"
          value={numberFormatter.format(metricsQuery.data.active_campaigns)}
          description="Acoes comerciais ativas"
          helper="Campanhas com processamento aberto."
          icon={<ShieldCheck size={18} />}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-4">
        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle className="text-base">Uptime API</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <p className="text-2xl font-semibold text-stone-900">{formatUptime(monitoring.uptime_seconds)}</p>
            <p className="text-stone-600">Ultima coleta: {formatDateTimeBR(monitoring.generated_at)}</p>
          </CardContent>
        </Card>
        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle className="text-base">Saude de servicos</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-stone-700">
            <p>API: <StatusBadge value={monitoring.services.api.status} /></p>
            <p>Banco: <StatusBadge value={monitoring.services.database.status} /></p>
            <p>Redis: <StatusBadge value={monitoring.services.redis.status} /></p>
            <p className="text-xs text-stone-500">
              Latencia DB {monitoring.services.database.latency_ms} ms • Redis {monitoring.services.redis.latency_ms} ms
            </p>
          </CardContent>
        </Card>
        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle className="text-base">Erros criticos</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm text-stone-700">
            <p>Falhas ultima hora: {numberFormatter.format(monitoring.errors.failed_jobs_last_hour)}</p>
            <p>Falhas 24h: {numberFormatter.format(monitoring.errors.failed_jobs_24h)}</p>
            <p>Incidentes criticos: {numberFormatter.format(monitoring.incidents.critical_open)}</p>
          </CardContent>
        </Card>
        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle className="text-base">Risco financeiro</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm text-stone-700">
            <p>Tenants em atraso: {numberFormatter.format(monitoring.billing.tenants_past_due)}</p>
            <p>Tenants bloqueados: {numberFormatter.format(monitoring.billing.tenants_blocked)}</p>
            <p>Canal de alerta: {monitoring.alert_channels[0] ?? "-"}</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <BellRing size={16} />
              Alertas ativos
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {monitoring.alerts.length ? (
              monitoring.alerts.map((alert) => (
                <div key={`${alert.title}-${alert.description}`} className="rounded-lg border border-stone-200 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-stone-800">{alert.title}</p>
                    <Badge className={severityClass(alert.severity)}>{alert.severity}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-stone-600">{alert.description}</p>
                </div>
              ))
            ) : (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">
                Nenhum alerta critico no momento.
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertTriangle size={16} />
              Logs recentes de falha
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {monitoring.errors.recent_failures.length ? (
              monitoring.errors.recent_failures.slice(0, 6).map((failure) => (
                <div key={failure.id} className="rounded-lg border border-stone-200 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-stone-800">{failure.job_type}</p>
                    <span className="text-xs text-stone-500">{formatDateTimeBR(failure.finished_at)}</span>
                  </div>
                  <p className="text-xs text-stone-600">{failure.error_message ?? "Sem mensagem de erro registrada."}</p>
                  <p className="mt-1 text-[11px] text-stone-500">Tentativas: {failure.attempts}</p>
                </div>
              ))
            ) : (
              <div className="rounded-lg border border-stone-200 bg-stone-50 p-3 text-sm text-stone-600">
                Nenhuma falha registrada recentemente.
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <DataTable<AdminOverview["plan_distribution"][number]>
          title="Planos e limites"
          rows={overviewQuery.data.plan_distribution}
          getRowId={(item) => item.code}
          searchBy={(item) => `${item.name} ${item.code}`}
          columns={[
            { key: "plano", label: "Plano", render: (item) => item.name },
            { key: "codigo", label: "Codigo", render: (item) => item.code },
            { key: "tenants", label: "Tenants", render: (item) => numberFormatter.format(item.tenants) },
            { key: "limite_usuarios", label: "Limite de usuarios", render: (item) => numberFormatter.format(item.limits.max_users) },
            { key: "limite_unidades", label: "Limite de unidades", render: (item) => numberFormatter.format(item.limits.max_units) },
            {
              key: "limite_mensagens",
              label: "Limite de mensagens/mes",
              render: (item) => numberFormatter.format(item.limits.max_monthly_messages),
            },
          ]}
          emptyTitle="Sem planos ativos"
          emptyDescription="Cadastre planos para controlar limites por tenant."
        />

        <DataTable<AdminOverview["feature_flags"][number]>
          title="Feature flags"
          rows={overviewQuery.data.feature_flags}
          getRowId={(item) => item.key}
          searchBy={(item) => `${item.key}`}
          columns={[
            { key: "flag", label: "Flag", render: (item) => item.key },
            {
              key: "tenants_habilitados",
              label: "Tenants habilitados",
              render: (item) => numberFormatter.format(item.enabled_tenants),
            },
          ]}
          emptyTitle="Sem feature flags"
          emptyDescription="Nenhuma feature flag cadastrada para tenants."
        />
      </div>

      <DataTable<AdminOverview["usage_by_tenant"][number]>
        title="Uso por tenant"
        rows={overviewQuery.data.usage_by_tenant}
        getRowId={(item) => item.tenant_id}
        searchBy={(item) => `${item.tenant_name} ${item.plan}`}
        columns={[
          { key: "tenant", label: "Tenant", render: (item) => item.tenant_name },
          { key: "plano", label: "Plano", render: (item) => item.plan },
          { key: "usuarios", label: "Usuarios", render: (item) => numberFormatter.format(item.users) },
          { key: "unidades", label: "Unidades", render: (item) => numberFormatter.format(item.units) },
          { key: "mensagens", label: "Mensagens", render: (item) => numberFormatter.format(item.messages) },
          {
            key: "uso_usuarios",
            label: "Uso de usuarios",
            render: (item) => `${percentFormatter.format(percentUsage(item.users, item.limits.users))}%`,
          },
          {
            key: "uso_unidades",
            label: "Uso de unidades",
            render: (item) => `${percentFormatter.format(percentUsage(item.units, item.limits.units))}%`,
          },
          {
            key: "uso_mensagens",
            label: "Uso de mensagens",
            render: (item) => `${percentFormatter.format(percentUsage(item.messages, item.limits.monthly_messages))}%`,
          },
          {
            key: "status",
            label: "Status",
            render: () => <StatusBadge value={overviewQuery.data.platform_status.api === "ok" ? "ativo" : "inativo"} />,
          },
        ]}
        emptyTitle="Sem uso registrado"
        emptyDescription="Ainda nao ha tenants com uso consolidado."
      />

      <DataTable<TenantItem>
        title="Tenants da plataforma"
        rows={tenantsQuery.data.data ?? []}
        getRowId={(item) => item.id}
        searchBy={(item) => `${item.trade_name} ${item.legal_name} ${item.slug}`}
        columns={[
          {
            key: "trade_name",
            label: "Clinica",
            render: (item) => (
              <div>
                <p className="font-semibold text-stone-800">{item.trade_name}</p>
                <p className="text-xs text-stone-500">{item.slug}</p>
              </div>
            ),
          },
          {
            key: "legal_name",
            label: "Razao social",
            render: (item) => item.legal_name,
          },
          {
            key: "status",
            label: "Assinatura",
            render: (item) => <StatusBadge value={item.subscription_status} />,
          },
          {
            key: "active",
            label: "Ativo",
            render: (item) => <StatusBadge value={item.is_active ? "ativo" : "inativo"} />,
          },
        ]}
        emptyTitle="Nenhum tenant disponivel"
        emptyDescription="Cadastre um tenant para iniciar a operacao multi-clinica."
      />

      <Card className="border-stone-200">
        <CardContent className="flex items-center gap-2 p-4 text-sm text-stone-700">
          <GaugeCircle size={16} className="text-primary" />
          Saude da plataforma: API {monitoring.services.api.status}, banco {monitoring.services.database.status}, redis{" "}
          {monitoring.services.redis.status}. Jobs falhos na ultima hora:{" "}
          {numberFormatter.format(monitoring.errors.failed_jobs_last_hour)}.
        </CardContent>
      </Card>
    </div>
  );
}

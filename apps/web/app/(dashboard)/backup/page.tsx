"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Database,
  Download,
  FileText,
  HardDrive,
  MessageSquare,
  Play,
  RefreshCw,
  Settings,
  ShieldCheck,
  Users,
} from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { api } from "@/lib/api";
import { triggerBlobDownload } from "@/lib/download";
import { formatDateTimeBR } from "@/lib/formatters";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, cn } from "@odontoflux/ui";

type BackupConfig = {
  enabled: boolean;
  frequency: "daily" | "weekly" | "monthly";
  run_time: string;
  retention_days: number;
  automatic_scopes: string[];
  last_run_at?: string | null;
  next_run_at?: string | null;
};

type BackupScope = {
  key: string;
  label: string;
  description: string;
};

type BackupHistoryEntry = {
  id: string;
  scope: string;
  scope_label: string;
  trigger: "manual" | "automatic" | string;
  status: "success" | "failed" | string;
  started_at: string;
  finished_at?: string | null;
  filename?: string | null;
  size_bytes?: number | null;
  checksum?: string | null;
  row_counts?: Record<string, number>;
  file_count?: number;
  error_message?: string | null;
};

type BackupDashboardResponse = {
  config: BackupConfig;
  scopes: BackupScope[];
  history: BackupHistoryEntry[];
  summary: {
    total_backups: number;
    successful_backups: number;
    failed_backups: number;
    latest_success_at?: string | null;
    latest_scope?: string | null;
    stored_size_bytes: number;
  };
};

const DEFAULT_CONFIG: BackupConfig = {
  enabled: false,
  frequency: "daily",
  run_time: "03:00",
  retention_days: 30,
  automatic_scopes: ["full"],
  last_run_at: null,
  next_run_at: null,
};

const SCOPE_ICONS: Record<string, typeof Database> = {
  full: Archive,
  clinic: Settings,
  patients: Users,
  appointments: CalendarDays,
  conversations: MessageSquare,
  commercial: CheckCircle2,
  documents: FileText,
  files: HardDrive,
};

const FREQUENCY_LABELS: Record<BackupConfig["frequency"], string> = {
  daily: "Diario",
  weekly: "Semanal",
  monthly: "Mensal",
};

function formatBytes(value?: number | null) {
  const size = Number(value || 0);
  if (size <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1);
  return `${(size / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function statusBadgeClass(status: string) {
  if (status === "success") return "bg-emerald-100 text-emerald-700";
  if (status === "failed") return "bg-red-100 text-red-700";
  return "bg-amber-100 text-amber-800";
}

function triggerLabel(value: string) {
  return value === "automatic" ? "Automatico" : "Manual";
}

export default function BackupPage() {
  const queryClient = useQueryClient();
  const [configDraft, setConfigDraft] = useState<BackupConfig>(DEFAULT_CONFIG);

  const backupQuery = useQuery<BackupDashboardResponse>({
    queryKey: ["backups-dashboard"],
    queryFn: async () => (await api.get("/backups")).data,
  });

  useEffect(() => {
    if (backupQuery.data?.config) {
      setConfigDraft({
        ...DEFAULT_CONFIG,
        ...backupQuery.data.config,
        automatic_scopes: backupQuery.data.config.automatic_scopes?.length
          ? backupQuery.data.config.automatic_scopes
          : ["full"],
      });
    }
  }, [backupQuery.data?.config]);

  const updateConfigMutation = useMutation({
    mutationFn: async () => (await api.put<BackupConfig>("/backups/config", configDraft)).data,
    onSuccess: () => {
      toast.success("Configuracao de backup salva.");
      queryClient.invalidateQueries({ queryKey: ["backups-dashboard"] });
    },
    onError: () => toast.error("Nao foi possivel salvar a configuracao de backup."),
  });

  const runBackupMutation = useMutation({
    mutationFn: async (scope: string) => (await api.post<BackupHistoryEntry>("/backups/run", { scope })).data,
    onSuccess: (entry) => {
      toast.success(`${entry.scope_label || "Backup"} concluido.`);
      queryClient.invalidateQueries({ queryKey: ["backups-dashboard"] });
    },
    onError: () => toast.error("Nao foi possivel executar o backup."),
  });

  const history = backupQuery.data?.history ?? [];
  const scopes = backupQuery.data?.scopes ?? [];
  const summary = backupQuery.data?.summary;
  const latestSuccess = history.find((item) => item.status === "success");
  const latestFailed = history.find((item) => item.status === "failed");

  const selectedAutomaticScopes = useMemo(
    () => new Set(configDraft.automatic_scopes || []),
    [configDraft.automatic_scopes],
  );

  function toggleAutomaticScope(scope: string) {
    const next = new Set(configDraft.automatic_scopes || []);
    if (next.has(scope)) next.delete(scope);
    else next.add(scope);
    setConfigDraft((current) => ({
      ...current,
      automatic_scopes: Array.from(next).length ? Array.from(next) : ["full"],
    }));
  }

  async function downloadBackup(entry: BackupHistoryEntry) {
    try {
      if (!entry.size_bytes || entry.size_bytes <= 0) {
        toast.error("Este backup esta vazio ou invalido. Gere um novo backup antes de baixar.");
        return;
      }

      const response = await api.get<Blob>(`/backups/${entry.id}/download`, {
        responseType: "blob",
        timeout: 120_000,
      });
      const contentType = String(response.headers["content-type"] || "application/zip");
      const blob = response.data instanceof Blob
        ? response.data
        : new Blob([response.data], { type: contentType });
      if (blob.size <= 0) {
        toast.error("O arquivo baixado veio vazio. Gere um novo backup e tente novamente.");
        return;
      }

      triggerBlobDownload(blob, entry.filename || `backup-${entry.id}.zip`);
      toast.success("Download do backup iniciado.");
    } catch (error: unknown) {
      let apiMessage: string | null = null;
      if (
        typeof error === "object" &&
        error &&
        "response" in error
      ) {
        const responseData = (error as { response?: { data?: unknown } }).response?.data;
        if (
          responseData &&
          typeof responseData === "object" &&
          "error" in responseData &&
          typeof (responseData as { error?: { message?: string } }).error?.message === "string"
        ) {
          apiMessage = (responseData as { error?: { message?: string } }).error?.message || null;
        } else if (responseData instanceof Blob) {
          try {
            const errorText = await responseData.text();
            const parsed = JSON.parse(errorText) as { error?: { message?: string } };
            apiMessage = typeof parsed.error?.message === "string" ? parsed.error.message : null;
          } catch {
            apiMessage = null;
          }
        }
      }
      toast.error(apiMessage || "Nao foi possivel baixar o backup.");
    }
  }

  if (backupQuery.isLoading) return <LoadingState message="Carregando central de backup..." />;
  if (backupQuery.isError || !backupQuery.data) return <ErrorState message="Nao foi possivel carregar os backups." />;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Seguranca operacional"
        title="Backup da clinica"
        description="Proteja dados, agenda, conversas, documentos e configuracoes do tenant com backups manuais e automaticos."
        meta={
          <Badge className={configDraft.enabled ? "bg-emerald-100 text-emerald-700" : "bg-stone-200 text-stone-700"}>
            {configDraft.enabled ? "Automatico ligado" : "Automatico desligado"}
          </Badge>
        }
      />

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Card className="border-border bg-card">
          <CardContent className="p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Status</p>
                <p className="mt-2 text-2xl font-black text-foreground">
                  {configDraft.enabled ? "Ativo" : "Manual"}
                </p>
              </div>
              <div className="grid h-11 w-11 place-items-center rounded-2xl bg-primary/10 text-primary">
                <ShieldCheck size={21} />
              </div>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              {configDraft.enabled ? `Roda ${FREQUENCY_LABELS[configDraft.frequency].toLowerCase()} as ${configDraft.run_time}.` : "Backup automatico pausado."}
            </p>
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardContent className="p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Proxima rotina</p>
            <p className="mt-2 text-lg font-black text-foreground">
              {configDraft.next_run_at ? formatDateTimeBR(configDraft.next_run_at) : "Nao agendada"}
            </p>
            <p className="mt-2 text-xs text-muted-foreground">Calculada quando o backup automatico esta ligado.</p>
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardContent className="p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Ultimo sucesso</p>
            <p className="mt-2 text-lg font-black text-foreground">
              {summary?.latest_success_at ? formatDateTimeBR(summary.latest_success_at) : "Ainda nao existe"}
            </p>
            <p className="mt-2 text-xs text-muted-foreground">
              {latestSuccess ? `${latestSuccess.scope_label} - ${formatBytes(latestSuccess.size_bytes)}` : "Execute um backup manual para iniciar."}
            </p>
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardContent className="p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Armazenado</p>
            <p className="mt-2 text-2xl font-black text-foreground">{formatBytes(summary?.stored_size_bytes)}</p>
            <p className="mt-2 text-xs text-muted-foreground">
              {summary?.successful_backups ?? 0} sucesso(s), {summary?.failed_backups ?? 0} falha(s).
            </p>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.05fr_1.45fr]">
        <Card
          className="overflow-hidden border-border bg-card"
          style={{
            boxShadow: "0 18px 55px color-mix(in srgb, var(--tenant-primary) 10%, transparent)",
          }}
        >
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock3 size={18} />
              Backup automatico
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 p-5 pt-0">
            <button
              type="button"
              className={cn(
                "flex w-full items-center justify-between rounded-2xl border p-4 text-left transition",
                configDraft.enabled
                  ? "border-primary/30 bg-primary/10 text-foreground"
                  : "border-border bg-muted/45 text-foreground",
              )}
              onClick={() => setConfigDraft((current) => ({ ...current, enabled: !current.enabled }))}
            >
              <div>
                <p className="font-black">{configDraft.enabled ? "Automatico ligado" : "Automatico desligado"}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Use para manter copias recorrentes sem depender de acao manual.
                </p>
              </div>
              <span
                className={cn(
                  "relative h-7 w-12 rounded-full transition",
                  configDraft.enabled ? "bg-primary" : "bg-muted-foreground/30",
                )}
              >
                <span
                  className={cn(
                    "absolute top-1 h-5 w-5 rounded-full bg-white shadow transition",
                    configDraft.enabled ? "left-6" : "left-1",
                  )}
                />
              </span>
            </button>

            <div className="grid gap-3 sm:grid-cols-3">
              <label className="space-y-1">
                <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Frequencia</span>
                <select
                  className="h-11 w-full rounded-xl border border-border bg-card px-3 text-sm text-foreground outline-none focus:border-primary"
                  value={configDraft.frequency}
                  onChange={(event) =>
                    setConfigDraft((current) => ({ ...current, frequency: event.target.value as BackupConfig["frequency"] }))
                  }
                >
                  <option value="daily">Diario</option>
                  <option value="weekly">Semanal</option>
                  <option value="monthly">Mensal</option>
                </select>
              </label>
              <label className="space-y-1">
                <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Horario</span>
                <input
                  type="time"
                  className="h-11 w-full rounded-xl border border-border bg-card px-3 text-sm text-foreground outline-none focus:border-primary"
                  value={configDraft.run_time}
                  onChange={(event) => setConfigDraft((current) => ({ ...current, run_time: event.target.value }))}
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Retencao</span>
                <input
                  type="number"
                  min={1}
                  max={365}
                  className="h-11 w-full rounded-xl border border-border bg-card px-3 text-sm text-foreground outline-none focus:border-primary"
                  value={configDraft.retention_days}
                  onChange={(event) =>
                    setConfigDraft((current) => ({
                      ...current,
                      retention_days: Math.max(1, Math.min(Number(event.target.value || 30), 365)),
                    }))
                  }
                />
              </label>
            </div>

            <div className="rounded-2xl border border-border bg-muted/35 p-3">
              <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">O que entra no automatico</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {scopes.map((scope) => (
                  <button
                    key={scope.key}
                    type="button"
                    className={cn(
                      "rounded-full border px-3 py-1.5 text-xs font-bold transition",
                      selectedAutomaticScopes.has(scope.key)
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-border bg-card text-foreground hover:border-primary/40",
                    )}
                    onClick={() => toggleAutomaticScope(scope.key)}
                  >
                    {scope.label}
                  </button>
                ))}
              </div>
            </div>

            <Button
              className="w-full gap-2"
              onClick={() => updateConfigMutation.mutate()}
              disabled={updateConfigMutation.isPending}
            >
              <RefreshCw size={15} />
              {updateConfigMutation.isPending ? "Salvando..." : "Salvar rotina de backup"}
            </Button>
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Database size={18} />
              Backup manual separado
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 p-5 pt-0 md:grid-cols-2">
            {scopes.map((scope) => {
              const Icon = SCOPE_ICONS[scope.key] ?? Database;
              const isRunning = runBackupMutation.isPending && runBackupMutation.variables === scope.key;
              return (
                <div
                  key={scope.key}
                  className="rounded-2xl border border-border bg-muted/30 p-4 transition hover:border-primary/35 hover:bg-card"
                >
                  <div className="flex items-start gap-3">
                    <div className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-primary/10 text-primary">
                      <Icon size={18} />
                    </div>
                    <div className="min-w-0">
                      <p className="font-black text-foreground">{scope.label}</p>
                      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{scope.description}</p>
                    </div>
                  </div>
                  <Button
                    variant={scope.key === "full" ? "default" : "outline"}
                    className="mt-4 w-full gap-2"
                    onClick={() => runBackupMutation.mutate(scope.key)}
                    disabled={runBackupMutation.isPending}
                  >
                    <Play size={14} />
                    {isRunning ? "Gerando..." : "Gerar agora"}
                  </Button>
                </div>
              );
            })}
          </CardContent>
        </Card>
      </section>

      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle className="flex items-center justify-between gap-3">
            <span>Historico de backups</span>
            <Badge className="bg-muted text-muted-foreground">{history.length} registro(s)</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 p-5 pt-0">
          {latestFailed ? (
            <div className="rounded-2xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              Ultima falha em {formatDateTimeBR(latestFailed.finished_at || latestFailed.started_at)}:{" "}
              {latestFailed.error_message || "erro nao informado"}
            </div>
          ) : null}

          {history.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-border bg-muted/25 p-8 text-center">
              <p className="text-lg font-black text-foreground">Nenhum backup criado ainda</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Comece com Backup completo ou ligue a rotina automatica.
              </p>
            </div>
          ) : (
            history.map((entry) => (
              <div
                key={entry.id}
                className="grid gap-3 rounded-2xl border border-border bg-muted/25 p-4 lg:grid-cols-[1.2fr_0.8fr_0.8fr_auto]"
              >
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge className={statusBadgeClass(entry.status)}>
                      {entry.status === "success" ? "Sucesso" : "Falha"}
                    </Badge>
                    <Badge className="bg-card text-foreground">{triggerLabel(entry.trigger)}</Badge>
                  </div>
                  <p className="mt-2 font-black text-foreground">{entry.scope_label}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {entry.filename || entry.id}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Quando</p>
                  <p className="mt-1 text-sm font-semibold text-foreground">
                    {formatDateTimeBR(entry.finished_at || entry.started_at)}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Conteudo</p>
                  <p className="mt-1 text-sm font-semibold text-foreground">
                    {Object.values(entry.row_counts || {}).reduce((total, count) => total + Number(count || 0), 0)} registro(s)
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {entry.file_count || 0} arquivo(s) - {formatBytes(entry.size_bytes)}
                  </p>
                </div>
                <div className="flex items-center justify-start lg:justify-end">
                  <Button
                    variant="outline"
                    className="gap-2"
                    disabled={entry.status !== "success" || !entry.size_bytes || entry.size_bytes <= 0}
                    onClick={() => downloadBackup(entry)}
                  >
                    <Download size={14} />
                    Baixar
                  </Button>
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}

"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle2,
  PauseCircle,
  PlayCircle,
  RefreshCw,
  Send,
  Trash2,
  UsersRound,
} from "lucide-react";
import { toast } from "sonner";

import { useAdmSession } from "@/hooks/use-adm-session";
import { canAccessAdmPage } from "@/lib/adm-page-access";
import { api } from "@/lib/api";
import { getAdminAccessToken } from "@/lib/auth";
import { formatDateTimeBR } from "@/lib/formatters";
import { Badge, Button, Card, CardContent, Input } from "@odontoflux/ui";

type ProspectPreview = {
  id: string;
  clinic_name: string;
  city?: string | null;
  state?: string | null;
  status: string;
  temperature: string;
  score: number;
  demo_status: string;
};

type EligibilityResponse = {
  eligible_count: number;
  preview: ProspectPreview[];
  filters: Record<string, unknown>;
};

type BatchSummary = Record<string, number>;

type BatchItem = {
  id: string;
  prospect: ProspectPreview | null;
  status: string;
  current_step?: string | null;
  last_reply_classification?: string | null;
  pause_reason?: string | null;
  last_message_preview?: string | null;
  last_error_message?: string | null;
  demo_generated_automatically: boolean;
  conversation_id?: string | null;
  sent_count: number;
  received_count: number;
  attempts: number;
  started_at?: string | null;
  last_activity_at?: string | null;
  finished_at?: string | null;
  open_adm_whatsapp_href?: string | null;
};

type Batch = {
  id: string;
  status: string;
  requested_count: number;
  selected_count: number;
  filters: Record<string, unknown>;
  summary: BatchSummary;
  stop_reason?: string | null;
  started_at?: string | null;
  paused_at?: string | null;
  completed_at?: string | null;
  last_processed_at?: string | null;
  created_at: string;
  updated_at: string;
  items?: BatchItem[];
};

type BatchListResponse = {
  data: Batch[];
};

type Runtime = {
  transport: string;
  sender_tenant_slug: string;
  bridge_enabled: boolean;
  bridge_configured: boolean;
  bridge_pending: number;
  bridge_processing: number;
  bridge_failed: number;
  bridge_dead_letter: number;
  bridge_command?: string | null;
};

type NoSiteOutreachStage = "first" | "second" | "third";

type NoSiteOutreachFlowConfig = {
  first_messages: string[];
  second_messages: string[];
  third_messages: string[];
};

type NoSiteEligibilityResponse = {
  stage: NoSiteOutreachStage;
  eligible_count: number;
  preview: ProspectPreview[];
  blocked_summary: Record<string, number>;
  limit: number;
};

type NoSiteBulkResponse = {
  stage: NoSiteOutreachStage;
  eligible_count: number;
  requested_count: number;
  queued_count: number;
  skipped_count: number;
  errors: Array<{ prospect_id?: string | null; clinic_name?: string | null; code: string; message: string }>;
  blocked_summary: Record<string, number>;
};

const NO_SITE_OUTREACH_STAGES: Array<{ value: NoSiteOutreachStage; label: string; helper: string }> = [
  {
    value: "first",
    label: "1a mensagem",
    helper: "Primeiro contato para clinicas sem site.",
  },
  {
    value: "second",
    label: "2a mensagem",
    helper: "Follow-up permitido depois da primeira etapa; o bridge segura se precisar aguardar intervalo.",
  },
  {
    value: "third",
    label: "3a mensagem",
    helper: "Liberada somente quando ja existe resposta humana da clinica.",
  },
];

const DEFAULT_NO_SITE_OUTREACH_FLOW: NoSiteOutreachFlowConfig = {
  first_messages: [
    "Oi, tudo bem?\n\nNotei que a clinica ainda nao possui um site profissional.\n\nEu ja montei um modelo de site para a clinica e gostaria de mostrar ao responsavel.\n\nQuem seria a pessoa ideal para eu encaminhar?",
    "Oi, tudo bem? Encontrei a clinica no Google e vi que voces ainda nao aparecem com um site proprio. Aqui e o time comercial da ClinicFlux AI. Quem cuida dessa parte de site e WhatsApp por ai?",
    "Bom dia! Aqui e o time comercial da ClinicFlux AI. Vi a clinica pelo Google e parece que ainda nao existe um site vinculado. Posso falar com quem decide sobre presenca online e WhatsApp?",
  ],
  second_messages: [
    "Obrigado. Meu contato e comercial, nao e para agendamento de paciente. A ideia e mostrar um modelo simples de site local com WhatsApp, mapa e servicos. Quem seria o responsavel por isso?",
    "So para alinhar: falo pela ClinicFlux AI, no contato comercial. Vi uma oportunidade de site local para ajudar pacientes a encontrarem a clinica no Google. Posso encaminhar ao responsavel?",
    "Passando de forma bem objetiva: preparei um modelo de site para clinicas que ainda dependem so do Google e WhatsApp. Faz sentido eu mandar para quem cuida dessa decisao?",
  ],
  third_messages: [
    "Perfeito. Posso te enviar o preview do modelo de site da clinica para voce avaliar se faz sentido levar adiante?",
    "Boa. A proposta e simples: site local com WhatsApp, mapa, servicos e prova de confianca. Quer que eu te mostre o preview rapido?",
    "Combinado. Se voce me autorizar, envio um preview curto do site e depois voces decidem se vale conversar.",
  ],
};

function noSiteStageConfigKey(stage: NoSiteOutreachStage): keyof NoSiteOutreachFlowConfig {
  return `${stage}_messages` as keyof NoSiteOutreachFlowConfig;
}

function humanize(value?: string | null) {
  if (!value) return "-";
  return value
    .replace(/_/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}

function batchStatusClass(status?: string | null) {
  if (status === "completed") return "bg-emerald-100 text-emerald-800";
  if (status === "running") return "bg-cyan-100 text-cyan-800";
  if (status === "paused") return "bg-amber-100 text-amber-800";
  if (status === "failed") return "bg-rose-100 text-rose-800";
  return "bg-stone-100 text-stone-700";
}

function temperatureClass(value?: string | null) {
  if (value === "muito_quente" || value === "quente") return "bg-orange-100 text-orange-800";
  if (value === "morno") return "bg-amber-100 text-amber-800";
  return "bg-stone-100 text-stone-700";
}

export default function OutreachAutomationPage() {
  const queryClient = useQueryClient();
  const [hasToken, setHasToken] = useState(false);
  const [quantity, setQuantity] = useState("20");
  const [statusFilter, setStatusFilter] = useState("");
  const [temperatureFilter, setTemperatureFilter] = useState("");
  const [demoStatusFilter, setDemoStatusFilter] = useState("");
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null);
  const [noSiteStage, setNoSiteStage] = useState<NoSiteOutreachStage>("first");
  const [noSiteLimit, setNoSiteLimit] = useState("200");
  const [noSiteFlowDraft, setNoSiteFlowDraft] = useState<NoSiteOutreachFlowConfig>(DEFAULT_NO_SITE_OUTREACH_FLOW);

  useEffect(() => {
    setHasToken(Boolean(getAdminAccessToken()));
  }, []);

  const admSessionQuery = useAdmSession(hasToken);
  const admPermissions = admSessionQuery.data?.resolved_adm_page_permissions;
  const canViewPage = canAccessAdmPage(admPermissions, "adm_outreach_automation", "view");
  const canCreatePage = canAccessAdmPage(admPermissions, "adm_outreach_automation", "create");
  const canEditPage = canAccessAdmPage(admPermissions, "adm_outreach_automation", "edit");

  const runtimeQuery = useQuery<Runtime>({
    queryKey: ["adm-outreach-runtime"],
    queryFn: async () => (await api.get("/admin/outreach/runtime")).data,
    enabled: hasToken && canViewPage,
    retry: false,
  });

  const eligibilityQuery = useQuery<EligibilityResponse>({
    queryKey: ["adm-outreach-automation-eligible", quantity, statusFilter, temperatureFilter, demoStatusFilter],
    queryFn: async () =>
      (
        await api.get("/admin/outreach/automation/eligible", {
          params: {
            quantity: Number(quantity || 20),
            status: statusFilter || undefined,
            temperature: temperatureFilter || undefined,
            demo_status: demoStatusFilter || undefined,
          },
        })
      ).data,
    enabled: hasToken && canViewPage,
    retry: false,
  });

  const noSiteFlowQuery = useQuery<NoSiteOutreachFlowConfig>({
    queryKey: ["adm-no-site-outreach-flow"],
    queryFn: async () => (await api.get("/admin/outreach/no-site-flow")).data,
    enabled: hasToken && canViewPage,
    retry: false,
  });

  const noSiteEligibilityQuery = useQuery<NoSiteEligibilityResponse>({
    queryKey: ["adm-no-site-outreach-eligible", noSiteStage, noSiteLimit],
    queryFn: async () =>
      (
        await api.get("/admin/outreach/no-site/eligible", {
          params: {
            stage: noSiteStage,
            limit: Math.min(Math.max(Number(noSiteLimit || 200), 1), 200),
          },
        })
      ).data,
    enabled: hasToken && canViewPage,
    retry: false,
  });

  const batchesQuery = useQuery<BatchListResponse>({
    queryKey: ["adm-outreach-automation-batches"],
    queryFn: async () => (await api.get("/admin/outreach/automation/batches", { params: { limit: 20 } })).data,
    enabled: hasToken && canViewPage,
    retry: false,
    refetchInterval: 10_000,
  });

  useEffect(() => {
    if (!noSiteFlowQuery.data) return;
    setNoSiteFlowDraft({
      first_messages: noSiteFlowQuery.data.first_messages?.slice(0, 3) || DEFAULT_NO_SITE_OUTREACH_FLOW.first_messages,
      second_messages: noSiteFlowQuery.data.second_messages?.slice(0, 3) || DEFAULT_NO_SITE_OUTREACH_FLOW.second_messages,
      third_messages: noSiteFlowQuery.data.third_messages?.slice(0, 3) || DEFAULT_NO_SITE_OUTREACH_FLOW.third_messages,
    });
  }, [noSiteFlowQuery.data]);

  useEffect(() => {
    const batches = batchesQuery.data?.data || [];
    if (!batches.length) {
      if (selectedBatchId) setSelectedBatchId(null);
      return;
    }
    if (!selectedBatchId || !batches.some((batch) => batch.id === selectedBatchId)) {
      setSelectedBatchId(batches[0].id);
    }
  }, [batchesQuery.data?.data, selectedBatchId]);

  const batchDetailQuery = useQuery<Batch>({
    queryKey: ["adm-outreach-automation-batch-detail", selectedBatchId],
    queryFn: async () => (await api.get(`/admin/outreach/automation/batches/${selectedBatchId}`)).data,
    enabled: hasToken && canViewPage && Boolean(selectedBatchId),
    retry: false,
    refetchInterval: 8_000,
  });

  const startMutation = useMutation({
    mutationFn: async () =>
      (
        await api.post<Batch>("/admin/outreach/automation/batches", {
          quantity: Number(quantity || 20),
          status: statusFilter || null,
          temperature: temperatureFilter || null,
          demo_status: demoStatusFilter || null,
        })
      ).data,
    onSuccess: (data) => {
      setSelectedBatchId(data.id);
      toast.success("Automacao comercial iniciada.");
      queryClient.invalidateQueries({ queryKey: ["adm-outreach-automation-batches"] });
      queryClient.invalidateQueries({ queryKey: ["adm-outreach-automation-eligible"] });
      queryClient.invalidateQueries({ queryKey: ["adm-outreach-runtime"] });
    },
    onError: () => toast.error("Nao foi possivel iniciar a automacao."),
  });

  const updateNoSiteFlowMessage = (stage: NoSiteOutreachStage, index: number, value: string) => {
    const key = noSiteStageConfigKey(stage);
    setNoSiteFlowDraft((current) => {
      const nextMessages = [...(current[key] || DEFAULT_NO_SITE_OUTREACH_FLOW[key])].slice(0, 3);
      while (nextMessages.length < 3) nextMessages.push("");
      nextMessages[index] = value;
      return { ...current, [key]: nextMessages };
    });
  };

  const saveNoSiteFlowMutation = useMutation({
    mutationFn: async () => (await api.put<NoSiteOutreachFlowConfig>("/admin/outreach/no-site-flow", noSiteFlowDraft)).data,
    onSuccess: (data) => {
      setNoSiteFlowDraft(data);
      toast.success("Mensagens para clinicas sem site salvas.");
      queryClient.invalidateQueries({ queryKey: ["adm-no-site-outreach-flow"] });
    },
    onError: () => toast.error("Nao foi possivel salvar as mensagens sem-site."),
  });

  const sendAllNoSiteMutation = useMutation({
    mutationFn: async () =>
      (
        await api.post<NoSiteBulkResponse>("/admin/outreach/no-site/send-all", {
          stage: noSiteStage,
          limit: Math.min(Math.max(Number(noSiteLimit || 200), 1), 500),
        })
      ).data,
    onSuccess: (data) => {
      toast.success(`${data.queued_count} clinica(s) sem site entraram na fila da ${NO_SITE_OUTREACH_STAGES.find((stage) => stage.value === data.stage)?.label || "etapa"}.`);
      queryClient.invalidateQueries({ queryKey: ["adm-no-site-outreach-eligible"] });
      queryClient.invalidateQueries({ queryKey: ["adm-outreach-runtime"] });
      queryClient.invalidateQueries({ queryKey: ["adm-outreach-automation-eligible"] });
    },
    onError: () => toast.error("Nao foi possivel disparar as mensagens sem-site."),
  });

  const pauseMutation = useMutation({
    mutationFn: async (batchId: string) => (await api.post<Batch>(`/admin/outreach/automation/batches/${batchId}/pause`)).data,
    onSuccess: () => {
      toast.success("Lote pausado.");
      queryClient.invalidateQueries({ queryKey: ["adm-outreach-automation-batches"] });
      queryClient.invalidateQueries({ queryKey: ["adm-outreach-automation-batch-detail", selectedBatchId] });
    },
    onError: () => toast.error("Nao foi possivel pausar o lote."),
  });

  const resumeMutation = useMutation({
    mutationFn: async (batchId: string) => (await api.post<Batch>(`/admin/outreach/automation/batches/${batchId}/resume`)).data,
    onSuccess: () => {
      toast.success("Lote retomado.");
      queryClient.invalidateQueries({ queryKey: ["adm-outreach-automation-batches"] });
      queryClient.invalidateQueries({ queryKey: ["adm-outreach-automation-batch-detail", selectedBatchId] });
    },
    onError: () => toast.error("Nao foi possivel retomar o lote."),
  });

  const deleteMutation = useMutation({
    mutationFn: async (batchId: string) => {
      await api.delete(`/admin/outreach/automation/batches/${batchId}`);
      return batchId;
    },
    onSuccess: (deletedBatchId) => {
      if (selectedBatchId === deletedBatchId) {
        setSelectedBatchId(null);
      }
      toast.success("Lote apagado.");
      queryClient.invalidateQueries({ queryKey: ["adm-outreach-automation-batches"] });
      queryClient.invalidateQueries({ queryKey: ["adm-outreach-automation-batch-detail", deletedBatchId] });
      queryClient.invalidateQueries({ queryKey: ["adm-outreach-runtime"] });
    },
    onError: () => toast.error("Nao foi possivel apagar o lote."),
  });

  const selectedBatch = batchDetailQuery.data ?? null;
  const noSiteStageMeta = NO_SITE_OUTREACH_STAGES.find((stage) => stage.value === noSiteStage) || NO_SITE_OUTREACH_STAGES[0];
  const noSiteEligibleCount = noSiteEligibilityQuery.data?.eligible_count ?? 0;
  const noSiteBulkLimit = Math.min(Math.max(Number(noSiteLimit || 200), 1), 500);
  const noSiteSendCount = Math.min(noSiteEligibleCount, noSiteBulkLimit);
  const batchCards = useMemo(() => {
    const summary = selectedBatch?.summary || {};
    return [
      { label: "Na fila", value: summary.queued ?? 0 },
      { label: "Em resposta", value: summary.waiting_reply ?? 0 },
      { label: "Concluidas", value: summary.completed ?? 0 },
      { label: "Pausadas", value: summary.paused ?? 0 },
      { label: "Falhas", value: summary.failed ?? 0 },
    ];
  }, [selectedBatch?.summary]);

  if (!hasToken) {
    return (
      <main className="min-h-screen overflow-x-hidden bg-stone-100 p-6 text-stone-950">
        <Card className="mx-auto mt-20 max-w-xl border-stone-200 bg-white">
          <CardContent className="space-y-4 p-6">
            <div className="grid h-12 w-12 place-items-center rounded-xl bg-stone-950 text-sm font-black text-white">CF</div>
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-stone-500">Area interna</p>
              <h1 className="mt-1 text-2xl font-black">Entre no /adm primeiro</h1>
              <p className="mt-2 text-sm leading-6 text-stone-600">Esta central usa o mesmo login administrativo do CRM comercial.</p>
            </div>
            <Link href="/adm" className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-stone-950 px-4 text-sm font-bold text-white">
              Abrir login do /adm
              <ArrowLeft className="h-4 w-4 rotate-180" />
            </Link>
          </CardContent>
        </Card>
      </main>
    );
  }

  if (admSessionQuery.isLoading) {
    return (
      <main className="grid min-h-screen place-items-center overflow-x-hidden bg-stone-100 px-4 text-stone-950">
        <Card className="w-full max-w-md border-stone-200 bg-white">
          <CardContent className="p-8 text-center text-sm text-stone-600">Carregando permissoes...</CardContent>
        </Card>
      </main>
    );
  }

  if (!canViewPage) {
    return (
      <main className="grid min-h-screen place-items-center overflow-x-hidden bg-stone-100 px-4 text-stone-950">
        <Card className="w-full max-w-xl border-stone-200 bg-white">
          <CardContent className="space-y-3 p-8 text-center">
            <h1 className="text-2xl font-black">Sem acesso a automacao comercial</h1>
            <p className="text-sm leading-6 text-stone-600">Seu usuario nao tem permissao para operar essa area do /adm.</p>
            <Link href="/adm" className="inline-flex h-10 items-center justify-center rounded-lg bg-stone-950 px-4 text-sm font-bold text-white">
              Voltar ao CRM
            </Link>
          </CardContent>
        </Card>
      </main>
    );
  }

  return (
    <main className="min-h-screen overflow-x-hidden bg-stone-100 p-4 text-stone-950 md:p-6">
      <div className="mx-auto max-w-7xl space-y-4">
        <Card className="border-stone-200 bg-white">
          <CardContent className="space-y-4 p-5">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.18em] text-stone-500">Outreach automatico</p>
                <h1 className="mt-1 text-3xl font-black">Automacao comercial</h1>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-stone-600">
                  Escolha quantas clinicas entram no lote. O sistema gera a demo quando faltar, envia a primeira mensagem,
                  acompanha as respostas pelo bridge do WhatsApp Web e salva tudo no WhatsApp do /adm.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Link href="/adm/mensagens-para-clinicas" className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-stone-200 bg-white px-4 text-sm font-semibold text-stone-900">
                  <ArrowLeft className="h-4 w-4" />
                  Fluxo comercial
                </Link>
                <Button variant="outline" onClick={() => {
                  queryClient.invalidateQueries({ queryKey: ["adm-outreach-automation-batches"] });
                  queryClient.invalidateQueries({ queryKey: ["adm-outreach-automation-batch-detail", selectedBatchId] });
                  queryClient.invalidateQueries({ queryKey: ["adm-outreach-automation-eligible"] });
                  queryClient.invalidateQueries({ queryKey: ["adm-outreach-runtime"] });
                }}>
                  <RefreshCw className="h-4 w-4" />
                  Atualizar
                </Button>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <MetricCard label="Clinicas aptas" value={String(eligibilityQuery.data?.eligible_count ?? 0)} helper="Prontas para entrar no lote." />
              <MetricCard label="Bridge pendente" value={String(runtimeQuery.data?.bridge_pending ?? 0)} helper="Mensagens aguardando o whatsapp_web.py." />
              <MetricCard label="Bridge processando" value={String(runtimeQuery.data?.bridge_processing ?? 0)} helper="Itens ja reivindicados pelo bridge." />
              <MetricCard label="Falhas no bridge" value={String((runtimeQuery.data?.bridge_failed ?? 0) + (runtimeQuery.data?.bridge_dead_letter ?? 0))} helper={runtimeQuery.data?.bridge_command || "Configure o bridge para envio real."} />
            </div>
          </CardContent>
        </Card>

        <Card className="overflow-hidden border-cyan-200 bg-cyan-50">
          <CardContent className="space-y-5 p-5">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.18em] text-cyan-800">Clinicas sem site</p>
                <h2 className="mt-1 text-2xl font-black text-stone-950">Fluxo automatico em 3 mensagens</h2>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-cyan-950">
                  Configure 3 variacoes para cada etapa. Ao disparar, o sistema escolhe uma variacao aleatoria da etapa
                  selecionada, coloca no WhatsApp Web local e salva o historico no CRM.
                </p>
                <p className="mt-1 text-xs font-bold uppercase tracking-[0.16em] text-cyan-800">
                  A 3a mensagem so fica elegivel depois de resposta humana da clinica.
                </p>
              </div>
              <Button
                type="button"
                className="shrink-0 bg-cyan-700 text-white hover:bg-cyan-600"
                onClick={() => saveNoSiteFlowMutation.mutate()}
                disabled={!canEditPage || saveNoSiteFlowMutation.isPending || noSiteFlowQuery.isLoading}
              >
                <CheckCircle2 className="h-4 w-4" />
                {saveNoSiteFlowMutation.isPending ? "Salvando..." : "Salvar mensagens"}
              </Button>
            </div>

            <div className="grid gap-3 lg:grid-cols-[220px_160px_minmax(0,1fr)_260px]">
              <label className="block space-y-2">
                <span className="text-xs font-bold uppercase tracking-wide text-cyan-900">Etapa para disparar</span>
                <select
                  className="h-10 w-full rounded-lg border border-cyan-200 bg-white px-3 text-sm font-semibold text-stone-950"
                  value={noSiteStage}
                  onChange={(event) => setNoSiteStage(event.target.value as NoSiteOutreachStage)}
                >
                  {NO_SITE_OUTREACH_STAGES.map((stage) => (
                    <option key={stage.value} value={stage.value}>
                      {stage.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block space-y-2">
                <span className="text-xs font-bold uppercase tracking-wide text-cyan-900">Limite</span>
                <Input value={noSiteLimit} onChange={(event) => setNoSiteLimit(event.target.value)} />
              </label>

              <div className="rounded-2xl border border-cyan-200 bg-white p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-black text-stone-950">{noSiteStageMeta.label}</p>
                    <p className="mt-1 text-xs leading-5 text-stone-600">{noSiteStageMeta.helper}</p>
                  </div>
                  <Badge className="bg-cyan-100 text-cyan-800">{noSiteEligibleCount} elegivel(is)</Badge>
                </div>
                {Object.entries(noSiteEligibilityQuery.data?.blocked_summary || {}).length ? (
                  <p className="mt-3 text-xs leading-5 text-stone-500">
                    Bloqueios: {Object.entries(noSiteEligibilityQuery.data?.blocked_summary || {}).map(([key, value]) => `${humanize(key)} ${value}`).join(", ")}.
                  </p>
                ) : null}
              </div>

              <Button
                type="button"
                className="h-full min-h-16 bg-stone-950 text-white hover:bg-stone-800"
                disabled={!canCreatePage || sendAllNoSiteMutation.isPending || noSiteSendCount <= 0}
                onClick={() => {
                  if (!noSiteSendCount) return;
                  const confirmed = window.confirm(
                    `Enviar ${noSiteStageMeta.label.toLowerCase()} para ${noSiteSendCount} clinica(s) sem site?`,
                  );
                  if (!confirmed) return;
                  sendAllNoSiteMutation.mutate();
                }}
              >
                <Send className="h-4 w-4" />
                {sendAllNoSiteMutation.isPending ? "Enfileirando..." : `Enviar para ${noSiteSendCount || "todas"}`}
              </Button>
            </div>

            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
              <div className="grid gap-4 lg:grid-cols-3">
                {NO_SITE_OUTREACH_STAGES.map((stage) => {
                  const key = noSiteStageConfigKey(stage.value);
                  const messages = noSiteFlowDraft[key] || DEFAULT_NO_SITE_OUTREACH_FLOW[key];
                  return (
                    <div key={stage.value} className="rounded-2xl border border-cyan-200 bg-white p-4">
                      <p className="font-black text-stone-950">{stage.label}</p>
                      <p className="mt-1 text-xs leading-5 text-stone-500">{stage.helper}</p>
                      <div className="mt-3 space-y-2">
                        {[0, 1, 2].map((index) => (
                          <label key={`${stage.value}-${index}`} className="block">
                            <span className="mb-1 block text-xs font-bold uppercase tracking-wide text-stone-500">
                              Variacao {index + 1}
                            </span>
                            <textarea
                              className="min-h-[116px] w-full resize-y rounded-lg border border-cyan-200 bg-white px-3 py-2 text-sm leading-6 outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
                              value={messages[index] || ""}
                              onChange={(event) => updateNoSiteFlowMessage(stage.value, index, event.target.value)}
                              disabled={!canEditPage}
                            />
                          </label>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="rounded-2xl border border-cyan-200 bg-white p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-black text-stone-950">Preview da etapa</p>
                    <p className="mt-1 text-xs text-stone-500">Primeiras clinicas que receberao {noSiteStageMeta.label.toLowerCase()}.</p>
                  </div>
                  <Badge className="bg-stone-100 text-stone-700">Sem site</Badge>
                </div>
                <div className="mt-3 space-y-2">
                  {(noSiteEligibilityQuery.data?.preview || []).slice(0, 8).map((item) => (
                    <div key={item.id} className="rounded-xl border border-stone-200 bg-stone-50 p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <p className="text-sm font-bold text-stone-950">{item.clinic_name}</p>
                          <p className="text-xs text-stone-500">{[item.city, item.state].filter(Boolean).join(" / ") || "Sem cidade"}</p>
                        </div>
                        <span className="text-sm font-black text-stone-900">{item.score}</span>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-1">
                        <Badge className={batchStatusClass(item.status)}>{humanize(item.status)}</Badge>
                        <Badge className={temperatureClass(item.temperature)}>{humanize(item.temperature)}</Badge>
                      </div>
                    </div>
                  ))}
                  {!noSiteEligibilityQuery.isLoading && !(noSiteEligibilityQuery.data?.preview || []).length ? (
                    <div className="rounded-xl border border-dashed border-cyan-200 bg-cyan-50 p-4 text-sm leading-6 text-cyan-900">
                      Nenhuma clinica elegivel para esta etapa agora. Troque a etapa ou aguarde respostas para liberar o proximo passo.
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <section className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
          <Card className="border-stone-200 bg-white">
            <CardContent className="space-y-4 p-5">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.18em] text-stone-500">Novo lote</p>
                <h2 className="mt-1 text-xl font-black">Disparar automacao</h2>
              </div>

              <label className="block space-y-2">
                <span className="text-xs font-bold uppercase tracking-wide text-stone-500">Quantidade de clinicas</span>
                <Input value={quantity} onChange={(event) => setQuantity(event.target.value)} />
              </label>

              <label className="block space-y-2">
                <span className="text-xs font-bold uppercase tracking-wide text-stone-500">Filtrar por status</span>
                <Input value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} placeholder="Ex.: novo" />
              </label>

              <label className="block space-y-2">
                <span className="text-xs font-bold uppercase tracking-wide text-stone-500">Filtrar por temperatura</span>
                <Input value={temperatureFilter} onChange={(event) => setTemperatureFilter(event.target.value)} placeholder="Ex.: morno" />
              </label>

              <label className="block space-y-2">
                <span className="text-xs font-bold uppercase tracking-wide text-stone-500">Filtrar por demo</span>
                <Input value={demoStatusFilter} onChange={(event) => setDemoStatusFilter(event.target.value)} placeholder="Ex.: enviada" />
              </label>

              <Button className="w-full bg-cyan-600 text-white hover:bg-cyan-500" onClick={() => startMutation.mutate()} disabled={!canCreatePage || startMutation.isPending}>
                <Send className="h-4 w-4" />
                {startMutation.isPending ? "Iniciando..." : "Iniciar fluxo comercial automatico"}
              </Button>

              <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-black text-stone-950">Preview das proximas clinicas</p>
                  <Badge className="bg-cyan-100 text-cyan-800">{eligibilityQuery.data?.eligible_count ?? 0}</Badge>
                </div>
                <div className="mt-3 space-y-2">
                  {(eligibilityQuery.data?.preview || []).slice(0, 8).map((item) => (
                    <div key={item.id} className="rounded-xl border border-stone-200 bg-white p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <p className="text-sm font-bold text-stone-950">{item.clinic_name}</p>
                          <p className="text-xs text-stone-500">{[item.city, item.state].filter(Boolean).join(" / ") || "Sem cidade"}</p>
                        </div>
                        <span className="text-sm font-black text-stone-900">{item.score}</span>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-1">
                        <Badge className={batchStatusClass(item.status)}>{humanize(item.status)}</Badge>
                        <Badge className={temperatureClass(item.temperature)}>{humanize(item.temperature)}</Badge>
                        <Badge className="bg-stone-100 text-stone-700">{humanize(item.demo_status)}</Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="space-y-4">
            <Card className="border-stone-200 bg-white">
              <CardContent className="space-y-4 p-5">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.18em] text-stone-500">Lotes recentes</p>
                    <h2 className="mt-1 text-xl font-black">Operacao em andamento</h2>
                  </div>
                  {selectedBatch ? (
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        onClick={() => {
                          if (!window.confirm(`Apagar o lote ${selectedBatch.id.slice(0, 8)}? Esta acao remove os itens do lote.`)) return;
                          deleteMutation.mutate(selectedBatch.id);
                        }}
                        disabled={!canEditPage || deleteMutation.isPending}
                      >
                        <Trash2 className="h-4 w-4" />
                        Apagar
                      </Button>
                      <Button variant="outline" onClick={() => pauseMutation.mutate(selectedBatch.id)} disabled={!canEditPage || pauseMutation.isPending || selectedBatch.status === "paused"}>
                        <PauseCircle className="h-4 w-4" />
                        Pausar
                      </Button>
                      <Button variant="outline" onClick={() => resumeMutation.mutate(selectedBatch.id)} disabled={!canEditPage || resumeMutation.isPending || selectedBatch.status !== "paused"}>
                        <PlayCircle className="h-4 w-4" />
                        Retomar
                      </Button>
                    </div>
                  ) : null}
                </div>

                <div className="grid gap-3 md:grid-cols-5">
                  {batchCards.map((item) => (
                    <MetricCard key={item.label} label={item.label} value={String(item.value)} helper={selectedBatch ? `Lote ${selectedBatch.id.slice(0, 8)}` : "Selecione um lote"} />
                  ))}
                </div>

                <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
                  <div className="space-y-2">
                    {(batchesQuery.data?.data || []).map((batch) => (
                      <button
                        key={batch.id}
                        type="button"
                        onClick={() => setSelectedBatchId(batch.id)}
                        className={`w-full rounded-2xl border p-4 text-left transition ${selectedBatchId === batch.id ? "border-cyan-300 bg-cyan-50" : "border-stone-200 bg-stone-50 hover:bg-white"}`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-black text-stone-950">Lote {batch.id.slice(0, 8)}</p>
                            <p className="mt-1 text-xs text-stone-500">{formatDateTimeBR(batch.created_at) || "-"}</p>
                          </div>
                          <Badge className={batchStatusClass(batch.status)}>{humanize(batch.status)}</Badge>
                        </div>
                        <div className="mt-3 flex items-center justify-between text-xs text-stone-600">
                          <span>{batch.selected_count} clinicas</span>
                          <span>{(batch.summary?.completed ?? 0)} concluidas</span>
                        </div>
                      </button>
                    ))}
                  </div>

                  <Card className="border-stone-200 bg-stone-50">
                    <CardContent className="space-y-4 p-4">
                      {selectedBatch ? (
                        <>
                          <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                            <div>
                              <p className="text-xs font-bold uppercase tracking-[0.18em] text-stone-500">Detalhes do lote</p>
                              <h3 className="text-xl font-black">Lote {selectedBatch.id.slice(0, 8)}</h3>
                              <p className="mt-1 text-sm text-stone-600">
                                Status {humanize(selectedBatch.status)}. Criado em {formatDateTimeBR(selectedBatch.created_at) || "-"}.
                              </p>
                            </div>
                            <div className="flex items-center gap-2">
                              <Badge className={batchStatusClass(selectedBatch.status)}>{humanize(selectedBatch.status)}</Badge>
                              {selectedBatch.stop_reason ? <Badge className="bg-stone-200 text-stone-800">{humanize(selectedBatch.stop_reason)}</Badge> : null}
                            </div>
                          </div>

                          <div className="space-y-3">
                            {(selectedBatch.items || []).map((item) => (
                              <div key={item.id} className="rounded-2xl border border-stone-200 bg-white p-4">
                                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                                  <div>
                                    <p className="text-sm font-black text-stone-950">{item.prospect?.clinic_name || "Clinica indisponivel"}</p>
                                    <div className="mt-2 flex flex-wrap gap-1">
                                      <Badge className={batchStatusClass(item.status)}>{humanize(item.status)}</Badge>
                                      <Badge className={temperatureClass(item.prospect?.temperature)}>{humanize(item.prospect?.temperature)}</Badge>
                                      <Badge className="bg-stone-100 text-stone-700">Score {item.prospect?.score ?? 0}</Badge>
                                      <Badge className="bg-stone-100 text-stone-700">{humanize(item.prospect?.demo_status)}</Badge>
                                      {item.demo_generated_automatically ? <Badge className="bg-emerald-100 text-emerald-800">Demo automatica</Badge> : null}
                                    </div>
                                  </div>
                                  <div className="flex flex-wrap gap-2">
                                    {item.open_adm_whatsapp_href ? (
                                      <Link href={item.open_adm_whatsapp_href} className="inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-stone-200 bg-white px-3 text-xs font-semibold text-stone-900">
                                        <UsersRound className="h-4 w-4" />
                                        Abrir no WhatsApp
                                      </Link>
                                    ) : null}
                                  </div>
                                </div>

                                <div className="mt-4 grid gap-3 md:grid-cols-4">
                                  <Info label="Etapa atual" value={humanize(item.current_step)} />
                                  <Info label="Ultima classificacao" value={humanize(item.last_reply_classification)} />
                                  <Info label="Enviadas / recebidas" value={`${item.sent_count} / ${item.received_count}`} />
                                  <Info label="Ultima atividade" value={formatDateTimeBR(item.last_activity_at || null) || "-"} />
                                </div>

                                {item.last_message_preview ? (
                                  <div className="mt-3 rounded-xl border border-stone-200 bg-stone-50 p-3 text-sm leading-6 text-stone-700">
                                    {item.last_message_preview}
                                  </div>
                                ) : null}
                                {item.last_error_message ? (
                                  <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm leading-6 text-rose-800">
                                    {item.last_error_message}
                                  </div>
                                ) : null}
                              </div>
                            ))}
                          </div>
                        </>
                      ) : (
                        <div className="py-16 text-center text-sm text-stone-500">Selecione um lote para ver a operacao.</div>
                      )}
                    </CardContent>
                  </Card>
                </div>
              </CardContent>
            </Card>
          </div>
        </section>
      </div>
    </main>
  );
}

function MetricCard({ label, value, helper }: { label: string; value: string; helper: string }) {
  return (
    <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
      <p className="text-xs font-bold uppercase tracking-[0.18em] text-stone-500">{label}</p>
      <p className="mt-2 text-3xl font-black text-stone-950">{value}</p>
      <p className="mt-2 text-xs leading-5 text-stone-500">{helper}</p>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-stone-200 bg-stone-50 p-3">
      <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-stone-500">{label}</p>
      <p className="mt-2 text-sm font-semibold text-stone-900">{value}</p>
    </div>
  );
}

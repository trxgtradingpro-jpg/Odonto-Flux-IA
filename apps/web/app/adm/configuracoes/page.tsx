"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Bot, CheckCircle2, RefreshCw, Save, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { ErrorState, LoadingState } from "@/components/page-state";
import { useAdmSession } from "@/hooks/use-adm-session";
import { canAccessAdmPage } from "@/lib/adm-page-access";
import { api } from "@/lib/api";
import { getAdminAccessToken } from "@/lib/auth";
import { BRAND_NAME } from "@/lib/brand";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, cn } from "@odontoflux/ui";

type AgentTenant = {
  id: string;
  name: string;
  slug: string;
  subscription_status?: string | null;
};

type AgentSettingsScope = "platform" | "tenant";

type AgentConfig = {
  enabled: boolean;
  conversation_flow_mode: "legacy" | "structured_elite";
  structured_flow_enabled: boolean;
  llm_model: string;
  pre_send_review_enabled: boolean;
  repetition_guard_enabled: boolean;
  conversation_memory_enabled: boolean;
  auto_save_patient_data_enabled: boolean;
  handoff_triggers: {
    low_confidence: boolean;
    urgency: boolean;
    patient_irritated: boolean;
    schedule_error: boolean;
    review_failed: boolean;
  };
  channels: { whatsapp: boolean; webchat?: boolean };
  interactive_booking_options_enabled: boolean;
  business_hours: {
    timezone: string;
    weekdays: number[];
    start: string;
    end: string;
  };
  outside_business_hours_mode: "handoff" | "allow" | "silent";
  max_consecutive_auto_replies: number;
  confidence_threshold: number;
  human_queue_tag: string;
  tone: string;
  fallback_user_id?: string | null;
};

type AgentSettingsPayload = {
  scope?: AgentSettingsScope;
  tenant: AgentTenant | null;
  config: AgentConfig;
  model_options?: Array<{ value: string; label: string }>;
};

const DEFAULT_HANDOFF = {
  low_confidence: true,
  urgency: true,
  patient_irritated: true,
  schedule_error: true,
  review_failed: true,
};

function normalizeConfig(config: Partial<AgentConfig> | null | undefined): AgentConfig {
  return {
    enabled: config?.enabled ?? true,
    conversation_flow_mode: config?.conversation_flow_mode === "structured_elite" ? "structured_elite" : "legacy",
    structured_flow_enabled: Boolean(config?.structured_flow_enabled),
    llm_model: config?.llm_model ?? "",
    pre_send_review_enabled: Boolean(config?.pre_send_review_enabled),
    repetition_guard_enabled: config?.repetition_guard_enabled ?? true,
    conversation_memory_enabled: config?.conversation_memory_enabled ?? true,
    auto_save_patient_data_enabled: config?.auto_save_patient_data_enabled ?? true,
    handoff_triggers: { ...DEFAULT_HANDOFF, ...(config?.handoff_triggers ?? {}) },
    channels: { whatsapp: config?.channels?.whatsapp ?? true, webchat: config?.channels?.webchat ?? true },
    interactive_booking_options_enabled: config?.interactive_booking_options_enabled ?? true,
    business_hours: {
      timezone: config?.business_hours?.timezone ?? "America/Sao_Paulo",
      weekdays: config?.business_hours?.weekdays ?? [0, 1, 2, 3, 4],
      start: config?.business_hours?.start ?? "08:00",
      end: config?.business_hours?.end ?? "18:00",
    },
    outside_business_hours_mode: config?.outside_business_hours_mode ?? "allow",
    max_consecutive_auto_replies: config?.max_consecutive_auto_replies ?? 3,
    confidence_threshold: config?.confidence_threshold ?? 0.65,
    human_queue_tag: config?.human_queue_tag ?? "fila_humana_ia",
    tone: config?.tone ?? "humano, claro, consultivo, acolhedor e objetivo",
    fallback_user_id: config?.fallback_user_id ?? null,
  };
}

function ToggleRow({
  label,
  description,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className={cn("flex cursor-pointer items-start gap-3 rounded-lg border border-stone-200 bg-white px-4 py-3", disabled && "opacity-60")}>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-1 h-4 w-4 rounded border-stone-300 text-emerald-600"
      />
      <span className="space-y-1">
        <span className="block text-sm font-bold text-stone-950">{label}</span>
        <span className="block text-sm leading-5 text-stone-600">{description}</span>
      </span>
    </label>
  );
}

export default function AdmConfiguracoesPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [ready, setReady] = useState(false);
  const [selectedScope, setSelectedScope] = useState<AgentSettingsScope>("tenant");
  const [selectedTenantId, setSelectedTenantId] = useState("");
  const [form, setForm] = useState<AgentConfig | null>(null);

  useEffect(() => {
    if (!getAdminAccessToken()) {
      router.replace("/adm");
      return;
    }
    setReady(true);
  }, [router]);

  const admSessionQuery = useAdmSession(ready);
  const canView = canAccessAdmPage(admSessionQuery.data?.resolved_adm_page_permissions, "adm_agent_settings", "view");
  const canEdit = canAccessAdmPage(admSessionQuery.data?.resolved_adm_page_permissions, "adm_agent_settings", "edit");
  const isPlatformAdmin = Boolean(admSessionQuery.data?.roles?.includes("admin_platform"));

  useEffect(() => {
    if (!ready) {
      return;
    }
    setSelectedScope(isPlatformAdmin ? "platform" : "tenant");
  }, [isPlatformAdmin, ready]);

  const tenantsQuery = useQuery<{ data: AgentTenant[] }>({
    queryKey: ["adm-agent-settings-tenants"],
    queryFn: async () => (await api.get("/admin/agent-settings/tenants")).data,
    enabled: ready && canView && (selectedScope === "tenant" || !isPlatformAdmin),
  });

  useEffect(() => {
    if (!selectedTenantId && tenantsQuery.data?.data?.[0]?.id) {
      setSelectedTenantId(tenantsQuery.data.data[0].id);
    }
  }, [selectedTenantId, tenantsQuery.data]);

  const settingsQuery = useQuery<AgentSettingsPayload>({
    queryKey: ["adm-agent-settings", selectedScope, selectedTenantId],
    queryFn: async () =>
      (
        await api.get("/admin/agent-settings", {
          params: selectedScope === "platform" ? { scope: "platform" } : { scope: "tenant", tenant_id: selectedTenantId },
        })
      ).data,
    enabled: ready && canView && (selectedScope === "platform" || Boolean(selectedTenantId)),
  });

  useEffect(() => {
    if (settingsQuery.data?.config) {
      setForm(normalizeConfig(settingsQuery.data.config));
    }
  }, [settingsQuery.data]);

  const modelOptions = useMemo(() => settingsQuery.data?.model_options ?? [{ value: "", label: "Padrao do ambiente" }], [settingsQuery.data]);

  const saveMutation = useMutation({
    mutationFn: async (config: AgentConfig) =>
      (
        await api.put(
          "/admin/agent-settings",
          { tenant_id: selectedScope === "tenant" ? selectedTenantId : null, scope: selectedScope, config },
          { params: selectedScope === "platform" ? { scope: "platform" } : { scope: "tenant", tenant_id: selectedTenantId } },
        )
      ).data,
    onSuccess: () => {
      toast.success("Configuracoes do agente salvas.");
      queryClient.invalidateQueries({ queryKey: ["adm-agent-settings", selectedScope, selectedTenantId] });
    },
    onError: () => toast.error("Nao foi possivel salvar as configuracoes do agente."),
  });

  if (!ready || admSessionQuery.isLoading || tenantsQuery.isLoading) {
    return <LoadingState message="Carregando configuracoes do agente..." />;
  }

  if (!canView) {
    return (
      <main className="grid min-h-screen place-items-center overflow-x-hidden bg-stone-950 px-4 text-white">
        <Card className="w-full max-w-md border-white/10 bg-white text-stone-950">
          <CardContent className="space-y-4 p-8 text-center">
            <h1 className="text-xl font-black">Area restrita</h1>
            <p className="text-sm leading-6 text-stone-600">Seu usuario nao tem permissao para ver configuracoes do agente.</p>
            <Link className="inline-flex h-10 items-center rounded-lg bg-stone-950 px-4 text-sm font-bold text-white" href="/adm">
              Voltar ao /adm
            </Link>
          </CardContent>
        </Card>
      </main>
    );
  }

  if (tenantsQuery.isError || settingsQuery.isError) {
    return <ErrorState message="Nao foi possivel carregar as configuracoes do agente." />;
  }

  const tenant = settingsQuery.data?.tenant;
  const updateForm = (patch: Partial<AgentConfig>) => setForm((current) => normalizeConfig({ ...(current ?? {}), ...patch }));
  const updateHandoff = (key: keyof AgentConfig["handoff_triggers"], value: boolean) =>
    setForm((current) => {
      const normalized = normalizeConfig(current);
      return normalizeConfig({
        ...normalized,
        handoff_triggers: { ...normalized.handoff_triggers, [key]: value },
      });
    });

  return (
    <main className="min-h-screen overflow-x-hidden bg-stone-950 px-4 py-6 text-white md:px-6">
      <div className="mx-auto w-full max-w-6xl space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="space-y-2">
            <Link href="/adm" className="inline-flex items-center gap-2 text-sm font-semibold text-emerald-200 hover:text-white">
              <ArrowLeft size={16} />
              Voltar ao /adm
            </Link>
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.24em] text-emerald-300">{BRAND_NAME}</p>
              <h1 className="text-2xl font-black tracking-tight md:text-3xl">Configuracoes do agente</h1>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge className="bg-emerald-100 text-emerald-800">
              <ShieldCheck size={14} />
              Fluxo antigo preservado
            </Badge>
            <Button
              type="button"
              variant="outline"
              className="border-white/15 bg-white/10 text-white hover:bg-white/15"
              onClick={() => {
                tenantsQuery.refetch();
                settingsQuery.refetch();
              }}
            >
              <RefreshCw size={16} />
              Atualizar
            </Button>
          </div>
        </div>

        <Card className="border-white/10 bg-white text-stone-950">
          <CardHeader>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="space-y-1">
                <CardTitle className="text-lg">Escopo da configuracao</CardTitle>
                <p className="text-sm text-stone-600">
                  {selectedScope === "platform"
                    ? "Esse modo define o padrao global do sistema para os proximos atendimentos."
                    : "Esse modo salva um override da clinica e vence o padrao global apenas para este tenant."}
                </p>
              </div>
              <Badge className="bg-stone-900 text-white">{selectedScope === "platform" ? "global-do-sistema" : tenant?.slug ?? "tenant"}</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {isPlatformAdmin ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <Button
                  type="button"
                  variant={selectedScope === "platform" ? "default" : "outline"}
                  className={selectedScope === "platform" ? "bg-stone-950 text-white hover:bg-stone-800" : ""}
                  onClick={() => setSelectedScope("platform")}
                >
                  Global do sistema
                </Button>
                <Button
                  type="button"
                  variant={selectedScope === "tenant" ? "default" : "outline"}
                  className={selectedScope === "tenant" ? "bg-emerald-600 text-white hover:bg-emerald-500" : ""}
                  onClick={() => setSelectedScope("tenant")}
                >
                  Somente esta clinica
                </Button>
              </div>
            ) : null}

            {selectedScope === "tenant" ? (
              <select
                value={selectedTenantId}
                onChange={(event) => setSelectedTenantId(event.target.value)}
                className="h-11 w-full rounded-lg border border-stone-200 bg-white px-3 text-sm font-semibold text-stone-950 outline-none focus:ring-4 focus:ring-emerald-100"
              >
                {(tenantsQuery.data?.data ?? []).map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} ({item.slug})
                  </option>
                ))}
              </select>
            ) : (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
                O fluxo escolhido aqui passa a ser o padrao oficial usado pelo sistema dali para frente nas clinicas sem override proprio.
              </div>
            )}
          </CardContent>
        </Card>

        {!form || settingsQuery.isLoading ? (
          <LoadingState message="Lendo configuracao do tenant..." />
        ) : (
          <div className="grid gap-6 lg:grid-cols-[1.05fr_0.95fr]">
            <Card className="border-white/10 bg-white text-stone-950">
              <CardHeader>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <CardTitle className="flex items-center gap-2 text-lg">
                      <Bot size={18} />
                      Fluxo de conversa
                    </CardTitle>
                    <p className="mt-1 text-sm text-stone-600">Escolha entre o motor antigo e o novo fluxo estruturado elite.</p>
                  </div>
                  <Badge className={form.conversation_flow_mode === "structured_elite" ? "bg-emerald-100 text-emerald-800" : "bg-stone-200 text-stone-700"}>
                    {form.conversation_flow_mode === "structured_elite" ? "Novo fluxo" : "Fluxo antigo"}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  <Button
                    type="button"
                    variant={form.conversation_flow_mode === "legacy" ? "default" : "outline"}
                    className={form.conversation_flow_mode === "legacy" ? "bg-stone-950 text-white hover:bg-stone-800" : ""}
                    onClick={() => updateForm({ conversation_flow_mode: "legacy", structured_flow_enabled: false })}
                    disabled={!canEdit}
                  >
                    Fluxo antigo
                  </Button>
                  <Button
                    type="button"
                    variant={form.conversation_flow_mode === "structured_elite" ? "default" : "outline"}
                    className={form.conversation_flow_mode === "structured_elite" ? "bg-emerald-600 text-white hover:bg-emerald-500" : ""}
                    onClick={() => updateForm({ conversation_flow_mode: "structured_elite", structured_flow_enabled: true })}
                    disabled={!canEdit}
                  >
                    Novo estruturado
                  </Button>
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-bold text-stone-800">Modelo do ChatGPT</label>
                  <select
                    value={form.llm_model}
                    onChange={(event) => updateForm({ llm_model: event.target.value })}
                    disabled={!canEdit}
                    className="h-11 w-full rounded-lg border border-stone-200 bg-white px-3 text-sm font-semibold text-stone-950 outline-none focus:ring-4 focus:ring-emerald-100"
                  >
                    {modelOptions.map((option) => (
                      <option key={option.value || "default"} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <Input
                    value={form.llm_model}
                    disabled={!canEdit}
                    onChange={(event) => updateForm({ llm_model: event.target.value })}
                    placeholder="Opcional: digite outro modelo suportado pela sua conta"
                  />
                </div>

                <ToggleRow
                  label="Agente ativo"
                  description="Permite que o backend responda automaticamente quando a conversa estiver habilitada."
                  checked={form.enabled}
                  onChange={(checked) => updateForm({ enabled: checked })}
                  disabled={!canEdit}
                />
                <ToggleRow
                  label="Salvar dados do paciente automaticamente"
                  description="Telefone, nome, email, CPF e preferencias identificadas sao gravadas assim que aparecem com seguranca."
                  checked={form.auto_save_patient_data_enabled}
                  onChange={(checked) => updateForm({ auto_save_patient_data_enabled: checked })}
                  disabled={!canEdit}
                />
                <ToggleRow
                  label="Memoria resumida da conversa"
                  description="Guarda resumo e estado do agendamento para o paciente voltar sem repetir tudo."
                  checked={form.conversation_memory_enabled}
                  onChange={(checked) => updateForm({ conversation_memory_enabled: checked })}
                  disabled={!canEdit}
                />
              </CardContent>
            </Card>

            <Card className="border-white/10 bg-white text-stone-950">
              <CardHeader>
                <CardTitle className="text-lg">Guardrails antes do envio</CardTitle>
                <p className="text-sm text-stone-600">Essas travas revisam a resposta antes de aparecer para o paciente.</p>
              </CardHeader>
              <CardContent className="space-y-4">
                <ToggleRow
                  label="Revisor antes do envio"
                  description="Bloqueia resposta que confirma sem banco, inventa preco ou contradiz horarios retornados."
                  checked={form.pre_send_review_enabled}
                  onChange={(checked) => updateForm({ pre_send_review_enabled: checked })}
                  disabled={!canEdit}
                />
                <ToggleRow
                  label="Detector de mensagem repetida"
                  description="Evita repetir saudacao, pedir dado ja salvo ou mandar resposta quase igual a anterior."
                  checked={form.repetition_guard_enabled}
                  onChange={(checked) => updateForm({ repetition_guard_enabled: checked })}
                  disabled={!canEdit}
                />
                <ToggleRow
                  label="Opcoes interativas de agenda"
                  description="Permite listas/botoes quando o canal suporta selecao de unidade, data e horario."
                  checked={form.interactive_booking_options_enabled}
                  onChange={(checked) => updateForm({ interactive_booking_options_enabled: checked })}
                  disabled={!canEdit}
                />

                <div className="grid gap-3 sm:grid-cols-2">
                  <ToggleRow label="Handoff: baixa confianca" description="Encaminha quando a resposta nao passa da confianca minima." checked={form.handoff_triggers.low_confidence} onChange={(checked) => updateHandoff("low_confidence", checked)} disabled={!canEdit} />
                  <ToggleRow label="Handoff: urgencia" description="Encaminha dor forte, trauma, febre, sangramento ou risco clinico." checked={form.handoff_triggers.urgency} onChange={(checked) => updateHandoff("urgency", checked)} disabled={!canEdit} />
                  <ToggleRow label="Handoff: irritacao" description="Encaminha reclamacao, conflito ou paciente pedindo atendente." checked={form.handoff_triggers.patient_irritated} onChange={(checked) => updateHandoff("patient_irritated", checked)} disabled={!canEdit} />
                  <ToggleRow label="Handoff: erro de agenda" description="Encaminha quando o sistema nao consegue validar horario com seguranca." checked={form.handoff_triggers.schedule_error} onChange={(checked) => updateHandoff("schedule_error", checked)} disabled={!canEdit} />
                </div>
              </CardContent>
            </Card>

            <Card className="border-white/10 bg-white text-stone-950 lg:col-span-2">
              <CardHeader>
                <CardTitle className="text-lg">Operacao e tom</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4 md:grid-cols-4">
                <label className="space-y-2">
                  <span className="text-sm font-bold text-stone-800">Confianca minima</span>
                  <Input
                    type="number"
                    min={0}
                    max={1}
                    step={0.01}
                    value={form.confidence_threshold}
                    disabled={!canEdit}
                    onChange={(event) => updateForm({ confidence_threshold: Number(event.target.value) })}
                  />
                </label>
                <label className="space-y-2">
                  <span className="text-sm font-bold text-stone-800">Max. respostas seguidas</span>
                  <Input
                    type="number"
                    min={1}
                    max={20}
                    value={form.max_consecutive_auto_replies}
                    disabled={!canEdit}
                    onChange={(event) => updateForm({ max_consecutive_auto_replies: Number(event.target.value) })}
                  />
                </label>
                <label className="space-y-2">
                  <span className="text-sm font-bold text-stone-800">Inicio</span>
                  <Input value={form.business_hours.start} disabled={!canEdit} onChange={(event) => updateForm({ business_hours: { ...form.business_hours, start: event.target.value } })} />
                </label>
                <label className="space-y-2">
                  <span className="text-sm font-bold text-stone-800">Fim</span>
                  <Input value={form.business_hours.end} disabled={!canEdit} onChange={(event) => updateForm({ business_hours: { ...form.business_hours, end: event.target.value } })} />
                </label>
                <label className="space-y-2 md:col-span-2">
                  <span className="text-sm font-bold text-stone-800">Tag da fila humana</span>
                  <Input value={form.human_queue_tag} disabled={!canEdit} onChange={(event) => updateForm({ human_queue_tag: event.target.value })} />
                </label>
                <label className="space-y-2 md:col-span-2">
                  <span className="text-sm font-bold text-stone-800">Tom do agente</span>
                  <Input value={form.tone} disabled={!canEdit} onChange={(event) => updateForm({ tone: event.target.value })} />
                </label>
              </CardContent>
            </Card>

            <div className="flex flex-wrap items-center justify-end gap-3 lg:col-span-2">
              <Badge className="bg-white text-stone-800">
                <CheckCircle2 size={14} />
                {selectedScope === "platform" ? "Salva no padrao global da plataforma" : "Salva no override da clinica"}
              </Badge>
              <Button
                type="button"
                disabled={!canEdit || saveMutation.isPending}
                onClick={() => form && saveMutation.mutate(form)}
                className="bg-emerald-500 text-stone-950 hover:bg-emerald-400"
              >
                <Save size={16} />
                {saveMutation.isPending ? "Salvando..." : "Salvar configuracoes"}
              </Button>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

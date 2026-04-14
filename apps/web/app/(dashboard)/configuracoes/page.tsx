"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

import { DataTable, FilterBar, PageHeader, StatusBadge } from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { api } from "@/lib/api";
import { ApiPage, UnitItem } from "@/lib/domain-types";
import { maskToken, toTitleCase } from "@/lib/formatters";
import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@odontoflux/ui";

type SettingItem = {
  id: string;
  key: string;
  value: unknown;
  is_secret: boolean;
};

type WhatsAppAccountItem = {
  id: string;
  provider_name: "meta_cloud" | "infobip" | "twilio" | string;
  phone_number_id: string;
  business_account_id: string;
  display_phone?: string | null;
  is_active: boolean;
};

type WhatsAppTemplateItem = {
  id: string;
  name: string;
  language: string;
  category: string;
  status: string;
};

type UnitSettingsItem = UnitItem & { is_active?: boolean };

type WhatsAppTestResult = {
  status: string;
  webhook_status: string;
  integration_valid: boolean;
  connected_number: string;
  last_event_at: string;
  message: string;
};

type PrivacySummary = {
  consent_rate: number;
  retention_days: number;
  communication_allowed: { marketing?: boolean; operacional?: boolean };
  terms_version?: string | null;
  policy_version?: string | null;
  accepted_at?: string | null;
};

type AIAutoresponderConfig = {
  enabled: boolean;
  channels: { whatsapp: boolean };
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

type AIAutoresponderSettings = {
  global: AIAutoresponderConfig;
  unit_overrides: Array<{ unit_id: string; config: Record<string, unknown> }>;
};

type AIKnowledgeServiceItem = {
  name: string;
  description: string;
  duration_note: string;
  price_note: string;
};

type AIKnowledgeFaqItem = {
  question: string;
  answer: string;
};

type AIKnowledgeBaseConfig = {
  clinic_profile: {
    clinic_name: string;
    about: string;
    differentials: string[];
    target_audience: string;
    tone_preferences: string;
  };
  services: AIKnowledgeServiceItem[];
  insurance: {
    accepted_plans: string[];
    notes: string;
  };
  operational_policies: {
    booking_rules: string;
    cancellation_policy: string;
    reschedule_policy: string;
    payment_policy: string;
    documents_required: string;
  };
  faq: AIKnowledgeFaqItem[];
  commercial_playbook: {
    value_proposition: string;
    objection_handling: string;
    default_cta: string;
  };
  escalation: {
    human_handoff_topics: string[];
    restricted_topics: string[];
    custom_urgent_keywords: string[];
    fallback_message: string;
  };
};

type AIKnowledgeBaseSettings = {
  global: AIKnowledgeBaseConfig;
};

function extractApiErrorMessage(error: unknown, fallback: string): string {
  if (
    typeof error === "object" &&
    error &&
    "response" in error &&
    typeof (error as { response?: { data?: { error?: { message?: string } } } }).response?.data?.error?.message === "string"
  ) {
    return (error as { response?: { data?: { error?: { message?: string } } } }).response?.data?.error?.message ?? fallback;
  }
  return fallback;
}

const TABS = [
  "Clínica",
  "Unidades",
  "Horários",
  "WhatsApp",
  "IA Auto-Responder",
  "Conhecimento IA",
  "Notificações",
  "Segurança",
  "Dados e Privacidade",
] as const;

const DEFAULT_AI_CONFIG: AIAutoresponderConfig = {
  enabled: false,
  channels: { whatsapp: true },
  business_hours: {
    timezone: "America/Sao_Paulo",
    weekdays: [0, 1, 2, 3, 4],
    start: "08:00",
    end: "18:00",
  },
  outside_business_hours_mode: "handoff",
  max_consecutive_auto_replies: 3,
  confidence_threshold: 0.65,
  human_queue_tag: "fila_humana_ia",
  tone: "profissional, cordial e objetivo",
  fallback_user_id: null,
};

const DEFAULT_AI_KNOWLEDGE_CONFIG: AIKnowledgeBaseConfig = {
  clinic_profile: {
    clinic_name: "",
    about: "",
    differentials: [],
    target_audience: "",
    tone_preferences: "",
  },
  services: [],
  insurance: {
    accepted_plans: [],
    notes: "",
  },
  operational_policies: {
    booking_rules: "",
    cancellation_policy: "",
    reschedule_policy: "",
    payment_policy: "",
    documents_required: "",
  },
  faq: [],
  commercial_playbook: {
    value_proposition: "",
    objection_handling: "",
    default_cta: "",
  },
  escalation: {
    human_handoff_topics: [],
    restricted_topics: [],
    custom_urgent_keywords: [],
    fallback_message: "",
  },
};

const EMPTY_SERVICE: AIKnowledgeServiceItem = {
  name: "",
  description: "",
  duration_note: "",
  price_note: "",
};

const EMPTY_FAQ: AIKnowledgeFaqItem = {
  question: "",
  answer: "",
};

function parseTagInput(value: string): string[] {
  return value
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatTagInput(value: string[]): string {
  return value.join(", ");
}

export default function ConfiguracoesPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]>("Clínica");

  const [settingKey, setSettingKey] = useState("clinic.timezone");
  const [settingValue, setSettingValue] = useState("America/Sao_Paulo");

  const [whatsappProvider, setWhatsappProvider] = useState<"meta_cloud" | "infobip" | "twilio">("meta_cloud");
  const [phoneNumberId, setPhoneNumberId] = useState("");
  const [businessAccountId, setBusinessAccountId] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [displayPhone, setDisplayPhone] = useState("");
  const [whatsappTestResult, setWhatsappTestResult] = useState<WhatsAppTestResult | null>(null);

  const [search, setSearch] = useState("");
  const [anonymizePatientId, setAnonymizePatientId] = useState("");
  const [anonymizeReason, setAnonymizeReason] = useState("Solicitação do titular de dados.");
  const [aiConfigDraft, setAiConfigDraft] = useState<AIAutoresponderConfig>(DEFAULT_AI_CONFIG);
  const [aiUnitEnabledDraft, setAiUnitEnabledDraft] = useState<Record<string, "default" | "enabled" | "disabled">>({});
  const [aiKnowledgeDraft, setAiKnowledgeDraft] = useState<AIKnowledgeBaseConfig>(
    DEFAULT_AI_KNOWLEDGE_CONFIG,
  );

  const settingsQuery = useQuery<{ data: SettingItem[] }>({
    queryKey: ["settings"],
    queryFn: async () => (await api.get("/settings")).data,
  });

  const unitsQuery = useQuery<{ data: UnitSettingsItem[] }>({
    queryKey: ["settings-units"],
    queryFn: async () => (await api.get<ApiPage<UnitSettingsItem>>("/units", { params: { limit: 100, offset: 0 } })).data,
  });

  const whatsappAccountsQuery = useQuery<{ data: WhatsAppAccountItem[] }>({
    queryKey: ["whatsapp-accounts"],
    queryFn: async () => (await api.get("/settings/whatsapp/accounts")).data,
  });

  const whatsappTemplatesQuery = useQuery<{ data: WhatsAppTemplateItem[] }>({
    queryKey: ["whatsapp-templates"],
    queryFn: async () => (await api.get("/settings/whatsapp/templates")).data,
  });

  const privacySummaryQuery = useQuery<PrivacySummary>({
    queryKey: ["privacy-summary"],
    queryFn: async () => (await api.get("/privacy/summary")).data,
  });

  const aiAutoresponderQuery = useQuery<AIAutoresponderSettings>({
    queryKey: ["ai-autoresponder-settings"],
    queryFn: async () => (await api.get("/settings/ai-autoresponder/config")).data,
  });

  const aiKnowledgeBaseQuery = useQuery<AIKnowledgeBaseSettings>({
    queryKey: ["ai-knowledge-base-settings"],
    queryFn: async () => (await api.get("/settings/ai-knowledge-base/config")).data,
  });

  useEffect(() => {
    if (!aiAutoresponderQuery.data?.global) return;
    setAiConfigDraft({
      ...DEFAULT_AI_CONFIG,
      ...aiAutoresponderQuery.data.global,
      channels: {
        ...DEFAULT_AI_CONFIG.channels,
        ...(aiAutoresponderQuery.data.global.channels ?? {}),
      },
      business_hours: {
        ...DEFAULT_AI_CONFIG.business_hours,
        ...(aiAutoresponderQuery.data.global.business_hours ?? {}),
      },
    });

    const draft: Record<string, "default" | "enabled" | "disabled"> = {};
    for (const item of aiAutoresponderQuery.data.unit_overrides ?? []) {
      const enabled = item?.config?.enabled;
      if (enabled === true) draft[item.unit_id] = "enabled";
      else if (enabled === false) draft[item.unit_id] = "disabled";
      else draft[item.unit_id] = "default";
    }
    setAiUnitEnabledDraft(draft);
  }, [aiAutoresponderQuery.data]);

  useEffect(() => {
    if (!aiKnowledgeBaseQuery.data?.global) return;

    const incoming = aiKnowledgeBaseQuery.data.global;
    setAiKnowledgeDraft({
      ...DEFAULT_AI_KNOWLEDGE_CONFIG,
      ...incoming,
      clinic_profile: {
        ...DEFAULT_AI_KNOWLEDGE_CONFIG.clinic_profile,
        ...(incoming.clinic_profile ?? {}),
      },
      insurance: {
        ...DEFAULT_AI_KNOWLEDGE_CONFIG.insurance,
        ...(incoming.insurance ?? {}),
      },
      operational_policies: {
        ...DEFAULT_AI_KNOWLEDGE_CONFIG.operational_policies,
        ...(incoming.operational_policies ?? {}),
      },
      commercial_playbook: {
        ...DEFAULT_AI_KNOWLEDGE_CONFIG.commercial_playbook,
        ...(incoming.commercial_playbook ?? {}),
      },
      escalation: {
        ...DEFAULT_AI_KNOWLEDGE_CONFIG.escalation,
        ...(incoming.escalation ?? {}),
      },
      services: Array.isArray(incoming.services)
        ? incoming.services.map((item) => ({
            ...EMPTY_SERVICE,
            ...item,
          }))
        : [],
      faq: Array.isArray(incoming.faq)
        ? incoming.faq.map((item) => ({
            ...EMPTY_FAQ,
            ...item,
          }))
        : [],
    });
  }, [aiKnowledgeBaseQuery.data]);

  const upsertSettingMutation = useMutation({
    mutationFn: async ({ key, value, isSecret = false }: { key: string; value: unknown; isSecret?: boolean }) =>
      api.put(`/settings/${key}`, { value, is_secret: isSecret }),
    onSuccess: () => {
      toast.success("Configuração salva com sucesso.");
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: () => toast.error("Não foi possível salvar a configuração."),
  });

  const saveAiConfigMutation = useMutation({
    mutationFn: async () => api.put("/settings/ai-autoresponder/config", aiConfigDraft),
    onSuccess: () => {
      toast.success("Configuração do Auto-Responder IA salva.");
      queryClient.invalidateQueries({ queryKey: ["ai-autoresponder-settings"] });
    },
    onError: () => toast.error("Não foi possível salvar a configuração do Auto-Responder IA."),
  });

  const saveAiKnowledgeMutation = useMutation({
    mutationFn: async () => api.put("/settings/ai-knowledge-base/config", aiKnowledgeDraft),
    onSuccess: () => {
      toast.success("Base de conhecimento da IA salva com sucesso.");
      queryClient.invalidateQueries({ queryKey: ["ai-knowledge-base-settings"] });
    },
    onError: () => toast.error("Não foi possível salvar o conhecimento da IA."),
  });

  const saveAiUnitOverrideMutation = useMutation({
    mutationFn: async ({ unitId, mode }: { unitId: string; mode: "default" | "enabled" | "disabled" }) =>
      api.put(`/settings/ai-autoresponder/unit/${unitId}`, mode === "default" ? {} : { enabled: mode === "enabled" }),
    onSuccess: () => {
      toast.success("Override de unidade atualizado.");
      queryClient.invalidateQueries({ queryKey: ["ai-autoresponder-settings"] });
    },
    onError: () => toast.error("Não foi possível atualizar o override da unidade."),
  });

  const updateUnitMutation = useMutation({
    mutationFn: async ({ unitId, payload }: { unitId: string; payload: Record<string, unknown> }) =>
      api.patch(`/units/${unitId}`, payload),
    onSuccess: () => {
      toast.success("Unidade atualizada.");
      queryClient.invalidateQueries({ queryKey: ["settings-units"] });
    },
    onError: () => toast.error("Não foi possível atualizar a unidade."),
  });

  const createWhatsappAccountMutation = useMutation({
    mutationFn: async () =>
      api.post("/settings/whatsapp/accounts", {
        provider_name: whatsappProvider,
        phone_number_id: phoneNumberId,
        business_account_id: businessAccountId,
        access_token: accessToken,
        display_phone: displayPhone || null,
      }),
    onSuccess: () => {
      toast.success("Conta WhatsApp salva com sucesso.");
      setPhoneNumberId("");
      setBusinessAccountId("");
      setAccessToken("");
      setDisplayPhone("");
      queryClient.invalidateQueries({ queryKey: ["whatsapp-accounts"] });
    },
    onError: (error) => toast.error(extractApiErrorMessage(error, "Não foi possível salvar a conta WhatsApp.")),
  });

  const testWhatsappMutation = useMutation({
    mutationFn: async () =>
      (
        await api.post<WhatsAppTestResult>("/settings/whatsapp/test", {
          provider_name: whatsappProvider,
          phone_number_id: phoneNumberId || undefined,
          business_account_id: businessAccountId || undefined,
          access_token: accessToken || undefined,
          display_phone: displayPhone || undefined,
        })
      ).data,
    onSuccess: (data) => {
      setWhatsappTestResult(data);
      toast.success("Conexão WhatsApp validada com sucesso.");
    },
    onError: (error) => {
      setWhatsappTestResult(null);
      toast.error(extractApiErrorMessage(error, "Não foi possível validar a conexão WhatsApp."));
    },
  });

  const acceptTermsMutation = useMutation({
    mutationFn: async () =>
      api.post("/privacy/terms/accept", {
        terms_version: "v1.0",
        policy_version: "v1.0",
      }),
    onSuccess: () => {
      toast.success("Termos de privacidade aceitos.");
      queryClient.invalidateQueries({ queryKey: ["privacy-summary"] });
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: () => toast.error("Não foi possível registrar aceite dos termos."),
  });

  const exportPrivacyDataMutation = useMutation({
    mutationFn: async () => (await api.post("/privacy/export", { scope: "tenant" })).data,
    onSuccess: () => toast.success("Exportação de dados registrada com sucesso."),
    onError: () => toast.error("Não foi possível solicitar exportação de dados."),
  });

  const anonymizePatientMutation = useMutation({
    mutationFn: async () =>
      api.post("/privacy/anonymize", {
        patient_id: anonymizePatientId,
        reason: anonymizeReason,
      }),
    onSuccess: () => {
      toast.success("Paciente anonimizado com sucesso.");
      setAnonymizePatientId("");
      queryClient.invalidateQueries({ queryKey: ["patients-dataset"] });
    },
    onError: () => toast.error("Não foi possível anonimizar o paciente."),
  });

  if (
    settingsQuery.isLoading ||
    whatsappAccountsQuery.isLoading ||
    whatsappTemplatesQuery.isLoading ||
    unitsQuery.isLoading ||
    privacySummaryQuery.isLoading ||
    aiAutoresponderQuery.isLoading ||
    aiKnowledgeBaseQuery.isLoading
  ) {
    return <LoadingState message="Carregando configurações..." />;
  }
  if (
    settingsQuery.isError ||
    whatsappAccountsQuery.isError ||
    whatsappTemplatesQuery.isError ||
    unitsQuery.isError ||
    privacySummaryQuery.isError ||
    aiAutoresponderQuery.isError ||
    aiKnowledgeBaseQuery.isError
  ) {
    return <ErrorState message="Não foi possível carregar as configurações da clínica." />;
  }

  const settingsRows = (settingsQuery.data?.data ?? []).filter((item) => {
    const term = search.toLowerCase().trim();
    return !term || `${item.key} ${JSON.stringify(item.value)}`.toLowerCase().includes(term);
  });
  const whatsappRows = (whatsappAccountsQuery.data?.data ?? []).filter((item) => {
    const term = search.toLowerCase().trim();
    return (
      !term ||
      `${item.display_phone ?? ""} ${item.phone_number_id} ${item.business_account_id} ${item.provider_name}`
        .toLowerCase()
        .includes(term)
    );
  });
  const templateRows = whatsappTemplatesQuery.data?.data ?? [];

  const timezoneSetting = settingsRows.find((item) => item.key === "clinic.timezone");
  const clinicTimezone =
    typeof timezoneSetting?.value === "string" ? timezoneSetting.value : "America/Sao_Paulo";
  const privacySummary = privacySummaryQuery.data;
  const isInfobipProvider = whatsappProvider === "infobip";
  const isTwilioProvider = whatsappProvider === "twilio";
  const providerDisplayName = isInfobipProvider
    ? "Infobip"
    : isTwilioProvider
      ? "Twilio"
      : "Meta Cloud API";
  const providerPhoneLabel = isInfobipProvider
    ? "Sender WhatsApp (Infobip)"
    : isTwilioProvider
      ? "Sender WhatsApp (Twilio)"
      : "ID do número (Meta)";
  const providerBusinessLabel = isInfobipProvider
    ? "Base URL da API Infobip"
    : isTwilioProvider
      ? "Account SID (Twilio)"
      : "ID da conta comercial (Meta)";
  const providerTokenLabel = isInfobipProvider
    ? "Chave API Infobip"
    : isTwilioProvider
      ? "Auth Token (Twilio)"
      : "Token de acesso da Meta";
  const providerPhonePlaceholder = isInfobipProvider
    ? "Ex.: 5511940431906 (sender aprovado na Infobip)"
    : isTwilioProvider
      ? "Ex.: whatsapp:+5511999999999"
      : "Ex.: 1101713436353674";
  const providerBusinessPlaceholder = isInfobipProvider
    ? "Ex.: 3dd13w.api.infobip.com"
    : isTwilioProvider
      ? "Ex.: ACXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
      : "Ex.: 936994182588219";
  const providerTokenPlaceholder = isInfobipProvider
    ? "Cole a chave App da Infobip"
    : isTwilioProvider
      ? "Cole o Auth Token da Twilio"
      : "Cole o access token da Meta";
  const knowledgeServices = aiKnowledgeDraft.services.length ? aiKnowledgeDraft.services : [EMPTY_SERVICE];
  const knowledgeFaq = aiKnowledgeDraft.faq.length ? aiKnowledgeDraft.faq : [EMPTY_FAQ];

  const upsertKnowledgeService = (
    index: number,
    field: keyof AIKnowledgeServiceItem,
    value: string,
  ) => {
    setAiKnowledgeDraft((current) => {
      const services = current.services.length ? [...current.services] : [EMPTY_SERVICE];
      services[index] = {
        ...(services[index] ?? EMPTY_SERVICE),
        [field]: value,
      };
      return {
        ...current,
        services,
      };
    });
  };

  const addKnowledgeService = () => {
    setAiKnowledgeDraft((current) => ({
      ...current,
      services: [...current.services, { ...EMPTY_SERVICE }],
    }));
  };

  const removeKnowledgeService = (index: number) => {
    setAiKnowledgeDraft((current) => ({
      ...current,
      services: current.services.filter((_, itemIndex) => itemIndex !== index),
    }));
  };

  const upsertKnowledgeFaq = (index: number, field: keyof AIKnowledgeFaqItem, value: string) => {
    setAiKnowledgeDraft((current) => {
      const faq = current.faq.length ? [...current.faq] : [EMPTY_FAQ];
      faq[index] = {
        ...(faq[index] ?? EMPTY_FAQ),
        [field]: value,
      };
      return {
        ...current,
        faq,
      };
    });
  };

  const addKnowledgeFaq = () => {
    setAiKnowledgeDraft((current) => ({
      ...current,
      faq: [...current.faq, { ...EMPTY_FAQ }],
    }));
  };

  const removeKnowledgeFaq = (index: number) => {
    setAiKnowledgeDraft((current) => ({
      ...current,
      faq: current.faq.filter((_, itemIndex) => itemIndex !== index),
    }));
  };

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Configuração"
        title="Configurações da clínica e WhatsApp"
        description="Parâmetros operacionais, segurança e integrações para sustentar a operação."
      />

      <FilterBar search={search} onSearchChange={setSearch} searchPlaceholder="Buscar configuração...">
        {TABS.map((tab) => (
          <Button
            key={tab}
            variant={activeTab === tab ? "default" : "outline"}
            className="h-8"
            onClick={() => setActiveTab(tab)}
          >
            {tab}
          </Button>
        ))}
      </FilterBar>

      {activeTab === "Clínica" ? (
        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle>Configurações gerais da clínica</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-2 md:grid-cols-3">
              <Input placeholder="Chave (ex.: clinic.timezone)" value={settingKey} onChange={(event) => setSettingKey(event.target.value)} />
              <Input placeholder="Valor" value={settingValue} onChange={(event) => setSettingValue(event.target.value)} />
              <Button
                onClick={() => upsertSettingMutation.mutate({ key: settingKey, value: settingValue })}
                disabled={upsertSettingMutation.isPending}
              >
                {upsertSettingMutation.isPending ? "Salvando..." : "Salvar configuração"}
              </Button>
            </div>
            <p className="text-xs text-stone-500">Timezone operacional atual: {clinicTimezone}</p>
          </CardContent>
        </Card>
      ) : null}

      {activeTab === "Unidades" ? (
        <DataTable<UnitSettingsItem>
          title="Unidades da clínica"
          rows={unitsQuery.data?.data ?? []}
          getRowId={(item) => item.id}
          searchBy={(item) => `${item.name} ${item.code} ${item.email ?? ""}`}
          columns={[
            { key: "nome", label: "Unidade", render: (item) => item.name },
            { key: "codigo", label: "Código", render: (item) => item.code },
            { key: "telefone", label: "Telefone", render: (item) => item.phone || "-" },
            { key: "email", label: "E-mail", render: (item) => item.email || "-" },
            {
              key: "status",
              label: "Status",
              render: (item) => <StatusBadge value={item.is_active === false ? "inativo" : "ativo"} />,
            },
            {
              key: "acoes",
              label: "Ações",
              render: (item) => (
                <Button
                  variant="outline"
                  className="h-8 px-2 text-xs"
                  onClick={() =>
                    updateUnitMutation.mutate({
                      unitId: item.id,
                      payload: { is_active: !(item.is_active !== false) },
                    })
                  }
                >
                  {item.is_active === false ? "Ativar" : "Desativar"}
                </Button>
              ),
            },
          ]}
          emptyTitle="Nenhuma unidade cadastrada"
          emptyDescription="Cadastre unidades para operar múltiplas agendas e equipes."
        />
      ) : null}

      {activeTab === "Horários" ? (
        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle>Horários de atendimento</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-stone-600">Defina horários padrão por unidade para agenda e automações.</p>
            <div className="grid gap-2 md:grid-cols-3">
              <Input value="Seg-Sex" readOnly />
              <Input value="08:00 - 18:00" readOnly />
              <Button
                onClick={() =>
                  upsertSettingMutation.mutate({
                    key: "clinic.working_hours",
                    value: { semana: "08:00-18:00", sabado: "08:00-12:00" },
                  })
                }
              >
                Salvar horário padrão
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {activeTab === "WhatsApp" ? (
        <div className="space-y-4">
          <Card className="border-stone-200">
            <CardHeader>
              <CardTitle>Conta WhatsApp ({providerDisplayName})</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-2 md:grid-cols-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Provedor</label>
                  <select
                    className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                    value={whatsappProvider}
                    onChange={(event) => {
                      const provider = event.target.value;
                      if (provider === "infobip" || provider === "twilio" || provider === "meta_cloud") {
                        setWhatsappProvider(provider);
                        return;
                      }
                      setWhatsappProvider("meta_cloud");
                    }}
                  >
                    <option value="meta_cloud">Meta Cloud API</option>
                    <option value="infobip">Infobip</option>
                    <option value="twilio">Twilio</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                    {providerPhoneLabel}
                  </label>
                  <Input
                    placeholder={providerPhonePlaceholder}
                    value={phoneNumberId}
                    onChange={(event) => setPhoneNumberId(event.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                    {providerBusinessLabel}
                  </label>
                  <Input
                    placeholder={providerBusinessPlaceholder}
                    value={businessAccountId}
                    onChange={(event) => setBusinessAccountId(event.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                    {providerTokenLabel}
                  </label>
                  <Input
                    placeholder={providerTokenPlaceholder}
                    value={accessToken}
                    onChange={(event) => setAccessToken(event.target.value)}
                  />
                </div>
              </div>
              <div className="grid gap-2 md:grid-cols-2">
                <Input
                  placeholder="Número de exibição (opcional)"
                  value={displayPhone}
                  onChange={(event) => setDisplayPhone(event.target.value)}
                />
                <p className="rounded-md border border-stone-200 bg-stone-50 p-2 text-xs text-stone-600">
                  {isInfobipProvider
                    ? "Infobip: informe sender, base URL (ex.: 3dd13w.api.infobip.com) e App key."
                    : isTwilioProvider
                      ? "Twilio: informe sender WhatsApp (whatsapp:+...), Account SID (AC...) e Auth Token."
                      : "Meta: informe Phone Number ID, Business Account ID e Access Token oficiais da Meta."}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button onClick={() => createWhatsappAccountMutation.mutate()} disabled={createWhatsappAccountMutation.isPending}>
                  {createWhatsappAccountMutation.isPending ? "Salvando..." : "Salvar conta"}
                </Button>
                <Button variant="outline" onClick={() => testWhatsappMutation.mutate()} disabled={testWhatsappMutation.isPending}>
                  {testWhatsappMutation.isPending ? "Testando..." : "Testar conexão"}
                </Button>
                <StatusBadge value={whatsappRows.length ? "ativo" : "inativo"} />
              </div>
              {whatsappTestResult ? (
                <p className="text-xs text-stone-600">
                  {whatsappTestResult.message}. Número: {whatsappTestResult.connected_number}. Webhook: {whatsappTestResult.webhook_status}. Último evento: {whatsappTestResult.last_event_at}.
                </p>
              ) : null}
            </CardContent>
          </Card>

          <DataTable<WhatsAppAccountItem>
            title="Contas conectadas"
            rows={whatsappRows}
            getRowId={(item) => item.id}
            searchBy={(item) => `${item.display_phone ?? ""} ${item.phone_number_id}`}
            columns={[
              {
                key: "provedor",
                label: "Provedor",
                render: (item) =>
                  item.provider_name === "infobip"
                    ? "Infobip"
                    : item.provider_name === "twilio"
                      ? "Twilio"
                      : "Meta Cloud",
              },
              { key: "numero", label: "Número conectado", render: (item) => item.display_phone || "-" },
              { key: "status", label: "Status", render: (item) => <StatusBadge value={item.is_active ? "ativo" : "inativo"} /> },
              { key: "webhook", label: "Webhook", render: () => <StatusBadge value="ativo" /> },
              {
                key: "phone_id",
                label: "Sender/ID telefone",
                render: (item) => maskToken(item.phone_number_id),
              },
              {
                key: "business_id",
                label: "Conta/URL base",
                render: (item) => maskToken(item.business_account_id),
              },
              { key: "ultimo_evento", label: "Último evento", render: () => "Hoje, 09:42" },
            ]}
            emptyTitle="Nenhuma conta WhatsApp"
            emptyDescription="Conecte uma conta para habilitar mensagens e automações."
          />

          <DataTable<WhatsAppTemplateItem>
            title="Templates ativos"
            rows={templateRows}
            getRowId={(item) => item.id}
            searchBy={(item) => `${item.name} ${item.category} ${item.status}`}
            columns={[
              { key: "nome", label: "Template", render: (item) => item.name },
              { key: "idioma", label: "Idioma", render: (item) => item.language },
              { key: "categoria", label: "Categoria", render: (item) => toTitleCase(item.category) },
              { key: "status", label: "Status", render: (item) => <StatusBadge value={item.status} /> },
            ]}
            emptyTitle="Sem templates cadastrados"
            emptyDescription="Cadastre templates para campanhas e automações."
          />
        </div>
      ) : null}

      {activeTab === "IA Auto-Responder" ? (
        <div className="space-y-4">
          <Card className="border-stone-200">
            <CardHeader>
              <CardTitle>Governança do Auto-Responder IA</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3">
                <p className="text-sm font-semibold text-emerald-800">Como funciona</p>
                <p className="mt-1 text-xs text-emerald-700">
                  Este painel define quando a IA responde automaticamente no WhatsApp e quando deve encaminhar para humano.
                  Configure horário, limites e segurança antes de ativar em produção.
                </p>
              </div>

              <div className="grid gap-3 md:grid-cols-2">
                <div>
                  <label className="flex items-center gap-2 text-sm text-stone-700">
                    <input
                      type="checkbox"
                      checked={aiConfigDraft.enabled}
                      onChange={(event) =>
                        setAiConfigDraft((current) => ({ ...current, enabled: event.target.checked }))
                      }
                    />
                    Habilitar IA automática no tenant
                  </label>
                  <p className="mt-1 text-xs text-stone-500">
                    Liga/desliga o auto-responder para toda a clínica (com possibilidade de override por unidade/conversa).
                  </p>
                </div>
                <div>
                  <label className="flex items-center gap-2 text-sm text-stone-700">
                    <input
                      type="checkbox"
                      checked={aiConfigDraft.channels.whatsapp}
                      onChange={(event) =>
                        setAiConfigDraft((current) => ({
                          ...current,
                          channels: { ...current.channels, whatsapp: event.target.checked },
                        }))
                      }
                    />
                    Habilitar canal WhatsApp
                  </label>
                  <p className="mt-1 text-xs text-stone-500">
                    Define se a IA pode responder automaticamente no canal WhatsApp.
                  </p>
                </div>
              </div>

              <div className="grid gap-2 md:grid-cols-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Timezone</label>
                  <Input
                    placeholder="Ex.: America/Sao_Paulo"
                    value={aiConfigDraft.business_hours.timezone}
                    onChange={(event) =>
                      setAiConfigDraft((current) => ({
                        ...current,
                        business_hours: { ...current.business_hours, timezone: event.target.value },
                      }))
                    }
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Início</label>
                  <Input
                    placeholder="Ex.: 08:00"
                    value={aiConfigDraft.business_hours.start}
                    onChange={(event) =>
                      setAiConfigDraft((current) => ({
                        ...current,
                        business_hours: { ...current.business_hours, start: event.target.value },
                      }))
                    }
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Fim</label>
                  <Input
                    placeholder="Ex.: 18:00"
                    value={aiConfigDraft.business_hours.end}
                    onChange={(event) =>
                      setAiConfigDraft((current) => ({
                        ...current,
                        business_hours: { ...current.business_hours, end: event.target.value },
                      }))
                    }
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Fora do horário</label>
                  <select
                    className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                    value={aiConfigDraft.outside_business_hours_mode}
                    onChange={(event) =>
                      setAiConfigDraft((current) => ({
                        ...current,
                        outside_business_hours_mode: event.target.value as "handoff" | "allow" | "silent",
                      }))
                    }
                  >
                    <option value="handoff">Handoff para humano</option>
                    <option value="allow">Responder mesmo fora do horário</option>
                    <option value="silent">Não responder automaticamente</option>
                  </select>
                </div>
              </div>
              <p className="text-xs text-stone-500">
                Define a janela operacional em que a IA atua automaticamente.
              </p>

              <div className="grid gap-2 md:grid-cols-3">
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                    Máx. respostas consecutivas
                  </label>
                  <Input
                    placeholder="Ex.: 3"
                    type="number"
                    min={1}
                    max={20}
                    value={String(aiConfigDraft.max_consecutive_auto_replies)}
                    onChange={(event) =>
                      setAiConfigDraft((current) => ({
                        ...current,
                        max_consecutive_auto_replies: Number(event.target.value || 3),
                      }))
                    }
                  />
                  <p className="text-xs text-stone-500">Evita loops. Ao atingir o limite, conversa vai para humano.</p>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                    Confiança mínima (0 a 1)
                  </label>
                  <Input
                    placeholder="Ex.: 0.65"
                    type="number"
                    step="0.05"
                    min={0}
                    max={1}
                    value={String(aiConfigDraft.confidence_threshold)}
                    onChange={(event) =>
                      setAiConfigDraft((current) => ({
                        ...current,
                        confidence_threshold: Number(event.target.value || 0.65),
                      }))
                    }
                  />
                  <p className="text-xs text-stone-500">Abaixo desse valor, a IA não responde e faz handoff.</p>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                    Tag da fila humana
                  </label>
                  <Input
                    placeholder="Ex.: fila_humana_ia"
                    value={aiConfigDraft.human_queue_tag}
                    onChange={(event) =>
                      setAiConfigDraft((current) => ({ ...current, human_queue_tag: event.target.value }))
                    }
                  />
                  <p className="text-xs text-stone-500">Tag aplicada quando a conversa é encaminhada para atendimento humano.</p>
                </div>
              </div>

              <div className="grid gap-2 md:grid-cols-2">
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Tom da IA</label>
                  <Input
                    placeholder="Ex.: profissional, cordial e objetivo"
                    value={aiConfigDraft.tone}
                    onChange={(event) =>
                      setAiConfigDraft((current) => ({ ...current, tone: event.target.value }))
                    }
                  />
                  <p className="text-xs text-stone-500">Define estilo das respostas automáticas para pacientes.</p>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                    Usuário fallback (opcional)
                  </label>
                  <Input
                    placeholder="UUID de um usuário responsável padrão"
                    value={aiConfigDraft.fallback_user_id ?? ""}
                    onChange={(event) =>
                      setAiConfigDraft((current) => ({
                        ...current,
                        fallback_user_id: event.target.value || null,
                      }))
                    }
                  />
                  <p className="text-xs text-stone-500">Recebe conversas em handoff quando não há responsável na conversa.</p>
                </div>
              </div>

              <div className="rounded-md border border-stone-200 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Dias de atendimento</p>
                <div className="mt-2 flex flex-wrap gap-3 text-sm text-stone-700">
                  {[
                    { id: 0, label: "Seg" },
                    { id: 1, label: "Ter" },
                    { id: 2, label: "Qua" },
                    { id: 3, label: "Qui" },
                    { id: 4, label: "Sex" },
                    { id: 5, label: "Sáb" },
                    { id: 6, label: "Dom" },
                  ].map((day) => (
                    <label key={day.id} className="flex items-center gap-1.5">
                      <input
                        type="checkbox"
                        checked={aiConfigDraft.business_hours.weekdays.includes(day.id)}
                        onChange={(event) =>
                          setAiConfigDraft((current) => {
                            const weekdays = new Set(current.business_hours.weekdays);
                            if (event.target.checked) weekdays.add(day.id);
                            else weekdays.delete(day.id);
                            return {
                              ...current,
                              business_hours: { ...current.business_hours, weekdays: Array.from(weekdays).sort() },
                            };
                          })
                        }
                      />
                      {day.label}
                    </label>
                  ))}
                </div>
              </div>

              <Button onClick={() => saveAiConfigMutation.mutate()} disabled={saveAiConfigMutation.isPending}>
                {saveAiConfigMutation.isPending ? "Salvando..." : "Salvar Auto-Responder IA"}
              </Button>
            </CardContent>
          </Card>

          <Card className="border-stone-200">
            <CardHeader>
              <CardTitle>Override por unidade</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {(unitsQuery.data?.data ?? []).length ? (
                (unitsQuery.data?.data ?? []).map((unit) => (
                  <div key={unit.id} className="grid gap-2 rounded-md border border-stone-200 p-3 md:grid-cols-[1fr,220px,160px]">
                    <div>
                      <p className="text-sm font-semibold text-stone-800">{unit.name}</p>
                      <p className="text-xs text-stone-500">{unit.code}</p>
                    </div>
                    <select
                      className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm"
                      value={aiUnitEnabledDraft[unit.id] ?? "default"}
                      onChange={(event) =>
                        setAiUnitEnabledDraft((current) => ({
                          ...current,
                          [unit.id]: event.target.value as "default" | "enabled" | "disabled",
                        }))
                      }
                    >
                      <option value="default">Herdar global</option>
                      <option value="enabled">Forçar ativo</option>
                      <option value="disabled">Forçar inativo</option>
                    </select>
                    <Button
                      variant="outline"
                      onClick={() =>
                        saveAiUnitOverrideMutation.mutate({
                          unitId: unit.id,
                          mode: aiUnitEnabledDraft[unit.id] ?? "default",
                        })
                      }
                      disabled={saveAiUnitOverrideMutation.isPending}
                    >
                      Salvar unidade
                    </Button>
                  </div>
                ))
              ) : (
                <p className="text-sm text-stone-500">Nenhuma unidade cadastrada para override.</p>
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}

      {activeTab === "Conhecimento IA" ? (
        <div className="space-y-4">
          <Card className="border-stone-200">
            <CardHeader>
              <CardTitle>Base de conhecimento da IA (conteúdo da clínica)</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3">
                <p className="text-sm font-semibold text-emerald-800">Como usar este painel</p>
                <p className="mt-1 text-xs text-emerald-700">
                  Tudo que você preencher aqui vira referência oficial para a IA responder pacientes no WhatsApp.
                  Quanto mais específico, melhor a qualidade das respostas automáticas.
                </p>
              </div>
              <p className="text-xs text-stone-500">
                Dica operacional: mantenha textos curtos, objetivos e atualizados. A IA evita inventar dados
                quando não encontra informação nesta base.
              </p>
            </CardContent>
          </Card>

          <Card className="border-stone-200">
            <CardHeader>
              <CardTitle>Perfil da clínica e posicionamento</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-2 md:grid-cols-2">
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                    Nome oficial para atendimento
                  </label>
                  <Input
                    placeholder="Ex.: Clínica Sorriso Sul"
                    value={aiKnowledgeDraft.clinic_profile.clinic_name}
                    onChange={(event) =>
                      setAiKnowledgeDraft((current) => ({
                        ...current,
                        clinic_profile: {
                          ...current.clinic_profile,
                          clinic_name: event.target.value,
                        },
                      }))
                    }
                  />
                  <p className="text-xs text-stone-500">
                    Nome que a IA pode citar ao se apresentar para o paciente.
                  </p>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                    Público principal
                  </label>
                  <Input
                    placeholder="Ex.: adultos, ortodontia estética e implantes"
                    value={aiKnowledgeDraft.clinic_profile.target_audience}
                    onChange={(event) =>
                      setAiKnowledgeDraft((current) => ({
                        ...current,
                        clinic_profile: {
                          ...current.clinic_profile,
                          target_audience: event.target.value,
                        },
                      }))
                    }
                  />
                  <p className="text-xs text-stone-500">
                    Ajuda a IA a adaptar linguagem comercial e prioridades de atendimento.
                  </p>
                </div>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                  Descrição da clínica
                </label>
                <textarea
                  className="min-h-[88px] w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                  placeholder="Ex.: Clínica focada em odontologia estética com atendimento consultivo e acolhedor."
                  value={aiKnowledgeDraft.clinic_profile.about}
                  onChange={(event) =>
                    setAiKnowledgeDraft((current) => ({
                      ...current,
                      clinic_profile: {
                        ...current.clinic_profile,
                        about: event.target.value,
                      },
                    }))
                  }
                />
                <p className="text-xs text-stone-500">
                  Resumo institucional para a IA explicar quem vocês são e qual proposta de valor.
                </p>
              </div>
              <div className="grid gap-2 md:grid-cols-2">
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                    Diferenciais (separar por vírgula)
                  </label>
                  <Input
                    placeholder="Ex.: agendamento rápido, atendimento humanizado, especialistas por área"
                    value={formatTagInput(aiKnowledgeDraft.clinic_profile.differentials)}
                    onChange={(event) =>
                      setAiKnowledgeDraft((current) => ({
                        ...current,
                        clinic_profile: {
                          ...current.clinic_profile,
                          differentials: parseTagInput(event.target.value),
                        },
                      }))
                    }
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                    Preferências de tom da IA
                  </label>
                  <Input
                    placeholder="Ex.: consultivo, acolhedor, sem gírias, objetivo"
                    value={aiKnowledgeDraft.clinic_profile.tone_preferences}
                    onChange={(event) =>
                      setAiKnowledgeDraft((current) => ({
                        ...current,
                        clinic_profile: {
                          ...current.clinic_profile,
                          tone_preferences: event.target.value,
                        },
                      }))
                    }
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border-stone-200">
            <CardHeader>
              <CardTitle>Serviços e ofertas operacionais</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-xs text-stone-500">
                Cadastre os serviços que a IA pode oferecer e explicar durante o atendimento.
              </p>
              {knowledgeServices.map((service, index) => (
                <div
                  key={`knowledge-service-${index}`}
                  className="space-y-2 rounded-md border border-stone-200 p-3"
                >
                  <div className="grid gap-2 md:grid-cols-2">
                    <Input
                      placeholder="Nome do serviço (ex.: Avaliação ortodôntica)"
                      value={service.name}
                      onChange={(event) =>
                        upsertKnowledgeService(index, "name", event.target.value)
                      }
                    />
                    <Input
                      placeholder="Duração estimada (ex.: 45 min)"
                      value={service.duration_note}
                      onChange={(event) =>
                        upsertKnowledgeService(index, "duration_note", event.target.value)
                      }
                    />
                  </div>
                  <div className="grid gap-2 md:grid-cols-2">
                    <Input
                      placeholder="Faixa de valor (ex.: avaliação a partir de R$ 190)"
                      value={service.price_note}
                      onChange={(event) =>
                        upsertKnowledgeService(index, "price_note", event.target.value)
                      }
                    />
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => removeKnowledgeService(index)}
                      disabled={aiKnowledgeDraft.services.length <= 1}
                    >
                      Remover serviço
                    </Button>
                  </div>
                  <textarea
                    className="min-h-[78px] w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                    placeholder="Descrição comercial e operacional do serviço."
                    value={service.description}
                    onChange={(event) =>
                      upsertKnowledgeService(index, "description", event.target.value)
                    }
                  />
                </div>
              ))}
              <Button type="button" variant="outline" onClick={addKnowledgeService}>
                Adicionar serviço
              </Button>
            </CardContent>
          </Card>

          <Card className="border-stone-200">
            <CardHeader>
              <CardTitle>Convênios, políticas e rotinas da operação</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-2 md:grid-cols-2">
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                    Convênios aceitos (vírgula)
                  </label>
                  <Input
                    placeholder="Ex.: Bradesco, Unimed, SulAmérica"
                    value={formatTagInput(aiKnowledgeDraft.insurance.accepted_plans)}
                    onChange={(event) =>
                      setAiKnowledgeDraft((current) => ({
                        ...current,
                        insurance: {
                          ...current.insurance,
                          accepted_plans: parseTagInput(event.target.value),
                        },
                      }))
                    }
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                    Observações sobre convênios
                  </label>
                  <Input
                    placeholder="Ex.: emitimos recibo para reembolso no particular"
                    value={aiKnowledgeDraft.insurance.notes}
                    onChange={(event) =>
                      setAiKnowledgeDraft((current) => ({
                        ...current,
                        insurance: {
                          ...current.insurance,
                          notes: event.target.value,
                        },
                      }))
                    }
                  />
                </div>
              </div>

              <div className="grid gap-2 md:grid-cols-2">
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                    Regras de agendamento
                  </label>
                  <textarea
                    className="min-h-[88px] w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                    placeholder="Ex.: primeira consulta com 24h de antecedência, confirmação no mesmo dia."
                    value={aiKnowledgeDraft.operational_policies.booking_rules}
                    onChange={(event) =>
                      setAiKnowledgeDraft((current) => ({
                        ...current,
                        operational_policies: {
                          ...current.operational_policies,
                          booking_rules: event.target.value,
                        },
                      }))
                    }
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                    Política de cancelamento
                  </label>
                  <textarea
                    className="min-h-[88px] w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                    placeholder="Ex.: cancelamentos com menos de 4h entram como falta."
                    value={aiKnowledgeDraft.operational_policies.cancellation_policy}
                    onChange={(event) =>
                      setAiKnowledgeDraft((current) => ({
                        ...current,
                        operational_policies: {
                          ...current.operational_policies,
                          cancellation_policy: event.target.value,
                        },
                      }))
                    }
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                    Política de reagendamento
                  </label>
                  <textarea
                    className="min-h-[88px] w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                    placeholder="Ex.: até duas remarcações sem custo, depois validação da equipe."
                    value={aiKnowledgeDraft.operational_policies.reschedule_policy}
                    onChange={(event) =>
                      setAiKnowledgeDraft((current) => ({
                        ...current,
                        operational_policies: {
                          ...current.operational_policies,
                          reschedule_policy: event.target.value,
                        },
                      }))
                    }
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                    Política de pagamento
                  </label>
                  <textarea
                    className="min-h-[88px] w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                    placeholder="Ex.: aceitamos PIX, débito e cartão em até 3x sem juros."
                    value={aiKnowledgeDraft.operational_policies.payment_policy}
                    onChange={(event) =>
                      setAiKnowledgeDraft((current) => ({
                        ...current,
                        operational_policies: {
                          ...current.operational_policies,
                          payment_policy: event.target.value,
                        },
                      }))
                    }
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                  Documentos necessários na primeira consulta
                </label>
                <Input
                  placeholder="Ex.: documento com foto, carteirinha do convênio e exames recentes"
                  value={aiKnowledgeDraft.operational_policies.documents_required}
                  onChange={(event) =>
                    setAiKnowledgeDraft((current) => ({
                      ...current,
                      operational_policies: {
                        ...current.operational_policies,
                        documents_required: event.target.value,
                      },
                    }))
                  }
                />
              </div>
            </CardContent>
          </Card>

          <Card className="border-stone-200">
            <CardHeader>
              <CardTitle>FAQ, playbook comercial e escalonamento</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                  Perguntas frequentes (FAQ)
                </p>
                {knowledgeFaq.map((item, index) => (
                  <div
                    key={`knowledge-faq-${index}`}
                    className="space-y-2 rounded-md border border-stone-200 p-3"
                  >
                    <Input
                      placeholder="Pergunta frequente"
                      value={item.question}
                      onChange={(event) =>
                        upsertKnowledgeFaq(index, "question", event.target.value)
                      }
                    />
                    <textarea
                      className="min-h-[78px] w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                      placeholder="Resposta padrão aprovada pela clínica."
                      value={item.answer}
                      onChange={(event) => upsertKnowledgeFaq(index, "answer", event.target.value)}
                    />
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => removeKnowledgeFaq(index)}
                      disabled={aiKnowledgeDraft.faq.length <= 1}
                    >
                      Remover FAQ
                    </Button>
                  </div>
                ))}
                <Button type="button" variant="outline" onClick={addKnowledgeFaq}>
                  Adicionar FAQ
                </Button>
              </div>

              <div className="grid gap-2 md:grid-cols-2">
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                    Proposta de valor principal
                  </label>
                  <textarea
                    className="min-h-[88px] w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                    placeholder="Ex.: atendimento premium com plano de tratamento claro e acompanhamento próximo."
                    value={aiKnowledgeDraft.commercial_playbook.value_proposition}
                    onChange={(event) =>
                      setAiKnowledgeDraft((current) => ({
                        ...current,
                        commercial_playbook: {
                          ...current.commercial_playbook,
                          value_proposition: event.target.value,
                        },
                      }))
                    }
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                    Tratamento de objeções
                  </label>
                  <textarea
                    className="min-h-[88px] w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                    placeholder="Ex.: se paciente achar caro, reforçar benefícios, segurança e possibilidade de parcelamento."
                    value={aiKnowledgeDraft.commercial_playbook.objection_handling}
                    onChange={(event) =>
                      setAiKnowledgeDraft((current) => ({
                        ...current,
                        commercial_playbook: {
                          ...current.commercial_playbook,
                          objection_handling: event.target.value,
                        },
                      }))
                    }
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                  CTA padrão da conversa
                </label>
                <Input
                  placeholder="Ex.: Posso confirmar seu melhor horário para esta semana?"
                  value={aiKnowledgeDraft.commercial_playbook.default_cta}
                  onChange={(event) =>
                    setAiKnowledgeDraft((current) => ({
                      ...current,
                      commercial_playbook: {
                        ...current.commercial_playbook,
                        default_cta: event.target.value,
                      },
                    }))
                  }
                />
              </div>

              <div className="rounded-md border border-stone-200 p-3 space-y-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                  Regras de escalonamento para humano
                </p>
                <div className="grid gap-2 md:grid-cols-3">
                  <div className="space-y-1">
                    <label className="text-xs text-stone-500">
                      Temas que devem ir para humano
                    </label>
                    <Input
                      placeholder="Ex.: negociação de desconto, reclamação formal"
                      value={formatTagInput(aiKnowledgeDraft.escalation.human_handoff_topics)}
                      onChange={(event) =>
                        setAiKnowledgeDraft((current) => ({
                          ...current,
                          escalation: {
                            ...current.escalation,
                            human_handoff_topics: parseTagInput(event.target.value),
                          },
                        }))
                      }
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-stone-500">
                      Assuntos bloqueados para IA
                    </label>
                    <Input
                      placeholder="Ex.: diagnóstico, prescrição, laudo"
                      value={formatTagInput(aiKnowledgeDraft.escalation.restricted_topics)}
                      onChange={(event) =>
                        setAiKnowledgeDraft((current) => ({
                          ...current,
                          escalation: {
                            ...current.escalation,
                            restricted_topics: parseTagInput(event.target.value),
                          },
                        }))
                      }
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-stone-500">
                      Palavras extras de urgência
                    </label>
                    <Input
                      placeholder="Ex.: dor pulsante, trauma recente"
                      value={formatTagInput(aiKnowledgeDraft.escalation.custom_urgent_keywords)}
                      onChange={(event) =>
                        setAiKnowledgeDraft((current) => ({
                          ...current,
                          escalation: {
                            ...current.escalation,
                            custom_urgent_keywords: parseTagInput(event.target.value),
                          },
                        }))
                      }
                    />
                  </div>
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-stone-500">
                    Mensagem padrão quando for necessário handoff
                  </label>
                  <Input
                    placeholder="Ex.: Vou encaminhar agora para nossa equipe humana te atender com prioridade."
                    value={aiKnowledgeDraft.escalation.fallback_message}
                    onChange={(event) =>
                      setAiKnowledgeDraft((current) => ({
                        ...current,
                        escalation: {
                          ...current.escalation,
                          fallback_message: event.target.value,
                        },
                      }))
                    }
                  />
                </div>
              </div>

              <Button
                onClick={() => saveAiKnowledgeMutation.mutate()}
                disabled={saveAiKnowledgeMutation.isPending}
              >
                {saveAiKnowledgeMutation.isPending
                  ? "Salvando conhecimento..."
                  : "Salvar base de conhecimento da IA"}
              </Button>
            </CardContent>
          </Card>
        </div>
      ) : null}

      {activeTab === "Notificações" ? (
        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle>Notificações operacionais</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <Button
              variant="outline"
              onClick={() =>
                upsertSettingMutation.mutate({ key: "notifications.whatsapp", value: { enabled: true } })
              }
            >
              Ativar notificações no WhatsApp
            </Button>
            <Button
              variant="outline"
              onClick={() => upsertSettingMutation.mutate({ key: "notifications.email", value: { enabled: true } })}
            >
              Ativar notificações por e-mail
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {activeTab === "Segurança" ? (
        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle>Segurança da operação</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <Button
              variant="outline"
              onClick={() => upsertSettingMutation.mutate({ key: "security.session_timeout", value: 30 })}
            >
              Sessão com timeout de 30 min
            </Button>
            <Button
              variant="outline"
              onClick={() => upsertSettingMutation.mutate({ key: "security.require_mfa", value: true })}
            >
              Exigir MFA para perfis críticos
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {activeTab === "Dados e Privacidade" ? (
        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle>Dados e privacidade</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
              <p className="text-sm font-semibold text-stone-800">Consentimento e retenção</p>
              <p className="text-xs text-stone-600">
                Flags de consentimento, período de retenção e políticas de comunicação disponíveis.
              </p>
              <p className="mt-1 text-xs text-stone-700">
                Taxa de consentimento: {privacySummary?.consent_rate?.toFixed(1) ?? "0.0"}% • Retenção padrão:{" "}
                {privacySummary?.retention_days ?? 365} dias
              </p>
              <p className="text-xs text-stone-700">
                Termos aceitos em: {privacySummary?.accepted_at ? new Date(privacySummary.accepted_at).toLocaleString("pt-BR") : "não aceito"}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => exportPrivacyDataMutation.mutate()}>
                Exportar dados
              </Button>
              <Button variant="outline" onClick={() => acceptTermsMutation.mutate()}>
                Aceitar termos LGPD
              </Button>
              <Button
                variant="outline"
                onClick={() =>
                  upsertSettingMutation.mutate({
                    key: "privacy.communication_allowed",
                    value: { marketing: true, operacional: true },
                  })
                }
              >
                Atualizar permissões de comunicação
              </Button>
            </div>
            <div className="grid gap-2 md:grid-cols-3">
              <Input
                placeholder="UUID do paciente"
                value={anonymizePatientId}
                onChange={(event) => setAnonymizePatientId(event.target.value)}
              />
              <Input
                placeholder="Motivo da anonimização"
                value={anonymizeReason}
                onChange={(event) => setAnonymizeReason(event.target.value)}
              />
              <Button
                variant="outline"
                onClick={() => anonymizePatientMutation.mutate()}
                disabled={anonymizePatientMutation.isPending || !anonymizePatientId.trim()}
              >
                {anonymizePatientMutation.isPending ? "Anonimizando..." : "Anonimizar paciente"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <DataTable<SettingItem>
        title="Catálogo de configurações"
        rows={settingsRows}
        getRowId={(item) => item.id}
        searchBy={(item) => `${item.key} ${JSON.stringify(item.value)}`}
        columns={[
          { key: "chave", label: "Chave", render: (item) => item.key },
          {
            key: "valor",
            label: "Valor",
            render: (item) => (item.is_secret ? maskToken(String(item.value ?? "")) : JSON.stringify(item.value)),
          },
          { key: "segredo", label: "Sensível", render: (item) => <StatusBadge value={item.is_secret ? "ativo" : "inativo"} /> },
          {
            key: "estado",
            label: "Validação",
            render: () => (
              <span className="inline-flex items-center gap-1 text-emerald-700">
                <CheckCircle2 size={13} /> OK
              </span>
            ),
          },
        ]}
        emptyTitle="Sem configurações"
        emptyDescription="Cadastre parâmetros para personalizar a operação da clínica."
      />
    </div>
  );
}

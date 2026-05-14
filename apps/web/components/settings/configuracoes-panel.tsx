"use client";

import { ChangeEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import Image from "next/image";
import { toast } from "sonner";

import { DataTable, FilterBar, PageHeader, RightDrawer, StatusBadge } from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { api } from "@/lib/api";
import { ApiPage, ServiceCatalogItem, UnitItem } from "@/lib/domain-types";
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

type UnitSettingsItem = UnitItem & {
  is_active?: boolean;
  address?: Record<string, unknown>;
  working_hours?: Record<string, unknown>;
  services?: string[];
};

type UnitFormState = {
  name: string;
  code: string;
  phone: string;
  email: string;
  address_line: string;
  address_number: string;
  complement: string;
  neighborhood: string;
  city: string;
  state: string;
  zip_code: string;
  reference_point: string;
  access_instructions: string;
  parking_info: string;
  working_days_text: string;
  working_hours_start: string;
  working_hours_end: string;
  working_hours_notes: string;
  services: string[];
};

type ClinicProfileConfig = {
  clinic_name: string;
  legal_name: string;
  cnpj: string;
  main_phone: string;
  whatsapp_phone: string;
  email: string;
  website: string;
  timezone: string;
  address_line: string;
  neighborhood: string;
  city: string;
  state: string;
  zip_code: string;
  technical_manager_name: string;
  technical_manager_cro: string;
  payment_methods: string;
  accepted_insurance: string;
  cancellation_policy: string;
  reschedule_policy: string;
  about: string;
};

type SecurityConfig = {
  session_timeout_minutes: number;
  idle_lock_minutes: number;
  require_mfa: boolean;
  enforce_single_session: boolean;
  password_rotation_days: number;
  audit_log_retention_days: number;
  allowed_ip_ranges: string;
  restrict_sensitive_exports: boolean;
  notify_new_device_login: boolean;
};

type PrivacyConfig = {
  retention_days: number;
  allow_marketing: boolean;
  allow_operational: boolean;
  terms_version: string;
  policy_version: string;
  privacy_contact_name: string;
  privacy_contact_email: string;
  privacy_contact_phone: string;
  export_scope: string;
  export_request_email: string;
  anonymize_leads_after_days: number;
  consent_text: string;
  data_sharing_notes: string;
};

type WhatsAppTestResult = {
  status: string;
  webhook_status: string;
  integration_valid: boolean;
  connected_number: string;
  last_event_at: string;
  message: string;
};

type WhatsAppHealth = {
  status: "ok" | "warning" | "blocked" | string;
  active_account?: {
    id: string;
    provider_name: string;
    phone_number_id: string;
    display_phone?: string | null;
  } | null;
  issues: string[];
  recent_failure?: {
    id: string;
    status: string;
    last_error: string;
    created_at: string;
    updated_at: string;
    is_credit_issue: boolean;
  } | null;
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
    welcome_greeting_example: string;
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

type ServiceCatalogSettings = {
  items: ServiceCatalogItem[];
};

type ServiceDrawerMode = "create" | "edit" | null;
type UnitDrawerMode = "create" | "edit" | null;

type ServiceCatalogFormState = {
  id: string;
  name: string;
  description: string;
  duration_minutes: number;
  price_note: string;
  is_active: boolean;
};

type BrandingConfig = {
  primary_color: string;
  secondary_color: string;
  accent_color: string;
  background_color: string;
  surface_color: string;
  card_color: string;
  text_color: string;
  muted_text_color: string;
  border_color: string;
  fullscreen_background_color: string;
  fullscreen_header_color: string;
  fullscreen_accent_color: string;
  fullscreen_foreground_color: string;
  surface_style: "soft" | "flat" | "glass";
  logo_data_url?: string | null;
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
  "Serviços",
  "Tema e Marca",
  "Unidades",
  "Horários",
  "WhatsApp",
  "IA Auto-Responder",
  "Conhecimento IA",
  "Notificações",
  "Segurança",
  "Dados e Privacidade",
] as const;

type ConfiguracoesTab = (typeof TABS)[number];

type ConfiguracoesPageProps = {
  fixedTab?: ConfiguracoesTab;
};

const CONFIGURATION_TABS = TABS.filter((tab) => tab !== "Serviços" && tab !== "Unidades") as ConfiguracoesTab[];

const DEFAULT_AI_CONFIG: AIAutoresponderConfig = {
  enabled: true,
  channels: { whatsapp: true },
  interactive_booking_options_enabled: true,
  business_hours: {
    timezone: "America/Sao_Paulo",
    weekdays: [0, 1, 2, 3, 4],
    start: "08:00",
    end: "18:00",
  },
  outside_business_hours_mode: "allow",
  max_consecutive_auto_replies: 3,
  confidence_threshold: 0.65,
  human_queue_tag: "fila_humana_ia",
  tone: "profissional, cordial e objetivo",
  fallback_user_id: null,
};

const DEFAULT_BRANDING_CONFIG: BrandingConfig = {
  primary_color: "#0f766e",
  secondary_color: "#0ea5a4",
  accent_color: "#f59e0b",
  background_color: "#f2f4f7",
  surface_color: "#eef2f6",
  card_color: "#ffffff",
  text_color: "#1c1917",
  muted_text_color: "#475569",
  border_color: "#d6d3d1",
  fullscreen_background_color: "#0c0a09",
  fullscreen_header_color: "#111111",
  fullscreen_accent_color: "#10b981",
  fullscreen_foreground_color: "#ffffff",
  surface_style: "soft",
  logo_data_url: null,
};

const BRANDING_PRESETS: Array<{
  id: string;
  name: string;
  description: string;
  config: Omit<BrandingConfig, "logo_data_url">;
}> = [
  {
    id: "neon-clinic",
    name: "Neon Clinic",
    description: "Visual tecnológico, verde vivo e alto contraste para demos impactantes.",
    config: {
      primary_color: "#00a884",
      secondary_color: "#00d4ff",
      accent_color: "#f7c948",
      background_color: "#e7fff7",
      surface_color: "#d9fbf0",
      card_color: "#ffffff",
      text_color: "#06251f",
      muted_text_color: "#31645a",
      border_color: "#9debd7",
      fullscreen_background_color: "#041b17",
      fullscreen_header_color: "#06231e",
      fullscreen_accent_color: "#00e0a4",
      fullscreen_foreground_color: "#ecfffa",
      surface_style: "glass",
    },
  },
  {
    id: "royal-blue",
    name: "Royal Blue",
    description: "Azul premium com detalhes âmbar, forte para clínicas modernas.",
    config: {
      primary_color: "#0b3d91",
      secondary_color: "#176bff",
      accent_color: "#ffb000",
      background_color: "#eef5ff",
      surface_color: "#dceaff",
      card_color: "#ffffff",
      text_color: "#071a38",
      muted_text_color: "#415a7a",
      border_color: "#b7cdf2",
      fullscreen_background_color: "#07111f",
      fullscreen_header_color: "#0a1730",
      fullscreen_accent_color: "#2f80ff",
      fullscreen_foreground_color: "#f2f7ff",
      surface_style: "soft",
    },
  },
  {
    id: "lux-gold",
    name: "Lux Gold",
    description: "Champagne, dourado e preto suave para uma apresentação mais sofisticada.",
    config: {
      primary_color: "#8a5a00",
      secondary_color: "#c28a19",
      accent_color: "#f5c451",
      background_color: "#fff7e6",
      surface_color: "#f3e2c3",
      card_color: "#fffdf8",
      text_color: "#2c1b08",
      muted_text_color: "#735a34",
      border_color: "#d9bd86",
      fullscreen_background_color: "#120d07",
      fullscreen_header_color: "#1d1408",
      fullscreen_accent_color: "#d8a21d",
      fullscreen_foreground_color: "#fff7df",
      surface_style: "soft",
    },
  },
  {
    id: "coral-energy",
    name: "Coral Energy",
    description: "Cores quentes e vibrantes para deixar botões, cards e CTAs chamativos.",
    config: {
      primary_color: "#e11d48",
      secondary_color: "#fb7185",
      accent_color: "#fb923c",
      background_color: "#fff1f2",
      surface_color: "#ffe4e6",
      card_color: "#ffffff",
      text_color: "#3b0713",
      muted_text_color: "#7f1d1d",
      border_color: "#fecdd3",
      fullscreen_background_color: "#2a0610",
      fullscreen_header_color: "#3f0715",
      fullscreen_accent_color: "#ff476f",
      fullscreen_foreground_color: "#fff1f4",
      surface_style: "glass",
    },
  },
  {
    id: "deep-violet",
    name: "Violet Prime",
    description: "Roxo escuro, ciano e lavanda para um painel premium bem diferente.",
    config: {
      primary_color: "#6d28d9",
      secondary_color: "#22d3ee",
      accent_color: "#a3e635",
      background_color: "#f3e8ff",
      surface_color: "#e9d5ff",
      card_color: "#ffffff",
      text_color: "#24113f",
      muted_text_color: "#60457f",
      border_color: "#c4b5fd",
      fullscreen_background_color: "#12091f",
      fullscreen_header_color: "#1e1033",
      fullscreen_accent_color: "#8b5cf6",
      fullscreen_foreground_color: "#faf5ff",
      surface_style: "glass",
    },
  },
  {
    id: "graphite-lime",
    name: "Graphite Lime",
    description: "Cinza grafite com verde-limão para um visual ousado e muito visível.",
    config: {
      primary_color: "#365314",
      secondary_color: "#65a30d",
      accent_color: "#bef264",
      background_color: "#f7fee7",
      surface_color: "#ecfccb",
      card_color: "#ffffff",
      text_color: "#1a2e05",
      muted_text_color: "#4d7c0f",
      border_color: "#bef264",
      fullscreen_background_color: "#0f1607",
      fullscreen_header_color: "#17220a",
      fullscreen_accent_color: "#a3e635",
      fullscreen_foreground_color: "#f7fee7",
      surface_style: "flat",
    },
  },
];

const DEFAULT_AI_KNOWLEDGE_CONFIG: AIKnowledgeBaseConfig = {
  clinic_profile: {
    clinic_name: "",
    about: "",
    differentials: [],
    target_audience: "",
    tone_preferences: "",
    welcome_greeting_example: "",
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

const EMPTY_SERVICE_CATALOG_ITEM: ServiceCatalogItem = {
  id: "",
  name: "",
  description: "",
  duration_minutes: 60,
  price_note: "",
  is_active: true,
};

const EMPTY_SERVICE_CATALOG_FORM: ServiceCatalogFormState = {
  id: "",
  name: "",
  description: "",
  duration_minutes: 60,
  price_note: "",
  is_active: true,
};

const EMPTY_FAQ: AIKnowledgeFaqItem = {
  question: "",
  answer: "",
};

const EMPTY_UNIT_FORM: UnitFormState = {
  name: "",
  code: "",
  phone: "",
  email: "",
  address_line: "",
  address_number: "",
  complement: "",
  neighborhood: "",
  city: "",
  state: "",
  zip_code: "",
  reference_point: "",
  access_instructions: "",
  parking_info: "",
  working_days_text: "Segunda a sexta",
  working_hours_start: "08:00",
  working_hours_end: "18:00",
  working_hours_notes: "",
  services: [],
};

const DEFAULT_CLINIC_PROFILE: ClinicProfileConfig = {
  clinic_name: "",
  legal_name: "",
  cnpj: "",
  main_phone: "",
  whatsapp_phone: "",
  email: "",
  website: "",
  timezone: "America/Sao_Paulo",
  address_line: "",
  neighborhood: "",
  city: "",
  state: "",
  zip_code: "",
  technical_manager_name: "",
  technical_manager_cro: "",
  payment_methods: "",
  accepted_insurance: "",
  cancellation_policy: "",
  reschedule_policy: "",
  about: "",
};

const DEFAULT_SECURITY_CONFIG: SecurityConfig = {
  session_timeout_minutes: 30,
  idle_lock_minutes: 10,
  require_mfa: true,
  enforce_single_session: false,
  password_rotation_days: 90,
  audit_log_retention_days: 365,
  allowed_ip_ranges: "",
  restrict_sensitive_exports: true,
  notify_new_device_login: true,
};

const DEFAULT_PRIVACY_CONFIG: PrivacyConfig = {
  retention_days: 365,
  allow_marketing: true,
  allow_operational: true,
  terms_version: "v1.0",
  policy_version: "v1.0",
  privacy_contact_name: "",
  privacy_contact_email: "",
  privacy_contact_phone: "",
  export_scope: "tenant",
  export_request_email: "",
  anonymize_leads_after_days: 365,
  consent_text: "",
  data_sharing_notes: "",
};

const CLINIC_PROFILE_COMPLETION_FIELDS: Array<keyof ClinicProfileConfig> = [
  "clinic_name",
  "legal_name",
  "cnpj",
  "main_phone",
  "whatsapp_phone",
  "email",
  "website",
  "address_line",
  "neighborhood",
  "city",
  "state",
  "zip_code",
  "technical_manager_name",
  "technical_manager_cro",
  "payment_methods",
  "accepted_insurance",
  "cancellation_policy",
  "reschedule_policy",
  "about",
];

const TEXTAREA_CLASSNAME =
  "min-h-[104px] w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm shadow-sm outline-none transition placeholder:text-stone-400 focus:border-primary focus:ring-2 focus:ring-primary/20";

const SORRISO_SUL_AI_KNOWLEDGE_PRESET: AIKnowledgeBaseConfig = {
  clinic_profile: {
    clinic_name: "Clinica Sorriso Sul",
    about:
      "A Clinica Sorriso Sul atua com atendimentos clinicos e esteticos, com abordagem consultiva, acolhimento premium e foco em previsibilidade de resultado.",
    differentials: [
      "avaliacao detalhada com planejamento digital",
      "atendimento acolhedor e linguagem simples",
      "parcelamento facilitado",
      "acompanhamento proximo no pos-procedimento",
      "instalacao de lentes em fluxo rapido quando indicado",
    ],
    target_audience:
      "adultos que buscam harmonizacao do sorriso, reabilitacao estetica e solucao funcional com orientacao clara",
    tone_preferences:
      "profissional, cordial, objetivo, comercial consultivo e sem jargao tecnico",
    welcome_greeting_example:
      "Oi! Que bom te ver por aqui.\nSou a assistente virtual da Clinica Sorriso Sul e posso te ajudar com servicos, valores e agendamentos.\nPara começar, escolha uma opção no menu abaixo:",
  },
  services: [],
  insurance: {
    accepted_plans: ["Particular", "Reembolso"],
    notes:
      "Atendimento principal em regime particular. Emitimos recibo e documentacao para reembolso quando aplicavel.",
  },
  operational_policies: {
    booking_rules:
      "Agendamentos por WhatsApp com confirmacao de disponibilidade em agenda. Recomendado solicitar 24h de antecedencia.",
    cancellation_policy:
      "Cancelamentos com menos de 4 horas podem gerar taxa operacional conforme tipo de agenda reservada.",
    reschedule_policy:
      "Remarcacao sem custo quando solicitada com antecedencia minima de 4 horas e mediante disponibilidade.",
    payment_policy:
      "Aceitamos PIX, debito e cartao de credito. Parcelamento disponivel conforme procedimento.",
    documents_required:
      "Documento com foto, contatos atualizados e exames recentes (quando houver).",
  },
  faq: [
    {
      question: "Quais servicos voces oferecem?",
      answer:
        "Oferecemos avaliacao detalhada, lentes de contato dental, clareamento e reabilitacao estetica. Posso te orientar no melhor proximo passo operacional para avaliacao.",
    },
    {
      question: "Quanto custa?",
      answer:
        "Os valores variam por caso. A avaliacao inicial parte de R$ 190 e nela definimos o plano e os custos com transparencia.",
    },
    {
      question: "Vocês parcelam?",
      answer:
        "Sim, trabalhamos com parcelamento no cartao conforme o procedimento e as condicoes vigentes.",
    },
    {
      question: "Em quanto tempo fica pronto?",
      answer:
        "Depende do caso. Em fluxos elegiveis de lentes, a instalacao pode ocorrer em 1 dia, apos avaliacao e validacao do plano.",
    },
    {
      question: "Como agendar?",
      answer:
        "Posso iniciar seu agendamento agora. Me informe seu nome completo e melhor periodo (manha, tarde ou noite).",
    },
  ],
  commercial_playbook: {
    value_proposition:
      "Sorriso bonito, natural e funcional com planejamento individual e acompanhamento de perto.",
    objection_handling:
      "Quando houver duvida de valor, reforcar qualidade, previsibilidade, planejamento e possibilidades de pagamento. Conduzir para avaliacao.",
    default_cta:
      "Posso confirmar seu melhor horario para avaliacao ainda esta semana?",
  },
  escalation: {
    human_handoff_topics: [
      "negociacao de desconto fora da politica",
      "reclamacao formal",
      "casos sensiveis com historico de conflito",
      "duvida clinica especifica que exija avaliacao profissional",
    ],
    restricted_topics: [
      "diagnostico",
      "prescricao",
      "laudo",
      "dose de medicamento",
      "conduta clinica",
    ],
    custom_urgent_keywords: [
      "dor forte",
      "sangramento",
      "trauma",
      "inchaco",
      "urgente",
    ],
    fallback_message:
      "Vou encaminhar agora para nossa equipe humana te atender com prioridade.",
  },
};

const SORRISO_SUL_SERVICE_CATALOG_PRESET: ServiceCatalogItem[] = [
  {
    id: "preset-avaliacao-detalhada",
    name: "Avaliacao detalhada",
    description:
      "Consulta inicial para entender objetivo estetico e funcional, levantar historico e montar plano personalizado.",
    duration_minutes: 60,
    price_note: "a partir de R$ 190",
    is_active: true,
  },
  {
    id: "preset-lentes-contato-dental",
    name: "Lentes de contato dental",
    description:
      "Planejamento e instalacao de lentes para melhorar forma, cor e harmonia do sorriso.",
    duration_minutes: 120,
    price_note: "valor sob avaliacao",
    is_active: true,
  },
  {
    id: "preset-clareamento-dental",
    name: "Clareamento dental",
    description:
      "Protocolos de clareamento supervisionado para ganho estetico com orientacoes operacionais de acompanhamento.",
    duration_minutes: 60,
    price_note: "a partir de R$ 650",
    is_active: true,
  },
  {
    id: "preset-reabilitacao-estetica",
    name: "Reabilitacao estetica",
    description:
      "Combinacao de procedimentos para recuperar estetica e funcao, conforme plano individual.",
    duration_minutes: 120,
    price_note: "valor sob avaliacao",
    is_active: true,
  },
];

function cloneKnowledgeConfig(config: AIKnowledgeBaseConfig): AIKnowledgeBaseConfig {
  return JSON.parse(JSON.stringify(config)) as AIKnowledgeBaseConfig;
}

function parseTagInput(value: string): string[] {
  return value
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatTagInput(value: string[]): string {
  return value.join(", ");
}

function readStringField(record: Record<string, unknown>, key: string, fallback = ""): string {
  const value = record[key];
  return typeof value === "string" ? value : fallback;
}

function unwrapSettingValue(value: unknown): unknown {
  if (value && typeof value === "object" && !Array.isArray(value) && "value" in (value as Record<string, unknown>)) {
    return (value as Record<string, unknown>).value;
  }
  return value;
}

function readSettingString(map: Map<string, unknown>, key: string, fallback = ""): string {
  const value = unwrapSettingValue(map.get(key));
  return typeof value === "string" ? value : fallback;
}

function readSettingNumber(map: Map<string, unknown>, key: string, fallback: number): number {
  const value = unwrapSettingValue(map.get(key));
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function readSettingBoolean(map: Map<string, unknown>, key: string, fallback: boolean): boolean {
  const value = unwrapSettingValue(map.get(key));
  return typeof value === "boolean" ? value : fallback;
}

function readSettingRecord(map: Map<string, unknown>, key: string): Record<string, unknown> {
  const value = map.get(key);
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function readThemeColor(value: unknown, fallback: string): string {
  return typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value) ? value : fallback;
}

function buildClinicProfileDraftFromSettings(settings: SettingItem[]): ClinicProfileConfig {
  const map = new Map(settings.map((item) => [item.key, item.value]));
  const profile = readSettingRecord(map, "clinic.profile");

  return {
    ...DEFAULT_CLINIC_PROFILE,
    clinic_name: readStringField(profile, "clinic_name"),
    legal_name: readStringField(profile, "legal_name"),
    cnpj: readStringField(profile, "cnpj"),
    main_phone: readStringField(profile, "main_phone"),
    whatsapp_phone: readStringField(profile, "whatsapp_phone"),
    email: readStringField(profile, "email"),
    website: readStringField(profile, "website"),
    timezone: readSettingString(map, "clinic.timezone", DEFAULT_CLINIC_PROFILE.timezone),
    address_line: readStringField(profile, "address_line"),
    neighborhood: readStringField(profile, "neighborhood"),
    city: readStringField(profile, "city"),
    state: readStringField(profile, "state"),
    zip_code: readStringField(profile, "zip_code"),
    technical_manager_name: readStringField(profile, "technical_manager_name"),
    technical_manager_cro: readStringField(profile, "technical_manager_cro"),
    payment_methods: readStringField(profile, "payment_methods"),
    accepted_insurance: readStringField(profile, "accepted_insurance"),
    cancellation_policy: readStringField(profile, "cancellation_policy"),
    reschedule_policy: readStringField(profile, "reschedule_policy"),
    about: readStringField(profile, "about"),
  };
}

function buildSecurityDraftFromSettings(settings: SettingItem[]): SecurityConfig {
  const map = new Map(settings.map((item) => [item.key, item.value]));

  return {
    session_timeout_minutes: readSettingNumber(
      map,
      "security.session_timeout",
      DEFAULT_SECURITY_CONFIG.session_timeout_minutes,
    ),
    idle_lock_minutes: readSettingNumber(map, "security.idle_lock_minutes", DEFAULT_SECURITY_CONFIG.idle_lock_minutes),
    require_mfa: readSettingBoolean(map, "security.require_mfa", DEFAULT_SECURITY_CONFIG.require_mfa),
    enforce_single_session: readSettingBoolean(
      map,
      "security.enforce_single_session",
      DEFAULT_SECURITY_CONFIG.enforce_single_session,
    ),
    password_rotation_days: readSettingNumber(
      map,
      "security.password_rotation_days",
      DEFAULT_SECURITY_CONFIG.password_rotation_days,
    ),
    audit_log_retention_days: readSettingNumber(
      map,
      "security.audit_log_retention_days",
      DEFAULT_SECURITY_CONFIG.audit_log_retention_days,
    ),
    allowed_ip_ranges: readSettingString(map, "security.allowed_ip_ranges", DEFAULT_SECURITY_CONFIG.allowed_ip_ranges),
    restrict_sensitive_exports: readSettingBoolean(
      map,
      "security.restrict_sensitive_exports",
      DEFAULT_SECURITY_CONFIG.restrict_sensitive_exports,
    ),
    notify_new_device_login: readSettingBoolean(
      map,
      "security.notify_new_device_login",
      DEFAULT_SECURITY_CONFIG.notify_new_device_login,
    ),
  };
}

function buildPrivacyDraftFromSettings(settings: SettingItem[]): PrivacyConfig {
  const map = new Map(settings.map((item) => [item.key, item.value]));
  const communicationAllowed = readSettingRecord(map, "privacy.communication_allowed");
  const privacyContact = readSettingRecord(map, "privacy.contact");
  const governance = readSettingRecord(map, "privacy.governance");
  const exportDefaults = readSettingRecord(map, "privacy.export_defaults");

  return {
    retention_days: readSettingNumber(map, "privacy.retention_days", DEFAULT_PRIVACY_CONFIG.retention_days),
    allow_marketing:
      typeof communicationAllowed.marketing === "boolean"
        ? communicationAllowed.marketing
        : DEFAULT_PRIVACY_CONFIG.allow_marketing,
    allow_operational:
      typeof communicationAllowed.operacional === "boolean"
        ? communicationAllowed.operacional
        : DEFAULT_PRIVACY_CONFIG.allow_operational,
    terms_version: readSettingString(map, "privacy.terms_version", DEFAULT_PRIVACY_CONFIG.terms_version),
    policy_version: readSettingString(map, "privacy.policy_version", DEFAULT_PRIVACY_CONFIG.policy_version),
    privacy_contact_name: readStringField(privacyContact, "name"),
    privacy_contact_email: readStringField(privacyContact, "email"),
    privacy_contact_phone: readStringField(privacyContact, "phone"),
    export_scope: readStringField(exportDefaults, "scope", DEFAULT_PRIVACY_CONFIG.export_scope),
    export_request_email: readStringField(exportDefaults, "requested_by_email"),
    anonymize_leads_after_days:
      typeof governance.anonymize_leads_after_days === "number"
        ? governance.anonymize_leads_after_days
        : DEFAULT_PRIVACY_CONFIG.anonymize_leads_after_days,
    consent_text: readStringField(governance, "consent_text"),
    data_sharing_notes: readStringField(governance, "data_sharing_notes"),
  };
}

function countFilledClinicProfileFields(profile: ClinicProfileConfig): number {
  return CLINIC_PROFILE_COMPLETION_FIELDS.filter((key) => profile[key].trim()).length;
}

function parseFlexibleSettingValue(rawValue: string): unknown {
  const trimmed = rawValue.trim();
  if (!trimmed) return "";

  const shouldTryJson =
    trimmed.startsWith("{") ||
    trimmed.startsWith("[") ||
    trimmed.startsWith("\"") ||
    trimmed === "true" ||
    trimmed === "false" ||
    trimmed === "null" ||
    /^-?\d+(\.\d+)?$/.test(trimmed);

  if (shouldTryJson) {
    try {
      return JSON.parse(trimmed);
    } catch {
      return rawValue;
    }
  }

  return rawValue;
}

function createServiceCatalogFormState(service?: Partial<ServiceCatalogItem> | null): ServiceCatalogFormState {
  return {
    id: service?.id ?? "",
    name: service?.name ?? "",
    description: service?.description ?? "",
    duration_minutes: service?.duration_minutes ?? 60,
    price_note: service?.price_note ?? "",
    is_active: service?.is_active !== false,
  };
}

export default function ConfiguracoesPage({ fixedTab }: ConfiguracoesPageProps = {}) {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<ConfiguracoesTab>(fixedTab ?? "Clínica");

  const [settingKey, setSettingKey] = useState("clinic.timezone");
  const [settingValue, setSettingValue] = useState("America/Sao_Paulo");
  const [clinicProfileDraft, setClinicProfileDraft] = useState<ClinicProfileConfig>(DEFAULT_CLINIC_PROFILE);
  const [securityConfigDraft, setSecurityConfigDraft] = useState<SecurityConfig>(DEFAULT_SECURITY_CONFIG);
  const [privacyConfigDraft, setPrivacyConfigDraft] = useState<PrivacyConfig>(DEFAULT_PRIVACY_CONFIG);

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
  const [serviceCatalogDraft, setServiceCatalogDraft] = useState<ServiceCatalogItem[]>([]);
  const [serviceDrawerMode, setServiceDrawerMode] = useState<ServiceDrawerMode>(null);
  const [editingServiceIndex, setEditingServiceIndex] = useState<number | null>(null);
  const [serviceForm, setServiceForm] = useState<ServiceCatalogFormState>(EMPTY_SERVICE_CATALOG_FORM);
  const [aiKnowledgeDraft, setAiKnowledgeDraft] = useState<AIKnowledgeBaseConfig>(
    DEFAULT_AI_KNOWLEDGE_CONFIG,
  );
  const [brandingDraft, setBrandingDraft] = useState<BrandingConfig>(DEFAULT_BRANDING_CONFIG);
  const [brandingLogoPreview, setBrandingLogoPreview] = useState<string | null>(null);
  const [unitForm, setUnitForm] = useState<UnitFormState>(EMPTY_UNIT_FORM);
  const [unitDrawerMode, setUnitDrawerMode] = useState<UnitDrawerMode>(null);
  const [editingUnitId, setEditingUnitId] = useState<string | null>(null);
  const [newUnitServiceName, setNewUnitServiceName] = useState("");

  useEffect(() => {
    if (fixedTab) {
      setActiveTab(fixedTab);
    }
  }, [fixedTab]);

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

  const whatsappHealthQuery = useQuery<WhatsAppHealth>({
    queryKey: ["whatsapp-health"],
    queryFn: async () => (await api.get("/settings/whatsapp/health")).data,
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
  const serviceCatalogQuery = useQuery<ServiceCatalogSettings>({
    queryKey: ["service-catalog-settings"],
    queryFn: async () => (await api.get("/settings/service-catalog/config")).data,
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

  useEffect(() => {
    const items = serviceCatalogQuery.data?.items ?? [];
    setServiceCatalogDraft(
      items.length
        ? items.map((item) => ({
            ...EMPTY_SERVICE_CATALOG_ITEM,
            ...item,
            duration_minutes: item.duration_minutes ?? 60,
          }))
        : [],
    );
  }, [serviceCatalogQuery.data]);

  useEffect(() => {
    const settings = settingsQuery.data?.data ?? [];
    setClinicProfileDraft(buildClinicProfileDraftFromSettings(settings));
    setSecurityConfigDraft(buildSecurityDraftFromSettings(settings));
    setPrivacyConfigDraft(buildPrivacyDraftFromSettings(settings));

    const map = new Map(settings.map((item) => [item.key, item.value]));
    const themePayload = map.get("branding.theme");
    const theme = themePayload && typeof themePayload === "object" ? (themePayload as Record<string, unknown>) : {};
    const logoValue = map.get("branding.logo_data_url");
    const logo =
      typeof logoValue === "string"
        ? logoValue
        : typeof theme.logo_data_url === "string"
          ? theme.logo_data_url
          : null;

    setBrandingDraft({
      primary_color: readThemeColor(theme.primary_color, DEFAULT_BRANDING_CONFIG.primary_color),
      secondary_color: readThemeColor(theme.secondary_color, DEFAULT_BRANDING_CONFIG.secondary_color),
      accent_color: readThemeColor(theme.accent_color, DEFAULT_BRANDING_CONFIG.accent_color),
      background_color: readThemeColor(theme.background_color, DEFAULT_BRANDING_CONFIG.background_color),
      surface_color: readThemeColor(theme.surface_color, DEFAULT_BRANDING_CONFIG.surface_color),
      card_color: readThemeColor(theme.card_color, DEFAULT_BRANDING_CONFIG.card_color),
      text_color: readThemeColor(theme.text_color, DEFAULT_BRANDING_CONFIG.text_color),
      muted_text_color: readThemeColor(theme.muted_text_color, DEFAULT_BRANDING_CONFIG.muted_text_color),
      border_color: readThemeColor(theme.border_color, DEFAULT_BRANDING_CONFIG.border_color),
      fullscreen_background_color: readThemeColor(
        theme.fullscreen_background_color,
        DEFAULT_BRANDING_CONFIG.fullscreen_background_color,
      ),
      fullscreen_header_color: readThemeColor(
        theme.fullscreen_header_color,
        DEFAULT_BRANDING_CONFIG.fullscreen_header_color,
      ),
      fullscreen_accent_color: readThemeColor(
        theme.fullscreen_accent_color,
        DEFAULT_BRANDING_CONFIG.fullscreen_accent_color,
      ),
      fullscreen_foreground_color: readThemeColor(
        theme.fullscreen_foreground_color,
        DEFAULT_BRANDING_CONFIG.fullscreen_foreground_color,
      ),
      surface_style:
        theme.surface_style === "flat" || theme.surface_style === "glass" ? theme.surface_style : "soft",
      logo_data_url: logo,
    });
    setBrandingLogoPreview(logo);
  }, [settingsQuery.data]);

  const upsertSettingMutation = useMutation({
    mutationFn: async ({ key, value, isSecret = false }: { key: string; value: unknown; isSecret?: boolean }) =>
      api.put(`/settings/${key}`, { value, is_secret: isSecret }),
    onSuccess: () => {
      toast.success("Configuração salva com sucesso.");
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: () => toast.error("Não foi possível salvar a configuração."),
  });

  const saveClinicProfileMutation = useMutation({
    mutationFn: async () => {
      const { timezone, ...profileValue } = clinicProfileDraft;
      return Promise.all([
        api.put("/settings/clinic.profile", {
          value: profileValue,
          is_secret: false,
        }),
        api.put("/settings/clinic.timezone", {
          value: timezone || DEFAULT_CLINIC_PROFILE.timezone,
          is_secret: false,
        }),
      ]);
    },
    onSuccess: () => {
      toast.success("Perfil da clínica salvo com sucesso.");
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: () => toast.error("Não foi possível salvar o perfil da clínica."),
  });

  const saveSecurityConfigMutation = useMutation({
    mutationFn: async () =>
      Promise.all([
        api.put("/settings/security.session_timeout", {
          value: securityConfigDraft.session_timeout_minutes,
          is_secret: false,
        }),
        api.put("/settings/security.idle_lock_minutes", {
          value: securityConfigDraft.idle_lock_minutes,
          is_secret: false,
        }),
        api.put("/settings/security.require_mfa", {
          value: securityConfigDraft.require_mfa,
          is_secret: false,
        }),
        api.put("/settings/security.enforce_single_session", {
          value: securityConfigDraft.enforce_single_session,
          is_secret: false,
        }),
        api.put("/settings/security.password_rotation_days", {
          value: securityConfigDraft.password_rotation_days,
          is_secret: false,
        }),
        api.put("/settings/security.audit_log_retention_days", {
          value: securityConfigDraft.audit_log_retention_days,
          is_secret: false,
        }),
        api.put("/settings/security.allowed_ip_ranges", {
          value: securityConfigDraft.allowed_ip_ranges.trim(),
          is_secret: false,
        }),
        api.put("/settings/security.restrict_sensitive_exports", {
          value: securityConfigDraft.restrict_sensitive_exports,
          is_secret: false,
        }),
        api.put("/settings/security.notify_new_device_login", {
          value: securityConfigDraft.notify_new_device_login,
          is_secret: false,
        }),
      ]),
    onSuccess: () => {
      toast.success("Política de segurança salva com sucesso.");
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: () => toast.error("Não foi possível salvar as configurações de segurança."),
  });

  const savePrivacyConfigMutation = useMutation({
    mutationFn: async () =>
      Promise.all([
        api.put("/settings/privacy.retention_days", {
          value: { value: privacyConfigDraft.retention_days },
          is_secret: false,
        }),
        api.put("/settings/privacy.communication_allowed", {
          value: {
            marketing: privacyConfigDraft.allow_marketing,
            operacional: privacyConfigDraft.allow_operational,
          },
          is_secret: false,
        }),
        api.put("/settings/privacy.terms_version", {
          value: { value: privacyConfigDraft.terms_version.trim() || DEFAULT_PRIVACY_CONFIG.terms_version },
          is_secret: false,
        }),
        api.put("/settings/privacy.policy_version", {
          value: { value: privacyConfigDraft.policy_version.trim() || DEFAULT_PRIVACY_CONFIG.policy_version },
          is_secret: false,
        }),
        api.put("/settings/privacy.contact", {
          value: {
            name: privacyConfigDraft.privacy_contact_name.trim(),
            email: privacyConfigDraft.privacy_contact_email.trim(),
            phone: privacyConfigDraft.privacy_contact_phone.trim(),
          },
          is_secret: false,
        }),
        api.put("/settings/privacy.export_defaults", {
          value: {
            scope: privacyConfigDraft.export_scope || DEFAULT_PRIVACY_CONFIG.export_scope,
            requested_by_email: privacyConfigDraft.export_request_email.trim() || null,
          },
          is_secret: false,
        }),
        api.put("/settings/privacy.governance", {
          value: {
            anonymize_leads_after_days: privacyConfigDraft.anonymize_leads_after_days,
            consent_text: privacyConfigDraft.consent_text.trim(),
            data_sharing_notes: privacyConfigDraft.data_sharing_notes.trim(),
          },
          is_secret: false,
        }),
      ]),
    onSuccess: () => {
      toast.success("Política de privacidade salva com sucesso.");
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      queryClient.invalidateQueries({ queryKey: ["privacy-summary"] });
    },
    onError: () => toast.error("Não foi possível salvar os dados de privacidade."),
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
    mutationFn: async () => {
      const payload = { ...aiKnowledgeDraft };
      delete (payload as Partial<AIKnowledgeBaseConfig>).services;
      return api.put("/settings/ai-knowledge-base/config", payload);
    },
    onSuccess: () => {
      toast.success("Base de conhecimento da IA salva com sucesso.");
      queryClient.invalidateQueries({ queryKey: ["ai-knowledge-base-settings"] });
      queryClient.invalidateQueries({ queryKey: ["support-knowledge"] });
    },
    onError: () => toast.error("Não foi possível salvar o conhecimento da IA."),
  });

  const saveServiceCatalogMutation = useMutation({
    mutationFn: async () =>
      api.put("/settings/service-catalog/config", {
        items: serviceCatalogDraft,
      }),
    onSuccess: () => {
      toast.success("Catálogo de serviços salvo com sucesso.");
      queryClient.invalidateQueries({ queryKey: ["service-catalog-settings"] });
      queryClient.invalidateQueries({ queryKey: ["settings-units"] });
      queryClient.invalidateQueries({ queryKey: ["team-dataset"] });
      queryClient.invalidateQueries({ queryKey: ["agenda-dataset"] });
      queryClient.invalidateQueries({ queryKey: ["ai-knowledge-base-settings"] });
      queryClient.invalidateQueries({ queryKey: ["support-service-catalog"] });
    },
    onError: () => toast.error("Não foi possível salvar o catálogo de serviços."),
  });

  const saveBrandingMutation = useMutation({
    mutationFn: async (payload?: BrandingConfig) => api.put("/settings/branding/theme", payload ?? brandingDraft),
    onSuccess: () => {
      toast.success("Tema e marca salvos com sucesso.");
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      queryClient.invalidateQueries({ queryKey: ["branding-theme"] });
    },
    onError: (error) => toast.error(extractApiErrorMessage(error, "Não foi possível salvar o tema da clínica.")),
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
      setUnitForm(EMPTY_UNIT_FORM);
      setUnitDrawerMode(null);
      setEditingUnitId(null);
      setNewUnitServiceName("");
      queryClient.invalidateQueries({ queryKey: ["settings-units"] });
      queryClient.invalidateQueries({ queryKey: ["agenda-dataset"] });
      queryClient.invalidateQueries({ queryKey: ["team-dataset"] });
      queryClient.invalidateQueries({ queryKey: ["service-catalog-settings"] });
    },
    onError: (error) => toast.error(extractApiErrorMessage(error, "Não foi possível atualizar a unidade.")),
  });

  const createUnitMutation = useMutation({
    mutationFn: async (payload: Record<string, unknown>) => api.post("/units", payload),
    onSuccess: () => {
      toast.success("Unidade criada com sucesso.");
      setUnitForm(EMPTY_UNIT_FORM);
      setUnitDrawerMode(null);
      setEditingUnitId(null);
      setNewUnitServiceName("");
      queryClient.invalidateQueries({ queryKey: ["settings-units"] });
      queryClient.invalidateQueries({ queryKey: ["agenda-dataset"] });
      queryClient.invalidateQueries({ queryKey: ["team-dataset"] });
      queryClient.invalidateQueries({ queryKey: ["service-catalog-settings"] });
    },
    onError: (error) => toast.error(extractApiErrorMessage(error, "Não foi possível criar a unidade.")),
  });

  const deleteUnitMutation = useMutation({
    mutationFn: async (unitId: string) => api.delete(`/units/${unitId}`),
    onSuccess: () => {
      toast.success("Unidade excluída com sucesso.");
      setUnitForm(EMPTY_UNIT_FORM);
      setUnitDrawerMode(null);
      setEditingUnitId(null);
      setNewUnitServiceName("");
      queryClient.invalidateQueries({ queryKey: ["settings-units"] });
      queryClient.invalidateQueries({ queryKey: ["agenda-dataset"] });
      queryClient.invalidateQueries({ queryKey: ["team-dataset"] });
      queryClient.invalidateQueries({ queryKey: ["service-catalog-settings"] });
    },
    onError: (error) => toast.error(extractApiErrorMessage(error, "Não foi possível excluir a unidade.")),
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
      queryClient.invalidateQueries({ queryKey: ["whatsapp-health"] });
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
      queryClient.invalidateQueries({ queryKey: ["whatsapp-health"] });
    },
    onError: (error) => {
      setWhatsappTestResult(null);
      toast.error(extractApiErrorMessage(error, "Não foi possível validar a conexão WhatsApp."));
    },
  });

  const acceptTermsMutation = useMutation({
    mutationFn: async () =>
      api.post("/privacy/terms/accept", {
        terms_version: privacyConfigDraft.terms_version.trim() || DEFAULT_PRIVACY_CONFIG.terms_version,
        policy_version: privacyConfigDraft.policy_version.trim() || DEFAULT_PRIVACY_CONFIG.policy_version,
      }),
    onSuccess: () => {
      toast.success("Termos de privacidade aceitos.");
      queryClient.invalidateQueries({ queryKey: ["privacy-summary"] });
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: () => toast.error("Não foi possível registrar aceite dos termos."),
  });

  const exportPrivacyDataMutation = useMutation({
    mutationFn: async () =>
      (
        await api.post("/privacy/export", {
          scope: privacyConfigDraft.export_scope || DEFAULT_PRIVACY_CONFIG.export_scope,
          requested_by_email: privacyConfigDraft.export_request_email.trim() || undefined,
        })
      ).data,
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

  const restoreClinicProfileDraft = () => {
    setClinicProfileDraft(buildClinicProfileDraftFromSettings(settingsQuery.data?.data ?? []));
  };

  const restoreSecurityConfigDraft = () => {
    setSecurityConfigDraft(buildSecurityDraftFromSettings(settingsQuery.data?.data ?? []));
  };

  const restorePrivacyConfigDraft = () => {
    setPrivacyConfigDraft(buildPrivacyDraftFromSettings(settingsQuery.data?.data ?? []));
  };

  const handleSaveClinicProfile = () => {
    if (!clinicProfileDraft.clinic_name.trim()) {
      toast.error("Informe o nome da clínica antes de salvar.");
      return;
    }
    if (!clinicProfileDraft.timezone.trim()) {
      toast.error("Informe o timezone operacional da clínica.");
      return;
    }
    saveClinicProfileMutation.mutate();
  };

  const handleSaveSecurityConfig = () => {
    if (securityConfigDraft.session_timeout_minutes < 5) {
      toast.error("Defina pelo menos 5 minutos para o timeout de sessão.");
      return;
    }
    if (securityConfigDraft.idle_lock_minutes < 1) {
      toast.error("Defina pelo menos 1 minuto para bloqueio por inatividade.");
      return;
    }
    saveSecurityConfigMutation.mutate();
  };

  const handleSavePrivacyConfig = () => {
    if (privacyConfigDraft.retention_days < 1) {
      toast.error("Informe um período de retenção válido.");
      return;
    }
    if (!privacyConfigDraft.terms_version.trim() || !privacyConfigDraft.policy_version.trim()) {
      toast.error("Informe a versão dos termos e da política.");
      return;
    }
    savePrivacyConfigMutation.mutate();
  };

  if (
    settingsQuery.isLoading ||
    whatsappAccountsQuery.isLoading ||
    whatsappHealthQuery.isLoading ||
    whatsappTemplatesQuery.isLoading ||
    unitsQuery.isLoading ||
    privacySummaryQuery.isLoading ||
    aiAutoresponderQuery.isLoading ||
    aiKnowledgeBaseQuery.isLoading ||
    serviceCatalogQuery.isLoading
  ) {
    return (
      <LoadingState
        message={
          fixedTab === "Serviços"
            ? "Carregando serviços..."
            : fixedTab === "Unidades"
              ? "Carregando unidades..."
              : "Carregando configurações..."
        }
      />
    );
  }
  if (
    settingsQuery.isError ||
    whatsappAccountsQuery.isError ||
    whatsappHealthQuery.isError ||
    whatsappTemplatesQuery.isError ||
    unitsQuery.isError ||
    privacySummaryQuery.isError ||
    aiAutoresponderQuery.isError ||
    aiKnowledgeBaseQuery.isError ||
    serviceCatalogQuery.isError
  ) {
    return (
      <ErrorState
        message={
          fixedTab === "Serviços"
            ? "Não foi possível carregar os serviços."
            : fixedTab === "Unidades"
              ? "Não foi possível carregar as unidades."
              : "Não foi possível carregar as configurações da clínica."
        }
      />
    );
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
  const whatsappHealth = whatsappHealthQuery.data;
  const whatsappHealthIsOk = whatsappHealth?.status === "ok";
  const whatsappHealthTone = whatsappHealthIsOk
    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
    : whatsappHealth?.status === "warning"
      ? "border-amber-200 bg-amber-50 text-amber-800"
      : "border-red-200 bg-red-50 text-red-800";
  const templateRows = whatsappTemplatesQuery.data?.data ?? [];

  const clinicTimezone = clinicProfileDraft.timezone || DEFAULT_CLINIC_PROFILE.timezone;
  const clinicProfileFilledFields = countFilledClinicProfileFields(clinicProfileDraft);
  const clinicProfileCompletionPercent = Math.round(
    (clinicProfileFilledFields / CLINIC_PROFILE_COMPLETION_FIELDS.length) * 100,
  );
  const privacySummary = privacySummaryQuery.data;
  const privacyAcceptedAtLabel = privacySummary?.accepted_at
    ? new Date(privacySummary.accepted_at).toLocaleString("pt-BR")
    : "não aceito";
  const consentRateLabel = `${privacySummary?.consent_rate?.toFixed(1) ?? "0.0"}%`;
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
  const unitServiceCatalog = Array.from(
    new Set(
      [
        ...serviceCatalogDraft
          .filter((item) => item.is_active !== false)
          .map((item) => item.name?.trim() ?? ""),
        ...(unitForm.services ?? []),
      ].filter(Boolean),
    ),
  ).sort((left, right) => left.localeCompare(right));
  const knowledgeFaq = aiKnowledgeDraft.faq.length ? aiKnowledgeDraft.faq : [EMPTY_FAQ];

  const readUnitNestedField = (source: Record<string, unknown> | undefined, ...keys: string[]) => {
    if (!source) return "";
    for (const key of keys) {
      const value = source[key];
      if (typeof value === "string" && value.trim()) return value;
      if (typeof value === "number") return String(value);
    }
    return "";
  };

  const formatUnitAddress = (unit: UnitSettingsItem) => {
    const address = unit.address ?? {};
    const direct = readUnitNestedField(address, "formatted", "full", "address", "line", "line1");
    if (direct) return direct;
    return [
      readUnitNestedField(address, "street", "logradouro", "address_line"),
      readUnitNestedField(address, "number", "numero"),
      readUnitNestedField(address, "complement", "complemento"),
      readUnitNestedField(address, "neighborhood", "bairro"),
      readUnitNestedField(address, "city", "cidade"),
      readUnitNestedField(address, "state", "uf"),
      readUnitNestedField(address, "zip_code", "cep"),
    ]
      .filter(Boolean)
      .join(", ");
  };

  const buildUnitAddressPayload = () => {
    const street = unitForm.address_line.trim();
    const number = unitForm.address_number.trim();
    const complement = unitForm.complement.trim();
    const neighborhood = unitForm.neighborhood.trim();
    const city = unitForm.city.trim();
    const state = unitForm.state.trim().toUpperCase();
    const zipCode = unitForm.zip_code.trim();
    const formatted = [
      street && number ? `${street}, ${number}` : street || number,
      complement,
      neighborhood,
      city && state ? `${city} - ${state}` : city || state,
      zipCode,
    ]
      .filter(Boolean)
      .join(", ");

    return {
      formatted,
      street,
      number,
      complement,
      neighborhood,
      city,
      state,
      zip_code: zipCode,
      reference_point: unitForm.reference_point.trim(),
      access_instructions: unitForm.access_instructions.trim(),
      parking_info: unitForm.parking_info.trim(),
    };
  };

  const buildUnitWorkingHoursPayload = () => ({
    days_text: unitForm.working_days_text.trim(),
    start: unitForm.working_hours_start.trim(),
    end: unitForm.working_hours_end.trim(),
    notes: unitForm.working_hours_notes.trim(),
  });

  const resetUnitForm = () => {
    setUnitForm(EMPTY_UNIT_FORM);
    setUnitDrawerMode(null);
    setEditingUnitId(null);
    setNewUnitServiceName("");
  };

  const openCreateUnitDrawer = () => {
    setEditingUnitId(null);
    setUnitForm(EMPTY_UNIT_FORM);
    setNewUnitServiceName("");
    setUnitDrawerMode("create");
  };

  const startEditingUnit = (unit: UnitSettingsItem) => {
    const address = unit.address ?? {};
    const workingHours = unit.working_hours ?? {};
    setEditingUnitId(unit.id);
    setUnitForm({
      name: unit.name ?? "",
      code: unit.code ?? "",
      phone: unit.phone ?? "",
      email: unit.email ?? "",
      address_line: readUnitNestedField(address, "street", "logradouro", "address_line", "line1", "line"),
      address_number: readUnitNestedField(address, "number", "numero"),
      complement: readUnitNestedField(address, "complement", "complemento"),
      neighborhood: readUnitNestedField(address, "neighborhood", "bairro"),
      city: readUnitNestedField(address, "city", "cidade"),
      state: readUnitNestedField(address, "state", "uf"),
      zip_code: readUnitNestedField(address, "zip_code", "cep"),
      reference_point: readUnitNestedField(address, "reference_point", "referencia"),
      access_instructions: readUnitNestedField(address, "access_instructions", "instructions"),
      parking_info: readUnitNestedField(address, "parking_info", "parking"),
      working_days_text: readUnitNestedField(workingHours, "days_text", "days", "weekdays_text") || "Segunda a sexta",
      working_hours_start: readUnitNestedField(workingHours, "start", "opens_at") || "08:00",
      working_hours_end: readUnitNestedField(workingHours, "end", "closes_at") || "18:00",
      working_hours_notes: readUnitNestedField(workingHours, "notes", "observation"),
      services: [...(unit.services ?? [])].sort((left, right) => left.localeCompare(right)),
    });
    setNewUnitServiceName("");
    setUnitDrawerMode("edit");
  };

  const toggleUnitService = (serviceName: string) => {
    setUnitForm((current) => {
      const selected = current.services.includes(serviceName);
      return {
        ...current,
        services: selected
          ? current.services.filter((item) => item !== serviceName)
          : [...current.services, serviceName].sort((left, right) => left.localeCompare(right)),
      };
    });
  };

  const addCustomServiceToUnitForm = () => {
    const nextServiceName = newUnitServiceName.trim();
    if (!nextServiceName) {
      toast.error("Digite o nome do serviço antes de adicionar.");
      return;
    }

    setUnitForm((current) => {
      if (current.services.some((item) => item.toLowerCase() === nextServiceName.toLowerCase())) {
        return current;
      }
      return {
        ...current,
        services: [...current.services, nextServiceName].sort((left, right) => left.localeCompare(right)),
      };
    });
    setNewUnitServiceName("");
  };

  const handleSubmitUnitForm = () => {
    const payload = {
      name: unitForm.name.trim(),
      code: unitForm.code.trim().toUpperCase(),
      phone: unitForm.phone.trim() || null,
      email: unitForm.email.trim() || null,
      address: buildUnitAddressPayload(),
      working_hours: buildUnitWorkingHoursPayload(),
      services: unitForm.services,
    };
    if (!payload.name || !payload.code) {
      toast.error("Preencha pelo menos nome e código da unidade.");
      return;
    }

    if (editingUnitId) {
      updateUnitMutation.mutate({ unitId: editingUnitId, payload });
      return;
    }
    createUnitMutation.mutate(payload);
  };

  const closeServiceDrawer = () => {
    setServiceDrawerMode(null);
    setEditingServiceIndex(null);
    setServiceForm(EMPTY_SERVICE_CATALOG_FORM);
  };

  const openCreateServiceDrawer = () => {
    setEditingServiceIndex(null);
    setServiceForm(createServiceCatalogFormState({ id: `${Date.now()}` }));
    setServiceDrawerMode("create");
  };

  const openEditServiceDrawer = (index: number) => {
    const service = serviceCatalogDraft[index];
    if (!service) return;
    setEditingServiceIndex(index);
    setServiceForm(createServiceCatalogFormState(service));
    setServiceDrawerMode("edit");
  };

  const handleSaveServiceForm = () => {
    const normalizedName = serviceForm.name.trim();
    const normalizedDescription = serviceForm.description.trim();
    const normalizedDuration = Number(serviceForm.duration_minutes || 0);

    if (!normalizedName) {
      toast.error("Informe o nome oficial do serviço.");
      return;
    }
    if (!normalizedDescription) {
      toast.error("Informe a descrição oficial do serviço.");
      return;
    }
    if (!Number.isFinite(normalizedDuration) || normalizedDuration < 5) {
      toast.error("Informe uma duração válida em minutos.");
      return;
    }

    const normalizedService: ServiceCatalogItem = {
      id: serviceForm.id || `${Date.now()}`,
      name: normalizedName,
      description: normalizedDescription,
      duration_minutes: normalizedDuration,
      price_note: serviceForm.price_note.trim(),
      is_active: serviceForm.is_active,
    };

    setServiceCatalogDraft((current) => {
      if (serviceDrawerMode === "edit" && editingServiceIndex !== null) {
        const items = [...current];
        items[editingServiceIndex] = normalizedService;
        return items;
      }
      return [...current, normalizedService];
    });

    toast.success(serviceDrawerMode === "edit" ? "Serviço atualizado no catálogo." : "Serviço adicionado ao catálogo.");
    closeServiceDrawer();
  };

  const removeServiceCatalogItem = (index: number) => {
    const service = serviceCatalogDraft[index];
    if (!service) return;
    const confirmed = window.confirm(`Excluir o serviço ${service.name || "sem nome"} do catálogo?`);
    if (!confirmed) return;

    setServiceCatalogDraft((current) => current.filter((_, itemIndex) => itemIndex !== index));
    if (serviceDrawerMode === "edit" && editingServiceIndex === index) {
      closeServiceDrawer();
    }
    toast.success("Serviço removido do catálogo.");
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

  const applySorrisoSulKnowledgePreset = () => {
    setAiKnowledgeDraft(cloneKnowledgeConfig(SORRISO_SUL_AI_KNOWLEDGE_PRESET));
    toast.success("Conteudo de conhecimento da Sorriso Sul aplicado. Revise e salve.");
  };

  const applySorrisoSulServiceCatalogPreset = () => {
    setServiceCatalogDraft(
      SORRISO_SUL_SERVICE_CATALOG_PRESET.map((item) => ({ ...item })),
    );
    closeServiceDrawer();
    toast.success("Catalogo oficial de servicos preenchido com o preset da Sorriso Sul.");
  };

  const clearKnowledgeBaseDraft = () => {
    setAiKnowledgeDraft(cloneKnowledgeConfig(DEFAULT_AI_KNOWLEDGE_CONFIG));
    toast.success("Formulario de conhecimento limpo.");
  };

  const clearServiceCatalogDraft = () => {
    setServiceCatalogDraft([]);
    closeServiceDrawer();
    toast.success("Catalogo oficial de servicos limpo.");
  };

  const onBrandingLogoUpload = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      toast.error("Selecione um arquivo de imagem para a logo.");
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = typeof reader.result === "string" ? reader.result : null;
      if (!dataUrl) return;
      setBrandingLogoPreview(dataUrl);
      setBrandingDraft((current) => ({ ...current, logo_data_url: dataUrl }));
    };
    reader.readAsDataURL(file);
  };

  const restoreBrandingColors = () => {
    setBrandingDraft((current) => ({
      ...DEFAULT_BRANDING_CONFIG,
      logo_data_url: current.logo_data_url ?? null,
    }));
    toast.success("Cores do tema restauradas para o padrao.");
  };

  const applyBrandingPreset = (preset: (typeof BRANDING_PRESETS)[number]) => {
    const nextDraft: BrandingConfig = {
      ...preset.config,
      logo_data_url: brandingDraft.logo_data_url ?? null,
    };

    setBrandingDraft(nextDraft);
    toast.success(`Tema "${preset.name}" aplicado na prévia.`);
  };

  const applyAndSaveBrandingPreset = (preset: (typeof BRANDING_PRESETS)[number]) => {
    const nextDraft: BrandingConfig = {
      ...preset.config,
      logo_data_url: brandingDraft.logo_data_url ?? null,
    };

    setBrandingDraft(nextDraft);
    saveBrandingMutation.mutate(nextDraft);
  };

  const pageHeaderCopy =
    fixedTab === "Serviços"
      ? {
          eyebrow: "Catálogo operacional",
          title: "Serviços da clínica",
          description: "Gerencie o catálogo oficial usado pela agenda, profissionais, unidades e IA.",
        }
      : fixedTab === "Unidades"
        ? {
            eyebrow: "Estrutura da clínica",
            title: "Unidades da clínica",
            description: "Cadastre endereços, contatos e quais serviços cada unidade oferece.",
          }
        : {
            eyebrow: "Configuração",
            title: "Configurações da clínica e WhatsApp",
            description: "Parâmetros operacionais, segurança e integrações para sustentar a operação.",
          };

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow={pageHeaderCopy.eyebrow}
        title={pageHeaderCopy.title}
        description={pageHeaderCopy.description}
      />

      {!fixedTab ? (
        <FilterBar search={search} onSearchChange={setSearch} searchPlaceholder="Buscar configuração...">
          {CONFIGURATION_TABS.map((tab) => (
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
      ) : null}

      {activeTab === "Clínica" ? (
        <div className="space-y-4">
          <Card className="border-stone-200">
            <CardHeader>
              <CardTitle>Perfil da clínica</CardTitle>
              <p className="text-sm text-stone-600">
                Centralize aqui os dados institucionais, comerciais e operacionais que a equipe usa no dia a dia.
              </p>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.75fr)_320px]">
                <div className="space-y-4">
                  <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">
                          Identidade e contato
                        </p>
                        <p className="text-xs text-stone-500">
                          Dados principais para recepção, atendimento e operação.
                        </p>
                      </div>
                      <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-stone-600">
                        Timezone: {clinicTimezone}
                      </span>
                    </div>

                    <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                      <div className="xl:col-span-2">
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                          Nome da clínica
                        </label>
                        <Input
                          placeholder="Ex.: Clínica Sorriso Sul"
                          value={clinicProfileDraft.clinic_name}
                          onChange={(event) =>
                            setClinicProfileDraft((current) => ({ ...current, clinic_name: event.target.value }))
                          }
                        />
                      </div>
                      <div>
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                          Timezone
                        </label>
                        <Input
                          placeholder="America/Sao_Paulo"
                          value={clinicProfileDraft.timezone}
                          onChange={(event) =>
                            setClinicProfileDraft((current) => ({ ...current, timezone: event.target.value }))
                          }
                        />
                      </div>
                      <div className="md:col-span-2">
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                          Razão social
                        </label>
                        <Input
                          placeholder="Ex.: Sorriso Sul Clinica Integrada LTDA"
                          value={clinicProfileDraft.legal_name}
                          onChange={(event) =>
                            setClinicProfileDraft((current) => ({ ...current, legal_name: event.target.value }))
                          }
                        />
                      </div>
                      <div>
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">CNPJ</label>
                        <Input
                          placeholder="00.000.000/0001-00"
                          value={clinicProfileDraft.cnpj}
                          onChange={(event) =>
                            setClinicProfileDraft((current) => ({ ...current, cnpj: event.target.value }))
                          }
                        />
                      </div>
                      <div>
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                          Telefone principal
                        </label>
                        <Input
                          type="tel"
                          placeholder="(11) 3333-0000"
                          value={clinicProfileDraft.main_phone}
                          onChange={(event) =>
                            setClinicProfileDraft((current) => ({ ...current, main_phone: event.target.value }))
                          }
                        />
                      </div>
                      <div>
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                          WhatsApp principal
                        </label>
                        <Input
                          type="tel"
                          placeholder="(11) 99999-0000"
                          value={clinicProfileDraft.whatsapp_phone}
                          onChange={(event) =>
                            setClinicProfileDraft((current) => ({ ...current, whatsapp_phone: event.target.value }))
                          }
                        />
                      </div>
                      <div>
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">E-mail</label>
                        <Input
                          type="email"
                          placeholder="contato@clinica.com"
                          value={clinicProfileDraft.email}
                          onChange={(event) =>
                            setClinicProfileDraft((current) => ({ ...current, email: event.target.value }))
                          }
                        />
                      </div>
                      <div>
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Site</label>
                        <Input
                          type="url"
                          placeholder="https://www.clinica.com.br"
                          value={clinicProfileDraft.website}
                          onChange={(event) =>
                            setClinicProfileDraft((current) => ({ ...current, website: event.target.value }))
                          }
                        />
                      </div>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-stone-200 bg-white p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Endereço</p>
                    <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                      <div className="md:col-span-2 xl:col-span-2">
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                          Endereço
                        </label>
                        <Input
                          placeholder="Rua, número e complemento"
                          value={clinicProfileDraft.address_line}
                          onChange={(event) =>
                            setClinicProfileDraft((current) => ({ ...current, address_line: event.target.value }))
                          }
                        />
                      </div>
                      <div>
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                          Bairro
                        </label>
                        <Input
                          placeholder="Bairro"
                          value={clinicProfileDraft.neighborhood}
                          onChange={(event) =>
                            setClinicProfileDraft((current) => ({ ...current, neighborhood: event.target.value }))
                          }
                        />
                      </div>
                      <div>
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">CEP</label>
                        <Input
                          placeholder="00000-000"
                          value={clinicProfileDraft.zip_code}
                          onChange={(event) =>
                            setClinicProfileDraft((current) => ({ ...current, zip_code: event.target.value }))
                          }
                        />
                      </div>
                      <div className="md:col-span-2">
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Cidade</label>
                        <Input
                          placeholder="Cidade"
                          value={clinicProfileDraft.city}
                          onChange={(event) =>
                            setClinicProfileDraft((current) => ({ ...current, city: event.target.value }))
                          }
                        />
                      </div>
                      <div>
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Estado</label>
                        <Input
                          placeholder="UF"
                          value={clinicProfileDraft.state}
                          onChange={(event) =>
                            setClinicProfileDraft((current) => ({ ...current, state: event.target.value }))
                          }
                        />
                      </div>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">
                      Operação comercial
                    </p>
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      <div className="space-y-1">
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                          Formas de pagamento
                        </label>
                        <textarea
                          className={TEXTAREA_CLASSNAME}
                          placeholder="Ex.: PIX, débito, crédito, parcelamento em até 10x."
                          value={clinicProfileDraft.payment_methods}
                          onChange={(event) =>
                            setClinicProfileDraft((current) => ({ ...current, payment_methods: event.target.value }))
                          }
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                          Convênios ou cobertura
                        </label>
                        <textarea
                          className={TEXTAREA_CLASSNAME}
                          placeholder="Ex.: Particular, reembolso, convênios aceitos."
                          value={clinicProfileDraft.accepted_insurance}
                          onChange={(event) =>
                            setClinicProfileDraft((current) => ({
                              ...current,
                              accepted_insurance: event.target.value,
                            }))
                          }
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                          Política de cancelamento
                        </label>
                        <textarea
                          className={TEXTAREA_CLASSNAME}
                          placeholder="Explique prazo mínimo, taxa e exceções."
                          value={clinicProfileDraft.cancellation_policy}
                          onChange={(event) =>
                            setClinicProfileDraft((current) => ({
                              ...current,
                              cancellation_policy: event.target.value,
                            }))
                          }
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                          Política de remarcação
                        </label>
                        <textarea
                          className={TEXTAREA_CLASSNAME}
                          placeholder="Explique antecedência mínima e como funciona a remarcação."
                          value={clinicProfileDraft.reschedule_policy}
                          onChange={(event) =>
                            setClinicProfileDraft((current) => ({
                              ...current,
                              reschedule_policy: event.target.value,
                            }))
                          }
                        />
                      </div>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-stone-200 bg-white p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">
                      Responsável técnico e posicionamento
                    </p>
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      <div>
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                          Responsável técnico
                        </label>
                        <Input
                          placeholder="Nome do responsável"
                          value={clinicProfileDraft.technical_manager_name}
                          onChange={(event) =>
                            setClinicProfileDraft((current) => ({
                              ...current,
                              technical_manager_name: event.target.value,
                            }))
                          }
                        />
                      </div>
                      <div>
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                          CRO do responsável
                        </label>
                        <Input
                          placeholder="Ex.: CRO-SP 12345"
                          value={clinicProfileDraft.technical_manager_cro}
                          onChange={(event) =>
                            setClinicProfileDraft((current) => ({
                              ...current,
                              technical_manager_cro: event.target.value,
                            }))
                          }
                        />
                      </div>
                      <div className="md:col-span-2">
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                          Sobre a clínica
                        </label>
                        <textarea
                          className={`${TEXTAREA_CLASSNAME} min-h-[128px]`}
                          placeholder="Resumo institucional da clínica, diferenciais e proposta de atendimento."
                          value={clinicProfileDraft.about}
                          onChange={(event) =>
                            setClinicProfileDraft((current) => ({ ...current, about: event.target.value }))
                          }
                        />
                      </div>
                    </div>
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="rounded-2xl border border-primary/15 bg-primary/5 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
                      Completude do cadastro
                    </p>
                    <p className="mt-2 text-2xl font-bold text-stone-900">
                      {clinicProfileFilledFields}/{CLINIC_PROFILE_COMPLETION_FIELDS.length}
                    </p>
                    <p className="text-sm text-stone-600">
                      Campos estratégicos preenchidos para recepção, operação e IA.
                    </p>
                    <div className="mt-4 h-2 overflow-hidden rounded-full bg-white">
                      <div
                        className="h-full rounded-full bg-primary transition-all"
                        style={{ width: `${clinicProfileCompletionPercent}%` }}
                      />
                    </div>
                  </div>

                  <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">
                      Esse perfil ajuda em
                    </p>
                    <ul className="mt-3 space-y-2 text-sm text-stone-700">
                      <li>Padronizar as informações que a equipe consulta no atendimento.</li>
                      <li>Organizar contato, endereço e regras comerciais da clínica.</li>
                      <li>Servir de base para onboarding, comunicação e futuras automações.</li>
                      <li>Evitar que informações importantes fiquem espalhadas em observações soltas.</li>
                    </ul>
                  </div>

                  <div className="rounded-2xl border border-stone-200 bg-white p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">
                      Recomendação prática
                    </p>
                    <p className="mt-3 text-sm leading-relaxed text-stone-700">
                      Preencha primeiro nome da clínica, contatos, endereço, pagamento e políticas de agenda. Isso já
                      cobre o essencial para operação diária.
                    </p>
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap justify-end gap-2">
                <Button variant="outline" onClick={restoreClinicProfileDraft}>
                  Recarregar dados salvos
                </Button>
                <Button onClick={handleSaveClinicProfile} disabled={saveClinicProfileMutation.isPending}>
                  {saveClinicProfileMutation.isPending ? "Salvando perfil..." : "Salvar perfil da clínica"}
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card className="border-stone-200">
            <CardHeader>
              <CardTitle>Configuração avançada</CardTitle>
              <p className="text-sm text-stone-600">
                Use esta área apenas quando precisar salvar uma chave técnica específica. Aceita texto puro ou JSON.
              </p>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-3 xl:grid-cols-[260px_minmax(0,1fr)_220px]">
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Chave técnica</label>
                  <Input
                    placeholder="Ex.: clinic.timezone"
                    value={settingKey}
                    onChange={(event) => setSettingKey(event.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Valor</label>
                  <textarea
                    className={`${TEXTAREA_CLASSNAME} min-h-[96px]`}
                    placeholder='Ex.: America/Sao_Paulo ou {"enabled": true}'
                    value={settingValue}
                    onChange={(event) => setSettingValue(event.target.value)}
                  />
                </div>
                <div className="flex flex-col justify-end gap-2">
                  <div className="rounded-xl border border-stone-200 bg-stone-50 px-3 py-2 text-xs text-stone-600">
                    Timezone operacional atual: {clinicTimezone}
                  </div>
                  <Button
                    onClick={() =>
                      upsertSettingMutation.mutate({
                        key: settingKey,
                        value: parseFlexibleSettingValue(settingValue),
                      })
                    }
                    disabled={upsertSettingMutation.isPending || !settingKey.trim()}
                  >
                    {upsertSettingMutation.isPending ? "Salvando..." : "Salvar configuração técnica"}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      ) : null}

      {activeTab === "Serviços" ? (
        <div className="space-y-4">
          <Card className="border-stone-200">
            <CardHeader>
              <CardTitle>Catalogo oficial de servicos</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3">
                <p className="text-sm font-semibold text-emerald-800">
                  Fonte oficial para agenda, unidades, profissionais e IA
                </p>
                <p className="mt-1 text-xs text-emerald-700">
                  Cadastre aqui o nome oficial do servico, descricao, duracao em minutos, faixa de preco e status.
                  A agenda usa esse tempo para bloquear o profissional corretamente e a IA usa essas mesmas
                  informacoes para responder pacientes com dados exatos.
                </p>
              </div>

              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="outline" onClick={applySorrisoSulServiceCatalogPreset}>
                  Preencher Sorriso Sul
                </Button>
                <Button type="button" variant="outline" onClick={clearServiceCatalogDraft}>
                  Limpar catalogo
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card className="border-stone-200">
            <CardHeader>
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <CardTitle>Servicos da clinica</CardTitle>
                  <p className="text-sm text-stone-600">
                    Organize o catalogo em cards e use o drawer para criar ou editar cada servico.
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-stone-100 px-3 py-1 text-xs font-medium text-stone-700">
                    {serviceCatalogDraft.length} servico(s)
                  </span>
                  <Button type="button" onClick={openCreateServiceDrawer}>
                    Cadastrar servico
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {serviceCatalogDraft.length ? (
                <div className="grid gap-3 xl:grid-cols-2">
                  {serviceCatalogDraft
                    .map((service, index) => ({ service, index }))
                    .sort((left, right) => {
                      const leftName = left.service.name?.trim() || "zzzz";
                      const rightName = right.service.name?.trim() || "zzzz";
                      return leftName.localeCompare(rightName);
                    })
                    .map(({ service, index }) => (
                      <div
                        key={service.id || `service-catalog-${index}`}
                        className="rounded-2xl border border-stone-200 bg-white p-4 shadow-sm"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="space-y-1">
                            <p className="text-base font-semibold text-stone-900">
                              {service.name?.trim() || "Servico sem nome"}
                            </p>
                            <p className="text-xs text-stone-500">
                              {service.duration_minutes ?? 60} min
                              {service.price_note?.trim() ? ` • ${service.price_note}` : ""}
                            </p>
                          </div>
                          <StatusBadge value={service.is_active === false ? "inativo" : "ativo"} />
                        </div>

                        <div className="mt-4 grid gap-3 sm:grid-cols-2">
                          <div className="rounded-xl border border-stone-100 bg-stone-50 px-3 py-2">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">
                              Duracao
                            </p>
                            <p className="mt-1 text-sm text-stone-700">{service.duration_minutes ?? 60} minutos</p>
                          </div>
                          <div className="rounded-xl border border-stone-100 bg-stone-50 px-3 py-2">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">
                              Faixa de preco
                            </p>
                            <p className="mt-1 text-sm text-stone-700">
                              {service.price_note?.trim() || "Nao informada"}
                            </p>
                          </div>
                        </div>

                        <div className="mt-3">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">
                            Descricao oficial
                          </p>
                          <p className="mt-1 line-clamp-4 text-sm leading-relaxed text-stone-700">
                            {service.description?.trim() || "Sem descricao cadastrada."}
                          </p>
                        </div>

                        <div className="mt-4 flex flex-wrap justify-end gap-2 max-sm:[&>*]:w-full">
                          <Button
                            type="button"
                            variant="outline"
                            className="h-9 px-3 text-xs"
                            onClick={() => openEditServiceDrawer(index)}
                          >
                            Editar servico
                          </Button>
                          <Button
                            type="button"
                            variant="destructive"
                            className="h-9 px-3 text-xs"
                            onClick={() => removeServiceCatalogItem(index)}
                          >
                            Excluir servico
                          </Button>
                        </div>
                      </div>
                    ))}
                </div>
              ) : (
                <div className="rounded-2xl border border-dashed border-stone-300 p-6 text-center">
                  <p className="text-sm font-medium text-stone-700">Ainda nao existe nenhum servico cadastrado.</p>
                  <p className="mt-1 text-xs text-stone-500">
                    Clique em cadastrar servico para abrir o formulario completo.
                  </p>
                  <div className="mt-4">
                    <Button type="button" onClick={openCreateServiceDrawer}>
                      Cadastrar servico
                    </Button>
                  </div>
                </div>
              )}

              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs text-stone-500">
                  Criar, editar e excluir altera o rascunho local. Clique em salvar para publicar o catalogo oficial.
                </p>
                <Button
                  onClick={() => saveServiceCatalogMutation.mutate()}
                  disabled={saveServiceCatalogMutation.isPending}
                >
                  {saveServiceCatalogMutation.isPending
                    ? "Salvando catalogo..."
                    : "Salvar catalogo oficial"}
                </Button>
              </div>
            </CardContent>
          </Card>

          <RightDrawer
            open={serviceDrawerMode !== null}
            onOpenChange={(open) => {
              if (!open) {
                closeServiceDrawer();
              }
            }}
            title={serviceDrawerMode === "edit" ? "Editar servico" : "Cadastrar servico"}
            description="Preencha nome, duracao, preco, status e descricao oficial do servico."
            widthClassName="w-full sm:max-w-2xl xl:max-w-3xl"
          >
            <Card className="border-stone-200">
              <CardContent className="space-y-4 p-4 sm:p-5">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="md:col-span-2">
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                      Nome oficial do servico
                    </label>
                    <Input
                      placeholder="Ex.: Instalacao de lentes"
                      value={serviceForm.name}
                      onChange={(event) =>
                        setServiceForm((current) => ({ ...current, name: event.target.value }))
                      }
                    />
                  </div>

                  <div>
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                      Duracao em minutos
                    </label>
                    <Input
                      type="number"
                      min={5}
                      step={5}
                      value={String(serviceForm.duration_minutes)}
                      onChange={(event) =>
                        setServiceForm((current) => ({
                          ...current,
                          duration_minutes: Number(event.target.value || 0),
                        }))
                      }
                    />
                  </div>

                  <div>
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Status</label>
                    <select
                      className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                      value={serviceForm.is_active ? "active" : "inactive"}
                      onChange={(event) =>
                        setServiceForm((current) => ({
                          ...current,
                          is_active: event.target.value === "active",
                        }))
                      }
                    >
                      <option value="active">Ativo</option>
                      <option value="inactive">Inativo</option>
                    </select>
                  </div>

                  <div className="md:col-span-2">
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                      Faixa de preco
                    </label>
                    <Input
                      placeholder="Ex.: a partir de R$ 650"
                      value={serviceForm.price_note}
                      onChange={(event) =>
                        setServiceForm((current) => ({ ...current, price_note: event.target.value }))
                      }
                    />
                  </div>

                  <div className="md:col-span-2">
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                      Descricao oficial
                    </label>
                    <textarea
                      className={`${TEXTAREA_CLASSNAME} min-h-[148px]`}
                      placeholder="Explique o servico com clareza para a IA orientar pacientes sem inventar detalhes."
                      value={serviceForm.description}
                      onChange={(event) =>
                        setServiceForm((current) => ({ ...current, description: event.target.value }))
                      }
                    />
                  </div>
                </div>

                <div className="flex flex-wrap justify-end gap-2 max-sm:[&>*]:w-full">
                  <Button variant="outline" onClick={closeServiceDrawer}>
                    Cancelar
                  </Button>
                  <Button onClick={handleSaveServiceForm}>
                    {serviceDrawerMode === "edit" ? "Salvar servico" : "Cadastrar servico"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </RightDrawer>
        </div>
      ) : null}

      {activeTab === "Tema e Marca" ? (
        <div className="space-y-4">
          <Card className="border-border">
            <CardHeader>
              <CardTitle>Tema visual da plataforma</CardTitle>
              <p className="text-sm text-muted-foreground">
                Ajuste a identidade visual completa da plataforma: fundo geral, superficies, cards, textos, bordas e
                cores principais da marca.
              </p>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="rounded-[28px] border border-border bg-muted/45 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                      Temas prontos
                    </p>
                    <h3 className="mt-1 text-lg font-bold text-foreground">Aplicar visual completo com 1 clique</h3>
                    <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
                      Cada opção muda cores da marca, fundo, cards, texto, bordas, estilo e tela cheia em uma ação.
                    </p>
                  </div>
                  <span className="rounded-full bg-card px-3 py-1 text-xs font-semibold text-muted-foreground">
                    {BRANDING_PRESETS.length} estilos premium
                  </span>
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {BRANDING_PRESETS.map((preset) => (
                    <div
                      key={preset.id}
                      className="group overflow-hidden rounded-[22px] border border-border bg-card text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-[0_18px_46px_rgba(15,23,42,0.14)]"
                    >
                      <div
                        className="h-24 p-3"
                        style={{
                          backgroundColor: preset.config.background_color,
                          backgroundImage: `radial-gradient(circle at 0% 0%, ${preset.config.primary_color}55, transparent 42%), radial-gradient(circle at 100% 100%, ${preset.config.accent_color}55, transparent 42%)`,
                        }}
                      >
                        <div
                          className="flex h-full items-end rounded-2xl border p-2"
                          style={{
                            borderColor: preset.config.border_color,
                            backgroundColor: `${preset.config.card_color}dd`,
                          }}
                        >
                          <div className="flex w-full items-center gap-1.5">
                            {[
                              preset.config.primary_color,
                              preset.config.secondary_color,
                              preset.config.accent_color,
                              preset.config.fullscreen_accent_color,
                            ].map((color) => (
                              <span
                                key={color}
                                className="h-7 flex-1 rounded-xl border border-white/50 shadow-sm"
                                style={{ backgroundColor: color }}
                              />
                            ))}
                          </div>
                        </div>
                      </div>
                      <div className="space-y-2 p-4">
                        <div className="flex items-center justify-between gap-2">
                          <p className="font-bold text-foreground">{preset.name}</p>
                          <span
                            className="rounded-full px-2 py-1 text-[11px] font-semibold"
                            style={{
                              backgroundColor: `${preset.config.primary_color}18`,
                              color: preset.config.primary_color,
                            }}
                          >
                            {preset.config.surface_style}
                          </span>
                        </div>
                        <p className="text-xs leading-5 text-muted-foreground">{preset.description}</p>
                        <div className="grid gap-2 pt-1 sm:grid-cols-[0.85fr_1.15fr]">
                          <Button
                            type="button"
                            variant="outline"
                            className="h-9 px-3 text-xs"
                            onClick={() => applyBrandingPreset(preset)}
                            disabled={saveBrandingMutation.isPending}
                          >
                            Prévia
                          </Button>
                          <Button
                            type="button"
                            className="h-9 px-3 text-xs"
                            onClick={() => applyAndSaveBrandingPreset(preset)}
                            disabled={saveBrandingMutation.isPending}
                            style={{
                              backgroundColor: preset.config.primary_color,
                              color: preset.config.card_color,
                            }}
                          >
                            {saveBrandingMutation.isPending ? "Salvando..." : "Aplicar e salvar"}
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid gap-5 xl:grid-cols-[1.12fr_0.88fr]">
                <div className="space-y-5">
                  <div className="rounded-2xl border border-border bg-muted/45 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                      Cores da marca
                    </p>
                    <div className="mt-4 grid gap-3 md:grid-cols-3">
                      <div className="space-y-1.5">
                        <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                          Cor primaria
                        </label>
                        <Input
                          type="color"
                          value={brandingDraft.primary_color}
                          onChange={(event) =>
                            setBrandingDraft((current) => ({ ...current, primary_color: event.target.value }))
                          }
                          className="h-12 p-1"
                        />
                        <p className="text-xs text-muted-foreground">{brandingDraft.primary_color}</p>
                      </div>
                      <div className="space-y-1.5">
                        <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                          Cor secundaria
                        </label>
                        <Input
                          type="color"
                          value={brandingDraft.secondary_color}
                          onChange={(event) =>
                            setBrandingDraft((current) => ({ ...current, secondary_color: event.target.value }))
                          }
                          className="h-12 p-1"
                        />
                        <p className="text-xs text-muted-foreground">{brandingDraft.secondary_color}</p>
                      </div>
                      <div className="space-y-1.5">
                        <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                          Cor de destaque
                        </label>
                        <Input
                          type="color"
                          value={brandingDraft.accent_color}
                          onChange={(event) =>
                            setBrandingDraft((current) => ({ ...current, accent_color: event.target.value }))
                          }
                          className="h-12 p-1"
                        />
                        <p className="text-xs text-muted-foreground">{brandingDraft.accent_color}</p>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-border bg-card p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                      Cores da interface
                    </p>
                    <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                      <div className="space-y-1.5">
                        <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                          Fundo da pagina
                        </label>
                        <Input
                          type="color"
                          value={brandingDraft.background_color}
                          onChange={(event) =>
                            setBrandingDraft((current) => ({ ...current, background_color: event.target.value }))
                          }
                          className="h-12 p-1"
                        />
                        <p className="text-xs text-muted-foreground">{brandingDraft.background_color}</p>
                      </div>
                      <div className="space-y-1.5">
                        <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                          Fundo sutil
                        </label>
                        <Input
                          type="color"
                          value={brandingDraft.surface_color}
                          onChange={(event) =>
                            setBrandingDraft((current) => ({ ...current, surface_color: event.target.value }))
                          }
                          className="h-12 p-1"
                        />
                        <p className="text-xs text-muted-foreground">{brandingDraft.surface_color}</p>
                      </div>
                      <div className="space-y-1.5">
                        <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                          Fundo dos cards
                        </label>
                        <Input
                          type="color"
                          value={brandingDraft.card_color}
                          onChange={(event) =>
                            setBrandingDraft((current) => ({ ...current, card_color: event.target.value }))
                          }
                          className="h-12 p-1"
                        />
                        <p className="text-xs text-muted-foreground">{brandingDraft.card_color}</p>
                      </div>
                      <div className="space-y-1.5">
                        <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                          Texto principal
                        </label>
                        <Input
                          type="color"
                          value={brandingDraft.text_color}
                          onChange={(event) =>
                            setBrandingDraft((current) => ({ ...current, text_color: event.target.value }))
                          }
                          className="h-12 p-1"
                        />
                        <p className="text-xs text-muted-foreground">{brandingDraft.text_color}</p>
                      </div>
                      <div className="space-y-1.5">
                        <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                          Texto secundario
                        </label>
                        <Input
                          type="color"
                          value={brandingDraft.muted_text_color}
                          onChange={(event) =>
                            setBrandingDraft((current) => ({ ...current, muted_text_color: event.target.value }))
                          }
                          className="h-12 p-1"
                        />
                        <p className="text-xs text-muted-foreground">{brandingDraft.muted_text_color}</p>
                      </div>
                      <div className="space-y-1.5">
                        <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                          Borda geral
                        </label>
                        <Input
                          type="color"
                          value={brandingDraft.border_color}
                          onChange={(event) =>
                            setBrandingDraft((current) => ({ ...current, border_color: event.target.value }))
                          }
                          className="h-12 p-1"
                        />
                        <p className="text-xs text-muted-foreground">{brandingDraft.border_color}</p>
                      </div>
                    </div>
                  </div>

                  <div className="grid gap-3 md:grid-cols-[1fr_220px]">
                    <div className="rounded-2xl border border-border bg-card p-4">
                      <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        Estilo de superficie
                      </label>
                      <select
                        className="mt-2 h-11 w-full rounded-md border border-border bg-card px-3 text-sm text-foreground"
                        value={brandingDraft.surface_style}
                        onChange={(event) =>
                          setBrandingDraft((current) => ({
                            ...current,
                            surface_style:
                              event.target.value === "flat" || event.target.value === "glass"
                                ? event.target.value
                                : "soft",
                          }))
                        }
                      >
                        <option value="soft">Suave</option>
                        <option value="flat">Flat</option>
                        <option value="glass">Glass</option>
                      </select>
                      <p className="mt-2 text-xs text-muted-foreground">
                        Controla a atmosfera do fundo geral da aplicacao sem mexer nas cores escolhidas.
                      </p>
                    </div>

                    <div className="rounded-2xl border border-border bg-card p-4 md:col-span-2">
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                        Modo tela cheia
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        Cores usadas pelos usuários que trabalham somente em tela cheia.
                      </p>
                      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                        <div className="space-y-1.5">
                          <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                            Fundo tela cheia
                          </label>
                          <Input
                            type="color"
                            value={brandingDraft.fullscreen_background_color}
                            onChange={(event) =>
                              setBrandingDraft((current) => ({
                                ...current,
                                fullscreen_background_color: event.target.value,
                              }))
                            }
                            className="h-12 p-1"
                          />
                          <p className="text-xs text-muted-foreground">{brandingDraft.fullscreen_background_color}</p>
                        </div>
                        <div className="space-y-1.5">
                          <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                            Barra superior
                          </label>
                          <Input
                            type="color"
                            value={brandingDraft.fullscreen_header_color}
                            onChange={(event) =>
                              setBrandingDraft((current) => ({
                                ...current,
                                fullscreen_header_color: event.target.value,
                              }))
                            }
                            className="h-12 p-1"
                          />
                          <p className="text-xs text-muted-foreground">{brandingDraft.fullscreen_header_color}</p>
                        </div>
                        <div className="space-y-1.5">
                          <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                            Destaque tela cheia
                          </label>
                          <Input
                            type="color"
                            value={brandingDraft.fullscreen_accent_color}
                            onChange={(event) =>
                              setBrandingDraft((current) => ({
                                ...current,
                                fullscreen_accent_color: event.target.value,
                              }))
                            }
                            className="h-12 p-1"
                          />
                          <p className="text-xs text-muted-foreground">{brandingDraft.fullscreen_accent_color}</p>
                        </div>
                        <div className="space-y-1.5">
                          <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                            Texto tela cheia
                          </label>
                          <Input
                            type="color"
                            value={brandingDraft.fullscreen_foreground_color}
                            onChange={(event) =>
                              setBrandingDraft((current) => ({
                                ...current,
                                fullscreen_foreground_color: event.target.value,
                              }))
                            }
                            className="h-12 p-1"
                          />
                          <p className="text-xs text-muted-foreground">{brandingDraft.fullscreen_foreground_color}</p>
                        </div>
                      </div>
                    </div>

                    <div className="rounded-2xl border border-border bg-muted/45 p-4">
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                        Acoes rapidas
                      </p>
                      <div className="mt-3 flex flex-col gap-2">
                        <Button variant="outline" onClick={restoreBrandingColors}>
                          Restaurar cores
                        </Button>
                        <Button onClick={() => saveBrandingMutation.mutate(brandingDraft)} disabled={saveBrandingMutation.isPending}>
                          {saveBrandingMutation.isPending ? "Salvando..." : "Salvar tema"}
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="space-y-4">
                  <div
                    className="overflow-hidden rounded-[28px] border p-4 shadow-[0_25px_65px_rgba(15,23,42,0.12)]"
                    style={{
                      borderColor: brandingDraft.border_color,
                      backgroundColor: brandingDraft.background_color,
                      color: brandingDraft.text_color,
                      backgroundImage: `radial-gradient(circle at 0% 0%, ${brandingDraft.primary_color}22, transparent 45%), radial-gradient(circle at 100% 100%, ${brandingDraft.accent_color}20, transparent 38%)`,
                    }}
                  >
                    <div
                      className="rounded-[22px] border p-3 backdrop-blur"
                      style={{
                        borderColor: brandingDraft.border_color,
                        backgroundColor: `${brandingDraft.card_color}e8`,
                      }}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2">
                          <div
                            className="h-10 w-10 rounded-xl"
                            style={{
                              background: `linear-gradient(135deg, ${brandingDraft.primary_color}, ${brandingDraft.secondary_color})`,
                            }}
                          />
                          <div>
                            <p className="text-[11px] font-semibold uppercase tracking-[0.16em]" style={{ color: brandingDraft.muted_text_color }}>
                              Clinica ativa
                            </p>
                            <p className="text-sm font-bold" style={{ color: brandingDraft.text_color }}>
                              Sorriso Sul
                            </p>
                          </div>
                        </div>
                        <div
                          className="rounded-full border px-3 py-1 text-xs font-semibold"
                          style={{
                            borderColor: brandingDraft.border_color,
                            color: brandingDraft.muted_text_color,
                            backgroundColor: `${brandingDraft.surface_color}cc`,
                          }}
                        >
                          Unidade Centro
                        </div>
                      </div>

                      <div className="mt-4 grid gap-3 md:grid-cols-[120px_1fr]">
                        <div
                          className="rounded-[20px] border p-3"
                          style={{
                            borderColor: brandingDraft.border_color,
                            backgroundColor: `${brandingDraft.card_color}f2`,
                          }}
                        >
                          <div
                            className="rounded-xl px-3 py-2 text-xs font-semibold text-white"
                            style={{ backgroundColor: brandingDraft.primary_color }}
                          >
                            WhatsApp
                          </div>
                          <div
                            className="mt-2 rounded-xl px-3 py-2 text-xs font-medium"
                            style={{
                              backgroundColor: `${brandingDraft.surface_color}d9`,
                              color: brandingDraft.muted_text_color,
                            }}
                          >
                            Agenda
                          </div>
                          <div
                            className="mt-2 rounded-xl px-3 py-2 text-xs font-medium"
                            style={{
                              backgroundColor: `${brandingDraft.surface_color}d9`,
                              color: brandingDraft.muted_text_color,
                            }}
                          >
                            Leads
                          </div>
                        </div>

                        <div className="space-y-3">
                          <div
                            className="rounded-[20px] border p-4"
                            style={{
                              borderColor: brandingDraft.border_color,
                              backgroundColor: brandingDraft.card_color,
                            }}
                          >
                            <p className="text-xs font-semibold uppercase tracking-[0.18em]" style={{ color: brandingDraft.muted_text_color }}>
                              Preview da interface
                            </p>
                            <h3 className="mt-2 text-xl font-bold" style={{ color: brandingDraft.text_color }}>
                              Tema e Marca
                            </h3>
                            <p className="mt-1 text-sm" style={{ color: brandingDraft.muted_text_color }}>
                              Veja como fundo, cards, bordas e textos ficam com a nova identidade.
                            </p>
                            <div className="mt-4 flex flex-wrap gap-2">
                              <span
                                className="inline-flex rounded-full px-3 py-1 text-xs font-semibold text-white"
                                style={{ backgroundColor: brandingDraft.primary_color }}
                              >
                                Botao principal
                              </span>
                              <span
                                className="inline-flex rounded-full border px-3 py-1 text-xs font-semibold"
                                style={{
                                  borderColor: brandingDraft.secondary_color,
                                  color: brandingDraft.secondary_color,
                                  backgroundColor: brandingDraft.card_color,
                                }}
                              >
                                Destaque secundario
                              </span>
                              <span
                                className="inline-flex rounded-full px-3 py-1 text-xs font-semibold text-white"
                                style={{ backgroundColor: brandingDraft.accent_color }}
                              >
                                CTA / alerta
                              </span>
                            </div>
                          </div>

                          <div className="grid gap-3 sm:grid-cols-2">
                            <div
                              className="rounded-[18px] border p-3"
                              style={{
                                borderColor: brandingDraft.border_color,
                                backgroundColor: `${brandingDraft.surface_color}e6`,
                              }}
                            >
                              <p className="text-xs font-semibold uppercase tracking-[0.16em]" style={{ color: brandingDraft.muted_text_color }}>
                                Fundo sutil
                              </p>
                              <p className="mt-2 text-sm font-semibold" style={{ color: brandingDraft.text_color }}>
                                Blocos auxiliares
                              </p>
                            </div>
                            <div
                              className="rounded-[18px] border p-3"
                              style={{
                                borderColor: brandingDraft.border_color,
                                backgroundColor: brandingDraft.card_color,
                              }}
                            >
                              <p className="text-xs font-semibold uppercase tracking-[0.16em]" style={{ color: brandingDraft.muted_text_color }}>
                                Card
                              </p>
                              <p className="mt-2 text-sm font-semibold" style={{ color: brandingDraft.text_color }}>
                                Conteudo principal
                              </p>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div
                    className="overflow-hidden rounded-2xl border p-3 shadow-[0_18px_50px_rgba(15,23,42,0.16)]"
                    style={{
                      borderColor: `${brandingDraft.fullscreen_accent_color}55`,
                      backgroundColor: brandingDraft.fullscreen_background_color,
                      color: brandingDraft.fullscreen_foreground_color,
                      backgroundImage: `radial-gradient(circle at top, ${brandingDraft.fullscreen_accent_color}33, transparent 45%)`,
                    }}
                  >
                    <div
                      className="flex items-center justify-between rounded-xl border px-3 py-2"
                      style={{
                        borderColor: `${brandingDraft.fullscreen_foreground_color}22`,
                        backgroundColor: `${brandingDraft.fullscreen_header_color}ee`,
                      }}
                    >
                      <div>
                        <p className="text-xs font-semibold">Modo tela cheia</p>
                        <p className="text-[11px] opacity-70">Preview do topo operacional</p>
                      </div>
                      <div className="flex gap-1.5">
                        {["WhatsApp", "Agenda", "Menu"].map((label, index) => (
                          <span
                            key={label}
                            className="rounded-full border px-2 py-1 text-[11px] font-semibold"
                            style={{
                              borderColor:
                                index === 0
                                  ? `${brandingDraft.fullscreen_accent_color}cc`
                                  : `${brandingDraft.fullscreen_foreground_color}22`,
                              backgroundColor:
                                index === 0
                                  ? `${brandingDraft.fullscreen_accent_color}30`
                                  : `${brandingDraft.fullscreen_foreground_color}0f`,
                              color: brandingDraft.fullscreen_foreground_color,
                            }}
                          >
                            {label}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-border bg-muted/45 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                      O que muda com este tema
                    </p>
                    <div className="mt-3 grid gap-2 text-sm text-muted-foreground">
                      <p>O fundo geral da aplicacao segue a cor de pagina escolhida.</p>
                      <p>Cards, menus, topo e tabelas passam a usar as novas superficies.</p>
                      <p>Textos principais e secundarios acompanham as cores definidas aqui.</p>
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border">
            <CardHeader>
              <CardTitle>Logo da clinica</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Envie a logo para aparecer no menu lateral e no topo da plataforma.
              </p>
              <div className="flex flex-wrap items-center gap-3">
                <Input type="file" accept="image/*" onChange={onBrandingLogoUpload} className="max-w-sm" />
                <Button
                  variant="outline"
                  onClick={() => {
                    setBrandingLogoPreview(null);
                    setBrandingDraft((current) => ({ ...current, logo_data_url: null }));
                  }}
                >
                  Limpar logo
                </Button>
              </div>
              {brandingLogoPreview ? (
                <div className="rounded-lg border border-border bg-muted/45 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Preview da logo</p>
                  <Image
                    src={brandingLogoPreview}
                    alt="Preview da logo"
                    width={64}
                    height={64}
                    unoptimized
                    className="mt-2 h-16 w-16 rounded-md border border-border object-cover"
                  />
                </div>
              ) : null}
              <div className="flex flex-wrap justify-end gap-2">
                <Button variant="outline" onClick={restoreBrandingColors}>
                  Restaurar cores
                </Button>
                <Button onClick={() => saveBrandingMutation.mutate(brandingDraft)} disabled={saveBrandingMutation.isPending}>
                  {saveBrandingMutation.isPending ? "Salvando tema..." : "Salvar tema e marca"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      ) : null}

      {activeTab === "Unidades" ? (
        <div className="space-y-4">
          <Card className="border-stone-200 bg-white/95">
            <CardHeader>
              <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <CardTitle>Unidades da clínica</CardTitle>
                  <p className="mt-1 text-sm text-stone-600">
                    Cadastre endereço completo, contatos, horários e orientações que a IA usa para informar pacientes com segurança.
                  </p>
                </div>
                <Button type="button" onClick={openCreateUnitDrawer}>
                  Cadastrar unidade
                </Button>
              </div>
            </CardHeader>
          </Card>

          <DataTable<UnitSettingsItem>
            title="Unidades da clínica"
            rows={unitsQuery.data?.data ?? []}
            getRowId={(item) => item.id}
            searchBy={(item) =>
              `${item.name} ${item.code} ${item.email ?? ""} ${formatUnitAddress(item)} ${(item.services ?? []).join(" ")}`
            }
            columns={[
              { key: "nome", label: "Unidade", render: (item) => item.name },
              { key: "codigo", label: "Código", render: (item) => item.code },
              {
                key: "endereco",
                label: "Endereço",
                render: (item) => formatUnitAddress(item) || <span className="text-xs text-stone-400">Não informado</span>,
              },
              { key: "telefone", label: "Telefone", render: (item) => item.phone || "-" },
              { key: "email", label: "E-mail", render: (item) => item.email || "-" },
              {
                key: "servicos",
                label: "Serviços",
                render: (item) =>
                  (item.services ?? []).length ? (
                    <span className="text-xs text-stone-700">{(item.services ?? []).join(", ")}</span>
                  ) : (
                    <span className="text-xs text-stone-400">Não definidos</span>
                  ),
              },
              {
                key: "status",
                label: "Status",
                render: (item) => <StatusBadge value={item.is_active === false ? "inativo" : "ativo"} />,
              },
              {
                key: "acoes",
                label: "Ações",
                render: (item) => (
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      className="h-8 px-2 text-xs"
                      onClick={() => startEditingUnit(item)}
                    >
                      Editar
                    </Button>
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
                    <Button
                      variant="outline"
                      className="h-8 px-2 text-xs text-red-700"
                      onClick={() => {
                        if (!window.confirm(`Deseja excluir a unidade ${item.name}?`)) return;
                        deleteUnitMutation.mutate(item.id);
                      }}
                    >
                      Excluir
                    </Button>
                  </div>
                ),
              },
            ]}
            emptyTitle="Nenhuma unidade cadastrada"
            emptyDescription="Cadastre unidades para operar múltiplas agendas, equipes e serviços por clínica."
          />

          <RightDrawer
            open={unitDrawerMode !== null}
            onOpenChange={(open) => {
              if (!open) resetUnitForm();
            }}
            title={unitDrawerMode === "edit" ? "Editar unidade" : "Cadastrar unidade"}
            description="Preencha dados completos para agenda, equipe e IA responderem pacientes sem inventar informações."
            widthClassName="w-full sm:max-w-3xl xl:max-w-5xl"
          >
            <Card className="border-stone-200">
              <CardContent className="space-y-5 p-4 sm:p-5">
                <div className="rounded-2xl border border-primary/15 bg-primary/5 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
                    Fonte da verdade para a IA
                  </p>
                  <p className="mt-1 text-sm text-stone-700">
                    Endereço, horários, referência e orientações salvos aqui entram no contexto usado pela IA quando o paciente pergunta onde fica a clínica ou como chegar.
                  </p>
                </div>

                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Nome da unidade</label>
                    <Input
                      placeholder="Ex.: Unidade Paulista"
                      value={unitForm.name}
                      onChange={(event) => setUnitForm((current) => ({ ...current, name: event.target.value }))}
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Código</label>
                    <Input
                      placeholder="Ex.: SP-PAULISTA"
                      value={unitForm.code}
                      onChange={(event) => setUnitForm((current) => ({ ...current, code: event.target.value.toUpperCase() }))}
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Telefone</label>
                    <Input
                      placeholder="Ex.: +55 11 3333-0002"
                      value={unitForm.phone}
                      onChange={(event) => setUnitForm((current) => ({ ...current, phone: event.target.value }))}
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">E-mail</label>
                    <Input
                      placeholder="Ex.: paulista@clinica.com"
                      value={unitForm.email}
                      onChange={(event) => setUnitForm((current) => ({ ...current, email: event.target.value }))}
                    />
                  </div>
                </div>

                <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Endereço completo</p>
                  <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-6">
                    <div className="space-y-1 xl:col-span-3">
                      <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Rua / avenida</label>
                      <Input
                        placeholder="Ex.: Avenida Paulista"
                        value={unitForm.address_line}
                        onChange={(event) => setUnitForm((current) => ({ ...current, address_line: event.target.value }))}
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Número</label>
                      <Input
                        placeholder="Ex.: 1000"
                        value={unitForm.address_number}
                        onChange={(event) => setUnitForm((current) => ({ ...current, address_number: event.target.value }))}
                      />
                    </div>
                    <div className="space-y-1 xl:col-span-2">
                      <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Complemento</label>
                      <Input
                        placeholder="Ex.: Sala 1204, 12º andar"
                        value={unitForm.complement}
                        onChange={(event) => setUnitForm((current) => ({ ...current, complement: event.target.value }))}
                      />
                    </div>
                    <div className="space-y-1 xl:col-span-2">
                      <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Bairro</label>
                      <Input
                        placeholder="Ex.: Bela Vista"
                        value={unitForm.neighborhood}
                        onChange={(event) => setUnitForm((current) => ({ ...current, neighborhood: event.target.value }))}
                      />
                    </div>
                    <div className="space-y-1 xl:col-span-2">
                      <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Cidade</label>
                      <Input
                        placeholder="Ex.: São Paulo"
                        value={unitForm.city}
                        onChange={(event) => setUnitForm((current) => ({ ...current, city: event.target.value }))}
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Estado</label>
                      <Input
                        placeholder="Ex.: SP"
                        value={unitForm.state}
                        onChange={(event) => setUnitForm((current) => ({ ...current, state: event.target.value.toUpperCase() }))}
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">CEP</label>
                      <Input
                        placeholder="Ex.: 01310-100"
                        value={unitForm.zip_code}
                        onChange={(event) => setUnitForm((current) => ({ ...current, zip_code: event.target.value }))}
                      />
                    </div>
                  </div>
                </div>

                <div className="grid gap-4 lg:grid-cols-2">
                  <div className="rounded-2xl border border-stone-200 bg-white p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Orientações para o paciente</p>
                    <div className="mt-4 space-y-3">
                      <div className="space-y-1">
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Ponto de referência</label>
                        <Input
                          placeholder="Ex.: Ao lado do metrô, próximo ao shopping"
                          value={unitForm.reference_point}
                          onChange={(event) => setUnitForm((current) => ({ ...current, reference_point: event.target.value }))}
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Como chegar / acesso</label>
                        <textarea
                          className={`${TEXTAREA_CLASSNAME} min-h-[92px]`}
                          placeholder="Ex.: Entrada pela recepção do prédio, apresentar documento na portaria."
                          value={unitForm.access_instructions}
                          onChange={(event) => setUnitForm((current) => ({ ...current, access_instructions: event.target.value }))}
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Estacionamento / transporte</label>
                        <textarea
                          className={`${TEXTAREA_CLASSNAME} min-h-[78px]`}
                          placeholder="Ex.: Estacionamento conveniado na rua lateral. Próximo à estação Consolação."
                          value={unitForm.parking_info}
                          onChange={(event) => setUnitForm((current) => ({ ...current, parking_info: event.target.value }))}
                        />
                      </div>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-stone-200 bg-white p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Horário da unidade</p>
                    <div className="mt-4 grid gap-3 sm:grid-cols-2">
                      <div className="space-y-1 sm:col-span-2">
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Dias de atendimento</label>
                        <Input
                          placeholder="Ex.: Segunda a sexta"
                          value={unitForm.working_days_text}
                          onChange={(event) => setUnitForm((current) => ({ ...current, working_days_text: event.target.value }))}
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Abre</label>
                        <Input
                          type="time"
                          value={unitForm.working_hours_start}
                          onChange={(event) => setUnitForm((current) => ({ ...current, working_hours_start: event.target.value }))}
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Fecha</label>
                        <Input
                          type="time"
                          value={unitForm.working_hours_end}
                          onChange={(event) => setUnitForm((current) => ({ ...current, working_hours_end: event.target.value }))}
                        />
                      </div>
                      <div className="space-y-1 sm:col-span-2">
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Observações de horário</label>
                        <textarea
                          className={`${TEXTAREA_CLASSNAME} min-h-[92px]`}
                          placeholder="Ex.: Sábado com atendimento mediante agendamento. Feriados sem expediente."
                          value={unitForm.working_hours_notes}
                          onChange={(event) => setUnitForm((current) => ({ ...current, working_hours_notes: event.target.value }))}
                        />
                      </div>
                    </div>
                  </div>
                </div>

                <div className="rounded-lg border border-stone-200 bg-stone-50 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Serviços da unidade</p>
                      <p className="text-xs text-stone-500">
                        Selecione os serviços já cadastrados ou adicione novos para esta unidade.
                      </p>
                    </div>
                    <span className="rounded-full bg-white px-2 py-1 text-[11px] font-medium text-stone-600">
                      {unitForm.services.length} serviço(s)
                    </span>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2">
                    {unitServiceCatalog.length ? (
                      unitServiceCatalog.map((serviceName) => {
                        const selected = unitForm.services.includes(serviceName);
                        return (
                          <button
                            key={serviceName}
                            type="button"
                            className={[
                              "rounded-full border px-3 py-1.5 text-xs transition",
                              selected
                                ? "border-teal-500 bg-teal-50 text-teal-800"
                                : "border-stone-300 bg-white text-stone-700 hover:border-stone-400",
                            ].join(" ")}
                            onClick={() => toggleUnitService(serviceName)}
                          >
                            {serviceName}
                          </button>
                        );
                      })
                    ) : (
                      <p className="text-xs text-stone-500">
                        Ainda não há serviços cadastrados. Você pode criar o primeiro logo abaixo.
                      </p>
                    )}
                  </div>

                  <div className="mt-4 grid gap-2 md:grid-cols-[minmax(0,1fr)_170px]">
                    <Input
                      placeholder="Novo serviço para esta unidade"
                      value={newUnitServiceName}
                      onChange={(event) => setNewUnitServiceName(event.target.value)}
                    />
                    <Button variant="outline" onClick={addCustomServiceToUnitForm}>
                      Adicionar serviço
                    </Button>
                  </div>
                </div>

                <div className="flex flex-wrap justify-end gap-2 max-sm:[&>*]:w-full">
                  <Button variant="outline" onClick={resetUnitForm}>
                    Cancelar
                  </Button>
                  <Button
                    onClick={handleSubmitUnitForm}
                    disabled={createUnitMutation.isPending || updateUnitMutation.isPending}
                  >
                    {createUnitMutation.isPending || updateUnitMutation.isPending
                      ? "Salvando..."
                      : editingUnitId
                        ? "Salvar alterações"
                        : "Criar unidade"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </RightDrawer>
        </div>
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
              {whatsappHealth ? (
                <div className={`rounded-md border p-3 text-sm ${whatsappHealthTone}`}>
                  <p className="font-semibold">
                    {whatsappHealthIsOk ? "WhatsApp pronto para produção" : "Atenção: WhatsApp pode não entregar mensagens"}
                  </p>
                  <p className="mt-1 text-xs">{whatsappHealth.message}</p>
                  {whatsappHealth.issues.length ? (
                    <p className="mt-1 text-xs">Pendências: {whatsappHealth.issues.join("; ")}</p>
                  ) : null}
                  {whatsappHealth.recent_failure ? (
                    <p className="mt-1 text-xs">
                      Última falha: {whatsappHealth.recent_failure.last_error || whatsappHealth.recent_failure.status}
                      {whatsappHealth.recent_failure.is_credit_issue ? " (provável falta de créditos no provedor)" : ""}
                    </p>
                  ) : null}
                </div>
              ) : null}
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

              <div className="grid gap-3 md:grid-cols-3">
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
                <div>
                  <label className="flex items-center gap-2 text-sm text-stone-700">
                    <input
                      type="checkbox"
                      checked={aiConfigDraft.interactive_booking_options_enabled}
                      onChange={(event) =>
                        setAiConfigDraft((current) => ({
                          ...current,
                          interactive_booking_options_enabled: event.target.checked,
                        }))
                      }
                    />
                    Usar listas e botões no agendamento
                  </label>
                  <p className="mt-1 text-xs text-stone-500">
                    Quando ligado, a IA envia clínica, serviço, data, horário e confirmação em botões/listas. Quando desligado,
                    envia tudo em texto e o paciente pode responder digitando ou por áudio.
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
              <CardTitle>Ações rápidas</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" onClick={applySorrisoSulKnowledgePreset}>
                Preencher Sorriso Sul
              </Button>
              <Button type="button" variant="outline" onClick={clearKnowledgeBaseDraft}>
                Limpar tudo
              </Button>
            </CardContent>
          </Card>

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
                  placeholder="Ex.: Clinica premium com atendimento consultivo, acolhedor e foco em experiencia do paciente."
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
              <div className="space-y-1">
                <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                  Exemplo de saudação / boas-vindas da IA
                </label>
                <textarea
                  className="min-h-[96px] w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                  placeholder="Ex.: Oi! Que bom te ver por aqui. Sou a assistente virtual da clínica..."
                  value={aiKnowledgeDraft.clinic_profile.welcome_greeting_example}
                  onChange={(event) =>
                    setAiKnowledgeDraft((current) => ({
                      ...current,
                      clinic_profile: {
                        ...current.clinic_profile,
                        welcome_greeting_example: event.target.value,
                      },
                    }))
                  }
                />
                <p className="text-xs text-stone-500">
                  Essa mensagem será usada no início da conversa, junto com o menu de opções por botões.
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
              <CardTitle>Servicos oficiais usados pela IA</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="rounded-md border border-stone-200 bg-stone-50 p-3">
                <p className="text-sm font-semibold text-stone-800">
                  Os servicos nao sao mais configurados aqui
                </p>
                <p className="mt-1 text-xs text-stone-600">
                  O cadastro oficial agora fica na aba <strong>Servicos</strong>. A IA recebe automaticamente o
                  nome, a descricao, o preco e a duracao de cada servico a partir desse catalogo unico, o que evita
                  divergencia entre agenda, profissionais, unidades e atendimento.
                </p>
              </div>
              <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">
                  Como a IA usa esse catalogo
                </p>
                <p className="mt-1 text-xs text-emerald-700">
                  Sempre que um paciente perguntar sobre um procedimento, a IA passa a usar os dados oficiais do
                  servico salvo em <strong>Serviços</strong>, incluindo tempo, faixa de valor e
                  descricao aprovada pela clinica.
                </p>
              </div>
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
        <div className="space-y-4">
          <Card className="border-stone-200">
            <CardHeader>
              <CardTitle>Segurança da operação</CardTitle>
              <p className="text-sm text-stone-600">
                Defina políticas mínimas de sessão, autenticação e proteção para reduzir risco operacional.
              </p>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.7fr)_320px]">
                <div className="space-y-4">
                  <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">
                      Sessão e autenticação
                    </p>
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      <div>
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                          Timeout da sessão
                        </label>
                        <Input
                          type="number"
                          min="5"
                          value={String(securityConfigDraft.session_timeout_minutes)}
                          onChange={(event) =>
                            setSecurityConfigDraft((current) => ({
                              ...current,
                              session_timeout_minutes: Number(event.target.value || 0),
                            }))
                          }
                        />
                        <p className="mt-1 text-xs text-stone-500">
                          Encerra a sessão automaticamente após esse período.
                        </p>
                      </div>
                      <div>
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                          Bloqueio por inatividade
                        </label>
                        <Input
                          type="number"
                          min="1"
                          value={String(securityConfigDraft.idle_lock_minutes)}
                          onChange={(event) =>
                            setSecurityConfigDraft((current) => ({
                              ...current,
                              idle_lock_minutes: Number(event.target.value || 0),
                            }))
                          }
                        />
                        <p className="mt-1 text-xs text-stone-500">
                          Pede novo acesso quando o operador fica parado.
                        </p>
                      </div>
                    </div>

                    <div className="mt-4 grid gap-2 md:grid-cols-2">
                      <label className="flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-3 py-2.5 text-sm text-stone-700">
                        <input
                          type="checkbox"
                          checked={securityConfigDraft.require_mfa}
                          onChange={(event) =>
                            setSecurityConfigDraft((current) => ({
                              ...current,
                              require_mfa: event.target.checked,
                            }))
                          }
                        />
                        Exigir MFA para perfis críticos
                      </label>
                      <label className="flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-3 py-2.5 text-sm text-stone-700">
                        <input
                          type="checkbox"
                          checked={securityConfigDraft.enforce_single_session}
                          onChange={(event) =>
                            setSecurityConfigDraft((current) => ({
                              ...current,
                              enforce_single_session: event.target.checked,
                            }))
                          }
                        />
                        Permitir apenas uma sessão por usuário
                      </label>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-stone-200 bg-white p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">
                      Governança e restrições
                    </p>
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      <div>
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                          Troca de senha a cada
                        </label>
                        <Input
                          type="number"
                          min="0"
                          value={String(securityConfigDraft.password_rotation_days)}
                          onChange={(event) =>
                            setSecurityConfigDraft((current) => ({
                              ...current,
                              password_rotation_days: Number(event.target.value || 0),
                            }))
                          }
                        />
                        <p className="mt-1 text-xs text-stone-500">
                          Use `0` se quiser apenas registrar a política sem forçar prazo.
                        </p>
                      </div>
                      <div>
                        <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                          Retenção dos logs de auditoria
                        </label>
                        <Input
                          type="number"
                          min="30"
                          value={String(securityConfigDraft.audit_log_retention_days)}
                          onChange={(event) =>
                            setSecurityConfigDraft((current) => ({
                              ...current,
                              audit_log_retention_days: Number(event.target.value || 0),
                            }))
                          }
                        />
                        <p className="mt-1 text-xs text-stone-500">
                          Quantos dias os registros operacionais devem permanecer disponíveis.
                        </p>
                      </div>
                    </div>

                    <div className="mt-4 space-y-1">
                      <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                        IPs ou faixas permitidas
                      </label>
                      <textarea
                        className={`${TEXTAREA_CLASSNAME} min-h-[96px]`}
                        placeholder="Opcional. Ex.: 200.10.10.1, 10.0.0.0/24"
                        value={securityConfigDraft.allowed_ip_ranges}
                        onChange={(event) =>
                          setSecurityConfigDraft((current) => ({
                            ...current,
                            allowed_ip_ranges: event.target.value,
                          }))
                        }
                      />
                    </div>

                    <div className="mt-4 grid gap-2 md:grid-cols-2">
                      <label className="flex items-center gap-2 rounded-xl border border-stone-200 bg-stone-50 px-3 py-2.5 text-sm text-stone-700">
                        <input
                          type="checkbox"
                          checked={securityConfigDraft.restrict_sensitive_exports}
                          onChange={(event) =>
                            setSecurityConfigDraft((current) => ({
                              ...current,
                              restrict_sensitive_exports: event.target.checked,
                            }))
                          }
                        />
                        Restringir exportações sensíveis
                      </label>
                      <label className="flex items-center gap-2 rounded-xl border border-stone-200 bg-stone-50 px-3 py-2.5 text-sm text-stone-700">
                        <input
                          type="checkbox"
                          checked={securityConfigDraft.notify_new_device_login}
                          onChange={(event) =>
                            setSecurityConfigDraft((current) => ({
                              ...current,
                              notify_new_device_login: event.target.checked,
                            }))
                          }
                        />
                        Notificar logins em novo dispositivo
                      </label>
                    </div>
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="rounded-2xl border border-primary/15 bg-primary/5 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
                      Resumo da política
                    </p>
                    <div className="mt-4 space-y-3 text-sm text-stone-700">
                      <p>Sessão expira em {securityConfigDraft.session_timeout_minutes} minuto(s).</p>
                      <p>Bloqueio por inatividade em {securityConfigDraft.idle_lock_minutes} minuto(s).</p>
                      <p>{securityConfigDraft.require_mfa ? "MFA obrigatório" : "MFA opcional"} para perfis críticos.</p>
                      <p>
                        {securityConfigDraft.restrict_sensitive_exports
                          ? "Exportações sensíveis restritas."
                          : "Exportações sensíveis liberadas."}
                      </p>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">
                      Boas práticas
                    </p>
                    <ul className="mt-3 space-y-2 text-sm text-stone-700">
                      <li>Use timeout curto para computadores compartilhados na recepção.</li>
                      <li>Ative MFA para usuários administrativos e perfis com acesso financeiro.</li>
                      <li>Mantenha logs por tempo suficiente para auditoria de incidentes.</li>
                    </ul>
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap justify-end gap-2">
                <Button variant="outline" onClick={restoreSecurityConfigDraft}>
                  Recarregar política
                </Button>
                <Button onClick={handleSaveSecurityConfig} disabled={saveSecurityConfigMutation.isPending}>
                  {saveSecurityConfigMutation.isPending ? "Salvando..." : "Salvar segurança"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      ) : null}

      {activeTab === "Dados e Privacidade" ? (
        <div className="space-y-4">
          <Card className="border-stone-200">
            <CardHeader>
              <CardTitle>Dados e privacidade</CardTitle>
              <p className="text-sm text-stone-600">
                Organize retenção, permissões de comunicação, contato LGPD e rotinas de exportação e anonimização.
              </p>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">
                    Consentimento
                  </p>
                  <p className="mt-2 text-2xl font-bold text-stone-900">{consentRateLabel}</p>
                  <p className="text-xs text-stone-600">Taxa de pacientes com consentimento registrado.</p>
                </div>
                <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Retenção</p>
                  <p className="mt-2 text-2xl font-bold text-stone-900">{privacyConfigDraft.retention_days} dias</p>
                  <p className="text-xs text-stone-600">Prazo padrão configurado para retenção de dados.</p>
                </div>
                <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Aceite LGPD</p>
                  <p className="mt-2 text-sm font-semibold text-stone-900">{privacyAcceptedAtLabel}</p>
                  <p className="mt-1 text-xs text-stone-600">
                    Termos {privacySummary?.terms_version ?? privacyConfigDraft.terms_version} • Política{" "}
                    {privacySummary?.policy_version ?? privacyConfigDraft.policy_version}
                  </p>
                </div>
              </div>

              <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">
                  Consentimento e retenção
                </p>
                <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                  <div>
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                      Retenção padrão
                    </label>
                    <Input
                      type="number"
                      min="1"
                      value={String(privacyConfigDraft.retention_days)}
                      onChange={(event) =>
                        setPrivacyConfigDraft((current) => ({
                          ...current,
                          retention_days: Number(event.target.value || 0),
                        }))
                      }
                    />
                  </div>
                  <div>
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                      Anonimizar leads após
                    </label>
                    <Input
                      type="number"
                      min="1"
                      value={String(privacyConfigDraft.anonymize_leads_after_days)}
                      onChange={(event) =>
                        setPrivacyConfigDraft((current) => ({
                          ...current,
                          anonymize_leads_after_days: Number(event.target.value || 0),
                        }))
                      }
                    />
                  </div>
                  <div className="md:col-span-2 xl:col-span-2 flex flex-wrap gap-2">
                    <label className="flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-3 py-2.5 text-sm text-stone-700">
                      <input
                        type="checkbox"
                        checked={privacyConfigDraft.allow_marketing}
                        onChange={(event) =>
                          setPrivacyConfigDraft((current) => ({
                            ...current,
                            allow_marketing: event.target.checked,
                          }))
                        }
                      />
                      Permitir comunicação de marketing
                    </label>
                    <label className="flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-3 py-2.5 text-sm text-stone-700">
                      <input
                        type="checkbox"
                        checked={privacyConfigDraft.allow_operational}
                        onChange={(event) =>
                          setPrivacyConfigDraft((current) => ({
                            ...current,
                            allow_operational: event.target.checked,
                          }))
                        }
                      />
                      Permitir comunicação operacional
                    </label>
                  </div>
                </div>

                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                      Texto de consentimento
                    </label>
                    <textarea
                      className={TEXTAREA_CLASSNAME}
                      placeholder="Explique como a clínica solicita e registra consentimento."
                      value={privacyConfigDraft.consent_text}
                      onChange={(event) =>
                        setPrivacyConfigDraft((current) => ({
                          ...current,
                          consent_text: event.target.value,
                        }))
                      }
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                      Compartilhamento e governança
                    </label>
                    <textarea
                      className={TEXTAREA_CLASSNAME}
                      placeholder="Descreva parceiros, armazenamento, descarte ou outras observações de privacidade."
                      value={privacyConfigDraft.data_sharing_notes}
                      onChange={(event) =>
                        setPrivacyConfigDraft((current) => ({
                          ...current,
                          data_sharing_notes: event.target.value,
                        }))
                      }
                    />
                  </div>
                </div>
              </div>

              <div className="rounded-2xl border border-stone-200 bg-white p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">
                  Contato LGPD, termos e exportação
                </p>
                <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                  <div>
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                      Responsável por privacidade
                    </label>
                    <Input
                      placeholder="Nome do responsável"
                      value={privacyConfigDraft.privacy_contact_name}
                      onChange={(event) =>
                        setPrivacyConfigDraft((current) => ({
                          ...current,
                          privacy_contact_name: event.target.value,
                        }))
                      }
                    />
                  </div>
                  <div>
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                      E-mail de privacidade
                    </label>
                    <Input
                      type="email"
                      placeholder="lgpd@clinica.com"
                      value={privacyConfigDraft.privacy_contact_email}
                      onChange={(event) =>
                        setPrivacyConfigDraft((current) => ({
                          ...current,
                          privacy_contact_email: event.target.value,
                        }))
                      }
                    />
                  </div>
                  <div>
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                      Telefone de privacidade
                    </label>
                    <Input
                      type="tel"
                      placeholder="(11) 99999-0000"
                      value={privacyConfigDraft.privacy_contact_phone}
                      onChange={(event) =>
                        setPrivacyConfigDraft((current) => ({
                          ...current,
                          privacy_contact_phone: event.target.value,
                        }))
                      }
                    />
                  </div>
                  <div>
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                      Escopo padrão de exportação
                    </label>
                    <select
                      className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                      value={privacyConfigDraft.export_scope}
                      onChange={(event) =>
                        setPrivacyConfigDraft((current) => ({
                          ...current,
                          export_scope: event.target.value,
                        }))
                      }
                    >
                      <option value="tenant">Clínica inteira</option>
                      <option value="patient">Paciente específico</option>
                      <option value="operational">Somente operacional</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                      Versão dos termos
                    </label>
                    <Input
                      placeholder="v1.0"
                      value={privacyConfigDraft.terms_version}
                      onChange={(event) =>
                        setPrivacyConfigDraft((current) => ({
                          ...current,
                          terms_version: event.target.value,
                        }))
                      }
                    />
                  </div>
                  <div>
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                      Versão da política
                    </label>
                    <Input
                      placeholder="v1.0"
                      value={privacyConfigDraft.policy_version}
                      onChange={(event) =>
                        setPrivacyConfigDraft((current) => ({
                          ...current,
                          policy_version: event.target.value,
                        }))
                      }
                    />
                  </div>
                  <div className="md:col-span-2">
                    <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                      E-mail para solicitar exportação
                    </label>
                    <Input
                      type="email"
                      placeholder="responsavel@clinica.com"
                      value={privacyConfigDraft.export_request_email}
                      onChange={(event) =>
                        setPrivacyConfigDraft((current) => ({
                          ...current,
                          export_request_email: event.target.value,
                        }))
                      }
                    />
                  </div>
                </div>
              </div>

              <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">
                  Ações operacionais
                </p>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button variant="outline" onClick={() => exportPrivacyDataMutation.mutate()}>
                    {exportPrivacyDataMutation.isPending ? "Exportando..." : "Solicitar exportação"}
                  </Button>
                  <Button variant="outline" onClick={() => acceptTermsMutation.mutate()}>
                    {acceptTermsMutation.isPending ? "Registrando..." : "Registrar aceite LGPD"}
                  </Button>
                </div>

                <div className="mt-4 grid gap-2 md:grid-cols-3">
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
              </div>

              <div className="flex flex-wrap justify-end gap-2">
                <Button variant="outline" onClick={restorePrivacyConfigDraft}>
                  Recarregar política
                </Button>
                <Button onClick={handleSavePrivacyConfig} disabled={savePrivacyConfigMutation.isPending}>
                  {savePrivacyConfigMutation.isPending ? "Salvando..." : "Salvar dados e privacidade"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      ) : null}

      {activeTab === "Clínica" ? (
        <DataTable<SettingItem>
          title="Catálogo técnico de configurações"
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
      ) : null}
    </div>
  );
}

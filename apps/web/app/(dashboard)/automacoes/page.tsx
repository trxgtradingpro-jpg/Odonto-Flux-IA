"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Bot,
  CalendarClock,
  CheckCircle2,
  Clock3,
  Copy,
  FileClock,
  GripVertical,
  Library,
  MessageSquareText,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Send,
  Settings2,
  Sparkles,
  UserRoundCheck,
  Zap,
} from "lucide-react";
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
import {
  ApiPage,
  AutomationHistoryItem,
  AutomationItem,
  AutomationManualExecutionResult,
  AutomationRunItem,
  AutomationSimulationResult,
} from "@/lib/domain-types";
import { formatDateTimeBR, numberFormatter, percentFormatter } from "@/lib/formatters";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, cn } from "@odontoflux/ui";

type TriggerType = "event" | "time";
type DrawerTab = "configuracao" | "simulacao" | "execucoes" | "impacto" | "historico";
type WorkspacePanel = "quick" | "playbooks" | "simulation";
type WizardStepId = "objetivo" | "disparo" | "regras" | "acoes" | "simulacao" | "publicacao";
type ConditionOperator = "eq" | "neq" | "in" | "contains";
type SupportedActionType = "send_message" | "add_tag" | "fila_humana" | "alter_status_conversa" | "agendar_job";

type ConditionDraft = {
  id: string;
  field: string;
  operator: ConditionOperator;
  value: string;
};

type ActionDraft = {
  id: string;
  type: SupportedActionType;
  body: string;
  messageType: string;
  to: string;
  tag: string;
  status: string;
  jobType: string;
  inMinutes: string;
  maxAttempts: string;
};

type AutomationFormState = {
  name: string;
  description: string;
  triggerType: TriggerType;
  triggerKey: string;
  isActive: boolean;
  windowMinutes: string;
  retryAttempts: string;
  conditionsMode: "visual" | "json";
  conditions: ConditionDraft[];
  conditionsJson: string;
  actions: ActionDraft[];
};

type AutomationWithStats = AutomationItem & {
  totalRuns: number;
  successRuns: number;
  failedRuns: number;
  successRate: number;
  lastExecution: string | null;
  nextExecution: string;
  health: "healthy" | "warning" | "critical" | "idle";
  messagesSent: number;
  handoffs: number;
};

type Playbook = {
  id: string;
  name: string;
  description: string;
  triggerType: TriggerType;
  triggerKey: string;
  conditions: Record<string, unknown>;
  actions: ActionDraft[];
};

const WIZARD_STEPS: Array<{ id: WizardStepId; label: string; helper: string }> = [
  { id: "objetivo", label: "Objetivo", helper: "Nome, descrição e playbook base." },
  { id: "disparo", label: "Disparo", helper: "Evento ou rotina de tempo." },
  { id: "regras", label: "Regras", helper: "Condições sem JSON por padrão." },
  { id: "acoes", label: "Ações", helper: "O que acontece em ordem." },
  { id: "simulacao", label: "Simulação", helper: "Teste seguro sem efeitos reais." },
  { id: "publicacao", label: "Publicação", helper: "Resumo final e ativação." },
];

const SUPPORTED_ACTION_LABELS: Record<SupportedActionType, string> = {
  send_message: "Enviar mensagem",
  add_tag: "Adicionar tag",
  fila_humana: "Mover para fila humana",
  alter_status_conversa: "Alterar status da conversa",
  agendar_job: "Agendar próximo passo",
};

const TRIGGER_HELP: Record<string, string> = {
  consulta_24h: "Rotina de tempo usada para lembretes de confirmação um dia antes da consulta.",
  consulta_2h: "Rotina de tempo usada para reforço operacional poucas horas antes do atendimento.",
  paciente_faltou: "Evento emitido quando a operação registra ausência do paciente.",
  orcamento_pendente_2d: "Evento para retomar orçamento pendente depois de dois dias.",
  orcamento_pendente_7d: "Evento para última tentativa de retorno em orçamento parado.",
  paciente_inativo: "Evento usado para campanha de reativação de pacientes sem retorno.",
  lead_whatsapp_entrada: "Evento de triagem quando um lead entra pelo WhatsApp.",
};

const CONDITION_FIELDS = [
  { value: "status", label: "Status" },
  { value: "channel", label: "Canal" },
  { value: "unit_id", label: "Unidade" },
  { value: "tag", label: "Tag no payload" },
  { value: "inactive_days", label: "Dias de inatividade" },
  { value: "confirmation_status", label: "Confirmação" },
];

const CONDITION_OPERATORS: Array<{ value: ConditionOperator; label: string }> = [
  { value: "eq", label: "igual a" },
  { value: "neq", label: "diferente de" },
  { value: "in", label: "está em lista" },
  { value: "contains", label: "contém" },
];

const DEFAULT_ACTION_BODY = "Mensagem automática da campanha operacional.";
const DEFAULT_SIMULATION_PAYLOAD = JSON.stringify(
  {
    phone: "11999999999",
    channel: "whatsapp",
    status: "pendente",
    confirmation_status: "pendente",
    conversation_id: "",
    patient_id: "",
  },
  null,
  2,
);

const PLAYBOOKS: Playbook[] = [
  {
    id: "consulta_24h",
    name: "Confirmação 24h antes",
    description: "Envia lembrete para confirmar presença antes da consulta.",
    triggerType: "time",
    triggerKey: "consulta_24h",
    conditions: { window_minutes: 120 },
    actions: [createActionDraft("send_message", { body: "Lembrete: sua consulta é amanhã. Responda CONFIRMO para confirmar." })],
  },
  {
    id: "consulta_2h",
    name: "Lembrete 2h antes",
    description: "Reforço operacional para consultas próximas.",
    triggerType: "time",
    triggerKey: "consulta_2h",
    conditions: { status: "pendente" },
    actions: [createActionDraft("send_message", { body: "Sua consulta está próxima. Responda CONFIRMO para validar." })],
  },
  {
    id: "paciente_faltou",
    name: "Recuperação de faltas",
    description: "Contato automático para reagendar pacientes que faltaram.",
    triggerType: "event",
    triggerKey: "paciente_faltou",
    conditions: {},
    actions: [
      createActionDraft("send_message", { body: "Sentimos sua falta hoje. Quer reagendar para um novo horário?" }),
      createActionDraft("add_tag", { tag: "faltou" }),
    ],
  },
  {
    id: "orcamento_pendente_2d",
    name: "Follow-up orçamento 2 dias",
    description: "Retoma contato com orçamento pendente de forma consultiva.",
    triggerType: "event",
    triggerKey: "orcamento_pendente_2d",
    conditions: {},
    actions: [createActionDraft("send_message", { body: "Passando para confirmar se você conseguiu analisar o orçamento." })],
  },
  {
    id: "orcamento_pendente_7d",
    name: "Follow-up orçamento 7 dias",
    description: "Última tentativa automática para recuperar oportunidade comercial.",
    triggerType: "event",
    triggerKey: "orcamento_pendente_7d",
    conditions: {},
    actions: [createActionDraft("send_message", { body: "Ainda conseguimos manter condições especiais esta semana." })],
  },
  {
    id: "paciente_inativo",
    name: "Reativação de inativos",
    description: "Convida pacientes sem retorno a retomar o tratamento.",
    triggerType: "event",
    triggerKey: "paciente_inativo",
    conditions: { inactive_days: 180 },
    actions: [createActionDraft("send_message", { body: "Estamos com agenda aberta para retomada do seu tratamento." })],
  },
  {
    id: "lead_whatsapp_entrada",
    name: "Triagem WhatsApp",
    description: "Recebe o lead e direciona para atendimento humano.",
    triggerType: "event",
    triggerKey: "lead_whatsapp_entrada",
    conditions: {},
    actions: [
      createActionDraft("send_message", { body: "Recebemos seu contato. Vou te direcionar para nossa equipe continuar o atendimento." }),
      createActionDraft("fila_humana"),
    ],
  },
];

function createId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function createActionDraft(type: SupportedActionType, params: Partial<ActionDraft> = {}): ActionDraft {
  return {
    id: createId("action"),
    type,
    body: params.body ?? DEFAULT_ACTION_BODY,
    messageType: params.messageType ?? "text",
    to: params.to ?? "",
    tag: params.tag ?? "",
    status: params.status ?? "aguardando",
    jobType: params.jobType ?? "follow_up",
    inMinutes: params.inMinutes ?? "5",
    maxAttempts: params.maxAttempts ?? "3",
  };
}

function defaultFormState(): AutomationFormState {
  return {
    name: "",
    description: "",
    triggerType: "event",
    triggerKey: "",
    isActive: true,
    windowMinutes: "60",
    retryAttempts: "3",
    conditionsMode: "visual",
    conditions: [],
    conditionsJson: "{}",
    actions: [createActionDraft("send_message")],
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function readNumberLike(value: unknown, fallback = "") {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "string") return value;
  return fallback;
}

function getActionParams(action: Record<string, unknown>) {
  return isRecord(action.params) ? action.params : {};
}

function actionTypeFromRecord(action: Record<string, unknown>): SupportedActionType | null {
  const type = readString(action.type);
  if (type in SUPPORTED_ACTION_LABELS) return type as SupportedActionType;
  return null;
}

function actionRecordToDraft(action: Record<string, unknown>): ActionDraft | null {
  const type = actionTypeFromRecord(action);
  if (!type) return null;
  const params = getActionParams(action);
  return createActionDraft(type, {
    body: readString(params.body, DEFAULT_ACTION_BODY),
    messageType: readString(params.message_type, "text"),
    to: readString(params.to),
    tag: readString(params.tag),
    status: readString(params.status, "aguardando"),
    jobType: readString(params.job_type, "follow_up"),
    inMinutes: readNumberLike(params.in_minutes, "5"),
    maxAttempts: readNumberLike(params.max_attempts, "3"),
  });
}

function actionDraftToPayload(action: ActionDraft) {
  if (action.type === "send_message") {
    const params: Record<string, unknown> = {
      body: action.body.trim(),
      message_type: action.messageType || "text",
    };
    if (action.to.trim()) params.to = action.to.trim();
    return { type: action.type, params };
  }
  if (action.type === "add_tag") {
    return { type: action.type, params: { tag: action.tag.trim() } };
  }
  if (action.type === "alter_status_conversa") {
    return { type: action.type, params: { status: action.status || "aguardando" } };
  }
  if (action.type === "agendar_job") {
    return {
      type: action.type,
      params: {
        job_type: action.jobType || "follow_up",
        in_minutes: Number(action.inMinutes || 5),
        max_attempts: Number(action.maxAttempts || 3),
      },
    };
  }
  return { type: action.type, params: {} };
}

function conditionsToDraft(conditions: Record<string, unknown>) {
  const visual: ConditionDraft[] = [];
  let windowMinutes = "60";

  Object.entries(conditions || {}).forEach(([field, rawValue]) => {
    if (field === "window_minutes") {
      windowMinutes = readNumberLike(rawValue, "60");
      return;
    }
    if (isRecord(rawValue) && "operator" in rawValue) {
      const operator = readString(rawValue.operator, "eq") as ConditionOperator;
      const value = rawValue.value;
      visual.push({
        id: createId("condition"),
        field,
        operator: ["eq", "neq", "in", "contains"].includes(operator) ? operator : "eq",
        value: Array.isArray(value) ? value.join(", ") : readNumberLike(value, readString(value)),
      });
      return;
    }
    visual.push({
      id: createId("condition"),
      field,
      operator: Array.isArray(rawValue) ? "in" : "eq",
      value: Array.isArray(rawValue) ? rawValue.join(", ") : readNumberLike(rawValue, readString(rawValue)),
    });
  });

  return { visual, windowMinutes };
}

function valueFromCondition(condition: ConditionDraft) {
  if (condition.operator === "in") {
    return condition.value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }
  const numeric = Number(condition.value);
  if (condition.field === "inactive_days" && Number.isFinite(numeric)) return numeric;
  return condition.value.trim();
}

function conditionsFromForm(form: AutomationFormState) {
  if (form.conditionsMode === "json") {
    return JSON.parse(form.conditionsJson || "{}") as Record<string, unknown>;
  }

  const payload: Record<string, unknown> = {};
  form.conditions
    .filter((condition) => condition.field.trim() && condition.value.trim())
    .forEach((condition) => {
      const value = valueFromCondition(condition);
      if (condition.operator === "eq") {
        payload[condition.field] = value;
      } else {
        payload[condition.field] = { operator: condition.operator, value };
      }
    });

  if (form.triggerType === "time") {
    payload.window_minutes = Math.max(1, Number(form.windowMinutes || 60));
  }

  return payload;
}

function automationToForm(automation: AutomationItem): AutomationFormState {
  const { visual, windowMinutes } = conditionsToDraft(automation.conditions || {});
  const actions = (automation.actions || [])
    .map((action) => actionRecordToDraft(action))
    .filter((action): action is ActionDraft => Boolean(action));
  const retryAttempts = readNumberLike(automation.retry_policy?.max_attempts, "3");

  return {
    name: automation.name,
    description: automation.description || "",
    triggerType: automation.trigger_type === "time" ? "time" : "event",
    triggerKey: automation.trigger_key,
    isActive: automation.is_active,
    windowMinutes,
    retryAttempts,
    conditionsMode: "visual",
    conditions: visual,
    conditionsJson: JSON.stringify(automation.conditions || {}, null, 2),
    actions: actions.length ? actions : [createActionDraft("send_message")],
  };
}

function playbookToForm(playbook: Playbook): AutomationFormState {
  const { visual, windowMinutes } = conditionsToDraft(playbook.conditions);
  return {
    ...defaultFormState(),
    name: playbook.name,
    description: playbook.description,
    triggerType: playbook.triggerType,
    triggerKey: playbook.triggerKey,
    windowMinutes,
    conditions: visual,
    conditionsJson: JSON.stringify(playbook.conditions, null, 2),
    actions: playbook.actions.map((action) => ({ ...action, id: createId("action") })),
  };
}

function formToPayload(form: AutomationFormState) {
  return {
    name: form.name.trim(),
    description: form.description.trim() || null,
    trigger_type: form.triggerType,
    trigger_key: form.triggerKey.trim(),
    conditions: conditionsFromForm(form),
    actions: form.actions.map(actionDraftToPayload),
    retry_policy: { max_attempts: Math.max(1, Number(form.retryAttempts || 3)) },
    is_active: form.isActive,
  };
}

function parseSimulationPayload(payloadJson: string) {
  const parsed = JSON.parse(payloadJson || "{}");
  if (!isRecord(parsed)) {
    throw new Error("O payload precisa ser um objeto JSON.");
  }
  return parsed;
}

function stringifyUnknown(value: unknown) {
  if (value === undefined || value === null || value === "") return "vazio";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function moveArrayItem<T>(items: T[], fromIndex: number, toIndex: number) {
  const copy = [...items];
  const [moved] = copy.splice(fromIndex, 1);
  copy.splice(toIndex, 0, moved);
  return copy;
}

function historyActionLabel(action: string) {
  const labels: Record<string, string> = {
    "automation.create": "Automação criada",
    "automation.update": "Configuração atualizada",
    "automation.pause": "Automação pausada",
    "automation.resume": "Automação reativada",
    "automation.duplicate": "Automação duplicada",
    "automation.execute_manual": "Execução manual solicitada",
  };
  return labels[action] ?? action;
}

function getFirstMessage(actions: ActionDraft[]) {
  return actions.find((action) => action.type === "send_message")?.body || "";
}

function summarizeConditions(conditions: Record<string, unknown>) {
  const entries = Object.entries(conditions || {}).filter(([field]) => field !== "window_minutes");
  if (!entries.length) return "Sem filtro adicional";
  return entries
    .slice(0, 2)
    .map(([field, value]) => {
      if (isRecord(value) && "operator" in value) return `${field} ${value.operator} ${String(value.value ?? "")}`;
      if (Array.isArray(value)) return `${field} em ${value.join(", ")}`;
      return `${field}: ${String(value)}`;
    })
    .join(" • ");
}

function summarizeActions(actions: Array<Record<string, unknown>> | ActionDraft[]) {
  if (!actions.length) return "Nenhuma ação";
  return actions
    .slice(0, 3)
    .map((action) => {
      const type = "type" in action ? action.type : "";
      const label = typeof type === "string" && type in SUPPORTED_ACTION_LABELS ? SUPPORTED_ACTION_LABELS[type as SupportedActionType] : "Ação";
      return label;
    })
    .join(" + ");
}

function humanSummary(form: AutomationFormState) {
  const trigger = form.triggerKey ? form.triggerKey.replaceAll("_", " ") : "gatilho definido";
  const actions = summarizeActions(form.actions);
  return `Quando ${trigger}, executar: ${actions}.`;
}

function runActions(run: AutomationRunItem) {
  const actions = run.result_payload?.actions;
  return Array.isArray(actions) ? actions.filter(isRecord) : [];
}

function countRunAction(runs: AutomationRunItem[], actionType: string) {
  return runs.reduce((total, run) => {
    return total + runActions(run).filter((action) => action.action === actionType).length;
  }, 0);
}

function healthFor(totalRuns: number, failedRuns: number): AutomationWithStats["health"] {
  if (!totalRuns) return "idle";
  const failureRate = failedRuns / totalRuns;
  if (failureRate >= 0.35) return "critical";
  if (failureRate > 0) return "warning";
  return "healthy";
}

function healthLabel(health: AutomationWithStats["health"]) {
  if (health === "healthy") return "Saudável";
  if (health === "warning") return "Atenção";
  if (health === "critical") return "Crítica";
  return "Sem execuções";
}

function nextExecutionLabel(automation: AutomationItem, lastExecution: string | null) {
  if (automation.trigger_type !== "time") return "Sob evento";
  const windowMinutes = Number(automation.conditions?.window_minutes || 60);
  if (!lastExecution) return "Aguardando scheduler";
  const date = new Date(lastExecution);
  if (Number.isNaN(date.getTime())) return "Aguardando scheduler";
  date.setMinutes(date.getMinutes() + Math.max(1, windowMinutes));
  return formatDateTimeBR(date);
}

function buildStats(item: AutomationItem, runs: AutomationRunItem[]): AutomationWithStats {
  const automationRuns = runs.filter((run) => run.automation_id === item.id);
  const totalRuns = automationRuns.length;
  const successRuns = automationRuns.filter((run) => run.status === "success").length;
  const failedRuns = automationRuns.filter((run) => run.status === "failed").length;
  const lastExecution = automationRuns[0]?.finished_at || automationRuns[0]?.started_at || automationRuns[0]?.created_at || null;
  const successRate = totalRuns ? (successRuns / totalRuns) * 100 : 0;
  return {
    ...item,
    totalRuns,
    successRuns,
    failedRuns,
    successRate,
    lastExecution,
    nextExecution: nextExecutionLabel(item, lastExecution),
    health: healthFor(totalRuns, failedRuns),
    messagesSent: countRunAction(automationRuns, "send_message"),
    handoffs: countRunAction(automationRuns, "fila_humana"),
  };
}

function statusFilterMatch(item: AutomationWithStats, statusFilter: string) {
  if (statusFilter === "all") return true;
  if (statusFilter === "active") return item.is_active;
  if (statusFilter === "paused") return !item.is_active;
  if (statusFilter === "failed") return item.failedRuns > 0;
  if (statusFilter === "healthy") return item.health === "healthy";
  return true;
}

function triggerTypeLabel(value: string) {
  return value === "time" ? "Tempo" : "Evento";
}

function AutomationBadge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "green" | "amber" | "red" | "blue" }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold",
        tone === "neutral" && "border-stone-200 bg-stone-50 text-stone-700",
        tone === "green" && "border-emerald-200 bg-emerald-50 text-emerald-700",
        tone === "amber" && "border-amber-200 bg-amber-50 text-amber-800",
        tone === "red" && "border-rose-200 bg-rose-50 text-rose-700",
        tone === "blue" && "border-sky-200 bg-sky-50 text-sky-700",
      )}
    >
      {children}
    </span>
  );
}

function HealthBadge({ health }: { health: AutomationWithStats["health"] }) {
  const tone = health === "healthy" ? "green" : health === "warning" ? "amber" : health === "critical" ? "red" : "neutral";
  return <AutomationBadge tone={tone}>{healthLabel(health)}</AutomationBadge>;
}

function FieldHelp({ children }: { children: React.ReactNode }) {
  return <p className="mt-1 text-xs leading-5 text-stone-500">{children}</p>;
}

export default function AutomacoesPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [workspacePanel, setWorkspacePanel] = useState<WorkspacePanel>("quick");

  const [quickForm, setQuickForm] = useState<AutomationFormState>(() => defaultFormState());
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>("configuracao");
  const [drawerMode, setDrawerMode] = useState<"create" | "edit">("edit");
  const [selectedAutomationId, setSelectedAutomationId] = useState<string | null>(null);
  const [form, setForm] = useState<AutomationFormState>(() => defaultFormState());
  const [wizardStep, setWizardStep] = useState<WizardStepId>("objetivo");
  const [simulationOpen, setSimulationOpen] = useState(false);
  const [simulationPayloadJson, setSimulationPayloadJson] = useState(DEFAULT_SIMULATION_PAYLOAD);
  const [workspaceSimulationAutomationId, setWorkspaceSimulationAutomationId] = useState("");
  const [manualExecutionConfirmation, setManualExecutionConfirmation] = useState("");

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

  const enrichedAutomations = useMemo(() => {
    if (!automationsQuery.data) return [];
    return automationsQuery.data.automations
      .map((item) => buildStats(item, automationsQuery.data.runs))
      .filter((item) => {
        const term = search.toLowerCase().trim();
        const haystack = `${item.name} ${item.description ?? ""} ${item.trigger_type} ${item.trigger_key} ${summarizeActions(item.actions)} ${summarizeConditions(item.conditions)}`.toLowerCase();
        const bySearch = !term || haystack.includes(term);
        const byStatus = statusFilterMatch(item, statusFilter);
        const byType = typeFilter === "all" || item.trigger_type === typeFilter;
        return bySearch && byStatus && byType;
      });
  }, [automationsQuery.data, search, statusFilter, typeFilter]);

  const selectedAutomation = selectedAutomationId
    ? enrichedAutomations.find((item) => item.id === selectedAutomationId) ??
      automationsQuery.data?.automations.find((item) => item.id === selectedAutomationId)
    : null;

  const selectedRuns = selectedAutomation
    ? automationsQuery.data?.runs.filter((run) => run.automation_id === selectedAutomation.id) ?? []
    : [];

  const historyQuery = useQuery<ApiPage<AutomationHistoryItem>>({
    queryKey: ["automation-history", selectedAutomationId],
    queryFn: async () => {
      const response = await api.get<ApiPage<AutomationHistoryItem>>(`/automations/${selectedAutomationId}/history`, {
        params: { limit: 80, offset: 0 },
      });
      return response.data;
    },
    enabled: Boolean(selectedAutomationId && drawerOpen && drawerTab === "historico"),
  });

  const overallStats = useMemo(() => {
    const all = automationsQuery.data?.automations ?? [];
    const runs = automationsQuery.data?.runs ?? [];
    const enriched = all.map((item) => buildStats(item, runs));
    const totalRuns = runs.length;
    const successRuns = runs.filter((run) => run.status === "success").length;
    const failedRuns = runs.filter((run) => run.status === "failed").length;
    return {
      active: all.filter((item) => item.is_active).length,
      paused: all.filter((item) => !item.is_active).length,
      totalRuns,
      successRate: totalRuns ? (successRuns / totalRuns) * 100 : 0,
      failedRuns,
      messagesSent: enriched.reduce((sum, item) => sum + item.messagesSent, 0),
      handoffs: enriched.reduce((sum, item) => sum + item.handoffs, 0),
    };
  }, [automationsQuery.data]);

  const automationNameById = new Map((automationsQuery.data?.automations ?? []).map((item) => [item.id, item.name]));
  const timelineItems = (automationsQuery.data?.runs ?? []).slice(0, 8).map((run) => ({
    id: run.id,
    title: `Execução ${run.status === "success" ? "concluída" : run.status === "failed" ? "com falha" : run.status}`,
    description: `${automationNameById.get(run.automation_id) ?? "Automação"} • ${runActions(run).length || 0} ação(ões) registrada(s)`,
    time: formatDateTimeBR(run.finished_at || run.started_at || run.created_at),
    badge: <StatusBadge value={run.status} />,
  }));

  const openCreateDrawer = (seed?: AutomationFormState) => {
    setSelectedAutomationId(null);
    setDrawerMode("create");
    setDrawerTab("configuracao");
    setWizardStep("objetivo");
    setForm(seed ?? defaultFormState());
    setDrawerOpen(true);
  };

  const openEditDrawer = (automation: AutomationItem | AutomationWithStats, tab: DrawerTab = "configuracao") => {
    setSelectedAutomationId(automation.id);
    setWorkspaceSimulationAutomationId(automation.id);
    setManualExecutionConfirmation("");
    setDrawerMode("edit");
    setDrawerTab(tab);
    setWizardStep(tab === "simulacao" ? "simulacao" : "objetivo");
    setForm(automationToForm(automation));
    setDrawerOpen(true);
  };

  const createMutation = useMutation({
    mutationFn: async (draft: AutomationFormState) => api.post<AutomationItem>("/automations", formToPayload(draft)),
    onSuccess: (response) => {
      const created = response.data;
      toast.success("Automação criada. Revise a configuração antes de escalar a operação.");
      queryClient.invalidateQueries({ queryKey: ["automations-dataset"] });
      setQuickForm(defaultFormState());
      setSelectedAutomationId(created.id);
      setDrawerMode("edit");
      setDrawerTab("configuracao");
      setForm(automationToForm(created));
      setDrawerOpen(true);
    },
    onError: () => toast.error("Não foi possível criar a automação."),
  });

  const updateMutation = useMutation({
    mutationFn: async ({ automationId, draft }: { automationId: string; draft: AutomationFormState }) =>
      api.patch(`/automations/${automationId}`, formToPayload(draft)),
    onSuccess: () => {
      toast.success("Automação atualizada com sucesso.");
      queryClient.invalidateQueries({ queryKey: ["automations-dataset"] });
      queryClient.invalidateQueries({ queryKey: ["automation-history", selectedAutomationId] });
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
      queryClient.invalidateQueries({ queryKey: ["automation-history", selectedAutomationId] });
    },
    onError: () => toast.error("Falha ao pausar automação."),
  });

  const resumeMutation = useMutation({
    mutationFn: async (automationId: string) => api.post(`/automations/${automationId}/resume`),
    onSuccess: () => {
      toast.success("Automação reativada.");
      queryClient.invalidateQueries({ queryKey: ["automations-dataset"] });
      queryClient.invalidateQueries({ queryKey: ["automation-history", selectedAutomationId] });
    },
    onError: () => toast.error("Falha ao reativar automação."),
  });

  const duplicateMutation = useMutation({
    mutationFn: async (automationId: string) => api.post<AutomationItem>(`/automations/${automationId}/duplicate`),
    onSuccess: (response) => {
      const created = response.data;
      toast.success("Cópia criada pausada para revisão segura.");
      queryClient.invalidateQueries({ queryKey: ["automations-dataset"] });
      setSelectedAutomationId(created.id);
      setDrawerMode("edit");
      setDrawerTab("configuracao");
      setWizardStep("objetivo");
      setForm(automationToForm(created));
      setDrawerOpen(true);
    },
    onError: () => toast.error("Não foi possível duplicar a automação."),
  });

  const simulateSavedMutation = useMutation({
    mutationFn: async ({ automationId, triggerPayload }: { automationId: string; triggerPayload: Record<string, unknown> }) => {
      const response = await api.post<AutomationSimulationResult>(`/automations/${automationId}/simulate`, {
        trigger_payload: triggerPayload,
      });
      return response.data;
    },
    onError: () => toast.error("Não foi possível simular esta automação."),
  });

  const simulateDraftMutation = useMutation({
    mutationFn: async ({ draft, triggerPayload }: { draft: AutomationFormState; triggerPayload: Record<string, unknown> }) => {
      const response = await api.post<AutomationSimulationResult>("/automations/simulate-config", {
        automation: formToPayload(draft),
        trigger_payload: triggerPayload,
      });
      return response.data;
    },
    onError: () => toast.error("Não foi possível simular o rascunho."),
  });

  const manualExecuteMutation = useMutation({
    mutationFn: async ({ automationId, triggerPayload, confirmation }: { automationId: string; triggerPayload: Record<string, unknown>; confirmation: string }) => {
      const response = await api.post<AutomationManualExecutionResult>(`/automations/${automationId}/execute`, {
        trigger_payload: triggerPayload,
        confirmation,
      });
      return response.data;
    },
    onSuccess: (result) => {
      if (result.run_created) {
        toast.success("Execução manual criada e enviada para processamento.");
      } else {
        toast.warning("Execução não criada: a simulação indicou que a automação não deve disparar.");
      }
      setManualExecutionConfirmation("");
      queryClient.invalidateQueries({ queryKey: ["automations-dataset"] });
      queryClient.invalidateQueries({ queryKey: ["automation-history", selectedAutomationId] });
    },
    onError: () => toast.error("Não foi possível executar manualmente a automação."),
  });

  const handleSaveForm = (draft: AutomationFormState = form) => {
    if (!draft.name.trim() || !draft.triggerKey.trim()) {
      toast.error("Preencha nome e gatilho antes de salvar.");
      return;
    }
    if (!draft.actions.length) {
      toast.error("Adicione pelo menos uma ação real para a automação.");
      return;
    }
    try {
      conditionsFromForm(draft);
    } catch {
      toast.error("Condições em JSON inválido. Revise antes de salvar.");
      return;
    }
    if (drawerMode === "create") {
      createMutation.mutate(draft);
      return;
    }
    if (selectedAutomationId) {
      updateMutation.mutate({ automationId: selectedAutomationId, draft });
    }
  };

  const handlePublishChoice = (isActive: boolean) => {
    const draft = { ...form, isActive };
    setForm(draft);
    handleSaveForm(draft);
  };

  const runDraftSimulation = () => {
    try {
      const triggerPayload = parseSimulationPayload(simulationPayloadJson);
      simulateDraftMutation.mutate({ draft: form, triggerPayload });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Payload JSON inválido.");
    }
  };

  const runWorkspaceSimulation = () => {
    if (!workspaceSimulationAutomationId) {
      toast.error("Escolha uma automação salva para simular.");
      return;
    }
    try {
      const triggerPayload = parseSimulationPayload(simulationPayloadJson);
      simulateSavedMutation.mutate({ automationId: workspaceSimulationAutomationId, triggerPayload });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Payload JSON inválido.");
    }
  };

  const runDrawerSavedSimulation = () => {
    if (!selectedAutomationId) {
      runDraftSimulation();
      return;
    }
    try {
      const triggerPayload = parseSimulationPayload(simulationPayloadJson);
      simulateSavedMutation.mutate({ automationId: selectedAutomationId, triggerPayload });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Payload JSON inválido.");
    }
  };

  const runManualExecution = () => {
    if (!selectedAutomationId) {
      toast.error("Salve a automação antes de executar de verdade.");
      return;
    }
    if (manualExecutionConfirmation !== "EXECUTAR") {
      toast.error("Digite EXECUTAR para confirmar a execução real.");
      return;
    }
    try {
      const triggerPayload = parseSimulationPayload(simulationPayloadJson);
      manualExecuteMutation.mutate({
        automationId: selectedAutomationId,
        triggerPayload,
        confirmation: manualExecutionConfirmation,
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Payload JSON inválido.");
    }
  };

  const handleQuickCreate = () => {
    if (!quickForm.name.trim() || !quickForm.triggerKey.trim()) {
      toast.error("Preencha nome e gatilho para criar a automação inicial.");
      return;
    }
    createMutation.mutate(quickForm);
  };

  const applyPlaybookToQuickForm = (playbook: Playbook) => {
    const draft = playbookToForm(playbook);
    setQuickForm(draft);
    setWorkspacePanel("quick");
    toast.success("Playbook carregado na criação rápida.");
  };

  if (automationsQuery.isLoading) return <LoadingState message="Carregando Studio de Automações..." />;
  if (automationsQuery.isError || !automationsQuery.data) return <ErrorState message="Não foi possível carregar automações." />;

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Studio de Automações"
        title="Automações que sustentam a operação"
        description="Crie, revise e acompanhe fluxos de WhatsApp, agenda e follow-up sem depender de regras escondidas."
        actions={
          <>
            <Button className="gap-1.5" onClick={() => openCreateDrawer()}>
              <Plus size={15} />
              Nova automação
            </Button>
            <Button variant="outline" className="gap-1.5" onClick={() => setWorkspacePanel("quick")}>
              <Zap size={15} />
              Criação rápida
            </Button>
            <Button variant="outline" className="gap-1.5" onClick={() => setWorkspacePanel("playbooks")}>
              <Library size={15} />
              Biblioteca de playbooks
            </Button>
            <Button variant="outline" className="gap-1.5" onClick={() => setSimulationOpen(true)}>
              <Sparkles size={15} />
              Simular disparo
            </Button>
          </>
        }
      />

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        <StatCard title="Ativas" value={numberFormatter.format(overallStats.active)} helper="Rodando na operação" icon={<Play size={16} />} />
        <StatCard title="Pausadas" value={numberFormatter.format(overallStats.paused)} helper="Guardadas sem disparo" icon={<Pause size={16} />} />
        <StatCard title="Execuções" value={numberFormatter.format(overallStats.totalRuns)} helper="Histórico carregado" icon={<Activity size={16} />} />
        <StatCard title="Sucesso médio" value={`${percentFormatter.format(overallStats.successRate)}%`} helper="Com base nos runs" icon={<CheckCircle2 size={16} />} />
        <StatCard title="Falhas" value={numberFormatter.format(overallStats.failedRuns)} helper="Exigem revisão" icon={<AlertTriangle size={16} />} />
        <StatCard title="Handoffs" value={numberFormatter.format(overallStats.handoffs)} helper="Estimativa por ação" icon={<UserRoundCheck size={16} />} />
      </div>

      <Card className="border-stone-200 bg-white/95 shadow-sm">
        <CardHeader className="border-b border-stone-200/80 pb-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <CardTitle>{workspacePanel === "playbooks" ? "Biblioteca de playbooks" : workspacePanel === "simulation" ? "Simulação segura" : "Criação rápida"}</CardTitle>
              <p className="mt-1 text-sm text-stone-600">
                {workspacePanel === "playbooks"
                  ? "Modelos prontos para carregar uma automação inicial com gatilho e ações reais."
                  : workspacePanel === "simulation"
                    ? "Teste uma automação salva com payload de exemplo sem enviar mensagem, alterar conversa ou criar job."
                    : "Use para criar a base da automação e abrir a configuração completa em seguida."}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant={workspacePanel === "quick" ? "default" : "outline"} onClick={() => setWorkspacePanel("quick")}>
                Criação rápida
              </Button>
              <Button variant={workspacePanel === "playbooks" ? "default" : "outline"} onClick={() => setWorkspacePanel("playbooks")}>
                Playbooks
              </Button>
              <Button variant={workspacePanel === "simulation" ? "default" : "outline"} onClick={() => setWorkspacePanel("simulation")}>
                Simulação
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {workspacePanel === "quick" ? (
            <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <div>
                  <Input placeholder="Nome da automação" value={quickForm.name} onChange={(event) => setQuickForm((current) => ({ ...current, name: event.target.value }))} />
                  <FieldHelp>Nome interno para a equipe encontrar essa regra depois.</FieldHelp>
                </div>
                <div>
                  <select
                    className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                    value={quickForm.triggerType}
                    onChange={(event) => setQuickForm((current) => ({ ...current, triggerType: event.target.value as TriggerType }))}
                  >
                    <option value="event">Evento</option>
                    <option value="time">Tempo</option>
                  </select>
                  <FieldHelp>Evento responde a algo que aconteceu; tempo roda pelo scheduler.</FieldHelp>
                </div>
                <div>
                  <Input placeholder="Gatilho (ex.: consulta_24h)" value={quickForm.triggerKey} onChange={(event) => setQuickForm((current) => ({ ...current, triggerKey: event.target.value }))} />
                  <FieldHelp>{TRIGGER_HELP[quickForm.triggerKey] ?? "Chave técnica que a automação escuta."}</FieldHelp>
                </div>
                <div>
                  <select
                    className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                    value=""
                    onChange={(event) => {
                      const playbook = PLAYBOOKS.find((item) => item.id === event.target.value);
                      if (playbook) setQuickForm(playbookToForm(playbook));
                    }}
                  >
                    <option value="">Usar preset</option>
                    {PLAYBOOKS.map((playbook) => (
                      <option key={playbook.id} value={playbook.id}>
                        {playbook.name}
                      </option>
                    ))}
                  </select>
                  <FieldHelp>Carrega nome, gatilho e ações principais.</FieldHelp>
                </div>
              </div>
              <div className="rounded-lg border border-primary/15 bg-primary/5 p-4">
                <p className="text-xs font-bold uppercase tracking-wide text-primary">Resumo operacional</p>
                <p className="mt-2 text-sm leading-6 text-stone-700">{humanSummary(quickForm)}</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button className="gap-1.5" onClick={handleQuickCreate} disabled={createMutation.isPending}>
                    <Settings2 size={14} />
                    {createMutation.isPending ? "Criando..." : "Criar e configurar"}
                  </Button>
                  <Button variant="outline" onClick={() => openCreateDrawer(quickForm)}>
                    Configurar antes
                  </Button>
                </div>
              </div>
            </div>
          ) : null}

          {workspacePanel === "playbooks" ? (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {PLAYBOOKS.map((playbook) => (
                <div key={playbook.id} className="rounded-lg border border-stone-200 bg-stone-50/60 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-semibold text-stone-900">{playbook.name}</p>
                      <p className="mt-1 text-sm leading-6 text-stone-600">{playbook.description}</p>
                    </div>
                    <AutomationBadge tone={playbook.triggerType === "time" ? "blue" : "green"}>
                      {triggerTypeLabel(playbook.triggerType)}
                    </AutomationBadge>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <AutomationBadge>{playbook.triggerKey}</AutomationBadge>
                    <AutomationBadge>{summarizeActions(playbook.actions)}</AutomationBadge>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Button className="h-9 px-3 text-xs" onClick={() => applyPlaybookToQuickForm(playbook)}>
                      Usar playbook
                    </Button>
                    <Button variant="outline" className="h-9 px-3 text-xs" onClick={() => openCreateDrawer(playbookToForm(playbook))}>
                      Configurar
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : null}

          {workspacePanel === "simulation" ? (
            <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
              <div className="space-y-3">
                <div>
                  <select
                    className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                    value={workspaceSimulationAutomationId}
                    onChange={(event) => setWorkspaceSimulationAutomationId(event.target.value)}
                  >
                    <option value="">Escolha uma automação salva</option>
                    {(automationsQuery.data.automations ?? []).map((automation) => (
                      <option key={automation.id} value={automation.id}>
                        {automation.name}
                      </option>
                    ))}
                  </select>
                  <FieldHelp>A simulação usa a configuração salva no backend e não executa efeitos colaterais.</FieldHelp>
                </div>
                <SimulationPayloadEditor value={simulationPayloadJson} onChange={setSimulationPayloadJson} />
                <Button className="w-full gap-1.5" onClick={runWorkspaceSimulation} disabled={simulateSavedMutation.isPending}>
                  <Sparkles size={15} />
                  {simulateSavedMutation.isPending ? "Simulando..." : "Simular automação salva"}
                </Button>
              </div>
              <SimulationResultCard result={simulateSavedMutation.data ?? null} />
            </div>
          ) : null}
        </CardContent>
      </Card>

      <FilterBar search={search} onSearchChange={setSearch} searchPlaceholder="Buscar por nome, gatilho, condição ou ação...">
        <select
          className="rounded-lg border border-stone-300 bg-white text-sm"
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value)}
        >
          <option value="all">Todas</option>
          <option value="active">Ativas</option>
          <option value="paused">Pausadas</option>
          <option value="failed">Com falha</option>
          <option value="healthy">Saudáveis</option>
        </select>
        <select
          className="rounded-lg border border-stone-300 bg-white text-sm"
          value={typeFilter}
          onChange={(event) => setTypeFilter(event.target.value)}
        >
          <option value="all">Todos os tipos</option>
          <option value="event">Evento</option>
          <option value="time">Tempo</option>
        </select>
      </FilterBar>

      <DataTable<AutomationWithStats>
        title="Automações operacionais"
        rows={enrichedAutomations}
        getRowId={(item) => item.id}
        searchBy={(item) => `${item.name} ${item.trigger_type} ${item.trigger_key}`}
        tableClassName="min-w-[1100px]"
        columns={[
          {
            key: "automacao",
            label: "Automação",
            render: (item) => (
              <div className="max-w-[280px]">
                <p className="font-semibold text-stone-900">{item.name}</p>
                <p className="mt-1 line-clamp-2 text-xs leading-5 text-stone-500">{item.description || "Sem descrição operacional."}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <AutomationBadge tone={item.trigger_type === "time" ? "blue" : "green"}>
                    {triggerTypeLabel(item.trigger_type)}
                  </AutomationBadge>
                  <AutomationBadge>{item.trigger_key}</AutomationBadge>
                </div>
              </div>
            ),
          },
          {
            key: "condicao",
            label: "Condição",
            render: (item) => <span className="text-sm text-stone-700">{summarizeConditions(item.conditions)}</span>,
          },
          {
            key: "acao",
            label: "Ação principal",
            render: (item) => <span className="text-sm text-stone-700">{summarizeActions(item.actions)}</span>,
          },
          {
            key: "ultima",
            label: "Última execução",
            render: (item) => <span className="text-sm text-stone-700">{formatDateTimeBR(item.lastExecution)}</span>,
          },
          {
            key: "proxima",
            label: "Próxima execução",
            render: (item) => <span className="text-sm text-stone-700">{item.nextExecution}</span>,
          },
          {
            key: "saude",
            label: "Saúde",
            render: (item) => <HealthBadge health={item.health} />,
          },
          {
            key: "status",
            label: "Status",
            render: (item) => <StatusBadge value={item.is_active ? "ativa" : "pausada"} />,
          },
          {
            key: "acoes",
            label: "Ações",
            cellClassName: "min-w-[320px]",
            render: (item) => (
              <div className="flex flex-wrap items-center gap-1.5">
                <Button variant="outline" className="h-8 px-2 text-xs" onClick={() => openEditDrawer(item, "configuracao")}>
                  Editar
                </Button>
                <Button variant="outline" className="h-8 px-2 text-xs" onClick={() => openEditDrawer(item, "simulacao")}>
                  Simular
                </Button>
                <Button variant="outline" className="h-8 px-2 text-xs" onClick={() => openEditDrawer(item, "execucoes")}>
                  Execuções
                </Button>
                <Button variant="outline" className="h-8 px-2 text-xs" onClick={() => openEditDrawer(item, "impacto")}>
                  Impacto
                </Button>
                <Button variant="outline" className="h-8 px-2 text-xs" onClick={() => duplicateMutation.mutate(item.id)} disabled={duplicateMutation.isPending}>
                  <Copy size={12} />
                  Duplicar
                </Button>
                {item.is_active ? (
                  <Button variant="outline" className="h-8 px-2 text-xs" onClick={() => pauseMutation.mutate(item.id)} disabled={pauseMutation.isPending}>
                    Pausar
                  </Button>
                ) : (
                  <Button className="h-8 px-2 text-xs" onClick={() => resumeMutation.mutate(item.id)} disabled={resumeMutation.isPending}>
                    Ativar
                  </Button>
                )}
              </div>
            ),
          },
        ]}
        emptyTitle="Nenhuma automação encontrada"
        emptyDescription="Ajuste filtros ou crie uma automação inicial."
      />

      <Timeline title="Últimas execuções" items={timelineItems} />

      <RightDrawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        title={drawerMode === "create" ? "Nova automação" : selectedAutomation?.name ?? "Automação"}
        description="Configure regra, ações e leitura operacional sem depender de JSON cru."
        widthClassName="w-full sm:max-w-4xl"
      >
        <div className="space-y-4">
          <div className="flex flex-wrap gap-1.5">
            {[
              ["configuracao", "Configuração"],
              ["simulacao", "Simulação"],
              ["execucoes", "Execuções"],
              ["impacto", "Impacto"],
              ["historico", "Histórico"],
            ].map(([id, label]) => (
              <Button
                key={id}
                variant={drawerTab === id ? "default" : "outline"}
                className="h-9 px-3 text-xs"
                onClick={() => setDrawerTab(id as DrawerTab)}
              >
                {label}
              </Button>
            ))}
          </div>

          {drawerTab === "configuracao" ? (
            <AutomationConfigPanel
              form={form}
              setForm={setForm}
              wizardStep={wizardStep}
              setWizardStep={setWizardStep}
              onSave={handleSaveForm}
              onSaveDraft={() => handlePublishChoice(false)}
              onSaveActive={() => handlePublishChoice(true)}
              saving={createMutation.isPending || updateMutation.isPending}
              simulationPayloadJson={simulationPayloadJson}
              setSimulationPayloadJson={setSimulationPayloadJson}
              onSimulate={runDraftSimulation}
              simulationResult={simulateDraftMutation.data ?? null}
              simulationPending={simulateDraftMutation.isPending}
            />
          ) : null}

          {drawerTab === "simulacao" ? (
            <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
              <div className="space-y-3">
                <div className="rounded-lg border border-primary/15 bg-primary/5 p-4">
                  <p className="text-xs font-bold uppercase tracking-wide text-primary">Teste seguro</p>
                  <p className="mt-2 text-sm leading-6 text-stone-700">
                    Esta simulação avalia condições e monta previews sem enviar WhatsApp, alterar conversa, tag ou agenda.
                  </p>
                </div>
                <SimulationPayloadEditor value={simulationPayloadJson} onChange={setSimulationPayloadJson} />
                <Button className="w-full gap-1.5" onClick={runDrawerSavedSimulation} disabled={simulateSavedMutation.isPending || simulateDraftMutation.isPending}>
                  <Sparkles size={15} />
                  {simulateSavedMutation.isPending || simulateDraftMutation.isPending ? "Simulando..." : "Simular disparo"}
                </Button>
                <ManualExecutionPanel
                  enabled={Boolean(selectedAutomationId)}
                  confirmation={manualExecutionConfirmation}
                  onConfirmationChange={setManualExecutionConfirmation}
                  onExecute={runManualExecution}
                  pending={manualExecuteMutation.isPending}
                  result={manualExecuteMutation.data ?? null}
                />
              </div>
              <SimulationResultCard result={(selectedAutomationId ? simulateSavedMutation.data : simulateDraftMutation.data) ?? null} />
            </div>
          ) : null}

          {drawerTab === "execucoes" ? <AutomationRunsPanel runs={selectedRuns} /> : null}

          {drawerTab === "impacto" ? (
            <AutomationImpactPanel automation={selectedAutomation ? buildStats(selectedAutomation, automationsQuery.data.runs) : null} />
          ) : null}

          {drawerTab === "historico" ? (
            <AutomationHistoryPanel
              automation={selectedAutomation ?? null}
              history={historyQuery.data?.data ?? []}
              loading={historyQuery.isLoading}
            />
          ) : null}
        </div>
      </RightDrawer>

      <RightDrawer
        open={simulationOpen}
        onOpenChange={setSimulationOpen}
        title="Simular disparo"
        description="Valide uma automação salva sem executar ações reais."
        widthClassName="w-full sm:max-w-4xl"
      >
        <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
          <div className="space-y-3">
            <div>
              <select
                className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                value={workspaceSimulationAutomationId}
                onChange={(event) => setWorkspaceSimulationAutomationId(event.target.value)}
              >
                <option value="">Escolha uma automação salva</option>
                {(automationsQuery.data.automations ?? []).map((automation) => (
                  <option key={automation.id} value={automation.id}>
                    {automation.name}
                  </option>
                ))}
              </select>
              <FieldHelp>A simulação não envia WhatsApp, não altera status e não agenda jobs.</FieldHelp>
            </div>
            <SimulationPayloadEditor value={simulationPayloadJson} onChange={setSimulationPayloadJson} />
            <Button className="w-full gap-1.5" onClick={runWorkspaceSimulation} disabled={simulateSavedMutation.isPending}>
              <Sparkles size={15} />
              {simulateSavedMutation.isPending ? "Simulando..." : "Simular agora"}
            </Button>
          </div>
          <SimulationResultCard result={simulateSavedMutation.data ?? null} />
        </div>
      </RightDrawer>
    </div>
  );
}

function AutomationConfigPanel({
  form,
  setForm,
  wizardStep,
  setWizardStep,
  onSave,
  onSaveDraft,
  onSaveActive,
  saving,
  simulationPayloadJson,
  setSimulationPayloadJson,
  onSimulate,
  simulationResult,
  simulationPending,
}: {
  form: AutomationFormState;
  setForm: React.Dispatch<React.SetStateAction<AutomationFormState>>;
  wizardStep: WizardStepId;
  setWizardStep: (step: WizardStepId) => void;
  onSave: () => void;
  onSaveDraft: () => void;
  onSaveActive: () => void;
  saving: boolean;
  simulationPayloadJson: string;
  setSimulationPayloadJson: (value: string) => void;
  onSimulate: () => void;
  simulationResult: AutomationSimulationResult | null;
  simulationPending: boolean;
}) {
  const messagePreview = getFirstMessage(form.actions);
  const [draggingActionId, setDraggingActionId] = useState<string | null>(null);
  const activeStepIndex = WIZARD_STEPS.findIndex((step) => step.id === wizardStep);
  const goToPreviousStep = () => setWizardStep(WIZARD_STEPS[Math.max(0, activeStepIndex - 1)].id);
  const goToNextStep = () => setWizardStep(WIZARD_STEPS[Math.min(WIZARD_STEPS.length - 1, activeStepIndex + 1)].id);
  const reorderAction = (fromId: string, toId: string) => {
    if (fromId === toId) return;
    setForm((current) => {
      const fromIndex = current.actions.findIndex((item) => item.id === fromId);
      const toIndex = current.actions.findIndex((item) => item.id === toId);
      if (fromIndex < 0 || toIndex < 0) return current;
      return { ...current, actions: moveArrayItem(current.actions, fromIndex, toIndex) };
    });
  };
  const moveActionByStep = (actionId: string, direction: -1 | 1) => {
    setForm((current) => {
      const fromIndex = current.actions.findIndex((item) => item.id === actionId);
      const toIndex = fromIndex + direction;
      if (fromIndex < 0 || toIndex < 0 || toIndex >= current.actions.length) return current;
      return { ...current, actions: moveArrayItem(current.actions, fromIndex, toIndex) };
    });
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-2 md:grid-cols-3 xl:grid-cols-6">
        {WIZARD_STEPS.map((step, index) => (
          <button
            key={step.id}
            type="button"
            onClick={() => setWizardStep(step.id)}
            className={cn(
              "rounded-lg border p-3 text-left transition",
              wizardStep === step.id ? "border-primary bg-primary/10 text-primary shadow-sm" : "border-stone-200 bg-white text-stone-600 hover:border-primary/40",
            )}
          >
            <span className="text-[11px] font-bold uppercase tracking-wide">Etapa {index + 1}</span>
            <span className="mt-1 block text-sm font-semibold">{step.label}</span>
            <span className="mt-1 block text-xs leading-5 opacity-80">{step.helper}</span>
          </button>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
        <div className="space-y-4">
          {wizardStep === "objetivo" ? (
            <section className="rounded-lg border border-stone-200 bg-white p-4">
              <div className="flex items-start gap-3">
                <Settings2 size={18} className="mt-1 text-primary" />
                <div>
                  <p className="font-semibold text-stone-900">Objetivo operacional</p>
                  <p className="text-sm text-stone-600">Dê contexto para a equipe entender quando usar, pausar ou revisar esta automação.</p>
                </div>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <div>
                  <Input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} placeholder="Nome da automação" />
                  <FieldHelp>Nome usado na lista, nos logs e no histórico operacional.</FieldHelp>
                </div>
                <div>
                  <select
                    className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                    value=""
                    onChange={(event) => {
                      const playbook = PLAYBOOKS.find((item) => item.id === event.target.value);
                      if (playbook) setForm(playbookToForm(playbook));
                    }}
                  >
                    <option value="">Playbook base opcional</option>
                    {PLAYBOOKS.map((playbook) => (
                      <option key={playbook.id} value={playbook.id}>
                        {playbook.name}
                      </option>
                    ))}
                  </select>
                  <FieldHelp>Carrega um ponto de partida real; você ainda pode revisar antes de publicar.</FieldHelp>
                </div>
                <div className="md:col-span-2">
                  <Input value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} placeholder="Objetivo operacional / descrição" />
                  <FieldHelp>Exemplo: recuperar faltas sem sobrecarregar a recepção.</FieldHelp>
                </div>
              </div>
              <label className="mt-4 flex items-center gap-2 text-sm text-stone-700">
                <input
                  type="checkbox"
                  checked={form.isActive}
                  onChange={(event) => setForm((current) => ({ ...current, isActive: event.target.checked }))}
                />
                Ativar ao salvar
              </label>
            </section>
          ) : null}

          {wizardStep === "disparo" ? (
            <section className="rounded-lg border border-stone-200 bg-white p-4">
          <div className="flex items-start gap-3">
            <Settings2 size={18} className="mt-1 text-primary" />
            <div>
              <p className="font-semibold text-stone-900">Disparo</p>
              <p className="text-sm text-stone-600">Defina o gatilho real e a janela mínima quando for uma rotina de tempo.</p>
            </div>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <div>
              <select
                className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                value={form.triggerType}
                onChange={(event) => setForm((current) => ({ ...current, triggerType: event.target.value as TriggerType }))}
              >
                <option value="event">Evento</option>
                <option value="time">Tempo</option>
              </select>
              <FieldHelp>Evento escuta uma ação do sistema; tempo é verificado pelo scheduler.</FieldHelp>
            </div>
            <div>
              <Input value={form.triggerKey} onChange={(event) => setForm((current) => ({ ...current, triggerKey: event.target.value }))} placeholder="Gatilho" />
              <FieldHelp>{TRIGGER_HELP[form.triggerKey] ?? "Chave usada pelo motor de automações."}</FieldHelp>
            </div>
            <div>
              <Input
                type="number"
                min={1}
                value={form.windowMinutes}
                onChange={(event) => setForm((current) => ({ ...current, windowMinutes: event.target.value }))}
                disabled={form.triggerType !== "time"}
                placeholder="Janela mínima em minutos"
              />
              <FieldHelp>Usado só em automações de tempo para evitar repetição excessiva.</FieldHelp>
            </div>
            <div>
              <Input
                type="number"
                min={1}
                value={form.retryAttempts}
                onChange={(event) => setForm((current) => ({ ...current, retryAttempts: event.target.value }))}
                placeholder="Máximo de tentativas"
              />
              <FieldHelp>Política salva para execução e evolução do retry.</FieldHelp>
            </div>
          </div>
        </section>
          ) : null}

          {wizardStep === "regras" ? (
            <section className="rounded-lg border border-stone-200 bg-white p-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="font-semibold text-stone-900">Regras de disparo</p>
              <p className="text-sm text-stone-600">Condições simples viram payload compatível com o backend atual.</p>
            </div>
            <div className="flex gap-2">
              <Button
                variant={form.conditionsMode === "visual" ? "default" : "outline"}
                className="h-8 px-3 text-xs"
                onClick={() => setForm((current) => ({ ...current, conditionsMode: "visual" }))}
              >
                Visual
              </Button>
              <Button
                variant={form.conditionsMode === "json" ? "default" : "outline"}
                className="h-8 px-3 text-xs"
                onClick={() =>
                  setForm((current) => ({
                    ...current,
                    conditionsMode: "json",
                    conditionsJson: JSON.stringify(conditionsFromForm({ ...current, conditionsMode: "visual" }), null, 2),
                  }))
                }
              >
                Modo JSON
              </Button>
            </div>
          </div>

          {form.conditionsMode === "visual" ? (
            <div className="mt-4 space-y-2">
              {form.conditions.length ? (
                form.conditions.map((condition) => (
                  <div key={condition.id} className="grid gap-2 rounded-lg border border-stone-200 bg-stone-50 p-3 md:grid-cols-[1fr_1fr_1.4fr_auto]">
                    <select
                      className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm"
                      value={condition.field}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          conditions: current.conditions.map((item) => (item.id === condition.id ? { ...item, field: event.target.value } : item)),
                        }))
                      }
                    >
                      {CONDITION_FIELDS.map((field) => (
                        <option key={field.value} value={field.value}>
                          {field.label}
                        </option>
                      ))}
                    </select>
                    <select
                      className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm"
                      value={condition.operator}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          conditions: current.conditions.map((item) =>
                            item.id === condition.id ? { ...item, operator: event.target.value as ConditionOperator } : item,
                          ),
                        }))
                      }
                    >
                      {CONDITION_OPERATORS.map((operator) => (
                        <option key={operator.value} value={operator.value}>
                          {operator.label}
                        </option>
                      ))}
                    </select>
                    <Input
                      value={condition.value}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          conditions: current.conditions.map((item) => (item.id === condition.id ? { ...item, value: event.target.value } : item)),
                        }))
                      }
                      placeholder={condition.operator === "in" ? "pendente, aberto, aguardando" : "Valor"}
                    />
                    <Button
                      variant="outline"
                      className="h-10 px-3 text-xs"
                      onClick={() =>
                        setForm((current) => ({
                          ...current,
                          conditions: current.conditions.filter((item) => item.id !== condition.id),
                        }))
                      }
                    >
                      Remover
                    </Button>
                  </div>
                ))
              ) : (
                <div className="rounded-lg border border-dashed border-stone-300 bg-stone-50 p-4 text-sm text-stone-600">
                  Sem condições adicionais. A automação dispara sempre que o gatilho real for recebido.
                </div>
              )}
              <Button
                variant="outline"
                className="gap-1.5"
                onClick={() =>
                  setForm((current) => ({
                    ...current,
                    conditions: [...current.conditions, { id: createId("condition"), field: "status", operator: "eq", value: "" }],
                  }))
                }
              >
                <Plus size={14} />
                Adicionar condição
              </Button>
            </div>
          ) : (
            <textarea
              className="mt-4 min-h-[150px] w-full rounded-md border border-stone-300 bg-white p-3 text-xs text-stone-800 outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
              value={form.conditionsJson}
              onChange={(event) => setForm((current) => ({ ...current, conditionsJson: event.target.value }))}
            />
          )}
            </section>
          ) : null}

          {wizardStep === "acoes" ? (
            <section className="rounded-lg border border-stone-200 bg-white p-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="font-semibold text-stone-900">Ações reais</p>
              <p className="text-sm text-stone-600">Somente ações suportadas pelo executor atual ficam disponíveis.</p>
            </div>
            <select
              className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm"
              value=""
              onChange={(event) => {
                const type = event.target.value as SupportedActionType;
                if (!type) return;
                setForm((current) => ({ ...current, actions: [...current.actions, createActionDraft(type)] }));
              }}
            >
              <option value="">Adicionar ação</option>
              {Object.entries(SUPPORTED_ACTION_LABELS).map(([type, label]) => (
                <option key={type} value={type}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          <div className="mt-4 space-y-3">
            {form.actions.map((action, index) => (
              <div
                key={action.id}
                draggable
                onDragStart={() => setDraggingActionId(action.id)}
                onDragOver={(event) => event.preventDefault()}
                onDrop={() => {
                  if (draggingActionId) reorderAction(draggingActionId, action.id);
                  setDraggingActionId(null);
                }}
                onDragEnd={() => setDraggingActionId(null)}
                className={cn(
                  "rounded-lg border border-stone-200 bg-stone-50 p-3 transition",
                  draggingActionId === action.id ? "border-primary bg-primary/5 opacity-70" : "",
                )}
              >
                <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                  <div className="flex items-center gap-2">
                    <span className="cursor-grab rounded-md bg-white p-1.5 text-stone-500" title="Arraste para reordenar">
                      <GripVertical size={14} />
                    </span>
                    <Badge className="bg-white text-stone-700">#{index + 1}</Badge>
                    <p className="font-semibold text-stone-900">{SUPPORTED_ACTION_LABELS[action.type]}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      className="h-9 px-2 text-xs"
                      onClick={() => moveActionByStep(action.id, -1)}
                      disabled={index === 0}
                    >
                      <ArrowUp size={13} />
                    </Button>
                    <Button
                      variant="outline"
                      className="h-9 px-2 text-xs"
                      onClick={() => moveActionByStep(action.id, 1)}
                      disabled={index === form.actions.length - 1}
                    >
                      <ArrowDown size={13} />
                    </Button>
                    <select
                      className="h-9 rounded-md border border-stone-300 bg-white px-3 text-xs"
                      value={action.type}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          actions: current.actions.map((item) =>
                            item.id === action.id ? createActionDraft(event.target.value as SupportedActionType) : item,
                          ),
                        }))
                      }
                    >
                      {Object.entries(SUPPORTED_ACTION_LABELS).map(([type, label]) => (
                        <option key={type} value={type}>
                          {label}
                        </option>
                      ))}
                    </select>
                    <Button
                      variant="outline"
                      className="h-9 px-3 text-xs"
                      onClick={() => setForm((current) => ({ ...current, actions: current.actions.filter((item) => item.id !== action.id) }))}
                    >
                      Remover
                    </Button>
                  </div>
                </div>
                <ActionFields action={action} setForm={setForm} />
              </div>
            ))}
          </div>
            </section>
          ) : null}

          {wizardStep === "simulacao" ? (
            <section className="rounded-lg border border-stone-200 bg-white p-4">
              <div className="flex items-start gap-3">
                <Sparkles size={18} className="mt-1 text-primary" />
                <div>
                  <p className="font-semibold text-stone-900">Simulação segura</p>
                  <p className="text-sm text-stone-600">Valide condições e ações sem enviar mensagens ou alterar dados reais.</p>
                </div>
              </div>
              <div className="mt-4 grid gap-4 lg:grid-cols-[320px_1fr]">
                <div className="space-y-3">
                  <SimulationPayloadEditor value={simulationPayloadJson} onChange={setSimulationPayloadJson} />
                  <Button className="w-full gap-1.5" onClick={onSimulate} disabled={simulationPending}>
                    <Sparkles size={15} />
                    {simulationPending ? "Simulando..." : "Simular rascunho"}
                  </Button>
                </div>
                <SimulationResultCard result={simulationResult} />
              </div>
            </section>
          ) : null}

          {wizardStep === "publicacao" ? (
            <section className="rounded-lg border border-stone-200 bg-white p-4">
              <div className="flex items-start gap-3">
                <CheckCircle2 size={18} className="mt-1 text-primary" />
                <div>
                  <p className="font-semibold text-stone-900">Publicação</p>
                  <p className="text-sm text-stone-600">Revise o resumo final antes de salvar como rascunho ou ativar na operação.</p>
                </div>
              </div>
              <div className="mt-4 space-y-3">
                <div className="rounded-lg border border-primary/15 bg-primary/5 p-4">
                  <p className="text-xs font-bold uppercase tracking-wide text-primary">Resumo humano</p>
                  <p className="mt-2 text-sm leading-6 text-stone-700">{humanSummary(form)}</p>
                </div>
                <div className="grid gap-3 md:grid-cols-3">
                  <ImpactMetric label="Tipo" value={triggerTypeLabel(form.triggerType)} icon={<Zap size={16} />} compact />
                  <ImpactMetric label="Condições" value={summarizeConditions(conditionsFromForm({ ...form, conditionsMode: "visual" }))} icon={<Settings2 size={16} />} compact />
                  <ImpactMetric label="Ações" value={summarizeActions(form.actions)} icon={<Send size={16} />} compact />
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" className="gap-1.5" onClick={onSaveDraft} disabled={saving}>
                    <Pause size={15} />
                    {saving ? "Salvando..." : "Salvar como rascunho"}
                  </Button>
                  <Button className="gap-1.5" onClick={onSaveActive} disabled={saving}>
                    <Play size={15} />
                    {saving ? "Salvando..." : "Salvar e ativar"}
                  </Button>
                </div>
              </div>
            </section>
          ) : null}
        </div>

      <aside className="space-y-4">
        <div className="rounded-lg border border-primary/15 bg-primary/5 p-4">
          <p className="text-xs font-bold uppercase tracking-wide text-primary">Resumo humano</p>
          <p className="mt-2 text-sm leading-6 text-stone-700">{humanSummary(form)}</p>
        </div>

        <div className="rounded-lg border border-stone-200 bg-white p-4">
          <div className="flex items-center gap-2">
            <MessageSquareText size={16} className="text-emerald-600" />
            <p className="font-semibold text-stone-900">Preview WhatsApp</p>
          </div>
          {messagePreview ? (
            <div className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm leading-6 text-emerald-950 shadow-inner">
              {messagePreview}
            </div>
          ) : (
            <p className="mt-4 text-sm text-stone-500">Adicione uma ação de mensagem para ver o preview.</p>
          )}
        </div>

        <div className="grid grid-cols-2 gap-2">
          <Button variant="outline" onClick={goToPreviousStep} disabled={activeStepIndex <= 0}>
            Voltar
          </Button>
          <Button variant="outline" onClick={goToNextStep} disabled={activeStepIndex >= WIZARD_STEPS.length - 1}>
            Avançar
          </Button>
        </div>

        <Button className="w-full gap-1.5" onClick={onSave} disabled={saving}>
          <CheckCircle2 size={15} />
          {saving ? "Salvando..." : "Salvar configuração"}
        </Button>
      </aside>
      </div>
    </div>
  );
}

function SimulationPayloadEditor({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <div>
      <div className="rounded-lg border border-stone-200 bg-white p-3">
        <p className="text-xs font-bold uppercase tracking-wide text-stone-500">Payload de teste</p>
        <p className="mt-1 text-xs leading-5 text-stone-500">Use dados parecidos com o evento real. Nada aqui dispara ação de produção.</p>
        <textarea
          className="mt-3 min-h-[220px] w-full rounded-md border border-stone-300 bg-stone-50 p-3 font-mono text-xs text-stone-800 outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      </div>
    </div>
  );
}

function SimulationResultCard({ result }: { result: AutomationSimulationResult | null }) {
  if (!result) {
    return (
      <div className="rounded-lg border border-dashed border-stone-300 bg-stone-50 p-5">
        <p className="font-semibold text-stone-900">Resultado da simulação</p>
        <p className="mt-2 text-sm leading-6 text-stone-600">
          Rode uma simulação para ver se a automação dispararia, quais condições bateram e quais ações seriam preparadas.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className={cn("rounded-lg border p-4", result.will_run ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50")}>
        <div className="flex flex-wrap items-center gap-2">
          <AutomationBadge tone={result.will_run ? "green" : "amber"}>{result.will_run ? "Vai disparar" : "Não vai disparar"}</AutomationBadge>
          <span className="text-sm font-semibold text-stone-900">{result.reason}</span>
        </div>
        <p className="mt-2 text-sm leading-6 text-stone-700">{result.summary}</p>
      </div>

      <div className="rounded-lg border border-stone-200 bg-white p-4">
        <p className="text-xs font-bold uppercase tracking-wide text-stone-500">Condições avaliadas</p>
        {result.condition_evaluations.length ? (
          <div className="mt-3 space-y-2">
            {result.condition_evaluations.map((condition) => (
              <div key={`${condition.field}-${condition.operator}`} className="flex flex-col gap-2 rounded-lg bg-stone-50 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
                <span className="text-sm text-stone-700">
                  {condition.field} {condition.operator} {stringifyUnknown(condition.expected)}
                </span>
                <span className="text-xs text-stone-500">Recebido: {stringifyUnknown(condition.actual)}</span>
                <AutomationBadge tone={condition.matched ? "green" : "red"}>{condition.matched ? "bateu" : "não bateu"}</AutomationBadge>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-sm text-stone-600">Sem condições adicionais; o gatilho é suficiente para disparar.</p>
        )}
      </div>

      <div className="rounded-lg border border-stone-200 bg-white p-4">
        <p className="text-xs font-bold uppercase tracking-wide text-stone-500">Ações preparadas</p>
        {result.actions.length ? (
          <div className="mt-3 space-y-2">
            {result.actions.map((action, index) => (
              <div key={`${action.action}-${index}`} className="rounded-lg bg-stone-50 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-semibold text-stone-900">{action.label ?? action.action ?? "Ação"}</p>
                  <AutomationBadge tone={action.will_execute ? "green" : "amber"}>{action.will_execute ? "preparada" : "ignorada"}</AutomationBadge>
                </div>
                {action.human_reason || action.reason ? <p className="mt-2 text-sm text-amber-700">{action.human_reason ?? action.reason}</p> : null}
                {action.preview ? (
                  <pre className="mt-2 max-h-36 overflow-auto rounded-md bg-white p-2 text-xs text-stone-700">{JSON.stringify(action.preview, null, 2)}</pre>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-sm text-stone-600">Nenhuma ação configurada.</p>
        )}
      </div>

      {result.message_preview ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
          <p className="text-xs font-bold uppercase tracking-wide text-emerald-700">Preview da mensagem</p>
          <p className="mt-3 rounded-lg bg-white p-3 text-sm leading-6 text-emerald-950 shadow-inner">{result.message_preview}</p>
        </div>
      ) : null}
    </div>
  );
}

function ManualExecutionPanel({
  enabled,
  confirmation,
  onConfirmationChange,
  onExecute,
  pending,
  result,
}: {
  enabled: boolean;
  confirmation: string;
  onConfirmationChange: (value: string) => void;
  onExecute: () => void;
  pending: boolean;
  result: AutomationManualExecutionResult | null;
}) {
  return (
    <div className="rounded-lg border border-rose-200 bg-rose-50 p-4">
      <div className="flex items-start gap-2">
        <AlertTriangle size={16} className="mt-0.5 text-rose-700" />
        <div>
          <p className="font-semibold text-rose-950">Execução real</p>
          <p className="mt-1 text-sm leading-6 text-rose-800">
            Use só quando quiser processar de verdade. Se as condições baterem, o backend cria um run e pode enviar mensagem, tag, status ou job.
          </p>
        </div>
      </div>
      <Input
        className="mt-3 bg-white"
        value={confirmation}
        onChange={(event) => onConfirmationChange(event.target.value)}
        placeholder="Digite EXECUTAR"
        disabled={!enabled || pending}
      />
      <Button
        variant="outline"
        className="mt-3 w-full border-rose-300 bg-white text-rose-700 hover:bg-rose-100"
        onClick={onExecute}
        disabled={!enabled || pending || confirmation !== "EXECUTAR"}
      >
        {pending ? "Criando execução..." : "Executar de verdade"}
      </Button>
      {!enabled ? <p className="mt-2 text-xs text-rose-700">Disponível apenas para automações já salvas.</p> : null}
      {result ? (
        <p className="mt-2 text-xs text-rose-700">
          {result.run_created ? `Run criado: ${result.run_id}` : `Nenhum run criado: ${result.simulation.reason}`}
        </p>
      ) : null}
    </div>
  );
}

function ActionFields({
  action,
  setForm,
}: {
  action: ActionDraft;
  setForm: React.Dispatch<React.SetStateAction<AutomationFormState>>;
}) {
  const updateAction = (patch: Partial<ActionDraft>) => {
    setForm((current) => ({
      ...current,
      actions: current.actions.map((item) => (item.id === action.id ? { ...item, ...patch } : item)),
    }));
  };

  if (action.type === "send_message") {
    return (
      <div className="mt-3 grid gap-2 md:grid-cols-[1fr_160px]">
        <Input value={action.body} onChange={(event) => updateAction({ body: event.target.value })} placeholder="Mensagem que será enviada" />
        <Input value={action.to} onChange={(event) => updateAction({ to: event.target.value })} placeholder="Destino fixo opcional" />
      </div>
    );
  }

  if (action.type === "add_tag") {
    return (
      <div className="mt-3 max-w-sm">
        <Input value={action.tag} onChange={(event) => updateAction({ tag: event.target.value })} placeholder="Tag do paciente" />
      </div>
    );
  }

  if (action.type === "alter_status_conversa") {
    return (
      <div className="mt-3 max-w-sm">
        <select
          className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
          value={action.status}
          onChange={(event) => updateAction({ status: event.target.value })}
        >
          <option value="aberta">Aberta</option>
          <option value="aguardando">Aguardando</option>
          <option value="finalizada">Finalizada</option>
        </select>
      </div>
    );
  }

  if (action.type === "agendar_job") {
    return (
      <div className="mt-3 grid gap-2 md:grid-cols-3">
        <Input value={action.jobType} onChange={(event) => updateAction({ jobType: event.target.value })} placeholder="Tipo do job" />
        <Input type="number" min={1} value={action.inMinutes} onChange={(event) => updateAction({ inMinutes: event.target.value })} placeholder="Minutos" />
        <Input type="number" min={1} value={action.maxAttempts} onChange={(event) => updateAction({ maxAttempts: event.target.value })} placeholder="Tentativas" />
      </div>
    );
  }

  return (
    <p className="mt-3 rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-600">
      Esta ação move a conversa para aguardando e aplica a tag operacional de fila humana.
    </p>
  );
}

function AutomationRunsPanel({ runs }: { runs: AutomationRunItem[] }) {
  if (!runs.length) {
    return (
      <div className="rounded-lg border border-dashed border-stone-300 bg-stone-50 p-5 text-sm text-stone-600">
        Nenhuma execução registrada para esta automação.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {runs.slice(0, 20).map((run) => {
        const actions = runActions(run);
        return (
          <div key={run.id} className="rounded-lg border border-stone-200 bg-white p-4">
            <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge value={run.status} />
                <span className="text-sm font-semibold text-stone-900">{formatDateTimeBR(run.finished_at || run.started_at || run.created_at)}</span>
                <AutomationBadge>{numberFormatter.format(run.retries ?? 0)} tentativa(s)</AutomationBadge>
              </div>
              {run.error_message ? <AutomationBadge tone="red">Erro registrado</AutomationBadge> : null}
            </div>
            <div className="mt-3 grid gap-3 lg:grid-cols-2">
              <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
                <p className="text-xs font-bold uppercase tracking-wide text-stone-500">Payload de entrada</p>
                <pre className="mt-2 max-h-40 overflow-auto text-xs text-stone-700">{JSON.stringify(run.trigger_payload || {}, null, 2)}</pre>
              </div>
              <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
                <p className="text-xs font-bold uppercase tracking-wide text-stone-500">Ações executadas</p>
                {actions.length ? (
                  <div className="mt-2 space-y-2 text-sm text-stone-700">
                    {actions.map((action, index) => (
                      <div key={`${run.id}-${index}`} className="rounded-md bg-white px-3 py-2">
                        {String(action.action ?? "ação")} {action.ignored ? "ignorada" : "executada"}
                      </div>
                    ))}
                  </div>
                ) : (
                  <pre className="mt-2 max-h-40 overflow-auto text-xs text-stone-700">{JSON.stringify(run.result_payload || {}, null, 2)}</pre>
                )}
              </div>
            </div>
            {run.error_message ? <p className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{run.error_message}</p> : null}
          </div>
        );
      })}
    </div>
  );
}

function AutomationImpactPanel({ automation }: { automation: AutomationWithStats | null }) {
  if (!automation) {
    return <div className="rounded-lg border border-stone-200 bg-stone-50 p-5 text-sm text-stone-600">Selecione uma automação para ver impacto.</div>;
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <ImpactMetric label="Execuções totais" value={numberFormatter.format(automation.totalRuns)} icon={<Activity size={16} />} />
        <ImpactMetric label="Taxa de sucesso" value={`${percentFormatter.format(automation.successRate)}%`} icon={<CheckCircle2 size={16} />} />
        <ImpactMetric label="Falhas" value={numberFormatter.format(automation.failedRuns)} icon={<AlertTriangle size={16} />} />
        <ImpactMetric label="Mensagens disparadas" value={numberFormatter.format(automation.messagesSent)} icon={<Send size={16} />} />
        <ImpactMetric label="Handoffs" value={numberFormatter.format(automation.handoffs)} icon={<UserRoundCheck size={16} />} />
        <ImpactMetric label="Última execução" value={formatDateTimeBR(automation.lastExecution)} icon={<Clock3 size={16} />} compact />
      </div>
      <div className="rounded-lg border border-stone-200 bg-white p-4">
        <p className="text-xs font-bold uppercase tracking-wide text-stone-500">Leitura operacional</p>
        <p className="mt-2 text-sm leading-6 text-stone-700">
          Saúde atual: {healthLabel(automation.health)}. Próxima execução: {automation.nextExecution}. Os números de mensagens e handoffs são estimados a partir dos resultados registrados em `automation_runs`.
        </p>
      </div>
    </div>
  );
}

function ImpactMetric({ label, value, icon, compact }: { label: string; value: string; icon: React.ReactNode; compact?: boolean }) {
  return (
    <div className="rounded-lg border border-stone-200 bg-white p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-bold uppercase tracking-wide text-stone-500">{label}</p>
        <span className="rounded-lg bg-stone-100 p-2 text-stone-600">{icon}</span>
      </div>
      <p className={cn("mt-3 font-extrabold text-stone-900", compact ? "text-sm" : "text-2xl")}>{value}</p>
    </div>
  );
}

function AutomationHistoryPanel({
  automation,
  history,
  loading,
}: {
  automation: AutomationItem | AutomationWithStats | null;
  history: AutomationHistoryItem[];
  loading: boolean;
}) {
  if (!automation) {
    return <div className="rounded-lg border border-stone-200 bg-stone-50 p-5 text-sm text-stone-600">Selecione uma automação para ver histórico.</div>;
  }

  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-primary/15 bg-primary/5 p-4">
        <p className="text-xs font-bold uppercase tracking-wide text-primary">Trilha operacional real</p>
        <p className="mt-2 text-sm leading-6 text-stone-700">
          Abaixo aparecem eventos registrados em `audit_logs` para esta automação. Mudanças antigas sem auditoria continuam resumidas pelo estado atual.
        </p>
      </div>

      <div className="flex gap-3 rounded-lg border border-stone-200 bg-white p-4">
        <span className="mt-0.5 rounded-lg bg-stone-100 p-2 text-stone-600">
          {automation.is_active ? <Play size={15} /> : <Pause size={15} />}
        </span>
        <div>
          <p className="font-semibold text-stone-900">{automation.is_active ? "Estado atual: ativa" : "Estado atual: pausada"}</p>
          <p className="mt-1 text-sm text-stone-600">
            Criada em {formatDateTimeBR(automation.created_at)}
            {automation.paused_at ? ` • pausada em ${formatDateTimeBR(automation.paused_at)}` : ""}
          </p>
        </div>
      </div>

      {loading ? (
        <div className="rounded-lg border border-stone-200 bg-stone-50 p-5 text-sm text-stone-600">Carregando histórico...</div>
      ) : history.length ? (
        history.map((item) => (
          <div key={item.id} className="flex gap-3 rounded-lg border border-stone-200 bg-white p-4">
            <span className="mt-0.5 rounded-lg bg-stone-100 p-2 text-stone-600">
              {item.action.includes("execute") ? <Zap size={15} /> : item.action.includes("pause") ? <Pause size={15} /> : item.action.includes("resume") ? <Play size={15} /> : <FileClock size={15} />}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                <p className="font-semibold text-stone-900">{historyActionLabel(item.action)}</p>
                <span className="text-xs text-stone-500">{formatDateTimeBR(item.occurred_at)}</span>
              </div>
              <p className="mt-1 text-sm text-stone-600">Usuário: {item.user_id ?? "sistema"}</p>
              {Object.keys(item.metadata || {}).length ? (
                <pre className="mt-3 max-h-32 overflow-auto rounded-md bg-stone-50 p-3 text-xs text-stone-700">{JSON.stringify(item.metadata, null, 2)}</pre>
              ) : null}
            </div>
          </div>
        ))
      ) : (
        <div className="flex gap-3 rounded-lg border border-dashed border-stone-300 bg-stone-50 p-4">
          <span className="mt-0.5 rounded-lg bg-white p-2 text-stone-600">
            <RotateCcw size={15} />
          </span>
          <div>
            <p className="font-semibold text-stone-900">Sem eventos auditados ainda</p>
            <p className="mt-1 text-sm text-stone-600">As próximas criações, edições, pausas, reativações, duplicações e execuções manuais entram aqui automaticamente.</p>
          </div>
        </div>
      )}
    </div>
  );
}

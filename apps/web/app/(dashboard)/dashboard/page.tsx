"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CalendarClock,
  CheckCircle2,
  Clock3,
  Siren,
  Users2,
} from "lucide-react";

import { ApiPage, DashboardKPI } from "@odontoflux/shared-types";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TR,
} from "@odontoflux/ui";

import { ErrorState, LoadingState } from "@/components/page-state";
import { api } from "@/lib/api";

type PeriodPreset = "today" | "7d" | "30d" | "custom";

type DateRange = {
  start: Date;
  end: Date;
};

type AppointmentItem = {
  id: string;
  patient_id: string;
  unit_id: string;
  starts_at: string;
  status: string;
  confirmation_status: string;
  procedure_type: string;
};

type ConversationItem = {
  id: string;
  patient_id: string | null;
  unit_id: string | null;
  assigned_user_id: string | null;
  status: string;
  channel: string;
  ai_summary: string | null;
  last_message_at: string | null;
};

type LeadItem = {
  id: string;
  name: string;
  origin: string | null;
  stage: string;
  temperature: string;
  created_at: string;
};

type PatientItem = {
  id: string;
  full_name: string;
  status: string;
  created_at: string;
};

type UserItem = {
  id: string;
  full_name: string;
  email: string;
  roles: string[];
};

type UnitItem = {
  id: string;
  name: string;
  code: string;
};

type CampaignItem = {
  id: string;
  name: string;
  status: string;
  objective: string;
  scheduled_at: string | null;
  started_at: string | null;
  ended_at: string | null;
};

type DashboardDataset = {
  kpis: DashboardKPI;
  appointments: AppointmentItem[];
  conversations: ConversationItem[];
  leads: LeadItem[];
  patients: PatientItem[];
  users: UserItem[];
  units: UnitItem[];
  campaigns: CampaignItem[];
};

type MetricFormat = "number" | "percent";

type KpiCardData = {
  key: string;
  title: string;
  description: string;
  current: number;
  previous: number;
  format: MetricFormat;
  higherIsBetter: boolean;
};

type AlertSeverity = "critical" | "warning" | "ok";

type AlertItem = {
  title: string;
  description: string;
  severity: AlertSeverity;
};

type QueuePriority = "Alta" | "Média" | "Baixa";

type QueueItem = {
  type: "Consulta" | "Conversa";
  person: string;
  unit: string;
  owner: string;
  time: string;
  priority: QueuePriority;
  action: string;
};

type HorizontalChartItem = {
  label: string;
  value: number;
};

type TimelinePoint = {
  label: string;
  leads: number;
  patients: number;
  appointments: number;
};

type DailyVolumePoint = {
  label: string;
  value: number;
};

const PERIOD_OPTIONS: { id: PeriodPreset; label: string; days?: number }[] = [
  { id: "today", label: "Hoje", days: 1 },
  { id: "7d", label: "7 dias", days: 7 },
  { id: "30d", label: "30 dias", days: 30 },
  { id: "custom", label: "Personalizado" },
];

const numberFormatter = new Intl.NumberFormat("pt-BR");
const percentFormatter = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

const chartPalette = [
  "#0f766e",
  "#14b8a6",
  "#f59e0b",
  "#3b82f6",
  "#ef4444",
  "#8b5cf6",
];

const emptyDashboardData: DashboardDataset = {
  kpis: {
    avg_first_response_minutes: 0,
    avg_resolution_minutes: 0,
    confirmation_rate: 0,
    cancellation_rate: 0,
    no_show_rate: 0,
    no_show_recovery_rate: 0,
    budget_conversion_rate: 0,
    reactivated_patients: 0,
    messages_count: 0,
    leads_by_origin: [],
    performance_by_unit: [],
    performance_by_attendant: [],
    ai_automation_rate: 0,
    ai_handoff_rate: 0,
    avg_first_response_ai_minutes: 0,
    ai_send_failure_rate: 0,
  },
  appointments: [],
  conversations: [],
  leads: [],
  patients: [],
  users: [],
  units: [],
  campaigns: [],
};

function startOfDay(date: Date) {
  const output = new Date(date);
  output.setHours(0, 0, 0, 0);
  return output;
}

function endOfDay(date: Date) {
  const output = new Date(date);
  output.setHours(23, 59, 59, 999);
  return output;
}

function addDays(date: Date, amount: number) {
  const output = new Date(date);
  output.setDate(output.getDate() + amount);
  return output;
}

function localDateKey(dateInput: Date | string) {
  const date = new Date(dateInput);
  const yyyy = String(date.getFullYear());
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function formatDateKey(dateKey: string) {
  const [year, month, day] = dateKey.split("-").map((value) => Number(value));
  const parsed = new Date(year, month - 1, day);
  return parsed.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

function isInRange(dateValue: string | null, range: DateRange) {
  if (!dateValue) return false;
  const target = new Date(dateValue);
  return target >= range.start && target <= range.end;
}

function isSameDay(dateValue: string, reference: Date) {
  const target = new Date(dateValue);
  return (
    target.getFullYear() === reference.getFullYear() &&
    target.getMonth() === reference.getMonth() &&
    target.getDate() === reference.getDate()
  );
}

function asPercent(numerator: number, denominator: number) {
  if (denominator <= 0) return 0;
  return (numerator / denominator) * 100;
}

function formatMetricValue(value: number, format: MetricFormat) {
  if (format === "percent") return `${percentFormatter.format(value)}%`;
  return numberFormatter.format(Math.round(value));
}

function comparisonDelta(current: number, previous: number) {
  if (previous === 0) return current > 0 ? 100 : 0;
  return ((current - previous) / Math.abs(previous)) * 100;
}
function previousRangeFrom(currentRange: DateRange): DateRange {
  const duration = currentRange.end.getTime() - currentRange.start.getTime();
  const previousEnd = new Date(currentRange.start.getTime() - 1);
  const previousStart = new Date(previousEnd.getTime() - duration);
  return { start: previousStart, end: previousEnd };
}

function resolvedRange(
  preset: PeriodPreset,
  customStart: string,
  customEnd: string,
): { range: DateRange; label: string } {
  const now = new Date();

  if (preset === "custom" && customStart && customEnd) {
    const start = startOfDay(new Date(`${customStart}T00:00:00`));
    const end = endOfDay(new Date(`${customEnd}T23:59:59`));
    const fixedStart = start <= end ? start : end;
    const fixedEnd = end >= start ? end : start;
    const label = `${fixedStart.toLocaleDateString("pt-BR")} até ${fixedEnd.toLocaleDateString("pt-BR")}`;
    return { range: { start: fixedStart, end: fixedEnd }, label };
  }

  if (preset === "today") {
    const start = startOfDay(now);
    const end = endOfDay(now);
    return {
      range: { start, end },
      label: "Hoje",
    };
  }

  const chosen = PERIOD_OPTIONS.find((option) => option.id === preset);
  const days = chosen?.days ?? 30;
  const start = startOfDay(addDays(now, -(days - 1)));
  const end = endOfDay(now);

  return {
    range: { start, end },
    label: `Últimos ${days} dias`,
  };
}

function countByDateKey<T>(items: T[], getDate: (item: T) => string | null) {
  const map = new Map<string, number>();

  for (const item of items) {
    const dateValue = getDate(item);
    if (!dateValue) continue;
    const key = localDateKey(dateValue);
    map.set(key, (map.get(key) ?? 0) + 1);
  }

  return map;
}

function severityStyle(severity: AlertSeverity) {
  if (severity === "critical") return "bg-red-100 text-red-700";
  if (severity === "warning") return "bg-amber-100 text-amber-800";
  return "bg-emerald-100 text-emerald-700";
}

function priorityWeight(priority: QueuePriority) {
  if (priority === "Alta") return 3;
  if (priority === "Média") return 2;
  return 1;
}

function campaignReferenceDate(campaign: CampaignItem) {
  return campaign.started_at ?? campaign.scheduled_at ?? campaign.ended_at;
}

function KpiCard({ item }: { item: KpiCardData }) {
  const delta = comparisonDelta(item.current, item.previous);
  const positive = delta >= 0;
  const directionIsGood = item.higherIsBetter ? positive : !positive;
  const signal = positive ? "+" : "";
  const deltaLabel = `${signal}${percentFormatter.format(delta)}%`;

  return (
    <Card className="border-stone-200 bg-white">
      <CardHeader className="space-y-3 pb-2">
        <div className="h-1.5 w-16 rounded-full bg-gradient-to-r from-primary to-accent" />
        <CardDescription className="text-sm font-medium text-stone-600">{item.title}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-3xl font-extrabold tracking-tight">{formatMetricValue(item.current, item.format)}</p>
        <div
          className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold ${
            directionIsGood ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"
          }`}
        >
          {positive ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
          {deltaLabel}
        </div>
        <p className="text-xs text-stone-500">
          Comparação com período anterior: {formatMetricValue(item.previous, item.format)}
        </p>
        <p className="text-xs text-stone-500">{item.description}</p>
      </CardContent>
    </Card>
  );
}

function LineTrendChart({ data }: { data: TimelinePoint[] }) {
  if (!data.length) {
    return <p className="text-sm text-muted-foreground">Sem dados no período selecionado.</p>;
  }

  const maxValue = Math.max(
    1,
    ...data.map((point) => Math.max(point.leads, point.patients, point.appointments)),
  );
  const pointCount = data.length;
  const xStep = pointCount > 1 ? 100 / (pointCount - 1) : 0;

  const makePoints = (values: number[]) =>
    values
      .map((value, index) => {
        const x = pointCount > 1 ? index * xStep : 50;
        const y = 34 - (value / maxValue) * 26;
        return `${x},${y}`;
      })
      .join(" ");

  const leadsPoints = makePoints(data.map((point) => point.leads));
  const patientsPoints = makePoints(data.map((point) => point.patients));
  const appointmentsPoints = makePoints(data.map((point) => point.appointments));

  const midIndex = Math.floor(data.length / 2);
  const lastIndex = data.length - 1;

  return (
    <div className="space-y-3">
      <svg viewBox="0 0 100 40" className="h-44 w-full rounded-lg bg-stone-50 p-2">
        <line x1="0" y1="34" x2="100" y2="34" stroke="#d6d3d1" strokeWidth="0.4" />
        <line x1="0" y1="21" x2="100" y2="21" stroke="#e7e5e4" strokeWidth="0.3" />
        <line x1="0" y1="8" x2="100" y2="8" stroke="#e7e5e4" strokeWidth="0.3" />

        <polyline fill="none" stroke={chartPalette[0]} strokeWidth="1.6" points={leadsPoints} />
        <polyline fill="none" stroke={chartPalette[3]} strokeWidth="1.6" points={patientsPoints} />
        <polyline fill="none" stroke={chartPalette[2]} strokeWidth="1.6" points={appointmentsPoints} />
      </svg>

      <div className="flex items-center gap-3 text-xs text-stone-600">
        <span className="inline-flex items-center gap-1">
          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: chartPalette[0] }} />
          Leads
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: chartPalette[3] }} />
          Pacientes
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: chartPalette[2] }} />
          Consultas
        </span>
      </div>

      <div className="flex justify-between text-xs text-stone-500">
        <span>{data[0]?.label}</span>
        <span>{data[midIndex]?.label}</span>
        <span>{data[lastIndex]?.label}</span>
      </div>
    </div>
  );
}

function HorizontalBars({
  data,
  emptyMessage,
}: {
  data: HorizontalChartItem[];
  emptyMessage: string;
}) {
  if (!data.length) {
    return <p className="text-sm text-muted-foreground">{emptyMessage}</p>;
  }

  const maxValue = Math.max(1, ...data.map((item) => item.value));

  return (
    <div className="space-y-3">
      {data.map((item, index) => {
        const width = (item.value / maxValue) * 100;
        return (
          <div key={item.label} className="space-y-1.5">
            <div className="flex items-center justify-between text-sm">
              <span className="text-stone-700">{item.label}</span>
              <span className="font-semibold text-stone-800">{numberFormatter.format(item.value)}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-stone-200">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${width}%`,
                  backgroundColor: chartPalette[index % chartPalette.length],
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function DonutDistribution({
  data,
}: {
  data: { label: string; value: number; color: string }[];
}) {
  const total = data.reduce((sum, item) => sum + item.value, 0);
  let cumulative = 0;
  const gradientStops = data
    .map((item) => {
      const start = cumulative;
      const amount = total === 0 ? 0 : (item.value / total) * 100;
      cumulative += amount;
      return `${item.color} ${start.toFixed(2)}% ${cumulative.toFixed(2)}%`;
    })
    .join(", ");

  return (
    <div className="grid gap-4 lg:grid-cols-[180px,1fr] lg:items-center">
      <div className="flex justify-center">
        <div
          className="relative h-40 w-40 rounded-full"
          style={{ background: total === 0 ? "#e7e5e4" : `conic-gradient(${gradientStops})` }}
        >
          <div className="absolute left-1/2 top-1/2 flex h-24 w-24 -translate-x-1/2 -translate-y-1/2 flex-col items-center justify-center rounded-full bg-white">
            <span className="text-xl font-bold text-stone-800">{numberFormatter.format(total)}</span>
            <span className="text-xs text-stone-500">consultas</span>
          </div>
        </div>
      </div>
      <div className="space-y-2">
        {data.map((item) => (
          <div key={item.label} className="flex items-center justify-between text-sm">
            <span className="inline-flex items-center gap-2 text-stone-700">
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: item.color }} />
              {item.label}
            </span>
            <span className="font-semibold text-stone-800">{numberFormatter.format(item.value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ColumnVolumeChart({ data, emptyMessage }: { data: DailyVolumePoint[]; emptyMessage: string }) {
  if (!data.length) {
    return <p className="text-sm text-muted-foreground">{emptyMessage}</p>;
  }

  const maxValue = Math.max(1, ...data.map((item) => item.value));
  const midIndex = Math.floor(data.length / 2);
  const lastIndex = data.length - 1;

  return (
    <div className="space-y-3">
      <div className="flex h-40 items-end gap-1 rounded-lg border border-stone-200 bg-stone-50 p-3">
        {data.map((item, index) => {
          const height = Math.max(8, (item.value / maxValue) * 120);
          return (
            <div
              key={`${item.label}-${index}`}
              className="min-w-0 flex-1 rounded-t-sm"
              style={{
                height: `${height}px`,
                backgroundColor: chartPalette[1],
                opacity: index === lastIndex ? 1 : 0.75,
              }}
              title={`${item.label}: ${numberFormatter.format(item.value)} mensagens`}
            />
          );
        })}
      </div>
      <div className="flex justify-between text-xs text-stone-500">
        <span>{data[0]?.label}</span>
        <span>{data[midIndex]?.label}</span>
        <span>{data[lastIndex]?.label}</span>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [periodPreset, setPeriodPreset] = useState<PeriodPreset>("30d");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");

  const { data, isLoading, isError } = useQuery<DashboardDataset>({
    queryKey: ["dashboard-premium"],
    queryFn: async () => {
      const [
        kpisResponse,
        appointmentsResponse,
        conversationsResponse,
        leadsResponse,
        patientsResponse,
        usersResponse,
        unitsResponse,
        campaignsResponse,
      ] = await Promise.all([
        api.get<DashboardKPI>("/dashboards/kpis"),
        api.get<ApiPage<AppointmentItem>>("/appointments", {
          params: { limit: 100, offset: 0 },
        }),
        api.get<ApiPage<ConversationItem>>("/conversations", {
          params: { limit: 100, offset: 0 },
        }),
        api.get<ApiPage<LeadItem>>("/leads", {
          params: { limit: 100, offset: 0 },
        }),
        api.get<ApiPage<PatientItem>>("/patients", {
          params: { limit: 100, offset: 0 },
        }),
        api.get<ApiPage<UserItem>>("/users", {
          params: { limit: 100, offset: 0 },
        }),
        api.get<ApiPage<UnitItem>>("/units", {
          params: { limit: 100, offset: 0 },
        }),
        api.get<ApiPage<CampaignItem>>("/campaigns", {
          params: { limit: 100, offset: 0 },
        }),
      ]);

      return {
        kpis: kpisResponse.data,
        appointments: appointmentsResponse.data.data,
        conversations: conversationsResponse.data.data,
        leads: leadsResponse.data.data,
        patients: patientsResponse.data.data,
        users: usersResponse.data.data,
        units: unitsResponse.data.data,
        campaigns: campaignsResponse.data.data,
      };
    },
  });

  const activeRange = useMemo(
    () => resolvedRange(periodPreset, customStart, customEnd),
    [periodPreset, customStart, customEnd],
  );

  const previousRange = useMemo(() => previousRangeFrom(activeRange.range), [activeRange.range]);
  const dataset = data ?? emptyDashboardData;

  const usersById = useMemo(
    () => new Map(dataset.users.map((user) => [user.id, user.full_name])),
    [dataset.users],
  );
  const unitsById = useMemo(
    () => new Map(dataset.units.map((unit) => [unit.id, unit.name])),
    [dataset.units],
  );
  const patientsById = useMemo(
    () => new Map(dataset.patients.map((patient) => [patient.id, patient.full_name])),
    [dataset.patients],
  );

  const appointmentsCurrent = useMemo(
    () => dataset.appointments.filter((item) => isInRange(item.starts_at, activeRange.range)),
    [dataset.appointments, activeRange.range],
  );
  const appointmentsPrevious = useMemo(
    () => dataset.appointments.filter((item) => isInRange(item.starts_at, previousRange)),
    [dataset.appointments, previousRange],
  );

  const conversationsCurrent = useMemo(
    () => dataset.conversations.filter((item) => isInRange(item.last_message_at, activeRange.range)),
    [dataset.conversations, activeRange.range],
  );
  const conversationsPrevious = useMemo(
    () => dataset.conversations.filter((item) => isInRange(item.last_message_at, previousRange)),
    [dataset.conversations, previousRange],
  );

  const leadsCurrent = useMemo(
    () => dataset.leads.filter((item) => isInRange(item.created_at, activeRange.range)),
    [dataset.leads, activeRange.range],
  );
  const leadsPrevious = useMemo(
    () => dataset.leads.filter((item) => isInRange(item.created_at, previousRange)),
    [dataset.leads, previousRange],
  );

  const patientsCurrent = useMemo(
    () => dataset.patients.filter((item) => isInRange(item.created_at, activeRange.range)),
    [dataset.patients, activeRange.range],
  );
  const patientsPrevious = useMemo(
    () => dataset.patients.filter((item) => isInRange(item.created_at, previousRange)),
    [dataset.patients, previousRange],
  );

  const campaignsCurrent = useMemo(
    () =>
      dataset.campaigns.filter((item) => {
        const reference = campaignReferenceDate(item);
        return isInRange(reference, activeRange.range);
      }),
    [dataset.campaigns, activeRange.range],
  );
  const campaignsPrevious = useMemo(
    () =>
      dataset.campaigns.filter((item) => {
        const reference = campaignReferenceDate(item);
        return isInRange(reference, previousRange);
      }),
    [dataset.campaigns, previousRange],
  );

  const confirmationsCurrent = appointmentsCurrent.filter(
    (item) => item.confirmation_status === "confirmada",
  ).length;
  const confirmationsPrevious = appointmentsPrevious.filter(
    (item) => item.confirmation_status === "confirmada",
  ).length;
  const cancellationsCurrent = appointmentsCurrent.filter((item) => item.status === "cancelada").length;
  const cancellationsPrevious = appointmentsPrevious.filter((item) => item.status === "cancelada").length;
  const noShowCurrent = appointmentsCurrent.filter((item) => item.status === "falta").length;
  const noShowPrevious = appointmentsPrevious.filter((item) => item.status === "falta").length;
  const activeConversationsCurrent = conversationsCurrent.filter((item) =>
    ["aberta", "aguardando"].includes(item.status),
  ).length;
  const activeConversationsPrevious = conversationsPrevious.filter((item) =>
    ["aberta", "aguardando"].includes(item.status),
  ).length;
  const hotLeadsCurrent = leadsCurrent.filter((item) => item.temperature === "quente").length;
  const hotLeadsPrevious = leadsPrevious.filter((item) => item.temperature === "quente").length;
  const activeCampaignsCurrent = campaignsCurrent.filter((item) =>
    ["em_execucao", "agendada"].includes(item.status),
  ).length;
  const activeCampaignsPrevious = campaignsPrevious.filter((item) =>
    ["em_execucao", "agendada"].includes(item.status),
  ).length;
  const waitingConversationsCurrent = conversationsCurrent.filter((item) => item.status === "aguardando").length;
  const waitingConversationsPrevious = conversationsPrevious.filter((item) => item.status === "aguardando").length;
  const messagesInPeriodCurrent = conversationsCurrent.length;
  const messagesInPeriodPrevious = conversationsPrevious.length;
  const consultationsTodayCurrent = dataset.appointments.filter((item) =>
    isSameDay(item.starts_at, new Date()),
  ).length;
  const consultationsTodayPrevious = dataset.appointments.filter((item) => {
    const yesterday = addDays(new Date(), -1);
    return isSameDay(item.starts_at, yesterday);
  }).length;

  const firstResponsePrevious = Math.max(
    0,
    dataset.kpis.avg_first_response_minutes +
      (activeConversationsPrevious - activeConversationsCurrent) * 0.25,
  );
  const resolutionPrevious = Math.max(
    0,
    dataset.kpis.avg_resolution_minutes +
      (activeConversationsPrevious - activeConversationsCurrent) * 0.4,
  );
  const noShowRecoveryPrevious = Math.max(
    0,
    dataset.kpis.no_show_recovery_rate + (noShowPrevious - noShowCurrent) * 1.2,
  );
  const budgetConversionPrevious = Math.max(
    0,
    dataset.kpis.budget_conversion_rate + (hotLeadsPrevious - hotLeadsCurrent) * 0.8,
  );
  const reactivatedPatientsPrevious = Math.max(
    0,
    dataset.kpis.reactivated_patients + (patientsPrevious.length - patientsCurrent.length),
  );

  const kpiCards: KpiCardData[] = [
    {
      key: "avg-first-response",
      title: "Tempo médio da 1ª resposta",
      description: "Velocidade inicial de atendimento no WhatsApp.",
      current: dataset.kpis.avg_first_response_minutes,
      previous: firstResponsePrevious,
      format: "number",
      higherIsBetter: false,
    },
    {
      key: "avg-resolution",
      title: "Tempo médio de resolução",
      description: "Tempo total para concluir um atendimento.",
      current: dataset.kpis.avg_resolution_minutes,
      previous: resolutionPrevious,
      format: "number",
      higherIsBetter: false,
    },
    {
      key: "confirmation-rate",
      title: "Taxa de confirmação",
      description: "Percentual de consultas confirmadas no período.",
      current: asPercent(confirmationsCurrent, appointmentsCurrent.length),
      previous: asPercent(confirmationsPrevious, appointmentsPrevious.length),
      format: "percent",
      higherIsBetter: true,
    },
    {
      key: "cancellation-rate",
      title: "Taxa de cancelamento",
      description: "Cancelamentos registrados na agenda.",
      current: asPercent(cancellationsCurrent, appointmentsCurrent.length),
      previous: asPercent(cancellationsPrevious, appointmentsPrevious.length),
      format: "percent",
      higherIsBetter: false,
    },
    {
      key: "no-show-rate",
      title: "Taxa de no-show",
      description: "Faltas sem comparecimento na agenda.",
      current: asPercent(noShowCurrent, appointmentsCurrent.length),
      previous: asPercent(noShowPrevious, appointmentsPrevious.length),
      format: "percent",
      higherIsBetter: false,
    },
    {
      key: "no-show-recovery",
      title: "Recuperação de faltas",
      description: "Retomadas após faltas recentes.",
      current: dataset.kpis.no_show_recovery_rate,
      previous: noShowRecoveryPrevious,
      format: "percent",
      higherIsBetter: true,
    },
    {
      key: "budget-conversion",
      title: "Conversão de orçamento",
      description: "Orçamentos convertidos em consulta.",
      current: dataset.kpis.budget_conversion_rate,
      previous: budgetConversionPrevious,
      format: "percent",
      higherIsBetter: true,
    },
    {
      key: "reactivated-patients",
      title: "Pacientes reativados",
      description: "Pacientes que voltaram ao funil ativo.",
      current: dataset.kpis.reactivated_patients,
      previous: reactivatedPatientsPrevious,
      format: "number",
      higherIsBetter: true,
    },
    {
      key: "messages-period",
      title: "Mensagens no período",
      description: "Interações registradas no inbox.",
      current: messagesInPeriodCurrent,
      previous: messagesInPeriodPrevious,
      format: "number",
      higherIsBetter: true,
    },
    {
      key: "consultations-day",
      title: "Consultas do dia",
      description: "Volume da agenda para hoje.",
      current: consultationsTodayCurrent,
      previous: consultationsTodayPrevious,
      format: "number",
      higherIsBetter: true,
    },
    {
      key: "patients-waiting-return",
      title: "Pacientes aguardando retorno",
      description: "Conversas aguardando ação da equipe.",
      current: waitingConversationsCurrent,
      previous: waitingConversationsPrevious,
      format: "number",
      higherIsBetter: false,
    },
    {
      key: "active-campaigns",
      title: "Campanhas engajadas",
      description: "Campanhas em execução ou agendadas.",
      current: activeCampaignsCurrent,
      previous: activeCampaignsPrevious,
      format: "number",
      higherIsBetter: true,
    },
  ];

  const leadsByOrigin = useMemo(() => {
    const grouped = new Map<string, number>();

    for (const lead of leadsCurrent) {
      const origin = lead.origin?.trim() || "Origem não informada";
      grouped.set(origin, (grouped.get(origin) ?? 0) + 1);
    }

    return Array.from(grouped.entries())
      .map(([label, value]) => ({ label, value }))
      .sort((a, b) => b.value - a.value);
  }, [leadsCurrent]);

  const appointmentsByUnit = useMemo(() => {
    const grouped = new Map<string, number>();

    for (const item of appointmentsCurrent) {
      const unitName = unitsById.get(item.unit_id) ?? "Unidade não identificada";
      grouped.set(unitName, (grouped.get(unitName) ?? 0) + 1);
    }

    return Array.from(grouped.entries())
      .map(([label, value]) => ({ label, value }))
      .sort((a, b) => b.value - a.value);
  }, [appointmentsCurrent, unitsById]);
  const conversationsByOwner = useMemo(() => {
    const grouped = new Map<string, number>();

    for (const item of conversationsCurrent) {
      const owner = item.assigned_user_id
        ? usersById.get(item.assigned_user_id) ?? "Responsável não identificado"
        : "Sem responsável";
      grouped.set(owner, (grouped.get(owner) ?? 0) + 1);
    }

    return Array.from(grouped.entries())
      .map(([label, value]) => ({ label, value }))
      .sort((a, b) => b.value - a.value);
  }, [conversationsCurrent, usersById]);

  const appointmentStatusDonut = useMemo(() => {
    const statuses = ["confirmada", "agendada", "falta", "cancelada"];

    return statuses.map((status, index) => ({
      label:
        status === "confirmada"
          ? "Confirmadas"
          : status === "agendada"
            ? "Agendadas"
            : status === "falta"
              ? "Faltas"
              : "Canceladas",
      value: appointmentsCurrent.filter((item) => item.status === status).length,
      color: chartPalette[index],
    }));
  }, [appointmentsCurrent]);

  const timelineData = useMemo(() => {
    const leadByDate = countByDateKey(leadsCurrent, (item) => item.created_at);
    const patientByDate = countByDateKey(patientsCurrent, (item) => item.created_at);
    const appointmentByDate = countByDateKey(appointmentsCurrent, (item) => item.starts_at);

    const timeline: TimelinePoint[] = [];
    for (
      let cursor = startOfDay(activeRange.range.start);
      cursor <= activeRange.range.end;
      cursor = addDays(cursor, 1)
    ) {
      const key = localDateKey(cursor);
      timeline.push({
        label: formatDateKey(key),
        leads: leadByDate.get(key) ?? 0,
        patients: patientByDate.get(key) ?? 0,
        appointments: appointmentByDate.get(key) ?? 0,
      });
    }

    return timeline;
  }, [activeRange.range, leadsCurrent, patientsCurrent, appointmentsCurrent]);

  const messagesVolumeData = useMemo(() => {
    const messageByDate = countByDateKey(conversationsCurrent, (item) => item.last_message_at);
    const timeline: DailyVolumePoint[] = [];

    for (
      let cursor = startOfDay(activeRange.range.start);
      cursor <= activeRange.range.end;
      cursor = addDays(cursor, 1)
    ) {
      const key = localDateKey(cursor);
      timeline.push({
        label: formatDateKey(key),
        value: messageByDate.get(key) ?? 0,
      });
    }

    return timeline;
  }, [activeRange.range, conversationsCurrent]);

  const alerts = useMemo<AlertItem[]>(() => {
    const items: AlertItem[] = [];

    const noShowRate = asPercent(noShowCurrent, appointmentsCurrent.length);
    const pendingConfirmations = appointmentsCurrent.filter(
      (item) => item.confirmation_status === "pendente",
    ).length;
    const waitingConversations = conversationsCurrent.filter(
      (item) => item.status === "aguardando",
    ).length;
    const hotLeadRate = asPercent(hotLeadsCurrent, leadsCurrent.length);
    const campaignsToday = dataset.campaigns.filter(
      (campaign) => campaign.scheduled_at && isSameDay(campaign.scheduled_at, new Date()),
    ).length;

    if (noShowRate > 12) {
      items.push({
        title: "Taxa de faltas acima do ideal",
        description: `A taxa atual está em ${percentFormatter.format(
          noShowRate,
        )}%. Recomendado reforçar confirmação e lembrete automático.`,
        severity: "critical",
      });
    }

    if (pendingConfirmations >= 3) {
      items.push({
        title: "Confirmações pendentes na agenda",
        description: `${pendingConfirmations} consultas ainda sem confirmação no período selecionado.`,
        severity: "warning",
      });
    }

    if (waitingConversations >= 3) {
      items.push({
        title: "Fila de conversas aguardando resposta",
        description: `${waitingConversations} conversas estão aguardando retorno da equipe.`,
        severity: "warning",
      });
    }

    if (hotLeadRate < 25 && leadsCurrent.length > 0) {
      items.push({
        title: "Baixa concentração de leads quentes",
        description: `Somente ${percentFormatter.format(
          hotLeadRate,
        )}% dos leads estão com temperatura quente.`,
        severity: "warning",
      });
    }

    if (campaignsToday > 0) {
      items.push({
        title: "Campanhas agendadas para hoje",
        description: `${campaignsToday} campanha(s) com agenda para hoje. Verifique execução no horário previsto.`,
        severity: "ok",
      });
    }

    if (!items.length) {
      items.push({
        title: "Operação estável",
        description: "Nenhum alerta crítico no período selecionado.",
        severity: "ok",
      });
    }

    return items;
  }, [
    appointmentsCurrent,
    conversationsCurrent,
    leadsCurrent,
    noShowCurrent,
    hotLeadsCurrent,
    dataset.campaigns,
  ]);

  const queueOfDay = useMemo(() => {
    const today = new Date();
    const queue: QueueItem[] = [];

    const todayAppointments = dataset.appointments.filter((item) => isSameDay(item.starts_at, today));
    for (const item of todayAppointments) {
      const startsAt = new Date(item.starts_at);
      const hoursUntil = (startsAt.getTime() - Date.now()) / (1000 * 60 * 60);

      let priority: QueuePriority = "Média";
      if (item.status === "falta") priority = "Alta";
      else if (item.confirmation_status === "pendente" && hoursUntil <= 3) priority = "Alta";
      else if (item.confirmation_status === "confirmada") priority = "Baixa";

      let action = "Acompanhar chegada do paciente";
      if (item.confirmation_status === "pendente") action = "Confirmar presença por WhatsApp";
      if (item.status === "falta") action = "Acionar fluxo de recuperação";

      queue.push({
        type: "Consulta",
        person: patientsById.get(item.patient_id) ?? "Paciente sem cadastro",
        unit: unitsById.get(item.unit_id) ?? "Unidade não identificada",
        owner: "Equipe da unidade",
        time: startsAt.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }),
        priority,
        action,
      });
    }

    const todayConversations = dataset.conversations.filter((item) => {
      if (!["aberta", "aguardando"].includes(item.status)) return false;
      if (!item.last_message_at) return true;
      return isSameDay(item.last_message_at, today);
    });

    for (const item of todayConversations) {
      const priority: QueuePriority = item.status === "aguardando" ? "Alta" : "Média";
      queue.push({
        type: "Conversa",
        person: item.patient_id
          ? patientsById.get(item.patient_id) ?? "Contato sem identificação"
          : "Contato sem identificação",
        unit: item.unit_id ? unitsById.get(item.unit_id) ?? "Unidade não identificada" : "Omnicanal",
        owner: item.assigned_user_id
          ? usersById.get(item.assigned_user_id) ?? "Responsável não identificado"
          : "Sem responsável",
        time: item.last_message_at
          ? new Date(item.last_message_at).toLocaleTimeString("pt-BR", {
              hour: "2-digit",
              minute: "2-digit",
            })
          : "--:--",
        priority,
        action: "Responder e registrar próximo passo",
      });
    }

    return queue
      .sort((left, right) => priorityWeight(right.priority) - priorityWeight(left.priority))
      .slice(0, 10);
  }, [dataset.appointments, dataset.conversations, patientsById, unitsById, usersById]);

  const recoveryOpportunities = useMemo(() => {
    const opportunities: { title: string; detail: string; action: string }[] = [];

    const missedAppointments = appointmentsCurrent.filter((item) => item.status === "falta").length;
    if (missedAppointments > 0) {
      opportunities.push({
        title: "Pacientes com falta recente",
        detail: `${missedAppointments} consulta(s) com status de falta no período.`,
        action: "Acionar automação de recuperação em até 24h.",
      });
    }

    const budgetFollowUp = leadsCurrent.filter((lead) =>
      ["orcamento_enviado", "qualificado"].includes(lead.stage),
    ).length;
    if (budgetFollowUp > 0) {
      opportunities.push({
        title: "Orçamentos em aberto",
        detail: `${budgetFollowUp} lead(s) precisam de follow-up comercial.`,
        action: "Executar cadência de 2 e 7 dias por WhatsApp.",
      });
    }

    const inactivePatients = dataset.patients.filter((patient) => patient.status === "inativo").length;
    if (inactivePatients > 0) {
      opportunities.push({
        title: "Pacientes inativos",
        detail: `${inactivePatients} paciente(s) podem entrar em campanha de reativação.`,
        action: "Segmentar por interesse e unidade para disparo.",
      });
    }

    if (!opportunities.length) {
      opportunities.push({
        title: "Sem oportunidades críticas",
        detail: "Não há pendências expressivas de recuperação neste período.",
        action: "Manter rotina de acompanhamento atual.",
      });
    }

    return opportunities.slice(0, 4);
  }, [appointmentsCurrent, dataset.patients, leadsCurrent]);

  const receptionSummary = useMemo(() => {
    const today = new Date();
    const todayAppointments = dataset.appointments.filter((item) => isSameDay(item.starts_at, today));
    const confirmed = todayAppointments.filter(
      (item) => item.confirmation_status === "confirmada",
    ).length;
    const pending = todayAppointments.filter((item) => item.confirmation_status === "pendente").length;
    const canceled = todayAppointments.filter((item) => item.status === "cancelada").length;
    const noShow = todayAppointments.filter((item) => item.status === "falta").length;

    return {
      total: todayAppointments.length,
      confirmed,
      pending,
      canceled,
      noShow,
    };
  }, [dataset.appointments]);

  if (isLoading) return <LoadingState message="Carregando visão operacional..." />;
  if (isError || !data) return <ErrorState message="Não foi possível carregar o dashboard operacional." />;

  return (
    <div className="space-y-6">
      <Card className="border-primary/20 bg-white">
        <CardHeader className="gap-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-1">
              <h1 className="text-3xl font-bold tracking-tight">Dashboard operacional</h1>
              <p className="text-sm text-stone-600">
                Visão executiva da operação comercial e assistencial da clínica.
              </p>
            </div>
            <div className="flex flex-col items-start gap-2 rounded-lg border border-stone-200 bg-stone-50 px-4 py-3">
              <span className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                Período analisado
              </span>
              <span className="text-sm font-semibold text-stone-800">{activeRange.label}</span>
              <span className="text-xs text-stone-500">
                Comparação automática com período anterior equivalente.
              </span>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {PERIOD_OPTIONS.map((option) => (
              <Button
                key={option.id}
                variant={periodPreset === option.id ? "default" : "outline"}
                onClick={() => setPeriodPreset(option.id)}
                className="h-9"
              >
                {option.label}
              </Button>
            ))}
          </div>

          {periodPreset === "custom" ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:max-w-xl">
              <div className="space-y-1">
                <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                  Data inicial
                </label>
                <Input type="date" value={customStart} onChange={(event) => setCustomStart(event.target.value)} />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                  Data final
                </label>
                <Input type="date" value={customEnd} onChange={(event) => setCustomEnd(event.target.value)} />
              </div>
            </div>
          ) : null}
        </CardHeader>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {kpiCards.map((item) => (
          <KpiCard key={item.key} item={item} />
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Atividade operacional no período</CardTitle>
            <CardDescription>
              Evolução diária de leads, pacientes e consultas para leitura de ritmo operacional.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <LineTrendChart data={timelineData} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Distribuição da agenda</CardTitle>
            <CardDescription>Status das consultas no período selecionado.</CardDescription>
          </CardHeader>
          <CardContent>
            <DonutDistribution data={appointmentStatusDonut} />
          </CardContent>
        </Card>
      </div>
      <div className="grid gap-4 xl:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Leads por origem</CardTitle>
            <CardDescription>Fontes que mais geram demanda qualificada.</CardDescription>
          </CardHeader>
          <CardContent>
            <HorizontalBars
              data={leadsByOrigin}
              emptyMessage="Ainda não há leads no período para consolidar origem."
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Performance por unidade</CardTitle>
            <CardDescription>Consultas distribuídas por unidade operacional.</CardDescription>
          </CardHeader>
          <CardContent>
            <HorizontalBars
              data={appointmentsByUnit}
              emptyMessage="Sem volume de consultas no período para avaliar unidades."
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Volume de mensagens por período</CardTitle>
            <CardDescription>Evolução diária do inbox para gestão de capacidade.</CardDescription>
          </CardHeader>
          <CardContent>
            <ColumnVolumeChart
              data={messagesVolumeData}
              emptyMessage="Sem mensagens no período para construir série histórica."
            />
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr,1.4fr]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Siren size={18} className="text-amber-600" />
              Alertas operacionais
            </CardTitle>
            <CardDescription>
              Riscos e desvios que merecem atuação tática imediata.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {alerts.map((alert) => (
              <div key={alert.title} className="rounded-lg border border-stone-200 p-3">
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm font-semibold text-stone-800">{alert.title}</p>
                  <Badge className={severityStyle(alert.severity)}>
                    {alert.severity === "critical"
                      ? "Crítico"
                      : alert.severity === "warning"
                        ? "Atenção"
                        : "Estável"}
                  </Badge>
                </div>
                <p className="mt-1 text-xs text-stone-600">{alert.description}</p>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CalendarClock size={18} className="text-primary" />
              Fila do dia
            </CardTitle>
            <CardDescription>
              Priorização operacional de hoje com foco em atendimento e conversão.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {queueOfDay.length ? (
              <div className="overflow-x-auto">
                <Table>
                  <THead>
                    <TR>
                      <TH>Tipo</TH>
                      <TH>Pessoa</TH>
                      <TH>Unidade</TH>
                      <TH>Responsável</TH>
                      <TH>Horário</TH>
                      <TH>Prioridade</TH>
                      <TH>Ação recomendada</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {queueOfDay.map((item, index) => (
                      <TR key={`${item.type}-${item.person}-${index}`}>
                        <TD>{item.type}</TD>
                        <TD>{item.person}</TD>
                        <TD>{item.unit}</TD>
                        <TD>{item.owner}</TD>
                        <TD>{item.time}</TD>
                        <TD>
                          <Badge
                            className={
                              item.priority === "Alta"
                                ? "bg-red-100 text-red-700"
                                : item.priority === "Média"
                                  ? "bg-amber-100 text-amber-800"
                                  : "bg-emerald-100 text-emerald-700"
                            }
                          >
                            {item.priority}
                          </Badge>
                        </TD>
                        <TD>{item.action}</TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </div>
            ) : (
              <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-700">
                <CheckCircle2 size={16} />
                Nenhuma pendência crítica na fila de hoje.
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Oportunidades de recuperação</CardTitle>
            <CardDescription>
              Itens com maior potencial de ganho rápido em receita e comparecimento.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {recoveryOpportunities.map((item) => (
              <div key={item.title} className="rounded-lg border border-stone-200 bg-stone-50 p-3">
                <p className="text-sm font-semibold text-stone-800">{item.title}</p>
                <p className="mt-1 text-xs text-stone-600">{item.detail}</p>
                <p className="mt-1 text-xs font-medium text-primary">{item.action}</p>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Resumo da recepção</CardTitle>
            <CardDescription>
              Situação do atendimento de hoje para acompanhamento da equipe front-desk.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Consultas do dia</p>
              <p className="mt-1 text-2xl font-bold text-stone-800">{numberFormatter.format(receptionSummary.total)}</p>
            </div>
            <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Confirmadas</p>
              <p className="mt-1 text-2xl font-bold text-emerald-700">{numberFormatter.format(receptionSummary.confirmed)}</p>
            </div>
            <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Pendentes</p>
              <p className="mt-1 text-2xl font-bold text-amber-700">{numberFormatter.format(receptionSummary.pending)}</p>
            </div>
            <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Canceladas / faltas</p>
              <p className="mt-1 text-2xl font-bold text-rose-700">
                {numberFormatter.format(receptionSummary.canceled + receptionSummary.noShow)}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users2 size={18} className="text-primary" />
              Distribuição por responsável
            </CardTitle>
            <CardDescription>
              Conversas ativas distribuídas por usuário para balanceamento de carga.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <HorizontalBars
              data={conversationsByOwner}
              emptyMessage="Sem conversas ativas no período para distribuição da equipe."
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock3 size={18} className="text-primary" />
              Saúde de SLA
            </CardTitle>
            <CardDescription>
              Indicadores de velocidade de atendimento consolidados pelo motor operacional.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-stone-200 bg-stone-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                Tempo médio da 1ª resposta
              </p>
              <p className="mt-2 text-2xl font-bold text-stone-800">
                {percentFormatter.format(dataset.kpis.avg_first_response_minutes)} min
              </p>
              <p className="mt-1 text-xs text-stone-500">
                Base histórica operacional da clínica.
              </p>
            </div>
            <div className="rounded-lg border border-stone-200 bg-stone-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                Tempo médio de resolução
              </p>
              <p className="mt-2 text-2xl font-bold text-stone-800">
                {percentFormatter.format(dataset.kpis.avg_resolution_minutes)} min
              </p>
              <p className="mt-1 text-xs text-stone-500">
                Indicador composto de eficiência do atendimento.
              </p>
            </div>
            <div className="rounded-lg border border-stone-200 bg-stone-50 p-4 sm:col-span-2">
              <div className="flex items-start gap-2 text-sm text-stone-700">
                <AlertTriangle size={16} className="mt-0.5 text-amber-600" />
                <p>
                  Esses dois indicadores ainda são agregados globais. O restante do painel já responde ao
                  filtro de período em tempo real.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

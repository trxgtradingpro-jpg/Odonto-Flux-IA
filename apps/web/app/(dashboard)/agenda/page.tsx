"use client";

import { ChangeEvent, MouseEvent as ReactMouseEvent, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarDays,
  CalendarClock,
  ChevronLeft,
  ChevronRight,
  ChevronsLeftRight,
  ChevronsUpDown,
  Expand,
  FileText,
  List,
  ListFilter,
  Minimize,
  MessageSquare,
  Palette,
  Pencil,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { DataTable, RightDrawer, StatusBadge } from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { useOwnerUnitScope } from "@/hooks/use-owner-unit-scope";
import { useSession } from "@/hooks/use-session";
import { api } from "@/lib/api";
import { ensureDemoSessionId } from "@/lib/demo-session";
import { DEMO_TOUR_TARGETS, dispatchDemoTourEvent, readDemoTourProgress, resolveDemoTourIdentity } from "@/lib/demo-tour";
import {
  ApiPage,
  AppointmentItem,
  ConversationItem,
  DocumentItem,
  PatientItem,
  ProfessionalItem,
  ServiceCatalogItem,
  UnitItem,
} from "@/lib/domain-types";
import { formatCpfBR, formatDateBR, formatDateTimeBR, formatPhoneBR, numberFormatter } from "@/lib/formatters";
import { canAccessPage } from "@/lib/page-access";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from "@odontoflux/ui";

type AgendaDataset = {
  appointments: AppointmentItem[];
  patients: PatientItem[];
  units: UnitItem[];
  professionals: ProfessionalItem[];
  conversations: ConversationItem[];
  documents: DocumentItem[];
  serviceCatalog: ServiceCatalogItem[];
};

const EMPTY_AGENDA_DATASET: AgendaDataset = {
  appointments: [],
  patients: [],
  units: [],
  professionals: [],
  conversations: [],
  documents: [],
  serviceCatalog: [],
};

type AgendaSettingItem = {
  id: string;
  key: string;
  value: unknown;
  is_secret: boolean;
};

type BoardResizeState =
  | {
      axis: "x" | "y";
      startPointer: number;
      startValue: number;
    }
  | null;

type AvailabilityCard = {
  top: number;
  height: number;
  startMinutes: number;
  endMinutes: number;
};

type AvailabilityBookingContext = {
  dayKey: string;
  unitId: string | null;
  unitName: string;
  professionalId: string;
  professionalName: string;
  startsAt: string;
  slotStartMinutes: number;
  slotEndMinutes: number;
};

type RescheduleSlotChoice = {
  id: string;
  label: string;
  startsAt: string;
  endsAt: string;
  professionalId: string;
  professionalName: string;
  unitId: string;
  dayKey: string;
};

type BoardLane = {
  id: string;
  professionalId: string | null;
  professionalName: string;
  unitId: string | null;
  unitName: string;
  label: string;
  color: string;
  workingDays: number[];
  shiftStart: string;
  shiftEnd: string;
  isPlaceholder?: boolean;
};

type EnrichedAppointment = AppointmentItem & {
  patient_name: string;
  patient_phone: string;
  unit_name: string;
  professional_name: string;
  last_conversation: string | null;
};

type AppointmentPatientDetailTab = "resumo" | "procedimentos" | "conversas" | "documentos" | "historico";

const WEEK_DAY_OPTIONS = [
  { value: 0, label: "Dom" },
  { value: 1, label: "Seg" },
  { value: 2, label: "Ter" },
  { value: 3, label: "Qua" },
  { value: 4, label: "Qui" },
  { value: 5, label: "Sex" },
  { value: 6, label: "Sab" },
] as const;

const MONTH_GRID_WEEK_DAY_VALUES = [1, 2, 3, 4, 5, 6, 0] as const;

const APPOINTMENT_STATUS_OPTIONS = [
  { value: "agendada", label: "Agendado" },
  { value: "confirmada", label: "Confirmado" },
  { value: "cancelada", label: "Cancelado" },
  { value: "falta", label: "No-show" },
  { value: "concluida", label: "Concluido" },
] as const;

const CONFIRMATION_STATUS_OPTIONS = [
  { value: "pendente", label: "Pendente" },
  { value: "confirmada", label: "Confirmada" },
  { value: "nao_confirmada", label: "Nao confirmada" },
] as const;

const APPOINTMENT_ATTENDANCE_STATUS_OPTIONS = [
  { value: "pendente", label: "Ainda nao marcado" },
  { value: "compareceu", label: "Paciente compareceu" },
  { value: "faltou", label: "Paciente nao veio" },
] as const;

const APPOINTMENT_NEXT_APPOINTMENT_OPTIONS = [
  { value: "nao_definido", label: "Ainda nao definido" },
  { value: "precisa_agendar", label: "Precisa de novo agendamento" },
  { value: "retorno_agendado", label: "Ja saiu com retorno agendado" },
  { value: "nao_precisa", label: "Nao precisa de novo agendamento" },
] as const;

const DEFAULT_AVAILABILITY_COLOR = "#22c55e";
const ACTIVE_BOARD_STATUSES = new Set(["agendada", "confirmada", "reagendada"]);
const DEFAULT_BOARD_LANE_WIDTH = 156;
const DEFAULT_BOARD_PX_PER_MINUTE = 1.45;
const APPOINTMENT_PATIENT_DETAIL_TABS: { id: AppointmentPatientDetailTab; label: string }[] = [
  { id: "resumo", label: "Resumo" },
  { id: "procedimentos", label: "Procedimentos" },
  { id: "conversas", label: "WhatsApp" },
  { id: "documentos", label: "Documentos" },
  { id: "historico", label: "Historico" },
];

function startOfWeekMonday(date: Date): Date {
  const output = new Date(date);
  const day = output.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  output.setDate(output.getDate() + diff);
  output.setHours(0, 0, 0, 0);
  return output;
}

function addDays(date: Date, days: number): Date {
  const output = new Date(date);
  output.setDate(output.getDate() + days);
  return output;
}

function startOfNextDemoWeek(date: Date): Date {
  return addDays(startOfWeekMonday(date), 7);
}

function toDayKey(date: Date): string {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseTimeToMinutes(value: string, fallback: number): number {
  const [hourText, minuteText] = (value || "").split(":");
  const hour = Number(hourText);
  const minute = Number(minuteText);
  if (!Number.isFinite(hour) || !Number.isFinite(minute)) return fallback;
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return fallback;
  return hour * 60 + minute;
}

function formatTimeFromMinutes(value: number): string {
  const hour = Math.floor(value / 60);
  const minute = value % 60;
  return `${`${hour}`.padStart(2, "0")}:${`${minute}`.padStart(2, "0")}`;
}

function formatRescheduleDayLabel(dayKey: string): string {
  const parsed = new Date(`${dayKey}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return dayKey;
  const weekday = parsed.toLocaleDateString("pt-BR", { weekday: "short" }).replace(".", "");
  const dateLabel = parsed.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  return `${weekday.charAt(0).toUpperCase()}${weekday.slice(1)}, ${dateLabel}`;
}

function toDateTimeLocalInput(value?: string | null): string {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return formatDateToLocalInput(parsed);
}

function formatDateToLocalInput(parsed: Date): string {
  const year = parsed.getFullYear();
  const month = `${parsed.getMonth() + 1}`.padStart(2, "0");
  const day = `${parsed.getDate()}`.padStart(2, "0");
  const hour = `${parsed.getHours()}`.padStart(2, "0");
  const minute = `${parsed.getMinutes()}`.padStart(2, "0");
  return `${year}-${month}-${day}T${hour}:${minute}`;
}

function combineDateAndMinutes(date: Date, minutes: number): string {
  const next = new Date(date);
  next.setHours(Math.floor(minutes / 60), minutes % 60, 0, 0);
  return formatDateToLocalInput(next);
}

function addMinutesToLocalInput(value: string, minutes: number): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return formatDateToLocalInput(new Date(parsed.getTime() + minutes * 60_000));
}

function getApiErrorMessage(error: unknown, fallback: string): string {
  const responseData = (error as { response?: { data?: unknown } })?.response?.data;
  if (responseData && typeof responseData === "object") {
    const apiMessage = (responseData as { error?: { message?: string } })?.error?.message;
    if (typeof apiMessage === "string" && apiMessage.trim()) {
      return apiMessage;
    }
    const directMessage = (responseData as { message?: string })?.message;
    if (typeof directMessage === "string" && directMessage.trim()) {
      return directMessage;
    }
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

function normalizeServiceLabel(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9\s]/g, " ")
    .toLowerCase()
    .trim()
    .replace(/\s+/g, " ");
}

const SERVICE_MATCH_IGNORED_TOKENS = new Set([
  "a",
  "o",
  "as",
  "os",
  "de",
  "da",
  "do",
  "das",
  "dos",
  "e",
  "em",
  "para",
  "com",
  "por",
  "na",
  "no",
  "nas",
  "nos",
  "um",
  "uma",
  "servico",
  "servicos",
  "procedimento",
  "procedimentos",
  "tratamento",
  "tratamentos",
  "odontologica",
  "odontologico",
  "odontologicas",
  "odontologicos",
  "dental",
  "dentais",
  "dentario",
  "dentaria",
  "instalacao",
  "instalar",
  "colocacao",
  "colocar",
  "aplicacao",
  "aplicar",
  "realizacao",
  "realizar",
]);

function tokenizeServiceLabel(value: string): string[] {
  return normalizeServiceLabel(value)
    .split(" ")
    .map((token) => token.trim())
    .filter((token) => token.length >= 3 && !SERVICE_MATCH_IGNORED_TOKENS.has(token));
}

function serviceLabelsMatch(left: string | null | undefined, right: string | null | undefined): boolean {
  const normalizedLeft = normalizeServiceLabel(left ?? "");
  const normalizedRight = normalizeServiceLabel(right ?? "");
  if (!normalizedLeft || !normalizedRight) return false;
  if (normalizedLeft === normalizedRight) return true;
  if (normalizedLeft.includes(normalizedRight) || normalizedRight.includes(normalizedLeft)) return true;

  const leftTokens = new Set(tokenizeServiceLabel(left ?? ""));
  const rightTokens = new Set(tokenizeServiceLabel(right ?? ""));
  if (!leftTokens.size || !rightTokens.size) return false;

  const overlappingTokens = Array.from(leftTokens).filter((token) => rightTokens.has(token));
  if (!overlappingTokens.length) return false;

  const hasStrongSingleToken = overlappingTokens.some((token) => token.length >= 5);
  return hasStrongSingleToken || overlappingTokens.length >= 2;
}

function professionalCanPerformService(
  professional: ProfessionalItem | undefined,
  serviceName: string,
): boolean {
  if (!professional) return true;
  const specialty = professional.specialty?.trim() ?? "";
  const procedures = (professional.procedures ?? []).map((item) => item.trim()).filter(Boolean);
  if (!specialty && !procedures.length) {
    return true;
  }
  if (serviceLabelsMatch(specialty, serviceName)) {
    return true;
  }
  return procedures.some((procedureName) => serviceLabelsMatch(procedureName, serviceName));
}

function resolveServiceCatalogItem(
  catalog: ServiceCatalogItem[],
  serviceName: string,
): ServiceCatalogItem | null {
  const directMatch = catalog.find((item) => serviceLabelsMatch(item.name, serviceName));
  return directMatch ?? null;
}

function isEvaluationProcedureName(value: string | null | undefined): boolean {
  return normalizeServiceLabel(value ?? "").includes("avali");
}

function resolveEvaluationServiceName(
  catalog: ServiceCatalogItem[],
  availableNames: string[],
): string {
  const candidateNames = availableNames.length ? availableNames : catalog.map((item) => item.name);
  const exactCatalogMatch = catalog.find((item) => candidateNames.some((name) => serviceLabelsMatch(item.name, name)) && isEvaluationProcedureName(item.name));
  if (exactCatalogMatch) return exactCatalogMatch.name;

  const localMatch = candidateNames.find((name) => isEvaluationProcedureName(name));
  if (localMatch) return localMatch;

  return "Avaliacao detalhada";
}

function buildProcedureOptions(serviceCatalog: string[], currentValue: string): string[] {
  const trimmedCurrentValue = currentValue.trim();
  const options = new Map<string, string>();

  if (trimmedCurrentValue) {
    options.set(trimmedCurrentValue.toLowerCase(), trimmedCurrentValue);
  }

  serviceCatalog.forEach((item) => {
    const trimmedItem = item.trim();
    if (!trimmedItem) return;
    const key = trimmedItem.toLowerCase();
    if (!options.has(key)) {
      options.set(key, trimmedItem);
    }
  });

  return Array.from(options.values()).sort((left, right) => {
    if (trimmedCurrentValue) {
      if (left === trimmedCurrentValue) return -1;
      if (right === trimmedCurrentValue) return 1;
    }
    return left.localeCompare(right);
  });
}

function findOptionLabel(
  options: readonly { value: string; label: string }[],
  value: string | null | undefined,
  fallback: string,
): string {
  const normalized = String(value || "").trim().toLowerCase();
  return options.find((option) => option.value === normalized)?.label ?? fallback;
}

function resolveAppointmentAttendanceStatus(appointment: AppointmentItem | null | undefined): string {
  const explicitValue = String(appointment?.attendance_status || "").trim().toLowerCase();
  if (explicitValue) return explicitValue;

  const status = String(appointment?.status || "").trim().toLowerCase();
  if (status === "concluida") return "compareceu";
  if (status === "falta") return "faltou";
  return "pendente";
}

function resolveNextAppointmentStatus(appointment: AppointmentItem | null | undefined): string {
  return String(appointment?.next_appointment_status || "").trim().toLowerCase() || "nao_definido";
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function splitTags(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function roundUpToStep(value: number, step: number): number {
  if (step <= 0) return value;
  return Math.ceil(value / step) * step;
}

function hexToRgba(hex: string, alpha: number): string {
  const normalized = hex.replace("#", "");
  if (normalized.length !== 6) return `rgba(15, 118, 110, ${alpha})`;
  const red = parseInt(normalized.slice(0, 2), 16);
  const green = parseInt(normalized.slice(2, 4), 16);
  const blue = parseInt(normalized.slice(4, 6), 16);
  if ([red, green, blue].some((item) => Number.isNaN(item))) return `rgba(15, 118, 110, ${alpha})`;
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

function colorFromSeed(seed: string): string {
  let hash = 0;
  for (let index = 0; index < seed.length; index += 1) {
    hash = seed.charCodeAt(index) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;
  const saturation = 58;
  const lightness = 74;

  const c = ((1 - Math.abs((2 * lightness) / 100 - 1)) * saturation) / 100;
  const x = c * (1 - Math.abs(((hue / 60) % 2) - 1));
  const m = lightness / 100 - c / 2;
  let red = 0;
  let green = 0;
  let blue = 0;

  if (hue < 60) {
    red = c;
    green = x;
  } else if (hue < 120) {
    red = x;
    green = c;
  } else if (hue < 180) {
    green = c;
    blue = x;
  } else if (hue < 240) {
    green = x;
    blue = c;
  } else if (hue < 300) {
    red = x;
    blue = c;
  } else {
    red = c;
    blue = x;
  }

  const toHex = (channel: number) =>
    Math.round((channel + m) * 255)
      .toString(16)
      .padStart(2, "0");

  return `#${toHex(red)}${toHex(green)}${toHex(blue)}`;
}

function formatBoardLaneLabel(fullName: string): string {
  const parts = String(fullName || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!parts.length) return "Equipe";
  if (parts.length === 1) return parts[0];
  return `${parts[0]} ${parts[1]}`;
}

function buildProfessionalAvailabilityCards(params: {
  date: Date;
  lane: BoardLane;
  appointments: AppointmentItem[];
  boardStartMinutes: number;
  boardEndMinutes: number;
  pxPerMinute: number;
}): AvailabilityCard[] {
  const { date, lane, appointments, boardStartMinutes, boardEndMinutes, pxPerMinute } = params;
  if (lane.isPlaceholder || !lane.professionalId) return [];
  if (!lane.workingDays.includes(date.getDay())) return [];

  const laneStart = clamp(parseTimeToMinutes(lane.shiftStart, boardStartMinutes), boardStartMinutes, boardEndMinutes);
  const laneEnd = clamp(parseTimeToMinutes(lane.shiftEnd, boardEndMinutes), boardStartMinutes, boardEndMinutes);
  if (laneEnd <= laneStart) return [];

  const busyWindows = appointments
    .filter(
      (appointment) =>
        appointment.professional_id === lane.professionalId &&
        ACTIVE_BOARD_STATUSES.has(String(appointment.status || "").trim().toLowerCase()),
    )
    .map((appointment) => {
      const startAt = new Date(appointment.starts_at);
      const fallbackEnd = new Date(startAt.getTime() + 60 * 60 * 1000);
      const endAt = appointment.ends_at ? new Date(appointment.ends_at) : fallbackEnd;
      return {
        start: clamp(startAt.getHours() * 60 + startAt.getMinutes(), boardStartMinutes, boardEndMinutes),
        end: clamp(endAt.getHours() * 60 + endAt.getMinutes(), boardStartMinutes, boardEndMinutes),
      };
    })
    .filter((item) => item.end > item.start)
    .sort((left, right) => left.start - right.start || left.end - right.end);

  const cards: AvailabilityCard[] = [];
  let cursor = laneStart;

  busyWindows.forEach((busy) => {
    if (busy.start > cursor) {
      cards.push({
        top: (cursor - boardStartMinutes) * pxPerMinute,
        height: (busy.start - cursor) * pxPerMinute,
        startMinutes: cursor,
        endMinutes: busy.start,
      });
    }
    cursor = Math.max(cursor, busy.end);
  });

  if (cursor < laneEnd) {
    cards.push({
      top: (cursor - boardStartMinutes) * pxPerMinute,
      height: (laneEnd - cursor) * pxPerMinute,
      startMinutes: cursor,
      endMinutes: laneEnd,
    });
  }

  return cards;
}

function buildRescheduleSlotChoices(params: {
  anchorDate: Date;
  unitId: string;
  procedureType: string;
  excludeAppointmentId: string;
  serviceCatalog: ServiceCatalogItem[];
  professionals: ProfessionalItem[];
  appointments: AppointmentItem[];
  maxDaysAfterAnchor?: number;
  maxDaysBeforeAnchor?: number;
  maxSlots?: number;
  maxSlotsPerDay?: number;
}): RescheduleSlotChoice[] {
  const {
    anchorDate,
    unitId,
    procedureType,
    excludeAppointmentId,
    serviceCatalog,
    professionals,
    appointments,
    maxDaysAfterAnchor = 21,
    maxDaysBeforeAnchor = 7,
    maxSlots = 42,
    maxSlotsPerDay = 6,
  } = params;

  if (!procedureType.trim() || !unitId) return [];

  const serviceItem = resolveServiceCatalogItem(serviceCatalog, procedureType);
  const durationMinutes = Math.max(15, serviceItem?.duration_minutes ?? 60);
  const eligibleProfessionals = professionals
    .filter(
      (professional) =>
        professional.is_active &&
        professional.unit_id === unitId &&
        professionalCanPerformService(professional, procedureType),
    )
    .sort((left, right) => left.full_name.localeCompare(right.full_name));

  if (!eligibleProfessionals.length) return [];

  const now = new Date();
  const todayStart = new Date(now);
  todayStart.setHours(0, 0, 0, 0);
  const anchorDay = new Date(anchorDate);
  anchorDay.setHours(0, 0, 0, 0);
  const searchStartDayCandidate = addDays(anchorDay, -maxDaysBeforeAnchor);
  const searchStartDay =
    searchStartDayCandidate.getTime() > todayStart.getTime() ? searchStartDayCandidate : todayStart;
  const searchEndDay = addDays(anchorDay, maxDaysAfterAnchor);
  const searchAnchor = new Date(Math.max(anchorDate.getTime(), now.getTime()));
  searchAnchor.setSeconds(0, 0);

  const results: RescheduleSlotChoice[] = [];
  const totalDays =
    Math.max(1, Math.ceil((searchEndDay.getTime() - searchStartDay.getTime()) / (24 * 60 * 60 * 1000)) + 1);

  for (let offset = 0; offset < totalDays && results.length < maxSlots; offset += 1) {
    const date = addDays(searchStartDay, offset);
    const dayKey = toDayKey(date);
    const isAnchorDay = dayKey === toDayKey(searchAnchor);
    const anchorMinutes = searchAnchor.getHours() * 60 + searchAnchor.getMinutes();
    const dayChoicesByProfessional = new Map<string, RescheduleSlotChoice[]>();

    for (const professional of eligibleProfessionals) {
      if (results.length >= maxSlots) break;
      if (!(professional.working_days ?? []).includes(date.getDay())) continue;

      const shiftStart = parseTimeToMinutes(professional.shift_start, 8 * 60);
      const shiftEnd = parseTimeToMinutes(professional.shift_end, 18 * 60);
      const windowStart = isAnchorDay ? Math.max(shiftStart, roundUpToStep(anchorMinutes, 15)) : shiftStart;
      if (shiftEnd - windowStart < durationMinutes) continue;

      const busyWindows = appointments
        .filter(
          (appointment) =>
            appointment.id !== excludeAppointmentId &&
            appointment.professional_id === professional.id &&
            ACTIVE_BOARD_STATUSES.has(String(appointment.status || '').trim().toLowerCase()) &&
            toDayKey(new Date(appointment.starts_at)) === dayKey,
        )
        .map((appointment) => {
          const startAt = new Date(appointment.starts_at);
          const fallbackEnd = new Date(startAt.getTime() + 60 * 60 * 1000);
          const endAt = appointment.ends_at ? new Date(appointment.ends_at) : fallbackEnd;
          return {
            start: startAt.getHours() * 60 + startAt.getMinutes(),
            end: endAt.getHours() * 60 + endAt.getMinutes(),
          };
        })
        .filter((window) => window.end > window.start)
        .sort((left, right) => left.start - right.start || left.end - right.end);

      const professionalDayChoices: RescheduleSlotChoice[] = [];
      const appendSlotsUntil = (freeStart: number, freeEnd: number) => {
        const slotStart = roundUpToStep(Math.max(freeStart, windowStart), 15);
        for (
          let candidateStart = slotStart;
          candidateStart + durationMinutes <= freeEnd && professionalDayChoices.length < maxSlotsPerDay;
          candidateStart += 15
        ) {
          const startsAt = combineDateAndMinutes(date, candidateStart);
          const endsAt = combineDateAndMinutes(date, candidateStart + durationMinutes);
          professionalDayChoices.push({
            id: `${dayKey}-${professional.id}-${candidateStart}`,
            label: `${formatDateBR(startsAt)} - ${formatTimeFromMinutes(candidateStart)} - ${formatTimeFromMinutes(candidateStart + durationMinutes)} - ${professional.full_name}`,
            startsAt,
            endsAt,
            professionalId: professional.id,
            professionalName: professional.full_name,
            unitId,
            dayKey,
          });
        }
      };

      let cursor = windowStart;
      busyWindows.forEach((busy) => {
        if (busy.start > cursor) {
          appendSlotsUntil(cursor, Math.min(busy.start, shiftEnd));
        }
        cursor = Math.max(cursor, busy.end);
      });

      if (cursor < shiftEnd) {
        appendSlotsUntil(cursor, shiftEnd);
      }

      if (professionalDayChoices.length) {
        dayChoicesByProfessional.set(professional.id, professionalDayChoices);
      }
    }

    const dayChoices = Array.from(dayChoicesByProfessional.values())
      .sort((left, right) => {
        const leftStartsAt = new Date(left[0]?.startsAt ?? 0).getTime();
        const rightStartsAt = new Date(right[0]?.startsAt ?? 0).getTime();
        if (leftStartsAt !== rightStartsAt) return leftStartsAt - rightStartsAt;
        return (left[0]?.professionalName ?? "").localeCompare(right[0]?.professionalName ?? "");
      })
      .map((choices) => [...choices]);

    const selectedDayChoices: RescheduleSlotChoice[] = [];

    // Distribui as sugestoes entre os profissionais elegiveis antes de aplicar o limite do dia.
    while (selectedDayChoices.length < maxSlotsPerDay && results.length + selectedDayChoices.length < maxSlots) {
      let addedInRound = false;

      dayChoices.forEach((choices) => {
        if (selectedDayChoices.length >= maxSlotsPerDay || results.length + selectedDayChoices.length >= maxSlots) {
          return;
        }
        const nextChoice = choices.shift();
        if (!nextChoice) return;
        selectedDayChoices.push(nextChoice);
        addedInRound = true;
      });

      if (!addedInRound) break;
    }

    selectedDayChoices
      .sort((left, right) => {
        const startsDiff = new Date(left.startsAt).getTime() - new Date(right.startsAt).getTime();
        if (startsDiff !== 0) return startsDiff;
        return left.professionalName.localeCompare(right.professionalName);
      })
      .forEach((choice) => {
        if (results.length < maxSlots) {
          results.push(choice);
        }
      });
  }

  return results;
}

function getMonthGrid(monthDate: Date): Date[] {
  const firstOfMonth = new Date(monthDate.getFullYear(), monthDate.getMonth(), 1);
  const start = startOfWeekMonday(firstOfMonth);
  return Array.from({ length: 42 }, (_, index) => addDays(start, index));
}

export default function AgendaPage() {
  const queryClient = useQueryClient();
  const boardRef = useRef<HTMLDivElement | null>(null);
  const previousProfessionalIdsRef = useRef<string[]>([]);
  const initializedUnitFilterRef = useRef(false);
  const initializedCreateUnitRef = useRef(false);

  const sessionQuery = useSession();
  const ownerUnitScope = useOwnerUnitScope();
  const isDemoUser = (sessionQuery.data?.roles ?? []).includes("demo_client");
  const [demoTourAppointmentId, setDemoTourAppointmentId] = useState<string | null>(null);
  const selectedOwnerUnitId =
    ownerUnitScope.canSwitchUnits && ownerUnitScope.selectedUnitId !== "all"
      ? ownerUnitScope.selectedUnitId
      : null;
  const currentUserPermissions = sessionQuery.data?.resolved_page_permissions;
  const canCreateAgenda = canAccessPage(currentUserPermissions, "agenda", "create");
  const canEditAgenda = canAccessPage(currentUserPermissions, "agenda", "edit");
  const canDeleteAgenda = canAccessPage(currentUserPermissions, "agenda", "delete");
  const canEditPatients = canAccessPage(currentUserPermissions, "pacientes", "edit");
  const canDeletePatients = canAccessPage(currentUserPermissions, "pacientes", "delete");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [unitFilter, setUnitFilter] = useState("all");
  const [viewMode, setViewMode] = useState<"day" | "week">("week");
  const [weekAnchor, setWeekAnchor] = useState(() => startOfWeekMonday(new Date()));
  const [focusedDate, setFocusedDate] = useState(() => new Date());
  const [selectedDayKeys, setSelectedDayKeys] = useState<string[]>([]);
  const [selectedProfessionalIds, setSelectedProfessionalIds] = useState<string[]>([]);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [agendaControlsOpen, setAgendaControlsOpen] = useState(false);
  const [appointmentListOpen, setAppointmentListOpen] = useState(false);
  const [createAppointmentOpen, setCreateAppointmentOpen] = useState(false);
  const [professionalColors, setProfessionalColors] = useState<Record<string, string>>({});
  const [availabilityColor, setAvailabilityColor] = useState(DEFAULT_AVAILABILITY_COLOR);
  const [boardLaneWidth, setBoardLaneWidth] = useState(DEFAULT_BOARD_LANE_WIDTH);
  const [boardMinuteScale, setBoardMinuteScale] = useState(DEFAULT_BOARD_PX_PER_MINUTE);
  const [boardResizeState, setBoardResizeState] = useState<BoardResizeState>(null);
  const [monthCursor, setMonthCursor] = useState(() => new Date());
  const [appointmentEditorOpen, setAppointmentEditorOpen] = useState(false);
  const [selectedAppointment, setSelectedAppointment] = useState<EnrichedAppointment | null>(null);
  const [appointmentDeleteConfirmOpen, setAppointmentDeleteConfirmOpen] = useState(false);
  const [appointmentRescheduleOpen, setAppointmentRescheduleOpen] = useState(false);
  const [appointmentRescheduleSelectedSlotId, setAppointmentRescheduleSelectedSlotId] = useState("");
  const [appointmentRescheduleSelectedDayKey, setAppointmentRescheduleSelectedDayKey] = useState("");
  const [appointmentReturnOpen, setAppointmentReturnOpen] = useState(false);
  const [appointmentReturnSelectedSlotId, setAppointmentReturnSelectedSlotId] = useState("");
  const [appointmentReturnSelectedDayKey, setAppointmentReturnSelectedDayKey] = useState("");
  const [appointmentPatientCardOpen, setAppointmentPatientCardOpen] = useState(false);
  const [appointmentPatientEditOpen, setAppointmentPatientEditOpen] = useState(false);
  const [appointmentPatientDeleteConfirmOpen, setAppointmentPatientDeleteConfirmOpen] = useState(false);
  const [appointmentPatientTab, setAppointmentPatientTab] = useState<AppointmentPatientDetailTab>("resumo");
  const [manualBookingOpen, setManualBookingOpen] = useState(false);
  const [manualBookingContext, setManualBookingContext] = useState<AvailabilityBookingContext | null>(null);
  const [editUnitId, setEditUnitId] = useState("");
  const [editProfessionalId, setEditProfessionalId] = useState("");
  const [editProcedure, setEditProcedure] = useState("");
  const [editStartsAt, setEditStartsAt] = useState("");
  const [editEndsAt, setEditEndsAt] = useState("");
  const [editStatus, setEditStatus] = useState("agendada");
  const [editConfirmationStatus, setEditConfirmationStatus] = useState("pendente");
  const [editNotes, setEditNotes] = useState("");
  const [editAttendanceStatus, setEditAttendanceStatus] = useState("pendente");
  const [editAttendanceNotes, setEditAttendanceNotes] = useState("");
  const [editNextAppointmentStatus, setEditNextAppointmentStatus] = useState("nao_definido");

  const [patientId, setPatientId] = useState("");
  const [unitId, setUnitId] = useState("");
  const [professionalId, setProfessionalId] = useState("");
  const [procedure, setProcedure] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [manualBookingPatientMode, setManualBookingPatientMode] = useState<"existing" | "new">("existing");
  const [manualBookingPatientSearch, setManualBookingPatientSearch] = useState("");
  const [manualBookingPatientId, setManualBookingPatientId] = useState("");
  const [manualBookingUnitId, setManualBookingUnitId] = useState("");
  const [manualBookingProfessionalId, setManualBookingProfessionalId] = useState("");
  const [manualBookingProcedure, setManualBookingProcedure] = useState("");
  const [manualBookingStartsAt, setManualBookingStartsAt] = useState("");
  const [manualBookingNotes, setManualBookingNotes] = useState("");
  const [manualBookingNeedsEvaluation, setManualBookingNeedsEvaluation] = useState(true);
  const [manualBookingHistoryOpen, setManualBookingHistoryOpen] = useState(false);
  const [manualBookingNewFullName, setManualBookingNewFullName] = useState("");
  const [manualBookingNewPhone, setManualBookingNewPhone] = useState("");
  const [manualBookingNewCpf, setManualBookingNewCpf] = useState("");
  const [manualBookingNewEmail, setManualBookingNewEmail] = useState("");
  const [manualBookingNewBirthDate, setManualBookingNewBirthDate] = useState("");
  const [appointmentPatientFormName, setAppointmentPatientFormName] = useState("");
  const [appointmentPatientFormCpf, setAppointmentPatientFormCpf] = useState("");
  const [appointmentPatientFormEmail, setAppointmentPatientFormEmail] = useState("");
  const [appointmentPatientFormBirthDate, setAppointmentPatientFormBirthDate] = useState("");
  const [appointmentPatientFormStatus, setAppointmentPatientFormStatus] = useState("ativo");
  const [appointmentPatientFormTags, setAppointmentPatientFormTags] = useState("");
  const [appointmentPatientFormNotes, setAppointmentPatientFormNotes] = useState("");
  const demoAgendaDefaultsAppliedRef = useRef(false);

  const agendaQuery = useQuery<AgendaDataset>({
    queryKey: ["agenda-dataset", selectedOwnerUnitId ?? "all"],
    queryFn: async () => {
      const [
        appointmentsResponse,
        patientsResponse,
        unitsResponse,
        professionalsResponse,
        conversationsResponse,
        documentsResponse,
        serviceCatalogResponse,
      ] =
        await Promise.all([
          api.get<ApiPage<AppointmentItem>>("/appointments", {
            params: { limit: 300, offset: 0, unit_id: selectedOwnerUnitId ?? undefined },
          }),
          api.get<ApiPage<PatientItem>>("/patients", {
            params: { limit: 200, offset: 0, unit_id: selectedOwnerUnitId ?? undefined },
          }),
          api.get<ApiPage<UnitItem>>("/units", { params: { limit: 100, offset: 0 } }),
          api.get<ApiPage<ProfessionalItem>>("/professionals", {
            params: { limit: 300, offset: 0, unit_id: selectedOwnerUnitId ?? undefined },
          }),
          api.get<ApiPage<ConversationItem>>("/conversations", {
            params: { limit: 200, offset: 0, unit_id: selectedOwnerUnitId ?? undefined },
          }),
          api.get<ApiPage<DocumentItem>>("/documents", {
            params: { limit: 200, offset: 0, unit_id: selectedOwnerUnitId ?? undefined },
          }),
          api.get<{ items: ServiceCatalogItem[] }>("/settings/service-catalog/config"),
        ]);

      return {
        appointments: appointmentsResponse.data.data ?? [],
        patients: patientsResponse.data.data ?? [],
        units: unitsResponse.data.data ?? [],
        professionals: professionalsResponse.data.data ?? [],
        conversations: conversationsResponse.data.data ?? [],
        documents: documentsResponse.data.data ?? [],
        serviceCatalog:
          (serviceCatalogResponse.data.items ?? [])
            .filter((item) => item.is_active !== false)
            .sort((left, right) => left.name.localeCompare(right.name)),
      };
    },
    refetchInterval: 12_000,
    refetchOnWindowFocus: true,
  });

  const settingsQuery = useQuery<{ data: AgendaSettingItem[] }>({
    queryKey: ["agenda-settings"],
    queryFn: async () => (await api.get("/settings")).data,
    staleTime: 60_000,
  });

  const patientLookupQuery = useQuery<PatientItem[]>({
    queryKey: ["agenda-manual-patient-search", selectedOwnerUnitId ?? "all", manualBookingPatientSearch.trim()],
    queryFn: async () => {
      const response = await api.get<ApiPage<PatientItem>>("/patients", {
        params: {
          limit: 20,
          offset: 0,
          q: manualBookingPatientSearch.trim(),
          unit_id: selectedOwnerUnitId ?? undefined,
        },
      });
      return response.data.data ?? [];
    },
    enabled:
      manualBookingOpen &&
      manualBookingPatientMode === "existing" &&
      manualBookingPatientSearch.trim().length >= 2,
    staleTime: 10_000,
  });

  const assignedUnitId = sessionQuery.data?.assigned_unit_id ?? null;
  const ownerSelectedUnitId =
    ownerUnitScope.canSwitchUnits && ownerUnitScope.selectedUnitId !== "all"
      ? ownerUnitScope.selectedUnitId
      : null;
  const preferredUnitId = ownerSelectedUnitId ?? sessionQuery.data?.unit_id ?? null;
  const scopedUnitId = assignedUnitId ?? preferredUnitId ?? null;
  const unitSelectionLocked = Boolean(
    scopedUnitId &&
      (sessionQuery.data?.roles?.includes("manager") || sessionQuery.data?.roles?.includes("receptionist")),
  );

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!canCreateAgenda) {
        throw new Error("Seu perfil nao pode criar consultas nesta pagina.");
      }
      return api.post("/appointments", {
        patient_id: patientId,
        unit_id: unitId,
        professional_id: professionalId || null,
        procedure_type: procedure,
        starts_at: new Date(startsAt).toISOString(),
      });
    },
    onSuccess: () => {
      toast.success("Consulta criada com sucesso.");
      setPatientId("");
      setUnitId("");
      setProfessionalId("");
      setProcedure("");
      setStartsAt("");
      setCreateAppointmentOpen(false);
      queryClient.invalidateQueries({ queryKey: ["agenda-dataset"] });
    },
    onError: (error) => toast.error(getApiErrorMessage(error, "Nao foi possivel criar a consulta.")),
  });

  const manualBookingMutation = useMutation({
    mutationFn: async () => {
      if (!canCreateAgenda) {
        throw new Error("Seu perfil nao pode criar consultas nesta pagina.");
      }
      if (!manualBookingUnitId || !manualBookingProcedure.trim() || !manualBookingStartsAt) {
        throw new Error("Escolha o servico e confirme o horario do card antes de salvar.");
      }

      const parsedStartsAt = new Date(manualBookingStartsAt);
      if (Number.isNaN(parsedStartsAt.getTime())) {
        throw new Error("Horario inicial invalido.");
      }
      if (!manualBookingBookedProcedure.trim()) {
        throw new Error("Escolha o servico antes de salvar.");
      }

      let resolvedPatientId = manualBookingPatientId;

      if (manualBookingPatientMode === "existing") {
        if (!resolvedPatientId) {
          throw new Error("Busque e selecione um paciente ja cadastrado.");
        }
      } else {
        if (!manualBookingNewFullName.trim() || !manualBookingNewPhone.trim()) {
          throw new Error("Preencha nome completo e telefone do novo paciente.");
        }

        const patientResponse = await api.post<{ id: string }>("/patients", {
          full_name: manualBookingNewFullName.trim(),
          phone: manualBookingNewPhone.trim(),
          cpf: manualBookingNewCpf.trim() || null,
          email: manualBookingNewEmail.trim() || null,
          birth_date: manualBookingNewBirthDate || null,
          operational_notes: "Criado automaticamente pelo agendamento manual da agenda.",
          origin: "agenda_manual",
          unit_id: manualBookingUnitId,
          lgpd_consent: false,
          marketing_opt_in: false,
        });
        resolvedPatientId = patientResponse.data.id;
      }

      const structuredNotes = [
        manualBookingPatientMode === "new"
          ? `Fluxo do novo cliente: ${manualBookingNeedsEvaluation ? "avaliacao antes do servico" : "servico com avaliacao no mesmo atendimento"}`
          : null,
        manualBookingProcedure.trim() && manualBookingBookedProcedure.trim() !== manualBookingProcedure.trim()
          ? `Servico de interesse: ${manualBookingProcedure.trim()}`
          : null,
        manualBookingNotes.trim() ? `Observacoes: ${manualBookingNotes.trim()}` : null,
      ]
        .filter(Boolean)
        .join("\n");

      return api.post("/appointments", {
        patient_id: resolvedPatientId,
        unit_id: manualBookingUnitId,
        professional_id: manualBookingProfessionalId || null,
        procedure_type: manualBookingBookedProcedure.trim(),
        starts_at: parsedStartsAt.toISOString(),
        origin: "manual",
        notes: structuredNotes,
      });
    },
    onSuccess: () => {
      toast.success("Agendamento manual criado com sucesso.");
      setManualBookingOpen(false);
      setManualBookingContext(null);
      setManualBookingPatientMode("existing");
      setManualBookingPatientSearch("");
      setManualBookingPatientId("");
      setManualBookingUnitId("");
      setManualBookingProfessionalId("");
      setManualBookingProcedure("");
      setManualBookingStartsAt("");
      setManualBookingNotes("");
      setManualBookingNeedsEvaluation(true);
      setManualBookingHistoryOpen(false);
      setManualBookingNewFullName("");
      setManualBookingNewPhone("");
      setManualBookingNewCpf("");
      setManualBookingNewEmail("");
      setManualBookingNewBirthDate("");
      queryClient.invalidateQueries({ queryKey: ["agenda-dataset"] });
    },
    onError: (error) => toast.error(getApiErrorMessage(error, "Nao foi possivel criar o agendamento manual.")),
  });

  const updateMutation = useMutation({
    mutationFn: async ({ appointmentId, payload }: { appointmentId: string; payload: Record<string, unknown> }) => {
      if (!canEditAgenda) {
        throw new Error("Seu perfil nao pode editar consultas nesta pagina.");
      }
      return api.patch(`/appointments/${appointmentId}`, payload);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["agenda-dataset"] }),
    onError: (error) => toast.error(getApiErrorMessage(error, "Nao foi possivel atualizar a consulta.")),
  });

  const createReturnAppointmentMutation = useMutation({
    mutationFn: async ({
      choice,
      currentAppointmentPayload,
    }: {
      choice: RescheduleSlotChoice;
      currentAppointmentPayload: Record<string, unknown>;
    }) => {
      if (!selectedAppointment) {
        throw new Error("Consulta atual nao encontrada para gerar retorno.");
      }

      const createdReturnResponse = await api.post("/appointments", {
        patient_id: selectedAppointment.patient_id,
        unit_id: choice.unitId,
        professional_id: choice.professionalId,
        procedure_type: editProcedure.trim(),
        starts_at: new Date(choice.startsAt).toISOString(),
        ends_at: new Date(choice.endsAt).toISOString(),
        origin: "retorno_manual",
        notes: `Retorno criado a partir da consulta de ${formatDateTimeBR(selectedAppointment.starts_at)}.`,
      });

      let syncError: unknown = null;
      try {
        await api.patch(`/appointments/${selectedAppointment.id}`, currentAppointmentPayload);
      } catch (error) {
        syncError = error;
      }

      return { createdReturnResponse, syncError };
    },
    onSuccess: ({ syncError }) => {
      if (syncError) {
        toast.error("Retorno criado, mas nao foi possivel atualizar o status da consulta atual.");
      } else {
        toast.success("Retorno agendado com sucesso.");
      }
      setAppointmentEditorOpen(false);
      setSelectedAppointment(null);
      queryClient.invalidateQueries({ queryKey: ["agenda-dataset"] });
    },
    onError: (error) => toast.error(getApiErrorMessage(error, "Nao foi possivel agendar o retorno.")),
  });

  const deleteMutation = useMutation({
    mutationFn: async (appointmentId: string) => {
      if (!canDeleteAgenda) {
        throw new Error("Seu perfil nao pode excluir consultas nesta pagina.");
      }
      return api.delete(`/appointments/${appointmentId}`);
    },
    onSuccess: () => {
      toast.success("Consulta excluida com sucesso.");
      setAppointmentEditorOpen(false);
      setSelectedAppointment(null);
      queryClient.invalidateQueries({ queryKey: ["agenda-dataset"] });
    },
    onError: (error) => toast.error(getApiErrorMessage(error, "Nao foi possivel excluir a consulta.")),
  });

  const updatePatientMutation = useMutation({
    mutationFn: async (patientId: string) => {
      if (!canEditPatients) {
        throw new Error("Seu perfil nao pode editar pacientes.");
      }
      return api.patch(`/patients/${patientId}`, {
        full_name: appointmentPatientFormName.trim(),
        cpf: appointmentPatientFormCpf.trim() || null,
        email: appointmentPatientFormEmail.trim() || null,
        birth_date: appointmentPatientFormBirthDate || null,
        operational_notes: appointmentPatientFormNotes.trim(),
        status: appointmentPatientFormStatus,
        tags: splitTags(appointmentPatientFormTags),
      });
    },
    onSuccess: () => {
      toast.success("Paciente atualizado com sucesso.");
      setAppointmentPatientEditOpen(false);
      queryClient.invalidateQueries({ queryKey: ["agenda-dataset"] });
      setSelectedAppointment((current) =>
        current
          ? {
              ...current,
              patient_name: appointmentPatientFormName.trim() || current.patient_name,
            }
          : current,
      );
    },
    onError: (error) => toast.error(getApiErrorMessage(error, "Nao foi possivel atualizar o paciente.")),
  });

  const deletePatientMutation = useMutation({
    mutationFn: async (patientId: string) => {
      if (!canDeletePatients) {
        throw new Error("Seu perfil nao pode excluir pacientes.");
      }
      return api.delete(`/patients/${patientId}`);
    },
    onSuccess: () => {
      toast.success("Paciente excluido com sucesso.");
      setAppointmentPatientDeleteConfirmOpen(false);
      setAppointmentPatientEditOpen(false);
      setAppointmentPatientCardOpen(false);
      queryClient.invalidateQueries({ queryKey: ["agenda-dataset"] });
      setSelectedAppointment((current) =>
        current
          ? {
              ...current,
              patient_name: "Paciente nao identificado",
              patient_phone: "",
            }
          : current,
      );
    },
    onError: (error) => toast.error(getApiErrorMessage(error, "Nao foi possivel excluir o paciente.")),
  });

  const saveColorsMutation = useMutation({
    mutationFn: async () =>
      Promise.all([
        api.put("/settings/agenda.professional_colors", {
          value: professionalColors,
          is_secret: false,
        }),
        api.put("/settings/agenda.availability_color", {
          value: availabilityColor,
          is_secret: false,
        }),
      ]),
    onSuccess: () => {
      toast.success("Cores da agenda salvas.");
      queryClient.invalidateQueries({ queryKey: ["agenda-settings"] });
    },
    onError: () => toast.error("Nao foi possivel salvar as cores da agenda."),
  });

  useEffect(() => {
    const professionalIds = (agendaQuery.data?.professionals ?? []).map((item) => item.id);
    if (!professionalIds.length) {
      previousProfessionalIdsRef.current = [];
      return;
    }

    setSelectedProfessionalIds((current) => {
      const previousProfessionalIds = previousProfessionalIdsRef.current;
      previousProfessionalIdsRef.current = professionalIds;

      if (!current.length && !previousProfessionalIds.length) {
        return professionalIds;
      }

      const filteredCurrent = current.filter((id) => professionalIds.includes(id));
      const addedProfessionalIds = professionalIds.filter((id) => !previousProfessionalIds.includes(id));
      const next = Array.from(new Set([...filteredCurrent, ...addedProfessionalIds]));

      if (next.length === current.length && next.every((id, index) => id === current[index])) {
        return current;
      }
      return next;
    });
  }, [agendaQuery.data?.professionals]);

  useEffect(() => {
    const allowedIds = new Set(
      (unitFilter === "all"
        ? agendaQuery.data?.professionals ?? []
        : (agendaQuery.data?.professionals ?? []).filter((professional) => professional.unit_id === unitFilter)
      ).map((professional) => professional.id),
    );
    if (!allowedIds.size) {
      setSelectedProfessionalIds([]);
      return;
    }
    setSelectedProfessionalIds((current) => {
      const filtered = current.filter((id) => allowedIds.has(id));
      const next = filtered.length ? filtered : Array.from(allowedIds);
      if (next.length === current.length && next.every((id, index) => id === current[index])) {
        return current;
      }
      return next;
    });
  }, [agendaQuery.data?.professionals, unitFilter]);

  useEffect(() => {
    const units = agendaQuery.data?.units ?? [];
    if (!units.length) return;

    if (unitSelectionLocked && scopedUnitId) {
      if (unitFilter !== scopedUnitId) {
        setUnitFilter(scopedUnitId);
      }
      if (unitId !== scopedUnitId) {
        setUnitId(scopedUnitId);
      }
      initializedUnitFilterRef.current = true;
      initializedCreateUnitRef.current = true;
      return;
    }

    if (ownerUnitScope.canSwitchUnits) {
      if (unitFilter !== ownerUnitScope.selectedUnitId) {
        setUnitFilter(ownerUnitScope.selectedUnitId);
      }
      if (ownerUnitScope.selectedUnitId !== "all" && unitId !== ownerUnitScope.selectedUnitId) {
        setUnitId(ownerUnitScope.selectedUnitId);
      }
      initializedUnitFilterRef.current = true;
      initializedCreateUnitRef.current = true;
      return;
    }

    if (!initializedUnitFilterRef.current) {
      initializedUnitFilterRef.current = true;
      if (preferredUnitId) {
        setUnitFilter(preferredUnitId);
      }
    }

    if (!initializedCreateUnitRef.current) {
      initializedCreateUnitRef.current = true;
      if (preferredUnitId) {
        setUnitId(preferredUnitId);
      }
    }
  }, [agendaQuery.data?.units, ownerUnitScope.canSwitchUnits, ownerUnitScope.selectedUnitId, preferredUnitId, scopedUnitId, unitFilter, unitId, unitSelectionLocked]);

  useEffect(() => {
    const visibleDays = isDemoUser ? 5 : 7;
    const weekKeys = Array.from({ length: visibleDays }, (_, index) => toDayKey(addDays(weekAnchor, index)));
    setSelectedDayKeys(weekKeys);
  }, [isDemoUser, weekAnchor]);

  useEffect(() => {
    if (!isDemoUser || demoAgendaDefaultsAppliedRef.current) return;
    const showcaseWeekStart = startOfNextDemoWeek(new Date());
    setViewMode("week");
    setWeekAnchor(showcaseWeekStart);
    setFocusedDate(showcaseWeekStart);
    setMonthCursor(showcaseWeekStart);
    demoAgendaDefaultsAppliedRef.current = true;
  }, [isDemoUser]);

  useEffect(() => {
    if (!isDemoUser || !sessionQuery.data || typeof window === "undefined") {
      setDemoTourAppointmentId(null);
      return;
    }

    const identity = resolveDemoTourIdentity(sessionQuery.data, ensureDemoSessionId());
    const progress = readDemoTourProgress(identity);
    setDemoTourAppointmentId(progress?.context.appointmentId ?? null);
  }, [isDemoUser, sessionQuery.data]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const savedLaneWidth = Number(window.localStorage.getItem("agenda.board_lane_width") || "");
    const savedMinuteScale = Number(window.localStorage.getItem("agenda.board_minute_scale") || "");

    if (Number.isFinite(savedLaneWidth) && savedLaneWidth >= 120 && savedLaneWidth <= 260) {
      setBoardLaneWidth(savedLaneWidth);
    }
    if (Number.isFinite(savedMinuteScale) && savedMinuteScale >= 0.9 && savedMinuteScale <= 3) {
      setBoardMinuteScale(savedMinuteScale);
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("agenda.board_lane_width", String(boardLaneWidth));
  }, [boardLaneWidth]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("agenda.board_minute_scale", String(boardMinuteScale));
  }, [boardMinuteScale]);

  useEffect(() => {
    if (!boardResizeState) return undefined;

    const previousUserSelect = document.body.style.userSelect;
    const previousCursor = document.body.style.cursor;
    document.body.style.userSelect = "none";
    document.body.style.cursor = boardResizeState.axis === "x" ? "ew-resize" : "ns-resize";

    const handlePointerMove = (event: MouseEvent) => {
      if (boardResizeState.axis === "x") {
        const deltaX = event.clientX - boardResizeState.startPointer;
        const nextWidth = clamp(
          Math.round((boardResizeState.startValue + deltaX) / 4) * 4,
          120,
          260,
        );
        setBoardLaneWidth(nextWidth);
        return;
      }

      const deltaY = event.clientY - boardResizeState.startPointer;
      const nextScale = clamp(
        Math.round((boardResizeState.startValue + deltaY * 0.01) * 20) / 20,
        0.9,
        3,
      );
      setBoardMinuteScale(nextScale);
    };

    const handlePointerUp = () => {
      setBoardResizeState(null);
    };

    window.addEventListener("mousemove", handlePointerMove);
    window.addEventListener("mouseup", handlePointerUp);

    return () => {
      document.body.style.userSelect = previousUserSelect;
      document.body.style.cursor = previousCursor;
      window.removeEventListener("mousemove", handlePointerMove);
      window.removeEventListener("mouseup", handlePointerUp);
    };
  }, [boardResizeState]);

  useEffect(() => {
    const settingMap = new Map((settingsQuery.data?.data ?? []).map((item) => [item.key, item.value]));
    const savedAvailabilityColor = settingMap.get("agenda.availability_color");
    if (typeof savedAvailabilityColor === "string" && /^#[0-9a-f]{6}$/i.test(savedAvailabilityColor)) {
      setAvailabilityColor(savedAvailabilityColor);
    } else {
      setAvailabilityColor(DEFAULT_AVAILABILITY_COLOR);
    }

    if (!agendaQuery.data?.professionals?.length) return;
    const savedColors = settingMap.get("agenda.professional_colors");
    const saved = savedColors && typeof savedColors === "object" ? (savedColors as Record<string, unknown>) : {};
    const nextColors: Record<string, string> = {};

    agendaQuery.data.professionals.forEach((professional, index) => {
      const maybeSaved = saved?.[professional.id];
      if (typeof maybeSaved === "string" && /^#[0-9a-f]{6}$/i.test(maybeSaved)) {
        nextColors[professional.id] = maybeSaved;
      } else {
        nextColors[professional.id] = colorFromSeed(`${professional.id}-${index}`);
      }
    });
    setProfessionalColors(nextColors);
  }, [agendaQuery.data?.professionals, settingsQuery.data?.data]);

  useEffect(() => {
    const onFullscreen = () => {
      const active = document.fullscreenElement === boardRef.current;
      setIsFullscreen(active);
    };
    document.addEventListener("fullscreenchange", onFullscreen);
    return () => document.removeEventListener("fullscreenchange", onFullscreen);
  }, []);

  useEffect(() => {
    if (!selectedAppointment) {
      setEditUnitId("");
      setEditProfessionalId("");
      setEditProcedure("");
      setEditStartsAt("");
      setEditEndsAt("");
      setEditStatus("agendada");
      setEditConfirmationStatus("pendente");
      setEditNotes("");
      setEditAttendanceStatus("pendente");
      setEditAttendanceNotes("");
      setEditNextAppointmentStatus("nao_definido");
      setAppointmentDeleteConfirmOpen(false);
      setAppointmentRescheduleOpen(false);
      setAppointmentRescheduleSelectedSlotId("");
      setAppointmentReturnOpen(false);
      setAppointmentReturnSelectedSlotId("");
      setAppointmentReturnSelectedDayKey("");
      setAppointmentPatientCardOpen(false);
      setAppointmentPatientEditOpen(false);
      setAppointmentPatientDeleteConfirmOpen(false);
      setAppointmentPatientTab("resumo");
      setAppointmentPatientFormName("");
      setAppointmentPatientFormCpf("");
      setAppointmentPatientFormEmail("");
      setAppointmentPatientFormBirthDate("");
      setAppointmentPatientFormStatus("ativo");
      setAppointmentPatientFormTags("");
      setAppointmentPatientFormNotes("");
      return;
    }

    setEditUnitId(selectedAppointment.unit_id);
    setEditProfessionalId(selectedAppointment.professional_id ?? "");
    setEditProcedure(selectedAppointment.procedure_type ?? "");
    setEditStartsAt(toDateTimeLocalInput(selectedAppointment.starts_at));
    setEditEndsAt(toDateTimeLocalInput(selectedAppointment.ends_at));
    setEditStatus(selectedAppointment.status || "agendada");
    setEditConfirmationStatus(selectedAppointment.confirmation_status || "pendente");
    setEditNotes(selectedAppointment.notes ?? "");
    setEditAttendanceStatus(resolveAppointmentAttendanceStatus(selectedAppointment));
    setEditAttendanceNotes(selectedAppointment.attendance_notes ?? "");
    setEditNextAppointmentStatus(resolveNextAppointmentStatus(selectedAppointment));
    setAppointmentReturnOpen(false);
    setAppointmentReturnSelectedSlotId("");
    setAppointmentReturnSelectedDayKey("");
  }, [selectedAppointment]);

  const dataset = agendaQuery.data ?? EMPTY_AGENDA_DATASET;
  const patientsById = new Map(dataset.patients.map((item) => [item.id, item]));
  const unitsById = new Map(dataset.units.map((item) => [item.id, item.name]));
  const unitsByUnitId = new Map(dataset.units.map((item) => [item.id, item]));
  const professionalsById = new Map(dataset.professionals.map((item) => [item.id, item]));
  const visibleUnits =
    unitSelectionLocked && scopedUnitId
      ? dataset.units.filter((unit) => unit.id === scopedUnitId)
      : dataset.units;
  const serviceCatalog = (dataset.serviceCatalog ?? []).map((item) => item.name);
  const createServiceCatalog =
    unitsByUnitId.get(unitId)?.services?.length
      ? [...(unitsByUnitId.get(unitId)?.services ?? [])]
      : serviceCatalog;
  const manualBookingBaseCatalog =
    unitsByUnitId.get(manualBookingUnitId)?.services?.length
      ? [...(unitsByUnitId.get(manualBookingUnitId)?.services ?? [])]
      : serviceCatalog;
  const manualBookingProfessional = manualBookingProfessionalId
    ? professionalsById.get(manualBookingProfessionalId)
    : undefined;
  const manualBookingServiceCatalog = manualBookingBaseCatalog.filter((serviceName) =>
    professionalCanPerformService(manualBookingProfessional, serviceName),
  );
  const editServiceCatalog =
    unitsByUnitId.get(editUnitId)?.services?.length
      ? [...(unitsByUnitId.get(editUnitId)?.services ?? [])]
      : serviceCatalog;
  const createProcedureOptions = buildProcedureOptions(createServiceCatalog, procedure);
  const manualBookingProcedureOptions = buildProcedureOptions(
    manualBookingProfessional ? manualBookingServiceCatalog : manualBookingBaseCatalog,
    manualBookingProcedure,
  );
  const editProcedureOptions = buildProcedureOptions(editServiceCatalog, editProcedure);
  const visibleProfessionals =
    unitFilter === "all"
      ? dataset.professionals
      : dataset.professionals.filter((item) => item.unit_id === unitFilter);
  const professionalsForSelectedUnit = dataset.professionals.filter(
    (item) => !unitId || item.unit_id === unitId,
  );

  const weekDays = Array.from({ length: 7 }, (_, index) => {
    const date = addDays(weekAnchor, index);
    return {
      date,
      key: toDayKey(date),
      label: WEEK_DAY_OPTIONS[date.getDay()]?.label ?? "",
      dayOfMonth: `${date.getDate()}`.padStart(2, "0"),
    };
  });
  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);
  const focusedDay = {
    date: focusedDate,
    key: toDayKey(focusedDate),
    label: WEEK_DAY_OPTIONS[focusedDate.getDay()]?.label ?? "",
    dayOfMonth: `${focusedDate.getDate()}`.padStart(2, "0"),
  };
  const selectedWeekDays = weekDays.filter((item) => selectedDayKeys.includes(item.key));
  const futureWeekDays = weekDays.filter((item) => item.date >= todayStart);
  const selectedCurrentOrFutureWeekDays = selectedWeekDays.filter((item) => item.date >= todayStart);

  const displayDays =
    viewMode === "day"
      ? [focusedDay]
      : selectedCurrentOrFutureWeekDays.length
        ? selectedCurrentOrFutureWeekDays
        : focusedDate < todayStart
          ? [focusedDay]
          : futureWeekDays.slice(0, 1);

  const appointments: EnrichedAppointment[] = dataset.appointments
    .map((appointment) => {
      const patient = patientsById.get(appointment.patient_id);
      const unit = unitsById.get(appointment.unit_id) ?? "Unidade nao identificada";
      const professional = appointment.professional_id
        ? professionalsById.get(appointment.professional_id)
        : undefined;
      const lastConversation = dataset.conversations
        .filter((conversation) => conversation.patient_id === appointment.patient_id)
        .sort(
          (left, right) =>
            new Date(right.last_message_at || 0).getTime() - new Date(left.last_message_at || 0).getTime(),
        )[0];

      return {
        ...appointment,
        patient_name: patient?.full_name ?? "Paciente nao identificado",
        patient_phone: patient?.phone ?? "",
        unit_name: unit,
        professional_name: professional?.full_name ?? "Nao definido",
        last_conversation: lastConversation?.last_message_at ?? null,
      };
    })
    .filter((appointment) => {
      const term = search.toLowerCase().trim();
      const haystack =
        `${appointment.patient_name} ${appointment.procedure_type} ${appointment.unit_name} ${appointment.professional_name}`.toLowerCase();
      const bySearch = !term || haystack.includes(term);
      const byStatus = statusFilter === "all" || appointment.status === statusFilter;
      const byUnit = unitFilter === "all" || appointment.unit_id === unitFilter;
      const byProfessional =
        !appointment.professional_id ||
        !selectedProfessionalIds.length ||
        selectedProfessionalIds.includes(appointment.professional_id);
      const byDisplayedDay = displayDays.some((item) => item.key === toDayKey(new Date(appointment.starts_at)));
      return bySearch && byStatus && byUnit && byProfessional && byDisplayedDay;
    })
    .sort((left, right) => new Date(left.starts_at).getTime() - new Date(right.starts_at).getTime());

  useEffect(() => {
    if (!isDemoUser) return;
    if (!demoTourAppointmentId) return;
    if (!appointments.some((appointment) => appointment.id === demoTourAppointmentId)) return;

    dispatchDemoTourEvent({
      type: "agenda_ready",
      appointmentId: demoTourAppointmentId,
    });
  }, [appointments, demoTourAppointmentId, isDemoUser]);

  if (agendaQuery.isLoading || sessionQuery.isLoading) return <LoadingState message="Carregando agenda operacional..." />;
  if (agendaQuery.isError || !agendaQuery.data) return <ErrorState message="Nao foi possivel carregar a agenda." />;

  const now = new Date();
  const tomorrowStart = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);

  const todayAppointments = dataset.appointments.filter((item) => {
    const starts = new Date(item.starts_at);
    return starts >= todayStart && starts < tomorrowStart;
  });
  const pendingConfirmation = dataset.appointments.filter((item) => item.confirmation_status === "pendente").length;
  const selectedVisibleProfessionalIds = selectedProfessionalIds.filter((id) =>
    visibleProfessionals.some((professional) => professional.id === id),
  );
  const possibleSlots = Math.max(
    0,
    Math.max(1, selectedVisibleProfessionalIds.length || visibleProfessionals.length) * 14 - todayAppointments.length,
  );
  const currentRangeLabel =
    viewMode === "day" ? formatDateBR(focusedDate) : `${formatDateBR(weekAnchor)} - ${formatDateBR(addDays(weekAnchor, 6))}`;
  const visibleDaysLabel =
    viewMode === "day"
      ? `${focusedDay.label}, ${focusedDay.dayOfMonth}`
      : displayDays.length === futureWeekDays.length
        ? "Semana completa"
        : `${displayDays.length} dia(s) visiveis`;
  const activeProfessionalCount = selectedVisibleProfessionalIds.length || visibleProfessionals.length;
  const activeFilterCount =
    Number(Boolean(search.trim())) +
    Number(statusFilter !== "all") +
    Number(unitFilter !== "all") +
    Number(selectedVisibleProfessionalIds.length > 0) +
    Number(viewMode === "week" && displayDays.length !== futureWeekDays.length);
  const monthCalendarDays = getMonthGrid(monthCursor);
  const professionalsForBoard = visibleProfessionals.filter(
    (item) =>
      !selectedVisibleProfessionalIds.length || selectedVisibleProfessionalIds.includes(item.id),
  );
  const hasUnassignedAppointments = appointments.some((item) => !item.professional_id);
  const boardLanes: BoardLane[] = professionalsForBoard.length
    ? [
        ...professionalsForBoard.map((item) => ({
          id: item.id,
          professionalId: item.id,
          professionalName: item.full_name,
          unitId: item.unit_id ?? (unitFilter !== "all" ? unitFilter : null),
          unitName: item.unit_id
            ? unitsById.get(item.unit_id) ?? "Unidade nao identificada"
            : unitFilter !== "all"
              ? unitsById.get(unitFilter) ?? "Unidade nao identificada"
              : "Defina a unidade",
          label: formatBoardLaneLabel(item.full_name),
          color: professionalColors[item.id] ?? "#9ad0ec",
          workingDays: item.working_days ?? [],
          shiftStart: item.shift_start,
          shiftEnd: item.shift_end,
        })),
        ...(hasUnassignedAppointments
          ? [
              {
                id: "__unassigned__",
                professionalId: null,
                professionalName: "Sem profissional",
                unitId: unitFilter !== "all" ? unitFilter : null,
                unitName: unitFilter !== "all" ? unitsById.get(unitFilter) ?? "Unidade nao identificada" : "Todas as unidades",
                label: "Sem profissional",
                color: "#d6d3d1",
                workingDays: [],
                shiftStart: "08:00",
                shiftEnd: "18:00",
              },
            ]
          : []),
      ]
    : [
        {
          id: "__placeholder__",
          professionalId: null,
          professionalName: "Sem equipe",
          unitId: unitFilter !== "all" ? unitFilter : null,
          unitName: unitFilter !== "all" ? unitsById.get(unitFilter) ?? "Unidade nao identificada" : "Todas as unidades",
          label: "Sem equipe",
          color: "#e7e5e4",
          workingDays: [],
          shiftStart: "08:00",
          shiftEnd: "18:00",
          isPlaceholder: true,
        },
      ];
  const boardLaneCount = Math.max(boardLanes.length, 1);
  const boardStartMinutes = clamp(
    Math.min(
      7 * 60,
      ...professionalsForBoard.map((item) => parseTimeToMinutes(item.shift_start, 8 * 60) - 30),
    ),
    5 * 60,
    13 * 60,
  );
  const boardEndMinutes = clamp(
    Math.max(
      19 * 60,
      ...professionalsForBoard.map((item) => parseTimeToMinutes(item.shift_end, 18 * 60) + 30),
    ),
    14 * 60,
    23 * 60,
  );
  const totalMinutes = Math.max(120, boardEndMinutes - boardStartMinutes);
  const pxPerMinute = boardMinuteScale;
  const boardHeight = totalMinutes * pxPerMinute;
  const slotMarks = Array.from({ length: Math.floor(totalMinutes / 15) + 1 }, (_, index) => boardStartMinutes + index * 15);
  const boardDayWidth = boardLaneCount * boardLaneWidth;
  const boardMinWidth = 72 + Math.max(displayDays.length, 1) * boardDayWidth;
  const boardGridTemplate = displayDays.length
    ? `72px ${displayDays.map(() => `${boardDayWidth}px`).join(" ")}`
    : "72px minmax(240px, 1fr)";
  const professionalsForEditedUnit = dataset.professionals.filter(
    (item) => !editUnitId || item.unit_id === editUnitId,
  );
  const selectedAppointmentPatient =
    selectedAppointment && selectedAppointment.patient_id
      ? patientsById.get(selectedAppointment.patient_id) ?? null
      : null;
  const selectedAppointmentPatientAppointments = selectedAppointmentPatient
    ? dataset.appointments
        .filter((item) => item.patient_id === selectedAppointmentPatient.id)
        .sort((left, right) => new Date(right.starts_at).getTime() - new Date(left.starts_at).getTime())
    : [];
  const selectedAppointmentPatientConversations = selectedAppointmentPatient
    ? dataset.conversations
        .filter((item) => item.patient_id === selectedAppointmentPatient.id)
        .sort((left, right) => new Date(right.last_message_at || 0).getTime() - new Date(left.last_message_at || 0).getTime())
    : [];
  const selectedAppointmentPatientDocuments = selectedAppointmentPatient
    ? dataset.documents
        .filter((item) => item.patient_id === selectedAppointmentPatient.id)
        .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime())
    : [];
  const selectedAppointmentPatientHistory = selectedAppointmentPatient
    ? [
        {
          date: selectedAppointmentPatient.created_at,
          title: "Paciente cadastrado",
          description: selectedAppointmentPatient.origin || "Origem nao informada",
        },
        ...selectedAppointmentPatientAppointments.map((appointment) => ({
          date: appointment.starts_at,
          title: isEvaluationProcedureName(appointment.procedure_type) ? "Avaliacao registrada" : "Procedimento registrado",
          description: `${appointment.procedure_type} â€¢ ${appointment.status} â€¢ ${appointment.confirmation_status}`,
        })),
        ...selectedAppointmentPatientConversations.map((conversation) => ({
          date: conversation.last_message_at || "",
          title: "Conversa registrada",
          description: `${conversation.channel} â€¢ ${conversation.status}`,
        })),
        ...selectedAppointmentPatientDocuments.map((document) => ({
          date: document.created_at,
          title: "Documento vinculado",
          description: `${document.title} â€¢ ${document.document_type}`,
        })),
      ]
        .filter((item) => item.date)
        .sort((left, right) => new Date(right.date).getTime() - new Date(left.date).getTime())
    : [];
  const appointmentRescheduleChoices =
    selectedAppointment && editUnitId && editProcedure.trim()
      ? buildRescheduleSlotChoices({
          anchorDate: new Date(editStartsAt || selectedAppointment.starts_at),
          unitId: editUnitId,
          procedureType: editProcedure.trim(),
          excludeAppointmentId: selectedAppointment.id,
          serviceCatalog: dataset.serviceCatalog,
          professionals: dataset.professionals,
          appointments: dataset.appointments,
        })
      : [];
  const appointmentRescheduleDayOptions = Array.from(
    appointmentRescheduleChoices.reduce((map, choice) => {
      const current = map.get(choice.dayKey);
      if (current) {
        current.count += 1;
      } else {
        map.set(choice.dayKey, {
          dayKey: choice.dayKey,
          label: formatRescheduleDayLabel(choice.dayKey),
          count: 1,
        });
      }
      return map;
    }, new Map<string, { dayKey: string; label: string; count: number }>()),
  ).map(([, option]) => option);
  const activeRescheduleDayKey =
    appointmentRescheduleSelectedDayKey &&
    appointmentRescheduleDayOptions.some((option) => option.dayKey === appointmentRescheduleSelectedDayKey)
      ? appointmentRescheduleSelectedDayKey
      : appointmentRescheduleDayOptions[0]?.dayKey || "";
  const appointmentRescheduleVisibleChoices = activeRescheduleDayKey
    ? appointmentRescheduleChoices.filter((choice) => choice.dayKey === activeRescheduleDayKey)
    : appointmentRescheduleChoices;
  const selectedRescheduleChoiceRaw =
    appointmentRescheduleChoices.find((choice) => choice.id === appointmentRescheduleSelectedSlotId) ?? null;
  const selectedRescheduleChoice =
    selectedRescheduleChoiceRaw && selectedRescheduleChoiceRaw.dayKey === activeRescheduleDayKey
      ? selectedRescheduleChoiceRaw
      : null;
  const appointmentReturnChoices =
    selectedAppointment && editUnitId && editProcedure.trim()
      ? buildRescheduleSlotChoices({
          anchorDate: new Date(editEndsAt || selectedAppointment.ends_at || editStartsAt || selectedAppointment.starts_at),
          unitId: editUnitId,
          procedureType: editProcedure.trim(),
          excludeAppointmentId: "",
          serviceCatalog: dataset.serviceCatalog,
          professionals: dataset.professionals,
          appointments: dataset.appointments,
        })
      : [];
  const appointmentReturnDayOptions = Array.from(
    appointmentReturnChoices.reduce((map, choice) => {
      const current = map.get(choice.dayKey);
      if (current) {
        current.count += 1;
      } else {
        map.set(choice.dayKey, {
          dayKey: choice.dayKey,
          label: formatRescheduleDayLabel(choice.dayKey),
          count: 1,
        });
      }
      return map;
    }, new Map<string, { dayKey: string; label: string; count: number }>()),
  ).map(([, option]) => option);
  const activeReturnDayKey =
    appointmentReturnSelectedDayKey &&
    appointmentReturnDayOptions.some((option) => option.dayKey === appointmentReturnSelectedDayKey)
      ? appointmentReturnSelectedDayKey
      : appointmentReturnDayOptions[0]?.dayKey || "";
  const appointmentReturnVisibleChoices = activeReturnDayKey
    ? appointmentReturnChoices.filter((choice) => choice.dayKey === activeReturnDayKey)
    : appointmentReturnChoices;
  const selectedReturnChoiceRaw =
    appointmentReturnChoices.find((choice) => choice.id === appointmentReturnSelectedSlotId) ?? null;
  const selectedReturnChoice =
    selectedReturnChoiceRaw && selectedReturnChoiceRaw.dayKey === activeReturnDayKey
      ? selectedReturnChoiceRaw
      : null;
  const localPatientMatches =
    manualBookingPatientSearch.trim().length >= 2
      ? dataset.patients.filter((patient) => {
          const haystack = `${patient.full_name} ${patient.phone}`.toLowerCase();
          return haystack.includes(manualBookingPatientSearch.trim().toLowerCase());
        })
      : dataset.patients.slice(0, 8);
  const manualBookingSelectedPatientBase = manualBookingPatientId
    ? patientsById.get(manualBookingPatientId) ??
      patientLookupQuery.data?.find((patient) => patient.id === manualBookingPatientId) ??
      null
    : null;
  const manualBookingPatientOptions = Array.from(
    new Map(
      [...(manualBookingSelectedPatientBase ? [manualBookingSelectedPatientBase] : []), ...localPatientMatches, ...(patientLookupQuery.data ?? [])].map(
        (patient) => [patient.id, patient],
      ),
    ).values(),
  ).slice(0, 12);
  const manualBookingSelectedPatient =
    manualBookingPatientOptions.find((patient) => patient.id === manualBookingPatientId) ??
    (manualBookingPatientId ? patientsById.get(manualBookingPatientId) ?? null : null);
  const manualBookingSelectedPatientAppointments = manualBookingSelectedPatient
    ? dataset.appointments
        .filter((appointment) => appointment.patient_id === manualBookingSelectedPatient.id)
        .sort((left, right) => new Date(right.starts_at).getTime() - new Date(left.starts_at).getTime())
    : [];
  const manualBookingEvaluationHistory = manualBookingSelectedPatientAppointments.filter((appointment) =>
    isEvaluationProcedureName(appointment.procedure_type),
  );
  const manualBookingHasEvaluation = manualBookingEvaluationHistory.length > 0;
  const manualBookingEvaluationServiceName = resolveEvaluationServiceName(
    dataset.serviceCatalog,
    manualBookingBaseCatalog,
  );
  const manualBookingBookedProcedure =
    manualBookingPatientMode === "new" && manualBookingNeedsEvaluation
      ? manualBookingEvaluationServiceName
      : manualBookingProcedure;
  const manualBookingServiceItem = resolveServiceCatalogItem(dataset.serviceCatalog, manualBookingBookedProcedure);
  const manualBookingDurationMinutes = manualBookingBookedProcedure ? manualBookingServiceItem?.duration_minutes ?? 60 : 0;
  const manualBookingExpectedEnd =
    manualBookingStartsAt && manualBookingDurationMinutes
      ? addMinutesToLocalInput(manualBookingStartsAt, manualBookingDurationMinutes)
      : "";
  const manualBookingSlotEnd =
    manualBookingContext
      ? combineDateAndMinutes(new Date(manualBookingContext.startsAt), manualBookingContext.slotEndMinutes)
      : "";
  const manualBookingFitsSelectedSlot = !manualBookingProcedure
    ? true
    : Boolean(
        manualBookingContext &&
          manualBookingStartsAt &&
          manualBookingExpectedEnd &&
          new Date(manualBookingStartsAt) >= new Date(manualBookingContext.startsAt) &&
          new Date(manualBookingExpectedEnd) <= new Date(manualBookingSlotEnd),
      );

  const handleEditStatusChange = (nextStatus: string) => {
    setEditStatus(nextStatus);

    if (nextStatus === "concluida") {
      setEditAttendanceStatus("compareceu");
      setEditConfirmationStatus((current) => (current === "pendente" ? "confirmada" : current));
      return;
    }

    if (nextStatus === "falta") {
      setEditAttendanceStatus("faltou");
      return;
    }

    setEditAttendanceStatus("pendente");
    if (nextStatus !== "concluida") {
      setEditNextAppointmentStatus("nao_definido");
    }
  };

  const handleEditAttendanceStatusChange = (nextAttendanceStatus: string) => {
    setEditAttendanceStatus(nextAttendanceStatus);

    if (nextAttendanceStatus === "compareceu") {
      setEditStatus("concluida");
      setEditConfirmationStatus((current) => (current === "pendente" ? "confirmada" : current));
      return;
    }

    if (nextAttendanceStatus === "faltou") {
      setEditStatus("falta");
      setEditNextAppointmentStatus("nao_definido");
      return;
    }

    const originalStatus =
      selectedAppointment && !["concluida", "falta"].includes(selectedAppointment.status)
        ? selectedAppointment.status
        : "agendada";

    setEditStatus(originalStatus);
    setEditNextAppointmentStatus("nao_definido");
  };

  const buildCurrentAppointmentPayload = (overrides: Record<string, unknown> = {}) => {
    if (!selectedAppointment) return null;
    if (!editUnitId || !editProcedure.trim() || !editStartsAt) {
      toast.error("Preencha unidade, procedimento e data/hora.");
      return null;
    }

    const parsedStartsAt = new Date(editStartsAt);
    if (Number.isNaN(parsedStartsAt.getTime())) {
      toast.error("Data/hora de inicio invalida.");
      return null;
    }

    let parsedEndsAt: Date | null = null;
    if (editEndsAt) {
      parsedEndsAt = new Date(editEndsAt);
      if (Number.isNaN(parsedEndsAt.getTime())) {
        toast.error("Data/hora de termino invalida.");
        return null;
      }
      if (parsedEndsAt <= parsedStartsAt) {
        toast.error("O termino deve ser maior que o inicio.");
        return null;
      }
    }

    return {
      unit_id: editUnitId,
      professional_id: editProfessionalId || null,
      procedure_type: editProcedure.trim(),
      starts_at: parsedStartsAt.toISOString(),
      ends_at: parsedEndsAt ? parsedEndsAt.toISOString() : null,
      status: editStatus,
      confirmation_status: editConfirmationStatus,
      notes: editNotes,
      attendance_status: editAttendanceStatus,
      attendance_notes: editAttendanceNotes,
      next_appointment_status: editNextAppointmentStatus,
      ...overrides,
    };
  };

  const handleSaveAppointmentEdits = () => {
    if (!canEditAgenda) {
      toast.error("Seu perfil nao pode editar consultas nesta pagina.");
      return;
    }
    if (!selectedAppointment) return;
    const payload = buildCurrentAppointmentPayload();
    if (!payload) return;

    updateMutation.mutate(
      {
        appointmentId: selectedAppointment.id,
        payload,
      },
      {
        onSuccess: () => {
          toast.success("Consulta atualizada com sucesso.");
          setAppointmentEditorOpen(false);
          setSelectedAppointment(null);
        },
      },
    );
  };

  const handleConfirmReturnAppointment = () => {
    if (!canCreateAgenda) {
      toast.error("Seu perfil nao pode criar consultas nesta pagina.");
      return;
    }
    if (!selectedAppointment) return;
    if (!selectedReturnChoice) {
      toast.error("Escolha um horario para o retorno.");
      return;
    }

    const currentAppointmentPayload = buildCurrentAppointmentPayload({
      next_appointment_status: "retorno_agendado",
    });
    if (!currentAppointmentPayload) return;

    createReturnAppointmentMutation.mutate({
      choice: selectedReturnChoice,
      currentAppointmentPayload,
    });
  };

  const handleToggleFullscreen = async () => {
    if (!boardRef.current) return;
    if (document.fullscreenElement === boardRef.current) {
      await document.exitFullscreen();
      return;
    }
    await boardRef.current.requestFullscreen();
  };

  const handlePreviousWeek = () => {
    setWeekAnchor((current) => addDays(current, -7));
    setMonthCursor((current) => addDays(current, -7));
  };

  const handleNextWeek = () => {
    setWeekAnchor((current) => addDays(current, 7));
    setMonthCursor((current) => addDays(current, 7));
  };

  const handleGoToday = () => {
    const today = new Date();
    setFocusedDate(today);
    setWeekAnchor(startOfWeekMonday(today));
    setMonthCursor(today);
  };

  const handleStartBoardWidthResize = (event: ReactMouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    setBoardResizeState({
      axis: "x",
      startPointer: event.clientX,
      startValue: boardLaneWidth,
    });
  };

  const handleStartBoardHeightResize = (event: ReactMouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    setBoardResizeState({
      axis: "y",
      startPointer: event.clientY,
      startValue: boardMinuteScale,
    });
  };

  const handleOpenManualBooking = (params: {
    day: { date: Date; key: string };
    lane: BoardLane;
    slot: AvailabilityCard;
  }) => {
    if (!canCreateAgenda) {
      toast.error("Seu perfil nao pode criar consultas nesta pagina.");
      return;
    }
    const { day, lane, slot } = params;
    if (!lane.professionalId) {
      toast.error("Esse horario nao esta vinculado a um profissional valido.");
      return;
    }
    if (!lane.unitId) {
      toast.error("Selecione uma unidade antes de agendar nesse horario.");
      return;
    }

    const startsAtValue = combineDateAndMinutes(day.date, slot.startMinutes);

    setAppointmentEditorOpen(false);
    setSelectedAppointment(null);
    setManualBookingContext({
      dayKey: day.key,
      unitId: lane.unitId,
      unitName: lane.unitName,
      professionalId: lane.professionalId,
      professionalName: lane.professionalName,
      startsAt: startsAtValue,
      slotStartMinutes: slot.startMinutes,
      slotEndMinutes: slot.endMinutes,
    });
    setManualBookingOpen(true);
    setManualBookingPatientMode("existing");
    setManualBookingPatientSearch("");
    setManualBookingPatientId("");
    setManualBookingUnitId(lane.unitId);
    setManualBookingProfessionalId(lane.professionalId);
    setManualBookingProcedure("");
    setManualBookingStartsAt(startsAtValue);
    setManualBookingNotes("");
    setManualBookingNewFullName("");
    setManualBookingNewPhone("");
    setManualBookingNewCpf("");
    setManualBookingNewEmail("");
    setManualBookingNewBirthDate("");
  };

  const populateAppointmentPatientForm = (patient: PatientItem | null) => {
    if (!patient) return;
    setAppointmentPatientFormName(patient.full_name || "");
    setAppointmentPatientFormCpf(patient.cpf || "");
    setAppointmentPatientFormEmail(patient.email || "");
    setAppointmentPatientFormBirthDate(patient.birth_date || "");
    setAppointmentPatientFormStatus(patient.status || "ativo");
    setAppointmentPatientFormTags((patient.tags_cache || []).join(", "));
    setAppointmentPatientFormNotes(patient.operational_notes || "");
  };

  const handleOpenAppointmentEditor = (appointment: EnrichedAppointment, mode: "edit" | "reschedule" = "edit") => {
    setManualBookingOpen(false);
    setManualBookingContext(null);
    setSelectedAppointment(appointment);
    setAppointmentEditorOpen(true);
    setAppointmentDeleteConfirmOpen(false);
    setAppointmentRescheduleOpen(mode === "reschedule");
    setAppointmentRescheduleSelectedSlotId("");
    setAppointmentRescheduleSelectedDayKey("");
    setAppointmentReturnOpen(false);
    setAppointmentReturnSelectedSlotId("");
    setAppointmentReturnSelectedDayKey("");
    setAppointmentPatientCardOpen(false);
    setAppointmentPatientEditOpen(false);
    setAppointmentPatientDeleteConfirmOpen(false);
  };

  const agendaOverviewStats = [
    { label: "Hoje", value: numberFormatter.format(todayAppointments.length), helper: "consultas no dia" },
    { label: "Pendente", value: numberFormatter.format(pendingConfirmation), helper: "aguardando confirmacao" },
    { label: "Encaixes", value: numberFormatter.format(possibleSlots), helper: "estimativa livre" },
    { label: "Visao ativa", value: numberFormatter.format(activeProfessionalCount), helper: visibleDaysLabel },
  ];

  const boardDockControls = (
      <div className="pointer-events-auto flex max-w-[calc(100vw-24px)] items-center gap-0.5 rounded-2xl border border-stone-200/65 bg-white/88 p-1 text-stone-800 shadow-xl shadow-stone-950/15 backdrop-blur-md">
        <button
          type="button"
          className="inline-flex h-8 items-center gap-1 rounded-xl px-2 text-[11px] font-semibold text-stone-700 transition hover:bg-stone-100"
          onClick={() => setAgendaControlsOpen(true)}
          title="Abrir ajustes da agenda"
        >
          <ListFilter size={14} />
          <span className="hidden sm:inline">Ajustes</span>
          {activeFilterCount ? (
            <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700">
              {activeFilterCount}
            </span>
          ) : null}
        </button>
        <button
          type="button"
          className="inline-flex h-8 items-center gap-1 rounded-xl px-2 text-[11px] font-semibold text-stone-700 transition hover:bg-stone-100"
          onClick={() => setAppointmentListOpen(true)}
          title="Abrir lista de consultas"
        >
          <List size={14} />
          <span className="hidden sm:inline">Lista</span>
        </button>
        <div className="mx-0.5 h-5 w-px bg-stone-200" />
        <div className="mr-1 hidden min-w-[118px] px-2 text-right md:block">
          <p className="text-[10px] font-bold leading-3 text-stone-800">
            {viewMode === "day" ? currentRangeLabel : `${formatDateBR(weekAnchor)} - ${formatDateBR(addDays(weekAnchor, 6))}`}
          </p>
          <p className="mt-0.5 text-[8px] uppercase tracking-[0.14em] text-stone-500">
            {viewMode === "day" ? visibleDaysLabel : "Semana"}
          </p>
        </div>
        <button
          type="button"
          className="grid h-8 w-8 place-items-center rounded-xl transition hover:bg-stone-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/40"
          onClick={handlePreviousWeek}
          aria-label="Semana anterior"
          title="Semana anterior"
        >
          <ChevronLeft size={15} />
        </button>
        <button
          type="button"
          className="h-8 rounded-xl px-2.5 text-[11px] font-semibold text-stone-700 transition hover:bg-stone-100"
          onClick={handleGoToday}
          title="Hoje"
        >
          Hoje
        </button>
        <button
          type="button"
          className="grid h-8 w-8 place-items-center rounded-xl transition hover:bg-stone-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/40"
          onClick={handleNextWeek}
          aria-label="Proxima semana"
          title="Proxima semana"
        >
          <ChevronRight size={15} />
        </button>
        <div className="mx-0.5 h-5 w-px bg-stone-200" />
        <button
          type="button"
          className={`h-8 rounded-xl px-2.5 text-[11px] font-semibold transition ${
            viewMode === "day" ? "bg-stone-900 text-white" : "text-stone-700 hover:bg-stone-100"
          }`}
          onClick={() => setViewMode("day")}
          title="Ver por dia"
        >
          Dia
        </button>
        <button
          type="button"
          className={`h-8 rounded-xl px-2.5 text-[11px] font-semibold transition ${
            viewMode === "week" ? "bg-stone-900 text-white" : "text-stone-700 hover:bg-stone-100"
          }`}
          onClick={() => setViewMode("week")}
          title="Ver por semana"
        >
          Semana
        </button>
        <button
          type="button"
          className={`ml-0.5 grid h-8 w-8 place-items-center rounded-xl transition focus-visible:outline-none focus-visible:ring-2 ${
            isFullscreen
              ? "text-stone-600 hover:bg-rose-50 hover:text-rose-600 focus-visible:ring-rose-400/40"
              : "text-stone-600 hover:bg-stone-100 focus-visible:ring-emerald-500/40"
          }`}
          onClick={handleToggleFullscreen}
          aria-label={isFullscreen ? "Sair da tela cheia" : "Entrar em tela cheia"}
          title={isFullscreen ? "Sair da tela cheia" : "Tela cheia"}
        >
          {isFullscreen ? <Minimize size={14} /> : <Expand size={14} />}
        </button>
      </div>
  );

  const floatingBoardDock = isFullscreen ? (
    <div className="pointer-events-none fixed bottom-4 left-1/2 z-[68] flex w-full -translate-x-1/2 items-end justify-center px-3 sm:px-4 md:left-auto md:w-auto md:translate-x-0 md:right-[5.75rem] md:justify-end md:px-0 lg:right-24">
      {boardDockControls}
    </div>
  ) : null;

  const topBoardDock = !isFullscreen ? (
    <div className="flex w-full justify-center sm:justify-end lg:w-auto lg:min-w-[430px]">
      {boardDockControls}
    </div>
  ) : null;

  const floatingCreateAppointmentButton = canCreateAgenda ? (
    <button
      type="button"
      className="fixed bottom-28 right-3 z-[69] inline-flex h-11 items-center gap-2 rounded-full bg-emerald-500 px-4 text-sm font-semibold text-white shadow-2xl transition hover:scale-[1.02] hover:bg-emerald-600 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-emerald-300 sm:bottom-24 sm:right-4 md:bottom-24 md:right-6"
      onClick={() => setCreateAppointmentOpen(true)}
      aria-label="Nova consulta"
      title="Nova consulta"
    >
      <Plus size={16} />
      <span>Nova consulta</span>
    </button>
  ) : null;

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <Card className="flex min-h-0 flex-1 flex-col overflow-hidden border-stone-200 bg-white/95">
        <CardContent className="flex min-h-0 flex-1 flex-col p-1.5 sm:p-2">
          <div className="mb-1.5 flex min-w-0 flex-col gap-1.5 pb-1 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex min-w-0 items-start gap-1.5 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              {agendaOverviewStats.map((item) => (
                <div
                  key={item.label}
                  className="min-w-[132px] rounded-2xl border border-stone-200 bg-stone-50/95 px-3 py-1.5 shadow-sm"
                >
                  <p className="text-[9px] font-semibold uppercase tracking-[0.18em] text-stone-500">{item.label}</p>
                  <div className="mt-1 flex items-end gap-1">
                    <p className="text-sm font-semibold leading-none text-stone-900 sm:text-base">{item.value}</p>
                    <p className="truncate pb-0.5 text-[10px] text-stone-500">{item.helper}</p>
                  </div>
                </div>
              ))}
            </div>
            {topBoardDock}
          </div>

          <div ref={boardRef} className="relative min-h-0 flex-1 overflow-auto rounded-[20px] border border-stone-200 bg-white">
              {floatingBoardDock}
              <div style={{ minWidth: boardMinWidth }}>
                <div
                  className="sticky top-0 z-10 grid border-b border-stone-200 bg-stone-50/95 backdrop-blur"
                  style={{ gridTemplateColumns: boardGridTemplate }}
                >
                  <div className="border-r border-stone-200 bg-stone-50 p-2 text-xs font-semibold text-stone-500">Hora</div>
                  {displayDays.length ? (
                    displayDays.map((day) => (
                      <div key={`board-head-${day.key}`} className="relative border-r border-stone-200 bg-stone-50">
                        <div className="border-b border-stone-200 px-3 py-2 text-sm font-semibold text-stone-700">
                          {day.label}, {day.dayOfMonth}
                        </div>
                        <div
                          className="relative grid"
                          style={{ gridTemplateColumns: `repeat(${boardLaneCount}, ${boardLaneWidth}px)` }}
                        >
                          {boardLanes.map((lane, laneIndex) => (
                            <div
                              key={`board-head-${day.key}-${lane.id}`}
                              className={`px-2 py-2 text-[11px] font-medium text-stone-600 ${laneIndex < boardLaneCount - 1 ? "border-r border-stone-200" : ""}`}
                              style={{
                                backgroundColor: hexToRgba(lane.color, lane.isPlaceholder ? 0.08 : 0.15),
                              }}
                            >
                              <p className="truncate">{lane.label}</p>
                            </div>
                          ))}
                          {boardLanes.slice(0, -1).map((lane, laneIndex) => (
                            <button
                              key={`board-width-handle-${day.key}-${lane.id}`}
                              type="button"
                              className="absolute top-1/2 z-20 flex h-6 w-6 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-stone-300 bg-white/95 text-stone-600 shadow-sm transition hover:bg-stone-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
                              style={{ left: (laneIndex + 1) * boardLaneWidth, cursor: "ew-resize" }}
                              onMouseDown={handleStartBoardWidthResize}
                              aria-label="Arrastar para ajustar a largura da agenda"
                              title="Arraste para ajustar a largura da agenda"
                            >
                              <ChevronsLeftRight size={14} />
                            </button>
                          ))}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="p-3 text-sm text-stone-500">Selecione ao menos um dia.</div>
                  )}
                </div>

                <div className="grid" style={{ gridTemplateColumns: boardGridTemplate }}>
                  <div className="relative border-r border-stone-200 bg-stone-50" style={{ height: boardHeight }}>
                    {slotMarks.map((slot) => (
                      <div
                        key={`slot-mark-${slot}`}
                        className="absolute left-0 right-0 px-1 text-[9px] text-stone-500"
                        style={{ top: (slot - boardStartMinutes) * pxPerMinute }}
                      >
                        <div
                          className={`border-t px-0.5 ${
                            slot % 60 === 0
                              ? "border-stone-300"
                              : slot % 30 === 0
                                ? "border-dashed border-stone-200"
                                : "border-dotted border-stone-200"
                          }`}
                        >
                          {formatTimeFromMinutes(slot)}
                        </div>
                      </div>
                    ))}
                    {slotMarks
                      .filter((slot) => slot > boardStartMinutes && slot < boardEndMinutes && slot % 30 === 0)
                      .map((slot) => (
                        <button
                          key={`board-height-handle-${slot}`}
                          type="button"
                          className="absolute right-0 z-20 flex h-5 w-5 translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-stone-300 bg-white/95 text-stone-600 shadow-sm transition hover:bg-stone-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
                          style={{ top: (slot - boardStartMinutes) * pxPerMinute, cursor: "ns-resize" }}
                          onMouseDown={handleStartBoardHeightResize}
                          aria-label="Arrastar para ajustar a altura da agenda"
                          title="Arraste para ajustar a altura da agenda"
                        >
                          <ChevronsUpDown size={12} />
                        </button>
                      ))}
                  </div>

                  {displayDays.map((day) => {
                    const dayAppointments = appointments.filter((appointment) => toDayKey(new Date(appointment.starts_at)) === day.key);

                    return (
                      <div key={`board-day-${day.key}`} className="relative border-r border-stone-200" style={{ height: boardHeight, width: boardDayWidth }}>
                        {slotMarks.map((slot) => (
                          <div
                            key={`slot-line-${day.key}-${slot}`}
                            className={`pointer-events-none absolute left-0 right-0 ${
                              slot % 60 === 0
                                ? "border-t border-stone-300"
                                : slot % 30 === 0
                                  ? "border-t border-dashed border-stone-200"
                                  : "border-t border-dotted border-stone-200"
                            }`}
                            style={{ top: (slot - boardStartMinutes) * pxPerMinute }}
                          />
                        ))}
                        {boardLanes.map((lane, laneIndex) => {
                          const laneLeft = laneIndex * boardLaneWidth;
                          const laneAppointments = dayAppointments.filter((appointment) =>
                            lane.professionalId ? appointment.professional_id === lane.professionalId : !appointment.professional_id,
                          );
                          const availabilityCards = buildProfessionalAvailabilityCards({
                            date: day.date,
                            lane,
                            appointments: dayAppointments,
                            boardStartMinutes,
                            boardEndMinutes,
                            pxPerMinute,
                          });

                          return (
                            <div
                              key={`board-lane-${day.key}-${lane.id}`}
                              className={`pointer-events-none absolute top-0 bottom-0 ${laneIndex < boardLaneCount - 1 ? "border-r border-stone-200/80" : ""}`}
                              style={{ left: laneLeft, width: boardLaneWidth }}
                            >
                              {availabilityCards.map((item, index) => (
                                <button
                                  type="button"
                                  key={`availability-${day.key}-${lane.id}-${index}`}
                                  className={`pointer-events-auto absolute left-1 right-1 overflow-hidden rounded-xl border text-left shadow-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/60 ${
                                    canCreateAgenda ? "hover:brightness-95" : "cursor-not-allowed opacity-75"
                                  }`}
                                  style={{
                                    top: item.top,
                                    height: item.height,
                                    backgroundColor: hexToRgba(availabilityColor, 0.26),
                                    borderColor: hexToRgba(availabilityColor, 0.9),
                                    zIndex: 1,
                                  }}
                                  disabled={!canCreateAgenda}
                                  onClick={() => handleOpenManualBooking({ day, lane, slot: item })}
                                >
                                  {item.height >= 28 ? (
                                    <div className="flex h-full flex-col px-2 py-1 text-emerald-950">
                                      <p className="truncate text-[11px] font-semibold">
                                        Disponivel
                                      </p>
                                      {item.height >= 42 ? (
                                        <p className="truncate text-[10px] font-medium text-emerald-900/90">
                                          {lane.label}
                                        </p>
                                      ) : null}
                                      {item.height >= 56 ? (
                                        <p className="truncate text-[10px] text-emerald-900/75">
                                          {formatTimeFromMinutes(item.startMinutes)} - {formatTimeFromMinutes(item.endMinutes)}
                                        </p>
                                      ) : null}
                                    </div>
                                  ) : null}
                                </button>
                              ))}
                              {laneAppointments.map((appointment) => {
                                const start = new Date(appointment.starts_at);
                                const end = appointment.ends_at ? new Date(appointment.ends_at) : new Date(start.getTime() + 60 * 60 * 1000);
                                const startMin = start.getHours() * 60 + start.getMinutes();
                                const endMin = end.getHours() * 60 + end.getMinutes();
                                const clampedStart = clamp(startMin, boardStartMinutes, boardEndMinutes);
                                const clampedEnd = clamp(endMin, boardStartMinutes, boardEndMinutes);
                                const top = (clampedStart - boardStartMinutes) * pxPerMinute;
                                const height = Math.max(12, (clampedEnd - clampedStart) * pxPerMinute);
                                const color = appointment.professional_id ? professionalColors[appointment.professional_id] ?? "#9ad0ec" : "#d6d3d1";

                                return (
                                  <button
                                    type="button"
                                    key={appointment.id}
                                    data-tour-id={
                                      appointment.id === demoTourAppointmentId
                                        ? DEMO_TOUR_TARGETS.agendaAppointment
                                        : undefined
                                    }
                                    className="pointer-events-auto absolute left-1 right-1 overflow-hidden rounded-xl border p-2 text-left shadow-md transition hover:scale-[1.01] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
                                    style={{
                                      top,
                                      height,
                                      backgroundColor: hexToRgba(color, 0.98),
                                      borderColor: hexToRgba(color, 1),
                                      zIndex: 3,
                                    }}
                                    onClick={() => handleOpenAppointmentEditor(appointment)}
                                  >
                                    <div className="flex h-full flex-col">
                                      {height >= 30 ? (
                                        <p className="truncate text-[11px] font-semibold text-stone-700">
                                          {formatDateTimeBR(appointment.starts_at).slice(-5)}
                                          {appointment.ends_at ? ` - ${formatDateTimeBR(appointment.ends_at).slice(-5)}` : ""}
                                        </p>
                                      ) : null}
                                      <p className="truncate text-xs font-semibold text-stone-900">{appointment.patient_name}</p>
                                      {height >= 34 ? (
                                        <p className="truncate text-[11px] font-medium text-stone-800">{appointment.procedure_type}</p>
                                      ) : null}
                                      {height >= 48 ? (
                                        <p className="truncate text-[11px] text-stone-700">{appointment.professional_name}</p>
                                      ) : null}
                                    </div>
                                  </button>
                                );
                              })}
                            </div>
                          );
                        })}
                      </div>
                    );
                  })}
                </div>
              </div>
          </div>
        </CardContent>
      </Card>

      {floatingCreateAppointmentButton}

      <RightDrawer
        open={agendaControlsOpen}
        onOpenChange={setAgendaControlsOpen}
        title="Controles da agenda"
        description="Ajuste periodo, filtros e equipe sem deixar a grade pesada."
        widthClassName="w-full sm:max-w-2xl"
      >
        <div className="space-y-4">
          <Card className="border-stone-200 bg-white/95">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CalendarDays size={16} /> Periodo e dias
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <Button variant="outline" className="h-8 w-8 px-0" onClick={handlePreviousWeek}>
                  <ChevronLeft size={14} />
                </Button>
                <p className="min-w-0 flex-1 text-center text-xs font-semibold text-stone-700 sm:text-sm">
                  {formatDateBR(weekAnchor)} - {formatDateBR(addDays(weekAnchor, 6))}
                </p>
                <Button variant="outline" className="h-8 w-8 px-0" onClick={handleNextWeek}>
                  <ChevronRight size={14} />
                </Button>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" className="h-8" onClick={handleGoToday}>
                  Hoje
                </Button>
                <Button
                  variant="outline"
                  className="h-8"
                  onClick={() =>
                    setSelectedDayKeys(
                      weekDays
                        .filter((item) => item.date >= todayStart)
                        .map((item) => item.key),
                    )
                  }
                >
                  Selecionar todos
                </Button>
              </div>

              <div className="overflow-x-auto">
                <div className="grid min-w-[320px] grid-cols-7 gap-1 rounded-md border border-stone-200 bg-stone-50 p-2 text-xs">
                  {MONTH_GRID_WEEK_DAY_VALUES.map((value) => {
                    const item = WEEK_DAY_OPTIONS.find((option) => option.value === value);
                    if (!item) return null;
                    return (
                      <p key={`month-head-${item.value}`} className="text-center font-semibold text-stone-500">
                        {item.label}
                      </p>
                    );
                  })}
                  {monthCalendarDays.map((date) => {
                    const key = toDayKey(date);
                    const focused = toDayKey(focusedDate) === key;
                    const sameMonth = date.getMonth() === monthCursor.getMonth();
                    return (
                      <button
                        key={key}
                        type="button"
                        className={`h-8 rounded-md text-xs transition ${
                          focused
                            ? "bg-primary text-primary-foreground"
                            : sameMonth
                              ? "text-stone-700 hover:bg-stone-200"
                              : "text-stone-400"
                        }`}
                        onClick={() => {
                          setFocusedDate(date);
                          setWeekAnchor(startOfWeekMonday(date));
                          setMonthCursor(date);
                          if (date < todayStart) {
                            setViewMode("day");
                          }
                        }}
                      >
                        {date.getDate()}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="space-y-2 rounded-md border border-stone-200 bg-stone-50 p-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Selecionar dia ou dias</p>
                <div className="flex flex-wrap gap-2">
                  {weekDays.map((day) => {
                    const active = selectedDayKeys.includes(day.key);
                    return (
                      <button
                        key={`toggle-day-${day.key}`}
                        type="button"
                        className={`rounded-full border px-3 py-1 text-xs transition ${
                          active
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-stone-300 bg-white text-stone-700"
                        }`}
                        onClick={() => {
                          if (viewMode === "day") {
                            setFocusedDate(day.date);
                            return;
                          }
                          if (day.date < todayStart) {
                            setFocusedDate(day.date);
                            setViewMode("day");
                            return;
                          }
                          setSelectedDayKeys((current) =>
                            current.includes(day.key) ? current.filter((item) => item !== day.key) : [...current, day.key],
                          );
                        }}
                      >
                        {day.label} {day.dayOfMonth}
                      </button>
                    );
                  })}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border-stone-200 bg-white/95">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ListFilter size={16} /> Filtros da grade
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <label className="field-label" htmlFor="agenda-search">Busca rapida</label>
                <Input
                  id="agenda-search"
                  placeholder="Buscar paciente, unidade ou procedimento..."
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <div>
                  <label className="field-label" htmlFor="agenda-status-filter">Status</label>
                  <select
                    id="agenda-status-filter"
                    className="h-11 w-full rounded-lg border border-stone-300 bg-white px-3 text-sm"
                    value={statusFilter}
                    onChange={(event) => setStatusFilter(event.target.value)}
                  >
                    <option value="all">Todos os status</option>
                    <option value="agendada">Agendado</option>
                    <option value="confirmada">Confirmado</option>
                    <option value="cancelada">Cancelado</option>
                    <option value="falta">No-show</option>
                    <option value="concluida">Concluido</option>
                  </select>
                </div>
                <div>
                  <label className="field-label" htmlFor="agenda-unit-filter">Unidade</label>
                  <select
                    id="agenda-unit-filter"
                    className="h-11 w-full rounded-lg border border-stone-300 bg-white px-3 text-sm"
                    value={unitFilter}
                    onChange={(event) => {
                      const nextValue = event.target.value;
                      setUnitFilter(nextValue);
                      if (ownerUnitScope.canSwitchUnits) {
                        ownerUnitScope.setSelectedUnitId(nextValue);
                      }
                    }}
                    disabled={unitSelectionLocked}
                  >
                    {!unitSelectionLocked ? <option value="all">Todas as unidades</option> : null}
                    {visibleUnits.map((unit) => (
                      <option key={unit.id} value={unit.id}>
                        {unit.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <p className="text-xs text-stone-500">Esses filtros afetam tanto a grade quanto a lista lateral de consultas.</p>
            </CardContent>
          </Card>

          <Card className="border-stone-200 bg-white/95">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Palette size={16} /> Equipe e cores
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="rounded-md border border-stone-200 bg-stone-50 p-2">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium text-stone-700">Horario disponivel</p>
                    <p className="text-xs text-stone-500">Cor usada nas faixas livres da agenda.</p>
                  </div>
                  <input
                    type="color"
                    value={availabilityColor}
                    onChange={(event) => setAvailabilityColor(event.target.value)}
                    className="h-7 w-9 rounded border border-stone-300 bg-white p-0.5"
                  />
                </div>
              </div>
              {visibleProfessionals.length ? (
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    className="h-8 flex-1 text-xs"
                    onClick={() => setSelectedProfessionalIds(visibleProfessionals.map((professional) => professional.id))}
                  >
                    Selecionar todos
                  </Button>
                  <Button
                    variant="outline"
                    className="h-8 flex-1 text-xs"
                    onClick={() => setSelectedProfessionalIds([])}
                  >
                    Limpar filtro
                  </Button>
                </div>
              ) : null}
              {visibleProfessionals.length ? (
                visibleProfessionals.map((professional) => {
                  const selected = selectedProfessionalIds.includes(professional.id);
                  return (
                    <div key={professional.id} className="rounded-md border border-stone-200 bg-stone-50 p-2">
                      <div className="flex items-center justify-between gap-2">
                        <label className="flex cursor-pointer items-center gap-2 text-sm text-stone-700">
                          <input
                            type="checkbox"
                            checked={selected}
                            onChange={(event) =>
                              setSelectedProfessionalIds((current) =>
                                event.target.checked
                                  ? Array.from(new Set([...current, professional.id]))
                                  : current.filter((item) => item !== professional.id),
                              )
                            }
                          />
                          <span>{professional.full_name}</span>
                        </label>
                        <input
                          type="color"
                          value={professionalColors[professional.id] ?? "#9ad0ec"}
                          onChange={(event) =>
                            setProfessionalColors((current) => ({
                              ...current,
                              [professional.id]: event.target.value,
                            }))
                          }
                          className="h-7 w-9 rounded border border-stone-300 bg-white p-0.5"
                        />
                      </div>
                    </div>
                  );
                })
              ) : (
                <p className="text-xs text-stone-500">Nenhum profissional cadastrado para esta unidade.</p>
              )}
              <Button
                variant="outline"
                className="h-9 w-full"
                onClick={() => saveColorsMutation.mutate()}
                disabled={saveColorsMutation.isPending}
              >
                {saveColorsMutation.isPending ? "Salvando cores..." : "Salvar cores"}
              </Button>
            </CardContent>
          </Card>
        </div>
      </RightDrawer>

      <RightDrawer
        open={createAppointmentOpen}
        onOpenChange={setCreateAppointmentOpen}
        title="Nova consulta"
        description="Preencha os dados principais e confirme para salvar na agenda."
        widthClassName="w-full sm:max-w-2xl"
      >
        <Card className="border-stone-200 bg-white/95">
          <CardContent className="p-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <label className="field-label" htmlFor="create-patient-id">Paciente</label>
                <select
                  id="create-patient-id"
                  className="h-11 w-full rounded-lg border border-stone-300 bg-white px-3 text-sm"
                  value={patientId}
                  onChange={(event) => setPatientId(event.target.value)}
                >
                  <option value="">Selecione o paciente</option>
                  {dataset.patients.map((patient) => (
                    <option key={patient.id} value={patient.id}>
                      {patient.full_name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="field-label" htmlFor="create-unit-id">Unidade</label>
                <select
                  id="create-unit-id"
                  className="h-11 w-full rounded-lg border border-stone-300 bg-white px-3 text-sm"
                  value={unitId}
                  disabled={unitSelectionLocked}
                  onChange={(event) => {
                    const nextUnitId = event.target.value;
                    setUnitId(nextUnitId);
                    const nextUnit = dataset.units.find((unit) => unit.id === nextUnitId);
                    const nextServices = nextUnit?.services?.length ? nextUnit.services : serviceCatalog;
                    setProcedure((current) =>
                      current && nextServices.length && !nextServices.includes(current) ? "" : current,
                    );
                    setProfessionalId("");
                  }}
                >
                  <option value="">Selecione a unidade</option>
                  {visibleUnits.map((unit) => (
                    <option key={unit.id} value={unit.id}>
                      {unit.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="field-label" htmlFor="create-professional-id">Profissional</label>
                <select
                  id="create-professional-id"
                  className="h-11 w-full rounded-lg border border-stone-300 bg-white px-3 text-sm"
                  value={professionalId}
                  onChange={(event) => setProfessionalId(event.target.value)}
                >
                  <option value="">Selecionar automaticamente</option>
                  {professionalsForSelectedUnit.map((professional) => (
                    <option key={professional.id} value={professional.id}>
                      {professional.full_name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="field-label" htmlFor="create-procedure">Procedimento</label>
                <select
                  id="create-procedure"
                  className="h-11 w-full rounded-lg border border-stone-300 bg-white px-3 text-sm"
                  value={procedure}
                  onChange={(event) => setProcedure(event.target.value)}
                  disabled={!createProcedureOptions.length}
                >
                  <option value="">
                    {createProcedureOptions.length ? "Selecione o procedimento" : "Cadastre servicos primeiro"}
                  </option>
                  {createProcedureOptions.map((serviceName) => (
                    <option key={serviceName} value={serviceName}>
                      {serviceName}
                    </option>
                  ))}
                </select>
                <p className="field-help">Os servicos exibidos aqui seguem exatamente o cadastro oficial da clinica.</p>
              </div>
              <div>
                <label className="field-label" htmlFor="create-starts-at">Data e hora</label>
                <Input
                  id="create-starts-at"
                  type="datetime-local"
                  value={startsAt}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => setStartsAt(event.target.value)}
                />
              </div>
              <div className="sm:col-span-2">
                <Button
                  className="w-full"
                  onClick={() => {
                    if (!canCreateAgenda) {
                      toast.error("Seu perfil nao pode criar consultas nesta pagina.");
                      return;
                    }
                    if (!patientId || !unitId || !procedure || !startsAt) {
                      toast.error("Preencha todos os campos para criar a consulta.");
                      return;
                    }
                    createMutation.mutate();
                  }}
                  disabled={createMutation.isPending || !canCreateAgenda}
                >
                  {createMutation.isPending ? "Criando..." : "Criar consulta"}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </RightDrawer>

      <RightDrawer
        open={appointmentListOpen}
        onOpenChange={setAppointmentListOpen}
        title={`Consultas (${viewMode === "day" ? "dia" : "semana"})`}
        description="Visualize e aja rapido sem sair da grade principal."
        widthClassName="w-full sm:max-w-[min(96vw,1200px)]"
      >
        <DataTable<(typeof appointments)[number]>
          title={`Consultas (${viewMode === "day" ? "dia" : "semana"})`}
          rows={appointments}
          getRowId={(item) => item.id}
          searchBy={(item) => `${item.patient_name} ${item.procedure_type} ${item.unit_name} ${item.professional_name}`}
          columns={[
            {
              key: "paciente",
              label: "Paciente",
              render: (item) => (
                <div>
                  <p className="font-semibold text-stone-800">{item.patient_name}</p>
                  <p className="text-xs text-stone-500">{formatPhoneBR(item.patient_phone)}</p>
                </div>
              ),
            },
            {
              key: "procedimento",
              label: "Procedimento",
              render: (item) => item.procedure_type,
            },
            {
              key: "inicio",
              label: "Data e hora",
              render: (item) => formatDateTimeBR(item.starts_at),
            },
            {
              key: "unidade",
              label: "Unidade",
              render: (item) => item.unit_name,
            },
            {
              key: "profissional",
              label: "Profissional",
              render: (item) => item.professional_name,
            },
            {
              key: "status",
              label: "Status",
              render: (item) => <StatusBadge value={item.status} />,
            },
            {
              key: "confirmacao",
              label: "Confirmacao",
              render: (item) => <StatusBadge value={item.confirmation_status} />,
            },
            {
              key: "ultima_conversa",
              label: "Ultima conversa",
              render: (item) => formatDateBR(item.last_conversation),
            },
            {
              key: "acoes",
              label: "Acoes rapidas",
              render: (item) => (
                <div className="flex flex-wrap gap-1">
                  <Button
                    variant="outline"
                    className="h-8 px-2 text-xs"
                    onClick={() =>
                      updateMutation.mutate({
                        appointmentId: item.id,
                        payload: { confirmation_status: "confirmada", status: "confirmada" },
                      })
                    }
                    disabled={!canEditAgenda}
                  >
                    Confirmar
                  </Button>
                  <Button
                    variant="outline"
                    className="h-8 px-2 text-xs"
                    onClick={() => handleOpenAppointmentEditor(item, "reschedule")}
                    disabled={!canEditAgenda}
                  >
                    Reagendar
                  </Button>
                  <Button
                    variant="destructive"
                    className="h-8 px-2 text-xs"
                    onClick={() =>
                      updateMutation.mutate({
                        appointmentId: item.id,
                        payload: { status: "cancelada", confirmation_status: "nao_confirmada" },
                      })
                    }
                    disabled={!canEditAgenda}
                  >
                    Cancelar
                  </Button>
                </div>
              ),
            },
          ]}
          emptyTitle="Sem consultas no periodo"
          emptyDescription="Nenhuma consulta encontrada com os filtros atuais."
          bodyWrapperClassName="max-h-[calc(100vh-240px)] overflow-y-auto"
        />
      </RightDrawer>

      <RightDrawer
        open={manualBookingOpen}
        onOpenChange={(open) => {
          setManualBookingOpen(open);
          if (!open) {
            setManualBookingContext(null);
            setManualBookingPatientMode("existing");
            setManualBookingPatientSearch("");
            setManualBookingPatientId("");
            setManualBookingUnitId("");
            setManualBookingProfessionalId("");
            setManualBookingProcedure("");
            setManualBookingStartsAt("");
            setManualBookingNotes("");
            setManualBookingNeedsEvaluation(true);
            setManualBookingHistoryOpen(false);
            setManualBookingNewFullName("");
            setManualBookingNewPhone("");
            setManualBookingNewCpf("");
            setManualBookingNewEmail("");
            setManualBookingNewBirthDate("");
          }
        }}
        title={
          manualBookingContext
            ? `Agendar com ${manualBookingContext.professionalName}`
            : "Agendar horario livre"
        }
        description="Clique no card verde para abrir este fluxo e salvar um agendamento manual completo, usando paciente existente ou novo."
      >
        {manualBookingContext ? (
          <div className="space-y-3">
            <Card className="border-stone-200 bg-white/95">
              <CardContent className="space-y-4 p-4">
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
                    <p className="field-label">Unidade</p>
                    <p className="text-sm font-semibold text-stone-800">{manualBookingContext.unitName}</p>
                  </div>
                  <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
                    <p className="field-label">Profissional</p>
                    <p className="text-sm font-semibold text-stone-800">{manualBookingContext.professionalName}</p>
                  </div>
                </div>

                <div className="grid gap-3 md:grid-cols-2">
                  <div>
                    <label className="field-label" htmlFor="manual-booking-starts-at">Horario inicial</label>
                    <Input
                      id="manual-booking-starts-at"
                      type="datetime-local"
                      value={manualBookingStartsAt}
                      onChange={(event: ChangeEvent<HTMLInputElement>) => setManualBookingStartsAt(event.target.value)}
                    />
                    <p className="field-help">
                      Slot livre do card: {formatTimeFromMinutes(manualBookingContext.slotStartMinutes)} ate{" "}
                      {formatTimeFromMinutes(manualBookingContext.slotEndMinutes)}.
                    </p>
                  </div>

                  <div>
                    <label className="field-label" htmlFor="manual-booking-procedure">Servico</label>
                    <select
                      id="manual-booking-procedure"
                      className="h-11 w-full rounded-lg border border-stone-300 bg-white px-3 text-sm"
                      value={manualBookingProcedure}
                      onChange={(event) => setManualBookingProcedure(event.target.value)}
                      disabled={!manualBookingProcedureOptions.length}
                    >
                      <option value="">
                        {manualBookingProcedureOptions.length
                          ? "Selecione o servico"
                          : "Esse profissional nao possui servicos compativeis"}
                      </option>
                      {manualBookingProcedureOptions.map((serviceName) => (
                        <option key={serviceName} value={serviceName}>
                          {serviceName}
                        </option>
                      ))}
                    </select>
                    <p className="field-help">
                      O sistema filtra apenas servicos que esse profissional pode executar nessa unidade.
                    </p>
                  </div>
                </div>

                {manualBookingPatientMode === "new" ? (
                  <div className="rounded-xl border border-stone-200 bg-stone-50 p-3">
                    <label className="flex items-start gap-3 text-sm text-stone-700">
                      <input
                        type="checkbox"
                        className="mt-1"
                        checked={manualBookingNeedsEvaluation}
                        onChange={(event) => setManualBookingNeedsEvaluation(event.target.checked)}
                      />
                      <span>
                        <span className="font-semibold text-stone-800">
                          Primeiro atendimento do novo cliente
                        </span>
                        <span className="mt-1 block text-xs text-stone-500">
                          Marcado: a consulta vira uma avaliaÃ§Ã£o inicial do serviÃ§o escolhido. Desmarcado: serviÃ§o e avaliaÃ§Ã£o seguem no mesmo tempo do serviÃ§o selecionado.
                        </span>
                      </span>
                    </label>
                  </div>
                ) : null}

                <div className="grid gap-3 md:grid-cols-3">
                  <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
                    <p className="field-label">Procedimento agendado</p>
                    <p className="text-sm font-semibold text-stone-800">
                      {manualBookingBookedProcedure || "-"}
                    </p>
                  </div>
                  <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
                    <p className="field-label">Duracao oficial</p>
                    <p className="text-sm font-semibold text-stone-800">
                      {manualBookingBookedProcedure ? `${manualBookingDurationMinutes} min` : "-"}
                    </p>
                  </div>
                  <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
                    <p className="field-label">Termino previsto</p>
                    <p className="text-sm font-semibold text-stone-800">
                      {manualBookingExpectedEnd ? formatDateTimeBR(new Date(manualBookingExpectedEnd).toISOString()) : "-"}
                    </p>
                  </div>
                  <div
                    className={`rounded-lg border p-3 ${
                      !manualBookingProcedure
                        ? "border-stone-200 bg-stone-50"
                        : manualBookingFitsSelectedSlot
                        ? "border-emerald-200 bg-emerald-50"
                        : "border-rose-200 bg-rose-50"
                    }`}
                  >
                    <p className="field-label">Validade do slot</p>
                    <p
                      className={`text-sm font-semibold ${
                        !manualBookingProcedure
                          ? "text-stone-700"
                          : manualBookingFitsSelectedSlot
                            ? "text-emerald-700"
                            : "text-rose-700"
                      }`}
                    >
                      {!manualBookingProcedure
                        ? "Escolha o servico"
                        : manualBookingFitsSelectedSlot
                          ? "Cabe no horario livre"
                          : "Nao cabe nesse card"}
                    </p>
                  </div>
                </div>

                <div className="space-y-3 rounded-xl border border-stone-200 bg-stone-50 p-3">
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant={manualBookingPatientMode === "existing" ? "default" : "outline"}
                      type="button"
                      onClick={() => {
                        setManualBookingPatientMode("existing");
                        setManualBookingHistoryOpen(false);
                        setManualBookingNewFullName("");
                        setManualBookingNewPhone("");
                        setManualBookingNewCpf("");
                        setManualBookingNewEmail("");
                        setManualBookingNewBirthDate("");
                      }}
                    >
                      Buscar cliente
                    </Button>
                    <Button
                      variant={manualBookingPatientMode === "new" ? "default" : "outline"}
                      type="button"
                      onClick={() => {
                        setManualBookingPatientMode("new");
                        setManualBookingNeedsEvaluation(true);
                        setManualBookingHistoryOpen(false);
                        setManualBookingPatientId("");
                        setManualBookingPatientSearch("");
                      }}
                    >
                      Criar novo paciente
                    </Button>
                  </div>

                  {manualBookingPatientMode === "existing" ? (
                    <div className="space-y-3">
                      <div>
                        <label className="field-label" htmlFor="manual-booking-patient-search">Buscar paciente</label>
                        <Input
                          id="manual-booking-patient-search"
                          placeholder="Digite nome ou telefone"
                          value={manualBookingPatientSearch}
                          onChange={(event: ChangeEvent<HTMLInputElement>) => setManualBookingPatientSearch(event.target.value)}
                        />
                        <p className="field-help">
                          A busca usa os pacientes carregados e consulta o banco por nome ou telefone.
                        </p>
                      </div>

                      <div className="space-y-2 rounded-lg border border-stone-200 bg-white p-2">
                        {patientLookupQuery.isFetching ? (
                          <p className="px-2 py-1 text-xs text-stone-500">Buscando pacientes...</p>
                        ) : null}
                        {manualBookingPatientOptions.length ? (
                          manualBookingPatientOptions.map((patient) => (
                            <button
                              key={patient.id}
                              type="button"
                              className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition ${
                                manualBookingPatientId === patient.id
                                  ? "bg-emerald-100 text-emerald-900"
                                  : "bg-stone-50 text-stone-700 hover:bg-stone-100"
                              }`}
                              onClick={() => setManualBookingPatientId(patient.id)}
                            >
                              <span className="truncate font-medium">{patient.full_name}</span>
                              <span className="ml-3 text-xs text-stone-500">{formatPhoneBR(patient.phone)}</span>
                            </button>
                          ))
                        ) : (
                          <p className="px-2 py-1 text-xs text-stone-500">
                            Nenhum paciente encontrado. Se preferir, crie um novo logo abaixo.
                          </p>
                        )}
                      </div>

                      {manualBookingSelectedPatient ? (
                        <div className="space-y-3">
                          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3">
                            <p className="field-label">Paciente selecionado</p>
                            <p className="text-sm font-semibold text-emerald-900">{manualBookingSelectedPatient.full_name}</p>
                            <p className="text-xs text-emerald-700">{formatPhoneBR(manualBookingSelectedPatient.phone)}</p>
                          </div>

                          <div
                            className={`rounded-lg border p-3 ${
                              manualBookingHasEvaluation
                                ? "border-sky-200 bg-sky-50"
                                : "border-amber-200 bg-amber-50"
                            }`}
                          >
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <div>
                                <p className="field-label">Status da avaliacao</p>
                                <p
                                  className={`text-sm font-semibold ${
                                    manualBookingHasEvaluation ? "text-sky-900" : "text-amber-800"
                                  }`}
                                >
                                  {manualBookingHasEvaluation
                                    ? "Paciente ja possui avaliacao registrada"
                                    : "Ainda nao encontrei avaliacao anterior"}
                                </p>
                              </div>
                              {manualBookingSelectedPatientAppointments.length ? (
                                <Button
                                  type="button"
                                  variant="outline"
                                  className="h-8 text-xs"
                                  onClick={() => setManualBookingHistoryOpen((current) => !current)}
                                >
                                  {manualBookingHistoryOpen ? "Ocultar historico" : "Ver historico"}
                                </Button>
                              ) : null}
                            </div>

                            {manualBookingHistoryOpen ? (
                              <div className="mt-3 rounded-2xl border border-white/80 bg-white/90 p-3 shadow-sm">
                                <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                                  Avaliacoes, procedimentos e observacoes salvas
                                </p>
                                <div className="mt-2 space-y-2">
                                  {manualBookingSelectedPatientAppointments.length ? (
                                    manualBookingSelectedPatientAppointments.map((appointment) => (
                                      <div
                                        key={`history-${appointment.id}`}
                                        className="rounded-xl border border-stone-200 bg-stone-50 p-3"
                                      >
                                        <div className="flex flex-wrap items-center justify-between gap-2">
                                          <p className="text-sm font-semibold text-stone-800">
                                            {appointment.procedure_type}
                                          </p>
                                          <p className="text-xs text-stone-500">
                                            {formatDateTimeBR(appointment.starts_at)}
                                          </p>
                                        </div>
                                        <p className="mt-1 text-xs text-stone-600">
                                          Profissional:{" "}
                                          {appointment.professional_id
                                            ? professionalsById.get(appointment.professional_id)?.full_name ?? "Nao definido"
                                            : "Nao definido"}
                                        </p>
                                        <p className="mt-1 text-xs text-stone-600">
                                          Status: {appointment.status} â€¢ Confirmacao: {appointment.confirmation_status}
                                        </p>
                                        <p className="mt-1 text-xs text-stone-600">
                                          Comparecimento:{" "}
                                          {findOptionLabel(
                                            APPOINTMENT_ATTENDANCE_STATUS_OPTIONS,
                                            resolveAppointmentAttendanceStatus(appointment),
                                            "Ainda nao marcado",
                                          )}
                                        </p>
                                        {resolveNextAppointmentStatus(appointment) !== "nao_definido" ? (
                                          <p className="mt-1 text-xs text-stone-600">
                                            Proximo agendamento:{" "}
                                            {findOptionLabel(
                                              APPOINTMENT_NEXT_APPOINTMENT_OPTIONS,
                                              resolveNextAppointmentStatus(appointment),
                                              "Ainda nao definido",
                                            )}
                                          </p>
                                        ) : null}
                                        {appointment.attendance_notes?.trim() ? (
                                          <p className="mt-2 text-xs text-stone-600">
                                            Resultado: {appointment.attendance_notes.trim()}
                                          </p>
                                        ) : null}
                                        <p className="mt-2 text-xs text-stone-600">
                                          {appointment.notes?.trim() || "Sem observacoes registradas."}
                                        </p>
                                      </div>
                                    ))
                                  ) : (
                                    <p className="text-xs text-stone-500">
                                      Nenhum procedimento anterior encontrado para esse paciente.
                                    </p>
                                  )}
                                </div>
                              </div>
                            ) : null}
                          </div>
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <div className="grid gap-3 md:grid-cols-2">
                      <div className="md:col-span-2">
                        <label className="field-label" htmlFor="manual-booking-new-name">Nome completo</label>
                        <Input
                          id="manual-booking-new-name"
                          placeholder="Ex.: Maria da Silva"
                          value={manualBookingNewFullName}
                          onChange={(event: ChangeEvent<HTMLInputElement>) => setManualBookingNewFullName(event.target.value)}
                        />
                      </div>
                      <div>
                        <label className="field-label" htmlFor="manual-booking-new-phone">Telefone</label>
                        <Input
                          id="manual-booking-new-phone"
                          placeholder="Ex.: (11) 99999-9999"
                          value={manualBookingNewPhone}
                          onChange={(event: ChangeEvent<HTMLInputElement>) => setManualBookingNewPhone(event.target.value)}
                        />
                      </div>
                      <div>
                        <label className="field-label" htmlFor="manual-booking-new-cpf">CPF</label>
                        <Input
                          id="manual-booking-new-cpf"
                          placeholder="opcional"
                          value={manualBookingNewCpf}
                          onChange={(event: ChangeEvent<HTMLInputElement>) => setManualBookingNewCpf(event.target.value)}
                        />
                      </div>
                      <div>
                        <label className="field-label" htmlFor="manual-booking-new-email">E-mail</label>
                        <Input
                          id="manual-booking-new-email"
                          type="email"
                          placeholder="opcional"
                          value={manualBookingNewEmail}
                          onChange={(event: ChangeEvent<HTMLInputElement>) => setManualBookingNewEmail(event.target.value)}
                        />
                      </div>
                      <div>
                        <label className="field-label" htmlFor="manual-booking-new-birth-date">Nascimento</label>
                        <Input
                          id="manual-booking-new-birth-date"
                          type="date"
                          value={manualBookingNewBirthDate}
                          onChange={(event: ChangeEvent<HTMLInputElement>) => setManualBookingNewBirthDate(event.target.value)}
                        />
                      </div>
                      <div className="rounded-lg border border-stone-200 bg-white p-3 text-xs text-stone-500 md:col-span-2">
                        Ao salvar, o paciente novo entra automaticamente no banco de pacientes e o agendamento ja fica ligado a ele.
                      </div>
                    </div>
                  )}
                </div>

                <div>
                  <label className="field-label" htmlFor="manual-booking-notes">Observacoes</label>
                  <textarea
                    id="manual-booking-notes"
                    className="min-h-[100px] w-full rounded-lg border border-stone-300 bg-white p-2.5 text-sm"
                    placeholder="Observacoes internas do agendamento"
                    value={manualBookingNotes}
                    onChange={(event) => setManualBookingNotes(event.target.value)}
                  />
                </div>

                {!manualBookingFitsSelectedSlot && manualBookingProcedure ? (
                  <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                    Esse servico termina depois do horario livre clicado. Escolha outro servico ou selecione outro card verde.
                  </div>
                ) : null}

                <div className="flex flex-wrap justify-end gap-2 max-sm:[&>*]:w-full">
                  <Button
                    variant="outline"
                    onClick={() => setManualBookingOpen(false)}
                  >
                    Cancelar
                  </Button>
                  <Button
                    onClick={() => manualBookingMutation.mutate()}
                    disabled={
                      manualBookingMutation.isPending ||
                      !canCreateAgenda ||
                      !manualBookingProcedure ||
                      !manualBookingFitsSelectedSlot ||
                      (manualBookingPatientMode === "existing"
                        ? !manualBookingPatientId
                        : !manualBookingNewFullName.trim() || !manualBookingNewPhone.trim())
                    }
                  >
                    {manualBookingMutation.isPending ? "Salvando..." : "Salvar agendamento"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        ) : (
          <p className="text-sm text-stone-500">Clique em um card verde para abrir o agendamento manual do horario livre.</p>
        )}
      </RightDrawer>

      <RightDrawer
        open={appointmentEditorOpen}
        onOpenChange={(open) => {
          setAppointmentEditorOpen(open);
          if (!open) setSelectedAppointment(null);
        }}
        title={selectedAppointment ? `Consulta de ${selectedAppointment.patient_name}` : "Editar consulta"}
        description="Ao clicar no bloco da grade voce pode visualizar e ajustar os dados manualmente."
      >
        {selectedAppointment ? (
          <div className="space-y-3">
            <Card className="border-stone-200 bg-white/95">
              <CardContent className="space-y-4 p-4">
                <div>
                  <p className="field-label">Paciente</p>
                  <button
                    type="button"
                    className="w-full rounded-md border border-stone-200 bg-stone-50 p-3 text-left text-sm text-stone-700 transition hover:border-primary/40 hover:bg-white"
                    onClick={() => {
                      if (!selectedAppointmentPatient) {
                        toast.error("Esse paciente nao esta mais disponivel no cadastro ativo.");
                        return;
                      }
                      if (!appointmentPatientCardOpen) {
                        populateAppointmentPatientForm(selectedAppointmentPatient);
                      }
                      setAppointmentPatientCardOpen((current) => !current);
                      setAppointmentPatientEditOpen(false);
                      setAppointmentPatientDeleteConfirmOpen(false);
                    }}
                  >
                    <p className="font-semibold text-stone-800">{selectedAppointment.patient_name}</p>
                    <p className="text-xs text-stone-500">{formatPhoneBR(selectedAppointment.patient_phone)}</p>
                  </button>
                  <p className="field-help">Clique no card acima para abrir o resumo completo do paciente com historico e acoes.</p>
                </div>

                {appointmentPatientCardOpen && selectedAppointmentPatient ? (
                  <Card className="border-stone-200 bg-stone-50/80">
                    <CardContent className="space-y-4 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="space-y-1">
                          <p className="text-lg font-semibold text-stone-900">{selectedAppointmentPatient.full_name}</p>
                          <p className="text-sm text-stone-600">{formatPhoneBR(selectedAppointmentPatient.phone)}</p>
                          <p className="text-sm text-stone-600">{selectedAppointmentPatient.email || "Sem e-mail cadastrado"}</p>
                          <p className="text-sm text-stone-600">CPF: {formatCpfBR(selectedAppointmentPatient.cpf)}</p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <Button
                            variant="outline"
                            className="gap-2"
                            onClick={() => {
                              populateAppointmentPatientForm(selectedAppointmentPatient);
                              setAppointmentPatientEditOpen(true);
                              setAppointmentPatientDeleteConfirmOpen(false);
                            }}
                            disabled={!canEditPatients}
                          >
                            <Pencil size={14} />
                            Editar
                          </Button>
                          <Button
                            variant="destructive"
                            className="gap-2"
                            onClick={() => {
                              setAppointmentPatientDeleteConfirmOpen(true);
                              setAppointmentPatientEditOpen(false);
                            }}
                            disabled={!canDeletePatients}
                          >
                            <Trash2 size={14} />
                            Excluir paciente
                          </Button>
                          <Button
                            variant="outline"
                            className="gap-2"
                            onClick={() => {
                              setAppointmentPatientCardOpen(false);
                              setAppointmentPatientEditOpen(false);
                              setAppointmentPatientDeleteConfirmOpen(false);
                            }}
                          >
                            <X size={14} />
                            Fechar
                          </Button>
                        </div>
                      </div>

                      <div className="grid gap-3 md:grid-cols-2">
                        <div className="rounded-xl border border-stone-200 bg-white p-3">
                          <p className="field-label">Cadastro</p>
                          <p className="text-sm text-stone-700">Nascimento: {formatDateBR(selectedAppointmentPatient.birth_date)}</p>
                          <p className="text-sm text-stone-700">Criado em: {formatDateTimeBR(selectedAppointmentPatient.created_at)}</p>
                          <p className="text-sm text-stone-700">Origem: {selectedAppointmentPatient.origin || "Nao informada"}</p>
                          <p className="text-sm text-stone-700">
                            Unidade: {selectedAppointmentPatient.unit_id ? unitsById.get(selectedAppointmentPatient.unit_id) ?? "Unidade nao identificada" : "Nao definida"}
                          </p>
                        </div>
                        <div className="rounded-xl border border-stone-200 bg-white p-3">
                          <p className="field-label">Relacionamento</p>
                          <div className="mt-1 flex flex-wrap gap-2">
                            <StatusBadge value={selectedAppointmentPatient.status} />
                            <Badge className="bg-stone-200 text-stone-700">
                              {selectedAppointmentPatient.marketing_opt_in ? "Marketing liberado" : "Marketing bloqueado"}
                            </Badge>
                            <Badge className="bg-stone-200 text-stone-700">
                              {selectedAppointmentPatient.lgpd_consent ? "LGPD ok" : "LGPD pendente"}
                            </Badge>
                          </div>
                          <div className="mt-3 flex flex-wrap gap-1">
                            {(selectedAppointmentPatient.tags_cache || []).length ? (
                              selectedAppointmentPatient.tags_cache.map((tag) => (
                                <Badge key={tag} className="bg-stone-200 text-stone-700">
                                  {tag}
                                </Badge>
                              ))
                            ) : (
                              <span className="text-sm text-stone-500">Sem tags</span>
                            )}
                          </div>
                        </div>
                      </div>

                      {appointmentPatientDeleteConfirmOpen ? (
                        <Card className="border-rose-200 bg-rose-50">
                          <CardContent className="space-y-3 p-4">
                            <div>
                              <p className="text-sm font-semibold text-rose-900">Confirmar exclusao do paciente</p>
                              <p className="text-sm text-rose-700">
                                Esse paciente sera removido da base ativa e a consulta continuara apenas como historico operacional.
                              </p>
                            </div>
                            <div className="grid gap-2 sm:grid-cols-3">
                              <div className="rounded-lg border border-rose-200 bg-white p-3 text-sm text-stone-700">
                                {selectedAppointmentPatientAppointments.length} agendamento(s)
                              </div>
                              <div className="rounded-lg border border-rose-200 bg-white p-3 text-sm text-stone-700">
                                {selectedAppointmentPatientConversations.length} conversa(s)
                              </div>
                              <div className="rounded-lg border border-rose-200 bg-white p-3 text-sm text-stone-700">
                                {selectedAppointmentPatientDocuments.length} documento(s)
                              </div>
                            </div>
                            <div className="flex flex-wrap justify-end gap-2">
                              <Button variant="outline" onClick={() => setAppointmentPatientDeleteConfirmOpen(false)}>
                                Nao
                              </Button>
                              <Button
                                variant="destructive"
                                onClick={() => deletePatientMutation.mutate(selectedAppointmentPatient.id)}
                                disabled={deletePatientMutation.isPending || !canDeletePatients}
                              >
                                {deletePatientMutation.isPending ? "Excluindo..." : "Sim, excluir paciente"}
                              </Button>
                            </div>
                          </CardContent>
                        </Card>
                      ) : null}

                      {appointmentPatientEditOpen ? (
                        <Card className="border-stone-200 bg-white">
                          <CardContent className="space-y-3 p-4">
                            <div className="grid gap-3 sm:grid-cols-2">
                              <div className="space-y-1.5">
                                <label className="field-label">Nome completo do paciente</label>
                                <Input
                                  placeholder="Ex.: Maria da Silva"
                                  value={appointmentPatientFormName}
                                  onChange={(event) => setAppointmentPatientFormName(event.target.value)}
                                />
                              </div>
                              <div className="space-y-1.5">
                                <label className="field-label">Telefone principal</label>
                                <div className="flex h-10 items-center rounded-lg border border-stone-200 bg-stone-50 px-3 text-sm text-stone-600">
                                  {formatPhoneBR(selectedAppointmentPatient.phone)}
                                </div>
                              </div>
                            </div>
                            <div className="grid gap-3 sm:grid-cols-2">
                              <div className="space-y-1.5">
                                <label className="field-label">CPF</label>
                                <Input
                                  placeholder="Opcional"
                                  value={appointmentPatientFormCpf}
                                  onChange={(event) => setAppointmentPatientFormCpf(event.target.value)}
                                />
                              </div>
                              <div className="space-y-1.5">
                                <label className="field-label">E-mail</label>
                                <Input
                                  placeholder="Opcional"
                                  value={appointmentPatientFormEmail}
                                  onChange={(event) => setAppointmentPatientFormEmail(event.target.value)}
                                />
                              </div>
                            </div>
                            <div className="grid gap-3 sm:grid-cols-2">
                              <div className="space-y-1.5">
                                <label className="field-label">Data de nascimento</label>
                                <Input
                                  type="date"
                                  value={appointmentPatientFormBirthDate}
                                  onChange={(event) => setAppointmentPatientFormBirthDate(event.target.value)}
                                />
                              </div>
                              <div className="space-y-1.5">
                                <label className="field-label">Status do cadastro</label>
                                <select
                                  className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                                  value={appointmentPatientFormStatus}
                                  onChange={(event) => setAppointmentPatientFormStatus(event.target.value)}
                                >
                                  <option value="ativo">Ativo</option>
                                  <option value="inativo">Inativo</option>
                                </select>
                              </div>
                            </div>
                            <div className="space-y-1.5">
                              <label className="field-label">Tags do CRM</label>
                              <Input
                                placeholder="Separadas por virgula"
                                value={appointmentPatientFormTags}
                                onChange={(event) => setAppointmentPatientFormTags(event.target.value)}
                              />
                            </div>
                            <div className="space-y-1.5">
                              <label className="field-label">Observacoes clinicas e operacionais</label>
                              <textarea
                                className="min-h-[110px] w-full rounded-lg border border-stone-300 bg-white p-3 text-sm"
                                placeholder="Ex.: alergias, preferencias de atendimento e observacoes internas."
                                value={appointmentPatientFormNotes}
                                onChange={(event) => setAppointmentPatientFormNotes(event.target.value)}
                              />
                            </div>
                            <div className="flex flex-wrap justify-end gap-2">
                              <Button variant="outline" onClick={() => setAppointmentPatientEditOpen(false)}>
                                Cancelar
                              </Button>
                              <Button
                                onClick={() => {
                                  if (!selectedAppointmentPatient) return;
                                  if (!appointmentPatientFormName.trim()) {
                                    toast.error("Informe pelo menos o nome do paciente.");
                                    return;
                                  }
                                  updatePatientMutation.mutate(selectedAppointmentPatient.id);
                                }}
                                disabled={updatePatientMutation.isPending || !canEditPatients}
                              >
                                {updatePatientMutation.isPending ? "Salvando..." : "Salvar paciente"}
                              </Button>
                            </div>
                          </CardContent>
                        </Card>
                      ) : null}

                      <div className="flex flex-wrap gap-2">
                        {APPOINTMENT_PATIENT_DETAIL_TABS.map((tab) => (
                          <Button
                            key={tab.id}
                            variant={appointmentPatientTab === tab.id ? "default" : "outline"}
                            className="h-8 text-xs"
                            onClick={() => setAppointmentPatientTab(tab.id)}
                          >
                            {tab.label}
                          </Button>
                        ))}
                      </div>

                      {appointmentPatientTab === "resumo" ? (
                        <Card className="border-stone-200">
                          <CardContent className="grid gap-3 p-4 sm:grid-cols-2">
                            <div className="rounded-xl border border-stone-200 bg-stone-50 p-3">
                              <p className="field-label">Ultima interacao</p>
                              <p className="text-sm font-semibold text-stone-800">
                                {formatDateTimeBR(selectedAppointmentPatientConversations[0]?.last_message_at)}
                              </p>
                            </div>
                            <div className="rounded-xl border border-stone-200 bg-stone-50 p-3">
                              <p className="field-label">Proxima consulta</p>
                              <p className="text-sm font-semibold text-stone-800">
                                {
                                  formatDateTimeBR(
                                    selectedAppointmentPatientAppointments.find((item) => new Date(item.starts_at) >= new Date())?.starts_at,
                                  )
                                }
                              </p>
                            </div>
                            <div className="rounded-xl border border-stone-200 bg-stone-50 p-3 sm:col-span-2">
                              <p className="field-label">Observacoes clinicas e operacionais</p>
                              <p className="text-sm text-stone-700">
                                {selectedAppointmentPatient.operational_notes?.trim() || "Sem observacoes salvas para este paciente."}
                              </p>
                            </div>
                          </CardContent>
                        </Card>
                      ) : null}

                      {appointmentPatientTab === "procedimentos" ? (
                        <Card className="border-stone-200">
                          <CardContent className="space-y-3 p-4">
                            {selectedAppointmentPatientAppointments.length ? (
                              selectedAppointmentPatientAppointments.map((appointment) => (
                                <div key={appointment.id} className="rounded-xl border border-stone-200 bg-stone-50 p-3">
                                  <div className="flex flex-wrap items-start justify-between gap-2">
                                    <div>
                                      <div className="flex flex-wrap gap-2">
                                        <p className="text-sm font-semibold text-stone-900">{appointment.procedure_type}</p>
                                        {isEvaluationProcedureName(appointment.procedure_type) ? (
                                          <Badge className="bg-sky-100 text-sky-800">Avaliacao</Badge>
                                        ) : null}
                                      </div>
                                      <p className="mt-1 text-xs text-stone-600">{formatDateTimeBR(appointment.starts_at)}</p>
                                      <p className="mt-1 text-xs text-stone-600">
                                        Profissional:{" "}
                                        {appointment.professional_id
                                          ? professionalsById.get(appointment.professional_id)?.full_name ?? "Nao definido"
                                          : "Nao definido"}
                                      </p>
                                    </div>
                                    <div className="flex flex-wrap gap-1">
                                      <StatusBadge value={appointment.status} />
                                      <StatusBadge value={appointment.confirmation_status} />
                                    </div>
                                  </div>
                                  <div className="mt-3 rounded-lg border border-stone-200 bg-white p-3 text-sm text-stone-700">
                                    <div className="space-y-2">
                                      <p>
                                        Comparecimento:{" "}
                                        {findOptionLabel(
                                          APPOINTMENT_ATTENDANCE_STATUS_OPTIONS,
                                          resolveAppointmentAttendanceStatus(appointment),
                                          "Ainda nao marcado",
                                        )}
                                      </p>
                                      {resolveNextAppointmentStatus(appointment) !== "nao_definido" ? (
                                        <p>
                                          Proximo agendamento:{" "}
                                          {findOptionLabel(
                                            APPOINTMENT_NEXT_APPOINTMENT_OPTIONS,
                                            resolveNextAppointmentStatus(appointment),
                                            "Ainda nao definido",
                                          )}
                                        </p>
                                      ) : null}
                                      {appointment.attendance_notes?.trim() ? <p>Resultado: {appointment.attendance_notes.trim()}</p> : null}
                                      <p>{appointment.notes?.trim() || "Sem observacoes registradas pelo medico/equipe."}</p>
                                    </div>
                                  </div>
                                </div>
                              ))
                            ) : (
                              <p className="text-sm text-stone-500">Nenhum procedimento ou avaliacao vinculado ao paciente.</p>
                            )}
                          </CardContent>
                        </Card>
                      ) : null}

                      {appointmentPatientTab === "conversas" ? (
                        <Card className="border-stone-200">
                          <CardContent className="space-y-3 p-4">
                            {selectedAppointmentPatientConversations.length ? (
                              selectedAppointmentPatientConversations.map((conversation) => (
                                <div key={conversation.id} className="rounded-xl border border-stone-200 bg-stone-50 p-3">
                                  <div className="flex items-center justify-between gap-2">
                                    <div className="flex items-center gap-2">
                                      <MessageSquare size={14} className="text-stone-500" />
                                      <p className="text-sm font-semibold text-stone-900">{conversation.channel.toUpperCase()}</p>
                                    </div>
                                    <StatusBadge value={conversation.status} />
                                  </div>
                                  <p className="mt-2 text-xs text-stone-600">{formatDateTimeBR(conversation.last_message_at)}</p>
                                  <p className="mt-2 text-sm text-stone-700">
                                    {conversation.ai_summary || "Sem resumo de IA salvo para esta conversa."}
                                  </p>
                                </div>
                              ))
                            ) : (
                              <p className="text-sm text-stone-500">Nenhuma conversa vinculada ao paciente.</p>
                            )}
                          </CardContent>
                        </Card>
                      ) : null}

                      {appointmentPatientTab === "documentos" ? (
                        <Card className="border-stone-200">
                          <CardContent className="space-y-3 p-4">
                            {selectedAppointmentPatientDocuments.length ? (
                              selectedAppointmentPatientDocuments.map((document) => (
                                <div key={document.id} className="rounded-xl border border-stone-200 bg-stone-50 p-3">
                                  <div className="flex items-center gap-2">
                                    <FileText size={14} className="text-stone-500" />
                                    <p className="text-sm font-semibold text-stone-900">{document.title}</p>
                                  </div>
                                  <p className="mt-2 text-xs text-stone-600">{document.document_type}</p>
                                  <p className="text-xs text-stone-500">{formatDateBR(document.created_at)}</p>
                                </div>
                              ))
                            ) : (
                              <p className="text-sm text-stone-500">Sem documentos vinculados para este paciente.</p>
                            )}
                          </CardContent>
                        </Card>
                      ) : null}

                      {appointmentPatientTab === "historico" ? (
                        <Card className="border-stone-200">
                          <CardContent className="space-y-3 p-4">
                            {selectedAppointmentPatientHistory.length ? (
                              selectedAppointmentPatientHistory.map((event, index) => (
                                <div key={`${event.title}-${index}`} className="rounded-xl border border-stone-200 bg-stone-50 p-3">
                                  <div className="flex items-center gap-2">
                                    <CalendarClock size={14} className="text-stone-500" />
                                    <p className="text-sm font-semibold text-stone-900">{event.title}</p>
                                  </div>
                                  <p className="mt-1 text-sm text-stone-700">{event.description}</p>
                                  <p className="mt-1 text-xs text-stone-500">{formatDateTimeBR(event.date)}</p>
                                </div>
                              ))
                            ) : (
                              <p className="text-sm text-stone-500">Sem historico operacional disponivel.</p>
                            )}
                          </CardContent>
                        </Card>
                      ) : null}
                    </CardContent>
                  </Card>
                ) : null}

                <div className="grid gap-2 md:grid-cols-2">
                  <div>
                    <label className="field-label" htmlFor="edit-unit-id">Unidade</label>
                    <select
                      id="edit-unit-id"
                      className="h-11 w-full rounded-lg border border-stone-300 bg-white px-3 text-sm"
                      value={editUnitId}
                      disabled={unitSelectionLocked}
                      onChange={(event) => {
                        const nextUnitId = event.target.value;
                        setEditUnitId(nextUnitId);
                        const nextUnit = dataset.units.find((unit) => unit.id === nextUnitId);
                        const nextServices = nextUnit?.services?.length ? nextUnit.services : serviceCatalog;
                        setEditProcedure((current) =>
                          current && nextServices.length && !nextServices.includes(current) ? "" : current,
                        );
                        setEditProfessionalId((current) => {
                          if (!current) return "";
                          const allowed = dataset.professionals.some(
                            (professional) =>
                              professional.id === current &&
                              professional.unit_id === nextUnitId,
                          );
                          return allowed ? current : "";
                        });
                      }}
                    >
                      <option value="">Selecione a unidade</option>
                      {visibleUnits.map((unit) => (
                        <option key={unit.id} value={unit.id}>
                          {unit.name}
                        </option>
                      ))}
                    </select>
                    <p className="field-help">Escolha a unidade onde essa consulta vai ocorrer.</p>
                  </div>

                  <div>
                    <label className="field-label" htmlFor="edit-professional-id">Profissional</label>
                    <select
                      id="edit-professional-id"
                      className="h-11 w-full rounded-lg border border-stone-300 bg-white px-3 text-sm"
                      value={editProfessionalId}
                      onChange={(event) => setEditProfessionalId(event.target.value)}
                    >
                      <option value="">Selecionar automaticamente</option>
                      {professionalsForEditedUnit.map((professional) => (
                        <option key={professional.id} value={professional.id}>
                          {professional.full_name}
                        </option>
                      ))}
                    </select>
                    <p className="field-help">Se deixar vazio, o sistema escolhe automaticamente pelo servico e disponibilidade.</p>
                  </div>
                </div>

                <div>
                  <label className="field-label" htmlFor="edit-procedure">Procedimento</label>
                  <select
                    id="edit-procedure"
                    className="h-11 w-full rounded-lg border border-stone-300 bg-white px-3 text-sm"
                    value={editProcedure}
                    onChange={(event) => setEditProcedure(event.target.value)}
                    disabled={!editProcedureOptions.length}
                  >
                    <option value="">
                      {editProcedureOptions.length ? "Selecione o procedimento" : "Cadastre servicos primeiro"}
                    </option>
                    {editProcedureOptions.map((serviceName) => (
                      <option key={serviceName} value={serviceName}>
                        {serviceName}
                      </option>
                    ))}
                  </select>
                  <p className="field-help">Use os servicos oficiais cadastrados na clinica para a selecao automatica funcionar.</p>
                </div>

                <div className="grid gap-2 md:grid-cols-2">
                  <div>
                    <label className="field-label" htmlFor="edit-starts-at">Inicio</label>
                    <Input
                      id="edit-starts-at"
                      type="datetime-local"
                      value={editStartsAt}
                      onChange={(event: ChangeEvent<HTMLInputElement>) => setEditStartsAt(event.target.value)}
                    />
                  </div>

                  <div>
                    <label className="field-label" htmlFor="edit-ends-at">Fim</label>
                    <Input
                      id="edit-ends-at"
                      type="datetime-local"
                      value={editEndsAt}
                      onChange={(event: ChangeEvent<HTMLInputElement>) => setEditEndsAt(event.target.value)}
                    />
                  </div>
                </div>

                <div className="grid gap-2 md:grid-cols-2">
                  <div>
                    <label className="field-label" htmlFor="edit-status">Status da consulta</label>
                    <select
                      id="edit-status"
                      className="h-11 w-full rounded-lg border border-stone-300 bg-white px-3 text-sm"
                      value={editStatus}
                      onChange={(event) => handleEditStatusChange(event.target.value)}
                    >
                      {APPOINTMENT_STATUS_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="field-label" htmlFor="edit-confirmation-status">Confirmacao</label>
                    <select
                      id="edit-confirmation-status"
                      className="h-11 w-full rounded-lg border border-stone-300 bg-white px-3 text-sm"
                      value={editConfirmationStatus}
                      onChange={(event) => setEditConfirmationStatus(event.target.value)}
                    >
                      {CONFIRMATION_STATUS_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <Card className="border-stone-200 bg-stone-50/70">
                  <CardContent className="space-y-3 p-4">
                    <div>
                      <p className="text-sm font-semibold text-stone-900">Resultado do atendimento</p>
                      <p className="text-sm text-stone-600">
                        Marque se o paciente compareceu e registre o que aconteceu nesse agendamento.
                      </p>
                    </div>

                    <div className="grid gap-2 md:grid-cols-2">
                      <div>
                        <label className="field-label" htmlFor="edit-attendance-status">Comparecimento</label>
                        <select
                          id="edit-attendance-status"
                          className="h-11 w-full rounded-lg border border-stone-300 bg-white px-3 text-sm"
                          value={editAttendanceStatus}
                          onChange={(event) => handleEditAttendanceStatusChange(event.target.value)}
                        >
                          {APPOINTMENT_ATTENDANCE_STATUS_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                        <p className="field-help">Ao marcar compareceu ou faltou, o status da consulta e ajustado automaticamente.</p>
                      </div>

                      <div>
                        <label className="field-label" htmlFor="edit-next-appointment-status">Proximo agendamento</label>
                        <select
                          id="edit-next-appointment-status"
                          className="h-11 w-full rounded-lg border border-stone-300 bg-white px-3 text-sm"
                          value={editNextAppointmentStatus}
                          onChange={(event) => setEditNextAppointmentStatus(event.target.value)}
                          disabled={editAttendanceStatus !== "compareceu"}
                        >
                          {APPOINTMENT_NEXT_APPOINTMENT_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                        <p className="field-help">
                          {editAttendanceStatus === "compareceu"
                            ? "Defina se o paciente precisa voltar ou se ja saiu com retorno marcado."
                            : "Esse campo fica disponivel quando o atendimento foi realizado."}
                        </p>
                      </div>
                    </div>

                    <div>
                      <label className="field-label" htmlFor="edit-attendance-notes">
                        {editAttendanceStatus === "compareceu"
                          ? "O que aconteceu no atendimento"
                          : editAttendanceStatus === "faltou"
                            ? "Observacoes sobre a falta"
                            : "Resumo do agendamento"}
                      </label>
                      <textarea
                        id="edit-attendance-notes"
                        className="min-h-[110px] w-full rounded-lg border border-stone-300 bg-white p-2.5 text-sm"
                        placeholder={
                          editAttendanceStatus === "compareceu"
                            ? "Ex.: avaliacao realizada, procedimento iniciado, orientacoes passadas, retorno necessario..."
                            : editAttendanceStatus === "faltou"
                              ? "Ex.: paciente nao compareceu, equipe tentou contato, reagendamento sugerido..."
                              : "Registre aqui o resultado ou contexto importante desse agendamento."
                        }
                        value={editAttendanceNotes}
                        onChange={(event) => setEditAttendanceNotes(event.target.value)}
                      />
                    </div>
                  </CardContent>
                </Card>

                <Card className="border-stone-200 bg-stone-50/70">
                  <CardContent className="space-y-3 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-stone-900">Agendar retorno</p>
                        <p className="text-sm text-stone-600">
                          Se o paciente precisar voltar, escolha um novo dia e horario para criar outra consulta sem perder a atual.
                        </p>
                      </div>
                      <Button
                        variant={appointmentReturnOpen ? "default" : "outline"}
                        className="h-9"
                        onClick={() => {
                          setAppointmentReturnOpen((current) => !current);
                          setAppointmentDeleteConfirmOpen(false);
                          setAppointmentRescheduleOpen(false);
                          if (!appointmentReturnOpen) {
                            setAppointmentReturnSelectedSlotId("");
                            setAppointmentReturnSelectedDayKey("");
                          }
                        }}
                        disabled={editAttendanceStatus !== "compareceu" || !canCreateAgenda}
                      >
                        Agendar retorno
                      </Button>
                    </div>

                    {editAttendanceStatus !== "compareceu" ? (
                      <p className="text-xs text-stone-500">
                        Marque primeiro que o paciente compareceu para liberar o agendamento de retorno.
                      </p>
                    ) : null}

                    {appointmentReturnOpen && editAttendanceStatus === "compareceu" ? (
                      appointmentReturnChoices.length ? (
                        <div className="space-y-2">
                          <p className="text-xs text-stone-500">
                            Escolha um dia e depois um horario. Ao confirmar, o sistema cria uma nova consulta para este mesmo paciente.
                          </p>
                          {appointmentReturnDayOptions.length ? (
                            <div className="flex flex-wrap gap-2">
                              {appointmentReturnDayOptions.map((option) => {
                                const active = activeReturnDayKey === option.dayKey;
                                return (
                                  <button
                                    key={option.dayKey}
                                    type="button"
                                    className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                                      active
                                        ? "border-primary bg-primary text-white shadow-sm"
                                        : "border-stone-200 bg-white text-stone-700 hover:border-primary/40"
                                    }`}
                                    onClick={() => {
                                      setAppointmentReturnSelectedDayKey(option.dayKey);
                                      setAppointmentReturnSelectedSlotId("");
                                    }}
                                  >
                                    {option.label} ({option.count})
                                  </button>
                                );
                              })}
                            </div>
                          ) : null}
                          <div className="grid gap-2">
                            {appointmentReturnVisibleChoices.map((choice) => {
                              const active = appointmentReturnSelectedSlotId === choice.id;
                              return (
                                <button
                                  key={choice.id}
                                  type="button"
                                  className={`rounded-xl border p-3 text-left transition ${
                                    active
                                      ? "border-primary bg-primary/5 shadow-sm"
                                      : "border-stone-200 bg-white hover:border-primary/40"
                                  }`}
                                  onClick={() => setAppointmentReturnSelectedSlotId(choice.id)}
                                >
                                  <p className="text-sm font-semibold text-stone-900">{choice.label}</p>
                                  <p className="mt-1 text-xs text-stone-500">{choice.professionalName}</p>
                                </button>
                              );
                            })}
                          </div>
                          {selectedReturnChoice ? (
                            <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-emerald-200 bg-emerald-50 p-3">
                              <p className="text-xs font-medium text-emerald-700">
                                Retorno selecionado: {selectedReturnChoice.label}
                              </p>
                              <Button
                                className="h-8"
                                onClick={handleConfirmReturnAppointment}
                                disabled={createReturnAppointmentMutation.isPending}
                              >
                                {createReturnAppointmentMutation.isPending ? "Agendando..." : "Confirmar retorno"}
                              </Button>
                            </div>
                          ) : null}
                        </div>
                      ) : (
                        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                          Nao encontrei horario livre para criar um retorno com esse servico nessa unidade.
                        </div>
                      )
                    ) : null}
                  </CardContent>
                </Card>

                <div>
                  <label className="field-label" htmlFor="edit-notes">Observacoes</label>
                  <textarea
                    id="edit-notes"
                    className="min-h-[100px] w-full rounded-lg border border-stone-300 bg-white p-2.5 text-sm"
                    placeholder="Observacoes da consulta"
                    value={editNotes}
                    onChange={(event) => setEditNotes(event.target.value)}
                  />
                </div>

                <Card className="border-stone-200 bg-stone-50/70">
                  <CardContent className="space-y-3 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-stone-900">Reagendamento inteligente</p>
                        <p className="text-sm text-stone-600">
                          Veja so horarios realmente livres para o servico selecionado, respeitando duracao e profissional disponivel.
                        </p>
                      </div>
                      <Button
                        variant={appointmentRescheduleOpen ? "default" : "outline"}
                        className="h-9"
                        onClick={() => {
                          setAppointmentRescheduleOpen((current) => !current);
                          setAppointmentDeleteConfirmOpen(false);
                          setAppointmentReturnOpen(false);
                        }}
                      >
                        Reagendar
                      </Button>
                    </div>

                    {appointmentRescheduleOpen ? (
                      appointmentRescheduleChoices.length ? (
                        <div className="space-y-2">
                          <p className="text-xs text-stone-500">
                            Escolha um dia e depois um horario. Ao selecionar, inicio, fim e profissional serao preenchidos automaticamente.
                          </p>
                          {appointmentRescheduleDayOptions.length ? (
                            <div className="flex flex-wrap gap-2">
                              {appointmentRescheduleDayOptions.map((option) => {
                                const active = activeRescheduleDayKey === option.dayKey;
                                return (
                                  <button
                                    key={option.dayKey}
                                    type="button"
                                    className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                                      active
                                        ? "border-primary bg-primary text-white shadow-sm"
                                        : "border-stone-200 bg-white text-stone-700 hover:border-primary/40"
                                    }`}
                                    onClick={() => {
                                      setAppointmentRescheduleSelectedDayKey(option.dayKey);
                                      setAppointmentRescheduleSelectedSlotId("");
                                      if (selectedAppointment) {
                                        setEditUnitId(selectedAppointment.unit_id || "");
                                        setEditProfessionalId(selectedAppointment.professional_id || "");
                                        setEditProcedure(selectedAppointment.procedure_type || "");
                                        setEditStartsAt(toDateTimeLocalInput(selectedAppointment.starts_at));
                                        setEditEndsAt(toDateTimeLocalInput(selectedAppointment.ends_at));
                                        setEditStatus(selectedAppointment.status || "agendada");
                                        setEditConfirmationStatus(selectedAppointment.confirmation_status || "pendente");
                                        setEditAttendanceStatus(resolveAppointmentAttendanceStatus(selectedAppointment));
                                        setEditAttendanceNotes(selectedAppointment.attendance_notes ?? "");
                                        setEditNextAppointmentStatus(resolveNextAppointmentStatus(selectedAppointment));
                                      }
                                    }}
                                  >
                                    {option.label} ({option.count})
                                  </button>
                                );
                              })}
                            </div>
                          ) : null}
                          <div className="grid gap-2">
                            {appointmentRescheduleVisibleChoices.map((choice) => {
                              const active = appointmentRescheduleSelectedSlotId === choice.id;
                              return (
                                <button
                                  key={choice.id}
                                  type="button"
                                  className={`rounded-xl border p-3 text-left transition ${
                                    active
                                      ? "border-primary bg-primary/5 shadow-sm"
                                      : "border-stone-200 bg-white hover:border-primary/40"
                                  }`}
                                  onClick={() => {
                                    setAppointmentRescheduleSelectedSlotId(choice.id);
                                    setEditUnitId(choice.unitId);
                                    setEditProfessionalId(choice.professionalId);
                                    setEditStartsAt(toDateTimeLocalInput(choice.startsAt));
                                    setEditEndsAt(toDateTimeLocalInput(choice.endsAt));
                                    setEditStatus("agendada");
                                    setEditConfirmationStatus("pendente");
                                    setEditAttendanceStatus("pendente");
                                    setEditAttendanceNotes("");
                                    setEditNextAppointmentStatus("nao_definido");
                                  }}
                                >
                                  <p className="text-sm font-semibold text-stone-900">{choice.label}</p>
                                  <p className="mt-1 text-xs text-stone-500">{choice.professionalName}</p>
                                </button>
                              );
                            })}
                          </div>
                          {selectedRescheduleChoice ? (
                            <p className="text-xs font-medium text-emerald-700">
                              Novo horario selecionado: {selectedRescheduleChoice.label}
                            </p>
                          ) : null}
                        </div>
                      ) : (
                        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                          Nao encontrei horario livre para esse servico nessa unidade com a duracao correta. Ajuste unidade/procedimento ou tente depois.
                        </div>
                      )
                    ) : null}
                  </CardContent>
                </Card>

                {appointmentDeleteConfirmOpen ? (
                  <Card className="border-rose-200 bg-rose-50">
                    <CardContent className="space-y-3 p-4">
                      <div>
                        <p className="text-sm font-semibold text-rose-900">Confirmar exclusao da consulta</p>
                        <p className="text-sm text-rose-700">
                          Essa consulta sera removida da agenda. Se preferir, use o reagendamento para manter o historico do paciente.
                        </p>
                      </div>
                      <div className="flex flex-wrap justify-end gap-2">
                        <Button variant="outline" onClick={() => setAppointmentDeleteConfirmOpen(false)}>
                          Nao
                        </Button>
                        <Button
                          variant="destructive"
                          onClick={() => {
                            if (!selectedAppointment) return;
                            deleteMutation.mutate(selectedAppointment.id);
                          }}
                          disabled={deleteMutation.isPending || updateMutation.isPending || !canDeleteAgenda}
                        >
                          {deleteMutation.isPending ? "Excluindo..." : "Sim, excluir consulta"}
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                ) : null}

                <div className="flex flex-wrap justify-end gap-2 max-sm:[&>*]:w-full">
                  <Button
                    variant="destructive"
                    onClick={() => {
                      setAppointmentDeleteConfirmOpen(true);
                      setAppointmentRescheduleOpen(false);
                      setAppointmentReturnOpen(false);
                    }}
                    disabled={deleteMutation.isPending || updateMutation.isPending || !canDeleteAgenda}
                  >
                    Excluir consulta
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setAppointmentRescheduleOpen((current) => !current);
                      setAppointmentDeleteConfirmOpen(false);
                      setAppointmentReturnOpen(false);
                    }}
                    disabled={deleteMutation.isPending || updateMutation.isPending || !canEditAgenda}
                  >
                    Reagendar
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setAppointmentEditorOpen(false);
                      setSelectedAppointment(null);
                    }}
                  >
                    Cancelar
                  </Button>
                  <Button
                    onClick={handleSaveAppointmentEdits}
                    disabled={updateMutation.isPending || deleteMutation.isPending || !canEditAgenda}
                  >
                    {updateMutation.isPending ? "Salvando..." : "Salvar alteracoes"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        ) : (
          <p className="text-sm text-stone-500">Clique em um bloco da grade para editar os dados manualmente.</p>
        )}
      </RightDrawer>

    </div>
  );
}


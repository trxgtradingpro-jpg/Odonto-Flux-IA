"use client";

import { ChangeEvent, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, ChevronLeft, ChevronRight, Expand, Minimize, Palette } from "lucide-react";
import { toast } from "sonner";

import { DataTable, FilterBar, PageHeader, RightDrawer, StatCard, StatusBadge } from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { api } from "@/lib/api";
import {
  ApiPage,
  AppointmentItem,
  ConversationItem,
  PatientItem,
  ProfessionalItem,
  UnitItem,
} from "@/lib/domain-types";
import { formatDateBR, formatDateTimeBR, formatPhoneBR, numberFormatter } from "@/lib/formatters";
import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@odontoflux/ui";

type AgendaDataset = {
  appointments: AppointmentItem[];
  patients: PatientItem[];
  units: UnitItem[];
  professionals: ProfessionalItem[];
  conversations: ConversationItem[];
};

type AgendaSettingItem = {
  id: string;
  key: string;
  value: unknown;
  is_secret: boolean;
};

type EnrichedAppointment = AppointmentItem & {
  patient_name: string;
  patient_phone: string;
  unit_name: string;
  professional_name: string;
  last_conversation: string | null;
};

const COLOR_PALETTE = [
  "#9ad0ec",
  "#bfe3af",
  "#f4d7a1",
  "#e7b4c0",
  "#d4c1ec",
  "#b9ded4",
  "#ffd8b1",
  "#f3c4fb",
];

const WEEK_DAY_OPTIONS = [
  { value: 0, label: "Dom" },
  { value: 1, label: "Seg" },
  { value: 2, label: "Ter" },
  { value: 3, label: "Qua" },
  { value: 4, label: "Qui" },
  { value: 5, label: "Sex" },
  { value: 6, label: "Sab" },
] as const;

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

function toDateTimeLocalInput(value?: string | null): string {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  const year = parsed.getFullYear();
  const month = `${parsed.getMonth() + 1}`.padStart(2, "0");
  const day = `${parsed.getDate()}`.padStart(2, "0");
  const hour = `${parsed.getHours()}`.padStart(2, "0");
  const minute = `${parsed.getMinutes()}`.padStart(2, "0");
  return `${year}-${month}-${day}T${hour}:${minute}`;
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
  return fallback;
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
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

function getMonthGrid(monthDate: Date): Date[] {
  const firstOfMonth = new Date(monthDate.getFullYear(), monthDate.getMonth(), 1);
  const start = startOfWeekMonday(firstOfMonth);
  return Array.from({ length: 42 }, (_, index) => addDays(start, index));
}

export default function AgendaPage() {
  const queryClient = useQueryClient();
  const boardRef = useRef<HTMLDivElement | null>(null);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [unitFilter, setUnitFilter] = useState("all");
  const [viewMode, setViewMode] = useState<"day" | "week">("week");
  const [weekAnchor, setWeekAnchor] = useState(() => startOfWeekMonday(new Date()));
  const [focusedDate, setFocusedDate] = useState(() => new Date());
  const [selectedDayKeys, setSelectedDayKeys] = useState<string[]>([]);
  const [selectedProfessionalIds, setSelectedProfessionalIds] = useState<string[]>([]);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [professionalColors, setProfessionalColors] = useState<Record<string, string>>({});
  const [monthCursor, setMonthCursor] = useState(() => new Date());
  const [appointmentEditorOpen, setAppointmentEditorOpen] = useState(false);
  const [selectedAppointment, setSelectedAppointment] = useState<EnrichedAppointment | null>(null);
  const [editUnitId, setEditUnitId] = useState("");
  const [editProfessionalId, setEditProfessionalId] = useState("");
  const [editProcedure, setEditProcedure] = useState("");
  const [editStartsAt, setEditStartsAt] = useState("");
  const [editEndsAt, setEditEndsAt] = useState("");
  const [editStatus, setEditStatus] = useState("agendada");
  const [editConfirmationStatus, setEditConfirmationStatus] = useState("pendente");
  const [editNotes, setEditNotes] = useState("");

  const [patientId, setPatientId] = useState("");
  const [unitId, setUnitId] = useState("");
  const [professionalId, setProfessionalId] = useState("");
  const [procedure, setProcedure] = useState("");
  const [startsAt, setStartsAt] = useState("");

  const agendaQuery = useQuery<AgendaDataset>({
    queryKey: ["agenda-dataset"],
    queryFn: async () => {
      const [appointmentsResponse, patientsResponse, unitsResponse, professionalsResponse, conversationsResponse] =
        await Promise.all([
          api.get<ApiPage<AppointmentItem>>("/appointments", { params: { limit: 300, offset: 0 } }),
          api.get<ApiPage<PatientItem>>("/patients", { params: { limit: 200, offset: 0 } }),
          api.get<ApiPage<UnitItem>>("/units", { params: { limit: 100, offset: 0 } }),
          api.get<ApiPage<ProfessionalItem>>("/professionals", { params: { limit: 300, offset: 0 } }),
          api.get<ApiPage<ConversationItem>>("/conversations", { params: { limit: 200, offset: 0 } }),
        ]);

      return {
        appointments: appointmentsResponse.data.data ?? [],
        patients: patientsResponse.data.data ?? [],
        units: unitsResponse.data.data ?? [],
        professionals: professionalsResponse.data.data ?? [],
        conversations: conversationsResponse.data.data ?? [],
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

  const createMutation = useMutation({
    mutationFn: async () =>
      api.post("/appointments", {
        patient_id: patientId,
        unit_id: unitId,
        professional_id: professionalId || null,
        procedure_type: procedure,
        starts_at: new Date(startsAt).toISOString(),
      }),
    onSuccess: () => {
      toast.success("Consulta criada com sucesso.");
      setPatientId("");
      setUnitId("");
      setProfessionalId("");
      setProcedure("");
      setStartsAt("");
      queryClient.invalidateQueries({ queryKey: ["agenda-dataset"] });
    },
    onError: () => toast.error("Nao foi possivel criar a consulta."),
  });

  const updateMutation = useMutation({
    mutationFn: async ({ appointmentId, payload }: { appointmentId: string; payload: Record<string, unknown> }) =>
      api.patch(`/appointments/${appointmentId}`, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["agenda-dataset"] }),
    onError: (error) => toast.error(getApiErrorMessage(error, "Nao foi possivel atualizar a consulta.")),
  });

  const deleteMutation = useMutation({
    mutationFn: async (appointmentId: string) => api.delete(`/appointments/${appointmentId}`),
    onSuccess: () => {
      toast.success("Consulta excluida com sucesso.");
      setAppointmentEditorOpen(false);
      setSelectedAppointment(null);
      queryClient.invalidateQueries({ queryKey: ["agenda-dataset"] });
    },
    onError: (error) => toast.error(getApiErrorMessage(error, "Nao foi possivel excluir a consulta.")),
  });

  const saveColorsMutation = useMutation({
    mutationFn: async () =>
      api.put("/settings/agenda.professional_colors", {
        value: professionalColors,
        is_secret: false,
      }),
    onSuccess: () => {
      toast.success("Cores da agenda salvas.");
      queryClient.invalidateQueries({ queryKey: ["agenda-settings"] });
    },
    onError: () => toast.error("Nao foi possivel salvar as cores da agenda."),
  });

  useEffect(() => {
    if (!agendaQuery.data?.professionals?.length) return;
    if (selectedProfessionalIds.length) return;
    setSelectedProfessionalIds(agendaQuery.data.professionals.map((item) => item.id));
  }, [agendaQuery.data?.professionals, selectedProfessionalIds.length]);

  useEffect(() => {
    const weekKeys = Array.from({ length: 7 }, (_, index) => toDayKey(addDays(weekAnchor, index)));
    setSelectedDayKeys(weekKeys);
  }, [weekAnchor]);

  useEffect(() => {
    if (!agendaQuery.data?.professionals?.length) return;
    const settingMap = new Map((settingsQuery.data?.data ?? []).map((item) => [item.key, item.value]));
    const savedColors = settingMap.get("agenda.professional_colors");
    const saved = savedColors && typeof savedColors === "object" ? (savedColors as Record<string, unknown>) : {};
    const nextColors: Record<string, string> = {};

    agendaQuery.data.professionals.forEach((professional, index) => {
      const maybeSaved = saved?.[professional.id];
      if (typeof maybeSaved === "string" && /^#[0-9a-f]{6}$/i.test(maybeSaved)) {
        nextColors[professional.id] = maybeSaved;
      } else {
        nextColors[professional.id] = COLOR_PALETTE[index % COLOR_PALETTE.length];
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
  }, [selectedAppointment]);

  if (agendaQuery.isLoading) return <LoadingState message="Carregando agenda operacional..." />;
  if (agendaQuery.isError || !agendaQuery.data) return <ErrorState message="Nao foi possivel carregar a agenda." />;

  const dataset = agendaQuery.data;
  const patientsById = new Map(dataset.patients.map((item) => [item.id, item]));
  const unitsById = new Map(dataset.units.map((item) => [item.id, item.name]));
  const professionalsById = new Map(dataset.professionals.map((item) => [item.id, item]));
  const professionalsForSelectedUnit = dataset.professionals.filter(
    (item) => !unitId || item.unit_id === unitId || !item.unit_id,
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

  const displayDays =
    viewMode === "day"
      ? [
          {
            date: focusedDate,
            key: toDayKey(focusedDate),
            label: WEEK_DAY_OPTIONS[focusedDate.getDay()]?.label ?? "",
            dayOfMonth: `${focusedDate.getDate()}`.padStart(2, "0"),
          },
        ]
      : weekDays.filter((item) => selectedDayKeys.includes(item.key));

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

  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const tomorrowStart = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);

  const todayAppointments = dataset.appointments.filter((item) => {
    const starts = new Date(item.starts_at);
    return starts >= todayStart && starts < tomorrowStart;
  });
  const pendingConfirmation = dataset.appointments.filter((item) => item.confirmation_status === "pendente").length;
  const possibleSlots = Math.max(0, Math.max(1, selectedProfessionalIds.length) * 14 - todayAppointments.length);
  const monthCalendarDays = getMonthGrid(monthCursor);
  const professionalsForBoard = dataset.professionals.filter(
    (item) => !selectedProfessionalIds.length || selectedProfessionalIds.includes(item.id),
  );
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
  const pxPerMinute = 1.35;
  const boardHeight = totalMinutes * pxPerMinute;
  const slotMarks = Array.from({ length: Math.floor(totalMinutes / 30) + 1 }, (_, index) => boardStartMinutes + index * 30);
  const boardColumnMin = viewMode === "day" ? 180 : 140;
  const boardMinWidth = 72 + Math.max(displayDays.length, 1) * boardColumnMin;
  const professionalsForEditedUnit = dataset.professionals.filter(
    (item) => !editUnitId || item.unit_id === editUnitId || !item.unit_id,
  );

  const handleSaveAppointmentEdits = () => {
    if (!selectedAppointment) return;
    if (!editUnitId || !editProcedure.trim() || !editStartsAt) {
      toast.error("Preencha unidade, procedimento e data/hora.");
      return;
    }

    const parsedStartsAt = new Date(editStartsAt);
    if (Number.isNaN(parsedStartsAt.getTime())) {
      toast.error("Data/hora de inicio invalida.");
      return;
    }

    let parsedEndsAt: Date | null = null;
    if (editEndsAt) {
      parsedEndsAt = new Date(editEndsAt);
      if (Number.isNaN(parsedEndsAt.getTime())) {
        toast.error("Data/hora de termino invalida.");
        return;
      }
      if (parsedEndsAt <= parsedStartsAt) {
        toast.error("O termino deve ser maior que o inicio.");
        return;
      }
    }

    updateMutation.mutate(
      {
        appointmentId: selectedAppointment.id,
        payload: {
          unit_id: editUnitId,
          professional_id: editProfessionalId || null,
          procedure_type: editProcedure.trim(),
          starts_at: parsedStartsAt.toISOString(),
          ends_at: parsedEndsAt ? parsedEndsAt.toISOString() : null,
          status: editStatus,
          confirmation_status: editConfirmationStatus,
          notes: editNotes,
        },
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

  return (
    <div className="min-w-0 space-y-4">
      <PageHeader
        eyebrow="Agenda inteligente"
        title="Agenda operacional"
        description="Visual semanal, filtros por equipe, cores por profissional e atualizacao automatica. Cadastro da equipe em Equipe medica."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button variant={viewMode === "day" ? "default" : "outline"} className="h-9" onClick={() => setViewMode("day")}>
              Dia
            </Button>
            <Button variant={viewMode === "week" ? "default" : "outline"} className="h-9" onClick={() => setViewMode("week")}>
              Semana
            </Button>
            <Button
              variant="outline"
              className="h-9 gap-1"
              onClick={async () => {
                if (!boardRef.current) return;
                if (document.fullscreenElement === boardRef.current) {
                  await document.exitFullscreen();
                } else {
                  await boardRef.current.requestFullscreen();
                }
              }}
            >
              {isFullscreen ? <Minimize size={14} /> : <Expand size={14} />}
              Tela cheia
            </Button>
          </div>
        }
      />

      <div className="grid gap-4 md:grid-cols-3">
        <StatCard
          title="Consultas de hoje"
          value={numberFormatter.format(todayAppointments.length)}
          description="Agenda do dia"
        />
        <StatCard
          title="Sem confirmacao"
          value={numberFormatter.format(pendingConfirmation)}
          description="Requer acao da recepcao"
        />
        <StatCard
          title="Encaixes possiveis"
          value={numberFormatter.format(possibleSlots)}
          description="Estimativa de disponibilidade"
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[300px_minmax(0,1fr)]">
        <div className="space-y-4">
          <Card className="border-stone-200">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CalendarDays size={16} /> Navegacao da agenda
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <Button
                  variant="outline"
                  className="h-8 w-8 px-0"
                  onClick={() => {
                    setWeekAnchor((current) => addDays(current, -7));
                    setMonthCursor((current) => addDays(current, -7));
                  }}
                >
                  <ChevronLeft size={14} />
                </Button>
                <p className="min-w-0 flex-1 text-center text-xs font-semibold text-stone-700 sm:text-sm">
                  {formatDateBR(weekAnchor)} - {formatDateBR(addDays(weekAnchor, 6))}
                </p>
                <Button
                  variant="outline"
                  className="h-8 w-8 px-0"
                  onClick={() => {
                    setWeekAnchor((current) => addDays(current, 7));
                    setMonthCursor((current) => addDays(current, 7));
                  }}
                >
                  <ChevronRight size={14} />
                </Button>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  className="h-8"
                  onClick={() => {
                    const today = new Date();
                    setFocusedDate(today);
                    setWeekAnchor(startOfWeekMonday(today));
                    setMonthCursor(today);
                  }}
                >
                  Hoje
                </Button>
                <Button
                  variant="outline"
                  className="h-8"
                  onClick={() => setSelectedDayKeys(weekDays.map((item) => item.key))}
                >
                  Selecionar todos
                </Button>
              </div>

              <div className="overflow-x-auto">
                <div className="grid min-w-[320px] grid-cols-7 gap-1 rounded-md border border-stone-200 bg-stone-50 p-2 text-xs">
                  {WEEK_DAY_OPTIONS.map((item) => (
                    <p key={`month-head-${item.value}`} className="text-center font-semibold text-stone-500">
                      {item.label}
                    </p>
                  ))}
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

          <Card className="border-stone-200">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Palette size={16} /> Cores e filtros da equipe
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {dataset.professionals.length ? (
                dataset.professionals.map((professional) => {
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
                <p className="text-xs text-stone-500">Nenhum profissional cadastrado.</p>
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

        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle>Grade visual da agenda</CardTitle>
          </CardHeader>
          <CardContent>
            <div ref={boardRef} className="overflow-auto rounded-lg border border-stone-200 bg-white">
              <div style={{ minWidth: boardMinWidth }}>
                <div
                  className="grid border-b border-stone-200"
                  style={{ gridTemplateColumns: `72px repeat(${Math.max(displayDays.length, 1)}, minmax(${boardColumnMin}px, 1fr))` }}
                >
                  <div className="border-r border-stone-200 bg-stone-50 p-2 text-xs font-semibold text-stone-500">Hora</div>
                  {displayDays.length ? (
                    displayDays.map((day) => (
                      <div key={`board-head-${day.key}`} className="border-r border-stone-200 bg-stone-50 p-2 text-sm font-semibold text-stone-700">
                        {day.label}, {day.dayOfMonth}
                      </div>
                    ))
                  ) : (
                    <div className="p-3 text-sm text-stone-500">Selecione ao menos um dia.</div>
                  )}
                </div>

                <div
                  className="grid"
                  style={{ gridTemplateColumns: `72px repeat(${Math.max(displayDays.length, 1)}, minmax(${boardColumnMin}px, 1fr))` }}
                >
                  <div className="relative border-r border-stone-200 bg-stone-50" style={{ height: boardHeight }}>
                    {slotMarks.map((slot) => (
                      <div
                        key={`slot-mark-${slot}`}
                        className="absolute left-0 right-0 border-t border-dashed border-stone-200 px-1 text-[10px] text-stone-500"
                        style={{ top: (slot - boardStartMinutes) * pxPerMinute }}
                      >
                        {formatTimeFromMinutes(slot)}
                      </div>
                    ))}
                  </div>

                  {displayDays.map((day) => {
                    const dayAppointments = appointments.filter((appointment) => toDayKey(new Date(appointment.starts_at)) === day.key);
                    const availability = professionalsForBoard
                      .filter((professional) => (professional.working_days ?? []).includes(day.date.getDay()))
                      .map((professional) => {
                        const start = parseTimeToMinutes(professional.shift_start, boardStartMinutes);
                        const end = parseTimeToMinutes(professional.shift_end, boardEndMinutes);
                        const clampedStart = clamp(start, boardStartMinutes, boardEndMinutes);
                        const clampedEnd = clamp(end, boardStartMinutes, boardEndMinutes);
                        return {
                          id: professional.id,
                          top: (clampedStart - boardStartMinutes) * pxPerMinute,
                          height: Math.max(0, (clampedEnd - clampedStart) * pxPerMinute),
                          color: professionalColors[professional.id] ?? "#9ad0ec",
                        };
                      })
                      .filter((item) => item.height > 0);

                    return (
                      <div key={`board-day-${day.key}`} className="relative border-r border-stone-200" style={{ height: boardHeight }}>
                        {slotMarks.map((slot) => (
                          <div
                            key={`slot-line-${day.key}-${slot}`}
                            className="absolute left-0 right-0 border-t border-dashed border-stone-200"
                            style={{ top: (slot - boardStartMinutes) * pxPerMinute }}
                          />
                        ))}
                        {availability.map((item) => (
                          <div
                            key={`availability-${day.key}-${item.id}`}
                            className="absolute left-1 right-1 rounded-md"
                            style={{ top: item.top, height: item.height, backgroundColor: hexToRgba(item.color, 0.15) }}
                          />
                        ))}
                        {dayAppointments.map((appointment) => {
                          const start = new Date(appointment.starts_at);
                          const end = appointment.ends_at ? new Date(appointment.ends_at) : new Date(start.getTime() + 60 * 60 * 1000);
                          const startMin = start.getHours() * 60 + start.getMinutes();
                          const endMin = end.getHours() * 60 + end.getMinutes();
                          const clampedStart = clamp(startMin, boardStartMinutes, boardEndMinutes);
                          const clampedEnd = clamp(endMin, boardStartMinutes, boardEndMinutes);
                          const top = (clampedStart - boardStartMinutes) * pxPerMinute;
                          const height = Math.max(34, (clampedEnd - clampedStart) * pxPerMinute);
                          const color = appointment.professional_id ? professionalColors[appointment.professional_id] ?? "#9ad0ec" : "#d6d3d1";

                          return (
                            <button
                              type="button"
                              key={appointment.id}
                              className="absolute left-1 right-1 overflow-hidden rounded-md border p-2 text-left shadow-sm transition hover:scale-[1.01]"
                              style={{
                                top,
                                minHeight: height,
                                backgroundColor: hexToRgba(color, 0.92),
                                borderColor: hexToRgba(color, 1),
                              }}
                              onClick={() => {
                                setSelectedAppointment(appointment);
                                setAppointmentEditorOpen(true);
                              }}
                            >
                              <p className="truncate text-xs font-semibold text-stone-800">{appointment.patient_name}</p>
                              <p className="truncate text-[11px] text-stone-700">{appointment.procedure_type}</p>
                              <p className="truncate text-[11px] text-stone-700">{appointment.professional_name}</p>
                            </button>
                          );
                        })}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
            <p className="mt-2 text-xs text-stone-500">
              A agenda sincroniza automaticamente com os novos dados sem precisar atualizar a pagina.
            </p>
          </CardContent>
        </Card>
      </div>

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
            <Card className="border-stone-200">
              <CardContent className="space-y-3 p-4">
                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-500">Paciente</p>
                  <div className="rounded-md border border-stone-200 bg-stone-50 p-3 text-sm text-stone-700">
                    <p className="font-semibold text-stone-800">{selectedAppointment.patient_name}</p>
                    <p className="text-xs text-stone-500">{formatPhoneBR(selectedAppointment.patient_phone)}</p>
                  </div>
                </div>

                <div className="grid gap-2 md:grid-cols-2">
                  <div>
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-500">Unidade</p>
                    <select
                      className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                      value={editUnitId}
                      onChange={(event) => {
                        const nextUnitId = event.target.value;
                        setEditUnitId(nextUnitId);
                        setEditProfessionalId((current) => {
                          if (!current) return "";
                          const allowed = dataset.professionals.some(
                            (professional) =>
                              professional.id === current &&
                              (professional.unit_id === nextUnitId || !professional.unit_id),
                          );
                          return allowed ? current : "";
                        });
                      }}
                    >
                      <option value="">Selecione a unidade</option>
                      {dataset.units.map((unit) => (
                        <option key={unit.id} value={unit.id}>
                          {unit.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-500">Profissional</p>
                    <select
                      className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                      value={editProfessionalId}
                      onChange={(event) => setEditProfessionalId(event.target.value)}
                    >
                      <option value="">Sem profissional (opcional)</option>
                      {professionalsForEditedUnit.map((professional) => (
                        <option key={professional.id} value={professional.id}>
                          {professional.full_name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-500">Procedimento</p>
                  <Input
                    placeholder="Ex.: Instalacao de lentes"
                    value={editProcedure}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => setEditProcedure(event.target.value)}
                  />
                </div>

                <div className="grid gap-2 md:grid-cols-2">
                  <div>
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-500">Inicio</p>
                    <Input
                      type="datetime-local"
                      value={editStartsAt}
                      onChange={(event: ChangeEvent<HTMLInputElement>) => setEditStartsAt(event.target.value)}
                    />
                  </div>

                  <div>
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-500">Fim</p>
                    <Input
                      type="datetime-local"
                      value={editEndsAt}
                      onChange={(event: ChangeEvent<HTMLInputElement>) => setEditEndsAt(event.target.value)}
                    />
                  </div>
                </div>

                <div className="grid gap-2 md:grid-cols-2">
                  <div>
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-500">Status da consulta</p>
                    <select
                      className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                      value={editStatus}
                      onChange={(event) => setEditStatus(event.target.value)}
                    >
                      {APPOINTMENT_STATUS_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-500">Confirmacao</p>
                    <select
                      className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
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

                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-500">Observacoes</p>
                  <textarea
                    className="min-h-[84px] w-full rounded-md border border-stone-300 bg-white p-2 text-sm"
                    placeholder="Observacoes da consulta"
                    value={editNotes}
                    onChange={(event) => setEditNotes(event.target.value)}
                  />
                </div>

                <div className="flex justify-end gap-2">
                  <Button
                    variant="destructive"
                    onClick={() => {
                      if (!selectedAppointment) return;
                      if (!window.confirm("Deseja excluir esta consulta? Esta acao nao pode ser desfeita.")) return;
                      deleteMutation.mutate(selectedAppointment.id);
                    }}
                    disabled={deleteMutation.isPending || updateMutation.isPending}
                  >
                    {deleteMutation.isPending ? "Excluindo..." : "Excluir consulta"}
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
                  <Button onClick={handleSaveAppointmentEdits} disabled={updateMutation.isPending || deleteMutation.isPending}>
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

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle>Nova consulta</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-500">Paciente</p>
              <select
                className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
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
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-500">Unidade</p>
              <select
                className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                value={unitId}
                onChange={(event) => {
                  setUnitId(event.target.value);
                  setProfessionalId("");
                }}
              >
                <option value="">Selecione a unidade</option>
                {dataset.units.map((unit) => (
                  <option key={unit.id} value={unit.id}>
                    {unit.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-500">Profissional</p>
              <select
                className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                value={professionalId}
                onChange={(event) => setProfessionalId(event.target.value)}
              >
                <option value="">Sem profissional (opcional)</option>
                {professionalsForSelectedUnit.map((professional) => (
                  <option key={professional.id} value={professional.id}>
                    {professional.full_name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-500">Procedimento</p>
              <Input
                placeholder="Ex.: Limpeza odontologica"
                value={procedure}
                onChange={(event: ChangeEvent<HTMLInputElement>) => setProcedure(event.target.value)}
              />
            </div>
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-500">Data e hora</p>
              <Input
                type="datetime-local"
                value={startsAt}
                onChange={(event: ChangeEvent<HTMLInputElement>) => setStartsAt(event.target.value)}
              />
            </div>
            <div className="flex items-end">
              <Button
                className="w-full"
                onClick={() => {
                  if (!patientId || !unitId || !procedure || !startsAt) {
                    toast.error("Preencha todos os campos para criar a consulta.");
                    return;
                  }
                  createMutation.mutate();
                }}
                disabled={createMutation.isPending}
              >
                {createMutation.isPending ? "Criando..." : "Criar consulta"}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <FilterBar search={search} onSearchChange={setSearch} searchPlaceholder="Buscar paciente, unidade ou procedimento...">
        <select
          className="h-9 rounded-md border border-stone-300 bg-white px-2 text-sm"
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
        <select
          className="h-9 rounded-md border border-stone-300 bg-white px-2 text-sm"
          value={unitFilter}
          onChange={(event) => setUnitFilter(event.target.value)}
        >
          <option value="all">Todas as unidades</option>
          {dataset.units.map((unit) => (
            <option key={unit.id} value={unit.id}>
              {unit.name}
            </option>
          ))}
        </select>
      </FilterBar>

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
                >
                  Confirmar
                </Button>
                <Button
                  variant="outline"
                  className="h-8 px-2 text-xs"
                  onClick={() =>
                    updateMutation.mutate({
                      appointmentId: item.id,
                      payload: { status: "agendada", confirmation_status: "pendente" },
                    })
                  }
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
                >
                  Cancelar
                </Button>
              </div>
            ),
          },
        ]}
        emptyTitle="Sem consultas no periodo"
        emptyDescription="Nenhuma consulta encontrada com os filtros atuais."
      />
    </div>
  );
}

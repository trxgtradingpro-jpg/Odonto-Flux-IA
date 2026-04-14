"use client";

import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, ChevronLeft, ChevronRight, Expand, Minimize, Palette } from "lucide-react";
import { toast } from "sonner";

import { DataTable, FilterBar, PageHeader, StatCard, StatusBadge } from "@/components/premium";
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

  const [patientId, setPatientId] = useState("");
  const [unitId, setUnitId] = useState("");
  const [professionalId, setProfessionalId] = useState("");
  const [procedure, setProcedure] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [newProfessionalName, setNewProfessionalName] = useState("");
  const [newProfessionalUnitId, setNewProfessionalUnitId] = useState("");
  const [newProfessionalSpecialty, setNewProfessionalSpecialty] = useState("");
  const [newProfessionalCro, setNewProfessionalCro] = useState("");
  const [newProfessionalStart, setNewProfessionalStart] = useState("08:00");
  const [newProfessionalEnd, setNewProfessionalEnd] = useState("18:00");
  const [newProfessionalProcedures, setNewProfessionalProcedures] = useState("");
  const [newProfessionalDays, setNewProfessionalDays] = useState<number[]>([1, 2, 3, 4, 5]);

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
    onError: () => toast.error("Nao foi possivel atualizar a consulta."),
  });

  const createProfessionalMutation = useMutation({
    mutationFn: async () => {
      const procedures = newProfessionalProcedures
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);

      return api.post("/professionals", {
        full_name: newProfessionalName,
        unit_id: newProfessionalUnitId || null,
        specialty: newProfessionalSpecialty || null,
        cro_number: newProfessionalCro || null,
        working_days: newProfessionalDays,
        shift_start: newProfessionalStart,
        shift_end: newProfessionalEnd,
        procedures,
        is_active: true,
      });
    },
    onSuccess: () => {
      toast.success("Profissional cadastrado com sucesso.");
      setNewProfessionalName("");
      setNewProfessionalUnitId("");
      setNewProfessionalSpecialty("");
      setNewProfessionalCro("");
      setNewProfessionalStart("08:00");
      setNewProfessionalEnd("18:00");
      setNewProfessionalProcedures("");
      setNewProfessionalDays([1, 2, 3, 4, 5]);
      queryClient.invalidateQueries({ queryKey: ["agenda-dataset"] });
    },
    onError: () => toast.error("Nao foi possivel cadastrar o profissional."),
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

  if (agendaQuery.isLoading) return <LoadingState message="Carregando agenda operacional..." />;
  if (agendaQuery.isError || !agendaQuery.data) return <ErrorState message="Nao foi possivel carregar a agenda." />;

  const dataset = agendaQuery.data;
  const patientsById = new Map(dataset.patients.map((item) => [item.id, item]));
  const unitsById = new Map(dataset.units.map((item) => [item.id, item.name]));
  const professionalsById = new Map(dataset.professionals.map((item) => [item.id, item]));
  const professionalsForSelectedUnit = dataset.professionals.filter((item) => !unitId || item.unit_id === unitId);

  const weekDayOptions = useMemo(
    () => [
      { value: 0, label: "Dom" },
      { value: 1, label: "Seg" },
      { value: 2, label: "Ter" },
      { value: 3, label: "Qua" },
      { value: 4, label: "Qui" },
      { value: 5, label: "Sex" },
      { value: 6, label: "Sab" },
    ],
    [],
  );

  const weekDays = Array.from({ length: 7 }, (_, index) => {
    const date = addDays(weekAnchor, index);
    return {
      date,
      key: toDayKey(date),
      label: weekDayOptions[date.getDay()]?.label ?? "",
      dayOfMonth: `${date.getDate()}`.padStart(2, "0"),
    };
  });

  const displayDays =
    viewMode === "day"
      ? [
          {
            date: focusedDate,
            key: toDayKey(focusedDate),
            label: weekDayOptions[focusedDate.getDay()]?.label ?? "",
            dayOfMonth: `${focusedDate.getDate()}`.padStart(2, "0"),
          },
        ]
      : weekDays.filter((item) => selectedDayKeys.includes(item.key));

  const appointments = dataset.appointments
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

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Agenda inteligente"
        title="Agenda operacional"
        description="Visual semanal, filtros por equipe, cores por profissional e atualizacao automatica."
        actions={
          <div className="flex items-center gap-2">
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

      <div className="grid gap-4 xl:grid-cols-[320px_1fr]">
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
                <p className="text-sm font-semibold text-stone-700">
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

              <div className="grid grid-cols-7 gap-1 rounded-md border border-stone-200 bg-stone-50 p-2 text-xs">
                {weekDayOptions.map((item) => (
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
              <div className="min-w-[860px]">
                <div
                  className="grid border-b border-stone-200"
                  style={{ gridTemplateColumns: `72px repeat(${Math.max(displayDays.length, 1)}, minmax(220px, 1fr))` }}
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
                  style={{ gridTemplateColumns: `72px repeat(${Math.max(displayDays.length, 1)}, minmax(220px, 1fr))` }}
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
                              className="absolute left-1 right-1 rounded-md border p-2 text-left shadow-sm transition hover:scale-[1.01]"
                              style={{
                                top,
                                minHeight: height,
                                backgroundColor: hexToRgba(color, 0.92),
                                borderColor: hexToRgba(color, 1),
                              }}
                              onClick={() =>
                                toast.info(
                                  `${appointment.patient_name} | ${appointment.procedure_type} | ${formatDateTimeBR(
                                    appointment.starts_at,
                                  )}`,
                                )
                              }
                            >
                              <p className="text-xs font-semibold text-stone-800">{appointment.patient_name}</p>
                              <p className="text-[11px] text-stone-700">{appointment.procedure_type}</p>
                              <p className="text-[11px] text-stone-700">{appointment.professional_name}</p>
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

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle>Nova consulta</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2 md:grid-cols-6">
            <select
              className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm"
              value={patientId}
              onChange={(event) => setPatientId(event.target.value)}
            >
              <option value="">Paciente</option>
              {dataset.patients.map((patient) => (
                <option key={patient.id} value={patient.id}>
                  {patient.full_name}
                </option>
              ))}
            </select>
            <select
              className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm"
              value={unitId}
              onChange={(event) => {
                setUnitId(event.target.value);
                setProfessionalId("");
              }}
            >
              <option value="">Unidade</option>
              {dataset.units.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  {unit.name}
                </option>
              ))}
            </select>
            <select
              className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm"
              value={professionalId}
              onChange={(event) => setProfessionalId(event.target.value)}
            >
              <option value="">Profissional (opcional)</option>
              {professionalsForSelectedUnit.map((professional) => (
                <option key={professional.id} value={professional.id}>
                  {professional.full_name}
                </option>
              ))}
            </select>
            <Input
              placeholder="Procedimento"
              value={procedure}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setProcedure(event.target.value)}
            />
            <Input
              type="datetime-local"
              value={startsAt}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setStartsAt(event.target.value)}
            />
            <Button
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
        </CardContent>
      </Card>

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle>Equipe clinica (dias, horarios e servicos)</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2 md:grid-cols-4">
            <Input
              placeholder="Nome do profissional"
              value={newProfessionalName}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setNewProfessionalName(event.target.value)}
            />
            <select
              className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm"
              value={newProfessionalUnitId}
              onChange={(event) => setNewProfessionalUnitId(event.target.value)}
            >
              <option value="">Unidade</option>
              {dataset.units.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  {unit.name}
                </option>
              ))}
            </select>
            <Input
              placeholder="Especialidade (opcional)"
              value={newProfessionalSpecialty}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setNewProfessionalSpecialty(event.target.value)}
            />
            <Input
              placeholder="CRO (opcional)"
              value={newProfessionalCro}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setNewProfessionalCro(event.target.value)}
            />
          </div>

          <div className="mt-3 grid gap-2 md:grid-cols-3">
            <Input
              type="time"
              value={newProfessionalStart}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setNewProfessionalStart(event.target.value)}
            />
            <Input
              type="time"
              value={newProfessionalEnd}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setNewProfessionalEnd(event.target.value)}
            />
            <Input
              placeholder="Servicos (virgula): avaliacao, lentes, limpeza"
              value={newProfessionalProcedures}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setNewProfessionalProcedures(event.target.value)}
            />
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            {weekDayOptions.map((day) => {
              const checked = newProfessionalDays.includes(day.value);
              return (
                <label
                  key={day.value}
                  className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-stone-300 px-3 py-1 text-xs text-stone-700"
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(event) => {
                      if (event.target.checked) {
                        setNewProfessionalDays((current) =>
                          Array.from(new Set([...current, day.value])).sort((left, right) => left - right),
                        );
                      } else {
                        setNewProfessionalDays((current) => current.filter((item) => item !== day.value));
                      }
                    }}
                  />
                  {day.label}
                </label>
              );
            })}
          </div>

          <div className="mt-4 flex items-center justify-between gap-3">
            <p className="text-xs text-stone-500">
              Cadastre cada profissional individualmente. A IA usa essas regras para sugerir e confirmar horarios.
            </p>
            <Button
              onClick={() => {
                if (!newProfessionalName || !newProfessionalUnitId) {
                  toast.error("Informe nome e unidade do profissional.");
                  return;
                }
                if (!newProfessionalDays.length) {
                  toast.error("Selecione ao menos um dia de atendimento.");
                  return;
                }
                createProfessionalMutation.mutate();
              }}
              disabled={createProfessionalMutation.isPending}
            >
              {createProfessionalMutation.isPending ? "Salvando..." : "Cadastrar profissional"}
            </Button>
          </div>

          <div className="mt-4 rounded-md border border-stone-200 bg-stone-50 p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Profissionais cadastrados</p>
            <div className="mt-2 space-y-2">
              {dataset.professionals.length ? (
                dataset.professionals.map((professional) => {
                  const unitName = professional.unit_id ? unitsById.get(professional.unit_id) : "Sem unidade";
                  const days = professional.working_days
                    .slice()
                    .sort()
                    .map((day) => weekDayOptions.find((item) => item.value === day)?.label ?? String(day))
                    .join(", ");
                  return (
                    <div
                      key={professional.id}
                      className="rounded-md border border-stone-200 bg-white p-3 text-sm text-stone-700"
                    >
                      <p className="font-semibold text-stone-800">{professional.full_name}</p>
                      <p className="text-xs text-stone-500">
                        {unitName} - {professional.shift_start} as {professional.shift_end} - {days || "Sem dias"}
                      </p>
                      <p className="mt-1 text-xs text-stone-600">
                        Servicos: {professional.procedures.length ? professional.procedures.join(", ") : "Nao informados"}
                      </p>
                    </div>
                  );
                })
              ) : (
                <p className="text-xs text-stone-500">Nenhum profissional cadastrado ainda.</p>
              )}
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

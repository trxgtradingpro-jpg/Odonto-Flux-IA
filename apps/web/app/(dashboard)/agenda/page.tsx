"use client";

import { ChangeEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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

export default function AgendaPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [unitFilter, setUnitFilter] = useState("all");
  const [viewMode, setViewMode] = useState<"day" | "week">("day");

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

  if (agendaQuery.isLoading) return <LoadingState message="Carregando agenda operacional..." />;
  if (agendaQuery.isError || !agendaQuery.data) return <ErrorState message="Nao foi possivel carregar a agenda." />;

  const dataset = agendaQuery.data;
  const patientsById = new Map(dataset.patients.map((item) => [item.id, item]));
  const unitsById = new Map(dataset.units.map((item) => [item.id, item.name]));
  const professionalsById = new Map(dataset.professionals.map((item) => [item.id, item]));
  const professionalsForSelectedUnit = dataset.professionals.filter((item) => !unitId || item.unit_id === unitId);

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

      const startsAtDate = new Date(appointment.starts_at);
      const now = new Date();
      const viewDays = viewMode === "day" ? 1 : 7;
      const maxDate = new Date(now);
      maxDate.setDate(now.getDate() + viewDays);
      const byView = startsAtDate >= new Date(now.setHours(0, 0, 0, 0)) && startsAtDate <= maxDate;
      return bySearch && byStatus && byUnit && byView;
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
  const possibleSlots = Math.max(0, dataset.units.length * 12 - todayAppointments.length);
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

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Operacao clinica"
        title="Agenda operacional"
        description="Gestao de consultas com foco em confirmacao, no-show e produtividade da recepcao."
        actions={
          <div className="flex items-center gap-2">
            <Button variant={viewMode === "day" ? "default" : "outline"} className="h-9" onClick={() => setViewMode("day")}>
              Visao diaria
            </Button>
            <Button variant={viewMode === "week" ? "default" : "outline"} className="h-9" onClick={() => setViewMode("week")}>
              Visao semanal
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

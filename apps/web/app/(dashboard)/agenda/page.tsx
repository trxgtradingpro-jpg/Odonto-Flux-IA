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
  UnitItem,
} from "@/lib/domain-types";
import { formatDateBR, formatDateTimeBR, formatPhoneBR, numberFormatter } from "@/lib/formatters";
import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@odontoflux/ui";

type AgendaDataset = {
  appointments: AppointmentItem[];
  patients: PatientItem[];
  units: UnitItem[];
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
  const [procedure, setProcedure] = useState("");
  const [startsAt, setStartsAt] = useState("");

  const agendaQuery = useQuery<AgendaDataset>({
    queryKey: ["agenda-dataset"],
    queryFn: async () => {
      const [appointmentsResponse, patientsResponse, unitsResponse, conversationsResponse] = await Promise.all([
        api.get<ApiPage<AppointmentItem>>("/appointments", { params: { limit: 300, offset: 0 } }),
        api.get<ApiPage<PatientItem>>("/patients", { params: { limit: 200, offset: 0 } }),
        api.get<ApiPage<UnitItem>>("/units", { params: { limit: 100, offset: 0 } }),
        api.get<ApiPage<ConversationItem>>("/conversations", { params: { limit: 200, offset: 0 } }),
      ]);

      return {
        appointments: appointmentsResponse.data.data ?? [],
        patients: patientsResponse.data.data ?? [],
        units: unitsResponse.data.data ?? [],
        conversations: conversationsResponse.data.data ?? [],
      };
    },
  });

  const createMutation = useMutation({
    mutationFn: async () =>
      api.post("/appointments", {
        patient_id: patientId,
        unit_id: unitId,
        procedure_type: procedure,
        starts_at: new Date(startsAt).toISOString(),
      }),
    onSuccess: () => {
      toast.success("Consulta criada com sucesso.");
      setPatientId("");
      setUnitId("");
      setProcedure("");
      setStartsAt("");
      queryClient.invalidateQueries({ queryKey: ["agenda-dataset"] });
    },
    onError: () => toast.error("Não foi possível criar a consulta."),
  });

  const updateMutation = useMutation({
    mutationFn: async ({ appointmentId, payload }: { appointmentId: string; payload: Record<string, unknown> }) =>
      api.patch(`/appointments/${appointmentId}`, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["agenda-dataset"] }),
    onError: () => toast.error("Não foi possível atualizar a consulta."),
  });

  if (agendaQuery.isLoading) return <LoadingState message="Carregando agenda operacional..." />;
  if (agendaQuery.isError || !agendaQuery.data) return <ErrorState message="Não foi possível carregar a agenda." />;

  const dataset = agendaQuery.data;
  const patientsById = new Map(dataset.patients.map((item) => [item.id, item]));
  const unitsById = new Map(dataset.units.map((item) => [item.id, item.name]));

  const appointments = dataset.appointments
    .map((appointment) => {
      const patient = patientsById.get(appointment.patient_id);
      const unit = unitsById.get(appointment.unit_id) ?? "Unidade não identificada";
      const lastConversation = dataset.conversations
        .filter((conversation) => conversation.patient_id === appointment.patient_id)
        .sort(
          (left, right) =>
            new Date(right.last_message_at || 0).getTime() - new Date(left.last_message_at || 0).getTime(),
        )[0];

      return {
        ...appointment,
        patient_name: patient?.full_name ?? "Paciente não identificado",
        patient_phone: patient?.phone ?? "",
        unit_name: unit,
        last_conversation: lastConversation?.last_message_at ?? null,
      };
    })
    .filter((appointment) => {
      const term = search.toLowerCase().trim();
      const haystack = `${appointment.patient_name} ${appointment.procedure_type} ${appointment.unit_name}`.toLowerCase();
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

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Operação clínica"
        title="Agenda operacional"
        description="Gestão de consultas com foco em confirmação, no-show e produtividade da recepção."
        actions={
          <div className="flex items-center gap-2">
            <Button variant={viewMode === "day" ? "default" : "outline"} className="h-9" onClick={() => setViewMode("day")}>
              Visão diária
            </Button>
            <Button variant={viewMode === "week" ? "default" : "outline"} className="h-9" onClick={() => setViewMode("week")}>
              Visão semanal
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
          title="Sem confirmação"
          value={numberFormatter.format(pendingConfirmation)}
          description="Requer ação da recepção"
        />
        <StatCard
          title="Encaixes possíveis"
          value={numberFormatter.format(possibleSlots)}
          description="Estimativa de disponibilidade"
        />
      </div>

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle>Nova consulta</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2 md:grid-cols-5">
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
              onChange={(event) => setUnitId(event.target.value)}
            >
              <option value="">Unidade</option>
              {dataset.units.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  {unit.name}
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
          <option value="concluida">Concluído</option>
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
        searchBy={(item) => `${item.patient_name} ${item.procedure_type} ${item.unit_name}`}
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
            key: "status",
            label: "Status",
            render: (item) => <StatusBadge value={item.status} />,
          },
          {
            key: "confirmacao",
            label: "Confirmação",
            render: (item) => <StatusBadge value={item.confirmation_status} />,
          },
          {
            key: "ultima_conversa",
            label: "Última conversa",
            render: (item) => formatDateBR(item.last_conversation),
          },
          {
            key: "acoes",
            label: "Ações rápidas",
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
        emptyTitle="Sem consultas no período"
        emptyDescription="Nenhuma consulta encontrada com os filtros atuais."
      />
    </div>
  );
}

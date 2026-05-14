"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, FileText, MessageSquare, Pencil, Trash2, UserPlus, X } from "lucide-react";
import { toast } from "sonner";

import { DataTable, FilterBar, PageHeader, RightDrawer, StatusBadge } from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { useOwnerUnitScope } from "@/hooks/use-owner-unit-scope";
import { useSession } from "@/hooks/use-session";
import { api } from "@/lib/api";
import {
  ApiPage,
  AppointmentItem,
  ConversationItem,
  DocumentItem,
  PatientItem,
  ProfessionalItem,
  UnitItem,
} from "@/lib/domain-types";
import { formatCpfBR, formatDateBR, formatDateTimeBR, formatPhoneBR } from "@/lib/formatters";
import { canAccessPage } from "@/lib/page-access";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from "@odontoflux/ui";

type PatientsDataset = {
  patients: PatientItem[];
  units: UnitItem[];
  appointments: AppointmentItem[];
  conversations: ConversationItem[];
  documents: DocumentItem[];
  professionals: ProfessionalItem[];
};

type PatientDetailTab = "resumo" | "procedimentos" | "conversas" | "documentos" | "historico";

const PATIENT_DETAIL_TABS: { id: PatientDetailTab; label: string }[] = [
  { id: "resumo", label: "Resumo" },
  { id: "procedimentos", label: "Procedimentos" },
  { id: "conversas", label: "WhatsApp" },
  { id: "documentos", label: "Documentos" },
  { id: "historico", label: "Historico" },
];

const UNASSIGNED_UNIT_FILTER = "__sem_unidade__";

function splitTags(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function isEvaluationProcedure(value?: string | null): boolean {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .includes("avali");
}

export default function PacientesPage() {
  const queryClient = useQueryClient();
  const ownerUnitScope = useOwnerUnitScope();
  const selectedOwnerUnitId =
    ownerUnitScope.canSwitchUnits && ownerUnitScope.selectedUnitId !== "all"
      ? ownerUnitScope.selectedUnitId
      : null;
  const sessionQuery = useSession();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [unitFilter, setUnitFilter] = useState("all");
  const [tagFilter, setTagFilter] = useState("all");
  const [createDrawerOpen, setCreateDrawerOpen] = useState(false);
  const [editDrawerOpen, setEditDrawerOpen] = useState(false);
  const [detailsDrawerOpen, setDetailsDrawerOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [detailsTab, setDetailsTab] = useState<PatientDetailTab>("resumo");
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null);

  const [formName, setFormName] = useState("");
  const [formPhone, setFormPhone] = useState("");
  const [formCpf, setFormCpf] = useState("");
  const [formEmail, setFormEmail] = useState("");
  const [formBirthDate, setFormBirthDate] = useState("");
  const [formUnitId, setFormUnitId] = useState("");
  const [formTags, setFormTags] = useState("");
  const [formStatus, setFormStatus] = useState("ativo");
  const [formOrigin, setFormOrigin] = useState("");
  const [formNotes, setFormNotes] = useState("");

  const resetForm = () => {
    setFormName("");
    setFormPhone("");
    setFormCpf("");
    setFormEmail("");
    setFormBirthDate("");
    setFormUnitId(ownerUnitScope.canSwitchUnits && ownerUnitScope.selectedUnitId !== "all" ? ownerUnitScope.selectedUnitId : "");
    setFormTags("");
    setFormStatus("ativo");
    setFormOrigin("");
    setFormNotes("");
  };

  const patientsQuery = useQuery<PatientsDataset>({
    queryKey: ["patients-dataset", selectedOwnerUnitId ?? "all"],
    queryFn: async () => {
      const [
        patientsResponse,
        unitsResponse,
        appointmentsResponse,
        conversationsResponse,
        documentsResponse,
        professionalsResponse,
      ] = await Promise.all([
        api.get<ApiPage<PatientItem>>("/patients", {
          params: { limit: 400, offset: 0, unit_id: selectedOwnerUnitId ?? undefined },
        }),
        api.get<ApiPage<UnitItem>>("/units", { params: { limit: 100, offset: 0 } }),
        api.get<ApiPage<AppointmentItem>>("/appointments", {
          params: { limit: 400, offset: 0, unit_id: selectedOwnerUnitId ?? undefined },
        }),
        api.get<ApiPage<ConversationItem>>("/conversations", {
          params: { limit: 400, offset: 0, unit_id: selectedOwnerUnitId ?? undefined },
        }),
        api.get<ApiPage<DocumentItem>>("/documents", {
          params: { limit: 400, offset: 0, unit_id: selectedOwnerUnitId ?? undefined },
        }),
        api.get<ApiPage<ProfessionalItem>>("/professionals", {
          params: { limit: 300, offset: 0, unit_id: selectedOwnerUnitId ?? undefined },
        }),
      ]);

      return {
        patients: patientsResponse.data.data ?? [],
        units: unitsResponse.data.data ?? [],
        appointments: appointmentsResponse.data.data ?? [],
        conversations: conversationsResponse.data.data ?? [],
        documents: documentsResponse.data.data ?? [],
        professionals: professionalsResponse.data.data ?? [],
      };
    },
    refetchOnWindowFocus: true,
  });

  const createPatientMutation = useMutation({
    mutationFn: async () =>
      api.post("/patients", {
        full_name: formName.trim(),
        phone: formPhone.trim(),
        cpf: formCpf.trim() || null,
        email: formEmail.trim() || null,
        birth_date: formBirthDate || null,
        unit_id: formUnitId || null,
        status: formStatus,
        origin: formOrigin.trim() || null,
        operational_notes: formNotes.trim(),
        tags: splitTags(formTags),
      }),
    onSuccess: () => {
      toast.success("Paciente cadastrado com sucesso.");
      resetForm();
      setCreateDrawerOpen(false);
      queryClient.invalidateQueries({ queryKey: ["patients-dataset"] });
    },
    onError: () => toast.error("Nao foi possivel cadastrar o paciente."),
  });

  const updatePatientMutation = useMutation({
    mutationFn: async (patientId: string) =>
      api.patch(`/patients/${patientId}`, {
        full_name: formName.trim(),
        phone: formPhone.trim(),
        email: formEmail.trim() || null,
        cpf: formCpf.trim() || null,
        birth_date: formBirthDate || null,
        operational_notes: formNotes.trim(),
        status: formStatus,
        origin: formOrigin.trim() || null,
        unit_id: formUnitId || null,
        tags: splitTags(formTags),
      }),
    onSuccess: () => {
      toast.success("Paciente atualizado com sucesso.");
      setEditDrawerOpen(false);
      queryClient.invalidateQueries({ queryKey: ["patients-dataset"] });
    },
    onError: () => toast.error("Nao foi possivel atualizar o paciente."),
  });

  const deletePatientMutation = useMutation({
    mutationFn: async (patientId: string) => api.delete(`/patients/${patientId}`),
    onSuccess: () => {
      toast.success("Paciente excluido com sucesso.");
      setDeleteConfirmOpen(false);
      setDetailsDrawerOpen(false);
      setSelectedPatientId(null);
      queryClient.invalidateQueries({ queryKey: ["patients-dataset"] });
    },
    onError: () => toast.error("Nao foi possivel excluir o paciente."),
  });

  const dataset = patientsQuery.data ?? {
    patients: [],
    units: [],
    appointments: [],
    conversations: [],
    documents: [],
    professionals: [],
  };

  const visibleUnits =
    ownerUnitScope.canSwitchUnits && ownerUnitScope.selectedUnitId !== "all"
      ? dataset.units.filter((unit) => unit.id === ownerUnitScope.selectedUnitId)
      : dataset.units;
  const currentUserPermissions = sessionQuery.data?.resolved_page_permissions;
  const canCreatePatients = canAccessPage(currentUserPermissions, "pacientes", "create");
  const canEditPatients = canAccessPage(currentUserPermissions, "pacientes", "edit");
  const canDeletePatients = canAccessPage(currentUserPermissions, "pacientes", "delete");

  useEffect(() => {
    if (ownerUnitScope.canSwitchUnits) {
      setUnitFilter(ownerUnitScope.selectedUnitId);
      if (ownerUnitScope.selectedUnitId !== "all") {
        setFormUnitId((current) => current || ownerUnitScope.selectedUnitId);
      } else {
        setFormUnitId("");
      }
      return;
    }
    setUnitFilter(ownerUnitScope.selectedUnitId);
    if (ownerUnitScope.selectedUnitId !== "all") {
      setFormUnitId(ownerUnitScope.selectedUnitId);
    }
  }, [ownerUnitScope.canSwitchUnits, ownerUnitScope.selectedUnitId]);

  const unitsById = new Map(dataset.units.map((item) => [item.id, item.name]));
  const professionalsById = new Map(dataset.professionals.map((item) => [item.id, item.full_name]));
  const latestAppointmentByPatient = useMemo(() => {
    const map = new Map<string, AppointmentItem>();
    const sortedAppointments = [...dataset.appointments].sort(
      (a, b) => new Date(b.starts_at).getTime() - new Date(a.starts_at).getTime(),
    );

    for (const appointment of sortedAppointments) {
      if (!map.has(appointment.patient_id)) {
        map.set(appointment.patient_id, appointment);
      }
    }

    return map;
  }, [dataset.appointments]);

  const availableTags = Array.from(new Set(dataset.patients.flatMap((patient) => patient.tags_cache || []))).sort();
  const unassignedPatientsCount = dataset.patients.filter((patient) => {
    const resolvedUnitId = patient.unit_id ?? latestAppointmentByPatient.get(patient.id)?.unit_id ?? null;
    return !resolvedUnitId;
  }).length;

  const patientRows = dataset.patients
    .filter((patient) => {
      const term = search.toLowerCase().trim();
      const haystack = `${patient.full_name} ${patient.phone} ${patient.cpf ?? ""} ${patient.email ?? ""}`.toLowerCase();
      const bySearch = !term || haystack.includes(term);
      const byStatus = statusFilter === "all" || patient.status === statusFilter;
      const resolvedUnitId = patient.unit_id ?? latestAppointmentByPatient.get(patient.id)?.unit_id ?? null;
      const byUnit =
        unitFilter === "all" ||
        (unitFilter === UNASSIGNED_UNIT_FILTER ? !resolvedUnitId : resolvedUnitId === unitFilter);
      const byTag = tagFilter === "all" || (patient.tags_cache ?? []).includes(tagFilter);
      return bySearch && byStatus && byUnit && byTag;
    })
    .map((patient) => {
      const patientAppointments = dataset.appointments
        .filter((item) => item.patient_id === patient.id)
        .sort((a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime());
      const patientConversations = dataset.conversations
        .filter((item) => item.patient_id === patient.id)
        .sort(
          (a, b) => new Date(b.last_message_at || 0).getTime() - new Date(a.last_message_at || 0).getTime(),
        );
      const patientDocuments = dataset.documents.filter((item) => item.patient_id === patient.id);
      const nextAppointment = patientAppointments.find((item) => new Date(item.starts_at) >= new Date());
      const latestAppointment = latestAppointmentByPatient.get(patient.id) ?? null;
      const lastConversation = patientConversations[0];
      const resolvedUnitId = patient.unit_id ?? latestAppointment?.unit_id ?? null;
      const lastProfessionalName =
        latestAppointment?.professional_id
          ? professionalsById.get(latestAppointment.professional_id) ?? "Nao definido"
          : "Nao definido";

      return {
        ...patient,
        resolved_unit_id: resolvedUnitId,
        unit_name: resolvedUnitId ? unitsById.get(resolvedUnitId) ?? "Unidade nao identificada" : "Nao definida",
        next_appointment: nextAppointment?.starts_at ?? null,
        last_interaction: lastConversation?.last_message_at ?? null,
        last_professional_name: lastProfessionalName,
        appointment_count: patientAppointments.length,
        conversation_count: patientConversations.length,
        document_count: patientDocuments.length,
      };
    });

  const selectedPatient = useMemo(
    () => (selectedPatientId ? patientRows.find((item) => item.id === selectedPatientId) ?? null : null),
    [patientRows, selectedPatientId],
  );

  const selectedPatientAppointments = useMemo(
    () =>
      selectedPatient
        ? dataset.appointments
            .filter((item) => item.patient_id === selectedPatient.id)
            .sort((a, b) => new Date(b.starts_at).getTime() - new Date(a.starts_at).getTime())
        : [],
    [dataset.appointments, selectedPatient],
  );

  const selectedPatientConversations = useMemo(
    () =>
      selectedPatient
        ? dataset.conversations
            .filter((item) => item.patient_id === selectedPatient.id)
            .sort((a, b) => new Date(b.last_message_at || 0).getTime() - new Date(a.last_message_at || 0).getTime())
        : [],
    [dataset.conversations, selectedPatient],
  );

  const selectedPatientDocuments = useMemo(
    () =>
      selectedPatient
        ? dataset.documents
            .filter((item) => item.patient_id === selectedPatient.id)
            .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
        : [],
    [dataset.documents, selectedPatient],
  );
  const selectedPatientLatestAppointment = selectedPatientAppointments[0] ?? null;
  const selectedPatientLatestProfessionalName =
    selectedPatientLatestAppointment?.professional_id
      ? professionalsById.get(selectedPatientLatestAppointment.professional_id) ?? "Nao definido"
      : "Nao definido";

  const selectedPatientHistory = useMemo(() => {
    if (!selectedPatient) return [];

    const historyItems = [
      {
        date: selectedPatient.created_at,
        title: "Paciente cadastrado",
        description: selectedPatient.origin || "Origem nao informada",
      },
      ...selectedPatientAppointments.map((appointment) => ({
        date: appointment.starts_at,
        title: isEvaluationProcedure(appointment.procedure_type) ? "Avaliacao registrada" : "Procedimento registrado",
        description: `${appointment.procedure_type} • ${appointment.status} • ${appointment.confirmation_status}`,
      })),
      ...selectedPatientConversations.map((conversation) => ({
        date: conversation.last_message_at || null,
        title: "Conversa registrada",
        description: `${conversation.channel} • ${conversation.status}`,
      })),
      ...selectedPatientDocuments.map((document) => ({
        date: document.created_at,
        title: "Documento vinculado",
        description: `${document.title} • ${document.document_type}`,
      })),
    ].filter((item): item is { date: string; title: string; description: string } => Boolean(item.date));

    return historyItems.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
  }, [selectedPatient, selectedPatientAppointments, selectedPatientConversations, selectedPatientDocuments]);

  const populateFormFromPatient = (patient: PatientItem | null) => {
    if (!patient) return;
    setFormName(patient.full_name || "");
    setFormPhone(patient.phone || "");
    setFormCpf(patient.cpf || "");
    setFormEmail(patient.email || "");
    setFormBirthDate(patient.birth_date || "");
    setFormUnitId(patient.unit_id || "");
    setFormTags((patient.tags_cache || []).join(", "));
    setFormStatus(patient.status || "ativo");
    setFormOrigin(patient.origin || "");
    setFormNotes(patient.operational_notes || "");
  };

  if (patientsQuery.isLoading) return <LoadingState message="Carregando CRM de pacientes..." />;
  if (patientsQuery.isError || !patientsQuery.data) {
    return <ErrorState message="Nao foi possivel carregar os pacientes." />;
  }

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="CRM"
        title="Pacientes"
        description="Visao central do paciente com historico de agenda, conversas, documentos e observacoes clinicas."
        actions={canCreatePatients ? (
          <Button
            className="gap-2"
            onClick={() => {
              resetForm();
              setCreateDrawerOpen(true);
            }}
          >
            <UserPlus size={16} />
            Novo paciente
          </Button>
        ) : undefined}
      />

      <FilterBar search={search} onSearchChange={setSearch} searchPlaceholder="Buscar por nome, telefone, CPF ou e-mail...">
        <select
          className="h-9 rounded-md border border-stone-300 bg-white px-2 text-sm"
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value)}
        >
          <option value="all">Todos os status</option>
          <option value="ativo">Ativo</option>
          <option value="inativo">Inativo</option>
        </select>
        <select
          className="h-9 rounded-md border border-stone-300 bg-white px-2 text-sm"
          value={unitFilter}
          onChange={(event) => {
            const nextValue = event.target.value;
            setUnitFilter(nextValue);
            if (ownerUnitScope.canSwitchUnits) {
              ownerUnitScope.setSelectedUnitId(nextValue);
            }
          }}
        >
          <option value="all">Todas as unidades</option>
          {visibleUnits.map((unit) => (
            <option key={unit.id} value={unit.id}>
              {unit.name}
            </option>
          ))}
          <option value={UNASSIGNED_UNIT_FILTER}>Sem unidade definida</option>
        </select>
        <select
          className="h-9 rounded-md border border-stone-300 bg-white px-2 text-sm"
          value={tagFilter}
          onChange={(event) => setTagFilter(event.target.value)}
        >
          <option value="all">Todas as tags</option>
          {availableTags.map((tag) => (
            <option key={tag} value={tag}>
              {tag}
            </option>
          ))}
        </select>
      </FilterBar>

      {ownerUnitScope.canSwitchUnits && unassignedPatientsCount ? (
        <Card className="border-amber-200 bg-amber-50/80">
          <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
            <div>
              <p className="text-sm font-semibold text-amber-900">Pacientes sem unidade definida</p>
              <p className="text-sm text-amber-800">
                {unassignedPatientsCount} paciente(s) ainda estao sem unidade vinculada no cadastro.
                Quando voce filtra por uma unidade especifica, eles nao aparecem nessa lista.
              </p>
            </div>
            <Button
              variant="outline"
              className="border-amber-300 bg-white text-amber-900 hover:bg-amber-100"
              onClick={() => setUnitFilter(UNASSIGNED_UNIT_FILTER)}
            >
              Ver pacientes sem unidade
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <DataTable<(typeof patientRows)[number]>
        title="Base de pacientes"
        rows={patientRows}
        getRowId={(item) => item.id}
        searchBy={(item) => `${item.full_name} ${item.phone} ${item.cpf ?? ""} ${item.email ?? ""} ${item.unit_name}`}
        columns={[
          {
            key: "nome",
            label: "Paciente",
            render: (item) => (
              <button
                type="button"
                className="text-left"
                onClick={() => {
                  setSelectedPatientId(item.id);
                  setDetailsTab("resumo");
                  setDeleteConfirmOpen(false);
                  setDetailsDrawerOpen(true);
                }}
              >
                <p className="font-semibold text-stone-800 hover:text-primary">{item.full_name}</p>
                <p className="text-xs text-stone-500">{item.origin || "Origem nao informada"}</p>
              </button>
            ),
          },
          {
            key: "telefone",
            label: "Contato",
            render: (item) => (
              <div>
                <p className="text-sm text-stone-800">{formatPhoneBR(item.phone)}</p>
                <p className="text-xs text-stone-500">{item.email || "-"}</p>
              </div>
            ),
          },
          {
            key: "cpf",
            label: "CPF",
            render: (item) => formatCpfBR(item.cpf),
          },
          {
            key: "status",
            label: "Status",
            render: (item) => <StatusBadge value={item.status} />,
          },
          {
            key: "relacionamento",
            label: "Relacionamento",
            render: (item) => (
              <div className="space-y-1 text-xs text-stone-600">
                <p>{item.appointment_count} agendamento(s)</p>
                <p>{item.conversation_count} conversa(s)</p>
                <p>{item.document_count} documento(s)</p>
              </div>
            ),
          },
          {
            key: "proxima_consulta",
            label: "Proxima consulta",
            render: (item) => formatDateTimeBR(item.next_appointment),
          },
          {
            key: "unidade",
            label: "Unidade",
            render: (item) => item.unit_name,
          },
          {
            key: "acoes",
            label: "Acoes",
            render: (item) => (
              <div className="flex flex-wrap gap-1">
                <Button
                  variant="outline"
                  className="h-8 px-2 text-xs"
                  onClick={() => {
                    setSelectedPatientId(item.id);
                    setDetailsTab("resumo");
                    setDeleteConfirmOpen(false);
                    setDetailsDrawerOpen(true);
                  }}
                >
                  Visualizar
                </Button>
                <Button
                  variant="outline"
                  className="h-8 px-2 text-xs"
                  onClick={() => {
                    setSelectedPatientId(item.id);
                    populateFormFromPatient(item);
                    setEditDrawerOpen(true);
                  }}
                  disabled={!canEditPatients}
                >
                  Editar
                </Button>
                <Button
                  variant="destructive"
                  className="h-8 px-2 text-xs"
                  onClick={() => {
                    setSelectedPatientId(item.id);
                    setDeleteConfirmOpen(true);
                    setDetailsDrawerOpen(true);
                    setDetailsTab("resumo");
                  }}
                  disabled={!canDeletePatients}
                >
                  Excluir
                </Button>
              </div>
            ),
          },
        ]}
        emptyTitle="Sem pacientes no filtro"
        emptyDescription={
          unitFilter !== "all"
            ? "Esse filtro de unidade pode estar escondendo pacientes sem unidade definida. Ajuste o filtro acima para conferir."
            : "Tente ajustar os filtros ou cadastre um novo paciente."
        }
      />

      <RightDrawer
        open={detailsDrawerOpen}
        onOpenChange={(open) => {
          setDetailsDrawerOpen(open);
          if (!open) {
            setDeleteConfirmOpen(false);
          }
        }}
        title={selectedPatient ? selectedPatient.full_name : "Detalhe do paciente"}
        description="Card completo do paciente com dados de cadastro, procedimentos, avaliacoes, agenda, documentos e acoes."
      >
        {selectedPatient ? (
          <div className="space-y-3">
            <Card className="border-stone-200 bg-white/95">
              <CardContent className="space-y-4 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="space-y-1">
                    <p className="text-lg font-semibold text-stone-900">{selectedPatient.full_name}</p>
                    <p className="text-sm text-stone-600">{formatPhoneBR(selectedPatient.phone)}</p>
                    <p className="text-sm text-stone-600">{selectedPatient.email || "Sem e-mail cadastrado"}</p>
                    <p className="text-sm text-stone-600">CPF: {formatCpfBR(selectedPatient.cpf)}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      className="gap-2"
                      onClick={() => {
                        populateFormFromPatient(selectedPatient);
                        setEditDrawerOpen(true);
                      }}
                      disabled={!canEditPatients}
                    >
                      <Pencil size={14} />
                      Editar
                    </Button>
                    <Button
                      variant="destructive"
                      className="gap-2"
                      onClick={() => setDeleteConfirmOpen(true)}
                      disabled={!canDeletePatients}
                    >
                      <Trash2 size={14} />
                      Excluir paciente
                    </Button>
                    <Button variant="outline" className="gap-2" onClick={() => setDetailsDrawerOpen(false)}>
                      <X size={14} />
                      Fechar
                    </Button>
                  </div>
                </div>

                <div className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-xl border border-stone-200 bg-stone-50 p-3">
                    <p className="field-label">Cadastro</p>
                    <p className="text-sm text-stone-700">Nascimento: {formatDateBR(selectedPatient.birth_date)}</p>
                    <p className="text-sm text-stone-700">Criado em: {formatDateTimeBR(selectedPatient.created_at)}</p>
                    <p className="text-sm text-stone-700">Origem: {selectedPatient.origin || "Nao informada"}</p>
                    <p className="text-sm text-stone-700">Unidade: {selectedPatient.unit_name}</p>
                    <p className="text-sm text-stone-700">Profissional mais recente: {selectedPatient.last_professional_name}</p>
                  </div>
                  <div className="rounded-xl border border-stone-200 bg-stone-50 p-3">
                    <p className="field-label">Relacionamento</p>
                    <div className="mt-1 flex flex-wrap gap-2">
                      <StatusBadge value={selectedPatient.status} />
                      <Badge className="bg-stone-200 text-stone-700">
                        {selectedPatient.marketing_opt_in ? "Marketing liberado" : "Marketing bloqueado"}
                      </Badge>
                      <Badge className="bg-stone-200 text-stone-700">
                        {selectedPatient.lgpd_consent ? "LGPD ok" : "LGPD pendente"}
                      </Badge>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-1">
                      {(selectedPatient.tags_cache || []).length ? (
                        selectedPatient.tags_cache.map((tag) => (
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

                {deleteConfirmOpen ? (
                  <Card className="border-rose-200 bg-rose-50">
                    <CardContent className="space-y-3 p-4">
                      <div>
                        <p className="text-sm font-semibold text-rose-900">Confirmar exclusao do paciente</p>
                        <p className="text-sm text-rose-700">
                          Esse paciente sera removido da base visivel, mas o historico relacionado continuara preservado para auditoria.
                        </p>
                      </div>
                      <div className="grid gap-2 sm:grid-cols-3">
                        <div className="rounded-lg border border-rose-200 bg-white p-3 text-sm text-stone-700">
                          {selectedPatientAppointments.length} agendamento(s)
                        </div>
                        <div className="rounded-lg border border-rose-200 bg-white p-3 text-sm text-stone-700">
                          {selectedPatientConversations.length} conversa(s)
                        </div>
                        <div className="rounded-lg border border-rose-200 bg-white p-3 text-sm text-stone-700">
                          {selectedPatientDocuments.length} documento(s)
                        </div>
                      </div>
                      <div className="flex flex-wrap justify-end gap-2">
                        <Button variant="outline" onClick={() => setDeleteConfirmOpen(false)}>
                          Cancelar
                        </Button>
                        <Button
                          variant="destructive"
                          onClick={() => deletePatientMutation.mutate(selectedPatient.id)}
                          disabled={deletePatientMutation.isPending || !canDeletePatients}
                        >
                          {deletePatientMutation.isPending ? "Excluindo..." : "Confirmar exclusao"}
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                ) : null}
              </CardContent>
            </Card>

            <div className="flex flex-wrap gap-2">
              {PATIENT_DETAIL_TABS.map((tab) => (
                <Button
                  key={tab.id}
                  variant={detailsTab === tab.id ? "default" : "outline"}
                  className="h-8 text-xs"
                  onClick={() => setDetailsTab(tab.id)}
                >
                  {tab.label}
                </Button>
              ))}
            </div>

            {detailsTab === "resumo" ? (
              <Card className="border-stone-200">
                <CardContent className="grid gap-3 p-4 sm:grid-cols-2">
                  <div className="rounded-xl border border-stone-200 bg-stone-50 p-3">
                    <p className="field-label">Ultima interacao</p>
                    <p className="text-sm font-semibold text-stone-800">{formatDateTimeBR(selectedPatient.last_interaction)}</p>
                  </div>
                  <div className="rounded-xl border border-stone-200 bg-stone-50 p-3">
                    <p className="field-label">Proxima consulta</p>
                    <p className="text-sm font-semibold text-stone-800">{formatDateTimeBR(selectedPatient.next_appointment)}</p>
                  </div>
                  <div className="rounded-xl border border-stone-200 bg-stone-50 p-3">
                    <p className="field-label">Ultimo profissional</p>
                    <p className="text-sm font-semibold text-stone-800">{selectedPatientLatestProfessionalName}</p>
                  </div>
                  <div className="rounded-xl border border-stone-200 bg-stone-50 p-3">
                    <p className="field-label">Ultima unidade com agenda</p>
                    <p className="text-sm font-semibold text-stone-800">{selectedPatient.unit_name}</p>
                  </div>
                  <div className="rounded-xl border border-stone-200 bg-stone-50 p-3 sm:col-span-2">
                    <p className="field-label">Observacoes clinicas e operacionais</p>
                    <p className="text-sm text-stone-700">
                      {selectedPatient.operational_notes?.trim() || "Sem observacoes salvas para este paciente."}
                    </p>
                  </div>
                </CardContent>
              </Card>
            ) : null}

            {detailsTab === "procedimentos" ? (
              <Card className="border-stone-200">
                <CardContent className="space-y-3 p-4">
                  {selectedPatientAppointments.length ? (
                    selectedPatientAppointments.map((appointment) => (
                      <div key={appointment.id} className="rounded-xl border border-stone-200 bg-stone-50 p-3">
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <div>
                            <div className="flex flex-wrap gap-2">
                              <p className="text-sm font-semibold text-stone-900">{appointment.procedure_type}</p>
                              {isEvaluationProcedure(appointment.procedure_type) ? (
                                <Badge className="bg-sky-100 text-sky-800">Avaliacao</Badge>
                              ) : null}
                            </div>
                            <p className="mt-1 text-xs text-stone-600">{formatDateTimeBR(appointment.starts_at)}</p>
                            <p className="mt-1 text-xs text-stone-600">
                              Profissional:{" "}
                              {appointment.professional_id
                                ? professionalsById.get(appointment.professional_id) ?? "Nao definido"
                                : "Nao definido"}
                            </p>
                          </div>
                          <div className="flex flex-wrap gap-1">
                            <StatusBadge value={appointment.status} />
                            <StatusBadge value={appointment.confirmation_status} />
                          </div>
                        </div>
                        <div className="mt-3 rounded-lg border border-stone-200 bg-white p-3 text-sm text-stone-700">
                          {appointment.notes?.trim() || "Sem observacoes registradas pelo medico/equipe."}
                        </div>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-stone-500">Nenhum procedimento ou avaliacao vinculado ao paciente.</p>
                  )}
                </CardContent>
              </Card>
            ) : null}

            {detailsTab === "conversas" ? (
              <Card className="border-stone-200">
                <CardContent className="space-y-3 p-4">
                  {selectedPatientConversations.length ? (
                    selectedPatientConversations.map((conversation) => (
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

            {detailsTab === "documentos" ? (
              <Card className="border-stone-200">
                <CardContent className="space-y-3 p-4">
                  {selectedPatientDocuments.length ? (
                    selectedPatientDocuments.map((document) => (
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

            {detailsTab === "historico" ? (
              <Card className="border-stone-200">
                <CardContent className="space-y-3 p-4">
                  {selectedPatientHistory.length ? (
                    selectedPatientHistory.map((event, index) => (
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
          </div>
        ) : (
          <p className="text-sm text-stone-500">Selecione um paciente para abrir o detalhe.</p>
        )}
      </RightDrawer>

      <RightDrawer
        open={createDrawerOpen}
        onOpenChange={setCreateDrawerOpen}
        title="Novo paciente"
        description="Cadastro completo do paciente com CPF, nascimento, tags e observacoes clinicas."
      >
        {canCreatePatients ? (
        <Card className="border-stone-200">
          <CardContent className="space-y-3 p-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <label className="field-label">Nome completo do paciente</label>
                <Input placeholder="Ex.: Maria da Silva" value={formName} onChange={(event) => setFormName(event.target.value)} />
              </div>
              <div className="space-y-1.5">
                <label className="field-label">Telefone principal</label>
                <Input placeholder="Ex.: (11) 99999-9999" value={formPhone} onChange={(event) => setFormPhone(event.target.value)} />
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <label className="field-label">CPF</label>
                <Input placeholder="Opcional" value={formCpf} onChange={(event) => setFormCpf(event.target.value)} />
              </div>
              <div className="space-y-1.5">
                <label className="field-label">E-mail</label>
                <Input placeholder="Opcional" value={formEmail} onChange={(event) => setFormEmail(event.target.value)} />
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <label className="field-label">Data de nascimento</label>
                <Input type="date" value={formBirthDate} onChange={(event) => setFormBirthDate(event.target.value)} />
              </div>
              <div className="space-y-1.5">
                <label className="field-label">Status do cadastro</label>
                <select
                  className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                  value={formStatus}
                  onChange={(event) => setFormStatus(event.target.value)}
                >
                  <option value="ativo">Ativo</option>
                  <option value="inativo">Inativo</option>
                </select>
              </div>
            </div>
            <div className="space-y-1.5">
              <label className="field-label">Unidade de referencia</label>
              <select
                className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                value={formUnitId}
                onChange={(event) => setFormUnitId(event.target.value)}
              >
                <option value="">Selecionar unidade (opcional)</option>
                {visibleUnits.map((unit) => (
                  <option key={unit.id} value={unit.id}>
                    {unit.name}
                  </option>
                ))}
              </select>
              <p className="text-xs text-stone-500">Use esse campo para o paciente aparecer nos filtros da unidade correta.</p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <label className="field-label">Origem do paciente</label>
                <Input placeholder="Ex.: WhatsApp, recepcao, indicacao" value={formOrigin} onChange={(event) => setFormOrigin(event.target.value)} />
              </div>
              <div className="space-y-1.5">
                <label className="field-label">Tags do CRM</label>
                <Input placeholder="Separadas por virgula" value={formTags} onChange={(event) => setFormTags(event.target.value)} />
              </div>
            </div>
            <div className="space-y-1.5">
              <label className="field-label">Observacoes clinicas e operacionais</label>
              <textarea
                className="min-h-[120px] w-full rounded-lg border border-stone-300 bg-white p-3 text-sm"
                placeholder="Ex.: alergias, preferencia de atendimento, observacoes internas."
                value={formNotes}
                onChange={(event) => setFormNotes(event.target.value)}
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                onClick={() => {
                  setCreateDrawerOpen(false);
                  resetForm();
                }}
              >
                Cancelar
              </Button>
              <Button
                onClick={() => {
                  if (!formName.trim() || !formPhone.trim()) {
                    toast.error("Preencha nome e telefone para cadastrar.");
                    return;
                  }
                  createPatientMutation.mutate();
                }}
                disabled={createPatientMutation.isPending || !canCreatePatients}
              >
                {createPatientMutation.isPending ? "Salvando..." : "Salvar paciente"}
              </Button>
            </div>
          </CardContent>
        </Card>
        ) : (
          <p className="text-sm text-stone-500">Seu perfil atual nao pode cadastrar pacientes.</p>
        )}
      </RightDrawer>

      <RightDrawer
        open={editDrawerOpen}
        onOpenChange={setEditDrawerOpen}
        title={selectedPatient ? `Editar ${selectedPatient.full_name}` : "Editar paciente"}
        description="Atualize os dados do paciente e salve as alteracoes."
      >
        {selectedPatient ? (
          <Card className="border-stone-200">
            <CardContent className="space-y-3 p-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <label className="field-label">Nome completo do paciente</label>
                  <Input placeholder="Ex.: Maria da Silva" value={formName} onChange={(event) => setFormName(event.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <label className="field-label">Telefone principal</label>
                  <Input placeholder="Ex.: (11) 99999-9999" value={formPhone} onChange={(event) => setFormPhone(event.target.value)} />
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <label className="field-label">CPF</label>
                  <Input placeholder="Opcional" value={formCpf} onChange={(event) => setFormCpf(event.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <label className="field-label">E-mail</label>
                  <Input placeholder="Opcional" value={formEmail} onChange={(event) => setFormEmail(event.target.value)} />
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <label className="field-label">Data de nascimento</label>
                  <Input type="date" value={formBirthDate} onChange={(event) => setFormBirthDate(event.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <label className="field-label">Status do cadastro</label>
                  <select
                    className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                    value={formStatus}
                    onChange={(event) => setFormStatus(event.target.value)}
                  >
                    <option value="ativo">Ativo</option>
                    <option value="inativo">Inativo</option>
                  </select>
                </div>
              </div>
              <div className="space-y-1.5">
                <label className="field-label">Unidade de referencia</label>
                <select
                  className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                  value={formUnitId}
                  onChange={(event) => setFormUnitId(event.target.value)}
                >
                  <option value="">Sem unidade definida</option>
                  {dataset.units.map((unit) => (
                    <option key={unit.id} value={unit.id}>
                      {unit.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <label className="field-label">Origem do paciente</label>
                  <Input placeholder="Ex.: WhatsApp, recepcao, indicacao" value={formOrigin} onChange={(event) => setFormOrigin(event.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <label className="field-label">Tags do CRM</label>
                  <Input placeholder="Separadas por virgula" value={formTags} onChange={(event) => setFormTags(event.target.value)} />
                </div>
              </div>
              <div className="space-y-1.5">
                <label className="field-label">Observacoes clinicas e operacionais</label>
                <textarea
                  className="min-h-[120px] w-full rounded-lg border border-stone-300 bg-white p-3 text-sm"
                  placeholder="Ex.: alergias, preferencia de atendimento, observacoes internas."
                  value={formNotes}
                  onChange={(event) => setFormNotes(event.target.value)}
                />
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setEditDrawerOpen(false)}>
                  Cancelar
                </Button>
              <Button
                onClick={() => updatePatientMutation.mutate(selectedPatient.id)}
                disabled={updatePatientMutation.isPending || !canEditPatients}
              >
                  {updatePatientMutation.isPending ? "Salvando..." : "Salvar alteracoes"}
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : (
          <p className="text-sm text-stone-500">Selecione um paciente para editar.</p>
        )}
      </RightDrawer>
    </div>
  );
}

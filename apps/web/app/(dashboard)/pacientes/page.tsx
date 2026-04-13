"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { UserPlus } from "lucide-react";
import { toast } from "sonner";

import { DataTable, FilterBar, PageHeader, RightDrawer, StatusBadge } from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { api } from "@/lib/api";
import {
  ApiPage,
  AppointmentItem,
  ConversationItem,
  DocumentItem,
  PatientItem,
  UnitItem,
} from "@/lib/domain-types";
import { formatDateBR, formatDateTimeBR, formatPhoneBR } from "@/lib/formatters";
import { Badge, Button, Card, CardContent, Input } from "@odontoflux/ui";

type PatientsDataset = {
  patients: PatientItem[];
  units: UnitItem[];
  appointments: AppointmentItem[];
  conversations: ConversationItem[];
  documents: DocumentItem[];
};

type PatientDetailTab =
  | "visao-geral"
  | "conversas"
  | "agenda"
  | "documentos"
  | "consentimentos"
  | "historico-operacional";

const PATIENT_DETAIL_TABS: { id: PatientDetailTab; label: string }[] = [
  { id: "visao-geral", label: "Visão geral" },
  { id: "conversas", label: "Conversas" },
  { id: "agenda", label: "Agenda" },
  { id: "documentos", label: "Documentos" },
  { id: "consentimentos", label: "Consentimentos" },
  { id: "historico-operacional", label: "Histórico operacional" },
];

export default function PacientesPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [unitFilter, setUnitFilter] = useState("all");
  const [tagFilter, setTagFilter] = useState("all");
  const [openDrawer, setOpenDrawer] = useState(false);
  const [detailsDrawerOpen, setDetailsDrawerOpen] = useState(false);
  const [detailsTab, setDetailsTab] = useState<PatientDetailTab>("visao-geral");
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null);

  const [newName, setNewName] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newUnitId, setNewUnitId] = useState("");
  const [newTags, setNewTags] = useState("");

  const patientsQuery = useQuery<PatientsDataset>({
    queryKey: ["patients-dataset"],
    queryFn: async () => {
      const [patientsResponse, unitsResponse, appointmentsResponse, conversationsResponse, documentsResponse] = await Promise.all([
        api.get<ApiPage<PatientItem>>("/patients", { params: { limit: 200, offset: 0 } }),
        api.get<ApiPage<UnitItem>>("/units", { params: { limit: 100, offset: 0 } }),
        api.get<ApiPage<AppointmentItem>>("/appointments", { params: { limit: 200, offset: 0 } }),
        api.get<ApiPage<ConversationItem>>("/conversations", { params: { limit: 200, offset: 0 } }),
        api.get<ApiPage<DocumentItem>>("/documents", { params: { limit: 200, offset: 0 } }),
      ]);

      return {
        patients: patientsResponse.data.data ?? [],
        units: unitsResponse.data.data ?? [],
        appointments: appointmentsResponse.data.data ?? [],
        conversations: conversationsResponse.data.data ?? [],
        documents: documentsResponse.data.data ?? [],
      };
    },
  });

  const createPatientMutation = useMutation({
    mutationFn: async () =>
      api.post("/patients", {
        full_name: newName,
        phone: newPhone,
        email: newEmail || null,
        unit_id: newUnitId || null,
        status: "ativo",
        tags: newTags
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
      }),
    onSuccess: () => {
      toast.success("Paciente cadastrado com sucesso.");
      setNewName("");
      setNewPhone("");
      setNewEmail("");
      setNewUnitId("");
      setNewTags("");
      setOpenDrawer(false);
      queryClient.invalidateQueries({ queryKey: ["patients-dataset"] });
    },
    onError: () => toast.error("Não foi possível cadastrar o paciente."),
  });

  const dataset = patientsQuery.data ?? {
    patients: [],
    units: [],
    appointments: [],
    conversations: [],
    documents: [],
  };
  const unitsById = new Map(dataset.units.map((item) => [item.id, item.name]));

  const availableTags = Array.from(
    new Set(dataset.patients.flatMap((patient) => patient.tags_cache || [])),
  ).sort();

  const patientRows = dataset.patients
    .filter((patient) => {
      const term = search.toLowerCase().trim();
      const haystack = `${patient.full_name} ${patient.phone} ${patient.email ?? ""}`.toLowerCase();
      const bySearch = !term || haystack.includes(term);
      const byStatus = statusFilter === "all" || patient.status === statusFilter;
      const byUnit = unitFilter === "all" || patient.unit_id === unitFilter;
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
          (a, b) =>
            new Date(b.last_message_at || 0).getTime() - new Date(a.last_message_at || 0).getTime(),
        );

      const nextAppointment = patientAppointments.find((item) => new Date(item.starts_at) >= new Date());
      const lastConversation = patientConversations[0];

      return {
        ...patient,
        unit_name: patient.unit_id ? unitsById.get(patient.unit_id) ?? "Unidade não identificada" : "Não definida",
        next_appointment: nextAppointment?.starts_at ?? null,
        last_interaction: lastConversation?.last_message_at ?? null,
      };
    });

  const selectedPatient = useMemo(
    () => (selectedPatientId ? patientRows.find((item) => item.id === selectedPatientId) ?? null : null),
    [patientRows, selectedPatientId],
  );

  const selectedPatientConversations = useMemo(
    () =>
      selectedPatient
        ? dataset.conversations
            .filter((item) => item.patient_id === selectedPatient.id)
            .sort(
              (a, b) =>
                new Date(b.last_message_at || 0).getTime() - new Date(a.last_message_at || 0).getTime(),
            )
        : [],
    [dataset.conversations, selectedPatient],
  );

  const selectedPatientAppointments = useMemo(
    () =>
      selectedPatient
        ? dataset.appointments
            .filter((item) => item.patient_id === selectedPatient.id)
            .sort((a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime())
        : [],
    [dataset.appointments, selectedPatient],
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

  const consentDocuments = useMemo(
    () =>
      selectedPatientDocuments.filter((item) =>
        item.document_type.toLowerCase().includes("consent"),
      ),
    [selectedPatientDocuments],
  );

  const operationalHistory = useMemo(() => {
    if (!selectedPatient) return [];

    const conversationEvents = selectedPatientConversations.map((item) => ({
      date: item.last_message_at ?? "",
      title: "Interação registrada no inbox",
      description: `${item.channel} • ${item.status}`,
    }));

    const appointmentEvents = selectedPatientAppointments.map((item) => ({
      date: item.starts_at,
      title: "Movimento na agenda",
      description: `${item.procedure_type} • ${item.status} • ${item.confirmation_status}`,
    }));

    const documentEvents = selectedPatientDocuments.map((item) => ({
      date: item.created_at,
      title: "Documento vinculado",
      description: `${item.title} • ${item.document_type}`,
    }));

    return [
      {
        date: selectedPatient.created_at,
        title: "Paciente cadastrado no CRM",
        description: selectedPatient.origin ?? "Origem não informada",
      },
      ...conversationEvents,
      ...appointmentEvents,
      ...documentEvents,
    ]
      .filter((item) => Boolean(item.date))
      .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
  }, [selectedPatient, selectedPatientAppointments, selectedPatientConversations, selectedPatientDocuments]);

  if (patientsQuery.isLoading) return <LoadingState message="Carregando CRM de pacientes..." />;
  if (patientsQuery.isError || !patientsQuery.data) {
    return <ErrorState message="Não foi possível carregar os pacientes." />;
  }

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="CRM"
        title="Pacientes"
        description="Visão central de relacionamento, agenda e documentação clínica."
        actions={
          <Button className="gap-2" onClick={() => setOpenDrawer(true)}>
            <UserPlus size={16} />
            Novo paciente
          </Button>
        }
      />

      <FilterBar search={search} onSearchChange={setSearch} searchPlaceholder="Buscar por nome, telefone ou e-mail...">
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
          onChange={(event) => setUnitFilter(event.target.value)}
        >
          <option value="all">Todas as unidades</option>
          {dataset.units.map((unit) => (
            <option key={unit.id} value={unit.id}>
              {unit.name}
            </option>
          ))}
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

      <DataTable<(typeof patientRows)[number]>
        title="Base de pacientes"
        rows={patientRows}
        getRowId={(item) => item.id}
        searchBy={(item) => `${item.full_name} ${item.phone} ${item.email ?? ""} ${item.unit_name}`}
        columns={[
          {
            key: "nome",
            label: "Paciente",
            render: (item) => (
              <div>
                <p className="font-semibold text-stone-800">{item.full_name}</p>
                <p className="text-xs text-stone-500">{item.origin ?? "Origem não informada"}</p>
              </div>
            ),
          },
          {
            key: "telefone",
            label: "Telefone",
            render: (item) => formatPhoneBR(item.phone),
          },
          {
            key: "email",
            label: "E-mail",
            render: (item) => item.email || "-",
          },
          {
            key: "status",
            label: "Status",
            render: (item) => <StatusBadge value={item.status} />,
          },
          {
            key: "tags",
            label: "Tags",
            render: (item) =>
              item.tags_cache?.length ? (
                <div className="flex flex-wrap gap-1">
                  {item.tags_cache.map((tag) => (
                    <Badge key={tag} className="bg-stone-200 text-stone-700">
                      {tag}
                    </Badge>
                  ))}
                </div>
              ) : (
                "-"
              ),
          },
          {
            key: "ultima_interacao",
            label: "Última interação",
            render: (item) => formatDateTimeBR(item.last_interaction),
          },
          {
            key: "proxima_consulta",
            label: "Próxima consulta",
            render: (item) => formatDateTimeBR(item.next_appointment),
          },
          {
            key: "unidade",
            label: "Unidade",
            render: (item) => item.unit_name,
          },
          {
            key: "acoes",
            label: "Ações",
            render: (item) => (
              <div className="flex flex-wrap gap-1">
                <Button
                  variant="outline"
                  className="h-8 px-2 text-xs"
                  onClick={() => {
                    setSelectedPatientId(item.id);
                    setDetailsTab("visao-geral");
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
                    setDetailsTab("conversas");
                    setDetailsDrawerOpen(true);
                  }}
                >
                  Conversas
                </Button>
                <Button
                  variant="outline"
                  className="h-8 px-2 text-xs"
                  onClick={() => {
                    setSelectedPatientId(item.id);
                    setDetailsTab("documentos");
                    setDetailsDrawerOpen(true);
                  }}
                >
                  Documentos
                </Button>
                <Button
                  variant="outline"
                  className="h-8 px-2 text-xs"
                  onClick={() => {
                    setSelectedPatientId(item.id);
                    setDetailsTab("agenda");
                    setDetailsDrawerOpen(true);
                  }}
                >
                  Agenda
                </Button>
              </div>
            ),
          },
        ]}
        emptyTitle="Sem pacientes no filtro"
        emptyDescription="Tente ajustar os filtros ou cadastre um novo paciente."
      />

      <RightDrawer
        open={detailsDrawerOpen}
        onOpenChange={setDetailsDrawerOpen}
        title={selectedPatient ? selectedPatient.full_name : "Detalhe do paciente"}
        description="Visão 360° do paciente com contexto de atendimento, agenda e documentos."
      >
        {selectedPatient ? (
          <div className="space-y-3">
            <Card className="border-stone-200">
              <CardContent className="space-y-2 p-4">
                <p className="text-sm font-semibold text-stone-800">{selectedPatient.full_name}</p>
                <p className="text-xs text-stone-600">{formatPhoneBR(selectedPatient.phone)}</p>
                <p className="text-xs text-stone-600">{selectedPatient.email || "Sem e-mail cadastrado"}</p>
                <div className="flex flex-wrap gap-1">
                  <StatusBadge value={selectedPatient.status} />
                  <Badge className="bg-stone-200 text-stone-700">{selectedPatient.unit_name}</Badge>
                  {(selectedPatient.tags_cache ?? []).map((tag) => (
                    <Badge key={tag} className="bg-stone-200 text-stone-700">
                      {tag}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>

            <div className="flex flex-wrap gap-1">
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

            {detailsTab === "visao-geral" ? (
              <Card className="border-stone-200">
                <CardContent className="grid gap-3 p-4 sm:grid-cols-2">
                  <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Última interação</p>
                    <p className="mt-1 text-sm font-medium text-stone-800">
                      {formatDateTimeBR(selectedPatient.last_interaction)}
                    </p>
                  </div>
                  <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Próxima consulta</p>
                    <p className="mt-1 text-sm font-medium text-stone-800">
                      {formatDateTimeBR(selectedPatient.next_appointment)}
                    </p>
                  </div>
                  <div className="rounded-lg border border-stone-200 bg-stone-50 p-3 sm:col-span-2">
                    <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Origem e marketing</p>
                    <p className="mt-1 text-sm text-stone-700">
                      Origem: {selectedPatient.origin ?? "Não informada"} • Comunicação permitida:{" "}
                      {selectedPatient.marketing_opt_in ? "sim" : "não"}
                    </p>
                  </div>
                </CardContent>
              </Card>
            ) : null}

            {detailsTab === "conversas" ? (
              <Card className="border-stone-200">
                <CardContent className="space-y-2 p-4">
                  {selectedPatientConversations.length ? (
                    selectedPatientConversations.map((conversation) => (
                      <div key={conversation.id} className="rounded-lg border border-stone-200 p-2">
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-sm font-semibold text-stone-800">
                            {conversation.channel.toUpperCase()}
                          </p>
                          <StatusBadge value={conversation.status} />
                        </div>
                        <p className="mt-1 text-xs text-stone-600">{formatDateTimeBR(conversation.last_message_at)}</p>
                        <p className="mt-1 text-xs text-stone-600">
                          {conversation.ai_summary || "Sem resumo IA para esta conversa."}
                        </p>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-stone-500">Nenhuma conversa vinculada ao paciente.</p>
                  )}
                </CardContent>
              </Card>
            ) : null}

            {detailsTab === "agenda" ? (
              <Card className="border-stone-200">
                <CardContent className="space-y-2 p-4">
                  {selectedPatientAppointments.length ? (
                    selectedPatientAppointments.map((appointment) => (
                      <div key={appointment.id} className="rounded-lg border border-stone-200 p-2">
                        <p className="text-sm font-semibold text-stone-800">{appointment.procedure_type}</p>
                        <p className="text-xs text-stone-600">{formatDateTimeBR(appointment.starts_at)}</p>
                        <div className="mt-1 flex items-center gap-2">
                          <StatusBadge value={appointment.status} />
                          <StatusBadge value={appointment.confirmation_status} />
                        </div>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-stone-500">Nenhuma consulta vinculada ao paciente.</p>
                  )}
                </CardContent>
              </Card>
            ) : null}

            {detailsTab === "documentos" ? (
              <Card className="border-stone-200">
                <CardContent className="space-y-2 p-4">
                  {selectedPatientDocuments.length ? (
                    selectedPatientDocuments.map((document) => (
                      <div key={document.id} className="rounded-lg border border-stone-200 p-2">
                        <p className="text-sm font-semibold text-stone-800">{document.title}</p>
                        <p className="text-xs text-stone-600">{document.document_type}</p>
                        <p className="text-xs text-stone-500">{formatDateBR(document.created_at)}</p>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-stone-500">Sem documentos operacionais vinculados.</p>
                  )}
                </CardContent>
              </Card>
            ) : null}

            {detailsTab === "consentimentos" ? (
              <Card className="border-stone-200">
                <CardContent className="space-y-2 p-4">
                  {consentDocuments.length ? (
                    consentDocuments.map((document) => (
                      <div key={document.id} className="rounded-lg border border-stone-200 p-2">
                        <p className="text-sm font-semibold text-stone-800">{document.title}</p>
                        <p className="text-xs text-stone-600">{document.document_type}</p>
                        <p className="text-xs text-stone-500">{formatDateBR(document.created_at)}</p>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-stone-500">Sem consentimentos vinculados.</p>
                  )}
                </CardContent>
              </Card>
            ) : null}

            {detailsTab === "historico-operacional" ? (
              <Card className="border-stone-200">
                <CardContent className="space-y-2 p-4">
                  {operationalHistory.length ? (
                    operationalHistory.map((event, index) => (
                      <div key={`${event.title}-${index}`} className="rounded-lg border border-stone-200 p-2">
                        <p className="text-sm font-semibold text-stone-800">{event.title}</p>
                        <p className="text-xs text-stone-600">{event.description}</p>
                        <p className="text-xs text-stone-500">{formatDateTimeBR(event.date)}</p>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-stone-500">Sem histórico operacional disponível.</p>
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
        open={openDrawer}
        onOpenChange={setOpenDrawer}
        title="Novo paciente"
        description="Cadastro rápido para o CRM operacional."
      >
        <Card className="border-stone-200">
          <CardContent className="space-y-3 p-4">
            <Input placeholder="Nome completo" value={newName} onChange={(event) => setNewName(event.target.value)} />
            <Input placeholder="Telefone (somente números)" value={newPhone} onChange={(event) => setNewPhone(event.target.value)} />
            <Input placeholder="E-mail" value={newEmail} onChange={(event) => setNewEmail(event.target.value)} />
            <select
              className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
              value={newUnitId}
              onChange={(event) => setNewUnitId(event.target.value)}
            >
              <option value="">Selecionar unidade (opcional)</option>
              {dataset.units.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  {unit.name}
                </option>
              ))}
            </select>
            <Input
              placeholder="Tags separadas por vírgula (ex.: vip, ortodontia)"
              value={newTags}
              onChange={(event) => setNewTags(event.target.value)}
            />
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setOpenDrawer(false)}>
                Cancelar
              </Button>
              <Button
                onClick={() => {
                  if (!newName.trim() || !newPhone.trim()) {
                    toast.error("Preencha nome e telefone para cadastrar.");
                    return;
                  }
                  createPatientMutation.mutate();
                }}
                disabled={createPatientMutation.isPending}
              >
                {createPatientMutation.isPending ? "Salvando..." : "Salvar paciente"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </RightDrawer>
    </div>
  );
}

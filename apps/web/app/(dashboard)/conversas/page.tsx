"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Brain, CircleOff, Paperclip, Send, Sparkles, UserRoundCheck } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";

import {
  ConfirmDialog,
  EmptyState,
  FilterBar,
  PageHeader,
  StatusBadge,
  TemperatureBadge,
} from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { api } from "@/lib/api";
import {
  ApiPage,
  AppointmentItem,
  ConversationItem,
  DocumentItem,
  LeadItem,
  MessageItem,
  PatientItem,
  UnitItem,
  UserItem,
} from "@/lib/domain-types";
import {
  formatDateBR,
  formatDateTimeBR,
  formatPhoneBR,
  formatRelativeTime,
  initials,
  STAGE_LABELS,
} from "@/lib/formatters";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from "@odontoflux/ui";

type InboxDataset = {
  conversations: ConversationItem[];
  users: UserItem[];
  patients: PatientItem[];
  units: UnitItem[];
  leads: LeadItem[];
  appointments: AppointmentItem[];
  documents: DocumentItem[];
};

type MessageResponse = { data: MessageItem[] };
type AIDecisionItem = {
  id: string;
  final_decision: string;
  decision_reason: string;
  decision_reason_label: string;
  handoff_required: boolean;
  guardrail_trigger?: string | null;
  confidence?: number | null;
  generated_response?: string | null;
  created_at: string;
};
type AIDecisionResponse = { data: AIDecisionItem[] };

const STATUS_FILTERS = [
  { id: "all", label: "Todas" },
  { id: "aberta", label: "Abertas" },
  { id: "aguardando", label: "Aguardando" },
  { id: "finalizada", label: "Finalizadas" },
  { id: "nao_respondida", label: "Não respondidas" },
] as const;

type PriorityFilter = "all" | "alta" | "media" | "baixa";

function conversationPriority(conversation: ConversationItem): "alta" | "media" | "baixa" {
  if (conversation.status === "aguardando") return "alta";
  if (!conversation.last_message_at) return "media";
  const minutes = (Date.now() - new Date(conversation.last_message_at).getTime()) / (1000 * 60);
  if (minutes > 180) return "alta";
  if (minutes > 60) return "media";
  return "baixa";
}

function priorityBadgeClass(priority: "alta" | "media" | "baixa") {
  if (priority === "alta") return "bg-rose-100 text-rose-700";
  if (priority === "media") return "bg-amber-100 text-amber-800";
  return "bg-emerald-100 text-emerald-700";
}

function aiDecisionLabel(value?: string | null) {
  if (!value) return "Sem decisão";
  if (value === "responded") return "Respondido";
  if (value === "handoff") return "Handoff";
  if (value === "blocked") return "Bloqueado";
  if (value === "ignored") return "Ignorado";
  if (value === "error") return "Erro";
  return value;
}

function aiReasonLabel(value?: string | null) {
  if (!value) return "Sem motivo";
  return value.replaceAll("_", " ");
}

export default function ConversasPage() {
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const focusConversationId = searchParams.get("focus");
  const [focusHandled, setFocusHandled] = useState(false);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_FILTERS)[number]["id"]>("all");
  const [unitFilter, setUnitFilter] = useState("all");
  const [ownerFilter, setOwnerFilter] = useState("all");
  const [priorityFilter, setPriorityFilter] = useState<PriorityFilter>("all");

  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [draftMessage, setDraftMessage] = useState("");
  const [internalNote, setInternalNote] = useState("");
  const [selectedAttachment, setSelectedAttachment] = useState<File | null>(null);

  const [closeDialogOpen, setCloseDialogOpen] = useState(false);
  const [aiSuggestion, setAiSuggestion] = useState("");
  const [aiIntent, setAiIntent] = useState("");
  const messageListRef = useRef<HTMLDivElement | null>(null);
  const seenMessageIdsRef = useRef<Map<string, Set<string>>>(new Map());
  const bootstrappedConversationsRef = useRef<Set<string>>(new Set());

  const aiSettingsQuery = useQuery<{ global?: { enabled?: boolean } }>({
    queryKey: ["ai-autoresponder-settings"],
    queryFn: async () => (await api.get("/settings/ai-autoresponder/config")).data,
  });

  const inboxQuery = useQuery<InboxDataset>({
    queryKey: ["inbox-dataset", focusConversationId ?? "default"],
    queryFn: async () => {
      const [
        conversationsResponse,
        usersResponse,
        patientsResponse,
        unitsResponse,
        leadsResponse,
        appointmentsResponse,
        documentsResponse,
      ] = await Promise.all([
        api.get<ApiPage<ConversationItem>>("/conversations", { params: { limit: 300, offset: 0 } }),
        api.get<ApiPage<UserItem>>("/users", { params: { limit: 100, offset: 0 } }),
        api.get<ApiPage<PatientItem>>("/patients", { params: { limit: 100, offset: 0 } }),
        api.get<ApiPage<UnitItem>>("/units", { params: { limit: 100, offset: 0 } }),
        api.get<ApiPage<LeadItem>>("/leads", { params: { limit: 100, offset: 0 } }),
        api.get<ApiPage<AppointmentItem>>("/appointments", { params: { limit: 100, offset: 0 } }),
        api.get<ApiPage<DocumentItem>>("/documents", { params: { limit: 100, offset: 0 } }),
      ]);

      return {
        conversations: conversationsResponse.data.data ?? [],
        users: usersResponse.data.data ?? [],
        patients: patientsResponse.data.data ?? [],
        units: unitsResponse.data.data ?? [],
        leads: leadsResponse.data.data ?? [],
        appointments: appointmentsResponse.data.data ?? [],
        documents: documentsResponse.data.data ?? [],
      };
    },
    refetchInterval: 7000,
    refetchOnWindowFocus: true,
  });

  const messagesQuery = useQuery<MessageResponse>({
    queryKey: ["conversation-messages", selectedConversationId],
    queryFn: async () =>
      (
        await api.get<MessageResponse>("/messages", {
          params: { conversation_id: selectedConversationId, limit: 200, offset: 0 },
        })
      ).data,
    enabled: Boolean(selectedConversationId),
    refetchInterval: selectedConversationId ? 2500 : false,
    refetchOnWindowFocus: true,
  });

  const aiDecisionsQuery = useQuery<AIDecisionResponse>({
    queryKey: ["conversation-ai-decisions", selectedConversationId],
    queryFn: async () =>
      (
        await api.get<AIDecisionResponse>(
          `/conversations/${selectedConversationId}/ai-autoresponder/decisions`,
          { params: { limit: 20 } },
        )
      ).data,
    enabled: Boolean(selectedConversationId),
    refetchInterval: selectedConversationId ? 5000 : false,
    refetchOnWindowFocus: true,
  });

  const sendMessageMutation = useMutation({
    mutationFn: async () => {
      const attachmentLabel = selectedAttachment ? `\n\n[Anexo enviado: ${selectedAttachment.name}]` : "";
      return api.post("/messages", {
        conversation_id: selectedConversationId,
        body: `${draftMessage.trim()}${attachmentLabel}`,
        message_type: "text",
      });
    },
    onSuccess: () => {
      setDraftMessage("");
      setSelectedAttachment(null);
      toast.success("Mensagem enviada para a fila de entrega.");
      queryClient.invalidateQueries({ queryKey: ["conversation-messages", selectedConversationId] });
      queryClient.invalidateQueries({ queryKey: ["inbox-dataset"] });
    },
    onError: (error: unknown) => {
      const apiMessage =
        typeof error === "object" &&
        error &&
        "response" in error &&
        typeof (error as { response?: { data?: { error?: { message?: string } } } }).response?.data?.error?.message === "string"
          ? (error as { response?: { data?: { error?: { message?: string } } } }).response?.data?.error?.message
          : null;
      toast.error(apiMessage || "Não foi possível enviar a mensagem.");
    },
  });

  const assignMutation = useMutation({
    mutationFn: async (assignedUserId: string | null) =>
      api.patch(`/conversations/${selectedConversationId}`, { assigned_user_id: assignedUserId }),
    onSuccess: () => {
      toast.success("Responsável atualizado.");
      queryClient.invalidateQueries({ queryKey: ["inbox-dataset"] });
    },
    onError: () => toast.error("Não foi possível atualizar o responsável."),
  });

  const closeConversationMutation = useMutation({
    mutationFn: async () => api.patch(`/conversations/${selectedConversationId}`, { status: "finalizada" }),
    onSuccess: () => {
      toast.success("Conversa encerrada.");
      setCloseDialogOpen(false);
      queryClient.invalidateQueries({ queryKey: ["inbox-dataset"] });
    },
    onError: () => toast.error("Não foi possível encerrar a conversa."),
  });

  const summarizeMutation = useMutation({
    mutationFn: async () => (await api.post(`/conversations/${selectedConversationId}/summarize`)).data,
    onSuccess: () => {
      toast.success("Resumo IA atualizado.");
      queryClient.invalidateQueries({ queryKey: ["inbox-dataset"] });
    },
    onError: () => toast.error("Falha ao gerar resumo IA."),
  });

  const suggestionMutation = useMutation({
    mutationFn: async () => (await api.post(`/messages/${selectedConversationId}/ai-suggestion`)).data,
    onSuccess: (data) => {
      setAiSuggestion(data?.suggested_reply ?? "");
      setAiIntent(data?.intent ?? "");
      toast.success("Sugestão IA atualizada.");
    },
    onError: () => toast.error("Não foi possível obter a sugestão IA."),
  });

  const toggleAiMutation = useMutation({
    mutationFn: async (enabled: boolean) =>
      api.put(`/conversations/${selectedConversationId}/ai-autoresponder`, { enabled }),
    onSuccess: (_, enabled) => {
      toast.success(enabled ? "IA ativada para esta conversa." : "IA desativada para esta conversa.");
      queryClient.invalidateQueries({ queryKey: ["inbox-dataset"] });
      queryClient.invalidateQueries({ queryKey: ["conversation-ai-decisions", selectedConversationId] });
    },
    onError: () => toast.error("Não foi possível alterar o modo IA da conversa."),
  });

  const convertLeadMutation = useMutation({
    mutationFn: async () => {
      const conversation = (inboxQuery.data?.conversations ?? []).find((item) => item.id === selectedConversationId);
      if (!conversation?.lead_id) throw new Error("Conversa sem lead vinculado.");

      const lead = (inboxQuery.data?.leads ?? []).find((item) => item.id === conversation.lead_id);
      if (!lead) throw new Error("Lead não encontrado para conversão.");
      if (lead.patient_id) {
        await api.patch(`/leads/${lead.id}`, { stage: "qualificado" });
        return;
      }
      if (!lead.phone) throw new Error("Lead sem telefone para conversão.");

      const patient = await api.post<{ id: string }>("/patients", {
        full_name: lead.name,
        phone: lead.phone,
        email: lead.email || null,
        status: "ativo",
        origin: lead.origin || "whatsapp",
        tags: ["lead_convertido"],
      });

      await api.patch(`/leads/${lead.id}`, { patient_id: patient.data.id, stage: "qualificado" });
      await api.patch(`/conversations/${conversation.id}`, { patient_id: patient.data.id });
    },
    onSuccess: () => {
      toast.success("Lead convertido em paciente com sucesso.");
      queryClient.invalidateQueries({ queryKey: ["inbox-dataset"] });
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : "Não foi possível converter o lead.";
      toast.error(message);
    },
  });

  const dataset = inboxQuery.data;
  const usersById = useMemo(
    () => new Map((dataset?.users ?? []).map((item) => [item.id, item.full_name])),
    [dataset?.users],
  );
  const patientsById = useMemo(
    () => new Map((dataset?.patients ?? []).map((item) => [item.id, item])),
    [dataset?.patients],
  );
  const unitsById = useMemo(
    () => new Map((dataset?.units ?? []).map((item) => [item.id, item.name])),
    [dataset?.units],
  );
  const leadsById = useMemo(
    () => new Map((dataset?.leads ?? []).map((item) => [item.id, item])),
    [dataset?.leads],
  );

  const filteredConversations = useMemo(() => {
    const items = dataset?.conversations ?? [];
    const term = search.toLowerCase().trim();

    return items.filter((conversation) => {
      const patient = conversation.patient_id ? patientsById.get(conversation.patient_id) : null;
      const owner = conversation.assigned_user_id ? usersById.get(conversation.assigned_user_id) : "";
      const priority = conversationPriority(conversation);

      const haystack = `${patient?.full_name ?? ""} ${owner ?? ""} ${conversation.channel} ${conversation.ai_summary ?? ""}`.toLowerCase();

      const isNoReply =
        ["aberta", "aguardando"].includes(conversation.status) &&
        (!conversation.last_message_at || Date.now() - new Date(conversation.last_message_at).getTime() > 1000 * 60 * 60 * 2);

      const byStatus =
        statusFilter === "all" ||
        conversation.status === statusFilter ||
        (statusFilter === "nao_respondida" && isNoReply);
      const bySearch = !term || haystack.includes(term);
      const byUnit = unitFilter === "all" || conversation.unit_id === unitFilter;
      const byOwner = ownerFilter === "all" || conversation.assigned_user_id === ownerFilter;
      const byPriority = priorityFilter === "all" || priority === priorityFilter;

      return byStatus && bySearch && byUnit && byOwner && byPriority;
    });
  }, [dataset?.conversations, ownerFilter, patientsById, priorityFilter, search, statusFilter, unitFilter, usersById]);

  useEffect(() => {
    const focusedFromStorage = localStorage.getItem("odontoflux_focus_conversation");
    const preferredConversationId = focusHandled ? null : focusConversationId || focusedFromStorage;

    if (preferredConversationId) {
      const foundInFiltered = filteredConversations.some((item) => item.id === preferredConversationId);
      if (foundInFiltered) {
        if (selectedConversationId !== preferredConversationId) {
          setSelectedConversationId(preferredConversationId);
        }
        localStorage.removeItem("odontoflux_focus_conversation");
        setFocusHandled(true);
        return;
      }

      const existsInDataset = (dataset?.conversations ?? []).some((item) => item.id === preferredConversationId);
      if (existsInDataset) {
        if (
          search !== "" ||
          statusFilter !== "all" ||
          unitFilter !== "all" ||
          ownerFilter !== "all" ||
          priorityFilter !== "all"
        ) {
          setSearch("");
          setStatusFilter("all");
          setUnitFilter("all");
          setOwnerFilter("all");
          setPriorityFilter("all");
        }
        if (selectedConversationId !== preferredConversationId) {
          setSelectedConversationId(preferredConversationId);
        }
        localStorage.removeItem("odontoflux_focus_conversation");
        setFocusHandled(true);
        return;
      }
    }

    const selectedStillVisible = selectedConversationId
      ? filteredConversations.some((item) => item.id === selectedConversationId)
      : false;

    if ((!selectedConversationId || !selectedStillVisible) && filteredConversations.length > 0) {
      setSelectedConversationId(filteredConversations[0].id);
      return;
    }

    if (filteredConversations.length === 0 && selectedConversationId) {
      setSelectedConversationId(null);
    }
  }, [
    dataset?.conversations,
    filteredConversations,
    focusConversationId,
    focusHandled,
    ownerFilter,
    priorityFilter,
    search,
    selectedConversationId,
    statusFilter,
    unitFilter,
  ]);

  useEffect(() => {
    setFocusHandled(false);
  }, [focusConversationId]);

  useEffect(() => {
    if (!selectedConversationId) return;
    const messages = messagesQuery.data?.data ?? [];
    const currentIds = new Set(messages.map((message) => message.id));

    if (!bootstrappedConversationsRef.current.has(selectedConversationId)) {
      bootstrappedConversationsRef.current.add(selectedConversationId);
      seenMessageIdsRef.current.set(selectedConversationId, currentIds);
    } else {
      const previousIds = seenMessageIdsRef.current.get(selectedConversationId) ?? new Set<string>();
      const newInboundCount = messages.filter(
        (message) => !previousIds.has(message.id) && message.direction === "inbound",
      ).length;
      if (newInboundCount > 0) {
        toast.info(
          newInboundCount === 1
            ? "Nova mensagem recebida na conversa."
            : `${newInboundCount} novas mensagens recebidas na conversa.`,
        );
      }
      seenMessageIdsRef.current.set(selectedConversationId, currentIds);
    }

    const container = messageListRef.current;
    if (container) {
      container.scrollTop = container.scrollHeight;
    }
  }, [messagesQuery.data?.data, selectedConversationId]);

  const selectedConversation = useMemo(
    () => filteredConversations.find((item) => item.id === selectedConversationId) ?? null,
    [filteredConversations, selectedConversationId],
  );

  const globalAiEnabled = Boolean(aiSettingsQuery.data?.global?.enabled);
  const aiEnabledForConversation = (conversation: ConversationItem) =>
    conversation.ai_autoresponder_enabled ?? globalAiEnabled;

  const selectedPriority = selectedConversation ? conversationPriority(selectedConversation) : "baixa";
  const selectedPatient = selectedConversation?.patient_id
    ? patientsById.get(selectedConversation.patient_id) ?? null
    : null;
  const selectedLead = selectedConversation?.lead_id ? leadsById.get(selectedConversation.lead_id) ?? null : null;
  const selectedAiEnabled = selectedConversation ? aiEnabledForConversation(selectedConversation) : false;
  const selectedAiLastDecision = selectedConversation?.ai_autoresponder_last_decision ?? null;
  const selectedAiLastReason = selectedConversation?.ai_autoresponder_last_reason ?? null;
  const selectedAiDecisions = aiDecisionsQuery.data?.data ?? [];

  const patientAppointments = useMemo(() => {
    if (!selectedPatient) return [];
    return (dataset?.appointments ?? [])
      .filter((item) => item.patient_id === selectedPatient.id)
      .sort((a, b) => new Date(b.starts_at).getTime() - new Date(a.starts_at).getTime());
  }, [dataset?.appointments, selectedPatient]);

  const patientDocuments = useMemo(() => {
    if (!selectedPatient) return [];
    return (dataset?.documents ?? [])
      .filter((item) => item.patient_id === selectedPatient.id)
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  }, [dataset?.documents, selectedPatient]);

  if (inboxQuery.isLoading) return <LoadingState message="Carregando inbox operacional..." />;
  if (inboxQuery.isError || !dataset) return <ErrorState message="Não foi possível carregar o inbox." />;

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Relacionamento"
        title="Inbox de conversas"
        description="Atendimento WhatsApp com contexto clínico, automações e priorização operacional."
        meta={<Badge className="bg-stone-200 text-stone-700">{filteredConversations.length} conversa(s) no filtro</Badge>}
      />

      <FilterBar search={search} onSearchChange={setSearch} searchPlaceholder="Buscar por paciente, canal ou responsável...">
        {STATUS_FILTERS.map((status) => (
          <Button
            key={status.id}
            variant={status.id === statusFilter ? "default" : "outline"}
            className="h-8"
            onClick={() => setStatusFilter(status.id)}
          >
            {status.label}
          </Button>
        ))}
        <select
          className="h-8 rounded-md border border-stone-300 bg-white px-2 text-xs"
          value={unitFilter}
          onChange={(event) => setUnitFilter(event.target.value)}
        >
          <option value="all">Todas as unidades</option>
          {dataset.units.map((unit) => (
            <option key={unit.id} value={unit.id}>{unit.name}</option>
          ))}
        </select>
        <select
          className="h-8 rounded-md border border-stone-300 bg-white px-2 text-xs"
          value={ownerFilter}
          onChange={(event) => setOwnerFilter(event.target.value)}
        >
          <option value="all">Todos responsáveis</option>
          {dataset.users.map((user) => (
            <option key={user.id} value={user.id}>{user.full_name}</option>
          ))}
        </select>
        <select
          className="h-8 rounded-md border border-stone-300 bg-white px-2 text-xs"
          value={priorityFilter}
          onChange={(event) => setPriorityFilter(event.target.value as PriorityFilter)}
        >
          <option value="all">Todas prioridades</option>
          <option value="alta">Alta</option>
          <option value="media">Média</option>
          <option value="baixa">Baixa</option>
        </select>
      </FilterBar>

      <div className="grid gap-4 xl:grid-cols-[340px,1fr,360px]">
        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle>Conversas</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {filteredConversations.length ? (
              filteredConversations.map((item) => {
                const patient = item.patient_id ? patientsById.get(item.patient_id) : null;
                const owner = item.assigned_user_id ? usersById.get(item.assigned_user_id) : null;
                const isActive = item.id === selectedConversationId;
                const priority = conversationPriority(item);
                const aiEnabled = aiEnabledForConversation(item);

                return (
                  <button
                    key={item.id}
                    onClick={() => setSelectedConversationId(item.id)}
                    className={`w-full rounded-lg border p-3 text-left transition ${
                      isActive ? "border-primary bg-primary/5" : "border-stone-200 hover:bg-stone-50"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-stone-200 text-xs font-semibold text-stone-700">
                          {initials(patient?.full_name ?? "Paciente")}
                        </div>
                        <div>
                          <p className="text-sm font-semibold text-stone-800">{patient?.full_name ?? "Contato sem identificação"}</p>
                          <p className="text-xs text-stone-500">{formatRelativeTime(item.last_message_at)}</p>
                        </div>
                      </div>
                      <StatusBadge value={item.status} />
                    </div>
                    <p className="mt-2 line-clamp-2 text-xs text-stone-600">
                      {item.ai_summary || "Sem resumo IA. Clique em “Atualizar resumo IA” para gerar contexto."}
                    </p>
                    <div className="mt-2 flex flex-wrap items-center justify-between gap-1 text-xs text-stone-500">
                      <span>Canal: {item.channel}</span>
                      <span>{owner ?? "Sem responsável"}</span>
                      <Badge className={aiEnabled ? "bg-emerald-100 text-emerald-700" : "bg-stone-200 text-stone-700"}>
                        IA {aiEnabled ? "ativa" : "inativa"}
                      </Badge>
                      <Badge className={priorityBadgeClass(priority)}>{priority === "alta" ? "Alta" : priority === "media" ? "Média" : "Baixa"}</Badge>
                    </div>
                  </button>
                );
              })
            ) : (
              <EmptyState title="Nenhuma conversa no filtro" description="Ajuste os filtros para visualizar atendimentos." />
            )}
          </CardContent>
        </Card>

        <Card className="border-stone-200">
          <CardHeader className="border-b border-stone-200 pb-4">
            <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <CardTitle>
                  {selectedPatient?.full_name ??
                    selectedLead?.name ??
                    (selectedConversation ? "Contato sem identificação" : "Selecione uma conversa")}
                </CardTitle>
                <p className="text-xs text-stone-500">
                  {selectedConversation
                    ? `${selectedConversation.channel} • Última atividade em ${formatDateTimeBR(selectedConversation.last_message_at)}`
                    : "Escolha uma conversa para iniciar o atendimento."}
                </p>
              </div>
              {selectedConversation ? (
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    variant={selectedAiEnabled ? "outline" : "default"}
                    className="h-8 gap-1.5"
                    onClick={() => toggleAiMutation.mutate(!selectedAiEnabled)}
                    disabled={toggleAiMutation.isPending}
                  >
                    <Brain size={14} />
                    {selectedAiEnabled ? "Desativar IA" : "Ativar IA"}
                  </Button>
                  <Button
                    variant="outline"
                    className="h-8 gap-1.5"
                    onClick={() => summarizeMutation.mutate()}
                    disabled={summarizeMutation.isPending}
                  >
                    <Brain size={14} />
                    Atualizar resumo IA
                  </Button>
                  <Button
                    variant="outline"
                    className="h-8 gap-1.5"
                    onClick={() => suggestionMutation.mutate()}
                    disabled={suggestionMutation.isPending}
                  >
                    <Sparkles size={14} />
                    Sugestão IA
                  </Button>
                  {selectedLead && !selectedPatient ? (
                    <Button
                      variant="outline"
                      className="h-8 gap-1.5"
                      onClick={() => convertLeadMutation.mutate()}
                      disabled={convertLeadMutation.isPending}
                    >
                      <UserRoundCheck size={14} />
                      Converter em paciente
                    </Button>
                  ) : null}
                  <Button variant="destructive" className="h-8 gap-1.5" onClick={() => setCloseDialogOpen(true)}>
                    <CircleOff size={14} />
                    Encerrar conversa
                  </Button>
                </div>
              ) : null}
            </div>
          </CardHeader>
          <CardContent className="space-y-4 pt-4">
            {selectedConversation ? (
              <>
                <div
                  ref={messageListRef}
                  className="max-h-[420px] space-y-3 overflow-y-auto rounded-xl border border-stone-200 bg-stone-50 p-4"
                >
                  {messagesQuery.isLoading ? (
                    <p className="text-sm text-stone-500">Carregando mensagens...</p>
                  ) : messagesQuery.isError ? (
                    <p className="text-sm text-rose-700">Não foi possível carregar o histórico de mensagens.</p>
                  ) : (messagesQuery.data?.data ?? []).length ? (
                    (messagesQuery.data?.data ?? []).map((message) => {
                      const outbound = message.direction === "outbound";
                      return (
                        <div key={message.id} className={`flex ${outbound ? "justify-end" : "justify-start"}`}>
                          <div
                            className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${
                              outbound
                                ? "bg-primary text-primary-foreground"
                                : "border border-stone-200 bg-white text-stone-800"
                            }`}
                          >
                            <p>{message.body}</p>
                            <p
                              className={`mt-1 text-[11px] ${
                                outbound ? "text-primary-foreground/80" : "text-stone-500"
                              }`}
                            >
                              {formatDateTimeBR(message.created_at)}
                            </p>
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <p className="text-sm text-stone-500">Sem mensagens registradas nesta conversa.</p>
                  )}
                </div>

                <div className="space-y-3 rounded-xl border border-stone-200 p-3">
                  <div className="grid gap-2 md:grid-cols-[1fr,220px]">
                    <Input
                      placeholder="Escreva sua mensagem para o paciente..."
                      value={draftMessage}
                      onChange={(event) => setDraftMessage(event.target.value)}
                    />
                    <Button
                      className="gap-1.5"
                      onClick={() => {
                        if (!draftMessage.trim() && !selectedAttachment) {
                          toast.error("Digite uma mensagem ou anexe um arquivo antes de enviar.");
                          return;
                        }
                        sendMessageMutation.mutate();
                      }}
                      disabled={sendMessageMutation.isPending}
                    >
                      <Send size={14} />
                      Enviar mensagem
                    </Button>
                  </div>

                  <div className="flex items-center gap-2">
                    <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-stone-300 px-2 py-1 text-xs text-stone-700">
                      <Paperclip size={13} />
                      Anexar arquivo
                      <input
                        type="file"
                        className="hidden"
                        onChange={(event) => setSelectedAttachment(event.target.files?.[0] ?? null)}
                      />
                    </label>
                    {selectedAttachment ? (
                      <span className="text-xs text-stone-500">{selectedAttachment.name}</span>
                    ) : (
                      <span className="text-xs text-stone-400">Nenhum anexo selecionado</span>
                    )}
                  </div>

                  <div className="grid gap-2 md:grid-cols-[1fr,220px]">
                    <Input
                      placeholder="Nota interna (não enviada ao paciente)"
                      value={internalNote}
                      onChange={(event) => setInternalNote(event.target.value)}
                    />
                    <Button
                      variant="outline"
                      onClick={() => {
                        if (!internalNote.trim()) {
                          toast.error("Digite uma nota interna para registrar.");
                          return;
                        }
                        toast.success("Nota interna registrada no contexto do atendimento.");
                        setInternalNote("");
                      }}
                    >
                      Registrar nota
                    </Button>
                  </div>
                </div>

                {(aiSuggestion || aiIntent) && (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 p-3">
                    {aiIntent ? <p className="text-xs font-semibold text-amber-800">Intenção detectada: {aiIntent}</p> : null}
                    {aiSuggestion ? <p className="mt-1 text-sm text-amber-900">Sugestão: {aiSuggestion}</p> : null}
                  </div>
                )}
              </>
            ) : (
              <EmptyState title="Selecione uma conversa" description="Escolha um atendimento na coluna esquerda para abrir o chat." />
            )}
          </CardContent>
        </Card>

        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle>Contexto do paciente</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {selectedConversation ? (
              <>
                <div className="rounded-lg border border-stone-200 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Contato</p>
                  <p className="mt-1 text-sm font-semibold text-stone-800">{selectedPatient?.full_name ?? "Contato sem identificação"}</p>
                  <p className="text-xs text-stone-600">{formatPhoneBR(selectedPatient?.phone)}</p>
                  <p className="text-xs text-stone-600">{selectedPatient?.email ?? "Sem e-mail cadastrado"}</p>
                  <p className="mt-2 text-xs text-stone-500">
                    Unidade: <span className="font-medium text-stone-700">{selectedConversation.unit_id ? unitsById.get(selectedConversation.unit_id) ?? "Unidade não identificada" : "Omnicanal"}</span>
                  </p>
                  <p className="mt-1 text-xs text-stone-500">
                    Responsável atual: <span className="font-medium text-stone-700">{selectedConversation.assigned_user_id ? usersById.get(selectedConversation.assigned_user_id) ?? "Equipe" : "Sem responsável"}</span>
                  </p>
                  <p className="mt-1 text-xs text-stone-500">
                    Prioridade: <Badge className={priorityBadgeClass(selectedPriority)}>{selectedPriority === "alta" ? "Alta" : selectedPriority === "media" ? "Média" : "Baixa"}</Badge>
                  </p>
                  <p className="mt-2 text-xs text-stone-500">
                    IA:{" "}
                    <Badge className={selectedAiEnabled ? "bg-emerald-100 text-emerald-700" : "bg-stone-200 text-stone-700"}>
                      {selectedAiEnabled ? "Ativa" : "Inativa"}
                    </Badge>
                  </p>
                  <p className="mt-1 text-xs text-stone-500">
                    Última decisão IA:{" "}
                    <span className="font-medium text-stone-700">
                      {aiDecisionLabel(selectedAiLastDecision)}
                    </span>
                  </p>
                  {selectedAiLastReason ? (
                    <p className="mt-1 text-xs text-stone-500">
                      Motivo: <span className="font-medium text-stone-700">{aiReasonLabel(selectedAiLastReason)}</span>
                    </p>
                  ) : null}
                </div>

                <div className="rounded-lg border border-stone-200 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Trilha de decisão IA</p>
                  {aiDecisionsQuery.isLoading ? (
                    <p className="mt-2 text-xs text-stone-500">Carregando decisões...</p>
                  ) : selectedAiDecisions.length ? (
                    <div className="mt-2 space-y-2">
                      {selectedAiDecisions.slice(0, 5).map((decision) => (
                        <div key={decision.id} className="rounded-md border border-stone-200 bg-stone-50 px-2 py-1.5">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-semibold text-stone-700">{aiDecisionLabel(decision.final_decision)}</span>
                            <span className="text-[11px] text-stone-500">{formatDateTimeBR(decision.created_at)}</span>
                          </div>
                          <p className="text-xs text-stone-600">{decision.decision_reason_label}</p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-2 text-xs text-stone-500">Nenhuma decisão IA registrada para esta conversa.</p>
                  )}
                </div>

                <div className="space-y-2 rounded-lg border border-stone-200 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Atribuição</p>
                  <select
                    className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                    value={selectedConversation.assigned_user_id ?? ""}
                    onChange={(event) => assignMutation.mutate(event.target.value || null)}
                  >
                    <option value="">Sem responsável</option>
                    {(dataset.users ?? []).map((user) => (
                      <option key={user.id} value={user.id}>{user.full_name}</option>
                    ))}
                  </select>
                </div>

                <div className="rounded-lg border border-stone-200 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Lead</p>
                  {selectedLead ? (
                    <div className="mt-2 space-y-1">
                      <p className="text-sm font-semibold text-stone-800">{selectedLead.name}</p>
                      <div className="flex items-center gap-2">
                        <StatusBadge value={STAGE_LABELS[selectedLead.stage] ?? selectedLead.stage} />
                        <TemperatureBadge value={selectedLead.temperature} />
                      </div>
                      <p className="text-xs text-stone-600">Interesse: {selectedLead.interest ?? "Não informado"}</p>
                    </div>
                  ) : (
                    <p className="mt-1 text-xs text-stone-500">Sem lead vinculado.</p>
                  )}
                </div>

                <div className="rounded-lg border border-stone-200 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Agenda</p>
                  {patientAppointments.length ? (
                    <div className="mt-2 space-y-2">
                      <p className="text-xs text-stone-600">Próxima consulta: <span className="font-medium text-stone-800">{formatDateTimeBR(patientAppointments[0]?.starts_at)}</span></p>
                      <p className="text-xs text-stone-600">Último status: <StatusBadge value={patientAppointments[0]?.status} className="align-middle" /></p>
                    </div>
                  ) : (
                    <p className="mt-1 text-xs text-stone-500">Paciente sem consultas registradas.</p>
                  )}
                </div>

                <div className="rounded-lg border border-stone-200 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Documentos recentes</p>
                  {patientDocuments.length ? (
                    <div className="mt-2 space-y-2">
                      {patientDocuments.slice(0, 3).map((doc) => (
                        <div key={doc.id} className="rounded-md border border-stone-200 bg-stone-50 px-2 py-1.5">
                          <p className="text-xs font-medium text-stone-700">{doc.title}</p>
                          <p className="text-[11px] text-stone-500">{formatDateBR(doc.created_at)}</p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-1 text-xs text-stone-500">Nenhum documento recente.</p>
                  )}
                </div>

                <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Indicadores de automação</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {(selectedConversation.tags ?? []).length ? (
                      selectedConversation.tags.map((tag) => (
                        <Badge key={tag} className="bg-stone-200 text-stone-700">{tag}</Badge>
                      ))
                    ) : (
                      <span className="text-xs text-stone-500">Sem automações ativas identificadas.</span>
                    )}
                  </div>
                  <p className="mt-2 text-xs text-stone-700">
                    {selectedConversation.ai_summary ?? "Sem resumo disponível. Use “Atualizar resumo IA” para gerar contexto automático."}
                  </p>
                </div>
              </>
            ) : (
              <EmptyState title="Sem contexto selecionado" description="Selecione uma conversa para visualizar dados do paciente." />
            )}
          </CardContent>
        </Card>
      </div>

      <ConfirmDialog
        open={closeDialogOpen}
        onOpenChange={setCloseDialogOpen}
        title="Encerrar conversa"
        description="Esta ação finaliza o atendimento atual. Você poderá reabrir depois, se necessário."
        confirmLabel="Encerrar atendimento"
        destructive
        loading={closeConversationMutation.isPending}
        onConfirm={() => closeConversationMutation.mutate()}
      />
    </div>
  );
}

"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KanbanSquare, Plus, Table2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import {
  DataTable,
  FilterBar,
  PageHeader,
  StatCard,
  StatusBadge,
  TemperatureBadge,
} from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { useOwnerUnitScope } from "@/hooks/use-owner-unit-scope";
import { api } from "@/lib/api";
import { ApiPage, ConversationItem, LeadItem, UserItem } from "@/lib/domain-types";
import { formatDateBR, formatDateTimeBR, formatPhoneBR, numberFormatter, STAGE_LABELS } from "@/lib/formatters";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from "@odontoflux/ui";

const FUNNEL_STAGES = [
  "novo",
  "qualificado",
  "em_contato",
  "orcamento_enviado",
  "agendado",
  "perdido",
] as const;

type LeadsDataset = {
  leads: LeadItem[];
  users: UserItem[];
  conversations: ConversationItem[];
};

export default function LeadsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const ownerUnitScope = useOwnerUnitScope();
  const selectedOwnerUnitId =
    ownerUnitScope.canSwitchUnits && ownerUnitScope.selectedUnitId !== "all"
      ? ownerUnitScope.selectedUnitId
      : null;

  const [search, setSearch] = useState("");
  const [stageFilter, setStageFilter] = useState("all");
  const [tempFilter, setTempFilter] = useState("all");
  const [viewMode, setViewMode] = useState<"table" | "kanban">("table");

  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [interest, setInterest] = useState("");
  const [origin, setOrigin] = useState("whatsapp");

  const leadsQuery = useQuery<LeadsDataset>({
    queryKey: ["leads-dataset", selectedOwnerUnitId ?? "all"],
    queryFn: async () => {
      const [leadsResponse, usersResponse, conversationsResponse] = await Promise.all([
        api.get<ApiPage<LeadItem>>("/leads", {
          params: { limit: 200, offset: 0, unit_id: selectedOwnerUnitId ?? undefined },
        }),
        api.get<ApiPage<UserItem>>("/users", { params: { limit: 100, offset: 0 } }),
        api.get<ApiPage<ConversationItem>>("/conversations", {
          params: { limit: 200, offset: 0, unit_id: selectedOwnerUnitId ?? undefined },
        }),
      ]);

      return {
        leads: leadsResponse.data.data ?? [],
        users: usersResponse.data.data ?? [],
        conversations: conversationsResponse.data.data ?? [],
      };
    },
  });

  const createLeadMutation = useMutation({
    mutationFn: async () =>
      api.post("/leads", {
        name,
        phone: phone || null,
        interest: interest || null,
        unit_id: selectedOwnerUnitId ?? null,
        origin,
        stage: "novo",
        score: 50,
        temperature: "morno",
        status: "ativo",
      }),
    onSuccess: () => {
      toast.success("Lead criado com sucesso.");
      setName("");
      setPhone("");
      setInterest("");
      queryClient.invalidateQueries({ queryKey: ["leads-dataset"] });
    },
    onError: () => toast.error("Não foi possível criar o lead."),
  });

  const updateLeadMutation = useMutation({
    mutationFn: async ({ leadId, payload }: { leadId: string; payload: Record<string, unknown> }) =>
      api.patch(`/leads/${leadId}`, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["leads-dataset"] }),
    onError: () => toast.error("Não foi possível atualizar o lead."),
  });

  const convertLeadMutation = useMutation({
    mutationFn: async (lead: LeadItem) => {
      if (lead.patient_id) {
        await api.patch(`/leads/${lead.id}`, { stage: "qualificado" });
        return;
      }
      if (!lead.phone) {
        throw new Error("Lead sem telefone para conversão.");
      }

      const patient = await api.post<{ id: string }>("/patients", {
        full_name: lead.name,
        phone: lead.phone,
        email: lead.email || null,
        status: "ativo",
        origin: lead.origin || "whatsapp",
        tags: ["lead_convertido"],
        unit_id: selectedOwnerUnitId ?? lead.unit_id ?? null,
      });

      await api.patch(`/leads/${lead.id}`, {
        patient_id: patient.data.id,
        stage: "qualificado",
      });
    },
    onSuccess: () => {
      toast.success("Lead convertido em paciente.");
      queryClient.invalidateQueries({ queryKey: ["leads-dataset"] });
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : "Não foi possível converter o lead.";
      toast.error(message);
    },
  });

  const followUpMutation = useMutation({
    mutationFn: async (lead: LeadItem) => {
      if (!lead.patient_id) {
        throw new Error("Converta o lead em paciente antes de follow-up.");
      }

      const conversations = leadsQuery.data?.conversations ?? [];
      const existingConversation = conversations.find(
        (item) => item.lead_id === lead.id || item.patient_id === lead.patient_id,
      );

      const conversationId =
        existingConversation?.id ??
        (
          await api.post<ConversationItem>("/conversations", {
            lead_id: lead.id,
            patient_id: lead.patient_id,
            unit_id: selectedOwnerUnitId ?? lead.unit_id ?? null,
            channel: "whatsapp",
            assigned_user_id: lead.owner_user_id || null,
            tags: ["follow_up"],
          })
        ).data.id;

      await api.post("/messages", {
        conversation_id: conversationId,
        body: `Olá, ${lead.name.split(" ")[0]}! Passando para retomar seu interesse em ${lead.interest || "tratamento odontológico"}.`,
        message_type: "text",
      });

      await api.patch(`/leads/${lead.id}`, { stage: "em_contato" });
    },
    onSuccess: () => {
      toast.success("Follow-up enviado com sucesso.");
      queryClient.invalidateQueries({ queryKey: ["leads-dataset"] });
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : "Não foi possível enviar o follow-up.";
      toast.error(message);
    },
  });

  if (leadsQuery.isLoading) return <LoadingState message="Carregando funil comercial..." />;
  if (leadsQuery.isError || !leadsQuery.data) return <ErrorState message="Não foi possível carregar os leads." />;

  const visibleUsers =
    selectedOwnerUnitId
      ? leadsQuery.data.users.filter((user) => !user.unit_id || user.unit_id === selectedOwnerUnitId)
      : leadsQuery.data.users;

  const usersById = new Map(leadsQuery.data.users.map((item) => [item.id, item.full_name]));

  const lastInteractionByLead = new Map<string, string | null>();
  for (const lead of leadsQuery.data.leads) {
    const related = leadsQuery.data.conversations
      .filter(
        (item) => item.lead_id === lead.id || Boolean(lead.patient_id && item.patient_id === lead.patient_id),
      )
      .sort(
        (left, right) =>
          new Date(right.last_message_at || 0).getTime() - new Date(left.last_message_at || 0).getTime(),
      );
    lastInteractionByLead.set(lead.id, related[0]?.last_message_at ?? null);
  }

  const filteredLeads = leadsQuery.data.leads.filter((lead) => {
    const term = search.toLowerCase().trim();
    const haystack = `${lead.name} ${lead.phone ?? ""} ${lead.interest ?? ""} ${lead.origin ?? ""}`.toLowerCase();
    const bySearch = !term || haystack.includes(term);
    const byStage = stageFilter === "all" || lead.stage === stageFilter;
    const byTemp = tempFilter === "all" || lead.temperature === tempFilter;
    return bySearch && byStage && byTemp;
  });

  const stageCounts = FUNNEL_STAGES.map((stage) => ({
    stage,
    count: leadsQuery.data.leads.filter((item) => item.stage === stage).length,
  }));

  const hot = leadsQuery.data.leads.filter((lead) => lead.temperature === "quente").length;
  const hotRate = leadsQuery.data.leads.length ? (hot / leadsQuery.data.leads.length) * 100 : 0;

  const openConversation = async (lead: LeadItem) => {
    const existing = leadsQuery.data.conversations.find(
      (item) => item.lead_id === lead.id || Boolean(lead.patient_id && item.patient_id === lead.patient_id),
    );

    const conversationId =
      existing?.id ??
      (
        await api.post<ConversationItem>("/conversations", {
          lead_id: lead.id,
          patient_id: lead.patient_id || null,
          unit_id: selectedOwnerUnitId ?? lead.unit_id ?? null,
          channel: "whatsapp",
          assigned_user_id: lead.owner_user_id || null,
          tags: ["lead"],
        })
      ).data.id;

    localStorage.setItem("odontoflux_focus_conversation", conversationId);
    router.push(`/conversas?focus=${conversationId}`);
  };

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Comercial"
        title="Leads e funil"
        description="Pipeline operacional com etapas claras, score e temperatura de oportunidade."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant={viewMode === "table" ? "default" : "outline"}
              className="h-9 gap-1.5"
              onClick={() => setViewMode("table")}
            >
              <Table2 size={14} />
              Tabela
            </Button>
            <Button
              variant={viewMode === "kanban" ? "default" : "outline"}
              className="h-9 gap-1.5"
              onClick={() => setViewMode("kanban")}
            >
              <KanbanSquare size={14} />
              Kanban
            </Button>
          </div>
        }
      />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard title="Leads totais" value={numberFormatter.format(leadsQuery.data.leads.length)} />
        <StatCard
          title="Leads quentes"
          value={`${hotRate.toFixed(1)}%`}
          description="Temperatura alta"
          helper="Percentual de leads com maior propensão de fechamento."
        />
        <StatCard
          title="Qualificados"
          value={numberFormatter.format(stageCounts.find((item) => item.stage === "qualificado")?.count ?? 0)}
          helper="Prontos para proposta."
        />
        <StatCard
          title="Agendados"
          value={numberFormatter.format(stageCounts.find((item) => item.stage === "agendado")?.count ?? 0)}
          helper="Leads com consulta marcada."
        />
      </div>

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle>Novo lead</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2 md:grid-cols-5">
            <Input placeholder="Nome do lead" value={name} onChange={(event) => setName(event.target.value)} />
            <Input placeholder="Telefone" value={phone} onChange={(event) => setPhone(event.target.value)} />
            <Input placeholder="Interesse" value={interest} onChange={(event) => setInterest(event.target.value)} />
            <select
              className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm"
              value={origin}
              onChange={(event) => setOrigin(event.target.value)}
            >
              <option value="whatsapp">WhatsApp</option>
              <option value="instagram">Instagram</option>
              <option value="indicacao">Indicação</option>
              <option value="site">Site</option>
            </select>
            <Button
              className="gap-1.5"
              onClick={() => {
                if (!name.trim()) {
                  toast.error("Informe o nome do lead.");
                  return;
                }
                createLeadMutation.mutate();
              }}
              disabled={createLeadMutation.isPending}
            >
              <Plus size={14} />
              {createLeadMutation.isPending ? "Criando..." : "Criar lead"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <FilterBar search={search} onSearchChange={setSearch} searchPlaceholder="Buscar lead, telefone ou interesse...">
        <select
          className="h-9 rounded-md border border-stone-300 bg-white px-2 text-sm"
          value={stageFilter}
          onChange={(event) => setStageFilter(event.target.value)}
        >
          <option value="all">Todas as etapas</option>
          {FUNNEL_STAGES.map((stage) => (
            <option key={stage} value={stage}>
              {STAGE_LABELS[stage]}
            </option>
          ))}
        </select>
        <select
          className="h-9 rounded-md border border-stone-300 bg-white px-2 text-sm"
          value={tempFilter}
          onChange={(event) => setTempFilter(event.target.value)}
        >
          <option value="all">Todas as temperaturas</option>
          <option value="frio">Frio</option>
          <option value="morno">Morno</option>
          <option value="quente">Quente</option>
        </select>
      </FilterBar>

      {viewMode === "table" ? (
        <DataTable<LeadItem>
          title="Leads"
          rows={filteredLeads}
          getRowId={(item) => item.id}
          searchBy={(item) => `${item.name} ${item.phone ?? ""} ${item.interest ?? ""}`}
          tableClassName="min-w-[1360px] table-fixed"
          bodyWrapperClassName="max-h-[min(74vh,720px)] overflow-y-auto"
          columns={[
            {
              key: "lead_contato",
              label: "Lead e contato",
              className: "min-w-[250px] w-[250px]",
              cellClassName: "min-w-[250px] w-[250px] break-normal",
              render: (item) => (
                <div className="space-y-2">
                  <div>
                    <p className="font-semibold text-stone-800">{item.name}</p>
                    <div className="mt-1 flex flex-wrap gap-2">
                      <Badge className="bg-stone-100 text-stone-700">{item.origin ?? "Origem nao informada"}</Badge>
                      {item.patient_id ? <Badge className="bg-emerald-100 text-emerald-700">Paciente vinculado</Badge> : null}
                    </div>
                  </div>
                  <div className="space-y-1 text-xs text-stone-500">
                    <p>{formatPhoneBR(item.phone)}</p>
                    <p>{item.email?.trim() || "Sem e-mail"}</p>
                  </div>
                </div>
              ),
            },
            {
              key: "interesse",
              label: "Interesse e entrada",
              className: "min-w-[220px] w-[220px]",
              cellClassName: "min-w-[220px] w-[220px] break-normal",
              render: (item) => (
                <div className="space-y-1">
                  <p className="font-medium text-stone-800">{item.interest ?? "Interesse a definir"}</p>
                  <p className="text-xs text-stone-500">Criado em {formatDateBR(item.created_at)}</p>
                </div>
              ),
            },
            {
              key: "pipeline",
              label: "Pipeline",
              className: "min-w-[210px] w-[210px]",
              cellClassName: "min-w-[210px] w-[210px] break-normal",
              render: (item) => (
                <div className="space-y-2">
                  <div className="flex flex-wrap gap-2">
                    <StatusBadge value={STAGE_LABELS[item.stage] ?? item.stage} />
                    <TemperatureBadge value={item.temperature} />
                  </div>
                  <div className="rounded-lg border border-stone-200 bg-stone-50 px-3 py-2 text-xs text-stone-600">
                    <span className="font-semibold text-stone-800">Score {numberFormatter.format(item.score)}</span>
                    <span className="ml-2">{item.status || "Sem status"}</span>
                  </div>
                </div>
              ),
            },
            {
              key: "atividade",
              label: "Atividade",
              className: "min-w-[180px] w-[180px]",
              cellClassName: "min-w-[180px] w-[180px] break-normal",
              render: (item) => {
                const lastInteraction = lastInteractionByLead.get(item.id) ?? null;
                return (
                  <div className="space-y-1">
                    <p className="text-sm font-medium text-stone-800">
                      {lastInteraction ? "Ultima mensagem" : "Sem interacao recente"}
                    </p>
                    <p className="text-xs text-stone-500">{formatDateTimeBR(lastInteraction)}</p>
                  </div>
                );
              },
            },
            {
              key: "responsavel",
              label: "Responsavel",
              className: "min-w-[240px] w-[240px]",
              cellClassName: "min-w-[240px] w-[240px] break-normal",
              render: (item) => (
                <div className="space-y-2">
                  <p className="text-xs font-medium text-stone-600">
                    {item.owner_user_id ? usersById.get(item.owner_user_id) ?? "Responsavel removido" : "Nao atribuido"}
                  </p>
                  <select
                    className="h-9 w-full rounded-md border border-stone-300 bg-white px-2 text-xs"
                    value={item.owner_user_id ?? ""}
                    onChange={(event) =>
                      updateLeadMutation.mutate({
                        leadId: item.id,
                        payload: { owner_user_id: event.target.value || null },
                      })
                    }
                  >
                    <option value="">Nao atribuido</option>
                    {visibleUsers.map((user) => (
                      <option key={user.id} value={user.id}>
                        {user.full_name}
                      </option>
                    ))}
                  </select>
                </div>
              ),
            },
            {
              key: "acoes",
              label: "Acoes",
              className: "min-w-[260px] w-[260px]",
              cellClassName: "min-w-[260px] w-[260px] break-normal",
              render: (item) => (
                <div className="space-y-2">
                  <select
                    className="h-9 w-full rounded-md border border-stone-300 bg-white px-2 text-xs"
                    value={item.stage}
                    onChange={(event) => {
                      updateLeadMutation.mutate({
                        leadId: item.id,
                        payload: { stage: event.target.value },
                      });
                    }}
                  >
                    {FUNNEL_STAGES.map((stage) => (
                      <option key={stage} value={stage}>
                        {STAGE_LABELS[stage]}
                      </option>
                    ))}
                  </select>
                  <div className="grid grid-cols-2 gap-2">
                    <Button variant="outline" className="h-8 px-2 text-xs" onClick={() => openConversation(item)}>
                      Conversa
                    </Button>
                    <Button
                      variant="outline"
                      className="h-8 px-2 text-xs"
                      onClick={() => followUpMutation.mutate(item)}
                      disabled={followUpMutation.isPending}
                    >
                      Follow-up
                    </Button>
                    <Button
                      variant="outline"
                      className="col-span-2 h-8 px-2 text-xs"
                      onClick={() => convertLeadMutation.mutate(item)}
                      disabled={convertLeadMutation.isPending}
                    >
                      Converter em paciente
                    </Button>
                  </div>
                </div>
              ),
            },
          ]}
          emptyTitle="Sem leads para exibir"
          emptyDescription="Ajuste os filtros ou cadastre um novo lead."
        />
      ) : (
        <div className="grid gap-3 xl:grid-cols-6">
          {FUNNEL_STAGES.map((stage) => {
            const stageLeads = filteredLeads.filter((item) => item.stage === stage);
            return (
              <Card key={stage} className="border-stone-200">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">
                    {STAGE_LABELS[stage]} <Badge className="ml-1 bg-stone-200 text-stone-700">{stageLeads.length}</Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {stageLeads.length ? (
                    stageLeads.map((lead) => (
                      <div key={lead.id} className="rounded-lg border border-stone-200 bg-stone-50 p-2">
                        <p className="text-sm font-semibold text-stone-800">{lead.name}</p>
                        <p className="text-xs text-stone-500">{lead.interest ?? "Interesse não informado"}</p>
                        <div className="mt-2 flex items-center justify-between">
                          <TemperatureBadge value={lead.temperature} />
                          <span className="text-xs font-semibold text-stone-700">Score {lead.score}</span>
                        </div>
                        <div className="mt-2 grid grid-cols-2 gap-1">
                          <Button
                            variant="outline"
                            className="h-7 px-2 text-[11px]"
                            onClick={() => {
                              const currentIndex = FUNNEL_STAGES.indexOf(lead.stage as (typeof FUNNEL_STAGES)[number]);
                              const nextStage = FUNNEL_STAGES[Math.min(currentIndex + 1, FUNNEL_STAGES.length - 1)];
                              updateLeadMutation.mutate({ leadId: lead.id, payload: { stage: nextStage } });
                            }}
                          >
                            Avançar
                          </Button>
                          <Button
                            variant="outline"
                            className="h-7 px-2 text-[11px]"
                            onClick={() => followUpMutation.mutate(lead)}
                            disabled={followUpMutation.isPending}
                          >
                            Follow-up
                          </Button>
                        </div>
                        <div className="mt-1 grid grid-cols-2 gap-1">
                          <Button variant="outline" className="h-7 px-2 text-[11px]" onClick={() => openConversation(lead)}>
                            Conversa
                          </Button>
                          <Button
                            variant="outline"
                            className="h-7 px-2 text-[11px]"
                            onClick={() => convertLeadMutation.mutate(lead)}
                            disabled={convertLeadMutation.isPending}
                          >
                            Converter
                          </Button>
                        </div>
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-stone-500">Sem leads nesta etapa.</p>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

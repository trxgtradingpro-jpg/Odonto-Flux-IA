"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LifeBuoy } from "lucide-react";
import { toast } from "sonner";

import { DataTable, PageHeader, StatusBadge } from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { api } from "@/lib/api";
import { formatDateTimeBR } from "@/lib/formatters";
import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@odontoflux/ui";

type SupportOverview = {
  channels: Array<{ name: string; contact: string; availability: string }>;
  sla_hours: Record<string, number>;
  open_incidents: number;
  last_incident_at: string | null;
};

type Incident = {
  id: string;
  title: string;
  severity: string;
  description: string;
  contact_email: string | null;
  status: string;
  sla_deadline_at: string | null;
  resolution_notes: string | null;
  created_at: string;
  finished_at: string | null;
};

export default function SuportePage() {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [severity, setSeverity] = useState("media");
  const [description, setDescription] = useState("");
  const [contactEmail, setContactEmail] = useState("");

  const overviewQuery = useQuery<SupportOverview>({
    queryKey: ["support-overview"],
    queryFn: async () => (await api.get("/support/overview")).data,
  });
  const incidentsQuery = useQuery<{ data: Incident[] }>({
    queryKey: ["support-incidents"],
    queryFn: async () => (await api.get("/support/incidents", { params: { limit: 100, offset: 0 } })).data,
  });

  const createIncidentMutation = useMutation({
    mutationFn: async () =>
      api.post("/support/incidents", {
        title,
        severity,
        description,
        contact_email: contactEmail || null,
      }),
    onSuccess: () => {
      toast.success("Incidente aberto com sucesso.");
      setTitle("");
      setDescription("");
      setContactEmail("");
      queryClient.invalidateQueries({ queryKey: ["support-overview"] });
      queryClient.invalidateQueries({ queryKey: ["support-incidents"] });
    },
    onError: () => toast.error("Não foi possível abrir o incidente."),
  });

  const resolveIncidentMutation = useMutation({
    mutationFn: async (incidentId: string) => api.post(`/support/incidents/${incidentId}/resolve`, null, { params: { notes: "Resolvido pela equipe." } }),
    onSuccess: () => {
      toast.success("Incidente marcado como resolvido.");
      queryClient.invalidateQueries({ queryKey: ["support-overview"] });
      queryClient.invalidateQueries({ queryKey: ["support-incidents"] });
    },
    onError: () => toast.error("Não foi possível resolver o incidente."),
  });

  if (overviewQuery.isLoading || incidentsQuery.isLoading) {
    return <LoadingState message="Carregando central de suporte..." />;
  }
  if (overviewQuery.isError || incidentsQuery.isError || !overviewQuery.data || !incidentsQuery.data) {
    return <ErrorState message="Não foi possível carregar a central de suporte." />;
  }

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Suporte"
        title="Central de suporte e SLA"
        description="Canal operacional para incidentes, comunicação com cliente e rastreabilidade."
      />

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="border-stone-200 xl:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <LifeBuoy size={16} />
              Abrir incidente
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2 md:grid-cols-2">
            <Input placeholder="Título do incidente" value={title} onChange={(event) => setTitle(event.target.value)} />
            <select
              className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm"
              value={severity}
              onChange={(event) => setSeverity(event.target.value)}
            >
              <option value="baixa">Baixa</option>
              <option value="media">Média</option>
              <option value="alta">Alta</option>
              <option value="critica">Crítica</option>
            </select>
            <Input placeholder="Contato para retorno (e-mail)" value={contactEmail} onChange={(event) => setContactEmail(event.target.value)} />
            <Input placeholder="Descrição resumida" value={description} onChange={(event) => setDescription(event.target.value)} />
            <div className="md:col-span-2">
              <Button
                onClick={() => {
                  if (!title.trim() || !description.trim()) {
                    toast.error("Informe título e descrição.");
                    return;
                  }
                  createIncidentMutation.mutate();
                }}
                disabled={createIncidentMutation.isPending}
              >
                {createIncidentMutation.isPending ? "Abrindo..." : "Abrir incidente"}
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle>Contato e SLA</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-stone-700">
            <p>Incidentes em aberto: {overviewQuery.data.open_incidents}</p>
            <p>Último incidente: {formatDateTimeBR(overviewQuery.data.last_incident_at)}</p>
            {overviewQuery.data.channels.map((channel) => (
              <div key={channel.name} className="rounded-md border border-stone-200 bg-stone-50 p-2">
                <p className="font-semibold text-stone-800">{channel.name}</p>
                <p>{channel.contact}</p>
                <p className="text-xs text-stone-600">{channel.availability}</p>
              </div>
            ))}
            <p className="text-xs text-stone-600">
              SLA: crítica {overviewQuery.data.sla_hours.critica}h, alta {overviewQuery.data.sla_hours.alta}h, média {overviewQuery.data.sla_hours.media}h.
            </p>
          </CardContent>
        </Card>
      </div>

      <DataTable<Incident>
        title="Incidentes registrados"
        rows={incidentsQuery.data.data ?? []}
        getRowId={(item) => item.id}
        searchBy={(item) => `${item.title} ${item.severity} ${item.status}`}
        columns={[
          { key: "titulo", label: "Título", render: (item) => item.title },
          { key: "severidade", label: "Severidade", render: (item) => <StatusBadge value={item.severity} /> },
          { key: "status", label: "Status", render: (item) => <StatusBadge value={item.status} /> },
          { key: "criado", label: "Criado em", render: (item) => formatDateTimeBR(item.created_at) },
          { key: "sla", label: "Prazo SLA", render: (item) => formatDateTimeBR(item.sla_deadline_at) },
          {
            key: "acoes",
            label: "Ações",
            render: (item) =>
              item.status !== "success" ? (
                <Button
                  variant="outline"
                  className="h-8 px-2 text-xs"
                  onClick={() => resolveIncidentMutation.mutate(item.id)}
                  disabled={resolveIncidentMutation.isPending}
                >
                  Resolver
                </Button>
              ) : (
                <span className="text-xs text-emerald-700">Resolvido</span>
              ),
          },
        ]}
        emptyTitle="Sem incidentes"
        emptyDescription="Nenhum incidente aberto até o momento."
      />
    </div>
  );
}

"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  Building2,
  CheckCircle2,
  Clipboard,
  Copy,
  ExternalLink,
  MessageSquareText,
  PhoneCall,
  Plus,
  RefreshCw,
  Save,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { useAdmSession } from "@/hooks/use-adm-session";
import { canAccessAdmPage } from "@/lib/adm-page-access";
import { api } from "@/lib/api";
import { getAdminAccessToken } from "@/lib/auth";
import { formatDateTimeBR } from "@/lib/formatters";
import { Badge, Button, Card, CardContent, Input, cn } from "@odontoflux/ui";

type Prospect = {
  id: string;
  clinic_name: string;
  owner_name?: string | null;
  manager_name?: string | null;
  phone?: string | null;
  whatsapp_phone?: string | null;
  city?: string | null;
  state?: string | null;
  main_pain?: string | null;
  status: string;
  temperature: string;
  score: number;
  do_not_contact: boolean;
  demo_tenant_id?: string | null;
  demo_user_id?: string | null;
  demo_status: string;
  demo_sent_at?: string | null;
  demo_first_login_at?: string | null;
};

type SalesTemplateMessage = {
  key: string;
  label: string;
  body: string;
  is_default: boolean;
};

type SalesTemplate = {
  key: string;
  label: string;
  description: string;
  recommended_for: string[];
  body: string;
  messages: SalesTemplateMessage[];
};

type TemplateDraft = {
  key: string;
  label: string;
  description: string;
  recommended_for_text: string;
  messages: SalesTemplateMessage[];
};

type ClinicMessageItem = {
  prospect: Prospect;
  suggested_template_key: string;
  contact_name: string;
  whatsapp_destination?: string | null;
  demo_ready: boolean;
  copy_blocked_reason?: string | null;
  last_event_name?: string | null;
  last_event_at?: string | null;
  last_template_key?: string | null;
};

type ClinicMessagesResponse = {
  data: ClinicMessageItem[];
  total: number;
  limit: number;
  offset: number;
  templates: SalesTemplate[];
};

type MessagePreview = {
  prospect: Prospect;
  template_key: string;
  template_label: string;
  message_key: string;
  message_label: string;
  message_text: string;
  demo_login_url?: string | null;
  can_copy: boolean;
  warnings: string[];
  missing_variables: string[];
  resolved_variables: Record<string, string>;
  suggested_template_key: string;
};

const STATUS_OPTIONS = [
  "novo",
  "pesquisado",
  "contato_iniciado",
  "respondeu",
  "decisor_identificado",
  "demo_criada",
  "demo_enviada",
  "demo_acessada",
  "testou_whatsapp",
  "visitou_agenda",
  "followup",
  "reuniao_marcada",
  "proposta_enviada",
  "negociacao",
  "fechado_ganho",
  "fechado_perdido",
];

const TEMPERATURE_OPTIONS = ["frio", "morno", "quente", "muito_quente"];
const DEMO_STATUS_OPTIONS = ["rascunho", "criada", "enviada", "acessada", "expirada"];

function humanize(value?: string | null) {
  if (!value) return "-";
  return value
    .replace(/_/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}

function extractApiErrorMessage(error: unknown, fallback: string) {
  const response = (error as { response?: { data?: { error?: { message?: string } } } }).response;
  return response?.data?.error?.message || fallback;
}

function statusClass(status?: string | null) {
  if (status === "demo_acessada" || status === "testou_whatsapp") {
    return "border-emerald-200 bg-emerald-50 text-emerald-800";
  }
  if (status === "demo_enviada" || status === "contato_iniciado") {
    return "border-cyan-200 bg-cyan-50 text-cyan-800";
  }
  if (status === "fechado_perdido") {
    return "border-stone-200 bg-stone-100 text-stone-600";
  }
  return "border-stone-200 bg-white text-stone-700";
}

function temperatureClass(value?: string | null) {
  if (value === "muito_quente" || value === "quente") {
    return "border-orange-200 bg-orange-50 text-orange-700";
  }
  if (value === "morno") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-stone-200 bg-stone-100 text-stone-600";
}

async function copyToClipboard(value: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const element = document.createElement("textarea");
  element.value = value;
  element.setAttribute("readonly", "true");
  element.style.position = "fixed";
  element.style.left = "-9999px";
  document.body.appendChild(element);
  element.select();
  document.execCommand("copy");
  document.body.removeChild(element);
}

function templateToDraft(template?: SalesTemplate | null): TemplateDraft {
  return {
    key: template?.key || "",
    label: template?.label || "Novo template",
    description: template?.description || "",
    recommended_for_text: (template?.recommended_for || []).join(", "),
    messages:
      template?.messages?.length
        ? template.messages.map((message) => ({ ...message }))
        : [
            {
              key: "principal",
              label: "Mensagem principal",
              body:
                "Oi, {contact_name}! Tudo bem?\n\n" +
                "Preparei uma demo personalizada da {clinic_name}.\n\n" +
                "Link oficial da demo:\n{demo_link}",
              is_default: true,
            },
          ],
  };
}

function draftToPayload(draft: TemplateDraft) {
  return {
    key: draft.key || null,
    label: draft.label,
    description: draft.description,
    recommended_for: draft.recommended_for_text
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
    messages: draft.messages.map((message, index) => ({
      ...message,
      is_default: message.is_default || index === 0,
    })),
  };
}

function newTemplateMessage(index: number): SalesTemplateMessage {
  return {
    key: `mensagem_${index + 1}`,
    label: `Mensagem ${index + 1}`,
    body: "Oi, {contact_name}! Tudo bem?\n\nLink oficial da demo da {clinic_name}:\n{demo_link}",
    is_default: index === 0,
  };
}

export default function ClinicMessagesPage() {
  const queryClient = useQueryClient();
  const [hasToken, setHasToken] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [temperatureFilter, setTemperatureFilter] = useState("");
  const [demoStatusFilter, setDemoStatusFilter] = useState("");
  const [hasDemoFilter, setHasDemoFilter] = useState("");
  const [templateKey, setTemplateKey] = useState("");
  const [messageKey, setMessageKey] = useState("");
  const [preview, setPreview] = useState<MessagePreview | null>(null);
  const [viewMode, setViewMode] = useState<"clinics" | "templates">("clinics");
  const [editingTemplateKey, setEditingTemplateKey] = useState<string | null>(null);
  const [templateDraft, setTemplateDraft] = useState<TemplateDraft | null>(null);

  useEffect(() => {
    setHasToken(Boolean(getAdminAccessToken()));
  }, []);

  const admSessionQuery = useAdmSession(hasToken);
  const admPermissions = admSessionQuery.data?.resolved_adm_page_permissions;
  const canViewMessages = canAccessAdmPage(admPermissions, "adm_messages", "view");
  const canCreateMessages = canAccessAdmPage(admPermissions, "adm_messages", "create");
  const canEditMessages = canAccessAdmPage(admPermissions, "adm_messages", "edit");
  const canDeleteMessages = canAccessAdmPage(admPermissions, "adm_messages", "delete");

  const messagesQuery = useQuery<ClinicMessagesResponse>({
    queryKey: [
      "adm-clinic-messages",
      search,
      statusFilter,
      temperatureFilter,
      demoStatusFilter,
      hasDemoFilter,
    ],
    queryFn: async () =>
      (
        await api.get("/admin/clinic-messages", {
          params: {
            q: search || undefined,
            status: statusFilter || undefined,
            temperature: temperatureFilter || undefined,
            demo_status: demoStatusFilter || undefined,
            has_demo: hasDemoFilter === "" ? undefined : hasDemoFilter === "sim",
            limit: 250,
            offset: 0,
          },
        })
      ).data,
    enabled: hasToken && canViewMessages,
    retry: false,
  });

  const templatesQuery = useQuery<SalesTemplate[]>({
    queryKey: ["adm-clinic-message-templates"],
    queryFn: async () => (await api.get("/admin/clinic-messages/templates")).data,
    enabled: hasToken && canViewMessages,
    retry: false,
  });

  const items = useMemo(() => messagesQuery.data?.data ?? [], [messagesQuery.data?.data]);
  const templates = useMemo(
    () => messagesQuery.data?.templates ?? templatesQuery.data ?? [],
    [messagesQuery.data?.templates, templatesQuery.data],
  );
  const selectedTemplate = useMemo(
    () => templates.find((template) => template.key === templateKey) ?? templates[0] ?? null,
    [templateKey, templates],
  );
  const selectedTemplateMessage = useMemo(() => {
    const messages = selectedTemplate?.messages ?? [];
    return messages.find((message) => message.key === messageKey) ?? messages.find((message) => message.is_default) ?? messages[0] ?? null;
  }, [messageKey, selectedTemplate]);

  const selectedItem = useMemo(() => {
    return items.find((item) => item.prospect.id === selectedId) ?? items[0] ?? null;
  }, [items, selectedId]);
  const selectedProspectId = selectedItem?.prospect.id ?? null;
  const selectedSuggestedTemplateKey = selectedItem?.suggested_template_key ?? "";

  useEffect(() => {
    if (!selectedId && selectedItem) {
      setSelectedId(selectedItem.prospect.id);
    }
  }, [selectedId, selectedItem]);

  useEffect(() => {
    if (!selectedProspectId) return;
    setTemplateKey(selectedSuggestedTemplateKey);
    setPreview(null);
  }, [selectedProspectId, selectedSuggestedTemplateKey]);

  useEffect(() => {
    if (!selectedTemplate) return;
    const defaultMessage =
      selectedTemplate.messages.find((message) => message.is_default) ?? selectedTemplate.messages[0] ?? null;
    if (defaultMessage && !selectedTemplate.messages.some((message) => message.key === messageKey)) {
      setMessageKey(defaultMessage.key);
    }
  }, [messageKey, selectedTemplate]);

  useEffect(() => {
    const currentTemplate =
      templates.find((template) => template.key === editingTemplateKey) ?? templates[0] ?? null;
    if (!templateDraft && currentTemplate) {
      setEditingTemplateKey(currentTemplate.key);
      setTemplateDraft(templateToDraft(currentTemplate));
    }
  }, [editingTemplateKey, templateDraft, templates]);

  const previewMutation = useMutation({
    mutationFn: async ({
      prospectId,
      selectedTemplateKey,
      selectedMessageKey,
    }: {
      prospectId: string;
      selectedTemplateKey: string;
      selectedMessageKey: string;
    }) =>
      (
        await api.post<MessagePreview>("/admin/clinic-messages/preview", {
          prospect_id: prospectId,
          template_key: selectedTemplateKey || null,
          message_key: selectedMessageKey || null,
          issue_demo_access: true,
        })
      ).data,
    onSuccess: (data) => {
      setPreview(data);
      setTemplateKey(data.template_key);
      setMessageKey(data.message_key);
      queryClient.invalidateQueries({ queryKey: ["adm-clinic-messages"] });
      queryClient.invalidateQueries({ queryKey: ["adm-prospects"] });
    },
    onError: (error) => {
      toast.error(extractApiErrorMessage(error, "Nao foi possivel gerar a mensagem."));
    },
  });

  const eventMutation = useMutation({
    mutationFn: async ({
      prospectId,
      eventName,
      currentPreview,
      note,
    }: {
      prospectId: string;
      eventName: "message_copied" | "demo_link_copied" | "contact_registered";
      currentPreview?: MessagePreview | null;
      note?: string | null;
    }) =>
      (
        await api.post(`/admin/clinic-messages/${prospectId}/events`, {
          event_name: eventName,
          template_key: currentPreview?.template_key || templateKey || null,
          message_key: currentPreview?.message_key || messageKey || null,
          message_snapshot: currentPreview?.message_text || null,
          demo_login_url: currentPreview?.demo_login_url || null,
          channel: "whatsapp_manual",
          note,
        })
      ).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["adm-clinic-messages"] });
      queryClient.invalidateQueries({ queryKey: ["adm-prospects"] });
    },
    onError: (error) => {
      toast.error(extractApiErrorMessage(error, "Nao foi possivel registrar o evento."));
    },
  });

  const saveTemplateMutation = useMutation({
    mutationFn: async ({ draft, originalKey }: { draft: TemplateDraft; originalKey: string | null }) => {
      const payload = draftToPayload(draft);
      if (originalKey) {
        return (await api.put<SalesTemplate>(`/admin/clinic-messages/templates/${originalKey}`, payload)).data;
      }
      return (await api.post<SalesTemplate>("/admin/clinic-messages/templates", payload)).data;
    },
    onSuccess: (template) => {
      toast.success("Template salvo.");
      setEditingTemplateKey(template.key);
      setTemplateDraft(templateToDraft(template));
      setTemplateKey(template.key);
      queryClient.invalidateQueries({ queryKey: ["adm-clinic-message-templates"] });
      queryClient.invalidateQueries({ queryKey: ["adm-clinic-messages"] });
    },
    onError: (error) => {
      toast.error(extractApiErrorMessage(error, "Nao foi possivel salvar o template."));
    },
  });

  const deleteTemplateMutation = useMutation({
    mutationFn: async (targetKey: string) =>
      (await api.delete<SalesTemplate[]>(`/admin/clinic-messages/templates/${targetKey}`)).data,
    onSuccess: (templatesAfterDelete) => {
      toast.success("Template removido.");
      const nextTemplate = templatesAfterDelete[0] ?? null;
      setEditingTemplateKey(nextTemplate?.key ?? null);
      setTemplateDraft(templateToDraft(nextTemplate));
      queryClient.invalidateQueries({ queryKey: ["adm-clinic-message-templates"] });
      queryClient.invalidateQueries({ queryKey: ["adm-clinic-messages"] });
    },
    onError: (error) => {
      toast.error(extractApiErrorMessage(error, "Nao foi possivel remover o template."));
    },
  });

  const totals = useMemo(() => {
    const withDemo = items.filter((item) => item.demo_ready).length;
    const blocked = items.filter((item) => item.prospect.do_not_contact).length;
    const hot = items.filter((item) => ["quente", "muito_quente"].includes(item.prospect.temperature)).length;
    return { withDemo, blocked, hot };
  }, [items]);

  function selectTemplateForEditing(template: SalesTemplate) {
    setEditingTemplateKey(template.key);
    setTemplateDraft(templateToDraft(template));
  }

  function startNewTemplate() {
    setEditingTemplateKey(null);
    setTemplateDraft(templateToDraft(null));
    setViewMode("templates");
  }

  function updateTemplateDraft(patch: Partial<TemplateDraft>) {
    setTemplateDraft((current) => (current ? { ...current, ...patch } : current));
  }

  function updateTemplateMessage(index: number, patch: Partial<SalesTemplateMessage>) {
    setTemplateDraft((current) => {
      if (!current) return current;
      const messages = current.messages.map((message, messageIndex) =>
        messageIndex === index ? { ...message, ...patch } : message,
      );
      if (patch.is_default) {
        messages.forEach((message, messageIndex) => {
          message.is_default = messageIndex === index;
        });
      }
      return { ...current, messages };
    });
  }

  function addTemplateMessage() {
    setTemplateDraft((current) => {
      if (!current) return current;
      return {
        ...current,
        messages: [...current.messages, newTemplateMessage(current.messages.length)],
      };
    });
  }

  function removeTemplateMessage(index: number) {
    setTemplateDraft((current) => {
      if (!current || current.messages.length <= 1) return current;
      const messages = current.messages.filter((_message, messageIndex) => messageIndex !== index);
      if (!messages.some((message) => message.is_default)) {
        messages[0].is_default = true;
      }
      return { ...current, messages };
    });
  }

  function saveTemplateDraft() {
    if (!templateDraft) return;
    saveTemplateMutation.mutate({ draft: templateDraft, originalKey: editingTemplateKey });
  }

  function deleteCurrentTemplate() {
    if (!editingTemplateKey) return;
    if (!window.confirm("Remover este template de mensagens?")) return;
    deleteTemplateMutation.mutate(editingTemplateKey);
  }

  async function generatePreview(copyAfter = false) {
    if (!selectedItem) return;
    try {
      const data = await previewMutation.mutateAsync({
        prospectId: selectedItem.prospect.id,
        selectedTemplateKey: templateKey || selectedItem.suggested_template_key,
        selectedMessageKey: messageKey || selectedTemplateMessage?.key || "",
      });
      if (copyAfter) await copyMessage(data);
    } catch {
      return;
    }
  }

  async function copyMessage(currentPreview = preview) {
    if (!selectedItem || !currentPreview) {
      await generatePreview(true);
      return;
    }
    if (!currentPreview.can_copy) {
      toast.error(currentPreview.warnings[0] || "Esta mensagem ainda nao pode ser copiada.");
      return;
    }
    await copyToClipboard(currentPreview.message_text);
    try {
      await eventMutation.mutateAsync({
        prospectId: selectedItem.prospect.id,
        eventName: "message_copied",
        currentPreview,
      });
      toast.success("Mensagem completa copiada.");
    } catch {
      return;
    }
  }

  async function copyDemoLink() {
    if (!selectedItem || !preview?.demo_login_url) {
      toast.error("Gere a mensagem para emitir um link de demo primeiro.");
      return;
    }
    await copyToClipboard(preview.demo_login_url);
    try {
      await eventMutation.mutateAsync({
        prospectId: selectedItem.prospect.id,
        eventName: "demo_link_copied",
        currentPreview: preview,
      });
      toast.success("Link da demo copiado.");
    } catch {
      return;
    }
  }

  async function markContactDone() {
    if (!selectedItem) return;
    try {
      await eventMutation.mutateAsync({
        prospectId: selectedItem.prospect.id,
        eventName: "contact_registered",
        currentPreview: preview,
        note: "Contato manual registrado pela pagina de mensagens para clinicas.",
      });
      toast.success("Contato registrado na timeline.");
    } catch {
      return;
    }
  }

  if (!hasToken) {
    return (
      <main className="min-h-screen overflow-x-hidden bg-stone-100 p-6 text-stone-950">
        <Card className="mx-auto mt-20 max-w-xl border-stone-200 bg-white">
          <CardContent className="space-y-4 p-6">
            <div className="grid h-12 w-12 place-items-center rounded-xl bg-stone-950 text-sm font-black text-white">
              CF
            </div>
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-stone-500">Area interna</p>
              <h1 className="mt-1 text-2xl font-black">Entre no /adm primeiro</h1>
              <p className="mt-2 text-sm leading-6 text-stone-600">
                Esta central usa o mesmo login administrativo do CRM comercial.
              </p>
            </div>
            <Link
              href="/adm"
              className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-stone-950 px-4 text-sm font-bold text-white"
            >
              Abrir login do /adm
              <ArrowLeft className="h-4 w-4 rotate-180" />
            </Link>
          </CardContent>
        </Card>
      </main>
    );
  }

  if (admSessionQuery.isLoading) {
    return (
      <main className="grid min-h-screen place-items-center overflow-x-hidden bg-stone-100 px-4 text-stone-950">
        <Card className="w-full max-w-md border-stone-200 bg-white">
          <CardContent className="p-8 text-center text-sm text-stone-600">Carregando permissoes...</CardContent>
        </Card>
      </main>
    );
  }

  if (!canViewMessages) {
    return (
      <main className="grid min-h-screen place-items-center overflow-x-hidden bg-stone-100 px-4 text-stone-950">
        <Card className="w-full max-w-md border-stone-200 bg-white">
          <CardContent className="space-y-4 p-8 text-center">
            <AlertTriangle className="mx-auto h-9 w-9 text-stone-400" />
            <h1 className="text-xl font-black">Area sem permissao</h1>
            <p className="text-sm leading-6 text-stone-600">Seu usuario nao tem acesso a Mensagens prontas.</p>
            <Link className="inline-flex h-10 items-center rounded-lg bg-stone-950 px-4 text-sm font-bold text-white" href="/adm">
              Voltar ao /adm
            </Link>
          </CardContent>
        </Card>
      </main>
    );
  }

  return (
    <main className="min-h-screen overflow-x-hidden bg-[#f5f2ea] text-stone-950">
      <header className="sticky top-0 z-20 border-b border-stone-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-3 px-4 py-4 lg:flex-row lg:items-center lg:justify-between lg:px-5">
          <div className="flex items-center gap-3">
            <Link
              href="/adm"
              className="grid h-10 w-10 place-items-center rounded-xl border border-stone-200 bg-white text-stone-700 transition hover:bg-stone-100"
            >
              <ArrowLeft size={18} />
            </Link>
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.2em] text-stone-500">
                Admin comercial
              </p>
              <h1 className="text-xl font-black">Mensagens para clinicas</h1>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => messagesQuery.refetch()}>
              <RefreshCw size={16} />
              Atualizar
            </Button>
            <Link
              href="/adm"
              className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-stone-200 bg-white px-4 text-sm font-bold text-stone-800 transition hover:bg-stone-100"
            >
              Voltar ao CRM
            </Link>
          </div>
        </div>
      </header>

      <div className="mx-auto w-full max-w-[1600px] space-y-4 px-4 py-5 lg:px-5">
        <section className="overflow-hidden rounded-2xl border border-stone-200 bg-stone-950 text-white shadow-sm">
          <div className="grid gap-4 p-5 lg:grid-cols-[1fr_420px] lg:p-7">
            <div>
              <Badge className="border-white/10 bg-white/10 text-white">Copiar, enviar, rastrear</Badge>
              <h2 className="mt-4 max-w-3xl text-3xl font-black tracking-tight lg:text-4xl">
                Uma central para montar a primeira mensagem de cada clinica com a demo no final.
              </h2>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-stone-300">
                Ela usa os dados que voce ja cadastra no CRM: nome da clinica, dono,
                dor percebida, status, WhatsApp e demo criada. Voce escolhe a clinica,
                gera a mensagem pronta e copia tudo para enviar manualmente.
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
              <MiniMetric icon={<Building2 size={18} />} label="Filtradas" value={messagesQuery.data?.total ?? 0} />
              <MiniMetric icon={<ShieldCheck size={18} />} label="Com demo" value={totals.withDemo} />
              <MiniMetric icon={<Sparkles size={18} />} label="Quentes" value={totals.hot} />
            </div>
          </div>
        </section>

        <div className="flex flex-wrap gap-2 rounded-2xl border border-stone-200 bg-white p-2">
          <Button
            variant={viewMode === "clinics" ? "default" : "ghost"}
            className={cn(viewMode === "clinics" && "bg-stone-950 text-white hover:bg-stone-800")}
            onClick={() => setViewMode("clinics")}
          >
            <MessageSquareText size={16} />
            Mensagens por clinica
          </Button>
          <Button
            variant={viewMode === "templates" ? "default" : "ghost"}
            className={cn(viewMode === "templates" && "bg-emerald-600 text-white hover:bg-emerald-500")}
            onClick={() => setViewMode("templates")}
          >
            <Save size={16} />
            Editar templates
          </Button>
          <Button variant="outline" onClick={startNewTemplate} disabled={!canCreateMessages}>
            <Plus size={16} />
            Novo template
          </Button>
        </div>

        {viewMode === "templates" ? (
          <TemplateEditorPanel
            templates={templates}
            editingTemplateKey={editingTemplateKey}
            templateDraft={templateDraft}
            onSelectTemplate={selectTemplateForEditing}
            onNewTemplate={startNewTemplate}
            onDraftChange={updateTemplateDraft}
            onMessageChange={updateTemplateMessage}
            onAddMessage={addTemplateMessage}
            onRemoveMessage={removeTemplateMessage}
            onSave={saveTemplateDraft}
            onDelete={deleteCurrentTemplate}
            saving={saveTemplateMutation.isPending}
            deleting={deleteTemplateMutation.isPending}
            canCreate={canCreateMessages}
            canEdit={canEditMessages}
            canDelete={canDeleteMessages}
          />
        ) : (
        <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_560px]">
          <div className="space-y-4">
            <Card className="border-stone-200 bg-white">
              <CardContent className="space-y-3 p-4">
                <div className="grid gap-3 lg:grid-cols-[1fr_180px_160px_160px_140px]">
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" />
                    <Input
                      className="pl-9"
                      placeholder="Buscar clinica, dono, cidade ou telefone"
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                    />
                  </div>
                  <FilterSelect value={statusFilter} onChange={setStatusFilter} label="Todos os status">
                    {STATUS_OPTIONS.map((status) => (
                      <option key={status} value={status}>
                        {humanize(status)}
                      </option>
                    ))}
                  </FilterSelect>
                  <FilterSelect value={temperatureFilter} onChange={setTemperatureFilter} label="Temperatura">
                    {TEMPERATURE_OPTIONS.map((item) => (
                      <option key={item} value={item}>
                        {humanize(item)}
                      </option>
                    ))}
                  </FilterSelect>
                  <FilterSelect value={demoStatusFilter} onChange={setDemoStatusFilter} label="Demo">
                    {DEMO_STATUS_OPTIONS.map((item) => (
                      <option key={item} value={item}>
                        {humanize(item)}
                      </option>
                    ))}
                  </FilterSelect>
                  <FilterSelect value={hasDemoFilter} onChange={setHasDemoFilter} label="Link">
                    <option value="sim">Com demo</option>
                    <option value="nao">Sem demo</option>
                  </FilterSelect>
                </div>
                {totals.blocked ? (
                  <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800">
                    <AlertTriangle size={15} />
                    {totals.blocked} clinica(s) filtrada(s) estao marcadas como nao contactar.
                  </div>
                ) : null}
              </CardContent>
            </Card>

            <div className="overflow-hidden rounded-2xl border border-stone-200 bg-white">
              <div className="hidden grid-cols-[1.3fr_0.8fr_0.7fr_0.7fr_0.9fr] gap-3 border-b border-stone-200 bg-stone-50 px-4 py-3 text-xs font-bold uppercase tracking-wide text-stone-500 md:grid">
                <span>Clinica</span>
                <span>Status</span>
                <span>Temp.</span>
                <span>Demo</span>
                <span>Ultima acao</span>
              </div>
              <div className="max-h-[680px] overflow-auto">
                {messagesQuery.isLoading ? (
                  <div className="p-6 text-sm text-stone-500">Carregando mensagens...</div>
                ) : items.length ? (
                  items.map((item) => {
                    const selected = selectedItem?.prospect.id === item.prospect.id;
                    return (
                      <button
                        key={item.prospect.id}
                        type="button"
                        onClick={() => setSelectedId(item.prospect.id)}
                        className={cn(
                          "grid w-full gap-3 border-b border-stone-100 px-4 py-4 text-left text-sm transition hover:bg-stone-50 md:grid-cols-[1.3fr_0.8fr_0.7fr_0.7fr_0.9fr]",
                          selected && "bg-emerald-50/80",
                        )}
                      >
                        <span className="min-w-0">
                          <span className="block truncate font-black text-stone-950">{item.prospect.clinic_name}</span>
                          <span className="mt-1 flex items-center gap-1 truncate text-xs text-stone-500">
                            <PhoneCall size={13} />
                            {item.whatsapp_destination || "Sem WhatsApp"}
                          </span>
                        </span>
                        <span>
                          <Badge className={statusClass(item.prospect.status)}>{humanize(item.prospect.status)}</Badge>
                        </span>
                        <span>
                          <Badge className={temperatureClass(item.prospect.temperature)}>
                            {humanize(item.prospect.temperature)}
                          </Badge>
                        </span>
                        <span className="text-xs font-semibold text-stone-700">
                          {item.demo_ready ? humanize(item.prospect.demo_status) : "Sem demo"}
                        </span>
                        <span className="min-w-0 text-xs text-stone-500">
                          {item.last_event_at ? formatDateTimeBR(item.last_event_at) : "Ainda nao copiou"}
                        </span>
                      </button>
                    );
                  })
                ) : (
                  <div className="p-8 text-center text-sm text-stone-500">
                    Nenhuma clinica encontrada com os filtros atuais.
                  </div>
                )}
              </div>
            </div>
          </div>

          <aside className="space-y-4">
            <Card className="border-stone-200 bg-white">
              <CardContent className="space-y-5 p-5">
                {selectedItem ? (
                  <>
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-xs font-bold uppercase tracking-[0.18em] text-stone-500">
                          Mensagem selecionada
                        </p>
                        <h2 className="mt-1 text-2xl font-black">{selectedItem.prospect.clinic_name}</h2>
                        <p className="mt-1 text-sm text-stone-600">
                          {selectedItem.prospect.city || "Cidade nao informada"}
                          {selectedItem.prospect.state ? ` - ${selectedItem.prospect.state}` : ""}
                        </p>
                      </div>
                      <Badge className={temperatureClass(selectedItem.prospect.temperature)}>
                        {humanize(selectedItem.prospect.temperature)}
                      </Badge>
                    </div>

                    <div className="grid gap-3 sm:grid-cols-2">
                      <InfoBlock label="Contato" value={selectedItem.contact_name} icon={<MessageSquareText size={16} />} />
                      <InfoBlock
                        label="WhatsApp"
                        value={selectedItem.whatsapp_destination || "Nao cadastrado"}
                        icon={<PhoneCall size={16} />}
                      />
                      <InfoBlock
                        label="Dor percebida"
                        value={selectedItem.prospect.main_pain || "Nao informada"}
                        icon={<Sparkles size={16} />}
                      />
                      <InfoBlock
                        label="Demo"
                        value={selectedItem.demo_ready ? humanize(selectedItem.prospect.demo_status) : "Gere a demo antes"}
                        icon={<ShieldCheck size={16} />}
                      />
                    </div>

                    <label className="block space-y-2">
                      <span className="text-xs font-bold uppercase tracking-wide text-stone-500">Template</span>
                      <select
                        className="h-11 w-full rounded-lg border border-stone-200 bg-white px-3 text-sm font-semibold text-stone-800"
                        value={templateKey}
                        onChange={(event) => {
                          setTemplateKey(event.target.value);
                          const nextTemplate = templates.find((template) => template.key === event.target.value);
                          const nextMessage =
                            nextTemplate?.messages.find((message) => message.is_default) ?? nextTemplate?.messages[0];
                          setMessageKey(nextMessage?.key ?? "");
                          setPreview(null);
                        }}
                      >
                        {templates.map((template) => (
                          <option key={template.key} value={template.key}>
                            {template.label}
                          </option>
                        ))}
                      </select>
                      <span className="block text-xs leading-5 text-stone-500">
                        Sugestao do sistema: {humanize(selectedItem.suggested_template_key)}.
                      </span>
                    </label>

                    <label className="block space-y-2">
                      <span className="text-xs font-bold uppercase tracking-wide text-stone-500">
                        Mensagem dentro do template
                      </span>
                      <select
                        className="h-11 w-full rounded-lg border border-stone-200 bg-white px-3 text-sm font-semibold text-stone-800"
                        value={messageKey}
                        onChange={(event) => {
                          setMessageKey(event.target.value);
                          setPreview(null);
                        }}
                      >
                        {(selectedTemplate?.messages ?? []).map((message) => (
                          <option key={message.key} value={message.key}>
                            {message.label}
                          </option>
                        ))}
                      </select>
                      <span className="block text-xs leading-5 text-stone-500">
                        Para alterar ou criar mensagens, abra a aba Editar templates acima.
                      </span>
                    </label>

                    <div className="flex flex-col gap-2 sm:flex-row">
                      <Button
                        className="flex-1 bg-emerald-600 text-white hover:bg-emerald-500"
                        onClick={() => generatePreview(false)}
                        disabled={!canCreateMessages || previewMutation.isPending || !selectedItem.demo_ready}
                      >
                        <Send size={16} />
                        {previewMutation.isPending ? "Gerando..." : "Gerar mensagem pronta"}
                      </Button>
                      <Button
                        variant="outline"
                        className="flex-1"
                        onClick={() => copyMessage()}
                        disabled={!canCreateMessages || previewMutation.isPending || eventMutation.isPending}
                      >
                        <Copy size={16} />
                        Copiar mensagem
                      </Button>
                    </div>

                    {!selectedItem.demo_ready ? (
                      <WarningBox text="Esta clinica ainda nao tem demo criada. Volte ao CRM, clique em Gerar demo e depois retorne para copiar a mensagem com link." />
                    ) : null}
                    {selectedItem.copy_blocked_reason ? <WarningBox text={selectedItem.copy_blocked_reason} /> : null}
                    {preview?.warnings.map((warning) => <WarningBox key={warning} text={warning} />)}

                    <textarea
                      className="min-h-[290px] w-full resize-none rounded-2xl border border-stone-200 bg-stone-50 p-4 font-mono text-sm leading-6 text-stone-800 outline-none transition focus:border-emerald-400 focus:bg-white"
                      value={
                        preview?.message_text ||
                        "Clique em Gerar mensagem pronta para criar o texto com a demo no final."
                      }
                      readOnly
                    />

                    <div className="grid gap-2 sm:grid-cols-3">
                      <Button variant="outline" onClick={copyDemoLink} disabled={!canCreateMessages || !preview?.demo_login_url}>
                        <ExternalLink size={16} />
                        Copiar link
                      </Button>
                      <Button variant="outline" onClick={markContactDone} disabled={!canCreateMessages || eventMutation.isPending}>
                        <CheckCircle2 size={16} />
                        Marcar contato
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => generatePreview(true)}
                        disabled={!canCreateMessages || previewMutation.isPending || !selectedItem.demo_ready}
                      >
                        <Clipboard size={16} />
                        Gerar e copiar
                      </Button>
                    </div>

                    {preview?.demo_login_url ? (
                      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-900">
                        <p className="font-bold">Link emitido para esta mensagem</p>
                        <p className="mt-1 break-all">{preview.demo_login_url}</p>
                      </div>
                    ) : null}
                  </>
                ) : (
                  <div className="py-16 text-center">
                    <MessageSquareText className="mx-auto h-10 w-10 text-stone-400" />
                    <h2 className="mt-3 text-xl font-black">Selecione uma clinica</h2>
                    <p className="mt-2 text-sm text-stone-500">
                      A mensagem pronta aparece aqui assim que voce escolher uma linha.
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </aside>
        </section>
        )}
      </div>
    </main>
  );
}

function TemplateEditorPanel({
  templates,
  editingTemplateKey,
  templateDraft,
  onSelectTemplate,
  onNewTemplate,
  onDraftChange,
  onMessageChange,
  onAddMessage,
  onRemoveMessage,
  onSave,
  onDelete,
  saving,
  deleting,
  canCreate,
  canEdit,
  canDelete,
}: {
  templates: SalesTemplate[];
  editingTemplateKey: string | null;
  templateDraft: TemplateDraft | null;
  onSelectTemplate: (template: SalesTemplate) => void;
  onNewTemplate: () => void;
  onDraftChange: (patch: Partial<TemplateDraft>) => void;
  onMessageChange: (index: number, patch: Partial<SalesTemplateMessage>) => void;
  onAddMessage: () => void;
  onRemoveMessage: (index: number) => void;
  onSave: () => void;
  onDelete: () => void;
  saving: boolean;
  deleting: boolean;
  canCreate: boolean;
  canEdit: boolean;
  canDelete: boolean;
}) {
  const canSaveCurrent = editingTemplateKey ? canEdit : canCreate;
  return (
    <section className="grid gap-4 xl:grid-cols-[390px_minmax(0,1fr)]">
      <Card className="border-stone-200 bg-white">
        <CardContent className="space-y-4 p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-stone-500">Biblioteca</p>
              <h2 className="text-xl font-black">Templates</h2>
            </div>
            <Button variant="outline" onClick={onNewTemplate} disabled={!canCreate}>
              <Plus size={16} />
              Novo
            </Button>
          </div>
          <div className="max-h-[720px] space-y-2 overflow-auto pr-1">
            {templates.map((template) => (
              <button
                key={template.key}
                type="button"
                onClick={() => onSelectTemplate(template)}
                className={cn(
                  "w-full rounded-2xl border p-4 text-left transition hover:bg-stone-50",
                  editingTemplateKey === template.key
                    ? "border-emerald-300 bg-emerald-50"
                    : "border-stone-200 bg-white",
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-black text-stone-950">{template.label}</p>
                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-stone-500">{template.description}</p>
                  </div>
                  <Badge className="border-stone-200 bg-stone-100 text-stone-700">
                    {template.messages.length} msg
                  </Badge>
                </div>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card className="border-stone-200 bg-white">
        <CardContent className="space-y-5 p-5">
          {templateDraft ? (
            <>
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.18em] text-stone-500">
                    Editor de template
                  </p>
                  <h2 className="mt-1 text-2xl font-black">
                    {editingTemplateKey ? "Editar template existente" : "Criar novo template"}
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-stone-600">
                    Use variaveis como <code>{"{clinic_name}"}</code>, <code>{"{contact_name}"}</code>,{" "}
                    <code>{"{pain_sentence}"}</code> e <code>{"{demo_link}"}</code>. O link da demo fica seguro e
                    temporario quando a mensagem e gerada.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    className="bg-emerald-600 text-white hover:bg-emerald-500"
                    onClick={onSave}
                    disabled={!canSaveCurrent || saving || !templateDraft.label.trim()}
                  >
                    <Save size={16} />
                    {saving ? "Salvando..." : "Salvar template"}
                  </Button>
                  {editingTemplateKey ? (
                    <Button variant="outline" onClick={onDelete} disabled={!canDelete || deleting}>
                      <Trash2 size={16} />
                      Excluir
                    </Button>
                  ) : null}
                </div>
              </div>

              <div className="grid gap-3 lg:grid-cols-[220px_1fr]">
                <label className="block space-y-2">
                  <span className="text-xs font-bold uppercase tracking-wide text-stone-500">Chave</span>
                  <Input
                    value={templateDraft.key}
                    onChange={(event) => onDraftChange({ key: event.target.value })}
                    placeholder="primeiro_contato"
                    disabled={Boolean(editingTemplateKey) || !canSaveCurrent}
                  />
                  <span className="block text-xs text-stone-500">
                    A chave fica travada depois de salvar para nao quebrar historico.
                  </span>
                </label>
                <label className="block space-y-2">
                  <span className="text-xs font-bold uppercase tracking-wide text-stone-500">Nome do template</span>
                  <Input
                    value={templateDraft.label}
                    onChange={(event) => onDraftChange({ label: event.target.value })}
                    placeholder="Primeira mensagem"
                    disabled={!canSaveCurrent}
                  />
                </label>
              </div>

              <label className="block space-y-2">
                <span className="text-xs font-bold uppercase tracking-wide text-stone-500">Descricao</span>
                <Input
                  value={templateDraft.description}
                  onChange={(event) => onDraftChange({ description: event.target.value })}
                  placeholder="Quando usar este template"
                  disabled={!canSaveCurrent}
                />
              </label>

              <label className="block space-y-2">
                <span className="text-xs font-bold uppercase tracking-wide text-stone-500">
                  Status recomendados
                </span>
                <Input
                  value={templateDraft.recommended_for_text}
                  onChange={(event) => onDraftChange({ recommended_for_text: event.target.value })}
                  placeholder="novo, pesquisado, demo_acessada"
                  disabled={!canSaveCurrent}
                />
                <span className="block text-xs text-stone-500">
                  Separe por virgula. Isso ajuda o sistema a sugerir o template certo para cada clinica.
                </span>
              </label>

              <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.18em] text-stone-500">
                      Mensagens deste template
                    </p>
                    <h3 className="text-lg font-black">Crie quantas variacoes quiser</h3>
                  </div>
                  <Button variant="outline" onClick={onAddMessage} disabled={!canSaveCurrent}>
                    <Plus size={16} />
                    Adicionar mensagem
                  </Button>
                </div>

                <div className="mt-4 space-y-4">
                  {templateDraft.messages.map((message, index) => (
                    <div key={`${message.key}-${index}`} className="rounded-2xl border border-stone-200 bg-white p-4">
                      <div className="grid gap-3 lg:grid-cols-[190px_1fr_auto]">
                        <label className="block space-y-2">
                          <span className="text-xs font-bold uppercase tracking-wide text-stone-500">Chave</span>
                          <Input
                            value={message.key}
                            onChange={(event) => onMessageChange(index, { key: event.target.value })}
                            placeholder="principal"
                            disabled={!canSaveCurrent}
                          />
                        </label>
                        <label className="block space-y-2">
                          <span className="text-xs font-bold uppercase tracking-wide text-stone-500">Nome</span>
                          <Input
                            value={message.label}
                            onChange={(event) => onMessageChange(index, { label: event.target.value })}
                            placeholder="Mensagem principal"
                            disabled={!canSaveCurrent}
                          />
                        </label>
                        <div className="flex items-end gap-2">
                          <label className="flex h-10 items-center gap-2 rounded-lg border border-stone-200 px-3 text-xs font-bold text-stone-600">
                            <input
                              type="checkbox"
                              checked={message.is_default}
                              onChange={(event) => onMessageChange(index, { is_default: event.target.checked })}
                              disabled={!canSaveCurrent}
                            />
                            Padrao
                          </label>
                          <Button
                            variant="outline"
                            onClick={() => onRemoveMessage(index)}
                            disabled={!canSaveCurrent || templateDraft.messages.length <= 1}
                          >
                            <Trash2 size={16} />
                          </Button>
                        </div>
                      </div>
                      <label className="mt-3 block space-y-2">
                        <span className="text-xs font-bold uppercase tracking-wide text-stone-500">
                          Texto da mensagem
                        </span>
                        <textarea
                          className="min-h-[220px] w-full resize-y rounded-2xl border border-stone-200 bg-stone-50 p-4 font-mono text-sm leading-6 text-stone-800 outline-none transition focus:border-emerald-400 focus:bg-white"
                          value={message.body}
                          onChange={(event) => onMessageChange(index, { body: event.target.value })}
                          disabled={!canSaveCurrent}
                        />
                      </label>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div className="py-16 text-center text-stone-500">Carregando editor de templates...</div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function MiniMetric({ icon, label, value }: { icon: ReactNode; label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/10 p-4">
      <div className="flex items-center justify-between text-white/70">
        <span className="text-xs font-bold uppercase tracking-wide">{label}</span>
        {icon}
      </div>
      <p className="mt-2 text-2xl font-black text-white">{value}</p>
    </div>
  );
}

function InfoBlock({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-stone-200 bg-stone-50 p-3">
      <div className="flex items-center gap-2 text-stone-500">
        {icon}
        <span className="text-xs font-bold uppercase tracking-wide">{label}</span>
      </div>
      <p className="mt-2 line-clamp-2 text-sm font-bold text-stone-900">{value}</p>
    </div>
  );
}

function FilterSelect({
  value,
  onChange,
  label,
  children,
}: {
  value: string;
  onChange: (value: string) => void;
  label: string;
  children: ReactNode;
}) {
  return (
    <select
      className="h-10 rounded-lg border border-stone-200 bg-white px-3 text-sm font-semibold text-stone-700"
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{label}</option>
      {children}
    </select>
  );
}

function WarningBox({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold leading-5 text-amber-900">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{text}</span>
    </div>
  );
}

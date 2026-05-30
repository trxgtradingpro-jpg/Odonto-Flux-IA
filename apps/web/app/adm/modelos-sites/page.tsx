"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle2,
  Clipboard,
  Copy,
  ExternalLink,
  Eye,
  Globe2,
  Lock,
  MousePointer2,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { toast } from "sonner";

import { useAdmSession } from "@/hooks/use-adm-session";
import { canAccessAdmPage } from "@/lib/adm-page-access";
import { api } from "@/lib/api";
import { getAdminAccessToken } from "@/lib/auth";
import {
  SITE_TEMPLATE_CATALOG_PATH,
  SITE_TEMPLATE_LIBRARY_VERSION,
  SITE_TEMPLATES,
  buildSiteTemplatePreviewPath,
  buildSiteTemplateSelectionSnapshot,
  getSiteTemplateBySlug,
} from "@/lib/site-templates";
import { cn } from "@odontoflux/ui";

type Prospect = {
  id: string;
  clinic_name: string;
  owner_name?: string | null;
  manager_name?: string | null;
  phone?: string | null;
  whatsapp_phone?: string | null;
  city?: string | null;
  state?: string | null;
  status: string;
  temperature: string;
  demo_status: string;
  proposal_snapshot: Record<string, unknown>;
};

type ProspectListResponse = {
  data: Prospect[];
  total: number;
  limit: number;
  offset: number;
};

const LIBRARY_STORAGE_KEY = "clinicflux.siteTemplateStudio.libraryReady";

function extractApiErrorMessage(error: unknown, fallback: string) {
  const response = (
    error as {
      response?: {
        data?: {
          error?: {
            message?: string;
          };
        };
      };
    }
  ).response;
  return response?.data?.error?.message?.trim() || fallback;
}

function selectedTemplateSlugFromProspect(prospect: Prospect | null | undefined) {
  const raw = prospect?.proposal_snapshot?.site_template;
  if (!raw || typeof raw !== "object") return "";
  const slug = (raw as { selected_template_slug?: unknown }).selected_template_slug;
  return typeof slug === "string" ? slug : "";
}

function absoluteUrl(origin: string, path: string) {
  const normalizedOrigin = origin.replace(/\/$/, "") || "http://localhost:3000";
  return `${normalizedOrigin}${path.startsWith("/") ? path : `/${path}`}`;
}

async function copyText(value: string, successMessage: string) {
  await navigator.clipboard.writeText(value);
  toast.success(successMessage);
}

export default function AdmSiteTemplatesPage() {
  const queryClient = useQueryClient();
  const [hasToken, setHasToken] = useState(false);
  const [appOrigin, setAppOrigin] = useState("");
  const [libraryReady, setLibraryReady] = useState(false);
  const [selectedTemplateSlug, setSelectedTemplateSlug] = useState(SITE_TEMPLATES[0]?.slug || "");
  const [selectedProspectId, setSelectedProspectId] = useState("");

  useEffect(() => {
    setHasToken(Boolean(getAdminAccessToken()));
    setAppOrigin(window.location.origin);
    setLibraryReady(window.localStorage.getItem(LIBRARY_STORAGE_KEY) === "true");
  }, []);

  const admSessionQuery = useAdmSession(hasToken);
  const admPermissions = admSessionQuery.data?.resolved_adm_page_permissions;
  const canViewPage = canAccessAdmPage(admPermissions, "adm_site_templates", "view");
  const canCreatePage = canAccessAdmPage(admPermissions, "adm_site_templates", "create");
  const canEditPage = canAccessAdmPage(admPermissions, "adm_site_templates", "edit");
  const canViewCrm = canAccessAdmPage(admPermissions, "adm_crm", "view");
  const canEditCrm = canAccessAdmPage(admPermissions, "adm_crm", "edit");
  const canSelectForProspect = canEditPage && canEditCrm;

  const prospectsQuery = useQuery<ProspectListResponse>({
    queryKey: ["adm-site-template-prospects"],
    queryFn: async () => (await api.get("/admin/prospects", { params: { limit: 250 } })).data,
    enabled: hasToken && canViewPage && canViewCrm,
    retry: false,
  });

  const prospects = useMemo(() => prospectsQuery.data?.data ?? [], [prospectsQuery.data?.data]);
  const selectedTemplate = getSiteTemplateBySlug(selectedTemplateSlug) ?? SITE_TEMPLATES[0];
  const selectedProspect = useMemo(
    () => prospects.find((prospect) => prospect.id === selectedProspectId) ?? prospects[0] ?? null,
    [prospects, selectedProspectId],
  );

  useEffect(() => {
    if (!selectedProspectId && selectedProspect) {
      setSelectedProspectId(selectedProspect.id);
    }
  }, [selectedProspect, selectedProspectId]);

  useEffect(() => {
    const prospectSlug = selectedTemplateSlugFromProspect(selectedProspect);
    if (prospectSlug && getSiteTemplateBySlug(prospectSlug)) {
      setSelectedTemplateSlug(prospectSlug);
    }
  }, [selectedProspect]);

  const personalizedPreviewPath =
    selectedTemplate && selectedProspect
      ? buildSiteTemplatePreviewPath(selectedTemplate, {
          clinic: selectedProspect.clinic_name,
          city: selectedProspect.city,
          whatsapp: selectedProspect.whatsapp_phone || selectedProspect.phone,
        })
      : selectedTemplate
        ? buildSiteTemplatePreviewPath(selectedTemplate)
        : SITE_TEMPLATE_CATALOG_PATH;

  const selectMutation = useMutation({
    mutationFn: async () => {
      if (!selectedTemplate || !selectedProspect) throw new Error("Selecione template e prospect.");
      const selectedAt = new Date().toISOString();
      const snapshot = buildSiteTemplateSelectionSnapshot(selectedTemplate, selectedAt, {
        clinic: selectedProspect.clinic_name,
        city: selectedProspect.city,
        whatsapp: selectedProspect.whatsapp_phone || selectedProspect.phone,
      });
      return (
        await api.patch(`/admin/prospects/${selectedProspect.id}`, {
          proposal_snapshot: {
            ...(selectedProspect.proposal_snapshot || {}),
            site_template: snapshot,
          },
        })
      ).data;
    },
    onSuccess: () => {
      toast.success("Template selecionado e salvo no prospect.");
      queryClient.invalidateQueries({ queryKey: ["adm-site-template-prospects"] });
    },
    onError: (error) => toast.error(extractApiErrorMessage(error, "Nao foi possivel salvar a selecao.")),
  });

  function handleCreateLibrary() {
    window.localStorage.setItem(LIBRARY_STORAGE_KEY, "true");
    setLibraryReady(true);
    toast.success("Biblioteca inicial criada com 10 templates profissionais.");
  }

  if (!hasToken) {
    return (
      <main className="grid min-h-screen place-items-center bg-stone-100 px-4 text-stone-950">
        <div className="w-full max-w-md rounded-lg border border-stone-200 bg-white p-8 shadow-sm">
          <Lock className="h-9 w-9 text-stone-400" />
          <h1 className="mt-4 text-xl font-black">Entre no /adm primeiro</h1>
          <Link className="mt-5 inline-flex h-10 items-center rounded-lg bg-stone-950 px-4 text-sm font-bold text-white" href="/adm">
            Abrir login
          </Link>
        </div>
      </main>
    );
  }

  if (admSessionQuery.isLoading) {
    return (
      <main className="grid min-h-screen place-items-center bg-stone-100 px-4 text-stone-950">
        <div className="rounded-lg border border-stone-200 bg-white p-8 text-sm text-stone-600">Carregando permissoes...</div>
      </main>
    );
  }

  if (!canViewPage) {
    return (
      <main className="grid min-h-screen place-items-center bg-stone-100 px-4 text-stone-950">
        <div className="w-full max-w-md rounded-lg border border-stone-200 bg-white p-8 text-center shadow-sm">
          <Lock className="mx-auto h-9 w-9 text-stone-400" />
          <h1 className="mt-4 text-xl font-black">Sem permissao para Modelos de Sites</h1>
          <p className="mt-2 text-sm leading-6 text-stone-600">Peça acesso a pagina adm_site_templates para usar o Studio.</p>
          <Link className="mt-5 inline-flex h-10 items-center rounded-lg border border-stone-300 px-4 text-sm font-bold text-stone-900" href="/adm">
            Voltar ao /adm
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-stone-100 text-stone-950">
      <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <Link href="/adm" className="inline-flex items-center gap-2 text-sm font-bold text-stone-600 hover:text-stone-950">
              <ArrowLeft className="h-4 w-4" />
              Voltar ao /adm
            </Link>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <span className="inline-flex h-10 items-center gap-2 rounded-lg bg-emerald-100 px-3 text-sm font-black text-emerald-900">
                <Sparkles className="h-4 w-4" />
                Template Studio
              </span>
              <span className="inline-flex h-10 items-center rounded-lg border border-stone-200 bg-white px-3 text-xs font-black text-stone-600">
                v{SITE_TEMPLATE_LIBRARY_VERSION}
              </span>
            </div>
            <h1 className="mt-4 font-heading text-3xl font-black sm:text-4xl">Modelos de sites para vender demos</h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-stone-600">
              Crie a biblioteca inicial, veja os 10 modelos, selecione um template para cada prospect e copie o link publico para vender com preview real.
            </p>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              disabled={!canCreatePage}
              onClick={handleCreateLibrary}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 text-sm font-black text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Sparkles className="h-4 w-4" />
              Criar biblioteca inicial
            </button>
            <button
              type="button"
              onClick={() => copyText(absoluteUrl(appOrigin, SITE_TEMPLATE_CATALOG_PATH), "Link do catalogo copiado.")}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-stone-300 bg-white px-4 text-sm font-black text-stone-950 transition hover:bg-stone-50"
            >
              <Copy className="h-4 w-4" />
              Copiar catalogo
            </button>
            <Link
              href={SITE_TEMPLATE_CATALOG_PATH}
              target="_blank"
              className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-stone-300 bg-white px-4 text-sm font-black text-stone-950 transition hover:bg-stone-50"
            >
              <ExternalLink className="h-4 w-4" />
              Abrir publico
            </Link>
          </div>
        </div>

        <section className="mt-8 grid gap-4 lg:grid-cols-4">
          {[
            ["10", "templates profissionais"],
            ["publico", "catalogo publicado"],
            ["CRM", "selecao no prospect"],
            ["SEO", "estrutura local"],
          ].map(([value, label]) => (
            <div key={label} className="rounded-lg border border-stone-200 bg-white p-5">
              <p className="text-2xl font-black text-stone-950">{value}</p>
              <p className="mt-2 text-sm font-bold text-stone-600">{label}</p>
            </div>
          ))}
        </section>

        {!libraryReady ? (
          <section className="mt-6 rounded-lg border border-dashed border-emerald-300 bg-emerald-50 p-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <h2 className="text-xl font-black text-emerald-950">Biblioteca ainda nao criada neste navegador</h2>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-emerald-800">
                  Clique em criar para liberar os cards do Studio. A pagina publica ja fica disponivel para envio.
                </p>
              </div>
              <button
                type="button"
                disabled={!canCreatePage}
                onClick={handleCreateLibrary}
                className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-emerald-700 px-4 text-sm font-black text-white transition hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Sparkles className="h-4 w-4" />
                Criar agora
              </button>
            </div>
          </section>
        ) : null}

        {libraryReady ? (
          <section className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {SITE_TEMPLATES.map((template) => {
              const isSelected = template.slug === selectedTemplateSlug;
              return (
                <article
                  key={template.slug}
                  className={cn(
                    "overflow-hidden rounded-lg border bg-white shadow-sm transition",
                    isSelected ? "border-emerald-400 ring-4 ring-emerald-100" : "border-stone-200",
                  )}
                >
                  <div
                    className="h-28 bg-cover bg-center"
                    style={{
                      backgroundImage: `linear-gradient(135deg, ${template.palette.primary}E6, ${template.palette.accent}BA), url(${template.heroImage})`,
                    }}
                  />
                  <div className="p-5">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-xs font-black uppercase tracking-[0.14em] text-stone-500">{template.niche}</p>
                        <h3 className="mt-2 text-lg font-black text-stone-950">{template.name}</h3>
                      </div>
                      {isSelected ? <CheckCircle2 className="h-5 w-5 text-emerald-600" /> : null}
                    </div>
                    <p className="mt-3 min-h-[72px] text-sm leading-6 text-stone-600">{template.outcome}</p>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {template.badges.map((badge) => (
                        <span key={badge} className="rounded-lg bg-stone-100 px-2.5 py-1 text-xs font-bold text-stone-700">
                          {badge}
                        </span>
                      ))}
                    </div>
                    <div className="mt-5 flex flex-col gap-2 sm:flex-row">
                      <button
                        type="button"
                        onClick={() => setSelectedTemplateSlug(template.slug)}
                        className="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-lg bg-stone-950 px-3 text-sm font-black text-white transition hover:bg-emerald-800"
                      >
                        <MousePointer2 className="h-4 w-4" />
                        Selecionar
                      </button>
                      <Link
                        href={buildSiteTemplatePreviewPath(template)}
                        target="_blank"
                        className="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-lg border border-stone-300 bg-white px-3 text-sm font-black text-stone-950 transition hover:bg-stone-50"
                      >
                        <Eye className="h-4 w-4" />
                        Ver
                      </Link>
                    </div>
                  </div>
                </article>
              );
            })}
          </section>
        ) : null}

        <section className="mt-8 grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
          <div className="rounded-lg border border-stone-200 bg-white p-6">
            <div className="flex items-center gap-2">
              <Clipboard className="h-5 w-5 text-emerald-700" />
              <h2 className="text-xl font-black">Selecionar para um prospect</h2>
            </div>
            <p className="mt-2 text-sm leading-6 text-stone-600">
              A selecao e salva em proposal_snapshot.site_template e fica junto do prospect comercial.
            </p>

            {!canViewCrm ? (
              <div className="mt-5 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm font-semibold text-amber-900">
                Voce precisa de permissao de CRM para listar prospects.
              </div>
            ) : prospectsQuery.isLoading ? (
              <div className="mt-5 flex items-center gap-2 text-sm font-semibold text-stone-600">
                <RefreshCw className="h-4 w-4 animate-spin" />
                Carregando prospects...
              </div>
            ) : prospects.length ? (
              <div className="mt-5 space-y-4">
                <label className="block space-y-2">
                  <span className="text-xs font-black uppercase tracking-[0.14em] text-stone-500">Prospect</span>
                  <select
                    value={selectedProspect?.id || ""}
                    onChange={(event) => setSelectedProspectId(event.target.value)}
                    className="h-11 w-full rounded-lg border border-stone-300 bg-white px-3 text-sm outline-none focus:border-emerald-600 focus:ring-4 focus:ring-emerald-100"
                  >
                    {prospects.map((prospect) => (
                      <option key={prospect.id} value={prospect.id}>
                        {prospect.clinic_name} {prospect.city ? `- ${prospect.city}` : ""}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block space-y-2">
                  <span className="text-xs font-black uppercase tracking-[0.14em] text-stone-500">Template</span>
                  <select
                    value={selectedTemplateSlug}
                    onChange={(event) => setSelectedTemplateSlug(event.target.value)}
                    className="h-11 w-full rounded-lg border border-stone-300 bg-white px-3 text-sm outline-none focus:border-emerald-600 focus:ring-4 focus:ring-emerald-100"
                  >
                    {SITE_TEMPLATES.map((template) => (
                      <option key={template.slug} value={template.slug}>
                        {template.name}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  disabled={!canSelectForProspect || selectMutation.isPending}
                  onClick={() => selectMutation.mutate()}
                  className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 text-sm font-black text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <CheckCircle2 className="h-4 w-4" />
                  Salvar selecao no prospect
                </button>
                {!canSelectForProspect ? (
                  <p className="text-xs leading-5 text-amber-700">
                    Para salvar, o usuario precisa editar Modelos de Sites e CRM comercial.
                  </p>
                ) : null}
              </div>
            ) : (
              <div className="mt-5 rounded-lg border border-stone-200 bg-stone-50 p-4 text-sm text-stone-600">
                Nenhum prospect encontrado no CRM.
              </div>
            )}
          </div>

          <div className="rounded-lg border border-stone-200 bg-white p-6">
            <div className="flex items-center gap-2">
              <Globe2 className="h-5 w-5 text-emerald-700" />
              <h2 className="text-xl font-black">Links de venda</h2>
            </div>
            <p className="mt-2 text-sm leading-6 text-stone-600">
              Use o catalogo para mostrar todos os modelos ou envie um preview personalizado com nome da clinica.
            </p>
            <div className="mt-5 space-y-3">
              <div className="rounded-lg border border-stone-200 bg-stone-50 p-4">
                <p className="text-xs font-black uppercase tracking-[0.14em] text-stone-500">Catalogo publico</p>
                <p className="mt-2 break-all text-sm font-bold text-stone-950">{absoluteUrl(appOrigin, SITE_TEMPLATE_CATALOG_PATH)}</p>
                <button
                  type="button"
                  onClick={() => copyText(absoluteUrl(appOrigin, SITE_TEMPLATE_CATALOG_PATH), "Catalogo publico copiado.")}
                  className="mt-3 inline-flex h-9 items-center gap-2 rounded-lg border border-stone-300 bg-white px-3 text-sm font-black text-stone-950"
                >
                  <Copy className="h-4 w-4" />
                  Copiar
                </button>
              </div>
              <div className="rounded-lg border border-stone-200 bg-stone-50 p-4">
                <p className="text-xs font-black uppercase tracking-[0.14em] text-stone-500">Preview selecionado</p>
                <p className="mt-2 break-all text-sm font-bold text-stone-950">{absoluteUrl(appOrigin, personalizedPreviewPath)}</p>
                <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                  <button
                    type="button"
                    onClick={() => copyText(absoluteUrl(appOrigin, personalizedPreviewPath), "Preview personalizado copiado.")}
                    className="inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-stone-300 bg-white px-3 text-sm font-black text-stone-950"
                  >
                    <Copy className="h-4 w-4" />
                    Copiar preview
                  </button>
                  <Link
                    href={personalizedPreviewPath}
                    target="_blank"
                    className="inline-flex h-9 items-center justify-center gap-2 rounded-lg bg-stone-950 px-3 text-sm font-black text-white"
                  >
                    <ExternalLink className="h-4 w-4" />
                    Abrir
                  </Link>
                </div>
              </div>
              {selectedProspect ? (
                <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
                  <p className="text-xs font-black uppercase tracking-[0.14em] text-emerald-700">Prospect atual</p>
                  <p className="mt-2 text-sm font-black text-emerald-950">{selectedProspect.clinic_name}</p>
                  <p className="mt-1 text-sm text-emerald-800">
                    Template salvo: {selectedTemplateSlugFromProspect(selectedProspect) || "nenhum ainda"}
                  </p>
                </div>
              ) : null}
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}

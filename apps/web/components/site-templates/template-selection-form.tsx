"use client";

import { type FormEvent, useMemo, useState } from "react";
import { ArrowRight, CheckCircle2, LoaderCircle, MessageCircle } from "lucide-react";

import { api } from "@/lib/api";
import type { SiteTemplate } from "@/lib/site-templates";
import { cn } from "@odontoflux/ui";

type QuickDemoResponse = {
  prospect: {
    id: string;
    clinic_name: string;
    owner_name?: string | null;
    proposal_snapshot?: Record<string, unknown>;
  };
  status: "created" | "reused";
  demo_login_url: string;
  demo_booking_path?: string | null;
  demo_booking_url?: string | null;
  selected_template_slug?: string | null;
  site_template_preview_url?: string | null;
};

type FormState = {
  clinic_name: string;
  owner_name: string;
  phone: string;
  template_slug: string;
};

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

export function TemplateSelectionForm({
  templates,
  defaultTemplateSlug,
  variant = "default",
}: {
  templates: SiteTemplate[];
  defaultTemplateSlug?: string | null;
  variant?: "default" | "premium";
}) {
  const initialSlug = defaultTemplateSlug || templates[0]?.slug || "";
  const [form, setForm] = useState<FormState>({
    clinic_name: "",
    owner_name: "",
    phone: "",
    template_slug: initialSlug,
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [result, setResult] = useState<QuickDemoResponse | null>(null);

  const selectedTemplate = useMemo(
    () => templates.find((template) => template.slug === form.template_slug) ?? templates[0] ?? null,
    [form.template_slug, templates],
  );

  const canSubmit = useMemo(() => {
    return (
      form.clinic_name.trim().length >= 2 &&
      form.owner_name.trim().length >= 2 &&
      form.phone.trim().length >= 8 &&
      Boolean(selectedTemplate) &&
      !isSubmitting
    );
  }, [form, isSubmitting, selectedTemplate]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;

    setErrorMessage("");
    setResult(null);
    setIsSubmitting(true);
    try {
      const response = await api.post<QuickDemoResponse>("/public/site/quick-demo", {
        clinic_name: form.clinic_name.trim(),
        owner_name: form.owner_name.trim(),
        phone: form.phone.trim(),
        template_slug: form.template_slug,
      });
      setResult(response.data);
    } catch (error) {
      setErrorMessage(extractApiErrorMessage(error, "Nao foi possivel registrar a escolha agora."));
    } finally {
      setIsSubmitting(false);
    }
  }

  const isPremium = variant === "premium";

  return (
    <section
      id="selecionar-template"
      className={cn(
        "px-4 py-16 text-white sm:px-6 lg:px-8",
        isPremium ? "relative overflow-hidden bg-[#060607]" : "bg-stone-950",
      )}
    >
      {isPremium ? (
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(31,119,111,0.18),transparent_32%),radial-gradient(circle_at_80%_20%,rgba(214,162,81,0.10),transparent_24%),linear-gradient(180deg,#060607_0%,#090909_100%)]" />
        </div>
      ) : null}

      <div
        className={cn(
          "mx-auto grid w-full max-w-7xl gap-8 lg:items-start",
          isPremium ? "relative z-10 lg:grid-cols-[0.84fr_1.16fr]" : "lg:grid-cols-[0.9fr_1.1fr]",
        )}
      >
        <div>
          <p className={cn("text-xs font-black uppercase tracking-[0.18em] text-emerald-300", isPremium && "tracking-[0.22em]")}>
            Selecionar modelo
          </p>
          <h2 className={cn("mt-3 font-heading text-3xl font-black sm:text-4xl", isPremium && "max-w-2xl text-4xl leading-tight sm:text-5xl")}>
            Registre o interesse e gere uma demo com o template escolhido.
          </h2>
          <p className={cn("mt-4 max-w-xl text-base leading-7 text-white/70", isPremium && "text-white/62")}>
            A escolha entra no CRM comercial como snapshot do prospect e ja volta com link de demo e preview personalizado.
          </p>
          {selectedTemplate ? (
            <div
              className={cn(
                "mt-6 rounded-lg border border-white/10 bg-white/10 p-4",
                isPremium && "rounded-[28px] border-white/10 bg-white/[0.04] p-6 shadow-[0_20px_60px_rgba(0,0,0,0.20)] backdrop-blur",
              )}
            >
              <div className={cn(isPremium && "flex items-start justify-between gap-4")}>
                <div>
                  <p className={cn("text-sm font-black", isPremium && "text-base text-white")}>{selectedTemplate.name}</p>
                  <p className={cn("mt-2 text-sm leading-6 text-white/70", isPremium && "max-w-lg text-white/60")}>{selectedTemplate.outcome}</p>
                </div>
                {isPremium ? (
                  <div className="rounded-full border border-white/10 bg-white/[0.05] px-3 py-1 text-[11px] font-black uppercase tracking-[0.16em] text-emerald-300">
                    snapshot pronto
                  </div>
                ) : null}
              </div>

              {isPremium ? (
                <div className="mt-5 grid gap-2 sm:grid-cols-2">
                  <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm font-black text-white/84">
                    Preview real para abrir na hora
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm font-black text-white/84">
                    Registro comercial com template escolhido
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>

        <form
          onSubmit={handleSubmit}
          className={cn(
            "rounded-lg border border-white/10 bg-white p-5 text-stone-950 shadow-[0_24px_70px_rgba(0,0,0,0.22)]",
            isPremium && "rounded-[32px] border-[#e8decc] bg-[#f7f1e6] p-6 shadow-[0_32px_100px_rgba(0,0,0,0.30)] sm:p-8",
          )}
        >
          {isPremium ? (
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-[11px] font-black uppercase tracking-[0.18em] text-stone-500">Fechamento de demo</p>
                <p className="mt-2 text-2xl font-black text-stone-950">Complete os dados e dispare a experiencia.</p>
              </div>
              <div className="rounded-full bg-stone-950 px-3 py-1 text-[11px] font-black uppercase tracking-[0.16em] text-white">
                premium flow
              </div>
            </div>
          ) : null}

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block space-y-2">
              <span className="text-xs font-black uppercase tracking-[0.14em] text-stone-500">Clinica</span>
              <input
                value={form.clinic_name}
                onChange={(event) => setForm((current) => ({ ...current, clinic_name: event.target.value }))}
                className="h-11 w-full rounded-lg border border-stone-300 px-3 text-sm outline-none focus:border-emerald-600 focus:ring-4 focus:ring-emerald-100"
                placeholder="Ex: Sorriso Sul"
              />
            </label>
            <label className="block space-y-2">
              <span className="text-xs font-black uppercase tracking-[0.14em] text-stone-500">Responsavel</span>
              <input
                value={form.owner_name}
                onChange={(event) => setForm((current) => ({ ...current, owner_name: event.target.value }))}
                className="h-11 w-full rounded-lg border border-stone-300 px-3 text-sm outline-none focus:border-emerald-600 focus:ring-4 focus:ring-emerald-100"
                placeholder="Nome do responsavel"
              />
            </label>
            <label className="block space-y-2">
              <span className="text-xs font-black uppercase tracking-[0.14em] text-stone-500">WhatsApp</span>
              <input
                value={form.phone}
                onChange={(event) => setForm((current) => ({ ...current, phone: event.target.value }))}
                className="h-11 w-full rounded-lg border border-stone-300 px-3 text-sm outline-none focus:border-emerald-600 focus:ring-4 focus:ring-emerald-100"
                placeholder="+55 11 99999-9999"
              />
            </label>
            <label className="block space-y-2">
              <span className="text-xs font-black uppercase tracking-[0.14em] text-stone-500">Template</span>
              <select
                value={form.template_slug}
                onChange={(event) => setForm((current) => ({ ...current, template_slug: event.target.value }))}
                className="h-11 w-full rounded-lg border border-stone-300 bg-white px-3 text-sm outline-none focus:border-emerald-600 focus:ring-4 focus:ring-emerald-100"
              >
                {templates.map((template) => (
                  <option key={template.slug} value={template.slug}>
                    {template.name}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {errorMessage ? (
            <div
              className={cn(
                "mt-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm font-semibold text-rose-700",
                isPremium && "rounded-2xl border-rose-200 bg-rose-50/90 p-4",
              )}
            >
              {errorMessage}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={!canSubmit}
            className={cn(
              "mt-5 inline-flex h-12 w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-5 text-sm font-black text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-60",
              isPremium &&
                "h-14 rounded-full bg-[linear-gradient(135deg,#0f766e,#1b8f84)] text-base shadow-[0_18px_44px_rgba(15,118,110,0.26)] hover:brightness-110",
            )}
          >
            {isSubmitting ? <LoaderCircle className="h-5 w-5 animate-spin" /> : <MessageCircle className="h-5 w-5" />}
            Selecionar template e gerar demo
          </button>

          {result ? (
            <div
              className={cn(
                "mt-5 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-emerald-950",
                isPremium && "rounded-[28px] border-emerald-200 bg-[#ecfbf5] p-5 shadow-sm",
              )}
            >
              <div className="flex items-start gap-3">
                <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-700" />
                <div>
                  <p className="font-black">
                    {result.status === "created" ? "Prospect criado" : "Prospect reaproveitado"} com template selecionado.
                  </p>
                  <p className="mt-1 text-sm leading-6 text-emerald-800">
                    Use os links abaixo para mostrar a demo e o modelo personalizado.
                  </p>
                </div>
              </div>
              <div className="mt-4 flex flex-col gap-2 sm:flex-row">
                <a
                  href={result.site_template_preview_url || `/modelos-sites/${result.selected_template_slug || form.template_slug}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-emerald-700 px-4 text-sm font-black text-white hover:bg-emerald-600"
                >
                  Ver preview
                  <ArrowRight className="h-4 w-4" />
                </a>
                <a
                  href={result.demo_login_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-emerald-300 bg-white px-4 text-sm font-black text-emerald-950 hover:bg-emerald-100"
                >
                  Abrir demo ClinicFlux
                </a>
              </div>
            </div>
          ) : null}
        </form>
      </div>
    </section>
  );
}

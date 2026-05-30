import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Eye, MousePointer2, Sparkles } from "lucide-react";

import { TemplateSelectionForm } from "@/components/site-templates/template-selection-form";
import { BRAND_NAME } from "@/lib/brand";
import { SITE_TEMPLATES, buildSiteTemplatePreviewPath } from "@/lib/site-templates";

export const metadata: Metadata = {
  title: `Modelos de sites profissionais | ${BRAND_NAME}`,
  description:
    "Catalogo com 10 templates profissionais para clinicas, consultorios e campanhas com foco em SEO local, WhatsApp e conversao.",
};

export default function SiteTemplatesCatalogPage() {
  return (
    <main className="min-h-screen bg-stone-50 text-stone-950">
      <section className="relative min-h-[86vh] overflow-hidden">
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: "url('/images/dental-floss-smile-background.png')" }}
        />
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(255,255,255,0.96)_0%,rgba(255,255,255,0.86)_52%,rgba(255,255,255,0.50)_100%)]" />
        <div className="relative mx-auto flex min-h-[86vh] w-full max-w-7xl flex-col px-4 py-5 sm:px-6 lg:px-8">
          <header className="flex items-center justify-between gap-4">
            <Link href="/" className="text-sm font-black text-stone-950">
              {BRAND_NAME}
            </Link>
            <a
              href="#selecionar-template"
              className="inline-flex h-10 items-center justify-center rounded-lg bg-stone-950 px-4 text-sm font-black text-white transition hover:bg-emerald-800"
            >
              Selecionar modelo
            </a>
          </header>

          <div className="grid flex-1 items-center gap-10 py-12 lg:grid-cols-[1.04fr_0.96fr]">
            <div>
              <div className="inline-flex items-center gap-2 rounded-lg border border-stone-200 bg-white/90 px-3 py-2 text-xs font-black uppercase tracking-[0.16em] text-emerald-800">
                <Sparkles className="h-4 w-4" />
                Template Studio
              </div>
              <h1 className="mt-6 max-w-4xl font-heading text-4xl font-black leading-[1.02] sm:text-5xl lg:text-6xl">
                10 modelos de sites profissionais para vender demos com mais impacto.
              </h1>
              <p className="mt-5 max-w-2xl text-base leading-7 text-stone-700 sm:text-lg">
                Escolha um template, abra a previa real e registre a selecao para gerar uma demo personalizada no
                fluxo comercial do ClinicFlux AI.
              </p>
              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <a
                  href="#modelos"
                  className="inline-flex h-12 items-center justify-center gap-2 rounded-lg bg-emerald-700 px-5 text-sm font-black text-white transition hover:bg-emerald-600"
                >
                  Ver os 10 modelos
                  <ArrowRight className="h-4 w-4" />
                </a>
                <a
                  href="#selecionar-template"
                  className="inline-flex h-12 items-center justify-center gap-2 rounded-lg border border-stone-300 bg-white px-5 text-sm font-black text-stone-950 transition hover:bg-stone-100"
                >
                  Selecionar template
                </a>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              {[
                ["10", "templates prontos"],
                ["SEO", "estrutura local"],
                ["CTA", "WhatsApp e agenda"],
                ["CRM", "selecao registrada"],
              ].map(([value, label]) => (
                <div key={label} className="rounded-lg border border-stone-200 bg-white/90 p-5 shadow-[0_18px_50px_rgba(28,25,23,0.10)]">
                  <p className="text-3xl font-black text-stone-950">{value}</p>
                  <p className="mt-2 text-sm font-bold text-stone-600">{label}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section id="modelos" className="mx-auto w-full max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.18em] text-emerald-700">Biblioteca inicial</p>
            <h2 className="mt-3 font-heading text-3xl font-black sm:text-4xl">Modelos com posicionamento comercial diferente</h2>
          </div>
          <p className="max-w-xl text-sm leading-6 text-stone-600">
            Cada modelo tem nicho, oferta, CTA e sinais de confianca para vender site, auditoria ou landing de conversao.
          </p>
        </div>

        <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {SITE_TEMPLATES.map((template) => (
            <article key={template.slug} className="overflow-hidden rounded-lg border border-stone-200 bg-white shadow-[0_14px_44px_rgba(28,25,23,0.08)]">
              <div
                className="h-36 bg-cover bg-center"
                style={{
                  backgroundImage: `linear-gradient(135deg, ${template.palette.primary}E6, ${template.palette.accent}B8), url(${template.heroImage})`,
                }}
              />
              <div className="p-5">
                <div className="flex flex-wrap gap-2">
                  <span className="rounded-lg border border-stone-200 bg-stone-50 px-2.5 py-1 text-xs font-black text-stone-700">
                    {template.niche}
                  </span>
                  <span className="rounded-lg border border-stone-200 bg-stone-50 px-2.5 py-1 text-xs font-black text-stone-700">
                    {template.offerLane.replace("_", " ")}
                  </span>
                </div>
                <h3 className="mt-4 text-xl font-black text-stone-950">{template.name}</h3>
                <p className="mt-2 min-h-[72px] text-sm leading-6 text-stone-600">{template.subheadline}</p>
                <div className="mt-4 grid grid-cols-3 gap-2">
                  {template.metrics.map((metric) => (
                    <div key={metric.label} className="rounded-lg bg-stone-50 p-3">
                      <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-stone-500">{metric.label}</p>
                      <p className="mt-1 text-sm font-black text-stone-950">{metric.value}</p>
                    </div>
                  ))}
                </div>
                <div className="mt-5 flex flex-col gap-2 sm:flex-row">
                  <Link
                    href={buildSiteTemplatePreviewPath(template)}
                    className="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-lg border border-stone-300 bg-white px-3 text-sm font-black text-stone-950 transition hover:bg-stone-100"
                  >
                    <Eye className="h-4 w-4" />
                    Ver
                  </Link>
                  <Link
                    href={`${buildSiteTemplatePreviewPath(template)}#selecionar-template`}
                    className="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-lg bg-stone-950 px-3 text-sm font-black text-white transition hover:bg-emerald-800"
                  >
                    <MousePointer2 className="h-4 w-4" />
                    Selecionar
                  </Link>
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>

      <TemplateSelectionForm templates={SITE_TEMPLATES} />
    </main>
  );
}

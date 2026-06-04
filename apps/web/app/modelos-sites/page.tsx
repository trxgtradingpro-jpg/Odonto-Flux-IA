import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  Eye,
  GalleryVerticalEnd,
  LayoutTemplate,
  MessageCircle,
  MousePointer2,
  ShieldCheck,
  Sparkles,
  Star,
} from "lucide-react";

import { TemplateSelectionForm } from "@/components/site-templates/template-selection-form";
import { BRAND_NAME } from "@/lib/brand";
import {
  SITE_TEMPLATE_LIBRARY_VERSION,
  SITE_TEMPLATES,
  buildSiteTemplatePreviewPath,
  getSiteTemplateEliteDetails,
  getSiteTemplateVisual,
  type SiteTemplate,
} from "@/lib/site-templates";

export const metadata: Metadata = {
  title: `Modelos de sites premium | ${BRAND_NAME}`,
  description:
    "Catalogo premium de modelos de sites para clinicas, consultorios e campanhas com foco em desejo, SEO local, WhatsApp e conversao.",
};

const FEATURED_TEMPLATE_SLUGS = [
  "clinica-odontologica-premium",
  "dermatologia-premium",
  "estetica-facial-moderna",
] as const;

const SALES_STEPS = [
  {
    title: "Escolha pelo fit comercial",
    body: "Cada modelo mostra posicionamento, tom visual e promessa para o vendedor encaixar o template com seguranca.",
    icon: ShieldCheck,
  },
  {
    title: "Abra a previa real",
    body: "O prospect ve o site completo, com hero, secoes e CTA ja organizados no fluxo certo para a conversa.",
    icon: GalleryVerticalEnd,
  },
  {
    title: "Registre e gere a demo",
    body: "A selecao entra no CRM com snapshot do template escolhido e volta com preview e demo personalizados.",
    icon: MessageCircle,
  },
];

function getFeaturedTemplates(): SiteTemplate[] {
  return FEATURED_TEMPLATE_SLUGS.map((slug) => SITE_TEMPLATES.find((template) => template.slug === slug)).filter(
    (template): template is SiteTemplate => Boolean(template),
  );
}

export default function SiteTemplatesCatalogPage() {
  const featuredTemplates = getFeaturedTemplates();
  const leadTemplate = featuredTemplates[0] ?? SITE_TEMPLATES[0];
  const leadVisual = getSiteTemplateVisual(leadTemplate);
  const leadElite = getSiteTemplateEliteDetails(leadTemplate);
  const catalogTemplates = SITE_TEMPLATES.filter((template) => template.slug !== leadTemplate.slug);

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#050506] text-white">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(31,119,111,0.18),transparent_36%),radial-gradient(circle_at_78%_22%,rgba(219,165,89,0.10),transparent_24%),linear-gradient(180deg,#050506_0%,#0a0b0d_42%,#060607_100%)]" />
        <div className="absolute inset-x-0 top-0 h-[620px] bg-[linear-gradient(180deg,rgba(255,255,255,0.04),transparent)]" />
      </div>

      <section className="relative border-b border-white/8">
        <div className="mx-auto w-full max-w-7xl px-4 py-5 sm:px-6 lg:px-8">
          <header className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-3 shadow-[0_16px_60px_rgba(0,0,0,0.24)] backdrop-blur-xl">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-full border border-white/12 bg-white/[0.05]">
                  <LayoutTemplate className="h-5 w-5 text-white" />
                </div>
                <div className="min-w-0">
                  <p className="text-[11px] font-black uppercase tracking-[0.28em] text-white/46">Template Studio</p>
                  <p className="truncate text-base font-black text-white">{BRAND_NAME}</p>
                </div>
              </div>

              <div className="hidden items-center gap-2 lg:flex">
                <div className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-[11px] font-black uppercase tracking-[0.18em] text-white/56">
                  Elite catalog
                </div>
                <div className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-[11px] font-black uppercase tracking-[0.18em] text-white/56">
                  {SITE_TEMPLATE_LIBRARY_VERSION}
                </div>
              </div>

              <div className="flex items-center gap-2">
                <a
                  href="#modelos"
                  className="inline-flex h-10 items-center justify-center rounded-full border border-white/12 px-4 text-sm font-black text-white/80 transition hover:bg-white/[0.06] hover:text-white"
                >
                  Ver modelos
                </a>
                <a
                  href="#selecionar-template"
                  className="inline-flex h-10 items-center justify-center rounded-full bg-[linear-gradient(135deg,#1b8f84,#0f766e)] px-4 text-sm font-black text-white shadow-[0_18px_44px_rgba(15,118,110,0.28)] transition hover:brightness-110"
                >
                  Gerar demo
                </a>
              </div>
            </div>
          </header>

          <div className="grid gap-10 py-12 lg:grid-cols-[0.88fr_1.12fr] lg:items-center lg:py-16">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.05] px-4 py-2 text-[11px] font-black uppercase tracking-[0.22em] text-emerald-300">
                <Sparkles className="h-4 w-4" />
                Curadoria premium para clinicas
              </div>
              <h1 className="mt-6 max-w-4xl font-heading text-4xl font-black leading-[0.98] text-white sm:text-5xl lg:text-7xl">
                Modelos de sites que parecem agencia premium antes mesmo da demo abrir.
              </h1>
              <p className="mt-6 max-w-2xl text-base leading-7 text-white/66 sm:text-lg">
                O catalogo agora apresenta cada template como produto premium: atmosfera, promessa comercial, preview real
                e selecao pronta para gerar demo personalizada no fluxo comercial do ClinicFlux AI.
              </p>

              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <a
                  href="#modelos"
                  className="inline-flex h-12 items-center justify-center gap-2 rounded-full bg-white px-5 text-sm font-black text-stone-950 transition hover:-translate-y-0.5 hover:bg-[#f5ede1]"
                >
                  Explorar catalogo
                  <ArrowRight className="h-4 w-4" />
                </a>
                <a
                  href="#selecionar-template"
                  className="inline-flex h-12 items-center justify-center gap-2 rounded-full border border-white/14 bg-white/[0.04] px-5 text-sm font-black text-white transition hover:bg-white/[0.08]"
                >
                  Fechar uma demo
                </a>
              </div>

              <div className="mt-10 grid gap-3 sm:grid-cols-3">
                {[
                  [String(SITE_TEMPLATES.length), "modelos com identidade propria"],
                  ["Multipage", "premium, preview e selecao"],
                  ["CRM-ready", "snapshot salvo no fluxo comercial"],
                ].map(([value, label]) => (
                  <div key={label} className="rounded-[24px] border border-white/10 bg-white/[0.04] p-5 backdrop-blur">
                    <p className="text-3xl font-black text-white">{value}</p>
                    <p className="mt-2 text-sm font-bold leading-6 text-white/54">{label}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-[1.12fr_0.88fr]">
              <article
                className="group relative min-h-[430px] overflow-hidden rounded-[32px] border border-white/10 bg-[#111214] shadow-[0_24px_90px_rgba(0,0,0,0.34)]"
                style={{
                  backgroundImage: `linear-gradient(180deg,rgba(7,7,7,0.08),rgba(7,7,7,0.72)), url(${leadVisual.heroImage})`,
                  backgroundPosition: leadVisual.heroImagePosition,
                  backgroundSize: "cover",
                }}
              >
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.16),transparent_38%),linear-gradient(180deg,transparent_0%,rgba(0,0,0,0.76)_84%)]" />
                <div className="relative flex h-full flex-col justify-between p-6">
                  <div className="flex items-start justify-between gap-3">
                    <div className="rounded-full border border-white/12 bg-black/20 px-3 py-1.5 text-[11px] font-black uppercase tracking-[0.18em] text-white/76 backdrop-blur">
                      Featured template
                    </div>
                    <div className="rounded-full border border-white/12 bg-white/[0.08] px-3 py-1.5 text-[11px] font-black uppercase tracking-[0.18em] text-white/60 backdrop-blur">
                      {leadTemplate.niche}
                    </div>
                  </div>

                  <div>
                    <p className="text-xs font-black uppercase tracking-[0.18em] text-emerald-300">{leadVisual.archetype}</p>
                    <h2 className="mt-4 max-w-xl font-heading text-4xl font-black leading-[0.96] text-white">
                      {leadTemplate.name}
                    </h2>
                    <p className="mt-4 max-w-lg text-sm leading-6 text-white/72">{leadElite.authority.title}</p>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
                    <div className="grid gap-2 sm:grid-cols-2">
                      {leadTemplate.badges.slice(0, 2).map((badge) => (
                        <div key={badge} className="rounded-2xl border border-white/12 bg-white/[0.08] px-4 py-3 text-sm font-black text-white backdrop-blur">
                          {badge}
                        </div>
                      ))}
                    </div>
                    <Link
                      href={buildSiteTemplatePreviewPath(leadTemplate)}
                      className="inline-flex h-11 items-center justify-center gap-2 rounded-full bg-white px-4 text-sm font-black text-stone-950 transition hover:bg-[#f5ede1]"
                    >
                      Abrir preview
                      <Eye className="h-4 w-4" />
                    </Link>
                  </div>
                </div>
              </article>

              <div className="grid gap-4">
                {featuredTemplates.slice(1).map((template) => {
                  const visual = getSiteTemplateVisual(template);
                  const elite = getSiteTemplateEliteDetails(template);
                  return (
                    <Link
                      key={template.slug}
                      href={buildSiteTemplatePreviewPath(template)}
                      className="group relative min-h-[206px] overflow-hidden rounded-[28px] border border-white/10 bg-[#121315] shadow-[0_20px_70px_rgba(0,0,0,0.24)]"
                      style={{
                        backgroundImage: `linear-gradient(180deg,rgba(6,6,6,0.12),rgba(6,6,6,0.74)), url(${visual.heroImage})`,
                        backgroundPosition: visual.heroImagePosition,
                        backgroundSize: "cover",
                      }}
                    >
                      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.14),transparent_34%)]" />
                      <div className="relative flex h-full flex-col justify-between p-5">
                        <div className="flex items-start justify-between gap-3">
                          <p className="text-[11px] font-black uppercase tracking-[0.18em] text-white/56">{template.niche}</p>
                          <Star className="h-4 w-4 text-amber-300" />
                        </div>
                        <div>
                          <h3 className="text-2xl font-black leading-tight text-white">{template.name}</h3>
                          <p className="mt-2 text-sm leading-6 text-white/68">{elite.visualFocus}</p>
                        </div>
                      </div>
                    </Link>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="relative border-b border-white/8">
        <div className="mx-auto grid w-full max-w-7xl gap-4 px-4 py-10 sm:px-6 lg:grid-cols-3 lg:px-8">
          {SALES_STEPS.map((step, index) => {
            const Icon = step.icon;
            return (
              <article
                key={step.title}
                className="rounded-[28px] border border-white/10 bg-white/[0.04] p-6 shadow-[0_20px_60px_rgba(0,0,0,0.18)] backdrop-blur"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/[0.06] text-emerald-300">
                    <Icon className="h-5 w-5" />
                  </div>
                  <span className="text-[11px] font-black uppercase tracking-[0.18em] text-white/40">0{index + 1}</span>
                </div>
                <h2 className="mt-5 text-2xl font-black text-white">{step.title}</h2>
                <p className="mt-3 text-sm leading-6 text-white/64">{step.body}</p>
              </article>
            );
          })}
        </div>
      </section>

      <section id="modelos" className="relative mx-auto w-full max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className="text-xs font-black uppercase tracking-[0.22em] text-emerald-300">Catalogo premium</p>
            <h2 className="mt-4 font-heading text-3xl font-black leading-tight text-white sm:text-5xl">
              Cada modelo agora parece um produto premium, nao apenas um card de template.
            </h2>
          </div>
          <p className="max-w-xl text-sm leading-6 text-white/58">
            Abra o preview real, entenda a atmosfera comercial e selecione o template certo para o prospect sem parecer
            uma pagina generica de vitrine.
          </p>
        </div>

        <div className="mt-10 overflow-hidden rounded-[36px] border border-white/10 bg-[linear-gradient(135deg,#111214,#191715)] shadow-[0_26px_100px_rgba(0,0,0,0.28)]">
          <div className="grid gap-0 lg:grid-cols-[0.96fr_1.04fr]">
            <div className="border-b border-white/8 p-7 lg:border-b-0 lg:border-r lg:p-10">
              <p className="text-xs font-black uppercase tracking-[0.18em] text-emerald-300">Lead template</p>
              <h3 className="mt-4 font-heading text-4xl font-black leading-[0.96] text-white">{leadTemplate.name}</h3>
              <p className="mt-4 text-sm leading-7 text-white/68">{leadElite.showcase.body}</p>

              <div className="mt-8 grid gap-3 sm:grid-cols-3">
                {leadTemplate.metrics.map((metric) => (
                  <div key={metric.label} className="rounded-[22px] border border-white/10 bg-white/[0.04] p-4">
                    <p className="text-[11px] font-black uppercase tracking-[0.14em] text-white/42">{metric.label}</p>
                    <p className="mt-2 text-base font-black text-white">{metric.value}</p>
                  </div>
                ))}
              </div>

              <div className="mt-8 grid gap-2 sm:grid-cols-2">
                {leadElite.authority.items.map((item) => (
                  <div key={item} className="rounded-[20px] border border-white/10 bg-white/[0.04] px-4 py-3 text-sm font-black text-white/86">
                    {item}
                  </div>
                ))}
              </div>

              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <Link
                  href={buildSiteTemplatePreviewPath(leadTemplate)}
                  className="inline-flex h-12 items-center justify-center gap-2 rounded-full border border-white/12 bg-white/[0.04] px-5 text-sm font-black text-white transition hover:bg-white/[0.08]"
                >
                  <Eye className="h-4 w-4" />
                  Ver experiencia
                </Link>
                <Link
                  href={`${buildSiteTemplatePreviewPath(leadTemplate)}#selecionar-template`}
                  className="inline-flex h-12 items-center justify-center gap-2 rounded-full bg-[linear-gradient(135deg,#1b8f84,#0f766e)] px-5 text-sm font-black text-white shadow-[0_18px_44px_rgba(15,118,110,0.28)] transition hover:brightness-110"
                >
                  <MousePointer2 className="h-4 w-4" />
                  Selecionar template
                </Link>
              </div>
            </div>

            <div
              className="relative min-h-[380px] bg-cover bg-center"
              style={{
                backgroundImage: `linear-gradient(180deg,rgba(0,0,0,0.14),rgba(0,0,0,0.56)), url(${leadVisual.heroImage})`,
                backgroundPosition: leadVisual.heroImagePosition,
              }}
            >
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.16),transparent_34%)]" />
              <div className="absolute left-5 right-5 top-5 rounded-[24px] border border-white/10 bg-black/20 p-5 backdrop-blur-md lg:left-8 lg:right-8 lg:top-8">
                <p className="text-[11px] font-black uppercase tracking-[0.18em] text-white/56">{leadVisual.archetype}</p>
                <p className="mt-3 text-3xl font-black leading-none text-white/94">{leadElite.visualFocus}</p>
              </div>
              <div className="absolute bottom-5 left-5 right-5 grid gap-2 sm:grid-cols-2 lg:left-8 lg:right-8 lg:bottom-8">
                {leadTemplate.services.slice(0, 4).map((service) => (
                  <div key={service} className="rounded-[18px] border border-white/12 bg-white/[0.08] px-4 py-3 text-sm font-black text-white backdrop-blur">
                    {service}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="mt-8 grid gap-5 md:grid-cols-2 2xl:grid-cols-3">
          {catalogTemplates.map((template) => {
            const visual = getSiteTemplateVisual(template);
            const elite = getSiteTemplateEliteDetails(template);

            return (
              <article
                key={template.slug}
                className="group overflow-hidden rounded-[32px] border border-white/10 bg-white/[0.04] shadow-[0_18px_70px_rgba(0,0,0,0.18)] backdrop-blur transition hover:-translate-y-1 hover:bg-white/[0.05] hover:shadow-[0_24px_80px_rgba(0,0,0,0.26)]"
              >
                <div
                  className="relative h-56 overflow-hidden bg-cover"
                  style={{
                    backgroundImage: `linear-gradient(180deg,rgba(0,0,0,0.08),rgba(0,0,0,0.52)), ${visual.catalogGradient}, url(${visual.heroImage})`,
                    backgroundPosition: visual.heroImagePosition,
                  }}
                >
                  <div className="absolute inset-x-5 top-5 rounded-[20px] border border-white/12 bg-black/20 px-4 py-3 backdrop-blur">
                    <p className="text-xs font-black uppercase tracking-[0.16em] text-white/82">{elite.visualFocus}</p>
                  </div>
                  <div className="absolute inset-x-5 bottom-5 flex flex-wrap gap-2">
                    <span className="rounded-full border border-white/14 bg-white/[0.08] px-3 py-1 text-[11px] font-black uppercase tracking-[0.14em] text-white/76">
                      {template.niche}
                    </span>
                    <span className="rounded-full border border-white/14 bg-white/[0.08] px-3 py-1 text-[11px] font-black uppercase tracking-[0.14em] text-white/76">
                      {visual.archetype}
                    </span>
                  </div>
                </div>

                <div className="p-6">
                  <h3 className="text-2xl font-black text-white">{template.name}</h3>
                  <p className="mt-3 min-h-[96px] text-sm leading-6 text-white/62">{elite.authority.title}</p>

                  <div className="mt-5 grid grid-cols-3 gap-2">
                    {template.metrics.map((metric) => (
                      <div key={metric.label} className="rounded-[18px] border border-white/8 bg-white/[0.03] p-3">
                        <p className="text-[10px] font-black uppercase tracking-[0.14em] text-white/40">{metric.label}</p>
                        <p className="mt-1 text-sm font-black text-white">{metric.value}</p>
                      </div>
                    ))}
                  </div>

                  <div className="mt-5 flex flex-wrap gap-2">
                    {template.badges.slice(0, 2).map((badge) => (
                      <div key={badge} className="rounded-full border border-white/8 bg-white/[0.03] px-3 py-1.5 text-[11px] font-black text-white/60">
                        {badge}
                      </div>
                    ))}
                  </div>

                  <div className="mt-6 flex flex-col gap-2 sm:flex-row">
                    <Link
                      href={buildSiteTemplatePreviewPath(template)}
                      className="inline-flex h-11 flex-1 items-center justify-center gap-2 rounded-full border border-white/12 bg-white/[0.03] px-3 text-sm font-black text-white transition hover:bg-white/[0.08]"
                    >
                      <Eye className="h-4 w-4" />
                      Ver
                    </Link>
                    <Link
                      href={`${buildSiteTemplatePreviewPath(template)}#selecionar-template`}
                      className="inline-flex h-11 flex-1 items-center justify-center gap-2 rounded-full bg-white px-3 text-sm font-black text-stone-950 transition hover:bg-[#f5ede1]"
                    >
                      <MousePointer2 className="h-4 w-4" />
                      Selecionar
                    </Link>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <TemplateSelectionForm templates={SITE_TEMPLATES} defaultTemplateSlug={leadTemplate.slug} variant="premium" />
    </main>
  );
}

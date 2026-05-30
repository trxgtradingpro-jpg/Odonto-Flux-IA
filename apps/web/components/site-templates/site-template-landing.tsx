import type { CSSProperties } from "react";
import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  Clock3,
  MapPin,
  MessageCircle,
  ShieldCheck,
  Sparkles,
  Star,
} from "lucide-react";

import type { SiteTemplate } from "@/lib/site-templates";

function digitsOnly(value?: string | null) {
  return String(value || "").replace(/\D/g, "");
}

function buildWhatsAppHref(template: SiteTemplate, clinicName: string, whatsapp?: string | null) {
  const digits = digitsOnly(whatsapp);
  const message = encodeURIComponent(
    `Ola, quero selecionar o template ${template.name} para ${clinicName}. Pode me passar o proximo passo?`,
  );
  if (!digits) return `#selecionar-template`;
  return `https://wa.me/${digits}?text=${message}`;
}

export function SiteTemplateLanding({
  template,
  clinicName,
  city,
  whatsapp,
  showBackLink = true,
}: {
  template: SiteTemplate;
  clinicName?: string | null;
  city?: string | null;
  whatsapp?: string | null;
  showBackLink?: boolean;
}) {
  const resolvedClinic = String(clinicName || "").trim() || template.name;
  const resolvedCity = String(city || "").trim() || "sua cidade";
  const themeStyle = {
    "--template-primary": template.palette.primary,
    "--template-secondary": template.palette.secondary,
    "--template-accent": template.palette.accent,
    "--template-background": template.palette.background,
    "--template-surface": template.palette.surface,
    "--template-text": template.palette.text,
    "--template-muted": template.palette.muted,
  } as CSSProperties;
  const whatsappHref = buildWhatsAppHref(template, resolvedClinic, whatsapp);

  return (
    <main style={themeStyle} className="min-h-screen bg-[var(--template-background)] text-[var(--template-text)]">
      <section className="relative min-h-[92vh] overflow-hidden">
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: `url(${template.heroImage})` }}
        />
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(255,255,255,0.96)_0%,rgba(255,255,255,0.88)_46%,rgba(255,255,255,0.52)_100%)]" />
        <div className="relative mx-auto flex min-h-[92vh] w-full max-w-7xl flex-col px-4 py-5 sm:px-6 lg:px-8">
          <header className="flex items-center justify-between gap-4">
            <div className="min-w-0">
              <p className="text-xs font-black uppercase tracking-[0.18em] text-[var(--template-primary)]">
                {template.niche}
              </p>
              <p className="mt-1 truncate text-lg font-black">{resolvedClinic}</p>
            </div>
            {showBackLink ? (
              <Link
                href="/modelos-sites"
                className="inline-flex h-10 items-center justify-center rounded-lg border border-stone-300 bg-white/80 px-4 text-sm font-bold text-stone-900 transition hover:bg-white"
              >
                Modelos
              </Link>
            ) : null}
          </header>

          <div className="grid flex-1 items-center gap-8 py-10 lg:grid-cols-[minmax(0,1.02fr)_minmax(360px,0.72fr)]">
            <div>
              <div className="inline-flex items-center gap-2 rounded-lg border border-stone-200 bg-white/80 px-3 py-2 text-xs font-bold text-stone-700">
                <Sparkles className="h-4 w-4 text-[var(--template-accent)]" />
                Template profissional para {resolvedCity}
              </div>
              <h1 className="mt-6 max-w-4xl font-heading text-4xl font-black leading-[1.02] sm:text-5xl lg:text-6xl">
                {template.headline}
              </h1>
              <p className="mt-5 max-w-2xl text-base leading-7 text-[var(--template-muted)] sm:text-lg">
                {template.subheadline}
              </p>
              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <a
                  href={whatsappHref}
                  className="inline-flex h-12 items-center justify-center gap-2 rounded-lg bg-[var(--template-primary)] px-5 text-sm font-black text-white transition hover:opacity-90"
                >
                  <MessageCircle className="h-5 w-5" />
                  Selecionar template
                </a>
                <a
                  href="#servicos"
                  className="inline-flex h-12 items-center justify-center gap-2 rounded-lg border border-stone-300 bg-white px-5 text-sm font-black text-stone-950 transition hover:bg-stone-100"
                >
                  Ver estrutura
                  <ArrowRight className="h-4 w-4" />
                </a>
              </div>
              <div className="mt-8 grid max-w-2xl gap-3 sm:grid-cols-3">
                {template.metrics.map((metric) => (
                  <div key={metric.label} className="rounded-lg border border-stone-200 bg-white/90 p-4">
                    <p className="text-xs font-bold uppercase tracking-[0.14em] text-[var(--template-muted)]">
                      {metric.label}
                    </p>
                    <p className="mt-2 text-xl font-black">{metric.value}</p>
                  </div>
                ))}
              </div>
            </div>

            <aside className="rounded-lg border border-stone-200 bg-white/90 p-5 shadow-[0_24px_70px_rgba(28,25,23,0.13)]">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-black text-stone-950">{template.shortName}</p>
                  <p className="mt-1 text-sm leading-6 text-stone-600">{template.outcome}</p>
                </div>
                <div className="rounded-lg bg-[var(--template-accent)] px-3 py-2 text-xs font-black text-white">
                  pronto
                </div>
              </div>
              <div className="mt-5 space-y-3">
                {template.badges.map((badge) => (
                  <div key={badge} className="flex items-center gap-3 rounded-lg border border-stone-200 bg-stone-50 p-3">
                    <CheckCircle2 className="h-4 w-4 text-[var(--template-primary)]" />
                    <span className="text-sm font-bold text-stone-800">{badge}</span>
                  </div>
                ))}
              </div>
              <div className="mt-5 rounded-lg border border-stone-200 p-4">
                <p className="text-xs font-black uppercase tracking-[0.16em] text-stone-500">Intencao local</p>
                <p className="mt-2 text-sm leading-6 text-stone-700">
                  Estrutura pensada para busca no Google, prova de confianca, mapa e WhatsApp no momento certo.
                </p>
              </div>
            </aside>
          </div>
        </div>
      </section>

      <section id="servicos" className="mx-auto w-full max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <div className="grid gap-8 lg:grid-cols-[0.8fr_1.2fr]">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.18em] text-[var(--template-primary)]">Oferta</p>
            <h2 className="mt-3 font-heading text-3xl font-black sm:text-4xl">Servicos que o paciente entende rapido</h2>
            <p className="mt-4 text-base leading-7 text-[var(--template-muted)]">
              O template organiza as principais buscas do nicho para reduzir duvida e levar o visitante para uma acao clara.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {template.services.map((service) => (
              <div key={service} className="rounded-lg border border-stone-200 bg-[var(--template-surface)] p-5">
                <p className="text-base font-black">{service}</p>
                <p className="mt-2 text-sm leading-6 text-[var(--template-muted)]">
                  Bloco editavel com explicacao curta, indicacao e chamada para atendimento.
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="border-y border-stone-200 bg-white/70">
        <div className="mx-auto grid w-full max-w-7xl gap-4 px-4 py-14 sm:px-6 lg:grid-cols-3 lg:px-8">
          {template.sections.map((section) => (
            <article key={section.title} className="rounded-lg border border-stone-200 bg-white p-5">
              <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--template-primary)] text-white">
                <ShieldCheck className="h-5 w-5" />
              </div>
              <h3 className="text-lg font-black">{section.title}</h3>
              <p className="mt-3 text-sm leading-6 text-[var(--template-muted)]">{section.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="mx-auto grid w-full max-w-7xl gap-8 px-4 py-16 sm:px-6 lg:grid-cols-[1.05fr_0.95fr] lg:px-8">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.18em] text-[var(--template-primary)]">Confianca</p>
          <h2 className="mt-3 font-heading text-3xl font-black sm:text-4xl">Sinais que ajudam o paciente a escolher</h2>
          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            {template.trustSignals.map((signal) => (
              <div key={signal} className="flex gap-3 rounded-lg border border-stone-200 bg-white p-4">
                <Star className="mt-0.5 h-4 w-4 shrink-0 text-[var(--template-accent)]" />
                <p className="text-sm font-bold leading-6">{signal}</p>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-lg border border-stone-200 bg-white p-6">
          <p className="text-xs font-black uppercase tracking-[0.18em] text-[var(--template-primary)]">Conversao</p>
          <div className="mt-5 space-y-4">
            {template.conversionHooks.map((hook) => (
              <div key={hook} className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--template-primary)] text-white">
                  <ArrowRight className="h-4 w-4" />
                </div>
                <span className="text-sm font-black">{hook}</span>
              </div>
            ))}
          </div>
          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg bg-stone-50 p-4">
              <MapPin className="h-5 w-5 text-[var(--template-primary)]" />
              <p className="mt-3 text-sm font-bold">Mapa, bairro e cidade em destaque.</p>
            </div>
            <div className="rounded-lg bg-stone-50 p-4">
              <Clock3 className="h-5 w-5 text-[var(--template-primary)]" />
              <p className="mt-3 text-sm font-bold">Horario e proximo passo sem confusao.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="bg-[var(--template-primary)] px-4 py-14 text-white sm:px-6 lg:px-8">
        <div className="mx-auto grid w-full max-w-7xl gap-8 lg:grid-cols-[0.85fr_1.15fr] lg:items-center">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.18em] text-white/70">FAQ</p>
            <h2 className="mt-3 font-heading text-3xl font-black sm:text-4xl">Perguntas que reduzem objecoes</h2>
          </div>
          <div className="grid gap-3">
            {template.faqs.map((faq) => (
              <article key={faq.question} className="rounded-lg border border-white/20 bg-white/10 p-5">
                <h3 className="text-base font-black">{faq.question}</h3>
                <p className="mt-2 text-sm leading-6 text-white/80">{faq.answer}</p>
              </article>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}

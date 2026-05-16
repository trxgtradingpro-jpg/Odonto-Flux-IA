import Link from "next/link";
import { ArrowLeft, Building2, FileText, ShieldCheck } from "lucide-react";

import { BRAND_DOMAIN, BRAND_LEGAL_ENTITY, BRAND_NAME, BRAND_SUPPORT_EMAIL } from "@/lib/brand";

type LegalSection = {
  id: string;
  title: string;
  paragraphs: readonly string[];
  bullets?: readonly string[];
};

type LegalFact = {
  label: string;
  value: string;
};

type LegalPageShellProps = {
  eyebrow: string;
  title: string;
  summary: string;
  updatedAt: string;
  version: string;
  sections: LegalSection[];
  facts: readonly LegalFact[];
  relatedLinks: ReadonlyArray<{ href: string; label: string }>;
};

export function LegalPageShell({
  eyebrow,
  title,
  summary,
  updatedAt,
  version,
  sections,
  facts,
  relatedLinks,
}: LegalPageShellProps) {
  return (
    <div className="min-h-screen bg-[#f6f0e8] text-stone-950">
      <div className="absolute inset-x-0 top-0 h-[480px] bg-[radial-gradient(circle_at_top_left,_rgba(22,163,74,0.18),_transparent_32%),radial-gradient(circle_at_top_right,_rgba(59,130,246,0.12),_transparent_24%),linear-gradient(180deg,#07110d_0%,#10211e_46%,#f6f0e8_100%)]" />

      <header className="sticky top-0 z-30 border-b border-white/10 bg-stone-950/82 backdrop-blur-xl">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
          <Link href="/" className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-[18px] bg-gradient-to-br from-emerald-300 via-teal-300 to-cyan-300 text-sm font-black text-stone-950 shadow-[0_10px_30px_rgba(16,185,129,0.25)]">
              CF
            </div>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.24em] text-white/45">{BRAND_NAME}</p>
              <p className="text-sm font-semibold text-white">Documentos legais</p>
            </div>
          </Link>

          <div className="flex items-center gap-2">
            <Link
              href="/"
              className="inline-flex items-center rounded-full border border-white/15 bg-white/5 px-4 py-2 text-sm font-semibold text-white transition hover:bg-white/10"
            >
              <ArrowLeft className="mr-2 h-4 w-4" />
              Voltar ao site
            </Link>
            <Link
              href="/login"
              className="inline-flex items-center rounded-full bg-white px-4 py-2 text-sm font-semibold text-stone-950 transition hover:bg-emerald-50"
            >
              Entrar
            </Link>
          </div>
        </div>
      </header>

      <main className="relative z-10">
        <section className="mx-auto w-full max-w-7xl px-4 pb-10 pt-12 sm:px-6 lg:px-8 lg:pb-14 lg:pt-16">
          <div className="grid gap-6 lg:grid-cols-[1.05fr_0.95fr] lg:items-start">
            <div>
              <p className="inline-flex rounded-full border border-emerald-300/20 bg-emerald-400/10 px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.24em] text-emerald-100">
                {eyebrow}
              </p>
              <h1 className="mt-5 max-w-4xl text-4xl font-black leading-tight text-white sm:text-5xl">{title}</h1>
              <p className="mt-5 max-w-3xl text-base leading-8 text-white/74 sm:text-lg">{summary}</p>
            </div>

            <div className="rounded-[32px] border border-white/12 bg-white/8 p-4 shadow-[0_24px_80px_rgba(0,0,0,0.22)] backdrop-blur-xl">
              <div className="grid gap-4 rounded-[28px] border border-stone-200 bg-[#fcf8f3] p-5 sm:grid-cols-2">
                <div className="rounded-[22px] border border-stone-200 bg-white p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Ultima atualizacao</p>
                  <p className="mt-2 text-sm font-semibold text-stone-950">{updatedAt}</p>
                </div>
                <div className="rounded-[22px] border border-stone-200 bg-white p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Versao</p>
                  <p className="mt-2 text-sm font-semibold text-stone-950">{version}</p>
                </div>

                {facts.map((fact) => (
                  <div key={fact.label} className="rounded-[22px] border border-stone-200 bg-white p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">{fact.label}</p>
                    <p className="mt-2 text-sm leading-6 text-stone-700">{fact.value}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="mx-auto w-full max-w-7xl px-4 pb-12 sm:px-6 lg:px-8">
          <div className="grid gap-8 lg:grid-cols-[0.34fr_0.66fr]">
            <aside className="space-y-6 lg:sticky lg:top-24 lg:self-start">
              <div className="rounded-[28px] border border-stone-200 bg-white p-5 shadow-[0_20px_70px_rgba(15,23,42,0.08)]">
                <div className="flex items-center gap-3">
                  <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-stone-950 text-white">
                    <FileText className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Navegacao</p>
                    <p className="text-sm font-semibold text-stone-950">Veja os pontos principais</p>
                  </div>
                </div>

                <div className="mt-5 space-y-2">
                  {sections.map((section, index) => (
                    <a
                      key={section.id}
                      href={`#${section.id}`}
                      className="block rounded-[18px] border border-stone-200 bg-[#faf6ef] px-4 py-3 text-sm font-semibold text-stone-700 transition hover:border-emerald-300 hover:text-stone-950"
                    >
                      <span className="mr-2 text-stone-400">{String(index + 1).padStart(2, "0")}</span>
                      {section.title}
                    </a>
                  ))}
                </div>
              </div>

              <div className="rounded-[28px] border border-stone-200 bg-stone-950 p-5 text-white shadow-[0_20px_70px_rgba(15,23,42,0.18)]">
                <div className="flex items-center gap-3">
                  <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white/10 text-emerald-200">
                    <ShieldCheck className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-white/48">Contato</p>
                    <p className="text-sm font-semibold text-white">Duvidas sobre uso e privacidade</p>
                  </div>
                </div>
                <p className="mt-4 text-sm leading-7 text-white/72">
                  Em caso de duvidas, solicitacoes de titulares ou notificacoes contratuais, utilize o suporte oficial
                  da {BRAND_NAME}.
                </p>
                <div className="mt-4 rounded-[20px] border border-white/10 bg-white/6 p-4 text-sm text-white/82">
                  <p>{BRAND_LEGAL_ENTITY}</p>
                  <p className="mt-2">
                    <a className="font-semibold text-white" href={`mailto:${BRAND_SUPPORT_EMAIL}`}>
                      {BRAND_SUPPORT_EMAIL}
                    </a>
                  </p>
                  <p className="mt-2">{BRAND_DOMAIN}</p>
                </div>
              </div>
            </aside>

            <div className="space-y-5">
              {sections.map((section) => (
                <section
                  key={section.id}
                  id={section.id}
                  className="scroll-mt-28 rounded-[30px] border border-stone-200 bg-white p-6 shadow-[0_20px_70px_rgba(15,23,42,0.08)] sm:p-7"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#faf6ef] text-stone-950">
                      <Building2 className="h-4 w-4" />
                    </div>
                    <h2 className="text-2xl font-black text-stone-950">{section.title}</h2>
                  </div>

                  <div className="mt-5 space-y-4 text-sm leading-7 text-stone-700 sm:text-base">
                    {section.paragraphs.map((paragraph) => (
                      <p key={paragraph}>{paragraph}</p>
                    ))}
                  </div>

                  {section.bullets?.length ? (
                    <div className="mt-5 space-y-3">
                      {section.bullets.map((bullet) => (
                        <div key={bullet} className="flex items-start gap-3 text-sm leading-7 text-stone-700 sm:text-base">
                          <span className="mt-2 h-2.5 w-2.5 shrink-0 rounded-full bg-emerald-500" />
                          <span>{bullet}</span>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </section>
              ))}
            </div>
          </div>
        </section>

        <section className="mx-auto w-full max-w-7xl px-4 pb-14 sm:px-6 lg:px-8">
          <div className="grid gap-5 rounded-[36px] border border-stone-200 bg-stone-950 p-6 text-white shadow-[0_24px_80px_rgba(15,23,42,0.18)] sm:p-8 lg:grid-cols-[1fr_auto] lg:items-center">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-white/45">Documentos relacionados</p>
              <h2 className="mt-3 text-2xl font-black">Transparencia juridica e operacional no mesmo lugar.</h2>
              <p className="mt-3 max-w-3xl text-sm leading-7 text-white/70">
                Estes documentos se complementam com contratos, propostas comerciais, aditivos, avisos operacionais e
                configuracoes especificas de cada clinica dentro da plataforma.
              </p>
            </div>

            <div className="flex flex-wrap gap-3 lg:justify-end">
              {relatedLinks.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className="inline-flex items-center rounded-full border border-white/12 bg-white/6 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-white/10"
                >
                  {link.label}
                </Link>
              ))}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

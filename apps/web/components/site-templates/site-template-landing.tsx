"use client";

import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Award,
  Building2,
  CalendarDays,
  CheckCircle2,
  Clock3,
  HeartPulse,
  MapPin,
  MessageCircle,
  Menu,
  Navigation,
  Quote,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  UserRoundCheck,
  UsersRound,
  X,
} from "lucide-react";

import type { SiteTemplate, SiteTemplateEliteDetails, SiteTemplateSectionKey, SiteTemplateVisual } from "@/lib/site-templates";
import {
  buildSiteTemplatePreviewPath,
  buildSiteTemplateSectionPath,
  getSiteTemplateEliteDetails,
  getSiteTemplateVisual,
} from "@/lib/site-templates";

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

function layoutClasses(layout: SiteTemplateVisual["layout"]) {
  const styles: Record<SiteTemplateVisual["layout"], { hero: string; panel: string; band: string; section: string }> = {
    boutique: {
      hero: "lg:grid-cols-[minmax(0,1fr)]",
      panel: "border-white/18 bg-white/12 shadow-[0_30px_90px_rgba(12,12,12,0.18)]",
      band: "bg-stone-950",
      section: "bg-[#f7f4ec]",
    },
    access: {
      hero: "lg:grid-cols-[minmax(0,0.92fr)_minmax(390px,0.82fr)]",
      panel: "border-sky-100 bg-white/92 shadow-[0_24px_70px_rgba(15,23,42,0.13)]",
      band: "bg-sky-50/70",
      section: "bg-white",
    },
    calm: {
      hero: "lg:grid-cols-[minmax(0,0.96fr)_minmax(390px,0.76fr)]",
      panel: "border-indigo-100 bg-white/88 shadow-[0_24px_70px_rgba(49,46,129,0.12)]",
      band: "bg-indigo-50/60",
      section: "bg-white/76",
    },
    clinical: {
      hero: "lg:grid-cols-[minmax(0,1fr)_minmax(410px,0.78fr)]",
      panel: "border-slate-200 bg-white/92 shadow-[0_24px_70px_rgba(15,23,42,0.12)]",
      band: "bg-white/78",
      section: "bg-slate-50/70",
    },
    editorial: {
      hero: "lg:grid-cols-[minmax(0,0.9fr)_minmax(430px,0.9fr)]",
      panel: "border-rose-100 bg-white/90 shadow-[0_24px_70px_rgba(136,19,55,0.12)]",
      band: "bg-rose-50/55",
      section: "bg-white",
    },
    performance: {
      hero: "lg:grid-cols-[minmax(0,0.92fr)_minmax(410px,0.82fr)]",
      panel: "border-amber-100 bg-white/92 shadow-[0_24px_70px_rgba(120,53,15,0.12)]",
      band: "bg-amber-50/60",
      section: "bg-white",
    },
    active: {
      hero: "lg:grid-cols-[minmax(380px,0.88fr)_minmax(0,0.92fr)]",
      panel: "border-emerald-100 bg-white/92 shadow-[0_24px_70px_rgba(20,83,45,0.12)]",
      band: "bg-emerald-50/60",
      section: "bg-white",
    },
    profile: {
      hero: "lg:grid-cols-[minmax(360px,0.72fr)_minmax(0,1fr)]",
      panel: "border-indigo-100 bg-white/92 shadow-[0_24px_70px_rgba(49,46,129,0.12)]",
      band: "bg-indigo-50/60",
      section: "bg-white",
    },
    signature: {
      hero: "lg:grid-cols-[minmax(0,0.98fr)_minmax(430px,0.82fr)]",
      panel: "border-stone-200 bg-white/90 shadow-[0_28px_80px_rgba(28,25,23,0.14)]",
      band: "bg-stone-50/70",
      section: "bg-white",
    },
  };
  return styles[layout];
}

function sectionVariantClasses(layout: SiteTemplateVisual["layout"]) {
  const styles: Record<
    SiteTemplateVisual["layout"],
    {
      journeyBand: string;
      journeyGrid: string;
      journeyCard: string;
      journeyText: string;
      serviceGrid: string;
      serviceCard: string;
    }
  > = {
    boutique: {
      journeyBand: "border-y border-stone-800 bg-stone-950",
      journeyGrid: "mx-auto grid w-full max-w-7xl gap-3 px-4 py-8 sm:px-6 md:grid-cols-4 lg:px-8",
      journeyCard: "border-white/12 bg-white/10 p-4 text-white shadow-sm backdrop-blur",
      journeyText: "text-white/86",
      serviceGrid: "grid gap-4 sm:grid-cols-2",
      serviceCard: "border-stone-200 bg-white",
    },
    access: {
      journeyBand: "border-y border-sky-100 bg-sky-50",
      journeyGrid: "mx-auto grid w-full max-w-7xl gap-3 px-4 py-7 sm:px-6 md:grid-cols-4 lg:px-8",
      journeyCard: "border-sky-100 bg-[#f7faff] p-4 shadow-sm",
      journeyText: "text-slate-800",
      serviceGrid: "grid gap-3",
      serviceCard: "border-sky-100 bg-[#f7faff]",
    },
    calm: {
      journeyBand: "border-y border-indigo-100 bg-indigo-50/60",
      journeyGrid: "mx-auto grid w-full max-w-5xl gap-3 px-4 py-8 sm:px-6 md:grid-cols-4 lg:px-8",
      journeyCard: "border-indigo-100 bg-white/82 p-4 text-center shadow-sm",
      journeyText: "text-slate-700",
      serviceGrid: "grid gap-3 sm:grid-cols-2",
      serviceCard: "border-indigo-100 bg-white/86",
    },
    clinical: {
      journeyBand: "border-y border-slate-200 bg-[#f3f5fb]",
      journeyGrid: "mx-auto grid w-full max-w-7xl gap-3 px-4 py-7 sm:px-6 md:grid-cols-4 lg:px-8",
      journeyCard: "border-slate-200 bg-[#f7f8fc] p-4 shadow-sm",
      journeyText: "text-slate-800",
      serviceGrid: "grid gap-3 sm:grid-cols-2",
      serviceCard: "border-slate-200 bg-[#f7f8fc]",
    },
    editorial: {
      journeyBand: "border-y border-stone-800 bg-stone-950",
      journeyGrid: "mx-auto grid w-full max-w-7xl gap-3 px-4 py-8 sm:px-6 md:grid-cols-4 lg:px-8",
      journeyCard: "border-white/12 bg-white/10 p-4 text-white shadow-sm backdrop-blur",
      journeyText: "text-white/88",
      serviceGrid: "grid gap-4 sm:grid-cols-2",
      serviceCard: "border-rose-100 bg-white",
    },
    performance: {
      journeyBand: "border-y border-stone-800 bg-stone-950",
      journeyGrid: "mx-auto grid w-full max-w-7xl gap-3 px-4 py-7 sm:px-6 md:grid-cols-4 lg:px-8",
      journeyCard: "border-white/12 bg-white/10 p-4 text-white shadow-sm backdrop-blur",
      journeyText: "text-white/90",
      serviceGrid: "grid gap-3",
      serviceCard: "border-amber-100 bg-white",
    },
    active: {
      journeyBand: "border-y border-emerald-100 bg-emerald-50/70",
      journeyGrid: "mx-auto grid w-full max-w-7xl gap-3 px-4 py-7 sm:px-6 md:grid-cols-4 lg:px-8",
      journeyCard: "border-emerald-100 bg-white p-4 shadow-sm",
      journeyText: "text-emerald-950",
      serviceGrid: "grid gap-3 sm:grid-cols-2",
      serviceCard: "border-emerald-100 bg-white",
    },
    profile: {
      journeyBand: "border-y border-indigo-100 bg-indigo-50/70",
      journeyGrid: "mx-auto grid w-full max-w-6xl gap-3 px-4 py-7 sm:px-6 md:grid-cols-4 lg:px-8",
      journeyCard: "border-indigo-100 bg-white p-4 shadow-sm",
      journeyText: "text-indigo-950",
      serviceGrid: "grid gap-3",
      serviceCard: "border-indigo-100 bg-white",
    },
    signature: {
      journeyBand: "border-y border-stone-200 bg-stone-50/70",
      journeyGrid: "mx-auto grid w-full max-w-7xl gap-3 px-4 py-7 sm:px-6 md:grid-cols-4 lg:px-8",
      journeyCard: "border-stone-200 bg-white/84 p-4 shadow-sm",
      journeyText: "text-stone-800",
      serviceGrid: "grid gap-3 sm:grid-cols-2",
      serviceCard: "border-stone-200 bg-white",
    },
  };
  return styles[layout];
}

function contentSurfaceClasses(layout: SiteTemplateVisual["layout"]) {
  const styles: Record<
    SiteTemplateVisual["layout"],
    {
      section: string;
      sectionAlt: string;
      card: string;
      cardStrong: string;
      subtle: string;
    }
  > = {
    boutique: {
      section: "border-white/10 bg-stone-950",
      sectionAlt: "border-white/10 bg-stone-950",
      card: "border-white/12 bg-white/10 backdrop-blur",
      cardStrong: "border-white/12 bg-white/10 backdrop-blur",
      subtle: "bg-white/10",
    },
    access: {
      section: "border-sky-100 bg-[#f4f8ff]",
      sectionAlt: "border-sky-100 bg-[#edf4ff]",
      card: "border-sky-100 bg-white/78 backdrop-blur-sm",
      cardStrong: "border-sky-100 bg-[#f8fbff]",
      subtle: "bg-[#eaf2ff]",
    },
    calm: {
      section: "border-indigo-100 bg-[#fbfbff]",
      sectionAlt: "border-indigo-100 bg-[#f3f4ff]",
      card: "border-indigo-100 bg-white/84 backdrop-blur-sm",
      cardStrong: "border-indigo-100 bg-[#fbfbff]",
      subtle: "bg-indigo-50/80",
    },
    clinical: {
      section: "border-slate-200 bg-[#f5f7fc]",
      sectionAlt: "border-slate-200 bg-[#edf2f8]",
      card: "border-slate-200 bg-white/76 backdrop-blur-sm",
      cardStrong: "border-slate-200 bg-[#fafbff]",
      subtle: "bg-[#edf2f8]",
    },
    editorial: {
      section: "border-rose-100 bg-[#fff7f8]",
      sectionAlt: "border-rose-100 bg-[#fff1f4]",
      card: "border-rose-100 bg-white/84 backdrop-blur-sm",
      cardStrong: "border-rose-100 bg-[#fffafb]",
      subtle: "bg-rose-50/80",
    },
    performance: {
      section: "border-amber-100 bg-[#fffaf1]",
      sectionAlt: "border-amber-100 bg-[#fff3df]",
      card: "border-amber-100 bg-white/84 backdrop-blur-sm",
      cardStrong: "border-amber-100 bg-[#fffdf8]",
      subtle: "bg-amber-50/80",
    },
    active: {
      section: "border-emerald-100 bg-[#f5fdfa]",
      sectionAlt: "border-emerald-100 bg-[#edfbf4]",
      card: "border-emerald-100 bg-white/84 backdrop-blur-sm",
      cardStrong: "border-emerald-100 bg-[#f8fffb]",
      subtle: "bg-emerald-50/90",
    },
    profile: {
      section: "border-indigo-100 bg-[#f8f9ff]",
      sectionAlt: "border-indigo-100 bg-[#eef1ff]",
      card: "border-indigo-100 bg-white/84 backdrop-blur-sm",
      cardStrong: "border-indigo-100 bg-[#fbfbff]",
      subtle: "bg-indigo-50/90",
    },
    signature: {
      section: "border-stone-200 bg-[#fbf8f3]",
      sectionAlt: "border-stone-200 bg-[#f3eee5]",
      card: "border-stone-200 bg-white/84 backdrop-blur-sm",
      cardStrong: "border-stone-200 bg-[#fffdfa]",
      subtle: "bg-stone-100/90",
    },
  };
  return styles[layout];
}

function motionClass(motion: SiteTemplateEliteDetails["motion"]) {
  const styles: Record<SiteTemplateEliteDetails["motion"], string> = {
    calm: "template-motion-calm",
    cinematic: "template-motion-cinematic",
    clinical: "template-motion-clinical",
    direct: "template-motion-direct",
    editorial: "template-motion-editorial",
    performance: "template-motion-performance",
  };
  return styles[motion];
}

function revealStyle(index: number) {
  return { "--template-delay": `${index * 90}ms` } as CSSProperties;
}

function TemplateAnimationStyles() {
  return (
    <style>{`
      @keyframes templateReveal {
        from { opacity: 0; transform: translateY(18px); }
        to { opacity: 1; transform: translateY(0); }
      }
      @keyframes templateHeroZoom {
        from { transform: scale(1); }
        to { transform: scale(1.06); }
      }
      @keyframes templateFloat {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-10px); }
      }
      @keyframes templateIntroStroke {
        from { stroke-dashoffset: 240; opacity: 0.2; }
        to { stroke-dashoffset: 0; opacity: 1; }
      }
      @keyframes templateIntroRise {
        from { opacity: 0; transform: translateY(16px); }
        to { opacity: 1; transform: translateY(0); }
      }
      @keyframes templateIntroPulse {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.035); }
      }
      .template-reveal {
        opacity: 0;
        animation: templateReveal 780ms cubic-bezier(0.22, 1, 0.36, 1) both;
        animation-delay: var(--template-delay, 0ms);
      }
      .template-hero-image {
        animation: templateHeroZoom 18s ease-in-out infinite alternate;
        transform-origin: center;
      }
      .template-float {
        animation: templateFloat 7s ease-in-out infinite;
      }
      .template-intro-stroke {
        stroke-dasharray: 240;
        stroke-dashoffset: 240;
        animation: templateIntroStroke 1200ms cubic-bezier(0.22, 1, 0.36, 1) forwards;
      }
      .template-intro-copy {
        opacity: 0;
        animation: templateIntroRise 760ms cubic-bezier(0.22, 1, 0.36, 1) 260ms forwards;
      }
      .template-intro-mark {
        animation: templateIntroPulse 3.4s ease-in-out infinite;
      }
      .template-motion-calm .template-reveal { animation-duration: 980ms; }
      .template-motion-direct .template-reveal { animation-duration: 560ms; }
      .template-motion-performance .template-reveal { animation-duration: 620ms; }
      .template-motion-clinical .template-hero-image { animation-duration: 24s; }
      .template-motion-editorial .template-hero-image { animation-duration: 20s; }
      @media (prefers-reduced-motion: reduce) {
        .template-reveal,
        .template-hero-image,
        .template-float {
          animation: none !important;
          opacity: 1 !important;
          transform: none !important;
        }
      }
    `}</style>
  );
}

function SectionHeader({
  eyebrow,
  title,
  body,
  align = "left",
  dark = false,
}: {
  eyebrow: string;
  title: string;
  body?: string;
  align?: "left" | "center";
  dark?: boolean;
}) {
  return (
    <div className={align === "center" ? "mx-auto max-w-3xl text-center" : "max-w-3xl"}>
      <p className={`text-xs font-black uppercase tracking-[0.18em] ${dark ? "text-white/58" : "text-[var(--template-primary)]"}`}>
        {eyebrow}
      </p>
      <h2 className="mt-3 font-heading text-3xl font-black leading-tight sm:text-4xl">{title}</h2>
      {body ? <p className={`mt-4 text-base leading-7 ${dark ? "text-white/68" : "text-[var(--template-muted)]"}`}>{body}</p> : null}
    </div>
  );
}

function IconFrame({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[var(--template-primary)] text-white shadow-[0_14px_30px_rgba(15,118,110,0.18)]">
      {children}
    </div>
  );
}

type PremiumQueryParams = {
  clinic?: string | null;
  city?: string | null;
  whatsapp?: string | null;
};

type PremiumSitePage = "home" | SiteTemplateSectionKey;

const PREMIUM_SITE_PAGES: Array<{ key: PremiumSitePage; label: string }> = [
  { key: "home", label: "Home" },
  { key: "tratamentos", label: "Tratamentos" },
  { key: "equipe", label: "Equipe" },
  { key: "estrutura", label: "Estrutura" },
  { key: "contato", label: "Contato" },
];

function buildPremiumPagePath(template: SiteTemplate, page: PremiumSitePage, params?: PremiumQueryParams) {
  if (page === "home") return buildSiteTemplatePreviewPath(template, params);
  return buildSiteTemplateSectionPath(template, page, params);
}

function PremiumBrandMark({ className = "h-12 w-12", animated = false }: { className?: string; animated?: boolean }) {
  const strokeClass = animated ? "template-intro-stroke" : "";
  return (
    <svg viewBox="0 0 120 120" className={className} fill="none" aria-hidden="true">
      <path
        d="M60 12 92 28 92 67C92 86 78 100 60 108 42 100 28 86 28 67V28L60 12Z"
        className={strokeClass}
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M60 30V76" className={strokeClass} stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
      <path d="M44 44C50 37 70 37 76 44" className={strokeClass} stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
      <path d="M42 60C49 69 71 69 78 60" className={strokeClass} stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
      <circle cx="60" cy="86" r="4" fill="currentColor" className={animated ? "template-intro-copy" : ""} />
    </svg>
  );
}

function FloatingWhatsAppButton({
  href,
  elevatedMobile = false,
}: {
  href: string;
  elevatedMobile?: boolean;
}) {
  return (
    <a
      href={href}
      aria-label="Falar no WhatsApp"
      className={`fixed right-4 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-[#25D366] text-white shadow-[0_18px_44px_rgba(37,211,102,0.36)] transition hover:scale-[1.03] hover:brightness-105 ${
        elevatedMobile ? "bottom-20 md:bottom-6" : "bottom-6"
      }`}
    >
      <MessageCircle className="h-7 w-7" />
    </a>
  );
}

function PremiumIntroReveal({ clinicName, closing = false }: { clinicName: string; closing?: boolean }) {
  return (
    <div
      className={`pointer-events-none fixed inset-0 z-[90] flex items-center justify-center bg-black transition-opacity duration-700 ${
        closing ? "opacity-0" : "opacity-100"
      }`}
      aria-hidden="true"
    >
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.08),transparent_42%)] opacity-80" />
      <div className="relative flex flex-col items-center gap-6 px-6 text-center">
        <div className="template-intro-mark rounded-full border border-white/10 bg-white/[0.03] p-6 shadow-[0_20px_80px_rgba(255,255,255,0.05)]">
          <PremiumBrandMark className="h-28 w-28 text-white sm:h-32 sm:w-32" animated />
        </div>
        <div className="template-intro-copy">
          <p className="text-[11px] font-black uppercase tracking-[0.34em] text-white/56">Atelier odontologico</p>
          <p className="mt-4 font-heading text-3xl font-black text-white sm:text-4xl">{clinicName}</p>
        </div>
      </div>
    </div>
  );
}

function PremiumSiteHeader({
  template,
  resolvedClinic,
  showBackLink,
  whatsappHref,
  activePage,
  navParams,
}: {
  template: SiteTemplate;
  resolvedClinic: string;
  showBackLink: boolean;
  whatsappHref: string;
  activePage: PremiumSitePage;
  navParams?: PremiumQueryParams;
}) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const bevelStyle = {
    clipPath: "polygon(14px 0,100% 0,calc(100% - 14px) 100%,0 100%)",
  } as CSSProperties;
  const navItems = PREMIUM_SITE_PAGES.map((item) => ({
    ...item,
    href: buildPremiumPagePath(template, item.key, navParams),
  }));

  useEffect(() => {
    if (!mobileMenuOpen) {
      document.body.style.removeProperty("overflow");
      return;
    }

    document.body.style.setProperty("overflow", "hidden");
    return () => {
      document.body.style.removeProperty("overflow");
    };
  }, [mobileMenuOpen]);

  return (
    <header className="template-reveal sticky top-0 z-[80] pt-2" style={revealStyle(0)}>
      <div className="rounded-2xl border border-white/10 bg-black/30 px-4 py-3 backdrop-blur-xl">
        <div className="flex items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-full border border-white/12 bg-white/[0.04] text-white">
              <PremiumBrandMark className="h-8 w-8" />
            </div>
            <div className="min-w-0">
              <p className="text-[11px] font-black uppercase tracking-[0.26em] text-white/46">{template.niche}</p>
              <p className="truncate text-lg font-black text-white">{resolvedClinic}</p>
            </div>
          </div>

          <nav className="hidden items-center gap-2 xl:flex">
            {navItems.map((item) => {
              const isActive = item.key === activePage;
              return (
                <Link
                  key={item.key}
                  href={item.href}
                  style={bevelStyle}
                  className={`inline-flex h-11 items-center px-4 text-xs font-black uppercase tracking-[0.18em] transition ${
                    isActive
                      ? "bg-white text-stone-950 shadow-[0_18px_44px_rgba(255,255,255,0.12)]"
                      : "border border-white/12 bg-white/[0.08] text-white/80 hover:bg-white/15 hover:text-white"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="hidden items-center gap-2 xl:flex">
            {showBackLink ? (
              <Link
                href="/modelos-sites"
                className="inline-flex h-11 items-center justify-center rounded-full border border-white/12 px-4 text-xs font-black uppercase tracking-[0.18em] text-white/80 transition hover:bg-white/10 hover:text-white"
              >
                Modelos
              </Link>
            ) : null}
            <a
              href={whatsappHref}
              style={bevelStyle}
              className="inline-flex h-11 items-center justify-center bg-[var(--template-primary)] px-5 text-xs font-black uppercase tracking-[0.18em] text-white shadow-[0_18px_44px_rgba(15,118,110,0.25)] transition hover:brightness-110"
            >
              Agendar
            </a>
          </div>

          <div className="flex items-center gap-2 xl:hidden">
            <a
              href={whatsappHref}
              className="hidden h-10 items-center justify-center rounded-full bg-[var(--template-primary)] px-4 text-[11px] font-black uppercase tracking-[0.18em] text-white sm:inline-flex"
            >
              Agendar
            </a>
            <button
              type="button"
              onClick={() => setMobileMenuOpen((current) => !current)}
              className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-white/12 bg-white/[0.08] text-white transition hover:bg-white/12"
              aria-expanded={mobileMenuOpen}
              aria-label={mobileMenuOpen ? "Fechar menu" : "Abrir menu"}
            >
              {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>
      </div>

      {mobileMenuOpen ? (
        <div
          className="fixed inset-0 z-[70] bg-stone-950/92 backdrop-blur-md xl:hidden"
          onClick={() => setMobileMenuOpen(false)}
          aria-hidden="true"
        >
          <div className="flex min-h-full" onClick={(event) => event.stopPropagation()}>
            <div className="flex min-h-screen w-full flex-col overflow-y-auto bg-[#0b0b0c]">
              <div className="flex items-center justify-between gap-3 border-b border-white/10 px-4 py-4 sm:px-5">
                <div className="flex min-w-0 items-center gap-3">
                  <div className="flex h-11 w-11 items-center justify-center rounded-full border border-white/12 bg-white/[0.04] text-white">
                    <PremiumBrandMark className="h-7 w-7" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-[10px] font-black uppercase tracking-[0.26em] text-white/46">{template.niche}</p>
                    <p className="truncate text-sm font-black text-white sm:text-base">{resolvedClinic}</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setMobileMenuOpen(false)}
                  className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-white/12 bg-white/[0.08] text-white transition hover:bg-white/12"
                  aria-label="Fechar menu"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="flex flex-1 flex-col gap-3 px-4 py-5 sm:px-5">
                <nav className="grid gap-2">
                  {navItems.map((item, index) => {
                    const isActive = item.key === activePage;
                    return (
                      <Link
                        key={item.key}
                        href={item.href}
                        onClick={() => setMobileMenuOpen(false)}
                        className={`flex items-center justify-between rounded-2xl border px-4 py-4 transition ${
                          isActive
                            ? "border-white/20 bg-white text-stone-950 shadow-[0_20px_44px_rgba(255,255,255,0.08)]"
                            : "border-white/12 bg-white/[0.04] text-white hover:bg-white/[0.08]"
                        }`}
                      >
                        <div>
                          <p className="text-[10px] font-black uppercase tracking-[0.2em] opacity-60">Capitulo {index + 1}</p>
                          <p className="mt-1 text-base font-black uppercase tracking-[0.12em]">{item.label}</p>
                        </div>
                        <span className={`text-sm font-black ${isActive ? "text-stone-950/70" : "text-white/50"}`}>
                          0{index + 1}
                        </span>
                      </Link>
                    );
                  })}
                </nav>

                <div className="mt-auto grid gap-2 pb-6 sm:grid-cols-2">
                  {showBackLink ? (
                    <Link
                      href="/modelos-sites"
                      onClick={() => setMobileMenuOpen(false)}
                      className="inline-flex h-12 items-center justify-center rounded-2xl border border-white/12 bg-white/[0.04] px-4 text-[11px] font-black uppercase tracking-[0.18em] text-white/80"
                    >
                      Voltar aos modelos
                    </Link>
                  ) : null}
                  <a
                    href={whatsappHref}
                    className="inline-flex h-12 items-center justify-center rounded-2xl bg-[var(--template-primary)] px-4 text-[11px] font-black uppercase tracking-[0.18em] text-white shadow-[0_18px_40px_rgba(15,118,110,0.28)]"
                  >
                    Agendar avaliacao
                  </a>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </header>
  );
}

type TemplateHeroProps = {
  template: SiteTemplate;
  visual: SiteTemplateVisual;
  elite: SiteTemplateEliteDetails;
  classes: ReturnType<typeof layoutClasses>;
  resolvedClinic: string;
  whatsappHref: string;
  showBackLink: boolean;
  navParams: PremiumQueryParams;
  activePage: PremiumSitePage;
};

function TemplateTopbar({
  template,
  resolvedClinic,
  showBackLink,
  dark = false,
}: {
  template: SiteTemplate;
  resolvedClinic: string;
  showBackLink: boolean;
  dark?: boolean;
}) {
  return (
    <header className="template-reveal flex items-center justify-between gap-4" style={revealStyle(0)}>
      <div className="min-w-0">
        <p className={`text-xs font-black uppercase tracking-[0.18em] ${dark ? "text-white/70" : "text-[var(--template-primary)]"}`}>
          {template.niche}
        </p>
        <p className={`mt-1 truncate text-lg font-black ${dark ? "text-white" : ""}`}>{resolvedClinic}</p>
      </div>
      {showBackLink ? (
        <Link
          href="/modelos-sites"
          className={`inline-flex h-10 items-center justify-center rounded-lg border px-4 text-sm font-bold shadow-sm transition hover:-translate-y-0.5 hover:shadow-md ${
            dark
              ? "border-white/20 bg-white/12 text-white backdrop-blur hover:bg-white/20"
              : "border-stone-300 bg-white/82 text-stone-900 hover:bg-white"
          }`}
        >
          Modelos
        </Link>
      ) : null}
    </header>
  );
}

function HeroKicker({ visual, dark = false }: { visual: SiteTemplateVisual; dark?: boolean }) {
  return (
    <div
      className={`template-reveal inline-flex max-w-full items-center gap-2 rounded-lg border px-3 py-2 text-xs font-black uppercase tracking-[0.14em] shadow-sm backdrop-blur ${
        dark
          ? "border-white/20 bg-white/12 text-white"
          : "border-white/70 bg-white/82 text-[var(--template-primary)]"
      }`}
      style={revealStyle(1)}
    >
      <Sparkles className={`h-4 w-4 shrink-0 ${dark ? "text-white/80" : "text-[var(--template-accent)]"}`} />
      <span className="min-w-0 whitespace-normal leading-5 sm:truncate">{visual.archetype}</span>
    </div>
  );
}

function HeroActions({
  visual,
  whatsappHref,
  dark = false,
  secondaryHref,
}: {
  visual: SiteTemplateVisual;
  whatsappHref: string;
  dark?: boolean;
  secondaryHref?: string;
}) {
  return (
    <div className="template-reveal mt-8 flex flex-col gap-3 sm:flex-row" style={revealStyle(4)}>
      <a
        href={whatsappHref}
        className={`inline-flex h-12 items-center justify-center gap-2 rounded-lg px-5 text-sm font-black shadow-[0_18px_40px_rgba(15,118,110,0.28)] transition hover:-translate-y-0.5 hover:opacity-95 ${
          dark ? "bg-white text-stone-950" : "bg-[var(--template-primary)] text-white"
        }`}
      >
        <MessageCircle className="h-5 w-5" />
        {visual.ctaLabel}
      </a>
      <a
        href={secondaryHref || "#servicos"}
        className={`inline-flex h-12 items-center justify-center gap-2 rounded-lg border px-5 text-sm font-black shadow-sm transition hover:-translate-y-0.5 hover:shadow-md ${
          dark
            ? "border-white/20 bg-white/10 text-white backdrop-blur hover:bg-white/16"
            : "border-stone-300 bg-white text-stone-950 hover:bg-stone-50"
        }`}
      >
        {visual.secondaryCtaLabel}
        <ArrowRight className="h-4 w-4" />
      </a>
    </div>
  );
}

function HeroMetrics({ template, dark = false }: { template: SiteTemplate; dark?: boolean }) {
  return (
    <div className="mt-8 grid max-w-2xl gap-3 sm:grid-cols-3">
      {template.metrics.map((metric, index) => (
        <div
          key={metric.label}
          className={`template-reveal rounded-lg border p-4 shadow-sm backdrop-blur transition hover:-translate-y-1 hover:shadow-lg ${
            dark ? "border-white/18 bg-white/12 text-white" : "border-white/70 bg-white/86"
          }`}
          style={revealStyle(index + 5)}
        >
          <p className={`text-xs font-bold uppercase tracking-[0.14em] ${dark ? "text-white/62" : "text-[var(--template-muted)]"}`}>
            {metric.label}
          </p>
          <p className="mt-2 text-xl font-black">{metric.value}</p>
        </div>
      ))}
    </div>
  );
}

function HeroProofPanel({ template, visual, elite, classes }: TemplateHeroProps) {
  return (
    <aside className={`template-reveal overflow-hidden rounded-lg border p-0 backdrop-blur ${classes.panel}`} style={revealStyle(5)}>
      <div
        className="relative min-h-[280px] bg-cover"
        style={{
          backgroundImage: `linear-gradient(180deg, rgba(0,0,0,0.02), rgba(0,0,0,0.38)), url(${visual.heroImage})`,
          backgroundPosition: visual.heroImagePosition,
        }}
      >
        <div className="absolute bottom-4 left-4 right-4 rounded-lg border border-white/25 bg-white/88 p-4 backdrop-blur">
          <p className="text-xs font-black uppercase tracking-[0.16em] text-[var(--template-primary)]">
            {elite.visualFocus}
          </p>
          <p className="mt-2 text-sm font-black text-stone-950">{visual.proofTitle}</p>
        </div>
      </div>
      <div className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-black text-stone-950">{visual.proofTitle}</p>
            <p className="mt-2 text-sm leading-6 text-stone-600">{visual.proofBody}</p>
          </div>
          <div className="template-float rounded-lg bg-[var(--template-accent)] px-3 py-2 text-xs font-black text-white">
            elite v2
          </div>
        </div>
        <div className="mt-5 grid gap-3">
          {template.badges.map((badge) => (
            <div key={badge} className="flex items-center gap-3 rounded-lg border border-stone-200 bg-white/80 p-3">
              <CheckCircle2 className="h-4 w-4 text-[var(--template-primary)]" />
              <span className="text-sm font-bold text-stone-800">{badge}</span>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}

function BoutiqueHero({ template, visual, elite, resolvedClinic, whatsappHref, showBackLink, navParams }: TemplateHeroProps) {
  const treatmentsHref = buildPremiumPagePath(template, "tratamentos", navParams);
  return (
    <section className="relative overflow-hidden bg-stone-950 text-white">
      <div
        className="template-hero-image absolute inset-0 bg-cover"
        style={{ backgroundImage: `url(${visual.heroImage})`, backgroundPosition: visual.heroImagePosition }}
      />
      <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(10,10,9,0.86)_0%,rgba(10,10,9,0.62)_42%,rgba(10,10,9,0.16)_100%)]" />
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(10,10,9,0.34)_0%,rgba(10,10,9,0.06)_44%,rgba(10,10,9,0.82)_100%)]" />
      <div className="relative mx-auto flex min-h-[86vh] w-full max-w-7xl flex-col px-4 py-5 sm:px-6 lg:px-8">
        <PremiumSiteHeader
          template={template}
          resolvedClinic={resolvedClinic}
          showBackLink={showBackLink}
          whatsappHref={whatsappHref}
          activePage="home"
          navParams={navParams}
        />
        <div className="flex flex-1 items-end pb-8 pt-16">
          <div className="w-full max-w-5xl">
            <HeroKicker visual={visual} dark />
            <h1 className="template-reveal mt-7 max-w-4xl font-heading text-5xl font-black leading-[0.96] sm:text-6xl lg:text-7xl" style={revealStyle(2)}>
              {resolvedClinic}
            </h1>
            <p className="template-reveal mt-5 max-w-3xl text-lg font-black leading-7 text-white sm:text-xl" style={revealStyle(3)}>
              {template.headline}
            </p>
            <p className="template-reveal mt-4 max-w-2xl text-sm leading-7 text-white/76 sm:text-base" style={revealStyle(4)}>
              {template.subheadline}
            </p>
            <HeroActions visual={visual} whatsappHref={whatsappHref} dark secondaryHref={treatmentsHref} />
          </div>
        </div>
        <div className="template-reveal border-t border-white/18 pb-20 pt-4 md:pb-4" style={revealStyle(6)}>
          <div className="grid gap-3 md:grid-cols-[1.1fr_0.9fr_0.9fr]">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.18em] text-white/54">{elite.authority.eyebrow}</p>
              <p className="mt-2 max-w-xl text-sm font-black leading-6 text-white">{elite.authority.title}</p>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {template.metrics.map((metric) => (
                <div key={metric.label} className="border-l border-white/16 pl-3">
                  <p className="text-[11px] font-black uppercase tracking-[0.12em] text-white/48">{metric.label}</p>
                  <p className="mt-1 text-sm font-black text-white">{metric.value}</p>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-2 md:justify-end">
              {template.services.slice(0, 3).map((service) => (
                <span key={service} className="rounded-lg border border-white/18 bg-white/10 px-3 py-2 text-xs font-black text-white/88 backdrop-blur">
                  {service}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function SignatureHero(props: TemplateHeroProps) {
  const { template, visual, elite, classes, resolvedClinic, whatsappHref, showBackLink } = props;
  return (
    <section className="relative min-h-[94vh] overflow-hidden">
      <div
        className="template-hero-image absolute inset-0 bg-cover"
        style={{ backgroundImage: `url(${visual.heroImage})`, backgroundPosition: visual.heroImagePosition }}
      />
      <div className="absolute inset-0" style={{ background: visual.heroOverlay }} />
      <div className="absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-[var(--template-background)] to-transparent" />
      <div className="relative mx-auto flex min-h-[94vh] w-full max-w-7xl flex-col px-4 py-5 sm:px-6 lg:px-8">
        <TemplateTopbar template={template} resolvedClinic={resolvedClinic} showBackLink={showBackLink} />
        <div className={`grid flex-1 items-center gap-8 py-10 ${classes.hero}`}>
          <div>
            <HeroKicker visual={visual} />
            <h1 className="template-reveal mt-6 max-w-4xl font-heading text-4xl font-black leading-[1.02] sm:text-5xl lg:text-6xl" style={revealStyle(2)}>
              {template.headline}
            </h1>
            <p className="template-reveal mt-5 max-w-2xl text-base leading-7 text-[var(--template-muted)] sm:text-lg" style={revealStyle(3)}>
              {template.subheadline}
            </p>
            <HeroActions visual={visual} whatsappHref={whatsappHref} />
            <HeroMetrics template={template} />
          </div>
          <HeroProofPanel {...props} />
        </div>
      </div>
    </section>
  );
}

function AccessHero({ template, visual, elite, resolvedClinic, whatsappHref, showBackLink }: TemplateHeroProps) {
  return (
    <section className="relative min-h-[88vh] overflow-hidden bg-[#eef4ff]">
      <div className="absolute inset-y-0 right-0 hidden w-[48%] bg-cover bg-center lg:block" style={{ backgroundImage: `url(${visual.heroImage})` }} />
      <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(238,244,255,0.96)_0%,rgba(238,244,255,0.88)_52%,rgba(238,244,255,0.34)_100%)]" />
      <div className="absolute inset-y-0 left-0 hidden w-[52%] bg-[radial-gradient(circle_at_top_left,rgba(37,99,235,0.10),transparent_58%)] lg:block" />
      <div className="relative mx-auto flex min-h-[88vh] w-full max-w-7xl flex-col px-4 py-5 sm:px-6 lg:px-8">
        <TemplateTopbar template={template} resolvedClinic={resolvedClinic} showBackLink={showBackLink} />
        <div className="grid flex-1 items-center gap-8 py-10 lg:grid-cols-[minmax(0,0.88fr)_minmax(360px,0.78fr)]">
          <div>
            <HeroKicker visual={visual} />
            <h1 className="template-reveal mt-6 max-w-3xl font-heading text-4xl font-black leading-[1.02] text-slate-950 sm:text-5xl" style={revealStyle(2)}>
              {template.headline}
            </h1>
            <p className="template-reveal mt-5 max-w-2xl text-base leading-7 text-slate-600 sm:text-lg" style={revealStyle(3)}>
              {template.subheadline}
            </p>
            <HeroActions visual={visual} whatsappHref={whatsappHref} />
          </div>
          <div className="template-reveal rounded-[24px] border border-white/24 bg-white/68 p-5 shadow-[0_24px_70px_rgba(15,23,42,0.12)] backdrop-blur-xl" style={revealStyle(5)}>
            <p className="text-xs font-black uppercase tracking-[0.18em] text-[var(--template-primary)]">{elite.authority.eyebrow}</p>
            <h2 className="mt-3 text-2xl font-black text-slate-950">{visual.proofTitle}</h2>
            <div className="mt-5 grid gap-3">
              {template.services.slice(0, 4).map((service, index) => (
                <div key={service} className="flex items-center justify-between rounded-xl border border-white/24 bg-white/56 p-3 backdrop-blur">
                  <span className="text-sm font-black text-slate-900">{service}</span>
                  <span className="rounded-full bg-white/76 px-2.5 py-1 text-xs font-black text-[var(--template-primary)]">0{index + 1}</span>
                </div>
              ))}
            </div>
            <div className="mt-5 grid grid-cols-2 gap-3">
              <div className="rounded-lg bg-[var(--template-primary)] p-4 text-white">
                <Clock3 className="h-5 w-5" />
                <p className="mt-3 text-sm font-black">Horario claro</p>
              </div>
              <div className="rounded-lg bg-slate-900 p-4 text-white">
                <MapPin className="h-5 w-5" />
                <p className="mt-3 text-sm font-black">Bairro visivel</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function EditorialHero({ template, visual, elite, resolvedClinic, whatsappHref, showBackLink }: TemplateHeroProps) {
  return (
    <section className="relative min-h-[96vh] overflow-hidden bg-stone-950 text-white">
      <div
        className="template-hero-image absolute inset-0 bg-cover"
        style={{ backgroundImage: `url(${visual.heroImage})`, backgroundPosition: visual.heroImagePosition }}
      />
      <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(15,23,42,0.78)_0%,rgba(15,23,42,0.48)_50%,rgba(15,23,42,0.22)_100%)]" />
      <div className="relative mx-auto flex min-h-[96vh] w-full max-w-7xl flex-col px-4 py-5 sm:px-6 lg:px-8">
        <TemplateTopbar template={template} resolvedClinic={resolvedClinic} showBackLink={showBackLink} dark />
        <div className="flex flex-1 items-end pb-12 pt-16">
          <div className="max-w-4xl">
            <HeroKicker visual={visual} dark />
            <h1 className="template-reveal mt-7 max-w-4xl font-heading text-4xl font-black leading-[1.02] sm:text-6xl lg:text-7xl" style={revealStyle(2)}>
              {template.headline}
            </h1>
            <p className="template-reveal mt-5 max-w-2xl text-base leading-7 text-white/78 sm:text-lg" style={revealStyle(3)}>
              {template.subheadline}
            </p>
            <HeroActions visual={visual} whatsappHref={whatsappHref} dark />
            <div className="mt-10 grid gap-3 md:grid-cols-3">
              {elite.showcase.items.map((item, index) => (
                <div key={item.title} className="template-reveal rounded-lg border border-white/16 bg-white/10 p-4 backdrop-blur" style={revealStyle(index + 5)}>
                  <p className="text-sm font-black">{item.title}</p>
                  <p className="mt-2 text-xs leading-5 text-white/70">{item.body}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function ClinicalHero({ template, visual, elite, resolvedClinic, whatsappHref, showBackLink }: TemplateHeroProps) {
  return (
    <section className="relative min-h-[90vh] overflow-hidden bg-[linear-gradient(180deg,#eef2ff_0%,#f8fafc_100%)]">
      <div className="absolute inset-y-0 right-0 hidden w-[44%] bg-[radial-gradient(circle_at_top,rgba(124,58,237,0.12),transparent_62%)] lg:block" />
      <div className="mx-auto flex min-h-[90vh] w-full max-w-7xl flex-col px-4 py-5 sm:px-6 lg:px-8">
        <TemplateTopbar template={template} resolvedClinic={resolvedClinic} showBackLink={showBackLink} />
        <div className="grid flex-1 items-center gap-8 py-10 lg:grid-cols-[0.86fr_1.14fr]">
          <div>
            <HeroKicker visual={visual} />
            <h1 className="template-reveal mt-6 max-w-3xl font-heading text-4xl font-black leading-[1.04] text-slate-950 sm:text-5xl" style={revealStyle(2)}>
              {template.headline}
            </h1>
            <p className="template-reveal mt-5 max-w-2xl text-base leading-7 text-slate-600" style={revealStyle(3)}>
              {template.subheadline}
            </p>
            <HeroActions visual={visual} whatsappHref={whatsappHref} />
            <HeroMetrics template={template} />
          </div>
          <div className="template-reveal grid gap-4 rounded-[24px] border border-white/20 bg-white/60 p-4 shadow-[0_24px_70px_rgba(15,23,42,0.10)] backdrop-blur-xl md:grid-cols-2" style={revealStyle(5)}>
            <div
              className="min-h-[360px] rounded-[20px] bg-cover"
              style={{ backgroundImage: `url(${visual.heroImage})`, backgroundPosition: visual.heroImagePosition }}
            />
            <div className="grid gap-3">
              <div className="rounded-[20px] bg-white/76 p-5 backdrop-blur">
                <p className="text-xs font-black uppercase tracking-[0.16em] text-[var(--template-primary)]">{elite.authority.eyebrow}</p>
                <h2 className="mt-3 text-xl font-black text-slate-950">{elite.authority.title}</h2>
              </div>
              {elite.authority.items.map((item) => (
                <div key={item} className="rounded-[20px] border border-white/24 bg-white/68 p-4 backdrop-blur">
                  <p className="text-sm font-black text-slate-900">{item}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function CalmHero({ template, visual, elite, resolvedClinic, whatsappHref, showBackLink }: TemplateHeroProps) {
  return (
    <section className="relative min-h-[92vh] overflow-hidden bg-[var(--template-background)]">
      <div className="absolute inset-x-6 top-24 h-[36vh] rounded-lg bg-cover bg-center opacity-70 blur-[1px]" style={{ backgroundImage: `url(${visual.heroImage})` }} />
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(250,250,249,0.74)_0%,rgba(250,250,249,0.96)_52%,rgba(250,250,249,1)_100%)]" />
      <div className="relative mx-auto flex min-h-[92vh] w-full max-w-6xl flex-col px-4 py-5 text-center sm:px-6 lg:px-8">
        <TemplateTopbar template={template} resolvedClinic={resolvedClinic} showBackLink={showBackLink} />
        <div className="mx-auto flex flex-1 max-w-4xl flex-col items-center justify-center py-14">
          <HeroKicker visual={visual} />
          <h1 className="template-reveal mt-7 font-heading text-4xl font-black leading-[1.06] sm:text-5xl lg:text-6xl" style={revealStyle(2)}>
            {template.headline}
          </h1>
          <p className="template-reveal mt-5 max-w-2xl text-base leading-7 text-[var(--template-muted)] sm:text-lg" style={revealStyle(3)}>
            {template.subheadline}
          </p>
          <HeroActions visual={visual} whatsappHref={whatsappHref} />
          <div className="template-reveal mt-10 max-w-2xl rounded-lg border border-stone-200 bg-white/86 p-5 text-left shadow-sm backdrop-blur" style={revealStyle(5)}>
            <p className="text-xs font-black uppercase tracking-[0.18em] text-[var(--template-primary)]">{elite.authority.eyebrow}</p>
            <p className="mt-3 text-lg font-black">{elite.authority.title}</p>
            <p className="mt-2 text-sm leading-6 text-[var(--template-muted)]">{elite.authority.body}</p>
          </div>
        </div>
      </div>
    </section>
  );
}

function PerformanceHero({ template, visual, elite, resolvedClinic, whatsappHref, showBackLink }: TemplateHeroProps) {
  return (
    <section className="relative min-h-[92vh] overflow-hidden bg-stone-950 text-white">
      <div
        className="absolute inset-0 bg-cover opacity-38"
        style={{ backgroundImage: `url(${visual.heroImage})`, backgroundPosition: visual.heroImagePosition }}
      />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_70%_18%,rgba(245,158,11,0.28),transparent_34%),linear-gradient(90deg,rgba(12,12,12,0.96),rgba(12,12,12,0.74))]" />
      <div className="relative mx-auto flex min-h-[92vh] w-full max-w-7xl flex-col px-4 py-5 sm:px-6 lg:px-8">
        <TemplateTopbar template={template} resolvedClinic={resolvedClinic} showBackLink={showBackLink} dark />
        <div className="grid flex-1 items-center gap-8 py-10 lg:grid-cols-[0.96fr_0.84fr]">
          <div>
            <HeroKicker visual={visual} dark />
            <h1 className="template-reveal mt-6 max-w-4xl font-heading text-4xl font-black leading-[0.98] sm:text-6xl" style={revealStyle(2)}>
              {template.headline}
            </h1>
            <p className="template-reveal mt-5 max-w-2xl text-base leading-7 text-white/72 sm:text-lg" style={revealStyle(3)}>
              {template.subheadline}
            </p>
            <HeroActions visual={visual} whatsappHref={whatsappHref} dark />
          </div>
          <div className="template-reveal rounded-lg border border-white/14 bg-white/10 p-5 backdrop-blur" style={revealStyle(5)}>
            <p className="text-xs font-black uppercase tracking-[0.18em] text-amber-300">{elite.authority.eyebrow}</p>
            <h2 className="mt-3 text-2xl font-black">{elite.authority.title}</h2>
            <div className="mt-5 grid gap-3">
              {template.conversionHooks.map((hook, index) => (
                <div key={hook} className="flex items-center justify-between rounded-lg border border-white/12 bg-white/10 p-4">
                  <span className="text-sm font-black">{hook}</span>
                  <span className="text-xs font-black text-amber-300">CTA {index + 1}</span>
                </div>
              ))}
            </div>
            <div className="mt-5 rounded-lg bg-white p-4 text-stone-950">
              <p className="text-sm font-black">{elite.finalCta.title}</p>
              <p className="mt-2 text-xs leading-5 text-stone-600">{elite.finalCta.body}</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function ActiveHero({ template, visual, elite, resolvedClinic, whatsappHref, showBackLink }: TemplateHeroProps) {
  return (
    <section className="relative min-h-[92vh] overflow-hidden bg-white">
      <div className="absolute inset-y-0 left-0 hidden w-[43%] bg-emerald-50 lg:block" />
      <div className="relative mx-auto flex min-h-[92vh] w-full max-w-7xl flex-col px-4 py-5 sm:px-6 lg:px-8">
        <TemplateTopbar template={template} resolvedClinic={resolvedClinic} showBackLink={showBackLink} />
        <div className="grid flex-1 items-center gap-8 py-10 lg:grid-cols-[minmax(380px,0.86fr)_minmax(0,0.96fr)]">
          <div className="template-reveal order-2 overflow-hidden rounded-lg border border-emerald-100 bg-white p-3 shadow-[0_24px_70px_rgba(20,83,45,0.14)] lg:order-1" style={revealStyle(4)}>
            <div
              className="min-h-[460px] rounded-lg bg-cover"
              style={{ backgroundImage: `url(${visual.heroImage})`, backgroundPosition: visual.heroImagePosition }}
            />
            <div className="grid gap-3 p-3 sm:grid-cols-3">
              {template.metrics.map((metric) => (
                <div key={metric.label} className="rounded-lg bg-emerald-50 p-3">
                  <p className="text-[11px] font-black uppercase tracking-[0.12em] text-emerald-800">{metric.label}</p>
                  <p className="mt-1 text-sm font-black text-emerald-950">{metric.value}</p>
                </div>
              ))}
            </div>
          </div>
          <div className="order-1 lg:order-2">
            <HeroKicker visual={visual} />
            <h1 className="template-reveal mt-6 max-w-4xl font-heading text-4xl font-black leading-[1.02] text-slate-950 sm:text-5xl lg:text-6xl" style={revealStyle(2)}>
              {template.headline}
            </h1>
            <p className="template-reveal mt-5 max-w-2xl text-base leading-7 text-slate-600 sm:text-lg" style={revealStyle(3)}>
              {template.subheadline}
            </p>
            <HeroActions visual={visual} whatsappHref={whatsappHref} />
            <div className="mt-8 grid gap-3 sm:grid-cols-3">
              {elite.authority.items.map((item, index) => (
                <div key={item} className="template-reveal rounded-lg border border-emerald-100 bg-emerald-50 p-4" style={revealStyle(index + 5)}>
                  <p className="text-sm font-black text-emerald-950">{item}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function ProfileHero({ template, visual, elite, resolvedClinic, whatsappHref, showBackLink }: TemplateHeroProps) {
  return (
    <section className="relative min-h-[92vh] overflow-hidden bg-indigo-50/70">
      <div className="relative mx-auto flex min-h-[92vh] w-full max-w-7xl flex-col px-4 py-5 sm:px-6 lg:px-8">
        <TemplateTopbar template={template} resolvedClinic={resolvedClinic} showBackLink={showBackLink} />
        <div className="grid flex-1 items-center gap-8 py-10 lg:grid-cols-[minmax(340px,0.72fr)_minmax(0,1fr)]">
          <aside className="template-reveal overflow-hidden rounded-lg border border-indigo-100 bg-white shadow-[0_24px_70px_rgba(49,46,129,0.14)]" style={revealStyle(4)}>
            <div
              className="min-h-[430px] bg-cover"
              style={{ backgroundImage: `linear-gradient(180deg, rgba(0,0,0,0.02), rgba(0,0,0,0.32)), url(${visual.heroImage})`, backgroundPosition: visual.heroImagePosition }}
            />
            <div className="p-5">
              <p className="text-xs font-black uppercase tracking-[0.18em] text-[var(--template-primary)]">{elite.authority.eyebrow}</p>
              <h2 className="mt-3 text-2xl font-black text-slate-950">{elite.authority.title}</h2>
              <div className="mt-5 grid gap-2">
                {elite.authority.items.map((item) => (
                  <div key={item} className="rounded-lg bg-indigo-50 p-3 text-sm font-black text-indigo-950">
                    {item}
                  </div>
                ))}
              </div>
            </div>
          </aside>
          <div>
            <HeroKicker visual={visual} />
            <h1 className="template-reveal mt-6 max-w-4xl font-heading text-4xl font-black leading-[1.02] text-slate-950 sm:text-5xl lg:text-6xl" style={revealStyle(2)}>
              {template.headline}
            </h1>
            <p className="template-reveal mt-5 max-w-2xl text-base leading-7 text-slate-600 sm:text-lg" style={revealStyle(3)}>
              {template.subheadline}
            </p>
            <HeroActions visual={visual} whatsappHref={whatsappHref} />
            <div className="mt-8 grid max-w-2xl gap-3 sm:grid-cols-2">
              {elite.showcase.items.slice(0, 2).map((item, index) => (
                <div key={item.title} className="template-reveal rounded-lg border border-indigo-100 bg-white p-4 shadow-sm" style={revealStyle(index + 5)}>
                  <p className="text-sm font-black text-slate-950">{item.title}</p>
                  <p className="mt-2 text-xs leading-5 text-slate-600">{item.body}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function TemplateHero(props: TemplateHeroProps) {
  if (props.visual.layout === "boutique") return <BoutiqueHero {...props} />;
  if (props.visual.layout === "access") return <AccessHero {...props} />;
  if (props.visual.layout === "editorial") return <EditorialHero {...props} />;
  if (props.visual.layout === "clinical") return <ClinicalHero {...props} />;
  if (props.visual.layout === "calm") return <CalmHero {...props} />;
  if (props.visual.layout === "performance") return <PerformanceHero {...props} />;
  if (props.visual.layout === "active") return <ActiveHero {...props} />;
  if (props.visual.layout === "profile") return <ProfileHero {...props} />;
  return <SignatureHero {...props} />;
}

type PremiumStoryChapter = {
  eyebrow: string;
  title: string;
  body: string;
  items: string[];
  label: string;
  imagePosition: string;
  tone: "smoke" | "ivory";
};

function buildPremiumStoryChapters(
  template: SiteTemplate,
  visual: SiteTemplateVisual,
  elite: SiteTemplateEliteDetails,
): PremiumStoryChapter[] {
  return [
    {
      eyebrow: "Exclusive Experience",
      title: "Busca premium com uma primeira impressao que ja vende cuidado e criterio.",
      body:
        "O visitante nao encontra blocos genericos; ele entra em uma narrativa visual de alto valor, onde tecnologia, estetica e atendimento consultivo aparecem antes da conversa comercial.",
      items: visual.patientJourney,
      label: "Core values",
      imagePosition: "center top",
      tone: "smoke",
    },
    {
      eyebrow: "Clinical Mastery",
      title: "Tratamentos deixam de ser uma lista e passam a parecer uma experiencia conduzida.",
      body:
        "Cada servico ganha contexto, indicacao e valor percebido, criando a sensacao de que a clinica tem metodo proprio, nao apenas uma vitrine de procedimentos.",
      items: template.services,
      label: "Innovative services",
      imagePosition: "center",
      tone: "ivory",
    },
    {
      eyebrow: "Concierge Care",
      title: "Autoridade, equipe e estrutura aparecem como camadas que se somam.",
      body:
        "A leitura cria profundidade: primeiro o desejo, depois a confianca, depois a prova. Isso sustenta um ticket maior sem depender de oferta agressiva.",
      items: elite.authority.items,
      label: "Clinical authority",
      imagePosition: "center right",
      tone: "smoke",
    },
    {
      eyebrow: "Artistic Technology",
      title: "O fundo sustenta a atmosfera enquanto os cards avancam como capitulos de marca.",
      body:
        "Essa rolagem funciona como um palco fixo. O pano de fundo quase nao se mexe, e os paineis entram por cima uns dos outros, dando um ar editorial e memoravel para a clinica.",
      items: [...visual.experiencePoints, elite.localTrust.title],
      label: "Premium local trust",
      imagePosition: "center left",
      tone: "ivory",
    },
  ];
}

function PremiumLayeredStory({
  template,
  visual,
  elite,
}: {
  template: SiteTemplate;
  visual: SiteTemplateVisual;
  elite: SiteTemplateEliteDetails;
}) {
  const chapters = buildPremiumStoryChapters(template, visual, elite);
  const tagStyle = {
    clipPath: "polygon(18px 0,100% 0,calc(100% - 18px) 100%,0 100%)",
  } as CSSProperties;

  return (
    <section className="relative overflow-hidden bg-stone-950">
      <div className="pointer-events-none absolute inset-0">
        <div className="sticky top-0 h-screen overflow-hidden">
          <div
            className="template-hero-image absolute inset-0 bg-cover opacity-18"
            style={{ backgroundImage: `url(${visual.heroImage})`, backgroundPosition: visual.heroImagePosition }}
          />
          <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(10,10,9,0.82)_0%,rgba(10,10,9,0.92)_100%)]" />
          <div className="absolute left-1/2 top-10 h-[88vh] w-[42vw] -translate-x-1/2 rounded-[999px] bg-[rgba(18,95,102,0.34)] blur-3xl" />
        </div>
      </div>

      <div className="relative z-10 mx-auto w-full max-w-7xl px-4 pb-32 pt-20 sm:px-6 lg:px-8">
        <div className="template-reveal mx-auto max-w-3xl text-center" style={revealStyle(0)}>
          <p className="text-xs font-black uppercase tracking-[0.22em] text-white/54">Rolagem premium</p>
          <h2 className="mt-4 font-heading text-3xl font-black leading-tight text-white sm:text-5xl">
            A historia da clinica avanca em capitulos, com fundo estavel e cards sobrepostos.
          </h2>
          <p className="mt-5 text-base leading-7 text-white/66">
            Esse e o comportamento que gera aquela sensacao de site caro e memoravel: menos blocos comuns, mais cenas.
          </p>
        </div>

        <div className="mt-12 lg:mt-16">
          {chapters.map((chapter, index) => {
            const isIvory = chapter.tone === "ivory";
            const textFirst = index % 2 === 0;

            return (
              <div
                key={chapter.title}
                className={`relative min-h-[auto] ${index === 0 ? "" : "mt-8 lg:-mt-[10vh]"} lg:min-h-[128vh]`}
                style={{ zIndex: index + 1 }}
              >
                <div className="lg:sticky lg:top-24">
                  <article
                    className={`overflow-hidden rounded-[30px] border shadow-[0_28px_90px_rgba(0,0,0,0.26)] ${
                      isIvory ? "border-stone-300 bg-[#f1eadc] text-stone-950" : "border-white/14 bg-[#2d2d2f]/88 text-white backdrop-blur"
                    }`}
                  >
                    <div className={`grid min-h-[76vh] lg:min-h-[88vh] ${textFirst ? "lg:grid-cols-[0.98fr_1.02fr]" : "lg:grid-cols-[1.02fr_0.98fr]"}`}>
                      <div className={`flex flex-col justify-between p-7 pb-10 sm:p-10 sm:pb-12 lg:p-14 lg:pb-20 ${textFirst ? "order-1" : "order-2"}`}>
                        <div>
                          <p className={`text-xs font-black uppercase tracking-[0.22em] ${isIvory ? "text-[var(--template-primary)]" : "text-white/54"}`}>
                            {chapter.eyebrow}
                          </p>
                          <h3 className="mt-5 max-w-xl font-heading text-4xl font-black leading-[0.98] sm:text-5xl">
                            {chapter.title}
                          </h3>
                          <p className={`mt-6 max-w-2xl text-base leading-8 ${isIvory ? "text-stone-600" : "text-white/74"}`}>{chapter.body}</p>
                        </div>

                        <div className="mt-8 grid gap-3 sm:grid-cols-2">
                          {chapter.items.map((item) => (
                            <div
                              key={item}
                              className={`rounded-2xl border p-4 ${
                                isIvory ? "border-stone-300 bg-[#fbf5e8] text-stone-900" : "border-white/10 bg-white/[0.06] text-white/85"
                              }`}
                            >
                              <p className="text-sm font-black leading-6">{item}</p>
                            </div>
                          ))}
                        </div>
                      </div>

                      <div className={`relative min-h-[300px] border-t lg:min-h-full ${textFirst ? "order-2 lg:border-l lg:border-t-0" : "order-1 lg:border-r lg:border-t-0"} ${isIvory ? "border-stone-300" : "border-white/12"}`}>
                        <div
                          className="absolute inset-0 bg-cover"
                          style={{
                            backgroundImage: `linear-gradient(180deg, rgba(0,0,0,0.06), rgba(0,0,0,0.36)), url(${visual.heroImage})`,
                            backgroundPosition: chapter.imagePosition,
                          }}
                        />
                        <div className={`absolute inset-0 ${isIvory ? "bg-[linear-gradient(180deg,rgba(241,234,220,0.08),rgba(241,234,220,0.18))]" : "bg-[linear-gradient(180deg,rgba(32,32,34,0.04),rgba(32,32,34,0.26))]"}`} />
                        <div className="absolute inset-x-6 top-6 rounded-2xl border border-white/10 bg-black/[0.16] px-6 py-5 backdrop-blur-md">
                          <p className="text-4xl font-black leading-none text-white/26 sm:text-5xl">{chapter.eyebrow}</p>
                        </div>
                        <div className="absolute bottom-0 left-0 right-0 p-4 sm:p-6">
                          <div
                            style={tagStyle}
                            className="ml-auto inline-flex h-12 items-center justify-center bg-[var(--template-secondary)] px-7 text-xs font-black uppercase tracking-[0.18em] text-white shadow-[0_16px_40px_rgba(17,94,89,0.28)]"
                          >
                            {chapter.label}
                          </div>
                        </div>
                      </div>
                    </div>
                  </article>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
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
  const visual = getSiteTemplateVisual(template);
  const elite = getSiteTemplateEliteDetails(template);
  const classes = layoutClasses(visual.layout);
  const sectionVariant = sectionVariantClasses(visual.layout);
  const contentSurface = contentSurfaceClasses(visual.layout);
  const isBoutique = visual.layout === "boutique";
  const navParams = { clinic: clinicName, city, whatsapp };
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
  const primaryActionHref = digitsOnly(whatsapp) ? whatsappHref : "#selecionar-template";
  const [introPhase, setIntroPhase] = useState<"hidden" | "visible" | "closing">(isBoutique ? "visible" : "hidden");

  useEffect(() => {
    if (!isBoutique) {
      setIntroPhase("hidden");
      return;
    }

    try {
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        setIntroPhase("hidden");
        return;
      }
      const introKey = `premium-intro:${template.slug}`;
      if (window.sessionStorage.getItem(introKey) === "seen") {
        setIntroPhase("hidden");
        return;
      }
      setIntroPhase("visible");
      const closeTimer = window.setTimeout(() => setIntroPhase("closing"), 1600);
      const hideTimer = window.setTimeout(() => {
        window.sessionStorage.setItem(introKey, "seen");
        setIntroPhase("hidden");
      }, 2400);
      return () => {
        window.clearTimeout(closeTimer);
        window.clearTimeout(hideTimer);
      };
    } catch {
      setIntroPhase("hidden");
    }
  }, [isBoutique, template.slug]);

  return (
    <main
      style={themeStyle}
      className={`min-h-screen overflow-x-hidden pb-20 md:pb-0 ${
        isBoutique ? "bg-stone-950 text-white" : "bg-[var(--template-background)] text-[var(--template-text)]"
      } ${motionClass(elite.motion)}`}
    >
      <TemplateAnimationStyles />
      {introPhase !== "hidden" ? <PremiumIntroReveal clinicName={resolvedClinic} closing={introPhase === "closing"} /> : null}

      <TemplateHero
        template={template}
        visual={visual}
        elite={elite}
        classes={classes}
        resolvedClinic={resolvedClinic}
        whatsappHref={primaryActionHref}
        showBackLink={showBackLink}
        navParams={navParams}
        activePage="home"
      />

      {isBoutique ? <PremiumLayeredStory template={template} visual={visual} elite={elite} /> : null}

      {!isBoutique ? (
        <>
      <section className={sectionVariant.journeyBand}>
        <div className={sectionVariant.journeyGrid}>
          {visual.patientJourney.map((step, index) => (
            <div
              key={step}
              className={`template-reveal group relative overflow-hidden rounded-lg border transition hover:-translate-y-1 hover:shadow-md ${sectionVariant.journeyCard}`}
              style={revealStyle(index)}
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--template-primary)] text-xs font-black text-white transition group-hover:scale-105">
                {index + 1}
              </span>
              <p className={`mt-4 text-sm font-black leading-5 ${sectionVariant.journeyText}`}>{step}</p>
              {index < visual.patientJourney.length - 1 ? (
                <div className="absolute left-12 top-8 hidden h-px w-full bg-[var(--template-primary)]/20 md:block" />
              ) : null}
            </div>
          ))}
        </div>
      </section>

      <section id="servicos" className="mx-auto w-full max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <div className="grid gap-8 lg:grid-cols-[0.78fr_1.22fr]">
          <SectionHeader eyebrow="Oferta" title="Servicos com posicionamento claro" body={visual.serviceIntro} dark={isBoutique} />
          <div className={sectionVariant.serviceGrid}>
            {template.services.map((service, index) => (
              <article
                key={service}
                className={`template-reveal group rounded-lg border p-5 shadow-sm transition hover:-translate-y-1 hover:border-[var(--template-primary)]/35 hover:shadow-xl ${sectionVariant.serviceCard}`}
                style={revealStyle(index)}
              >
                <IconFrame>
                  {index % 3 === 0 ? (
                    <Stethoscope className="h-5 w-5" />
                  ) : index % 3 === 1 ? (
                    <HeartPulse className="h-5 w-5" />
                  ) : (
                    <Award className="h-5 w-5" />
                  )}
                </IconFrame>
                <p className="mt-5 text-base font-black">{service}</p>
                <p className="mt-2 text-sm leading-6 text-[var(--template-muted)]">
                  Bloco editavel para explicar indicacao, beneficio e proximo passo com linguagem do nicho.
                </p>
                <div className="mt-4 inline-flex items-center gap-2 text-xs font-black uppercase tracking-[0.14em] text-[var(--template-primary)] opacity-80 transition group-hover:opacity-100">
                  Ver encaixe
                  <ArrowRight className="h-3.5 w-3.5" />
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className={`border-y ${contentSurface.section}`}>
        <div className="mx-auto grid w-full max-w-7xl gap-8 px-4 py-16 sm:px-6 lg:grid-cols-[0.95fr_1.05fr] lg:px-8">
          <div className={`template-reveal overflow-hidden rounded-lg border shadow-[0_20px_70px_rgba(28,25,23,0.08)] ${contentSurface.cardStrong}`}>
            <div
              className="min-h-[340px] bg-cover"
              style={{
                backgroundImage: `linear-gradient(180deg, rgba(0,0,0,0.04), rgba(0,0,0,0.34)), url(${visual.heroImage})`,
                backgroundPosition: visual.heroImagePosition,
              }}
            />
            <div className="p-6">
              <p className="text-xs font-black uppercase tracking-[0.18em] text-[var(--template-primary)]">
                {elite.authority.eyebrow}
              </p>
              <h2 className="mt-3 font-heading text-3xl font-black leading-tight">{elite.authority.title}</h2>
              <p className="mt-4 text-sm leading-6 text-[var(--template-muted)]">{elite.authority.body}</p>
            </div>
          </div>

          <div className="grid content-center gap-3">
            {elite.authority.items.map((item, index) => (
              <article
                key={item}
                className={`template-reveal flex gap-4 rounded-lg border p-5 shadow-sm transition hover:-translate-y-1 hover:shadow-lg ${contentSurface.card}`}
                style={revealStyle(index)}
              >
                <IconFrame>
                  {index % 2 === 0 ? <ShieldCheck className="h-5 w-5" /> : <UserRoundCheck className="h-5 w-5" />}
                </IconFrame>
                <div>
                  <h3 className="text-base font-black">{item}</h3>
                  <p className="mt-2 text-sm leading-6 text-[var(--template-muted)]">
                    Parte modular para substituir por credenciais, fotos reais e diferenciais da clinica.
                  </p>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto w-full max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <div>
        <SectionHeader eyebrow="Vitrine" title={elite.showcase.title} body={elite.showcase.body} align="center" dark={isBoutique} />
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {elite.showcase.items.map((item, index) => (
            <article
              key={item.title}
              className={`template-reveal min-h-[220px] rounded-lg border p-6 shadow-sm transition hover:-translate-y-1 hover:shadow-xl ${contentSurface.card}`}
              style={revealStyle(index)}
            >
              <div className="mb-5 flex items-center justify-between gap-3">
                <IconFrame>
                  {index === 0 ? <Building2 className="h-5 w-5" /> : index === 1 ? <UsersRound className="h-5 w-5" /> : <Sparkles className="h-5 w-5" />}
                </IconFrame>
                <span className="text-xs font-black uppercase tracking-[0.14em] text-[var(--template-accent)]">
                  0{index + 1}
                </span>
              </div>
              <h3 className="text-lg font-black">{item.title}</h3>
              <p className="mt-3 text-sm leading-6 text-[var(--template-muted)]">{item.body}</p>
            </article>
          ))}
        </div>
        </div>
      </section>

      <section className="mx-auto grid w-full max-w-7xl gap-8 px-4 pb-16 sm:px-6 lg:grid-cols-[1fr_1fr] lg:px-8">
        <div className={`template-reveal rounded-lg border p-6 shadow-sm ${contentSurface.card}`}>
          <p className="text-xs font-black uppercase tracking-[0.18em] text-[var(--template-primary)]">Experiencia</p>
          <h2 className="mt-3 font-heading text-3xl font-black leading-tight">{visual.experienceTitle}</h2>
          <p className="mt-4 text-sm leading-6 text-[var(--template-muted)]">{visual.experienceBody}</p>
          <div className="mt-6 grid gap-3">
            {visual.experiencePoints.map((point) => (
              <div key={point} className={`flex gap-3 rounded-lg p-4 ${contentSurface.subtle}`}>
                <UserRoundCheck className="mt-0.5 h-4 w-4 shrink-0 text-[var(--template-primary)]" />
                <p className="text-sm font-bold leading-6 text-stone-800">{point}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="grid gap-3">
          {template.sections.map((section, index) => (
            <article
              key={section.title}
              className={`template-reveal rounded-lg border p-5 shadow-sm transition hover:-translate-y-1 hover:shadow-lg ${contentSurface.card}`}
              style={revealStyle(index)}
            >
              <IconFrame>
                <ShieldCheck className="h-5 w-5" />
              </IconFrame>
              <h3 className="mt-4 text-lg font-black">{section.title}</h3>
              <p className="mt-3 text-sm leading-6 text-[var(--template-muted)]">{section.body}</p>
            </article>
          ))}
        </div>
      </section>
        </>
      ) : null}

      <section className={isBoutique ? "border-y border-white/10 bg-stone-950 text-white" : `border-y ${contentSurface.sectionAlt}`}>
        <div className="mx-auto grid w-full max-w-7xl gap-8 px-4 py-16 sm:px-6 lg:grid-cols-[0.9fr_1.1fr] lg:px-8">
          <div className={`template-reveal rounded-lg border p-6 shadow-sm ${
            isBoutique ? "border-white/12 bg-white/10 backdrop-blur" : contentSurface.card
          }`}>
            <Quote className="h-8 w-8 text-[var(--template-accent)]" />
            <p className="mt-5 text-xs font-black uppercase tracking-[0.18em] text-[var(--template-primary)]">
              {elite.socialProof.title}
            </p>
            <blockquote className={`mt-4 text-xl font-black leading-8 ${isBoutique ? "text-white" : "text-stone-950"}`}>
              &quot;{elite.socialProof.quote}&quot;
            </blockquote>
            <p className={`mt-4 text-sm font-bold ${isBoutique ? "text-white/62" : "text-[var(--template-muted)]"}`}>{elite.socialProof.source}</p>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className={`template-reveal rounded-lg border p-6 shadow-sm ${
              isBoutique ? "border-white/12 bg-white/10 backdrop-blur" : contentSurface.card
            }`} style={revealStyle(1)}>
              <p className="text-xs font-black uppercase tracking-[0.18em] text-[var(--template-primary)]">
                {elite.localTrust.eyebrow}
              </p>
              <h2 className="mt-3 font-heading text-3xl font-black leading-tight">{elite.localTrust.title}</h2>
              <p className={`mt-4 text-sm leading-6 ${isBoutique ? "text-white/66" : "text-[var(--template-muted)]"}`}>{elite.localTrust.body}</p>
              <div className="mt-5 grid gap-3">
                {elite.localTrust.items.map((item) => (
                  <div key={item} className={`flex items-center gap-3 rounded-lg p-3 ${isBoutique ? "bg-white/10" : contentSurface.subtle}`}>
                    <MapPin className="h-4 w-4 text-[var(--template-primary)]" />
                    <span className={`text-sm font-bold ${isBoutique ? "text-white/82" : "text-stone-800"}`}>{item}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className={`template-reveal rounded-lg border p-6 shadow-sm ${
              isBoutique ? "border-white/12 bg-white/10 backdrop-blur" : contentSurface.card
            }`} style={revealStyle(2)}>
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
              <div className="mt-6 grid gap-3">
                <div className={`rounded-lg p-4 ${isBoutique ? "bg-white/10" : contentSurface.subtle}`}>
                  <Navigation className="h-5 w-5 text-[var(--template-primary)]" />
                  <p className="mt-3 text-sm font-bold">Mapa, bairro e cidade em destaque para {resolvedCity}.</p>
                </div>
                <div className={`rounded-lg p-4 ${isBoutique ? "bg-white/10" : contentSurface.subtle}`}>
                  <Clock3 className="h-5 w-5 text-[var(--template-primary)]" />
                  <p className="mt-3 text-sm font-bold">Horario e proximo passo sem confusao.</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="selecionar-template" className="bg-[var(--template-primary)] px-4 py-14 text-white sm:px-6 lg:px-8">
        <div className="mx-auto grid w-full max-w-7xl gap-8 lg:grid-cols-[0.78fr_1.22fr] lg:items-center">
          <div className="template-reveal">
            <p className="text-xs font-black uppercase tracking-[0.18em] text-white/70">FAQ e proximo passo</p>
            <h2 className="mt-3 font-heading text-3xl font-black leading-tight sm:text-4xl">{elite.finalCta.title}</h2>
            <p className="mt-4 text-sm leading-6 text-white/78">{elite.finalCta.body}</p>
            <a
              href={primaryActionHref}
              className="mt-6 inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-white px-4 text-sm font-black text-[var(--template-primary)] shadow-lg transition hover:-translate-y-0.5 hover:bg-white/90"
            >
              <CalendarDays className="h-4 w-4" />
              {visual.ctaLabel}
            </a>
          </div>
          <div className="grid gap-3">
            {template.faqs.map((faq, index) => (
              <article
                key={faq.question}
                className="template-reveal rounded-lg border border-white/20 bg-white/10 p-5 backdrop-blur transition hover:bg-white/14"
                style={revealStyle(index)}
              >
                <h3 className="text-base font-black">{faq.question}</h3>
                <p className="mt-2 text-sm leading-6 text-white/80">{faq.answer}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <FloatingWhatsAppButton href={primaryActionHref} elevatedMobile />
    </main>
  );
}

function premiumPageHeroContent(
  page: SiteTemplateSectionKey,
  template: SiteTemplate,
  visual: SiteTemplateVisual,
  elite: SiteTemplateEliteDetails,
  resolvedCity: string,
) {
  switch (page) {
    case "tratamentos":
      return {
        eyebrow: "Tratamentos",
        title: "Tratamentos explicados com valor, criterio e desejo responsavel.",
        body: visual.serviceIntro,
        panelTitle: elite.showcase.title,
        panelItems: template.services.slice(0, 4),
      };
    case "equipe":
      return {
        eyebrow: "Equipe",
        title: "Autoridade clinica, especialidades e atendimento consultivo.",
        body: elite.authority.body,
        panelTitle: "Criterios de confianca",
        panelItems: elite.authority.items,
      };
    case "estrutura":
      return {
        eyebrow: "Estrutura",
        title: "Ambiente, tecnologia e experiencia pensados para decisao premium.",
        body: visual.experienceBody,
        panelTitle: "Diferenciais da experiencia",
        panelItems: visual.experiencePoints,
      };
    case "contato":
      return {
        eyebrow: "Contato",
        title: `Conversa premium e presenca local em ${resolvedCity}.`,
        body: elite.localTrust.body,
        panelTitle: "Pontos de contato",
        panelItems: [...template.conversionHooks.slice(0, 2), "Mapa e bairro em destaque", "WhatsApp com proximo passo claro"],
      };
  }
}

export function SiteTemplateSectionPage({
  template,
  page,
  clinicName,
  city,
  whatsapp,
  showBackLink = true,
}: {
  template: SiteTemplate;
  page: SiteTemplateSectionKey;
  clinicName?: string | null;
  city?: string | null;
  whatsapp?: string | null;
  showBackLink?: boolean;
}) {
  const resolvedClinic = String(clinicName || "").trim() || template.name;
  const resolvedCity = String(city || "").trim() || "sua cidade";
  const visual = getSiteTemplateVisual(template);
  const elite = getSiteTemplateEliteDetails(template);
  const isBoutique = visual.layout === "boutique";
  const navParams = { clinic: clinicName, city, whatsapp };
  const homeHref = buildSiteTemplatePreviewPath(template, navParams);
  const selectHref = `${homeHref}#selecionar-template`;
  const whatsappHref = buildWhatsAppHref(template, resolvedClinic, whatsapp);
  const primaryActionHref = digitsOnly(whatsapp) ? whatsappHref : selectHref;
  const hero = premiumPageHeroContent(page, template, visual, elite, resolvedCity);
  const themeStyle = {
    "--template-primary": template.palette.primary,
    "--template-secondary": template.palette.secondary,
    "--template-accent": template.palette.accent,
    "--template-background": template.palette.background,
    "--template-surface": template.palette.surface,
    "--template-text": template.palette.text,
    "--template-muted": template.palette.muted,
  } as CSSProperties;

  return (
    <main
      style={themeStyle}
      className={`${isBoutique ? "bg-stone-950 text-white" : "bg-[var(--template-background)] text-[var(--template-text)]"} min-h-screen overflow-x-hidden`}
    >
      <TemplateAnimationStyles />

      <section className="relative overflow-hidden">
        <div
          className="absolute inset-0 bg-cover"
          style={{ backgroundImage: `url(${visual.heroImage})`, backgroundPosition: visual.heroImagePosition }}
        />
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(10,10,9,0.88)_0%,rgba(10,10,9,0.72)_50%,rgba(10,10,9,0.32)_100%)]" />
        <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(10,10,9,0.16)_0%,rgba(10,10,9,0.72)_100%)]" />

        <div className="relative mx-auto flex min-h-[72vh] w-full max-w-7xl flex-col px-4 py-5 sm:px-6 lg:px-8">
          <PremiumSiteHeader
            template={template}
            resolvedClinic={resolvedClinic}
            showBackLink={showBackLink}
            whatsappHref={primaryActionHref}
            activePage={page}
            navParams={navParams}
          />

          <div className="grid flex-1 items-end gap-8 py-12 lg:grid-cols-[0.88fr_0.72fr]">
            <div className="max-w-4xl">
              <p className="template-reveal text-xs font-black uppercase tracking-[0.22em] text-white/60" style={revealStyle(1)}>
                {hero.eyebrow}
              </p>
              <h1 className="template-reveal mt-5 font-heading text-4xl font-black leading-[0.96] sm:text-6xl" style={revealStyle(2)}>
                {hero.title}
              </h1>
              <p className="template-reveal mt-5 max-w-2xl text-base leading-7 text-white/74 sm:text-lg" style={revealStyle(3)}>
                {hero.body}
              </p>
              <div className="template-reveal mt-8 flex flex-col gap-3 sm:flex-row" style={revealStyle(4)}>
                <a
                  href={primaryActionHref}
                  className="inline-flex h-12 items-center justify-center rounded-lg bg-[var(--template-primary)] px-5 text-sm font-black text-white shadow-[0_18px_40px_rgba(15,118,110,0.28)]"
                >
                  Agendar avaliacao
                </a>
                <Link
                  href={selectHref}
                  className="inline-flex h-12 items-center justify-center rounded-lg border border-white/20 bg-white/10 px-5 text-sm font-black text-white backdrop-blur"
                >
                  Selecionar este modelo
                </Link>
              </div>
            </div>

            <aside className="template-reveal rounded-2xl border border-white/12 bg-white/10 p-5 backdrop-blur-xl" style={revealStyle(5)}>
              <p className="text-xs font-black uppercase tracking-[0.18em] text-white/56">{hero.panelTitle}</p>
              <div className="mt-5 grid gap-3">
                {hero.panelItems.map((item) => (
                  <div key={item} className="rounded-xl border border-white/10 bg-white/10 p-4">
                    <p className="text-sm font-black text-white">{item}</p>
                  </div>
                ))}
              </div>
            </aside>
          </div>
        </div>
      </section>

      {page === "tratamentos" ? (
        <>
          <section className="bg-stone-950 px-4 py-16 text-white sm:px-6 lg:px-8">
            <div className="mx-auto grid w-full max-w-7xl gap-4 md:grid-cols-2">
              {template.services.map((service, index) => (
                <article key={service} className="rounded-2xl border border-white/12 bg-white/10 p-6 backdrop-blur">
                  <IconFrame>
                    {index % 3 === 0 ? <Stethoscope className="h-5 w-5" /> : index % 3 === 1 ? <Sparkles className="h-5 w-5" /> : <Award className="h-5 w-5" />}
                  </IconFrame>
                  <h2 className="mt-5 text-2xl font-black">{service}</h2>
                  <p className="mt-3 text-sm leading-6 text-white/66">
                    Bloco pensado para explicar indicacao, valor percebido, tecnologia envolvida e caminho natural para avaliacao.
                  </p>
                </article>
              ))}
            </div>
          </section>
          <section className="border-y border-stone-300 bg-[#f1eadc] px-4 py-16 text-stone-950 sm:px-6 lg:px-8">
            <div className="mx-auto grid w-full max-w-7xl gap-4 md:grid-cols-3">
              {elite.showcase.items.map((item, index) => (
                <article key={item.title} className="rounded-2xl border border-stone-300 bg-[#fbf5e8] p-6 shadow-sm">
                  <p className="text-xs font-black uppercase tracking-[0.18em] text-[var(--template-primary)]">0{index + 1}</p>
                  <h3 className="mt-4 text-xl font-black">{item.title}</h3>
                  <p className="mt-3 text-sm leading-6 text-stone-600">{item.body}</p>
                </article>
              ))}
            </div>
          </section>
        </>
      ) : null}

      {page === "equipe" ? (
        <>
          <section className="border-y border-stone-300 bg-[#f1eadc] px-4 py-16 text-stone-950 sm:px-6 lg:px-8">
            <div className="mx-auto grid w-full max-w-7xl gap-8 lg:grid-cols-[0.9fr_1.1fr]">
              <div className="overflow-hidden rounded-2xl border border-stone-300 bg-[#fbf5e8] shadow-sm">
                <div
                  className="min-h-[320px] bg-cover"
                  style={{
                    backgroundImage: `linear-gradient(180deg, rgba(0,0,0,0.04), rgba(0,0,0,0.22)), url(${visual.heroImage})`,
                    backgroundPosition: visual.heroImagePosition,
                  }}
                />
                <div className="p-6">
                  <p className="text-xs font-black uppercase tracking-[0.18em] text-[var(--template-primary)]">{elite.authority.eyebrow}</p>
                  <h2 className="mt-3 text-3xl font-black leading-tight">{elite.authority.title}</h2>
                  <p className="mt-4 text-sm leading-6 text-stone-600">{elite.authority.body}</p>
                </div>
              </div>
              <div className="grid gap-3">
                {[...elite.authority.items, ...template.trustSignals.slice(0, 3)].map((item, index) => (
                  <article key={item} className="rounded-2xl border border-stone-300 bg-[#fbf5e8] p-5 shadow-sm">
                    <div className="flex items-start gap-4">
                      <IconFrame>{index % 2 === 0 ? <UserRoundCheck className="h-5 w-5" /> : <ShieldCheck className="h-5 w-5" />}</IconFrame>
                      <div>
                        <h3 className="text-lg font-black">{item}</h3>
                        <p className="mt-2 text-sm leading-6 text-stone-600">
                          Espaco para CRO, experiencia, area de atuacao e postura de atendimento da equipe.
                        </p>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </div>
          </section>
          <section className="bg-stone-950 px-4 py-16 text-white sm:px-6 lg:px-8">
            <div className="mx-auto grid w-full max-w-7xl gap-4 md:grid-cols-3">
              {template.idealFor.map((item) => (
                <article key={item} className="rounded-2xl border border-white/12 bg-white/10 p-6 backdrop-blur">
                  <p className="text-xs font-black uppercase tracking-[0.18em] text-white/54">Especialidade em foco</p>
                  <h3 className="mt-4 text-xl font-black">{item}</h3>
                </article>
              ))}
            </div>
          </section>
        </>
      ) : null}

      {page === "estrutura" ? (
        <>
          <section className="bg-stone-950 px-4 py-16 text-white sm:px-6 lg:px-8">
            <div className="mx-auto grid w-full max-w-7xl gap-8 lg:grid-cols-[1.05fr_0.95fr]">
              <div
                className="min-h-[520px] rounded-2xl border border-white/12 bg-cover shadow-[0_28px_80px_rgba(0,0,0,0.22)]"
                style={{
                  backgroundImage: `linear-gradient(180deg, rgba(0,0,0,0.08), rgba(0,0,0,0.38)), url(${visual.heroImage})`,
                  backgroundPosition: visual.heroImagePosition,
                }}
              />
              <div className="grid gap-4">
                {visual.experiencePoints.map((point) => (
                  <article key={point} className="rounded-2xl border border-white/12 bg-white/10 p-5 backdrop-blur">
                    <p className="text-sm font-black text-white">{point}</p>
                  </article>
                ))}
                {template.metrics.map((metric) => (
                  <article key={metric.label} className="rounded-2xl border border-white/12 bg-white/10 p-5 backdrop-blur">
                    <p className="text-xs font-black uppercase tracking-[0.18em] text-white/52">{metric.label}</p>
                    <p className="mt-2 text-2xl font-black text-white">{metric.value}</p>
                  </article>
                ))}
              </div>
            </div>
          </section>
          <section className="border-y border-stone-300 bg-[#f1eadc] px-4 py-16 text-stone-950 sm:px-6 lg:px-8">
            <div className="mx-auto grid w-full max-w-7xl gap-4 md:grid-cols-3">
              {template.badges.map((badge) => (
                <article key={badge} className="rounded-2xl border border-stone-300 bg-[#fbf5e8] p-6 shadow-sm">
                  <p className="text-xs font-black uppercase tracking-[0.18em] text-[var(--template-primary)]">Ambiente premium</p>
                  <h3 className="mt-4 text-xl font-black">{badge}</h3>
                </article>
              ))}
            </div>
          </section>
        </>
      ) : null}

      {page === "contato" ? (
        <>
          <section className="bg-stone-950 px-4 py-16 text-white sm:px-6 lg:px-8">
            <div className="mx-auto grid w-full max-w-7xl gap-4 lg:grid-cols-[0.9fr_1.1fr]">
              <article className="rounded-2xl border border-white/12 bg-white/10 p-6 backdrop-blur">
                <p className="text-xs font-black uppercase tracking-[0.18em] text-white/54">{elite.localTrust.eyebrow}</p>
                <h2 className="mt-4 text-4xl font-black leading-tight">{elite.localTrust.title}</h2>
                <p className="mt-4 text-sm leading-6 text-white/66">{elite.localTrust.body}</p>
                <div className="mt-6 grid gap-3">
                  {elite.localTrust.items.map((item) => (
                    <div key={item} className="rounded-xl border border-white/10 bg-white/10 p-4">
                      <p className="text-sm font-black text-white">{item}</p>
                    </div>
                  ))}
                </div>
              </article>
              <div className="grid gap-3 md:grid-cols-2">
                {template.conversionHooks.map((hook) => (
                  <article key={hook} className="rounded-2xl border border-white/12 bg-white/10 p-5 backdrop-blur">
                    <p className="text-xs font-black uppercase tracking-[0.18em] text-white/52">Proximo passo</p>
                    <h3 className="mt-4 text-lg font-black">{hook}</h3>
                  </article>
                ))}
                <article className="rounded-2xl border border-white/12 bg-[var(--template-primary)] p-5 text-white shadow-[0_24px_60px_rgba(15,118,110,0.22)] md:col-span-2">
                  <p className="text-xs font-black uppercase tracking-[0.18em] text-white/72">Contato principal</p>
                  <a href={primaryActionHref} className="mt-4 inline-flex items-center gap-2 text-2xl font-black">
                    <MessageCircle className="h-6 w-6" />
                    Conversar pelo WhatsApp
                  </a>
                </article>
              </div>
            </div>
          </section>
          <section className="border-y border-stone-300 bg-[#f1eadc] px-4 py-16 text-stone-950 sm:px-6 lg:px-8">
            <div className="mx-auto grid w-full max-w-7xl gap-4 md:grid-cols-2">
              {template.faqs.map((faq) => (
                <article key={faq.question} className="rounded-2xl border border-stone-300 bg-[#fbf5e8] p-6 shadow-sm">
                  <h3 className="text-xl font-black">{faq.question}</h3>
                  <p className="mt-3 text-sm leading-6 text-stone-600">{faq.answer}</p>
                </article>
              ))}
            </div>
          </section>
        </>
      ) : null}

      <section className="bg-[var(--template-primary)] px-4 py-14 text-white sm:px-6 lg:px-8">
        <div className="mx-auto flex w-full max-w-7xl flex-col justify-between gap-6 lg:flex-row lg:items-center">
          <div className="max-w-2xl">
            <p className="text-xs font-black uppercase tracking-[0.18em] text-white/72">Continuar a experiencia</p>
            <h2 className="mt-3 font-heading text-3xl font-black leading-tight sm:text-4xl">Esse caminho vira um site premium completo.</h2>
            <p className="mt-4 text-sm leading-6 text-white/78">
              Home, paginas internas e uma leitura pensada para vender autoridade antes do contato.
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row">
            <Link
              href={selectHref}
              className="inline-flex h-12 items-center justify-center rounded-lg bg-white px-5 text-sm font-black text-[var(--template-primary)] shadow-lg"
            >
              Selecionar este modelo
            </Link>
            <a
              href={primaryActionHref}
              className="inline-flex h-12 items-center justify-center rounded-lg border border-white/24 bg-white/10 px-5 text-sm font-black text-white backdrop-blur"
            >
              Agendar avaliacao
            </a>
          </div>
        </div>
      </section>
      <FloatingWhatsAppButton href={primaryActionHref} />
    </main>
  );
}

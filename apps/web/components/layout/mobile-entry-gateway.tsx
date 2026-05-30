"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import {
  AlertTriangle,
  BarChart3,
  Bell,
  Bot,
  Building2,
  CalendarDays,
  ClipboardList,
  CreditCard,
  Database,
  FileStack,
  FileText,
  Gauge,
  LifeBuoy,
  ListChecks,
  MessageCircle,
  PhoneCall,
  Rocket,
  Settings,
  Shield,
  Sparkles,
  Stethoscope,
  UploadCloud,
  UserCog,
  Users,
  X,
  type LucideIcon,
} from "lucide-react";

import { Button, cn } from "@odontoflux/ui";

import { BrandingTheme } from "@/hooks/use-branding";
import { SessionContext } from "@/hooks/use-session";
import { MANAGED_PAGES, type ManagedPageDefinition, type PageKey } from "@/lib/page-access";

const MOBILE_ENTRY_MODAL_PREFIX = "clinicflux_mobile_entry_modal_seen";

const PAGE_ICONS: Record<PageKey, LucideIcon> = {
  dashboard: Gauge,
  operacoes: AlertTriangle,
  onboarding: Rocket,
  conversas: MessageCircle,
  agenda: CalendarDays,
  "equipe-medica": Stethoscope,
  servicos: ListChecks,
  unidades: Building2,
  pacientes: Users,
  leads: Bell,
  campanhas: ClipboardList,
  automacoes: Bot,
  "ia-lab": Sparkles,
  documentos: FileStack,
  importacao: UploadCloud,
  relatorios: BarChart3,
  faturamento: CreditCard,
  backup: Database,
  suporte: LifeBuoy,
  usuarios: UserCog,
  configuracoes: Settings,
  auditoria: FileText,
  admin: Shield,
};

const PAGE_COPY: Partial<Record<PageKey, string>> = {
  conversas: "Atendimento",
  agenda: "Horarios",
  pacientes: "Cadastros",
  dashboard: "Visao geral",
  leads: "Oportunidades",
  relatorios: "Indicadores",
};

function getStorageKey(prefix: string, session?: SessionContext): string {
  return `${prefix}:${session?.tenant_id ?? "tenant"}:${session?.id ?? "user"}`;
}

function sortMobilePages(pages: ManagedPageDefinition[]): ManagedPageDefinition[] {
  const priority: PageKey[] = ["conversas", "agenda", "pacientes", "dashboard", "leads", "relatorios"];
  return [...pages].sort((left, right) => {
    const leftIndex = priority.indexOf(left.key);
    const rightIndex = priority.indexOf(right.key);
    const normalizedLeft = leftIndex === -1 ? priority.length + MANAGED_PAGES.findIndex((page) => page.key === left.key) : leftIndex;
    const normalizedRight =
      rightIndex === -1 ? priority.length + MANAGED_PAGES.findIndex((page) => page.key === right.key) : rightIndex;
    return normalizedLeft - normalizedRight;
  });
}

function getButtonStyle(pageKey: PageKey): CSSProperties | undefined {
  if (pageKey === "conversas") {
    return {
      background: "linear-gradient(135deg, #25d366 0%, #128c7e 100%)",
      color: "#ffffff",
      borderColor: "rgba(255,255,255,0.28)",
      boxShadow: "0 16px 34px rgba(37, 211, 102, 0.32)",
    };
  }

  if (pageKey === "agenda") {
    return {
      background:
        "linear-gradient(135deg, color-mix(in srgb, var(--tenant-accent) 94%, white 6%), #fb923c 100%)",
      color: "rgb(var(--theme-accent-foreground))",
      borderColor: "rgba(255,255,255,0.32)",
      boxShadow: "0 16px 34px color-mix(in srgb, var(--tenant-accent) 30%, transparent)",
    };
  }

  if (pageKey === "pacientes") {
    return {
      background:
        "linear-gradient(135deg, color-mix(in srgb, var(--tenant-secondary) 86%, white 14%), color-mix(in srgb, var(--tenant-primary) 82%, black 18%))",
      color: "#ffffff",
      borderColor: "rgba(255,255,255,0.28)",
      boxShadow: "0 16px 34px color-mix(in srgb, var(--tenant-secondary) 26%, transparent)",
    };
  }

  return undefined;
}

export function MobileEntryGateway({
  pages,
  branding,
  session,
}: {
  pages: ManagedPageDefinition[];
  branding?: BrandingTheme;
  session?: SessionContext;
}) {
  const [ready, setReady] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [entryComplete, setEntryComplete] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const router = useRouter();
  const pathname = usePathname();

  const modalStorageKey = useMemo(() => getStorageKey(MOBILE_ENTRY_MODAL_PREFIX, session), [session]);
  const orderedPages = useMemo(() => sortMobilePages(pages), [pages]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const media = window.matchMedia("(hover: none) and (pointer: coarse) and (max-width: 767px)");
    const syncMobileState = () => {
      const mobile = media.matches;
      setIsMobile(mobile);
      setEntryComplete(!mobile);
      if (mobile && window.sessionStorage.getItem(modalStorageKey) !== "1") {
        window.setTimeout(() => setShowModal(true), 520);
      }
      setReady(true);
    };

    syncMobileState();
    media.addEventListener("change", syncMobileState);
    return () => media.removeEventListener("change", syncMobileState);
  }, [modalStorageKey]);

  useEffect(() => {
    if (typeof document === "undefined") return;
    const root = document.documentElement;
    const shouldMarkOpen = ready && isMobile && !entryComplete;
    if (shouldMarkOpen) {
      root.setAttribute("data-mobile-entry-open", "true");
    } else {
      root.removeAttribute("data-mobile-entry-open");
    }
    return () => root.removeAttribute("data-mobile-entry-open");
  }, [entryComplete, isMobile, ready]);

  const closeModal = () => {
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(modalStorageKey, "1");
    }
    setShowModal(false);
  };

  const openPage = (href: string) => {
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(modalStorageKey, "1");
    }
    setEntryComplete(true);
    setShowModal(false);
    if (pathname !== href) router.push(href);
  };

  if (!ready || !isMobile || entryComplete || !orderedPages.length) return null;

  const clinicName = session?.tenant_name ?? branding?.clinicName ?? "sua clinica";

  return (
    <div className="fixed inset-0 z-[100] h-dvh w-screen overflow-hidden bg-[var(--surface-base)] text-[var(--text-primary)]">
      <div
        className={cn(
          "mobile-entry-stage relative flex h-full w-full overflow-hidden px-[clamp(12px,4vw,18px)] py-[calc(10px+env(safe-area-inset-top))] pb-[calc(10px+env(safe-area-inset-bottom))]",
          showModal && "pointer-events-none",
        )}
      >
        <div className="mobile-entry-shine absolute inset-0 opacity-80" />
        <div className="relative z-10 flex h-full min-h-0 w-full flex-col">
          <header className="mobile-entry-reveal shrink-0 text-center">
            <div className="mx-auto flex h-[clamp(46px,12vw,60px)] w-[clamp(46px,12vw,60px)] items-center justify-center overflow-hidden rounded-2xl border border-white/35 bg-white shadow-2xl">
              <Image
                src="/clinicflux-icon-128x128.png"
                alt="ClinicFlux AI"
                width={56}
                height={56}
                priority
                className="h-full w-full object-cover"
              />
            </div>
            <p className="mt-2 text-[clamp(10px,2.7vw,12px)] font-bold uppercase tracking-[0.16em] text-muted-foreground">
              Experiencia mobile
            </p>
            <h1 className="mx-auto mt-1 max-w-[20rem] text-balance text-[clamp(19px,6vw,27px)] font-black leading-[1.03] text-foreground">
              Para onde voce quer ir agora?
            </h1>
            <p className="mx-auto mt-1 max-w-[21rem] text-[clamp(11px,3vw,13px)] leading-snug text-muted-foreground">
              {clinicName} com acesso rapido aos pontos mais importantes da rotina.
            </p>
          </header>

          <div className="mobile-entry-reveal mobile-entry-grid mt-3 grid min-h-0 grid-cols-2 gap-x-[clamp(10px,2.8vw,14px)] gap-y-[clamp(6px,1.8vw,9px)]">
            {orderedPages.map((page) => {
              const Icon = page.key === "conversas" ? PhoneCall : PAGE_ICONS[page.key];
              const featured = page.key === "conversas" || page.key === "agenda" || page.key === "pacientes";
              return (
                <button
                  key={page.key}
                  type="button"
                  onClick={() => openPage(page.href)}
                  className={cn(
                    "group relative flex min-h-0 min-w-0 items-center gap-1.5 overflow-hidden rounded-md border px-[clamp(6px,2vw,9px)] text-left shadow-sm transition active:scale-[0.98]",
                    featured
                      ? "border-white/25 text-white"
                      : "border-border bg-card/86 text-foreground backdrop-blur hover:bg-card",
                  )}
                  style={getButtonStyle(page.key)}
                >
                  <span
                    className={cn(
                      "flex h-[clamp(22px,6vw,28px)] w-[clamp(22px,6vw,28px)] shrink-0 items-center justify-center rounded-md",
                      featured ? "bg-white/18 text-white" : "bg-muted text-[var(--tenant-primary)]",
                    )}
                  >
                    <Icon size={15} strokeWidth={2.3} />
                  </span>
                  <span className="min-w-0 leading-tight">
                    <span className="block truncate text-[clamp(11px,3vw,14px)] font-extrabold">{page.label}</span>
                    <span className={cn("block truncate text-[clamp(8px,2.2vw,10px)]", featured ? "text-white/82" : "text-muted-foreground")}>
                      {PAGE_COPY[page.key] ?? "Abrir area"}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {showModal ? (
        <div className="fixed inset-0 z-[101] flex h-dvh w-screen items-center justify-center overflow-hidden bg-black/48 px-5 backdrop-blur-sm">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="mobile-entry-dialog-title"
            className="mobile-entry-modal w-full max-w-[22rem] rounded-2xl border border-white/25 bg-card p-5 text-center shadow-[0_24px_80px_rgba(15,23,42,0.32)]"
          >
            <button
              type="button"
              aria-label="Fechar aviso"
              onClick={closeModal}
              className="ml-auto flex h-8 w-8 items-center justify-center rounded-md border border-border text-muted-foreground"
            >
              <X size={15} />
            </button>
            <div
              className="mx-auto mt-1 flex h-12 w-12 items-center justify-center rounded-2xl text-white"
              style={{ background: "linear-gradient(135deg, var(--tenant-primary), var(--tenant-secondary))" }}
            >
              <Sparkles size={22} />
            </div>
            <h2 id="mobile-entry-dialog-title" className="mt-3 text-xl font-black text-foreground">
              Versao mobile detectada
            </h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Vimos que voce esta usando o sistema na versao mobile. Ele tambem funciona por aqui, mas para ver como ele
              vai ficar na sua clinica no dia a dia, abra de um computador ou notebook.
            </p>
            <Button className="mt-5 w-full" onClick={closeModal}>
              Continuar
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

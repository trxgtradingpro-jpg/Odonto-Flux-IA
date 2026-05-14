"use client";

import { useEffect, useMemo, useRef, useState, type UIEvent } from "react";
import { ChevronDown, LogOut } from "lucide-react";

import AdminPage from "@/app/(dashboard)/admin/page";
import AgendaPage from "@/app/(dashboard)/agenda/page";
import AuditoriaPage from "@/app/(dashboard)/auditoria/page";
import AutomacoesPage from "@/app/(dashboard)/automacoes/page";
import BackupPage from "@/app/(dashboard)/backup/page";
import CampanhasPage from "@/app/(dashboard)/campanhas/page";
import ConversasPage from "@/app/(dashboard)/conversas/page";
import DashboardPage from "@/app/(dashboard)/dashboard/page";
import DocumentosPage from "@/app/(dashboard)/documentos/page";
import EquipeMedicaPage from "@/app/(dashboard)/equipe-medica/page";
import FaturamentoPage from "@/app/(dashboard)/faturamento/page";
import IaLabPage from "@/app/(dashboard)/ia-lab/page";
import ImportacaoPage from "@/app/(dashboard)/importacao/page";
import LeadsPage from "@/app/(dashboard)/leads/page";
import OnboardingPage from "@/app/(dashboard)/onboarding/page";
import OperacoesPage from "@/app/(dashboard)/operacoes/page";
import PacientesPage from "@/app/(dashboard)/pacientes/page";
import RelatoriosPage from "@/app/(dashboard)/relatorios/page";
import SuportePage from "@/app/(dashboard)/suporte/page";
import UsuariosPage from "@/app/(dashboard)/usuarios/page";
import ConfiguracoesPanel from "@/components/settings/configuracoes-panel";
import { SessionContext } from "@/hooks/use-session";
import {
  canAccessPage,
  getAccessiblePages,
  PageKey,
  PRIMARY_PAGE_KEYS,
} from "@/lib/page-access";
import { initials } from "@/lib/formatters";
import { Button, cn } from "@odontoflux/ui";

const PAGE_RENDERERS: Record<PageKey, () => JSX.Element> = {
  dashboard: () => <DashboardPage />,
  operacoes: () => <OperacoesPage />,
  onboarding: () => <OnboardingPage />,
  conversas: () => <ConversasPage />,
  agenda: () => <AgendaPage />,
  "equipe-medica": () => <EquipeMedicaPage />,
  servicos: () => <ConfiguracoesPanel fixedTab="Serviços" />,
  unidades: () => <ConfiguracoesPanel fixedTab="Unidades" />,
  pacientes: () => <PacientesPage />,
  leads: () => <LeadsPage />,
  campanhas: () => <CampanhasPage />,
  automacoes: () => <AutomacoesPage />,
  "ia-lab": () => <IaLabPage />,
  documentos: () => <DocumentosPage />,
  importacao: () => <ImportacaoPage />,
  relatorios: () => <RelatoriosPage />,
  faturamento: () => <FaturamentoPage />,
  backup: () => <BackupPage />,
  suporte: () => <SuportePage />,
  usuarios: () => <UsuariosPage />,
  configuracoes: () => <ConfiguracoesPanel />,
  auditoria: () => <AuditoriaPage />,
  admin: () => <AdminPage />,
};

function getInitialPageKey(pageKeys: PageKey[]): PageKey | null {
  return pageKeys[0] ?? null;
}

export function FullscreenWorkspaceShell({
  session,
  onLogout,
}: {
  session?: SessionContext;
  onLogout: () => void;
}) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const floatingMenuRef = useRef<HTMLDivElement | null>(null);
  const contentScrollRef = useRef<HTMLDivElement | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [activePageKey, setActivePageKey] = useState<PageKey | null>(null);
  const [fullscreenActivated, setFullscreenActivated] = useState(false);
  const [showFloatingNav, setShowFloatingNav] = useState(false);
  const permissions = session?.resolved_page_permissions;
  const accessiblePages = useMemo(() => getAccessiblePages(permissions), [permissions]);
  const primaryPages = useMemo(
    () => accessiblePages.filter((page) => PRIMARY_PAGE_KEYS.includes(page.key)),
    [accessiblePages],
  );
  const menuPages = useMemo(
    () => accessiblePages.filter((page) => !PRIMARY_PAGE_KEYS.includes(page.key)),
    [accessiblePages],
  );

  useEffect(() => {
    const allowedKeys = accessiblePages.map((page) => page.key);
    if (!allowedKeys.length) {
      setActivePageKey(null);
      return;
    }

    setActivePageKey((current) => {
      if (current && allowedKeys.includes(current)) return current;
      return getInitialPageKey([
        ...primaryPages.map((page) => page.key),
        ...menuPages.map((page) => page.key),
        ...allowedKeys,
      ]);
    });
  }, [accessiblePages, menuPages, primaryPages]);

  useEffect(() => {
    let cancelled = false;
    async function enterFullscreen() {
      if (!rootRef.current || document.fullscreenElement) return;
      try {
        await rootRef.current.requestFullscreen();
        if (!cancelled) {
          setFullscreenActivated(true);
        }
      } catch {
        // keep workspace visible even if browser blocks the initial request
      }
    }
    void enterFullscreen();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const handleFullscreenChange = () => {
      if (!document.fullscreenElement && fullscreenActivated) {
        onLogout();
      }
      if (document.fullscreenElement) {
        setFullscreenActivated(true);
      }
    };
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, [fullscreenActivated, onLogout]);

  useEffect(() => {
    if (!menuOpen) return;
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!menuRef.current?.contains(target) && !floatingMenuRef.current?.contains(target)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [menuOpen]);

  const openPage = (pageKey: PageKey) => {
    if (!permissions || !canAccessPage(permissions, pageKey, "view")) return;
    setActivePageKey(pageKey);
    setMenuOpen(false);
    setShowFloatingNav(false);
    contentScrollRef.current?.scrollTo({ top: 0 });
  };

  const handleContentScroll = (event: UIEvent<HTMLDivElement>) => {
    const shouldFloat = event.currentTarget.scrollTop > 90;
    setShowFloatingNav((current) => (current === shouldFloat ? current : shouldFloat));
    if (shouldFloat) {
      setMenuOpen(false);
    }
  };

  const activePage = accessiblePages.find((page) => page.key === activePageKey) ?? null;
  const ActiveRenderer = activePageKey ? PAGE_RENDERERS[activePageKey] : null;
  const lockWorkspaceScroll = activePageKey === "conversas";
  const activeButtonStyle = {
    borderColor: "color-mix(in srgb, var(--fullscreen-accent) 72%, white 14%)",
    backgroundColor: "color-mix(in srgb, var(--fullscreen-accent) 24%, transparent)",
    color: "var(--fullscreen-foreground)",
    boxShadow: "0 12px 34px color-mix(in srgb, var(--fullscreen-accent) 20%, transparent)",
  };

  return (
    <div
      ref={rootRef}
      className="relative flex h-dvh max-h-dvh w-screen flex-col overflow-hidden"
      style={{
        backgroundColor: "var(--fullscreen-background)",
        color: "var(--fullscreen-foreground)",
      }}
    >
      <header
        className={cn(
          "relative z-50 flex items-center justify-between gap-3 overflow-visible border-b border-white/10 px-4 transition-[height,opacity,transform,border-color] duration-200",
          showFloatingNav
            ? "h-0 -translate-y-3 border-transparent opacity-0 pointer-events-none"
            : "h-16 translate-y-0 opacity-100",
        )}
        style={{ backgroundColor: "color-mix(in srgb, var(--fullscreen-header) 94%, transparent)" }}
      >
        <div className="flex min-w-0 items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white/10 text-xs font-semibold">
            {initials(session?.full_name)}
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{session?.full_name ?? "Usuario"}</p>
            <p className="truncate text-xs text-white/60">{session?.tenant_name ?? "OdontoFlux"}</p>
          </div>
        </div>

        <div className="flex flex-1 items-center justify-center gap-2 overflow-visible px-2">
          {primaryPages.map((page) => (
            <Button
              key={page.key}
              variant="outline"
              className="h-10 shrink-0 border-white/15 bg-white/5 text-white hover:bg-white/10"
              style={activePageKey === page.key ? activeButtonStyle : undefined}
              onClick={() => openPage(page.key)}
            >
              {page.label}
            </Button>
          ))}

          {menuPages.length ? (
            <div className="relative" ref={menuRef}>
              <Button
                variant="outline"
                className="h-10 shrink-0 gap-2 border-white/15 bg-white/5 text-white hover:bg-white/10"
                style={menuPages.some((page) => page.key === activePageKey) ? activeButtonStyle : undefined}
                onClick={() => setMenuOpen((current) => !current)}
              >
                Menu
                <ChevronDown size={14} />
              </Button>
              {menuOpen ? (
                <div
                  className="absolute right-0 top-12 z-[100] w-[min(88vw,320px)] rounded-[24px] border p-2 shadow-[0_28px_90px_rgba(0,0,0,0.45)] backdrop-blur-2xl"
                  style={{
                    borderColor: "color-mix(in srgb, var(--fullscreen-accent) 28%, white 10%)",
                    backgroundColor: "color-mix(in srgb, var(--fullscreen-header) 92%, black 8%)",
                  }}
                >
                  <div className="border-b border-white/10 px-3 py-2">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-white/45">Mais módulos</p>
                    <p className="text-sm font-semibold text-white">Escolha uma área para abrir</p>
                  </div>
                  <div className="mt-2 grid gap-1">
                    {menuPages.map((page) => {
                      const active = activePageKey === page.key;
                      return (
                        <button
                          key={page.key}
                          type="button"
                          className={cn(
                            "flex w-full items-center justify-between rounded-2xl px-3 py-2.5 text-left text-sm text-white/86 transition hover:bg-white/10",
                            active && "text-white",
                          )}
                          style={
                            active
                              ? {
                                  backgroundColor: "color-mix(in srgb, var(--fullscreen-accent) 20%, transparent)",
                                  border: "1px solid color-mix(in srgb, var(--fullscreen-accent) 42%, transparent)",
                                }
                              : undefined
                          }
                          onClick={() => openPage(page.key)}
                        >
                          <span className="font-semibold">{page.label}</span>
                          <span className="text-[11px] text-white/45">{page.href}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>

        <Button
          variant="outline"
          className="h-10 shrink-0 gap-2 border-white/15 bg-white/5 text-white hover:bg-white/10"
          onClick={onLogout}
        >
          <LogOut size={14} />
          Sair
        </Button>
      </header>

      {showFloatingNav ? (
        <div className="pointer-events-none absolute left-0 right-0 top-3 z-[80] flex justify-center px-3">
          <div
            className="pointer-events-auto flex max-w-[calc(100vw-24px)] items-center gap-1 rounded-2xl border border-white/12 p-1 shadow-[0_22px_70px_rgba(0,0,0,0.36)] backdrop-blur-2xl"
            style={{
              backgroundColor: "color-mix(in srgb, var(--fullscreen-header) 88%, transparent)",
              borderColor: "color-mix(in srgb, var(--fullscreen-accent) 24%, white 10%)",
            }}
          >
            {primaryPages.map((page) => (
              <button
                key={page.key}
                type="button"
                className="h-9 shrink-0 rounded-xl border border-white/12 bg-white/5 px-3 text-xs font-semibold text-white transition hover:bg-white/10"
                style={activePageKey === page.key ? activeButtonStyle : undefined}
                onClick={() => openPage(page.key)}
              >
                {page.label}
              </button>
            ))}

            {menuPages.length ? (
              <div className="relative" ref={floatingMenuRef}>
                <button
                  type="button"
                  className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-xl border border-white/12 bg-white/5 px-3 text-xs font-semibold text-white transition hover:bg-white/10"
                  style={menuPages.some((page) => page.key === activePageKey) ? activeButtonStyle : undefined}
                  onClick={() => setMenuOpen((current) => !current)}
                >
                  Menu
                  <ChevronDown size={13} />
                </button>
                {menuOpen ? (
                  <div
                    className="absolute right-0 top-11 z-[100] w-[min(88vw,320px)] rounded-[24px] border p-2 shadow-[0_28px_90px_rgba(0,0,0,0.45)] backdrop-blur-2xl"
                    style={{
                      borderColor: "color-mix(in srgb, var(--fullscreen-accent) 28%, white 10%)",
                      backgroundColor: "color-mix(in srgb, var(--fullscreen-header) 92%, black 8%)",
                    }}
                  >
                    <div className="border-b border-white/10 px-3 py-2">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-white/45">Mais modulos</p>
                      <p className="text-sm font-semibold text-white">Escolha uma area para abrir</p>
                    </div>
                    <div className="mt-2 grid gap-1">
                      {menuPages.map((page) => {
                        const active = activePageKey === page.key;
                        return (
                          <button
                            key={page.key}
                            type="button"
                            className={cn(
                              "flex w-full items-center justify-between rounded-2xl px-3 py-2.5 text-left text-sm text-white/86 transition hover:bg-white/10",
                              active && "text-white",
                            )}
                            style={
                              active
                                ? {
                                    backgroundColor: "color-mix(in srgb, var(--fullscreen-accent) 20%, transparent)",
                                    border: "1px solid color-mix(in srgb, var(--fullscreen-accent) 42%, transparent)",
                                  }
                                : undefined
                            }
                            onClick={() => openPage(page.key)}
                          >
                            <span className="font-semibold">{page.label}</span>
                            <span className="text-[11px] text-white/45">{page.href}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      <div
        className="relative flex-1 overflow-hidden"
        style={{
          background:
            "radial-gradient(circle at top, color-mix(in srgb, var(--fullscreen-accent) 18%, transparent), transparent 34%), linear-gradient(180deg, var(--fullscreen-background), color-mix(in srgb, var(--fullscreen-background) 88%, #111827 12%))",
        }}
      >
        {!accessiblePages.length ? (
          <div className="flex h-full items-center justify-center p-8">
            <div className="max-w-xl rounded-3xl border border-white/10 bg-white/5 p-6 text-center">
              <p className="text-lg font-semibold">Esse usuario nao possui paginas liberadas.</p>
              <p className="mt-2 text-sm text-white/70">
                Volte em Usuarios e libere pelo menos uma pagina com permissao de visualizacao.
              </p>
            </div>
          </div>
        ) : activePage && ActiveRenderer ? (
          <section className="flex h-full w-full flex-col overflow-hidden">
            <div
              ref={contentScrollRef}
              onScroll={lockWorkspaceScroll ? undefined : handleContentScroll}
              className={cn(
                "flex min-h-0 min-w-0 flex-1 flex-col bg-white text-stone-900",
                lockWorkspaceScroll ? "overflow-hidden overscroll-none" : "overflow-auto",
              )}
            >
              <ActiveRenderer />
            </div>
          </section>
        ) : (
          <div className="flex h-full items-center justify-center p-8">
            <div className="max-w-xl rounded-3xl border border-white/10 bg-white/5 p-6 text-center">
              <p className="text-lg font-semibold">Escolha um modulo para continuar.</p>
              <p className="mt-2 text-sm text-white/70">
                Os botoes do topo sempre abrem um unico modulo por vez ocupando toda a tela.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

"use client";

import { useEffect, useMemo, useRef, useState, type UIEvent } from "react";
import { flushSync } from "react-dom";
import { usePathname, useRouter } from "next/navigation";

import { FullscreenWorkspaceShell } from "./fullscreen-workspace-shell";
import { QuickAccessPill } from "./quick-access-pill";
import { QuickFullscreenWorkspace } from "./quick-fullscreen-workspace";
import { QUICK_FOCUS_PAGE_KEYS, QuickFocusPageKey } from "./quick-focus-pages";
import { Sidebar } from "./sidebar";
import { SupportFab } from "./support-fab";
import { Topbar } from "./topbar";
import { brandingSurfaceClass, useBranding } from "@/hooks/use-branding";
import { OwnerUnitScopeProvider } from "@/hooks/use-owner-unit-scope";
import { useSession } from "@/hooks/use-session";
import { api } from "@/lib/api";
import { DEMO_WEBCHAT_WORKSPACE_EVENT_NAME, type DemoWebchatWorkspaceDetail } from "@/lib/demo-tour";
import { clearDemoEntryTargetPath, readDemoEntryTargetPath } from "@/lib/demo-session";
import { canAccessPage, findManagedPageByPathname, getAccessiblePages, getFirstAccessiblePageHref } from "@/lib/page-access";
import { Button, cn } from "@odontoflux/ui";

function hexToRgbTriplet(color: string): string {
  const normalized = color.replace("#", "");
  if (!/^[0-9a-f]{6}$/i.test(normalized)) return "0 0 0";
  const numeric = Number.parseInt(normalized, 16);
  const red = (numeric >> 16) & 255;
  const green = (numeric >> 8) & 255;
  const blue = numeric & 255;
  return `${red} ${green} ${blue}`;
}

function getReadableForegroundTriplet(color: string): string {
  const normalized = color.replace("#", "");
  if (!/^[0-9a-f]{6}$/i.test(normalized)) return "255 255 255";
  const numeric = Number.parseInt(normalized, 16);
  const red = (numeric >> 16) & 255;
  const green = (numeric >> 8) & 255;
  const blue = numeric & 255;
  const luminance = (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255;
  return luminance > 0.58 ? "17 24 39" : "255 255 255";
}

function buildCssUrlValue(url: string): string {
  const safeValue = url.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  return `url("${safeValue}")`;
}

export function AppShell({ children, onLogout }: { children: React.ReactNode; onLogout: () => void }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [quickFocusPageKey, setQuickFocusPageKey] = useState<QuickFocusPageKey | null>(null);
  const [showFloatingQuickAccess, setShowFloatingQuickAccess] = useState(false);
  const [hideSidebarForGuide, setHideSidebarForGuide] = useState(false);
  const [hideChromeForDemoWorkspace, setHideChromeForDemoWorkspace] = useState(false);
  const contentScrollRef = useRef<HTMLDivElement | null>(null);
  const sessionQuery = useSession();
  const brandingQuery = useBranding();
  const branding = brandingQuery.data;
  const pathname = usePathname();
  const router = useRouter();
  const isConversationWorkspace = pathname === "/conversas";
  const isAgendaWorkspace = pathname === "/agenda";
  const isImmersiveWorkspace = isConversationWorkspace || isAgendaWorkspace;
  const hideDashboardChrome = isConversationWorkspace && hideChromeForDemoWorkspace;
  const reserveGuideDockedRail = hideSidebarForGuide && isImmersiveWorkspace && !hideDashboardChrome;

  useEffect(() => {
    const root = document.documentElement;
    if (!branding) return;

    root.style.setProperty("--tenant-primary", branding.primaryColor);
    root.style.setProperty("--tenant-secondary", branding.secondaryColor);
    root.style.setProperty("--tenant-accent", branding.accentColor);
    root.style.setProperty("--surface-base", branding.backgroundColor);
    root.style.setProperty("--surface-subtle", branding.surfaceColor);
    root.style.setProperty("--surface-card", branding.cardColor);
    root.style.setProperty("--text-primary", branding.textColor);
    root.style.setProperty("--text-secondary", branding.mutedTextColor);
    root.style.setProperty("--border-soft", branding.borderColor);
    root.style.setProperty("--theme-background", hexToRgbTriplet(branding.backgroundColor));
    root.style.setProperty("--theme-foreground", hexToRgbTriplet(branding.textColor));
    root.style.setProperty("--theme-primary", hexToRgbTriplet(branding.primaryColor));
    root.style.setProperty("--theme-primary-foreground", getReadableForegroundTriplet(branding.primaryColor));
    root.style.setProperty("--theme-secondary", hexToRgbTriplet(branding.secondaryColor));
    root.style.setProperty("--theme-accent", hexToRgbTriplet(branding.accentColor));
    root.style.setProperty("--theme-accent-foreground", getReadableForegroundTriplet(branding.accentColor));
    root.style.setProperty("--theme-muted", hexToRgbTriplet(branding.surfaceColor));
    root.style.setProperty("--theme-muted-foreground", hexToRgbTriplet(branding.mutedTextColor));
    root.style.setProperty("--theme-card", hexToRgbTriplet(branding.cardColor));
    root.style.setProperty("--theme-border", hexToRgbTriplet(branding.borderColor));
    root.style.setProperty("--fullscreen-background", branding.fullscreenBackgroundColor);
    root.style.setProperty("--fullscreen-header", branding.fullscreenHeaderColor);
    root.style.setProperty("--fullscreen-accent", branding.fullscreenAccentColor);
    root.style.setProperty("--fullscreen-foreground", branding.fullscreenForegroundColor);
    root.style.setProperty("--branded-demo-background-image", buildCssUrlValue(branding.demoBackgroundImageUrl));
    root.style.setProperty("--branded-demo-background-opacity", String(branding.demoBackgroundOpacity));
  }, [branding]);

  const surfaceClass = useMemo(
    () => brandingSurfaceClass(branding?.surfaceStyle ?? "soft"),
    [branding?.surfaceStyle],
  );
  const permissions = sessionQuery.data?.resolved_page_permissions;
  const accessiblePages = useMemo(() => getAccessiblePages(permissions), [permissions]);
  const allowedPageKeys = useMemo(() => accessiblePages.map((page) => page.key), [accessiblePages]);
  const quickAccessPages = useMemo(
    () => QUICK_FOCUS_PAGE_KEYS.filter((pageKey) => canAccessPage(permissions, pageKey, "view")),
    [permissions],
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    const media = window.matchMedia("(min-width: 1024px)");
    const onChange = (event: MediaQueryListEvent) => {
      if (event.matches) {
        setMobileSidebarOpen(false);
      }
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const syncWorkspaceChrome = (detail?: DemoWebchatWorkspaceDetail | null) => {
      const shouldHide = Boolean(isConversationWorkspace && detail?.open);
      setHideChromeForDemoWorkspace((current) => (current === shouldHide ? current : shouldHide));
      if (shouldHide) {
        setMobileSidebarOpen(false);
      }
    };

    const scopedWindow = window as Window & {
      __odontofluxDemoWebchatWorkspaceOpen?: boolean;
    };
    syncWorkspaceChrome({ open: scopedWindow.__odontofluxDemoWebchatWorkspaceOpen ?? false });

    const handleWorkspaceUpdate = (event: Event) => {
      syncWorkspaceChrome((event as CustomEvent<DemoWebchatWorkspaceDetail>).detail);
    };

    window.addEventListener(DEMO_WEBCHAT_WORKSPACE_EVENT_NAME, handleWorkspaceUpdate as EventListener);
    return () =>
      window.removeEventListener(DEMO_WEBCHAT_WORKSPACE_EVENT_NAME, handleWorkspaceUpdate as EventListener);
  }, [isConversationWorkspace]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    type DemoGuideStateDetail = {
      active?: boolean;
      placement?: "centered" | "docked" | null;
    };

    const syncGuideSidebar = (detail?: DemoGuideStateDetail | null) => {
      const shouldHide = Boolean(detail?.active && detail?.placement === "docked");
      setHideSidebarForGuide((current) => (current === shouldHide ? current : shouldHide));
    };

    const scopedWindow = window as Window & {
      __odontofluxDemoGuideState?: DemoGuideStateDetail;
    };
    syncGuideSidebar(scopedWindow.__odontofluxDemoGuideState);

    const handleGuideStateUpdate = (event: Event) => {
      syncGuideSidebar((event as CustomEvent<DemoGuideStateDetail>).detail);
    };

    window.addEventListener("odontoflux:demo-guide-state", handleGuideStateUpdate as EventListener);
    return () =>
      window.removeEventListener("odontoflux:demo-guide-state", handleGuideStateUpdate as EventListener);
  }, []);

  useEffect(() => {
    if (!sessionQuery.data || sessionQuery.data.force_fullscreen_mode) return;
    if (!accessiblePages.length) return;
    const currentPage = findManagedPageByPathname(pathname);
    if (!currentPage) return;
    if (canAccessPage(permissions, currentPage.key, "view")) return;
    router.replace(getFirstAccessiblePageHref(permissions));
  }, [accessiblePages.length, pathname, permissions, router, sessionQuery.data]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!sessionQuery.data?.roles?.includes("demo_client")) return;

    const targetPath = readDemoEntryTargetPath();
    if (!targetPath) return;

    const currentPath = pathname.split("?")[0];
    if (currentPath === targetPath) {
      clearDemoEntryTargetPath();
      return;
    }

    window.location.replace(targetPath);
  }, [pathname, sessionQuery.data?.roles]);

  useEffect(() => {
    if (quickFocusPageKey && !quickAccessPages.includes(quickFocusPageKey)) {
      setQuickFocusPageKey(null);
    }
  }, [quickAccessPages, quickFocusPageKey]);

  useEffect(() => {
    if (!sessionQuery.data?.roles?.includes("demo_client")) return;
    const sessionKey = "odontoflux_demo_session_id";
    const existing = window.sessionStorage.getItem(sessionKey);
    const demoSessionId = existing ?? crypto.randomUUID();
    window.sessionStorage.setItem(sessionKey, demoSessionId);
    const eventByPath: Record<string, string> = {
      "/conversas": "visited_conversations",
      "/agenda": "visited_agenda",
      "/pacientes": "visited_patients",
      "/configuracoes": "visited_settings",
      "/equipe-medica": "visited_team",
      "/servicos": "visited_services",
      "/unidades": "visited_units",
      "/leads": "visited_leads",
    };
    const eventName = eventByPath[pathname] ?? "page_view";
    api
      .post("/demo/events", {
        event_name: eventName,
        page_path: pathname,
        session_id: demoSessionId,
        payload: { title: document.title },
      })
      .catch(() => undefined);
  }, [pathname, sessionQuery.data?.roles]);

  const handleToggleSidebar = () => {
    if (typeof window !== "undefined" && window.matchMedia("(max-width: 1023px)").matches) {
      setMobileSidebarOpen((current) => !current);
      return;
    }
    setCollapsed((current) => !current);
  };

  const handleOpenQuickFocus = (pageKey: QuickFocusPageKey) => {
    if (!quickAccessPages.includes(pageKey)) return;
    flushSync(() => setQuickFocusPageKey(pageKey));
    const workspace = document.getElementById("odontoflux-quick-fullscreen-workspace");
    if (!workspace || document.fullscreenElement) return;
    workspace.requestFullscreen().catch(() => undefined);
  };

  const handleContentScroll = (event: UIEvent<HTMLDivElement>) => {
    const shouldFloat = event.currentTarget.scrollTop > 90;
    setShowFloatingQuickAccess((current) => (current === shouldFloat ? current : shouldFloat));
  };

  return (
    <OwnerUnitScopeProvider session={sessionQuery.data}>
      {sessionQuery.data?.force_fullscreen_mode ? (
        <FullscreenWorkspaceShell session={sessionQuery.data} onLogout={onLogout} />
      ) : sessionQuery.data && !accessiblePages.length ? (
        <div className={`branded-app-shell flex min-h-screen items-center justify-center px-6 py-10 ${surfaceClass}`}>
          <div className="w-full max-w-xl rounded-[32px] border border-border bg-card/95 p-8 text-center shadow-[0_30px_80px_rgba(15,23,42,0.12)]">
            <p className="text-sm font-semibold uppercase tracking-[0.28em] text-muted-foreground">Acesso bloqueado</p>
            <h1 className="mt-3 text-3xl font-semibold text-foreground">Este usuario ainda nao tem paginas liberadas</h1>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              Edite o cadastro em <strong>Usuarios</strong> e habilite pelo menos uma pagina com permissao de
              visualizacao para continuar.
            </p>
            <div className="mt-6 flex justify-center">
              <Button onClick={onLogout}>Sair</Button>
            </div>
          </div>
        </div>
      ) : (
        <div className={`branded-app-shell flex h-dvh w-full overflow-hidden ${surfaceClass}`}>
          <Sidebar
            collapsed={collapsed}
            autoHide={hideSidebarForGuide || hideDashboardChrome}
            mobileOpen={mobileSidebarOpen}
            onCloseMobile={() => setMobileSidebarOpen(false)}
            session={sessionQuery.data}
            branding={branding}
            allowedPageKeys={allowedPageKeys}
          />
          <div className="relative flex min-h-0 min-w-0 flex-1 flex-col">
            <div
              ref={contentScrollRef}
              onScroll={isImmersiveWorkspace ? undefined : handleContentScroll}
              className={cn(
                "branded-content-frame min-h-0 min-w-0 flex-1 overflow-x-hidden overscroll-contain",
                isImmersiveWorkspace ? "flex flex-col overflow-hidden" : "overflow-y-auto",
              )}
            >
              {!hideDashboardChrome ? (
                <Topbar
                  onLogout={onLogout}
                  collapsed={collapsed}
                  onToggleSidebar={handleToggleSidebar}
                  session={sessionQuery.data}
                  branding={branding}
                  quickAccessPages={quickAccessPages}
                  onOpenQuickAccess={handleOpenQuickFocus}
                />
              ) : null}
              <main
                className={cn(
                  "min-w-0 transition-[padding] duration-700 ease-in-out",
                  isConversationWorkspace
                    ? cn(
                        "flex min-h-0 flex-1 flex-col px-0 py-0",
                        reserveGuideDockedRail && "lg:pl-[20rem] xl:pl-[21rem]",
                      )
                    : isAgendaWorkspace
                      ? cn(
                          "flex min-h-0 flex-1 flex-col px-2 py-2 sm:px-3 sm:py-2.5 md:px-4 md:py-3 lg:px-5",
                          reserveGuideDockedRail && "lg:pl-[21rem] xl:pl-[22rem]",
                        )
                      : "px-3 py-4 pb-24 sm:px-4 sm:pb-28 md:px-6 md:py-6 md:pb-28 lg:px-8",
                )}
              >
                <div className={cn(isImmersiveWorkspace ? "flex min-h-0 flex-1 flex-col" : "content-shell")}>
                  {children}
                </div>
              </main>
            </div>
            {showFloatingQuickAccess && quickAccessPages.length && !isImmersiveWorkspace ? (
              <div className="pointer-events-none absolute left-0 right-0 top-3 z-40 hidden justify-center px-3 md:flex">
                <QuickAccessPill
                  pages={quickAccessPages}
                  onOpen={handleOpenQuickFocus}
                  labels="always"
                  tone="floating"
                  className="pointer-events-auto flex"
                />
              </div>
            ) : null}
          </div>
          {quickFocusPageKey ? (
            <QuickFullscreenWorkspace
              activePageKey={quickFocusPageKey}
              session={sessionQuery.data}
              onChangePage={setQuickFocusPageKey}
              onClose={() => setQuickFocusPageKey(null)}
            />
          ) : null}
          <SupportFab />
        </div>
      )}
    </OwnerUnitScopeProvider>
  );
}

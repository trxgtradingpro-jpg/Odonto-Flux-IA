"use client";

import { useEffect, useMemo, useRef, useState, type UIEvent } from "react";
import { CalendarDays, MessageSquare, UsersRound, X } from "lucide-react";

import AgendaPage from "@/app/(dashboard)/agenda/page";
import ConversasPage from "@/app/(dashboard)/conversas/page";
import PacientesPage from "@/app/(dashboard)/pacientes/page";
import { SessionContext } from "@/hooks/use-session";
import { api } from "@/lib/api";
import { canAccessPage } from "@/lib/page-access";
import { Button, cn } from "@odontoflux/ui";

import {
  QUICK_FOCUS_PAGE_KEYS,
  QUICK_FOCUS_PAGE_LABELS,
  QuickFocusPageKey,
} from "./quick-focus-pages";

const QUICK_PAGE_RENDERERS: Record<QuickFocusPageKey, () => JSX.Element> = {
  conversas: () => <ConversasPage />,
  agenda: () => <AgendaPage />,
  pacientes: () => <PacientesPage />,
};

const QUICK_PAGE_ICONS = {
  conversas: MessageSquare,
  agenda: CalendarDays,
  pacientes: UsersRound,
} satisfies Record<QuickFocusPageKey, typeof MessageSquare>;

const DEMO_EVENT_BY_PAGE: Record<QuickFocusPageKey, string> = {
  conversas: "visited_conversations",
  agenda: "visited_agenda",
  pacientes: "visited_patients",
};

function getDemoSessionId() {
  const sessionKey = "odontoflux_demo_session_id";
  const existing = window.sessionStorage.getItem(sessionKey);
  const demoSessionId = existing ?? crypto.randomUUID();
  window.sessionStorage.setItem(sessionKey, demoSessionId);
  return demoSessionId;
}

export function QuickFullscreenWorkspace({
  activePageKey,
  session,
  onChangePage,
  onClose,
}: {
  activePageKey: QuickFocusPageKey;
  session?: SessionContext;
  onChangePage: (pageKey: QuickFocusPageKey) => void;
  onClose: () => void;
}) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const contentScrollRef = useRef<HTMLDivElement | null>(null);
  const [wasFullscreen, setWasFullscreen] = useState(false);
  const [showFloatingNav, setShowFloatingNav] = useState(false);
  const permissions = session?.resolved_page_permissions;
  const availablePages = useMemo(
    () => QUICK_FOCUS_PAGE_KEYS.filter((pageKey) => canAccessPage(permissions, pageKey, "view")),
    [permissions],
  );
  const ActiveRenderer = QUICK_PAGE_RENDERERS[activePageKey];
  const lockWorkspaceScroll = activePageKey === "conversas";

  useEffect(() => {
    if (!availablePages.length) {
      onClose();
      return;
    }
    if (!availablePages.includes(activePageKey)) {
      onChangePage(availablePages[0]);
    }
  }, [activePageKey, availablePages, onChangePage, onClose]);

  useEffect(() => {
    const handleFullscreenChange = () => {
      const ownsFullscreen = document.fullscreenElement === rootRef.current;
      if (ownsFullscreen) {
        setWasFullscreen(true);
        return;
      }
      if (!document.fullscreenElement && wasFullscreen) {
        onClose();
      }
    };

    handleFullscreenChange();
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, [onClose, wasFullscreen]);

  useEffect(() => {
    if (!session?.roles?.includes("demo_client")) return;
    const demoSessionId = getDemoSessionId();
    api
      .post("/demo/events", {
        event_name: DEMO_EVENT_BY_PAGE[activePageKey],
        page_path: `/${activePageKey}`,
        session_id: demoSessionId,
        payload: { source: "quick_fullscreen" },
      })
      .catch(() => undefined);
  }, [activePageKey, session?.roles]);

  const closeWorkspace = async () => {
    if (document.fullscreenElement) {
      await document.exitFullscreen().catch(() => undefined);
    }
    onClose();
  };

  const openPage = (pageKey: QuickFocusPageKey) => {
    onChangePage(pageKey);
    setShowFloatingNav(false);
    contentScrollRef.current?.scrollTo({ top: 0 });
  };

  const handleContentScroll = (event: UIEvent<HTMLDivElement>) => {
    const shouldFloat = event.currentTarget.scrollTop > 90;
    setShowFloatingNav((current) => (current === shouldFloat ? current : shouldFloat));
  };

  return (
    <div
      ref={rootRef}
      id="odontoflux-quick-fullscreen-workspace"
      className="fixed inset-0 z-[90] flex h-dvh max-h-dvh w-screen flex-col overflow-hidden"
      style={{
        backgroundColor: "var(--fullscreen-background)",
        color: "var(--fullscreen-foreground)",
      }}
    >
      <header
        className={cn(
          "flex shrink-0 items-center justify-between gap-2 overflow-hidden border-b border-white/10 px-2 shadow-[0_12px_40px_rgba(0,0,0,0.35)] backdrop-blur transition-[height,opacity,transform,border-color] duration-200 md:px-4",
          showFloatingNav
            ? "h-0 -translate-y-3 border-transparent opacity-0 pointer-events-none"
            : "h-14 translate-y-0 opacity-100",
        )}
        style={{ backgroundColor: "color-mix(in srgb, var(--fullscreen-header) 94%, transparent)" }}
      >
        <div className="hidden min-w-0 px-2 sm:block">
          <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-white/45">Acesso rapido</p>
          <p className="truncate text-xs font-semibold text-white/80">{session?.tenant_name ?? "OdontoFlux"}</p>
        </div>

        <nav className="flex min-w-0 flex-1 items-center justify-center gap-1 overflow-x-auto px-1">
          {availablePages.map((pageKey) => {
            const Icon = QUICK_PAGE_ICONS[pageKey];
            const active = activePageKey === pageKey;
            return (
              <button
                key={pageKey}
                type="button"
                className={cn(
                  "inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border px-3 text-xs font-semibold transition",
                  active
                    ? "text-white shadow-[0_10px_30px_rgba(0,0,0,0.22)]"
                    : "border-white/12 bg-white/5 text-white/82 hover:bg-white/10",
                )}
                style={
                  active
                    ? {
                        borderColor: "color-mix(in srgb, var(--fullscreen-accent) 72%, white 14%)",
                        backgroundColor: "var(--fullscreen-accent)",
                        color: "var(--fullscreen-foreground)",
                      }
                    : undefined
                }
                onClick={() => openPage(pageKey)}
              >
                <Icon size={14} />
                {QUICK_FOCUS_PAGE_LABELS[pageKey]}
              </button>
            );
          })}
        </nav>

        <Button
          variant="outline"
          className="h-9 shrink-0 gap-1.5 border-white/15 bg-white/5 px-3 text-xs text-white hover:bg-white/10"
          onClick={() => void closeWorkspace()}
          title="Fechar tela cheia"
        >
          <X size={14} />
          <span className="hidden sm:inline">Fechar</span>
        </Button>
      </header>

      {showFloatingNav ? (
        <div className="pointer-events-none absolute left-0 right-0 top-3 z-[95] flex justify-center px-3">
          <div
            className="pointer-events-auto flex max-w-[calc(100vw-24px)] items-center gap-1 rounded-2xl border border-white/12 p-1 shadow-[0_22px_70px_rgba(0,0,0,0.36)] backdrop-blur-2xl"
            style={{
              backgroundColor: "color-mix(in srgb, var(--fullscreen-header) 88%, transparent)",
              borderColor: "color-mix(in srgb, var(--fullscreen-accent) 24%, white 10%)",
            }}
          >
            {availablePages.map((pageKey) => {
              const Icon = QUICK_PAGE_ICONS[pageKey];
              const active = activePageKey === pageKey;
              return (
                <button
                  key={pageKey}
                  type="button"
                  className={cn(
                    "inline-flex h-9 shrink-0 items-center gap-1.5 rounded-xl border px-3 text-xs font-semibold transition",
                    active
                      ? "text-white shadow-[0_10px_30px_rgba(0,0,0,0.22)]"
                      : "border-white/12 bg-white/5 text-white/82 hover:bg-white/10",
                  )}
                  style={
                    active
                      ? {
                          borderColor: "color-mix(in srgb, var(--fullscreen-accent) 72%, white 14%)",
                          backgroundColor: "var(--fullscreen-accent)",
                          color: "var(--fullscreen-foreground)",
                        }
                      : undefined
                  }
                  onClick={() => openPage(pageKey)}
                >
                  <Icon size={14} />
                  <span className="hidden sm:inline">{QUICK_FOCUS_PAGE_LABELS[pageKey]}</span>
                </button>
              );
            })}
            <button
              type="button"
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/12 bg-white/5 text-white/82 transition hover:bg-white/10"
              onClick={() => void closeWorkspace()}
              title="Fechar tela cheia"
            >
              <X size={14} />
            </button>
          </div>
        </div>
      ) : null}

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
    </div>
  );
}

"use client";

import Link from "next/link";
import Image from "next/image";
import { useState } from "react";
import { Bell, LogOut, Menu } from "lucide-react";

import { Badge, Button } from "@odontoflux/ui";

import { BrandingTheme } from "@/hooks/use-branding";
import { useLiveNotifications } from "@/hooks/use-live-notifications";
import { useOwnerUnitScope } from "@/hooks/use-owner-unit-scope";
import { SessionContext } from "@/hooks/use-session";
import { clinicInitials } from "@/lib/formatters";
import { QuickFocusPageKey } from "./quick-focus-pages";
import { QuickAccessPill } from "./quick-access-pill";

export function Topbar({
  onLogout,
  collapsed,
  onToggleSidebar,
  session,
  branding,
  quickAccessPages = [],
  onOpenQuickAccess,
}: {
  onLogout: () => void;
  collapsed: boolean;
  onToggleSidebar: () => void;
  session?: SessionContext;
  branding?: BrandingTheme;
  quickAccessPages?: QuickFocusPageKey[];
  onOpenQuickAccess?: (pageKey: QuickFocusPageKey) => void;
}) {
  const [openNotifications, setOpenNotifications] = useState(false);
  const notificationsQuery = useLiveNotifications();
  const ownerUnitScope = useOwnerUnitScope();
  const notifications = notificationsQuery.data?.notifications ?? [];
  const badges = notificationsQuery.data?.badges;
  const totalAlerts = (badges?.pendingConfirmations ?? 0) + (badges?.conversations ?? 0);
  const clinicDisplayName = session?.tenant_name ?? branding?.clinicName ?? "Clinica atual";
  const activeWorkspaceLabel = ownerUnitScope.canSwitchUnits
    ? ownerUnitScope.selectedUnitName || "Todas as unidades"
    : session?.unit_name ?? "Unidade principal";

  return (
    <header
      data-app-shell-topbar="true"
      className="flex min-h-16 shrink-0 min-w-0 items-center justify-between gap-2 border-b border-border bg-card/90 px-3 py-2 backdrop-blur-md sm:px-4 md:px-6 lg:px-8"
      style={{
        boxShadow: "0 8px 24px rgba(0,0,0,0.05)",
      }}
    >
      <div className="flex min-w-0 items-center gap-2 sm:gap-3">
        <Button variant="outline" className="h-9 w-9 shrink-0 px-0" onClick={onToggleSidebar} title="Alternar menu">
          <Menu size={16} />
        </Button>
        <div className="hidden items-center gap-2 rounded-xl border border-border bg-card px-2.5 py-1.5 md:flex">
          {branding?.logoDataUrl ? (
            <Image
              src={branding.logoDataUrl}
              alt="Logo da clinica"
              width={32}
              height={32}
              unoptimized
              className="h-8 w-8 rounded-md object-cover"
            />
          ) : (
            <div
              className="flex h-8 w-8 items-center justify-center rounded-md text-xs font-bold text-white"
              style={{ backgroundColor: "var(--tenant-primary)" }}
            >
              {clinicInitials(clinicDisplayName)}
            </div>
          )}
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
              Clinica ativa {collapsed ? "- compacto" : ""}
            </p>
            <h2 className="text-sm font-bold text-foreground md:text-base">
              {clinicDisplayName}
            </h2>
            <p className="text-[11px] text-muted-foreground">{activeWorkspaceLabel}</p>
          </div>
        </div>
      </div>

      <div className="flex min-w-0 items-center gap-1 sm:gap-2">
        {quickAccessPages.length && onOpenQuickAccess ? (
          <QuickAccessPill pages={quickAccessPages} onOpen={onOpenQuickAccess} className="hidden md:flex" />
        ) : null}

        {ownerUnitScope.canSwitchUnits ? (
          <select
            className="hidden h-9 rounded-xl border border-border bg-card px-3 text-sm font-medium text-foreground md:inline-flex"
            value={ownerUnitScope.selectedUnitId}
            onChange={(event) => ownerUnitScope.setSelectedUnitId(event.target.value)}
            aria-label="Selecionar unidade global"
          >
            <option value="all">Todas as unidades</option>
            {ownerUnitScope.units.map((unit) => (
              <option key={unit.id} value={unit.id}>
                {unit.name}
              </option>
            ))}
          </select>
        ) : (
          <Badge className="hidden border-primary/20 bg-primary/10 text-primary md:inline-flex">
            {session?.unit_name ?? "Unidade"}
          </Badge>
        )}

        <div className="relative">
          <button
            type="button"
            className="relative inline-flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground transition hover:bg-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
            onClick={() => setOpenNotifications((current) => !current)}
            aria-label="Abrir notificacoes"
          >
            <Bell size={16} />
            {totalAlerts > 0 ? (
              <span className="absolute -right-1 -top-1 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold text-white">
                {totalAlerts > 99 ? "99+" : totalAlerts}
              </span>
            ) : null}
          </button>
          {openNotifications ? (
            <div className="absolute right-0 top-11 z-30 w-[min(92vw,340px)] rounded-2xl border border-border bg-card p-2 shadow-2xl">
              <div className="flex items-center justify-between px-2 py-1">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Notificacoes</p>
                <span className="text-[11px] text-muted-foreground">
                  {notificationsQuery.data?.updatedAt
                    ? new Date(notificationsQuery.data.updatedAt).toLocaleTimeString("pt-BR")
                    : "--:--"}
                </span>
              </div>
              <div className="max-h-[260px] space-y-1 overflow-y-auto pr-1">
                {notifications.length ? (
                  notifications.map((item) => (
                    <Link
                      href={item.href ?? "/dashboard"}
                      key={item.id}
                      className="block rounded-md border border-border p-2 text-sm transition hover:bg-muted/60"
                      onClick={() => setOpenNotifications(false)}
                    >
                      <p className="font-semibold text-foreground">{item.title}</p>
                      <p className="text-xs text-muted-foreground">{item.description}</p>
                    </Link>
                  ))
                ) : (
                  <p className="rounded-md border border-border p-2 text-xs text-muted-foreground">
                    Nenhuma notificacao no momento.
                  </p>
                )}
              </div>
            </div>
          ) : null}
        </div>

        <Button variant="outline" onClick={onLogout} className="shrink-0 gap-1.5 px-2 sm:px-3">
          <LogOut size={14} />
          <span className="hidden sm:inline">Sair</span>
        </Button>
      </div>
    </header>
  );
}

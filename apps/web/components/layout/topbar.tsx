"use client";

import Link from "next/link";
import Image from "next/image";
import { useState } from "react";
import { Bell, CalendarDays, LogOut, Menu } from "lucide-react";

import { Badge, Button } from "@odontoflux/ui";

import { BrandingTheme } from "@/hooks/use-branding";
import { useLiveNotifications } from "@/hooks/use-live-notifications";
import { SessionContext } from "@/hooks/use-session";
import { formatDateBR, initials, ROLE_LABELS } from "@/lib/formatters";

export function Topbar({
  onLogout,
  collapsed,
  onToggleSidebar,
  session,
  branding,
}: {
  onLogout: () => void;
  collapsed: boolean;
  onToggleSidebar: () => void;
  session?: SessionContext;
  branding?: BrandingTheme;
}) {
  const [openNotifications, setOpenNotifications] = useState(false);
  const notificationsQuery = useLiveNotifications();
  const notifications = notificationsQuery.data?.notifications ?? [];
  const badges = notificationsQuery.data?.badges;
  const totalAlerts = (badges?.pendingConfirmations ?? 0) + (badges?.conversations ?? 0);
  const today = formatDateBR(new Date());

  return (
    <header
      className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-border bg-white/90 px-4 backdrop-blur md:px-6"
      style={{
        boxShadow: "0 8px 24px rgba(0,0,0,0.04)",
      }}
    >
      <div className="flex items-center gap-3">
        <Button variant="outline" className="h-9 w-9 px-0" onClick={onToggleSidebar} title="Alternar menu">
          <Menu size={16} />
        </Button>
        <div className="hidden items-center gap-2 rounded-lg border border-stone-200 bg-white px-2 py-1 md:flex">
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
              OF
            </div>
          )}
          <div>
            <p className="text-[11px] uppercase tracking-wide text-stone-500">
              SaaS OdontoFlux {collapsed ? "- compacto" : ""}
            </p>
            <h2 className="text-sm font-semibold text-stone-800 md:text-base">
              Gestao da clinica em tempo real
            </h2>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <div className="hidden items-center gap-2 rounded-lg border border-stone-200 bg-stone-50 px-3 py-1.5 lg:flex">
          <CalendarDays size={14} className="text-stone-500" />
          <span className="text-xs text-stone-600">{today}</span>
        </div>

        <Badge className="hidden bg-amber-100 text-amber-800 lg:inline-flex">{session?.unit_name ?? "Unidade"}</Badge>

        <div className="relative">
          <button
            type="button"
            className="relative inline-flex h-9 w-9 items-center justify-center rounded-md border border-stone-200 bg-white text-stone-600 transition hover:bg-stone-100"
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
            <div className="absolute right-0 top-11 z-30 w-[320px] rounded-xl border border-stone-200 bg-white p-2 shadow-2xl">
              <div className="flex items-center justify-between px-2 py-1">
                <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Notificacoes</p>
                <span className="text-[11px] text-stone-500">
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
                      className="block rounded-md border border-stone-200 p-2 text-sm transition hover:bg-stone-50"
                      onClick={() => setOpenNotifications(false)}
                    >
                      <p className="font-semibold text-stone-800">{item.title}</p>
                      <p className="text-xs text-stone-600">{item.description}</p>
                    </Link>
                  ))
                ) : (
                  <p className="rounded-md border border-stone-200 p-2 text-xs text-stone-500">
                    Nenhuma notificacao no momento.
                  </p>
                )}
              </div>
            </div>
          ) : null}
        </div>

        <div className="hidden items-center gap-2 rounded-lg border border-stone-200 bg-white px-2 py-1 md:flex">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-stone-200 text-xs font-semibold text-stone-700">
            {initials(session?.full_name)}
          </div>
          <div className="pr-1">
            <p className="text-xs font-semibold text-stone-800">{session?.full_name ?? "Usuario"}</p>
            <p className="text-[11px] text-stone-500">{ROLE_LABELS[session?.roles?.[0] ?? ""] ?? "Perfil"}</p>
          </div>
        </div>

        <Button variant="outline" onClick={onLogout} className="gap-1.5">
          <LogOut size={14} />
          Sair
        </Button>
      </div>
    </header>
  );
}

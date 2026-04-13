"use client";

import { CalendarDays, LogOut, Menu } from "lucide-react";

import { Badge, Button } from "@odontoflux/ui";

import { SessionContext } from "@/hooks/use-session";
import { formatDateBR, initials, ROLE_LABELS } from "@/lib/formatters";

export function Topbar({
  onLogout,
  collapsed,
  onToggleSidebar,
  session,
}: {
  onLogout: () => void;
  collapsed: boolean;
  onToggleSidebar: () => void;
  session?: SessionContext;
}) {
  const today = formatDateBR(new Date());

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-border bg-white/90 px-6 backdrop-blur">
      <div className="flex items-center gap-3">
        <Button variant="outline" className="h-9 w-9 px-0" onClick={onToggleSidebar} title="Alternar menu">
          <Menu size={16} />
        </Button>
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">
            SaaS OdontoFlux {collapsed ? "• Menu compacto" : ""}
          </p>
          <h2 className="text-lg font-semibold">Gestão operacional odontológica</h2>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <div className="hidden items-center gap-2 rounded-lg border border-stone-200 bg-stone-50 px-3 py-1.5 md:flex">
          <CalendarDays size={14} className="text-stone-500" />
          <span className="text-xs text-stone-600">{today}</span>
        </div>
        <Badge className="hidden bg-amber-100 text-amber-800 md:inline-flex">{session?.unit_name ?? "Unidade"}</Badge>
        <div className="hidden items-center gap-2 rounded-lg border border-stone-200 bg-white px-2 py-1 md:flex">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-stone-200 text-xs font-semibold text-stone-700">
            {initials(session?.full_name)}
          </div>
          <div className="pr-1">
            <p className="text-xs font-semibold text-stone-800">{session?.full_name ?? "Usuário"}</p>
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

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Bell,
  Bot,
  CalendarDays,
  ClipboardList,
  CreditCard,
  FileStack,
  FileText,
  Gauge,
  LifeBuoy,
  MessageSquare,
  Rocket,
  Settings,
  Shield,
  Sparkles,
  UploadCloud,
  UserCog,
  Users,
  Building2,
} from "lucide-react";

import { Badge, cn } from "@odontoflux/ui";

import { SessionContext } from "@/hooks/use-session";
import { initials, ROLE_LABELS } from "@/lib/formatters";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: Gauge },
  { href: "/onboarding", label: "Onboarding", icon: Rocket },
  { href: "/conversas", label: "Conversas", icon: MessageSquare },
  { href: "/pacientes", label: "Pacientes", icon: Users },
  { href: "/leads", label: "Leads", icon: Bell },
  { href: "/agenda", label: "Agenda", icon: CalendarDays },
  { href: "/campanhas", label: "Campanhas", icon: ClipboardList },
  { href: "/automacoes", label: "Automações", icon: Bot },
  { href: "/documentos", label: "Documentos", icon: FileStack },
  { href: "/importacao", label: "Importação", icon: UploadCloud },
  { href: "/relatorios", label: "Relatórios", icon: BarChart3 },
  { href: "/faturamento", label: "Faturamento", icon: CreditCard },
  { href: "/suporte", label: "Suporte", icon: LifeBuoy },
  { href: "/usuarios", label: "Usuários", icon: UserCog },
  { href: "/configuracoes", label: "Configurações", icon: Settings },
  { href: "/auditoria", label: "Auditoria", icon: FileText },
  { href: "/admin", label: "Admin Plataforma", icon: Shield, role: "admin_platform" },
];

export function Sidebar({
  collapsed,
  session,
}: {
  collapsed: boolean;
  session?: SessionContext;
}) {
  const pathname = usePathname();
  const currentRole = session?.roles?.[0] ?? "";
  const visibleNav = navItems.filter((item) => !item.role || session?.roles?.includes(item.role));

  return (
    <aside
      className={cn(
        "flex h-screen flex-col border-r border-border bg-white/95 transition-all duration-300",
        collapsed ? "w-[88px]" : "w-72",
      )}
    >
      <div className={cn("border-b border-border px-4 py-4", collapsed ? "text-center" : "px-6 py-5")}>
        <p className="text-xs font-semibold uppercase tracking-wide text-primary">OdontoFlux</p>
        <h1 className={cn("mt-1 text-2xl font-bold", collapsed ? "text-lg" : "text-2xl")}>
          {collapsed ? "OF" : "Operação"}
        </h1>
        {!collapsed ? (
          <div className="mt-3 space-y-2 rounded-lg border border-stone-200 bg-stone-50 p-3">
            <div className="flex items-center gap-2 text-xs text-stone-600">
              <Building2 size={14} />
              <span className="font-semibold">{session?.tenant_name ?? "Clínica atual"}</span>
            </div>
            <p className="text-xs text-stone-500">{session?.unit_name ?? "Unidade principal"}</p>
          </div>
        ) : null}
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto p-3">
        {visibleNav.map((item) => {
          const active = pathname === item.href;
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              className={cn(
                "group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition",
                collapsed && "justify-center px-2",
                active
                  ? "bg-gradient-to-r from-primary to-teal-600 text-primary-foreground shadow-sm"
                  : "text-stone-700 hover:bg-stone-100",
              )}
            >
              <Icon size={17} />
              {!collapsed ? (
                <span className="truncate">
                  {item.label}
                  {item.href === "/admin" ? (
                    <Badge className="ml-2 bg-stone-200 text-stone-700">Restrito</Badge>
                  ) : null}
                </span>
              ) : null}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-border p-3">
        {collapsed ? (
          <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-stone-200 text-xs font-semibold text-stone-700">
            {initials(session?.full_name)}
          </div>
        ) : (
          <div className="rounded-xl border border-stone-200 bg-stone-50 p-3">
            <div className="flex items-center gap-2">
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-stone-200 text-xs font-semibold text-stone-700">
                {initials(session?.full_name)}
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-stone-800">{session?.full_name ?? "Usuário"}</p>
                <p className="truncate text-xs text-stone-500">{ROLE_LABELS[currentRole] ?? "Perfil"}</p>
              </div>
            </div>
            <div className="mt-2 inline-flex items-center gap-1 text-xs text-stone-500">
              <Sparkles size={12} />
              Ambiente de demonstração
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}

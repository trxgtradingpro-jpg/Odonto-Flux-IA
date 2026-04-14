"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ComponentType } from "react";
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

import { BrandingTheme } from "@/hooks/use-branding";
import { useLiveNotifications } from "@/hooks/use-live-notifications";
import { SessionContext } from "@/hooks/use-session";
import { initials, ROLE_LABELS } from "@/lib/formatters";

type NavItem = {
  href: string;
  label: string;
  icon: ComponentType<{ size?: number; className?: string }>;
  role?: string;
  badgeKey?: "conversations" | "leads" | "appointmentsToday" | "pendingConfirmations";
};

const navGroups: Array<{ title: string; items: NavItem[] }> = [
  {
    title: "Operacao",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: Gauge },
      { href: "/onboarding", label: "Onboarding", icon: Rocket },
      { href: "/conversas", label: "Conversas", icon: MessageSquare, badgeKey: "conversations" },
      { href: "/agenda", label: "Agenda", icon: CalendarDays, badgeKey: "pendingConfirmations" },
      { href: "/pacientes", label: "Pacientes", icon: Users },
      { href: "/leads", label: "Leads", icon: Bell, badgeKey: "leads" },
    ],
  },
  {
    title: "Crescimento",
    items: [
      { href: "/campanhas", label: "Campanhas", icon: ClipboardList },
      { href: "/automacoes", label: "Automacoes", icon: Bot },
      { href: "/documentos", label: "Documentos", icon: FileStack },
      { href: "/importacao", label: "Importacao", icon: UploadCloud },
      { href: "/relatorios", label: "Relatorios", icon: BarChart3 },
    ],
  },
  {
    title: "Administracao",
    items: [
      { href: "/faturamento", label: "Faturamento", icon: CreditCard },
      { href: "/suporte", label: "Suporte", icon: LifeBuoy },
      { href: "/usuarios", label: "Usuarios", icon: UserCog },
      { href: "/configuracoes", label: "Configuracoes", icon: Settings },
      { href: "/auditoria", label: "Auditoria", icon: FileText },
      { href: "/admin", label: "Admin Plataforma", icon: Shield, role: "admin_platform" },
    ],
  },
];

function NavGroupSection({
  title,
  items,
  collapsed,
  pathname,
  badges,
  roles,
}: {
  title: string;
  items: NavItem[];
  collapsed: boolean;
  pathname: string;
  badges: Record<string, number>;
  roles: string[];
}) {
  return (
    <div className="space-y-1">
      {!collapsed ? (
        <p className="px-2 text-[11px] font-semibold uppercase tracking-wide text-stone-500">{title}</p>
      ) : null}
      {items
        .filter((item) => !item.role || roles.includes(item.role))
        .map((item) => {
          const active = pathname === item.href;
          const Icon = item.icon;
          const badgeValue = item.badgeKey ? badges[item.badgeKey] ?? 0 : 0;
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              className={cn(
                "group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition",
                collapsed && "justify-center px-2",
                active
                  ? "bg-gradient-to-r text-white shadow-sm"
                  : "text-stone-700 hover:bg-stone-100",
              )}
              style={
                active
                  ? {
                      backgroundImage:
                        "linear-gradient(90deg, var(--tenant-primary), color-mix(in srgb, var(--tenant-secondary) 70%, white 30%))",
                    }
                  : undefined
              }
            >
              <Icon size={17} />
              {!collapsed ? (
                <span className="flex min-w-0 flex-1 items-center justify-between gap-2">
                  <span className="truncate">{item.label}</span>
                  {badgeValue > 0 ? (
                    <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold text-white">
                      {badgeValue > 99 ? "99+" : badgeValue}
                    </span>
                  ) : null}
                  {item.href === "/admin" ? (
                    <Badge className="ml-1 bg-stone-200 text-stone-700">Restrito</Badge>
                  ) : null}
                </span>
              ) : badgeValue > 0 ? (
                <span className="absolute ml-7 mt-[-18px] inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold text-white">
                  {badgeValue > 99 ? "99+" : badgeValue}
                </span>
              ) : null}
            </Link>
          );
        })}
    </div>
  );
}

export function Sidebar({
  collapsed,
  session,
  branding,
}: {
  collapsed: boolean;
  session?: SessionContext;
  branding?: BrandingTheme;
}) {
  const pathname = usePathname();
  const currentRole = session?.roles?.[0] ?? "";
  const notificationsQuery = useLiveNotifications();
  const badges = notificationsQuery.data?.badges ?? {
    conversations: 0,
    leads: 0,
    appointmentsToday: 0,
    pendingConfirmations: 0,
  };
  const roles = session?.roles ?? [];

  return (
    <aside
      className={cn(
        "flex h-screen flex-col border-r border-border bg-white/95 transition-all duration-300",
        collapsed ? "w-[88px]" : "w-[286px]",
      )}
    >
      <div className={cn("border-b border-border", collapsed ? "px-3 py-4 text-center" : "px-5 py-5")}>
        <div className={cn("flex items-center gap-2", collapsed ? "justify-center" : "justify-start")}>
          {branding?.logoDataUrl ? (
            <img src={branding.logoDataUrl} alt="Logo" className="h-9 w-9 rounded-md object-cover" />
          ) : (
            <div
              className="flex h-9 w-9 items-center justify-center rounded-md text-xs font-bold text-white"
              style={{ backgroundColor: "var(--tenant-primary)" }}
            >
              OF
            </div>
          )}
          {!collapsed ? (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">OdontoFlux</p>
              <h1 className="text-lg font-bold text-stone-900">{branding?.clinicName ?? "Clinica"}</h1>
            </div>
          ) : null}
        </div>

        {!collapsed ? (
          <div className="mt-3 space-y-2 rounded-lg border border-stone-200 bg-stone-50 p-3">
            <div className="flex items-center gap-2 text-xs text-stone-600">
              <Building2 size={14} />
              <span className="font-semibold">{session?.tenant_name ?? "Clinica atual"}</span>
            </div>
            <p className="text-xs text-stone-500">{session?.unit_name ?? "Unidade principal"}</p>
          </div>
        ) : null}
      </div>

      <nav className="flex-1 space-y-4 overflow-y-auto p-3">
        {navGroups.map((group) => (
          <NavGroupSection
            key={group.title}
            title={group.title}
            items={group.items}
            collapsed={collapsed}
            pathname={pathname}
            badges={badges}
            roles={roles}
          />
        ))}
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
                <p className="truncate text-sm font-semibold text-stone-800">{session?.full_name ?? "Usuario"}</p>
                <p className="truncate text-xs text-stone-500">{ROLE_LABELS[currentRole] ?? "Perfil"}</p>
              </div>
            </div>
            <div className="mt-2 inline-flex items-center gap-1 text-xs text-stone-500">
              <Sparkles size={12} />
              Atualizacao automatica ativa
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}

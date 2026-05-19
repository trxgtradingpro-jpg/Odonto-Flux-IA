"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { ComponentType } from "react";
import {
  AlertTriangle,
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
  ListChecks,
  MessageSquare,
  Rocket,
  Settings,
  Shield,
  Sparkles,
  Stethoscope,
  UploadCloud,
  UserCog,
  Users,
  X,
  Building2,
  Database,
} from "lucide-react";

import { Badge, cn } from "@odontoflux/ui";

import { BrandingTheme } from "@/hooks/use-branding";
import { useLiveNotifications } from "@/hooks/use-live-notifications";
import { useOwnerUnitScope } from "@/hooks/use-owner-unit-scope";
import { SessionContext } from "@/hooks/use-session";
import { BRAND_PLATFORM_LABEL } from "@/lib/brand";
import { clinicInitials, initials, ROLE_LABELS } from "@/lib/formatters";
import { PageKey } from "@/lib/page-access";

type NavItem = {
  key: PageKey;
  href: string;
  label: string;
  icon: ComponentType<{ size?: string | number; className?: string }>;
  role?: string;
  badgeKey?: "conversations" | "leads" | "appointmentsToday" | "pendingConfirmations";
};

const navGroups: Array<{ title: string; items: NavItem[] }> = [
  {
    title: "Operacao",
    items: [
      { key: "dashboard", href: "/dashboard", label: "Dashboard", icon: Gauge },
      { key: "operacoes", href: "/operacoes", label: "Operacoes", icon: AlertTriangle },
      { key: "onboarding", href: "/onboarding", label: "Onboarding", icon: Rocket },
      { key: "conversas", href: "/conversas", label: "WhatsApp", icon: MessageSquare, badgeKey: "conversations" },
      { key: "agenda", href: "/agenda", label: "Agenda", icon: CalendarDays, badgeKey: "pendingConfirmations" },
      { key: "equipe-medica", href: "/equipe-medica", label: "Equipe medica", icon: Stethoscope },
      { key: "servicos", href: "/servicos", label: "Servicos", icon: ListChecks },
      { key: "unidades", href: "/unidades", label: "Unidades", icon: Building2 },
      { key: "pacientes", href: "/pacientes", label: "Pacientes", icon: Users },
      { key: "leads", href: "/leads", label: "Leads", icon: Bell, badgeKey: "leads" },
    ],
  },
  {
    title: "Crescimento",
    items: [
      { key: "campanhas", href: "/campanhas", label: "Campanhas", icon: ClipboardList },
      { key: "automacoes", href: "/automacoes", label: "Automacoes", icon: Bot },
      { key: "ia-lab", href: "/ia-lab", label: "IA Lab", icon: Sparkles },
      { key: "documentos", href: "/documentos", label: "Documentos", icon: FileStack },
      { key: "importacao", href: "/importacao", label: "Importacao", icon: UploadCloud },
      { key: "relatorios", href: "/relatorios", label: "Relatorios", icon: BarChart3 },
    ],
  },
  {
    title: "Administracao",
    items: [
      { key: "faturamento", href: "/faturamento", label: "Faturamento", icon: CreditCard },
      { key: "backup", href: "/backup", label: "Backup", icon: Database },
      { key: "suporte", href: "/suporte", label: "Suporte", icon: LifeBuoy },
      { key: "usuarios", href: "/usuarios", label: "Usuarios", icon: UserCog },
      { key: "configuracoes", href: "/configuracoes", label: "Configuracoes", icon: Settings },
      { key: "auditoria", href: "/auditoria", label: "Auditoria", icon: FileText },
      { key: "admin", href: "/admin", label: "Admin Plataforma", icon: Shield, role: "admin_platform" },
    ],
  },
];

function NavGroupSection({
  title,
  items,
  collapsed,
  mobileOpen,
  onCloseMobile,
  pathname,
  badges,
  roles,
  allowedPageKeys,
}: {
  title: string;
  items: NavItem[];
  collapsed: boolean;
  mobileOpen: boolean;
  onCloseMobile?: () => void;
  pathname: string;
  badges: Record<string, number>;
  roles: string[];
  allowedPageKeys: PageKey[];
}) {
  return (
    <div className="space-y-1">
      {!collapsed ? (
        <p className="px-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{title}</p>
      ) : null}
      {items
        .filter((item) => (!item.role || roles.includes(item.role)) && allowedPageKeys.includes(item.key))
        .map((item) => {
          const active = pathname === item.href;
          const Icon = item.icon;
          const badgeValue = item.badgeKey ? badges[item.badgeKey] ?? 0 : 0;
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              onClick={() => {
                if (mobileOpen) onCloseMobile?.();
              }}
              className={cn(
                "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition",
                collapsed && "justify-center px-2",
                active
                  ? "bg-gradient-to-r text-white shadow-sm"
                  : "text-foreground hover:bg-muted/75",
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
                    <Badge className="ml-1">Restrito</Badge>
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
  autoHide,
  mobileOpen,
  onCloseMobile,
  session,
  branding,
  allowedPageKeys,
}: {
  collapsed: boolean;
  autoHide?: boolean;
  mobileOpen: boolean;
  onCloseMobile?: () => void;
  session?: SessionContext;
  branding?: BrandingTheme;
  allowedPageKeys: PageKey[];
}) {
  const ownerUnitScope = useOwnerUnitScope();
  const pathname = usePathname();
  const currentRole = session?.roles?.[0] ?? "";
  const useCollapsed = collapsed && !mobileOpen;
  const notificationsQuery = useLiveNotifications();
  const badges = notificationsQuery.data?.badges ?? {
    conversations: 0,
    leads: 0,
    appointmentsToday: 0,
    pendingConfirmations: 0,
  };
  const roles = session?.roles ?? [];
  const clinicDisplayName = session?.tenant_name ?? branding?.clinicName ?? "Clinica";
  const activeUnitLabel = ownerUnitScope.canSwitchUnits
    ? ownerUnitScope.selectedUnitName || "Todas as unidades"
    : session?.unit_name ?? "Unidade principal";

  return (
    <>
      {mobileOpen ? (
        <button
          type="button"
          aria-label="Fechar menu"
          onClick={onCloseMobile}
          className="fixed inset-0 z-30 bg-black/40 lg:hidden"
        />
      ) : null}

      <aside
        data-app-shell-sidebar="true"
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex h-dvh max-w-[84vw] shrink-0 flex-col overflow-y-auto overflow-x-hidden overscroll-contain border-r border-border bg-card transition-[width,transform,opacity,border-color,box-shadow] duration-700 ease-in-out [scrollbar-gutter:stable]",
          "w-[286px] -translate-x-full shadow-none",
          mobileOpen && "translate-x-0 shadow-2xl",
          "lg:sticky lg:top-0 lg:z-auto lg:max-w-none lg:translate-x-0 lg:shadow-none",
          autoHide
            ? "lg:w-0 lg:min-w-0 lg:-translate-x-6 lg:border-r-transparent lg:opacity-0 lg:pointer-events-none"
            : useCollapsed
              ? "lg:w-[88px]"
              : "lg:w-[286px]",
        )}
      >
      <div
        className={cn(
          "flex min-h-full flex-col transition-[opacity,transform,filter] duration-700 ease-in-out",
          autoHide && "lg:-translate-x-6 lg:scale-[0.98] lg:opacity-0 lg:blur-[1px]",
        )}
      >
      <div className={cn("shrink-0 border-b border-border", useCollapsed ? "px-3 py-4 text-center" : "px-5 py-5")}>
        <div className={cn("flex items-center gap-2", useCollapsed ? "justify-center" : "justify-between")}>
          <div className={cn("flex items-center gap-2", useCollapsed ? "justify-center" : "justify-start")}>
            {branding?.logoDataUrl ? (
              <Image
                src={branding.logoDataUrl}
                alt="Logo"
                width={36}
                height={36}
                unoptimized
                className="h-9 w-9 rounded-md object-cover"
              />
            ) : (
              <div
                className="flex h-9 w-9 items-center justify-center rounded-md text-xs font-bold text-white"
                style={{ backgroundColor: "var(--tenant-primary)" }}
              >
                {clinicInitials(clinicDisplayName)}
              </div>
            )}
            {!useCollapsed ? (
              <div>
                <h1 className="text-lg font-bold text-foreground">{clinicDisplayName}</h1>
                <p className="text-xs text-muted-foreground">{BRAND_PLATFORM_LABEL}</p>
              </div>
            ) : null}
          </div>
          <button
            type="button"
            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border text-muted-foreground lg:hidden"
            onClick={onCloseMobile}
            aria-label="Fechar barra lateral"
          >
            <X size={14} />
          </button>
        </div>

        {!useCollapsed ? (
          <div className="mt-3 space-y-2 rounded-lg border border-border bg-muted p-3">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Building2 size={14} />
              <span className="font-semibold">Unidade ativa</span>
            </div>
            <p className="text-sm font-semibold text-foreground">{activeUnitLabel}</p>
            <p className="text-xs text-muted-foreground">
              {ownerUnitScope.canSwitchUnits
                ? "Troque a unidade no seletor do topo quando precisar."
                : "Escopo fixado conforme o perfil deste usuario."}
            </p>
          </div>
        ) : null}
      </div>

      <nav className="flex-1 space-y-4 p-3">
        {navGroups.map((group) => (
          <NavGroupSection
            key={group.title}
            title={group.title}
            items={group.items}
            collapsed={useCollapsed}
            mobileOpen={mobileOpen}
            onCloseMobile={onCloseMobile}
            pathname={pathname}
            badges={badges}
            roles={roles}
            allowedPageKeys={allowedPageKeys}
          />
        ))}
      </nav>

      <div className="shrink-0 border-t border-border p-3">
        {useCollapsed ? (
          <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-muted text-xs font-semibold text-foreground">
            {initials(session?.full_name)}
          </div>
        ) : (
          <div className="rounded-xl border border-border bg-muted p-3">
            <div className="flex items-center gap-2">
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-muted text-xs font-semibold text-foreground">
                {initials(session?.full_name)}
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-foreground">{session?.full_name ?? "Usuario"}</p>
                <p className="truncate text-xs text-muted-foreground">{ROLE_LABELS[currentRole] ?? "Perfil"}</p>
              </div>
            </div>
            <div className="mt-2 inline-flex items-center gap-1 text-xs text-muted-foreground">
              <Sparkles size={12} />
              Atualizacao automatica ativa
            </div>
          </div>
        )}
      </div>
      </div>
      </aside>
    </>
  );
}

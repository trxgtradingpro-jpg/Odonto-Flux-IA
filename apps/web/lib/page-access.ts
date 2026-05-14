export type PageAction = "view" | "create" | "edit" | "delete";

export type PagePermissionFlags = {
  view: boolean;
  create: boolean;
  edit: boolean;
  delete: boolean;
};

export type PageKey =
  | "dashboard"
  | "operacoes"
  | "onboarding"
  | "conversas"
  | "agenda"
  | "equipe-medica"
  | "servicos"
  | "unidades"
  | "pacientes"
  | "leads"
  | "campanhas"
  | "automacoes"
  | "ia-lab"
  | "documentos"
  | "importacao"
  | "relatorios"
  | "faturamento"
  | "backup"
  | "suporte"
  | "usuarios"
  | "configuracoes"
  | "auditoria"
  | "admin";

export type PagePermissionMap = Record<PageKey, PagePermissionFlags>;

export type ManagedPageDefinition = {
  key: PageKey;
  href: string;
  label: string;
  menuGroup: "principal" | "menu";
};

const EMPTY_FLAGS: PagePermissionFlags = {
  view: false,
  create: false,
  edit: false,
  delete: false,
};

export const MANAGED_PAGES: ManagedPageDefinition[] = [
  { key: "dashboard", href: "/dashboard", label: "Dashboard", menuGroup: "menu" },
  { key: "operacoes", href: "/operacoes", label: "Operacoes", menuGroup: "menu" },
  { key: "onboarding", href: "/onboarding", label: "Onboarding", menuGroup: "menu" },
  { key: "conversas", href: "/conversas", label: "WhatsApp", menuGroup: "principal" },
  { key: "agenda", href: "/agenda", label: "Agenda", menuGroup: "principal" },
  { key: "equipe-medica", href: "/equipe-medica", label: "Equipe medica", menuGroup: "menu" },
  { key: "servicos", href: "/servicos", label: "Servicos", menuGroup: "menu" },
  { key: "unidades", href: "/unidades", label: "Unidades", menuGroup: "menu" },
  { key: "pacientes", href: "/pacientes", label: "Pacientes", menuGroup: "principal" },
  { key: "leads", href: "/leads", label: "Leads", menuGroup: "menu" },
  { key: "campanhas", href: "/campanhas", label: "Campanhas", menuGroup: "menu" },
  { key: "automacoes", href: "/automacoes", label: "Automacoes", menuGroup: "menu" },
  { key: "ia-lab", href: "/ia-lab", label: "IA Lab", menuGroup: "menu" },
  { key: "documentos", href: "/documentos", label: "Documentos", menuGroup: "menu" },
  { key: "importacao", href: "/importacao", label: "Importacao", menuGroup: "menu" },
  { key: "relatorios", href: "/relatorios", label: "Relatorios", menuGroup: "menu" },
  { key: "faturamento", href: "/faturamento", label: "Faturamento", menuGroup: "menu" },
  { key: "backup", href: "/backup", label: "Backup", menuGroup: "menu" },
  { key: "suporte", href: "/suporte", label: "Suporte", menuGroup: "menu" },
  { key: "usuarios", href: "/usuarios", label: "Usuarios", menuGroup: "menu" },
  { key: "configuracoes", href: "/configuracoes", label: "Configuracoes", menuGroup: "menu" },
  { key: "auditoria", href: "/auditoria", label: "Auditoria", menuGroup: "menu" },
  { key: "admin", href: "/admin", label: "Admin Plataforma", menuGroup: "menu" },
];

export const PRIMARY_PAGE_KEYS: PageKey[] = ["conversas", "agenda", "pacientes"];

function cloneFlags(source?: Partial<PagePermissionFlags> | null): PagePermissionFlags {
  return {
    view: Boolean(source?.view),
    create: Boolean(source?.create),
    edit: Boolean(source?.edit),
    delete: Boolean(source?.delete),
  };
}

function withFlags(keys: PageKey[], flags: Partial<PagePermissionFlags>): PagePermissionMap {
  const base = createEmptyPagePermissionMap();
  keys.forEach((key) => {
    base[key] = {
      view: flags.view ?? false,
      create: flags.create ?? false,
      edit: flags.edit ?? false,
      delete: flags.delete ?? false,
    };
  });
  return base;
}

export function createEmptyPagePermissionMap(): PagePermissionMap {
  return MANAGED_PAGES.reduce((acc, page) => {
    acc[page.key] = { ...EMPTY_FLAGS };
    return acc;
  }, {} as PagePermissionMap);
}

export function buildDefaultPagePermissionsForRole(role: string): PagePermissionMap {
  if (role === "owner") {
    return withFlags(
      MANAGED_PAGES.map((page) => page.key),
      { view: true, create: true, edit: true, delete: true },
    );
  }

  if (role === "admin_platform") {
    return withFlags(["admin"], { view: true, create: true, edit: true, delete: true });
  }

  if (role === "manager") {
    return withFlags(
      [
        "dashboard",
        "operacoes",
        "onboarding",
        "conversas",
        "agenda",
        "equipe-medica",
        "servicos",
        "unidades",
        "pacientes",
        "leads",
        "campanhas",
        "automacoes",
        "ia-lab",
        "documentos",
        "importacao",
        "relatorios",
        "backup",
        "suporte",
      ],
      { view: true, create: true, edit: true, delete: true },
    );
  }

  if (role === "receptionist") {
    const map = createEmptyPagePermissionMap();
    ([
      "conversas",
      "agenda",
      "pacientes",
      "documentos",
      "leads",
      "suporte",
    ] as PageKey[]).forEach((key) => {
      map[key] = { view: true, create: true, edit: true, delete: false };
    });
    return map;
  }

  if (role === "analyst") {
    const map = createEmptyPagePermissionMap();
    (["dashboard", "relatorios", "auditoria", "documentos"] as PageKey[]).forEach((key) => {
      map[key] = { view: true, create: false, edit: false, delete: false };
    });
    return map;
  }

  return createEmptyPagePermissionMap();
}

export function normalizePagePermissions(
  rawPermissions: Record<string, Partial<PagePermissionFlags>> | null | undefined,
  roles: string[] | null | undefined,
): PagePermissionMap {
  const combined = createEmptyPagePermissionMap();
  (roles ?? []).forEach((role) => {
    const defaults = buildDefaultPagePermissionsForRole(role);
    MANAGED_PAGES.forEach((page) => {
      combined[page.key] = {
        view: combined[page.key].view || defaults[page.key].view,
        create: combined[page.key].create || defaults[page.key].create,
        edit: combined[page.key].edit || defaults[page.key].edit,
        delete: combined[page.key].delete || defaults[page.key].delete,
      };
    });
  });

  MANAGED_PAGES.forEach((page) => {
    const rawPage = rawPermissions?.[page.key];
    if (!rawPage) return;
    combined[page.key] = cloneFlags(rawPage);
  });

  return combined;
}

export function canAccessPage(
  permissions: PagePermissionMap | null | undefined,
  pageKey: PageKey,
  action: PageAction = "view",
): boolean {
  if (!permissions) return false;
  return Boolean(permissions[pageKey]?.[action]);
}

export function getAccessiblePages(permissions: PagePermissionMap | null | undefined): ManagedPageDefinition[] {
  if (!permissions) return [];
  return MANAGED_PAGES.filter((page) => permissions[page.key]?.view);
}

export function findManagedPageByPathname(pathname: string): ManagedPageDefinition | null {
  const cleanPath = pathname.split("?")[0];
  return MANAGED_PAGES.find((page) => cleanPath === page.href || cleanPath.startsWith(`${page.href}/`)) ?? null;
}

export function getFirstAccessiblePageHref(permissions: PagePermissionMap | null | undefined): string {
  const first = getAccessiblePages(permissions)[0];
  return first?.href ?? "/dashboard";
}

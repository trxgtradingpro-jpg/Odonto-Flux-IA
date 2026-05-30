export type AdmAction = "view" | "create" | "edit" | "delete";

export type AdmPagePermissionFlags = {
  view: boolean;
  create: boolean;
  edit: boolean;
  delete: boolean;
};

export type AdmPageKey =
  | "adm_crm"
  | "adm_messages"
  | "adm_site_templates"
  | "adm_outreach_automation"
  | "adm_import_places"
  | "adm_whatsapp"
  | "adm_whatsapp_settings"
  | "adm_agent_settings"
  | "adm_implementations"
  | "adm_affiliates";

export type AdmPagePermissionMap = Record<AdmPageKey, AdmPagePermissionFlags>;

export type AdmManagedPageDefinition = {
  key: AdmPageKey;
  href: string;
  label: string;
  description: string;
};

const EMPTY_FLAGS: AdmPagePermissionFlags = {
  view: false,
  create: false,
  edit: false,
  delete: false,
};

export const ADM_MANAGED_PAGES: AdmManagedPageDefinition[] = [
  {
    key: "adm_crm",
    href: "/adm",
    label: "CRM comercial",
    description: "Prospects, demos, follow-up e status comerciais.",
  },
  {
    key: "adm_messages",
    href: "/adm/mensagens-para-clinicas",
    label: "Mensagens prontas",
    description: "Biblioteca de templates e mensagens para clinicas.",
  },
  {
    key: "adm_site_templates",
    href: "/adm/modelos-sites",
    label: "Modelos de sites",
    description: "Studio de templates, catalogo publico e selecao por prospect.",
  },
  {
    key: "adm_outreach_automation",
    href: "/adm/automacao-comercial",
    label: "Automacao comercial",
    description: "Controle de lotes automaticos de outreach comercial.",
  },
  {
    key: "adm_import_places",
    href: "/adm/importar-clinicas",
    label: "Importar Google Places",
    description: "Busca e cadastro automatico de prospects pelo Google Places.",
  },
  {
    key: "adm_whatsapp",
    href: "/adm",
    label: "WhatsApp do /adm",
    description: "Leitura das conversas comerciais e demos vinculadas.",
  },
  {
    key: "adm_whatsapp_settings",
    href: "/adm",
    label: "WhatsApp do sistema",
    description: "Configuracao dos numeros oficiais da plataforma.",
  },
  {
    key: "adm_agent_settings",
    href: "/adm/configuracoes",
    label: "Configuracoes do agente",
    description: "Fluxo de conversa, modelo e guardrails do agente de agenda.",
  },
  {
    key: "adm_implementations",
    href: "/adm/implementacoes",
    label: "Implementacoes",
    description: "Controle de funcionalidades entregues e rollouts.",
  },
  {
    key: "adm_affiliates",
    href: "/adm/afiliados",
    label: "Afiliados",
    description: "Cadastro e permissoes dos usuarios afiliados.",
  },
];

export const ADM_ACTION_LABELS: Record<AdmAction, string> = {
  view: "Ver",
  create: "Adicionar",
  edit: "Editar",
  delete: "Excluir",
};

export const ADM_FULL_ACCESS_ROLES = ["admin_platform", "sales_admin"];
export const ADM_AFFILIATE_ROLE = "sales_affiliate";

export const DEFAULT_AFFILIATE_ADM_PERMISSIONS: Partial<AdmPagePermissionMap> = {
  adm_crm: { view: true, create: true, edit: true, delete: false },
  adm_messages: { view: true, create: true, edit: true, delete: false },
  adm_site_templates: { view: true, create: true, edit: true, delete: false },
  adm_outreach_automation: { view: true, create: false, edit: false, delete: false },
};

function cloneFlags(source?: Partial<AdmPagePermissionFlags> | null): AdmPagePermissionFlags {
  return {
    view: Boolean(source?.view),
    create: Boolean(source?.create),
    edit: Boolean(source?.edit),
    delete: Boolean(source?.delete),
  };
}

export function createEmptyAdmPagePermissionMap(): AdmPagePermissionMap {
  return ADM_MANAGED_PAGES.reduce((acc, page) => {
    acc[page.key] = { ...EMPTY_FLAGS };
    return acc;
  }, {} as AdmPagePermissionMap);
}

function createFullAdmPagePermissionMap(): AdmPagePermissionMap {
  return ADM_MANAGED_PAGES.reduce((acc, page) => {
    acc[page.key] = { view: true, create: true, edit: true, delete: true };
    return acc;
  }, {} as AdmPagePermissionMap);
}

export function normalizeAdmPagePermissions(
  rawPermissions: Record<string, Partial<AdmPagePermissionFlags>> | null | undefined,
  roles: string[] | null | undefined,
): AdmPagePermissionMap {
  if ((roles ?? []).some((role) => ADM_FULL_ACCESS_ROLES.includes(role))) {
    return createFullAdmPagePermissionMap();
  }

  const combined = createEmptyAdmPagePermissionMap();
  if ((roles ?? []).includes(ADM_AFFILIATE_ROLE)) {
    Object.entries(DEFAULT_AFFILIATE_ADM_PERMISSIONS).forEach(([pageKey, flags]) => {
      combined[pageKey as AdmPageKey] = cloneFlags(flags);
    });
  }
  if ((roles ?? []).includes("sales_viewer")) {
    (["adm_crm", "adm_messages", "adm_site_templates", "adm_outreach_automation", "adm_whatsapp"] as AdmPageKey[]).forEach((pageKey) => {
      combined[pageKey] = { view: true, create: false, edit: false, delete: false };
    });
  }

  ADM_MANAGED_PAGES.forEach((page) => {
    const rawPage = rawPermissions?.[page.key];
    if (!rawPage) return;
    combined[page.key] = cloneFlags(rawPage);
  });
  return combined;
}

export function canAccessAdmPage(
  permissions: AdmPagePermissionMap | null | undefined,
  pageKey: AdmPageKey,
  action: AdmAction = "view",
): boolean {
  return Boolean(permissions?.[pageKey]?.[action]);
}

export function isAdmFullAccess(roles: string[] | null | undefined): boolean {
  return Boolean((roles ?? []).some((role) => ADM_FULL_ACCESS_ROLES.includes(role)));
}

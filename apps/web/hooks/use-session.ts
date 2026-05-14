"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { normalizePagePermissions, PagePermissionMap } from "@/lib/page-access";

type SessionResponse = {
  id: string;
  email: string;
  full_name: string;
  tenant_id: string | null;
  unit_id?: string | null;
  unit_name?: string | null;
  tenant_trade_name?: string | null;
  tenant_timezone?: string | null;
  roles: string[];
  permissions: string[];
  page_permissions?: Record<string, unknown> | null;
  force_fullscreen_mode?: boolean;
};

type UnitResponse = {
  id: string;
  name: string;
};

type SettingResponse = {
  key: string;
  value: unknown;
};

export type SessionContext = SessionResponse & {
  tenant_name: string;
  assigned_unit_id: string | null;
  unit_name: string;
  resolved_page_permissions: PagePermissionMap;
};

function parseSettingText(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (value && typeof value === "object" && "name" in value) {
    const named = value as { name?: unknown };
    if (typeof named.name === "string") return named.name;
  }
  if (value && typeof value === "object") {
    const clinicProfile = value as {
      clinic_name?: unknown;
      display_name?: unknown;
      trade_name?: unknown;
    };
    if (typeof clinicProfile.clinic_name === "string") return clinicProfile.clinic_name;
    if (typeof clinicProfile.display_name === "string") return clinicProfile.display_name;
    if (typeof clinicProfile.trade_name === "string") return clinicProfile.trade_name;
  }
  return null;
}

export function useSession() {
  return useQuery<SessionContext>({
    queryKey: ["session-context"],
    queryFn: async () => {
      const meResponse = await api.get<SessionResponse>("/auth/me");
      const me = meResponse.data;

      // Perfil de plataforma pode nao estar vinculado a tenant; evita chamadas que retornam 400.
      if (!me.tenant_id) {
        return {
          ...me,
          assigned_unit_id: null,
          tenant_name: me.tenant_trade_name ?? "Plataforma OdontoFlux",
          unit_name: "Visao global",
          resolved_page_permissions: normalizePagePermissions(
            me.page_permissions as Record<string, { view?: boolean; create?: boolean; edit?: boolean; delete?: boolean }> | null | undefined,
            me.roles,
          ),
        };
      }

      const [unitsResponse, settingsResponse] = await Promise.allSettled([
        api.get<{ data: UnitResponse[] }>("/units", { params: { limit: 100, offset: 0 } }),
        api.get<{ data: SettingResponse[] }>("/settings"),
      ]);

      const units = unitsResponse.status === "fulfilled" ? (unitsResponse.value.data.data ?? []) : [];
      const settings = settingsResponse.status === "fulfilled" ? (settingsResponse.value.data.data ?? []) : [];

      const clinicSetting = settings.find((item) =>
        ["clinic.display_name", "clinic.name", "clinic.trade_name", "clinic.profile"].includes(item.key),
      );

      const tenantName = me.tenant_trade_name ?? parseSettingText(clinicSetting?.value) ?? "Clinica atual";
      const assignedUnit = me.unit_id ? units.find((item) => item.id === me.unit_id) : undefined;
      const fallbackUnit = units[0];
      const effectiveUnit = assignedUnit ?? fallbackUnit;

      return {
        ...me,
        unit_id: effectiveUnit?.id ?? me.unit_id ?? null,
        assigned_unit_id: me.unit_id ?? null,
        tenant_name: tenantName,
        unit_name: me.unit_name ?? assignedUnit?.name ?? effectiveUnit?.name ?? "Unidade principal",
        resolved_page_permissions: normalizePagePermissions(
          me.page_permissions as Record<string, { view?: boolean; create?: boolean; edit?: boolean; delete?: boolean }> | null | undefined,
          me.roles,
        ),
      };
    },
    staleTime: 60_000,
  });
}

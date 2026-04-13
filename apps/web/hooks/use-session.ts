"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

type SessionResponse = {
  id: string;
  email: string;
  full_name: string;
  tenant_id: string | null;
  tenant_trade_name?: string | null;
  tenant_timezone?: string | null;
  roles: string[];
  permissions: string[];
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
  unit_name: string;
};

function parseSettingText(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (value && typeof value === "object" && "name" in value) {
    const named = value as { name?: unknown };
    if (typeof named.name === "string") return named.name;
  }
  return null;
}

export function useSession() {
  return useQuery<SessionContext>({
    queryKey: ["session-context"],
    queryFn: async () => {
      const meResponse = await api.get<SessionResponse>("/auth/me");
      const me = meResponse.data;

      // Perfil de plataforma pode não estar vinculado a tenant; evita chamadas que retornam 400.
      if (!me.tenant_id) {
        return {
          ...me,
          tenant_name: me.tenant_trade_name ?? "Plataforma OdontoFlux",
          unit_name: "Visão global",
        };
      }

      const [unitsResponse, settingsResponse] = await Promise.allSettled([
        api.get<{ data: UnitResponse[] }>("/units", { params: { limit: 5, offset: 0 } }),
        api.get<{ data: SettingResponse[] }>("/settings"),
      ]);

      const units =
        unitsResponse.status === "fulfilled" ? (unitsResponse.value.data.data ?? []) : [];
      const settings =
        settingsResponse.status === "fulfilled" ? (settingsResponse.value.data.data ?? []) : [];

      const clinicSetting = settings.find((item) =>
        ["clinic.display_name", "clinic.name", "clinic.trade_name"].includes(item.key),
      );

      const tenantName =
        me.tenant_trade_name ?? parseSettingText(clinicSetting?.value) ?? "Clínica atual";
      const unitName = units[0]?.name ?? "Unidade principal";

      return {
        ...me,
        tenant_name: tenantName,
        unit_name: unitName,
      };
    },
    staleTime: 60_000,
  });
}

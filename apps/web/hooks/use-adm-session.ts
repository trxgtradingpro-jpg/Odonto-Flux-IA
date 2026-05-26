"use client";

import { useQuery } from "@tanstack/react-query";

import {
  AdmPagePermissionMap,
  normalizeAdmPagePermissions,
} from "@/lib/adm-page-access";
import { api } from "@/lib/api";

export type AdmSession = {
  id: string;
  email: string;
  full_name: string;
  phone?: string | null;
  roles: string[];
  is_active: boolean;
  force_password_change: boolean;
  page_permissions?: Record<string, unknown> | null;
  adm_page_permissions?: AdmPagePermissionMap | null;
  is_affiliate: boolean;
  last_login_at?: string | null;
  created_at: string;
  updated_at: string;
  resolved_adm_page_permissions: AdmPagePermissionMap;
};

export function useAdmSession(enabled: boolean) {
  return useQuery<AdmSession>({
    queryKey: ["adm-session"],
    queryFn: async () => {
      const response = await api.get<Omit<AdmSession, "resolved_adm_page_permissions">>("/admin/auth/me");
      const me = response.data;
      return {
        ...me,
        resolved_adm_page_permissions: normalizeAdmPagePermissions(
          (me.adm_page_permissions || me.page_permissions) as Record<string, { view?: boolean; create?: boolean; edit?: boolean; delete?: boolean }> | null | undefined,
          me.roles,
        ),
      };
    },
    enabled,
    retry: false,
    staleTime: 60_000,
  });
}

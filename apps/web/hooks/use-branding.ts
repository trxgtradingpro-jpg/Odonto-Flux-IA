"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

type SettingItem = {
  id: string;
  key: string;
  value: unknown;
  is_secret: boolean;
};

export type SurfaceStyle = "soft" | "flat" | "glass";

export type BrandingTheme = {
  primaryColor: string;
  secondaryColor: string;
  accentColor: string;
  surfaceStyle: SurfaceStyle;
  logoDataUrl: string | null;
  clinicName: string;
};

const DEFAULT_BRANDING: BrandingTheme = {
  primaryColor: "#0f766e",
  secondaryColor: "#0ea5a4",
  accentColor: "#f59e0b",
  surfaceStyle: "soft",
  logoDataUrl: null,
  clinicName: "OdontoFlux",
};

function readString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function sanitizeHexColor(value: unknown, fallback: string): string {
  const text = readString(value);
  if (!text) return fallback;
  const normalized = text.toLowerCase();
  return /^#[0-9a-f]{6}$/i.test(normalized) ? normalized : fallback;
}

function parseSurfaceStyle(value: unknown): SurfaceStyle {
  if (value === "flat" || value === "glass") return value;
  return "soft";
}

export function useBranding() {
  return useQuery<BrandingTheme>({
    queryKey: ["branding-theme"],
    queryFn: async () => {
      const response = await api.get<{ data: SettingItem[] }>("/settings");
      const settings = response.data.data ?? [];
      const settingMap = new Map(settings.map((item) => [item.key, item.value]));

      const themeValue = settingMap.get("branding.theme");
      const logoValue = settingMap.get("branding.logo_data_url");

      const themePayload = themeValue && typeof themeValue === "object" ? (themeValue as Record<string, unknown>) : {};
      const logoDataUrl =
        readString(logoValue) ??
        (themePayload.logo_data_url && typeof themePayload.logo_data_url === "string"
          ? themePayload.logo_data_url
          : null);

      const clinicName =
        readString(settingMap.get("clinic.display_name")) ??
        readString(settingMap.get("clinic.name")) ??
        readString(settingMap.get("clinic.trade_name")) ??
        DEFAULT_BRANDING.clinicName;

      return {
        primaryColor: sanitizeHexColor(themePayload.primary_color, DEFAULT_BRANDING.primaryColor),
        secondaryColor: sanitizeHexColor(themePayload.secondary_color, DEFAULT_BRANDING.secondaryColor),
        accentColor: sanitizeHexColor(themePayload.accent_color, DEFAULT_BRANDING.accentColor),
        surfaceStyle: parseSurfaceStyle(themePayload.surface_style),
        logoDataUrl,
        clinicName,
      };
    },
    staleTime: 60_000,
    refetchInterval: 90_000,
  });
}

export function brandingSurfaceClass(style: SurfaceStyle): string {
  if (style === "flat") return "surface-flat";
  if (style === "glass") return "surface-glass";
  return "surface-soft";
}


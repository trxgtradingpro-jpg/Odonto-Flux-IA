"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { BRAND_NAME } from "@/lib/brand";

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
  backgroundColor: string;
  surfaceColor: string;
  cardColor: string;
  textColor: string;
  mutedTextColor: string;
  borderColor: string;
  fullscreenBackgroundColor: string;
  fullscreenHeaderColor: string;
  fullscreenAccentColor: string;
  fullscreenForegroundColor: string;
  surfaceStyle: SurfaceStyle;
  logoDataUrl: string | null;
  demoBackgroundImageUrl: string;
  demoBackgroundOpacity: number;
  demoAiTestButtonEnabled: boolean;
  clinicName: string;
};

const DEFAULT_BRANDING: BrandingTheme = {
  primaryColor: "#0f766e",
  secondaryColor: "#0ea5a4",
  accentColor: "#f59e0b",
  backgroundColor: "#f2f4f7",
  surfaceColor: "#eef2f6",
  cardColor: "#ffffff",
  textColor: "#1c1917",
  mutedTextColor: "#475569",
  borderColor: "#d6d3d1",
  fullscreenBackgroundColor: "#0c0a09",
  fullscreenHeaderColor: "#111111",
  fullscreenAccentColor: "#10b981",
  fullscreenForegroundColor: "#ffffff",
  surfaceStyle: "soft",
  logoDataUrl: null,
  demoBackgroundImageUrl: "/images/dental-floss-smile-background.png",
  demoBackgroundOpacity: 0.18,
  demoAiTestButtonEnabled: true,
  clinicName: BRAND_NAME,
};

function readString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function readClinicName(value: unknown): string | null {
  if (!value || typeof value !== "object") return null;
  const record = value as {
    clinic_name?: unknown;
    display_name?: unknown;
    trade_name?: unknown;
    name?: unknown;
  };
  return (
    readString(record.clinic_name) ??
    readString(record.display_name) ??
    readString(record.trade_name) ??
    readString(record.name)
  );
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

function parseOpacity(value: unknown, fallback: number): number {
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(Math.max(parsed, 0), 1);
}

function parseBoolean(value: unknown, fallback: boolean): boolean {
  if (typeof value === "boolean") return value;
  if (value === "true") return true;
  if (value === "false") return false;
  return fallback;
}

export function useBranding(scopeKey: string) {
  return useQuery<BrandingTheme>({
    queryKey: ["branding-theme", scopeKey],
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
        readClinicName(settingMap.get("clinic.profile")) ??
        DEFAULT_BRANDING.clinicName;

      return {
        primaryColor: sanitizeHexColor(themePayload.primary_color, DEFAULT_BRANDING.primaryColor),
        secondaryColor: sanitizeHexColor(themePayload.secondary_color, DEFAULT_BRANDING.secondaryColor),
        accentColor: sanitizeHexColor(themePayload.accent_color, DEFAULT_BRANDING.accentColor),
        backgroundColor: sanitizeHexColor(themePayload.background_color, DEFAULT_BRANDING.backgroundColor),
        surfaceColor: sanitizeHexColor(themePayload.surface_color, DEFAULT_BRANDING.surfaceColor),
        cardColor: sanitizeHexColor(themePayload.card_color, DEFAULT_BRANDING.cardColor),
        textColor: sanitizeHexColor(themePayload.text_color, DEFAULT_BRANDING.textColor),
        mutedTextColor: sanitizeHexColor(themePayload.muted_text_color, DEFAULT_BRANDING.mutedTextColor),
        borderColor: sanitizeHexColor(themePayload.border_color, DEFAULT_BRANDING.borderColor),
        fullscreenBackgroundColor: sanitizeHexColor(
          themePayload.fullscreen_background_color,
          DEFAULT_BRANDING.fullscreenBackgroundColor,
        ),
        fullscreenHeaderColor: sanitizeHexColor(
          themePayload.fullscreen_header_color,
          DEFAULT_BRANDING.fullscreenHeaderColor,
        ),
        fullscreenAccentColor: sanitizeHexColor(
          themePayload.fullscreen_accent_color,
          DEFAULT_BRANDING.fullscreenAccentColor,
        ),
        fullscreenForegroundColor: sanitizeHexColor(
          themePayload.fullscreen_foreground_color,
          DEFAULT_BRANDING.fullscreenForegroundColor,
        ),
        surfaceStyle: parseSurfaceStyle(themePayload.surface_style),
        logoDataUrl,
        demoBackgroundImageUrl:
          readString(themePayload.demo_background_image_url) ?? DEFAULT_BRANDING.demoBackgroundImageUrl,
        demoBackgroundOpacity: parseOpacity(
          themePayload.demo_background_opacity,
          DEFAULT_BRANDING.demoBackgroundOpacity,
        ),
        demoAiTestButtonEnabled: parseBoolean(
          themePayload.demo_ai_test_button_enabled,
          DEFAULT_BRANDING.demoAiTestButtonEnabled,
        ),
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

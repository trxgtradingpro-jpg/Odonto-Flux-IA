export const DEMO_GUIDE_AUTOSTART_KEY = "odontoflux_demo_guided_autostart";
export const DEMO_GUIDE_OVERRIDE_KEY = "odontoflux_demo_guided_override_enabled";
export const DEMO_GUIDE_QUERY_PARAM = "demo_guide";

export function isDemoGuideFeatureEnabled() {
  const normalized = String(process.env.NEXT_PUBLIC_ENABLE_DEMO_GUIDE ?? "")
    .trim()
    .toLowerCase();
  return normalized === "1" || normalized === "true" || normalized === "yes" || normalized === "on";
}

export function isDemoGuideOverrideEnabled() {
  if (typeof window === "undefined") return false;
  return window.sessionStorage.getItem(DEMO_GUIDE_OVERRIDE_KEY) === "1";
}

export function clearDemoGuideSessionState() {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(DEMO_GUIDE_AUTOSTART_KEY);
  window.sessionStorage.removeItem(DEMO_GUIDE_OVERRIDE_KEY);
}

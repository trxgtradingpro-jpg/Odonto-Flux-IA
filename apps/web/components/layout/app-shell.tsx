"use client";

import { useEffect, useMemo, useState } from "react";

import { Sidebar } from "./sidebar";
import { SupportFab } from "./support-fab";
import { Topbar } from "./topbar";
import { brandingSurfaceClass, useBranding } from "@/hooks/use-branding";
import { useSession } from "@/hooks/use-session";

export function AppShell({ children, onLogout }: { children: React.ReactNode; onLogout: () => void }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const sessionQuery = useSession();
  const brandingQuery = useBranding();
  const branding = brandingQuery.data;

  useEffect(() => {
    const root = document.documentElement;
    if (!branding) return;

    root.style.setProperty("--tenant-primary", branding.primaryColor);
    root.style.setProperty("--tenant-secondary", branding.secondaryColor);
    root.style.setProperty("--tenant-accent", branding.accentColor);
  }, [branding]);

  const surfaceClass = useMemo(
    () => brandingSurfaceClass(branding?.surfaceStyle ?? "soft"),
    [branding?.surfaceStyle],
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    const media = window.matchMedia("(min-width: 1024px)");
    const onChange = (event: MediaQueryListEvent) => {
      if (event.matches) {
        setMobileSidebarOpen(false);
      }
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  const handleToggleSidebar = () => {
    if (typeof window !== "undefined" && window.matchMedia("(max-width: 1023px)").matches) {
      setMobileSidebarOpen((current) => !current);
      return;
    }
    setCollapsed((current) => !current);
  };

  return (
    <div className={`flex min-h-screen w-full overflow-x-hidden ${surfaceClass}`}>
      <Sidebar
        collapsed={collapsed}
        mobileOpen={mobileSidebarOpen}
        onCloseMobile={() => setMobileSidebarOpen(false)}
        session={sessionQuery.data}
        branding={branding}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar
          onLogout={onLogout}
          collapsed={collapsed}
          onToggleSidebar={handleToggleSidebar}
          session={sessionQuery.data}
          branding={branding}
        />
        <main className="flex-1 min-w-0 overflow-x-hidden px-3 py-4 sm:px-4 md:px-6 md:py-6">
          <div className="mx-auto w-full max-w-full">{children}</div>
        </main>
      </div>
      <SupportFab />
    </div>
  );
}

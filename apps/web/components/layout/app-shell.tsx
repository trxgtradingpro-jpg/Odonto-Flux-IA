"use client";

import { useEffect, useMemo, useState } from "react";

import { Sidebar } from './sidebar';
import { SupportFab } from "./support-fab";
import { Topbar } from './topbar';
import { brandingSurfaceClass, useBranding } from "@/hooks/use-branding";
import { useSession } from "@/hooks/use-session";

export function AppShell({ children, onLogout }: { children: React.ReactNode; onLogout: () => void }) {
  const [collapsed, setCollapsed] = useState(false);
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

  return (
    <div className={`flex min-h-screen ${surfaceClass}`}>
      <Sidebar collapsed={collapsed} session={sessionQuery.data} branding={branding} />
      <div className="flex flex-1 flex-col">
        <Topbar
          onLogout={onLogout}
          collapsed={collapsed}
          onToggleSidebar={() => setCollapsed((current) => !current)}
          session={sessionQuery.data}
          branding={branding}
        />
        <main className="flex-1 p-6">{children}</main>
      </div>
      <SupportFab />
    </div>
  );
}

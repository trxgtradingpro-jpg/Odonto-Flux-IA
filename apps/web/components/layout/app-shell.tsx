"use client";

import { useState } from "react";

import { Sidebar } from './sidebar';
import { Topbar } from './topbar';
import { useSession } from "@/hooks/use-session";

export function AppShell({ children, onLogout }: { children: React.ReactNode; onLogout: () => void }) {
  const [collapsed, setCollapsed] = useState(false);
  const sessionQuery = useSession();

  return (
    <div className="flex min-h-screen">
      <Sidebar collapsed={collapsed} session={sessionQuery.data} />
      <div className="flex flex-1 flex-col">
        <Topbar
          onLogout={onLogout}
          collapsed={collapsed}
          onToggleSidebar={() => setCollapsed((current) => !current)}
          session={sessionQuery.data}
        />
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}

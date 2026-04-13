"use client";

import { AppShell } from '@/components/layout/app-shell';
import { useAuthGuard } from '@/hooks/use-auth-guard';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { ready, logout } = useAuthGuard();

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">Carregando sessão...</p>
      </div>
    );
  }

  return <AppShell onLogout={logout}>{children}</AppShell>;
}

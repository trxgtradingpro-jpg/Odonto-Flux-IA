"use client";

import { ReactNode } from "react";
import { LockKeyhole } from "lucide-react";

import { Button, Card, CardContent, CardHeader, CardTitle } from "@odontoflux/ui";

type PermissionGateProps = {
  roles?: string[];
  allowedRoles: string[];
  children: ReactNode;
  fallbackTitle?: string;
  fallbackDescription?: string;
  helpText?: string;
  onBack?: () => void;
};

export function PermissionGate({
  roles,
  allowedRoles,
  children,
  fallbackTitle = "Acesso restrito",
  fallbackDescription = "Seu perfil nao possui permissao para visualizar este modulo.",
  helpText,
  onBack,
}: PermissionGateProps) {
  const userRoles = roles ?? [];
  const allowed = userRoles.some((role) => allowedRoles.includes(role));

  if (allowed) return <>{children}</>;

  return (
    <Card className="border-stone-200">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <LockKeyhole size={18} className="text-amber-700" />
          {fallbackTitle}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-stone-700">{fallbackDescription}</p>
        {helpText ? <p className="text-xs text-stone-500">{helpText}</p> : null}
        {onBack ? (
          <Button variant="outline" onClick={onBack}>
            Voltar para o dashboard
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

import { AlertTriangle, Loader2 } from "lucide-react";

import { Card, CardContent } from '@odontoflux/ui';

export function LoadingState({ message = 'Carregando...' }: { message?: string }) {
  return (
    <Card className="border-stone-200 bg-white/95">
      <CardContent className="flex flex-col items-center justify-center gap-3 py-12 text-center">
        <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-stone-100 text-stone-600">
          <Loader2 size={18} className="animate-spin" />
        </span>
        <p className="text-sm font-medium text-muted-foreground">{message}</p>
      </CardContent>
    </Card>
  );
}

export function ErrorState({ message = 'Erro ao carregar dados.' }: { message?: string }) {
  return (
    <Card className="border-rose-200 bg-rose-50/60">
      <CardContent className="flex flex-col items-center justify-center gap-3 py-12 text-center">
        <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-rose-100 text-rose-700">
          <AlertTriangle size={18} />
        </span>
        <p className="text-sm font-semibold text-rose-700">{message}</p>
      </CardContent>
    </Card>
  );
}

import { Card, CardContent } from '@odontoflux/ui';

export function LoadingState({ message = 'Carregando...' }: { message?: string }) {
  return (
    <Card>
      <CardContent className="py-10 text-center text-sm text-muted-foreground">{message}</CardContent>
    </Card>
  );
}

export function ErrorState({ message = 'Erro ao carregar dados.' }: { message?: string }) {
  return (
    <Card>
      <CardContent className="py-10 text-center text-sm text-red-700">{message}</CardContent>
    </Card>
  );
}

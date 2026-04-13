import { Card, CardContent, CardHeader, CardTitle } from '@odontoflux/ui';

export function StatsGrid({
  stats,
}: {
  stats: { label: string; value: string | number; helper?: string }[];
}) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
      {stats.map((stat) => (
        <Card key={stat.label}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">{stat.label}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold tracking-tight">{stat.value}</p>
            {stat.helper ? <p className="mt-1 text-xs text-muted-foreground">{stat.helper}</p> : null}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

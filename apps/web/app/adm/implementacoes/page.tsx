"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Power, RefreshCw, ShieldCheck, SlidersHorizontal } from "lucide-react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { ErrorState, LoadingState } from "@/components/page-state";
import { useAdmSession } from "@/hooks/use-adm-session";
import { canAccessAdmPage } from "@/lib/adm-page-access";
import { api } from "@/lib/api";
import { getAdminAccessToken } from "@/lib/auth";
import { BRAND_NAME } from "@/lib/brand";
import { formatDateTimeBR } from "@/lib/formatters";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, cn } from "@odontoflux/ui";

type ImplementationItem = {
  key: string;
  label: string;
  category: string;
  description: string;
  delivery_status: "implemented" | "partial" | "planned" | string;
  enabled: boolean;
  default_enabled: boolean;
  can_toggle: boolean;
  notes?: string | null;
  updated_at?: string | null;
};

type ImplementationSnapshot = {
  generated_at: string;
  summary: {
    total: number;
    enabled: number;
    implemented: number;
    partial: number;
    planned: number;
  };
  items: ImplementationItem[];
};

function deliveryLabel(value: string) {
  if (value === "implemented") return "Implementado";
  if (value === "partial") return "Parcial";
  return "Planejado";
}

function deliveryClass(value: string) {
  if (value === "implemented") return "bg-emerald-100 text-emerald-700";
  if (value === "partial") return "bg-amber-100 text-amber-800";
  return "bg-stone-200 text-stone-700";
}

function ImplementationCard({
  item,
  onToggle,
  pending,
  canEdit,
}: {
  item: ImplementationItem;
  onToggle: (item: ImplementationItem) => void;
  pending: boolean;
  canEdit: boolean;
}) {
  return (
    <Card className="border-stone-200 bg-white">
      <CardHeader className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <Badge className={deliveryClass(item.delivery_status)}>{deliveryLabel(item.delivery_status)}</Badge>
              <Badge className={item.enabled ? "bg-emerald-100 text-emerald-700" : "bg-stone-200 text-stone-700"}>
                {item.enabled ? "Ativa" : "Desligada"}
              </Badge>
              <Badge className="bg-sky-100 text-sky-700">{item.category}</Badge>
            </div>
            <CardTitle className="text-base text-stone-900">{item.label}</CardTitle>
          </div>
          <Button
            type="button"
            disabled={!canEdit || !item.can_toggle || pending}
            onClick={() => onToggle(item)}
            className={cn("min-w-28", !item.enabled && "bg-stone-900 text-white hover:bg-stone-800")}
          >
            <Power size={16} />
            {pending ? "Salvando..." : item.enabled ? "Desativar" : item.can_toggle ? "Ativar" : "Bloqueado"}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm text-stone-600">
        <p>{item.description}</p>
        {item.notes ? <p className="rounded-xl bg-stone-50 px-3 py-2 text-stone-500">{item.notes}</p> : null}
        <div className="flex flex-wrap items-center gap-3 text-xs text-stone-500">
          <span>Chave: {item.key}</span>
          <span>Padrao: {item.default_enabled ? "ligada" : "desligada"}</span>
          {item.updated_at ? <span>Atualizada em {formatDateTimeBR(item.updated_at)}</span> : null}
        </div>
      </CardContent>
    </Card>
  );
}

export default function AdmImplementacoesPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getAdminAccessToken()) {
      router.replace("/adm");
      return;
    }
    setReady(true);
  }, [router]);

  const admSessionQuery = useAdmSession(ready);
  const canViewImplementations = canAccessAdmPage(
    admSessionQuery.data?.resolved_adm_page_permissions,
    "adm_implementations",
    "view",
  );
  const canEditImplementations = canAccessAdmPage(
    admSessionQuery.data?.resolved_adm_page_permissions,
    "adm_implementations",
    "edit",
  );

  const snapshotQuery = useQuery<ImplementationSnapshot>({
    queryKey: ["adm-implementations"],
    queryFn: async () => (await api.get("/admin/platform/implementations")).data,
    enabled: ready && canViewImplementations,
  });

  const toggleMutation = useMutation({
    mutationFn: async ({ key, enabled }: { key: string; enabled: boolean }) =>
      (await api.patch(`/admin/platform/implementations/${key}`, { enabled })).data,
    onSuccess: (_data, variables) => {
      toast.success(variables.enabled ? "Implementacao ativada." : "Implementacao desativada.");
      queryClient.invalidateQueries({ queryKey: ["adm-implementations"] });
    },
    onError: () => toast.error("Nao foi possivel salvar o estado da implementacao."),
  });

  if (!ready || admSessionQuery.isLoading || snapshotQuery.isLoading) {
    return <LoadingState message="Carregando central de implementacoes..." />;
  }

  if (!canViewImplementations) {
    return (
      <main className="grid min-h-screen place-items-center overflow-x-hidden bg-stone-950 px-4 text-white">
        <Card className="w-full max-w-md border-white/10 bg-white text-stone-950">
          <CardContent className="space-y-4 p-8 text-center">
            <h1 className="text-xl font-black">Area restrita</h1>
            <p className="text-sm leading-6 text-stone-600">Seu usuario nao tem permissao para ver implementacoes.</p>
            <Link className="inline-flex h-10 items-center rounded-lg bg-stone-950 px-4 text-sm font-bold text-white" href="/adm">
              Voltar ao /adm
            </Link>
          </CardContent>
        </Card>
      </main>
    );
  }

  if (snapshotQuery.isError || !snapshotQuery.data) {
    return <ErrorState message="Nao foi possivel carregar as implementacoes do /adm." />;
  }

  const activeItems = snapshotQuery.data.items.filter((item) => item.enabled);
  const readyItems = snapshotQuery.data.items.filter(
    (item) => !item.enabled && item.can_toggle && item.delivery_status !== "planned",
  );
  const plannedItems = snapshotQuery.data.items.filter(
    (item) => item.delivery_status === "planned" || !item.can_toggle,
  );

  return (
    <main className="min-h-screen overflow-x-hidden bg-stone-950 px-4 py-6 text-white md:px-6">
      <div className="mx-auto w-full max-w-7xl space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-white/45">Admin comercial</p>
            <h1 className="text-2xl font-bold">{BRAND_NAME} /adm implementacoes</h1>
            <p className="max-w-3xl text-sm text-white/70">
              Painel para acompanhar o que ja foi entregue, o que ainda esta desligado e o que ainda depende de rollout planejado.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link
              href="/adm"
              className="inline-flex h-10 items-center justify-center gap-1.5 rounded-lg bg-white px-4 text-sm font-semibold text-stone-950 transition hover:bg-stone-100 active:translate-y-[1px]"
            >
              <ArrowLeft size={16} />
              Voltar ao /adm
            </Link>
            <Button
              type="button"
              className="border border-white/15 bg-white/5 text-white hover:bg-white/10"
              onClick={() => snapshotQuery.refetch()}
            >
              <RefreshCw size={16} />
              Atualizar
            </Button>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Card className="border-white/10 bg-white text-stone-950">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <ShieldCheck size={16} />
                Ativas agora
              </CardTitle>
            </CardHeader>
            <CardContent className="text-3xl font-bold">{snapshotQuery.data.summary.enabled}</CardContent>
          </Card>
          <Card className="border-white/10 bg-white text-stone-950">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <SlidersHorizontal size={16} />
                Implementadas
              </CardTitle>
            </CardHeader>
            <CardContent className="text-3xl font-bold">{snapshotQuery.data.summary.implemented}</CardContent>
          </Card>
          <Card className="border-white/10 bg-white text-stone-950">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <RefreshCw size={16} />
                Parciais
              </CardTitle>
            </CardHeader>
            <CardContent className="text-3xl font-bold">{snapshotQuery.data.summary.partial}</CardContent>
          </Card>
          <Card className="border-white/10 bg-white text-stone-950">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Power size={16} />
                Catalogo total
              </CardTitle>
            </CardHeader>
            <CardContent className="text-3xl font-bold">{snapshotQuery.data.summary.total}</CardContent>
          </Card>
        </div>

        <section className="space-y-3">
          <div>
            <h2 className="text-lg font-semibold">Ativas agora</h2>
            <p className="text-sm text-white/60">Implementacoes em operacao no momento.</p>
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            {activeItems.length ? (
              activeItems.map((item) => (
                <ImplementationCard
                  key={item.key}
                  item={item}
                  pending={toggleMutation.isPending && toggleMutation.variables?.key === item.key}
                  onToggle={(current) => toggleMutation.mutate({ key: current.key, enabled: !current.enabled })}
                  canEdit={canEditImplementations}
                />
              ))
            ) : (
              <Card className="border-white/10 bg-white/5 text-white">
                <CardContent className="py-6 text-sm text-white/70">Nenhuma implementacao ativa neste momento.</CardContent>
              </Card>
            )}
          </div>
        </section>

        <section className="space-y-3">
          <div>
            <h2 className="text-lg font-semibold">Disponiveis para ativar</h2>
            <p className="text-sm text-white/60">Entregas com base pronta, mas ainda desligadas para rollout controlado.</p>
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            {readyItems.length ? (
              readyItems.map((item) => (
                <ImplementationCard
                  key={item.key}
                  item={item}
                  pending={toggleMutation.isPending && toggleMutation.variables?.key === item.key}
                  onToggle={(current) => toggleMutation.mutate({ key: current.key, enabled: !current.enabled })}
                  canEdit={canEditImplementations}
                />
              ))
            ) : (
              <Card className="border-white/10 bg-white/5 text-white">
                <CardContent className="py-6 text-sm text-white/70">Nenhuma implementacao pronta aguardando ativacao.</CardContent>
              </Card>
            )}
          </div>
        </section>

        <section className="space-y-3">
          <div>
            <h2 className="text-lg font-semibold">Planejadas ou bloqueadas</h2>
            <p className="text-sm text-white/60">Itens que ainda dependem de rollout adicional antes de virarem chave operacional.</p>
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            {plannedItems.length ? (
              plannedItems.map((item) => (
                <ImplementationCard
                  key={item.key}
                  item={item}
                  pending={toggleMutation.isPending && toggleMutation.variables?.key === item.key}
                  onToggle={(current) => toggleMutation.mutate({ key: current.key, enabled: !current.enabled })}
                  canEdit={canEditImplementations}
                />
              ))
            ) : (
              <Card className="border-white/10 bg-white/5 text-white">
                <CardContent className="py-6 text-sm text-white/70">Sem itens bloqueados neste momento.</CardContent>
              </Card>
            )}
          </div>
        </section>

        <p className="text-xs text-white/45">Snapshot gerado em {formatDateTimeBR(snapshotQuery.data.generated_at)}.</p>
      </div>
    </main>
  );
}

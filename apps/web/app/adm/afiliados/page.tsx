"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Lock, RefreshCw, Save, Trash2, UsersRound } from "lucide-react";
import { toast } from "sonner";

import { useAdmSession, type AdmSession } from "@/hooks/use-adm-session";
import {
  ADM_ACTION_LABELS,
  ADM_MANAGED_PAGES,
  type AdmAction,
  type AdmPageKey,
  type AdmPagePermissionMap,
  canAccessAdmPage,
  createEmptyAdmPagePermissionMap,
  normalizeAdmPagePermissions,
} from "@/lib/adm-page-access";
import { api } from "@/lib/api";
import { getAdminAccessToken } from "@/lib/auth";
import { formatDateTimeBR } from "@/lib/formatters";
import { Badge, Button, Card, CardContent, Input, cn } from "@odontoflux/ui";

type AffiliatesResponse = {
  data: AdmSession[];
  total: number;
};

type AffiliateCrmStats = {
  contacts_today: number;
  contacts_week: number;
  contacts_month: number;
  total_contacted: number;
  current_portfolio: number;
  portfolio_with_site: number;
  portfolio_without_site: number;
  last_contact_at?: string | null;
};

const ACTIONS: AdmAction[] = ["view", "create", "edit", "delete"];

function extractApiErrorMessage(error: unknown, fallback: string) {
  const response = (error as { response?: { data?: { error?: { message?: string } } } }).response;
  return response?.data?.error?.message || fallback;
}

function clonePermissions(permissions: AdmPagePermissionMap | null | undefined) {
  const base = createEmptyAdmPagePermissionMap();
  ADM_MANAGED_PAGES.forEach((page) => {
    base[page.key] = { ...(permissions?.[page.key] ?? base[page.key]) };
  });
  return base;
}

function togglePermission(
  permissions: AdmPagePermissionMap,
  pageKey: AdmPageKey,
  action: AdmAction,
): AdmPagePermissionMap {
  const next = clonePermissions(permissions);
  const nextValue = !next[pageKey][action];
  if (action === "view" && !nextValue) {
    next[pageKey] = { view: false, create: false, edit: false, delete: false };
    return next;
  }
  next[pageKey][action] = nextValue;
  if (action !== "view" && nextValue) {
    next[pageKey].view = true;
  }
  return next;
}

function PermissionMatrix({
  value,
  disabled,
  onChange,
}: {
  value: AdmPagePermissionMap;
  disabled: boolean;
  onChange: (next: AdmPagePermissionMap) => void;
}) {
  return (
    <div className="space-y-3">
      {ADM_MANAGED_PAGES.map((page) => (
        <div key={page.key} className="rounded-2xl border border-stone-200 bg-white p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <p className="text-sm font-black text-stone-950">{page.label}</p>
              <p className="mt-1 text-xs leading-5 text-stone-500">{page.description}</p>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {ACTIONS.map((action) => {
                const checked = value[page.key]?.[action] ?? false;
                return (
                  <button
                    key={action}
                    type="button"
                    disabled={disabled}
                    className={cn(
                      "rounded-xl border px-3 py-2 text-xs font-bold transition",
                      checked
                        ? "border-emerald-300 bg-emerald-50 text-emerald-800"
                        : "border-stone-200 bg-stone-50 text-stone-500",
                      disabled && "cursor-not-allowed opacity-60",
                    )}
                    onClick={() => onChange(togglePermission(value, page.key, action))}
                  >
                    {ADM_ACTION_LABELS[action]}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function AdmAffiliatesPage() {
  const queryClient = useQueryClient();
  const [hasToken, setHasToken] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [permissions, setPermissions] = useState<AdmPagePermissionMap>(() => createEmptyAdmPagePermissionMap());

  useEffect(() => {
    setHasToken(Boolean(getAdminAccessToken()));
  }, []);

  const admSessionQuery = useAdmSession(hasToken);
  const canView = canAccessAdmPage(admSessionQuery.data?.resolved_adm_page_permissions, "adm_affiliates", "view");
  const canEdit = canAccessAdmPage(admSessionQuery.data?.resolved_adm_page_permissions, "adm_affiliates", "edit");
  const canDelete = canAccessAdmPage(admSessionQuery.data?.resolved_adm_page_permissions, "adm_affiliates", "delete");

  const affiliatesQuery = useQuery<AffiliatesResponse>({
    queryKey: ["adm-affiliates"],
    queryFn: async () => (await api.get("/admin/affiliates")).data,
    enabled: hasToken && canView,
    retry: false,
  });

  const affiliates = useMemo(() => affiliatesQuery.data?.data ?? [], [affiliatesQuery.data?.data]);
  const selectedAffiliate = useMemo(
    () => affiliates.find((affiliate) => affiliate.id === selectedId) ?? affiliates[0] ?? null,
    [affiliates, selectedId],
  );
  const affiliateStatsQuery = useQuery<AffiliateCrmStats>({
    queryKey: ["adm-affiliate-stats", selectedAffiliate?.id],
    queryFn: async () => (await api.get(`/admin/affiliates/${selectedAffiliate?.id}/stats`)).data,
    enabled: hasToken && canView && Boolean(selectedAffiliate?.id),
    retry: false,
  });

  useEffect(() => {
    if (!selectedId && selectedAffiliate) setSelectedId(selectedAffiliate.id);
  }, [selectedAffiliate, selectedId]);

  useEffect(() => {
    if (!selectedAffiliate) return;
    setFullName(selectedAffiliate.full_name);
    setPhone(selectedAffiliate.phone ?? "");
    setIsActive(selectedAffiliate.is_active);
    setPermissions(
      clonePermissions(
        normalizeAdmPagePermissions(
          (selectedAffiliate.adm_page_permissions || selectedAffiliate.page_permissions) as Record<string, { view?: boolean; create?: boolean; edit?: boolean; delete?: boolean }> | null | undefined,
          selectedAffiliate.roles,
        ),
      ),
    );
  }, [selectedAffiliate]);

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!selectedAffiliate) throw new Error("Afiliado nao selecionado.");
      return (
        await api.patch(`/admin/affiliates/${selectedAffiliate.id}`, {
          full_name: fullName,
          phone: phone || null,
          is_active: isActive,
          page_permissions: permissions,
        })
      ).data;
    },
    onSuccess: () => {
      toast.success("Permissoes do afiliado atualizadas.");
      queryClient.invalidateQueries({ queryKey: ["adm-affiliates"] });
    },
    onError: (error) => toast.error(extractApiErrorMessage(error, "Nao foi possivel atualizar o afiliado.")),
  });

  const deleteMutation = useMutation({
    mutationFn: async (affiliateId: string) => (await api.delete(`/admin/affiliates/${affiliateId}`)).data,
    onSuccess: () => {
      toast.success("Afiliado removido.");
      setSelectedId(null);
      queryClient.invalidateQueries({ queryKey: ["adm-affiliates"] });
    },
    onError: (error) => toast.error(extractApiErrorMessage(error, "Nao foi possivel remover o afiliado.")),
  });

  if (!hasToken) {
    return (
      <main className="grid min-h-screen place-items-center overflow-x-hidden bg-stone-100 px-4 text-stone-950">
        <Card className="w-full max-w-md border-stone-200 bg-white">
          <CardContent className="space-y-4 p-8">
            <Lock className="h-9 w-9 text-stone-400" />
            <h1 className="text-xl font-black">Entre no /adm primeiro</h1>
            <Link className="inline-flex h-10 items-center rounded-lg bg-stone-950 px-4 text-sm font-bold text-white" href="/adm">
              Abrir login
            </Link>
          </CardContent>
        </Card>
      </main>
    );
  }

  if (admSessionQuery.isLoading) {
    return (
      <main className="grid min-h-screen place-items-center overflow-x-hidden bg-stone-100 px-4 text-stone-950">
        <Card className="w-full max-w-md border-stone-200 bg-white">
          <CardContent className="p-8 text-center text-sm text-stone-600">Carregando permissoes...</CardContent>
        </Card>
      </main>
    );
  }

  if (!canView) {
    return (
      <main className="grid min-h-screen place-items-center overflow-x-hidden bg-stone-100 px-4 text-stone-950">
        <Card className="w-full max-w-md border-stone-200 bg-white">
          <CardContent className="space-y-4 p-8 text-center">
            <Lock className="mx-auto h-9 w-9 text-stone-400" />
            <h1 className="text-xl font-black">Area restrita</h1>
            <p className="text-sm leading-6 text-stone-600">Seu usuario nao tem permissao para gerenciar afiliados.</p>
            <Link className="inline-flex h-10 items-center rounded-lg bg-stone-950 px-4 text-sm font-bold text-white" href="/adm">
              Voltar ao /adm
            </Link>
          </CardContent>
        </Card>
      </main>
    );
  }

  return (
    <main className="min-h-screen overflow-x-hidden bg-[#f5f2ea] text-stone-950">
      <header className="sticky top-0 z-20 border-b border-stone-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-3 px-4 py-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-3">
            <Link
              href="/adm"
              className="grid h-10 w-10 place-items-center rounded-xl border border-stone-200 bg-white text-stone-700 transition hover:bg-stone-100"
            >
              <ArrowLeft size={18} />
            </Link>
            <div className="min-w-0">
              <p className="text-xs font-bold uppercase tracking-[0.2em] text-stone-500">Permissoes do /adm</p>
              <h1 className="text-xl font-black">Afiliados</h1>
            </div>
          </div>
          <Button variant="outline" onClick={() => affiliatesQuery.refetch()} disabled={affiliatesQuery.isFetching}>
            <RefreshCw size={16} className={cn(affiliatesQuery.isFetching && "animate-spin")} />
            Atualizar
          </Button>
        </div>
      </header>

      <div className="mx-auto grid w-full max-w-[1500px] gap-5 px-4 py-5 xl:grid-cols-[360px_minmax(0,1fr)]">
        <aside className="space-y-3">
          <Card className="border-stone-200 bg-white">
            <CardContent className="space-y-3 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.18em] text-stone-500">Usuarios afiliados</p>
                  <h2 className="text-2xl font-black">{affiliatesQuery.data?.total ?? affiliates.length}</h2>
                </div>
                <div className="grid h-11 w-11 place-items-center rounded-2xl bg-emerald-50 text-emerald-700">
                  <UsersRound size={20} />
                </div>
              </div>
              <p className="text-sm leading-6 text-stone-600">
                O cadastro publico cria afiliados com CRM comercial e mensagens prontas por padrao. O admin principal pode ajustar pagina por pagina aqui.
              </p>
            </CardContent>
          </Card>

          <div className="space-y-2">
            {affiliatesQuery.isLoading ? (
              <Card className="border-stone-200 bg-white">
                <CardContent className="p-5 text-sm text-stone-500">Carregando afiliados...</CardContent>
              </Card>
            ) : affiliates.length ? (
              affiliates.map((affiliate) => {
                const selected = selectedAffiliate?.id === affiliate.id;
                return (
                  <button
                    key={affiliate.id}
                    type="button"
                    className={cn(
                      "w-full rounded-2xl border bg-white p-4 text-left transition hover:border-emerald-200 hover:bg-emerald-50/50",
                      selected ? "border-emerald-300 bg-emerald-50 shadow-sm" : "border-stone-200",
                    )}
                    onClick={() => setSelectedId(affiliate.id)}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-black text-stone-950">{affiliate.full_name}</p>
                        <p className="truncate text-xs text-stone-500">{affiliate.email}</p>
                      </div>
                      <Badge className={affiliate.is_active ? "bg-emerald-100 text-emerald-700" : "bg-stone-200 text-stone-700"}>
                        {affiliate.is_active ? "Ativo" : "Inativo"}
                      </Badge>
                    </div>
                    <p className="mt-2 text-xs text-stone-500">Criado em {formatDateTimeBR(affiliate.created_at)}</p>
                  </button>
                );
              })
            ) : (
              <Card className="border-dashed border-stone-300 bg-white">
                <CardContent className="p-5 text-sm text-stone-500">Nenhum afiliado cadastrado ainda.</CardContent>
              </Card>
            )}
          </div>
        </aside>

        <section className="min-w-0 space-y-4">
          {selectedAffiliate ? (
            <>
              <Card className="border-stone-200 bg-white">
                <CardContent className="space-y-4 p-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <p className="text-xs font-bold uppercase tracking-[0.18em] text-stone-500">Dados do afiliado</p>
                      <h2 className="mt-1 text-2xl font-black">{selectedAffiliate.full_name}</h2>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        className="bg-emerald-600 text-white hover:bg-emerald-500"
                        disabled={!canEdit || updateMutation.isPending}
                        onClick={() => updateMutation.mutate()}
                      >
                        <Save size={16} />
                        {updateMutation.isPending ? "Salvando..." : "Salvar permissoes"}
                      </Button>
                      <Button
                        variant="outline"
                        disabled={!canDelete || deleteMutation.isPending}
                        onClick={() => {
                          if (window.confirm(`Excluir o afiliado ${selectedAffiliate.full_name}?`)) {
                            deleteMutation.mutate(selectedAffiliate.id);
                          }
                        }}
                      >
                        <Trash2 size={16} />
                        Excluir
                      </Button>
                    </div>
                  </div>

                  <div className="grid gap-3 lg:grid-cols-3">
                    <label className="space-y-2 lg:col-span-2">
                      <span className="text-xs font-bold uppercase tracking-[0.16em] text-stone-500">Nome</span>
                      <Input value={fullName} onChange={(event) => setFullName(event.target.value)} disabled={!canEdit} />
                    </label>
                    <label className="space-y-2">
                      <span className="text-xs font-bold uppercase tracking-[0.16em] text-stone-500">Telefone</span>
                      <Input value={phone} onChange={(event) => setPhone(event.target.value)} disabled={!canEdit} />
                    </label>
                    <label className="flex items-center gap-2 rounded-2xl border border-stone-200 bg-stone-50 px-4 py-3 text-sm font-semibold">
                      <input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} disabled={!canEdit} />
                      Afiliado ativo
                    </label>
                    <div className="rounded-2xl border border-stone-200 bg-stone-50 px-4 py-3 text-sm text-stone-600 lg:col-span-2">
                      <strong className="text-stone-900">E-mail:</strong> {selectedAffiliate.email}
                    </div>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    <AffiliateStatCard label="Hoje" value={affiliateStatsQuery.data?.contacts_today ?? 0} />
                    <AffiliateStatCard label="Semana" value={affiliateStatsQuery.data?.contacts_week ?? 0} />
                    <AffiliateStatCard label="Mes" value={affiliateStatsQuery.data?.contacts_month ?? 0} />
                    <AffiliateStatCard label="Total contatadas" value={affiliateStatsQuery.data?.total_contacted ?? 0} />
                    <AffiliateStatCard label="Carteira" value={affiliateStatsQuery.data?.current_portfolio ?? 0} />
                    <AffiliateStatCard label="Com site" value={affiliateStatsQuery.data?.portfolio_with_site ?? 0} />
                    <AffiliateStatCard label="Sem site" value={affiliateStatsQuery.data?.portfolio_without_site ?? 0} />
                    <div className="rounded-2xl border border-stone-200 bg-stone-50 px-4 py-3">
                      <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-stone-500">Ultimo contato</p>
                      <p className="mt-2 text-sm font-semibold text-stone-900">
                        {affiliateStatsQuery.data?.last_contact_at ? formatDateTimeBR(affiliateStatsQuery.data.last_contact_at) : "Ainda nao iniciou"}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <PermissionMatrix value={permissions} disabled={!canEdit} onChange={setPermissions} />
            </>
          ) : (
            <Card className="border-stone-200 bg-white">
              <CardContent className="p-8 text-center text-sm text-stone-500">Selecione um afiliado para editar as permissoes.</CardContent>
            </Card>
          )}
        </section>
      </div>
    </main>
  );
}

function AffiliateStatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-stone-200 bg-stone-50 px-4 py-3">
      <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-stone-500">{label}</p>
      <p className="mt-2 text-2xl font-black text-stone-950">{value}</p>
    </div>
  );
}

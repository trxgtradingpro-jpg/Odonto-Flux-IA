"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Database,
  ExternalLink,
  MapPin,
  RefreshCw,
  Search,
  ShieldCheck,
} from "lucide-react";
import { toast } from "sonner";

import { useAdmSession } from "@/hooks/use-adm-session";
import { canAccessAdmPage } from "@/lib/adm-page-access";
import { api } from "@/lib/api";
import { getAdminAccessToken } from "@/lib/auth";
import { Badge, Button, Card, CardContent, Input, cn } from "@odontoflux/ui";

const RECENT_QUERIES_STORAGE_KEY = "adm-google-places-recent-queries";
const LAST_QUERY_STORAGE_KEY = "adm-google-places-last-query";
const MAX_RECENT_QUERIES = 6;

type PlaceCandidate = {
  place_id: string;
  name: string;
  formatted_address?: string | null;
  city?: string | null;
  state?: string | null;
  google_maps_url?: string | null;
  business_status?: string | null;
  types: string[];
  duplicate_prospect_id?: string | null;
  duplicate_clinic_name?: string | null;
};

type PlacesSearchResponse = {
  query: string;
  limit: number;
  field_mask: string;
  cost_mode: string;
  results: PlaceCandidate[];
};

type Prospect = {
  id: string;
  clinic_name: string;
  phone?: string | null;
  whatsapp_phone?: string | null;
  city?: string | null;
  state?: string | null;
  website?: string | null;
};

type ImportResult = {
  place_id: string;
  status: "created" | "duplicate" | "failed";
  message: string;
  name?: string | null;
  prospect?: Prospect | null;
};

type PlacesImportResponse = {
  created_count: number;
  duplicate_count: number;
  failed_count: number;
  requested_count: number;
  include_rating: boolean;
  results: ImportResult[];
};

function extractApiErrorMessage(error: unknown, fallback: string) {
  const response = (error as { response?: { data?: { error?: { message?: string } } } }).response;
  return response?.data?.error?.message || fallback;
}

function statusBadgeClass(status?: string | null) {
  if (status === "OPERATIONAL") return "border-emerald-200 bg-emerald-50 text-emerald-800";
  if (status === "CLOSED_TEMPORARILY") return "border-amber-200 bg-amber-50 text-amber-800";
  if (status === "CLOSED_PERMANENTLY") return "border-red-200 bg-red-50 text-red-700";
  return "border-stone-200 bg-stone-100 text-stone-700";
}

function resultBadgeClass(status: ImportResult["status"]) {
  if (status === "created") return "border-emerald-200 bg-emerald-50 text-emerald-800";
  if (status === "duplicate") return "border-amber-200 bg-amber-50 text-amber-800";
  return "border-red-200 bg-red-50 text-red-700";
}

function normalizeRecentQuery(value: string) {
  return value.trim().replace(/\s+/g, " ");
}

function loadRecentQueries() {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(RECENT_QUERIES_STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string" && item.trim().length >= 3) : [];
  } catch {
    return [];
  }
}

function persistRecentQueries(queries: string[]) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(RECENT_QUERIES_STORAGE_KEY, JSON.stringify(queries));
}

function saveLastQuery(query: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(LAST_QUERY_STORAGE_KEY, query);
}

export default function ImportClinicsFromPlacesPage() {
  const queryClient = useQueryClient();
  const [hasToken, setHasToken] = useState(false);
  const [query, setQuery] = useState("clinica odontologica em Sao Paulo");
  const [limit, setLimit] = useState(10);
  const [includedType, setIncludedType] = useState("dentist");
  const [includeRating, setIncludeRating] = useState(false);
  const [recentQueries, setRecentQueries] = useState<string[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [searchData, setSearchData] = useState<PlacesSearchResponse | null>(null);
  const [importData, setImportData] = useState<PlacesImportResponse | null>(null);

  useEffect(() => {
    setHasToken(Boolean(getAdminAccessToken()));
  }, []);

  useEffect(() => {
    const storedRecentQueries = loadRecentQueries();
    setRecentQueries(storedRecentQueries);

    if (typeof window === "undefined") return;
    const lastQuery = window.localStorage.getItem(LAST_QUERY_STORAGE_KEY);
    if (lastQuery && lastQuery.trim().length >= 3) {
      setQuery(lastQuery);
    }
  }, []);

  const admSessionQuery = useAdmSession(hasToken);
  const admPermissions = admSessionQuery.data?.resolved_adm_page_permissions;
  const canViewImport = canAccessAdmPage(admPermissions, "adm_import_places", "view");
  const canCreateImport = canAccessAdmPage(admPermissions, "adm_import_places", "create");

  const candidates = useMemo(() => searchData?.results ?? [], [searchData?.results]);
  const selectedCandidates = useMemo(
    () => candidates.filter((candidate) => selectedIds.includes(candidate.place_id)),
    [candidates, selectedIds],
  );

  const searchMutation = useMutation({
    mutationFn: async (overrideQuery?: string) =>
      (
        await api.post<PlacesSearchResponse>("/admin/google-places/search", {
          query: normalizeRecentQuery(overrideQuery ?? query),
          limit,
          region_code: "BR",
          included_type: includedType === "none" ? null : includedType,
        })
      ).data,
    onSuccess: (data) => {
      setSearchData(data);
      setImportData(null);
      const normalizedQuery = normalizeRecentQuery(data.query);
      saveLastQuery(normalizedQuery);
      setRecentQueries((current) => {
        const next = [normalizedQuery, ...current.filter((item) => item !== normalizedQuery)].slice(0, MAX_RECENT_QUERIES);
        persistRecentQueries(next);
        return next;
      });
      const selectableIds = data.results
        .filter((candidate) => !candidate.duplicate_prospect_id)
        .map((candidate) => candidate.place_id);
      setSelectedIds(selectableIds);
      toast.success(`${data.results.length} clinicas encontradas no Google Places.`);
    },
    onError: (error) => {
      toast.error(extractApiErrorMessage(error, "Nao foi possivel buscar clinicas no Google Places."));
    },
  });

  const importMutation = useMutation({
    mutationFn: async () =>
      (
        await api.post<PlacesImportResponse>("/admin/google-places/import", {
          place_ids: selectedIds,
          lead_source: "google_places",
          include_rating: includeRating,
        })
      ).data,
    onSuccess: (data) => {
      setImportData(data);
      queryClient.invalidateQueries({ queryKey: ["adm-prospects"] });
      queryClient.invalidateQueries({ queryKey: ["adm-overview"] });
      toast.success(`${data.created_count} clinica(s) importada(s) para o CRM.`);
    },
    onError: (error) => {
      toast.error(extractApiErrorMessage(error, "Nao foi possivel importar as clinicas selecionadas."));
    },
  });

  function toggleCandidate(placeId: string) {
    setSelectedIds((current) =>
      current.includes(placeId) ? current.filter((item) => item !== placeId) : [...current, placeId],
    );
  }

  function selectOnlyAvailable() {
    setSelectedIds(candidates.filter((candidate) => !candidate.duplicate_prospect_id).map((candidate) => candidate.place_id));
  }

  if (!hasToken) {
    return (
      <main className="min-h-screen overflow-x-hidden bg-[#f5f2ea] p-6 text-stone-950">
        <Card className="mx-auto max-w-xl border-stone-200 bg-white">
          <CardContent className="space-y-5 p-8">
            <div className="grid h-12 w-12 place-items-center rounded-xl bg-stone-950 text-sm font-black text-white">
              CF
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Admin comercial</p>
              <h1 className="mt-1 text-2xl font-black">Entre no /adm primeiro</h1>
              <p className="mt-2 text-sm leading-6 text-stone-600">
                A importacao pelo Google Places usa o mesmo login administrativo do CRM comercial.
              </p>
            </div>
            <Link
              href="/adm"
              className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-stone-950 px-4 text-sm font-bold text-white"
            >
              Abrir login do /adm
              <ArrowLeft className="h-4 w-4 rotate-180" />
            </Link>
          </CardContent>
        </Card>
      </main>
    );
  }

  if (admSessionQuery.isLoading) {
    return (
      <main className="grid min-h-screen place-items-center overflow-x-hidden bg-[#f5f2ea] px-4 text-stone-950">
        <Card className="w-full max-w-md border-stone-200 bg-white">
          <CardContent className="p-8 text-center text-sm text-stone-600">Carregando permissoes...</CardContent>
        </Card>
      </main>
    );
  }

  if (!canViewImport) {
    return (
      <main className="grid min-h-screen place-items-center overflow-x-hidden bg-[#f5f2ea] px-4 text-stone-950">
        <Card className="w-full max-w-md border-stone-200 bg-white">
          <CardContent className="space-y-4 p-8 text-center">
            <AlertTriangle className="mx-auto h-9 w-9 text-stone-400" />
            <h1 className="text-xl font-black">Area sem permissao</h1>
            <p className="text-sm leading-6 text-stone-600">Seu usuario nao tem acesso a importacao pelo Google Places.</p>
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
        <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-3 px-4 py-4 lg:flex-row lg:items-center lg:justify-between lg:px-5">
          <div className="flex items-center gap-3">
            <Link
              href="/adm"
              className="grid h-10 w-10 place-items-center rounded-xl border border-stone-200 bg-white text-stone-700 transition hover:bg-stone-100"
            >
              <ArrowLeft size={18} />
            </Link>
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.2em] text-stone-500">Google Places</p>
              <h1 className="text-xl font-black">Importar clinicas automaticamente</h1>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => searchMutation.mutate(undefined)} disabled={searchMutation.isPending}>
              <RefreshCw size={16} className={cn(searchMutation.isPending && "animate-spin")} />
              Buscar novamente
            </Button>
            <Link
              href="/adm"
              className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-stone-200 bg-white px-4 text-sm font-bold text-stone-800 transition hover:bg-stone-100"
            >
              Voltar ao CRM
            </Link>
          </div>
        </div>
      </header>

      <div className="mx-auto w-full max-w-[1500px] space-y-5 px-4 py-5 lg:px-5">
        <section className="overflow-hidden rounded-3xl border border-emerald-200 bg-[radial-gradient(circle_at_top_left,#dcfce7,transparent_32%),linear-gradient(135deg,#052e2b,#0f766e)] text-white shadow-sm">
          <div className="grid gap-6 p-6 lg:grid-cols-[1fr_360px] lg:p-8">
            <div>
              <Badge className="border-white/15 bg-white/10 text-white">Busca economica + cadastro automatico</Badge>
              <h2 className="mt-4 max-w-3xl text-3xl font-black tracking-tight lg:text-5xl">
                Puxe clinicas do Google Places e transforme em prospects do /adm.
              </h2>
              <p className="mt-4 max-w-2xl text-sm leading-6 text-emerald-50">
                A busca carrega apenas campos basicos. Telefone, site e coordenadas so sao buscados quando voce
                seleciona as clinicas e confirma a importacao.
              </p>
            </div>
            <div className="grid gap-3">
              <MiniMetric icon={<Search size={18} />} label="Resultados" value={candidates.length} />
              <MiniMetric icon={<CheckCircle2 size={18} />} label="Selecionadas" value={selectedCandidates.length} />
              <MiniMetric icon={<Database size={18} />} label="Importadas" value={importData?.created_count ?? 0} />
            </div>
          </div>
        </section>

        <Card className="border-stone-200 bg-white">
          <CardContent className="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_130px_180px_180px] lg:items-end">
            <label className="space-y-2">
              <span className="text-xs font-bold uppercase tracking-[0.16em] text-stone-500">Busca</span>
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Ex.: clinica odontologica em Campinas"
              />
            </label>
            <label className="space-y-2">
              <span className="text-xs font-bold uppercase tracking-[0.16em] text-stone-500">Quantidade</span>
              <Input
                type="number"
                min={1}
                max={20}
                value={limit}
                onChange={(event) => setLimit(Math.max(1, Math.min(Number(event.target.value) || 1, 20)))}
              />
              <span className="block text-xs leading-5 text-stone-500">
                O Google Places limita a busca a 20 resultados por pagina. Para chegar a 100, seriam 5 chamadas e mais custo.
              </span>
            </label>
            <label className="space-y-2">
              <span className="text-xs font-bold uppercase tracking-[0.16em] text-stone-500">Tipo</span>
              <select
                className="h-10 w-full rounded-lg border border-stone-200 bg-white px-3 text-sm font-semibold text-stone-800 outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-100"
                value={includedType}
                onChange={(event) => setIncludedType(event.target.value)}
              >
                <option value="dentist">Dentistas/clinicas odontologicas</option>
                <option value="doctor">Medicos/clinicas medicas</option>
                <option value="none">Sem filtro de tipo</option>
              </select>
            </label>
            <Button
              className="bg-emerald-600 text-white hover:bg-emerald-500"
              onClick={() => searchMutation.mutate(undefined)}
              disabled={searchMutation.isPending || query.trim().length < 3}
            >
              <Search size={16} />
              {searchMutation.isPending ? "Buscando..." : "Buscar"}
            </Button>
          </CardContent>
        </Card>

        {recentQueries.length ? (
          <Card className="border-stone-200 bg-white">
            <CardContent className="space-y-3 p-4">
              <p className="text-xs font-bold uppercase tracking-[0.16em] text-stone-500">Buscas recentes</p>
              <div className="flex flex-wrap gap-2">
                {recentQueries.map((recentQuery) => (
                  <button
                    key={recentQuery}
                    type="button"
                    className="inline-flex items-center rounded-full border border-stone-200 bg-stone-50 px-3 py-1.5 text-sm font-semibold text-stone-700 transition hover:border-emerald-300 hover:bg-emerald-50 hover:text-emerald-800"
                    onClick={() => {
                      setQuery(recentQuery);
                      searchMutation.mutate(recentQuery);
                    }}
                  >
                    {recentQuery}
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>
        ) : null}

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_390px]">
          <section className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-black">Resultados encontrados</h2>
                <p className="text-sm text-stone-600">
                  Selecione quais clinicas vao virar prospects. Duplicadas ficam visiveis, mas nao entram por padrao.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" onClick={selectOnlyAvailable} disabled={!candidates.length}>
                  Selecionar disponiveis
                </Button>
                <Button variant="outline" onClick={() => setSelectedIds([])} disabled={!selectedIds.length}>
                  Limpar selecao
                </Button>
              </div>
            </div>

            {!candidates.length ? (
              <Card className="border-dashed border-stone-300 bg-white">
                <CardContent className="grid min-h-[260px] place-items-center p-8 text-center">
                  <div>
                    <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-emerald-50 text-emerald-700">
                      <MapPin size={24} />
                    </div>
                    <h3 className="mt-4 text-xl font-black">Nenhuma busca feita ainda</h3>
                    <p className="mt-2 max-w-md text-sm leading-6 text-stone-600">
                      Digite cidade, bairro ou nome da clinica e escolha quantos resultados quer puxar.
                    </p>
                  </div>
                </CardContent>
              </Card>
            ) : (
              <div className="grid gap-3">
                {candidates.map((candidate) => {
                  const selected = selectedIds.includes(candidate.place_id);
                  const duplicated = Boolean(candidate.duplicate_prospect_id);
                  return (
                    <Card
                      key={candidate.place_id}
                      className={cn(
                        "border-stone-200 bg-white transition",
                        selected && "border-emerald-300 bg-emerald-50/45 shadow-sm",
                        duplicated && "bg-amber-50/45",
                      )}
                    >
                      <CardContent className="grid gap-4 p-4 lg:grid-cols-[32px_minmax(0,1fr)_auto] lg:items-start">
                        <input
                          type="checkbox"
                          className="mt-1 h-5 w-5 rounded border-stone-300 accent-emerald-600"
                          checked={selected}
                          disabled={duplicated}
                          onChange={() => toggleCandidate(candidate.place_id)}
                          aria-label={`Selecionar ${candidate.name}`}
                        />
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="text-base font-black text-stone-950">{candidate.name}</h3>
                            {candidate.business_status ? (
                              <Badge className={statusBadgeClass(candidate.business_status)}>
                                {candidate.business_status}
                              </Badge>
                            ) : null}
                            {duplicated ? (
                              <Badge className="border-amber-200 bg-amber-100 text-amber-800">Ja existe no CRM</Badge>
                            ) : null}
                          </div>
                          <p className="mt-2 flex items-start gap-2 text-sm leading-6 text-stone-600">
                            <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-stone-400" />
                            <span>{candidate.formatted_address || "Endereco nao retornado na busca economica"}</span>
                          </p>
                          <div className="mt-3 flex flex-wrap gap-2 text-xs font-semibold text-stone-500">
                            <span>{[candidate.city, candidate.state].filter(Boolean).join(" - ") || "Cidade nao identificada"}</span>
                            <span>Place ID: {candidate.place_id}</span>
                            {candidate.duplicate_clinic_name ? <span>Duplicada: {candidate.duplicate_clinic_name}</span> : null}
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-2 lg:justify-end">
                          {candidate.google_maps_url ? (
                            <a
                              href={candidate.google_maps_url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg border border-stone-200 bg-white px-3 text-xs font-bold text-stone-800 transition hover:bg-stone-100"
                            >
                              <ExternalLink size={14} />
                              Maps
                            </a>
                          ) : null}
                        </div>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}
          </section>

          <aside className="space-y-4">
            <Card className="border-stone-200 bg-white">
              <CardContent className="space-y-4 p-5">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.18em] text-stone-500">Importacao</p>
                  <h2 className="mt-1 text-xl font-black">Cadastrar selecionadas</h2>
                  <p className="mt-2 text-sm leading-6 text-stone-600">
                    Detalhes completos serao buscados somente para as clinicas selecionadas.
                  </p>
                </div>

                <label className="flex items-start gap-3 rounded-2xl border border-stone-200 bg-stone-50 p-3">
                  <input
                    type="checkbox"
                    className="mt-1 h-4 w-4 rounded border-stone-300 accent-emerald-600"
                    checked={includeRating}
                    onChange={(event) => setIncludeRating(event.target.checked)}
                  />
                  <span>
                    <span className="block text-sm font-bold text-stone-900">Incluir rating do Google</span>
                    <span className="mt-1 block text-xs leading-5 text-stone-600">
                      Opcional. Pode aumentar custo da chamada de detalhes. Deixe desligado para economizar.
                    </span>
                  </span>
                </label>

                <Button
                  className="w-full bg-stone-950 text-white hover:bg-stone-800"
                  disabled={!canCreateImport || !selectedIds.length || importMutation.isPending}
                  onClick={() => importMutation.mutate()}
                >
                  <Database size={16} />
                  {importMutation.isPending ? "Importando..." : `Cadastrar ${selectedIds.length} clinica(s)`}
                </Button>

                <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm leading-6 text-emerald-900">
                  <div className="mb-2 flex items-center gap-2 font-black">
                    <ShieldCheck size={16} />
                    Economia ativa
                  </div>
                  Busca: campos basicos. Importacao: detalhes so das selecionadas. Reviews nao sao puxados.
                </div>
              </CardContent>
            </Card>

            {importData ? (
              <Card className="border-stone-200 bg-white">
                <CardContent className="space-y-4 p-5">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.18em] text-stone-500">Resultado</p>
                    <h2 className="mt-1 text-xl font-black">
                      {importData.created_count} criadas, {importData.duplicate_count} duplicadas
                    </h2>
                  </div>
                  <div className="space-y-2">
                    {importData.results.map((result) => (
                      <div key={result.place_id} className="rounded-2xl border border-stone-200 bg-stone-50 p-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge className={resultBadgeClass(result.status)}>{result.status}</Badge>
                          <p className="font-bold text-stone-950">{result.prospect?.clinic_name || result.name || result.place_id}</p>
                        </div>
                        <p className="mt-2 text-xs leading-5 text-stone-600">{result.message}</p>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ) : null}

            <Card className="border-amber-200 bg-amber-50">
              <CardContent className="space-y-2 p-4 text-sm leading-6 text-amber-900">
                <div className="flex items-center gap-2 font-black">
                  <AlertTriangle size={16} />
                  Observacao
                </div>
                <p>
                  A chave precisa estar no backend como <strong>GOOGLE_PLACES_API_KEY</strong>. No Render, coloque a
                  mesma variavel no servico da API.
                </p>
              </CardContent>
            </Card>
          </aside>
        </div>
      </div>
    </main>
  );
}

function MiniMetric({ icon, label, value }: { icon: ReactNode; label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-white/15 bg-white/10 p-4 backdrop-blur">
      <div className="flex items-center gap-3">
        <div className="grid h-10 w-10 place-items-center rounded-xl bg-white text-emerald-800">{icon}</div>
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-emerald-100">{label}</p>
          <p className="text-2xl font-black text-white">{value}</p>
        </div>
      </div>
    </div>
  );
}

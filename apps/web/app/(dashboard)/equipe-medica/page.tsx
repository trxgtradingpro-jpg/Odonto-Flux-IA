"use client";

import { ChangeEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ErrorState, LoadingState } from "@/components/page-state";
import { PageHeader, RightDrawer } from "@/components/premium";
import { useOwnerUnitScope } from "@/hooks/use-owner-unit-scope";
import { api } from "@/lib/api";
import { ApiPage, ProfessionalItem, ServiceCatalogItem, UnitItem } from "@/lib/domain-types";
import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@odontoflux/ui";

const WEEK_DAY_OPTIONS = [
  { value: 0, label: "Dom" },
  { value: 1, label: "Seg" },
  { value: 2, label: "Ter" },
  { value: 3, label: "Qua" },
  { value: 4, label: "Qui" },
  { value: 5, label: "Sex" },
  { value: 6, label: "Sab" },
] as const;

const DEFAULT_WORKING_DAYS = [1, 2, 3, 4, 5];

type TeamDataset = {
  professionals: ProfessionalItem[];
  units: UnitItem[];
  serviceCatalog: ServiceCatalogItem[];
};

type ProfessionalDrawerMode = "create" | "edit" | null;

type ProfessionalFormState = {
  fullName: string;
  unitId: string;
  specialty: string;
  croNumber: string;
  shiftStart: string;
  shiftEnd: string;
  procedures: string[];
  workingDays: number[];
  isActive: boolean;
};

function sortTextList(items: string[]): string[] {
  return [...items].sort((left, right) => left.localeCompare(right));
}

function sortWorkingDays(days: number[]): number[] {
  return [...days].sort((left, right) => left - right);
}

function createEmptyProfessionalForm(): ProfessionalFormState {
  return {
    fullName: "",
    unitId: "",
    specialty: "",
    croNumber: "",
    shiftStart: "08:00",
    shiftEnd: "18:00",
    procedures: [],
    workingDays: [...DEFAULT_WORKING_DAYS],
    isActive: true,
  };
}

function createProfessionalFormFromItem(professional: ProfessionalItem): ProfessionalFormState {
  return {
    fullName: professional.full_name || "",
    unitId: professional.unit_id || "",
    specialty: professional.specialty || "",
    croNumber: professional.cro_number || "",
    shiftStart: professional.shift_start || "08:00",
    shiftEnd: professional.shift_end || "18:00",
    procedures: sortTextList(professional.procedures ?? []),
    workingDays: sortWorkingDays(professional.working_days ?? DEFAULT_WORKING_DAYS),
    isActive: professional.is_active !== false,
  };
}

function getApiErrorMessage(error: unknown, fallback: string): string {
  const responseData = (error as { response?: { data?: unknown } })?.response?.data;
  if (responseData && typeof responseData === "object") {
    const apiMessage = (responseData as { error?: { message?: string } })?.error?.message;
    if (typeof apiMessage === "string" && apiMessage.trim()) {
      return apiMessage;
    }
    const directMessage = (responseData as { message?: string })?.message;
    if (typeof directMessage === "string" && directMessage.trim()) {
      return directMessage;
    }
  }
  return fallback;
}

function resolveUnitServices(dataset: TeamDataset, unitId: string): string[] {
  const selectedUnit = dataset.units.find((item) => item.id === unitId);
  return selectedUnit?.services?.length
    ? sortTextList(selectedUnit.services)
    : sortTextList(dataset.serviceCatalog.map((item) => item.name));
}

export default function TeamPage() {
  const queryClient = useQueryClient();
  const ownerUnitScope = useOwnerUnitScope();
  const selectedOwnerUnitId =
    ownerUnitScope.canSwitchUnits && ownerUnitScope.selectedUnitId !== "all"
      ? ownerUnitScope.selectedUnitId
      : null;

  const [drawerMode, setDrawerMode] = useState<ProfessionalDrawerMode>(null);
  const [editingProfessional, setEditingProfessional] = useState<ProfessionalItem | null>(null);
  const [professionalForm, setProfessionalForm] = useState<ProfessionalFormState>(() => createEmptyProfessionalForm());

  const datasetQuery = useQuery<TeamDataset>({
    queryKey: ["team-dataset", selectedOwnerUnitId ?? "all"],
    queryFn: async () => {
      const [professionalsResponse, unitsResponse, serviceCatalogResponse] = await Promise.all([
        api.get<ApiPage<ProfessionalItem>>("/professionals", {
          params: { limit: 300, offset: 0, unit_id: selectedOwnerUnitId ?? undefined },
        }),
        api.get<ApiPage<UnitItem>>("/units", { params: { limit: 100, offset: 0 } }),
        api.get<{ items: ServiceCatalogItem[] }>("/settings/service-catalog/config"),
      ]);

      return {
        professionals: professionalsResponse.data.data ?? [],
        units: unitsResponse.data.data ?? [],
        serviceCatalog: (serviceCatalogResponse.data.items ?? [])
          .filter((item) => item.is_active !== false)
          .sort((left, right) => left.name.localeCompare(right.name)),
      };
    },
    refetchOnWindowFocus: true,
  });

  const closeProfessionalDrawer = () => {
    setDrawerMode(null);
    setEditingProfessional(null);
    setProfessionalForm(createEmptyProfessionalForm());
  };

  const createProfessionalMutation = useMutation({
    mutationFn: async () =>
      api.post("/professionals", {
        full_name: professionalForm.fullName,
        unit_id: professionalForm.unitId || null,
        specialty: professionalForm.specialty || null,
        cro_number: professionalForm.croNumber || null,
        working_days: professionalForm.workingDays,
        shift_start: professionalForm.shiftStart,
        shift_end: professionalForm.shiftEnd,
        procedures: professionalForm.procedures,
        is_active: professionalForm.isActive,
      }),
    onSuccess: () => {
      toast.success("Profissional cadastrado com sucesso.");
      closeProfessionalDrawer();
      queryClient.invalidateQueries({ queryKey: ["team-dataset"] });
      queryClient.invalidateQueries({ queryKey: ["agenda-dataset"] });
    },
    onError: (error) => toast.error(getApiErrorMessage(error, "Nao foi possivel cadastrar o profissional.")),
  });

  const updateProfessionalMutation = useMutation({
    mutationFn: async () => {
      if (!editingProfessional) {
        throw new Error("Profissional nao selecionado para edicao.");
      }
      return api.patch(`/professionals/${editingProfessional.id}`, {
        full_name: professionalForm.fullName,
        unit_id: professionalForm.unitId || null,
        specialty: professionalForm.specialty || null,
        cro_number: professionalForm.croNumber || null,
        working_days: professionalForm.workingDays,
        shift_start: professionalForm.shiftStart,
        shift_end: professionalForm.shiftEnd,
        procedures: professionalForm.procedures,
        is_active: professionalForm.isActive,
      });
    },
    onSuccess: () => {
      toast.success("Profissional atualizado com sucesso.");
      closeProfessionalDrawer();
      queryClient.invalidateQueries({ queryKey: ["team-dataset"] });
      queryClient.invalidateQueries({ queryKey: ["agenda-dataset"] });
    },
    onError: (error) => toast.error(getApiErrorMessage(error, "Nao foi possivel atualizar o profissional.")),
  });

  const deleteProfessionalMutation = useMutation({
    mutationFn: async (professionalId: string) => api.delete(`/professionals/${professionalId}`),
    onSuccess: () => {
      toast.success("Profissional excluido com sucesso.");
      queryClient.invalidateQueries({ queryKey: ["team-dataset"] });
      queryClient.invalidateQueries({ queryKey: ["agenda-dataset"] });
    },
    onError: (error) => toast.error(getApiErrorMessage(error, "Nao foi possivel excluir o profissional.")),
  });

  useEffect(() => {
    if (!ownerUnitScope.canSwitchUnits || drawerMode !== "create" || !datasetQuery.data) return;
    const nextUnitId = ownerUnitScope.selectedUnitId === "all" ? "" : ownerUnitScope.selectedUnitId;
    const nextAvailableServices = resolveUnitServices(datasetQuery.data, nextUnitId);
    setProfessionalForm((current) => {
      if (current.unitId === nextUnitId) return current;
      return {
        ...current,
        unitId: nextUnitId,
        specialty: current.specialty && !nextAvailableServices.includes(current.specialty) ? "" : current.specialty,
        procedures: current.procedures.filter((item) => nextAvailableServices.includes(item)),
      };
    });
  }, [datasetQuery.data, drawerMode, ownerUnitScope.canSwitchUnits, ownerUnitScope.selectedUnitId]);

  const unitsById = useMemo(
    () => new Map((datasetQuery.data?.units ?? []).map((item) => [item.id, item.name])),
    [datasetQuery.data?.units],
  );

  if (datasetQuery.isLoading) return <LoadingState message="Carregando equipe medica..." />;
  if (datasetQuery.isError || !datasetQuery.data) {
    return <ErrorState message="Nao foi possivel carregar a equipe medica." />;
  }

  const visibleUnits =
    selectedOwnerUnitId
      ? datasetQuery.data.units.filter((unit) => unit.id === selectedOwnerUnitId)
      : datasetQuery.data.units;
  const professionals = [...datasetQuery.data.professionals].sort((left, right) =>
    left.full_name.localeCompare(right.full_name),
  );
  const activeProfessionalsCount = professionals.filter((professional) => professional.is_active !== false).length;
  const availableServices = resolveUnitServices(datasetQuery.data, professionalForm.unitId);
  const isDrawerOpen = drawerMode !== null;
  const isEditingProfessional = drawerMode === "edit";
  const isSavingProfessional = createProfessionalMutation.isPending || updateProfessionalMutation.isPending;

  const openCreateProfessionalDrawer = () => {
    setEditingProfessional(null);
    setProfessionalForm({ ...createEmptyProfessionalForm(), unitId: selectedOwnerUnitId ?? "" });
    setDrawerMode("create");
  };

  const openProfessionalEditor = (professional: ProfessionalItem) => {
    setEditingProfessional(professional);
    setProfessionalForm(createProfessionalFormFromItem(professional));
    setDrawerMode("edit");
  };

  const handleUnitChange = (nextUnitId: string) => {
    const nextAvailableServices = resolveUnitServices(datasetQuery.data, nextUnitId);
    setProfessionalForm((current) => ({
      ...current,
      unitId: nextUnitId,
      specialty: current.specialty && !nextAvailableServices.includes(current.specialty) ? "" : current.specialty,
      procedures: current.procedures.filter((item) => nextAvailableServices.includes(item)),
    }));
  };

  const handleSpecialtyChange = (nextSpecialty: string) => {
    setProfessionalForm((current) => ({
      ...current,
      specialty: nextSpecialty,
      procedures:
        nextSpecialty && !current.procedures.includes(nextSpecialty)
          ? sortTextList([...current.procedures, nextSpecialty])
          : current.procedures,
    }));
  };

  const toggleProcedure = (serviceName: string) => {
    setProfessionalForm((current) => {
      const alreadySelected = current.procedures.includes(serviceName);
      if (alreadySelected) {
        return {
          ...current,
          procedures: current.procedures.filter((item) => item !== serviceName),
          specialty: current.specialty === serviceName ? "" : current.specialty,
        };
      }
      return {
        ...current,
        procedures: sortTextList([...current.procedures, serviceName]),
      };
    });
  };

  const toggleWorkingDay = (dayValue: number, checked: boolean) => {
    setProfessionalForm((current) => ({
      ...current,
      workingDays: checked
        ? sortWorkingDays(Array.from(new Set([...current.workingDays, dayValue])))
        : current.workingDays.filter((item) => item !== dayValue),
    }));
  };

  const validateProfessionalForm = () => {
    if (!professionalForm.fullName.trim() || !professionalForm.unitId) {
      toast.error("Informe nome e unidade do profissional.");
      return false;
    }
    if (!availableServices.length) {
      toast.error("Cadastre os servicos da clinica antes de vincular profissionais.");
      return false;
    }
    if (!professionalForm.procedures.length) {
      toast.error("Selecione ao menos um servico para o profissional.");
      return false;
    }
    if (!professionalForm.workingDays.length) {
      toast.error("Selecione ao menos um dia de atendimento.");
      return false;
    }
    if (!professionalForm.shiftStart || !professionalForm.shiftEnd) {
      toast.error("Informe inicio e fim do expediente.");
      return false;
    }
    return true;
  };

  const submitProfessionalForm = () => {
    if (!validateProfessionalForm()) return;
    if (isEditingProfessional) {
      updateProfessionalMutation.mutate();
      return;
    }
    createProfessionalMutation.mutate();
  };

  const drawerTitle = isEditingProfessional
    ? `Editar ${editingProfessional?.full_name ?? "profissional"}`
    : "Cadastrar profissional";
  const drawerDescription = isEditingProfessional
    ? "Atualize unidade, horarios, dias e servicos do profissional cadastrado."
    : "Preencha a ficha do novo profissional. A agenda e a IA passam a usar esse cadastro imediatamente.";

  return (
    <div className="min-w-0 space-y-4">
      <PageHeader
        eyebrow="Estrutura clinica"
        title="Equipe medica"
        description="Cadastre profissionais, dias de atendimento, horarios e servicos. A agenda e a IA usam esses dados."
        actions={
          <Button onClick={openCreateProfessionalDrawer}>
            Cadastrar profissional
          </Button>
        }
        meta={
          <div className="rounded-2xl border border-stone-200 bg-stone-50 px-4 py-3 text-sm text-stone-700">
            <p className="font-semibold text-stone-900">{professionals.length} profissional(is)</p>
            <p className="text-xs text-stone-500">{activeProfessionalsCount} ativo(s) na escala atual</p>
          </div>
        }
      />

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle>Profissionais cadastrados</CardTitle>
        </CardHeader>
        <CardContent>
          {professionals.length ? (
            <div className="grid gap-3 xl:grid-cols-2">
              {professionals.map((professional) => {
                const unitName = professional.unit_id ? unitsById.get(professional.unit_id) : "Sem unidade";
                const days = sortWorkingDays(professional.working_days ?? [])
                  .map((day) => WEEK_DAY_OPTIONS.find((item) => item.value === day)?.label ?? String(day))
                  .join(", ");
                const isDeletingCurrent =
                  deleteProfessionalMutation.isPending && deleteProfessionalMutation.variables === professional.id;
                return (
                  <div
                    key={professional.id}
                    className="rounded-2xl border border-stone-200 bg-white p-4 text-sm text-stone-700 shadow-sm"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="space-y-1">
                        <p className="text-base font-semibold text-stone-900">{professional.full_name}</p>
                        <p className="text-xs text-stone-500">{unitName ?? "Sem unidade"}</p>
                      </div>
                      <span
                        className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                          professional.is_active !== false
                            ? "bg-emerald-50 text-emerald-700"
                            : "bg-stone-100 text-stone-600"
                        }`}
                      >
                        {professional.is_active !== false ? "Ativo" : "Inativo"}
                      </span>
                    </div>

                    <div className="mt-4 grid gap-3 sm:grid-cols-2">
                      <div className="rounded-xl border border-stone-100 bg-stone-50 px-3 py-2">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">Expediente</p>
                        <p className="mt-1 text-sm text-stone-700">
                          {professional.shift_start} as {professional.shift_end}
                        </p>
                      </div>
                      <div className="rounded-xl border border-stone-100 bg-stone-50 px-3 py-2">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500">Dias</p>
                        <p className="mt-1 text-sm text-stone-700">{days || "Sem dias definidos"}</p>
                      </div>
                    </div>

                    <div className="mt-3 space-y-2">
                      <p className="text-xs text-stone-600">
                        <span className="font-semibold text-stone-700">Especialidade:</span>{" "}
                        {professional.specialty?.trim() ? professional.specialty : "Nao definida"}
                      </p>
                      <p className="text-xs text-stone-600">
                        <span className="font-semibold text-stone-700">CRO:</span>{" "}
                        {professional.cro_number?.trim() ? professional.cro_number : "Nao informado"}
                      </p>
                      <p className="text-xs text-stone-600">
                        <span className="font-semibold text-stone-700">Servicos:</span>{" "}
                        {professional.procedures.length ? professional.procedures.join(", ") : "Nao informados"}
                      </p>
                    </div>

                    <div className="mt-4 flex flex-wrap justify-end gap-2 max-sm:[&>*]:w-full">
                      <Button
                        variant="outline"
                        className="h-9 px-3 text-xs"
                        onClick={() => openProfessionalEditor(professional)}
                        disabled={isSavingProfessional}
                      >
                        Editar profissional
                      </Button>
                      <Button
                        variant="destructive"
                        className="h-9 px-3 text-xs"
                        onClick={() => {
                          const confirmed = window.confirm(
                            `Excluir o profissional ${professional.full_name}? Essa acao remove o cadastro.`,
                          );
                          if (!confirmed) return;
                          deleteProfessionalMutation.mutate(professional.id);
                        }}
                        disabled={deleteProfessionalMutation.isPending}
                      >
                        {isDeletingCurrent ? "Excluindo..." : "Excluir profissional"}
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-stone-200 bg-stone-50 px-4 py-8 text-center">
              <p className="text-sm font-medium text-stone-700">Nenhum profissional cadastrado ainda.</p>
              <p className="mt-1 text-xs text-stone-500">
                Clique em <span className="font-medium text-stone-700">Cadastrar profissional</span> para abrir a ficha
                completa.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      <RightDrawer
        open={isDrawerOpen}
        onOpenChange={(open) => {
          if (!open) {
            closeProfessionalDrawer();
          }
        }}
        title={drawerTitle}
        description={drawerDescription}
        widthClassName="w-full sm:max-w-3xl xl:max-w-5xl"
      >
        <div className="space-y-4">
          <Card className="border-stone-200">
            <CardContent className="space-y-5 p-4 sm:p-5">
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.8fr)_320px]">
                <div className="space-y-4">
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="md:col-span-2">
                      <label className="field-label" htmlFor="professional-name">
                        Nome do profissional
                      </label>
                      <Input
                        id="professional-name"
                        value={professionalForm.fullName}
                        onChange={(event: ChangeEvent<HTMLInputElement>) =>
                          setProfessionalForm((current) => ({ ...current, fullName: event.target.value }))
                        }
                      />
                    </div>

                    <div>
                      <label className="field-label" htmlFor="professional-unit">
                        Unidade
                      </label>
                      <select
                        id="professional-unit"
                        className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                        value={professionalForm.unitId}
                        onChange={(event) => handleUnitChange(event.target.value)}
                      >
                        <option value="">Selecione a unidade</option>
                        {visibleUnits.map((unit) => (
                          <option key={unit.id} value={unit.id}>
                            {unit.name}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="field-label" htmlFor="professional-specialty">
                        Especialidade
                      </label>
                      <select
                        id="professional-specialty"
                        className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                        value={professionalForm.specialty}
                        onChange={(event) => handleSpecialtyChange(event.target.value)}
                        disabled={!availableServices.length}
                      >
                        <option value="">
                          {availableServices.length ? "Especialidade (opcional)" : "Cadastre servicos primeiro"}
                        </option>
                        {availableServices.map((serviceName) => (
                          <option key={serviceName} value={serviceName}>
                            {serviceName}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="field-label" htmlFor="professional-cro">
                        CRO
                      </label>
                      <Input
                        id="professional-cro"
                        placeholder="Opcional"
                        value={professionalForm.croNumber}
                        onChange={(event: ChangeEvent<HTMLInputElement>) =>
                          setProfessionalForm((current) => ({ ...current, croNumber: event.target.value }))
                        }
                      />
                    </div>

                    <label className="flex items-center gap-2 rounded-xl border border-stone-200 bg-stone-50 px-3 py-2.5 text-sm text-stone-700">
                      <input
                        type="checkbox"
                        checked={professionalForm.isActive}
                        onChange={(event) =>
                          setProfessionalForm((current) => ({ ...current, isActive: event.target.checked }))
                        }
                      />
                      Profissional ativo
                    </label>
                  </div>

                  <div className="grid gap-4 md:grid-cols-2">
                    <div>
                      <label className="field-label" htmlFor="professional-start">
                        Inicio do expediente
                      </label>
                      <Input
                        id="professional-start"
                        type="time"
                        value={professionalForm.shiftStart}
                        onChange={(event: ChangeEvent<HTMLInputElement>) =>
                          setProfessionalForm((current) => ({ ...current, shiftStart: event.target.value }))
                        }
                      />
                    </div>

                    <div>
                      <label className="field-label" htmlFor="professional-end">
                        Fim do expediente
                      </label>
                      <Input
                        id="professional-end"
                        type="time"
                        value={professionalForm.shiftEnd}
                        onChange={(event: ChangeEvent<HTMLInputElement>) =>
                          setProfessionalForm((current) => ({ ...current, shiftEnd: event.target.value }))
                        }
                      />
                    </div>
                  </div>
                </div>

                <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">
                    Resumo do cadastro
                  </p>
                  <div className="mt-4 space-y-3 text-sm text-stone-700">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Status</p>
                      <p className="mt-1">{professionalForm.isActive ? "Ativo para agendamentos" : "Inativo"}</p>
                    </div>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Dias selecionados</p>
                      <p className="mt-1">{professionalForm.workingDays.length} dia(s) de atendimento</p>
                    </div>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Servicos vinculados</p>
                      <p className="mt-1">{professionalForm.procedures.length} servico(s) habilitado(s)</p>
                    </div>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Observacao</p>
                      <p className="mt-1 text-xs leading-relaxed text-stone-600">
                        Esse mesmo formulario serve tanto para cadastrar quanto para editar, mantendo a agenda e a IA
                        alinhadas com a escala real da clinica.
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">
                      Servicos atendidos
                    </p>
                    <p className="text-xs text-stone-500">
                      Selecione todos os servicos que esse profissional pode realizar.
                    </p>
                  </div>
                  <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-stone-600">
                    {professionalForm.procedures.length} selecionado(s)
                  </span>
                </div>

                {availableServices.length ? (
                  <div className="mt-4 flex max-h-64 flex-wrap gap-2 overflow-y-auto pr-1">
                    {availableServices.map((serviceName) => {
                      const selected = professionalForm.procedures.includes(serviceName);
                      const specialty = professionalForm.specialty === serviceName;
                      return (
                        <button
                          key={serviceName}
                          type="button"
                          className={[
                            "rounded-full border px-3 py-1.5 text-xs transition",
                            selected
                              ? "border-teal-500 bg-teal-50 text-teal-800"
                              : "border-stone-300 bg-white text-stone-700 hover:border-stone-400",
                          ].join(" ")}
                          onClick={() => toggleProcedure(serviceName)}
                        >
                          {serviceName}
                          {specialty ? " - especialidade" : ""}
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <p className="mt-4 text-xs text-amber-700">
                    Nenhum servico foi encontrado no cadastro oficial da clinica. Preencha primeiro em Configuracoes
                    &gt; Servicos.
                  </p>
                )}
              </div>

              <div className="rounded-2xl border border-stone-200 bg-white p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Dias de atendimento</p>
                <p className="mt-1 text-xs text-stone-500">
                  Marque os dias em que o profissional aparece como disponivel para a agenda.
                </p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {WEEK_DAY_OPTIONS.map((day) => {
                    const checked = professionalForm.workingDays.includes(day.value);
                    return (
                      <label
                        key={day.value}
                        className={`inline-flex cursor-pointer items-center gap-2 rounded-full border px-3 py-1.5 text-xs transition ${
                          checked
                            ? "border-primary bg-primary/10 text-primary"
                            : "border-stone-300 bg-white text-stone-700"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(event) => toggleWorkingDay(day.value, event.target.checked)}
                        />
                        {day.label}
                      </label>
                    );
                  })}
                </div>
              </div>

              <div className="flex flex-wrap justify-end gap-2 max-sm:[&>*]:w-full">
                <Button variant="outline" onClick={closeProfessionalDrawer}>
                  Cancelar
                </Button>
                <Button onClick={submitProfessionalForm} disabled={isSavingProfessional}>
                  {isSavingProfessional
                    ? "Salvando..."
                    : isEditingProfessional
                      ? "Salvar alteracoes"
                      : "Cadastrar profissional"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </RightDrawer>
    </div>
  );
}

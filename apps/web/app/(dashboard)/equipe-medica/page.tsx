"use client";

import { ChangeEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { PageHeader } from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { api } from "@/lib/api";
import { ApiPage, ProfessionalItem, UnitItem } from "@/lib/domain-types";
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

type TeamDataset = {
  professionals: ProfessionalItem[];
  units: UnitItem[];
};

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

export default function TeamPage() {
  const queryClient = useQueryClient();

  const [newProfessionalName, setNewProfessionalName] = useState("");
  const [newProfessionalUnitId, setNewProfessionalUnitId] = useState("");
  const [newProfessionalSpecialty, setNewProfessionalSpecialty] = useState("");
  const [newProfessionalCro, setNewProfessionalCro] = useState("");
  const [newProfessionalStart, setNewProfessionalStart] = useState("08:00");
  const [newProfessionalEnd, setNewProfessionalEnd] = useState("18:00");
  const [newProfessionalProcedures, setNewProfessionalProcedures] = useState("");
  const [newProfessionalDays, setNewProfessionalDays] = useState<number[]>([1, 2, 3, 4, 5]);

  const datasetQuery = useQuery<TeamDataset>({
    queryKey: ["team-dataset"],
    queryFn: async () => {
      const [professionalsResponse, unitsResponse] = await Promise.all([
        api.get<ApiPage<ProfessionalItem>>("/professionals", { params: { limit: 300, offset: 0 } }),
        api.get<ApiPage<UnitItem>>("/units", { params: { limit: 100, offset: 0 } }),
      ]);

      return {
        professionals: professionalsResponse.data.data ?? [],
        units: unitsResponse.data.data ?? [],
      };
    },
    refetchOnWindowFocus: true,
  });

  const createProfessionalMutation = useMutation({
    mutationFn: async () => {
      const procedures = newProfessionalProcedures
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);

      return api.post("/professionals", {
        full_name: newProfessionalName,
        unit_id: newProfessionalUnitId || null,
        specialty: newProfessionalSpecialty || null,
        cro_number: newProfessionalCro || null,
        working_days: newProfessionalDays,
        shift_start: newProfessionalStart,
        shift_end: newProfessionalEnd,
        procedures,
        is_active: true,
      });
    },
    onSuccess: () => {
      toast.success("Profissional cadastrado com sucesso.");
      setNewProfessionalName("");
      setNewProfessionalUnitId("");
      setNewProfessionalSpecialty("");
      setNewProfessionalCro("");
      setNewProfessionalStart("08:00");
      setNewProfessionalEnd("18:00");
      setNewProfessionalProcedures("");
      setNewProfessionalDays([1, 2, 3, 4, 5]);
      queryClient.invalidateQueries({ queryKey: ["team-dataset"] });
      queryClient.invalidateQueries({ queryKey: ["agenda-dataset"] });
    },
    onError: (error) => toast.error(getApiErrorMessage(error, "Nao foi possivel cadastrar o profissional.")),
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

  const unitsById = useMemo(
    () => new Map((datasetQuery.data?.units ?? []).map((item) => [item.id, item.name])),
    [datasetQuery.data?.units],
  );

  if (datasetQuery.isLoading) return <LoadingState message="Carregando equipe medica..." />;
  if (datasetQuery.isError || !datasetQuery.data) return <ErrorState message="Nao foi possivel carregar a equipe medica." />;

  const professionals = [...datasetQuery.data.professionals].sort((left, right) =>
    left.full_name.localeCompare(right.full_name),
  );

  return (
    <div className="min-w-0 space-y-4">
      <PageHeader
        eyebrow="Estrutura clinica"
        title="Equipe medica"
        description="Cadastre profissionais, dias de atendimento, horarios e servicos. A agenda e a IA usam esses dados."
      />

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle>Novo profissional</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2 md:grid-cols-4">
            <Input
              placeholder="Nome do profissional"
              value={newProfessionalName}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setNewProfessionalName(event.target.value)}
            />
            <select
              className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm"
              value={newProfessionalUnitId}
              onChange={(event) => setNewProfessionalUnitId(event.target.value)}
            >
              <option value="">Unidade</option>
              {datasetQuery.data.units.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  {unit.name}
                </option>
              ))}
            </select>
            <Input
              placeholder="Especialidade (opcional)"
              value={newProfessionalSpecialty}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setNewProfessionalSpecialty(event.target.value)}
            />
            <Input
              placeholder="CRO (opcional)"
              value={newProfessionalCro}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setNewProfessionalCro(event.target.value)}
            />
          </div>

          <div className="mt-3 grid gap-2 md:grid-cols-3">
            <Input
              type="time"
              value={newProfessionalStart}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setNewProfessionalStart(event.target.value)}
            />
            <Input
              type="time"
              value={newProfessionalEnd}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setNewProfessionalEnd(event.target.value)}
            />
            <Input
              placeholder="Servicos (virgula): avaliacao, lentes, limpeza"
              value={newProfessionalProcedures}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setNewProfessionalProcedures(event.target.value)}
            />
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            {WEEK_DAY_OPTIONS.map((day) => {
              const checked = newProfessionalDays.includes(day.value);
              return (
                <label
                  key={day.value}
                  className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-stone-300 px-3 py-1 text-xs text-stone-700"
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(event) => {
                      if (event.target.checked) {
                        setNewProfessionalDays((current) =>
                          Array.from(new Set([...current, day.value])).sort((left, right) => left - right),
                        );
                      } else {
                        setNewProfessionalDays((current) => current.filter((item) => item !== day.value));
                      }
                    }}
                  />
                  {day.label}
                </label>
              );
            })}
          </div>

          <div className="mt-4 flex items-center justify-between gap-3">
            <p className="text-xs text-stone-500">
              Cadastre cada profissional individualmente. A IA usa essas regras para sugerir e confirmar horarios.
            </p>
            <Button
              onClick={() => {
                if (!newProfessionalName || !newProfessionalUnitId) {
                  toast.error("Informe nome e unidade do profissional.");
                  return;
                }
                if (!newProfessionalDays.length) {
                  toast.error("Selecione ao menos um dia de atendimento.");
                  return;
                }
                createProfessionalMutation.mutate();
              }}
              disabled={createProfessionalMutation.isPending}
            >
              {createProfessionalMutation.isPending ? "Salvando..." : "Cadastrar profissional"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle>Profissionais cadastrados</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {professionals.length ? (
              professionals.map((professional) => {
                const unitName = professional.unit_id ? unitsById.get(professional.unit_id) : "Sem unidade";
                const days = professional.working_days
                  .slice()
                  .sort()
                  .map((day) => WEEK_DAY_OPTIONS.find((item) => item.value === day)?.label ?? String(day))
                  .join(", ");
                const isDeletingCurrent =
                  deleteProfessionalMutation.isPending && deleteProfessionalMutation.variables === professional.id;
                return (
                  <div key={professional.id} className="rounded-md border border-stone-200 bg-white p-3 text-sm text-stone-700">
                    <p className="font-semibold text-stone-800">{professional.full_name}</p>
                    <p className="text-xs text-stone-500">
                      {unitName} - {professional.shift_start} as {professional.shift_end} - {days || "Sem dias"}
                    </p>
                    <p className="mt-1 text-xs text-stone-600">
                      Servicos: {professional.procedures.length ? professional.procedures.join(", ") : "Nao informados"}
                    </p>
                    <div className="mt-2 flex justify-end">
                      <Button
                        variant="destructive"
                        className="h-8 px-2 text-xs"
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
              })
            ) : (
              <p className="text-xs text-stone-500">Nenhum profissional cadastrado ainda.</p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

"use client";

import { ChangeEvent, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { FileUp, UploadCloud } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/premium";
import { api } from "@/lib/api";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@odontoflux/ui";

type ImportResult = {
  dry_run: boolean;
  processed: number;
  created: number;
  skipped: number;
  errors: Array<{ line: number; message: string }>;
};

function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(new Error("Não foi possível ler o arquivo."));
    reader.readAsText(file);
  });
}

export default function ImportacaoPage() {
  const [dryRun, setDryRun] = useState(true);
  const [patientsCsv, setPatientsCsv] = useState("");
  const [leadsCsv, setLeadsCsv] = useState("");
  const [patientsResult, setPatientsResult] = useState<ImportResult | null>(null);
  const [leadsResult, setLeadsResult] = useState<ImportResult | null>(null);

  const importPatientsMutation = useMutation({
    mutationFn: async () =>
      (await api.post<ImportResult>("/patients/import/csv", { csv_content: patientsCsv, dry_run: dryRun })).data,
    onSuccess: (data) => {
      setPatientsResult(data);
      toast.success(dryRun ? "Simulação de pacientes concluída." : "Pacientes importados com sucesso.");
    },
    onError: () => toast.error("Não foi possível importar pacientes."),
  });

  const importLeadsMutation = useMutation({
    mutationFn: async () =>
      (await api.post<ImportResult>("/leads/import/csv", { csv_content: leadsCsv, dry_run: dryRun })).data,
    onSuccess: (data) => {
      setLeadsResult(data);
      toast.success(dryRun ? "Simulação de leads concluída." : "Leads importados com sucesso.");
    },
    onError: () => toast.error("Não foi possível importar leads."),
  });

  async function onFileChange(
    event: ChangeEvent<HTMLInputElement>,
    setter: (text: string) => void,
  ) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const text = await readFileAsText(file);
      setter(text);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Erro ao ler arquivo CSV.";
      toast.error(message);
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Dados"
        title="Importação de base"
        description="Importe pacientes e leads por CSV para acelerar onboarding e início da operação."
      />

      <Card className="border-stone-200">
        <CardContent className="flex items-center justify-between gap-3 p-4">
          <div>
            <p className="text-sm font-semibold text-stone-800">Modo de importação</p>
            <p className="text-xs text-stone-600">
              Use simulação (`dry-run`) para validar erros antes de efetivar os registros.
            </p>
          </div>
          <Button variant={dryRun ? "default" : "outline"} onClick={() => setDryRun((prev) => !prev)}>
            {dryRun ? "Dry-run ativo" : "Dry-run inativo"}
          </Button>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <UploadCloud size={16} />
              Importar pacientes
            </CardTitle>
            <CardDescription>
              Colunas suportadas: `full_name`, `phone`, `email`, `status`, `origin`, `tags`, `unit_code`.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <input type="file" accept=".csv,text/csv" onChange={(event) => onFileChange(event, setPatientsCsv)} />
            <textarea
              value={patientsCsv}
              onChange={(event) => setPatientsCsv(event.target.value)}
              className="h-56 w-full rounded-md border border-stone-300 bg-white p-3 text-xs"
              placeholder="Cole o CSV de pacientes aqui..."
            />
            <Button
              className="gap-2"
              onClick={() => importPatientsMutation.mutate()}
              disabled={!patientsCsv.trim() || importPatientsMutation.isPending}
            >
              <FileUp size={14} />
              {importPatientsMutation.isPending ? "Importando..." : dryRun ? "Simular importação" : "Importar pacientes"}
            </Button>
            {patientsResult ? (
              <div className="rounded-md border border-stone-200 bg-stone-50 p-3 text-xs text-stone-700">
                <p>Processados: {patientsResult.processed}</p>
                <p>Criados: {patientsResult.created}</p>
                <p>Pulados: {patientsResult.skipped}</p>
                <p>Erros: {patientsResult.errors.length}</p>
                {patientsResult.errors.slice(0, 5).map((item) => (
                  <p key={`${item.line}-${item.message}`}>
                    Linha {item.line}: {item.message}
                  </p>
                ))}
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <UploadCloud size={16} />
              Importar leads
            </CardTitle>
            <CardDescription>
              Colunas suportadas: `name`, `phone`, `email`, `interest`, `origin`, `stage`, `temperature`, `score`, `owner_email`.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <input type="file" accept=".csv,text/csv" onChange={(event) => onFileChange(event, setLeadsCsv)} />
            <textarea
              value={leadsCsv}
              onChange={(event) => setLeadsCsv(event.target.value)}
              className="h-56 w-full rounded-md border border-stone-300 bg-white p-3 text-xs"
              placeholder="Cole o CSV de leads aqui..."
            />
            <Button
              className="gap-2"
              onClick={() => importLeadsMutation.mutate()}
              disabled={!leadsCsv.trim() || importLeadsMutation.isPending}
            >
              <FileUp size={14} />
              {importLeadsMutation.isPending ? "Importando..." : dryRun ? "Simular importação" : "Importar leads"}
            </Button>
            {leadsResult ? (
              <div className="rounded-md border border-stone-200 bg-stone-50 p-3 text-xs text-stone-700">
                <p>Processados: {leadsResult.processed}</p>
                <p>Criados: {leadsResult.created}</p>
                <p>Pulados: {leadsResult.skipped}</p>
                <p>Erros: {leadsResult.errors.length}</p>
                {leadsResult.errors.slice(0, 5).map((item) => (
                  <p key={`${item.line}-${item.message}`}>
                    Linha {item.line}: {item.message}
                  </p>
                ))}
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Eye, FileUp } from "lucide-react";
import { toast } from "sonner";

import { DataTable, FilterBar, PageHeader, RightDrawer, StatusBadge } from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { api } from "@/lib/api";
import { ApiPage, DocumentItem, PatientItem, UnitItem, UserItem } from "@/lib/domain-types";
import { formatDateTimeBR } from "@/lib/formatters";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from "@odontoflux/ui";

type DocumentVersion = {
  id: string;
  version_number: number;
  file_name: string;
  mime_type: string;
  size_bytes: number;
  uploaded_at: string;
};

type DocumentPreview = {
  document_id: string;
  file_name: string;
  mime_type: string;
  preview_text: string | null;
  preview_available: boolean;
  truncated?: boolean;
  message?: string;
};

type DocumentsDataset = {
  documents: DocumentItem[];
  patients: PatientItem[];
  units: UnitItem[];
  users: UserItem[];
};

export default function DocumentosPage() {
  const queryClient = useQueryClient();

  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [unitFilter, setUnitFilter] = useState("all");
  const [sensitiveFilter, setSensitiveFilter] = useState("all");

  const [title, setTitle] = useState("");
  const [documentType, setDocumentType] = useState("documento_operacional");
  const [patientId, setPatientId] = useState("");
  const [unitId, setUnitId] = useState("");
  const [isSensitive, setIsSensitive] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const [versionsDrawerOpen, setVersionsDrawerOpen] = useState(false);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);

  const [previewDrawerOpen, setPreviewDrawerOpen] = useState(false);
  const [previewData, setPreviewData] = useState<DocumentPreview | null>(null);

  const docsQuery = useQuery<DocumentsDataset>({
    queryKey: ["documents-dataset"],
    queryFn: async () => {
      const [documentsResponse, patientsResponse, unitsResponse, usersResponse] = await Promise.all([
        api.get<ApiPage<DocumentItem>>("/documents", { params: { limit: 200, offset: 0 } }),
        api.get<ApiPage<PatientItem>>("/patients", { params: { limit: 200, offset: 0 } }),
        api.get<ApiPage<UnitItem>>("/units", { params: { limit: 100, offset: 0 } }),
        api.get<ApiPage<UserItem>>("/users", { params: { limit: 100, offset: 0 } }),
      ]);

      return {
        documents: documentsResponse.data.data ?? [],
        patients: patientsResponse.data.data ?? [],
        units: unitsResponse.data.data ?? [],
        users: usersResponse.data.data ?? [],
      };
    },
  });

  const versionsQuery = useQuery<{ data: DocumentVersion[] }>({
    queryKey: ["document-versions", selectedDocumentId],
    queryFn: async () => (await api.get(`/documents/${selectedDocumentId}/versions`)).data,
    enabled: Boolean(selectedDocumentId && versionsDrawerOpen),
  });

  const createMutation = useMutation({
    mutationFn: async () =>
      (
        await api.post<DocumentItem>("/documents", {
          title,
          document_type: documentType,
          patient_id: patientId || null,
          unit_id: unitId || null,
          is_sensitive: isSensitive,
        })
      ).data,
    onSuccess: async (document) => {
      if (selectedFile) {
        const formData = new FormData();
        formData.append("file", selectedFile);
        await api.post(`/documents/${document.id}/upload`, formData, {
          headers: { "Content-Type": "multipart/form-data" },
        });
      }
      toast.success("Documento salvo com sucesso.");
      setTitle("");
      setDocumentType("documento_operacional");
      setPatientId("");
      setUnitId("");
      setIsSensitive(false);
      setSelectedFile(null);
      queryClient.invalidateQueries({ queryKey: ["documents-dataset"] });
    },
    onError: () => toast.error("Não foi possível salvar o documento."),
  });

  const previewMutation = useMutation({
    mutationFn: async (documentId: string) =>
      (await api.get<DocumentPreview>(`/documents/${documentId}/preview`)).data,
    onSuccess: (data) => {
      setPreviewData(data);
      setPreviewDrawerOpen(true);
    },
    onError: () => toast.error("Não foi possível carregar o preview do documento."),
  });

  const downloadMutation = useMutation({
    mutationFn: async (doc: { id: string; title: string }) => {
      const response = await api.get(`/documents/${doc.id}/download`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${doc.title}.bin`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
    },
    onSuccess: () => toast.success("Download iniciado."),
    onError: () => toast.error("Não foi possível baixar o documento."),
  });

  if (docsQuery.isLoading) return <LoadingState message="Carregando documentos..." />;
  if (docsQuery.isError || !docsQuery.data) return <ErrorState message="Não foi possível carregar documentos." />;

  const patientsById = new Map(docsQuery.data.patients.map((item) => [item.id, item.full_name]));
  const unitsById = new Map(docsQuery.data.units.map((item) => [item.id, item.name]));
  const usersById = new Map(docsQuery.data.users.map((item) => [item.id, item.full_name]));

  const documents = docsQuery.data.documents
    .filter((item) => {
      const term = search.toLowerCase().trim();
      const haystack = `${item.title} ${item.document_type}`.toLowerCase();
      const bySearch = !term || haystack.includes(term);
      const byType = typeFilter === "all" || item.document_type === typeFilter;
      const byUnit = unitFilter === "all" || item.unit_id === unitFilter;
      const bySensitive =
        sensitiveFilter === "all" ||
        (sensitiveFilter === "yes" && item.is_sensitive) ||
        (sensitiveFilter === "no" && !item.is_sensitive);
      return bySearch && byType && byUnit && bySensitive;
    })
    .map((item) => ({
      ...item,
      patient_name: item.patient_id ? patientsById.get(item.patient_id) ?? "Paciente não identificado" : "-",
      unit_name: item.unit_id ? unitsById.get(item.unit_id) ?? "Unidade não identificada" : "-",
      owner_name: item.created_by_user_id ? usersById.get(item.created_by_user_id) ?? "Equipe" : "Equipe",
    }));

  const typeOptions = Array.from(new Set(docsQuery.data.documents.map((item) => item.document_type))).sort();

  const operationalDocs = documents.filter((item) => !item.document_type.includes("consent"));
  const consentDocs = documents.filter((item) => item.document_type.includes("consent"));

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Documental"
        title="Documentos e consentimentos"
        description="Gestão segura de versões, sensibilidade e rastreabilidade documental."
      />

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle>Novo documento</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2 md:grid-cols-6">
            <Input placeholder="Título do documento" value={title} onChange={(event) => setTitle(event.target.value)} />
            <Input
              placeholder="Tipo (ex.: consentimento_operacional)"
              value={documentType}
              onChange={(event) => setDocumentType(event.target.value)}
            />
            <select
              className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm"
              value={patientId}
              onChange={(event) => setPatientId(event.target.value)}
            >
              <option value="">Paciente (opcional)</option>
              {docsQuery.data.patients.map((patient) => (
                <option key={patient.id} value={patient.id}>
                  {patient.full_name}
                </option>
              ))}
            </select>
            <select
              className="h-10 rounded-md border border-stone-300 bg-white px-3 text-sm"
              value={unitId}
              onChange={(event) => setUnitId(event.target.value)}
            >
              <option value="">Unidade (opcional)</option>
              {docsQuery.data.units.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  {unit.name}
                </option>
              ))}
            </select>
            <Input type="file" onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)} />
            <Button
              className="gap-1.5"
              onClick={() => {
                if (!title.trim() || !documentType.trim()) {
                  toast.error("Preencha título e tipo do documento.");
                  return;
                }
                createMutation.mutate();
              }}
              disabled={createMutation.isPending}
            >
              <FileUp size={14} />
              {createMutation.isPending ? "Salvando..." : "Salvar documento"}
            </Button>
          </div>
          <div className="mt-2 flex items-center gap-2 text-sm">
            <input
              id="sensitive-doc"
              type="checkbox"
              checked={isSensitive}
              onChange={(event) => setIsSensitive(event.target.checked)}
            />
            <label htmlFor="sensitive-doc">Documento sensível (LGPD)</label>
          </div>
        </CardContent>
      </Card>

      <FilterBar search={search} onSearchChange={setSearch} searchPlaceholder="Buscar título ou tipo...">
        <select
          className="h-9 rounded-md border border-stone-300 bg-white px-2 text-sm"
          value={typeFilter}
          onChange={(event) => setTypeFilter(event.target.value)}
        >
          <option value="all">Todos os tipos</option>
          {typeOptions.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        <select
          className="h-9 rounded-md border border-stone-300 bg-white px-2 text-sm"
          value={unitFilter}
          onChange={(event) => setUnitFilter(event.target.value)}
        >
          <option value="all">Todas as unidades</option>
          {docsQuery.data.units.map((unit) => (
            <option key={unit.id} value={unit.id}>
              {unit.name}
            </option>
          ))}
        </select>
        <select
          className="h-9 rounded-md border border-stone-300 bg-white px-2 text-sm"
          value={sensitiveFilter}
          onChange={(event) => setSensitiveFilter(event.target.value)}
        >
          <option value="all">Sensível: todos</option>
          <option value="yes">Somente sensíveis</option>
          <option value="no">Somente não sensíveis</option>
        </select>
      </FilterBar>

      <div className="grid gap-4 xl:grid-cols-2">
        <DataTable<(typeof operationalDocs)[number]>
          title="Documentos operacionais"
          rows={operationalDocs}
          getRowId={(item) => item.id}
          searchBy={(item) => `${item.title} ${item.document_type} ${item.unit_name}`}
          columns={[
            { key: "titulo", label: "Título", render: (item) => item.title },
            { key: "tipo", label: "Tipo", render: (item) => item.document_type },
            { key: "paciente", label: "Paciente", render: (item) => item.patient_name },
            { key: "unidade", label: "Unidade", render: (item) => item.unit_name },
            { key: "responsavel", label: "Responsável", render: (item) => item.owner_name },
            {
              key: "sensivel",
              label: "Sensível",
              render: (item) => <StatusBadge value={item.is_sensitive ? "ativo" : "inativo"} />,
            },
            {
              key: "versao",
              label: "Versão atual",
              render: () => "Atual",
            },
            {
              key: "acoes",
              label: "Ações",
              render: (item) => (
                <div className="flex items-center gap-1">
                  <Button
                    variant="outline"
                    className="h-8 px-2 text-xs"
                    onClick={() => previewMutation.mutate(item.id)}
                    disabled={previewMutation.isPending}
                  >
                    <Eye size={13} />
                  </Button>
                  <Button
                    variant="outline"
                    className="h-8 px-2 text-xs"
                    onClick={() => downloadMutation.mutate({ id: item.id, title: item.title })}
                    disabled={downloadMutation.isPending}
                  >
                    <Download size={13} />
                  </Button>
                  <Button
                    variant="outline"
                    className="h-8 px-2 text-xs"
                    onClick={() => {
                      setSelectedDocumentId(item.id);
                      setVersionsDrawerOpen(true);
                    }}
                  >
                    Versões
                  </Button>
                </div>
              ),
            },
          ]}
          emptyTitle="Sem documentos operacionais"
          emptyDescription="Cadastre um novo documento para iniciar o acervo."
        />

        <DataTable<(typeof consentDocs)[number]>
          title="Consentimentos"
          rows={consentDocs}
          getRowId={(item) => item.id}
          searchBy={(item) => `${item.title} ${item.document_type} ${item.patient_name}`}
          columns={[
            { key: "titulo", label: "Título", render: (item) => item.title },
            { key: "tipo", label: "Tipo", render: (item) => item.document_type },
            { key: "paciente", label: "Paciente", render: (item) => item.patient_name },
            { key: "data", label: "Data", render: (item) => formatDateTimeBR(item.created_at) },
            {
              key: "seguranca",
              label: "Segurança",
              render: (item) => (
                <Badge className={item.is_sensitive ? "bg-rose-100 text-rose-700" : "bg-stone-200 text-stone-700"}>
                  {item.is_sensitive ? "Sensível" : "Padrão"}
                </Badge>
              ),
            },
          ]}
          emptyTitle="Sem consentimentos cadastrados"
          emptyDescription="Cadastre consentimentos para reforçar rastreabilidade e compliance."
        />
      </div>

      <RightDrawer
        open={versionsDrawerOpen}
        onOpenChange={setVersionsDrawerOpen}
        title="Histórico de versões"
        description="Rastreabilidade das versões do documento selecionado."
      >
        {versionsQuery.isLoading ? <LoadingState message="Carregando versões..." /> : null}
        {versionsQuery.isError ? <ErrorState message="Não foi possível carregar as versões do documento." /> : null}
        {versionsQuery.data ? (
          <div className="space-y-2">
            {(versionsQuery.data.data ?? []).map((version) => (
              <div key={version.id} className="rounded-lg border border-stone-200 bg-stone-50 p-3">
                <p className="text-sm font-semibold text-stone-800">
                  Versão {version.version_number} • {version.file_name}
                </p>
                <p className="text-xs text-stone-600">
                  {version.mime_type} • {(version.size_bytes / 1024).toFixed(1)} KB
                </p>
                <p className="text-xs text-stone-500">{formatDateTimeBR(version.uploaded_at)}</p>
              </div>
            ))}
          </div>
        ) : null}
      </RightDrawer>

      <RightDrawer
        open={previewDrawerOpen}
        onOpenChange={setPreviewDrawerOpen}
        title="Preview do documento"
        description="Visualização rápida da versão atual do arquivo."
      >
        {previewData ? (
          <Card className="border-stone-200">
            <CardContent className="space-y-2 p-4">
              <p className="text-sm font-semibold text-stone-800">{previewData.file_name}</p>
              <p className="text-xs text-stone-500">{previewData.mime_type}</p>
              {previewData.preview_available ? (
                <pre className="max-h-[420px] overflow-auto rounded-lg border border-stone-200 bg-stone-50 p-3 text-xs text-stone-700">
                  {previewData.preview_text}
                </pre>
              ) : (
                <p className="text-sm text-stone-600">{previewData.message ?? "Preview não disponível."}</p>
              )}
              {previewData.truncated ? (
                <p className="text-xs text-amber-700">Preview parcial exibido para manter performance.</p>
              ) : null}
            </CardContent>
          </Card>
        ) : (
          <p className="text-sm text-stone-500">Selecione um documento para visualizar.</p>
        )}
      </RightDrawer>
    </div>
  );
}

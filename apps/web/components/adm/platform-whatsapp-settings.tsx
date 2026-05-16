"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Radio, ShieldCheck, Smartphone, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/premium/confirm-dialog";
import { StatusBadge } from "@/components/premium";
import { api } from "@/lib/api";
import { maskToken } from "@/lib/formatters";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from "@odontoflux/ui";

type PlatformWhatsAppContext = {
  tenant_id: string;
  tenant_slug: string;
  tenant_trade_name: string;
  tenant_legal_name: string;
  accounts_total: number;
  configured_sender_slug: string;
  uses_default_sender_slug: boolean;
  display_name: string;
};

type PlatformWhatsAppAccountItem = {
  id: string;
  provider_name: "meta_cloud" | "infobip" | "twilio" | string;
  phone_number_id: string;
  business_account_id: string;
  display_phone?: string | null;
  is_active: boolean;
};

type PlatformWhatsAppHealth = {
  status: "ok" | "warning" | "blocked" | string;
  active_account?: PlatformWhatsAppAccountItem | null;
  issues: string[];
  message: string;
  recent_failure?: {
    id: string;
    status: string;
    last_error: string;
    created_at: string;
    updated_at: string;
    is_credit_issue: boolean;
  } | null;
};

type WhatsAppTestResult = {
  status: string;
  webhook_status: string;
  integration_valid: boolean;
  connected_number: string;
  last_event_at: string;
  message: string;
};

function extractApiErrorMessage(error: unknown, fallback: string): string {
  const apiError =
    typeof error === "object" && error && "response" in error
      ? (error as { response?: { data?: { error?: { message?: string; details?: Record<string, unknown> } } } }).response?.data?.error
      : undefined;

  if (apiError && typeof apiError.message === "string") {
    const providerDetail = typeof apiError.details?.provider_detail === "string" ? apiError.details.provider_detail : null;
    const providerHint = typeof apiError.details?.provider_hint === "string" ? apiError.details.provider_hint : null;
    const issues = Array.isArray(apiError.details?.issues)
      ? (apiError.details.issues as unknown[]).filter((item): item is string => typeof item === "string")
      : [];
    const suffix = [providerHint, providerDetail, issues.length ? `Pendencias: ${issues.join("; ")}` : null]
      .filter(Boolean)
      .join(" ");
    return suffix ? `${apiError.message} ${suffix}`.trim() : apiError.message;
  }
  return fallback;
}

export default function PlatformWhatsAppSettings() {
  const queryClient = useQueryClient();
  const [provider, setProvider] = useState<"meta_cloud" | "infobip" | "twilio">("meta_cloud");
  const [phoneNumberId, setPhoneNumberId] = useState("");
  const [businessAccountId, setBusinessAccountId] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [displayPhone, setDisplayPhone] = useState("");
  const [testResult, setTestResult] = useState<WhatsAppTestResult | null>(null);
  const [accountPendingDelete, setAccountPendingDelete] = useState<PlatformWhatsAppAccountItem | null>(null);

  const contextQuery = useQuery<PlatformWhatsAppContext>({
    queryKey: ["adm-platform-whatsapp-context"],
    queryFn: async () => (await api.get("/admin/platform/whatsapp/context")).data,
  });

  const accountsQuery = useQuery<{ data: PlatformWhatsAppAccountItem[] }>({
    queryKey: ["adm-platform-whatsapp-accounts"],
    queryFn: async () => (await api.get("/admin/platform/whatsapp/accounts")).data,
  });

  const healthQuery = useQuery<PlatformWhatsAppHealth>({
    queryKey: ["adm-platform-whatsapp-health"],
    queryFn: async () => (await api.get("/admin/platform/whatsapp/health")).data,
  });

  const activeAccount = healthQuery.data?.active_account ?? null;

  useEffect(() => {
    if (!activeAccount) return;
    setProvider((current) => (current === "meta_cloud" && activeAccount.provider_name !== "meta_cloud"
      ? (activeAccount.provider_name === "infobip" || activeAccount.provider_name === "twilio" ? activeAccount.provider_name : "meta_cloud")
      : current));
    if (!phoneNumberId) setPhoneNumberId(activeAccount.phone_number_id ?? "");
    if (!businessAccountId) setBusinessAccountId(activeAccount.business_account_id ?? "");
    if (!displayPhone) setDisplayPhone(activeAccount.display_phone ?? "");
  }, [activeAccount, businessAccountId, displayPhone, phoneNumberId]);

  const createAccountMutation = useMutation({
    mutationFn: async () =>
      (
        await api.post<PlatformWhatsAppAccountItem>("/admin/platform/whatsapp/accounts", {
          provider_name: provider,
          phone_number_id: phoneNumberId,
          business_account_id: businessAccountId,
          access_token: accessToken,
          display_phone: displayPhone || null,
        })
      ).data,
    onSuccess: () => {
      toast.success("Numero oficial do sistema salvo com sucesso.");
      setAccessToken("");
      queryClient.invalidateQueries({ queryKey: ["adm-platform-whatsapp-context"] });
      queryClient.invalidateQueries({ queryKey: ["adm-platform-whatsapp-accounts"] });
      queryClient.invalidateQueries({ queryKey: ["adm-platform-whatsapp-health"] });
    },
    onError: (error) => toast.error(extractApiErrorMessage(error, "Nao foi possivel salvar o WhatsApp do sistema.")),
  });

  const testAccountMutation = useMutation({
    mutationFn: async () =>
      (
        await api.post<WhatsAppTestResult>("/admin/platform/whatsapp/test", {
          provider_name: provider,
          phone_number_id: phoneNumberId || undefined,
          business_account_id: businessAccountId || undefined,
          access_token: accessToken || undefined,
          display_phone: displayPhone || undefined,
        })
      ).data,
    onSuccess: (data) => {
      setTestResult(data);
      toast.success("Credenciais validadas com sucesso. Agora salve para ativar o numero do sistema.");
      queryClient.invalidateQueries({ queryKey: ["adm-platform-whatsapp-health"] });
    },
    onError: (error) => {
      setTestResult(null);
      toast.error(extractApiErrorMessage(error, "Nao foi possivel validar o WhatsApp do sistema."));
    },
  });

  const deleteAccountMutation = useMutation({
    mutationFn: async (accountId: string) => (await api.delete(`/admin/platform/whatsapp/accounts/${accountId}`)).data,
    onSuccess: (data) => {
      setAccountPendingDelete(null);
      setTestResult(null);
      queryClient.invalidateQueries({ queryKey: ["adm-platform-whatsapp-context"] });
      queryClient.invalidateQueries({ queryKey: ["adm-platform-whatsapp-accounts"] });
      queryClient.invalidateQueries({ queryKey: ["adm-platform-whatsapp-health"] });
      const removedActiveAccount = Boolean(data?.removed_active_account);
      const clearedDemoAssignments = Number(data?.cleared_demo_assignments || 0);
      const extra =
        clearedDemoAssignments > 0 ? ` ${clearedDemoAssignments} demo(s) tiveram o numero desvinculado.` : "";
      toast.success(
        removedActiveAccount
          ? `Numero oficial removido. O WhatsApp do sistema ficara sem numero ativo ate conectar outro.${extra}`
          : `Numero removido da lista com sucesso.${extra}`,
      );
    },
    onError: (error) => {
      toast.error(extractApiErrorMessage(error, "Nao foi possivel apagar o numero do sistema."));
    },
  });

  const isInfobipProvider = provider === "infobip";
  const isTwilioProvider = provider === "twilio";
  const providerDisplayName = isInfobipProvider ? "Infobip" : isTwilioProvider ? "Twilio" : "Meta Cloud API";
  const providerPhoneLabel = isInfobipProvider
    ? "Sender WhatsApp (Infobip)"
    : isTwilioProvider
      ? "Sender WhatsApp (Twilio)"
      : "ID do numero (Meta)";
  const providerBusinessLabel = isInfobipProvider
    ? "Base URL da API Infobip"
    : isTwilioProvider
      ? "Account SID (Twilio)"
      : "ID da conta comercial (Meta)";
  const providerTokenLabel = isInfobipProvider
    ? "Chave API Infobip"
    : isTwilioProvider
      ? "Auth Token (Twilio)"
      : "Token de acesso da Meta";
  const providerPhonePlaceholder = isInfobipProvider
    ? "Ex.: 5511940431906"
    : isTwilioProvider
      ? "Ex.: whatsapp:+5511999999999"
      : "Ex.: 1101713436353674";
  const providerBusinessPlaceholder = isInfobipProvider
    ? "Ex.: 3dd13w.api.infobip.com"
    : isTwilioProvider
      ? "Ex.: ACXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
      : "Ex.: 936994182588219";
  const providerTokenPlaceholder = isInfobipProvider
    ? "Cole a chave App da Infobip"
    : isTwilioProvider
      ? "Cole o Auth Token da Twilio"
      : "Cole o access token da Meta";

  const accounts = accountsQuery.data?.data ?? [];
  const health = healthQuery.data;
  const healthTone =
    health?.status === "ok"
      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
      : health?.status === "warning"
        ? "border-amber-200 bg-amber-50 text-amber-800"
        : "border-rose-200 bg-rose-50 text-rose-800";

  return (
    <div className="space-y-4">
      <Card className="border-stone-200 bg-white">
        <CardHeader className="space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Canal oficial do sistema</p>
              <CardTitle className="mt-1 text-2xl font-black text-stone-950">WhatsApp do ClinicFlux AI</CardTitle>
              <p className="mt-2 max-w-3xl text-sm text-stone-600">
                Esta area configura o numero oficial usado pela plataforma para prospeccao, demonstracoes e operacao do proprio sistema.
                Nenhuma clinica e alterada aqui.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge className="border-stone-200 bg-stone-100 text-stone-700">
                {contextQuery.data?.uses_default_sender_slug ? "Slug padrao do sistema" : "Slug definido no ambiente"}
              </Badge>
              <StatusBadge value={accounts.length ? "ativo" : "inativo"} />
            </div>
          </div>
        </CardHeader>
        <CardContent className="grid gap-3 lg:grid-cols-3">
          <div className="rounded-xl border border-stone-200 bg-stone-50 p-4">
            <div className="flex items-center gap-2 text-stone-900">
              <ShieldCheck size={18} />
              <p className="text-sm font-semibold">Tenant tecnico do sistema</p>
            </div>
            <p className="mt-3 text-lg font-bold text-stone-950">{contextQuery.data?.tenant_trade_name ?? "Carregando..."}</p>
            <p className="mt-1 text-xs text-stone-500">Slug: {contextQuery.data?.tenant_slug ?? "-"}</p>
          </div>
          <div className="rounded-xl border border-stone-200 bg-stone-50 p-4">
            <div className="flex items-center gap-2 text-stone-900">
              <Radio size={18} />
              <p className="text-sm font-semibold">Nome exibido nas abordagens</p>
            </div>
            <p className="mt-3 text-lg font-bold text-stone-950">{contextQuery.data?.display_name ?? "ClinicFlux AI"}</p>
            <p className="mt-1 text-xs text-stone-500">Usado pelo sistema ao iniciar contatos e demonstracoes.</p>
          </div>
          <div className="rounded-xl border border-stone-200 bg-stone-50 p-4">
            <div className="flex items-center gap-2 text-stone-900">
              <Smartphone size={18} />
              <p className="text-sm font-semibold">Numeros conectados</p>
            </div>
            <p className="mt-3 text-lg font-bold text-stone-950">{contextQuery.data?.accounts_total ?? 0}</p>
            <p className="mt-1 text-xs text-stone-500">Sempre que voce salvar uma nova conta, ela vira o canal ativo do sistema.</p>
          </div>
        </CardContent>
      </Card>

      {health ? (
        <Card className="border-stone-200 bg-white">
          <CardContent className="space-y-3 p-4">
            <div className={`rounded-xl border p-4 ${healthTone}`}>
              <div className="flex items-start gap-3">
                <AlertTriangle size={18} className="mt-0.5 shrink-0" />
                <div className="space-y-1 text-sm">
                  <p className="font-semibold">
                    {health.status === "ok" ? "WhatsApp do sistema pronto para operacao" : "Revise o WhatsApp oficial do sistema"}
                  </p>
                  <p>{health.message}</p>
                  {health.issues.length ? <p className="text-xs">Pendencias: {health.issues.join("; ")}</p> : null}
                  {health.recent_failure ? (
                    <p className="text-xs">
                      Ultima falha: {health.recent_failure.last_error || health.recent_failure.status}
                      {health.recent_failure.is_credit_issue ? " (possivel falta de creditos no provedor)" : ""}
                    </p>
                  ) : null}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Card className="border-stone-200 bg-white">
        <CardHeader>
          <CardTitle>Conectar numero oficial ({providerDisplayName})</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-4">
            <div className="space-y-1">
              <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">Provedor</label>
              <select
                className="h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm"
                value={provider}
                onChange={(event) => {
                  const nextProvider = event.target.value;
                  if (nextProvider === "infobip" || nextProvider === "twilio" || nextProvider === "meta_cloud") {
                    setProvider(nextProvider);
                    return;
                  }
                  setProvider("meta_cloud");
                }}
              >
                <option value="meta_cloud">Meta Cloud API</option>
                <option value="infobip">Infobip</option>
                <option value="twilio">Twilio</option>
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">{providerPhoneLabel}</label>
              <Input placeholder={providerPhonePlaceholder} value={phoneNumberId} onChange={(event) => setPhoneNumberId(event.target.value)} />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">{providerBusinessLabel}</label>
              <Input
                placeholder={providerBusinessPlaceholder}
                value={businessAccountId}
                onChange={(event) => setBusinessAccountId(event.target.value)}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold uppercase tracking-wide text-stone-500">{providerTokenLabel}</label>
              <Input placeholder={providerTokenPlaceholder} value={accessToken} onChange={(event) => setAccessToken(event.target.value)} />
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-[1fr_1.2fr]">
            <Input
              placeholder="Numero de exibicao (opcional)"
              value={displayPhone}
              onChange={(event) => setDisplayPhone(event.target.value)}
            />
            <p className="rounded-xl border border-stone-200 bg-stone-50 p-3 text-xs text-stone-600">
              {isInfobipProvider
                ? "Infobip: informe sender aprovado, base URL da conta e App key oficial."
                : isTwilioProvider
                  ? "Twilio: informe sender WhatsApp, Account SID e Auth Token oficial."
                  : "Meta: informe Phone Number ID, Business Account ID e Access Token oficiais da conta do sistema."}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={() => createAccountMutation.mutate()} disabled={createAccountMutation.isPending}>
              {createAccountMutation.isPending ? "Salvando..." : "Salvar numero do sistema"}
            </Button>
            <Button variant="outline" onClick={() => testAccountMutation.mutate()} disabled={testAccountMutation.isPending}>
              {testAccountMutation.isPending ? "Testando..." : "Testar credenciais"}
            </Button>
          </div>
          <p className="text-xs text-stone-500">
            O teste apenas valida as credenciais atuais no provedor. Ele nao salva nem ativa o numero do sistema.
          </p>

          {testResult ? (
            <p className="text-xs text-stone-600">
              {testResult.message}. Numero: {testResult.connected_number}. Webhook: {testResult.webhook_status}. Ultimo evento:{" "}
              {new Date(testResult.last_event_at).toLocaleString("pt-BR")}.
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card className="border-stone-200 bg-white">
        <CardHeader>
          <CardTitle>Numeros conectados ao sistema</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {accountsQuery.isError ? (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
              {extractApiErrorMessage(accountsQuery.error, "Nao foi possivel carregar os numeros do sistema.")}
            </div>
          ) : null}

          {!accountsQuery.isError && !accounts.length ? (
            <div className="rounded-xl border border-dashed border-stone-300 bg-stone-50 p-5 text-sm text-stone-600">
              Nenhum numero oficial conectado ainda. Salve a conta acima para ativar o WhatsApp do sistema.
            </div>
          ) : null}

          {accounts.map((account) => (
            <div key={account.id} className="rounded-xl border border-stone-200 bg-stone-50 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-stone-950">
                    {account.display_phone || "Numero sem exibicao"}{" "}
                    <span className="font-normal text-stone-500">
                      (
                      {account.provider_name === "infobip"
                        ? "Infobip"
                        : account.provider_name === "twilio"
                          ? "Twilio"
                          : "Meta Cloud"}
                      )
                    </span>
                  </p>
                  <p className="mt-1 text-xs text-stone-500">Sender/ID: {maskToken(account.phone_number_id)}</p>
                  <p className="mt-1 text-xs text-stone-500">Conta/URL base: {maskToken(account.business_account_id)}</p>
                </div>
                <div className="flex flex-col items-end gap-2">
                  <StatusBadge value={account.is_active ? "ativo" : "inativo"} />
                  <Button
                    type="button"
                    variant="destructive"
                    className="h-8 px-3"
                    onClick={() => setAccountPendingDelete(account)}
                  >
                    <Trash2 size={14} />
                    Apagar
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={Boolean(accountPendingDelete)}
        onOpenChange={(open) => {
          if (!deleteAccountMutation.isPending) {
            setAccountPendingDelete(open ? accountPendingDelete : null);
          }
        }}
        title="Apagar numero do sistema"
        description={
          accountPendingDelete
            ? accountPendingDelete.is_active
              ? `Deseja apagar ${accountPendingDelete.display_phone || "este numero"}? Ele e o numero ativo do sistema e o canal oficial ficara sem numero conectado ate voce salvar outro.`
              : `Deseja apagar ${accountPendingDelete.display_phone || "este numero"} da lista de numeros conectados ao sistema?`
            : ""
        }
        confirmLabel="Apagar numero"
        cancelLabel="Cancelar"
        destructive
        loading={deleteAccountMutation.isPending}
        onConfirm={() => {
          if (!accountPendingDelete) return;
          deleteAccountMutation.mutate(accountPendingDelete.id);
        }}
      />
    </div>
  );
}

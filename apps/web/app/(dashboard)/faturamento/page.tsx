"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CreditCard } from "lucide-react";
import { toast } from "sonner";

import { PageHeader, StatusBadge } from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { api } from "@/lib/api";
import { currencyFormatter, formatDateBR, formatDateTimeBR, numberFormatter, percentFormatter } from "@/lib/formatters";
import { Button, Card, CardContent, CardHeader, CardTitle } from "@odontoflux/ui";

type InvoiceEvent = {
  id: string;
  status: string;
  amount_cents: number;
  currency: string;
  description: string;
  occurred_at: string;
  provider: string;
  provider_invoice_id?: string | null;
};

type BillingSummary = {
  tenant_name: string;
  subscription_status: string;
  is_active: boolean;
  trial_ends_at: string | null;
  plan: { code: string; name: string; price_cents: number; currency: string };
  usage: { users: number; units: number; monthly_messages: number };
  limits: { users: number | null; units: number | null; monthly_messages: number | null };
  usage_percent: { users: number; units: number; monthly_messages: number };
  billing: {
    provider: string;
    customer_id: string | null;
    last_paid_at: string | null;
    last_failed_at: string | null;
    next_due_at: string | null;
    grace_days: number;
    is_delinquent: boolean;
    days_overdue: number;
    recommended_action: string;
  };
  recent_invoices: InvoiceEvent[];
};

type BillingPlan = {
  id: string;
  code: string;
  name: string;
  max_users: number;
  max_units: number;
  max_monthly_messages: number;
  price_cents: number;
  currency: string;
};

type CheckoutResult = {
  message: string;
  requires_payment: boolean;
  checkout_url: string | null;
  provider: string;
};

function usageValue(current: number, limit: number | null) {
  if (!limit || limit <= 0) return `${numberFormatter.format(current)} / Ilimitado`;
  return `${numberFormatter.format(current)} / ${numberFormatter.format(limit)}`;
}

export default function FaturamentoPage() {
  const queryClient = useQueryClient();

  const summaryQuery = useQuery<BillingSummary>({
    queryKey: ["billing-summary"],
    queryFn: async () => (await api.get("/billing/summary")).data,
  });
  const plansQuery = useQuery<{ data: BillingPlan[] }>({
    queryKey: ["billing-plans"],
    queryFn: async () => (await api.get("/billing/plans")).data,
  });
  const invoicesQuery = useQuery<{ data: InvoiceEvent[] }>({
    queryKey: ["billing-invoices"],
    queryFn: async () => (await api.get("/billing/invoices", { params: { limit: 20 } })).data,
  });

  const checkoutMutation = useMutation({
    mutationFn: async (planCode: string) =>
      (await api.post<CheckoutResult>("/billing/checkout", { plan_code: planCode })).data,
    onSuccess: (payload) => {
      toast.success(payload.message);
      queryClient.invalidateQueries({ queryKey: ["billing-summary"] });
      queryClient.invalidateQueries({ queryKey: ["billing-invoices"] });
      if (payload.requires_payment && payload.checkout_url) {
        window.open(payload.checkout_url, "_blank", "noopener,noreferrer");
      }
    },
    onError: () => toast.error("Nao foi possivel iniciar o checkout."),
  });

  const portalMutation = useMutation({
    mutationFn: async () => (await api.get<{ provider: string; url: string | null; available: boolean }>("/billing/portal")).data,
    onSuccess: (payload) => {
      if (payload.available && payload.url) {
        window.open(payload.url, "_blank", "noopener,noreferrer");
        return;
      }
      toast.error("Portal de pagamento indisponivel.");
    },
    onError: () => toast.error("Nao foi possivel abrir o portal de pagamento."),
  });

  if (summaryQuery.isLoading || plansQuery.isLoading || invoicesQuery.isLoading) {
    return <LoadingState message="Carregando faturamento..." />;
  }
  if (
    summaryQuery.isError ||
    plansQuery.isError ||
    invoicesQuery.isError ||
    !summaryQuery.data ||
    !plansQuery.data ||
    !invoicesQuery.data
  ) {
    return <ErrorState message="Nao foi possivel carregar os dados de faturamento." />;
  }

  const summary = summaryQuery.data;

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Assinatura"
        title="Faturamento e plano"
        description="Checkout de assinatura, controle de inadimplencia e historico de cobranca."
      />

      {summary.billing.is_delinquent ? (
        <Card className="border-rose-200 bg-rose-50">
          <CardContent className="flex items-start gap-3 p-4">
            <AlertTriangle size={18} className="mt-0.5 text-rose-700" />
            <div className="space-y-1">
              <p className="text-sm font-semibold text-rose-800">Atencao: pagamento em atraso</p>
              <p className="text-xs text-rose-700">
                {summary.billing.days_overdue} dia(s) em atraso. Carencia de {summary.billing.grace_days} dia(s).
                Acao recomendada: {summary.billing.recommended_action === "block" ? "regularizar imediatamente" : "notificar financeiro"}.
              </p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CreditCard size={17} />
            Resumo da assinatura
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-md border border-stone-200 bg-stone-50 p-3">
            <p className="text-xs text-stone-500">Clinica</p>
            <p className="text-sm font-semibold text-stone-800">{summary.tenant_name}</p>
          </div>
          <div className="rounded-md border border-stone-200 bg-stone-50 p-3">
            <p className="text-xs text-stone-500">Plano atual</p>
            <p className="text-sm font-semibold text-stone-800">{summary.plan.name}</p>
            <p className="text-xs text-stone-600">{currencyFormatter.format(summary.plan.price_cents / 100)}/mes</p>
          </div>
          <div className="rounded-md border border-stone-200 bg-stone-50 p-3">
            <p className="text-xs text-stone-500">Status</p>
            <StatusBadge value={summary.subscription_status} />
          </div>
          <div className="rounded-md border border-stone-200 bg-stone-50 p-3">
            <p className="text-xs text-stone-500">Proxima cobranca</p>
            <p className="text-sm font-semibold text-stone-800">{formatDateBR(summary.billing.next_due_at)}</p>
            <p className="text-xs text-stone-600">Gateway: {summary.billing.provider || "manual"}</p>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle>Uso de usuarios</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm text-stone-700">
            <p>{usageValue(summary.usage.users, summary.limits.users)}</p>
            <p>{percentFormatter.format(summary.usage_percent.users)}%</p>
          </CardContent>
        </Card>
        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle>Uso de unidades</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm text-stone-700">
            <p>{usageValue(summary.usage.units, summary.limits.units)}</p>
            <p>{percentFormatter.format(summary.usage_percent.units)}%</p>
          </CardContent>
        </Card>
        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle>Mensagens do mes</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm text-stone-700">
            <p>{usageValue(summary.usage.monthly_messages, summary.limits.monthly_messages)}</p>
            <p>{percentFormatter.format(summary.usage_percent.monthly_messages)}%</p>
          </CardContent>
        </Card>
      </div>

      <Card className="border-stone-200">
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <CardTitle>Upgrade de plano</CardTitle>
          <Button variant="outline" onClick={() => portalMutation.mutate()} disabled={portalMutation.isPending}>
            {portalMutation.isPending ? "Abrindo..." : "Abrir portal de pagamento"}
          </Button>
        </CardHeader>
        <CardContent className="grid gap-3 xl:grid-cols-3">
          {plansQuery.data.data.map((plan) => (
            <div key={plan.id} className="rounded-md border border-stone-200 p-3">
              <p className="text-sm font-semibold text-stone-800">{plan.name}</p>
              <p className="text-xs text-stone-600">{currencyFormatter.format(plan.price_cents / 100)}/mes</p>
              <p className="mt-1 text-xs text-stone-600">
                {plan.max_users} usuarios • {plan.max_units} unidades • {numberFormatter.format(plan.max_monthly_messages)} mensagens/mes
              </p>
              <Button
                className="mt-3 h-8 px-3 text-xs"
                variant={summary.plan.code === plan.code ? "outline" : "default"}
                disabled={checkoutMutation.isPending || summary.plan.code === plan.code}
                onClick={() => checkoutMutation.mutate(plan.code)}
              >
                {summary.plan.code === plan.code ? "Plano atual" : "Assinar este plano"}
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle>Historico de cobrancas</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {invoicesQuery.data.data.length ? (
            invoicesQuery.data.data.map((invoice) => (
              <div key={invoice.id} className="flex flex-col gap-1 rounded-md border border-stone-200 p-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="text-sm font-semibold text-stone-800">{invoice.description}</p>
                  <p className="text-xs text-stone-500">{formatDateTimeBR(invoice.occurred_at)}</p>
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge value={invoice.status} />
                  <p className="text-sm font-semibold text-stone-700">
                    {currencyFormatter.format((invoice.amount_cents || 0) / 100)}
                  </p>
                </div>
              </div>
            ))
          ) : (
            <div className="rounded-md border border-stone-200 bg-stone-50 p-3 text-sm text-stone-600">
              Nenhum evento de cobranca registrado.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, CheckCircle2, CircleDashed, HelpCircle, Sparkles, Timer } from "lucide-react";
import { toast } from "sonner";

import { PageHeader, StatusBadge } from "@/components/premium";
import { ErrorState, LoadingState } from "@/components/page-state";
import { api } from "@/lib/api";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@odontoflux/ui";

type OnboardingStep = {
  id: string;
  title: string;
  description: string;
  completed: boolean;
  href: string;
};

type TourStep = {
  id: string;
  title: string;
  description: string;
  href: string;
  duration_minutes: number;
};

type OnboardingStatus = {
  completion_percent: number;
  completed_steps: number;
  total_steps: number;
  next_step: OnboardingStep | null;
  steps: OnboardingStep[];
  tour: {
    title: string;
    description: string;
    estimated_total_minutes: number;
    steps: TourStep[];
  };
  help_resources: Array<{
    id: string;
    title: string;
    description: string;
    href: string;
    cta: string;
  }>;
  faq: Array<{ question: string; answer: string }>;
  support: {
    email: string;
    whatsapp: string;
    hours: string;
  };
};

export default function OnboardingPage() {
  const queryClient = useQueryClient();
  const onboardingQuery = useQuery<OnboardingStatus>({
    queryKey: ["onboarding-status"],
    queryFn: async () => (await api.get("/onboarding/status")).data,
  });

  const completeStepMutation = useMutation({
    mutationFn: async (stepId: string) => api.post("/onboarding/complete", { step_id: stepId }),
    onSuccess: () => {
      toast.success("Etapa atualizada.");
      queryClient.invalidateQueries({ queryKey: ["onboarding-status"] });
    },
    onError: () => toast.error("Nao foi possivel atualizar a etapa."),
  });

  if (onboardingQuery.isLoading) return <LoadingState message="Carregando checklist de onboarding..." />;
  if (onboardingQuery.isError || !onboardingQuery.data) {
    return <ErrorState message="Nao foi possivel carregar o onboarding comercial." />;
  }

  const status = onboardingQuery.data;
  const nextTourStep =
    status.tour.steps.find((step) => step.href === status.next_step?.href) ?? status.tour.steps[0] ?? null;

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Go-live"
        title="Onboarding comercial"
        description="Checklist guiado para ativar clinica, equipe, LGPD e operacao antes da primeira venda."
      />

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles size={18} className="text-primary" />
            Progresso de implantacao
          </CardTitle>
          <CardDescription>
            {status.completed_steps} de {status.total_steps} etapas concluidas.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="h-2 w-full overflow-hidden rounded-full bg-stone-200">
            <div
              className="h-full rounded-full bg-primary transition-all"
              style={{ width: `${Math.max(0, Math.min(status.completion_percent, 100))}%` }}
            />
          </div>
          <p className="text-sm text-stone-600">Concluido: {status.completion_percent.toFixed(1)}%</p>
          {status.next_step ? (
            <div className="rounded-lg border border-primary/25 bg-primary/5 p-3 text-sm">
              <p className="font-semibold text-stone-800">Proxima etapa recomendada</p>
              <p className="text-stone-700">{status.next_step.title}</p>
              <p className="text-xs text-stone-600">{status.next_step.description}</p>
              <Link href={status.next_step.href} className="mt-2 inline-flex text-xs font-semibold text-primary underline">
                Abrir etapa
              </Link>
            </div>
          ) : (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">
              Onboarding concluido. A clinica esta pronta para operacao comercial.
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="border-stone-200 xl:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Timer size={17} />
              {status.tour.title}
            </CardTitle>
            <CardDescription>
              {status.tour.description} Tempo total estimado: {status.tour.estimated_total_minutes} min.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {status.tour.steps.map((tourStep) => (
              <div key={tourStep.id} className="flex items-start justify-between gap-3 rounded-lg border border-stone-200 p-3">
                <div className="space-y-0.5">
                  <p className="text-sm font-semibold text-stone-800">{tourStep.title}</p>
                  <p className="text-xs text-stone-600">{tourStep.description}</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-stone-500">{tourStep.duration_minutes} min</span>
                  <Link href={tourStep.href}>
                    <Button variant="outline" className="h-8 px-3 text-xs">
                      Abrir
                    </Button>
                  </Link>
                </div>
              </div>
            ))}
            {nextTourStep ? (
              <Link href={nextTourStep.href}>
                <Button className="mt-1 h-8 px-3 text-xs">Iniciar tour guiado</Button>
              </Link>
            ) : null}
          </CardContent>
        </Card>

        <Card className="border-stone-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <BookOpen size={16} />
              Ajuda rapida
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {status.help_resources.map((resource) => (
              <div key={resource.id} className="rounded-lg border border-stone-200 p-3">
                <p className="text-sm font-semibold text-stone-800">{resource.title}</p>
                <p className="text-xs text-stone-600">{resource.description}</p>
                <Link href={resource.href} className="mt-2 inline-flex text-xs font-semibold text-primary underline">
                  {resource.cta}
                </Link>
              </div>
            ))}
            <div className="rounded-lg border border-stone-200 bg-stone-50 p-3 text-xs text-stone-600">
              <p className="font-semibold text-stone-700">Suporte de implantacao</p>
              <p>E-mail: {status.support.email}</p>
              <p>WhatsApp: {status.support.whatsapp}</p>
              <p>Horario: {status.support.hours}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        {status.steps.map((step) => (
          <Card key={step.id} className="border-stone-200">
            <CardContent className="space-y-3 p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1">
                  <p className="text-sm font-semibold text-stone-800">{step.title}</p>
                  <p className="text-xs text-stone-600">{step.description}</p>
                </div>
                <StatusBadge value={step.completed ? "concluido" : "pendente"} />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Link href={step.href}>
                  <Button variant="outline" className="h-8 px-3 text-xs">
                    Abrir
                  </Button>
                </Link>
                {!step.completed ? (
                  <Button
                    className="h-8 px-3 text-xs"
                    onClick={() => completeStepMutation.mutate(step.id)}
                    disabled={completeStepMutation.isPending}
                  >
                    <CircleDashed size={14} className="mr-1" />
                    Marcar como concluida
                  </Button>
                ) : (
                  <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700">
                    <CheckCircle2 size={14} />
                    Etapa concluida
                  </span>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="border-stone-200">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <HelpCircle size={16} />
            FAQ de onboarding
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {status.faq.map((item) => (
            <details key={item.question} className="rounded-lg border border-stone-200 p-3">
              <summary className="cursor-pointer text-sm font-semibold text-stone-800">{item.question}</summary>
              <p className="mt-2 text-xs text-stone-600">{item.answer}</p>
            </details>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

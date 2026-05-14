"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@odontoflux/ui";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { type UseFormReturn, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { DemoPreparationScreen } from "@/components/auth/demo-preparation-screen";
import { type DemoPreparationStep } from "@/components/auth/demo-progress";
import { setAccessToken } from "@/lib/auth";
import { api } from "@/lib/api";
import { BRAND_DESCRIPTION, BRAND_NAME, BRAND_TAGLINE } from "@/lib/brand";
import {
  clearDemoGuideSessionState,
  DEMO_GUIDE_AUTOSTART_KEY,
  DEMO_GUIDE_OVERRIDE_KEY,
  DEMO_GUIDE_QUERY_PARAM,
} from "@/lib/demo-guide";
import { ensureDemoSessionId, storeDemoWhatsAppEntry } from "@/lib/demo-session";

const loginSchema = z.object({
  email: z.string().email("Informe um e-mail valido"),
  password: z.string().min(8, "A senha precisa ter pelo menos 8 caracteres"),
});

type LoginForm = z.infer<typeof loginSchema>;
type DemoRedeemResponse = {
  access_token: string;
  refresh_token?: string | null;
  demo_test_phone_number?: string | null;
  demo_whatsapp_link?: string | null;
  demo_target_path?: string | null;
};

type DemoFlowState = "idle" | "redeeming" | "success" | "error";

type DemoQueryState = {
  guideRequested: boolean;
  resolved: boolean;
  token: string | null;
};

const DEMO_MIN_VISIBLE_MS = 1600;
const DEMO_REDIRECT_DELAY_MS = 900;
const DEMO_PROGRESS_LIMIT = 91;
const DEMO_PROGRESS_INTERVAL_MS = 180;
const DEMO_PREPARATION_STEPS: DemoPreparationStep[] = [
  {
    title: "Organizando agenda da clinica",
    detail: "Montando um cenario claro para a apresentacao.",
  },
  {
    title: "Ajustando automacoes de WhatsApp",
    detail: "Deixando mensagens e fluxos prontos.",
  },
  {
    title: "Preparando indicadores principais",
    detail: "Separando o que mais gera percepcao de valor.",
  },
  {
    title: "Liberando sua demonstracao",
    detail: "Seu acesso sera aberto em instantes.",
  },
];

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function getActiveDemoStep(progress: number, phase: DemoFlowState) {
  if (phase === "success") {
    return DEMO_PREPARATION_STEPS.length - 1;
  }

  if (progress >= 78) {
    return 3;
  }

  if (progress >= 55) {
    return 2;
  }

  if (progress >= 28) {
    return 1;
  }

  return 0;
}

function LoginFormCard({
  form,
  isPending,
  onSubmit,
}: {
  form: UseFormReturn<LoginForm>;
  isPending: boolean;
  onSubmit: (values: LoginForm) => void;
}) {
  return (
    <div className="mx-auto w-full max-w-md">
      <Card>
        <CardHeader>
          <p className="text-xs font-semibold uppercase tracking-wide text-primary">{BRAND_NAME}</p>
          <CardTitle className="text-2xl">Entrar na plataforma</CardTitle>
          <p className="text-sm font-medium text-foreground">{BRAND_TAGLINE}</p>
          <p className="text-sm text-muted-foreground">
            Quer apresentar o sistema antes de entrar?{" "}
            <Link href="/apresentacao" className="font-semibold text-primary hover:underline">
              Ver demonstracao
            </Link>
          </p>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)}>
            <div className="space-y-1">
              <label className="text-sm font-medium">E-mail</label>
              <Input type="email" placeholder="voce@clinica.com" {...form.register("email")} />
              {form.formState.errors.email ? (
                <p className="text-xs text-red-600">{form.formState.errors.email.message}</p>
              ) : null}
            </div>

            <div className="space-y-1">
              <label className="text-sm font-medium">Senha</label>
              <Input type="password" placeholder="********" {...form.register("password")} />
              {form.formState.errors.password ? (
                <p className="text-xs text-red-600">{form.formState.errors.password.message}</p>
              ) : null}
            </div>

            <Button className="w-full" type="submit" disabled={isPending}>
              {isPending ? "Entrando..." : "Entrar"}
            </Button>
          </form>

          <div className="mt-4 rounded-md bg-stone-100 p-3 text-xs text-stone-700">
            <p className="mb-2 font-semibold text-stone-900">{BRAND_DESCRIPTION}</p>
            Use credenciais demo: <strong>owner@sorrisosul.com</strong> /{" "}
            <strong>Odonto@123</strong>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const redeemedRef = useRef(false);
  const redirectTimeoutRef = useRef<number | null>(null);
  const [demoState, setDemoState] = useState<DemoFlowState>("idle");
  const [demoProgress, setDemoProgress] = useState(7);
  const [showManualLogin, setShowManualLogin] = useState(false);
  const [demoErrorMessage, setDemoErrorMessage] = useState<string | null>(null);
  const [retrySeed, setRetrySeed] = useState(0);
  const [demoQuery, setDemoQuery] = useState<DemoQueryState>({
    guideRequested: false,
    resolved: false,
    token: null,
  });
  const form = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: "owner@sorrisosul.com",
      password: "Odonto@123",
    },
  });

  const loginMutation = useMutation({
    mutationFn: async (values: LoginForm) => {
      const response = await api.post("/auth/login", values);
      return response.data;
    },
    onSuccess: (data) => {
      setAccessToken(data.access_token, data.refresh_token);
      toast.success("Acesso realizado com sucesso.");
      router.push("/dashboard");
    },
    onError: () => {
      toast.error("Falha no login. Verifique e-mail e senha.");
    },
  });

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setDemoQuery({
      guideRequested: params.get(DEMO_GUIDE_QUERY_PARAM) === "1",
      resolved: true,
      token: params.get("demo_token"),
    });
  }, []);

  useEffect(() => {
    if (
      !demoQuery.resolved ||
      !demoQuery.token ||
      showManualLogin ||
      demoState === "error" ||
      demoState === "success"
    )
      return;

    setDemoState((current) => (current === "success" ? current : "redeeming"));
    setDemoErrorMessage(null);

    const intervalId = window.setInterval(() => {
      setDemoProgress((current) => {
        if (current >= DEMO_PROGRESS_LIMIT) {
          return current;
        }

        if (current < 32) {
          return Math.min(current + 5, DEMO_PROGRESS_LIMIT);
        }

        if (current < 58) {
          return Math.min(current + 3.5, DEMO_PROGRESS_LIMIT);
        }

        if (current < 76) {
          return Math.min(current + 2.1, DEMO_PROGRESS_LIMIT);
        }

        return Math.min(current + 0.8, DEMO_PROGRESS_LIMIT);
      });
    }, DEMO_PROGRESS_INTERVAL_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [demoQuery.resolved, demoQuery.token, demoState, showManualLogin]);

  useEffect(() => {
    if (!demoQuery.resolved || !demoQuery.token || showManualLogin || redeemedRef.current) return;

    redeemedRef.current = true;
    setDemoState("redeeming");
    setDemoProgress(10);
    setDemoErrorMessage(null);

    const currentSession = ensureDemoSessionId();
    const startedAt = performance.now();
    let cancelled = false;

    const runRedemption = async () => {
      try {
        const response = await api.post<DemoRedeemResponse>(
          "/demo/auth/redeem-token",
          { token: demoQuery.token },
          { headers: { "x-demo-session-id": currentSession } },
        );

        const elapsed = performance.now() - startedAt;
        if (elapsed < DEMO_MIN_VISIBLE_MS) {
          await delay(DEMO_MIN_VISIBLE_MS - elapsed);
        }

        if (cancelled) return;

        setAccessToken(response.data.access_token, response.data.refresh_token ?? null);
        const targetPath = response.data.demo_target_path || "/conversas";
        storeDemoWhatsAppEntry({
          testPhoneNumber: response.data.demo_test_phone_number ?? null,
          whatsappLink: response.data.demo_whatsapp_link ?? null,
          targetPath,
        });
        clearDemoGuideSessionState();
        window.sessionStorage.setItem(DEMO_GUIDE_AUTOSTART_KEY, "1");
        window.sessionStorage.setItem(DEMO_GUIDE_OVERRIDE_KEY, "1");

        setDemoProgress(100);
        setDemoState("success");
        toast.success("Demo personalizada liberada.");

        redirectTimeoutRef.current = window.setTimeout(() => {
          window.location.replace(targetPath);
        }, DEMO_REDIRECT_DELAY_MS);
      } catch {
        if (cancelled) return;

        setDemoState("error");
        setDemoProgress((current) => Math.max(current, 24));
        setDemoErrorMessage("O link informado pode ter expirado ou ja foi utilizado.");
        toast.error("Link de demo invalido ou expirado.");
      }
    };

    runRedemption();

    return () => {
      cancelled = true;
      if (redirectTimeoutRef.current) {
        window.clearTimeout(redirectTimeoutRef.current);
        redirectTimeoutRef.current = null;
      }
    };
  }, [
    demoQuery.guideRequested,
    demoQuery.resolved,
    demoQuery.token,
    retrySeed,
    showManualLogin,
  ]);

  const openManualLogin = () => {
    redeemedRef.current = true;
    setShowManualLogin(true);
    setDemoState("idle");
    setDemoErrorMessage(null);
    setDemoProgress(7);
    if (redirectTimeoutRef.current) {
      window.clearTimeout(redirectTimeoutRef.current);
      redirectTimeoutRef.current = null;
    }
    window.history.replaceState({}, "", "/login");
  };

  const retryDemoRedemption = () => {
    redeemedRef.current = false;
    setShowManualLogin(false);
    setDemoState("idle");
    setDemoErrorMessage(null);
    setDemoProgress(9);
    if (redirectTimeoutRef.current) {
      window.clearTimeout(redirectTimeoutRef.current);
      redirectTimeoutRef.current = null;
    }
    setRetrySeed((current) => current + 1);
  };

  const hasDemoToken = Boolean(demoQuery.token);
  const showDemoExperience = demoQuery.resolved && hasDemoToken && !showManualLogin;
  const activeDemoStep = getActiveDemoStep(demoProgress, demoState);

  if (!demoQuery.resolved) {
    return (
      <div className="auth-demo-shell mx-auto flex min-h-[420px] w-full max-w-xl items-center justify-center overflow-hidden rounded-[32px] border border-[#cfe4e7] bg-[#f7fbfb] px-8 py-12 text-slate-900 shadow-[0_30px_120px_rgba(15,55,72,0.14)]">
        <div className="space-y-3 text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.32em] text-[#4d8f96]">
            {BRAND_NAME}
          </p>
          <h1 className="text-2xl font-semibold text-[#12343a] sm:text-3xl">Preparando sua demo</h1>
          <p className="text-sm leading-7 text-slate-600 sm:text-base">Validando seu acesso.</p>
        </div>
      </div>
    );
  }

  if (showDemoExperience) {
    return (
      <DemoPreparationScreen
        activeStep={activeDemoStep}
        errorMessage={demoErrorMessage}
        etaLabel={demoState === "success" ? "Concluido agora" : "Tempo estimado: 10 a 20 segundos"}
        onRetry={retryDemoRedemption}
        onShowManualLogin={openManualLogin}
        phase={demoState}
        progress={demoProgress}
        steps={DEMO_PREPARATION_STEPS}
      />
    );
  }

  return (
    <LoginFormCard
      form={form}
      isPending={loginMutation.isPending}
      onSubmit={(values) => loginMutation.mutate(values)}
    />
  );
}

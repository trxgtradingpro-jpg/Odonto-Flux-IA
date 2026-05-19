"use client";

import { startTransition, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import type { SessionContext } from "@/hooks/use-session";
import { ensureDemoSessionId, readDemoWhatsAppEntry } from "@/lib/demo-session";
import {
  createInitialDemoTourProgress,
  dispatchDemoTourCommand,
  dispatchDemoTourTestAction,
  DEMO_TOUR_EVENT_NAME,
  DEMO_TOUR_TARGETS,
  markDemoTourEventSeen,
  readDemoTourProgress,
  resolveDemoTourIdentity,
  writeDemoTourProgress,
  type DemoTourEventDetail,
  type DemoTourIdentity,
  type DemoTourProgress,
  type DemoTourStep,
} from "@/lib/demo-tour";
import {
  DEMO_GUIDE_AUTOSTART_KEY,
  isDemoGuideFeatureEnabled,
  isDemoGuideOverrideEnabled,
} from "@/lib/demo-guide";

import { FinalCtaCard } from "./final-cta-card";
import { SpotlightOverlay } from "./spotlight-overlay";

type DemoGuidedControllerProps = {
  pathname: string;
  session: SessionContext | undefined;
};

type GuideBroadcastDetail = {
  active: boolean;
  stepId: string | null;
  stepOrder: number | null;
  placement: "centered" | "docked" | null;
  pagePath: string | null;
  title: string | null;
};

type DemoOverlayAction = {
  label: string;
  onClick: () => void;
};

type DemoOverlayConfig = {
  align: "top" | "bottom" | "center" | "left";
  badge: string;
  title: string;
  description: string;
  primaryLabel?: string;
  secondaryLabel?: string;
  statusLabel?: string;
  testActions?: DemoOverlayAction[];
  compact?: boolean;
  showTargetFrame?: boolean;
  primaryLoading?: boolean;
  visualState?: "idle" | "exiting";
};

const BREATHING_DELAY_MS = 3_400;
const AGENDA_ROUTE_DELAY_MS = 1_200;
const WHATSAPP_PREOPEN_COUNTDOWN_SECONDS = 7;
const WHATSAPP_LAUNCH_EXIT_MS = 240;

const STEP_ORDER: DemoTourStep[] = [
  "breathing",
  "spotlight_whatsapp",
  "spotlight_conversation",
  "spotlight_ai_intent",
  "spotlight_ai_response",
  "waiting_appointment",
  "appointment_detected",
  "spotlight_agenda",
  "spotlight_dashboard",
  "completed",
];

function findTargetElement(targetId: string | null) {
  if (!targetId || typeof document === "undefined") return null;
  return document.querySelector<HTMLElement>(`[data-tour-id="${targetId}"]`);
}

function findTargetRect(targetId: string | null) {
  return findTargetElement(targetId)?.getBoundingClientRect() ?? null;
}

function isActiveStatus(progress: DemoTourProgress) {
  return progress.status === "active";
}

export function GuidedDemoController({ pathname, session }: DemoGuidedControllerProps) {
  const router = useRouter();
  const isDemoUser = (session?.roles ?? []).includes("demo_client");
  const featureEnabled = isDemoGuideFeatureEnabled() || isDemoGuideOverrideEnabled();
  const [identity, setIdentity] = useState<DemoTourIdentity | null>(null);
  const [progress, setProgress] = useState<DemoTourProgress>(() => createInitialDemoTourProgress());
  const [viewportTick, setViewportTick] = useState(0);
  const [whatsappLaunchState, setWhatsappLaunchState] = useState<"idle" | "loading" | "exiting">("idle");
  const [whatsappLaunchCountdown, setWhatsappLaunchCountdown] = useState<number | null>(null);
  const progressRef = useRef(progress);
  const bootstrapKeyRef = useRef<string | null>(null);
  const launchTimerIdsRef = useRef<number[]>([]);
  const launchIntervalIdRef = useRef<number | null>(null);
  const whatsappPopupRef = useRef<Window | null>(null);

  const clearLaunchTimers = () => {
    for (const timerId of launchTimerIdsRef.current) {
      window.clearTimeout(timerId);
    }
    launchTimerIdsRef.current = [];
    if (launchIntervalIdRef.current !== null) {
      window.clearInterval(launchIntervalIdRef.current);
      launchIntervalIdRef.current = null;
    }
  };

  useEffect(() => {
    progressRef.current = progress;
    writeDemoTourProgress(identity, progress);
  }, [identity, progress]);

  useEffect(() => () => clearLaunchTimers(), []);

  const updateProgress = (recipe: (current: DemoTourProgress) => DemoTourProgress) => {
    setProgress((current) => ({
      ...recipe(current),
      updatedAt: new Date().toISOString(),
    }));
  };

  const goToStep = (
    step: DemoTourStep,
    status: DemoTourProgress["status"] = "active",
    contextPatch: Partial<DemoTourProgress["context"]> = {},
  ) => {
    updateProgress((current) => ({
      ...current,
      status,
      step,
      lastActiveStep: status === "active" ? step : current.lastActiveStep,
      context: {
        ...current.context,
        ...contextPatch,
      },
    }));
  };

  useEffect(() => {
    if (!isDemoUser) return;
    const sessionId = ensureDemoSessionId();
    setIdentity(resolveDemoTourIdentity(session, sessionId));
  }, [isDemoUser, session]);

  useEffect(() => {
    if (!identity || !featureEnabled || !isDemoUser) return;

    const bootstrapKey = `${identity.tenantId}:${identity.userId}:${identity.sessionId}`;
    if (bootstrapKeyRef.current === bootstrapKey) return;
    bootstrapKeyRef.current = bootstrapKey;

    const entry = readDemoWhatsAppEntry();
    const autostartRequested =
      typeof window !== "undefined" && window.sessionStorage.getItem(DEMO_GUIDE_AUTOSTART_KEY) === "1";
    const shouldBootstrap =
      autostartRequested ||
      entry.active ||
      entry.stage === "awaiting_appointment" ||
      entry.stage === "appointment_ready";
    const saved = readDemoTourProgress(identity);
    const shouldReuseSavedProgress =
      Boolean(saved) &&
      (!shouldBootstrap || saved?.status !== "idle" || saved?.step !== "idle" || Boolean(saved?.lastActiveStep));

    if (saved && shouldReuseSavedProgress) {
      setProgress(saved);
      return;
    }

    if (!shouldBootstrap) {
      setProgress(
        createInitialDemoTourProgress({
          phoneLabel: entry.testPhoneNumber || null,
          whatsappLink: entry.whatsappLink || null,
          entryChannel: entry.entryChannel || (entry.whatsappLink ? "whatsapp" : null),
          publicEntryPath: entry.publicEntryPath || null,
        }),
      );
      return;
    }

    if (typeof window !== "undefined") {
      window.sessionStorage.removeItem(DEMO_GUIDE_AUTOSTART_KEY);
    }

    const initialStep: DemoTourStep =
      entry.stage === "appointment_ready"
        ? "appointment_detected"
        : entry.stage === "awaiting_appointment"
          ? "spotlight_whatsapp"
          : "breathing";

    setProgress({
      ...createInitialDemoTourProgress({
        whatsappLink: entry.whatsappLink || null,
        phoneLabel: entry.testPhoneNumber || null,
        entryChannel: entry.entryChannel || (entry.whatsappLink ? "whatsapp" : null),
        publicEntryPath: entry.publicEntryPath || null,
        conversationId: entry.trackedConversationId || null,
        patientId: entry.trackedPatientId || null,
        waitingStartedAt: null,
      }),
      step: initialStep,
      status: "active",
      lastActiveStep: initialStep,
    });
  }, [featureEnabled, identity, isDemoUser]);

  useEffect(() => {
    if (!identity || !featureEnabled || !isDemoUser) return;
    if (!isActiveStatus(progressRef.current)) return;
    if (progressRef.current.step === "completed") return;

    const shouldStayInConversations =
      progressRef.current.step === "breathing" ||
      progressRef.current.step === "spotlight_whatsapp" ||
      progressRef.current.step === "spotlight_conversation" ||
      progressRef.current.step === "spotlight_ai_intent" ||
      progressRef.current.step === "spotlight_ai_response" ||
      progressRef.current.step === "waiting_appointment";

    if (shouldStayInConversations && pathname !== "/conversas") {
      startTransition(() => router.replace("/conversas"));
    }
  }, [featureEnabled, identity, isDemoUser, pathname, router]);

  useEffect(() => {
    if (!featureEnabled || !isDemoUser || !isActiveStatus(progress)) return;

    if (progress.step === "breathing") {
      const timerId = window.setTimeout(() => {
        updateProgress((current) => {
          if (current.step !== "breathing" || current.status !== "active") return current;
          return {
            ...current,
            step: "spotlight_whatsapp",
            lastActiveStep: "spotlight_whatsapp",
          };
        });
      }, BREATHING_DELAY_MS);
      return () => window.clearTimeout(timerId);
    }

    if (progress.step === "appointment_detected" && pathname !== "/agenda") {
      const timerId = window.setTimeout(() => {
        startTransition(() => router.replace("/agenda"));
      }, AGENDA_ROUTE_DELAY_MS);
      return () => window.clearTimeout(timerId);
    }

    if (
      progress.step === "appointment_detected" &&
      pathname === "/agenda" &&
      findTargetElement(DEMO_TOUR_TARGETS.agendaAppointment)
    ) {
      updateProgress((current) => {
        if (current.step !== "appointment_detected" || current.status !== "active") return current;
        return {
          ...current,
          step: "spotlight_agenda",
          lastActiveStep: "spotlight_agenda",
        };
      });
    }
  }, [featureEnabled, isDemoUser, pathname, progress, router]);

  useEffect(() => {
    if (!identity || !featureEnabled || !isDemoUser) return;

    const handleEvent = (event: Event) => {
      const detail = (event as CustomEvent<DemoTourEventDetail>).detail;
      if (!detail) return;

      updateProgress((current) => {
        let next = markDemoTourEventSeen(current, detail);

        if (next.status !== "active") {
          return next;
        }

        if (detail.type === "conversation_detected" && ["spotlight_whatsapp", "breathing"].includes(next.step)) {
          next = {
            ...next,
            step: "spotlight_conversation",
            lastActiveStep: "spotlight_conversation",
            context: {
              ...next.context,
              waitingStartedAt: null,
            },
          };
        }

        if (detail.type === "appointment_detected" && ["waiting_appointment", "spotlight_ai_response"].includes(next.step)) {
          next = {
            ...next,
            step: "appointment_detected",
            lastActiveStep: "appointment_detected",
            context: {
              ...next.context,
              waitingStartedAt: null,
            },
          };
        }

        if (detail.type === "agenda_ready" && next.step === "appointment_detected") {
          next = {
            ...next,
            step: "spotlight_agenda",
            lastActiveStep: "spotlight_agenda",
          };
        }

        return next;
      });
    };

    window.addEventListener(DEMO_TOUR_EVENT_NAME, handleEvent as EventListener);
    return () => window.removeEventListener(DEMO_TOUR_EVENT_NAME, handleEvent as EventListener);
  }, [featureEnabled, identity, isDemoUser]);

  useEffect(() => {
    if (progress.step !== "spotlight_whatsapp") {
      setWhatsappLaunchState("idle");
      setWhatsappLaunchCountdown(null);
    }
  }, [progress.step]);

  const isWebchatEntry = progress.context.entryChannel === "webchat";

  const activeTargetId = useMemo(() => {
    if (progress.step === "spotlight_whatsapp") return DEMO_TOUR_TARGETS.whatsappButton;
    if (progress.step === "spotlight_conversation") {
      return DEMO_TOUR_TARGETS.conversationItem;
    }
    if (progress.step === "waiting_appointment") {
      return DEMO_TOUR_TARGETS.conversationThread;
    }
    if (progress.step === "spotlight_ai_intent") return DEMO_TOUR_TARGETS.aiIntent;
    if (progress.step === "spotlight_ai_response") return DEMO_TOUR_TARGETS.conversationPanel;
    if (progress.step === "spotlight_agenda" || progress.step === "appointment_detected") {
      return DEMO_TOUR_TARGETS.agendaAppointment;
    }
    if (progress.step === "spotlight_dashboard") return DEMO_TOUR_TARGETS.dashboardMetrics;
    return null;
  }, [progress.step]);

  const showOverlay =
    progress.status === "active" &&
    progress.step !== "idle" &&
    progress.step !== "completed" &&
    !(progress.step === "appointment_detected" && pathname === "/agenda");

  useEffect(() => {
    if (!showOverlay) return;

    const handleViewportChange = () => setViewportTick((current) => current + 1);
    window.addEventListener("resize", handleViewportChange);
    window.addEventListener("scroll", handleViewportChange, true);
    return () => {
      window.removeEventListener("resize", handleViewportChange);
      window.removeEventListener("scroll", handleViewportChange, true);
    };
  }, [showOverlay]);

  const targetRect = findTargetRect(activeTargetId);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const detail: GuideBroadcastDetail = {
      active:
        isDemoUser &&
        featureEnabled &&
        progress.status === "active" &&
        progress.step !== "idle" &&
        progress.step !== "completed",
      stepId: progress.status === "active" ? progress.step : null,
      stepOrder: STEP_ORDER.indexOf(progress.step) >= 0 ? STEP_ORDER.indexOf(progress.step) + 1 : null,
      placement: progress.status === "active" ? "centered" : null,
      pagePath: pathname,
      title: progress.step,
    };

    const scopedWindow = window as Window & { __odontofluxDemoGuideState?: GuideBroadcastDetail };
    scopedWindow.__odontofluxDemoGuideState = detail;
    window.dispatchEvent(new CustomEvent("odontoflux:demo-guide-state", { detail }));
  }, [featureEnabled, isDemoUser, pathname, progress.status, progress.step]);

  const handleSimulateMessage = () => {
    dispatchDemoTourTestAction({ action: "simulate_message" });
  };

  const handleSimulateCompleteConversation = () => {
    dispatchDemoTourTestAction({ action: "simulate_complete_conversation" });
  };

  const handlePrimaryAction = () => {
    if (progress.step === "spotlight_whatsapp") {
      if (isWebchatEntry) {
        const publicEntryPath = progress.context.publicEntryPath;
        if (!publicEntryPath) return;
        dispatchDemoTourCommand({ type: "open_whatsapp", popup: null });
        return;
      }

      if (whatsappLaunchState !== "idle") return;

      if (!whatsappPopupRef.current || whatsappPopupRef.current.closed) {
        whatsappPopupRef.current = window.open("", "_blank");
      }
      if (whatsappPopupRef.current && !whatsappPopupRef.current.closed) {
        whatsappPopupRef.current.document.title = "Abrindo WhatsApp da demo";
        whatsappPopupRef.current.document.body.innerHTML =
          "<div style=\"font-family:Arial,sans-serif;padding:24px;line-height:1.5;color:#0f172a;\">" +
          "<h1 style=\"font-size:20px;margin-bottom:12px;\">Abrindo WhatsApp da demo...</h1>" +
          "<p>Voce sera redirecionado em instantes. Deixe esta aba aberta.</p>" +
          "</div>";
      }

      clearLaunchTimers();
      setWhatsappLaunchState("loading");
      setWhatsappLaunchCountdown(WHATSAPP_PREOPEN_COUNTDOWN_SECONDS);

      launchIntervalIdRef.current = window.setInterval(() => {
        setWhatsappLaunchCountdown((current) => {
          if (current === null) return current;

          if (current <= 1) {
            if (launchIntervalIdRef.current !== null) {
              window.clearInterval(launchIntervalIdRef.current);
              launchIntervalIdRef.current = null;
            }

            setWhatsappLaunchState("exiting");
            const exitTimerId = window.setTimeout(() => {
              dispatchDemoTourCommand({ type: "open_whatsapp", popup: whatsappPopupRef.current });
              setWhatsappLaunchState("idle");
              setWhatsappLaunchCountdown(null);
              launchTimerIdsRef.current = launchTimerIdsRef.current.filter((timerId) => timerId !== exitTimerId);
            }, WHATSAPP_LAUNCH_EXIT_MS);

            launchTimerIdsRef.current.push(exitTimerId);
            return 0;
          }

          return current - 1;
        });
      }, 1_000);

      return;
    }

    if (progress.step === "spotlight_conversation") {
      goToStep("spotlight_ai_intent");
      return;
    }

    if (progress.step === "spotlight_ai_intent") {
      goToStep("spotlight_ai_response");
      return;
    }

    if (progress.step === "spotlight_ai_response") {
      if (progress.seenEvents.appointment_detected) {
        goToStep("appointment_detected");
        return;
      }
      goToStep("waiting_appointment");
      return;
    }

    if (progress.step === "spotlight_agenda") {
      goToStep("spotlight_dashboard");
      startTransition(() => router.push("/dashboard"));
      return;
    }

    if (progress.step === "spotlight_dashboard") {
      goToStep("completed", "completed");
    }
  };

  const currentOverlay = useMemo<DemoOverlayConfig | null>(() => {
    const initialTestActions: DemoOverlayAction[] = [
      { label: "Teste sem WhatsApp", onClick: handleSimulateMessage },
      { label: "Criar conversa + agenda", onClick: handleSimulateCompleteConversation },
    ];
    const hasRealWhatsAppLink = Boolean(progress.context.whatsappLink);
    const canOpenWebchatEntry = isWebchatEntry && Boolean(progress.context.publicEntryPath);

    switch (progress.step) {
      case "spotlight_whatsapp":
        return {
          align: "center",
          badge: isWebchatEntry ? "Webchat publico" : hasRealWhatsAppLink ? "Conversa real" : "Teste guiado",
          title: isWebchatEntry
            ? "Teste o webchat publico da demo"
            : hasRealWhatsAppLink
              ? "Teste como paciente"
              : "Esta demo ainda nao tem um numero real conectado",
          description:
            isWebchatEntry
              ? "Abra o webchat publico embutido na mesma tela e envie uma mensagem. A conversa deve aparecer aqui em tempo real."
              : hasRealWhatsAppLink
              ? "Abra o WhatsApp da demo e envie uma mensagem simples, como se fosse um paciente querendo agendar."
              : "Use um dos testes guiados abaixo ou conecte um numero real da clinica dentro do tenant da demo. O numero de teste do /adm identifica quem vai testar, mas nao e o numero da clinica.",
          primaryLabel: isWebchatEntry
            ? canOpenWebchatEntry
              ? "Abrir webchat"
              : undefined
            : hasRealWhatsAppLink
            ? whatsappLaunchState === "loading"
              ? "Abrindo WhatsApp"
              : "Abrir WhatsApp"
            : undefined,
          statusLabel:
            hasRealWhatsAppLink && whatsappLaunchCountdown !== null
              ? `Abrindo WhatsApp em ${String(whatsappLaunchCountdown).padStart(2, "0")}s`
              : undefined,
          compact: false,
          primaryLoading: whatsappLaunchState === "loading",
          visualState: whatsappLaunchState === "exiting" ? "exiting" : "idle",
          showTargetFrame: false,
          testActions: initialTestActions,
        };
      case "spotlight_conversation":
        return {
          align: "top",
          badge: "Nova conversa",
          title: "Nova conversa recebida",
          description: "A nova conversa apareceu na lista em tempo real, pronta para atendimento.",
          primaryLabel: "Continuar",
          compact: true,
        };
      case "spotlight_ai_intent":
        return {
          align: "bottom",
          badge: "Leitura da IA",
          title: "A IA entendeu o motivo do contato.",
          description: "As tags e o contexto operacional j\u00e1 aparecem organizados para a equipe.",
          primaryLabel: "Entendi",
          compact: true,
        };
      case "spotlight_ai_response":
        return {
          align: "left",
          badge: "Resposta automatizada",
          title: "A IA respondeu com base nos dados reais da cl\u00ednica.",
          description: "Agora a conversa parece viva, autom\u00e1tica e pronta para avan\u00e7ar at\u00e9 o agendamento.",
          primaryLabel: progress.seenEvents.appointment_detected ? "Ver agenda" : "Continuar",
          compact: true,
        };
      case "waiting_appointment":
        return {
          align: "center",
          badge: "Pr\u00f3ximo passo",
          title: "Finalize um agendamento para atualizar a agenda ao vivo.",
          description: "Quando o hor\u00e1rio for confirmado, vamos abrir a agenda automaticamente.",
          compact: false,
          showTargetFrame: false,
          testActions: [{ label: "Criar conversa + agenda", onClick: handleSimulateCompleteConversation }],
        };
      case "appointment_detected":
        return {
          align: "center",
          badge: "Agendamento criado",
          title: "Seu agendamento j\u00e1 virou opera\u00e7\u00e3o real.",
          description: "Estamos abrindo a agenda para mostrar o hor\u00e1rio reservado em tempo real.",
          compact: false,
          showTargetFrame: false,
        };
      case "spotlight_agenda":
        return {
          align: "top",
          badge: "Agenda atualizada",
          title: "O agendamento foi criado automaticamente.",
          description: "A equipe não precisa repetir esse trabalho manualmente.",
          primaryLabel: "Ver dashboard",
          compact: true,
        };
      case "spotlight_dashboard":
        return {
          align: "top",
          badge: "Opera\u00e7\u00e3o consolidada",
          title: "Acompanhe a opera\u00e7\u00e3o em tempo real.",
          description: "Aqui a cl\u00ednica enxerga velocidade, fila e produtividade na mesma tela.",
          primaryLabel: "Encerrar",
          compact: true,
        };
      default:
        return null;
    }
  }, [
    isWebchatEntry,
    progress.context.whatsappLink,
    progress.context.publicEntryPath,
    progress.seenEvents.appointment_detected,
    progress.step,
    whatsappLaunchCountdown,
    whatsappLaunchState,
  ]);

  if (!featureEnabled || !isDemoUser) {
    return null;
  }

  return (
    <>
      {showOverlay && currentOverlay ? (
        <SpotlightOverlay
          key={progress.step}
          rect={targetRect}
          badge={currentOverlay.badge}
          title={currentOverlay.title}
          description={currentOverlay.description}
          primaryLabel={currentOverlay.primaryLabel}
          secondaryLabel={currentOverlay.secondaryLabel}
          statusLabel={currentOverlay.statusLabel}
          testActions={currentOverlay.testActions}
          align={currentOverlay.align}
          compact={currentOverlay.compact ?? !targetRect}
          showTargetFrame={currentOverlay.showTargetFrame ?? Boolean(targetRect)}
          primaryLoading={currentOverlay.primaryLoading}
          visualState={currentOverlay.visualState}
          onPrimaryAction={currentOverlay.primaryLabel ? handlePrimaryAction : undefined}
        />
      ) : null}

      {progress.status === "completed" ? <FinalCtaCard /> : null}
    </>
  );
}

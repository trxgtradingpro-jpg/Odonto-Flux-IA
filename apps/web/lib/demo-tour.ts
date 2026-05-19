"use client";

import type { SessionContext } from "@/hooks/use-session";

export const DEMO_TOUR_EVENT_NAME = "odontoflux:demo-tour-event";
export const DEMO_TOUR_TEST_ACTION_EVENT_NAME = "odontoflux:demo-tour-test-action";
export const DEMO_TOUR_COMMAND_EVENT_NAME = "odontoflux:demo-tour-command";
export const DEMO_WEBCHAT_WORKSPACE_EVENT_NAME = "odontoflux:demo-webchat-workspace";
export const DEMO_TOUR_STORAGE_PREFIX = "odontoflux_demo_tour";

export const DEMO_TOUR_TARGETS = {
  whatsappButton: "demo-tour-whatsapp-button",
  conversationItem: "demo-tour-conversation-item",
  conversationPanel: "demo-tour-conversation-panel",
  conversationThread: "demo-tour-conversation-thread",
  aiIntent: "demo-tour-ai-intent",
  agendaAppointment: "demo-tour-agenda-appointment",
  dashboardMetrics: "demo-tour-dashboard-metrics",
} as const;

export type DemoTourTargetId = (typeof DEMO_TOUR_TARGETS)[keyof typeof DEMO_TOUR_TARGETS];

export type DemoTourStep =
  | "idle"
  | "breathing"
  | "spotlight_whatsapp"
  | "spotlight_conversation"
  | "spotlight_ai_intent"
  | "spotlight_ai_response"
  | "waiting_appointment"
  | "appointment_detected"
  | "spotlight_agenda"
  | "spotlight_dashboard"
  | "completed"
  | "paused"
  | "skipped"
  | "error";

export type DemoTourStatus = "idle" | "active" | "paused" | "completed" | "skipped" | "error";

export type DemoTourIdentity = {
  sessionId: string;
  tenantId: string;
  userId: string;
};

export type DemoTourContext = {
  whatsappLink?: string | null;
  phoneLabel?: string | null;
  entryChannel?: "whatsapp" | "webchat" | null;
  publicEntryPath?: string | null;
  conversationId?: string | null;
  patientId?: string | null;
  appointmentId?: string | null;
  waitingStartedAt?: string | null;
};

export type DemoTourProgress = {
  step: DemoTourStep;
  status: DemoTourStatus;
  lastActiveStep: DemoTourStep | null;
  createdAt: string;
  updatedAt: string;
  context: DemoTourContext;
  seenEvents: Partial<Record<DemoTourEventType, string>>;
};

export type DemoTourEventDetail =
  | {
      type: "whatsapp_cta_ready";
      whatsappLink?: string | null;
      phoneLabel?: string | null;
      entryChannel?: "whatsapp" | "webchat" | null;
      publicEntryPath?: string | null;
    }
  | {
      type: "whatsapp_clicked";
      whatsappLink?: string | null;
      phoneLabel?: string | null;
      entryChannel?: "whatsapp" | "webchat" | null;
      publicEntryPath?: string | null;
    }
  | {
      type: "conversation_detected";
      conversationId?: string | null;
      patientId?: string | null;
    }
  | {
      type: "ai_intent_detected";
      conversationId?: string | null;
    }
  | {
      type: "ai_response_detected";
      conversationId?: string | null;
    }
  | {
      type: "appointment_detected";
      conversationId?: string | null;
      patientId?: string | null;
      appointmentId?: string | null;
    }
  | {
      type: "agenda_ready";
      appointmentId?: string | null;
    }
  | {
      type: "dashboard_ready";
    };

export type DemoTourEventType = DemoTourEventDetail["type"];

export type DemoTourTestActionDetail =
  | {
      action: "simulate_message";
    }
  | {
      action: "simulate_complete_conversation";
    };

export type DemoTourCommandDetail =
  | {
      type: "open_whatsapp";
      popup?: Window | null;
    }
  | {
      type: "close_webchat_workspace";
    }
  | {
      type: "check_message";
    };

export type DemoWebchatWorkspaceDetail = {
  open: boolean;
};

function nowIso() {
  return new Date().toISOString();
}

export function resolveDemoTourIdentity(session: SessionContext | undefined, sessionId: string | null): DemoTourIdentity | null {
  if (!session?.id || !sessionId) return null;
  return {
    sessionId,
    tenantId: session.tenant_id ?? "platform",
    userId: session.id,
  };
}

export function getDemoTourStorageKey(identity: DemoTourIdentity) {
  return `${DEMO_TOUR_STORAGE_PREFIX}:${identity.tenantId}:${identity.userId}:${identity.sessionId}`;
}

export function createInitialDemoTourProgress(context: DemoTourContext = {}): DemoTourProgress {
  const timestamp = nowIso();
  return {
    step: "idle",
    status: "idle",
    lastActiveStep: null,
    createdAt: timestamp,
    updatedAt: timestamp,
    context,
    seenEvents: {},
  };
}

export function readDemoTourProgress(identity: DemoTourIdentity | null): DemoTourProgress | null {
  if (!identity || typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(getDemoTourStorageKey(identity));
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as DemoTourProgress;
    if (!parsed || typeof parsed !== "object") return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeDemoTourProgress(identity: DemoTourIdentity | null, progress: DemoTourProgress) {
  if (!identity || typeof window === "undefined") return;
  window.sessionStorage.setItem(getDemoTourStorageKey(identity), JSON.stringify(progress));
}

export function clearDemoTourProgress(identity: DemoTourIdentity | null) {
  if (!identity || typeof window === "undefined") return;
  window.sessionStorage.removeItem(getDemoTourStorageKey(identity));
}

export function patchDemoTourProgress(
  identity: DemoTourIdentity | null,
  updater: (current: DemoTourProgress) => DemoTourProgress,
) {
  if (!identity) return null;
  const current = readDemoTourProgress(identity) ?? createInitialDemoTourProgress();
  const next = updater(current);
  writeDemoTourProgress(identity, {
    ...next,
    updatedAt: nowIso(),
  });
  return next;
}

export function markDemoTourEventSeen(progress: DemoTourProgress, detail: DemoTourEventDetail): DemoTourProgress {
  return {
    ...progress,
    seenEvents: {
      ...progress.seenEvents,
      [detail.type]: nowIso(),
    },
    context: {
      ...progress.context,
      ...(detail.type === "whatsapp_cta_ready" || detail.type === "whatsapp_clicked"
        ? {
            whatsappLink: detail.whatsappLink ?? progress.context.whatsappLink ?? null,
            phoneLabel: detail.phoneLabel ?? progress.context.phoneLabel ?? null,
            entryChannel: detail.entryChannel ?? progress.context.entryChannel ?? null,
            publicEntryPath: detail.publicEntryPath ?? progress.context.publicEntryPath ?? null,
          }
        : {}),
      ...(detail.type === "conversation_detected"
        ? {
            conversationId: detail.conversationId ?? progress.context.conversationId ?? null,
            patientId: detail.patientId ?? progress.context.patientId ?? null,
          }
        : {}),
      ...(detail.type === "ai_intent_detected" || detail.type === "ai_response_detected"
        ? {
            conversationId: detail.conversationId ?? progress.context.conversationId ?? null,
          }
        : {}),
      ...(detail.type === "appointment_detected"
        ? {
            conversationId: detail.conversationId ?? progress.context.conversationId ?? null,
            patientId: detail.patientId ?? progress.context.patientId ?? null,
            appointmentId: detail.appointmentId ?? progress.context.appointmentId ?? null,
          }
        : {}),
      ...(detail.type === "agenda_ready"
        ? {
            appointmentId: detail.appointmentId ?? progress.context.appointmentId ?? null,
          }
        : {}),
    },
  };
}

export function dispatchDemoTourEvent(detail: DemoTourEventDetail) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<DemoTourEventDetail>(DEMO_TOUR_EVENT_NAME, { detail }));
}

export function dispatchDemoTourTestAction(detail: DemoTourTestActionDetail) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent<DemoTourTestActionDetail>(DEMO_TOUR_TEST_ACTION_EVENT_NAME, { detail }),
  );
}

export function dispatchDemoTourCommand(detail: DemoTourCommandDetail) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<DemoTourCommandDetail>(DEMO_TOUR_COMMAND_EVENT_NAME, { detail }));
}

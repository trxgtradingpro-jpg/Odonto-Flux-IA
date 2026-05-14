export const DEMO_SESSION_ID_KEY = "odontoflux_demo_session_id";
export const DEMO_WHATSAPP_ENTRY_ACTIVE_KEY = "odontoflux_demo_whatsapp_entry_active";
export const DEMO_WHATSAPP_ENTRY_PHONE_KEY = "odontoflux_demo_whatsapp_entry_phone";
export const DEMO_WHATSAPP_ENTRY_LINK_KEY = "odontoflux_demo_whatsapp_entry_link";
export const DEMO_ENTRY_TARGET_PATH_KEY = "odontoflux_demo_entry_target_path";
export const DEMO_WHATSAPP_STAGE_KEY = "odontoflux_demo_whatsapp_stage";
export const DEMO_WHATSAPP_STARTED_AT_KEY = "odontoflux_demo_whatsapp_started_at";
export const DEMO_WHATSAPP_TRACKED_CONVERSATION_ID_KEY = "odontoflux_demo_whatsapp_tracked_conversation_id";
export const DEMO_WHATSAPP_TRACKED_PATIENT_ID_KEY = "odontoflux_demo_whatsapp_tracked_patient_id";
export const DEMO_WHATSAPP_BASELINE_APPOINTMENTS_KEY = "odontoflux_demo_whatsapp_baseline_appointments";

export type DemoWhatsAppFlowStage = "entry" | "awaiting_appointment" | "appointment_ready";

type DemoWhatsAppEntryPayload = {
  testPhoneNumber?: string | null;
  whatsappLink?: string | null;
  targetPath?: string | null;
};

type DemoWhatsAppAwaitingPayload = {
  startedAt?: string | null;
  trackedConversationId?: string | null;
  trackedPatientId?: string | null;
  baselineAppointmentIds?: string[];
};

function hasWindow() {
  return typeof window !== "undefined";
}

function setDemoEntryTargetPathInternal(targetPath?: string | null) {
  if (!hasWindow()) return;
  if (targetPath) {
    window.sessionStorage.setItem(DEMO_ENTRY_TARGET_PATH_KEY, targetPath);
  } else {
    window.sessionStorage.removeItem(DEMO_ENTRY_TARGET_PATH_KEY);
  }
}

function setDemoWhatsAppStage(stage?: DemoWhatsAppFlowStage | null) {
  if (!hasWindow()) return;
  if (stage) {
    window.sessionStorage.setItem(DEMO_WHATSAPP_STAGE_KEY, stage);
  } else {
    window.sessionStorage.removeItem(DEMO_WHATSAPP_STAGE_KEY);
  }
}

function clearTrackedDemoWhatsAppState() {
  if (!hasWindow()) return;
  window.sessionStorage.removeItem(DEMO_WHATSAPP_STARTED_AT_KEY);
  window.sessionStorage.removeItem(DEMO_WHATSAPP_TRACKED_CONVERSATION_ID_KEY);
  window.sessionStorage.removeItem(DEMO_WHATSAPP_TRACKED_PATIENT_ID_KEY);
  window.sessionStorage.removeItem(DEMO_WHATSAPP_BASELINE_APPOINTMENTS_KEY);
}

export function ensureDemoSessionId() {
  if (!hasWindow()) return null;
  const existing = window.sessionStorage.getItem(DEMO_SESSION_ID_KEY);
  const sessionId = existing ?? crypto.randomUUID();
  window.sessionStorage.setItem(DEMO_SESSION_ID_KEY, sessionId);
  return sessionId;
}

export function storeDemoWhatsAppEntry(payload: DemoWhatsAppEntryPayload) {
  if (!hasWindow()) return;
  window.sessionStorage.setItem(DEMO_WHATSAPP_ENTRY_ACTIVE_KEY, "1");
  setDemoWhatsAppStage("entry");
  clearTrackedDemoWhatsAppState();
  if (payload.testPhoneNumber) {
    window.sessionStorage.setItem(DEMO_WHATSAPP_ENTRY_PHONE_KEY, payload.testPhoneNumber);
  } else {
    window.sessionStorage.removeItem(DEMO_WHATSAPP_ENTRY_PHONE_KEY);
  }
  if (payload.whatsappLink) {
    window.sessionStorage.setItem(DEMO_WHATSAPP_ENTRY_LINK_KEY, payload.whatsappLink);
  } else {
    window.sessionStorage.removeItem(DEMO_WHATSAPP_ENTRY_LINK_KEY);
  }
  setDemoEntryTargetPathInternal(payload.targetPath);
}

export function markDemoWhatsAppAwaitingAppointment(payload: DemoWhatsAppAwaitingPayload = {}) {
  if (!hasWindow()) return;
  window.sessionStorage.setItem(DEMO_WHATSAPP_ENTRY_ACTIVE_KEY, "0");
  setDemoWhatsAppStage("awaiting_appointment");
  window.sessionStorage.setItem(
    DEMO_WHATSAPP_STARTED_AT_KEY,
    payload.startedAt || new Date().toISOString(),
  );
  if (payload.trackedConversationId) {
    window.sessionStorage.setItem(DEMO_WHATSAPP_TRACKED_CONVERSATION_ID_KEY, payload.trackedConversationId);
  } else {
    window.sessionStorage.removeItem(DEMO_WHATSAPP_TRACKED_CONVERSATION_ID_KEY);
  }
  if (payload.trackedPatientId) {
    window.sessionStorage.setItem(DEMO_WHATSAPP_TRACKED_PATIENT_ID_KEY, payload.trackedPatientId);
  } else {
    window.sessionStorage.removeItem(DEMO_WHATSAPP_TRACKED_PATIENT_ID_KEY);
  }
  window.sessionStorage.setItem(
    DEMO_WHATSAPP_BASELINE_APPOINTMENTS_KEY,
    JSON.stringify(payload.baselineAppointmentIds ?? []),
  );
}

export function markDemoWhatsAppAppointmentReady() {
  if (!hasWindow()) return;
  window.sessionStorage.setItem(DEMO_WHATSAPP_ENTRY_ACTIVE_KEY, "0");
  setDemoWhatsAppStage("appointment_ready");
}

export function readDemoWhatsAppEntry() {
  if (!hasWindow()) {
    return {
      active: false,
      testPhoneNumber: null,
      whatsappLink: null,
      targetPath: null,
      stage: null,
      startedAt: null,
      trackedConversationId: null,
      trackedPatientId: null,
      baselineAppointmentIds: [] as string[],
    };
  }

  let baselineAppointmentIds: string[] = [];
  const rawBaseline = window.sessionStorage.getItem(DEMO_WHATSAPP_BASELINE_APPOINTMENTS_KEY);
  if (rawBaseline) {
    try {
      const parsed = JSON.parse(rawBaseline);
      if (Array.isArray(parsed)) {
        baselineAppointmentIds = parsed.filter((item): item is string => typeof item === "string");
      }
    } catch {
      baselineAppointmentIds = [];
    }
  }

  return {
    active: window.sessionStorage.getItem(DEMO_WHATSAPP_ENTRY_ACTIVE_KEY) === "1",
    testPhoneNumber: window.sessionStorage.getItem(DEMO_WHATSAPP_ENTRY_PHONE_KEY),
    whatsappLink: window.sessionStorage.getItem(DEMO_WHATSAPP_ENTRY_LINK_KEY),
    targetPath: window.sessionStorage.getItem(DEMO_ENTRY_TARGET_PATH_KEY),
    stage: (window.sessionStorage.getItem(DEMO_WHATSAPP_STAGE_KEY) as DemoWhatsAppFlowStage | null) ?? null,
    startedAt: window.sessionStorage.getItem(DEMO_WHATSAPP_STARTED_AT_KEY),
    trackedConversationId: window.sessionStorage.getItem(DEMO_WHATSAPP_TRACKED_CONVERSATION_ID_KEY),
    trackedPatientId: window.sessionStorage.getItem(DEMO_WHATSAPP_TRACKED_PATIENT_ID_KEY),
    baselineAppointmentIds,
  };
}

export function readDemoEntryTargetPath() {
  if (!hasWindow()) return null;
  return window.sessionStorage.getItem(DEMO_ENTRY_TARGET_PATH_KEY);
}

export function storeDemoEntryTargetPath(targetPath?: string | null) {
  setDemoEntryTargetPathInternal(targetPath);
}

export function clearDemoEntryTargetPath() {
  if (!hasWindow()) return;
  window.sessionStorage.removeItem(DEMO_ENTRY_TARGET_PATH_KEY);
}

export function clearDemoWhatsAppEntry() {
  if (!hasWindow()) return;
  window.sessionStorage.removeItem(DEMO_WHATSAPP_ENTRY_ACTIVE_KEY);
  window.sessionStorage.removeItem(DEMO_WHATSAPP_ENTRY_PHONE_KEY);
  window.sessionStorage.removeItem(DEMO_WHATSAPP_ENTRY_LINK_KEY);
  window.sessionStorage.removeItem(DEMO_WHATSAPP_STAGE_KEY);
  clearTrackedDemoWhatsAppState();
  window.sessionStorage.removeItem(DEMO_ENTRY_TARGET_PATH_KEY);
}

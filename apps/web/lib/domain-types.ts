export type ApiPage<T> = {
  data: T[];
  meta?: {
    total: number;
    limit: number;
    offset: number;
  };
};

export type UserItem = {
  id: string;
  full_name: string;
  email: string;
  phone?: string | null;
  roles: string[];
  is_active: boolean;
  last_login_at?: string | null;
  created_at: string;
};

export type UnitItem = {
  id: string;
  code: string;
  name: string;
  phone?: string | null;
  email?: string | null;
};

export type ProfessionalItem = {
  id: string;
  unit_id?: string | null;
  full_name: string;
  cro_number?: string | null;
  specialty?: string | null;
  working_days: number[];
  shift_start: string;
  shift_end: string;
  procedures: string[];
  is_active: boolean;
};

export type PatientItem = {
  id: string;
  full_name: string;
  phone: string;
  email?: string | null;
  status: string;
  origin?: string | null;
  tags_cache: string[];
  marketing_opt_in: boolean;
  unit_id?: string | null;
  created_at: string;
};

export type LeadItem = {
  id: string;
  patient_id?: string | null;
  name: string;
  phone?: string | null;
  email?: string | null;
  origin?: string | null;
  interest?: string | null;
  stage: string;
  score: number;
  temperature: string;
  status: string;
  owner_user_id?: string | null;
  created_at: string;
};

export type ConversationItem = {
  id: string;
  patient_id?: string | null;
  lead_id?: string | null;
  unit_id?: string | null;
  channel: string;
  status: string;
  assigned_user_id?: string | null;
  tags: string[];
  ai_summary?: string | null;
  ai_autoresponder_enabled?: boolean | null;
  ai_autoresponder_last_decision?: string | null;
  ai_autoresponder_last_reason?: string | null;
  ai_autoresponder_last_at?: string | null;
  ai_autoresponder_consecutive_count?: number;
  last_message_at?: string | null;
};

export type MessageItem = {
  id: string;
  conversation_id: string;
  direction: string;
  status: string;
  body: string;
  message_type: string;
  sender_type: string;
  sent_at?: string | null;
  created_at: string;
};

export type AppointmentItem = {
  id: string;
  patient_id: string;
  unit_id: string;
  professional_id?: string | null;
  procedure_type: string;
  starts_at: string;
  ends_at?: string | null;
  status: string;
  confirmation_status: string;
  origin: string;
  notes: string;
};

export type CampaignItem = {
  id: string;
  name: string;
  objective: string;
  status: string;
  scheduled_at?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
};

export type AutomationItem = {
  id: string;
  name: string;
  description?: string | null;
  trigger_type: string;
  trigger_key: string;
  conditions: Record<string, unknown>;
  actions: Array<Record<string, unknown>>;
  is_active: boolean;
  created_at: string;
};

export type AutomationRunItem = {
  id: string;
  automation_id: string;
  status: string;
  trigger_payload: Record<string, unknown>;
  result_payload: Record<string, unknown>;
  error_message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
};

export type DocumentItem = {
  id: string;
  title: string;
  document_type: string;
  description?: string | null;
  patient_id?: string | null;
  unit_id?: string | null;
  created_by_user_id?: string | null;
  current_version_id?: string | null;
  is_sensitive: boolean;
  created_at: string;
};

export type AuditItem = {
  id: string;
  user_id?: string | null;
  action: string;
  entity_type: string;
  entity_id?: string | null;
  metadata: Record<string, unknown>;
  occurred_at: string;
};

export type SettingItem = {
  id: string;
  key: string;
  value: unknown;
  is_secret: boolean;
};

export type WhatsAppAccountItem = {
  id: string;
  phone_number_id: string;
  business_account_id: string;
  display_phone?: string | null;
  is_active: boolean;
};

export type WhatsAppTemplateItem = {
  id: string;
  name: string;
  language: string;
  category: string;
  status: string;
};

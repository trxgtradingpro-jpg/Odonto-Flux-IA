export type RoleName = 'owner' | 'manager' | 'receptionist' | 'analyst' | 'admin_platform';

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
  expires_in: number;
}

export interface ApiPage<T> {
  data: T[];
  meta: {
    total: number;
    limit: number;
    offset: number;
  };
}

export interface DashboardKPI {
  avg_first_response_minutes: number;
  avg_resolution_minutes: number;
  confirmation_rate: number;
  cancellation_rate: number;
  no_show_rate: number;
  no_show_recovery_rate: number;
  budget_conversion_rate: number;
  reactivated_patients: number;
  messages_count: number;
  leads_by_origin: { origin: string; count: number }[];
  performance_by_unit: { unit_id: string; count: number }[];
  performance_by_attendant: { user_id: string; count: number }[];
  ai_automation_rate: number;
  ai_handoff_rate: number;
  avg_first_response_ai_minutes: number;
  ai_send_failure_rate: number;
}

export interface ConversationItem {
  id: string;
  channel: string;
  status: string;
  ai_summary?: string;
  last_message_at?: string;
}

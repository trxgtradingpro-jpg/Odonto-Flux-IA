# Modelo de Dados

## Tabelas principais
- Plataforma: `tenant_plans`, `tenants`, `feature_flags`, `api_keys`, `settings`
- Identidade: `users`, `roles`, `user_roles`, `refresh_tokens`, `password_reset_tokens`, `invitations`
- Operacao: `units`, `professionals`, `patients`, `patient_contacts`, `patient_tags`, `leads`, `lead_sources`
- Atendimento: `conversations`, `conversation_participants`, `messages`, `message_events`
- WhatsApp: `whatsapp_accounts`, `whatsapp_templates`, `webhooks_inbox`, `outbox_messages`
- Agenda: `appointments`, `appointment_events`
- Automacao/campanha: `automations`, `automation_runs`, `campaigns`, `campaign_audiences`, `campaign_messages`, `jobs`
- Documentos: `documents`, `document_versions`, `consents`
- Governanca: `audit_logs`, `llm_interactions`
- IA Auto-Responder: `ai_autoresponder_decisions` + campos de controle em `conversations`

## IA Auto-Responder
- `conversations.ai_autoresponder_enabled`: override por conversa (`true`, `false` ou `null` para herdar global).
- `conversations.ai_autoresponder_last_decision`: ultima decisao (`responded`, `handoff`, `blocked`, `ignored`).
- `conversations.ai_autoresponder_last_reason`: motivo tecnico da decisao.
- `conversations.ai_autoresponder_last_at`: timestamp da ultima decisao.
- `conversations.ai_autoresponder_consecutive_count`: contador para evitar loops.
- `ai_autoresponder_decisions`: trilha completa com entrada, resposta gerada, confianca, decisao final, motivo, tokens/custo, latencia e dedupe.

## Estrategia de isolamento
- Entidades tenant-scoped possuem `tenant_id` indexado
- Unique constraints compostas por `tenant_id` quando necessario
- Endpoints tenant-scoped sempre filtram por `tenant_id`

## Futuro prontuario
Base permite expandir para prontuario estruturado com vinculo paciente/profissional/unidade e trilha temporal.

# Link Flow

O `link_flow` e a entrada publica de agendamento inteligente da ClinicFlux AI. O paciente acessa `/agendar/[clinicSlug]`, recebe uma sessao temporaria e continua pelo CTA configurado da clinica.

Na Fase 3 existem dois CTAs suportados:

- `whatsapp_redirect`: abre o WhatsApp oficial compartilhado do sistema com um token `CFX:{token}`.
- `webchat`: mantem o atendimento dentro da landing publica com uma conversa real `channel="webchat"`.

Os dois caminhos reutilizam o mesmo motor de IA, agenda, disponibilidade, confirmacao, automacoes e protecao contra duplicidade. O webhook oficial do WhatsApp continua com o mesmo contrato.

## Modos

`official_api`: a clinica opera pelo WhatsApp oficial proprio ja integrado. Inbound sem token segue o fluxo legado e as respostas saem pela conta da propria clinica.

`link_flow`: a clinica opera pela landing publica. O CTA pode ser `whatsapp_redirect` ou `webchat`.

`hybrid`: conta propria, link por WhatsApp do sistema e webchat podem coexistir conforme a configuracao. Uma conversa de WhatsApp permanece WhatsApp; uma conversa de webchat permanece webchat.

A configuracao fica em `Setting.key = "intake.config"`:

```json
{
  "mode": "hybrid",
  "link_flow": {
    "enabled": true,
    "cta_mode": "webchat",
    "headline": "Agendamento oficial da clinica",
    "trust_message": "Continue pelo canal oficial para falar com a assistente de agendamento.",
    "button_label": "Iniciar chat",
    "session_ttl_minutes": 30
  }
}
```

Sem configuracao persistida, o default e `official_api`. Se `cta_mode` estiver ausente em configuracoes antigas, o sistema assume `whatsapp_redirect`.

## Endpoints

- `GET /api/v1/settings/intake/config`: retorna a configuracao administrativa validada.
- `PUT /api/v1/settings/intake/config`: salva `official_api`, `link_flow` ou `hybrid`.
- `GET /api/v1/settings/intake/status`: retorna readiness resumido, sem tokens, hashes ou credenciais.
- `GET /api/v1/public/booking/{clinic_slug}`: retorna branding publico, CTA atual e disponibilidade operacional.
- `POST /api/v1/public/booking/{clinic_slug}/sessions`: cria sessao publica para o CTA configurado.
- `GET /api/v1/public/booking/sessions/{session_id}`: retorna estado publico resumido da sessao webchat autenticada.
- `POST /api/v1/public/booking/sessions/{session_id}/chat/messages`: envia mensagem do paciente no webchat.
- `GET /api/v1/public/booking/sessions/{session_id}/chat/messages`: lista mensagens publicas por polling, com `after_message_id`.
- `POST /api/v1/public/booking/sessions/{session_id}/events`: registra eventos publicos permitidos.

## Webchat

O navegador nunca usa `conversation_id`, `tenant_id`, hashes ou IDs internos. Ao criar uma sessao `webchat`, o backend gera um `public_access_token` opaco, salva somente o hash em `link_flow_sessions.public_access_token_hash` e exige esse token nos endpoints de chat.

Validacoes obrigatorias por request:

- sessao existe e token publico confere
- tenant ainda esta ativo
- sessao nao expirou e nao foi encerrada
- sessao foi criada para `cta_mode="webchat"`
- configuracao atual ainda permite `link_flow + webchat`

No primeiro envio do paciente, o backend cria ou retoma:

- `LinkFlowSession(channel="webchat")`
- `Conversation(channel="webchat")`
- `Message(channel="webchat", direction="inbound", sender_type="patient")`

As respostas da IA usam o dispatcher por canal. Para `webchat`, o outbound e salvo localmente como mensagem `sent`; nao existe chamada a provider externo nem outbox WhatsApp. Para `whatsapp`, o fluxo existente continua usando a rota real da conversa.

## WhatsApp Redirect

No `whatsapp_redirect`, a landing cria a sessao e devolve uma URL `wa.me` com `CFX:{token}`. O webhook resolve o hash do token, vincula a sessao a conversa real e salva o `provider_context` da conta que recebeu a mensagem.

No modo `hybrid`, inbound pela conta propria da clinica continua legado. Inbound pelo sender compartilhado sem token valido nao e roteado para tenant por heuristica.

## Polling

A landing publica usa polling-first:

- carrega mensagens iniciais ao abrir o chat
- envia mensagem com `client_message_id` opcional
- busca novas mensagens com `after_message_id`
- aumenta a frequencia logo apos envio e reduz depois

O payload publico de mensagem contem apenas:

- `id`
- `role`
- `text`
- `created_at`
- `status`

Nao sao expostos payloads internos, traces, provider IDs, `conversation_id` ou dados do tenant.

## Fallback Seguro

Casos tratados:

- token publico invalido
- token WhatsApp invalido
- sessao expirada
- sessao cancelada, concluida ou inativa
- tenant desativado apos criacao
- sender compartilhado indisponivel para `whatsapp_redirect`
- webchat desabilitado apos a sessao ser aberta

O sistema nao tenta inferir clinica por texto, slug, nome humano ou heuristica. Quando nao pode continuar com seguranca, registra `session_invalid`, `session_expired` ou `webchat_error` e retorna mensagem neutra:

```text
Abra novamente o link oficial da clinica para continuar.
```

## Analytics

Eventos mantidos:

- `landing_viewed`
- `cta_whatsapp_clicked`
- `conversation_started`
- `booking_attempt_started`
- `appointment_created`
- `appointment_duplicate_detected`
- `session_invalid`
- `session_expired`

Eventos de webchat:

- `webchat_opened`
- `webchat_started`
- `webchat_message_sent`
- `webchat_first_ai_response`
- `webchat_session_resumed`
- `webchat_session_closed`
- `webchat_error`

Quando a sessao resulta em consulta, recebe `linked_appointment_id`, `completed_at` e status `completed`.

## Duplicidade

A protecao central fica em `appointment_validation_service.find_duplicate_active_patient_appointment`.

O criterio minimo e:

- mesmo `tenant_id`
- mesmo `patient_id`
- mesmo `unit_id`
- mesmo `starts_at`
- status ativo (`agendada`, `confirmada`, `reagendada`)

Legacy, structured flow e conversas originadas por `link_flow` consultam esse helper antes da criacao final. Se ja existir appointment compativel, o sistema nao cria outro e registra `appointment_duplicate_detected` quando houver sessao rastreavel.

## Limites da Fase 3

- Sem upload de midia, audio, imagem ou documento.
- Sem websocket obrigatorio.
- Sem inbox publica administrativa.
- Sem handoff humano em tempo real dentro da landing.
- Sem unificacao automatica de conversas entre WhatsApp e webchat.
- Sem novo motor de IA ou agenda paralela.

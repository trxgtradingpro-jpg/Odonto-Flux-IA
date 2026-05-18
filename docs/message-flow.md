# Fluxo de Mensagens

## Entrada WhatsApp
1. Meta envia webhook para `/api/v1/webhooks/whatsapp`
2. API valida payload e grava em `webhooks_inbox`
3. Dedup por `provider + event_id`
4. Resolve tenant por `phone_number_id`
5. Busca paciente por telefone normalizado
6. Se nao existir, cria paciente e lead automaticamente
7. Cria/reativa conversa
8. Persiste mensagem inbound e evento
9. Emite gatilho de automacao (`mensagem_recebida`)
10. Avalia elegibilidade do IA Auto-Responder (tenant/unidade/conversa/canal/horario)
11. Aplica guardrails (pedido de humano, urgencia, solicitacao clinica, baixa confianca)
12. Se elegivel, gera resposta IA e enfileira em `outbox_messages`
13. Se nao elegivel, registra handoff/bloqueio em `ai_autoresponder_decisions`

## Branch link_flow WhatsApp
1. A landing publica cria `link_flow_sessions` com `cta_mode = whatsapp_redirect`
2. A pagina abre o WhatsApp compartilhado com `CFX:{token}`
3. O webhook extrai o token antes de criar paciente, lead ou conversa
4. Token valido resolve `link_flow_sessions.tenant_id` e remove o token do texto salvo
5. A mensagem inbound salva `entry_source = link_flow` e `provider_context` da conta real que recebeu a mensagem
6. A sessao recebe `linked_conversation_id`, `linked_patient_id` e evento `conversation_started`
7. Token invalido, expirado ou ausente no sender compartilhado nao roteia por heuristica
8. O fallback registra `session_invalid` ou `session_expired` e nao cria conversa no tenant errado

## Branch link_flow Webchat
1. A landing publica cria `link_flow_sessions` com `cta_mode = webchat`
2. A API devolve somente um `public_access_token` opaco; o hash fica no banco
3. O navegador envia mensagens publicas com `X-Link-Flow-Token`
4. A API valida sessao, tenant ativo, TTL, canal e configuracao atual
5. No primeiro envio, cria ou retoma `Conversation.channel = webchat`
6. A mensagem do paciente e salva como `Message.channel = webchat`
7. O mesmo motor de IA/agendamento processa o inbound
8. A resposta usa dispatcher por canal e fica salva localmente como outbound `webchat`
9. A landing lista mensagens seguras por polling com `after_message_id`

## Saida WhatsApp
1. Usuario/automacao cria item em `outbox_messages`
2. Para conversa WhatsApp, a rota de resposta prioriza o `provider_context` do inbound real
3. Conversa `link_flow` responde pelo sender compartilhado sem exigir conta propria da clinica
4. Conversa `official_api` responde pela conta propria da clinica
5. Worker processa lote pendente
6. Envia via provider com retry
7. Marca status sent/failed/dead-letter
8. Callback de status atualiza `messages` e `message_events`

## Saida Webchat
1. IA ou atendente cria `Message.direction = outbound` na conversa `webchat`
2. O dispatcher de canal marca a mensagem como `sent` localmente
3. Nenhum provider externo e chamado
4. `GET /public/booking/sessions/{session_id}/chat/messages` retorna somente campos publicos
5. Eventos `webchat_first_ai_response` e timestamps da sessao atualizam o funil

## IA operacional
- Classificacao de intencao
- Resumo de conversa
- Sugestao de resposta
- Classificacao de lead
- Registro de prompt/response em `llm_interactions`
- Guardrail bloqueia termos de decisao clinica
- Modo automatico com fallback humano: handoff em `conversations.status = aguardando`
- Trilha de decisao: tabela `ai_autoresponder_decisions`
- Idempotencia por inbound (`dedupe_key`) para evitar resposta duplicada

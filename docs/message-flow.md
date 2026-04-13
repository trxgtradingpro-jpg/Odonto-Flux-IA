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

## Saida WhatsApp
1. Usuario/automacao cria item em `outbox_messages`
2. Worker processa lote pendente
3. Envia via Cloud API com retry
4. Marca status sent/failed/dead-letter
5. Callback de status atualiza `messages` e `message_events`

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

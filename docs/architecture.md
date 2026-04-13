# Arquitetura OdontoFlux

## Visao geral
Plataforma SaaS B2B multi-tenant para operacao administrativa/comercial de clinicas odontologicas.

## Componentes
- `web`: SPA/SSR com Next.js App Router
- `api`: backend FastAPI versionado
- `worker`: Celery worker para automacoes e fila outbox
- `scheduler`: Celery Beat para gatilhos de tempo
- `postgres`: persistencia relacional
- `redis`: broker e cache
- `nginx`: reverse proxy

## Multi-tenant
- Tenant por clinica (`tenants`)
- `tenant_id` em entidades de dominio
- Query always-on com filtro por tenant
- JWT carrega contexto do tenant
- RBAC por roles + permissoes

## Seguranca
- JWT access + refresh
- Senha com bcrypt
- Rate limiting middleware
- CORS por ambiente
- Auditoria de eventos sensiveis
- Guardrails de IA (sem decisao clinica)

## Automacoes
- Gatilho por evento e tempo
- Motor de acoes: enviar mensagem, tag, alterar status, fila humana, job
- Runs e logs de execucao
- Retry/backoff e dead-letter para envio

## Integracao WhatsApp
- Verificacao GET webhook
- Recebimento POST webhook
- Parsing de mensagens/status
- Idempotencia (`webhooks_inbox`)
- Outbox para envio resiliente

## IA Auto-Responder
- Configuracao hierarquica (tenant -> unidade -> conversa)
- Guardrails operacionais (sem orientacao clinica, urgencia => handoff humano)
- Decisao assíncrona inbound -> LLM -> outbox
- Trilha detalhada em `ai_autoresponder_decisions`
- Auditoria dedicada para toggle, bloqueio, handoff e resposta enviada

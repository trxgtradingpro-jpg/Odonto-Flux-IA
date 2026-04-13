# Checklist de Produção

## 1. Infraestrutura mínima
- Executar API, Web, Worker, Scheduler, Redis e PostgreSQL em ambiente dedicado.
- Publicar `web` e `api` atrás de proxy com TLS (HTTPS obrigatório).
- Configurar domínio e certificado válido.
- Definir variáveis seguras de produção (`APP_ENV=production`, `API_SECRET_KEY` forte).

## 2. Observabilidade
- Healthcheck:
  - `GET /health`
  - `GET /readiness`
  - `GET /api/v1/admin/platform/health` (perfil `admin_platform`)
- Monitorar:
  - disponibilidade (uptime)
  - latência de API
  - taxa de erro 4xx/5xx
  - fila de jobs e outbox WhatsApp
- Habilitar Sentry (`SENTRY_DSN`) em produção.

## 3. Segurança
- Política de senha forte ativa (mín. 10, maiúscula, minúscula, número e símbolo).
- Reset de senha com token de uso único e expiração curta (30 min).
- Rever perfis e permissões por clínica antes do go-live.
- Nunca expor token sensível em logs ou UI.

## 4. Dados e continuidade
- Backup diário de PostgreSQL.
- Teste de restore semanal.
- Armazenar backup fora do host principal.
- Script de backup:
  - Linux/macOS: `./infra/scripts/backup-postgres.sh`
  - Windows: `./infra/scripts/backup-postgres.ps1`

## 5. Go-live comercial
- Concluir `Onboarding` (rota `/onboarding`).
- Validar WhatsApp com teste de conexão.
- Executar importação inicial em `dry-run` (`/importacao`).
- Confirmar relatório mensal (`/relatorios`) e trilha de auditoria.

## 6. Ativacao IA Auto-Responder (producao)
- Aplicar migration `202604080001_ai_autoresponder_mode`.
- Confirmar `worker` + `scheduler` ativos (fila outbox obrigatoria para envio IA).
- Configurar:
  - `Configuracoes > IA Auto-Responder > Toggle global`
  - Canal WhatsApp habilitado
  - Janela de atendimento e regra fora do horario
  - Limite de respostas consecutivas
  - Threshold de confianca
- Configurar override por unidade (quando necessario).
- Executar smoke test:
  - inbound normal -> resposta IA enfileirada e enviada
  - mensagem com urgencia -> handoff humano
  - mensagem pedindo atendente -> handoff humano
- Validar auditoria:
  - `ai_autoresponder.toggle`
  - `ai_autoresponder.response_sent`
  - `ai_autoresponder.handoff`
  - `ai_autoresponder.blocked`

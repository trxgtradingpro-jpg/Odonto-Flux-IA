# Incidentes e SLA

## Central de suporte
- UI: `/suporte`
- API:
  - `GET /api/v1/support/overview`
  - `GET /api/v1/support/incidents`
  - `POST /api/v1/support/incidents`
  - `POST /api/v1/support/incidents/{id}/resolve`
  - `GET /api/v1/support/playbook`

## SLA padrão
- Crítica: 1h
- Alta: 4h
- Média: 8h
- Baixa: 24h

## Fluxo operacional
1. Abrir incidente com severidade e descrição.
2. Confirmar recebimento em até 15 min.
3. Publicar primeira atualização em até 30 min.
4. Aplicar mitigação e registrar resolução.
5. Publicar pós-incidente (causa raiz + prevenção) em até 24h.

## Playbook rápido
- Conferir saúde da plataforma: `/api/v1/admin/platform/health`.
- Validar DB e Redis.
- Verificar outbox WhatsApp e jobs pendentes.
- Escalar para engenharia com contexto mínimo:
  - tenant
  - impacto
  - horário de início
  - evidência (erro/log/print)

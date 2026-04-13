# Troubleshooting

## API nao sobe
- Verifique `.env`
- Confirme conectividade com PostgreSQL/Redis
- Rode `alembic upgrade head`

## Login falha
- Rode seed
- Verifique hash de senha e usuario ativo

## Webhook WhatsApp nao processa
- Validar `WHATSAPP_VERIFY_TOKEN`
- Confirmar `phone_number_id` cadastrado
- Ver logs em `webhooks_inbox`

## Mensagens nao saem
- Verificar `outbox_messages` com `failed/dead_letter`
- Conferir token WhatsApp e conectividade externa
- Conferir worker Celery em execucao

## Dados cruzados entre tenants
- Revisar token JWT (tenant_id)
- Validar filtros de tenant em endpoint custom
- Executar testes de multi-tenant

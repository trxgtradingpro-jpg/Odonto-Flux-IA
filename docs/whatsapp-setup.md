# Setup WhatsApp Cloud API

1. Crie app no Meta Developers
2. Ative WhatsApp Cloud API
3. Obtenha `phone_number_id`, `business_account_id` e `access_token`
4. Configure webhook:
   - URL: `https://SEU-DOMINIO/api/v1/webhooks/whatsapp`
   - Verify token: igual a `WHATSAPP_VERIFY_TOKEN`
5. Assine eventos `messages` e `message_template_status_update`
6. Cadastre conta em `Configuracoes > WhatsApp` ou endpoint:
   - `POST /api/v1/settings/whatsapp/accounts`
7. Cadastre templates utilitarios em:
   - `POST /api/v1/settings/whatsapp/templates`

## Teste rapido
- Envie mensagem para numero de teste
- Verifique criacao de `patient`, `lead`, `conversation`, `message`
- Consulte logs em `audit` e `webhooks_inbox`

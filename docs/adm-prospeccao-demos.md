# Modulo /adm de prospeccao e demos

## Objetivo

O `/adm` é o painel interno do ClinicFlux AI para operar prospecção B2B, gerar demos personalizadas por clínica e acompanhar sinais de interesse comercial.

Cada demo criada pelo `/adm` vira um tenant separado. Conversas, agenda, pacientes, configuracoes, equipe e tracking ficam isolados por clinica.

## Configuracao

Defina as variaveis no ambiente da API:

- `ADM_BOOTSTRAP_EMAIL`
- `ADM_BOOTSTRAP_PASSWORD`
- `ADM_LOGIN_RATE_LIMIT_PER_MINUTE`
- `DEMO_ACCESS_TOKEN_EXPIRE_HOURS`
- `DEMO_DEFAULT_EXPIRE_DAYS`

Exemplo local:

```env
ADM_BOOTSTRAP_EMAIL=netmultiverso@gmail.com
ADM_BOOTSTRAP_PASSWORD=Ia.123456789
ADM_LOGIN_RATE_LIMIT_PER_MINUTE=8
DEMO_ACCESS_TOKEN_EXPIRE_HOURS=72
DEMO_DEFAULT_EXPIRE_DAYS=21
```

O bootstrap cria o admin somente se o e-mail ainda nao existir. A senha inicial deve ser trocada no primeiro acesso.

## Fluxo operacional

1. Acesse `/adm`.
2. Entre com o admin comercial.
3. Cadastre a clinica prospectada.
4. Preencha WhatsApp, cidade, dor principal, unidades e servicos.
5. Clique em `Gerar demo`.
6. O sistema cria tenant, usuario, unidades, profissionais, pacientes, conversas, agenda e configuracoes iniciais.
7. Copie o link da demo e envie manualmente para o dono ou gerente.
8. Quando o cliente acessa, o sistema registra login, paginas visitadas, modulo de interesse e score.

## Endpoints principais

- `POST /api/v1/admin/auth/login`
- `POST /api/v1/admin/auth/change-initial-password`
- `GET /api/v1/admin/prospects/overview`
- `GET /api/v1/admin/prospects`
- `POST /api/v1/admin/prospects`
- `POST /api/v1/admin/prospects/{id}/generate-demo`
- `POST /api/v1/admin/prospects/{id}/send-demo-access`
- `POST /api/v1/demo/auth/redeem-token`
- `POST /api/v1/demo/events`

## Tracking

Eventos de demo registrados:

- `login_completed`
- `page_view`
- `visited_conversations`
- `visited_agenda`
- `visited_patients`
- `visited_settings`
- `visited_team`
- `tested_whatsapp_flow`
- `edited_settings`
- `changed_service`

O score comercial e recalculado quando eventos chegam.

## Regras de seguranca

- Nao usar scraping automatico.
- Nao usar telefone puro como senha.
- Nao compartilhar dados entre tenants.
- Nao hardcodear credenciais.
- Usar magic link/token temporario para acesso de demo.
- Registrar eventos e timeline por prospect.

## Validacao manual local

1. Aplicar migrations:

```bash
alembic upgrade head
```

2. Entrar no `/adm`.
3. Criar uma clinica.
4. Gerar demo.
5. Abrir o link com `demo_token`.
6. Navegar na agenda ou conversas.
7. Voltar ao `/adm` e conferir atividade e score.

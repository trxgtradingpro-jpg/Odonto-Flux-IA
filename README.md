# OdontoFlux

Plataforma SaaS multi-tenant para operacao comercial e administrativa de clinicas odontologicas.

## Stack
- Frontend: Next.js App Router, TypeScript, Tailwind CSS, React Query, Zod, React Hook Form
- Backend: FastAPI, SQLAlchemy 2.x, Alembic, Pydantic, Celery, Redis, PostgreSQL
- Infra: Docker Compose, Nginx, Makefile, CI basica

## Estrutura
```text
odontoflux/
  apps/
    api/
    web/
  packages/
    ui/
    shared-types/
    eslint-config/
    tsconfig/
  infra/
    docker/
    nginx/
    scripts/
  docs/
```

## Inicio rapido
1. Copie variaveis:
```bash
cp .env.example .env
```
2. Suba stack:
```bash
make up
```
3. Execute migracoes:
```bash
make migrate
```
4. Execute seed:
```bash
make seed
```
5. Acesse:
- Web: http://localhost:3000
- API: http://localhost:8000
- OpenAPI: http://localhost:8000/api/v1/docs

## Credenciais demo
- owner tenant A: `owner@sorrisosul.com` / `Odonto@123`
- manager tenant B: `manager@oralprime.com` / `Odonto@123`
- admin plataforma: `admin@odontoflux.com` / `Odonto@123`

## IA Auto-Responder (operacao)
1. Acesse **Configuracoes**.
2. Aba **IA Auto-Responder**:
- habilite/desabilite resposta automatica
- ajuste horario, confianca minima e fallback humano
3. Aba **Conhecimento IA**:
- preencha perfil da clinica, servicos, FAQ e politicas
- salve para a IA usar essas informacoes nas respostas automaticas

## WhatsApp Providers
- O sistema suporta dois provedores em **Configuracoes > WhatsApp**:
  - `Meta Cloud API`
  - `Infobip`
- Para `Infobip`, use:
  - `Sender WhatsApp` no campo de telefone
  - `Base URL` no campo conta/URL
  - `App key` no campo token

## Comandos uteis
- `make up`: sobe servicos
- `make down`: derruba servicos
- `make logs`: logs agregados
- `make migrate`: aplica migracoes
- `make seed`: popula dados demo
- `make test`: roda testes backend e frontend

Documentacao detalhada em [`docs/`](docs).

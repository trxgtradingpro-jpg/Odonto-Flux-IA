# Outreach Intelligence Hardening Report

Data: 2026-05-29

## Resumo

Foi feito hardening da inteligencia comercial continua do ClinicFlux AI com foco em seguranca de WhatsApp frio, economia de tokens, validade de JSON/JSONL, exemplos ficticios, dashboard manual e testes.

O sistema agora aplica a politica `token_efficiency_policy` com os modos `economico`, `profissional` e `elite_300`, escolhendo o menor modo suficiente para uma decisao segura. Lead frio sem resposta humana permanece em modo economico, auto-resposta nao conta como resposta humana, terceira mensagem fria sem resposta humana e bloqueada, e resposta humana real muda o fluxo para resposta contextual.

## Arquivos Alterados

- `skills/seo/SKILL.md`
- `C:/Users/Gui Trader/.codex/skills/local-seo-outreach-playbook/SKILL.md`
- `outreach-intelligence/scripts/outreach_intelligence.py`
- `outreach-intelligence/schemas/conversation-review.schema.json`
- `outreach-intelligence/schemas/message-evaluation.schema.json`
- `outreach-intelligence/schemas/campaign-summary.schema.json`
- `outreach-intelligence/schemas/skill-update-suggestion.schema.json`
- `outreach-intelligence/examples/sample-conversation-review.json`
- `outreach-intelligence/examples/sample-message-evaluation.json`
- `outreach-intelligence/examples/sample-campaign-summary.json`
- `outreach-intelligence/examples/sample-skill-update-suggestion.json`
- `outreach-intelligence/skill-update-suggestions.jsonl`
- `outreach-reviews/conversation-reviews.jsonl`
- `outreach-reports/weekly-summary-2026-05-29.json`
- `apps/api/tests/unit/test_outreach_intelligence.py`
- `apps/web/app/adm/inteligencia-comercial/page.tsx`

## Arquivos Criados

- `outreach-intelligence/examples/conversation-review-cold-first-economico.json`
- `outreach-intelligence/examples/conversation-review-auto-reply-economico.json`
- `outreach-intelligence/examples/conversation-review-stop-after-second-economico.json`
- `outreach-intelligence/examples/conversation-review-first-human-morning-profissional.json`
- `outreach-intelligence/examples/conversation-review-permission-to-send-profissional.json`
- `outreach-intelligence/examples/conversation-review-price-elite.json`
- `outreach-intelligence/examples/conversation-review-demo-request-elite.json`
- `outreach-intelligence/examples/conversation-review-do-not-contact.json`
- `outreach-intelligence/examples/conversation-review-outside-24h-template.json`
- `OUTREACH_INTELLIGENCE_HARDENING_REPORT.md`

## O Que Foi Validado

- Limite de 2 mensagens outbound para lead frio sem resposta humana.
- Auto-resposta classificada como automacao, sem virar opt-in ou interesse real.
- Stop contact depois da segunda mensagem fria sem resposta humana.
- Bloqueio de terceira e quarta mensagem fria sem resposta humana.
- Bloqueio de mensagem livre fora da janela de 24h quando API/template exige template aprovado.
- Primeira mensagem humana vinda da clinica classificada como `human_replied`.
- Resposta humana sobe para modo `profissional`.
- Pedido de preco/demo sobe para modo `elite_300` com `elite_mode_reason`.
- Decisoes simples nao leem todo `conversation-reviews.jsonl`.
- Relatorio semanal usa modo `elite_300` com `data_loading_strategy = "aggregated_summary"`.
- Sugestao de melhoria da skill usa modo `elite_300` somente com `requires_human_approval = true`.
- Dashboard manual mostra indicadores de seguranca, custo, modos e bloqueios a partir de JSONL colado.
- Exemplos e JSONL usam dados ficticios.
- Scan ampliado nao encontrou segredo, token, telefone real, email privado ou dado sensivel nos arquivos de inteligencia comercial.

## Testes Criados Ou Atualizados

Arquivo: `apps/api/tests/unit/test_outreach_intelligence.py`

Coberturas adicionadas/reforcadas:

- Primeira mensagem fria permitida em modo economico.
- Auto-resposta nao vira resposta humana.
- Segunda mensagem apos auto-resposta permitida apenas se curta e comercial.
- Terceira e quarta mensagens frias bloqueadas sem modo elite.
- Janela de 24h bloqueia mensagem livre sem resposta humana.
- `do_not_contact` bloqueia qualquer nova mensagem.
- Primeira mensagem humana da clinica vira `human_replied`.
- `sobre o que seria?` e `pode mandar` entram em fluxo contextual/profissional.
- Pedido de preco/demo permite `elite_300` com justificativa.
- Mensagem fingindo paciente, pitch longo apos auto-resposta e link cedo demais aumentam risco/bloqueio.
- Link de demo apos permissao humana e permitido com risco recalculado.
- Decisao simples nao chama `load_jsonl`.
- Exemplos de conversation review validam contra schema.
- Schema tem todos os campos de seguranca e token.

## Testes Executados

- `python -m py_compile outreach-intelligence/scripts/outreach_intelligence.py`
- `.venv/Scripts/python.exe -m py_compile outreach-intelligence/scripts/outreach_intelligence.py`
- `python -m json.tool` em schemas, exemplos, JSONL e relatorio semanal
- `.venv/Scripts/python.exe -m pytest test_outreach_intelligence.py -q`
- `.venv/Scripts/python.exe -m pytest test_sales_outreach.py -q`
- `pnpm --filter @odontoflux/web build`
- Scan ampliado com `rg` para tokens, keys, senhas, emails privados e telefones reais
- Passada ampla: `.venv/Scripts/python.exe -m pytest . -q` dentro de `apps/api/tests/unit`

## Testes Aprovados

- Inteligencia comercial: 29 passed.
- Sales outreach: 50 passed.
- Web build: passou.
- JSON/JSONL: todos validos.
- `py_compile`: passou.
- Scan de segredos: sem achados.

## Falhas Restantes

A passada ampla de unitarios da API chegou ao resumo, mas o comando estourou timeout de 300s apos reportar:

- 160 passed
- 91 skipped
- 34 failed

Categorias das falhas fora do escopo desta rodada:

- `test_ai_autoresponder.py`: falhas de slots, wizard de agendamento, handoff/timeout, prompt/knowledge base e modos de scheduling.
- `test_backup_service.py`: backup de mutacao sem `tracked_items`.
- `test_sales_message_service.py`: edicao de template nao preserva o `is_default` esperado no segundo item.

Impacto sobre a inteligencia comercial:

- As falhas de `ai_autoresponder` e `backup_service` nao bloqueiam o motor offline de outreach, schemas, JSONL, dashboard ou politica de tokens.
- A falha de `test_sales_message_service.py` e adjacente ao fluxo comercial porque templates de mensagem podem afetar escolha/edicao de variantes. Recomenda-se corrigir em rodada separada antes de operar envio real em massa.
- `test_sales_outreach.py` passou inteiro, entao os gates comerciais existentes de outreach permanecem cobertos.

## Riscos Corrigidos

- Auto-resposta nao reduz risco nem vira resposta humana.
- Lead frio sem humano nao aciona modo elite.
- Terceira e quarta mensagens frias sao bloqueadas.
- Mensagem livre fora de 24h sem humano/template e bloqueada.
- Link de demo antes de resposta humana em lead frio e bloqueado.
- Pitch longo depois de auto-resposta aumenta risco.
- Mensagem que tenta parecer paciente aumenta risco.
- Decisao simples usa `data_loading_strategy = "minimal"` e nao le JSONL completo.
- Dashboard expoe contadores de bloqueio, stop contact, do not follow-up, 24h/template, modos e custo.

## Riscos Ainda Abertos

- Suite ampla da API tem falhas antigas fora do escopo que devem ser tratadas antes de uma liberacao geral.
- O teste amplo por raiz ainda e sensivel ao ambiente; para evitar `.env` local com variaveis extras, os testes focados foram executados a partir de `apps/api/tests/unit` com `PYTHONPATH=../..`.
- O dashboard continua manual/local, sem endpoint. Isso e intencional para evitar endpoint inseguro nesta fase.
- A regra de 24h depende de os produtores preencherem corretamente `outside_24h_window`, `template_required`, `template_used` e `last_human_reply_at`.

## Confirmacoes Obrigatorias

- Confirmado: lead frio sem resposta humana recebe no maximo 2 mensagens.
- Confirmado: resposta automatica nao conta como resposta humana.
- Confirmado: terceira mensagem fria sem resposta humana e bloqueada.
- Confirmado: mensagem humana da clinica muda o fluxo para resposta contextual.
- Confirmado: se a clinica mandar a primeira mensagem humana do dia, o sistema classifica como `human_replied`.
- Confirmado: lead frio sem resposta humana usa modo economico.
- Confirmado: modo elite 300% nao e usado em lead frio sem resposta humana.
- Confirmado: resposta humana sobe para modo profissional.
- Confirmado: pedido de preco, demo ou reuniao pode subir para modo elite 300%.
- Confirmado: o sistema escolhe o menor modo suficiente para tomar uma decisao segura.

## Proximos Passos Recomendados

1. Corrigir a falha de `test_sales_message_service.py`, por ser adjacente a templates comerciais.
2. Tratar as falhas antigas de `test_ai_autoresponder.py` em uma rodada separada de agendamento/IA clinica.
3. Garantir que o produtor real de JSONL preencha `first_human_message_at`, `last_human_reply_at`, `outside_24h_window` e `template_used`.
4. Fazer uma primeira rodada controlada com poucos leads reais, revisando manualmente todos os registros antes de escalar.
5. Manter o dashboard como leitura local/manual ate existir endpoint autenticado e agregado com controle de permissao.

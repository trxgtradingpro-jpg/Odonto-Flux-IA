# /adm/mensagens-para-clinicas

## Objetivo

A pagina `/adm/mensagens-para-clinicas` centraliza mensagens comerciais prontas para
clinicas cadastradas no CRM do `/adm`. Ela nao cria outro cadastro de clinica: cada
linha usa `ProspectAccount`, os dados comerciais ja preenchidos e a demo vinculada.

## Fluxo

1. O operador entra no `/adm` e abre `Mensagens prontas`.
2. Filtra por clinica, status, temperatura, demo ou busca livre.
3. Seleciona a clinica cadastrada no CRM.
4. Escolhe um template ou usa a sugestao automatica.
5. Clica em `Gerar mensagem pronta`.
6. O backend emite um novo link temporario da demo quando a demo ja existe.
7. A mensagem e renderizada com o link oficial no final.
8. O operador copia a mensagem completa e envia manualmente para a clinica.
9. O sistema registra preview, copia, copia de link e contato feito na timeline.

## Endpoints

- `GET /api/v1/admin/clinic-messages`
- `GET /api/v1/admin/clinic-messages/templates`
- `POST /api/v1/admin/clinic-messages/preview`
- `POST /api/v1/admin/clinic-messages/{prospect_id}/events`

## Regras

- A pagina usa o mesmo token administrativo do `/adm`.
- Clinicas marcadas como `nao contactar` aparecem com bloqueio visual e nao devem ser copiadas.
- Se a demo ainda nao foi criada, o preview orienta o operador a gerar a demo no CRM.
- O link de demo e temporario e segue a mesma politica existente de `demo_token`.
- Os eventos sao registrados em `ProspectTimelineEvent` com prefixo `sales_message.*`.

## Templates iniciais

- `primeiro_contato`
- `demo_enviada`
- `demo_acessada`
- `followup_quente`
- `pedir_reuniao`
- `reativar_parado`

## Validacao manual

1. Abra `/adm`, faca login e confirme que o botao `Mensagens prontas` aparece.
2. Abra `/adm/mensagens-para-clinicas`.
3. Selecione uma clinica com demo criada.
4. Gere a mensagem pronta e confirme que o link aparece no final.
5. Clique em `Copiar mensagem` e confira a timeline do prospect no CRM.
6. Selecione uma clinica sem demo e confirme o aviso de bloqueio.

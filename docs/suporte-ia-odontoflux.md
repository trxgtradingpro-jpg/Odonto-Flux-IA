# Suporte IA OdontoFlux

O Suporte IA do OdontoFlux responde dúvidas operacionais sobre o próprio sistema. Ele deve ser usado para orientar usuários sobre telas, botões, fluxos, configurações, agenda, WhatsApp, IA, pacientes, leads, equipe médica, usuários, permissões, segurança, LGPD, demos comerciais e implantação.

## Fontes de conhecimento

- Conhecimento versionado no backend em `system_support_service.py`.
- Documentação em `docs/`, quando disponível no ambiente.
- Dados reais do tenant logado, como unidades, serviços, profissionais e contadores operacionais.
- Configurações oficiais da clínica, incluindo catálogo de serviços, conhecimento IA e políticas operacionais.

## Regras de resposta

- Responder apenas com base no contexto autorizado.
- Não inventar comportamento, botão, tela, preço, política ou disponibilidade.
- Se a informação não estiver na base atual, informar que não encontrou com segurança e sugerir abrir incidente.
- Não fornecer diagnóstico, prescrição ou recomendação clínica.
- Priorizar caminhos práticos como `Configurações > Tema e Marca` ou `Agenda > Tela cheia`.
- Quando o comportamento depender de configuração, orientar o usuário a conferir a configuração oficial.

## Atualização conforme implantação

Ao implantar novas funcionalidades, atualize este documento ou os chunks versionados em `system_support_service.py`. O endpoint `/api/v1/support/ai-answer` usa a versão atual da base e registra a interação para auditoria.

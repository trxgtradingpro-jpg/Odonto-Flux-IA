# Guia de Operacao

## Rotina diaria
1. Monitorar fila `outbox_messages`
2. Monitorar `automation_runs` com falha
3. Revisar tempo medio de resposta no dashboard
4. Revisar fila humana (conversas pendentes)
5. Revisar trilha `ai_autoresponder_decisions` para bloqueios/handoff

## Rotina semanal
1. Revisar campanhas e taxa de resposta
2. Revisar no-show e recuperacao
3. Revisar usuarios/permissoes
4. Revisar trilha de auditoria

## LGPD e seguranca
- Restringir acesso por menor privilegio
- Exportar dados de paciente sob demanda
- Anonimizar/arquivar registros quando aplicavel
- Evitar dados sensiveis em logs
- Revisar prompt e guardrails de IA a cada ciclo operacional

## Operacao do IA Auto-Responder
1. Ligar toggle global em `Configuracoes > IA Auto-Responder`.
2. Definir horario operacional e regra fora do horario (`handoff`, `allow` ou `silent`).
3. Definir limite de respostas consecutivas e threshold de confianca.
4. Configurar override por unidade quando necessario.
5. Monitorar:
   - taxa de automacao
   - taxa de handoff
   - tempo medio de 1a resposta IA
   - taxa de falha de envio IA

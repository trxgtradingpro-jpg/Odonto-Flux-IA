# Decisoes Arquiteturais

1. Monorepo com apps isolados e pacotes compartilhados
   - Facilita versionamento conjunto de API + Web + infra.

2. Multi-tenancy logico por `tenant_id`
   - Menor custo inicial que isolamento fisico por banco.
   - Permite evoluir para sharding futuro.

3. Outbox para mensagens externas
   - Garante resiliencia, retries e observabilidade.

4. Motor de automacao orientado a eventos + scheduler
   - Suporta jornadas operacionais sem hardcode por fluxo.

5. IA com camada abstrata
   - Facilita troca de provider e aplica guardrails centralizados.

6. Seed rico e focado em demo comercial
   - Acelera onboarding e testes de ponta a ponta.

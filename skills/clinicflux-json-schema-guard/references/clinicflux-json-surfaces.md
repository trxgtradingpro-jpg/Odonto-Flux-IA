# ClinicFlux JSON Surfaces

Use this as a quick map, not as a replacement for current `rg`.

## Backend

- Pydantic schemas: `apps/api/app/schemas`
- API endpoints: `apps/api/app/api`
- Services using structured payloads: `apps/api/app/services`
- Tasks/workers: `apps/api/app/tasks`
- Tests and fixtures: `apps/api/tests`
- Settings/env parsing: `apps/api/app/core/config.py`

## Frontend

- Admin pages and API clients: `apps/web/app`, `apps/web/lib`, `apps/web/hooks`
- TypeScript types may live near page code rather than in one central folder.
- Check both snake_case API fields and camelCase UI transforms.

## WhatsApp And Sales Outreach

- Bridge and local Selenium payloads: `apps/msg/whatsapp_web.py`
- Internal WhatsApp bridge endpoints and services under `apps/api/app`
- Sales outreach state, review decisions, and LLM JSON decisions often cross service, worker, and DB state.

## JSONB And Stored Metadata

Search for keys before changing payloads stored in metadata/config columns. Use both quoted and unquoted variants:

- `"field_name"`
- `'field_name'`
- `fieldName`
- `metadata`
- `config`
- `payload`
- `settings`

## Useful Searches

```powershell
rg "field_name|fieldName" apps/api apps/web apps/msg
rg "response_format|json_schema|json_object|structured" apps/api
rg "BaseModel|Field\\(" apps/api/app
rg "JSONB|metadata|config|payload|settings" apps/api/app
```

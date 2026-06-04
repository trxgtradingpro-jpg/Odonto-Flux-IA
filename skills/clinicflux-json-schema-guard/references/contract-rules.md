# Contract Rules

Use this when changing JSON shape, schema, structured LLM output, or integration payloads.

## Schema Evolution

- Additive changes are safer than breaking changes.
- New backend fields should usually be optional or have defaults until every producer is updated.
- Renames need a compatibility period: accept old and new names or migrate all stored data.
- Removals require proof that no backend, frontend, worker, prompt, fixture, or external webhook still uses the field.
- Enum changes require producer, consumer, UI label, tests, and stored-data review.

## Producer And Consumer Search

Search by:

- exact field name
- snake_case and camelCase variants
- endpoint route
- Pydantic schema/class name
- TypeScript interface/type name
- JSONB key access
- prompt text that names the field

Do not trust a single search result. Many ClinicFlux contracts cross API, worker, admin UI, and WhatsApp automation.

## LLM Structured Output

- Treat model JSON as untrusted input.
- Prompt for one JSON object only when the parser expects an object.
- Keep schema short and explicit.
- Require all fields that downstream logic assumes.
- Validate and fallback before user-visible behavior can go silent.
- Do not place Markdown fences around JSON consumed by code.
- If model output is used for send/hold decisions, include a safe default such as `wait` or fallback text.

## Examples And Fixtures

- Every example should parse as strict JSON.
- Do not use comments to explain fields inside JSON. Explain outside the JSON.
- Keep sample IDs and phone numbers clearly fake unless testing a real controlled fixture.
- When examples are copied into prompts, preserve valid JSON syntax.

## Failure Pattern To Avoid

- "Only changed response text" can still break code if a parser expects JSON.
- "Only removed unused field" can break frontend if the field is rendered conditionally.
- "Only added enum value" can break dashboards if labels/colors do not handle it.
- "Only changed prompt" can break automation if the AI returns prose around JSON.

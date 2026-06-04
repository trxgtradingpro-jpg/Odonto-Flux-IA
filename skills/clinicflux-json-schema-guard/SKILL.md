---
name: clinicflux-json-schema-guard
description: Use when creating, editing, reviewing, or returning JSON, JSON Schema, Pydantic schemas, API payloads, webhook bodies, LLM structured outputs, JSONB fields, examples, fixtures, or integrations in ClinicFlux AI/OdontoFlux; prevents invalid JSON and unsafe contract changes that could break backend, frontend, automation, or WhatsApp flows.
metadata:
  short-description: Guard JSON contracts safely
---

# ClinicFlux JSON Schema Guard

Protect JSON contracts. Be strict, fast, and compatible. Saving tokens is good; breaking a payload shape is not.

## Fast Protocol

1. Identify the contract owner before editing: Pydantic model, TypeScript type, OpenAPI route, JSON Schema, DB JSONB shape, LLM prompt schema, fixture, or test.
2. Find both producer and consumer before changing fields. Use `rg` for exact field names and endpoint paths.
3. Never remove or rename a field unless all consumers, tests, migrations/defaults, and UI usage are updated or a compatibility shim exists.
4. If changing JSON shape, update schema/types/examples/tests together.
5. Validate every JSON example/payload you create with strict JSON: no comments, no trailing commas, no single quotes, no text outside the object/array.
6. For LLM JSON outputs, force a single valid JSON object/array and require parser-safe fallback when runtime user output depends on it.
7. If the user asks for "somente JSON", return only JSON. No Markdown, no explanation.

## Load References Only When Needed

- Need exact guardrails for schema evolution or AI structured output: read `references/contract-rules.md`.
- Need common ClinicFlux JSON surfaces and search hints: read `references/clinicflux-json-surfaces.md`.
- Need to validate a payload/file: run `scripts/validate_json_payload.py`.

## Default Checks Before Editing

- Search field and endpoint usage with `rg`.
- Check nearby tests/fixtures.
- Preserve backward compatibility by adding optional fields/defaults before removing old fields.
- Prefer explicit schema validation over string parsing.
- Keep examples minimal but executable.

## Safe Output Rules

- Valid JSON is data only. Do not include comments or prose inside JSON.
- Use double quotes for all strings and keys.
- Use `true`, `false`, and `null`, not Python/JS variants.
- Do not leave trailing commas.
- Do not serialize dates ambiguously when ISO timestamps are expected.
- Do not invent enum values. Find the current enum first.

## Validation Bar

Before final response, state:

- which JSON/schema surface was protected
- which files were created or changed
- what validation ran
- any compatibility risk that remains

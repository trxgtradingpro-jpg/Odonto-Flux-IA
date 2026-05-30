# Outreach Dashboard Spec

## Route

`/adm/inteligencia-comercial`

## Goal

Give the commercial operator a simple internal view of outreach intelligence without adding unauthenticated APIs or external integrations.

## Initial Implementation

The first version is a client-side admin page that:

- uses the existing `/adm` token/session pattern
- checks the existing `adm_outreach_automation` permission
- shows safe sample data by default
- lets the operator paste JSONL content from `outreach-reviews/conversation-reviews.jsonl`
- parses JSONL locally in the browser
- summarizes leads and messages without sending the pasted data to a new endpoint

## Views

The page should show:

- hot leads
- leads that replied
- leads that opened demo
- leads that tested WhatsApp
- leads that asked price
- stalled leads
- best messages
- worst messages
- next actions recommended

## Privacy

- Do not expose `outreach-reviews/conversation-reviews.jsonl` through a public Next route.
- Do not create an unauthenticated API endpoint to read local JSONL files.
- Do not show phone numbers.
- Prefer `lead_id`, `clinic_name`, stage, offer lane, and scores.

## Future Upgrade Path

If this dashboard becomes production-critical, add a FastAPI admin endpoint protected by the existing admin auth model. That endpoint should:

- validate admin permissions
- read from a database or approved storage layer
- redact sensitive fields
- paginate results
- preserve the same schemas

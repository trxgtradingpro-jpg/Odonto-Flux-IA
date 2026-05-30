# Outreach Testing Guide

## Focused Tests

Run the new outreach intelligence tests:

```powershell
python -m pytest apps/api/tests/unit/test_outreach_intelligence.py -q
```

These tests validate:

- JSONL syntax.
- JSON schema files.
- Examples against schemas.
- Message evaluation.
- Lead scoring.
- Next best action.
- Objection library.
- Commercial brain.
- Skill update suggestions.
- Secret hygiene in the new outreach files.
- Skill frontmatter.

## Existing Relevant Tests

Run the existing sales outreach unit tests:

```powershell
python -m pytest apps/api/tests/unit/test_sales_outreach.py -q
```

If the local environment lacks database services or required test settings, record the failure/blocker in the final report instead of hiding it.

## Frontend Validation

Run:

```powershell
pnpm --filter @odontoflux/web build
```

This checks that the new `/adm/inteligencia-comercial` page compiles with the existing Next app.

## JSON Validation

Strict JSON checks:

```powershell
python skills/clinicflux-json-schema-guard/scripts/validate_json_payload.py outreach-intelligence/commercial-brain.json outreach-reports/weekly-summary-2026-05-29.json
```

JSONL checks are covered by pytest because JSONL is not one single JSON document.

## Manual Acceptance Checklist

- `skills/seo/SKILL.md` still has valid frontmatter.
- All schemas parse as JSON.
- All examples are fictional and schema-compatible.
- `conversation-reviews.jsonl` has one JSON object per line.
- Message evaluation rewrites unsafe messages below 85/100.
- Lead scoring routes no-site clinics to website/SEO.
- Next Best Action stops contact on refusal.
- Weekly summary can be generated from reviews.
- Dashboard page exists under `/adm/inteligencia-comercial`.
- No secrets were added.

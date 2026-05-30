# Outreach Intelligence Implementation Plan

## 1. What will change in the skill

The `local-seo-outreach-playbook` skill will remain the central sales playbook and will be expanded from static message guidance into an operating system for continuous commercial improvement.

Planned skill additions:

- Pre-send Message Sense Check with a mandatory 85/100 approval bar.
- Post-conversation Review with a structured JSON object for each conversation.
- Lead scoring rules for website status, Google rating, review count, category, WhatsApp dependency, and digital maturity.
- Message evaluation rules with commercial clarity, context match, one objective, repetition, WhatsApp naturalness, risk, burn risk, and rewrite guidance.
- AI committee checklist: `sales_judge`, `local_seo_judge`, `whatsapp_judge`, `persuasion_judge`, and `risk_judge`.
- Digital Twin simulation before sending a message.
- Next Best Action rules for routing to message, responsible person, demo, video, summary, meeting, wait, follow-up, stop contact, offer switch, or proposal.
- Anti-repetition system for openings, already-answered questions, and similar messages.
- Microconversion tracking.
- Anti-hallucination commercial rules.
- Human-approval-only skill update suggestion loop.

Compatibility decision:

- Preserve the current Google Places signal logic, offer lane routing, message examples, quality bar, red flags, and references.
- Add new sections after the current workflow/rules instead of deleting useful existing content.
- Keep the same frontmatter `name` and `description`.

## 2. Files to create

Root-level documents requested explicitly:

- `OUTREACH_INTELLIGENCE_IMPLEMENTATION_PLAN.md`
- `OUTREACH_INTELLIGENCE_README.md`
- `OUTREACH_TESTING_GUIDE.md`
- `OUTREACH_DATA_DICTIONARY.md`
- `OUTREACH_DASHBOARD_SPEC.md`

Operational data directories:

- `outreach-reviews/conversation-reviews.jsonl`
- `outreach-reports/weekly-summary-YYYY-MM-DD.json`
- `outreach-intelligence/commercial-brain.json`
- `outreach-intelligence/objection-library.jsonl`
- `outreach-intelligence/skill-update-suggestions.jsonl`
- `outreach-intelligence/lead-profiles/README.md`

Schema directory:

- `outreach-intelligence/schemas/conversation-review.schema.json`
- `outreach-intelligence/schemas/lead-profile.schema.json`
- `outreach-intelligence/schemas/message-evaluation.schema.json`
- `outreach-intelligence/schemas/objection.schema.json`
- `outreach-intelligence/schemas/campaign-summary.schema.json`
- `outreach-intelligence/schemas/skill-update-suggestion.schema.json`

Examples directory:

- `outreach-intelligence/examples/sample-conversation-review.json`
- `outreach-intelligence/examples/sample-lead-profile.json`
- `outreach-intelligence/examples/sample-message-evaluation.json`
- `outreach-intelligence/examples/sample-objection.json`
- `outreach-intelligence/examples/sample-campaign-summary.json`
- `outreach-intelligence/examples/sample-skill-update-suggestion.json`

Script directory:

- `outreach-intelligence/scripts/outreach_intelligence.py`
- `outreach-intelligence/scripts/generate_weekly_summary.py`

Tests:

- `apps/api/tests/unit/test_outreach_intelligence.py`

Dashboard:

- `apps/web/app/adm/inteligencia-comercial/page.tsx`

Skill update target:

- `skills/seo/SKILL.md`

The installed Codex copy was also found at:

- `C:\Users\Gui Trader\.codex\skills\local-seo-outreach-playbook\SKILL.md`

The implementation will keep the project copy as the repository source of truth and, if safely possible, mirror the same updated playbook into the installed copy so future Codex runs use the upgraded workflow.

## 3. Schemas to use

All schemas will be strict JSON Schema documents using draft 2020-12 style metadata, `additionalProperties: false` where practical, typed fields, enums for controlled vocabulary, and required fields for the operational review flow.

Primary contracts:

- `conversation-review.schema.json`: post-conversation review and JSONL line contract.
- `lead-profile.schema.json`: one file per lead under `lead-profiles`.
- `message-evaluation.schema.json`: pre-send evaluation result.
- `objection.schema.json`: objection response library line contract.
- `campaign-summary.schema.json`: weekly summary and campaign report contract.
- `skill-update-suggestion.schema.json`: suggestion-only skill improvement contract.

Schema compatibility rules:

- Additive changes are allowed.
- Field removals or renames require test updates and documentation updates.
- Examples must validate against schemas.
- JSONL files must contain one valid JSON object per non-empty line.

## 4. Tests to create

Automated tests will cover:

- JSONL parsing for `conversation-reviews.jsonl`, `objection-library.jsonl`, and `skill-update-suggestions.jsonl`.
- JSON syntax and baseline JSON Schema shape for all schema files.
- Example validation against the matching schema.
- Message evaluation scoring, burn risk, rewrite suggestion, AI committee output, and digital twin output.
- Lead scoring for no-site, weak-site, strong-site, Google rating, reviews, WhatsApp dependency, and recommended offer.
- Next Best Action decisions for responsible routing, demo, price objection, waiting, stop contact, and offer switching.
- Objection library required fields and metrics.
- Commercial brain required accumulated-intelligence sections.
- Skill update suggestions requiring human approval.
- Secret scan over the new outreach intelligence files and updated skill files.
- Skill frontmatter validity with `name` and `description`.

The test implementation will avoid new third-party dependencies. It will use stdlib JSON parsing and a minimal in-test schema validator for the subset of JSON Schema features used by these files.

## 5. Validation flow

Validation will run in this order:

1. Validate all new JSON and JSONL files.
2. Run the new focused pytest file:
   - `python -m pytest apps/api/tests/unit/test_outreach_intelligence.py -q`
3. Run existing relevant sales outreach tests if feasible:
   - `python -m pytest apps/api/tests/unit/test_sales_outreach.py -q`
4. Run frontend build/type validation if feasible:
   - `pnpm --filter @odontoflux/web build`

If a full existing test suite is too slow or blocked by environment/database requirements, the final report must say exactly what ran and what was blocked.

## 6. How to avoid root clutter

Only the documents explicitly requested by name will be created in the repository root.

Everything operational will be grouped under:

- `outreach-intelligence/`
- `outreach-reviews/`
- `outreach-reports/`

No random temp files, personal lead dumps, screenshots, tokens, or real clinic transcripts will be added.

Runtime/generated weekly reports should follow the naming convention:

- `outreach-reports/weekly-summary-YYYY-MM-DD.json`

Lead history files should stay inside:

- `outreach-intelligence/lead-profiles/{lead_id}.json`

## 7. Compatibility with the current project

The implementation will be intentionally low-coupling:

- No database migrations.
- No external integrations.
- No new API keys or secrets.
- No changes to WhatsApp bridge behavior.
- No changes to existing sales automation send logic unless explicitly documented.
- The dashboard will be a simple internal `/adm` view that can parse safe JSONL/report data locally in the browser and show sample-safe empty states, rather than exposing a new unauthenticated data API.
- The Python intelligence script will be a standalone utility that can be tested without Docker, Postgres, Redis, or the live WhatsApp bridge.

Privacy and safety rules:

- Examples use fictional clinics only.
- Do not store full phone numbers unless operationally necessary.
- Never store API keys, access tokens, refresh tokens, passwords, or private clinic data in examples.
- Commercial claims must use possibility/opportunity language, not guaranteed outcomes.

## 8. Complete documented flow

The finished system will document and test this flow:

`lead -> lead scoring -> message evaluation -> approved/rewrite -> conversation review JSONL -> weekly report -> commercial brain update candidate -> skill update suggestion requiring human approval`

This flow creates a feedback loop without automatically modifying the skill or making unsupported commercial promises.

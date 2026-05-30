# Outreach Intelligence README

This folder system turns the ClinicFlux AI local SEO outreach playbook into a continuous commercial improvement loop.

## Structure

- `skills/seo/SKILL.md`: central playbook and operating rules.
- `outreach-intelligence/schemas/`: JSON Schema contracts.
- `outreach-intelligence/examples/`: fictional safe examples.
- `outreach-intelligence/scripts/`: offline scoring, evaluation, next action, and weekly summary helpers.
- `outreach-intelligence/commercial-brain.json`: accumulated patterns and recommended strategy.
- `outreach-intelligence/objection-library.jsonl`: objection responses and performance.
- `outreach-intelligence/lead-profiles/`: one optional JSON file per lead.
- `outreach-intelligence/skill-update-suggestions.jsonl`: proposed playbook changes, never auto-applied.
- `outreach-reviews/conversation-reviews.jsonl`: one structured conversation review per line.
- `outreach-reports/weekly-summary-YYYY-MM-DD.json`: weekly summary output.
- `apps/web/app/adm/inteligencia-comercial/page.tsx`: simple internal dashboard view.

## Complete Flow

1. Capture lead context from Google Places, Google Maps, local SERP, manual research, or CRM.
2. Run lead scoring using `calculate_lead_score(...)`.
3. Draft the next message from the playbook.
4. Run `evaluate_message(...)` before presenting or sending the message.
5. If `approved_to_send` is false or score is below 85, use `corrected_message` or rewrite.
6. After the conversation checkpoint, append one JSON object to `outreach-reviews/conversation-reviews.jsonl`.
7. Generate the weekly report.
8. Review patterns in `commercial-brain.json`.
9. Add skill improvement candidates to `skill-update-suggestions.jsonl`.
10. Apply skill changes only after human approval.

## Registering a Conversation

Use the schema:

`outreach-intelligence/schemas/conversation-review.schema.json`

Append one compact JSON object per line to:

`outreach-reviews/conversation-reviews.jsonl`

Rules:

- Each non-empty line must be valid JSON.
- Use internal `lead_id`, not a phone number.
- Use fictional/anonymized data in examples.
- Do not store API keys, tokens, passwords, refresh tokens, private notes, or full phone numbers unless approved and necessary.

## Evaluating a Message

Use the offline engine:

```powershell
python - <<'PY'
import importlib.util
from pathlib import Path

path = Path("outreach-intelligence/scripts/outreach_intelligence.py")
spec = importlib.util.spec_from_file_location("outreach_intelligence", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

result = mod.evaluate_message(
    "Oi, aqui e o time comercial da ClinicFlux AI. Encontrei voces no Google. Quem cuida do WhatsApp?",
    {
        "clinic_name": "Clinica Exemplo",
        "source": "google_places",
        "has_website": True,
        "website_quality": "good",
        "latest_reply": "",
        "previous_messages": []
    },
)
print(result)
PY
```

Approval rule:

- `message_quality_score >= 85`
- `risk_score <= 35`
- `burn_risk` is not `high` or `critical`
- `approved_to_send` is true

## Lead Scoring

`calculate_lead_score(...)` returns:

- `lead_score`
- `revenue_potential`
- `digital_maturity_score`
- `whatsapp_dependency`
- `likely_pain`
- `recommended_offer`

Interpretation:

- `website_seo`: no site or no useful local trust layer.
- `audit`: weak or unclear site.
- `clinicflux_ai`: site already exists and WhatsApp/agendamento is likely the conversion bottleneck.
- `demo`: strong engagement or responsible person identified.
- `stop_contact`: refusal, opt-out, or high burn risk.

## Reading JSONL

JSONL is one JSON object per line. This makes it easy to append reviews without rewriting a large array.

Example:

```json
{"lead_id":"lead-demo-001","clinic_name":"Clinica Aurora Ficticia","clinic_replied":true}
```

Do not add commas between lines.

## Weekly Report

Generate a weekly report:

```powershell
python outreach-intelligence/scripts/generate_weekly_summary.py --input outreach-reviews/conversation-reviews.jsonl --output-dir outreach-reports
```

The output file will be:

`outreach-reports/weekly-summary-YYYY-MM-DD.json`

## Skill Update Suggestions

Add suggestions to:

`outreach-intelligence/skill-update-suggestions.jsonl`

Each suggestion must set:

`requires_human_approval: true`

Never auto-update the skill from a suggestion file. Treat suggestions as a review queue.

## Using This at 100, 500, and 1000 Leads

At 100 leads:

- Track all reviews.
- Compare two or three message variants.
- Identify top objections.

At 500 leads:

- Segment reports by website quality, source, city, and offer lane.
- Retire low-performing openings.
- Promote winning objection responses to the commercial brain.

At 1000 leads:

- Require weekly review before new message variants.
- Keep separate reporting for no-site, weak-site, and strong-site clinics.
- Use skill update suggestions only when pattern count and confidence justify it.

## Safety

- Do not promise guaranteed commercial results.
- Do not invent patient volume, clinic revenue, integrations, or losses.
- Use possibility language: "pode", "parece", "oportunidade", "validar", "testar".
- Do not expose secrets or sensitive clinic information.

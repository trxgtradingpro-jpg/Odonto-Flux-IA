---
name: local-seo-outreach-playbook
description: Use when analyzing local-business sales conversations, improving WhatsApp outreach for leads sourced from Google Search or Maps, deciding when to sell a site versus ClinicFlux AI SaaS, or aligning sales messages with local SEO intent and trust signals.
---

# Local SEO Sales Playbook

Use this skill when the task is not only "write a sales message", but "find the best moment to sell the right thing to a local business lead".

## Goal

Create elite, humanized local-business sales conversations that can score 90/100 or higher:

- sound like a real commercial contact, not a patient
- match the likely query that surfaced the clinic
- build trust fast
- route quickly to the person responsible for WhatsApp, agenda, or reception
- decide whether the best offer is website/SEO, ClinicFlux AI SaaS, or both
- avoid repetitive or robotic follow-ups that hurt scale

## Google Places signals

Use Google Places data before choosing the pitch:

- `has_website = false`: the website/SEO offer is usually the best first commercial angle.
- `has_website = true`: lead with ClinicFlux AI SaaS unless the site is clearly weak, outdated, slow, missing booking, missing WhatsApp CTA, or not aligned with local search intent.
- `rating`, `reviews`, `category`, `address`, `business_status`, `opening_hours`, and `website_url` are sales context, not decoration.
- Do not shame the clinic for not having a site. Use opportunity language.

## Core workflow

1. Identify the acquisition context.
   - If the lead came from Google Places, Google Maps, or a local SERP scrape, assume local commercial intent.
   - If the clinic asks `como nos achou?` or `o que escreveu na busca?`, answer concretely.

2. Decide the offer lane.
   - No website: sell a local SEO website that helps patients find, trust, and contact the clinic.
   - Website exists but weak: sell a quick SEO/conversion audit before offering rebuild.
   - Website exists and is acceptable: sell ClinicFlux AI to capture, respond to, and convert the demand the site and Google already generate.
   - Strong inbound engagement: sell the demo, not another discovery question.

3. Classify the conversation opening.
   - Good opening: commercial identity + source transparency + one routing question.
   - Weak opening: generic question, patient-like wording, or hidden commercial intent.
   - Bad opening: wording that makes ClinicFlux AI sound like the clinic itself.

4. Score the flow on seven dimensions.
   - Intent match
   - Persona clarity
   - Trust and relevance
   - Decision-maker routing
   - Product-fit timing
   - Website/SEO opportunity use
   - Scalability without sounding repetitive

5. Find the best sales moment.
   - Do not sell before source and identity are clear.
   - Sell after the clinic answers, asks source, confirms reception, shares the responsible person, or exposes a gap.
   - If the clinic asks a direct question, answer it first, then bridge to the offer.

6. Repair the message sequence.
   - If the clinic answers like patient support, clarify `meu contato e comercial`.
   - If the clinic asks source/keyword, answer it before pitching.
   - If the clinic shares a new responsible contact, restart with a shorter and cleaner opener.
   - If the clinic declines, stop politely. Do not keep educating the lead.

7. Recommend the next best message.
   - Keep one objective per turn.
   - Prefer one short paragraph over a long pitch.
   - Avoid localhost links, duplicated lines, or repeated intros.

## Message rules

- Open with identity early: `Aqui e o time comercial da ClinicFlux AI`.
- Mention source when relevant: `Encontrei a clinica no Google`.
- Use likely local-intent language: `agendamentos`, `WhatsApp`, `recepcao`, `atendimento`.
- Ask only one routing question at a time.
- Never pretend to be a patient.
- Never start with `Como posso ajudar?` in outbound sales.
- Never ignore a direct question from the clinic.
- Never sell both site and SaaS in the same first pitch unless the lead asks for both.

## Cold WhatsApp Outreach Safety Policy

This policy is mandatory for ClinicFlux AI cold outreach. It reduces spam risk, prevents commercial insistence, and keeps cold conversations respectful.

Definitions:

- Cold lead: clinic found through Google, Google Maps, Google Places, Instagram, public website, or a prospecting list, with no prior request for contact.
- Automatic reply: welcome message, automatic menu, greeting, request for name/procedure, or any WhatsApp Business/clinic automation response.
- Human reply: message clearly written by a person at the clinic, reception, management, dentist, owner, or responsible staff member.

Core limit:

- For cold leads, suggest at most 2 outbound WhatsApp messages when there is no human reply.
- Automatic replies do not count as human replies and are not strong opt-in.
- If the first outbound message receives only an automatic reply, a second short clarification is allowed, as long as it is transparent that the contact is commercial.
- If there is no human reply after the second outbound message, stop contact.
- Do not suggest a third, fourth, or fifth cold message without a human reply.
- Do not insist, educate the lead, or try to route around silence.

24-hour rule awareness:

- When using WhatsApp Business Platform/API, do not suggest a free-form message outside the 24-hour window if the lead has not sent a human reply.
- Outside the 24-hour window, allow only an approved template when it is compatible with the provider/API policy.
- If there is no approved template or clear permission, recommend `stop_contact` or wait for a new interaction.
- Never try to bypass the 24-hour window.

Auto-reply handling:

- When the clinic sends an automatic reply after the first cold message, classify the state as:

```json
{
  "auto_reply_received": true,
  "human_reply_received": false,
  "reply_type": "auto_reply",
  "detected_persona": "automation",
  "interest_level": "unknown",
  "recommended_action": "send_second_commercial_clarification",
  "max_remaining_cold_messages": 1,
  "analysis_mode": "economico",
  "token_efficiency_mode": "economico",
  "token_budget_level": "low",
  "should_use_elite_mode": false,
  "estimated_token_cost_level": "low",
  "data_loading_strategy": "minimal",
  "large_context_allowed": false
}
```

- After the second outbound message with no human reply, classify the state as:

```json
{
  "auto_reply_received": true,
  "human_reply_received": false,
  "reply_type": "no_human_reply_after_second_message",
  "recommended_action": "stop_contact",
  "max_remaining_cold_messages": 0,
  "do_not_follow_up": true,
  "analysis_mode": "economico",
  "token_efficiency_mode": "economico",
  "token_budget_level": "low",
  "should_use_elite_mode": false,
  "estimated_token_cost_level": "low",
  "data_loading_strategy": "minimal",
  "large_context_allowed": false
}
```

Allowed two-message flow:

- Message 1: short initial contact, no aggressive link, no long pitch, and no pretending to be a patient.
- Example: `Oi, tudo bem?`
- More transparent example: `Oi, tudo bem? Encontrei a clinica no Google. Aqui e o time comercial da ClinicFlux AI. Posso falar com quem cuida do WhatsApp e dos agendamentos?`
- Message 2 after an automatic reply: `Obrigado. Meu contato e comercial, nao e para agendamento de paciente. Aqui e o time da ClinicFlux AI. Queria falar com quem cuida do WhatsApp e dos agendamentos da clinica. Se nao fizer sentido, sem problema.`
- After that, if there is no human reply, stop.

Risk scoring update:

- First personalized cold message: `risk_score` 40-50.
- Automatic reply received: does not reduce risk or interest uncertainty; the lead remains cold.
- Second message after automatic reply: `risk_score` 35-50 when short, transparent, and commercial.
- Third message without human reply: `risk_score` 75-90 and must be blocked.
- Fourth message without human reply: `risk_score` 90-100 and must be blocked.
- If there is a real human reply, recalculate risk from the message content and conversation stage.

JSONL review fields for cold WhatsApp safety:

- `cold_outreach_message_count`
- `auto_reply_received`
- `human_reply_received`
- `last_human_reply_at`
- `first_human_message_received`
- `first_human_message_at`
- `outside_24h_window`
- `template_required`
- `template_used`
- `stop_contact_required`
- `do_not_follow_up`
- `opt_in_status`
- `do_not_contact`
- `max_remaining_cold_messages`
- `analysis_mode`
- `token_efficiency_mode`
- `token_budget_level`
- `should_use_elite_mode`
- `elite_mode_reason`
- `estimated_token_cost_level`
- `data_loading_strategy`
- `large_context_allowed`

Allowed `opt_in_status` values:

- `unknown`
- `public_business_contact`
- `explicit_opt_in`
- `human_replied`
- `requested_information`
- `do_not_contact`

## Token Efficiency Policy

Use `token_efficiency_policy` for every commercial intelligence decision. Always choose the smallest mode that can make a safe decision.

Mode `economico`:

- Use for cold leads, first cold messages, automatic replies, no human reply, quick risk checks, third-message blocking, and basic next-action classification.
- Do only: classify cold lead/auto reply/human reply, validate message safety, apply the 2-message cold limit, avoid long pitch, avoid early links, detect stop-contact requests, choose a simple next action, and register minimal JSONL fields.
- Do not use digital twin, full AI committee, long ROI analysis, large histories, full `conversation-reviews.jsonl`, complete reports, `commercial-brain.json` strategy updates, or skill-improvement suggestions.

Mode `profissional`:

- Use after a real human reply, a question, `pode mandar`, `sobre o que seria?`, a real chance of conversation, full JSONL review, light lead-profile update, short objection analysis, or contextual response.
- May use message evaluation, risk score, next best action, intent/persona classification, short contextual reply, and demo/summary recommendation when appropriate.

Mode `elite_300`:

- Use only for hot leads, price/demo/proposal/meeting requests, implementation or WhatsApp/agenda integration questions, demo tests, weekly reports, skill suggestions, campaign analysis, or `commercial-brain.json` consolidation.
- May use digital twin, AI evaluation committee, ROI analysis, full lead history, campaign comparison, objection library, commercial brain, strategic reports, message ranking, and accumulated-pattern analysis.

Hard token rules:

- Cold lead without human reply defaults to `analysis_mode = "economico"`.
- Automatic replies stay in `analysis_mode = "economico"`.
- Real human replies move to `analysis_mode = "profissional"` unless there is a strong buying signal.
- Price, demo, meeting, proposal, implementation, WhatsApp/agenda integration, demo click, or demo test may move to `analysis_mode = "elite_300"` with `elite_mode_reason`.
- Never use `elite_300` for a cold lead without a human reply.
- Simple decisions must not read all `conversation-reviews.jsonl`; use `data_loading_strategy = "minimal"`, `lead_profile_only`, or `recent_events_only`.
- Weekly reports may use aggregated loading; skill improvement suggestions may use elite mode only with human approval.

Token policy fields:

- `analysis_mode`
- `token_efficiency_mode`
- `token_budget_level`
- `should_use_elite_mode`
- `elite_mode_reason`
- `estimated_token_cost_level`
- `data_loading_strategy`
- `large_context_allowed`

Allowed values:

- `analysis_mode`: `economico`, `profissional`, `elite_300`
- `token_efficiency_mode`: `economico`, `profissional`, `elite_300`
- `token_budget_level`: `low`, `medium`, `high`
- `estimated_token_cost_level`: `low`, `medium`, `high`, `very_high`
- `data_loading_strategy`: `minimal`, `lead_profile_only`, `recent_events_only`, `aggregated_summary`, `full_campaign_analysis`

First human message rule:

- If the first useful message of the day comes from the clinic, or the clinic replies humanly after a previous cold approach, classify it as a real human conversation.
- Set `human_reply_received = true`, `opt_in_status = "human_replied"`, `next_best_action = "reply_contextually"`, `analysis_mode = "profissional"`, `token_budget_level = "medium"`, and `data_loading_strategy = "lead_profile_only"` or `recent_events_only`.
- A real human reply removes the cold no-reply block for that point in the conversation, but it does not allow spam, pressure, long pitches, or ignoring stop-contact requests.

Human reply examples:

- `Bom dia, sobre o que seria?`
- `Pode mandar.`
- `Quem fala?`
- `Como funciona?`
- `Fala com a Bruna nesse numero.`
- `Qual o valor?`
- `Pode explicar melhor?`

## Strong patterns

### First contact from Google / Maps lead

`Oi, tudo bem? Encontrei a clinica no Google pesquisando por atendimento odontologico na regiao. Aqui e o time comercial da ClinicFlux AI. Posso falar com quem cuida do WhatsApp e dos agendamentos?`

### First contact when Google Places shows no website

```text
Oi, tudo bem?

Notei que a clínica ainda não possui um site profissional.

Eu já montei um modelo de site para a clínica e gostaria de mostrar ao responsável.

Quem seria a pessoa ideal para eu encaminhar?
```

### When website exists and the clinic asks how we can help

`Perfeito. Vi a clinica pelo Google e meu contato e comercial. A ideia e simples: ajudar voces a aproveitar melhor os pacientes que chegam pelo Google, site e WhatsApp, com resposta mais rapida e mais controle da agenda. Quem cuida disso por ai?`

### When the clinic asks how you found them

`Encontrei voces no Google pesquisando por clinica odontologica na regiao. Nosso contato e comercial: ajudamos clinicas a organizar o WhatsApp e os agendamentos para responder mais rapido e perder menos oportunidades.`

### When the clinic asks what was searched

`Pesquisei no Google por algo como "clinica odontologica em [bairro/cidade]". Vi a clinica de voces e achei que faria sentido mostrar nossa solucao para atendimento e agenda.`

### When the clinic answers like patient intake

`Perfeito, obrigado. Meu contato e comercial, nao e para agendamento de paciente. Queria falar com quem organiza o atendimento e os agendamentos da clinica no WhatsApp.`

### When the clinic sends the first useful human message

`Bom dia! Aqui e o time comercial da ClinicFlux AI. Meu contato e sobre atendimento e agendamentos no WhatsApp, nao e para consulta. Voces tem alguem responsavel por essa parte?`

### When the clinic asks what it is about

`E sobre uma IA para clinicas que responde pacientes no WhatsApp, mostra horarios disponiveis e ajuda no agendamento automatico. Faz sentido eu te mandar uma demo rapida?`

### When the clinic says it can send

`Perfeito. Vou te mandar uma demo rapida para voce testar como se fosse um paciente falando com a clinica pelo WhatsApp.`

### When a new responsible contact is shared

`Oi, [Nome]. A [clinica] me indicou voce como responsavel por atendimento/agendamentos. Aqui e o time comercial da ClinicFlux AI. Podemos marcar 10 minutos para eu te mostrar como reduzir atraso no WhatsApp e melhorar conversao em consulta?`

### When selling website is the right moment

`Vi que a clinica ainda nao aparece com um site forte no Google. Isso pode fazer pacientes escolherem concorrentes antes mesmo de chamar no WhatsApp. Posso te mostrar uma proposta simples de site local com WhatsApp, mapa, servicos, prova de confianca e base de SEO?`

### When selling SaaS is the right moment

`Como voces ja recebem pacientes pelo WhatsApp, o maior ganho aqui parece ser velocidade e controle: responder mais rapido, organizar agenda e nao deixar retorno se perder. Posso te mostrar uma demo rapida da ClinicFlux AI aplicada nesse fluxo?`

## 90/100 quality bar

A message is elite only when it passes all checks:

- It is clearly commercial.
- It uses the clinic's real context from Google Places.
- It answers the latest clinic message directly.
- It sells one next step, not the whole product catalog.
- It sounds like a person who researched the clinic.
- It avoids pressure, hype, and repetition.
- It creates a natural next action: responsible person, quick audit, demo, or permission to send summary.

## Red flags

- duplicated outbound turns
- repeated opener after a real reply
- answering a patient-style autoresponder with another patient-style message
- sending a third cold message without a human reply
- treating an automatic reply as real interest
- sending a demo link to a cold lead without a human reply
- repeating the same opener
- pretending to be a patient to pass clinic automation
- sending a long pitch after an automatic reply
- following up outside the 24-hour API window without an approved template
- ignoring a stop-contact request
- sending pitch before answering `como nos achou?`
- selling website when the website already looks solid and the pain is WhatsApp conversion
- selling SaaS before acknowledging that the clinic has no site or weak local presence
- long explanatory blocks before establishing role and relevance
- calling the clinic from a localhost/demo link in the first useful reply

## Outreach Intelligence System

Use the playbook as the commercial brain, not only as a message library. Every lead should move through this operating loop:

`lead -> lead scoring -> pre-send evaluation -> approved/rewrite -> conversation -> post-conversation review JSONL -> weekly report -> improvement suggestion with human approval`

The maturity target "300%" means internal rigor, instrumentation, and learning discipline. It is not a promise of guaranteed commercial results.

## Pre-send Message Sense Check

Before suggesting, presenting, or sending any commercial message, evaluate the candidate message against these checks:

- Does it answer the clinic's latest reply directly?
- Is the commercial identity clear?
- Does it use the clinic's real context?
- Was the correct offer chosen: website/SEO, ClinicFlux AI, demo, audit, or responsible person?
- Does it have only one objective?
- Does it avoid sounding like a patient?
- Does it avoid repetition?
- Does it avoid pressure, hype, or exaggerated promise?
- Does it have a clear next action?
- Does it have risk of burning the lead?

Scoring rule:

- Score each message from 0 to 100.
- If `message_quality_score < 85`, rewrite it before presenting it.
- If `burn_risk` is `high` or `critical`, do not send; rewrite or wait.
- If the clinic asked a direct question, the next message must answer that question first.

Required output fields for a pre-send evaluation:

- `message_quality_score`
- `commercial_clarity_score`
- `context_match_score`
- `one_objective_score`
- `repetition_score`
- `whatsapp_naturalness_score`
- `risk_score`
- `burn_risk`
- `approved_to_send`
- `rewrite_suggestion`

## Message Evaluation Engine

Use `outreach-intelligence/scripts/outreach_intelligence.py` as the offline reference implementation for:

- message quality scoring
- commercial clarity scoring
- context match scoring
- one-objective scoring
- repetition scoring
- WhatsApp naturalness scoring
- risk scoring
- burn risk classification
- corrected message generation

The engine is intentionally local and stdlib-only. Do not add external APIs or secret-dependent services for this evaluation.

## AI Evaluation Committee

Evaluate important messages from five perspectives:

- `sales_judge`: Is the sales next step clear and commercially useful?
- `local_seo_judge`: Does the message use Google/local/website context honestly?
- `whatsapp_judge`: Does it sound natural, short, and human on WhatsApp?
- `persuasion_judge`: Does it create interest without pressure?
- `risk_judge`: Does it avoid false promises, repetition, and lead burn?

Each judge must return:

- `score`
- `reason`

## Digital Twin Simulation

Before sending a message, simulate how these lead personas may react:

- busy receptionist
- skeptical owner
- busy dentist
- cold lead
- interested lead

The simulation should produce:

- likely reaction
- main risk
- suggestion to improve the message

Use the simulation to catch messages that are technically correct but commercially awkward.

## Lead Scoring Engine

Score every lead before choosing the offer lane. The scoring must consider:

- clinic without website
- weak website
- good website
- Google review count
- Google rating
- category
- WhatsApp presence
- volume signals
- premium clinic signals
- popular clinic signals
- digital maturity

Required lead scoring output:

- `lead_score`
- `revenue_potential`
- `digital_maturity_score`
- `whatsapp_dependency`
- `likely_pain`
- `recommended_offer`

Offer routing rules:

- No website: default to `website_seo`.
- Weak website: default to `audit`.
- Good or strong website with active WhatsApp demand: default to `clinicflux_ai`.
- Hot lead or responsible person identified: prefer `demo`.
- Refusal or opt-out: use `stop_contact`.

## Next Best Action Engine

Classify the next action after every meaningful signal:

- `send_message`
- `ask_for_responsible`
- `send_demo`
- `send_video`
- `send_summary`
- `book_meeting`
- `wait`
- `follow_up`
- `stop_contact`
- `reply_contextually`
- `send_second_commercial_clarification`
- `use_approved_template_only`
- `stop_contact_or_use_approved_template_only`
- `switch_to_website_offer`
- `switch_to_clinicflux_ai_offer`
- `send_proposal`

Decision inputs:

- latest clinic reply
- detected intent
- objection
- lead stage
- lead temperature
- burn risk
- clinic history
- website status
- previous outbound count
- cold outreach message count
- auto reply received
- human reply received
- 24-hour API window status
- template requirement and usage

Hard rules:

- If the clinic refuses contact, choose `stop_contact`.
- If burn risk is high, choose `wait` or rewrite.
- If the lead is cold, only an automatic reply was received, and `cold_outreach_message_count = 1`, choose `send_second_commercial_clarification`.
- If the lead is cold, `cold_outreach_message_count >= 2`, and `human_reply_received = false`, choose `stop_contact` and set `do_not_follow_up = true`.
- If `outside_24h_window = true`, `human_reply_received = false`, `template_required = true`, and `template_used = false`, choose `stop_contact_or_use_approved_template_only`.
- If the clinic asks how we found them, answer source before any pitch.
- If the clinic asks price before seeing value, send a short summary or demo route before a proposal.
- If the clinic has no website, do not lead with SaaS before acknowledging the website/SEO opportunity.
- If the clinic has a strong website, do not keep pushing website rebuild; switch to ClinicFlux AI.

## Anti-repetition System

Before any follow-up, check the clinic history:

- Do not repeat the same opening.
- Do not ask a question already answered.
- Do not send a message too similar to the previous outbound message.
- Do not ignore a known objection.
- Do not restart the conversation after a real reply.

Simple heuristic:

- Normalize text.
- Compare token overlap against recent outbound messages.
- If similarity is high, rewrite with a different objective or wait.

## Post-conversation Review

After each conversation or meaningful checkpoint, append one JSON object per line to:

`outreach-reviews/conversation-reviews.jsonl`

Each review must include:

- `lead_id`
- `clinic_name`
- `source`
- `has_website`
- `website_quality`
- `google_rating`
- `review_count`
- `category`
- `city`
- `neighborhood`
- `offer_lane`
- `lead_temperature`
- `cold_outreach_message_count`
- `message_variant`
- `message_sent`
- `clinic_replied`
- `reply_time_minutes`
- `auto_reply_received`
- `human_reply_received`
- `first_human_message_received`
- `first_human_message_at`
- `last_human_reply_at`
- `reply_type`
- `detected_persona`
- `detected_intent`
- `outside_24h_window`
- `template_required`
- `template_used`
- `stop_contact_required`
- `do_not_follow_up`
- `opt_in_status`
- `do_not_contact`
- `max_remaining_cold_messages`
- `analysis_mode`
- `token_efficiency_mode`
- `token_budget_level`
- `should_use_elite_mode`
- `elite_mode_reason`
- `estimated_token_cost_level`
- `data_loading_strategy`
- `large_context_allowed`
- `objection_type`
- `stage_reached`
- `demo_clicked`
- `whatsapp_tested`
- `meeting_booked`
- `proposal_sent`
- `closed_sale`
- `lost_reason`
- `conversation_score`
- `message_quality_score`
- `commercial_risk_score`
- `burn_risk`
- `what_worked`
- `what_failed`
- `missed_opportunities`
- `next_best_action`
- `next_best_message`
- `improvement_notes`
- `tags`
- `created_at`

Privacy rule:

- Do not store full phone numbers, secrets, passwords, API keys, or private clinic data unless strictly necessary and approved.
- Examples must always be fictional.
- For cold outreach, record automatic replies separately from human replies so JSONL review does not treat automation as opt-in or real interest.

## Microconversions

Track microconversions so the weekly report can find where the funnel leaks:

- `message_sent`
- `clinic_replied`
- `asked_source`
- `asked_price`
- `asked_info`
- `responsible_identified`
- `demo_sent`
- `demo_clicked`
- `whatsapp_tested`
- `booking_attempted`
- `meeting_booked`
- `proposal_sent`
- `closed_sale`
- `lost`

## Outreach Intelligence Files

Use these files as the structured memory layer:

- `outreach-reviews/conversation-reviews.jsonl`: one post-conversation review per line.
- `outreach-intelligence/commercial-brain.json`: accumulated commercial intelligence.
- `outreach-intelligence/objection-library.jsonl`: objection variants and performance.
- `outreach-intelligence/lead-profiles/{lead_id}.json`: historical profile by clinic lead.
- `outreach-intelligence/skill-update-suggestions.jsonl`: suggested skill improvements requiring human approval.
- `outreach-reports/weekly-summary-YYYY-MM-DD.json`: weekly performance summary.

## Schemas

Use the JSON Schemas in `outreach-intelligence/schemas/`:

- `conversation-review.schema.json`
- `lead-profile.schema.json`
- `message-evaluation.schema.json`
- `objection.schema.json`
- `campaign-summary.schema.json`
- `skill-update-suggestion.schema.json`

Compatibility rule:

- Add fields only when needed and update schema, examples, tests, and docs together.
- Do not remove or rename fields without checking producers, consumers, reports, and tests.

## Commercial Brain

The file `outreach-intelligence/commercial-brain.json` stores accumulated intelligence:

- `best_opening_by_lead_type`
- `best_offer_by_website_status`
- `best_followup_by_objection`
- `winning_patterns`
- `losing_patterns`
- `worst_messages`
- `pricing_resistance_patterns`
- `best_campaigns`
- `recommended_strategy_next_week`
- `last_updated_at`

Update this file only from reviewed patterns, not from a single emotional anecdote.

## Objection Library

The file `outreach-intelligence/objection-library.jsonl` stores one objection response record per line:

- `objection_type`
- `raw_objection`
- `response_variant`
- `times_used`
- `reply_rate`
- `demo_conversion_rate`
- `meeting_conversion_rate`
- `close_rate`
- `status`
- `notes`

Retire responses that create confusion, pressure, or repeated no-replies.

## Historical Lead Profiles

Store per-lead history under:

`outreach-intelligence/lead-profiles/{lead_id}.json`

Each profile should track:

- `lead_id`
- `clinic_name`
- `source`
- `first_contact_date`
- `last_contact_date`
- `current_stage`
- `lead_temperature`
- `responsible_person`
- `detected_personas`
- `known_objections`
- `preferred_angle`
- `do_not_repeat`
- `next_best_action`
- `notes`

Use stable internal ids. Avoid phone numbers in filenames.

## Weekly Report

Generate weekly summaries as:

`outreach-reports/weekly-summary-YYYY-MM-DD.json`

The report must include:

- `total_leads_contacted`
- `reply_rate`
- `demo_click_rate`
- `whatsapp_test_rate`
- `meeting_rate`
- `close_rate`
- `best_opening`
- `worst_opening`
- `best_lead_type`
- `worst_lead_type`
- `top_objections`
- `lost_reasons`
- `recommended_next_strategy`
- `stop_doing`
- `continue_doing`
- `test_next`

Use:

`python outreach-intelligence/scripts/generate_weekly_summary.py --input outreach-reviews/conversation-reviews.jsonl --output-dir outreach-reports`

## Dashboard

The simple internal view lives at:

`/adm/inteligencia-comercial`

It should help inspect:

- hot leads
- leads that replied
- leads that opened demo
- leads that tested WhatsApp
- leads that asked price
- stalled leads
- best messages
- worst messages
- recommended next actions

The initial dashboard must not expose private data through an unauthenticated API. If a future backend endpoint is added, it must use the existing admin auth model.

## Skill Update Suggestions

Use:

`outreach-intelligence/skill-update-suggestions.jsonl`

Each line must include:

- `skill`
- `change_type`
- `suggested_rule`
- `reason`
- `based_on_count`
- `confidence`
- `expected_impact`
- `requires_human_approval`

Mandatory rule:

- Never update this skill automatically from suggestions.
- Always require human approval before changing the playbook.

## Anti-hallucination Commercial Rules

Block or rewrite any message that:

- promises guaranteed results
- invents patient volume
- invents clinic revenue
- promises "agenda cheia" as certainty
- claims an integration that does not exist in the project
- says the clinic will lose a specific number of patients without evidence
- uses fear, urgency, or pressure as the main reason to reply

Use language of possibility, estimate, opportunity, or hypothesis:

- Better: `isso pode estar reduzindo contatos pelo WhatsApp`
- Better: `parece uma oportunidade de melhorar resposta e agendamento`
- Better: `posso te mostrar uma demo para validar se faz sentido`

## Continuous Improvement Rules

- Review conversations weekly before changing message strategy.
- Prefer patterns supported by multiple reviews.
- Separate no-site, weak-site, and strong-site leads.
- Do not compare campaigns with different lead sources as if they were equal.
- Mark examples as fictional unless they are approved anonymized records.
- Keep the playbook central, but keep operational data in `outreach-intelligence/`, `outreach-reviews/`, and `outreach-reports/`.

## Automated Testing

The outreach intelligence layer must keep tests for:

- valid JSONL lines
- valid JSON schemas
- sample conversation review
- message evaluation
- lead scoring
- next best action
- automatic replies do not count as human replies
- cold leads without human replies receive at most 2 outbound messages
- third cold messages without human replies are blocked
- free-form API messages outside 24h without human reply are blocked unless an approved template is used
- `stop_contact` is recommended after the second cold message without human reply
- objection library
- commercial brain
- skill update suggestions
- no exposed secrets in the outreach files
- valid skill frontmatter with `name` and `description`

## References

Read [official-seo-principles.md](official-seo-principles.md) when you need the official SEO rationale behind these rules.
Read [elite-sales-research.md](elite-sales-research.md) when you need the SaaS and website-builder sales patterns behind the playbook.

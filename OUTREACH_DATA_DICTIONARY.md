# Outreach Data Dictionary

## Conversation Review

- `lead_id`: Stable internal lead identifier. Do not use phone numbers.
- `clinic_name`: Clinic display name.
- `source`: Lead source such as `google_places`, `google_maps`, `local_serp`, `manual`, `referral`, or `unknown`.
- `has_website`: Whether a website is known.
- `website_quality`: `none`, `weak`, `average`, `good`, `strong`, or `unknown`.
- `google_rating`: Google rating from 0 to 5, or null.
- `review_count`: Google review count.
- `category`: Business category.
- `city`: City.
- `neighborhood`: Neighborhood.
- `offer_lane`: `website_seo`, `clinicflux_ai`, `demo`, `audit`, `responsible`, `hybrid`, or `stop`.
- `lead_temperature`: `cold`, `warm`, `hot`, `very_hot`, `lost`, or `unknown`.
- `message_variant`: Message/campaign variant id.
- `message_sent`: Exact outbound message sent.
- `clinic_replied`: Whether the clinic replied.
- `reply_time_minutes`: Minutes until reply, or null.
- `reply_type`: Reply classification.
- `detected_persona`: `reception`, `owner`, `dentist`, `manager`, `automated`, or `unknown`.
- `detected_intent`: Detected intent such as `ask_price`, `request_demo`, or `refuse`.
- `objection_type`: Main objection type.
- `stage_reached`: Funnel stage reached.
- `demo_clicked`: Whether the demo was clicked.
- `whatsapp_tested`: Whether WhatsApp was tested.
- `meeting_booked`: Whether a meeting was booked.
- `proposal_sent`: Whether a proposal was sent.
- `closed_sale`: Whether the sale closed.
- `lost_reason`: Reason lost, or null.
- `conversation_score`: Overall conversation score from 0 to 100.
- `message_quality_score`: Pre-send or post-send message score from 0 to 100.
- `commercial_risk_score`: Risk score from 0 to 100.
- `burn_risk`: `low`, `medium`, `high`, or `critical`.
- `what_worked`: Array of positive observations.
- `what_failed`: Array of problems.
- `missed_opportunities`: Array of missed chances.
- `next_best_action`: Recommended next action.
- `next_best_message`: Suggested next message.
- `improvement_notes`: Notes for improvement.
- `tags`: Searchable tags.
- `created_at`: ISO date-time.

## Microconversions

- `message_sent`: First commercial message sent.
- `clinic_replied`: Clinic sent any reply.
- `asked_source`: Clinic asked how it was found.
- `asked_price`: Clinic asked price.
- `asked_info`: Clinic asked for more details.
- `responsible_identified`: Responsible person identified.
- `demo_sent`: Demo link sent.
- `demo_clicked`: Demo opened.
- `whatsapp_tested`: WhatsApp test completed.
- `booking_attempted`: Booking attempted.
- `meeting_booked`: Meeting booked.
- `proposal_sent`: Proposal sent.
- `closed_sale`: Sale closed.
- `lost`: Opportunity lost.

## Message Evaluation Scores

- `message_quality_score`: Weighted final score.
- `commercial_clarity_score`: Identity, commercial role, and brand clarity.
- `context_match_score`: Match to latest reply and clinic context.
- `one_objective_score`: Whether the message has one clear objective.
- `repetition_score`: Whether it avoids repeated content.
- `whatsapp_naturalness_score`: Length, tone, and readability for WhatsApp.
- `risk_score`: Higher means more commercial risk.
- `burn_risk`: Qualitative risk level.
- `approved_to_send`: Whether it can be sent as-is.
- `rewrite_suggestion`: What to change if not approved.

## Lead Scoring

- `lead_score`: Overall sales priority from 0 to 100.
- `revenue_potential`: `low`, `medium`, `high`, or `very_high`.
- `digital_maturity_score`: Digital maturity from 0 to 100.
- `whatsapp_dependency`: Estimated WhatsApp dependency from 0 to 100.
- `likely_pain`: Best hypothesis for the lead's pain.
- `recommended_offer`: `website_seo`, `audit`, `clinicflux_ai`, `demo`, or `stop_contact`.

## Skill Update Suggestion

- `skill`: Skill name.
- `change_type`: Suggested change type.
- `suggested_rule`: Proposed rule or example.
- `reason`: Why it is suggested.
- `based_on_count`: Number of observations behind it.
- `confidence`: Confidence from 0 to 1.
- `expected_impact`: Expected impact if approved.
- `requires_human_approval`: Must be true.

## Sensitive Data Rules

- Avoid phone numbers in filenames.
- Avoid complete phone numbers in examples.
- Never store API keys, tokens, passwords, or refresh tokens.
- Do not store private clinic conversations unless approved and necessary.
- Use fictional examples for tests and documentation.

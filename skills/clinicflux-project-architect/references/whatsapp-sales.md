# WhatsApp And Sales Outreach

Use this for WhatsApp Web bridge, clinic sales outreach, Google Places leads, SEO/local site positioning, and AI-generated clinic conversations.

## Non-Negotiable Guardrails

- Sync the real visible WhatsApp conversation before send/review decisions when bridge state matters.
- Do not send repeated messages if the clinic has not replied.
- Treat "numero sem WhatsApp" as a per-item `dead_letter`, not a fatal bridge error.
- Respect auto-replies, out-of-hours replies, "vamos retornar", "nao estamos disponiveis", and "sem interesse".
- If a clinic shares another responsible contact, save/use that contact before continuing the pitch.
- Never let one bad lead stop the whole bridge loop.
- Avoid sending when the composer or active chat is not the intended contact.
- Repair persona mistakes: ClinicFlux is a commercial SaaS/site provider, not a patient trying to book treatment.

## Conversation Logic

- Answer pending clinic questions before selling.
- Do not send demo/link too early.
- Keep messages short, natural, and specific to the clinic.
- Use the last real inbound message as context, not only database assumptions.
- If the candidate reply ignores the clinic question, hold/rewrite it.
- If the clinic said it will return or is unavailable, wait for a new message.

## Google Places And SEO Lane

Use `local-seo-outreach-playbook` when available.

- If sourced from Google Places and no website is present: lead with local site/SEO trust and Google visibility.
- If sourced from Google Places and website exists: lead with ClinicFlux AI as conversion/WhatsApp/agendamento layer.
- Do not pitch site and SaaS as one overloaded first message.
- Use Google Places data carefully: name, category, rating, reviews, city/neighborhood, website presence, phone.
- Avoid pretending certainty beyond the captured data.

## Model Scope

- If the user requests a stronger model for clinic conversation, scope it only to sales outreach LLM calls when possible.
- Do not globally switch all system AI unless explicitly requested.
- Verify official OpenAI model IDs when using latest/current model names.

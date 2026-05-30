# Lead Profiles

Store one JSON file per clinic lead here when a historical profile is needed:

`outreach-intelligence/lead-profiles/{lead_id}.json`

Use `outreach-intelligence/schemas/lead-profile.schema.json` as the contract.

Privacy rules:

- Prefer stable internal lead ids over phone numbers.
- Do not store full phone numbers unless strictly necessary for an approved operational flow.
- Do not store API keys, tokens, passwords, or private clinic data in examples.
- Keep fictional samples in `outreach-intelligence/examples/`, not in this folder.

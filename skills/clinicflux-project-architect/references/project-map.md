# Project Map

Use this only when the task touches unfamiliar parts of ClinicFlux AI / OdontoFlux or crosses multiple surfaces.

## Repo

- Main working root: `C:\Users\Gui Trader\Documents\GitHub\OdontoFlux\odontoflux`
- Backend: `apps/api`
- Frontend/admin: `apps/web`
- WhatsApp Selenium bridge: `apps/msg/whatsapp_web.py`
- Skills copied into repo: `skills/`
- Local Codex skills installed under: `C:\Users\Gui Trader\.codex\skills`

## Architecture Habits

- Inspect current code before proposing structure.
- Reuse service boundaries and env settings before adding new global behavior.
- Check Docker/runtime when behavior is user-visible.
- For branding/localhost issues, suspect env/cache/container state before assuming edits failed.
- For `/adm`, verify permission/page mappings instead of guessing route names.

## High-Risk Surfaces

- Sales outreach and WhatsApp bridge: can send wrong messages to real clinics.
- `/adm`: user validates visually; page overflow, permissions, and selected conversation behavior matter.
- AI messaging: must never fail silently.
- Google Places import/search: can spend API quota and create duplicate prospects.
- Docker/localhost: stale containers or cache can hide correct code.

## Efficient Exploration Pattern

1. `rg` for exact function/env/route names.
2. Open only likely files and nearby tests.
3. Check existing tests and logs.
4. Patch smallest safe path.
5. Run focused validation.
6. Expand only if the evidence demands it.

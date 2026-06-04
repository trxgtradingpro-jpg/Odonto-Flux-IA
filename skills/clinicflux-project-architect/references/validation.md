# Validation

Use this when changing runtime behavior, `/adm`, Docker, WhatsApp, AI messaging, or anything the user will verify on localhost.

## Backend

- Syntax: `python -m py_compile <changed_python_files>`
- Container syntax when imports depend on app env: `docker compose exec api sh -lc "python -m py_compile <files>"`
- Focused tests beat full-suite guessing when time is tight.
- If tests need DB inside Docker, use the container DB host, not host `localhost`.

## Frontend

- Build: `pnpm --filter @odontoflux/web build`
- Browser-visible changes should be checked on `http://localhost:3000`.
- If localhost looks stale, check env, cache, and container restart before assuming the patch failed.

## Docker Runtime

- Rebuild when service code/env changed: `docker compose up -d --build <services>`
- Health: `curl.exe -s http://localhost:8000/health`
- Status: `docker compose ps`
- Wait/retry briefly after recreating containers before diagnosing as code failure.

## WhatsApp Bridge

- Compile bridge: `python -m py_compile apps/msg/whatsapp_web.py`
- Validate that bad numbers become `dead_letter` and loop continues.
- Validate that inbound/replied conversations are prioritized over older outbound pendings.
- Validate live transcript review before send when applicable.
- For startup failures, prefer retry/recover logic over manual restart rituals.

## Reporting

In the final answer, separate:

- validated
- not validated
- blocked or timed out
- exact command to run next, if needed

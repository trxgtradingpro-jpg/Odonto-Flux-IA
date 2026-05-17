from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import WhatsAppAccount
from app.services.whatsapp_service import ingest_webhook_payload

router = APIRouter(prefix='/webhooks/whatsapp', tags=['webhooks_whatsapp'])


def _allowed_verify_tokens(db: Session) -> set[str]:
    tokens: set[str] = set()
    configured_token = str(settings.whatsapp_verify_token or '').strip()
    if configured_token:
        tokens.add(configured_token)

    account_tokens = db.execute(
        select(WhatsAppAccount.verify_token).where(
            WhatsAppAccount.provider_name == 'meta_cloud',
            WhatsAppAccount.is_active.is_(True),
        )
    ).scalars().all()
    for value in account_tokens:
        token = str(value or '').strip()
        if token:
            tokens.add(token)
    return tokens


@router.get('')
def verify_webhook(
    hub_mode: str | None = Query(default=None, alias='hub.mode'),
    hub_verify_token: str | None = Query(default=None, alias='hub.verify_token'),
    hub_challenge: str | None = Query(default=None, alias='hub.challenge'),
    db: Session = Depends(get_db),
):
    allowed_tokens = _allowed_verify_tokens(db)
    if hub_mode == 'subscribe' and hub_verify_token in allowed_tokens and hub_challenge:
        return PlainTextResponse(content=hub_challenge)
    raise HTTPException(status_code=403, detail='Falha na verificacao do webhook')


@router.post('')
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    payload: dict = {}
    content_type = (request.headers.get('content-type') or '').lower()

    if 'application/json' in content_type:
        raw_json = await request.json()
        if isinstance(raw_json, dict):
            payload = raw_json
    elif 'application/x-www-form-urlencoded' in content_type or 'multipart/form-data' in content_type:
        form_data = await request.form()
        payload = {key: value for key, value in form_data.multi_items()}

    if not payload and request.headers.get('content-length'):
        try:
            raw_json = await request.json()
        except Exception:
            raw_json = {}
        if isinstance(raw_json, dict):
            payload = raw_json

    result = ingest_webhook_payload(db, payload)
    return {'status': 'ok', 'result': result}

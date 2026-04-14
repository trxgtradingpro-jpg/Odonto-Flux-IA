from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.whatsapp_service import ingest_webhook_payload

router = APIRouter(prefix='/webhooks/whatsapp', tags=['webhooks_whatsapp'])


@router.get('')
def verify_webhook(
    hub_mode: str | None = Query(default=None, alias='hub.mode'),
    hub_verify_token: str | None = Query(default=None, alias='hub.verify_token'),
    hub_challenge: str | None = Query(default=None, alias='hub.challenge'),
):
    if hub_mode == 'subscribe' and hub_verify_token == settings.whatsapp_verify_token and hub_challenge:
        return int(hub_challenge) if hub_challenge.isdigit() else hub_challenge
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

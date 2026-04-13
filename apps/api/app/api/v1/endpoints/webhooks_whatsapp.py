from fastapi import APIRouter, Depends, HTTPException, Query
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
def receive_webhook(payload: dict, db: Session = Depends(get_db)):
    result = ingest_webhook_payload(db, payload)
    return {'status': 'ok', 'result': result}

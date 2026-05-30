from __future__ import annotations

from datetime import datetime
from secrets import compare_digest
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.services.whatsapp_web_bridge_service import (
    acknowledge_bridge_outbox,
    claim_bridge_outbox_messages,
    ingest_bridge_inbound_message,
    review_bridge_outbox_live_conversation,
    sync_bridge_conversation_messages,
)

router = APIRouter(prefix="/internal/whatsapp-web", tags=["internal_whatsapp_web"])


def _require_bridge_token(authorization: str = Header(default="")) -> None:
    configured = str(settings.whatsapp_web_bridge_token or "").strip()
    if not configured:
        raise ApiError(status_code=503, code="BRIDGE_NOT_CONFIGURED", message="Bridge do WhatsApp Web nao configurado.")
    if not authorization.lower().startswith("bearer "):
        raise ApiError(status_code=401, code="BRIDGE_TOKEN_REQUIRED", message="Token do bridge ausente.")
    token = authorization.split(" ", 1)[1].strip()
    if not compare_digest(token, configured):
        raise ApiError(status_code=403, code="BRIDGE_TOKEN_INVALID", message="Token do bridge invalido.")


class WhatsAppWebBridgePullOutput(BaseModel):
    items: list[dict]


class WhatsAppWebBridgeAckInput(BaseModel):
    status: Literal["sent", "failed", "dead_letter"] = "sent"
    error: str | None = None
    retryable: bool = True
    provider_message_id: str | None = None
    external_chat_id: str | None = None
    external_message_id: str | None = None
    sent_at: datetime | None = None


class WhatsAppWebBridgeInboundInput(BaseModel):
    body: str = Field(min_length=1)
    conversation_id: UUID | None = None
    phone_number: str | None = None
    contact_name: str | None = None
    shared_contact_name: str | None = None
    shared_contact_phone: str | None = None
    external_message_id: str | None = None
    external_chat_id: str | None = None
    visible_time: str | None = None
    received_at: datetime | None = None


class WhatsAppWebBridgeLiveMessageInput(BaseModel):
    direction: str
    body: str = Field(min_length=1)
    visible_time: str | None = None
    timestamp: str | None = None
    external_message_id: str | None = None


class WhatsAppWebBridgeConversationSyncInput(BaseModel):
    conversation_id: UUID | None = None
    phone_number: str | None = None
    contact_name: str | None = None
    captured_at: datetime | None = None
    messages: list[WhatsAppWebBridgeLiveMessageInput] = Field(default_factory=list)


class WhatsAppWebBridgeLiveReviewInput(BaseModel):
    body: str = Field(min_length=1)
    captured_at: datetime | None = None
    messages: list[WhatsAppWebBridgeLiveMessageInput] = Field(default_factory=list)


@router.get("/outbox/pull", response_model=WhatsAppWebBridgePullOutput, dependencies=[Depends(_require_bridge_token)])
def pull_bridge_outbox(
    limit: int = Query(default=5, ge=1, le=20),
    worker_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return {"items": claim_bridge_outbox_messages(db, limit=limit, worker_id=worker_id)}


@router.post("/outbox/{outbox_id}/ack", dependencies=[Depends(_require_bridge_token)])
def ack_bridge_outbox(
    outbox_id: UUID,
    payload: WhatsAppWebBridgeAckInput,
    db: Session = Depends(get_db),
):
    return acknowledge_bridge_outbox(
        db,
        outbox_id=outbox_id,
        success=payload.status == "sent",
        retryable=payload.retryable and payload.status != "dead_letter",
        error=payload.error,
        provider_message_id=payload.provider_message_id,
        external_chat_id=payload.external_chat_id,
        external_message_id=payload.external_message_id,
        sent_at=payload.sent_at,
    )


@router.post("/outbox/{outbox_id}/live-review", dependencies=[Depends(_require_bridge_token)])
def review_bridge_outbox_live(
    outbox_id: UUID,
    payload: WhatsAppWebBridgeLiveReviewInput,
    db: Session = Depends(get_db),
):
    return review_bridge_outbox_live_conversation(
        db,
        outbox_id=outbox_id,
        candidate_body=payload.body,
        live_messages=[item.model_dump() for item in payload.messages],
        captured_at=payload.captured_at,
    )


@router.post("/conversation/sync", dependencies=[Depends(_require_bridge_token)])
def sync_bridge_conversation(
    payload: WhatsAppWebBridgeConversationSyncInput,
    db: Session = Depends(get_db),
):
    return sync_bridge_conversation_messages(
        db,
        conversation_id=payload.conversation_id,
        phone_number=payload.phone_number,
        contact_name=payload.contact_name,
        captured_at=payload.captured_at,
        messages=[item.model_dump() for item in payload.messages],
    )


@router.post("/inbound", dependencies=[Depends(_require_bridge_token)])
def create_bridge_inbound(
    payload: WhatsAppWebBridgeInboundInput,
    db: Session = Depends(get_db),
):
    return ingest_bridge_inbound_message(
        db,
        body=payload.body,
        conversation_id=payload.conversation_id,
        phone_number=payload.phone_number,
        contact_name=payload.contact_name,
        shared_contact_name=payload.shared_contact_name,
        shared_contact_phone=payload.shared_contact_phone,
        external_message_id=payload.external_message_id,
        external_chat_id=payload.external_chat_id,
        visible_time=payload.visible_time,
        received_at=payload.received_at,
    )

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.models import Conversation, LinkFlowSession, Message
from app.models.enums import MessageStatus
from app.services.link_flow_service import register_link_flow_event_once
from app.services.whatsapp_service import (
    assert_whatsapp_route_ready_for_dispatch,
    queue_outbound_message,
    resolve_whatsapp_reply_route,
)


@dataclass
class PatientDispatchResult:
    channel: str
    outbox_id: UUID | None = None
    destination: str | None = None
    provider_context: dict[str, Any] | None = None


def _linked_link_flow_session(db: Session, *, conversation: Conversation) -> LinkFlowSession | None:
    return db.scalar(
        select(LinkFlowSession)
        .where(
            LinkFlowSession.tenant_id == conversation.tenant_id,
            LinkFlowSession.linked_conversation_id == conversation.id,
        )
        .order_by(LinkFlowSession.created_at.desc())
        .limit(1)
    )


def _mark_webchat_delivered(
    db: Session,
    *,
    conversation: Conversation,
    outbound_message: Message,
) -> PatientDispatchResult:
    now = datetime.now(UTC)
    outbound_message.channel = "webchat"
    outbound_message.status = MessageStatus.SENT.value
    outbound_message.sent_at = now
    payload = outbound_message.payload if isinstance(outbound_message.payload, dict) else {}
    payload["delivery_channel"] = "webchat"
    payload["webchat_delivered"] = True
    outbound_message.payload = payload
    db.add(outbound_message)

    session = _linked_link_flow_session(db, conversation=conversation)
    if session:
        session.last_assistant_message_at = now
        db.add(session)
        if outbound_message.sender_type == "ai":
            register_link_flow_event_once(
                db,
                session=session,
                event_name="webchat_first_ai_response",
                payload={"source": "channel_dispatch", "conversation_id": str(conversation.id)},
                unique_payload_key="conversation_id",
                unique_payload_value=str(conversation.id),
            )

    return PatientDispatchResult(channel="webchat")


def dispatch_patient_message(
    db: Session,
    *,
    tenant_id: UUID,
    conversation: Conversation,
    outbound_message: Message,
    body: str,
    message_type: str = "text",
    interactive: dict[str, Any] | None = None,
    inbound_message: Message | None = None,
    provider_context: dict[str, Any] | None = None,
    destination: str | None = None,
    metadata: dict[str, Any] | None = None,
    commit: bool = False,
) -> PatientDispatchResult:
    channel = str(conversation.channel or "whatsapp").strip().lower()

    if channel == "webchat":
        return _mark_webchat_delivered(
            db,
            conversation=conversation,
            outbound_message=outbound_message,
        )

    if channel != "whatsapp":
        raise ApiError(
            status_code=400,
            code="UNSUPPORTED_CONVERSATION_CHANNEL",
            message="Canal da conversa nao suportado para envio ao paciente.",
        )

    resolved_destination = destination
    resolved_provider_context = provider_context
    if not resolved_destination:
        resolved_destination, resolved_provider_context = resolve_whatsapp_reply_route(
            db,
            conversation=conversation,
            inbound_message=inbound_message,
        )

    if not resolved_destination:
        raise ApiError(
            status_code=400,
            code="PATIENT_PHONE_REQUIRED",
            message="Conversa sem telefone de contato (paciente ou lead).",
        )

    assert_whatsapp_route_ready_for_dispatch(
        db,
        tenant_id=tenant_id,
        provider_context=resolved_provider_context,
    )
    outbox = queue_outbound_message(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        to=resolved_destination,
        body=body,
        message_type=message_type,
        interactive=interactive,
        provider_context=resolved_provider_context,
        metadata=metadata or {},
        commit=commit,
    )

    payload = outbound_message.payload if isinstance(outbound_message.payload, dict) else {}
    payload["queued_outbox_id"] = str(outbox.id)
    payload["delivery_channel"] = "whatsapp"
    outbound_message.payload = payload
    db.add(outbound_message)
    return PatientDispatchResult(
        channel="whatsapp",
        outbox_id=outbox.id,
        destination=resolved_destination,
        provider_context=resolved_provider_context,
    )

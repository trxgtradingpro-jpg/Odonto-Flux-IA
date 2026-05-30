from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha1
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ApiError
from app.models import Conversation, Message, MessageEvent, OutboxMessage, Patient
from app.models.enums import MessageDirection, MessageStatus, OutboxStatus
from app.services import sales_demo_service
from app.services.whatsapp_bridge_support import (
    WHATSAPP_WEB_BRIDGE_TRANSPORT,
    payload_metadata,
    payload_uses_whatsapp_web_bridge,
)
from app.utils.phone import normalize_phone


def _now() -> datetime:
    return datetime.now(UTC)


def _bridge_provider_context() -> dict[str, str]:
    return {
        "provider_name": "whatsapp_web",
        "transport": WHATSAPP_WEB_BRIDGE_TRANSPORT,
    }


def _is_missing_whatsapp_number_error(error: str | None) -> bool:
    normalized = sales_demo_service._normalized_lookup_text(str(error or ""))
    if not normalized:
        return False
    phrases = (
        "nao esta no whatsapp",
        "numero nao esta no whatsapp",
        "nao tem uma conta no whatsapp",
        "isn't on whatsapp",
        "is not on whatsapp",
        "phone number shared via url is invalid",
        "numero de telefone compartilhado por url e invalido",
    )
    return any(phrase in normalized for phrase in phrases)


def _bridge_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _bridge_outbox_priority_key(item: OutboxMessage) -> tuple[int, datetime, datetime, str]:
    payload = item.payload if isinstance(item.payload, dict) else {}
    metadata = payload_metadata(payload)
    priority_reason = str(metadata.get("priority_reason") or "").strip().lower()
    priority_order_raw = str(metadata.get("priority_order_at") or "").strip()

    priority_at = _bridge_utc_datetime(item.created_at) or _now()
    if priority_order_raw:
        try:
            parsed = datetime.fromisoformat(priority_order_raw.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        priority_at = _bridge_utc_datetime(parsed) or priority_at

    created_at = _bridge_utc_datetime(item.created_at) or priority_at
    priority_rank = 0 if priority_reason == "inbound_reply" else 1
    return (priority_rank, priority_at, created_at, str(item.id))


def _bridge_normalize_live_direction(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"in", "inbound", "received", "clinic", "clinica", "lead", "patient"}:
        return MessageDirection.INBOUND.value
    if normalized in {"out", "outbound", "sent", "me", "clinicflux", "clinicflux ai"}:
        return MessageDirection.OUTBOUND.value
    return None


def _bridge_visible_datetime(visible_time: object, captured_at: datetime) -> datetime:
    text = str(visible_time or "").strip()
    match = None
    for pattern in (r"\b(\d{1,2}):(\d{2})\b",):
        import re

        match = re.search(pattern, text)
        if match:
            break
    if not match:
        return captured_at

    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return captured_at

    value = captured_at.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if value > captured_at + timedelta(minutes=5):
        value -= timedelta(days=1)
    return value


def _bridge_sync_provider_message_id(
    *,
    conversation_id: UUID,
    direction: str,
    visible_time: str,
    body: str,
    raw_external_id: str | None = None,
) -> str:
    raw_value = str(raw_external_id or "").strip()
    if raw_value:
        return _safe_bridge_provider_message_id(raw_value) or raw_value[:120]
    digest = sha1(f"{conversation_id}:{direction}:{visible_time}:{body}".encode("utf-8")).hexdigest()
    return f"whatsapp_web_sync:{digest[:32]}"


def _safe_bridge_provider_message_id(raw_value: str | None) -> str | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    if len(value) <= 120:
        return value
    digest = sha1(value.encode("utf-8")).hexdigest()[:12]
    return f"{value[:107]}:{digest}"


def _serialize_bridge_outbox_item(item: OutboxMessage) -> dict:
    payload = item.payload if isinstance(item.payload, dict) else {}
    metadata = payload_metadata(payload)
    return {
        "id": str(item.id),
        "conversation_id": str(payload.get("conversation_id") or ""),
        "phone_number": str(payload.get("to") or ""),
        "body": str(payload.get("body") or ""),
        "message_type": str(payload.get("message_type") or "text"),
        "prospect_account_id": str(metadata.get("prospect_account_id") or ""),
        "outbound_message_id": str(metadata.get("outbound_message_id") or ""),
        "step": str(metadata.get("step") or ""),
        "transport": str(metadata.get("transport") or ""),
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "claim_expires_at": item.next_retry_at.isoformat() if item.next_retry_at else None,
    }


def _bridge_outbound_message_for_payload(db: Session, item: OutboxMessage, payload: dict) -> Message | None:
    metadata = payload_metadata(payload)
    outbound_message_id = str(metadata.get("outbound_message_id") or "").strip()
    if not outbound_message_id:
        return None
    try:
        return db.scalar(
            select(Message).where(
                Message.id == UUID(outbound_message_id),
                Message.tenant_id == item.tenant_id,
            )
        )
    except (TypeError, ValueError):
        return None


def _apply_bridge_send_gate_decision(
    db: Session,
    *,
    item: OutboxMessage,
    payload: dict,
    gate: dict,
    now: datetime,
) -> bool:
    payload = dict(payload or {})
    metadata = dict(payload_metadata(payload))
    decision = str(gate.get("decision") or "send").strip().lower()
    metadata["send_gate"] = {
        **gate,
        "reviewed_at": now.isoformat(),
    }
    payload["metadata"] = metadata

    outbound_message = _bridge_outbound_message_for_payload(db, item, payload)
    if decision == "send":
        final_message = str(gate.get("final_message") or "").strip()
        if final_message and final_message != str(payload.get("body") or ""):
            payload["body"] = final_message
            if outbound_message:
                existing_payload = outbound_message.payload if isinstance(outbound_message.payload, dict) else {}
                outbound_message.body = final_message
                outbound_message.payload = {
                    **existing_payload,
                    "send_gate": metadata["send_gate"],
                }
                db.add(outbound_message)
        item.payload = payload
        db.add(item)
        return True

    if decision == "block":
        reason = str(gate.get("reason") or "Envio bloqueado pela revisao comercial.").strip()
        item.status = OutboxStatus.DEAD_LETTER.value
        item.next_retry_at = None
        item.last_error = reason[:1000]
        item.payload = payload
        if outbound_message:
            existing_payload = outbound_message.payload if isinstance(outbound_message.payload, dict) else {}
            outbound_message.status = MessageStatus.FAILED.value
            outbound_message.payload = {
                **existing_payload,
                "send_gate": metadata["send_gate"],
                "dispatch_error": reason[:300],
            }
            db.add(outbound_message)
        db.add(item)
        return False

    reason = str(gate.get("reason") or "Aguardando melhor momento para envio.").strip()
    try:
        wait_minutes = max(1, int(gate.get("wait_minutes") or 120))
    except (TypeError, ValueError):
        wait_minutes = 120
    item.status = OutboxStatus.PENDING.value
    item.next_retry_at = now + timedelta(minutes=wait_minutes)
    item.last_error = reason[:1000]
    item.payload = payload
    if outbound_message:
        existing_payload = outbound_message.payload if isinstance(outbound_message.payload, dict) else {}
        outbound_message.payload = {
            **existing_payload,
            "send_gate": metadata["send_gate"],
        }
        db.add(outbound_message)
    db.add(item)
    return False


def claim_bridge_outbox_messages(db: Session, *, limit: int = 5, worker_id: str | None = None) -> list[dict]:
    now = _now()
    claim_until = now + timedelta(seconds=max(30, int(settings.whatsapp_web_bridge_claim_seconds or 120)))
    candidates = db.execute(
        select(OutboxMessage)
        .where(
            OutboxMessage.status.in_(
                [
                    OutboxStatus.PENDING.value,
                    OutboxStatus.FAILED.value,
                    OutboxStatus.PROCESSING.value,
                ]
            )
        )
    ).scalars().all()
    candidates.sort(key=_bridge_outbox_priority_key)

    claimed: list[OutboxMessage] = []
    claimed_conversation_ids: set[str] = set()
    for item in candidates:
        if len(claimed) >= limit:
            break
        payload = item.payload if isinstance(item.payload, dict) else {}
        if not payload_uses_whatsapp_web_bridge(payload):
            continue
        if item.status == OutboxStatus.PROCESSING.value and item.next_retry_at and item.next_retry_at > now:
            continue
        if item.status in {OutboxStatus.PENDING.value, OutboxStatus.FAILED.value}:
            if item.next_retry_at and item.next_retry_at > now:
                continue

        conversation_id = str(payload.get("conversation_id") or "").strip()
        if conversation_id and conversation_id in claimed_conversation_ids:
            gate = {
                "decision": "wait",
                "confidence": 1.0,
                "reason": "Ja existe uma mensagem desta conversa liberada neste ciclo; aguardando envio antes de liberar outra.",
                "wait_minutes": 5,
            }
            _apply_bridge_send_gate_decision(db, item=item, payload=payload, gate=gate, now=now)
            continue

        gate = sales_demo_service.review_sales_outreach_outbox_send_gate(db, outbox=item, now=now)
        if not _apply_bridge_send_gate_decision(db, item=item, payload=payload, gate=gate, now=now):
            continue

        payload = item.payload if isinstance(item.payload, dict) else {}
        metadata = payload_metadata(payload)
        metadata["bridge_claimed_at"] = now.isoformat()
        metadata["bridge_worker_id"] = worker_id or "default"
        payload["metadata"] = metadata
        item.payload = payload
        item.status = OutboxStatus.PROCESSING.value
        item.next_retry_at = claim_until
        db.add(item)
        claimed.append(item)
        if conversation_id:
            claimed_conversation_ids.add(conversation_id)

    db.commit()
    return [_serialize_bridge_outbox_item(item) for item in claimed]


def review_bridge_outbox_live_conversation(
    db: Session,
    *,
    outbox_id: UUID,
    candidate_body: str | None,
    live_messages: list[dict] | None,
    captured_at: datetime | None = None,
) -> dict:
    item = db.get(OutboxMessage, outbox_id)
    if not item:
        raise ApiError(status_code=404, code="BRIDGE_OUTBOX_NOT_FOUND", message="Outbox do bridge nao encontrado.")

    payload = item.payload if isinstance(item.payload, dict) else {}
    if not payload_uses_whatsapp_web_bridge(payload):
        raise ApiError(status_code=409, code="BRIDGE_OUTBOX_TRANSPORT_INVALID", message="Esse outbox nao pertence ao transporte WhatsApp Web.")

    conversation_id = payload.get("conversation_id")
    try:
        conversation_uuid = UUID(str(conversation_id))
    except (TypeError, ValueError):
        gate = {
            "decision": "block",
            "confidence": 1.0,
            "reason": "Envio bloqueado: conversa ausente para revisao live do WhatsApp Web.",
        }
        _apply_bridge_send_gate_decision(db, item=item, payload=payload, gate=gate, now=_now())
        db.commit()
        return {"outbox_id": str(item.id), "decision": "block", "gate": gate, "body": str(payload.get("body") or "")}

    conversation = db.get(Conversation, conversation_uuid)
    if not conversation:
        gate = {
            "decision": "block",
            "confidence": 1.0,
            "reason": "Envio bloqueado: conversa nao encontrada para revisao live do WhatsApp Web.",
        }
        _apply_bridge_send_gate_decision(db, item=item, payload=payload, gate=gate, now=_now())
        db.commit()
        return {"outbox_id": str(item.id), "decision": "block", "gate": gate, "body": str(payload.get("body") or "")}

    candidate = str(candidate_body or payload.get("body") or "").strip()
    metadata = payload_metadata(payload)
    gate = sales_demo_service.review_sales_outreach_live_whatsapp_send_gate(
        db,
        conversation=conversation,
        candidate_message=candidate,
        live_messages=live_messages or [],
        captured_at=captured_at,
        candidate_step=str(metadata.get("step") or ""),
    )
    now = captured_at or _now()
    _apply_bridge_send_gate_decision(db, item=item, payload=payload, gate=gate, now=now)
    db.commit()
    db.refresh(item)
    updated_payload = item.payload if isinstance(item.payload, dict) else {}
    return {
        "outbox_id": str(item.id),
        "decision": str(gate.get("decision") or "send"),
        "gate": gate,
        "body": str(updated_payload.get("body") or candidate),
        "status": item.status,
        "next_retry_at": item.next_retry_at.isoformat() if item.next_retry_at else None,
    }


def acknowledge_bridge_outbox(
    db: Session,
    *,
    outbox_id: UUID,
    success: bool,
    retryable: bool,
    error: str | None = None,
    provider_message_id: str | None = None,
    external_chat_id: str | None = None,
    external_message_id: str | None = None,
    sent_at: datetime | None = None,
) -> dict:
    item = db.get(OutboxMessage, outbox_id)
    if not item:
        raise ApiError(status_code=404, code="BRIDGE_OUTBOX_NOT_FOUND", message="Outbox do bridge nao encontrado.")

    payload = item.payload if isinstance(item.payload, dict) else {}
    if not payload_uses_whatsapp_web_bridge(payload):
        raise ApiError(status_code=409, code="BRIDGE_OUTBOX_TRANSPORT_INVALID", message="Esse outbox nao pertence ao transporte WhatsApp Web.")

    metadata = payload_metadata(payload)
    outbound_message = None
    outbound_message_id = str(metadata.get("outbound_message_id") or "").strip()
    if outbound_message_id:
        try:
            outbound_message = db.scalar(
                select(Message).where(
                    Message.id == UUID(outbound_message_id),
                    Message.tenant_id == item.tenant_id,
                )
            )
        except (TypeError, ValueError):
            outbound_message = None

    effective_sent_at = sent_at or _now()
    if success:
        item.status = OutboxStatus.SENT.value
        item.last_error = None
        item.next_retry_at = None
        metadata["bridge_sent_at"] = effective_sent_at.isoformat()
        if external_chat_id:
            metadata["bridge_external_chat_id"] = external_chat_id
        if external_message_id:
            metadata["bridge_external_message_id"] = external_message_id
        payload["metadata"] = metadata
        item.payload = payload
        db.add(item)

        if outbound_message:
            existing_payload = outbound_message.payload if isinstance(outbound_message.payload, dict) else {}
            outbound_message.provider_message_id = _safe_bridge_provider_message_id(provider_message_id or external_message_id)
            outbound_message.status = MessageStatus.SENT.value
            outbound_message.sent_at = effective_sent_at
            outbound_message.payload = {
                **existing_payload,
                "provider_context": _bridge_provider_context(),
                "bridge_delivery": {
                    "sent_at": effective_sent_at.isoformat(),
                    "external_chat_id": external_chat_id,
                    "external_message_id": external_message_id,
                },
            }
            db.add(outbound_message)
            db.add(
                MessageEvent(
                    tenant_id=item.tenant_id,
                    message_id=outbound_message.id,
                    event_type="whatsapp_web_bridge_sent",
                    payload={
                        "outbox_id": str(item.id),
                        "external_chat_id": external_chat_id,
                        "external_message_id": external_message_id,
                    },
                )
            )

        db.commit()
        return {
            "status": item.status,
            "outbox_id": str(item.id),
            "outbound_message_id": str(outbound_message.id) if outbound_message else None,
        }

    failure_message = str(error or "Falha ao enviar mensagem pelo WhatsApp Web.").strip()
    item.last_error = failure_message[:1000]
    item.retry_count += 1
    if _is_missing_whatsapp_number_error(failure_message):
        metadata["bridge_failure_classification"] = "missing_whatsapp_number"
        prospect_account_id = str(metadata.get("prospect_account_id") or "").strip()
        if prospect_account_id:
            try:
                from app.services.sales_outreach_automation_service import remove_prospect_from_batches_for_missing_whatsapp

                remove_prospect_from_batches_for_missing_whatsapp(
                    db,
                    prospect_id=UUID(prospect_account_id),
                    reason=failure_message,
                    outbox_id=item.id,
                )
            except Exception:
                pass
    if outbound_message:
        existing_payload = outbound_message.payload if isinstance(outbound_message.payload, dict) else {}
        outbound_message.status = MessageStatus.FAILED.value
        outbound_message.payload = {
            **existing_payload,
            "dispatch_error": failure_message[:300],
            "provider_context": _bridge_provider_context(),
        }
        db.add(outbound_message)

    metadata["bridge_last_error_at"] = _now().isoformat()
    payload["metadata"] = metadata
    item.payload = payload

    if (not retryable) or item.retry_count >= item.max_retries:
        item.status = OutboxStatus.DEAD_LETTER.value
        item.next_retry_at = None
    else:
        item.status = OutboxStatus.FAILED.value
        item.next_retry_at = _now() + timedelta(minutes=(2**item.retry_count))

    db.add(item)
    db.commit()
    return {
        "status": item.status,
        "outbox_id": str(item.id),
        "retry_count": item.retry_count,
        "next_retry_at": item.next_retry_at.isoformat() if item.next_retry_at else None,
    }


def _resolve_bridge_conversation(
    db: Session,
    *,
    conversation_id: UUID | None = None,
    phone_number: str | None = None,
) -> Conversation:
    conversation = None
    if conversation_id:
        conversation = db.get(Conversation, conversation_id)
        if not conversation:
            raise ApiError(status_code=404, code="BRIDGE_CONVERSATION_NOT_FOUND", message="Conversa nao encontrada.")
    elif phone_number:
        normalized = normalize_phone(phone_number)
        if not normalized:
            raise ApiError(status_code=400, code="BRIDGE_PHONE_INVALID", message="Numero invalido para localizar a conversa.")
        sender_tenant = sales_demo_service.ensure_sales_outreach_sender_tenant(db)
        candidates = db.execute(
            select(Conversation)
            .where(
                Conversation.tenant_id == sender_tenant.id,
                Conversation.channel == "whatsapp",
                Conversation.status.in_(["aberta", "aguardando"]),
            )
            .order_by(Conversation.last_message_at.desc())
        ).scalars().all()
        for item in candidates:
            if "prospect_outreach" not in set(item.tags or []):
                continue
            patient = db.get(Patient, item.patient_id) if item.patient_id else None
            if patient and normalize_phone(patient.phone) == normalized:
                conversation = item
                break
        if not conversation:
            raise ApiError(status_code=404, code="BRIDGE_CONVERSATION_NOT_FOUND", message="Nenhuma conversa comercial encontrada para esse telefone.")
    else:
        raise ApiError(status_code=400, code="BRIDGE_CONVERSATION_REQUIRED", message="Informe conversation_id ou phone_number.")

    if "prospect_outreach" not in set(conversation.tags or []):
        raise ApiError(status_code=409, code="BRIDGE_CONVERSATION_INVALID", message="A conversa informada nao pertence ao outreach comercial.")
    return conversation


def ingest_bridge_inbound_message(
    db: Session,
    *,
    body: str,
    conversation_id: UUID | None = None,
    phone_number: str | None = None,
    contact_name: str | None = None,
    shared_contact_name: str | None = None,
    shared_contact_phone: str | None = None,
    external_message_id: str | None = None,
    external_chat_id: str | None = None,
    visible_time: str | None = None,
    received_at: datetime | None = None,
) -> dict:
    inbound_body = str(body or "").strip()
    if not inbound_body:
        raise ApiError(status_code=400, code="BRIDGE_BODY_REQUIRED", message="Mensagem recebida vazia.")

    conversation = _resolve_bridge_conversation(db, conversation_id=conversation_id, phone_number=phone_number)
    if external_message_id:
        existing = db.scalar(
            select(Message).where(
                Message.tenant_id == conversation.tenant_id,
                Message.provider_message_id == external_message_id,
            )
        )
        if existing:
            return {
                "status": "duplicate",
                "conversation_id": str(conversation.id),
                "message_id": str(existing.id),
            }

    message_payload = {
        "source": "whatsapp_web_bridge",
        "provider_context": _bridge_provider_context(),
        "bridge_contact_name": contact_name,
        "bridge_shared_contact_name": str(shared_contact_name or "").strip() or None,
        "bridge_shared_contact_phone": str(shared_contact_phone or "").strip() or None,
        "bridge_external_chat_id": external_chat_id,
        "bridge_visible_time": visible_time,
        "received_via": WHATSAPP_WEB_BRIDGE_TRANSPORT,
    }
    inbound_message = Message(
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND.value,
        channel="whatsapp",
        provider_message_id=_safe_bridge_provider_message_id(external_message_id),
        sender_type="patient",
        body=inbound_body,
        message_type="text",
        payload=message_payload,
        status=MessageStatus.RECEIVED.value,
    )
    db.add(inbound_message)

    conversation.last_message_at = received_at or _now()
    db.add(conversation)

    sales_demo_service.sync_prospect_outreach_reply(
        db,
        conversation=conversation,
        message=inbound_message,
    )
    db.add(
        MessageEvent(
            tenant_id=conversation.tenant_id,
            message_id=inbound_message.id,
            event_type="whatsapp_web_bridge_received",
            payload=message_payload,
        )
    )
    db.commit()
    return {
        "status": "received",
        "conversation_id": str(conversation.id),
        "message_id": str(inbound_message.id),
    }


def sync_bridge_conversation_messages(
    db: Session,
    *,
    conversation_id: UUID | None = None,
    phone_number: str | None = None,
    contact_name: str | None = None,
    messages: list[dict] | None = None,
    captured_at: datetime | None = None,
) -> dict:
    conversation = _resolve_bridge_conversation(db, conversation_id=conversation_id, phone_number=phone_number)
    effective_captured_at = _bridge_utc_datetime(captured_at) or _now()
    inserted = 0
    skipped = 0
    latest_message_at = _bridge_utc_datetime(conversation.last_message_at)
    synced_message_ids: list[str] = []

    for raw_item in messages or []:
        if not isinstance(raw_item, dict):
            skipped += 1
            continue

        direction = _bridge_normalize_live_direction(raw_item.get("direction"))
        body = str(raw_item.get("body") or raw_item.get("message") or raw_item.get("text") or "").strip()
        if not direction or not body:
            skipped += 1
            continue

        visible_time = str(raw_item.get("visible_time") or "").strip()
        message_at = _bridge_visible_datetime(visible_time, effective_captured_at)
        provider_message_id = _bridge_sync_provider_message_id(
            conversation_id=conversation.id,
            direction=direction,
            visible_time=visible_time,
            body=body,
            raw_external_id=raw_item.get("external_message_id"),
        )

        existing = db.scalar(
            select(Message).where(
                Message.tenant_id == conversation.tenant_id,
                Message.provider_message_id == provider_message_id,
            )
        )
        if existing:
            skipped += 1
            synced_message_ids.append(str(existing.id))
            existing_created_at = _bridge_utc_datetime(existing.created_at)
            if existing_created_at and (latest_message_at is None or existing_created_at > latest_message_at):
                latest_message_at = existing_created_at
            continue

        message_payload = {
            "source": "whatsapp_web_bridge_live_sync",
            "provider_context": _bridge_provider_context(),
            "bridge_contact_name": contact_name,
            "bridge_shared_contact_name": str(raw_item.get("shared_contact_name") or "").strip() or None,
            "bridge_shared_contact_phone": str(raw_item.get("shared_contact_phone") or "").strip() or None,
            "bridge_visible_time": visible_time,
            "captured_at": effective_captured_at.isoformat(),
        }
        message = Message(
            tenant_id=conversation.tenant_id,
            conversation_id=conversation.id,
            direction=direction,
            channel="whatsapp",
            provider_message_id=provider_message_id,
            sender_type="patient" if direction == MessageDirection.INBOUND.value else "system",
            body=body,
            message_type="text",
            payload=message_payload,
            status=MessageStatus.RECEIVED.value if direction == MessageDirection.INBOUND.value else MessageStatus.SENT.value,
            sent_at=message_at if direction == MessageDirection.OUTBOUND.value else None,
            created_at=message_at,
        )
        db.add(message)
        db.flush()
        if direction == MessageDirection.INBOUND.value and (
            message_payload.get("bridge_shared_contact_name") or message_payload.get("bridge_shared_contact_phone")
        ):
            sales_demo_service.sync_prospect_outreach_reply(
                db,
                conversation=conversation,
                message=message,
            )
        db.add(
            MessageEvent(
                tenant_id=conversation.tenant_id,
                message_id=message.id,
                event_type="whatsapp_web_bridge_synced",
                payload=message_payload,
            )
        )
        inserted += 1
        synced_message_ids.append(str(message.id))
        normalized_message_at = _bridge_utc_datetime(message_at)
        if normalized_message_at and (latest_message_at is None or normalized_message_at > latest_message_at):
            latest_message_at = normalized_message_at

    if latest_message_at:
        conversation.last_message_at = latest_message_at
    db.add(conversation)
    db.commit()
    return {
        "status": "synced",
        "conversation_id": str(conversation.id),
        "inserted": inserted,
        "skipped": skipped,
        "total_received": len(messages or []),
        "message_ids": synced_message_ids,
    }

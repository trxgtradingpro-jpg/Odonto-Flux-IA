from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.models import Conversation, LinkFlowSession, Message, Patient, Tenant
from app.models.enums import MessageDirection, MessageStatus
from app.services.link_flow_service import (
    LINK_FLOW_ACTIVE_STATUSES,
    LINK_FLOW_INACTIVE_STATUSES,
    get_intake_config,
    is_link_flow_enabled,
    register_link_flow_event,
    register_link_flow_event_once,
)
from app.utils.hash import sha256_text

WEBCHAT_MAX_MESSAGE_LENGTH = 1200
WEBCHAT_RATE_LIMIT_WINDOW_SECONDS = 60
WEBCHAT_RATE_LIMIT_MAX_MESSAGES = 8


@dataclass
class WebchatSessionBundle:
    session: LinkFlowSession
    public_access_token: str


def _now() -> datetime:
    return datetime.now(UTC)


def _hash_token(raw_token: str) -> str:
    return sha256_text(raw_token.strip())


def _positive_int(value: Any, fallback: int, *, minimum: int = 5, maximum: int = 240) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(minimum, min(parsed, maximum))


def _token_matches(session: LinkFlowSession, raw_token: str | None) -> bool:
    token = str(raw_token or "").strip()
    return bool(token and session.public_access_token_hash and _hash_token(token) == session.public_access_token_hash)


def _commit_public_validation_event(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()


def create_webchat_link_flow_session(
    db: Session,
    *,
    tenant: Tenant,
    config: dict,
    landing_path: str,
    browser_session_id: str | None = None,
    utm_payload: dict | None = None,
    unit_id: UUID | None = None,
) -> WebchatSessionBundle:
    if not is_link_flow_enabled(config):
        raise ApiError(
            status_code=404,
            code="LINK_FLOW_NOT_ENABLED",
            message="Agendamento por link indisponivel para esta clinica.",
        )

    link_flow = config.get("link_flow") if isinstance(config.get("link_flow"), dict) else {}
    if str(link_flow.get("cta_mode") or "whatsapp_redirect") != "webchat":
        raise ApiError(
            status_code=409,
            code="WEBCHAT_NOT_CONFIGURED",
            message="Chat publico indisponivel para esta clinica.",
        )

    public_access_token = secrets.token_urlsafe(32)
    internal_token = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(minutes=_positive_int(link_flow.get("session_ttl_minutes"), 30))
    session = LinkFlowSession(
        tenant_id=tenant.id,
        unit_id=unit_id,
        mode="link_flow",
        cta_mode="webchat",
        channel="webchat",
        token_hash=_hash_token(internal_token),
        public_access_token_hash=_hash_token(public_access_token),
        status="pending",
        landing_path=landing_path[:255],
        browser_session_id=(str(browser_session_id or "").strip()[:120] or None),
        utm_payload=utm_payload if isinstance(utm_payload, dict) else {},
        expires_at=expires_at,
    )
    db.add(session)
    db.flush()
    return WebchatSessionBundle(session=session, public_access_token=public_access_token)


def validate_public_webchat_session(
    db: Session,
    *,
    session_id: UUID,
    public_access_token: str | None,
    clinic_slug: str | None = None,
) -> tuple[LinkFlowSession, Tenant]:
    session = db.get(LinkFlowSession, session_id)
    if not session:
        raise ApiError(
            status_code=404,
            code="WEBCHAT_SESSION_NOT_FOUND",
            message="Sessao do atendimento nao encontrada.",
        )

    if not _token_matches(session, public_access_token):
        register_link_flow_event_once(
            db,
            session=session,
            event_name="webchat_error",
            payload={"source": "public_webchat", "reason": "invalid_public_token"},
            unique_payload_key="reason",
            unique_payload_value="invalid_public_token",
        )
        db.add(session)
        _commit_public_validation_event(db)
        raise ApiError(
            status_code=403,
            code="WEBCHAT_SESSION_FORBIDDEN",
            message="Sessao do atendimento invalida.",
        )

    tenant = db.get(Tenant, session.tenant_id)
    if not tenant or not tenant.is_active:
        session.status = "inactive"
        session.failure_reason = "tenant_inactive"
        db.add(session)
        register_link_flow_event_once(
            db,
            session=session,
            event_name="session_invalid",
            payload={"source": "public_webchat", "reason": "tenant_inactive"},
        )
        _commit_public_validation_event(db)
        raise ApiError(
            status_code=409,
            code="WEBCHAT_SESSION_INVALID",
            message="Atendimento indisponivel. Abra novamente o link oficial da clinica para continuar.",
        )

    if clinic_slug and tenant.slug != clinic_slug:
        raise ApiError(
            status_code=404,
            code="WEBCHAT_SESSION_NOT_FOUND",
            message="Sessao do atendimento nao encontrada.",
        )

    if str(session.cta_mode or "") != "webchat" or str(session.channel or "") != "webchat":
        register_link_flow_event_once(
            db,
            session=session,
            event_name="session_invalid",
            payload={"source": "public_webchat", "reason": "wrong_channel"},
        )
        _commit_public_validation_event(db)
        raise ApiError(
            status_code=409,
            code="WEBCHAT_SESSION_INVALID",
            message="Atendimento indisponivel. Abra novamente o link oficial da clinica para continuar.",
        )

    current_status = str(session.status or "").strip().lower()
    if current_status in LINK_FLOW_INACTIVE_STATUSES or session.closed_at:
        register_link_flow_event_once(
            db,
            session=session,
            event_name="session_invalid",
            payload={"source": "public_webchat", "reason": current_status or "closed"},
        )
        _commit_public_validation_event(db)
        raise ApiError(
            status_code=409,
            code="WEBCHAT_SESSION_CLOSED",
            message="Esta sessao de atendimento foi encerrada. Abra novamente o link oficial da clinica para continuar.",
        )

    if session.expires_at <= _now():
        session.status = "expired"
        session.failure_reason = "expired"
        db.add(session)
        register_link_flow_event_once(
            db,
            session=session,
            event_name="session_expired",
            payload={"source": "public_webchat"},
        )
        _commit_public_validation_event(db)
        raise ApiError(
            status_code=409,
            code="WEBCHAT_SESSION_EXPIRED",
            message="Sua sessao expirou. Abra novamente o link oficial da clinica para continuar.",
        )

    if current_status and current_status not in LINK_FLOW_ACTIVE_STATUSES:
        register_link_flow_event_once(
            db,
            session=session,
            event_name="session_invalid",
            payload={"source": "public_webchat", "reason": current_status},
        )
        _commit_public_validation_event(db)
        raise ApiError(
            status_code=409,
            code="WEBCHAT_SESSION_INVALID",
            message="Atendimento indisponivel. Abra novamente o link oficial da clinica para continuar.",
        )

    config = get_intake_config(db, tenant_id=tenant.id)
    link_flow = config.get("link_flow") if isinstance(config.get("link_flow"), dict) else {}
    if not is_link_flow_enabled(config) or str(link_flow.get("cta_mode") or "whatsapp_redirect") != "webchat":
        register_link_flow_event_once(
            db,
            session=session,
            event_name="webchat_error",
            payload={"source": "public_webchat", "reason": "webchat_disabled"},
            unique_payload_key="reason",
            unique_payload_value="webchat_disabled",
        )
        _commit_public_validation_event(db)
        raise ApiError(
            status_code=409,
            code="WEBCHAT_NOT_AVAILABLE",
            message="Chat publico indisponivel no momento. Entre em contato com a clinica pelo canal oficial.",
        )

    return session, tenant


def _ensure_webchat_patient(db: Session, *, session: LinkFlowSession, tenant: Tenant) -> Patient:
    if session.linked_patient_id:
        patient = db.get(Patient, session.linked_patient_id)
        if patient and patient.tenant_id == tenant.id:
            return patient

    synthetic_contact = f"webchat{session.id.hex[:18]}"
    patient = db.scalar(
        select(Patient).where(
            Patient.tenant_id == tenant.id,
            Patient.normalized_phone == synthetic_contact,
        )
    )
    if not patient:
        patient = Patient(
            tenant_id=tenant.id,
            unit_id=session.unit_id,
            full_name="Paciente Webchat",
            phone=synthetic_contact,
            normalized_phone=synthetic_contact,
            origin="link_flow_webchat",
            lgpd_consent=True,
            marketing_opt_in=False,
            tags_cache=["entry_link_flow", "entry_webchat"],
        )
        db.add(patient)
        db.flush()
    session.linked_patient_id = patient.id
    db.add(session)
    return patient


def ensure_webchat_conversation(
    db: Session,
    *,
    session: LinkFlowSession,
    tenant: Tenant,
) -> Conversation:
    if session.linked_conversation_id:
        conversation = db.get(Conversation, session.linked_conversation_id)
        if conversation and conversation.tenant_id == tenant.id and conversation.channel == "webchat":
            return conversation

    patient = _ensure_webchat_patient(db, session=session, tenant=tenant)
    conversation = Conversation(
        tenant_id=tenant.id,
        unit_id=session.unit_id,
        patient_id=patient.id,
        channel="webchat",
        external_thread_id=f"link_flow:{session.id}",
        status="aberta",
        ai_autoresponder_enabled=True,
        tags=["entry_link_flow", "entry_webchat"],
        last_message_at=_now(),
    )
    db.add(conversation)
    db.flush()

    session.linked_conversation_id = conversation.id
    session.linked_patient_id = patient.id
    session.linked_at = session.linked_at or _now()
    session.status = "linked"
    db.add(session)
    register_link_flow_event_once(
        db,
        session=session,
        event_name="conversation_started",
        payload={"source": "webchat"},
    )
    register_link_flow_event_once(
        db,
        session=session,
        event_name="webchat_started",
        payload={"source": "public_webchat"},
    )
    return conversation


def _existing_client_message(
    db: Session,
    *,
    conversation: Conversation,
    client_message_id: str | None,
) -> Message | None:
    if not client_message_id:
        return None
    rows = db.execute(
        select(Message)
        .where(
            Message.tenant_id == conversation.tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == MessageDirection.INBOUND.value,
            Message.channel == "webchat",
        )
        .order_by(Message.created_at.desc())
        .limit(50)
    ).scalars().all()
    for row in rows:
        payload = row.payload if isinstance(row.payload, dict) else {}
        if str(payload.get("client_message_id") or "") == client_message_id:
            return row
    return None


def _assert_rate_limit(db: Session, *, conversation: Conversation, ip_address: str | None = None) -> None:
    window_start = _now() - timedelta(seconds=WEBCHAT_RATE_LIMIT_WINDOW_SECONDS)
    recent_messages = db.execute(
        select(Message)
        .where(
            Message.tenant_id == conversation.tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == MessageDirection.INBOUND.value,
            Message.channel == "webchat",
            Message.created_at >= window_start,
        )
    ).scalars().all()
    same_ip_count = 0
    if ip_address:
        for message in recent_messages:
            payload = message.payload if isinstance(message.payload, dict) else {}
            if str(payload.get("ip_address") or "") == ip_address:
                same_ip_count += 1
    if len(recent_messages) >= WEBCHAT_RATE_LIMIT_MAX_MESSAGES or same_ip_count >= WEBCHAT_RATE_LIMIT_MAX_MESSAGES:
        raise ApiError(
            status_code=429,
            code="WEBCHAT_RATE_LIMITED",
            message="Muitas mensagens em pouco tempo. Aguarde alguns instantes para continuar.",
        )


def serialize_public_webchat_message(message: Message) -> dict[str, Any]:
    role = "patient" if message.direction == MessageDirection.INBOUND.value else "assistant"
    return {
        "id": str(message.id),
        "role": role,
        "text": message.body or "",
        "created_at": message.created_at.isoformat() if message.created_at else None,
        "status": message.status,
    }


def list_public_webchat_messages(
    db: Session,
    *,
    session: LinkFlowSession,
    after_message_id: UUID | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if not session.linked_conversation_id:
        return []

    stmt = select(Message).where(
        Message.tenant_id == session.tenant_id,
        Message.conversation_id == session.linked_conversation_id,
        Message.channel == "webchat",
        Message.message_type.in_(["text", "interactive_list", "interactive_buttons"]),
    )
    if after_message_id:
        after_message = db.get(Message, after_message_id)
        if after_message and after_message.tenant_id == session.tenant_id and after_message.conversation_id == session.linked_conversation_id:
            stmt = stmt.where(Message.created_at > after_message.created_at)

    messages = db.execute(stmt.order_by(Message.created_at.asc()).limit(max(1, min(limit, 100)))).scalars().all()
    return [serialize_public_webchat_message(message) for message in messages]


def post_public_webchat_message(
    db: Session,
    *,
    session: LinkFlowSession,
    tenant: Tenant,
    text: str,
    client_message_id: str | None = None,
    ip_address: str | None = None,
) -> dict[str, Any]:
    body = " ".join(str(text or "").strip().split())
    if not body:
        raise ApiError(status_code=422, code="WEBCHAT_MESSAGE_EMPTY", message="Digite uma mensagem para continuar.")
    if len(body) > WEBCHAT_MAX_MESSAGE_LENGTH:
        raise ApiError(
            status_code=422,
            code="WEBCHAT_MESSAGE_TOO_LONG",
            message="Mensagem muito longa. Envie um texto mais curto para continuar.",
        )

    conversation = ensure_webchat_conversation(db, session=session, tenant=tenant)
    _assert_rate_limit(db, conversation=conversation, ip_address=ip_address)

    normalized_client_id = str(client_message_id or "").strip()[:120] or None
    existing = _existing_client_message(db, conversation=conversation, client_message_id=normalized_client_id)
    if existing:
        return {
            "status": "duplicate",
            "message": serialize_public_webchat_message(existing),
            "ai": None,
        }

    now = _now()
    inbound = Message(
        tenant_id=tenant.id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND.value,
        channel="webchat",
        sender_type="patient",
        body=body,
        message_type="text",
        payload={
            "source": "public_webchat",
            "client_message_id": normalized_client_id,
            "link_flow_session_id": str(session.id),
            "ip_address": (str(ip_address or "").strip()[:100] or None),
        },
        status=MessageStatus.RECEIVED.value,
    )
    db.add(inbound)
    db.flush()

    conversation.last_message_at = now
    session.last_patient_message_at = now
    db.add(conversation)
    db.add(session)
    register_link_flow_event(
        db,
        session=session,
        event_name="webchat_message_sent",
        payload={"source": "public_webchat", "message_id": str(inbound.id)},
    )
    db.commit()
    db.refresh(inbound)
    db.refresh(conversation)

    ai_result: dict[str, Any] | None = None
    try:
        from app.services.ai_autoresponder_service import process_inbound_message

        ai_result = process_inbound_message(
            db,
            tenant_id=tenant.id,
            conversation_id=conversation.id,
            inbound_message_id=inbound.id,
        )
    except Exception as exc:
        db.rollback()
        refreshed_session = db.get(LinkFlowSession, session.id)
        if refreshed_session:
            register_link_flow_event(
                db,
                session=refreshed_session,
                event_name="webchat_error",
                payload={"source": "public_webchat", "reason": "ai_processing_error"},
            )
            db.commit()
        raise ApiError(
            status_code=502,
            code="WEBCHAT_PROCESSING_FAILED",
            message="Nao consegui processar sua mensagem agora. Tente novamente em instantes.",
        ) from exc

    return {
        "status": "accepted",
        "message": serialize_public_webchat_message(inbound),
        "ai": ai_result,
    }


def public_webchat_session_state(session: LinkFlowSession) -> dict[str, Any]:
    return {
        "session_id": str(session.id),
        "status": session.status,
        "cta_mode": session.cta_mode,
        "channel": "webchat",
        "expires_at": session.expires_at.isoformat(),
        "closed_at": session.closed_at.isoformat() if session.closed_at else None,
        "has_conversation": bool(session.linked_conversation_id),
        "completed": bool(session.linked_appointment_id or session.completed_at),
    }

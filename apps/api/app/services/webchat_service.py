from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.models import Appointment, Conversation, LinkFlowEvent, LinkFlowSession, Message, Patient, Tenant, Unit
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
WEBCHAT_FALLBACK_REPLY = "Nao entendi completamente sua mensagem. Pode me explicar melhor?"


@dataclass
class WebchatSessionBundle:
    session: LinkFlowSession
    public_access_token: str


def _now() -> datetime:
    return datetime.now(UTC)


def _placeholder_patient_name(value: str | None) -> bool:
    normalized = str(value or "").strip().casefold()
    return not normalized or normalized in {"paciente webchat", "paciente", "novo paciente", "paciente do agendamento"}


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


def _latest_webchat_assistant_reply_for_inbound(
    db: Session,
    *,
    conversation: Conversation,
    inbound_message_id: UUID,
) -> Message | None:
    rows = db.execute(
        select(Message)
        .where(
            Message.tenant_id == conversation.tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == MessageDirection.OUTBOUND.value,
            Message.channel == "webchat",
        )
        .order_by(Message.created_at.desc())
        .limit(20)
    ).scalars().all()
    for row in rows:
        payload = row.payload if isinstance(row.payload, dict) else {}
        if str(payload.get("reply_to_message_id") or "") == str(inbound_message_id):
            return row
    return None


def _create_webchat_fallback_reply(
    db: Session,
    *,
    session: LinkFlowSession,
    conversation: Conversation,
    inbound_message: Message,
) -> Message:
    now = _now()
    outbound = Message(
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        direction=MessageDirection.OUTBOUND.value,
        channel="webchat",
        sender_type="ai",
        body=WEBCHAT_FALLBACK_REPLY,
        message_type="text",
        payload={
            "source": "webchat_fallback",
            "mode": "fallback_clarification",
            "reply_to_message_id": str(inbound_message.id),
        },
        status=MessageStatus.SENT.value,
    )
    db.add(outbound)
    conversation.last_message_at = now
    session.last_assistant_message_at = now
    db.add(conversation)
    db.add(session)
    register_link_flow_event(
        db,
        session=session,
        event_name="webchat_fallback_reply_sent",
        payload={"source": "public_webchat", "inbound_message_id": str(inbound_message.id)},
    )
    db.commit()
    db.refresh(outbound)
    return outbound


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


def _latest_public_summary_draft(db: Session, *, session: LinkFlowSession) -> dict[str, Any]:
    event = db.scalar(
        select(LinkFlowEvent)
        .where(
            LinkFlowEvent.link_flow_session_id == session.id,
            LinkFlowEvent.event_name == "webchat_summary_updated",
        )
        .order_by(desc(LinkFlowEvent.occurred_at), desc(LinkFlowEvent.created_at))
        .limit(1)
    )
    return event.payload if event and isinstance(event.payload, dict) else {}


def _latest_public_booking_progress(
    db: Session,
    *,
    conversation: Conversation | None,
) -> dict[str, Any]:
    if not conversation:
        return {}
    from app.services.ai_autoresponder_service import _latest_saved_booking_state

    state = _latest_saved_booking_state(db, conversation=conversation)
    return state if isinstance(state, dict) else {}


def _unit_name_by_id(db: Session, *, tenant_id: UUID, unit_id: UUID | None) -> str | None:
    if not unit_id:
        return None
    unit = db.scalar(
        select(Unit).where(
            Unit.id == unit_id,
            Unit.tenant_id == tenant_id,
            Unit.is_active.is_(True),
        )
    )
    return unit.name if unit else None


def _clean_summary_text(value: Any, *, max_length: int = 140) -> str | None:
    text = " ".join(str(value or "").strip().split())
    return text[:max_length] if text else None


def _parse_summary_birth_date(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ApiError(
            status_code=422,
            code="WEBCHAT_SUMMARY_BIRTH_DATE_INVALID",
            message="Data de nascimento invalida.",
        ) from exc
    return parsed


def _parse_summary_preferred_date(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise ApiError(
            status_code=422,
            code="WEBCHAT_SUMMARY_PREFERRED_DATE_INVALID",
            message="Data preferencial invalida.",
        ) from exc


def _summary_value(value: Any, *, source: str | None = None) -> dict[str, Any]:
    text = None if value is None else str(value).strip()
    complete = bool(text)
    return {
        "value": text or None,
        "complete": complete,
        "source": source if complete and source else None,
    }


def _public_summary_service_options(
    db: Session,
    *,
    tenant_id: UUID,
    current_unit_id: UUID | None,
) -> list[dict[str, str]]:
    from app.services.service_catalog_service import get_service_catalog_items
    from app.services.unit_catalog_service import list_unit_services_map

    seen: set[str] = set()
    names: list[str] = []
    unit_services_map = list_unit_services_map(db, tenant_id=tenant_id)

    if current_unit_id:
        for service_name in unit_services_map.get(str(current_unit_id), []):
            key = service_name.casefold()
            if key in seen:
                continue
            seen.add(key)
            names.append(service_name)

    if not names:
        for service_names in unit_services_map.values():
            for service_name in service_names:
                key = service_name.casefold()
                if key in seen:
                    continue
                seen.add(key)
                names.append(service_name)

    if not names:
        for item in get_service_catalog_items(db, tenant_id=tenant_id):
            if not item.get("is_active", True):
                continue
            service_name = _clean_summary_text(item.get("name"), max_length=120)
            if not service_name:
                continue
            key = service_name.casefold()
            if key in seen:
                continue
            seen.add(key)
            names.append(service_name)

    return [{"id": f"service_{index}", "name": name} for index, name in enumerate(names, start=1)]


def _public_summary_schedule_options(
    db: Session,
    *,
    session: LinkFlowSession,
    tenant: Tenant,
    current_unit_id: UUID | None,
    procedure_value: str | None,
    preferred_date: str | None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    if not current_unit_id or not procedure_value or not session.linked_conversation_id:
        return [], []

    unit = db.scalar(
        select(Unit).where(
            Unit.id == current_unit_id,
            Unit.tenant_id == tenant.id,
            Unit.is_active.is_(True),
        )
    )
    conversation = db.get(Conversation, session.linked_conversation_id)
    if not unit or not conversation or conversation.tenant_id != tenant.id:
        return [], []

    config = get_intake_config(db, tenant_id=tenant.id)
    from app.services.ai_autoresponder_service import (
        _resolve_operation_timezone,
        _wizard_collect_day_choices,
        _wizard_collect_time_choices,
    )

    selected_date: date | None = None
    if preferred_date:
        try:
            selected_date = date.fromisoformat(preferred_date[:10])
        except ValueError:
            selected_date = None

    day_choices = _wizard_collect_day_choices(
        db,
        conversation=conversation,
        unit_id=unit.id,
        procedure_type=procedure_value,
        period=None,
        requested_date=selected_date,
        operation_timezone=_resolve_operation_timezone(config),
        config=config,
    )
    preferred_dates = [
        {
            "id": str(choice.get("id") or choice.get("date") or ""),
            "date": str(choice.get("date") or ""),
            "label": str(choice.get("label") or ""),
            "description": str(choice.get("description") or ""),
        }
        for choice in day_choices
        if str(choice.get("date") or "").strip() and str(choice.get("label") or "").strip()
    ]

    if not selected_date:
        return preferred_dates, []

    slot_choices = _wizard_collect_time_choices(
        db,
        conversation=conversation,
        unit=unit,
        procedure_type=procedure_value,
        period=None,
        selected_date=selected_date,
        config=config,
    )
    preferred_times = [
        {
            "id": str(choice.get("id") or ""),
            "label": str(choice.get("label") or ""),
            "time": str(choice.get("time") or ""),
        }
        for choice in slot_choices
        if str(choice.get("label") or "").strip()
    ]
    return preferred_dates, preferred_times


def _build_manual_summary_followup_text(
    *,
    patient_name: str | None = None,
    patient_email: str | None = None,
    birth_date_value: date | None = None,
    unit_name: str | None,
    procedure_value: str | None,
    preferred_date: str | None,
    preferred_time: str | None,
) -> str | None:
    details: list[str] = []
    if patient_name:
        details.append(f"Paciente: {patient_name}")
    if patient_email:
        details.append(f"E-mail: {patient_email}")
    if birth_date_value:
        details.append(f"Data de nascimento: {birth_date_value.strftime('%d/%m/%Y')}")
    if unit_name:
        details.append(f"Unidade: {unit_name}")
    if procedure_value:
        details.append(f"Servico: {procedure_value}")
    if preferred_date:
        details.append(f"Data desejada: {date.fromisoformat(preferred_date).strftime('%d/%m/%Y')}")
    if preferred_time:
        details.append(f"Horario desejado: {preferred_time}")
    if not details:
        return None
    return (
        "Atualizei manualmente meu agendamento pelo painel.\n"
        + "\n".join(f"- {item}" for item in details)
        + "\nConsidere essas informacoes e continue meu atendimento."
    )


def _summary_context(
    db: Session,
    *,
    session: LinkFlowSession,
    tenant: Tenant,
) -> dict[str, Any]:
    patient = db.get(Patient, session.linked_patient_id) if session.linked_patient_id else None
    conversation = db.get(Conversation, session.linked_conversation_id) if session.linked_conversation_id else None
    appointment = db.get(Appointment, session.linked_appointment_id) if session.linked_appointment_id else None
    draft = _latest_public_summary_draft(db, session=session)
    progress_state = _latest_public_booking_progress(db, conversation=conversation)

    draft_unit_id: UUID | None = None
    raw_draft_unit_id = draft.get("unit_id")
    if raw_draft_unit_id:
        try:
            draft_unit_id = UUID(str(raw_draft_unit_id))
        except (TypeError, ValueError):
            draft_unit_id = None

    progress_unit_id: UUID | None = None
    raw_progress_unit_id = progress_state.get("clinic_id")
    if raw_progress_unit_id:
        try:
            progress_unit_id = UUID(str(raw_progress_unit_id))
        except (TypeError, ValueError):
            progress_unit_id = None

    current_unit_id = (
        appointment.unit_id
        if appointment
        else conversation.unit_id if conversation and conversation.unit_id else patient.unit_id if patient and patient.unit_id else session.unit_id or draft_unit_id or progress_unit_id
    )
    unit = db.scalar(
        select(Unit).where(
            Unit.id == current_unit_id,
            Unit.tenant_id == tenant.id,
            Unit.is_active.is_(True),
        )
    ) if current_unit_id else None

    progress_selected_slot = (
        progress_state.get("selected_slot")
        if isinstance(progress_state.get("selected_slot"), dict)
        else {}
    )
    return {
        "patient": patient,
        "conversation": conversation,
        "appointment": appointment,
        "draft": draft,
        "progress_state": progress_state,
        "progress_selected_slot": progress_selected_slot,
        "current_unit_id": current_unit_id,
        "unit": unit,
    }


def _dispatch_manual_summary_followup(
    db: Session,
    *,
    session: LinkFlowSession,
    tenant: Tenant,
    text: str,
    changed_fields: list[str],
) -> None:
    conversation = ensure_webchat_conversation(db, session=session, tenant=tenant)
    now = _now()
    inbound = Message(
        tenant_id=tenant.id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND.value,
        channel="webchat",
        sender_type="patient",
        body=text,
        message_type="text",
        payload={
            "source": "public_webchat_summary_manual_update",
            "link_flow_session_id": str(session.id),
            "changed_fields": changed_fields,
        },
        status=MessageStatus.RECEIVED.value,
    )
    db.add(inbound)
    conversation.last_message_at = now
    session.last_patient_message_at = now
    db.add(conversation)
    db.add(session)
    register_link_flow_event(
        db,
        session=session,
        event_name="webchat_summary_manual_followup_sent",
        payload={"source": "public_webchat", "changed_fields": changed_fields},
    )
    db.commit()
    db.refresh(inbound)

    from app.services.ai_autoresponder_service import process_inbound_message

    process_inbound_message(
        db,
        tenant_id=tenant.id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )


def send_public_webchat_summary_followup(
    db: Session,
    *,
    session: LinkFlowSession,
    tenant: Tenant,
) -> dict[str, Any]:
    context = _summary_context(db, session=session, tenant=tenant)
    patient = context["patient"]
    draft = context["draft"]
    unit = context["unit"]
    progress_state = context["progress_state"]
    progress_selected_slot = context["progress_selected_slot"]

    patient_name = None if _placeholder_patient_name(patient.full_name if patient else None) else _clean_summary_text(patient.full_name if patient else None, max_length=180)
    patient_email = _clean_summary_text(patient.email if patient else None, max_length=180)
    birth_date_value = patient.birth_date if patient and patient.birth_date else None
    procedure_value = _clean_summary_text(
        progress_state.get("service") or draft.get("procedure_type"),
        max_length=120,
    )
    progress_requested_date = (
        _parse_summary_preferred_date(progress_state.get("requested_date"))
        if progress_state.get("requested_date")
        else None
    )
    appointment_date = appointment.starts_at.date().isoformat() if appointment and appointment.starts_at else None
    preferred_date = (
        _parse_summary_preferred_date(draft.get("preferred_date"))
        if draft.get("preferred_date")
        else _parse_summary_preferred_date(progress_state.get("date")) if progress_state.get("date")
        else progress_requested_date
        or appointment_date
    )
    preferred_time = _clean_summary_text(
        draft.get("preferred_time")
        or progress_selected_slot.get("label")
        or progress_selected_slot.get("time")
        or progress_state.get("time"),
        max_length=80,
    )
    followup_text = _build_manual_summary_followup_text(
        patient_name=patient_name,
        patient_email=patient_email,
        birth_date_value=birth_date_value,
        unit_name=unit.name if unit else _clean_summary_text(progress_state.get("clinic_name"), max_length=120),
        procedure_value=procedure_value,
        preferred_date=preferred_date,
        preferred_time=preferred_time,
    )
    if not followup_text:
        raise ApiError(
            status_code=422,
            code="WEBCHAT_SUMMARY_FOLLOWUP_EMPTY",
            message="Ainda nao ha informacoes suficientes no painel para continuar o atendimento.",
        )
    _dispatch_manual_summary_followup(
        db,
        session=session,
        tenant=tenant,
        text=followup_text,
        changed_fields=["panel_resume"],
    )
    return public_webchat_booking_summary(db, session=session, tenant=tenant)


def public_webchat_booking_summary(
    db: Session,
    *,
    session: LinkFlowSession,
    tenant: Tenant,
) -> dict[str, Any]:
    context = _summary_context(db, session=session, tenant=tenant)
    patient = context["patient"]
    conversation = context["conversation"]
    appointment = context["appointment"]
    draft = context["draft"]
    progress_state = context["progress_state"]
    progress_selected_slot = context["progress_selected_slot"]
    current_unit_id = context["current_unit_id"]
    unit = context["unit"]

    patient_name = None if _placeholder_patient_name(patient.full_name if patient else None) else _clean_summary_text(patient.full_name if patient else None, max_length=180)
    patient_email = _clean_summary_text(patient.email if patient else None, max_length=180)
    birth_date_value = patient.birth_date.isoformat() if patient and patient.birth_date else None
    progress_unit_id = None
    raw_progress_unit_id = progress_state.get("clinic_id")
    if raw_progress_unit_id:
        try:
            progress_unit_id = UUID(str(raw_progress_unit_id))
        except (TypeError, ValueError):
            progress_unit_id = None
    unit_name = unit.name if unit else _clean_summary_text(progress_state.get("clinic_name"), max_length=120)
    unit_address = None
    if unit:
        from app.services.ai_autoresponder_service import _format_unit_address

        unit_address = _clean_summary_text(_format_unit_address(unit.address), max_length=240)

    procedure_value = _clean_summary_text(
        appointment.procedure_type
        if appointment and appointment.procedure_type
        else progress_state.get("service") or draft.get("procedure_type"),
        max_length=120,
    )
    preferred_date = (
        _parse_summary_preferred_date(draft.get("preferred_date"))
        if draft.get("preferred_date")
        else _parse_summary_preferred_date(progress_state.get("date")) if progress_state.get("date") else None
    )
    preferred_time = _clean_summary_text(draft.get("preferred_time"), max_length=80)
    progress_slot_starts_at = _clean_summary_text(progress_selected_slot.get("starts_at_utc"), max_length=80)
    progress_slot_time = _clean_summary_text(
        progress_selected_slot.get("time") or progress_state.get("time"),
        max_length=80,
    )
    progress_slot_label = _clean_summary_text(progress_selected_slot.get("label"), max_length=140)
    confirmed_slot = (
        appointment.starts_at.isoformat()
        if appointment and appointment.starts_at
        else progress_slot_starts_at or preferred_time or progress_slot_time or progress_slot_label
    )
    confirmed_slot_source = (
        "auto"
        if appointment and appointment.starts_at
        else "conversation"
        if progress_slot_starts_at
        else "manual"
        if confirmed_slot
        else None
    )
    preferred_dates, preferred_times = _public_summary_schedule_options(
        db,
        session=session,
        tenant=tenant,
        current_unit_id=current_unit_id,
        procedure_value=procedure_value,
        preferred_date=preferred_date,
    )
    service_options = _public_summary_service_options(
        db,
        tenant_id=tenant.id,
        current_unit_id=current_unit_id,
    )

    fields = {
        "patient_name": _summary_value(patient_name, source="auto" if patient_name else None),
        "email": _summary_value(patient_email, source="auto" if patient_email else None),
        "birth_date": _summary_value(birth_date_value, source="auto" if birth_date_value else None),
        "unit": {
            **_summary_value(
                unit_name,
                source=(
                    "auto"
                    if appointment or (conversation and conversation.unit_id) or (patient and patient.unit_id) or session.unit_id
                    else "conversation"
                    if progress_state.get("clinic_name") or progress_unit_id
                    else "manual"
                ),
            ),
            "unit_id": str(current_unit_id) if current_unit_id else None,
        },
        "procedure": _summary_value(
            procedure_value,
            source="auto" if appointment and appointment.procedure_type else "conversation" if progress_state.get("service") else "manual",
        ),
        "preferred_date": _summary_value(
            preferred_date,
            source="conversation" if progress_state.get("date") and not draft.get("preferred_date") else "manual",
        ),
        "confirmed_slot": _summary_value(confirmed_slot, source=confirmed_slot_source),
    }

    completion_order = ["patient_name", "email", "birth_date", "unit", "procedure", "confirmed_slot"]
    complete_count = sum(1 for key in completion_order if bool(fields[key]["complete"]))

    units = db.execute(
        select(Unit)
        .where(Unit.tenant_id == tenant.id, Unit.is_active.is_(True))
        .order_by(Unit.name.asc())
        .limit(20)
    ).scalars().all()

    appointment_status = "Agendado" if appointment else "Em andamento" if complete_count >= 2 else "Coletando dados"
    appointment_tone = "success" if appointment else "progress" if complete_count >= 2 else "pending"

    return {
        "session_status": session.status,
        "progress": {
            "complete_count": complete_count,
            "total_count": len(completion_order),
        },
        "status": {
            "label": appointment_status,
            "tone": appointment_tone,
            "appointment_created": bool(appointment),
        },
        "fields": fields,
        "appointment": {
            "id": str(appointment.id) if appointment else None,
            "starts_at": confirmed_slot,
            "confirmation_status": appointment.confirmation_status if appointment else None,
            "unit_name": unit_name,
            "unit_address": unit_address,
            "patient_name": patient_name,
            "patient_email": patient_email,
            "birth_date": birth_date_value,
            "procedure_type": procedure_value,
        },
        "options": {
            "units": [{"id": str(unit.id), "name": unit.name} for unit in units],
            "services": service_options,
            "preferred_dates": preferred_dates,
            "preferred_times": preferred_times,
        },
    }


def update_public_webchat_booking_summary(
    db: Session,
    *,
    session: LinkFlowSession,
    tenant: Tenant,
    full_name: str | None = None,
    email: str | None = None,
    birth_date_value: str | None = None,
    procedure_type: str | None = None,
    unit_id: UUID | None = None,
    preferred_date: str | None = None,
    preferred_time: str | None = None,
    dispatch_followup: bool = False,
) -> dict[str, Any]:
    patient = _ensure_webchat_patient(db, session=session, tenant=tenant)
    draft = _latest_public_summary_draft(db, session=session)
    previous_procedure = _clean_summary_text(draft.get("procedure_type"), max_length=120)
    previous_preferred_date = _parse_summary_preferred_date(draft.get("preferred_date")) if draft.get("preferred_date") else None
    previous_preferred_time = _clean_summary_text(draft.get("preferred_time"), max_length=80)
    previous_unit_id = str(session.unit_id or patient.unit_id or draft.get("unit_id") or "").strip() or None
    unit_name_for_followup = _unit_name_by_id(db, tenant_id=tenant.id, unit_id=session.unit_id or patient.unit_id)
    changed_fields: list[str] = []
    previous_name = _clean_summary_text(patient.full_name, max_length=180)
    previous_email = _clean_summary_text(patient.email, max_length=180)
    previous_birth_date = patient.birth_date

    normalized_name = _clean_summary_text(full_name, max_length=180)
    if normalized_name:
        patient.full_name = normalized_name
    if normalized_name != previous_name:
        changed_fields.append("patient_name")

    normalized_email = _clean_summary_text(email, max_length=180)
    if normalized_email:
        patient.email = normalized_email
    if normalized_email != previous_email:
        changed_fields.append("email")

    parsed_birth_date = _parse_summary_birth_date(birth_date_value)
    if parsed_birth_date:
        patient.birth_date = parsed_birth_date
    if parsed_birth_date != previous_birth_date:
        changed_fields.append("birth_date")

    if procedure_type is not None:
        normalized_procedure = _clean_summary_text(procedure_type, max_length=120)
        if normalized_procedure:
            draft["procedure_type"] = normalized_procedure
        else:
            draft.pop("procedure_type", None)
        if normalized_procedure != previous_procedure:
            changed_fields.append("procedure")

    if preferred_date is not None:
        parsed_preferred_date = _parse_summary_preferred_date(preferred_date)
        if parsed_preferred_date:
            draft["preferred_date"] = parsed_preferred_date
        else:
            draft.pop("preferred_date", None)
        draft.pop("preferred_time", None)
        if parsed_preferred_date != previous_preferred_date:
            changed_fields.append("preferred_date")
        if previous_preferred_time:
            changed_fields.append("confirmed_slot")

    if preferred_time is not None:
        normalized_preferred_time = _clean_summary_text(preferred_time, max_length=80)
        if normalized_preferred_time:
            draft["preferred_time"] = normalized_preferred_time
        else:
            draft.pop("preferred_time", None)
        if normalized_preferred_time != previous_preferred_time:
            changed_fields.append("confirmed_slot")

    if unit_id:
        unit = db.scalar(
            select(Unit).where(
                Unit.id == unit_id,
                Unit.tenant_id == tenant.id,
                Unit.is_active.is_(True),
            )
        )
        if not unit:
            raise ApiError(
                status_code=404,
                code="WEBCHAT_SUMMARY_UNIT_NOT_FOUND",
                message="Unidade nao encontrada para este agendamento.",
            )
        session.unit_id = unit.id
        patient.unit_id = unit.id
        draft["unit_id"] = str(unit.id)
        draft.pop("preferred_date", None)
        draft.pop("preferred_time", None)
        if session.linked_conversation_id:
            conversation = db.get(Conversation, session.linked_conversation_id)
            if conversation and conversation.tenant_id == tenant.id:
                conversation.unit_id = unit.id
                db.add(conversation)
        unit_name_for_followup = unit.name
        if str(unit.id) != previous_unit_id:
            changed_fields.append("unit")
        if previous_preferred_date:
            changed_fields.append("preferred_date")
        if previous_preferred_time:
            changed_fields.append("confirmed_slot")

    changed_fields = list(dict.fromkeys(changed_fields))

    db.add(patient)
    db.add(session)
    register_link_flow_event(
        db,
        session=session,
        event_name="webchat_summary_updated",
        payload=draft,
    )
    db.commit()
    db.refresh(session)
    followup_text = None
    if dispatch_followup and changed_fields:
        followup_text = _build_manual_summary_followup_text(
            patient_name=_clean_summary_text(patient.full_name, max_length=180),
            patient_email=_clean_summary_text(patient.email, max_length=180),
            birth_date_value=patient.birth_date,
            unit_name=unit_name_for_followup or _unit_name_by_id(db, tenant_id=tenant.id, unit_id=session.unit_id),
            procedure_value=_clean_summary_text(draft.get("procedure_type"), max_length=120),
            preferred_date=_parse_summary_preferred_date(draft.get("preferred_date")) if draft.get("preferred_date") else None,
            preferred_time=_clean_summary_text(draft.get("preferred_time"), max_length=80),
        )
    if followup_text:
        _dispatch_manual_summary_followup(
            db,
            session=session,
            tenant=tenant,
            text=followup_text,
            changed_fields=changed_fields,
        )
    return public_webchat_booking_summary(db, session=session, tenant=tenant)


def confirm_public_webchat_booking_summary(
    db: Session,
    *,
    session: LinkFlowSession,
    tenant: Tenant,
) -> dict[str, Any]:
    context = _summary_context(db, session=session, tenant=tenant)
    patient = context["patient"]
    conversation = context["conversation"]
    appointment = context["appointment"]
    draft = context["draft"]
    progress_state = context["progress_state"]
    progress_selected_slot = context["progress_selected_slot"]
    unit = context["unit"]
    from app.services.ai_autoresponder_service import _wizard_slot_from_choice

    if appointment:
        unit_address = None
        appointment_unit = db.scalar(
            select(Unit).where(
                Unit.id == appointment.unit_id,
                Unit.tenant_id == tenant.id,
                Unit.is_active.is_(True),
            )
        )
        if appointment_unit:
            from app.services.ai_autoresponder_service import _format_unit_address

            unit_address = _clean_summary_text(_format_unit_address(appointment_unit.address), max_length=240)
        return {
            "summary": public_webchat_booking_summary(db, session=session, tenant=tenant),
            "result": {
                "status": "already_created",
                "appointment_id": str(appointment.id),
                "unit_name": _unit_name_by_id(db, tenant_id=tenant.id, unit_id=appointment.unit_id),
                "unit_address": unit_address,
                "procedure_type": appointment.procedure_type,
                "starts_at": appointment.starts_at.isoformat() if appointment.starts_at else None,
                "patient_name": None if _placeholder_patient_name(patient.full_name if patient else None) else _clean_summary_text(patient.full_name if patient else None, max_length=180),
                "patient_email": _clean_summary_text(patient.email if patient else None, max_length=180),
                "birth_date": patient.birth_date.isoformat() if patient and patient.birth_date else None,
            },
        }

    if not patient or _placeholder_patient_name(patient.full_name):
        raise ApiError(status_code=422, code="WEBCHAT_SUMMARY_NAME_REQUIRED", message="Informe o nome do paciente antes de agendar.")
    if not patient.birth_date:
        raise ApiError(status_code=422, code="WEBCHAT_SUMMARY_BIRTH_DATE_REQUIRED", message="Informe a data de nascimento antes de agendar.")
    if not unit:
        raise ApiError(status_code=422, code="WEBCHAT_SUMMARY_UNIT_REQUIRED", message="Escolha a unidade antes de agendar.")

    procedure_type = _clean_summary_text(
        appointment.procedure_type if appointment and appointment.procedure_type else progress_state.get("service") or draft.get("procedure_type"),
        max_length=120,
    )
    if not procedure_type:
        raise ApiError(status_code=422, code="WEBCHAT_SUMMARY_SERVICE_REQUIRED", message="Escolha o servico antes de agendar.")

    preferred_date_iso = (
        _parse_summary_preferred_date(draft.get("preferred_date"))
        if draft.get("preferred_date")
        else _parse_summary_preferred_date(progress_state.get("date")) if progress_state.get("date") else None
    )
    if not preferred_date_iso:
        raise ApiError(status_code=422, code="WEBCHAT_SUMMARY_DATE_REQUIRED", message="Escolha a data antes de agendar.")

    selected_slot: dict[str, Any] | None = None
    if progress_selected_slot:
        selected_slot = _wizard_slot_from_choice(progress_selected_slot)
    else:
        preferred_time = _clean_summary_text(draft.get("preferred_time"), max_length=80)
        if not preferred_time:
            raise ApiError(status_code=422, code="WEBCHAT_SUMMARY_TIME_REQUIRED", message="Escolha o horario antes de agendar.")
        if not conversation:
            conversation = ensure_webchat_conversation(db, session=session, tenant=tenant)
        config = get_intake_config(db, tenant_id=tenant.id)
        from app.services.ai_autoresponder_service import _wizard_collect_time_choices

        slot_choices = _wizard_collect_time_choices(
            db,
            conversation=conversation,
            unit=unit,
            procedure_type=procedure_type,
            period=None,
            selected_date=date.fromisoformat(preferred_date_iso),
            config=config,
        )
        matched_choice = next(
            (
                choice for choice in slot_choices
                if _clean_summary_text(choice.get("label"), max_length=80) == preferred_time
                or _clean_summary_text(choice.get("time"), max_length=80) == preferred_time
            ),
            None,
        )
        if not matched_choice:
            raise ApiError(
                status_code=409,
                code="WEBCHAT_SUMMARY_TIME_UNAVAILABLE",
                message="Esse horario nao esta mais disponivel. Escolha outra opcao no painel ou continue pelo chat.",
            )
        selected_slot = _wizard_slot_from_choice(matched_choice)

    if not selected_slot:
        raise ApiError(
            status_code=409,
            code="WEBCHAT_SUMMARY_SLOT_INVALID",
            message="Nao consegui validar o horario escolhido. Selecione outro horario e tente novamente.",
        )

    if not conversation:
        conversation = ensure_webchat_conversation(db, session=session, tenant=tenant)
    from app.services.ai_autoresponder_service import _appointment_response_from_selected_slot, _format_unit_address

    result = _appointment_response_from_selected_slot(
        db,
        conversation=conversation,
        unit=unit,
        selected_slot=selected_slot,
        procedure_type=procedure_type,
        period=str(progress_state.get("period") or "").strip() or None,
        requested_date=date.fromisoformat(preferred_date_iso),
    )
    if result.get("mode") not in {"appointment_created", "appointment_already_created"}:
        raise ApiError(
            status_code=409,
            code="WEBCHAT_SUMMARY_CONFIRMATION_FAILED",
            message=str(result.get("response_text") or "Nao foi possivel concluir o agendamento agora."),
        )

    db.commit()
    updated_summary = public_webchat_booking_summary(db, session=session, tenant=tenant)
    return {
        "summary": updated_summary,
        "result": {
            "status": "created" if result.get("mode") == "appointment_created" else "already_created",
            "appointment_id": str(result.get("metadata", {}).get("appointment_id") or ""),
            "unit_name": str(result.get("metadata", {}).get("unit_name") or unit.name),
            "unit_address": str(result.get("metadata", {}).get("unit_address") or _format_unit_address(unit.address) or ""),
            "procedure_type": str(result.get("metadata", {}).get("procedure_type") or procedure_type),
            "starts_at": str(result.get("metadata", {}).get("starts_at_utc") or ""),
            "patient_name": _clean_summary_text(patient.full_name, max_length=180),
            "patient_email": _clean_summary_text(patient.email, max_length=180),
            "birth_date": patient.birth_date.isoformat() if patient.birth_date else None,
        },
    }


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

    refreshed_conversation = db.get(Conversation, conversation.id)
    refreshed_session = db.get(LinkFlowSession, session.id)
    if refreshed_conversation and refreshed_session:
        assistant_reply = _latest_webchat_assistant_reply_for_inbound(
            db,
            conversation=refreshed_conversation,
            inbound_message_id=inbound.id,
        )
        if not assistant_reply:
            assistant_reply = _create_webchat_fallback_reply(
                db,
                session=refreshed_session,
                conversation=refreshed_conversation,
                inbound_message=inbound,
            )
            if isinstance(ai_result, dict):
                ai_result = {
                    **ai_result,
                    "fallback_reply_used": True,
                    "fallback_outbound_message_id": str(assistant_reply.id),
                }

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

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import quote
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.models import (
    Conversation,
    LinkFlowEvent,
    LinkFlowSession,
    Patient,
    PatientContact,
    Setting,
    Tenant,
    WhatsAppAccount,
)
from app.utils.hash import sha256_text
from app.utils.phone import normalize_phone

INTAKE_CONFIG_KEY = "intake.config"
LINK_FLOW_TOKEN_PREFIX = "CFX"
LINK_FLOW_TOKEN_PATTERN = re.compile(r"\bCFX:([A-Za-z0-9_-]{16,256})\b")
LINK_FLOW_ALLOWED_EVENTS = {
    "landing_viewed",
    "cta_whatsapp_clicked",
    "conversation_started",
    "booking_attempt_started",
    "appointment_created",
    "appointment_duplicate_detected",
    "session_invalid",
    "session_expired",
    "webchat_opened",
    "webchat_started",
    "webchat_message_sent",
    "webchat_first_ai_response",
    "webchat_session_resumed",
    "webchat_summary_updated",
    "webchat_summary_manual_followup_sent",
    "webchat_session_closed",
    "webchat_error",
    "contact_phone_captured",
}
LINK_FLOW_ACTIVE_STATUSES = {"pending", "linked"}
LINK_FLOW_INACTIVE_STATUSES = {"cancelled", "completed", "closed", "inactive"}

DEFAULT_LINK_FLOW_CONFIG = {
    "enabled": False,
    "cta_mode": "whatsapp_redirect",
    "headline": "Agendamento oficial da clinica",
    "trust_message": "Continue pelo canal oficial para falar com a assistente de agendamento.",
    "button_label": "Continuar pelo WhatsApp",
    "session_ttl_minutes": 30,
}

DEFAULT_INTAKE_CONFIG = {
    "mode": "official_api",
    "link_flow": DEFAULT_LINK_FLOW_CONFIG,
}


class IntakeLinkFlowConfigInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    cta_mode: Literal["whatsapp_redirect", "webchat"] = "whatsapp_redirect"
    headline: str = Field(default=DEFAULT_LINK_FLOW_CONFIG["headline"], min_length=3, max_length=240)
    trust_message: str = Field(default=DEFAULT_LINK_FLOW_CONFIG["trust_message"], min_length=3, max_length=500)
    button_label: str = Field(default=DEFAULT_LINK_FLOW_CONFIG["button_label"], min_length=2, max_length=80)
    session_ttl_minutes: int = Field(default=30, ge=5, le=240)

    @field_validator("headline", "trust_message", "button_label", mode="before")
    @classmethod
    def _compact_text_field(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())


class IntakeConfigInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["official_api", "link_flow", "hybrid"] = "official_api"
    link_flow: IntakeLinkFlowConfigInput = Field(default_factory=IntakeLinkFlowConfigInput)


@dataclass
class LinkFlowInboundResolution:
    token_found: bool
    session: LinkFlowSession | None
    sanitized_text: str
    failure_reason: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.session is not None and self.failure_reason is None


def _clean_text(value: Any, fallback: str, *, max_length: int = 240) -> str:
    text = " ".join(str(value or "").strip().split())
    if not text:
        text = fallback
    return text[:max_length]


def _positive_int(value: Any, fallback: int, *, minimum: int = 5, maximum: int = 240) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(minimum, min(parsed, maximum))


def validate_intake_config_payload(payload: Any) -> dict:
    try:
        return IntakeConfigInput.model_validate(payload or {}).model_dump(mode="json")
    except ValidationError as exc:
        raise ApiError(
            status_code=422,
            code="INTAKE_CONFIG_INVALID",
            message="Configuracao de entrada invalida.",
            details={"errors": exc.errors()},
        ) from exc


def get_intake_config(db: Session, *, tenant_id: UUID) -> dict:
    setting = db.scalar(
        select(Setting).where(
            Setting.tenant_id == tenant_id,
            Setting.key == INTAKE_CONFIG_KEY,
        )
    )
    raw = setting.value if setting and isinstance(setting.value, dict) else {}
    raw_link_flow = raw.get("link_flow") if isinstance(raw.get("link_flow"), dict) else {}

    mode = str(raw.get("mode") or DEFAULT_INTAKE_CONFIG["mode"]).strip()
    if mode not in {"official_api", "link_flow", "hybrid"}:
        mode = "official_api"

    cta_mode = str(raw_link_flow.get("cta_mode") or DEFAULT_LINK_FLOW_CONFIG["cta_mode"]).strip()
    if cta_mode not in {"whatsapp_redirect", "webchat"}:
        cta_mode = "whatsapp_redirect"

    link_flow = {
        "enabled": bool(raw_link_flow.get("enabled", False)),
        "cta_mode": cta_mode,
        "headline": _clean_text(raw_link_flow.get("headline"), DEFAULT_LINK_FLOW_CONFIG["headline"]),
        "trust_message": _clean_text(raw_link_flow.get("trust_message"), DEFAULT_LINK_FLOW_CONFIG["trust_message"], max_length=500),
        "button_label": _clean_text(raw_link_flow.get("button_label"), DEFAULT_LINK_FLOW_CONFIG["button_label"], max_length=80),
        "session_ttl_minutes": _positive_int(
            raw_link_flow.get("session_ttl_minutes"),
            DEFAULT_LINK_FLOW_CONFIG["session_ttl_minutes"],
        ),
    }
    return {"mode": mode, "link_flow": link_flow}


def upsert_intake_config(db: Session, *, tenant_id: UUID, payload: Any) -> Setting:
    config = validate_intake_config_payload(payload)
    setting = db.scalar(
        select(Setting).where(
            Setting.tenant_id == tenant_id,
            Setting.key == INTAKE_CONFIG_KEY,
        )
    )
    if not setting:
        setting = Setting(
            tenant_id=tenant_id,
            key=INTAKE_CONFIG_KEY,
            value=config,
            is_secret=False,
        )
    else:
        setting.value = config
        setting.is_secret = False
    db.add(setting)
    return setting


def is_link_flow_enabled(config: dict) -> bool:
    mode = str(config.get("mode") or "official_api")
    link_flow = config.get("link_flow") if isinstance(config.get("link_flow"), dict) else {}
    return mode in {"link_flow", "hybrid"} and bool(link_flow.get("enabled"))


def extract_link_flow_token(text: str | None) -> tuple[str | None, str]:
    body = str(text or "")
    match = LINK_FLOW_TOKEN_PATTERN.search(body)
    if not match:
        return None, body.strip()
    sanitized = f"{body[:match.start()]} {body[match.end():]}"
    sanitized = " ".join(sanitized.split()).strip()
    return match.group(1), sanitized


def _hash_token(raw_token: str) -> str:
    return sha256_text(raw_token.strip())


def _now() -> datetime:
    return datetime.now(UTC)


def _sanitize_utm_payload(payload: dict | None) -> dict:
    if not isinstance(payload, dict):
        return {}
    sanitized: dict[str, str] = {}
    for key, value in payload.items():
        clean_key = re.sub(r"[^A-Za-z0-9_.-]", "_", str(key or "").strip())[:80]
        if not clean_key:
            continue
        sanitized[clean_key] = str(value or "").strip()[:240]
    return sanitized


def _system_whatsapp_account(db: Session) -> WhatsAppAccount | None:
    from app.services.sales_demo_service import ensure_sales_outreach_sender_tenant

    tenant = ensure_sales_outreach_sender_tenant(db)
    return db.scalar(
        select(WhatsAppAccount)
        .where(
            WhatsAppAccount.tenant_id == tenant.id,
            WhatsAppAccount.is_active.is_(True),
        )
        .order_by(WhatsAppAccount.created_at.desc())
        .limit(1)
    )


def _existing_system_sender_tenant(db: Session) -> Tenant | None:
    from app.services.sales_demo_service import resolve_sales_outreach_sender_tenant_slug

    slug = resolve_sales_outreach_sender_tenant_slug()
    return db.scalar(select(Tenant).where(Tenant.slug == slug))


def get_system_whatsapp_account(db: Session) -> WhatsAppAccount | None:
    return _system_whatsapp_account(db)


def is_system_link_flow_sender(db: Session, account: WhatsAppAccount | None) -> bool:
    if not account:
        return False
    tenant = _existing_system_sender_tenant(db)
    return bool(tenant and account.tenant_id == tenant.id)


def _system_whatsapp_phone(db: Session) -> str:
    account = _system_whatsapp_account(db)
    raw_phone = str((account.display_phone if account else None) or (account.phone_number_id if account else "")).strip()
    normalized = normalize_phone(raw_phone)
    if not normalized:
        raise ApiError(
            status_code=503,
            code="LINK_FLOW_SYSTEM_WHATSAPP_UNAVAILABLE",
            message="WhatsApp oficial do sistema indisponivel para criar o link de agendamento.",
        )
    return normalized


def _is_webchat_placeholder_phone(value: str | None) -> bool:
    return str(value or "").strip().lower().startswith("webchat")


def _public_contact_phone(patient: Patient | None) -> str | None:
    raw_phone = str(patient.phone or "").strip() if patient else ""
    normalized = normalize_phone(raw_phone)
    if not normalized or _is_webchat_placeholder_phone(raw_phone):
        return None
    return raw_phone


def public_contact_phone_state(db: Session, *, session: LinkFlowSession) -> dict[str, Any]:
    patient = db.get(Patient, session.linked_patient_id) if session.linked_patient_id else None
    contact_phone = _public_contact_phone(patient)
    return {
        "contact_phone": contact_phone,
        "contact_phone_required": not bool(contact_phone),
    }


def _normalize_public_contact_phone(value: str | None) -> tuple[str, str]:
    raw_phone = " ".join(str(value or "").strip().split())[:30]
    normalized_phone = normalize_phone(raw_phone)
    if len(normalized_phone) < 10 or len(normalized_phone) > 15:
        raise ApiError(
            status_code=422,
            code="PUBLIC_BOOKING_PHONE_INVALID",
            message="Informe um celular ou WhatsApp com DDD para continuar o atendimento.",
        )
    return raw_phone, normalized_phone


def _upsert_primary_phone_contact(
    db: Session,
    *,
    patient: Patient,
    raw_phone: str,
    normalized_phone: str,
) -> None:
    existing_contact = db.scalar(
        select(PatientContact).where(
            PatientContact.tenant_id == patient.tenant_id,
            PatientContact.patient_id == patient.id,
            PatientContact.channel == "whatsapp",
            PatientContact.is_primary.is_(True),
        )
    )
    if existing_contact:
        existing_contact.value = raw_phone
        existing_contact.normalized_value = normalized_phone
        existing_contact.is_verified = False
        db.add(existing_contact)
        return

    db.add(
        PatientContact(
            tenant_id=patient.tenant_id,
            patient_id=patient.id,
            channel="whatsapp",
            value=raw_phone,
            normalized_value=normalized_phone,
            is_primary=True,
            is_verified=False,
        )
    )


def capture_public_contact_phone(
    db: Session,
    *,
    session: LinkFlowSession,
    raw_phone: str | None,
) -> dict[str, Any]:
    compact_phone, normalized_phone = _normalize_public_contact_phone(raw_phone)
    tenant = db.get(Tenant, session.tenant_id)
    if not tenant or not tenant.is_active:
        raise ApiError(
            status_code=409,
            code="PUBLIC_BOOKING_NOT_AVAILABLE",
            message="Atendimento indisponivel. Abra novamente o link oficial da clinica para continuar.",
        )

    linked_patient = db.get(Patient, session.linked_patient_id) if session.linked_patient_id else None
    target_patient = db.scalar(
        select(Patient).where(
            Patient.tenant_id == session.tenant_id,
            Patient.normalized_phone == normalized_phone,
        )
    )
    if not target_patient:
        target_patient = linked_patient

    if not target_patient:
        target_patient = Patient(
            tenant_id=session.tenant_id,
            unit_id=session.unit_id,
            full_name="Paciente do agendamento",
            phone=compact_phone,
            normalized_phone=normalized_phone,
            status="lead",
            origin="link_flow_public",
            lgpd_consent=True,
            marketing_opt_in=False,
            tags_cache=["entry_link_flow"],
        )
        db.add(target_patient)
        db.flush()
    else:
        if session.unit_id and not target_patient.unit_id:
            target_patient.unit_id = session.unit_id
        target_patient.phone = compact_phone
        target_patient.normalized_phone = normalized_phone
        if not str(target_patient.origin or "").strip():
            target_patient.origin = "link_flow_public"
        db.add(target_patient)

    _upsert_primary_phone_contact(
        db,
        patient=target_patient,
        raw_phone=compact_phone,
        normalized_phone=normalized_phone,
    )

    session.linked_patient_id = target_patient.id
    db.add(session)

    if session.linked_conversation_id:
        conversation = db.get(Conversation, session.linked_conversation_id)
        if conversation and conversation.tenant_id == session.tenant_id and conversation.patient_id != target_patient.id:
            conversation.patient_id = target_patient.id
            if session.unit_id and not conversation.unit_id:
                conversation.unit_id = session.unit_id
            db.add(conversation)

    if session.cta_mode == "webchat":
        from app.services.webchat_service import ensure_webchat_conversation

        ensure_webchat_conversation(db, session=session, tenant=tenant)

    register_link_flow_event_once(
        db,
        session=session,
        event_name="contact_phone_captured",
        payload={"phone": normalized_phone},
        unique_payload_key="phone",
        unique_payload_value=normalized_phone,
    )

    return public_contact_phone_state(db, session=session)


def build_whatsapp_url(*, phone: str, raw_token: str | None, clinic_name: str) -> str:
    base_message = f"Ola, vim pelo agendamento oficial da {clinic_name}."
    if raw_token:
        message = f"{LINK_FLOW_TOKEN_PREFIX}:{raw_token} {base_message}"
    else:
        message = base_message
    return f"https://wa.me/{phone}?text={quote(message)}"


def create_link_flow_session(
    db: Session,
    *,
    tenant: Tenant,
    config: dict,
    landing_path: str,
    browser_session_id: str | None = None,
    utm_payload: dict | None = None,
    unit_id: UUID | None = None,
) -> tuple[LinkFlowSession, str, str]:
    if not is_link_flow_enabled(config):
        raise ApiError(
            status_code=404,
            code="LINK_FLOW_NOT_ENABLED",
            message="Agendamento por link indisponivel para esta clinica.",
        )

    link_flow = config.get("link_flow") if isinstance(config.get("link_flow"), dict) else {}
    raw_token = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(minutes=_positive_int(link_flow.get("session_ttl_minutes"), 30))
    phone = _system_whatsapp_phone(db)

    session = LinkFlowSession(
        tenant_id=tenant.id,
        unit_id=unit_id,
        mode="link_flow",
        cta_mode="whatsapp_redirect",
        channel="whatsapp",
        token_hash=_hash_token(raw_token),
        status="pending",
        landing_path=landing_path[:255],
        browser_session_id=(str(browser_session_id or "").strip()[:120] or None),
        utm_payload=_sanitize_utm_payload(utm_payload),
        expires_at=expires_at,
    )
    db.add(session)
    db.flush()
    whatsapp_url = build_whatsapp_url(phone=phone, raw_token=raw_token, clinic_name=tenant.trade_name or tenant.legal_name)
    return session, raw_token, whatsapp_url


def register_link_flow_event(
    db: Session,
    *,
    session: LinkFlowSession,
    event_name: str,
    page_path: str | None = None,
    payload: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    occurred_at: datetime | None = None,
) -> LinkFlowEvent:
    if event_name not in LINK_FLOW_ALLOWED_EVENTS:
        raise ApiError(
            status_code=422,
            code="LINK_FLOW_EVENT_INVALID",
            message="Evento do link flow invalido.",
        )

    timestamp = occurred_at or _now()
    event = LinkFlowEvent(
        tenant_id=session.tenant_id,
        link_flow_session_id=session.id,
        event_name=event_name,
        page_path=(str(page_path or "").strip()[:255] or None),
        payload=payload if isinstance(payload, dict) else {},
        ip_address=(str(ip_address or "").strip()[:100] or None),
        user_agent=(str(user_agent or "").strip()[:255] or None),
        occurred_at=timestamp,
    )
    if event_name == "landing_viewed" and not session.first_opened_at:
        session.first_opened_at = timestamp
    if event_name == "cta_whatsapp_clicked" and not session.cta_clicked_at:
        session.cta_clicked_at = timestamp
    db.add(session)
    db.add(event)
    return event


def register_link_flow_event_once(
    db: Session,
    *,
    session: LinkFlowSession,
    event_name: str,
    payload: dict | None = None,
    page_path: str | None = None,
    unique_payload_key: str | None = None,
    unique_payload_value: str | None = None,
) -> LinkFlowEvent | None:
    existing_events = db.execute(
        select(LinkFlowEvent).where(
            LinkFlowEvent.link_flow_session_id == session.id,
            LinkFlowEvent.event_name == event_name,
        )
    ).scalars().all()
    if not unique_payload_key:
        if existing_events:
            return None
    else:
        for event in existing_events:
            event_payload = event.payload if isinstance(event.payload, dict) else {}
            if str(event_payload.get(unique_payload_key) or "") == str(unique_payload_value or ""):
                return None
    return register_link_flow_event(
        db,
        session=session,
        event_name=event_name,
        page_path=page_path,
        payload=payload,
    )


def record_link_flow_unrouted_event(
    db: Session,
    *,
    tenant_id: UUID,
    event_name: str,
    payload: dict | None = None,
) -> LinkFlowEvent:
    if event_name not in LINK_FLOW_ALLOWED_EVENTS:
        raise ApiError(
            status_code=422,
            code="LINK_FLOW_EVENT_INVALID",
            message="Evento do link flow invalido.",
        )
    event = LinkFlowEvent(
        tenant_id=tenant_id,
        link_flow_session_id=None,
        event_name=event_name,
        page_path=None,
        payload=payload if isinstance(payload, dict) else {},
        occurred_at=_now(),
    )
    db.add(event)
    return event


def link_flow_session_for_conversation(db: Session, *, conversation: Conversation) -> LinkFlowSession | None:
    return db.scalar(
        select(LinkFlowSession)
        .where(
            LinkFlowSession.tenant_id == conversation.tenant_id,
            LinkFlowSession.linked_conversation_id == conversation.id,
        )
        .order_by(LinkFlowSession.created_at.desc())
        .limit(1)
    )


def record_link_flow_booking_attempt_started(
    db: Session,
    *,
    conversation: Conversation,
    payload: dict | None = None,
) -> LinkFlowEvent | None:
    session = link_flow_session_for_conversation(db, conversation=conversation)
    if not session:
        return None
    return register_link_flow_event_once(
        db,
        session=session,
        event_name="booking_attempt_started",
        payload=payload or {"source": "ai_booking"},
    )


def record_link_flow_appointment_result(
    db: Session,
    *,
    conversation: Conversation,
    appointment_id: UUID,
    event_name: Literal["appointment_created", "appointment_duplicate_detected"],
    payload: dict | None = None,
) -> LinkFlowEvent | None:
    session = link_flow_session_for_conversation(db, conversation=conversation)
    if not session:
        return None
    now = _now()
    if not session.linked_appointment_id:
        session.linked_appointment_id = appointment_id
    if not session.completed_at:
        session.completed_at = now
    if conversation.channel != "webchat":
        session.status = "completed"
    db.add(session)
    event_payload = {
        "appointment_id": str(appointment_id),
        **(payload if isinstance(payload, dict) else {}),
    }
    event = register_link_flow_event_once(
        db,
        session=session,
        event_name=event_name,
        payload=event_payload,
        unique_payload_key="appointment_id",
        unique_payload_value=str(appointment_id),
    )
    if event:
        db.flush()
    return event


def close_link_flow_session(
    db: Session,
    *,
    conversation: Conversation,
    reason: str,
    payload: dict | None = None,
) -> LinkFlowEvent | None:
    session = link_flow_session_for_conversation(db, conversation=conversation)
    if not session:
        return None

    now = _now()
    if not session.completed_at:
        session.completed_at = now
    if not session.closed_at:
        session.closed_at = now
    session.status = "closed"
    db.add(session)
    return register_link_flow_event_once(
        db,
        session=session,
        event_name="webchat_session_closed",
        payload={
            "reason": reason,
            **(payload if isinstance(payload, dict) else {}),
        },
        unique_payload_key="reason",
        unique_payload_value=reason,
    )


def resolve_inbound_link_flow_session(db: Session, *, text: str | None) -> LinkFlowInboundResolution:
    raw_token, sanitized_text = extract_link_flow_token(text)
    if not raw_token:
        return LinkFlowInboundResolution(token_found=False, session=None, sanitized_text=sanitized_text)

    session = db.scalar(
        select(LinkFlowSession).where(
            LinkFlowSession.token_hash == _hash_token(raw_token),
        )
    )
    if not session:
        return LinkFlowInboundResolution(
            token_found=True,
            session=None,
            sanitized_text=sanitized_text,
            failure_reason="session_invalid",
        )

    tenant = db.get(Tenant, session.tenant_id)
    if not tenant or not tenant.is_active:
        session.status = "inactive"
        db.add(session)
        register_link_flow_event_once(
            db,
            session=session,
            event_name="session_invalid",
            payload={"source": "whatsapp_inbound", "reason": "tenant_inactive"},
        )
        return LinkFlowInboundResolution(
            token_found=True,
            session=session,
            sanitized_text=sanitized_text,
            failure_reason="session_invalid",
        )

    current_status = str(session.status or "").strip().lower()
    if current_status in LINK_FLOW_INACTIVE_STATUSES:
        register_link_flow_event_once(
            db,
            session=session,
            event_name="session_invalid",
            payload={"source": "whatsapp_inbound", "reason": current_status or "inactive"},
        )
        return LinkFlowInboundResolution(
            token_found=True,
            session=session,
            sanitized_text=sanitized_text,
            failure_reason="session_invalid",
        )

    if session.expires_at <= _now():
        if current_status != "expired":
            session.status = "expired"
            db.add(session)
        register_link_flow_event_once(
            db,
            session=session,
            event_name="session_expired",
            payload={"source": "whatsapp_inbound"},
        )
        return LinkFlowInboundResolution(
            token_found=True,
            session=session,
            sanitized_text=sanitized_text,
            failure_reason="session_expired",
        )

    if current_status and current_status not in LINK_FLOW_ACTIVE_STATUSES:
        register_link_flow_event_once(
            db,
            session=session,
            event_name="session_invalid",
            payload={"source": "whatsapp_inbound", "reason": current_status},
        )
        return LinkFlowInboundResolution(
            token_found=True,
            session=session,
            sanitized_text=sanitized_text,
            failure_reason="session_invalid",
        )

    return LinkFlowInboundResolution(token_found=True, session=session, sanitized_text=sanitized_text)


def link_session_to_conversation(
    db: Session,
    *,
    session: LinkFlowSession,
    conversation: Conversation | None,
    patient_id: UUID | None,
    lead_id: UUID | None,
) -> None:
    now = _now()
    if conversation:
        tags = list(conversation.tags or [])
        if "entry_link_flow" not in tags:
            conversation.tags = sorted([*tags, "entry_link_flow"])
        db.add(conversation)
        session.linked_conversation_id = conversation.id
    if patient_id and not session.linked_patient_id:
        session.linked_patient_id = patient_id
    if lead_id and not session.linked_lead_id:
        session.linked_lead_id = lead_id
    if not session.linked_at:
        session.linked_at = now
        session.status = "linked"
        register_link_flow_event(db, session=session, event_name="conversation_started", payload={"source": "whatsapp_inbound"})
    db.add(session)

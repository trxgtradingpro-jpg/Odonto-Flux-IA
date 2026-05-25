from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.db.session import get_db
from app.models import LinkFlowSession, Setting, Tenant, Unit, WhatsAppAccount
from app.services.link_flow_service import (
    build_whatsapp_url,
    capture_public_contact_phone,
    create_link_flow_session,
    get_intake_config,
    get_system_whatsapp_account,
    is_link_flow_enabled,
    public_contact_phone_state,
    register_link_flow_event,
)
from app.services.webchat_service import (
    confirm_public_webchat_booking_summary,
    create_webchat_link_flow_session,
    list_public_webchat_messages,
    post_public_webchat_message,
    public_webchat_booking_summary,
    public_webchat_session_state,
    send_public_webchat_summary_followup,
    update_public_webchat_booking_summary,
    validate_public_webchat_session,
)
from app.services.whatsapp_service import whatsapp_account_issues
from app.utils.phone import normalize_phone

router = APIRouter(prefix="/public/booking", tags=["public_booking"])


class PublicBookingSessionInput(BaseModel):
    browser_session_id: str | None = Field(default=None, max_length=120)
    utm_payload: dict[str, str] | None = None
    unit_id: UUID | None = None
    cta_mode: Literal["whatsapp_redirect", "webchat"] | None = None


class PublicBookingEventInput(BaseModel):
    event_name: str = Field(max_length=80)
    page_path: str | None = Field(default=None, max_length=255)
    payload: dict | None = None


class PublicWebchatMessageInput(BaseModel):
    text: str = Field(max_length=1200)
    client_message_id: str | None = Field(default=None, max_length=120)


class PublicWebchatSummaryUpdateInput(BaseModel):
    full_name: str | None = Field(default=None, max_length=180)
    email: str | None = Field(default=None, max_length=180)
    birth_date: str | None = Field(default=None, max_length=10)
    procedure_type: str | None = Field(default=None, max_length=120)
    unit_id: UUID | None = None
    preferred_date: str | None = Field(default=None, max_length=10)
    preferred_time: str | None = Field(default=None, max_length=80)
    dispatch_followup: bool = False


class PublicBookingContactInput(BaseModel):
    phone: str = Field(min_length=8, max_length=30)


def _client_ip(request: Request) -> str | None:
    forwarded = str(request.headers.get("x-forwarded-for") or "").strip()
    if forwarded:
        return forwarded.split(",", 1)[0].strip()[:100] or None
    return request.client.host if request.client else None


def _public_access_token(request: Request) -> str | None:
    authorization = str(request.headers.get("authorization") or "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return str(request.headers.get("x-link-flow-token") or "").strip() or None


def _public_settings(db: Session, *, tenant_id) -> dict[str, object]:
    rows = db.execute(
        select(Setting).where(
            Setting.tenant_id == tenant_id,
            Setting.key.in_(["branding.theme", "branding.logo_data_url", "clinic.profile", "privacy.contact"]),
        )
    ).scalars().all()
    return {row.key: row.value for row in rows}


def _read_string(value: object) -> str | None:
    return str(value).strip() if isinstance(value, str) and value.strip() else None


def _clinic_name(tenant: Tenant, settings_map: dict[str, object]) -> str:
    profile = settings_map.get("clinic.profile")
    if isinstance(profile, dict):
        for key in ("clinic_name", "display_name", "trade_name", "name"):
            value = _read_string(profile.get(key))
            if value:
                return value
    return tenant.trade_name or tenant.legal_name


def _shared_sender_operational(db: Session) -> bool:
    account = get_system_whatsapp_account(db)
    if not account:
        return False
    phone = normalize_phone(account.display_phone or account.phone_number_id)
    if not phone:
        return False
    return not whatsapp_account_issues(
        provider_name=account.provider_name,
        phone_number_id=account.phone_number_id,
        business_account_id=account.business_account_id,
        access_token=account.access_token_encrypted,
    )


def _public_contact_channels(
    db: Session,
    *,
    tenant: Tenant,
    clinic_name: str,
    settings_map: dict[str, object] | None = None,
) -> dict[str, str | None]:
    tenant_account = db.scalar(
        select(WhatsAppAccount).where(
            WhatsAppAccount.tenant_id == tenant.id,
            WhatsAppAccount.is_active.is_(True),
        )
        .order_by(WhatsAppAccount.created_at.desc())
        .limit(1)
    )
    account = tenant_account or get_system_whatsapp_account(db)
    phone = normalize_phone(account.display_phone or account.phone_number_id) if account else None
    if not phone and isinstance(settings_map, dict):
        clinic_profile = settings_map.get("clinic.profile")
        if isinstance(clinic_profile, dict):
            phone = normalize_phone(
                _read_string(clinic_profile.get("whatsapp_phone"))
                or _read_string(clinic_profile.get("main_phone"))
                or _read_string(clinic_profile.get("phone"))
            )
    if not phone and isinstance(settings_map, dict):
        privacy_contact = settings_map.get("privacy.contact")
        if isinstance(privacy_contact, dict):
            phone = normalize_phone(_read_string(privacy_contact.get("phone")))
    if not phone:
        return {"phone": None, "whatsapp_url": None}
    return {
        "phone": phone,
        "whatsapp_url": build_whatsapp_url(phone=phone, raw_token=None, clinic_name=clinic_name),
    }


def _booking_payload(db: Session, *, tenant: Tenant) -> dict:
    config = get_intake_config(db, tenant_id=tenant.id)
    link_flow_enabled = is_link_flow_enabled(config)
    cta_mode = str((config.get("link_flow") or {}).get("cta_mode") or "whatsapp_redirect")
    shared_sender_ready = _shared_sender_operational(db) if link_flow_enabled and cta_mode == "whatsapp_redirect" else False
    webchat_ready = link_flow_enabled and cta_mode == "webchat"
    operational = link_flow_enabled and (webchat_ready or shared_sender_ready)

    settings_map = _public_settings(db, tenant_id=tenant.id)
    theme = settings_map.get("branding.theme")
    theme_payload = theme if isinstance(theme, dict) else {}
    logo_data_url = _read_string(settings_map.get("branding.logo_data_url")) or _read_string(theme_payload.get("logo_data_url"))
    link_flow = config["link_flow"]

    clinic_name = _clinic_name(tenant, settings_map)
    contact_channels = _public_contact_channels(db, tenant=tenant, clinic_name=clinic_name, settings_map=settings_map)

    return {
        "clinic": {
            "slug": tenant.slug,
            "name": clinic_name,
            "logo_data_url": logo_data_url,
            "contact_phone": contact_channels["phone"],
            "contact_whatsapp_url": contact_channels["whatsapp_url"],
        },
        "branding": {
            "primary_color": theme_payload.get("primary_color") or "#0f766e",
            "secondary_color": theme_payload.get("secondary_color") or "#0ea5a4",
            "accent_color": theme_payload.get("accent_color") or "#f59e0b",
            "background_color": theme_payload.get("background_color") or "#f2f4f7",
            "card_color": theme_payload.get("card_color") or "#ffffff",
            "text_color": theme_payload.get("text_color") or "#1c1917",
            "muted_text_color": theme_payload.get("muted_text_color") or "#475569",
            "border_color": theme_payload.get("border_color") or "#d6d3d1",
        },
        "link_flow": {
            "enabled": link_flow_enabled,
            "operational": operational,
            "cta_mode": cta_mode,
            "headline": link_flow["headline"],
            "trust_message": link_flow["trust_message"],
            "button_label": link_flow["button_label"],
            "unavailable_message": (
                None
                if operational
                else "Agendamento por link indisponivel no momento. Entre em contato com a clinica pelo canal oficial."
            ),
        },
    }


def _active_tenant_by_slug(db: Session, clinic_slug: str) -> Tenant:
    tenant = db.scalar(
        select(Tenant).where(
            Tenant.slug == clinic_slug,
            Tenant.is_active.is_(True),
        )
    )
    if not tenant:
        raise ApiError(
            status_code=404,
            code="PUBLIC_BOOKING_NOT_FOUND",
            message="Agendamento publico nao encontrado.",
        )
    return tenant


def _validated_public_unit_id(db: Session, *, tenant: Tenant, unit_id: UUID | None) -> UUID | None:
    if not unit_id:
        return None
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
            code="PUBLIC_BOOKING_UNIT_NOT_FOUND",
            message="Unidade de agendamento nao encontrada.",
        )
    return unit.id


@router.get("/{clinic_slug}")
def get_public_booking(clinic_slug: str, db: Session = Depends(get_db)):
    tenant = _active_tenant_by_slug(db, clinic_slug)
    return _booking_payload(db, tenant=tenant)


@router.post("/{clinic_slug}/sessions")
def create_public_booking_session(
    clinic_slug: str,
    payload: PublicBookingSessionInput,
    request: Request,
    db: Session = Depends(get_db),
):
    tenant = _active_tenant_by_slug(db, clinic_slug)
    config = get_intake_config(db, tenant_id=tenant.id)
    if not is_link_flow_enabled(config):
        raise ApiError(
            status_code=404,
            code="PUBLIC_BOOKING_NOT_AVAILABLE",
            message="Agendamento por link indisponivel para esta clinica.",
        )
    link_flow = config.get("link_flow") if isinstance(config.get("link_flow"), dict) else {}
    configured_cta_mode = str(link_flow.get("cta_mode") or "whatsapp_redirect")
    requested_cta_mode = str(payload.cta_mode or configured_cta_mode).strip()
    if requested_cta_mode != configured_cta_mode:
        raise ApiError(
            status_code=409,
            code="PUBLIC_BOOKING_CTA_MODE_MISMATCH",
            message="Modo de atendimento publico indisponivel para esta clinica.",
        )
    settings_map = _public_settings(db, tenant_id=tenant.id)
    unit_id = _validated_public_unit_id(db, tenant=tenant, unit_id=payload.unit_id)
    if configured_cta_mode == "webchat":
        clinic_name = _clinic_name(tenant, settings_map)
        contact_channels = _public_contact_channels(db, tenant=tenant, clinic_name=clinic_name, settings_map=settings_map)
        bundle = create_webchat_link_flow_session(
            db,
            tenant=tenant,
            config=config,
            landing_path=f"/agendar/{clinic_slug}",
            browser_session_id=payload.browser_session_id,
            utm_payload=payload.utm_payload,
            unit_id=unit_id,
        )
        session = bundle.session
        db.commit()
        db.refresh(session)
        return {
            "session_id": str(session.id),
            "expires_at": session.expires_at.isoformat(),
            "cta_mode": "webchat",
            "whatsapp_url": None,
            "public_access_token": bundle.public_access_token,
            **public_contact_phone_state(db, session=session),
            "clinic": {
                "slug": tenant.slug,
                "name": clinic_name,
                "contact_phone": contact_channels["phone"],
                "contact_whatsapp_url": contact_channels["whatsapp_url"],
            },
        }

    if not _shared_sender_operational(db):
        raise ApiError(
            status_code=503,
            code="LINK_FLOW_SYSTEM_WHATSAPP_UNAVAILABLE",
            message="Agendamento por link indisponivel no momento.",
        )
    session, _raw_token, whatsapp_url = create_link_flow_session(
        db,
        tenant=tenant,
        config=config,
        landing_path=f"/agendar/{clinic_slug}",
        browser_session_id=payload.browser_session_id,
        utm_payload=payload.utm_payload,
        unit_id=unit_id,
    )
    db.commit()
    db.refresh(session)
    clinic_name = _clinic_name(tenant, settings_map)
    contact_channels = _public_contact_channels(db, tenant=tenant, clinic_name=clinic_name, settings_map=settings_map)
    return {
        "session_id": str(session.id),
        "expires_at": session.expires_at.isoformat(),
        "cta_mode": "whatsapp_redirect",
        "whatsapp_url": whatsapp_url,
        "public_access_token": None,
        **public_contact_phone_state(db, session=session),
        "clinic": {
            "slug": tenant.slug,
            "name": clinic_name,
            "contact_phone": contact_channels["phone"],
            "contact_whatsapp_url": contact_channels["whatsapp_url"] or whatsapp_url,
        },
    }


@router.post("/sessions/{session_id}/events")
def create_public_booking_event(
    session_id: UUID,
    payload: PublicBookingEventInput,
    request: Request,
    db: Session = Depends(get_db),
):
    if payload.event_name not in {
        "landing_viewed",
        "cta_whatsapp_clicked",
        "webchat_opened",
        "webchat_session_resumed",
        "webchat_session_closed",
        "webchat_error",
    }:
        raise ApiError(
            status_code=422,
            code="LINK_FLOW_PUBLIC_EVENT_INVALID",
            message="Evento publico do link flow invalido.",
        )

    session = db.get(LinkFlowSession, session_id)
    if not session:
        raise ApiError(
            status_code=404,
            code="LINK_FLOW_SESSION_NOT_FOUND",
            message="Sessao do agendamento por link nao encontrada.",
        )
    if session.cta_mode == "webchat":
        session, _tenant = validate_public_webchat_session(
            db,
            session_id=session_id,
            public_access_token=_public_access_token(request),
        )
    if session.expires_at <= datetime.now(UTC):
        raise ApiError(
            status_code=409,
            code="LINK_FLOW_SESSION_EXPIRED",
            message="Sessao do agendamento por link expirada.",
        )
    event = register_link_flow_event(
        db,
        session=session,
        event_name=payload.event_name,
        page_path=payload.page_path,
        payload=payload.payload if isinstance(payload.payload, dict) else {},
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(event)
    return {"id": str(event.id), "event_name": event.event_name}


@router.get("/sessions/{session_id}")
def get_public_booking_session(
    session_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    session, _tenant = validate_public_webchat_session(
        db,
        session_id=session_id,
        public_access_token=_public_access_token(request),
    )
    return {
        **public_webchat_session_state(session),
        **public_contact_phone_state(db, session=session),
    }


@router.post("/sessions/{session_id}/contact")
def capture_public_booking_contact(
    session_id: UUID,
    payload: PublicBookingContactInput,
    request: Request,
    db: Session = Depends(get_db),
):
    session = db.get(LinkFlowSession, session_id)
    if not session:
        raise ApiError(
            status_code=404,
            code="LINK_FLOW_SESSION_NOT_FOUND",
            message="Sessao do agendamento por link nao encontrada.",
        )

    if session.cta_mode == "webchat":
        session, _tenant = validate_public_webchat_session(
            db,
            session_id=session_id,
            public_access_token=_public_access_token(request),
        )
    else:
        tenant = db.get(Tenant, session.tenant_id)
        if not tenant or not tenant.is_active:
            raise ApiError(
                status_code=409,
                code="PUBLIC_BOOKING_NOT_AVAILABLE",
                message="Atendimento indisponivel. Abra novamente o link oficial da clinica para continuar.",
            )
        if session.expires_at <= datetime.now(UTC):
            raise ApiError(
                status_code=409,
                code="LINK_FLOW_SESSION_EXPIRED",
                message="Sessao do agendamento por link expirada.",
            )

    response = capture_public_contact_phone(
        db,
        session=session,
        raw_phone=payload.phone,
    )
    db.commit()
    db.refresh(session)
    return {
        "session_id": str(session.id),
        **response,
    }


@router.get("/sessions/{session_id}/summary")
def get_public_webchat_summary(
    session_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    session, tenant = validate_public_webchat_session(
        db,
        session_id=session_id,
        public_access_token=_public_access_token(request),
    )
    return public_webchat_booking_summary(db, session=session, tenant=tenant)


@router.patch("/sessions/{session_id}/summary")
def patch_public_webchat_summary(
    session_id: UUID,
    payload: PublicWebchatSummaryUpdateInput,
    request: Request,
    db: Session = Depends(get_db),
):
    session, tenant = validate_public_webchat_session(
        db,
        session_id=session_id,
        public_access_token=_public_access_token(request),
    )
    return update_public_webchat_booking_summary(
        db,
        session=session,
        tenant=tenant,
        full_name=payload.full_name,
        email=payload.email,
        birth_date_value=payload.birth_date,
        procedure_type=payload.procedure_type,
        unit_id=payload.unit_id,
        preferred_date=payload.preferred_date,
        preferred_time=payload.preferred_time,
        dispatch_followup=payload.dispatch_followup,
    )


@router.post("/sessions/{session_id}/summary/followup")
def create_public_webchat_summary_followup(
    session_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    session, tenant = validate_public_webchat_session(
        db,
        session_id=session_id,
        public_access_token=_public_access_token(request),
    )
    return send_public_webchat_summary_followup(
        db,
        session=session,
        tenant=tenant,
    )


@router.post("/sessions/{session_id}/summary/confirm")
def confirm_public_webchat_summary(
    session_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    session, tenant = validate_public_webchat_session(
        db,
        session_id=session_id,
        public_access_token=_public_access_token(request),
    )
    return confirm_public_webchat_booking_summary(
        db,
        session=session,
        tenant=tenant,
    )


@router.post("/sessions/{session_id}/chat/messages")
def create_public_webchat_message(
    session_id: UUID,
    payload: PublicWebchatMessageInput,
    request: Request,
    db: Session = Depends(get_db),
):
    session, tenant = validate_public_webchat_session(
        db,
        session_id=session_id,
        public_access_token=_public_access_token(request),
    )
    return post_public_webchat_message(
        db,
        session=session,
        tenant=tenant,
        text=payload.text,
        client_message_id=payload.client_message_id,
        ip_address=_client_ip(request),
    )


@router.get("/sessions/{session_id}/chat/messages")
def list_public_webchat_chat_messages(
    session_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    after_message_id: UUID | None = None,
    limit: int = 50,
):
    session, _tenant = validate_public_webchat_session(
        db,
        session_id=session_id,
        public_access_token=_public_access_token(request),
    )
    messages = list_public_webchat_messages(
        db,
        session=session,
        after_message_id=after_message_id,
        limit=limit,
    )
    return {"data": messages, "meta": {"limit": max(1, min(limit, 100))}}

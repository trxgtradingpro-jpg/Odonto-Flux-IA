from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_principal
from app.core.config import settings
from app.core.exceptions import ApiError
from app.core.security import TokenError, decode_token
from app.db.session import get_db
from app.models import (
    Conversation,
    DemoActivityEvent,
    Lead,
    Message,
    Patient,
    ProspectAccount,
    ProspectNote,
    ProspectService,
    ProspectTimelineEvent,
    ProspectUnit,
)
from app.schemas.admin_sales import (
    AdminChangeInitialPasswordInput,
    AdminLoginInput,
    AdminLoginOutput,
    DemoAccessOutput,
    DemoActivityOutput,
    DemoEventInput,
    DemoGuideBackStepInput,
    DemoGuideCompleteStepInput,
    DemoGuideDismissInput,
    DemoGuideResumeInput,
    DemoGuideStateOutput,
    DemoProvisionOutput,
    DemoRedeemTokenInput,
    MagicLinkInput,
    ProspectContactInput,
    ProspectCreate,
    ProspectInsightsOutput,
    ProspectListOutput,
    ProspectNoteInput,
    ProspectNoteOutput,
    ProspectOutput,
    ProspectOutreachInput,
    ProspectOutreachLabInput,
    ProspectOutreachLabOutput,
    ProspectOutreachOutput,
    ProspectOverviewOutput,
    ProspectServiceInput,
    ProspectServiceOutput,
    ProspectStatusInput,
    ProspectTimelineEventOutput,
    ProspectUnitInput,
    ProspectUnitOutput,
    ProspectUpdate,
    SalesClinicMessageEventInput,
    SalesClinicMessageEventOutput,
    SalesClinicMessageListOutput,
    SalesClinicMessagePreviewInput,
    SalesClinicMessagePreviewOutput,
    SalesMessageTemplateInput,
    SalesMessageTemplateOutput,
)
from app.services import sales_demo_service as sales
from app.services import sales_message_service as sales_messages

router = APIRouter(tags=["admin_sales"])

_login_attempts: dict[str, list[datetime]] = {}


def _client_key(request: Request, email: str) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded or (request.client.host if request.client else "unknown")
    return f"{ip}:{email.lower().strip()}"


def _rate_limit_login(request: Request, email: str) -> None:
    key = _client_key(request, email)
    now = datetime.now(UTC)
    attempts = [item for item in _login_attempts.get(key, []) if item > now - timedelta(minutes=1)]
    if len(attempts) >= settings.adm_login_rate_limit_per_minute:
        raise ApiError(status_code=429, code="ADM_LOGIN_RATE_LIMIT", message="Muitas tentativas. Tente novamente em instantes.")
    attempts.append(now)
    _login_attempts[key] = attempts


def _base_url(request: Request) -> str:
    return request.headers.get("origin") or "http://localhost:3000"


def _get_prospect(db: Session, prospect_id: UUID) -> ProspectAccount:
    prospect = db.get(ProspectAccount, prospect_id)
    if not prospect:
        raise ApiError(status_code=404, code="PROSPECT_NOT_FOUND", message="Prospect nao encontrado")
    return prospect


def _current_principal_optional(request: Request, db: Session):
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        return None
    try:
        payload = decode_token(header.split(" ", 1)[1])
    except TokenError:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    from app.api.deps import _load_principal

    return _load_principal(db, user_id)


def _require_demo_prospect(principal, db: Session) -> ProspectAccount:
    if "demo_client" not in set(principal.roles):
        raise ApiError(status_code=403, code="DEMO_GUIDE_FORBIDDEN", message="Guia disponivel apenas para usuarios de demo")
    if not principal.tenant_id:
        raise ApiError(status_code=403, code="DEMO_GUIDE_FORBIDDEN", message="Contexto de tenant ausente para a demo")
    prospect = db.scalar(select(ProspectAccount).where(ProspectAccount.demo_tenant_id == principal.tenant_id))
    if not prospect:
        raise ApiError(status_code=404, code="DEMO_PROSPECT_NOT_FOUND", message="Demo vinculada nao encontrada")
    return prospect


def _prospect_id_from_tags(tags: list[str] | None) -> UUID | None:
    for tag in tags or []:
        value = str(tag or "").strip()
        if not value.startswith("prospect_id:"):
            continue
        try:
            return UUID(value.split(":", 1)[1].strip())
        except ValueError:
            return None
    return None


def _conversation_contact(db: Session, conversation: Conversation) -> dict[str, str | None]:
    patient = db.get(Patient, conversation.patient_id) if conversation.patient_id else None
    if patient:
        return {
            "name": patient.full_name,
            "phone": patient.phone,
        }
    lead = db.get(Lead, conversation.lead_id) if conversation.lead_id else None
    if lead:
        return {
            "name": lead.name,
            "phone": lead.phone,
        }
    return {
        "name": None,
        "phone": None,
    }


def _serialize_admin_whatsapp_conversation(
    db: Session,
    *,
    prospect: ProspectAccount,
    conversation: Conversation,
    source: str,
) -> dict:
    contact = _conversation_contact(db, conversation)
    latest_message = db.scalar(
        select(Message)
        .where(Message.tenant_id == conversation.tenant_id, Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    message_count = db.scalar(
        select(func.count())
        .select_from(Message)
        .where(Message.tenant_id == conversation.tenant_id, Message.conversation_id == conversation.id)
    ) or 0
    simulated_count = db.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.tenant_id == conversation.tenant_id,
            Message.conversation_id == conversation.id,
            Message.payload["simulated_patient"].astext == "true",
        )
    ) or 0
    return {
        "id": str(conversation.id),
        "source": source,
        "prospect_id": str(prospect.id),
        "prospect_name": prospect.clinic_name,
        "demo_tenant_id": str(prospect.demo_tenant_id) if prospect.demo_tenant_id else None,
        "contact_name": contact["name"] or prospect.owner_name or prospect.manager_name or prospect.clinic_name,
        "contact_phone": contact["phone"] or prospect.whatsapp_phone or prospect.phone,
        "patient_id": str(conversation.patient_id) if conversation.patient_id else None,
        "lead_id": str(conversation.lead_id) if conversation.lead_id else None,
        "channel": conversation.channel,
        "status": conversation.status,
        "tags": conversation.tags or [],
        "ai_summary": conversation.ai_summary,
        "ai_autoresponder_enabled": conversation.ai_autoresponder_enabled,
        "last_message_at": conversation.last_message_at,
        "last_message_preview": latest_message.body if latest_message else None,
        "last_message_direction": latest_message.direction if latest_message else None,
        "message_count": message_count,
        "simulated_patient_messages": simulated_count,
        "created_at": conversation.created_at,
    }


def _resolve_admin_whatsapp_conversation(db: Session, conversation_id: UUID) -> tuple[ProspectAccount, Conversation, str]:
    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        raise ApiError(status_code=404, code="ADM_WHATSAPP_CONVERSATION_NOT_FOUND", message="Conversa nao encontrada no /adm")

    prospect = db.scalar(select(ProspectAccount).where(ProspectAccount.demo_tenant_id == conversation.tenant_id))
    if prospect:
        return prospect, conversation, "demo"

    sender_tenant = sales.ensure_sales_outreach_sender_tenant(db)
    if conversation.tenant_id == sender_tenant.id:
        prospect_id = _prospect_id_from_tags(conversation.tags)
        if prospect_id:
            prospect = db.get(ProspectAccount, prospect_id)
            if prospect:
                return prospect, conversation, "comercial"

    raise ApiError(status_code=404, code="ADM_WHATSAPP_CONVERSATION_NOT_FOUND", message="Conversa nao vinculada a um prospect do /adm")


@router.post("/admin/auth/login", response_model=AdminLoginOutput)
def admin_login(payload: AdminLoginInput, request: Request, db: Session = Depends(get_db)):
    _rate_limit_login(request, payload.email)
    return sales.admin_login(db, email=payload.email, password=payload.password)


@router.post("/admin/auth/logout")
def admin_logout():
    return {"message": "Sessao encerrada no cliente."}


@router.post("/admin/auth/change-initial-password")
def change_initial_password(
    payload: AdminChangeInitialPasswordInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.change_initial_admin_password(
        db,
        user=principal.user,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    return {"message": "Senha atualizada com sucesso."}


@router.get("/admin/whatsapp/conversations")
def list_admin_whatsapp_conversations(
    prospect_id: UUID | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_sales_principal(principal)
    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    prospect_stmt = select(ProspectAccount)
    if prospect_id:
        prospect_stmt = prospect_stmt.where(ProspectAccount.id == prospect_id)
    prospects = db.execute(prospect_stmt).scalars().all()
    prospect_by_id = {item.id: item for item in prospects}
    prospect_by_demo_tenant = {item.demo_tenant_id: item for item in prospects if item.demo_tenant_id}

    items: list[dict] = []
    if prospect_by_demo_tenant:
        demo_conversations = db.execute(
            select(Conversation)
            .where(
                Conversation.tenant_id.in_(tuple(prospect_by_demo_tenant.keys())),
                Conversation.channel == "whatsapp",
            )
            .order_by(Conversation.last_message_at.desc().nullslast(), Conversation.created_at.desc())
        ).scalars().all()
        for conversation in demo_conversations:
            prospect = prospect_by_demo_tenant.get(conversation.tenant_id)
            if prospect:
                items.append(_serialize_admin_whatsapp_conversation(db, prospect=prospect, conversation=conversation, source="demo"))

    sender_tenant = sales.ensure_sales_outreach_sender_tenant(db)
    outreach_conversations = db.execute(
        select(Conversation)
        .where(
            Conversation.tenant_id == sender_tenant.id,
            Conversation.channel == "whatsapp",
        )
        .order_by(Conversation.last_message_at.desc().nullslast(), Conversation.created_at.desc())
    ).scalars().all()
    for conversation in outreach_conversations:
        linked_prospect_id = _prospect_id_from_tags(conversation.tags)
        if not linked_prospect_id:
            continue
        prospect = prospect_by_id.get(linked_prospect_id)
        if prospect:
            items.append(_serialize_admin_whatsapp_conversation(db, prospect=prospect, conversation=conversation, source="comercial"))

    if q:
        term = q.lower().strip()
        items = [
            item
            for item in items
            if term
            in " ".join(
                str(value or "")
                for value in [
                    item.get("prospect_name"),
                    item.get("contact_name"),
                    item.get("contact_phone"),
                    item.get("last_message_preview"),
                    item.get("ai_summary"),
                ]
            ).lower()
        ]

    items.sort(key=lambda item: item.get("last_message_at") or item.get("created_at") or datetime.min.replace(tzinfo=UTC), reverse=True)
    total = len(items)
    return {
        "data": items[offset : offset + limit],
        "meta": {"total": total, "limit": limit, "offset": offset},
    }


@router.get("/admin/whatsapp/conversations/{conversation_id}/messages")
def list_admin_whatsapp_messages(
    conversation_id: UUID,
    limit: int = 200,
    offset: int = 0,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_sales_principal(principal)
    _prospect, conversation, source = _resolve_admin_whatsapp_conversation(db, conversation_id)
    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    stmt = select(Message).where(
        Message.tenant_id == conversation.tenant_id,
        Message.conversation_id == conversation.id,
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        reversed(
            db.execute(stmt.order_by(Message.created_at.desc()).offset(offset).limit(limit)).scalars().all()
        )
    )
    return {
        "data": [
            {
                "id": str(message.id),
                "tenant_id": str(message.tenant_id),
                "conversation_id": str(message.conversation_id),
                "direction": message.direction,
                "provider_message_id": message.provider_message_id,
                "status": message.status,
                "body": message.body,
                "message_type": message.message_type,
                "sender_type": message.sender_type,
                "payload": message.payload or {},
                "sent_at": message.sent_at,
                "delivered_at": message.delivered_at,
                "read_at": message.read_at,
                "created_at": message.created_at,
            }
            for message in rows
        ],
        "conversation": _serialize_admin_whatsapp_conversation(db, prospect=_prospect, conversation=conversation, source=source),
        "meta": {"total": total, "limit": limit, "offset": offset},
    }


@router.get("/admin/prospects/overview", response_model=ProspectOverviewOutput)
def prospects_overview(principal=Depends(get_current_principal), db: Session = Depends(get_db)):
    sales.require_sales_principal(principal)
    return sales.overview(db)


@router.get("/admin/prospects", response_model=ProspectListOutput)
def list_prospects(
    status: str | None = None,
    temperature: str | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_sales_principal(principal)
    query = select(ProspectAccount)
    count_query = select(func.count(ProspectAccount.id))
    filters = []
    if status:
        filters.append(ProspectAccount.status == status)
    if temperature:
        filters.append(ProspectAccount.temperature == temperature)
    if q:
        term = f"%{q.lower()}%"
        filters.append(
            func.lower(
                func.concat(
                    ProspectAccount.clinic_name,
                    " ",
                    func.coalesce(ProspectAccount.city, ""),
                    " ",
                    func.coalesce(ProspectAccount.whatsapp_phone, ""),
                    " ",
                    func.coalesce(ProspectAccount.phone, ""),
                )
            ).like(term)
        )
    for item in filters:
        query = query.where(item)
        count_query = count_query.where(item)
    rows = db.execute(query.order_by(ProspectAccount.updated_at.desc()).limit(limit).offset(offset)).scalars().all()
    total = db.scalar(count_query) or 0
    return {
        "data": [sales.serialize_prospect(db, row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/admin/clinic-messages/templates", response_model=list[SalesMessageTemplateOutput])
def list_clinic_message_templates(
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_sales_principal(principal)
    return sales_messages.list_sales_message_templates(db)


@router.post("/admin/clinic-messages/templates", response_model=SalesMessageTemplateOutput)
def create_clinic_message_template(
    payload: SalesMessageTemplateInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_sales_write(principal)
    return sales_messages.create_sales_message_template(db, payload.model_dump())


@router.put("/admin/clinic-messages/templates/{template_key}", response_model=SalesMessageTemplateOutput)
def update_clinic_message_template(
    template_key: str,
    payload: SalesMessageTemplateInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_sales_write(principal)
    return sales_messages.update_sales_message_template(db, template_key, payload.model_dump())


@router.delete("/admin/clinic-messages/templates/{template_key}", response_model=list[SalesMessageTemplateOutput])
def delete_clinic_message_template(
    template_key: str,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_sales_write(principal)
    return sales_messages.delete_sales_message_template(db, template_key)


@router.get("/admin/clinic-messages", response_model=SalesClinicMessageListOutput)
def list_clinic_messages(
    status: str | None = None,
    temperature: str | None = None,
    demo_status: str | None = None,
    has_demo: bool | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_sales_principal(principal)
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    query = select(ProspectAccount)
    count_query = select(func.count(ProspectAccount.id))
    filters = []
    if status:
        filters.append(ProspectAccount.status == status)
    if temperature:
        filters.append(ProspectAccount.temperature == temperature)
    if demo_status:
        filters.append(ProspectAccount.demo_status == demo_status)
    if has_demo is True:
        filters.append(ProspectAccount.demo_tenant_id.is_not(None))
    elif has_demo is False:
        filters.append(ProspectAccount.demo_tenant_id.is_(None))
    if q:
        term = f"%{q.lower()}%"
        filters.append(
            func.lower(
                func.concat(
                    ProspectAccount.clinic_name,
                    " ",
                    func.coalesce(ProspectAccount.city, ""),
                    " ",
                    func.coalesce(ProspectAccount.whatsapp_phone, ""),
                    " ",
                    func.coalesce(ProspectAccount.phone, ""),
                    " ",
                    func.coalesce(ProspectAccount.owner_name, ""),
                    " ",
                    func.coalesce(ProspectAccount.manager_name, ""),
                )
            ).like(term)
        )
    for item in filters:
        query = query.where(item)
        count_query = count_query.where(item)
    rows = db.execute(
        query.order_by(ProspectAccount.updated_at.desc()).limit(limit).offset(offset)
    ).scalars().all()
    total = db.scalar(count_query) or 0
    return {
        "data": [sales_messages.serialize_sales_message_item(db, row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "templates": sales_messages.list_sales_message_templates(db),
    }


@router.post("/admin/clinic-messages/preview", response_model=SalesClinicMessagePreviewOutput)
def preview_clinic_message(
    payload: SalesClinicMessagePreviewInput,
    request: Request,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_sales_write(principal)
    prospect = _get_prospect(db, payload.prospect_id)
    return sales_messages.build_sales_message_preview(
        db,
        prospect=prospect,
        template_key=payload.template_key,
        message_key=payload.message_key,
        actor_id=principal.user.id,
        base_url=_base_url(request),
        issue_demo_access=payload.issue_demo_access,
    )


@router.post(
    "/admin/clinic-messages/{prospect_id}/events",
    response_model=SalesClinicMessageEventOutput,
)
def record_clinic_message_event(
    prospect_id: UUID,
    payload: SalesClinicMessageEventInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_sales_write(principal)
    prospect = _get_prospect(db, prospect_id)
    event = sales_messages.record_sales_message_event(
        db,
        prospect=prospect,
        event_name=payload.event_name,
        actor_id=principal.user.id,
        template_key=payload.template_key,
        message_key=payload.message_key,
        message_snapshot=payload.message_snapshot,
        demo_login_url=payload.demo_login_url,
        channel=payload.channel,
        note=payload.note,
    )
    return {
        "prospect": sales.serialize_prospect(db, prospect),
        "event": {
            "id": event.id,
            "event_type": event.event_type,
            "event_label": event.event_label,
            "actor_type": event.actor_type,
            "actor_id": event.actor_id,
            "payload": event.payload_json or {},
            "created_at": event.created_at,
        },
    }


@router.post("/admin/prospects", response_model=ProspectOutput)
def create_prospect(payload: ProspectCreate, principal=Depends(get_current_principal), db: Session = Depends(get_db)):
    sales.require_sales_write(principal)
    prospect = sales.create_prospect(db, payload, actor_id=principal.user.id)
    return sales.serialize_prospect(db, prospect)


@router.get("/admin/prospects/{prospect_id}", response_model=ProspectOutput)
def get_prospect(prospect_id: UUID, principal=Depends(get_current_principal), db: Session = Depends(get_db)):
    sales.require_sales_principal(principal)
    return sales.serialize_prospect(db, _get_prospect(db, prospect_id))


@router.patch("/admin/prospects/{prospect_id}", response_model=ProspectOutput)
def update_prospect(
    prospect_id: UUID,
    payload: ProspectUpdate,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_sales_write(principal)
    prospect = sales.update_prospect(db, _get_prospect(db, prospect_id), payload, actor_id=principal.user.id)
    return sales.serialize_prospect(db, prospect)


@router.delete("/admin/prospects/{prospect_id}")
def delete_prospect(prospect_id: UUID, principal=Depends(get_current_principal), db: Session = Depends(get_db)):
    sales.require_sales_write(principal)
    prospect = _get_prospect(db, prospect_id)
    if prospect.demo_tenant_id or prospect.demo_user_id:
        sales.cleanup_demo_resources(
            db,
            prospect=prospect,
            reason="deleted",
            actor_id=principal.user.id,
            delete_prospect=True,
        )
    db.delete(prospect)
    db.commit()
    return {"message": "Prospect removido."}


@router.post("/admin/prospects/{prospect_id}/units", response_model=ProspectUnitOutput)
def add_unit(
    prospect_id: UUID,
    payload: ProspectUnitInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_sales_write(principal)
    prospect = _get_prospect(db, prospect_id)
    unit = ProspectUnit(
        prospect_account_id=prospect.id,
        unit_name=payload.unit_name,
        address=payload.address,
        phone=payload.phone,
        email=str(payload.email) if payload.email else None,
        is_primary=payload.is_primary,
    )
    db.add(unit)
    sales.add_timeline(db, prospect, event_type="prospect.unit_added", event_label=f"Unidade adicionada: {payload.unit_name}", actor_id=principal.user.id, actor_type="admin")
    db.commit()
    db.refresh(unit)
    return sales.serialize_unit(unit)


@router.post("/admin/prospects/{prospect_id}/services", response_model=ProspectServiceOutput)
def add_service(
    prospect_id: UUID,
    payload: ProspectServiceInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_sales_write(principal)
    prospect = _get_prospect(db, prospect_id)
    service = ProspectService(
        prospect_account_id=prospect.id,
        service_name=payload.service_name,
        category=payload.category,
        duration_minutes=payload.duration_minutes,
        price_range=payload.price_range,
        description=payload.description,
    )
    db.add(service)
    sales.add_timeline(db, prospect, event_type="prospect.service_added", event_label=f"Servico adicionado: {payload.service_name}", actor_id=principal.user.id, actor_type="admin")
    db.commit()
    db.refresh(service)
    return sales.serialize_service(service)


@router.post("/admin/prospects/{prospect_id}/notes", response_model=ProspectNoteOutput)
def add_note(
    prospect_id: UUID,
    payload: ProspectNoteInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_sales_write(principal)
    prospect = _get_prospect(db, prospect_id)
    note = ProspectNote(
        prospect_account_id=prospect.id,
        author_user_id=principal.user.id,
        body=payload.body,
        note_type=payload.note_type,
    )
    db.add(note)
    sales.add_timeline(db, prospect, event_type="prospect.note_added", event_label="Nota comercial registrada", actor_id=principal.user.id, actor_type="admin")
    db.commit()
    db.refresh(note)
    return {
        "id": note.id,
        "body": note.body,
        "note_type": note.note_type,
        "author_user_id": note.author_user_id,
        "created_at": note.created_at,
    }


@router.get("/admin/prospects/{prospect_id}/timeline", response_model=list[ProspectTimelineEventOutput])
def timeline(prospect_id: UUID, principal=Depends(get_current_principal), db: Session = Depends(get_db)):
    sales.require_sales_principal(principal)
    _get_prospect(db, prospect_id)
    rows = db.execute(
        select(ProspectTimelineEvent)
        .where(ProspectTimelineEvent.prospect_account_id == prospect_id)
        .order_by(ProspectTimelineEvent.created_at.desc())
    ).scalars().all()
    return [
        {
            "id": row.id,
            "event_type": row.event_type,
            "event_label": row.event_label,
            "actor_type": row.actor_type,
            "actor_id": row.actor_id,
            "payload": row.payload_json or {},
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.post("/admin/prospects/{prospect_id}/generate-demo", response_model=DemoProvisionOutput)
def generate_demo(
    prospect_id: UUID,
    request: Request,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_sales_write(principal)
    result = sales.generate_demo(db, _get_prospect(db, prospect_id), actor_id=principal.user.id, base_url=_base_url(request))
    return {
        "prospect": sales.serialize_prospect(db, result["prospect"]),
        "access_token": result["access_token"],
        "demo_login_url": result["demo_login_url"],
        "checklist": result["checklist"],
        "ai_draft": result["ai_draft"],
    }


@router.post("/admin/prospects/{prospect_id}/send-demo-access", response_model=DemoAccessOutput)
def send_demo_access(
    prospect_id: UUID,
    request: Request,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_sales_write(principal)
    prospect = _get_prospect(db, prospect_id)
    raw_token = sales.issue_demo_access(db, prospect, actor_id=principal.user.id)
    return {
        "access_token": raw_token,
        "demo_login_url": f"{_base_url(request)}/login?demo_token={raw_token}",
        "expires_at": prospect.demo_access_token_expires_at,
    }


@router.post("/admin/prospects/{prospect_id}/record-contact", response_model=ProspectOutput)
def record_contact(
    prospect_id: UUID,
    payload: ProspectContactInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_sales_write(principal)
    prospect = _get_prospect(db, prospect_id)
    prospect.first_contact_channel = prospect.first_contact_channel or payload.channel
    prospect.first_contact_at = prospect.first_contact_at or datetime.now(UTC)
    if prospect.status in {"novo", "pesquisado"}:
        prospect.status = "contato_iniciado"
    sales.add_timeline(
        db,
        prospect,
        event_type="contact.recorded",
        event_label=f"Contato registrado via {payload.channel}",
        actor_id=principal.user.id,
        actor_type="admin",
        payload={"summary": payload.summary, "next_step": payload.next_step},
    )
    db.add(prospect)
    db.commit()
    db.refresh(prospect)
    return sales.serialize_prospect(db, prospect)


@router.post("/admin/prospects/{prospect_id}/outreach", response_model=ProspectOutreachOutput)
def send_outreach(
    prospect_id: UUID,
    payload: ProspectOutreachInput,
    request: Request,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_sales_write(principal)
    result = sales.send_sales_outreach_step(
        db,
        prospect=_get_prospect(db, prospect_id),
        step=payload.step,
        actor_id=principal.user.id,
        base_url=_base_url(request),
        recipient_name=payload.recipient_name,
        explicit_video_url=payload.video_url,
    )
    return result


@router.post("/admin/prospects/{prospect_id}/outreach/automation/start", response_model=ProspectOutreachOutput)
def start_outreach_automation(
    prospect_id: UUID,
    request: Request,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_sales_write(principal)
    result = sales.start_sales_outreach_automation(
        db,
        prospect=_get_prospect(db, prospect_id),
        actor_id=principal.user.id,
        base_url=_base_url(request),
    )
    return result


@router.post("/admin/prospects/{prospect_id}/outreach/lab", response_model=ProspectOutreachLabOutput)
def run_outreach_lab(
    prospect_id: UUID,
    payload: ProspectOutreachLabInput,
    request: Request,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_sales_write(principal)
    result = sales.simulate_sales_outreach_lab(
        db,
        prospect=_get_prospect(db, prospect_id),
        actor_id=principal.user.id,
        base_url=_base_url(request),
        scenario=payload.scenario,
    )
    return result


@router.post("/admin/prospects/{prospect_id}/mark-status", response_model=ProspectOutput)
def mark_status(
    prospect_id: UUID,
    payload: ProspectStatusInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_sales_write(principal)
    if payload.status not in sales.PROSPECT_STATUSES:
        raise ApiError(status_code=400, code="PROSPECT_STATUS_INVALID", message="Status comercial invalido")
    prospect = _get_prospect(db, prospect_id)
    old_status = prospect.status
    prospect.status = payload.status
    sales.add_timeline(
        db,
        prospect,
        event_type="prospect.status_changed",
        event_label=f"Status alterado para {payload.status}",
        actor_id=principal.user.id,
        actor_type="admin",
        payload={"from": old_status, "to": payload.status, "note": payload.note},
    )
    db.add(prospect)
    db.commit()
    db.refresh(prospect)
    return sales.serialize_prospect(db, prospect)


@router.post("/admin/prospects/{prospect_id}/score/recalculate", response_model=ProspectOutput)
def recalculate_score(prospect_id: UUID, principal=Depends(get_current_principal), db: Session = Depends(get_db)):
    sales.require_sales_principal(principal)
    prospect = sales.recalculate_score(db, _get_prospect(db, prospect_id))
    return sales.serialize_prospect(db, prospect)


@router.get("/admin/prospects/{prospect_id}/activity", response_model=list[DemoActivityOutput])
def activity(prospect_id: UUID, principal=Depends(get_current_principal), db: Session = Depends(get_db)):
    sales.require_sales_principal(principal)
    _get_prospect(db, prospect_id)
    rows = db.execute(
        select(DemoActivityEvent)
        .where(DemoActivityEvent.prospect_account_id == prospect_id)
        .order_by(DemoActivityEvent.occurred_at.desc())
    ).scalars().all()
    return [
        {
            "id": row.id,
            "event_name": row.event_name,
            "page_path": row.page_path,
            "session_id": row.session_id,
            "payload": row.payload_json or {},
            "occurred_at": row.occurred_at,
        }
        for row in rows
    ]


@router.get("/admin/prospects/{prospect_id}/insights", response_model=ProspectInsightsOutput)
def insights(prospect_id: UUID, principal=Depends(get_current_principal), db: Session = Depends(get_db)):
    sales.require_sales_principal(principal)
    return sales.get_insights(db, _get_prospect(db, prospect_id))


@router.post("/demo/events")
def demo_events(payload: DemoEventInput, request: Request, db: Session = Depends(get_db)):
    principal = _current_principal_optional(request, db)
    prospect = None
    user_id = principal.user.id if principal else None
    if payload.prospect_account_id:
        prospect = _get_prospect(db, payload.prospect_account_id)
    elif principal and principal.tenant_id:
        prospect = db.scalar(select(ProspectAccount).where(ProspectAccount.demo_tenant_id == principal.tenant_id))
    if not prospect:
        raise ApiError(status_code=400, code="DEMO_PROSPECT_REQUIRED", message="Nao foi possivel identificar a demo")
    event = sales.record_demo_event(
        db,
        prospect=prospect,
        user_id=user_id,
        event_name=payload.event_name,
        page_path=payload.page_path,
        session_id=payload.session_id,
        payload=payload.payload,
    )
    return {"id": event.id, "message": "Evento registrado."}


@router.get("/demo/guide", response_model=DemoGuideStateOutput)
def get_demo_guide(principal=Depends(get_current_principal), db: Session = Depends(get_db)):
    prospect = _require_demo_prospect(principal, db)
    sales.ensure_demo_showcase_state(db, prospect=prospect)
    db.commit()
    return sales.get_demo_guide_state(db, tenant_id=prospect.demo_tenant_id)


@router.post("/demo/guide/resume", response_model=DemoGuideStateOutput)
def resume_demo_guide(
    payload: DemoGuideResumeInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    prospect = _require_demo_prospect(principal, db)
    return sales.resume_demo_guide(
        db,
        prospect=prospect,
        user_id=principal.user.id,
        page_path=payload.page_path,
        session_id=payload.session_id,
        source=payload.source,
    )


@router.post("/demo/guide/complete-step", response_model=DemoGuideStateOutput)
def complete_demo_guide_step(
    payload: DemoGuideCompleteStepInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    prospect = _require_demo_prospect(principal, db)
    return sales.complete_demo_guide_step(
        db,
        prospect=prospect,
        user_id=principal.user.id,
        step_id=payload.step_id,
        page_path=payload.page_path,
        session_id=payload.session_id,
        source=payload.source,
    )


@router.post("/demo/guide/back-step", response_model=DemoGuideStateOutput)
def go_back_demo_guide_step(
    payload: DemoGuideBackStepInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    prospect = _require_demo_prospect(principal, db)
    return sales.go_back_demo_guide_step(
        db,
        prospect=prospect,
        user_id=principal.user.id,
        page_path=payload.page_path,
        session_id=payload.session_id,
        source=payload.source,
    )


@router.post("/demo/guide/dismiss", response_model=DemoGuideStateOutput)
def dismiss_demo_guide(
    payload: DemoGuideDismissInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    prospect = _require_demo_prospect(principal, db)
    return sales.dismiss_demo_guide(
        db,
        prospect=prospect,
        user_id=principal.user.id,
        page_path=payload.page_path,
        session_id=payload.session_id,
        source=payload.source,
    )


@router.post("/demo/auth/magic-link", response_model=DemoAccessOutput)
def demo_magic_link(
    payload: MagicLinkInput,
    request: Request,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_sales_write(principal)
    prospect = _get_prospect(db, payload.prospect_account_id)
    raw_token = sales.issue_demo_access(db, prospect, actor_id=principal.user.id)
    return {
        "access_token": raw_token,
        "demo_login_url": f"{_base_url(request)}/login?demo_token={raw_token}",
        "expires_at": prospect.demo_access_token_expires_at,
    }


@router.post("/demo/auth/redeem-token")
def redeem_demo_token(payload: DemoRedeemTokenInput, request: Request, db: Session = Depends(get_db)):
    session_id = request.headers.get("x-demo-session-id")
    return sales.redeem_demo_token(db, token=payload.token, session_id=session_id)

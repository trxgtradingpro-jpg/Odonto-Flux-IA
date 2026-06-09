from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
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
    OutboxMessage,
    Patient,
    ProspectAccount,
    ProspectNote,
    ProspectService,
    ProspectTimelineEvent,
    ProspectUnit,
    Tenant,
)
from app.models.enums import OutboxStatus
from app.schemas.admin_sales import (
    AdminOutreachRuntimeOutput,
    AdminAffiliateListOutput,
    AdminAffiliateRegisterInput,
    AdminAffiliateUpdateInput,
    AdminChangeInitialPasswordInput,
    AdminLoginInput,
    AdminLoginOutput,
    AdminPageDefinitionOutput,
    AdminSessionOutput,
    AffiliateContactMessageConfigInput,
    AffiliateContactMessageConfigOutput,
    AffiliateContactPrepareInput,
    AffiliateContactPrepareOutput,
    AffiliateCrmAvailableOutput,
    AffiliateFirstMessageConfigInput,
    AffiliateFirstMessageConfigOutput,
    AffiliateFirstMessageSendInput,
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
    GooglePlacesImportInput,
    GooglePlacesImportOutput,
    GooglePlacesSearchInput,
    GooglePlacesSearchOutput,
    MagicLinkInput,
    ProspectContactInput,
    ProspectCreate,
    ProspectInsightsOutput,
    ProspectListOutput,
    ProspectNoSiteOutreachInput,
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
    SalesNoSiteOutreachFlowConfigInput,
    SalesNoSiteOutreachFlowConfigOutput,
    SalesNoSiteOutreachBulkInput,
    SalesNoSiteOutreachBulkOutput,
    SalesNoSiteOutreachEligibilityOutput,
    SalesOutreachAutomationBatchListOutput,
    SalesOutreachAutomationBatchOutput,
    SalesOutreachAutomationBatchStartInput,
    SalesOutreachAutomationEligibilityOutput,
    SalesOutreachFlowConfigInput,
    SalesOutreachFlowConfigOutput,
    SalesMessageTemplateInput,
    SalesMessageTemplateOutput,
)
from app.services import sales_demo_service as sales
from app.services import google_places_service
from app.services import sales_outreach_automation_service as outreach_automation
from app.services import sales_message_service as sales_messages
from app.services.ai_autoresponder_service import get_global_config as get_ai_agent_config
from app.services.ai_autoresponder_service import get_platform_global_config as get_ai_agent_platform_config
from app.services.ai_autoresponder_service import set_global_config as set_ai_agent_config
from app.services.ai_autoresponder_service import set_platform_global_config as set_ai_agent_platform_config
from app.services.audit_service import record_audit
from app.services.whatsapp_bridge_support import WHATSAPP_WEB_BRIDGE_TRANSPORT, payload_uses_whatsapp_web_bridge, resolve_sales_outreach_transport

router = APIRouter(tags=["admin_sales"])

_login_attempts: dict[str, list[datetime]] = {}


class AdminWhatsAppTestContactInput(BaseModel):
    prospect_id: UUID


class AdminWhatsAppSimulatedInboundInput(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class AdminAgentSettingsInput(BaseModel):
    tenant_id: UUID | None = None
    scope: str | None = None
    config: dict = Field(default_factory=dict)


def _serialize_sales_outreach_flow_config(raw_config: dict) -> dict:
    classifications = []
    rules = raw_config.get("classification_rules") if isinstance(raw_config.get("classification_rules"), dict) else {}
    class_to_step = raw_config.get("class_to_step") if isinstance(raw_config.get("class_to_step"), dict) else {}
    for class_name, config in rules.items():
        classifications.append(
            {
                "class_name": class_name,
                "priority": int(config.get("priority") or 0),
                "keywords": list(config.get("keywords") or []),
                "next_step": class_to_step.get(class_name),
            }
        )
    classifications.sort(key=lambda item: (-item["priority"], item["class_name"]))
    return {
        "initial_messages": list(raw_config.get("initial_messages") or []),
        "step_messages": {
            key: list(value) if isinstance(value, list) else [str(value).strip()]
            for key, value in dict(raw_config.get("step_messages") or {}).items()
            if (isinstance(value, list) and value) or str(value).strip()
        },
        "classifications": classifications,
    }


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


def _is_affiliate_prospect_scope(principal) -> bool:
    roles = set(principal.roles)
    return sales.ADM_AFFILIATE_ROLE_NAME in roles and not roles.intersection(sales.ADM_FULL_ACCESS_ROLE_NAMES)


def _prospect_visibility_filter(principal):
    if _is_affiliate_prospect_scope(principal):
        return ProspectAccount.affiliate_owner_user_id == principal.user.id
    return None


def _apply_prospect_visibility(query, principal):
    visibility_filter = _prospect_visibility_filter(principal)
    return query.where(visibility_filter) if visibility_filter is not None else query


def _require_prospect_visible_to_principal(prospect: ProspectAccount, principal) -> None:
    if _is_affiliate_prospect_scope(principal) and prospect.affiliate_owner_user_id != principal.user.id:
        raise ApiError(status_code=404, code="PROSPECT_NOT_FOUND", message="Prospect nao encontrado")


def _get_visible_prospect(db: Session, prospect_id: UUID, principal) -> ProspectAccount:
    prospect = _get_prospect(db, prospect_id)
    _require_prospect_visible_to_principal(prospect, principal)
    return prospect


def _require_affiliate_principal(principal) -> None:
    if not _is_affiliate_prospect_scope(principal):
        raise ApiError(
            status_code=403,
            code="AFFILIATE_CRM_FORBIDDEN",
            message="Esta area e exclusiva para usuarios afiliados.",
        )


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
    tags = conversation.tags or []
    internal_simulation = sales.ADM_INTERNAL_WHATSAPP_SIMULATION_TAG in tags
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
        "contact_name": (
            f"Simulador interno - {prospect.clinic_name}"
            if internal_simulation
            else contact["name"] or prospect.owner_name or prospect.manager_name or prospect.clinic_name
        ),
        "contact_phone": None if internal_simulation else contact["phone"] or prospect.whatsapp_phone or prospect.phone,
        "patient_id": str(conversation.patient_id) if conversation.patient_id else None,
        "lead_id": str(conversation.lead_id) if conversation.lead_id else None,
        "channel": conversation.channel,
        "status": conversation.status,
        "tags": tags,
        "internal_simulation": internal_simulation,
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


def _resolve_agent_settings_tenant(db: Session, *, principal, tenant_id: UUID | None) -> Tenant:
    target_tenant_id = principal.tenant_id or tenant_id
    if not target_tenant_id:
        raise ApiError(
            status_code=422,
            code="ADM_AGENT_SETTINGS_TENANT_REQUIRED",
            message="Selecione uma clinica para configurar o agente.",
        )
    if principal.tenant_id and tenant_id and tenant_id != principal.tenant_id and "admin_platform" not in set(principal.roles):
        raise ApiError(
            status_code=403,
            code="ADM_AGENT_SETTINGS_TENANT_FORBIDDEN",
            message="Seu usuario nao pode alterar configuracoes de outro tenant.",
        )
    tenant = db.get(Tenant, target_tenant_id)
    if not tenant:
        raise ApiError(status_code=404, code="TENANT_NOT_FOUND", message="Clinica nao encontrada.")
    return tenant


def _serialize_agent_settings_tenant(tenant: Tenant) -> dict:
    return {
        "id": str(tenant.id),
        "name": tenant.trade_name or tenant.legal_name,
        "slug": tenant.slug,
        "subscription_status": tenant.subscription_status,
    }


def _is_platform_scope_requested(*, principal, scope: str | None) -> bool:
    normalized = str(scope or "").strip().lower()
    if normalized != "platform":
        return False
    if "admin_platform" not in set(principal.roles):
        raise ApiError(
            status_code=403,
            code="ADM_AGENT_SETTINGS_PLATFORM_FORBIDDEN",
            message="Somente admin da plataforma pode alterar o padrao global do sistema.",
        )
    return True


@router.post("/admin/auth/login", response_model=AdminLoginOutput)
def admin_login(payload: AdminLoginInput, request: Request, db: Session = Depends(get_db)):
    _rate_limit_login(request, payload.email)
    return sales.admin_login(db, email=payload.email, password=payload.password)


@router.get("/admin/auth/me", response_model=AdminSessionOutput)
def admin_me(principal=Depends(get_current_principal)):
    sales.require_sales_principal(principal)
    return sales.serialize_admin_session(user=principal.user, roles=principal.roles)


@router.post("/admin/affiliates/register", response_model=AdminLoginOutput)
def register_affiliate(payload: AdminAffiliateRegisterInput, request: Request, db: Session = Depends(get_db)):
    _rate_limit_login(request, payload.email)
    return sales.register_adm_affiliate(
        db,
        full_name=payload.full_name,
        email=str(payload.email),
        password=payload.password,
        phone=payload.phone,
    )


@router.get("/admin/affiliates/pages", response_model=list[AdminPageDefinitionOutput])
def list_affiliate_page_definitions(principal=Depends(get_current_principal)):
    sales.require_adm_page_permission(principal, "adm_affiliates", "view")
    return sales.adm_page_definitions()


@router.get("/admin/affiliates", response_model=AdminAffiliateListOutput)
def list_affiliates(principal=Depends(get_current_principal), db: Session = Depends(get_db)):
    sales.require_adm_page_permission(principal, "adm_affiliates", "view")
    data = sales.list_adm_affiliates(db)
    return {"data": data, "total": len(data)}


@router.get("/admin/agent-settings/tenants")
def list_agent_settings_tenants(
    search: str | None = Query(default=None, max_length=80),
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_agent_settings", "view")
    if principal.tenant_id:
        tenant = db.get(Tenant, principal.tenant_id)
        return {"data": [_serialize_agent_settings_tenant(tenant)] if tenant else []}

    filters = []
    if search:
        pattern = f"%{search.strip()}%"
        filters.append((Tenant.trade_name.ilike(pattern)) | (Tenant.legal_name.ilike(pattern)) | (Tenant.slug.ilike(pattern)))
    query = select(Tenant).order_by(Tenant.trade_name.asc(), Tenant.legal_name.asc()).limit(200)
    if filters:
        query = query.where(*filters)
    rows = db.execute(query).scalars().all()
    return {"data": [_serialize_agent_settings_tenant(row) for row in rows]}


@router.get("/admin/agent-settings")
def get_agent_settings(
    tenant_id: UUID | None = Query(default=None),
    scope: str | None = Query(default=None),
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_agent_settings", "view")
    if _is_platform_scope_requested(principal=principal, scope=scope):
        return {
            "scope": "platform",
            "tenant": None,
            "config": get_ai_agent_platform_config(db),
            "model_options": [
                {"value": "", "label": "Padrao do ambiente"},
                {"value": "gpt-4.1-mini", "label": "gpt-4.1-mini"},
                {"value": "gpt-4.1", "label": "gpt-4.1"},
                {"value": "gpt-4o-mini", "label": "gpt-4o-mini"},
                {"value": "gpt-4o", "label": "gpt-4o"},
            ],
        }
    tenant = _resolve_agent_settings_tenant(db, principal=principal, tenant_id=tenant_id)
    return {
        "scope": "tenant",
        "tenant": _serialize_agent_settings_tenant(tenant),
        "config": get_ai_agent_config(db, tenant_id=tenant.id),
        "model_options": [
            {"value": "", "label": "Padrao do ambiente"},
            {"value": "gpt-4.1-mini", "label": "gpt-4.1-mini"},
            {"value": "gpt-4.1", "label": "gpt-4.1"},
            {"value": "gpt-4o-mini", "label": "gpt-4o-mini"},
            {"value": "gpt-4o", "label": "gpt-4o"},
        ],
    }


@router.put("/admin/agent-settings")
def update_agent_settings(
    payload: AdminAgentSettingsInput,
    tenant_id: UUID | None = Query(default=None),
    scope: str | None = Query(default=None),
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_agent_settings", "edit")
    requested_scope = payload.scope or scope
    if _is_platform_scope_requested(principal=principal, scope=requested_scope):
        config = set_ai_agent_platform_config(db, payload=payload.config)
        record_audit(
            db,
            action="admin.agent_settings.update",
            entity_type="platform_agent_settings",
            entity_id="platform.ai_autoresponder.global",
            tenant_id=None,
            user_id=principal.user.id,
            metadata={
                "scope": "platform",
                "conversation_flow_mode": config.get("conversation_flow_mode"),
                "structured_flow_enabled": config.get("structured_flow_enabled"),
                "llm_model": config.get("llm_model"),
                "pre_send_review_enabled": config.get("pre_send_review_enabled"),
                "repetition_guard_enabled": config.get("repetition_guard_enabled"),
                "conversation_memory_enabled": config.get("conversation_memory_enabled"),
                "auto_save_patient_data_enabled": config.get("auto_save_patient_data_enabled"),
            },
        )
        return {
            "scope": "platform",
            "tenant": None,
            "config": config,
        }
    tenant = _resolve_agent_settings_tenant(
        db,
        principal=principal,
        tenant_id=payload.tenant_id or tenant_id,
    )
    config = set_ai_agent_config(db, tenant_id=tenant.id, payload=payload.config)
    record_audit(
        db,
        action="admin.agent_settings.update",
        entity_type="tenant",
        entity_id=str(tenant.id),
        tenant_id=tenant.id,
        user_id=principal.user.id,
        metadata={
            "conversation_flow_mode": config.get("conversation_flow_mode"),
            "structured_flow_enabled": config.get("structured_flow_enabled"),
            "llm_model": config.get("llm_model"),
            "pre_send_review_enabled": config.get("pre_send_review_enabled"),
            "repetition_guard_enabled": config.get("repetition_guard_enabled"),
            "conversation_memory_enabled": config.get("conversation_memory_enabled"),
            "auto_save_patient_data_enabled": config.get("auto_save_patient_data_enabled"),
        },
    )
    return {
        "scope": "tenant",
        "tenant": _serialize_agent_settings_tenant(tenant),
        "config": config,
    }


@router.patch("/admin/affiliates/{user_id}", response_model=AdminSessionOutput)
def update_affiliate(
    user_id: UUID,
    payload: AdminAffiliateUpdateInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_affiliates", "edit")
    return sales.update_adm_affiliate(
        db,
        user_id=user_id,
        full_name=payload.full_name,
        phone=payload.phone,
        is_active=payload.is_active,
        page_permissions=payload.page_permissions,
    )


@router.delete("/admin/affiliates/{user_id}")
def delete_affiliate(user_id: UUID, principal=Depends(get_current_principal), db: Session = Depends(get_db)):
    sales.require_adm_page_permission(principal, "adm_affiliates", "delete")
    sales.delete_adm_affiliate(db, user_id=user_id)
    return {"message": "Afiliado removido."}


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
    sales.require_adm_page_permission(principal, "adm_whatsapp", "view")
    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    prospect_stmt = _apply_prospect_visibility(select(ProspectAccount), principal)
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
                Conversation.channel.in_(["whatsapp", "webchat"]),
            )
            .order_by(Conversation.last_message_at.desc().nullslast(), Conversation.created_at.desc())
        ).scalars().all()
        for conversation in demo_conversations:
            prospect = prospect_by_demo_tenant.get(conversation.tenant_id)
            if prospect:
                source = "demo_webchat" if conversation.channel == "webchat" else "demo"
                items.append(_serialize_admin_whatsapp_conversation(db, prospect=prospect, conversation=conversation, source=source))

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
    sales.require_adm_page_permission(principal, "adm_whatsapp", "view")
    _prospect, conversation, source = _resolve_admin_whatsapp_conversation(db, conversation_id)
    _require_prospect_visible_to_principal(_prospect, principal)
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


@router.post("/admin/whatsapp/conversations/{conversation_id}/simulate-inbound")
def simulate_admin_whatsapp_inbound(
    conversation_id: UUID,
    payload: AdminWhatsAppSimulatedInboundInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_whatsapp", "view")
    prospect, conversation, source = _resolve_admin_whatsapp_conversation(db, conversation_id)
    _require_prospect_visible_to_principal(prospect, principal)
    if source != "comercial" or sales.ADM_INTERNAL_WHATSAPP_SIMULATION_TAG not in (conversation.tags or []):
        raise ApiError(
            status_code=400,
            code="ADM_INTERNAL_SIMULATION_REQUIRED",
            message="Abra o simulador interno comercial antes de enviar uma resposta simulada da clinica.",
        )

    result = sales.simulate_admin_internal_whatsapp_inbound(
        db,
        prospect=prospect,
        conversation=conversation,
        body=payload.body,
        actor_id=principal.user.id,
    )
    inbound = result["inbound_message"]
    outbound = result["outbound_message"]

    def serialize_message(message: Message) -> dict:
        return {
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

    return {
        "conversation_id": str(conversation.id),
        "prospect_id": str(prospect.id),
        "source": source,
        "internal_simulation": True,
        "reply_classification": result.get("reply_classification"),
        "step": result.get("step"),
        "inbound_message": serialize_message(inbound),
        "outbound_message": serialize_message(outbound),
        "conversation": _serialize_admin_whatsapp_conversation(db, prospect=prospect, conversation=conversation, source=source),
    }


@router.post("/admin/whatsapp/test-contact")
def ensure_admin_whatsapp_test_contact(
    payload: AdminWhatsAppTestContactInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_whatsapp", "view")
    prospect = _get_visible_prospect(db, payload.prospect_id, principal)
    conversation = sales.ensure_admin_whatsapp_test_contact(db, prospect=prospect)
    return {
        "conversation_id": str(conversation.id),
        "prospect_id": str(prospect.id),
        "prospect_name": prospect.clinic_name,
        "contact_name": f"Simulador interno - {prospect.clinic_name}",
        "contact_phone": None,
        "source": "comercial",
        "test_contact": True,
        "internal_simulation": True,
    }


@router.get("/admin/prospects/overview", response_model=ProspectOverviewOutput)
def prospects_overview(principal=Depends(get_current_principal), db: Session = Depends(get_db)):
    sales.require_adm_page_permission(principal, "adm_crm", "view")
    return sales.overview(
        db,
        affiliate_owner_user_id=principal.user.id if _is_affiliate_prospect_scope(principal) else None,
    )


@router.get("/admin/affiliate-crm/available", response_model=AffiliateCrmAvailableOutput)
def affiliate_crm_available(
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_crm", "view")
    _require_affiliate_principal(principal)
    prospect = sales.get_next_affiliate_prospect(db)
    return {
        "prospect": sales.serialize_prospect(db, prospect) if prospect else None,
        "available": bool(prospect),
    }


@router.get("/admin/affiliate-crm/mine", response_model=ProspectListOutput)
def affiliate_crm_mine(
    limit: int = 200,
    offset: int = 0,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_crm", "view")
    _require_affiliate_principal(principal)
    return sales.list_affiliate_claimed_prospects(
        db,
        user_id=principal.user.id,
        limit=min(max(limit, 1), 500),
        offset=max(offset, 0),
    )


@router.get(
    "/admin/affiliate-crm/first-messages",
    response_model=AffiliateFirstMessageConfigOutput,
)
def affiliate_crm_first_messages(
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_crm", "view")
    _require_affiliate_principal(principal)
    return sales.get_affiliate_first_message_config(db, user_id=principal.user.id)


@router.put(
    "/admin/affiliate-crm/first-messages",
    response_model=AffiliateFirstMessageConfigOutput,
)
def update_affiliate_crm_first_messages(
    payload: AffiliateFirstMessageConfigInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_crm", "edit")
    _require_affiliate_principal(principal)
    return sales.save_affiliate_first_message_config(
        db,
        user_id=principal.user.id,
        payload=payload.model_dump(),
    )


@router.get(
    "/admin/affiliate-crm/contact-messages",
    response_model=AffiliateContactMessageConfigOutput,
)
def affiliate_crm_contact_messages(
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_crm", "view")
    _require_affiliate_principal(principal)
    return sales.get_affiliate_contact_message_config(db, user_id=principal.user.id)


@router.put(
    "/admin/affiliate-crm/contact-messages",
    response_model=AffiliateContactMessageConfigOutput,
)
def update_affiliate_crm_contact_messages(
    payload: AffiliateContactMessageConfigInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_crm", "edit")
    _require_affiliate_principal(principal)
    return sales.save_affiliate_contact_message_config(
        db,
        user_id=principal.user.id,
        payload=payload.model_dump(),
    )


@router.post(
    "/admin/affiliate-crm/prospects/{prospect_id}/prepare-contact",
    response_model=AffiliateContactPrepareOutput,
)
def affiliate_crm_prepare_contact(
    prospect_id: UUID,
    payload: AffiliateContactPrepareInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_crm", "edit")
    _require_affiliate_principal(principal)
    return sales.prepare_affiliate_whatsapp_contact(
        db,
        prospect_id=prospect_id,
        affiliate_user_id=principal.user.id,
        stage=payload.stage,
        message_index=payload.message_index,
        consent_exclusive=payload.consent_exclusive,
        consent_responsible_use=payload.consent_responsible_use,
        human_reply_confirmed=payload.human_reply_confirmed,
    )


@router.post(
    "/admin/affiliate-crm/prospects/{prospect_id}/send-first",
    response_model=ProspectOutreachOutput,
)
def affiliate_crm_send_first_message(
    prospect_id: UUID,
    payload: AffiliateFirstMessageSendInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_crm", "edit")
    _require_affiliate_principal(principal)
    return sales.claim_prospect_with_affiliate_first_message(
        db,
        prospect_id=prospect_id,
        affiliate_user_id=principal.user.id,
        message_index=payload.message_index,
    )


@router.get("/admin/outreach/runtime", response_model=AdminOutreachRuntimeOutput)
def outreach_runtime(principal=Depends(get_current_principal), db: Session = Depends(get_db)):
    sales.require_adm_page_permission(principal, "adm_crm", "view")

    transport = resolve_sales_outreach_transport()
    sender_tenant = sales.ensure_sales_outreach_sender_tenant(db)
    bridge_pending = 0
    bridge_processing = 0
    bridge_failed = 0
    bridge_dead_letter = 0

    if transport == WHATSAPP_WEB_BRIDGE_TRANSPORT:
        outboxes = db.execute(
            select(OutboxMessage)
            .where(OutboxMessage.tenant_id == sender_tenant.id)
            .order_by(OutboxMessage.created_at.desc())
            .limit(400)
        ).scalars().all()
        for item in outboxes:
            payload = item.payload if isinstance(item.payload, dict) else {}
            if not payload_uses_whatsapp_web_bridge(payload):
                continue
            status = str(item.status or "").strip()
            if status == OutboxStatus.PENDING.value:
                bridge_pending += 1
            elif status == OutboxStatus.PROCESSING.value:
                bridge_processing += 1
            elif status == OutboxStatus.FAILED.value:
                bridge_failed += 1
            elif status == OutboxStatus.DEAD_LETTER.value:
                bridge_dead_letter += 1

    return {
        "transport": transport,
        "sender_tenant_slug": sender_tenant.slug,
        "bridge_enabled": transport == WHATSAPP_WEB_BRIDGE_TRANSPORT,
        "bridge_configured": bool(str(settings.whatsapp_web_bridge_token or "").strip()),
        "bridge_pending": bridge_pending,
        "bridge_processing": bridge_processing,
        "bridge_failed": bridge_failed,
        "bridge_dead_letter": bridge_dead_letter,
        "bridge_command": "python apps/msg/whatsapp_web.py bridge" if transport == WHATSAPP_WEB_BRIDGE_TRANSPORT else None,
    }


@router.get("/admin/outreach/automation/eligible", response_model=SalesOutreachAutomationEligibilityOutput)
def outreach_automation_eligible(
    quantity: int = 20,
    status: str | None = None,
    temperature: str | None = None,
    demo_status: str | None = None,
    q: str | None = None,
    only_without_demo: bool = False,
    only_with_demo: bool = False,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_outreach_automation", "view")
    return outreach_automation.eligible_summary(
        db,
        filters={
            "status": status,
            "temperature": temperature,
            "demo_status": demo_status,
            "q": q,
            "only_without_demo": only_without_demo,
            "only_with_demo": only_with_demo,
        },
        limit=min(max(quantity, 1), 50),
    )


@router.get("/admin/outreach/no-site/eligible", response_model=SalesNoSiteOutreachEligibilityOutput)
def no_site_outreach_eligible(
    stage: Literal["first", "second", "third"] = "first",
    limit: int = 50,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_outreach_automation", "view")
    return sales.list_no_site_outreach_eligible(db, stage=stage, limit=min(max(limit, 1), 200))


@router.post("/admin/outreach/no-site/send-all", response_model=SalesNoSiteOutreachBulkOutput)
def send_no_site_outreach_to_all(
    payload: SalesNoSiteOutreachBulkInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_outreach_automation", "create")
    return sales.send_no_site_outreach_bulk(
        db,
        stage=payload.stage,
        actor_id=principal.user.id,
        limit=payload.limit,
    )


@router.get("/admin/outreach/automation/batches", response_model=SalesOutreachAutomationBatchListOutput)
def list_outreach_automation_batches(
    limit: int = 20,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_outreach_automation", "view")
    return outreach_automation.list_batches(db, limit=min(max(limit, 1), 100))


@router.get("/admin/outreach/automation/batches/{batch_id}", response_model=SalesOutreachAutomationBatchOutput)
def get_outreach_automation_batch(
    batch_id: UUID,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_outreach_automation", "view")
    return outreach_automation.get_batch(db, batch_id)


@router.post("/admin/outreach/automation/batches", response_model=SalesOutreachAutomationBatchOutput)
def create_outreach_automation_batch(
    payload: SalesOutreachAutomationBatchStartInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_outreach_automation", "create")
    return outreach_automation.create_batch(
        db,
        quantity=payload.quantity,
        filters=payload.model_dump(exclude={"quantity"}),
        actor_id=principal.user.id,
    )


@router.post("/admin/outreach/automation/batches/{batch_id}/pause", response_model=SalesOutreachAutomationBatchOutput)
def pause_outreach_automation_batch(
    batch_id: UUID,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_outreach_automation", "edit")
    return outreach_automation.pause_batch(db, batch_id=batch_id)


@router.post("/admin/outreach/automation/batches/{batch_id}/resume", response_model=SalesOutreachAutomationBatchOutput)
def resume_outreach_automation_batch(
    batch_id: UUID,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_outreach_automation", "edit")
    return outreach_automation.resume_batch(db, batch_id=batch_id)


@router.delete("/admin/outreach/automation/batches/{batch_id}", status_code=204)
def delete_outreach_automation_batch(
    batch_id: UUID,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_outreach_automation", "delete")
    outreach_automation.delete_batch(db, batch_id=batch_id)
    return Response(status_code=204)


@router.get("/admin/prospects", response_model=ProspectListOutput)
def list_prospects(
    status: str | None = None,
    temperature: str | None = None,
    website_status: str | None = Query(default=None),
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_crm", "view")
    query = select(ProspectAccount)
    count_query = select(func.count(ProspectAccount.id))
    filters = []
    if status:
        filters.append(ProspectAccount.status == status)
    if temperature:
        filters.append(ProspectAccount.temperature == temperature)
    visibility_filter = _prospect_visibility_filter(principal)
    if visibility_filter is not None:
        filters.append(visibility_filter)
    if website_status:
        website_present_filter = and_(
            ProspectAccount.website.is_not(None),
            func.length(func.trim(ProspectAccount.website)) > 0,
        )
        if website_status == "with_site":
            filters.append(website_present_filter)
        elif website_status == "without_site":
            filters.append(or_(ProspectAccount.website.is_(None), func.length(func.trim(ProspectAccount.website)) == 0))
        else:
            raise ApiError(status_code=400, code="PROSPECT_WEBSITE_STATUS_INVALID", message="Filtro de site invalido")
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
    sales.require_adm_page_permission(principal, "adm_messages", "view")
    return sales_messages.list_sales_message_templates(db)


@router.get("/admin/outreach/flow", response_model=SalesOutreachFlowConfigOutput)
def get_sales_outreach_flow(
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_messages", "view")
    return _serialize_sales_outreach_flow_config(sales.get_sales_outreach_flow_config(db))


@router.put("/admin/outreach/flow", response_model=SalesOutreachFlowConfigOutput)
def update_sales_outreach_flow(
    payload: SalesOutreachFlowConfigInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_messages", "edit")
    config_payload = payload.model_dump()
    classifications = config_payload.pop("classifications", [])
    config_payload["classification_rules"] = {
        item["class_name"]: {
            "priority": int(item.get("priority") or 0),
            "keywords": list(item.get("keywords") or []),
        }
        for item in classifications
    }
    config_payload["class_to_step"] = {
        item["class_name"]: str(item.get("next_step") or "").strip()
        for item in classifications
        if str(item.get("next_step") or "").strip()
    }
    saved = sales.save_sales_outreach_flow_config(db, config_payload)
    return _serialize_sales_outreach_flow_config(saved)


@router.get("/admin/outreach/no-site-flow", response_model=SalesNoSiteOutreachFlowConfigOutput)
def get_no_site_outreach_flow(
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_outreach_automation", "view")
    return sales.get_no_site_outreach_flow_config(db)


@router.put("/admin/outreach/no-site-flow", response_model=SalesNoSiteOutreachFlowConfigOutput)
def update_no_site_outreach_flow(
    payload: SalesNoSiteOutreachFlowConfigInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_outreach_automation", "edit")
    return sales.save_no_site_outreach_flow_config(db, payload.model_dump())


@router.post("/admin/clinic-messages/templates", response_model=SalesMessageTemplateOutput)
def create_clinic_message_template(
    payload: SalesMessageTemplateInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_messages", "create")
    return sales_messages.create_sales_message_template(db, payload.model_dump())


@router.put("/admin/clinic-messages/templates/{template_key}", response_model=SalesMessageTemplateOutput)
def update_clinic_message_template(
    template_key: str,
    payload: SalesMessageTemplateInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_messages", "edit")
    return sales_messages.update_sales_message_template(db, template_key, payload.model_dump())


@router.delete("/admin/clinic-messages/templates/{template_key}", response_model=list[SalesMessageTemplateOutput])
def delete_clinic_message_template(
    template_key: str,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_messages", "delete")
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
    sales.require_adm_page_permission(principal, "adm_messages", "view")
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
    visibility_filter = _prospect_visibility_filter(principal)
    if visibility_filter is not None:
        filters.append(visibility_filter)
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
    sales.require_adm_page_permission(principal, "adm_messages", "create")
    prospect = _get_visible_prospect(db, payload.prospect_id, principal)
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
    sales.require_adm_page_permission(principal, "adm_messages", "create")
    prospect = _get_visible_prospect(db, prospect_id, principal)
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


@router.post("/admin/google-places/search", response_model=GooglePlacesSearchOutput)
def search_google_places(
    payload: GooglePlacesSearchInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_import_places", "view")
    return google_places_service.search_google_places(
        db,
        query=payload.query,
        limit=payload.limit,
        region_code=payload.region_code,
        included_type=payload.included_type,
    )


@router.post("/admin/google-places/import", response_model=GooglePlacesImportOutput)
def import_google_places(
    payload: GooglePlacesImportInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_import_places", "create")
    return google_places_service.import_google_places(
        db,
        place_ids=payload.place_ids,
        lead_source=payload.lead_source,
        include_rating=payload.include_rating,
        actor_id=principal.user.id,
    )


@router.post("/admin/prospects", response_model=ProspectOutput)
def create_prospect(payload: ProspectCreate, principal=Depends(get_current_principal), db: Session = Depends(get_db)):
    sales.require_adm_page_permission(principal, "adm_crm", "create")
    prospect = sales.create_prospect(
        db,
        payload,
        actor_id=principal.user.id,
        affiliate_owner_user_id=principal.user.id if _is_affiliate_prospect_scope(principal) else None,
    )
    return sales.serialize_prospect(db, prospect)


@router.get("/admin/prospects/{prospect_id}", response_model=ProspectOutput)
def get_prospect(prospect_id: UUID, principal=Depends(get_current_principal), db: Session = Depends(get_db)):
    sales.require_adm_page_permission(principal, "adm_crm", "view")
    return sales.serialize_prospect(db, _get_visible_prospect(db, prospect_id, principal))


@router.patch("/admin/prospects/{prospect_id}", response_model=ProspectOutput)
def update_prospect(
    prospect_id: UUID,
    payload: ProspectUpdate,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_crm", "edit")
    prospect = sales.update_prospect(db, _get_visible_prospect(db, prospect_id, principal), payload, actor_id=principal.user.id)
    return sales.serialize_prospect(db, prospect)


@router.delete("/admin/prospects/{prospect_id}")
def delete_prospect(prospect_id: UUID, principal=Depends(get_current_principal), db: Session = Depends(get_db)):
    sales.require_adm_page_permission(principal, "adm_crm", "delete")
    prospect = _get_visible_prospect(db, prospect_id, principal)
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
    sales.require_adm_page_permission(principal, "adm_crm", "edit")
    prospect = _get_visible_prospect(db, prospect_id, principal)
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
    sales.require_adm_page_permission(principal, "adm_crm", "edit")
    prospect = _get_visible_prospect(db, prospect_id, principal)
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
    sales.require_adm_page_permission(principal, "adm_crm", "edit")
    prospect = _get_visible_prospect(db, prospect_id, principal)
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
    sales.require_adm_page_permission(principal, "adm_crm", "view")
    _get_visible_prospect(db, prospect_id, principal)
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
    sales.require_adm_page_permission(principal, "adm_crm", "edit")
    result = sales.generate_demo(db, _get_visible_prospect(db, prospect_id, principal), actor_id=principal.user.id, base_url=_base_url(request))
    return {
        "prospect": sales.serialize_prospect(db, result["prospect"]),
        "access_token": result["access_token"],
        "demo_login_url": result["demo_login_url"],
        "demo_booking_path": result["demo_booking_path"],
        "demo_booking_url": result["demo_booking_url"],
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
    sales.require_adm_page_permission(principal, "adm_crm", "edit")
    prospect = _get_visible_prospect(db, prospect_id, principal)
    raw_token = sales.issue_demo_access(db, prospect, actor_id=principal.user.id)
    demo_booking_path = sales.resolve_demo_booking_path(db, prospect=prospect)
    demo_booking_url = None
    if demo_booking_path:
        demo_booking_url = f"{_base_url(request).rstrip('/')}{demo_booking_path}"
    return {
        "access_token": raw_token,
        "demo_login_url": sales.build_demo_login_url(_base_url(request), raw_token),
        "demo_booking_path": demo_booking_path,
        "demo_booking_url": demo_booking_url,
        "expires_at": prospect.demo_access_token_expires_at,
    }


@router.post("/admin/prospects/{prospect_id}/record-contact", response_model=ProspectOutput)
def record_contact(
    prospect_id: UUID,
    payload: ProspectContactInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_crm", "edit")
    prospect = _get_visible_prospect(db, prospect_id, principal)
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
    sales.require_adm_page_permission(principal, "adm_crm", "edit")
    result = sales.send_sales_outreach_step(
        db,
        prospect=_get_visible_prospect(db, prospect_id, principal),
        step=payload.step,
        actor_id=principal.user.id,
        base_url=_base_url(request),
        recipient_name=payload.recipient_name,
        explicit_video_url=payload.video_url,
    )
    return result


@router.post("/admin/prospects/{prospect_id}/outreach/no-site", response_model=ProspectOutreachOutput)
def send_no_site_outreach(
    prospect_id: UUID,
    payload: ProspectNoSiteOutreachInput,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_crm", "edit")
    return sales.send_no_site_outreach_stage(
        db,
        prospect=_get_visible_prospect(db, prospect_id, principal),
        stage=payload.stage,
        actor_id=principal.user.id,
    )


@router.post("/admin/prospects/{prospect_id}/outreach/automation/start", response_model=ProspectOutreachOutput)
def start_outreach_automation(
    prospect_id: UUID,
    request: Request,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    sales.require_adm_page_permission(principal, "adm_crm", "edit")
    result = sales.start_sales_outreach_automation(
        db,
        prospect=_get_visible_prospect(db, prospect_id, principal),
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
    sales.require_adm_page_permission(principal, "adm_crm", "edit")
    result = sales.simulate_sales_outreach_lab(
        db,
        prospect=_get_visible_prospect(db, prospect_id, principal),
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
    sales.require_adm_page_permission(principal, "adm_crm", "edit")
    if payload.status not in sales.PROSPECT_STATUSES:
        raise ApiError(status_code=400, code="PROSPECT_STATUS_INVALID", message="Status comercial invalido")
    prospect = _get_visible_prospect(db, prospect_id, principal)
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
    sales.require_adm_page_permission(principal, "adm_crm", "edit")
    prospect = sales.recalculate_score(db, _get_visible_prospect(db, prospect_id, principal))
    return sales.serialize_prospect(db, prospect)


@router.get("/admin/prospects/{prospect_id}/activity", response_model=list[DemoActivityOutput])
def activity(prospect_id: UUID, principal=Depends(get_current_principal), db: Session = Depends(get_db)):
    sales.require_adm_page_permission(principal, "adm_crm", "view")
    _get_visible_prospect(db, prospect_id, principal)
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
    sales.require_adm_page_permission(principal, "adm_crm", "view")
    return sales.get_insights(db, _get_visible_prospect(db, prospect_id, principal))


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
    sales.require_adm_page_permission(principal, "adm_messages", "create")
    prospect = _get_visible_prospect(db, payload.prospect_account_id, principal)
    raw_token = sales.issue_demo_access(db, prospect, actor_id=principal.user.id)
    return {
        "access_token": raw_token,
        "demo_login_url": sales.build_demo_login_url(_base_url(request), raw_token),
        "expires_at": prospect.demo_access_token_expires_at,
    }


@router.post("/demo/auth/redeem-token")
def redeem_demo_token(payload: DemoRedeemTokenInput, request: Request, db: Session = Depends(get_db)):
    session_id = request.headers.get("x-demo-session-id")
    return sales.redeem_demo_token(db, token=payload.token, session_id=session_id)

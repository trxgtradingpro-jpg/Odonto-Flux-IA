from datetime import UTC, datetime
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, require_roles
from app.core.config import settings
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.integrations.whatsapp.cloud_api import WhatsAppCloudProvider
from app.integrations.whatsapp.infobip import InfobipWhatsAppProvider
from app.integrations.whatsapp.twilio import TwilioWhatsAppProvider
from app.models import OutboxMessage, ProspectAccount, WhatsAppAccount
from app.models.enums import OutboxStatus
from app.services.implementation_registry_service import (
    list_platform_implementations,
    set_platform_implementation_enabled,
)
from app.services import sales_demo_service as sales
from app.services.audit_service import record_audit
from app.services.dashboard_service import global_admin_metrics, global_admin_overview
from app.services.monitoring_service import monitoring_snapshot
from app.services.whatsapp_service import normalize_whatsapp_provider_name, whatsapp_account_issues

router = APIRouter(prefix="/admin/platform", tags=["admin_platform"])


class ImplementationToggleInput(BaseModel):
    enabled: bool


def _provider_validation_hint(provider_name: str) -> str:
    if provider_name == "infobip":
        return "Revise sender aprovado, base URL da conta e App key oficial da Infobip."
    if provider_name == "twilio":
        return "Revise sender WhatsApp, Account SID e Auth Token oficial da Twilio."
    return "Revise Phone Number ID, Business Account ID e Access Token oficial da Meta."


def _provider_validation_detail(exc: httpx.HTTPStatusError) -> str | None:
    response = exc.response
    if response is None:
        return None
    try:
        payload = response.json()
        detail = str(payload)
    except ValueError:
        detail = response.text or ""
    detail = " ".join(detail.split()).strip()
    if not detail:
        return None
    return detail[:280]


def _system_whatsapp_tenant(db: Session):
    return sales.ensure_sales_outreach_sender_tenant(db)


def _serialize_account(item: WhatsAppAccount) -> dict:
    return {
        "id": str(item.id),
        "provider_name": item.provider_name,
        "phone_number_id": item.phone_number_id,
        "business_account_id": item.business_account_id,
        "display_phone": item.display_phone,
        "is_active": item.is_active,
    }


def _health_payload(db: Session) -> dict:
    tenant = _system_whatsapp_tenant(db)
    active_account = db.scalar(
        select(WhatsAppAccount)
        .where(
            WhatsAppAccount.tenant_id == tenant.id,
            WhatsAppAccount.is_active.is_(True),
        )
        .order_by(WhatsAppAccount.created_at.desc())
        .limit(1)
    )

    issues: list[str] = []
    if not active_account:
        issues.append("Nenhum numero oficial do sistema foi conectado ainda.")
    else:
        issues = whatsapp_account_issues(
            provider_name=active_account.provider_name,
            phone_number_id=active_account.phone_number_id,
            business_account_id=active_account.business_account_id,
            access_token=active_account.access_token_encrypted,
        )

    recent_failure = db.scalar(
        select(OutboxMessage)
        .where(
            OutboxMessage.tenant_id == tenant.id,
            OutboxMessage.channel == "whatsapp",
            OutboxMessage.status.in_([OutboxStatus.FAILED.value, OutboxStatus.DEAD_LETTER.value]),
        )
        .order_by(OutboxMessage.updated_at.desc(), OutboxMessage.created_at.desc())
        .limit(1)
    )
    recent_error = str(recent_failure.last_error or "") if recent_failure else ""
    normalized_error = recent_error.lower()
    credit_issue = any(marker in normalized_error for marker in ["not enough credits", "insufficient credit", "credito", "credito"])

    if issues or credit_issue:
        status = "blocked"
    elif recent_failure:
        status = "warning"
    else:
        status = "ok"

    return {
        "status": status,
        "tenant": {
            "id": str(tenant.id),
            "slug": tenant.slug,
            "trade_name": tenant.trade_name,
            "legal_name": tenant.legal_name,
        },
        "active_account": _serialize_account(active_account) if active_account else None,
        "issues": issues,
        "recent_failure": (
            {
                "id": str(recent_failure.id),
                "status": recent_failure.status,
                "last_error": recent_error,
                "created_at": recent_failure.created_at.isoformat(),
                "updated_at": recent_failure.updated_at.isoformat(),
                "is_credit_issue": credit_issue,
            }
            if recent_failure
            else None
        ),
        "message": (
            "WhatsApp oficial do sistema ainda nao configurado."
            if not active_account
            else "WhatsApp do sistema bloqueado por configuracao ou creditos."
            if status == "blocked"
            else "WhatsApp do sistema com falhas recentes de envio."
            if status == "warning"
            else "WhatsApp oficial do sistema pronto para operacao."
        ),
    }


def _provider_instance(provider_name: str, business_account_id: str):
    if provider_name == "infobip":
        return InfobipWhatsAppProvider(base_url=business_account_id)
    if provider_name == "twilio":
        return TwilioWhatsAppProvider(account_sid=business_account_id)
    return WhatsAppCloudProvider()


@router.get("/metrics", dependencies=[Depends(require_roles("admin_platform"))])
def metrics(db: Session = Depends(get_db)):
    return global_admin_metrics(db)


@router.get("/health", dependencies=[Depends(require_roles("admin_platform"))])
def admin_health(db: Session = Depends(get_db)):
    snapshot = monitoring_snapshot(db)
    database_status = snapshot["services"]["database"]["status"]
    redis_status = snapshot["services"]["redis"]["status"]
    overall = "ok" if database_status == "up" and redis_status == "up" else "degraded"

    return {
        "status": overall,
        "services": {
            "api": "up",
            "database": database_status,
            "redis": redis_status,
        },
        "uptime_seconds": snapshot["uptime_seconds"],
        "failed_jobs_last_hour": snapshot["errors"]["failed_jobs_last_hour"],
        "alerts": snapshot["alerts"],
    }


@router.get("/overview", dependencies=[Depends(require_roles("admin_platform"))])
def overview(db: Session = Depends(get_db)):
    return global_admin_overview(db)


@router.get("/implementations", dependencies=[Depends(require_roles("admin_platform"))])
def implementations(db: Session = Depends(get_db)):
    return list_platform_implementations(db)


@router.patch("/implementations/{implementation_key}")
def toggle_implementation(
    implementation_key: str,
    payload: ImplementationToggleInput,
    principal: Principal = Depends(require_roles("admin_platform")),
    db: Session = Depends(get_db),
):
    item = set_platform_implementation_enabled(
        db,
        key=implementation_key,
        enabled=bool(payload.enabled),
    )
    db.commit()
    record_audit(
        db,
        action="admin_platform.implementation.toggle",
        entity_type="feature_flag",
        entity_id=str(item["key"]),
        tenant_id=None,
        user_id=principal.user.id,
        metadata={
            "enabled": item["enabled"],
            "delivery_status": item["delivery_status"],
            "category": item["category"],
        },
    )
    return item


@router.get("/monitoring", dependencies=[Depends(require_roles("admin_platform"))])
def monitoring(db: Session = Depends(get_db)):
    return monitoring_snapshot(db)


@router.get("/whatsapp/context", dependencies=[Depends(require_roles("admin_platform", "sales_admin", "sales_viewer"))])
def system_whatsapp_context(db: Session = Depends(get_db)):
    tenant = _system_whatsapp_tenant(db)
    accounts_total = db.execute(select(WhatsAppAccount).where(WhatsAppAccount.tenant_id == tenant.id)).scalars().all()
    configured_slug = str(settings.sales_outreach_sender_tenant_slug or "").strip()
    return {
        "tenant_id": str(tenant.id),
        "tenant_slug": tenant.slug,
        "tenant_trade_name": tenant.trade_name,
        "tenant_legal_name": tenant.legal_name,
        "accounts_total": len(accounts_total),
        "configured_sender_slug": configured_slug or tenant.slug,
        "uses_default_sender_slug": not bool(configured_slug),
        "display_name": str(settings.sales_outreach_display_name or "ClinicFlux AI").strip() or "ClinicFlux AI",
    }


@router.get("/whatsapp/accounts", dependencies=[Depends(require_roles("admin_platform", "sales_admin", "sales_viewer"))])
def list_system_whatsapp_accounts(db: Session = Depends(get_db)):
    tenant = _system_whatsapp_tenant(db)
    rows = db.execute(
        select(WhatsAppAccount)
        .where(WhatsAppAccount.tenant_id == tenant.id)
        .order_by(WhatsAppAccount.created_at.desc())
    ).scalars().all()
    return {"data": [_serialize_account(item) for item in rows]}


@router.delete("/whatsapp/accounts/{account_id}")
def delete_system_whatsapp_account(
    account_id: UUID,
    principal: Principal = Depends(require_roles("admin_platform", "sales_admin")),
    db: Session = Depends(get_db),
):
    tenant = _system_whatsapp_tenant(db)
    account = db.scalar(
        select(WhatsAppAccount).where(
            WhatsAppAccount.id == account_id,
            WhatsAppAccount.tenant_id == tenant.id,
        )
    )
    if not account:
        raise ApiError(
            status_code=404,
            code="SYSTEM_WHATSAPP_ACCOUNT_NOT_FOUND",
            message="Conta WhatsApp do sistema nao encontrada",
        )

    cleared_demo_assignments = 0
    account_id_text = str(account.id)
    prospects = db.execute(select(ProspectAccount)).scalars().all()
    for prospect in prospects:
        snapshot = dict(prospect.proposal_snapshot or {})
        demo_whatsapp = snapshot.get("demo_whatsapp") if isinstance(snapshot.get("demo_whatsapp"), dict) else {}
        assigned_account_id = str(demo_whatsapp.get("account_id") or "").strip()
        if assigned_account_id != account_id_text:
            continue
        snapshot["demo_whatsapp"] = {"account_id": None}
        prospect.proposal_snapshot = snapshot
        db.add(prospect)
        cleared_demo_assignments += 1

    removed_active_account = bool(account.is_active)
    removed_account_payload = _serialize_account(account)
    db.delete(account)
    db.commit()

    record_audit(
        db,
        action="admin_platform.whatsapp.account.delete",
        entity_type="whatsapp_account",
        entity_id=account_id_text,
        tenant_id=tenant.id,
        user_id=principal.user.id,
        metadata={
            "scope": "system",
            "tenant_slug": tenant.slug,
            "provider_name": removed_account_payload["provider_name"],
            "phone_number_id": removed_account_payload["phone_number_id"],
            "removed_active_account": removed_active_account,
            "cleared_demo_assignments": cleared_demo_assignments,
        },
    )

    return {
        "status": "deleted",
        "id": account_id_text,
        "removed_active_account": removed_active_account,
        "cleared_demo_assignments": cleared_demo_assignments,
    }


@router.get("/whatsapp/health", dependencies=[Depends(require_roles("admin_platform", "sales_admin", "sales_viewer"))])
def get_system_whatsapp_health(db: Session = Depends(get_db)):
    return _health_payload(db)


@router.post("/whatsapp/accounts")
def create_system_whatsapp_account(
    payload: dict,
    principal: Principal = Depends(require_roles("admin_platform", "sales_admin")),
    db: Session = Depends(get_db),
):
    tenant = _system_whatsapp_tenant(db)
    provider_name = normalize_whatsapp_provider_name(payload.get("provider_name"))

    required = ["phone_number_id", "business_account_id", "access_token"]
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ApiError(
            status_code=400,
            code="SYSTEM_WHATSAPP_ACCOUNT_INVALID",
            message=f"Campos obrigatorios ausentes: {', '.join(missing)}",
        )

    issues = whatsapp_account_issues(
        provider_name=provider_name,
        phone_number_id=payload.get("phone_number_id"),
        business_account_id=payload.get("business_account_id"),
        access_token=payload.get("access_token"),
    )
    if issues:
        raise ApiError(
            status_code=400,
            code="SYSTEM_WHATSAPP_ACCOUNT_INVALID",
            message="Dados do WhatsApp do sistema invalidos para envio real.",
            details={"issues": issues},
        )

    current_active_accounts = db.execute(
        select(WhatsAppAccount).where(
            WhatsAppAccount.tenant_id == tenant.id,
            WhatsAppAccount.is_active.is_(True),
        )
    ).scalars().all()
    for current in current_active_accounts:
        current.is_active = False
        db.add(current)

    item = WhatsAppAccount(
        tenant_id=tenant.id,
        unit_id=None,
        provider_name=provider_name,
        phone_number_id=str(payload["phone_number_id"]).strip(),
        business_account_id=str(payload["business_account_id"]).strip(),
        display_phone=(str(payload.get("display_phone") or "").strip() or None),
        access_token_encrypted=str(payload["access_token"]).strip(),
        verify_token=str(payload.get("verify_token") or settings.whatsapp_verify_token or "verify-token-dev").strip(),
        webhook_secret=(str(payload.get("webhook_secret") or "").strip() or None),
        is_active=True,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    record_audit(
        db,
        action="admin_platform.whatsapp.account.create",
        entity_type="whatsapp_account",
        entity_id=str(item.id),
        tenant_id=tenant.id,
        user_id=principal.user.id,
        metadata={
            "scope": "system",
            "tenant_slug": tenant.slug,
            "provider_name": item.provider_name,
            "phone_number_id": item.phone_number_id,
        },
    )

    return _serialize_account(item)


@router.post("/whatsapp/test")
def test_system_whatsapp_connection(
    payload: dict,
    principal: Principal = Depends(require_roles("admin_platform", "sales_admin")),
    db: Session = Depends(get_db),
):
    tenant = _system_whatsapp_tenant(db)
    account = None
    account_id = payload.get("account_id")
    if account_id:
        account = db.scalar(
            select(WhatsAppAccount).where(
                WhatsAppAccount.id == account_id,
                WhatsAppAccount.tenant_id == tenant.id,
            )
        )
        if not account:
            raise ApiError(status_code=404, code="SYSTEM_WHATSAPP_ACCOUNT_NOT_FOUND", message="Conta WhatsApp do sistema nao encontrada")

    provider_name = normalize_whatsapp_provider_name(payload.get("provider_name") or (account.provider_name if account else None))
    phone_number_id = payload.get("phone_number_id") or (account.phone_number_id if account else None)
    business_account_id = payload.get("business_account_id") or (account.business_account_id if account else None)
    access_token = payload.get("access_token") or (account.access_token_encrypted if account else None)
    display_phone = payload.get("display_phone") or (account.display_phone if account else None)

    missing = [
        key
        for key, value in {
            "phone_number_id": phone_number_id,
            "business_account_id": business_account_id,
            "access_token": access_token,
        }.items()
        if not value
    ]
    if missing:
        raise ApiError(
            status_code=400,
            code="SYSTEM_WHATSAPP_TEST_INVALID",
            message=f"Campos obrigatorios ausentes para teste: {', '.join(missing)}",
        )

    issues = whatsapp_account_issues(
        provider_name=provider_name,
        phone_number_id=phone_number_id,
        business_account_id=business_account_id,
        access_token=access_token,
    )
    if issues:
        raise ApiError(
            status_code=400,
            code="SYSTEM_WHATSAPP_TEST_INVALID",
            message="Credenciais invalidas para validar o WhatsApp do sistema.",
            details={"issues": issues},
        )

    provider = _provider_instance(provider_name, str(business_account_id))

    try:
        result = provider.test_connection(
            phone_number_id=str(phone_number_id),
            business_account_id=str(business_account_id),
            access_token=str(access_token),
        )
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response else 502
        hint = _provider_validation_hint(provider_name)
        detail = _provider_validation_detail(exc)
        raise ApiError(
            status_code=400,
            code="SYSTEM_WHATSAPP_TEST_FAILED",
            message=(
                f"Falha ao validar o WhatsApp do sistema no provedor configurado. {hint}"
                + (f" Detalhe do provedor: {detail}" if detail else "")
            ),
            details={"status_code": status_code, "error": str(exc), "provider_detail": detail, "provider_hint": hint},
        ) from exc
    except Exception as exc:
        hint = _provider_validation_hint(provider_name)
        raise ApiError(
            status_code=400,
            code="SYSTEM_WHATSAPP_TEST_FAILED",
            message=f"Falha inesperada ao validar o WhatsApp do sistema. {hint}",
            details={"error": str(exc), "provider_hint": hint},
        ) from exc

    phone_data = result.get("phone") if isinstance(result, dict) else {}
    connected_number = None
    if isinstance(phone_data, dict):
        connected_number = phone_data.get("display_phone_number")
    if provider_name in {"infobip", "twilio"}:
        connected_number = (result.get("sender") if isinstance(result, dict) else None) or display_phone or phone_number_id

    record_audit(
        db,
        action="admin_platform.whatsapp.account.test",
        entity_type="whatsapp_account",
        entity_id=str(account.id) if account else None,
        tenant_id=tenant.id,
        user_id=principal.user.id,
        metadata={
            "scope": "system",
            "tenant_slug": tenant.slug,
            "provider_name": provider_name,
            "phone_number_id": phone_number_id,
            "business_account_id": business_account_id,
            "integration_valid": True,
        },
    )

    return {
        "status": "conectado",
        "webhook_status": "ativo",
        "integration_valid": True,
        "connected_number": connected_number or display_phone or "Numero nao informado",
        "last_event_at": datetime.now(UTC).isoformat(),
        "message": (
            "Conexao validada com sucesso na Infobip API"
            if provider_name == "infobip"
            else "Conexao validada com sucesso na Twilio API"
            if provider_name == "twilio"
            else "Conexao validada com sucesso na Meta Cloud API"
        ),
    }

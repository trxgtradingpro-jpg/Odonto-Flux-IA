import json
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    Principal,
    get_current_principal,
    get_tenant_id,
    require_roles,
)
from app.core.config import settings
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.models import Tenant, TenantPlan
from app.services.audit_service import record_audit
from app.services.billing_gateway_service import (
    create_checkout_session,
    create_customer_portal_link,
    handle_stripe_event,
    list_invoice_events,
    run_delinquency_check,
    verify_stripe_signature,
)
from app.services.subscription_service import billing_summary, get_tenant_and_plan

router = APIRouter(prefix="/billing", tags=["billing"])


class BillingUpgradeInput(BaseModel):
    plan_code: str = Field(min_length=2)


@router.get("/summary")
def summary(db: Session = Depends(get_db), tenant_id=Depends(get_tenant_id)):
    return billing_summary(db, tenant_id)


@router.get("/plans")
def list_plans(
    db: Session = Depends(get_db),
    _: Principal = Depends(get_current_principal),
):
    plans = (
        db.execute(
            select(TenantPlan)
            .where(TenantPlan.is_active.is_(True))
            .order_by(TenantPlan.price_cents.asc())
        )
        .scalars()
        .all()
    )
    return {
        "data": [
            {
                "id": str(item.id),
                "code": item.code,
                "name": item.name,
                "max_users": item.max_users,
                "max_units": item.max_units,
                "max_monthly_messages": item.max_monthly_messages,
                "price_cents": item.price_cents,
                "currency": item.currency,
                "features": item.features,
            }
            for item in plans
        ]
    }


def _resolve_target_plan(db: Session, payload: BillingUpgradeInput) -> TenantPlan:
    target_plan = db.scalar(
        select(TenantPlan).where(
            TenantPlan.code == payload.plan_code,
            TenantPlan.is_active.is_(True),
        )
    )
    if not target_plan:
        raise ApiError(
            status_code=404,
            code="PLAN_NOT_FOUND",
            message="Plano informado nao encontrado",
        )
    return target_plan


@router.post("/checkout")
def checkout_plan(
    payload: BillingUpgradeInput,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    tenant, current_plan = get_tenant_and_plan(db, tenant_id)
    target_plan = _resolve_target_plan(db, payload)

    if current_plan and current_plan.code == target_plan.code and tenant.subscription_status == "active":
        raise ApiError(
            status_code=400,
            code="PLAN_ALREADY_ACTIVE",
            message="Tenant ja esta no plano selecionado",
        )

    checkout = create_checkout_session(
        db,
        tenant=tenant,
        plan=target_plan,
        customer_email=principal.user.email,
    )
    db.commit()
    db.refresh(tenant)

    record_audit(
        db,
        action="billing.checkout.create",
        entity_type="tenant",
        entity_id=str(tenant.id),
        tenant_id=tenant.id,
        user_id=principal.user.id,
        metadata={
            "from_plan": current_plan.code if current_plan else None,
            "to_plan": target_plan.code,
            "provider": checkout["provider"],
            "requires_payment": checkout["requires_payment"],
        },
    )

    message = (
        "Checkout criado. Conclua o pagamento para ativar o plano."
        if checkout["requires_payment"]
        else "Plano atualizado com sucesso."
    )
    return {
        "message": message,
        "tenant_id": str(tenant.id),
        "from_plan": current_plan.code if current_plan else None,
        "to_plan": target_plan.code,
        "subscription_status": tenant.subscription_status,
        "requires_payment": checkout["requires_payment"],
        "checkout_url": checkout["checkout_url"],
        "provider_session_id": checkout["provider_session_id"],
        "provider": checkout["provider"],
    }


@router.post("/upgrade")
def upgrade_plan(
    payload: BillingUpgradeInput,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    # Endpoint de compatibilidade: upgrade agora inicia checkout.
    return checkout_plan(
        payload=payload,
        db=db,
        tenant_id=tenant_id,
        principal=principal,
    )


@router.get("/invoices")
def invoices(
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
):
    return {"data": list_invoice_events(db, tenant_id, limit=limit)}


@router.get("/portal")
def customer_portal(
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
):
    return create_customer_portal_link(db, tenant_id)


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: Session = Depends(get_db),
):
    payload_raw = await request.body()
    try:
        payload = json.loads(payload_raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ApiError(
            status_code=400,
            code="BILLING_WEBHOOK_INVALID_JSON",
            message="Payload de webhook invalido",
        ) from exc

    if settings.billing_provider.lower() == "stripe":
        if not verify_stripe_signature(payload_raw, stripe_signature):
            raise ApiError(
                status_code=400,
                code="BILLING_WEBHOOK_INVALID_SIGNATURE",
                message="Assinatura do webhook invalida",
            )

    result = handle_stripe_event(db, payload)
    db.commit()
    tenant_id = None
    if isinstance(result, dict) and result.get("tenant_id"):
        try:
            tenant_id = UUID(str(result.get("tenant_id")))
        except ValueError:
            tenant_id = None
    record_audit(
        db,
        action="billing.webhook.process",
        entity_type="webhook",
        entity_id=result.get("provider_session_id") if isinstance(result, dict) else None,
        tenant_id=tenant_id,
        user_id=None,
        metadata={"type": payload.get("type"), "result": result},
    )
    return {"received": True, "result": result}


@router.post(
    "/delinquency/run",
    dependencies=[Depends(require_roles("admin_platform"))],
)
def run_delinquency_scan(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    result = run_delinquency_check(db)
    record_audit(
        db,
        action="billing.delinquency.scan",
        entity_type="platform",
        entity_id=None,
        tenant_id=None,
        user_id=principal.user.id,
        metadata=result,
    )
    return result


@router.post("/status/{status}")
def update_subscription_status(
    status: str,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    allowed = {"trialing", "active", "past_due", "blocked", "suspended", "canceled"}
    if status not in allowed:
        raise ApiError(
            status_code=400,
            code="SUBSCRIPTION_STATUS_INVALID",
            message="Status de assinatura invalido",
        )

    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise ApiError(
            status_code=404,
            code="TENANT_NOT_FOUND",
            message="Tenant nao encontrado",
        )

    previous = tenant.subscription_status
    tenant.subscription_status = status
    tenant.is_active = status not in {"suspended", "canceled"}
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    record_audit(
        db,
        action="billing.subscription_status.update",
        entity_type="tenant",
        entity_id=str(tenant.id),
        tenant_id=tenant.id,
        user_id=principal.user.id,
        metadata={"from": previous, "to": status},
    )

    return {
        "tenant_id": str(tenant.id),
        "previous_status": previous,
        "current_status": tenant.subscription_status,
        "is_active": tenant.is_active,
    }

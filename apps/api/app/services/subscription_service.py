from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.models import Message, Tenant, TenantPlan, Unit, User
from app.services.billing_gateway_service import (
    get_billing_state,
    get_delinquency_snapshot,
    list_invoice_events,
)

BLOCKED_SUBSCRIPTION_STATUSES = {'blocked', 'suspended', 'canceled'}


def _month_start_utc(now: datetime) -> datetime:
    return datetime(now.year, now.month, 1, tzinfo=UTC)


def get_tenant_and_plan(db: Session, tenant_id: UUID) -> tuple[Tenant, TenantPlan | None]:
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise ApiError(status_code=404, code='TENANT_NOT_FOUND', message='Tenant nao encontrado')
    plan = db.get(TenantPlan, tenant.plan_id) if tenant.plan_id else None
    return tenant, plan


def get_usage_snapshot(db: Session, tenant_id: UUID) -> dict[str, int]:
    now = datetime.now(UTC)
    return {
        'users': db.scalar(select(func.count(User.id)).where(User.tenant_id == tenant_id)) or 0,
        'units': db.scalar(select(func.count(Unit.id)).where(Unit.tenant_id == tenant_id)) or 0,
        'monthly_messages': db.scalar(
            select(func.count(Message.id)).where(
                Message.tenant_id == tenant_id,
                Message.created_at >= _month_start_utc(now),
            )
        )
        or 0,
    }


def enforce_subscription_active(db: Session, tenant_id: UUID) -> tuple[Tenant, TenantPlan | None]:
    tenant, plan = get_tenant_and_plan(db, tenant_id)
    if not tenant.is_active:
        raise ApiError(
            status_code=403,
            code='TENANT_INACTIVE',
            message='Tenant inativo. Reative a conta para continuar operando.',
        )
    if tenant.subscription_status in BLOCKED_SUBSCRIPTION_STATUSES:
        raise ApiError(
            status_code=402,
            code='SUBSCRIPTION_BLOCKED',
            message='Assinatura bloqueada. Regularize o plano para continuar operando.',
        )
    return tenant, plan


def enforce_plan_limit(db: Session, tenant_id: UUID, *, resource: str, increment: int = 1) -> None:
    _, plan = enforce_subscription_active(db, tenant_id)
    if not plan:
        raise ApiError(
            status_code=400,
            code='PLAN_REQUIRED',
            message='Tenant sem plano vinculado. Defina um plano para continuar.',
        )

    usage = get_usage_snapshot(db, tenant_id)
    limits = {
        'users': plan.max_users,
        'units': plan.max_units,
        'monthly_messages': plan.max_monthly_messages,
    }

    if resource not in limits:
        raise ApiError(status_code=400, code='PLAN_RESOURCE_INVALID', message='Recurso de limite invalido')

    current = usage.get(resource, 0)
    limit = limits[resource]
    if limit is not None and current + increment > limit:
        raise ApiError(
            status_code=402,
            code='PLAN_LIMIT_REACHED',
            message=f'Limite do plano atingido para {resource}',
            details={
                'resource': resource,
                'current': current,
                'limit': limit,
                'required': current + increment,
            },
        )


def billing_summary(db: Session, tenant_id: UUID) -> dict:
    tenant, plan = get_tenant_and_plan(db, tenant_id)
    usage = get_usage_snapshot(db, tenant_id)
    billing_state = get_billing_state(db, tenant_id)
    delinquency = get_delinquency_snapshot(db, tenant_id, tenant=tenant)
    invoices = list_invoice_events(db, tenant_id, limit=12)
    limits = {
        'users': plan.max_users if plan else None,
        'units': plan.max_units if plan else None,
        'monthly_messages': plan.max_monthly_messages if plan else None,
    }

    usage_percent = {}
    for key, current in usage.items():
        limit = limits.get(key)
        usage_percent[key] = round((current / limit) * 100, 2) if limit and limit > 0 else 0

    return {
        'tenant_id': str(tenant.id),
        'tenant_name': tenant.trade_name,
        'subscription_status': tenant.subscription_status,
        'is_active': tenant.is_active,
        'trial_ends_at': tenant.trial_ends_at.isoformat() if tenant.trial_ends_at else None,
        'plan': {
            'code': plan.code if plan else 'sem_plano',
            'name': plan.name if plan else 'Sem plano',
            'price_cents': plan.price_cents if plan else 0,
            'currency': plan.currency if plan else 'BRL',
        },
        'billing': {
            'provider': billing_state.get('provider'),
            'customer_id': billing_state.get('customer_id'),
            'last_paid_at': billing_state.get('last_paid_at'),
            'last_failed_at': billing_state.get('last_failed_at'),
            'next_due_at': billing_state.get('next_due_at'),
            'grace_days': billing_state.get('grace_days'),
            'is_delinquent': delinquency.get('is_delinquent'),
            'days_overdue': delinquency.get('days_overdue'),
            'recommended_action': delinquency.get('recommended_action'),
        },
        'recent_invoices': invoices,
        'usage': usage,
        'limits': limits,
        'usage_percent': usage_percent,
    }

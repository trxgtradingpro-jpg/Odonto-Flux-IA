from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, require_roles
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.models import Tenant, TenantPlan
from app.schemas.tenant import TenantCreate, TenantOutput, TenantUpdate
from app.services.audit_service import record_audit

router = APIRouter(prefix='/tenants', tags=['tenants'])


@router.get('', dependencies=[Depends(require_roles('admin_platform'))])
def list_tenants(
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = None,
):
    stmt = select(Tenant)
    if search:
        stmt = stmt.where(Tenant.trade_name.ilike(f'%{search}%'))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    data = db.execute(stmt.order_by(Tenant.created_at.desc()).offset(offset).limit(limit)).scalars().all()
    return {'data': [TenantOutput.model_validate(item, from_attributes=True).model_dump() for item in data], 'meta': {'total': total, 'limit': limit, 'offset': offset}}


@router.post('', response_model=TenantOutput, dependencies=[Depends(require_roles('admin_platform'))])
def create_tenant(payload: TenantCreate, db: Session = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    existing = db.scalar(select(Tenant).where(Tenant.slug == payload.slug))
    if existing:
        raise ApiError(status_code=409, code='TENANT_SLUG_EXISTS', message='Slug ja utilizado')

    plan = db.scalar(select(TenantPlan).where(TenantPlan.code == payload.plan_code))
    if not plan:
        raise ApiError(status_code=400, code='PLAN_NOT_FOUND', message='Plano informado nao existe')

    tenant = Tenant(
        legal_name=payload.legal_name,
        trade_name=payload.trade_name,
        slug=payload.slug,
        plan_id=plan.id,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    record_audit(
        db,
        action='tenant.create',
        entity_type='tenant',
        entity_id=str(tenant.id),
        tenant_id=tenant.id,
        user_id=principal.user.id,
        metadata={'slug': tenant.slug, 'plan': payload.plan_code},
    )
    return TenantOutput.model_validate(tenant, from_attributes=True)


@router.get('/{tenant_id}', response_model=TenantOutput, dependencies=[Depends(require_roles('admin_platform'))])
def get_tenant(tenant_id: str, db: Session = Depends(get_db)):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise ApiError(status_code=404, code='TENANT_NOT_FOUND', message='Tenant nao encontrado')
    return TenantOutput.model_validate(tenant, from_attributes=True)


@router.patch('/{tenant_id}', response_model=TenantOutput, dependencies=[Depends(require_roles('admin_platform'))])
def update_tenant(
    tenant_id: str,
    payload: TenantUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise ApiError(status_code=404, code='TENANT_NOT_FOUND', message='Tenant nao encontrado')

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(tenant, key, value)

    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    record_audit(
        db,
        action='tenant.update',
        entity_type='tenant',
        entity_id=str(tenant.id),
        tenant_id=tenant.id,
        user_id=principal.user.id,
        metadata=updates,
    )

    return TenantOutput.model_validate(tenant, from_attributes=True)

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.models import Unit
from app.schemas.tenant import UnitCreate, UnitOutput, UnitUpdate
from app.services.audit_service import record_audit
from app.services.subscription_service import enforce_plan_limit

router = APIRouter(prefix='/units', tags=['units'])


@router.get('')
def list_units(
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(Unit).where(Unit.tenant_id == tenant_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Unit.created_at.desc()).offset(offset).limit(limit)).scalars().all()
    return {'data': [UnitOutput.model_validate(item, from_attributes=True).model_dump() for item in rows], 'meta': {'total': total, 'limit': limit, 'offset': offset}}


@router.post('', response_model=UnitOutput)
def create_unit(
    payload: UnitCreate,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    enforce_plan_limit(db, tenant_id, resource='units', increment=1)

    exists = db.scalar(select(Unit).where(Unit.tenant_id == tenant_id, Unit.code == payload.code))
    if exists:
        raise ApiError(status_code=409, code='UNIT_CODE_EXISTS', message='Codigo da unidade ja existe')

    item = Unit(tenant_id=tenant_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    record_audit(
        db,
        action='unit.create',
        entity_type='unit',
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'code': item.code},
    )
    return UnitOutput.model_validate(item, from_attributes=True)


@router.patch('/{unit_id}', response_model=UnitOutput)
def update_unit(
    unit_id: str,
    payload: UnitUpdate,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    item = db.scalar(select(Unit).where(Unit.id == unit_id, Unit.tenant_id == tenant_id))
    if not item:
        raise ApiError(status_code=404, code='UNIT_NOT_FOUND', message='Unidade nao encontrada')

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(item, key, value)
    db.add(item)
    db.commit()
    db.refresh(item)

    record_audit(
        db,
        action='unit.update',
        entity_type='unit',
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata=updates,
    )
    return UnitOutput.model_validate(item, from_attributes=True)

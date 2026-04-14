from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.models import Professional, Unit
from app.schemas.professional import ProfessionalCreate, ProfessionalOutput, ProfessionalUpdate
from app.services.audit_service import record_audit

router = APIRouter(prefix="/professionals", tags=["professionals"])


@router.get("")
def list_professionals(
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    limit: int = Query(default=50, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    unit_id: UUID | None = None,
    active_only: bool = Query(default=False),
):
    stmt = select(Professional).where(Professional.tenant_id == tenant_id)
    if unit_id:
        stmt = stmt.where(Professional.unit_id == unit_id)
    if active_only:
        stmt = stmt.where(Professional.is_active.is_(True))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(Professional.full_name.asc()).offset(offset).limit(limit)
    ).scalars().all()
    return {
        "data": [
            ProfessionalOutput.model_validate(item, from_attributes=True).model_dump()
            for item in rows
        ],
        "meta": {"total": total, "limit": limit, "offset": offset},
    }


@router.post("", response_model=ProfessionalOutput)
def create_professional(
    payload: ProfessionalCreate,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    if payload.unit_id:
        unit = db.scalar(select(Unit).where(Unit.id == payload.unit_id, Unit.tenant_id == tenant_id))
        if not unit:
            raise ApiError(status_code=404, code="UNIT_NOT_FOUND", message="Unidade nao encontrada")

    item = Professional(tenant_id=tenant_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)

    record_audit(
        db,
        action="professional.create",
        entity_type="professional",
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={"unit_id": str(item.unit_id) if item.unit_id else None},
    )
    return ProfessionalOutput.model_validate(item, from_attributes=True)


@router.patch("/{professional_id}", response_model=ProfessionalOutput)
def update_professional(
    professional_id: UUID,
    payload: ProfessionalUpdate,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    item = db.scalar(
        select(Professional).where(
            Professional.id == professional_id,
            Professional.tenant_id == tenant_id,
        )
    )
    if not item:
        raise ApiError(status_code=404, code="PROFESSIONAL_NOT_FOUND", message="Profissional nao encontrado")

    updates = payload.model_dump(exclude_unset=True)
    unit_id = updates.get("unit_id")
    if unit_id:
        unit = db.scalar(select(Unit).where(Unit.id == unit_id, Unit.tenant_id == tenant_id))
        if not unit:
            raise ApiError(status_code=404, code="UNIT_NOT_FOUND", message="Unidade nao encontrada")

    for key, value in updates.items():
        setattr(item, key, value)
    db.add(item)
    db.commit()
    db.refresh(item)

    record_audit(
        db,
        action="professional.update",
        entity_type="professional",
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata=updates,
    )
    return ProfessionalOutput.model_validate(item, from_attributes=True)

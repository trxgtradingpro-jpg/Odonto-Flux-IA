from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.models import Appointment, Professional, Unit
from app.schemas.professional import ProfessionalCreate, ProfessionalOutput, ProfessionalUpdate
from app.services.appointment_validation_service import (
    backfill_missing_appointment_professionals,
    rebalance_future_unit_appointments,
)
from app.services.audit_service import record_audit

router = APIRouter(prefix="/professionals", tags=["professionals"])


def _normalize_professional_payload(raw_payload: dict) -> dict:
    data = dict(raw_payload)
    specialty = str(data.get("specialty") or "").strip() or None
    procedures = [str(item or "").strip() for item in (data.get("procedures") or []) if str(item or "").strip()]
    if specialty and specialty not in procedures:
        procedures.append(specialty)
    data["specialty"] = specialty
    data["procedures"] = procedures
    return data


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

    item = Professional(tenant_id=tenant_id, **_normalize_professional_payload(payload.model_dump()))
    db.add(item)
    db.commit()
    db.refresh(item)
    backfill_summary = (
        backfill_missing_appointment_professionals(
            db,
            tenant_id=tenant_id,
            unit_id=item.unit_id,
        )
        if item.is_active
        else {"assigned": 0, "unresolved": 0}
    )
    rebalance_summary = (
        rebalance_future_unit_appointments(
            db,
            tenant_id=tenant_id,
            unit_id=item.unit_id,
        )
        if item.is_active and item.unit_id
        else {"moved": 0, "unchanged": 0, "unresolved": 0}
    )

    record_audit(
        db,
        action="professional.create",
        entity_type="professional",
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={
            "unit_id": str(item.unit_id) if item.unit_id else None,
            "backfill_assigned": int(backfill_summary.get("assigned", 0)),
            "backfill_unresolved": int(backfill_summary.get("unresolved", 0)),
            "rebalance_moved": int(rebalance_summary.get("moved", 0)),
            "rebalance_unchanged": int(rebalance_summary.get("unchanged", 0)),
            "rebalance_unresolved": int(rebalance_summary.get("unresolved", 0)),
        },
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

    updates = _normalize_professional_payload(payload.model_dump(exclude_unset=True))
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
    backfill_summary = (
        backfill_missing_appointment_professionals(
            db,
            tenant_id=tenant_id,
            unit_id=item.unit_id,
        )
        if item.is_active
        else {"assigned": 0, "unresolved": 0}
    )
    rebalance_summary = (
        rebalance_future_unit_appointments(
            db,
            tenant_id=tenant_id,
            unit_id=item.unit_id,
        )
        if item.is_active and item.unit_id
        else {"moved": 0, "unchanged": 0, "unresolved": 0}
    )

    record_audit(
        db,
        action="professional.update",
        entity_type="professional",
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={
            **updates,
            "backfill_assigned": int(backfill_summary.get("assigned", 0)),
            "backfill_unresolved": int(backfill_summary.get("unresolved", 0)),
            "rebalance_moved": int(rebalance_summary.get("moved", 0)),
            "rebalance_unchanged": int(rebalance_summary.get("unchanged", 0)),
            "rebalance_unresolved": int(rebalance_summary.get("unresolved", 0)),
        },
    )
    return ProfessionalOutput.model_validate(item, from_attributes=True)


@router.delete("/{professional_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_professional(
    professional_id: UUID,
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

    reassigned_appointments = db.execute(
        update(Appointment)
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.professional_id == professional_id,
        )
        .values(professional_id=None, updated_at=datetime.now(UTC))
    ).rowcount or 0

    professional_name = item.full_name
    professional_unit_id = item.unit_id
    db.delete(item)
    db.commit()
    backfill_summary = backfill_missing_appointment_professionals(
        db,
        tenant_id=tenant_id,
        unit_id=professional_unit_id,
    )
    rebalance_summary = (
        rebalance_future_unit_appointments(
            db,
            tenant_id=tenant_id,
            unit_id=professional_unit_id,
        )
        if professional_unit_id
        else {"moved": 0, "unchanged": 0, "unresolved": 0}
    )

    record_audit(
        db,
        action="professional.delete",
        entity_type="professional",
        entity_id=str(professional_id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={
            "full_name": professional_name,
            "reassigned_appointments": int(reassigned_appointments),
            "backfill_assigned": int(backfill_summary.get("assigned", 0)),
            "backfill_unresolved": int(backfill_summary.get("unresolved", 0)),
            "rebalance_moved": int(rebalance_summary.get("moved", 0)),
            "rebalance_unchanged": int(rebalance_summary.get("unchanged", 0)),
            "rebalance_unresolved": int(rebalance_summary.get("unresolved", 0)),
        },
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)

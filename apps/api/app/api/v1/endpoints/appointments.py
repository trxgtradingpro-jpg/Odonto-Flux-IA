from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.models import Appointment, AppointmentEvent, Professional
from app.schemas.appointment import AppointmentCreate, AppointmentOutput, AppointmentUpdate
from app.services.appointment_validation_service import (
    ACTIVE_APPOINTMENT_STATUSES,
    find_professional_conflict,
)
from app.services.audit_service import record_audit
from app.services.automation_service import emit_event

router = APIRouter(prefix='/appointments', tags=['appointments'])


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def _target_status_for_create(payload: AppointmentCreate) -> str:
    # Creation always starts as scheduled in the current API contract.
    return "agendada"


def _target_status_for_update(appointment: Appointment, updates: dict[str, Any]) -> str:
    raw_status = updates.get("status", appointment.status)
    return str(raw_status or "").strip().lower()


@router.get('')
def list_appointments(
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    limit: int = Query(default=30, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status: str | None = None,
):
    stmt = select(Appointment).where(Appointment.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(Appointment.status == status)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Appointment.starts_at.asc()).offset(offset).limit(limit)).scalars().all()
    return {'data': [AppointmentOutput.model_validate(item, from_attributes=True).model_dump() for item in rows], 'meta': {'total': total, 'limit': limit, 'offset': offset}}


@router.post('', response_model=AppointmentOutput)
def create_appointment(
    payload: AppointmentCreate,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    target_status = _target_status_for_create(payload)

    if payload.professional_id:
        professional = db.scalar(
            select(Professional).where(
                Professional.id == payload.professional_id,
                Professional.tenant_id == tenant_id,
                Professional.is_active.is_(True),
            )
        )
        if not professional:
            raise ApiError(status_code=404, code="PROFESSIONAL_NOT_FOUND", message="Profissional nao encontrado")
        if professional.unit_id and professional.unit_id != payload.unit_id:
            raise ApiError(
                status_code=409,
                code="PROFESSIONAL_UNIT_MISMATCH",
                message="Profissional nao atende na unidade selecionada",
            )

        if target_status in ACTIVE_APPOINTMENT_STATUSES:
            conflict = find_professional_conflict(
                db,
                tenant_id=tenant_id,
                professional_id=payload.professional_id,
                starts_at=payload.starts_at,
                ends_at=payload.ends_at,
            )
            if conflict:
                raise ApiError(
                    status_code=409,
                    code="PROFESSIONAL_SLOT_CONFLICT",
                    message="Profissional ja possui consulta nesse horario",
                    details={
                        "conflict_appointment_id": str(conflict.id),
                        "professional_id": str(payload.professional_id),
                        "starts_at": payload.starts_at.isoformat(),
                    },
                )

    appointment = Appointment(
        tenant_id=tenant_id,
        patient_id=payload.patient_id,
        unit_id=payload.unit_id,
        professional_id=payload.professional_id,
        procedure_type=payload.procedure_type,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        origin=payload.origin,
        notes=payload.notes,
    )
    db.add(appointment)
    db.flush()

    db.add(
        AppointmentEvent(
            tenant_id=tenant_id,
            appointment_id=appointment.id,
            event_type='created',
            to_status=appointment.status,
            metadata_json={'origin': appointment.origin},
            created_by_user_id=principal.user.id,
        )
    )

    db.commit()
    db.refresh(appointment)

    emit_event(
        db,
        tenant_id=tenant_id,
        event_key='consulta_criada',
        payload={
            'appointment_id': str(appointment.id),
            'patient_id': str(appointment.patient_id),
            'starts_at': appointment.starts_at.isoformat(),
            'status': appointment.status,
        },
    )

    record_audit(
        db,
        action='appointment.create',
        entity_type='appointment',
        entity_id=str(appointment.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'status': appointment.status},
    )

    return AppointmentOutput.model_validate(appointment, from_attributes=True)


@router.patch('/{appointment_id}', response_model=AppointmentOutput)
def update_appointment(
    appointment_id: str,
    payload: AppointmentUpdate,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    appointment = db.scalar(
        select(Appointment).where(Appointment.id == appointment_id, Appointment.tenant_id == tenant_id)
    )
    if not appointment:
        raise ApiError(status_code=404, code='APPOINTMENT_NOT_FOUND', message='Consulta nao encontrada')

    previous_status = str(appointment.status)
    updates = payload.model_dump(exclude_unset=True)
    safe_updates = _json_safe(updates)

    if "unit_id" in updates and updates["unit_id"] is None:
        raise ApiError(
            status_code=422,
            code="UNIT_ID_REQUIRED",
            message="Unidade nao pode ser vazia",
        )
    if "starts_at" in updates and updates["starts_at"] is None:
        raise ApiError(
            status_code=422,
            code="STARTS_AT_REQUIRED",
            message="Horario inicial nao pode ser vazio",
        )

    target_unit_id = updates.get("unit_id", appointment.unit_id)
    target_professional_id = (
        updates["professional_id"] if "professional_id" in updates else appointment.professional_id
    )
    target_starts_at = updates.get("starts_at", appointment.starts_at)
    target_ends_at = updates.get("ends_at", appointment.ends_at)
    target_status = _target_status_for_update(appointment, updates)

    if target_professional_id:
        professional = db.scalar(
            select(Professional).where(
                Professional.id == target_professional_id,
                Professional.tenant_id == tenant_id,
                Professional.is_active.is_(True),
            )
        )
        if not professional:
            raise ApiError(status_code=404, code="PROFESSIONAL_NOT_FOUND", message="Profissional nao encontrado")

        if professional.unit_id and professional.unit_id != target_unit_id:
            raise ApiError(
                status_code=409,
                code="PROFESSIONAL_UNIT_MISMATCH",
                message="Profissional nao atende na unidade selecionada",
            )

        if target_status in ACTIVE_APPOINTMENT_STATUSES:
            conflict = find_professional_conflict(
                db,
                tenant_id=tenant_id,
                professional_id=target_professional_id,
                starts_at=target_starts_at,
                ends_at=target_ends_at,
                exclude_appointment_id=appointment.id,
            )
            if conflict:
                raise ApiError(
                    status_code=409,
                    code="PROFESSIONAL_SLOT_CONFLICT",
                    message="Profissional ja possui consulta nesse horario",
                    details={
                        "conflict_appointment_id": str(conflict.id),
                        "professional_id": str(target_professional_id),
                        "starts_at": target_starts_at.isoformat() if target_starts_at else None,
                    },
                )

    for key, value in updates.items():
        setattr(appointment, key, value)

    if updates.get('confirmation_status') == 'confirmada' and not appointment.confirmed_at:
        appointment.confirmed_at = datetime.now(UTC)

    db.add(appointment)
    db.flush()

    db.add(
        AppointmentEvent(
            tenant_id=tenant_id,
            appointment_id=appointment.id,
            event_type='updated',
            from_status=previous_status,
            to_status=appointment.status,
            metadata_json={'changes': safe_updates},
            created_by_user_id=principal.user.id,
        )
    )

    db.commit()
    db.refresh(appointment)

    emit_event(
        db,
        tenant_id=tenant_id,
        event_key='consulta_atualizada',
        payload={
            'appointment_id': str(appointment.id),
            'patient_id': str(appointment.patient_id),
            'status': appointment.status,
            'previous_status': previous_status,
            'confirmation_status': appointment.confirmation_status,
        },
    )

    record_audit(
        db,
        action='appointment.update',
        entity_type='appointment',
        entity_id=str(appointment.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata=safe_updates,
    )

    return AppointmentOutput.model_validate(appointment, from_attributes=True)


@router.delete('/{appointment_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_appointment(
    appointment_id: str,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    appointment = db.scalar(
        select(Appointment).where(Appointment.id == appointment_id, Appointment.tenant_id == tenant_id)
    )
    if not appointment:
        raise ApiError(status_code=404, code='APPOINTMENT_NOT_FOUND', message='Consulta nao encontrada')

    patient_id = appointment.patient_id
    previous_status = appointment.status

    db.delete(appointment)
    db.commit()

    emit_event(
        db,
        tenant_id=tenant_id,
        event_key='consulta_excluida',
        payload={
            'appointment_id': appointment_id,
            'patient_id': str(patient_id),
            'previous_status': previous_status,
        },
    )

    record_audit(
        db,
        action='appointment.delete',
        entity_type='appointment',
        entity_id=appointment_id,
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'previous_status': previous_status},
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)

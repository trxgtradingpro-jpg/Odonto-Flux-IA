from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.models import Appointment, AppointmentEvent
from app.schemas.appointment import AppointmentCreate, AppointmentOutput, AppointmentUpdate
from app.services.audit_service import record_audit
from app.services.automation_service import emit_event

router = APIRouter(prefix='/appointments', tags=['appointments'])


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

    previous_status = appointment.status
    updates = payload.model_dump(exclude_unset=True)
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
            metadata_json={'changes': updates},
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
        metadata=updates,
    )

    return AppointmentOutput.model_validate(appointment, from_attributes=True)

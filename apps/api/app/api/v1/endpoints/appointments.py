from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.api.unit_scope import ensure_unit_access, get_restricted_unit_id
from app.core.config import settings
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.models import Appointment, AppointmentEvent, Conversation, Patient, Professional, Tenant, Unit
from app.schemas.appointment import AppointmentCreate, AppointmentOutput, AppointmentUpdate
from app.services.appointment_validation_service import (
    ACTIVE_APPOINTMENT_STATUSES,
    ensure_appointment_within_working_days,
    eligible_professionals_for_procedure,
    find_professional_conflict,
    list_active_professionals_for_unit,
    pick_best_available_professional,
)
from app.services.audit_service import record_audit
from app.services.automation_service import emit_event
from app.services.service_duration_service import get_service_duration_catalog, resolve_appointment_end

router = APIRouter(prefix='/appointments', tags=['appointments'])
APPOINTMENT_ATTENDANCE_STATUSES = {"pendente", "compareceu", "faltou"}
APPOINTMENT_NEXT_APPOINTMENT_STATUSES = {
    "nao_definido",
    "precisa_agendar",
    "nao_precisa",
    "retorno_agendado",
}


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
    # New appointments default to scheduled unless attendance data explicitly closes them.
    return "agendada"


def _target_status_for_update(appointment: Appointment, updates: dict[str, Any]) -> str:
    raw_status = updates.get("status", appointment.status)
    return str(raw_status or "").strip().lower()


def _normalize_attendance_status(value: Any) -> str:
    normalized = str(value or "").strip().lower() or "pendente"
    if normalized not in APPOINTMENT_ATTENDANCE_STATUSES:
        raise ApiError(
            status_code=422,
            code="INVALID_ATTENDANCE_STATUS",
            message="Comparecimento invalido para a consulta",
        )
    return normalized


def _normalize_next_appointment_status(value: Any) -> str:
    normalized = str(value or "").strip().lower() or "nao_definido"
    if normalized not in APPOINTMENT_NEXT_APPOINTMENT_STATUSES:
        raise ApiError(
            status_code=422,
            code="INVALID_NEXT_APPOINTMENT_STATUS",
            message="Proximo passo invalido para a consulta",
        )
    return normalized


def _apply_attendance_updates(appointment: Appointment | None, updates: dict[str, Any]) -> None:
    if "attendance_status" in updates:
        updates["attendance_status"] = _normalize_attendance_status(updates.get("attendance_status"))
    if "next_appointment_status" in updates:
        updates["next_appointment_status"] = _normalize_next_appointment_status(updates.get("next_appointment_status"))
    if "attendance_notes" in updates:
        updates["attendance_notes"] = str(updates.get("attendance_notes") or "")

    if "status" in updates:
        updates["status"] = str(updates.get("status") or "").strip().lower()

    current_status = str(appointment.status or "").strip().lower() if appointment else "agendada"
    target_status = str(updates.get("status", current_status) or "").strip().lower()
    attendance_status = updates.get("attendance_status")

    if attendance_status == "compareceu":
        updates["status"] = "concluida"
        if "confirmation_status" not in updates and (appointment is None or appointment.confirmation_status == "pendente"):
            updates["confirmation_status"] = "confirmada"
        target_status = "concluida"
    elif attendance_status == "faltou":
        updates["status"] = "falta"
        target_status = "falta"
    elif attendance_status == "pendente" and "status" not in updates and "next_appointment_status" not in updates:
        updates["next_appointment_status"] = "nao_definido"

    if "attendance_status" not in updates:
        if target_status == "concluida":
            updates["attendance_status"] = "compareceu"
        elif target_status == "falta":
            updates["attendance_status"] = "faltou"
        elif "status" in updates and target_status in {"agendada", "confirmada", "reagendada", "cancelada"}:
            updates["attendance_status"] = "pendente"

    final_attendance_status = str(updates.get("attendance_status") or "").strip().lower()
    if (
        "next_appointment_status" not in updates
        and final_attendance_status
        and final_attendance_status != "compareceu"
        and "status" in updates
    ):
        updates["next_appointment_status"] = "nao_definido"


def _hydrate_patient_unit_from_appointment(
    db: Session,
    *,
    tenant_id: UUID,
    patient_id: UUID,
    unit_id: UUID | None,
) -> None:
    if not unit_id:
        return

    patient = db.scalar(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.tenant_id == tenant_id,
        )
    )
    if not patient or patient.unit_id:
        return

    patient.unit_id = unit_id
    db.add(patient)


def _get_tenant_timezone_name(db: Session, *, tenant_id: UUID) -> str:
    timezone_name = db.scalar(select(Tenant.timezone).where(Tenant.id == tenant_id))
    return str(timezone_name or settings.app_timezone or "America/Sao_Paulo")


def _appointment_automation_payload(
    db: Session,
    *,
    tenant_id: UUID,
    appointment: Appointment,
) -> dict[str, Any]:
    patient = db.scalar(
        select(Patient).where(
            Patient.id == appointment.patient_id,
            Patient.tenant_id == tenant_id,
        )
    )
    conversation = db.scalar(
        select(Conversation)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.patient_id == appointment.patient_id,
        )
        .order_by(Conversation.last_message_at.desc().nullslast(), Conversation.created_at.desc())
        .limit(1)
    )
    return {
        'appointment_id': str(appointment.id),
        'patient_id': str(appointment.patient_id),
        'conversation_id': str(conversation.id) if conversation else None,
        'unit_id': str(appointment.unit_id),
        'professional_id': str(appointment.professional_id) if appointment.professional_id else None,
        'procedure_type': appointment.procedure_type,
        'starts_at': appointment.starts_at.isoformat(),
        'status': appointment.status,
        'confirmation_status': appointment.confirmation_status,
        'phone': patient.phone if patient else None,
    }


def _auto_assign_professional_or_raise(
    db: Session,
    *,
    tenant_id: UUID,
    unit_id: UUID,
    procedure_type: str,
    starts_at,
    ends_at,
    timezone_name: str,
    exclude_appointment_id: UUID | None = None,
) -> UUID | None:
    service_catalog = get_service_duration_catalog(db, tenant_id=tenant_id)
    effective_ends_at = resolve_appointment_end(
        starts_at=starts_at,
        ends_at=ends_at,
        procedure_type=procedure_type,
        service_catalog=service_catalog,
    )
    professionals = list_active_professionals_for_unit(
        db,
        tenant_id=tenant_id,
        unit_id=unit_id,
    )
    if not professionals:
        raise ApiError(
            status_code=409,
            code="NO_ACTIVE_PROFESSIONAL_IN_UNIT",
            message="Nenhum profissional ativo esta cadastrado na unidade selecionada",
        )

    eligible_professionals = eligible_professionals_for_procedure(professionals, procedure_type)
    if not eligible_professionals:
        raise ApiError(
            status_code=409,
            code="NO_AVAILABLE_PROFESSIONAL_FOR_PROCEDURE",
            message="Nenhum profissional ativo atende esse servico na unidade selecionada",
        )

    selected_professional = pick_best_available_professional(
        db,
        tenant_id=tenant_id,
        unit_id=unit_id,
        procedure_type=procedure_type,
        starts_at=starts_at,
        ends_at=effective_ends_at,
        timezone_name=timezone_name,
        exclude_appointment_id=exclude_appointment_id,
    )
    if not selected_professional:
        raise ApiError(
            status_code=409,
            code="NO_AVAILABLE_PROFESSIONAL_FOR_SLOT",
            message="Nao encontrei profissional disponivel para esse servico nesse horario",
        )
    return selected_professional.id


@router.get('')
def list_appointments(
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
    limit: int = Query(default=30, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status: str | None = None,
    unit_id: UUID | None = None,
):
    stmt = select(Appointment).where(Appointment.tenant_id == tenant_id)
    restricted_unit_id = get_restricted_unit_id(db, principal=principal, tenant_id=tenant_id)
    if restricted_unit_id:
        stmt = stmt.where(Appointment.unit_id == restricted_unit_id)
    elif unit_id:
        stmt = stmt.where(Appointment.unit_id == unit_id)
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
    ensure_unit_access(db, principal=principal, tenant_id=tenant_id, target_unit_id=payload.unit_id)
    create_updates = payload.model_dump()
    _apply_attendance_updates(None, create_updates)
    target_status = str(create_updates.get("status") or _target_status_for_create(payload))
    target_professional_id = payload.professional_id
    tenant_timezone_name = _get_tenant_timezone_name(db, tenant_id=tenant_id)
    service_catalog = get_service_duration_catalog(db, tenant_id=tenant_id)
    effective_ends_at = resolve_appointment_end(
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        procedure_type=payload.procedure_type,
        service_catalog=service_catalog,
    )

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
        if professional.unit_id and professional.unit_id != payload.unit_id:
            raise ApiError(
                status_code=409,
                code="PROFESSIONAL_UNIT_MISMATCH",
                message="Profissional nao atende na unidade selecionada",
            )

        if target_status in ACTIVE_APPOINTMENT_STATUSES:
            ensure_appointment_within_working_days(
                starts_at=payload.starts_at,
                timezone_name=tenant_timezone_name,
                professional=professional,
            )
            conflict = find_professional_conflict(
                db,
                tenant_id=tenant_id,
                professional_id=target_professional_id,
                starts_at=payload.starts_at,
                ends_at=effective_ends_at,
                procedure_type=payload.procedure_type,
                service_catalog=service_catalog,
            )
            if conflict:
                raise ApiError(
                    status_code=409,
                    code="PROFESSIONAL_SLOT_CONFLICT",
                    message="Profissional ja possui consulta nesse horario",
                    details={
                        "conflict_appointment_id": str(conflict.id),
                        "professional_id": str(target_professional_id),
                        "starts_at": payload.starts_at.isoformat(),
                    },
                )
    elif target_status in ACTIVE_APPOINTMENT_STATUSES:
        ensure_appointment_within_working_days(
            starts_at=payload.starts_at,
            timezone_name=tenant_timezone_name,
        )
        target_professional_id = _auto_assign_professional_or_raise(
            db,
            tenant_id=tenant_id,
            unit_id=payload.unit_id,
            procedure_type=payload.procedure_type,
            starts_at=payload.starts_at,
            ends_at=effective_ends_at,
            timezone_name=tenant_timezone_name,
        )

    appointment = Appointment(
        tenant_id=tenant_id,
        patient_id=payload.patient_id,
        unit_id=payload.unit_id,
        professional_id=target_professional_id,
        procedure_type=payload.procedure_type,
        starts_at=payload.starts_at,
        ends_at=effective_ends_at,
        origin=payload.origin,
        notes=payload.notes,
        status=target_status,
        confirmation_status=str(create_updates.get("confirmation_status") or "pendente"),
        attendance_status=str(create_updates.get("attendance_status") or "pendente"),
        attendance_notes=str(create_updates.get("attendance_notes") or ""),
        next_appointment_status=str(create_updates.get("next_appointment_status") or "nao_definido"),
    )
    if appointment.confirmation_status == "confirmada" and not appointment.confirmed_at:
        appointment.confirmed_at = datetime.now(UTC)
    db.add(appointment)
    db.flush()
    _hydrate_patient_unit_from_appointment(
        db,
        tenant_id=tenant_id,
        patient_id=appointment.patient_id,
        unit_id=appointment.unit_id,
    )

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
        payload=_appointment_automation_payload(
            db,
            tenant_id=tenant_id,
            appointment=appointment,
        ),
    )

    record_audit(
        db,
        action='appointment.create',
        entity_type='appointment',
        entity_id=str(appointment.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={
            'status': appointment.status,
            'professional_id': str(appointment.professional_id) if appointment.professional_id else None,
            'auto_assigned_professional': bool(appointment.professional_id and not payload.professional_id),
        },
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
    ensure_unit_access(db, principal=principal, tenant_id=tenant_id, target_unit_id=appointment.unit_id)

    previous_status = str(appointment.status)
    updates = payload.model_dump(exclude_unset=True)
    _apply_attendance_updates(appointment, updates)

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
    ensure_unit_access(db, principal=principal, tenant_id=tenant_id, target_unit_id=target_unit_id)
    target_professional_id = (
        updates["professional_id"] if "professional_id" in updates else appointment.professional_id
    )
    tenant_timezone_name = _get_tenant_timezone_name(db, tenant_id=tenant_id)
    target_starts_at = updates.get("starts_at", appointment.starts_at)
    target_procedure_type = str(updates.get("procedure_type", appointment.procedure_type) or "")
    service_catalog = get_service_duration_catalog(db, tenant_id=tenant_id)
    ends_at_was_provided = "ends_at" in updates
    starts_or_procedure_changed = "starts_at" in updates or "procedure_type" in updates
    raw_target_ends_at = (
        updates.get("ends_at")
        if ends_at_was_provided
        else (appointment.ends_at if not starts_or_procedure_changed else None)
    )
    target_ends_at = resolve_appointment_end(
        starts_at=target_starts_at,
        ends_at=raw_target_ends_at,
        procedure_type=target_procedure_type,
        service_catalog=service_catalog,
    )
    updates["ends_at"] = target_ends_at
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
            ensure_appointment_within_working_days(
                starts_at=target_starts_at,
                timezone_name=tenant_timezone_name,
                professional=professional,
            )
            conflict = find_professional_conflict(
                db,
                tenant_id=tenant_id,
                professional_id=target_professional_id,
                starts_at=target_starts_at,
                ends_at=target_ends_at,
                procedure_type=target_procedure_type,
                exclude_appointment_id=appointment.id,
                service_catalog=service_catalog,
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
    elif target_status in ACTIVE_APPOINTMENT_STATUSES:
        ensure_appointment_within_working_days(
            starts_at=target_starts_at,
            timezone_name=tenant_timezone_name,
        )
        target_professional_id = _auto_assign_professional_or_raise(
            db,
            tenant_id=tenant_id,
            unit_id=target_unit_id,
            procedure_type=target_procedure_type,
            starts_at=target_starts_at,
            ends_at=target_ends_at,
            timezone_name=tenant_timezone_name,
            exclude_appointment_id=appointment.id,
        )
        updates["professional_id"] = target_professional_id

    safe_updates = _json_safe(updates)

    for key, value in updates.items():
        setattr(appointment, key, value)

    if updates.get('confirmation_status') == 'confirmada' and not appointment.confirmed_at:
        appointment.confirmed_at = datetime.now(UTC)

    db.add(appointment)
    db.flush()
    _hydrate_patient_unit_from_appointment(
        db,
        tenant_id=tenant_id,
        patient_id=appointment.patient_id,
        unit_id=appointment.unit_id,
    )

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
            **_appointment_automation_payload(
                db,
                tenant_id=tenant_id,
                appointment=appointment,
            ),
            'previous_status': previous_status,
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
    ensure_unit_access(db, principal=principal, tenant_id=tenant_id, target_unit_id=appointment.unit_id)

    previous_status = appointment.status
    event_payload = {
        **_appointment_automation_payload(
            db,
            tenant_id=tenant_id,
            appointment=appointment,
        ),
        'previous_status': previous_status,
    }

    db.delete(appointment)
    db.commit()

    emit_event(
        db,
        tenant_id=tenant_id,
        event_key='consulta_excluida',
        payload=event_payload,
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

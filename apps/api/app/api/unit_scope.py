from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import Principal
from app.core.exceptions import ApiError
from app.models import Appointment, Conversation, Document, Lead, Patient, Unit

UNIT_RESTRICTED_ROLES = {"manager", "receptionist"}


def get_restricted_unit_id(db: Session, *, principal: Principal, tenant_id: UUID) -> UUID | None:
    if not set(principal.roles).intersection(UNIT_RESTRICTED_ROLES):
        return None
    if principal.user.unit_id:
        return principal.user.unit_id
    return db.scalar(
        select(Unit.id).where(Unit.tenant_id == tenant_id).order_by(Unit.created_at.desc()).limit(1)
    )


def get_effective_unit_id(
    db: Session,
    *,
    principal: Principal,
    tenant_id: UUID,
    requested_unit_id: UUID | None,
) -> UUID | None:
    return get_restricted_unit_id(db, principal=principal, tenant_id=tenant_id) or requested_unit_id


def ensure_unit_access(
    db: Session,
    *,
    principal: Principal,
    tenant_id: UUID,
    target_unit_id: UUID | None,
) -> None:
    restricted_unit_id = get_restricted_unit_id(db, principal=principal, tenant_id=tenant_id)
    if restricted_unit_id and target_unit_id and restricted_unit_id != target_unit_id:
        raise ApiError(
            status_code=403,
            code="UNIT_ACCESS_DENIED",
            message="Seu usuario so pode operar dados da unidade vinculada",
        )


def patient_unit_scope_filter(*, tenant_id: UUID, unit_id: UUID):
    return or_(
        Patient.unit_id == unit_id,
        Patient.id.in_(
            select(Appointment.patient_id).where(
                Appointment.tenant_id == tenant_id,
                Appointment.unit_id == unit_id,
            )
        ),
        Patient.id.in_(
            select(Conversation.patient_id).where(
                Conversation.tenant_id == tenant_id,
                Conversation.unit_id == unit_id,
                Conversation.patient_id.is_not(None),
            )
        ),
        Patient.id.in_(
            select(Document.patient_id).where(
                Document.tenant_id == tenant_id,
                Document.unit_id == unit_id,
                Document.patient_id.is_not(None),
            )
        ),
    )


def lead_unit_scope_filter(*, tenant_id: UUID, unit_id: UUID):
    scoped_patient_ids = select(Patient.id).where(
        Patient.tenant_id == tenant_id,
        patient_unit_scope_filter(tenant_id=tenant_id, unit_id=unit_id),
    )
    return or_(
        Lead.patient_id.in_(scoped_patient_ids),
        Lead.id.in_(
            select(Conversation.lead_id).where(
                Conversation.tenant_id == tenant_id,
                Conversation.unit_id == unit_id,
                Conversation.lead_id.is_not(None),
            )
        ),
    )

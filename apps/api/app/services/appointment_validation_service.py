from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Appointment

ACTIVE_APPOINTMENT_STATUSES = {"agendada", "confirmada", "reagendada"}
DEFAULT_SLOT_DURATION_MINUTES = 60


def appointment_effective_end(*, starts_at, ends_at):
    if ends_at and ends_at > starts_at:
        return ends_at
    return starts_at + timedelta(minutes=DEFAULT_SLOT_DURATION_MINUTES)


def find_professional_conflict(
    db: Session,
    *,
    tenant_id: UUID,
    professional_id: UUID,
    starts_at,
    ends_at,
    exclude_appointment_id: UUID | None = None,
) -> Appointment | None:
    target_start = starts_at
    target_end = appointment_effective_end(starts_at=starts_at, ends_at=ends_at)

    stmt = select(Appointment).where(
        Appointment.tenant_id == tenant_id,
        Appointment.professional_id == professional_id,
        Appointment.status.in_(list(ACTIVE_APPOINTMENT_STATUSES)),
    )
    if exclude_appointment_id:
        stmt = stmt.where(Appointment.id != exclude_appointment_id)

    candidates = db.execute(stmt).scalars().all()
    for candidate in candidates:
        candidate_end = appointment_effective_end(
            starts_at=candidate.starts_at,
            ends_at=candidate.ends_at,
        )
        if candidate.starts_at < target_end and candidate_end > target_start:
            return candidate
    return None


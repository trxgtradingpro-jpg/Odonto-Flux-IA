from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ApiError
from app.models import Appointment, AppointmentEvent, Professional
from app.services.service_duration_service import (
    DEFAULT_SERVICE_DURATION_MINUTES,
    get_service_duration_catalog,
    labels_match,
    resolve_appointment_end,
)

ACTIVE_APPOINTMENT_STATUSES = {"agendada", "confirmada", "reagendada"}
DEFAULT_SLOT_DURATION_MINUTES = DEFAULT_SERVICE_DURATION_MINUTES
DEFAULT_WORKING_DAYS = [1, 2, 3, 4, 5]
WEEKEND_WORKING_DAYS = {0, 6}


def _resolve_timezone(timezone_name: str | None) -> ZoneInfo:
    candidate = str(timezone_name or settings.app_timezone or "America/Sao_Paulo").strip()
    try:
        return ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        return ZoneInfo("America/Sao_Paulo")


def python_weekday_to_ui_weekday(weekday: int) -> int:
    # Python: segunda=0. UI/profissionais: domingo=0.
    return (weekday + 1) % 7


def resolve_appointment_ui_weekday(*, starts_at: datetime, timezone_name: str | None = None) -> int:
    timezone = _resolve_timezone(timezone_name)
    localized = starts_at.astimezone(timezone) if starts_at.tzinfo else starts_at.replace(tzinfo=timezone)
    return python_weekday_to_ui_weekday(localized.weekday())


def normalize_working_days(days: list[int] | None) -> list[int]:
    cleaned = sorted({int(day) for day in (days or []) if 0 <= int(day) <= 6})
    return cleaned or DEFAULT_WORKING_DAYS


def professional_working_days(professional: Professional) -> list[int]:
    raw_days = professional.working_days if isinstance(professional.working_days, list) else []
    return normalize_working_days(raw_days)


def professional_is_available_on_day(
    professional: Professional,
    *,
    starts_at: datetime,
    timezone_name: str | None = None,
) -> bool:
    ui_weekday = resolve_appointment_ui_weekday(starts_at=starts_at, timezone_name=timezone_name)
    return ui_weekday in professional_working_days(professional)


def ensure_appointment_within_working_days(
    *,
    starts_at: datetime,
    timezone_name: str | None = None,
    professional: Professional | None = None,
) -> int:
    ui_weekday = resolve_appointment_ui_weekday(starts_at=starts_at, timezone_name=timezone_name)
    if ui_weekday in WEEKEND_WORKING_DAYS:
        raise ApiError(
            status_code=422,
            code="APPOINTMENT_OUTSIDE_WORKING_DAYS",
            message="Nao e permitido agendar consultas aos sabados ou domingos",
        )

    if professional and ui_weekday not in professional_working_days(professional):
        raise ApiError(
            status_code=422,
            code="PROFESSIONAL_OUTSIDE_WORKING_DAYS",
            message="Profissional nao atende nesse dia da semana",
        )
    return ui_weekday


def appointment_effective_end(
    *,
    starts_at,
    ends_at,
    procedure_type: str | None = None,
    service_catalog: list[dict] | None = None,
):
    return resolve_appointment_end(
        starts_at=starts_at,
        ends_at=ends_at,
        procedure_type=procedure_type,
        service_catalog=service_catalog,
        default_minutes=DEFAULT_SLOT_DURATION_MINUTES,
    )


def find_duplicate_active_patient_appointment(
    db: Session,
    *,
    tenant_id: UUID,
    patient_id: UUID,
    unit_id: UUID,
    starts_at: datetime,
    exclude_appointment_id: UUID | None = None,
    lock: bool = False,
) -> Appointment | None:
    stmt = (
        select(Appointment)
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.patient_id == patient_id,
            Appointment.unit_id == unit_id,
            Appointment.starts_at == starts_at,
            Appointment.status.in_(list(ACTIVE_APPOINTMENT_STATUSES)),
        )
        .order_by(Appointment.created_at.asc(), Appointment.id.asc())
        .limit(1)
    )
    if exclude_appointment_id:
        stmt = stmt.where(Appointment.id != exclude_appointment_id)
    if lock:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def _labels_match(left: str | None, right: str | None) -> bool:
    return labels_match(left, right)


def professional_specialty_matches(professional: Professional, procedure_type: str) -> bool:
    return _labels_match(professional.specialty, procedure_type)


def professional_procedure_matches(professional: Professional, procedure_type: str) -> bool:
    procedures = [str(item or "").strip() for item in (professional.procedures or []) if str(item or "").strip()]
    if not procedures:
        return False
    return any(_labels_match(option, procedure_type) for option in procedures)


def professional_is_generalist(professional: Professional) -> bool:
    procedures = [str(item or "").strip() for item in (professional.procedures or []) if str(item or "").strip()]
    specialty = str(professional.specialty or "").strip()
    return not procedures and not specialty


def professional_assignment_priority(professional: Professional, procedure_type: str) -> int:
    if professional_specialty_matches(professional, procedure_type):
        return 0
    if professional_procedure_matches(professional, procedure_type):
        return 1
    if professional_is_generalist(professional):
        return 2
    return 3


def eligible_professionals_for_procedure(
    professionals: list[Professional],
    procedure_type: str,
) -> list[Professional]:
    active_professionals = [item for item in professionals if getattr(item, "is_active", True)]
    if not active_professionals:
        return []

    has_capability_mapping = any(
        professional_is_generalist(item) is False
        for item in active_professionals
    )
    if not has_capability_mapping:
        return active_professionals

    return [
        item
        for item in active_professionals
        if professional_assignment_priority(item, procedure_type) < 3
    ]


def list_active_professionals_for_unit(
    db: Session,
    *,
    tenant_id: UUID,
    unit_id: UUID,
) -> list[Professional]:
    return db.execute(
        select(Professional).where(
            Professional.tenant_id == tenant_id,
            or_(Professional.unit_id == unit_id, Professional.unit_id.is_(None)),
            Professional.is_active.is_(True),
        )
    ).scalars().all()


def pick_best_available_professional(
    db: Session,
    *,
    tenant_id: UUID,
    unit_id: UUID,
    procedure_type: str,
    starts_at,
    ends_at,
    timezone_name: str | None = None,
    exclude_appointment_id: UUID | None = None,
) -> Professional | None:
    professionals = list_active_professionals_for_unit(
        db,
        tenant_id=tenant_id,
        unit_id=unit_id,
    )
    eligible_professionals = eligible_professionals_for_procedure(professionals, procedure_type)
    if not eligible_professionals:
        return None

    eligible_professionals = [
        professional
        for professional in eligible_professionals
        if professional_is_available_on_day(
            professional,
            starts_at=starts_at,
            timezone_name=timezone_name,
        )
    ]
    if not eligible_professionals:
        return None

    professional_ids = [item.id for item in eligible_professionals]
    load_rows = db.execute(
        select(Appointment.professional_id)
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.professional_id.in_(professional_ids),
            Appointment.status.in_(list(ACTIVE_APPOINTMENT_STATUSES)),
        )
    ).all()
    load_counter = Counter(
        str(row[0])
        for row in load_rows
        if row and row[0] is not None
    )

    ranked_professionals = sorted(
        eligible_professionals,
        key=lambda item: (
            professional_assignment_priority(item, procedure_type),
            load_counter.get(str(item.id), 0),
            str(item.full_name or "").lower(),
            str(item.id),
        ),
    )

    service_catalog = get_service_duration_catalog(db, tenant_id=tenant_id)
    for professional in ranked_professionals:
        conflict = find_professional_conflict(
            db,
            tenant_id=tenant_id,
            professional_id=professional.id,
            starts_at=starts_at,
            ends_at=ends_at,
            procedure_type=procedure_type,
            exclude_appointment_id=exclude_appointment_id,
            service_catalog=service_catalog,
        )
        if not conflict:
            return professional
    return None


def _load_counter_for_professionals(
    db: Session,
    *,
    tenant_id: UUID,
    professional_ids: list[UUID],
) -> Counter[str]:
    if not professional_ids:
        return Counter()
    load_rows = db.execute(
        select(Appointment.professional_id)
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.professional_id.in_(professional_ids),
            Appointment.status.in_(list(ACTIVE_APPOINTMENT_STATUSES)),
        )
    ).all()
    return Counter(
        str(row[0])
        for row in load_rows
        if row and row[0] is not None
    )


def _rank_professionals_for_procedure(
    db: Session,
    *,
    tenant_id: UUID,
    eligible_professionals: list[Professional],
    procedure_type: str,
) -> list[Professional]:
    load_counter = _load_counter_for_professionals(
        db,
        tenant_id=tenant_id,
        professional_ids=[item.id for item in eligible_professionals],
    )
    return sorted(
        eligible_professionals,
        key=lambda item: (
            professional_assignment_priority(item, procedure_type),
            load_counter.get(str(item.id), 0),
            str(item.full_name or "").lower(),
            str(item.id),
        ),
    )


def pick_preferred_professional(
    db: Session,
    *,
    tenant_id: UUID,
    unit_id: UUID,
    procedure_type: str,
) -> Professional | None:
    professionals = list_active_professionals_for_unit(
        db,
        tenant_id=tenant_id,
        unit_id=unit_id,
    )
    eligible_professionals = eligible_professionals_for_procedure(professionals, procedure_type)
    if not eligible_professionals:
        return None
    ranked_professionals = _rank_professionals_for_procedure(
        db,
        tenant_id=tenant_id,
        eligible_professionals=eligible_professionals,
        procedure_type=procedure_type,
    )
    return ranked_professionals[0] if ranked_professionals else None


def resolve_professional_for_existing_appointment(
    db: Session,
    *,
    appointment: Appointment,
    reference_time: datetime | None = None,
    timezone_name: str | None = None,
) -> tuple[Professional | None, str]:
    professionals = list_active_professionals_for_unit(
        db,
        tenant_id=appointment.tenant_id,
        unit_id=appointment.unit_id,
    )
    if not professionals:
        return None, "no_active_professionals"

    eligible_professionals = eligible_professionals_for_procedure(professionals, appointment.procedure_type)
    if not eligible_professionals:
        return None, "no_service_match"

    effective_reference_time = reference_time or datetime.now(UTC)
    is_future_active_appointment = (
        str(appointment.status or "").strip().lower() in ACTIVE_APPOINTMENT_STATUSES
        and appointment.starts_at >= effective_reference_time
    )

    if is_future_active_appointment:
        selected_professional = pick_best_available_professional(
            db,
            tenant_id=appointment.tenant_id,
            unit_id=appointment.unit_id,
            procedure_type=appointment.procedure_type,
            starts_at=appointment.starts_at,
            ends_at=appointment.ends_at,
            timezone_name=timezone_name,
            exclude_appointment_id=appointment.id,
        )
        if not selected_professional:
            return None, "no_slot_available"
        return selected_professional, "assigned_with_availability"

    selected_professional = _rank_professionals_for_procedure(
        db,
        tenant_id=appointment.tenant_id,
        eligible_professionals=eligible_professionals,
        procedure_type=appointment.procedure_type,
    )[0]
    return selected_professional, "assigned_historical"


def backfill_missing_appointment_professionals(
    db: Session,
    *,
    tenant_id: UUID,
    unit_id: UUID | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    stmt = (
        select(Appointment)
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.professional_id.is_(None),
        )
        .order_by(Appointment.starts_at.asc(), Appointment.id.asc())
    )
    if unit_id:
        stmt = stmt.where(Appointment.unit_id == unit_id)
    if limit:
        stmt = stmt.limit(limit)

    scanned = 0
    assigned = 0
    reason_counter: Counter[str] = Counter()
    unresolved_examples: list[dict[str, str]] = []
    reference_time = datetime.now(UTC)

    appointments = db.execute(stmt).scalars().all()
    for appointment in appointments:
        scanned += 1
        selected_professional, reason = resolve_professional_for_existing_appointment(
            db,
            appointment=appointment,
            reference_time=reference_time,
        )
        if not selected_professional:
            reason_counter[reason] += 1
            if len(unresolved_examples) < 25:
                unresolved_examples.append(
                    {
                        "appointment_id": str(appointment.id),
                        "unit_id": str(appointment.unit_id),
                        "procedure_type": str(appointment.procedure_type or "").strip(),
                        "status": str(appointment.status or "").strip(),
                        "starts_at": appointment.starts_at.isoformat(),
                        "reason": reason,
                    }
                )
            continue

        assigned += 1
        reason_counter[reason] += 1
        if dry_run:
            continue

        appointment.professional_id = selected_professional.id
        appointment.updated_at = datetime.now(UTC)
        db.add(appointment)
        db.add(
            AppointmentEvent(
                tenant_id=appointment.tenant_id,
                appointment_id=appointment.id,
                event_type="professional_backfilled",
                from_status=str(appointment.status),
                to_status=str(appointment.status),
                metadata_json={
                    "assigned_professional_id": str(selected_professional.id),
                    "assigned_professional_name": str(selected_professional.full_name or ""),
                    "procedure_type": str(appointment.procedure_type or ""),
                    "assignment_mode": reason,
                },
                created_by_user_id=None,
            )
        )
        db.flush()

    if not dry_run:
        db.commit()

    return {
        "scanned": scanned,
        "assigned": assigned,
        "unresolved": scanned - assigned,
        "reason_counts": dict(reason_counter),
        "unresolved_examples": unresolved_examples,
        "dry_run": dry_run,
        "unit_id": str(unit_id) if unit_id else None,
    }


def backfill_appointment_end_times(
    db: Session,
    *,
    tenant_id: UUID,
    unit_id: UUID | None = None,
    future_only: bool = False,
    dry_run: bool = False,
) -> dict[str, object]:
    stmt = select(Appointment).where(Appointment.tenant_id == tenant_id)
    if unit_id:
        stmt = stmt.where(Appointment.unit_id == unit_id)
    if future_only:
        stmt = stmt.where(Appointment.starts_at >= datetime.now(UTC))

    appointments = db.execute(stmt.order_by(Appointment.starts_at.asc(), Appointment.id.asc())).scalars().all()
    service_catalog = get_service_duration_catalog(db, tenant_id=tenant_id)

    scanned = len(appointments)
    updated = 0
    unchanged = 0

    for appointment in appointments:
        expected_end = resolve_appointment_end(
            starts_at=appointment.starts_at,
            ends_at=None,
            procedure_type=appointment.procedure_type,
            service_catalog=service_catalog,
            default_minutes=DEFAULT_SLOT_DURATION_MINUTES,
        )
        if appointment.ends_at and appointment.ends_at == expected_end:
            unchanged += 1
            continue
        if dry_run:
            updated += 1
            continue
        appointment.ends_at = expected_end
        appointment.updated_at = datetime.now(UTC)
        db.add(appointment)
        updated += 1

    if not dry_run:
        db.commit()

    return {
        "scanned": scanned,
        "updated": updated,
        "unchanged": unchanged,
        "dry_run": dry_run,
        "future_only": future_only,
        "unit_id": str(unit_id) if unit_id else None,
    }


def rebalance_future_unit_appointments(
    db: Session,
    *,
    tenant_id: UUID,
    unit_id: UUID,
    restore_original_on_failure: bool = True,
    dry_run: bool = False,
) -> dict[str, object]:
    reference_time = datetime.now(UTC)
    appointments = db.execute(
        select(Appointment)
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.unit_id == unit_id,
            Appointment.status.in_(list(ACTIVE_APPOINTMENT_STATUSES)),
            Appointment.starts_at >= reference_time,
        )
        .order_by(Appointment.starts_at.asc(), Appointment.id.asc())
    ).scalars().all()

    scanned = len(appointments)
    moved = 0
    unchanged = 0
    restored_original = 0
    unassigned = 0
    unresolved = 0
    reason_counter: Counter[str] = Counter()

    if not appointments:
        return {
            "scanned": 0,
            "moved": 0,
            "unchanged": 0,
            "restored_original": 0,
            "unassigned": 0,
            "unresolved": 0,
            "reason_counts": {},
            "dry_run": dry_run,
            "unit_id": str(unit_id),
        }

    original_professional_by_id = {
        appointment.id: appointment.professional_id
        for appointment in appointments
    }

    if not dry_run:
        for appointment in appointments:
            appointment.professional_id = None
            appointment.updated_at = datetime.now(UTC)
            db.add(appointment)
        db.flush()

    for appointment in appointments:
        original_professional_id = original_professional_by_id.get(appointment.id)
        selected_professional, reason = resolve_professional_for_existing_appointment(
            db,
            appointment=appointment,
            reference_time=reference_time,
        )
        if not selected_professional:
            if not dry_run and original_professional_id and restore_original_on_failure:
                appointment.professional_id = original_professional_id
                appointment.updated_at = datetime.now(UTC)
                db.add(appointment)
                db.flush()
                restored_original += 1
                reason_counter[f"restored_original_{reason}"] += 1
                continue

            if not dry_run:
                appointment.professional_id = None
                appointment.updated_at = datetime.now(UTC)
                db.add(appointment)
                db.add(
                    AppointmentEvent(
                        tenant_id=appointment.tenant_id,
                        appointment_id=appointment.id,
                        event_type="professional_unassigned",
                        from_status=str(appointment.status),
                        to_status=str(appointment.status),
                        metadata_json={
                            "previous_professional_id": str(original_professional_id) if original_professional_id else None,
                            "procedure_type": str(appointment.procedure_type or ""),
                            "unassignment_reason": reason,
                        },
                        created_by_user_id=None,
                    )
                )
                db.flush()

            unassigned += 1
            unresolved += 1
            reason_counter[f"unassigned_{reason}"] += 1
            continue

        selected_professional_id = selected_professional.id
        if original_professional_id == selected_professional_id:
            unchanged += 1
        else:
            moved += 1
        reason_counter[reason] += 1

        if dry_run:
            continue

        appointment.professional_id = selected_professional_id
        appointment.updated_at = datetime.now(UTC)
        db.add(appointment)
        if original_professional_id != selected_professional_id:
            db.add(
                AppointmentEvent(
                    tenant_id=appointment.tenant_id,
                    appointment_id=appointment.id,
                    event_type="professional_rebalanced",
                    from_status=str(appointment.status),
                    to_status=str(appointment.status),
                    metadata_json={
                        "previous_professional_id": str(original_professional_id) if original_professional_id else None,
                        "assigned_professional_id": str(selected_professional_id),
                        "assigned_professional_name": str(selected_professional.full_name or ""),
                        "procedure_type": str(appointment.procedure_type or ""),
                        "assignment_mode": reason,
                    },
                    created_by_user_id=None,
                )
            )
        db.flush()

    if not dry_run:
        db.commit()

    return {
        "scanned": scanned,
        "moved": moved,
        "unchanged": unchanged,
        "restored_original": restored_original,
        "unassigned": unassigned,
        "unresolved": unresolved,
        "reason_counts": dict(reason_counter),
        "dry_run": dry_run,
        "unit_id": str(unit_id),
    }


def sync_future_appointments_with_service_catalog(
    db: Session,
    *,
    tenant_id: UUID,
    dry_run: bool = False,
) -> dict[str, object]:
    backfill_summary = backfill_appointment_end_times(
        db,
        tenant_id=tenant_id,
        future_only=True,
        dry_run=dry_run,
    )

    reference_time = datetime.now(UTC)
    unit_ids = [
        unit_id
        for unit_id in db.execute(
            select(Appointment.unit_id)
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.unit_id.is_not(None),
                Appointment.starts_at >= reference_time,
            )
            .distinct()
        ).scalars().all()
        if unit_id is not None
    ]

    rebalance_summaries: list[dict[str, object]] = []
    totals = {
        "units_scanned": len(unit_ids),
        "appointments_scanned": 0,
        "appointments_moved": 0,
        "appointments_unchanged": 0,
        "appointments_restored_original": 0,
        "appointments_unassigned": 0,
        "appointments_unresolved": 0,
    }

    for unit_id in unit_ids:
        summary = rebalance_future_unit_appointments(
            db,
            tenant_id=tenant_id,
            unit_id=unit_id,
            restore_original_on_failure=False,
            dry_run=dry_run,
        )
        rebalance_summaries.append(summary)
        totals["appointments_scanned"] += int(summary.get("scanned", 0) or 0)
        totals["appointments_moved"] += int(summary.get("moved", 0) or 0)
        totals["appointments_unchanged"] += int(summary.get("unchanged", 0) or 0)
        totals["appointments_restored_original"] += int(summary.get("restored_original", 0) or 0)
        totals["appointments_unassigned"] += int(summary.get("unassigned", 0) or 0)
        totals["appointments_unresolved"] += int(summary.get("unresolved", 0) or 0)

    return {
        "backfill": backfill_summary,
        "rebalance": {
            "totals": totals,
            "units": rebalance_summaries,
        },
        "dry_run": dry_run,
    }


def find_professional_conflict(
    db: Session,
    *,
    tenant_id: UUID,
    professional_id: UUID,
    starts_at,
    ends_at,
    procedure_type: str | None = None,
    exclude_appointment_id: UUID | None = None,
    service_catalog: list[dict] | None = None,
) -> Appointment | None:
    target_start = starts_at
    effective_service_catalog = service_catalog or get_service_duration_catalog(db, tenant_id=tenant_id)
    target_end = appointment_effective_end(
        starts_at=starts_at,
        ends_at=ends_at,
        procedure_type=procedure_type,
        service_catalog=effective_service_catalog,
    )

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
            procedure_type=candidate.procedure_type,
            service_catalog=effective_service_catalog,
        )
        if candidate.starts_at < target_end and candidate_end > target_start:
            return candidate
    return None

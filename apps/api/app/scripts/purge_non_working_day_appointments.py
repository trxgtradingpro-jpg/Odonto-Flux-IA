from __future__ import annotations

import argparse
import json
import unicodedata
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Appointment, Professional, Tenant, Unit
from app.services.appointment_validation_service import (
    DEFAULT_WORKING_DAYS,
    WEEKEND_WORKING_DAYS,
    normalize_working_days,
    professional_working_days,
    resolve_appointment_ui_weekday,
)


def _normalize_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _strip_weekend_hours(working_hours: object) -> tuple[dict, list[str]]:
    if not isinstance(working_hours, dict):
        return {}, []

    removed_keys: list[str] = []
    cleaned: dict = {}
    for key, value in working_hours.items():
        normalized_key = _normalize_key(str(key))
        if any(token in normalized_key for token in ("sab", "sat", "domingo", "sunday", "sun")):
            removed_keys.append(str(key))
            continue
        cleaned[key] = value
    return cleaned, removed_keys


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove consultas fora dos dias trabalhados e limpa horarios de fim de semana.")
    parser.add_argument("--dry-run", action="store_true", help="Somente calcula o que seria alterado, sem gravar.")
    args = parser.parse_args()

    with SessionLocal() as db:
        tenant_timezones = {
            tenant_id: timezone
            for tenant_id, timezone in db.execute(select(Tenant.id, Tenant.timezone)).all()
        }

        professionals = db.execute(select(Professional)).scalars().all()
        professionals_by_id = {professional.id: professional for professional in professionals}
        professional_updates = 0
        professional_removed_days = 0

        for professional in professionals:
            before_days = normalize_working_days(professional.working_days if isinstance(professional.working_days, list) else [])
            after_days = [day for day in before_days if day not in WEEKEND_WORKING_DAYS] or list(DEFAULT_WORKING_DAYS)
            removed_days = len(set(before_days) - set(after_days))
            if after_days == before_days:
                continue
            professional_updates += 1
            professional_removed_days += removed_days
            if args.dry_run:
                continue
            professional.working_days = after_days
            professional.updated_at = datetime.now(UTC)
            db.add(professional)

        unit_updates = 0
        unit_removed_keys = 0
        units = db.execute(select(Unit)).scalars().all()
        for unit in units:
            cleaned_hours, removed_keys = _strip_weekend_hours(unit.working_hours)
            if not removed_keys:
                continue
            unit_updates += 1
            unit_removed_keys += len(removed_keys)
            if args.dry_run:
                continue
            unit.working_hours = cleaned_hours
            unit.updated_at = datetime.now(UTC)
            db.add(unit)

        appointments = db.execute(select(Appointment).order_by(Appointment.starts_at.asc())).scalars().all()
        deleted_appointments = 0
        reason_counter: Counter[str] = Counter()
        tenant_counter: Counter[str] = Counter()

        for appointment in appointments:
            timezone_name = tenant_timezones.get(appointment.tenant_id)
            ui_weekday = resolve_appointment_ui_weekday(
                starts_at=appointment.starts_at,
                timezone_name=timezone_name,
            )
            professional = professionals_by_id.get(appointment.professional_id) if appointment.professional_id else None

            reason: str | None = None
            if ui_weekday in WEEKEND_WORKING_DAYS:
                reason = "weekend"
            elif professional and ui_weekday not in professional_working_days(professional):
                reason = "professional_day_mismatch"

            if not reason:
                continue

            deleted_appointments += 1
            reason_counter[reason] += 1
            tenant_counter[str(appointment.tenant_id)] += 1
            if args.dry_run:
                continue
            db.delete(appointment)

        if args.dry_run:
            db.rollback()
        else:
            db.commit()

    summary = {
        "dry_run": args.dry_run,
        "professionals_updated": professional_updates,
        "professional_weekend_days_removed": professional_removed_days,
        "units_updated": unit_updates,
        "unit_weekend_keys_removed": unit_removed_keys,
        "appointments_deleted": deleted_appointments,
        "reasons": dict(reason_counter),
        "appointments_deleted_by_tenant": dict(tenant_counter),
    }
    print(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

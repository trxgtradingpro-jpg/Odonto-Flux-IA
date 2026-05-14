from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Appointment, Patient, Tenant


def _resolve_tenant_ids(db, *, tenant_id: str | None, tenant_slug: str | None) -> list[UUID]:
    if tenant_id:
        return [UUID(tenant_id)]
    if tenant_slug:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == tenant_slug))
        return [tenant.id] if tenant else []
    return [item.id for item in db.execute(select(Tenant).order_by(Tenant.created_at.asc())).scalars().all()]


def backfill_patient_units_from_appointments(
    db,
    *,
    tenant_id: UUID,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    patients = db.execute(
        select(Patient)
        .where(
            Patient.tenant_id == tenant_id,
            Patient.archived_at.is_(None),
            Patient.unit_id.is_(None),
        )
        .order_by(Patient.created_at.asc())
    ).scalars().all()

    if limit is not None:
        patients = patients[:limit]

    patient_ids = [item.id for item in patients]
    if not patient_ids:
        return {
            "scanned": 0,
            "updated": 0,
            "unresolved": 0,
            "dry_run": dry_run,
            "samples": [],
        }

    appointments = db.execute(
        select(Appointment)
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.patient_id.in_(patient_ids),
            Appointment.unit_id.is_not(None),
        )
        .order_by(
            Appointment.patient_id.asc(),
            Appointment.starts_at.desc(),
            Appointment.created_at.desc(),
            Appointment.id.desc(),
        )
    ).scalars().all()

    latest_appointment_by_patient: dict[UUID, Appointment] = {}
    for appointment in appointments:
        latest_appointment_by_patient.setdefault(appointment.patient_id, appointment)

    updated = 0
    unresolved = 0
    samples: list[dict[str, str]] = []

    for patient in patients:
        latest = latest_appointment_by_patient.get(patient.id)
        if not latest or not latest.unit_id:
            unresolved += 1
            continue

        if len(samples) < 15:
            samples.append(
                {
                    "patient_id": str(patient.id),
                    "patient_name": patient.full_name,
                    "unit_id": str(latest.unit_id),
                    "appointment_id": str(latest.id),
                    "starts_at": latest.starts_at.isoformat(),
                }
            )

        if not dry_run:
            patient.unit_id = latest.unit_id
            db.add(patient)
        updated += 1

    if not dry_run:
        db.commit()

    return {
        "scanned": len(patients),
        "updated": updated,
        "unresolved": unresolved,
        "dry_run": dry_run,
        "samples": samples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill de unidade em pacientes a partir do agendamento mais recente com unidade definida."
    )
    parser.add_argument("--tenant-id", type=str, default=None, help="Tenant alvo pelo ID.")
    parser.add_argument("--tenant-slug", type=str, default=None, help="Tenant alvo pelo slug.")
    parser.add_argument("--limit", type=int, default=None, help="Limita a quantidade de pacientes analisados.")
    parser.add_argument("--dry-run", action="store_true", help="Apenas simula sem gravar no banco.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        tenant_ids = _resolve_tenant_ids(db, tenant_id=args.tenant_id, tenant_slug=args.tenant_slug)
        finished_at = datetime.now(UTC)
        per_tenant: list[dict[str, object]] = []
        aggregate = {
            "scanned": 0,
            "updated": 0,
            "unresolved": 0,
            "dry_run": args.dry_run,
        }

        for current_tenant_id in tenant_ids:
            summary = backfill_patient_units_from_appointments(
                db,
                tenant_id=current_tenant_id,
                limit=args.limit,
                dry_run=args.dry_run,
            )
            summary["tenant_id"] = str(current_tenant_id)
            per_tenant.append(summary)
            aggregate["scanned"] += int(summary.get("scanned", 0))
            aggregate["updated"] += int(summary.get("updated", 0))
            aggregate["unresolved"] += int(summary.get("unresolved", 0))

        report = {
            **aggregate,
            "tenants_processed": len(tenant_ids),
            "per_tenant": per_tenant,
            "finished_at": finished_at.isoformat(),
        }

        output_dir = Path(settings.storage_base_path or "/storage") / "patient-backfills"
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = finished_at.strftime("%Y%m%d-%H%M%S")
        output_path = output_dir / f"patient-unit-backfill-{stamp}.json"
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"report_path={output_path}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

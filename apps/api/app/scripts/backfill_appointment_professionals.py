from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Tenant
from app.services.appointment_validation_service import backfill_missing_appointment_professionals


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill de profissionais em consultas antigas sem profissional.")
    parser.add_argument("--tenant-id", type=str, default=None, help="Tenant alvo. Se omitido, usa o primeiro tenant.")
    parser.add_argument("--unit-id", type=str, default=None, help="Limita o backfill para uma unidade.")
    parser.add_argument("--limit", type=int, default=None, help="Limita a quantidade de consultas analisadas.")
    parser.add_argument("--dry-run", action="store_true", help="Apenas simula sem gravar no banco.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.tenant_id:
            tenant_ids = [UUID(args.tenant_id)]
        else:
            tenant_ids = [item.id for item in db.execute(select(Tenant).order_by(Tenant.created_at.asc())).scalars().all()]

        finished_at = datetime.now(UTC)
        per_tenant: list[dict[str, object]] = []
        aggregate = {
            "scanned": 0,
            "assigned": 0,
            "unresolved": 0,
            "reason_counts": {},
            "dry_run": args.dry_run,
            "unit_id": args.unit_id,
        }

        for tenant_id in tenant_ids:
            summary = backfill_missing_appointment_professionals(
                db,
                tenant_id=tenant_id,
                unit_id=UUID(args.unit_id) if args.unit_id else None,
                limit=args.limit,
                dry_run=args.dry_run,
            )
            summary["tenant_id"] = str(tenant_id)
            per_tenant.append(summary)
            aggregate["scanned"] += int(summary.get("scanned", 0))
            aggregate["assigned"] += int(summary.get("assigned", 0))
            aggregate["unresolved"] += int(summary.get("unresolved", 0))
            for reason, quantity in dict(summary.get("reason_counts", {})).items():
                current = int(aggregate["reason_counts"].get(reason, 0))
                aggregate["reason_counts"][reason] = current + int(quantity)

        summary = {
            **aggregate,
            "tenants_processed": len(tenant_ids),
            "per_tenant": per_tenant,
            "finished_at": finished_at.isoformat(),
        }

        output_dir = Path(settings.storage_base_path or "/storage") / "appointment-backfills"
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = finished_at.strftime("%Y%m%d-%H%M%S")
        output_path = output_dir / f"appointment-backfill-{stamp}.json"
        output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"report_path={output_path}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

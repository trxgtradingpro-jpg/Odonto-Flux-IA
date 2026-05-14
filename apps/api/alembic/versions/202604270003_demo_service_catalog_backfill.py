"""Backfill official service catalog for commercial demos.

Revision ID: 202604270003
Revises: 202604270002
Create Date: 2026-04-27
"""

from __future__ import annotations

import json
import re

from alembic import op
import sqlalchemy as sa


revision = "202604270003"
down_revision = "202604270002"
branch_labels = None
depends_on = None


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return slug or "servico"


def _normalize_service(raw: dict) -> dict | None:
    name = " ".join(str(raw.get("name") or raw.get("service_name") or "").strip().split())
    if not name:
        return None
    duration = raw.get("duration_minutes")
    try:
        duration = int(duration) if duration is not None else 60
    except (TypeError, ValueError):
        duration = 60
    return {
        "id": str(raw.get("id") or _slugify(name)),
        "name": name,
        "description": " ".join(str(raw.get("description") or name).strip().split()),
        "duration_minutes": max(15, min(duration, 480)),
        "price_note": str(raw.get("price_note") or raw.get("price_range") or "sob consulta").strip(),
        "is_active": bool(raw.get("is_active", True)),
    }


def _upsert_setting(conn, *, tenant_id, key: str, value: dict) -> None:
    conn.execute(
        sa.text(
            """
            INSERT INTO settings (id, tenant_id, key, value, is_secret, created_at, updated_at)
            VALUES (gen_random_uuid(), :tenant_id, :key, CAST(:value AS JSONB), false, NOW(), NOW())
            ON CONFLICT (tenant_id, key)
            DO UPDATE SET value = EXCLUDED.value, is_secret = false, updated_at = NOW()
            """
        ),
        {"tenant_id": tenant_id, "key": key, "value": json.dumps(value)},
    )


def upgrade() -> None:
    conn = op.get_bind()
    prospects = conn.execute(
        sa.text(
            """
            SELECT id, demo_tenant_id
            FROM prospect_accounts
            WHERE demo_tenant_id IS NOT NULL
            """
        )
    ).mappings().all()

    for prospect in prospects:
        tenant_id = prospect["demo_tenant_id"]
        service_rows = conn.execute(
            sa.text(
                """
                SELECT service_name, description, duration_minutes, price_range
                FROM prospect_services
                WHERE prospect_account_id = :prospect_id
                ORDER BY service_name
                """
            ),
            {"prospect_id": prospect["id"]},
        ).mappings().all()

        services = [_normalize_service(dict(row)) for row in service_rows]
        services = [item for item in services if item]

        if not services:
            legacy = conn.execute(
                sa.text(
                    """
                    SELECT value
                    FROM settings
                    WHERE tenant_id = :tenant_id AND key = 'services.catalog'
                    LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id},
            ).scalar()
            raw_services = legacy.get("services") if isinstance(legacy, dict) else []
            services = [_normalize_service(item) for item in raw_services if isinstance(item, dict)]
            services = [item for item in services if item]

        if not services:
            procedure_rows = conn.execute(
                sa.text(
                    """
                    SELECT DISTINCT jsonb_array_elements_text(procedures) AS service_name
                    FROM professionals
                    WHERE tenant_id = :tenant_id AND jsonb_typeof(procedures) = 'array'
                    ORDER BY service_name
                    """
                ),
                {"tenant_id": tenant_id},
            ).mappings().all()
            services = [_normalize_service(dict(row)) for row in procedure_rows]
            services = [item for item in services if item]

        if not services:
            continue

        service_names = [item["name"] for item in services]
        _upsert_setting(conn, tenant_id=tenant_id, key="service_catalog.global", value={"items": services})
        _upsert_setting(conn, tenant_id=tenant_id, key="services.catalog", value={"services": services})

        unit_rows = conn.execute(
            sa.text("SELECT id FROM units WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        ).mappings().all()
        for unit in unit_rows:
            _upsert_setting(
                conn,
                tenant_id=tenant_id,
                key=f"unit.services.{unit['id']}",
                value={"services": service_names},
            )

        conn.execute(
            sa.text(
                """
                UPDATE professionals
                SET procedures = CAST(:procedures AS JSONB), updated_at = NOW()
                WHERE tenant_id = :tenant_id
                """
            ),
            {"tenant_id": tenant_id, "procedures": json.dumps(service_names)},
        )


def downgrade() -> None:
    conn = op.get_bind()
    demo_tenants = conn.execute(
        sa.text(
            """
            SELECT demo_tenant_id
            FROM prospect_accounts
            WHERE demo_tenant_id IS NOT NULL
            """
        )
    ).scalars().all()
    for tenant_id in demo_tenants:
        conn.execute(
            sa.text(
                """
                DELETE FROM settings
                WHERE tenant_id = :tenant_id
                  AND (
                    key = 'service_catalog.global'
                    OR key LIKE 'unit.services.%'
                  )
                """
            ),
            {"tenant_id": tenant_id},
        )

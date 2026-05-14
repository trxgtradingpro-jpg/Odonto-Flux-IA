from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Setting
from app.services.service_catalog_service import ensure_service_names_in_catalog

UNIT_SERVICES_SETTING_PREFIX = "unit.services."


def normalize_unit_services(raw_services: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_services or []:
        text = " ".join(str(item or "").strip().split())
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text[:120])
    return normalized


def _setting_key(unit_id: UUID) -> str:
    return f"{UNIT_SERVICES_SETTING_PREFIX}{unit_id}"


def list_unit_services_map(db: Session, *, tenant_id: UUID) -> dict[str, list[str]]:
    rows = db.execute(
        select(Setting).where(
            Setting.tenant_id == tenant_id,
            Setting.key.like(f"{UNIT_SERVICES_SETTING_PREFIX}%"),
        )
    ).scalars().all()

    output: dict[str, list[str]] = {}
    for row in rows:
        unit_id = row.key.removeprefix(UNIT_SERVICES_SETTING_PREFIX)
        value = row.value if isinstance(row.value, dict) else {}
        output[unit_id] = normalize_unit_services(value.get("services") if isinstance(value, dict) else [])
    return output


def get_unit_services(db: Session, *, tenant_id: UUID, unit_id: UUID) -> list[str]:
    services_map = list_unit_services_map(db, tenant_id=tenant_id)
    return services_map.get(str(unit_id), [])


def set_unit_services(
    db: Session,
    *,
    tenant_id: UUID,
    unit_id: UUID,
    services: list[str] | None,
) -> list[str]:
    normalized = normalize_unit_services(services)
    key = _setting_key(unit_id)
    item = db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == key))
    if not item:
        item = Setting(tenant_id=tenant_id, key=key, value={"services": normalized}, is_secret=False)
    else:
        item.value = {"services": normalized}
        item.is_secret = False
    db.add(item)
    db.commit()
    db.refresh(item)
    return normalized


def delete_unit_services(db: Session, *, tenant_id: UUID, unit_id: UUID) -> None:
    item = db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == _setting_key(unit_id)))
    if not item:
        return
    db.delete(item)
    db.commit()


def sync_unit_services_into_global_knowledge_base(
    db: Session,
    *,
    tenant_id: UUID,
    services: list[str] | None,
) -> dict[str, Any]:
    items = ensure_service_names_in_catalog(
        db,
        tenant_id=tenant_id,
        service_names=normalize_unit_services(services),
    )
    return {"items": items}

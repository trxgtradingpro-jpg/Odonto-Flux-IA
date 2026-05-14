from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Appointment, Professional, Setting

SERVICE_CATALOG_SETTING_KEY = "service_catalog.global"
UNIT_SERVICES_SETTING_PREFIX = "unit.services."


def _compact_text(value, *, max_length: int) -> str:
    text = " ".join(str(value or "").strip().split())
    return text[:max_length]


def format_duration_minutes(value: int | None) -> str:
    if not isinstance(value, int) or value <= 0:
        return ""
    hours = value // 60
    minutes = value % 60
    if hours and minutes:
        return f"{hours}h{minutes:02d}"
    if hours:
        return f"{hours}h"
    return f"{minutes} min"


def _normalize_duration_minutes(value) -> int | None:
    if isinstance(value, int):
        minutes = value
    elif isinstance(value, float):
        minutes = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            minutes = int(text)
        else:
            from app.services.service_duration_service import parse_duration_note_to_minutes

            minutes = parse_duration_note_to_minutes(text)
            return minutes
    else:
        minutes = None

    if minutes is None or minutes <= 0:
        return None
    return min(minutes, 8 * 60)


def _normalize_service_item(raw_item: dict | None) -> dict | None:
    if not isinstance(raw_item, dict):
        return None
    name = _compact_text(raw_item.get("name"), max_length=120)
    if not name:
        return None
    service_id = str(raw_item.get("id") or "").strip() or str(uuid4())
    duration_minutes = _normalize_duration_minutes(
        raw_item.get("duration_minutes") if "duration_minutes" in raw_item else raw_item.get("duration_note")
    )
    return {
        "id": service_id,
        "name": name,
        "description": _compact_text(raw_item.get("description"), max_length=500),
        "duration_minutes": duration_minutes,
        "price_note": _compact_text(raw_item.get("price_note"), max_length=120),
        "is_active": bool(raw_item.get("is_active", True)),
    }


def normalize_service_catalog_items(raw_items) -> list[dict]:
    if not isinstance(raw_items, list):
        return []
    items: list[dict] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for raw_item in raw_items:
        normalized = _normalize_service_item(raw_item)
        if not normalized:
            continue
        service_id = normalized["id"]
        name_key = normalized["name"].casefold()
        if service_id in seen_ids or name_key in seen_names:
            continue
        seen_ids.add(service_id)
        seen_names.add(name_key)
        items.append(normalized)
        if len(items) >= 100:
            break
    return items


def _load_service_catalog_setting(db: Session, *, tenant_id: UUID) -> Setting | None:
    return db.scalar(
        select(Setting).where(
            Setting.tenant_id == tenant_id,
            Setting.key == SERVICE_CATALOG_SETTING_KEY,
        )
    )


def has_service_catalog_setting(db: Session, *, tenant_id: UUID) -> bool:
    return _load_service_catalog_setting(db, tenant_id=tenant_id) is not None


def _load_legacy_ai_knowledge_services(db: Session, *, tenant_id: UUID) -> list[dict]:
    item = db.scalar(
        select(Setting).where(
            Setting.tenant_id == tenant_id,
            Setting.key == "ai_knowledge_base.global",
        )
    )
    if not item or not isinstance(item.value, dict):
        return []
    raw_services = item.value.get("services")
    return normalize_service_catalog_items(raw_services if isinstance(raw_services, list) else [])


def get_service_catalog_items(db: Session, *, tenant_id: UUID) -> list[dict]:
    item = _load_service_catalog_setting(db, tenant_id=tenant_id)
    if item and isinstance(item.value, dict):
        return normalize_service_catalog_items(item.value.get("items"))
    return _load_legacy_ai_knowledge_services(db, tenant_id=tenant_id)


def service_catalog_as_knowledge_services(items: list[dict] | None) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for item in items or []:
        if not item.get("is_active", True):
            continue
        output.append(
            {
                "name": _compact_text(item.get("name"), max_length=120),
                "description": _compact_text(item.get("description"), max_length=500),
                "duration_note": format_duration_minutes(item.get("duration_minutes")),
                "price_note": _compact_text(item.get("price_note"), max_length=120),
            }
        )
    return output


def _replace_service_name_references(
    db: Session,
    *,
    tenant_id: UUID,
    old_name: str,
    new_name: str,
) -> None:
    old_key = old_name.casefold()
    if not old_key or old_key == new_name.casefold():
        return

    unit_service_settings = db.execute(
        select(Setting).where(
            Setting.tenant_id == tenant_id,
            Setting.key.like(f"{UNIT_SERVICES_SETTING_PREFIX}%"),
        )
    ).scalars().all()
    for item in unit_service_settings:
        value = item.value if isinstance(item.value, dict) else {}
        services = value.get("services") if isinstance(value.get("services"), list) else []
        replaced = False
        next_services: list[str] = []
        for service_name in services:
            text = _compact_text(service_name, max_length=120)
            if text.casefold() == old_key:
                next_services.append(new_name)
                replaced = True
            else:
                next_services.append(text)
        if replaced:
            deduped: list[str] = []
            seen: set[str] = set()
            for service_name in next_services:
                key = service_name.casefold()
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(service_name)
            item.value = {"services": deduped}
            db.add(item)

    professionals = db.execute(
        select(Professional).where(Professional.tenant_id == tenant_id)
    ).scalars().all()
    for professional in professionals:
        changed = False
        if str(professional.specialty or "").strip().casefold() == old_key:
            professional.specialty = new_name
            changed = True
        procedures = []
        for procedure_name in professional.procedures or []:
            text = _compact_text(procedure_name, max_length=120)
            if text.casefold() == old_key:
                procedures.append(new_name)
                changed = True
            else:
                procedures.append(text)
        if changed:
            deduped: list[str] = []
            seen: set[str] = set()
            for procedure_name in procedures:
                key = procedure_name.casefold()
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(procedure_name)
            professional.procedures = deduped
            db.add(professional)

    appointments = db.execute(
        select(Appointment).where(Appointment.tenant_id == tenant_id)
    ).scalars().all()
    for appointment in appointments:
        if str(appointment.procedure_type or "").strip().casefold() != old_key:
            continue
        appointment.procedure_type = new_name
        db.add(appointment)


def set_service_catalog_items(
    db: Session,
    *,
    tenant_id: UUID,
    payload: dict | list,
) -> list[dict]:
    raw_items = payload.get("items") if isinstance(payload, dict) else payload
    existing_items = get_service_catalog_items(db, tenant_id=tenant_id)
    existing_names_by_id = {
        str(item.get("id")): str(item.get("name") or "").strip()
        for item in existing_items
        if str(item.get("id") or "").strip() and str(item.get("name") or "").strip()
    }
    normalized = normalize_service_catalog_items(raw_items)

    for item in normalized:
        old_name = existing_names_by_id.get(str(item["id"]))
        new_name = str(item["name"])
        if old_name and old_name != new_name:
            _replace_service_name_references(
                db,
                tenant_id=tenant_id,
                old_name=old_name,
                new_name=new_name,
            )

    record = _load_service_catalog_setting(db, tenant_id=tenant_id)
    if not record:
        record = Setting(
            tenant_id=tenant_id,
            key=SERVICE_CATALOG_SETTING_KEY,
            value={"items": normalized},
            is_secret=False,
        )
    else:
        record.value = {"items": normalized}
        record.is_secret = False
    db.add(record)
    db.commit()
    db.refresh(record)
    return normalize_service_catalog_items((record.value or {}).get("items"))


def ensure_service_names_in_catalog(
    db: Session,
    *,
    tenant_id: UUID,
    service_names: list[str] | None,
) -> list[dict]:
    current_items = get_service_catalog_items(db, tenant_id=tenant_id)
    by_name = {str(item.get("name") or "").strip().casefold(): item for item in current_items}
    changed = False
    for raw_name in service_names or []:
        name = _compact_text(raw_name, max_length=120)
        if not name:
            continue
        key = name.casefold()
        if key in by_name:
            continue
        by_name[key] = {
            "id": str(uuid4()),
            "name": name,
            "description": "",
            "duration_minutes": None,
            "price_note": "",
            "is_active": True,
        }
        changed = True
    if not changed and has_service_catalog_setting(db, tenant_id=tenant_id):
        return current_items
    return set_service_catalog_items(
        db,
        tenant_id=tenant_id,
        payload={"items": list(by_name.values())},
    )

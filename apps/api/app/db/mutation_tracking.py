from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import event
from sqlalchemy.orm import attributes, sessionmaker

from app.models import AuditLog, Setting, Tenant

PENDING_MUTATION_BACKUPS_KEY = "pending_mutation_backups"
SKIP_MUTATION_TRACKING_KEY = "skip_mutation_tracking"
ACTOR_USER_ID_KEY = "audit_actor_user_id"
ACTOR_USER_NAME_KEY = "audit_actor_user_name"
ACTOR_TENANT_ID_KEY = "audit_actor_tenant_id"
EXCLUDED_SETTING_KEYS = {"backup.history"}


def _table_name_for(instance: Any) -> str:
    return str(getattr(instance, "__tablename__", instance.__class__.__name__.lower()))


def _entity_type_from_table_name(table_name: str) -> str:
    parts = table_name.split("_")
    normalized: list[str] = []
    for part in parts:
        if part.endswith("ies") and len(part) > 3:
            normalized.append(f"{part[:-3]}y")
        elif part.endswith("s") and len(part) > 1:
            normalized.append(part[:-1])
        else:
            normalized.append(part)
    return "_".join(normalized)


def _serialize_instance(instance: Any) -> dict[str, Any]:
    mapper = sa_inspect(instance.__class__)
    payload: dict[str, Any] = {}
    for attr in mapper.column_attrs:
        payload[attr.key] = jsonable_encoder(getattr(instance, attr.key))
    return payload


def _tenant_id_for(instance: Any, session_tenant_id: UUID | None) -> UUID | None:
    if isinstance(instance, Tenant):
        return instance.id

    tenant_id = getattr(instance, "tenant_id", None)
    if isinstance(tenant_id, UUID):
        return tenant_id
    if tenant_id:
        try:
            return UUID(str(tenant_id))
        except ValueError:
            return session_tenant_id
    return session_tenant_id


def _is_trackable_instance(instance: Any) -> bool:
    if isinstance(instance, AuditLog):
        return False
    if isinstance(instance, Setting) and instance.key in EXCLUDED_SETTING_KEYS:
        return False
    return hasattr(instance, "__table__") and hasattr(instance, "id")


def _build_update_snapshot(instance: Any) -> dict[str, Any] | None:
    state = sa_inspect(instance)
    if not state.mapper.column_attrs:
        return None

    after_snapshot = _serialize_instance(instance)
    before_snapshot = dict(after_snapshot)
    changed_fields: list[str] = []

    for attr in state.mapper.column_attrs:
        key = attr.key
        history = state.attrs[key].history
        if not history.has_changes():
            continue

        changed_fields.append(key)
        if history.deleted:
            before_snapshot[key] = jsonable_encoder(history.deleted[0])
            continue

        committed_value = state.committed_state.get(key, attributes.NO_VALUE)
        if committed_value is not attributes.NO_VALUE:
            before_snapshot[key] = jsonable_encoder(committed_value)

    if not changed_fields:
        return None

    return {
        "operation": "update",
        "before": before_snapshot,
        "after": after_snapshot,
        "changed_fields": changed_fields,
    }


def _build_delete_snapshot(instance: Any) -> dict[str, Any]:
    return {
        "operation": "delete",
        "before": _serialize_instance(instance),
        "after": None,
        "changed_fields": [],
    }


def _store_pending_event(session, *, instance: Any, payload: dict[str, Any]) -> None:
    entity_id = getattr(instance, "id", None)
    if not entity_id:
        return

    table_name = _table_name_for(instance)
    entity_type = _entity_type_from_table_name(table_name)
    tenant_id = _tenant_id_for(instance, session.info.get(ACTOR_TENANT_ID_KEY))
    event_key = (
        payload["operation"],
        entity_type,
        str(entity_id),
    )

    session.info.setdefault(PENDING_MUTATION_BACKUPS_KEY, {})
    session.info[PENDING_MUTATION_BACKUPS_KEY][event_key] = {
        "operation": payload["operation"],
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "table_name": table_name,
        "model_name": instance.__class__.__name__,
        "tenant_id": str(tenant_id) if tenant_id else None,
        "before": payload["before"],
        "after": payload["after"],
        "changed_fields": payload["changed_fields"],
        "captured_at": datetime.now(UTC).isoformat(),
    }


def register_mutation_tracking(session_factory: sessionmaker) -> None:
    session_cls = session_factory.class_
    if getattr(session_cls, "_odontoflux_mutation_tracking_registered", False):
        return

    setattr(session_cls, "_odontoflux_mutation_tracking_registered", True)

    @event.listens_for(session_cls, "before_flush")
    def _capture_mutations(session, flush_context, instances) -> None:
        if session.info.get(SKIP_MUTATION_TRACKING_KEY):
            return

        for instance in list(session.deleted):
            if not _is_trackable_instance(instance):
                continue
            _store_pending_event(session, instance=instance, payload=_build_delete_snapshot(instance))

        for instance in list(session.dirty):
            if instance in session.deleted or instance in session.new:
                continue
            if not _is_trackable_instance(instance):
                continue
            if not session.is_modified(instance, include_collections=False):
                continue

            payload = _build_update_snapshot(instance)
            if payload:
                _store_pending_event(session, instance=instance, payload=payload)

    @event.listens_for(session_cls, "after_rollback")
    def _clear_pending_mutations(session) -> None:
        session.info.pop(PENDING_MUTATION_BACKUPS_KEY, None)


def consume_pending_mutation_backups(
    session,
    *,
    entity_type: str,
    entity_id: str | None,
    tenant_id: UUID | None,
) -> list[dict[str, Any]]:
    pending = session.info.get(PENDING_MUTATION_BACKUPS_KEY)
    if not isinstance(pending, dict) or not pending:
        return []

    target_tenant_id = str(tenant_id) if tenant_id else None
    matched_keys: list[tuple[str, str, str]] = []
    matched_items: list[dict[str, Any]] = []

    for key, item in pending.items():
        if item.get("entity_type") != entity_type:
            continue
        if entity_id and item.get("entity_id") != entity_id:
            continue
        if target_tenant_id and item.get("tenant_id") not in {None, target_tenant_id}:
            continue
        matched_keys.append(key)
        matched_items.append(item)

    for key in matched_keys:
        pending.pop(key, None)

    if not pending:
        session.info.pop(PENDING_MUTATION_BACKUPS_KEY, None)

    return matched_items


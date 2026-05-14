from datetime import UTC, datetime
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.db.mutation_tracking import consume_pending_mutation_backups
from app.models import AuditLog
from app.services.backup_service import record_mutation_backup

MUTATING_AUDIT_ACTION_MARKERS = (".update", ".delete", ".toggle", ".archive", ".deactivate", ".reactivate")


def _should_create_mutation_backup(action: str, tracked_items: list[dict]) -> bool:
    if tracked_items:
        return True
    return any(marker in action for marker in MUTATING_AUDIT_ACTION_MARKERS)


def record_audit(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str | None,
    tenant_id: UUID | None,
    user_id: UUID | None,
    metadata: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    normalized_metadata = jsonable_encoder(metadata or {})
    item = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        tenant_id=tenant_id,
        user_id=user_id,
        metadata_json=normalized_metadata,
        ip_address=ip_address,
        user_agent=user_agent,
        occurred_at=datetime.now(UTC),
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    tracked_items = consume_pending_mutation_backups(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        tenant_id=tenant_id,
    )
    if _should_create_mutation_backup(action, tracked_items):
        try:
            record_mutation_backup(
                db,
                tenant_id=tenant_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                metadata=normalized_metadata,
                tracked_items=tracked_items,
                requested_by_user_id=user_id,
                audit_log_id=item.id,
            )
        except Exception:
            pass

    return item

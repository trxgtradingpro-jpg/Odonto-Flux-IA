from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AuditLog


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
    item = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        tenant_id=tenant_id,
        user_id=user_id,
        metadata_json=metadata or {},
        ip_address=ip_address,
        user_agent=user_agent,
        occurred_at=datetime.now(UTC),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item

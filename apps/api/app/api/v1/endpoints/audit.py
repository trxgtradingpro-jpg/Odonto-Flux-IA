from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id
from app.db.session import get_db
from app.models import AuditLog
from app.schemas.audit import AuditLogOutput

router = APIRouter(prefix='/audit', tags=['audit'])


@router.get('')
def list_audit_logs(
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    action: str | None = None,
    entity_type: str | None = None,
    user_id: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
):
    stmt = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if start_at:
        stmt = stmt.where(AuditLog.occurred_at >= start_at)
    if end_at:
        stmt = stmt.where(AuditLog.occurred_at <= end_at)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(AuditLog.occurred_at.desc()).offset(offset).limit(limit)).scalars().all()

    return {'data': [AuditLogOutput.model_validate(item, from_attributes=True).model_dump() for item in rows], 'meta': {'total': total, 'limit': limit, 'offset': offset}}

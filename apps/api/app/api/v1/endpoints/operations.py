from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.models import Job, OutboxMessage, WebhookInbox
from app.models.enums import OutboxStatus
from app.services.audit_service import record_audit

router = APIRouter(prefix="/operations", tags=["operations"])


def _serialize_outbox(item: OutboxMessage) -> dict[str, object]:
    payload = item.payload if isinstance(item.payload, dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return {
        "source": "outbox",
        "id": str(item.id),
        "status": str(item.status),
        "summary": str(payload.get("message_type") or "message"),
        "detail": str(item.last_error or ""),
        "created_at": item.created_at.isoformat(),
        "conversation_id": str(payload.get("conversation_id") or metadata.get("conversation_id") or ""),
        "retry_count": int(item.retry_count or 0),
        "max_retries": int(item.max_retries or 0),
    }


def _serialize_job(item: Job) -> dict[str, object]:
    return {
        "source": "job",
        "id": str(item.id),
        "status": str(item.status),
        "summary": item.job_type,
        "detail": str(item.error_message or ""),
        "created_at": item.created_at.isoformat(),
        "retry_count": int(item.attempts or 0),
        "max_retries": int(item.max_attempts or 0),
    }


def _serialize_webhook(item: WebhookInbox) -> dict[str, object]:
    return {
        "source": "webhook",
        "id": str(item.id),
        "status": "failed" if item.error_message else "ok",
        "summary": item.provider,
        "detail": str(item.error_message or ""),
        "created_at": item.created_at.isoformat(),
        "event_id": item.event_id,
    }


@router.get("/overview")
def operations_overview(
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
):
    since_24h = datetime.now(UTC) - timedelta(hours=24)

    failed_outbox = db.execute(
        select(OutboxMessage).where(
            OutboxMessage.tenant_id == tenant_id,
            OutboxMessage.status.in_([OutboxStatus.FAILED.value, OutboxStatus.DEAD_LETTER.value]),
        )
    ).scalars().all()

    pending_outbox = db.execute(
        select(OutboxMessage).where(
            OutboxMessage.tenant_id == tenant_id,
            OutboxMessage.status.in_([OutboxStatus.PENDING.value, OutboxStatus.PROCESSING.value]),
        )
    ).scalars().all()

    failed_jobs_24h = db.execute(
        select(Job).where(
            Job.tenant_id == tenant_id,
            Job.status == "failed",
            Job.updated_at >= since_24h,
        )
    ).scalars().all()

    failed_webhooks = db.execute(
        select(WebhookInbox).where(
            WebhookInbox.tenant_id == tenant_id,
            WebhookInbox.error_message.is_not(None),
        )
    ).scalars().all()

    return {
        "outbox": {
            "failed": len(failed_outbox),
            "pending": len(pending_outbox),
            "dead_letter": len([item for item in failed_outbox if item.status == OutboxStatus.DEAD_LETTER.value]),
        },
        "jobs": {
            "failed_last_24h": len(failed_jobs_24h),
        },
        "webhooks": {
            "failed": len(failed_webhooks),
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


@router.get("/failures")
def list_failures(
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    limit: int = Query(default=30, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    outbox_rows = db.execute(
        select(OutboxMessage).where(
            OutboxMessage.tenant_id == tenant_id,
            OutboxMessage.status.in_([OutboxStatus.FAILED.value, OutboxStatus.DEAD_LETTER.value]),
        )
    ).scalars().all()
    job_rows = db.execute(
        select(Job).where(
            Job.tenant_id == tenant_id,
            Job.status == "failed",
        )
    ).scalars().all()
    webhook_rows = db.execute(
        select(WebhookInbox).where(
            WebhookInbox.tenant_id == tenant_id,
            WebhookInbox.error_message.is_not(None),
        )
    ).scalars().all()

    merged = [
        *[_serialize_outbox(item) for item in outbox_rows],
        *[_serialize_job(item) for item in job_rows],
        *[_serialize_webhook(item) for item in webhook_rows],
    ]
    merged.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    paginated = merged[offset : offset + limit]

    return {
        "data": paginated,
        "meta": {
            "total": len(merged),
            "limit": limit,
            "offset": offset,
        },
    }


@router.post("/outbox/{outbox_id}/retry")
def retry_outbox_item(
    outbox_id: str,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    item = db.scalar(
        select(OutboxMessage).where(
            OutboxMessage.id == outbox_id,
            OutboxMessage.tenant_id == tenant_id,
        )
    )
    if not item:
        raise ApiError(status_code=404, code="OUTBOX_NOT_FOUND", message="Item de outbox nao encontrado")

    item.status = OutboxStatus.PENDING.value
    item.retry_count = 0
    item.last_error = None
    item.next_retry_at = datetime.now(UTC)
    db.add(item)
    db.commit()
    db.refresh(item)

    record_audit(
        db,
        action="operations.outbox.retry",
        entity_type="outbox_message",
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={"status": item.status},
    )

    return {"id": str(item.id), "status": item.status, "retry_count": item.retry_count}


@router.post("/jobs/{job_id}/retry")
def retry_job_item(
    job_id: str,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    job = db.scalar(
        select(Job).where(
            Job.id == job_id,
            Job.tenant_id == tenant_id,
        )
    )
    if not job:
        raise ApiError(status_code=404, code="JOB_NOT_FOUND", message="Job nao encontrado")

    job.status = "pending"
    job.attempts = 0
    job.error_message = None
    job.started_at = None
    job.finished_at = None
    job.scheduled_for = datetime.now(UTC)
    db.add(job)
    db.commit()
    db.refresh(job)

    record_audit(
        db,
        action="operations.job.retry",
        entity_type="job",
        entity_id=str(job.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={"job_type": job.job_type},
    )

    return {"id": str(job.id), "status": job.status, "attempts": job.attempts}


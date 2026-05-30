from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ApiError
from app.models import (
    Conversation,
    Message,
    ProspectAccount,
    SalesOutreachAutomationBatch,
    SalesOutreachAutomationBatchItem,
    Tenant,
)
from app.services import sales_demo_service
from app.services.whatsapp_bridge_support import WHATSAPP_WEB_BRIDGE_TRANSPORT, resolve_sales_outreach_transport
from app.utils.phone import normalize_phone

BATCH_STATUS_ACTIVE = {"queued", "running"}
ITEM_STATUS_ACTIVE = {"queued", "demo_pending", "starting", "waiting_reply"}
ITEM_STATUS_TERMINAL = {"completed", "paused", "failed", "skipped"}

TERMINAL_COMPLETED_REASONS = {"sequence_completed", "direct_demo_offered", "opt_out"}
PAUSED_REASONS = {
    "requested_better_time",
    "reroute_requested",
    "access_blocked",
    "automated_channel",
    "awaiting_internal_forward",
    "clarification_sent",
    "awaiting_human_reply",
    "batch_paused",
}
DEMO_READY_STATUSES = {"criada", "enviada", "acessada"}
OUTREACH_AUTOMATION_STEPS = {
    "reception_intro",
    "reception_triage",
    "reception_cta",
    "clarification_reply",
    "clarification_cta",
    "direct_demo_offer",
    "decision_maker_pitch",
    "video_followup",
    "timing_followup",
    "routing_followup",
    "access_request",
}
OUTREACH_NO_WHATSAPP_TAG = "sem_whatsapp"


def _now() -> datetime:
    return datetime.now(UTC)


def _assert_whatsapp_web_bridge_enabled() -> None:
    if resolve_sales_outreach_transport() != WHATSAPP_WEB_BRIDGE_TRANSPORT:
        raise ApiError(
            status_code=409,
            code="OUTREACH_AUTOMATION_TRANSPORT_INVALID",
            message="A automacao comercial exige o transporte whatsapp_web.py ativo no sales_outreach_transport.",
        )
    if not str(settings.whatsapp_web_bridge_token or "").strip():
        raise ApiError(
            status_code=409,
            code="OUTREACH_AUTOMATION_BRIDGE_NOT_CONFIGURED",
            message="Configure WHATSAPP_WEB_BRIDGE_TOKEN antes de iniciar a automacao comercial.",
        )


def _temperature_rank(value: str | None) -> int:
    ranks = {"muito_quente": 4, "quente": 3, "morno": 2, "frio": 1}
    return ranks.get(str(value or "").strip(), 0)


def _is_demo_ready(prospect: ProspectAccount) -> bool:
    return bool(prospect.demo_tenant_id and str(prospect.demo_status or "").strip() in DEMO_READY_STATUSES)


def _has_valid_outreach_phone(prospect: ProspectAccount) -> bool:
    return bool(normalize_phone(prospect.whatsapp_phone or prospect.phone))


def _item_status_from_outreach(prospect: ProspectAccount) -> tuple[str, str | None]:
    outreach = sales_demo_service._outreach_snapshot(prospect)
    stop_reason = str(outreach.get("automation_stop_reason") or "").strip() or None
    if prospect.do_not_contact or stop_reason == "opt_out":
        return "completed", "opt_out"
    if bool(outreach.get("automation_active")):
        return "waiting_reply", None
    if stop_reason in TERMINAL_COMPLETED_REASONS:
        return "completed", stop_reason
    if stop_reason in PAUSED_REASONS:
        return "paused", stop_reason
    if str(outreach.get("last_step") or "").strip() in {"video_followup", "direct_demo_offer"}:
        return "completed", stop_reason
    return "queued", stop_reason


def _append_note_line(existing_notes: str | None, note_line: str) -> str:
    current = str(existing_notes or "").strip()
    normalized_line = str(note_line or "").strip()
    if not normalized_line:
        return current
    if normalized_line in current:
        return current
    return f"{current}\n{normalized_line}".strip() if current else normalized_line


def _batch_summary(db: Session, batch: SalesOutreachAutomationBatch) -> dict:
    items = db.execute(
        select(SalesOutreachAutomationBatchItem.status).where(SalesOutreachAutomationBatchItem.batch_id == batch.id)
    ).scalars().all()
    summary = {
        "queued": 0,
        "demo_pending": 0,
        "starting": 0,
        "waiting_reply": 0,
        "completed": 0,
        "paused": 0,
        "failed": 0,
        "skipped": 0,
        "total": len(items),
    }
    for status in items:
        key = str(status or "").strip()
        if key in summary:
            summary[key] += 1
    return summary


def _refresh_batch_status(db: Session, batch: SalesOutreachAutomationBatch) -> SalesOutreachAutomationBatch:
    summary = _batch_summary(db, batch)
    batch.summary_json = summary
    batch.last_processed_at = _now()

    active_total = sum(summary.get(key, 0) for key in ITEM_STATUS_ACTIVE)
    terminal_total = sum(summary.get(key, 0) for key in ITEM_STATUS_TERMINAL)
    if batch.status == "paused":
        db.add(batch)
        return batch
    if batch.status == "queued" and not batch.started_at:
        db.add(batch)
        return batch
    if summary["total"] == 0:
        batch.status = "completed"
        batch.completed_at = batch.completed_at or _now()
    elif active_total > 0:
        batch.status = "running"
        batch.completed_at = None
    elif terminal_total == summary["total"]:
        batch.status = "completed"
        batch.completed_at = batch.completed_at or _now()
    db.add(batch)
    return batch


def _serialize_batch_item(db: Session, item: SalesOutreachAutomationBatchItem) -> dict:
    prospect = db.get(ProspectAccount, item.prospect_account_id)
    return {
        "id": item.id,
        "prospect": sales_demo_service.serialize_prospect(db, prospect, include_children=False) if prospect else None,
        "status": item.status,
        "current_step": item.current_step,
        "last_reply_classification": item.last_reply_classification,
        "pause_reason": item.pause_reason,
        "last_message_preview": item.last_message_preview,
        "last_error_message": item.last_error_message,
        "demo_generated_automatically": item.demo_generated_automatically,
        "conversation_id": item.conversation_id,
        "last_outbound_message_id": item.last_outbound_message_id,
        "last_inbound_message_id": item.last_inbound_message_id,
        "sent_count": item.sent_count,
        "received_count": item.received_count,
        "attempts": item.attempts,
        "started_at": item.started_at,
        "last_activity_at": item.last_activity_at,
        "finished_at": item.finished_at,
        "details": item.details_json or {},
        "open_adm_whatsapp_href": f"/adm?section=adm_whatsapp&prospect_id={item.prospect_account_id}",
    }


def serialize_batch(db: Session, batch: SalesOutreachAutomationBatch, *, include_items: bool = False) -> dict:
    summary = batch.summary_json if isinstance(batch.summary_json, dict) else _batch_summary(db, batch)
    payload = {
        "id": batch.id,
        "tenant_id": batch.tenant_id,
        "created_by_user_id": batch.created_by_user_id,
        "status": batch.status,
        "requested_count": batch.requested_count,
        "selected_count": batch.selected_count,
        "filters": batch.filters_json or {},
        "summary": summary,
        "stop_reason": batch.stop_reason,
        "started_at": batch.started_at,
        "paused_at": batch.paused_at,
        "completed_at": batch.completed_at,
        "last_processed_at": batch.last_processed_at,
        "created_at": batch.created_at,
        "updated_at": batch.updated_at,
    }
    if include_items:
        rows = db.execute(
            select(SalesOutreachAutomationBatchItem)
            .where(SalesOutreachAutomationBatchItem.batch_id == batch.id)
            .order_by(SalesOutreachAutomationBatchItem.created_at.asc())
        ).scalars().all()
        payload["items"] = [_serialize_batch_item(db, item) for item in rows]
    return payload


def _eligible_filters_expression(filters: dict) -> list:
    clauses = [
        ProspectAccount.do_not_contact.is_(False),
        or_(ProspectAccount.whatsapp_phone.is_not(None), ProspectAccount.phone.is_not(None)),
        ProspectAccount.status.not_in(["fechado_ganho", "fechado_perdido"]),
    ]
    if str(filters.get("status") or "").strip():
        clauses.append(ProspectAccount.status == str(filters["status"]).strip())
    if str(filters.get("temperature") or "").strip():
        clauses.append(ProspectAccount.temperature == str(filters["temperature"]).strip())
    if str(filters.get("demo_status") or "").strip():
        clauses.append(ProspectAccount.demo_status == str(filters["demo_status"]).strip())
    if filters.get("only_without_demo") is True:
        clauses.append(or_(ProspectAccount.demo_tenant_id.is_(None), ProspectAccount.demo_status.not_in(list(DEMO_READY_STATUSES))))
    if filters.get("only_with_demo") is True:
        clauses.append(ProspectAccount.demo_tenant_id.is_not(None))
    if str(filters.get("q") or "").strip():
        term = f"%{str(filters['q']).strip().lower()}%"
        clauses.append(
            func.lower(
                func.concat(
                    ProspectAccount.clinic_name,
                    " ",
                    func.coalesce(ProspectAccount.city, ""),
                    " ",
                    func.coalesce(ProspectAccount.state, ""),
                )
            ).like(term)
        )
    return clauses


def _active_prospect_ids_in_batches(db: Session) -> set[UUID]:
    rows = db.execute(
        select(SalesOutreachAutomationBatchItem.prospect_account_id).where(
            SalesOutreachAutomationBatchItem.status.in_(list(ITEM_STATUS_ACTIVE))
        )
    ).scalars().all()
    return {row for row in rows}


def list_eligible_prospects(db: Session, *, quantity: int, filters: dict | None = None) -> list[ProspectAccount]:
    criteria = _eligible_filters_expression(filters or {})
    prospects = db.execute(
        select(ProspectAccount)
        .where(*criteria)
        .order_by(ProspectAccount.score.desc(), ProspectAccount.created_at.asc())
    ).scalars().all()
    active_ids = _active_prospect_ids_in_batches(db)
    filtered = [item for item in prospects if item.id not in active_ids and _has_valid_outreach_phone(item)]
    filtered.sort(key=lambda item: (_temperature_rank(item.temperature), item.score, item.created_at.timestamp()), reverse=True)
    return filtered[:quantity]


def eligible_summary(db: Session, *, filters: dict | None = None, limit: int = 20) -> dict:
    filters = filters or {}
    criteria = _eligible_filters_expression(filters)
    prospects = db.execute(select(ProspectAccount).where(*criteria)).scalars().all()
    active_ids = _active_prospect_ids_in_batches(db)
    rows = [item for item in prospects if item.id not in active_ids and _has_valid_outreach_phone(item)]
    rows.sort(key=lambda item: (_temperature_rank(item.temperature), item.score, item.created_at.timestamp()), reverse=True)
    return {
        "eligible_count": len(rows),
        "preview": [sales_demo_service.serialize_prospect(db, item, include_children=False) for item in rows[:limit]],
        "filters": filters,
    }


def _enqueue_batch_processing(batch_id: UUID) -> None:
    try:
        from app.tasks.jobs import process_sales_outreach_batch_task

        process_sales_outreach_batch_task.delay(str(batch_id))
    except Exception:
        pass


def create_batch(
    db: Session,
    *,
    quantity: int,
    filters: dict | None,
    actor_id: UUID | None,
) -> dict:
    _assert_whatsapp_web_bridge_enabled()
    sender_tenant = sales_demo_service.ensure_sales_outreach_sender_tenant(db)
    normalized_filters = jsonable_encoder(filters or {})
    prospects = list_eligible_prospects(db, quantity=quantity, filters=normalized_filters)

    batch = SalesOutreachAutomationBatch(
        tenant_id=sender_tenant.id,
        created_by_user_id=actor_id,
        status="queued",
        requested_count=quantity,
        selected_count=len(prospects),
        filters_json=normalized_filters,
        summary_json={},
    )
    db.add(batch)
    db.flush()

    for prospect in prospects:
        db.add(
            SalesOutreachAutomationBatchItem(
                batch_id=batch.id,
                prospect_account_id=prospect.id,
                status="queued",
            )
        )

    if not prospects:
        batch.status = "completed"
        batch.stop_reason = "no_eligible_prospects"
        batch.completed_at = _now()
    _refresh_batch_status(db, batch)
    db.commit()
    db.refresh(batch)

    if prospects:
        _enqueue_batch_processing(batch.id)
    return serialize_batch(db, batch, include_items=True)


def list_batches(db: Session, *, limit: int = 20) -> dict:
    rows = db.execute(
        select(SalesOutreachAutomationBatch)
        .order_by(SalesOutreachAutomationBatch.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return {"data": [serialize_batch(db, item) for item in rows]}


def get_batch(db: Session, batch_id: UUID) -> dict:
    batch = db.get(SalesOutreachAutomationBatch, batch_id)
    if not batch:
        raise ApiError(status_code=404, code="OUTREACH_BATCH_NOT_FOUND", message="Lote de automacao nao encontrado.")
    return serialize_batch(db, batch, include_items=True)


def process_batch(db: Session, *, batch_id: UUID) -> dict:
    _assert_whatsapp_web_bridge_enabled()
    batch = db.get(SalesOutreachAutomationBatch, batch_id)
    if not batch:
        raise ApiError(status_code=404, code="OUTREACH_BATCH_NOT_FOUND", message="Lote de automacao nao encontrado.")
    if batch.status == "paused":
        return serialize_batch(db, batch, include_items=True)

    batch.status = "running"
    batch.started_at = batch.started_at or _now()
    db.add(batch)
    db.commit()

    items = db.execute(
        select(SalesOutreachAutomationBatchItem)
        .where(
            SalesOutreachAutomationBatchItem.batch_id == batch.id,
            SalesOutreachAutomationBatchItem.status.in_(["queued", "failed"]),
        )
        .order_by(SalesOutreachAutomationBatchItem.created_at.asc())
    ).scalars().all()

    for item in items:
        prospect = db.get(ProspectAccount, item.prospect_account_id)
        item.started_at = item.started_at or _now()
        item.last_activity_at = _now()
        item.attempts += 1
        item.status = "starting"
        db.add(item)
        db.commit()

        if not prospect:
            item.status = "skipped"
            item.pause_reason = "prospect_missing"
            item.finished_at = _now()
            db.add(item)
            db.commit()
            continue

        if not _has_valid_outreach_phone(prospect):
            item.status = "skipped"
            item.pause_reason = "phone_invalid"
            item.last_error_message = "Prospect sem telefone valido para outreach."
            item.finished_at = _now()
            db.add(item)
            db.commit()
            continue

        try:
            if not _is_demo_ready(prospect):
                item.status = "demo_pending"
                db.add(item)
                db.commit()
                sales_demo_service.generate_demo(
                    db,
                    prospect,
                    actor_id=batch.created_by_user_id,
                    base_url=sales_demo_service._default_sales_outreach_base_url(),
                )
                db.refresh(prospect)
                item.demo_generated_automatically = True

            outreach = sales_demo_service._outreach_snapshot(prospect)
            if bool(outreach.get("automation_active")):
                item.status = "paused"
                item.pause_reason = "already_active"
                item.last_error_message = "A clinica ja estava com automacao comercial ativa."
                item.finished_at = _now()
                db.add(item)
                db.commit()
                continue

            result = sales_demo_service.start_sales_outreach_automation(
                db,
                prospect=prospect,
                actor_id=batch.created_by_user_id,
                base_url=sales_demo_service._default_sales_outreach_base_url(),
            )
            db.refresh(prospect)
            outreach = sales_demo_service._outreach_snapshot(prospect)
            item.status = "waiting_reply"
            item.pause_reason = None
            item.current_step = str(result.get("step") or outreach.get("last_step") or "").strip() or None
            item.conversation_id = result.get("conversation_id")
            item.last_outbound_message_id = result.get("outbound_message_id")
            item.sent_count = max(item.sent_count, 1)
            item.last_message_preview = str(result.get("message_text") or "")[:1000] or item.last_message_preview
            item.details_json = {
                **(item.details_json if isinstance(item.details_json, dict) else {}),
                "demo_login_url": result.get("demo_login_url"),
                "transport": result.get("transport"),
            }
            db.add(item)
            db.commit()
        except Exception as exc:
            item.status = "failed"
            item.last_error_message = str(exc)[:2000]
            item.finished_at = _now()
            db.add(item)
            db.commit()

    batch = db.get(SalesOutreachAutomationBatch, batch.id)
    _refresh_batch_status(db, batch)
    db.commit()
    db.refresh(batch)
    return serialize_batch(db, batch, include_items=True)


def pause_batch(db: Session, *, batch_id: UUID) -> dict:
    batch = db.get(SalesOutreachAutomationBatch, batch_id)
    if not batch:
        raise ApiError(status_code=404, code="OUTREACH_BATCH_NOT_FOUND", message="Lote de automacao nao encontrado.")

    now = _now()
    batch.status = "paused"
    batch.paused_at = now
    batch.stop_reason = "manual_pause"
    db.add(batch)

    items = db.execute(
        select(SalesOutreachAutomationBatchItem).where(
            SalesOutreachAutomationBatchItem.batch_id == batch.id,
            SalesOutreachAutomationBatchItem.status.in_(["queued", "demo_pending", "starting", "waiting_reply"]),
        )
    ).scalars().all()
    for item in items:
        prospect = db.get(ProspectAccount, item.prospect_account_id)
        if prospect:
            sales_demo_service._update_outreach_snapshot(
                prospect,
                patch={
                    "automation_active": False,
                    "automation_stopped_at": now.isoformat(),
                    "automation_stop_reason": "batch_paused",
                },
            )
            db.add(prospect)
        item.status = "paused"
        item.pause_reason = "batch_paused"
        item.last_activity_at = now
        db.add(item)

    _refresh_batch_status(db, batch)
    db.commit()
    db.refresh(batch)
    return serialize_batch(db, batch, include_items=True)


def resume_batch(db: Session, *, batch_id: UUID) -> dict:
    _assert_whatsapp_web_bridge_enabled()
    batch = db.get(SalesOutreachAutomationBatch, batch_id)
    if not batch:
        raise ApiError(status_code=404, code="OUTREACH_BATCH_NOT_FOUND", message="Lote de automacao nao encontrado.")

    batch.status = "running"
    batch.paused_at = None
    batch.stop_reason = None
    db.add(batch)

    items = db.execute(
        select(SalesOutreachAutomationBatchItem).where(
            SalesOutreachAutomationBatchItem.batch_id == batch.id,
            SalesOutreachAutomationBatchItem.status == "paused",
            SalesOutreachAutomationBatchItem.pause_reason == "batch_paused",
        )
    ).scalars().all()
    for item in items:
        prospect = db.get(ProspectAccount, item.prospect_account_id)
        if prospect and item.current_step:
            sales_demo_service._update_outreach_snapshot(
                prospect,
                patch={
                    "automation_active": True,
                    "automation_stopped_at": None,
                    "automation_stop_reason": None,
                },
            )
            db.add(prospect)
        item.status = "waiting_reply" if item.current_step else "queued"
        item.pause_reason = None
        item.finished_at = None
        db.add(item)

    _refresh_batch_status(db, batch)
    db.commit()
    db.refresh(batch)
    _enqueue_batch_processing(batch.id)
    return serialize_batch(db, batch, include_items=True)


def delete_batch(db: Session, *, batch_id: UUID) -> None:
    batch = db.get(SalesOutreachAutomationBatch, batch_id)
    if not batch:
        raise ApiError(status_code=404, code="OUTREACH_BATCH_NOT_FOUND", message="Lote de automacao nao encontrado.")

    db.execute(delete(SalesOutreachAutomationBatchItem).where(SalesOutreachAutomationBatchItem.batch_id == batch.id))
    db.execute(delete(SalesOutreachAutomationBatch).where(SalesOutreachAutomationBatch.id == batch.id))
    db.commit()


def remove_prospect_from_batches_for_missing_whatsapp(
    db: Session,
    *,
    prospect_id: UUID,
    reason: str,
    outbox_id: UUID | None = None,
) -> dict:
    prospect = db.get(ProspectAccount, prospect_id)
    if not prospect:
        return {"removed_items": 0, "deleted_batches": 0, "batch_ids": []}

    note_timestamp = _now().astimezone().strftime("%d/%m/%Y %H:%M")
    note_line = f"{note_timestamp} - Numero removido do lote comercial: nao possui WhatsApp ativo."
    tags = [str(tag or "").strip() for tag in (prospect.tags or []) if str(tag or "").strip()]
    if OUTREACH_NO_WHATSAPP_TAG not in tags:
        tags.append(OUTREACH_NO_WHATSAPP_TAG)
    prospect.tags = tags
    prospect.do_not_contact = True
    prospect.notes = _append_note_line(prospect.notes, note_line)
    db.add(prospect)
    sales_demo_service.add_timeline(
        db,
        prospect,
        event_type="prospect.outreach.phone_missing_whatsapp",
        event_label="Numero removido do lote comercial por nao ter WhatsApp",
        actor_type="system",
        payload={
            "reason": str(reason or "").strip()[:1000],
            "outbox_id": str(outbox_id) if outbox_id else None,
        },
    )

    items = db.execute(
        select(SalesOutreachAutomationBatchItem)
        .join(SalesOutreachAutomationBatch, SalesOutreachAutomationBatch.id == SalesOutreachAutomationBatchItem.batch_id)
        .where(
            SalesOutreachAutomationBatchItem.prospect_account_id == prospect_id,
            SalesOutreachAutomationBatch.status.in_(["queued", "running", "paused"]),
        )
    ).scalars().all()

    affected_batch_ids: set[UUID] = set()
    for item in items:
        affected_batch_ids.add(item.batch_id)
        db.execute(delete(SalesOutreachAutomationBatchItem).where(SalesOutreachAutomationBatchItem.id == item.id))

    deleted_batches = 0
    for batch_id in affected_batch_ids:
        batch = db.get(SalesOutreachAutomationBatch, batch_id)
        if not batch:
            continue
        remaining_items = db.execute(
            select(func.count())
            .select_from(SalesOutreachAutomationBatchItem)
            .where(SalesOutreachAutomationBatchItem.batch_id == batch_id)
        ).scalar_one()
        if not remaining_items:
            db.execute(delete(SalesOutreachAutomationBatch).where(SalesOutreachAutomationBatch.id == batch_id))
            deleted_batches += 1
            continue
        batch.selected_count = int(remaining_items)
        _refresh_batch_status(db, batch)
        db.add(batch)

    return {
        "removed_items": len(items),
        "deleted_batches": deleted_batches,
        "batch_ids": [str(batch_id) for batch_id in affected_batch_ids],
    }


def sync_batch_item_for_prospect(
    db: Session,
    *,
    prospect: ProspectAccount,
    message: Message | None = None,
    conversation: Conversation | None = None,
) -> None:
    item = db.execute(
        select(SalesOutreachAutomationBatchItem)
        .join(SalesOutreachAutomationBatch, SalesOutreachAutomationBatch.id == SalesOutreachAutomationBatchItem.batch_id)
        .where(SalesOutreachAutomationBatchItem.prospect_account_id == prospect.id)
        .where(SalesOutreachAutomationBatch.status.in_(["queued", "running", "paused"]))
        .order_by(SalesOutreachAutomationBatchItem.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if not item:
        return

    outreach = sales_demo_service._outreach_snapshot(prospect)
    item.current_step = str(outreach.get("last_step") or "").strip() or item.current_step
    item.last_reply_classification = str(outreach.get("last_reply_classification") or "").strip() or item.last_reply_classification
    item.last_message_preview = (
        str(outreach.get("last_reply_preview") or "").strip() or item.last_message_preview
    )
    item.conversation_id = conversation.id if conversation else item.conversation_id
    item.last_activity_at = _now()
    item.details_json = {
        **(item.details_json if isinstance(item.details_json, dict) else {}),
        "last_dispatch_status": outreach.get("last_dispatch_status"),
        "dispatch_transport": outreach.get("dispatch_transport"),
        "last_demo_login_url": outreach.get("last_demo_login_url"),
    }

    if message:
        if message.direction == "outbound":
            item.last_outbound_message_id = message.id
            item.sent_count += 1
            item.last_message_preview = str(message.body or "").strip()[:1000] or item.last_message_preview
        elif message.direction == "inbound":
            item.last_inbound_message_id = message.id
            item.received_count += 1
            item.last_message_preview = str(message.body or "").strip()[:1000] or item.last_message_preview

    item.status, item.pause_reason = _item_status_from_outreach(prospect)
    if item.status in ITEM_STATUS_TERMINAL:
        item.finished_at = item.finished_at or _now()
    else:
        item.finished_at = None
    db.add(item)

    batch = db.get(SalesOutreachAutomationBatch, item.batch_id)
    if batch:
        _refresh_batch_status(db, batch)
        db.add(batch)

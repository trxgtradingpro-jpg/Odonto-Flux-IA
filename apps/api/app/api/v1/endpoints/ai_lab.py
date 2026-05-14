from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.db.session import get_db
from app.services.ai_lab_service import clear_history, list_history, save_manual_edit, simulate
from app.services.audit_service import record_audit

router = APIRouter(prefix="/settings/ai-lab", tags=["ai_lab"])


@router.post("/simulate")
def simulate_ai_lab(
    payload: dict,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    result = simulate(
        db,
        tenant_id=tenant_id,
        message=str(payload.get("message") or ""),
        context_text=str(payload.get("context_text") or ""),
        include_knowledge=bool(payload.get("include_knowledge", True)),
        use_training_examples=bool(payload.get("use_training_examples", True)),
        auto_save_history=bool(payload.get("auto_save_history", True)),
        flow_mode=str(payload.get("flow_mode") or "auto"),
        persist_conversation=bool(payload.get("persist_conversation", False)),
        lab_conversation_id=str(payload.get("lab_conversation_id") or "").strip() or None,
    )
    record_audit(
        db,
        action="ai_lab.simulate",
        entity_type="ai_lab",
        entity_id=(result.get("history_entry") or {}).get("id"),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={
            "contract_valid": bool(result.get("contract_valid")),
            "contract_retried": bool(result.get("contract_retried")),
            "next_action": ((result.get("response") or {}).get("next_action") if isinstance(result.get("response"), dict) else None),
            "flow_mode": result.get("flow_mode"),
            "structured_flow": bool(result.get("structured_flow")),
            "no_dispatch": bool(result.get("no_dispatch")),
            "no_persistence": bool(result.get("no_persistence")),
        },
    )
    return result


@router.get("/history")
def list_ai_lab_history(
    limit: int = Query(default=40, ge=1, le=120),
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
):
    data = list_history(db, tenant_id=tenant_id, limit=limit)
    return {
        "data": data,
        "meta": {
            "total": len(data),
            "limit": limit,
        },
    }


@router.post("/history")
def save_ai_lab_history_edit(
    payload: dict,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    item = save_manual_edit(
        db,
        tenant_id=tenant_id,
        history_id=str(payload.get("history_id") or "").strip() or None,
        input_text=str(payload.get("input_text") or ""),
        edited_response_text=str(payload.get("edited_response_text") or ""),
        note=str(payload.get("note") or ""),
    )
    record_audit(
        db,
        action="ai_lab.history.save_edit",
        entity_type="ai_lab_entry",
        entity_id=item.get("id"),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={"has_note": bool(item.get("note"))},
    )
    return item


@router.delete("/history")
def clear_ai_lab_history(
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    removed = clear_history(db, tenant_id=tenant_id)
    record_audit(
        db,
        action="ai_lab.history.clear",
        entity_type="ai_lab",
        entity_id=None,
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={"removed": removed},
    )
    return {"removed": removed}

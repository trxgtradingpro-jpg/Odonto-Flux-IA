from copy import deepcopy
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.models import AuditLog, Automation, AutomationRun
from app.schemas.automation import (
    AutomationCreate,
    AutomationDraftSimulationInput,
    AutomationHistoryOutput,
    AutomationManualExecuteInput,
    AutomationManualExecuteOutput,
    AutomationOutput,
    AutomationRunOutput,
    AutomationSimulationInput,
    AutomationUpdate,
)
from app.services.audit_service import record_audit
from app.services.automation_service import emit_event, enqueue_manual_automation_run, simulate_automation_definition

router = APIRouter(prefix='/automations', tags=['automations'])


@router.get('')
def list_automations(
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    limit: int = Query(default=20, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(Automation).where(Automation.tenant_id == tenant_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Automation.created_at.desc()).offset(offset).limit(limit)).scalars().all()
    return {'data': [AutomationOutput.model_validate(item, from_attributes=True).model_dump() for item in rows], 'meta': {'total': total, 'limit': limit, 'offset': offset}}


@router.post('', response_model=AutomationOutput)
def create_automation(
    payload: AutomationCreate,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    item = Automation(tenant_id=tenant_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)

    record_audit(
        db,
        action='automation.create',
        entity_type='automation',
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'trigger': item.trigger_key},
    )
    return AutomationOutput.model_validate(item, from_attributes=True)


@router.post('/simulate-config')
def simulate_draft_automation(
    payload: AutomationDraftSimulationInput,
    tenant_id=Depends(get_tenant_id),
):
    draft = payload.automation.model_dump()
    draft['tenant_id'] = str(tenant_id)
    return simulate_automation_definition(
        automation=draft,
        trigger_payload=payload.trigger_payload,
    )


@router.patch('/{automation_id}', response_model=AutomationOutput)
def update_automation(
    automation_id: str,
    payload: AutomationUpdate,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    item = db.scalar(
        select(Automation).where(Automation.id == automation_id, Automation.tenant_id == tenant_id)
    )
    if not item:
        raise ApiError(status_code=404, code='AUTOMATION_NOT_FOUND', message='Automacao nao encontrada')

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(item, key, value)

    db.add(item)
    db.commit()
    db.refresh(item)

    record_audit(
        db,
        action='automation.update',
        entity_type='automation',
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata=updates,
    )

    return AutomationOutput.model_validate(item, from_attributes=True)


@router.post('/{automation_id}/duplicate', response_model=AutomationOutput)
def duplicate_automation(
    automation_id: str,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    item = db.scalar(
        select(Automation).where(Automation.id == automation_id, Automation.tenant_id == tenant_id)
    )
    if not item:
        raise ApiError(status_code=404, code='AUTOMATION_NOT_FOUND', message='Automacao nao encontrada')

    copy = Automation(
        tenant_id=tenant_id,
        name=f'{item.name} (copia)',
        description=item.description,
        trigger_type=item.trigger_type,
        trigger_key=item.trigger_key,
        conditions=deepcopy(item.conditions or {}),
        actions=deepcopy(item.actions or []),
        retry_policy=deepcopy(item.retry_policy or {}),
        is_active=False,
        paused_at=datetime.now(UTC),
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)

    record_audit(
        db,
        action='automation.duplicate',
        entity_type='automation',
        entity_id=str(copy.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'source_automation_id': str(item.id)},
    )
    return AutomationOutput.model_validate(copy, from_attributes=True)


@router.post('/{automation_id}/simulate')
def simulate_saved_automation(
    automation_id: str,
    payload: AutomationSimulationInput,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
):
    item = db.scalar(
        select(Automation).where(Automation.id == automation_id, Automation.tenant_id == tenant_id)
    )
    if not item:
        raise ApiError(status_code=404, code='AUTOMATION_NOT_FOUND', message='Automacao nao encontrada')

    return simulate_automation_definition(
        automation={
            'name': item.name,
            'description': item.description,
            'trigger_type': item.trigger_type,
            'trigger_key': item.trigger_key,
            'conditions': item.conditions or {},
            'actions': item.actions or [],
            'retry_policy': item.retry_policy or {},
            'is_active': item.is_active,
        },
        trigger_payload=payload.trigger_payload,
    )


@router.post('/{automation_id}/execute', response_model=AutomationManualExecuteOutput)
def execute_saved_automation_manually(
    automation_id: str,
    payload: AutomationManualExecuteInput,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    if payload.confirmation != 'EXECUTAR':
        raise ApiError(
            status_code=400,
            code='AUTOMATION_CONFIRMATION_REQUIRED',
            message='Digite EXECUTAR para confirmar a execucao manual',
        )

    item = db.scalar(
        select(Automation).where(Automation.id == automation_id, Automation.tenant_id == tenant_id)
    )
    if not item:
        raise ApiError(status_code=404, code='AUTOMATION_NOT_FOUND', message='Automacao nao encontrada')

    run, simulation = enqueue_manual_automation_run(
        db,
        automation=item,
        trigger_payload=payload.trigger_payload,
    )

    record_audit(
        db,
        action='automation.execute_manual',
        entity_type='automation',
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={
            'run_id': str(run.id) if run else None,
            'will_run': simulation.get('will_run'),
            'reason': simulation.get('reason'),
        },
    )

    return AutomationManualExecuteOutput(
        run_created=bool(run),
        run_id=run.id if run else None,
        simulation=simulation,
    )


@router.get('/{automation_id}/history')
def automation_history(
    automation_id: str,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    item = db.scalar(
        select(Automation).where(Automation.id == automation_id, Automation.tenant_id == tenant_id)
    )
    if not item:
        raise ApiError(status_code=404, code='AUTOMATION_NOT_FOUND', message='Automacao nao encontrada')

    stmt = select(AuditLog).where(
        AuditLog.tenant_id == tenant_id,
        AuditLog.entity_type == 'automation',
        AuditLog.entity_id == str(item.id),
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(AuditLog.occurred_at.desc()).offset(offset).limit(limit)).scalars().all()
    data = [
        AutomationHistoryOutput(
            id=row.id,
            action=row.action,
            user_id=row.user_id,
            metadata=row.metadata_json or {},
            occurred_at=row.occurred_at,
        ).model_dump()
        for row in rows
    ]
    return {'data': data, 'meta': {'total': total, 'limit': limit, 'offset': offset}}


@router.post('/{automation_id}/pause')
def pause_automation(
    automation_id: str,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    item = db.scalar(
        select(Automation).where(Automation.id == automation_id, Automation.tenant_id == tenant_id)
    )
    if not item:
        raise ApiError(status_code=404, code='AUTOMATION_NOT_FOUND', message='Automacao nao encontrada')
    item.is_active = False
    item.paused_at = datetime.now(UTC)
    db.add(item)
    db.commit()

    record_audit(
        db,
        action='automation.pause',
        entity_type='automation',
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
    )
    return {'message': 'Automacao pausada com sucesso'}


@router.post('/{automation_id}/resume')
def resume_automation(
    automation_id: str,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    item = db.scalar(
        select(Automation).where(Automation.id == automation_id, Automation.tenant_id == tenant_id)
    )
    if not item:
        raise ApiError(status_code=404, code='AUTOMATION_NOT_FOUND', message='Automacao nao encontrada')
    item.is_active = True
    item.paused_at = None
    db.add(item)
    db.commit()

    record_audit(
        db,
        action='automation.resume',
        entity_type='automation',
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
    )
    return {'message': 'Automacao reativada com sucesso'}


@router.get('/runs')
def list_runs(
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    automation_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(AutomationRun).where(AutomationRun.tenant_id == tenant_id)
    if automation_id:
        stmt = stmt.where(AutomationRun.automation_id == automation_id)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(AutomationRun.created_at.desc()).offset(offset).limit(limit)).scalars().all()
    return {'data': [AutomationRunOutput.model_validate(item, from_attributes=True).model_dump() for item in rows], 'meta': {'total': total, 'limit': limit, 'offset': offset}}


@router.post('/emit/{event_key}')
def emit_manual_event(
    event_key: str,
    payload: dict,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
):
    runs = emit_event(db, tenant_id=tenant_id, event_key=event_key, payload=payload)
    return {'event_key': event_key, 'runs_created': len(runs)}

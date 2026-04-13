from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.models import (
    Automation,
    AutomationRun,
    Conversation,
    OutboxMessage,
    Patient,
    PatientTag,
)
from app.models.enums import OutboxStatus, RunStatus
from app.utils.phone import normalize_phone


def _conditions_match(conditions: dict, payload: dict) -> bool:
    if not conditions:
        return True
    for key, expected_value in conditions.items():
        current = payload.get(key)
        if isinstance(expected_value, list):
            if current not in expected_value:
                return False
        else:
            if current != expected_value:
                return False
    return True



def emit_event(db: Session, *, tenant_id: UUID, event_key: str, payload: dict) -> list[AutomationRun]:
    automations = db.execute(
        select(Automation).where(
            Automation.tenant_id == tenant_id,
            Automation.is_active.is_(True),
            Automation.trigger_type == 'event',
            Automation.trigger_key == event_key,
        )
    ).scalars().all()

    runs: list[AutomationRun] = []
    for automation in automations:
        if not _conditions_match(automation.conditions or {}, payload):
            continue
        run = AutomationRun(
            tenant_id=tenant_id,
            automation_id=automation.id,
            status=RunStatus.PENDING.value,
            trigger_payload=payload,
        )
        db.add(run)
        runs.append(run)

    db.commit()

    from app.tasks.jobs import execute_automation_run_task

    for run in runs:
        execute_automation_run_task.delay(str(run.id))

    return runs



def _enqueue_outbox(db: Session, *, tenant_id: UUID, payload: dict) -> OutboxMessage:
    item = OutboxMessage(
        tenant_id=tenant_id,
        channel='whatsapp',
        status=OutboxStatus.PENDING.value,
        payload=payload,
        retry_count=0,
        max_retries=5,
    )
    db.add(item)
    db.flush()
    return item



def _execute_action(db: Session, *, tenant_id: UUID, action: dict, trigger_payload: dict) -> dict:
    action_type = action.get('type')
    params = action.get('params', {})

    if action_type == 'send_message':
        destination = params.get('to') or trigger_payload.get('phone')
        normalized_to = normalize_phone(destination)
        body = params.get('body') or trigger_payload.get('default_message', '')
        if not normalized_to:
            return {'action': action_type, 'ignored': True, 'reason': 'destino_ausente'}
        if not (body or '').strip():
            return {'action': action_type, 'ignored': True, 'reason': 'mensagem_vazia'}

        outbox = _enqueue_outbox(
            db,
            tenant_id=tenant_id,
            payload={
                'conversation_id': trigger_payload.get('conversation_id') or params.get('conversation_id'),
                'to': normalized_to,
                'body': body,
                'message_type': params.get('message_type', 'text'),
                'template': params.get('template'),
                'metadata': {'source': 'automation', 'trigger_payload': trigger_payload},
            },
        )
        return {'action': action_type, 'outbox_id': str(outbox.id)}

    if action_type == 'add_tag':
        patient_id = params.get('patient_id') or trigger_payload.get('patient_id')
        tag = params.get('tag')
        if patient_id and tag:
            existing = db.scalar(
                select(PatientTag).where(
                    PatientTag.tenant_id == tenant_id,
                    PatientTag.patient_id == patient_id,
                    PatientTag.tag == tag,
                )
            )
            if not existing:
                db.add(PatientTag(tenant_id=tenant_id, patient_id=patient_id, tag=tag))
            patient = db.get(Patient, patient_id)
            if patient:
                tags = set(patient.tags_cache or [])
                tags.add(tag)
                patient.tags_cache = sorted(tags)
                db.add(patient)
        return {'action': action_type, 'tag': tag, 'patient_id': patient_id}

    if action_type == 'alter_status_conversa':
        conversation_id = params.get('conversation_id') or trigger_payload.get('conversation_id')
        new_status = params.get('status', 'finalizada')
        if conversation_id:
            conversation = db.get(Conversation, conversation_id)
            if conversation and conversation.tenant_id == tenant_id:
                conversation.status = new_status
                db.add(conversation)
        return {'action': action_type, 'conversation_id': conversation_id, 'status': new_status}

    if action_type == 'fila_humana':
        conversation_id = params.get('conversation_id') or trigger_payload.get('conversation_id')
        if conversation_id:
            conversation = db.get(Conversation, conversation_id)
            if conversation and conversation.tenant_id == tenant_id:
                conversation.status = 'aguardando'
                tags = set(conversation.tags or [])
                tags.add('fila_humana')
                conversation.tags = sorted(tags)
                db.add(conversation)
        return {'action': action_type, 'conversation_id': conversation_id}

    if action_type == 'agendar_job':
        next_run_minutes = int(params.get('in_minutes', 5))
        from app.models import Job

        job = Job(
            tenant_id=tenant_id,
            job_type=params.get('job_type', 'follow_up'),
            status='pending',
            payload={'trigger_payload': trigger_payload, 'action_params': params},
            scheduled_for=datetime.now(UTC) + timedelta(minutes=next_run_minutes),
            max_attempts=int(params.get('max_attempts', 3)),
        )
        db.add(job)
        db.flush()
        return {'action': action_type, 'job_id': str(job.id)}

    return {'action': action_type, 'ignored': True}



def execute_automation_run(db: Session, run_id: UUID) -> None:
    run = db.get(AutomationRun, run_id)
    if not run:
        return

    automation = db.get(Automation, run.automation_id)
    if not automation:
        run.status = RunStatus.FAILED.value
        run.error_message = 'Automation nao encontrada'
        db.add(run)
        db.commit()
        return

    run.status = RunStatus.RUNNING.value
    run.started_at = datetime.now(UTC)
    db.add(run)
    db.commit()

    try:
        results: list[dict] = []
        for action in automation.actions or []:
            results.append(
                _execute_action(
                    db,
                    tenant_id=automation.tenant_id,
                    action=action,
                    trigger_payload=run.trigger_payload or {},
                )
            )

        run.status = RunStatus.SUCCESS.value
        run.result_payload = {'actions': results}
        run.finished_at = datetime.now(UTC)
        db.add(run)
        db.commit()
    except Exception as exc:
        logger.exception('automation.run_failed', run_id=str(run.id), error=str(exc))
        run.status = RunStatus.FAILED.value
        run.error_message = str(exc)
        run.retries += 1
        run.finished_at = datetime.now(UTC)
        db.add(run)
        db.commit()



def run_time_triggers(db: Session) -> int:
    now = datetime.now(UTC)
    automations = db.execute(
        select(Automation).where(
            Automation.trigger_type == 'time',
            Automation.is_active.is_(True),
        )
    ).scalars().all()

    created = 0
    for automation in automations:
        window_minutes = int((automation.conditions or {}).get('window_minutes', 60))
        last_run = db.scalar(
            select(AutomationRun)
            .where(AutomationRun.automation_id == automation.id)
            .order_by(AutomationRun.created_at.desc())
            .limit(1)
        )
        if last_run and (now - last_run.created_at).total_seconds() < (window_minutes * 60):
            continue

        run = AutomationRun(
            tenant_id=automation.tenant_id,
            automation_id=automation.id,
            status=RunStatus.PENDING.value,
            trigger_payload={'source': 'scheduler', 'executed_at': now.isoformat()},
        )
        db.add(run)
        db.flush()
        created += 1

        from app.tasks.jobs import execute_automation_run_task

        execute_automation_run_task.delay(str(run.id))

    db.commit()
    return created



def pending_jobs_for_dispatch(db: Session):
    now = datetime.now(UTC)
    return db.execute(
        select(OutboxMessage).where(
            OutboxMessage.status.in_([OutboxStatus.PENDING.value, OutboxStatus.FAILED.value]),
            or_(OutboxMessage.next_retry_at.is_(None), OutboxMessage.next_retry_at <= now),
        )
    ).scalars().all()

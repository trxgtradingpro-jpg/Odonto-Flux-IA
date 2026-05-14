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

SCHEDULER_ONLY_CONDITIONS = {'window_minutes'}

ACTION_LABELS = {
    'send_message': 'Enviar mensagem',
    'add_tag': 'Adicionar tag',
    'fila_humana': 'Mover para fila humana',
    'alter_status_conversa': 'Alterar status da conversa',
    'agendar_job': 'Agendar próximo passo',
}


def _runtime_conditions(conditions: dict | None) -> dict:
    return {
        key: value
        for key, value in (conditions or {}).items()
        if key not in SCHEDULER_ONLY_CONDITIONS
    }


def _evaluate_condition(key: str, expected_value, payload: dict) -> dict:
    current = payload.get(key)
    operator = 'eq'
    value = expected_value

    if isinstance(expected_value, dict) and 'operator' in expected_value:
        operator = str(expected_value.get('operator') or 'eq')
        value = expected_value.get('value')
    elif isinstance(expected_value, list):
        operator = 'in'

    matched = True
    if operator == 'eq':
        matched = current == value
    elif operator == 'neq':
        matched = current != value
    elif operator == 'in':
        options = value if isinstance(value, list) else [value]
        matched = current in options
    elif operator == 'contains':
        current_text = str(current or '').lower()
        value_text = str(value or '').lower()
        matched = value_text in current_text
    else:
        matched = False

    return {
        'field': key,
        'operator': operator,
        'expected': value,
        'actual': current,
        'matched': matched,
    }


def evaluate_conditions(conditions: dict | None, payload: dict) -> list[dict]:
    return [
        _evaluate_condition(key, expected_value, payload)
        for key, expected_value in _runtime_conditions(conditions).items()
    ]


def _conditions_match(conditions: dict, payload: dict) -> bool:
    return all(item['matched'] for item in evaluate_conditions(conditions, payload))


def _safe_int(value, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _simulate_action(action: dict, trigger_payload: dict) -> dict:
    if not isinstance(action, dict):
        return {
            'action': 'unknown',
            'label': 'Acao desconhecida',
            'will_execute': False,
            'ignored': True,
            'reason': 'acao_invalida',
        }

    action_type = action.get('type')
    params = action.get('params', {}) or {}
    label = ACTION_LABELS.get(action_type, str(action_type or 'Ação desconhecida'))

    if action_type == 'send_message':
        destination = params.get('to') or trigger_payload.get('phone')
        normalized_to = normalize_phone(destination)
        body = params.get('body') or trigger_payload.get('default_message', '')
        message_type = params.get('message_type', 'text')
        if not normalized_to:
            return {
                'action': action_type,
                'label': label,
                'will_execute': False,
                'ignored': True,
                'reason': 'destino_ausente',
                'human_reason': 'Sem telefone no payload ou destino fixo.',
            }
        if not (body or '').strip():
            return {
                'action': action_type,
                'label': label,
                'will_execute': False,
                'ignored': True,
                'reason': 'mensagem_vazia',
                'human_reason': 'A mensagem está vazia.',
            }
        return {
            'action': action_type,
            'label': label,
            'will_execute': True,
            'ignored': False,
            'preview': {
                'to': normalized_to,
                'body': body,
                'message_type': message_type,
                'conversation_id': trigger_payload.get('conversation_id') or params.get('conversation_id'),
            },
        }

    if action_type == 'add_tag':
        patient_id = params.get('patient_id') or trigger_payload.get('patient_id')
        tag = params.get('tag')
        return {
            'action': action_type,
            'label': label,
            'will_execute': bool(patient_id and tag),
            'ignored': not bool(patient_id and tag),
            'reason': None if patient_id and tag else 'paciente_ou_tag_ausente',
            'preview': {'patient_id': patient_id, 'tag': tag},
        }

    if action_type == 'alter_status_conversa':
        conversation_id = params.get('conversation_id') or trigger_payload.get('conversation_id')
        status = params.get('status', 'finalizada')
        return {
            'action': action_type,
            'label': label,
            'will_execute': bool(conversation_id),
            'ignored': not bool(conversation_id),
            'reason': None if conversation_id else 'conversa_ausente',
            'preview': {'conversation_id': conversation_id, 'status': status},
        }

    if action_type == 'fila_humana':
        conversation_id = params.get('conversation_id') or trigger_payload.get('conversation_id')
        return {
            'action': action_type,
            'label': label,
            'will_execute': bool(conversation_id),
            'ignored': not bool(conversation_id),
            'reason': None if conversation_id else 'conversa_ausente',
            'preview': {'conversation_id': conversation_id, 'status': 'aguardando', 'tag': 'fila_humana'},
        }

    if action_type == 'agendar_job':
        next_run_minutes = _safe_int(params.get('in_minutes'), 5)
        scheduled_for = datetime.now(UTC) + timedelta(minutes=next_run_minutes)
        return {
            'action': action_type,
            'label': label,
            'will_execute': True,
            'ignored': False,
            'preview': {
                'job_type': params.get('job_type', 'follow_up'),
                'scheduled_for': scheduled_for.isoformat(),
                'max_attempts': _safe_int(params.get('max_attempts'), 3),
            },
        }

    return {
        'action': action_type,
        'label': label,
        'will_execute': False,
        'ignored': True,
        'reason': 'acao_nao_suportada',
    }


def simulate_automation_definition(*, automation: dict, trigger_payload: dict) -> dict:
    conditions = automation.get('conditions') or {}
    actions = automation.get('actions') or []
    condition_evaluations = evaluate_conditions(conditions, trigger_payload or {})
    conditions_match = all(item['matched'] for item in condition_evaluations)
    is_active = bool(automation.get('is_active', True))
    will_run = is_active and conditions_match

    if not is_active:
        reason = 'automation_paused'
        summary = 'Não vai disparar porque a automação está pausada.'
    elif not conditions_match:
        reason = 'conditions_not_matched'
        summary = 'Não vai disparar porque uma ou mais condições não bateram.'
    else:
        reason = 'conditions_matched'
        summary = 'Vai disparar: o payload atende às condições configuradas.'

    simulated_actions = [_simulate_action(action, trigger_payload or {}) for action in actions]
    message_preview = None
    for action_result in simulated_actions:
        preview = action_result.get('preview') or {}
        if action_result.get('action') == 'send_message' and preview.get('body'):
            message_preview = preview.get('body')
            break

    return {
        'will_run': will_run,
        'reason': reason,
        'summary': summary,
        'conditions_match': conditions_match,
        'condition_evaluations': condition_evaluations,
        'actions': simulated_actions,
        'message_preview': message_preview,
        'trigger_payload': trigger_payload or {},
    }


def enqueue_manual_automation_run(
    db: Session,
    *,
    automation: Automation,
    trigger_payload: dict,
) -> tuple[AutomationRun | None, dict]:
    simulation = simulate_automation_definition(
        automation={
            'name': automation.name,
            'description': automation.description,
            'trigger_type': automation.trigger_type,
            'trigger_key': automation.trigger_key,
            'conditions': automation.conditions or {},
            'actions': automation.actions or [],
            'retry_policy': automation.retry_policy or {},
            'is_active': automation.is_active,
        },
        trigger_payload=trigger_payload or {},
    )
    if not simulation['will_run']:
        return None, simulation

    run = AutomationRun(
        tenant_id=automation.tenant_id,
        automation_id=automation.id,
        status=RunStatus.PENDING.value,
        trigger_payload=trigger_payload or {},
        result_payload={'source': 'manual_execution'},
    )
    db.add(run)
    db.commit()

    from app.tasks.jobs import execute_automation_run_task

    execute_automation_run_task.delay(str(run.id))
    return run, simulation



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

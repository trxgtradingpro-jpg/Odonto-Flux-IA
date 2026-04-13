from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import (
    Automation,
    AutomationRun,
    CampaignAudience,
    CampaignMessage,
    Conversation,
    OutboxMessage,
    Patient,
    PatientTag,
    Unit,
)
from app.services.automation_service import execute_automation_run


def _ensure_unit_and_patient(db_session, tenant_id):
    unit = db_session.scalar(select(Unit).where(Unit.tenant_id == tenant_id))
    if not unit:
        unit = Unit(tenant_id=tenant_id, code='U1', name='Unidade 1', address={})
        db_session.add(unit)
        db_session.flush()

    patient = db_session.scalar(select(Patient).where(Patient.tenant_id == tenant_id))
    if not patient:
        patient = Patient(
            tenant_id=tenant_id,
            unit_id=unit.id,
            full_name='Paciente Fluxo',
            phone='5511998000001',
            normalized_phone='5511998000001',
            status='ativo',
            origin='manual',
            lgpd_consent=True,
            marketing_opt_in=True,
            tags_cache=[],
        )
        db_session.add(patient)
        db_session.flush()

    return unit, patient



def _run_pending_automation(db_session, tenant_id):
    run = db_session.scalar(
        select(AutomationRun)
        .where(AutomationRun.tenant_id == tenant_id, AutomationRun.status == 'pending')
        .order_by(AutomationRun.created_at.desc())
    )
    if run:
        execute_automation_run(db_session, run.id)
    return run



def test_flow_consulta_criada_lembrete_e_confirmacao(client, auth_headers, seeded_db, db_session):
    tenant_id = seeded_db['tenant_a'].id
    unit, patient = _ensure_unit_and_patient(db_session, tenant_id)

    db_session.add(
        Automation(
            tenant_id=tenant_id,
            name='Lembrete consulta criada',
            trigger_type='event',
            trigger_key='consulta_criada',
            actions=[{'type': 'send_message', 'params': {'body': 'Lembrete 24h enviado'}}],
            conditions={},
            retry_policy={'max_attempts': 3},
            is_active=True,
        )
    )
    db_session.commit()

    response = client.post(
        '/api/v1/appointments',
        headers=auth_headers['owner_a'],
        json={
            'patient_id': str(patient.id),
            'unit_id': str(unit.id),
            'procedure_type': 'Avaliacao',
            'starts_at': (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 200

    run = _run_pending_automation(db_session, tenant_id)
    assert run is not None

    outbox = db_session.scalar(select(OutboxMessage).where(OutboxMessage.tenant_id == tenant_id))
    assert outbox is not None

    appointment_id = response.json()['id']
    confirm = client.patch(
        f'/api/v1/appointments/{appointment_id}',
        headers=auth_headers['owner_a'],
        json={'confirmation_status': 'confirmada', 'status': 'confirmada'},
    )
    assert confirm.status_code == 200
    assert confirm.json()['confirmation_status'] == 'confirmada'



def test_flow_sem_resposta_segunda_tentativa_fila_humana(client, auth_headers, seeded_db, db_session):
    tenant_id = seeded_db['tenant_a'].id
    _, patient = _ensure_unit_and_patient(db_session, tenant_id)

    conversation = Conversation(
        tenant_id=tenant_id,
        patient_id=patient.id,
        channel='whatsapp',
        status='aberta',
        tags=[],
    )
    db_session.add(conversation)

    db_session.add(
        Automation(
            tenant_id=tenant_id,
            name='Sem confirmacao vai para fila humana',
            trigger_type='event',
            trigger_key='consulta_sem_confirmacao',
            actions=[
                {'type': 'send_message', 'params': {'body': 'Segunda tentativa'}},
                {'type': 'fila_humana', 'params': {}},
            ],
            conditions={'status': 'pendente'},
            retry_policy={'max_attempts': 3},
            is_active=True,
        )
    )
    db_session.commit()

    emit = client.post(
        '/api/v1/automations/emit/consulta_sem_confirmacao',
        headers=auth_headers['owner_a'],
        json={
            'status': 'pendente',
            'conversation_id': str(conversation.id),
            'phone': patient.phone,
        },
    )
    assert emit.status_code == 200

    run = _run_pending_automation(db_session, tenant_id)
    assert run is not None

    refreshed = db_session.get(Conversation, conversation.id)
    assert refreshed.status == 'aguardando'



def test_flow_paciente_faltou_recuperacao(client, auth_headers, seeded_db, db_session):
    tenant_id = seeded_db['tenant_a'].id
    _, patient = _ensure_unit_and_patient(db_session, tenant_id)

    db_session.add(
        Automation(
            tenant_id=tenant_id,
            name='Recuperacao falta',
            trigger_type='event',
            trigger_key='paciente_faltou',
            actions=[
                {'type': 'send_message', 'params': {'body': 'Vamos reagendar?'}},
                {'type': 'add_tag', 'params': {'tag': 'faltou'}},
            ],
            conditions={},
            retry_policy={'max_attempts': 3},
            is_active=True,
        )
    )
    db_session.commit()

    emit = client.post(
        '/api/v1/automations/emit/paciente_faltou',
        headers=auth_headers['owner_a'],
        json={'patient_id': str(patient.id), 'phone': patient.phone},
    )
    assert emit.status_code == 200

    run = _run_pending_automation(db_session, tenant_id)
    assert run is not None

    tag = db_session.scalar(
        select(PatientTag).where(PatientTag.tenant_id == tenant_id, PatientTag.patient_id == patient.id, PatientTag.tag == 'faltou')
    )
    assert tag is not None



def test_flow_orcamento_followup_2dias(client, auth_headers, seeded_db, db_session):
    tenant_id = seeded_db['tenant_a'].id
    _, patient = _ensure_unit_and_patient(db_session, tenant_id)

    db_session.add(
        Automation(
            tenant_id=tenant_id,
            name='Follow-up orcamento 2 dias',
            trigger_type='event',
            trigger_key='orcamento_pendente_2d',
            actions=[{'type': 'send_message', 'params': {'body': 'Retornando sobre seu orcamento'}}],
            conditions={},
            retry_policy={'max_attempts': 3},
            is_active=True,
        )
    )
    db_session.commit()

    emit = client.post(
        '/api/v1/automations/emit/orcamento_pendente_2d',
        headers=auth_headers['owner_a'],
        json={'patient_id': str(patient.id), 'phone': patient.phone},
    )
    assert emit.status_code == 200

    run = _run_pending_automation(db_session, tenant_id)
    assert run is not None

    outbox = db_session.scalar(select(OutboxMessage).where(OutboxMessage.tenant_id == tenant_id))
    assert outbox is not None



def test_flow_paciente_inativo_campanha_reativacao(client, auth_headers, seeded_db, db_session):
    tenant_id = seeded_db['tenant_a'].id
    _, patient = _ensure_unit_and_patient(db_session, tenant_id)
    patient.marketing_opt_in = True
    patient.inactive_since = datetime.now(UTC) - timedelta(days=240)
    db_session.add(patient)
    db_session.commit()

    campaign = client.post(
        '/api/v1/campaigns',
        headers=auth_headers['owner_a'],
        json={'name': 'Reativacao inativos', 'objective': 'Trazer inativos de volta'},
    )
    assert campaign.status_code == 200

    start = client.post(
        f"/api/v1/campaigns/{campaign.json()['id']}/start",
        headers=auth_headers['owner_a'],
    )
    assert start.status_code == 200
    assert start.json()['queued_messages'] >= 1

    audience = db_session.scalar(select(CampaignAudience).where(CampaignAudience.tenant_id == tenant_id))
    message = db_session.scalar(select(CampaignMessage).where(CampaignMessage.tenant_id == tenant_id))
    assert audience is not None
    assert message is not None

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import (
    Appointment,
    Automation,
    AutomationRun,
    CampaignAudience,
    CampaignMessage,
    Conversation,
    Job,
    OutboxMessage,
    Patient,
    PatientTag,
    Professional,
    Unit,
    WebhookInbox,
)
from app.models.enums import OutboxStatus
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


def _create_professional(db_session, *, tenant_id, unit_id, full_name="Dr Profissional"):
    professional = Professional(
        tenant_id=tenant_id,
        unit_id=unit_id,
        full_name=full_name,
        working_days=[0, 1, 2, 3, 4, 5],
        shift_start="08:00",
        shift_end="18:00",
        procedures=["Limpeza odontolÃ³gica", "ReabilitaÃ§Ã£o estÃ©tica"],
        is_active=True,
    )
    db_session.add(professional)
    db_session.flush()
    return professional



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

    # Regression: updates with datetime/UUID fields must be JSON-safe in event/audit metadata.
    reschedule = client.patch(
        f'/api/v1/appointments/{appointment_id}',
        headers=auth_headers['owner_a'],
        json={
            'unit_id': str(unit.id),
            'starts_at': (datetime.now(UTC) + timedelta(days=2)).isoformat(),
            'status': 'agendada',
            'confirmation_status': 'pendente',
        },
    )
    assert reschedule.status_code == 200
    assert reschedule.json()['unit_id'] == str(unit.id)


def test_delete_professional_unlinks_appointments(client, auth_headers, seeded_db, db_session):
    tenant_id = seeded_db['tenant_a'].id
    unit, patient = _ensure_unit_and_patient(db_session, tenant_id)

    professional_response = client.post(
        '/api/v1/professionals',
        headers=auth_headers['owner_a'],
        json={
            'unit_id': str(unit.id),
            'full_name': 'Dr Excluir',
            'working_days': [1, 2, 3, 4, 5],
            'shift_start': '08:00',
            'shift_end': '18:00',
            'procedures': ['Limpeza odontológica'],
        },
    )
    assert professional_response.status_code == 200
    professional_id = professional_response.json()['id']

    appointment_response = client.post(
        '/api/v1/appointments',
        headers=auth_headers['owner_a'],
        json={
            'patient_id': str(patient.id),
            'unit_id': str(unit.id),
            'professional_id': professional_id,
            'procedure_type': 'Limpeza odontológica',
            'starts_at': (datetime.now(UTC) + timedelta(days=3)).isoformat(),
        },
    )
    assert appointment_response.status_code == 200
    appointment_id = appointment_response.json()['id']

    delete_response = client.delete(
        f'/api/v1/professionals/{professional_id}',
        headers=auth_headers['owner_a'],
    )
    assert delete_response.status_code == 204

    appointment = db_session.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.tenant_id == tenant_id,
        )
    )
    assert appointment is not None
    assert appointment.professional_id is None

    professionals_list = client.get('/api/v1/professionals', headers=auth_headers['owner_a'])
    assert professionals_list.status_code == 200
    ids = [item['id'] for item in professionals_list.json()['data']]
    assert professional_id not in ids


def test_create_appointment_blocks_overlapping_professional_slot(client, auth_headers, seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    unit, patient = _ensure_unit_and_patient(db_session, tenant_id)
    professional = _create_professional(
        db_session,
        tenant_id=tenant_id,
        unit_id=unit.id,
        full_name="Dra Slot",
    )
    db_session.commit()

    first_start = datetime.now(UTC) + timedelta(days=2)
    first_end = first_start + timedelta(minutes=60)
    first = client.post(
        "/api/v1/appointments",
        headers=auth_headers["owner_a"],
        json={
            "patient_id": str(patient.id),
            "unit_id": str(unit.id),
            "professional_id": str(professional.id),
            "procedure_type": "Limpeza odontolÃ³gica",
            "starts_at": first_start.isoformat(),
            "ends_at": first_end.isoformat(),
        },
    )
    assert first.status_code == 200

    conflict_start = first_start + timedelta(minutes=30)
    conflict_end = conflict_start + timedelta(minutes=60)
    conflict = client.post(
        "/api/v1/appointments",
        headers=auth_headers["owner_a"],
        json={
            "patient_id": str(patient.id),
            "unit_id": str(unit.id),
            "professional_id": str(professional.id),
            "procedure_type": "ReabilitaÃ§Ã£o estÃ©tica",
            "starts_at": conflict_start.isoformat(),
            "ends_at": conflict_end.isoformat(),
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "PROFESSIONAL_SLOT_CONFLICT"


def test_update_appointment_blocks_overlapping_professional_slot(client, auth_headers, seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    unit, patient = _ensure_unit_and_patient(db_session, tenant_id)
    professional = _create_professional(
        db_session,
        tenant_id=tenant_id,
        unit_id=unit.id,
        full_name="Dr Conflito",
    )
    db_session.commit()

    first_start = datetime.now(UTC) + timedelta(days=5)
    first_end = first_start + timedelta(minutes=60)
    first = client.post(
        "/api/v1/appointments",
        headers=auth_headers["owner_a"],
        json={
            "patient_id": str(patient.id),
            "unit_id": str(unit.id),
            "professional_id": str(professional.id),
            "procedure_type": "Limpeza odontolÃ³gica",
            "starts_at": first_start.isoformat(),
            "ends_at": first_end.isoformat(),
        },
    )
    assert first.status_code == 200

    second_start = first_start + timedelta(hours=2)
    second = client.post(
        "/api/v1/appointments",
        headers=auth_headers["owner_a"],
        json={
            "patient_id": str(patient.id),
            "unit_id": str(unit.id),
            "procedure_type": "ReabilitaÃ§Ã£o estÃ©tica",
            "starts_at": second_start.isoformat(),
            "ends_at": (second_start + timedelta(minutes=60)).isoformat(),
        },
    )
    assert second.status_code == 200

    second_id = second.json()["id"]
    conflict_update = client.patch(
        f"/api/v1/appointments/{second_id}",
        headers=auth_headers["owner_a"],
        json={
            "professional_id": str(professional.id),
            "starts_at": (first_start + timedelta(minutes=20)).isoformat(),
            "ends_at": (first_start + timedelta(minutes=80)).isoformat(),
        },
    )
    assert conflict_update.status_code == 409
    assert conflict_update.json()["error"]["code"] == "PROFESSIONAL_SLOT_CONFLICT"



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


def test_operations_overview_and_retry_actions(client, auth_headers, seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id

    outbox_failed = OutboxMessage(
        tenant_id=tenant_id,
        channel="whatsapp",
        status=OutboxStatus.FAILED.value,
        payload={"message_type": "text", "body": "teste"},
        retry_count=2,
        max_retries=5,
        last_error="Falha de envio",
    )
    outbox_dead = OutboxMessage(
        tenant_id=tenant_id,
        channel="whatsapp",
        status=OutboxStatus.DEAD_LETTER.value,
        payload={"message_type": "interactive_list", "body": "menu"},
        retry_count=5,
        max_retries=5,
        last_error="Conta invalida",
    )
    failed_job = Job(
        tenant_id=tenant_id,
        job_type="process_whatsapp_outbox",
        status="failed",
        payload={"origin": "test"},
        result={},
        attempts=3,
        max_attempts=3,
        error_message="Erro no worker",
    )
    failed_webhook = WebhookInbox(
        tenant_id=tenant_id,
        provider="infobip_whatsapp",
        event_id="evt-test-1",
        payload={"kind": "message"},
        processed=False,
        error_message="Payload invalido",
    )
    db_session.add_all([outbox_failed, outbox_dead, failed_job, failed_webhook])
    db_session.commit()

    overview = client.get("/api/v1/operations/overview", headers=auth_headers["owner_a"])
    assert overview.status_code == 200
    overview_data = overview.json()
    assert overview_data["outbox"]["failed"] >= 2
    assert overview_data["outbox"]["dead_letter"] >= 1
    assert overview_data["jobs"]["failed_last_24h"] >= 1
    assert overview_data["webhooks"]["failed"] >= 1

    failures = client.get("/api/v1/operations/failures", headers=auth_headers["owner_a"])
    assert failures.status_code == 200
    assert failures.json()["meta"]["total"] >= 4

    retry_outbox = client.post(
        f"/api/v1/operations/outbox/{outbox_dead.id}/retry",
        headers=auth_headers["owner_a"],
    )
    assert retry_outbox.status_code == 200
    assert retry_outbox.json()["status"] == OutboxStatus.PENDING.value

    retry_job = client.post(
        f"/api/v1/operations/jobs/{failed_job.id}/retry",
        headers=auth_headers["owner_a"],
    )
    assert retry_job.status_code == 200
    assert retry_job.json()["status"] == "pending"



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

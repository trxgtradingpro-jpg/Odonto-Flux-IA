from uuid import UUID

from sqlalchemy import select

from app.models import (
    Automation,
    AutomationRun,
    Conversation,
    Job,
    Message,
    OutboxMessage,
    Patient,
    PatientTag,
    ProspectAccount,
    Unit,
)
from app.services.automation_service import execute_automation_run, run_time_triggers
from app.services.demo_whatsapp_simulation_service import process_demo_whatsapp_reply_simulation
from app.services.whatsapp_service import process_outbox_batch


def _ensure_unit_patient_conversation(db_session, tenant_id):
    unit = db_session.scalar(select(Unit).where(Unit.tenant_id == tenant_id))
    if not unit:
        unit = Unit(
            tenant_id=tenant_id,
            code="U1",
            name="Unidade Principal",
            address={},
            is_active=True,
        )
        db_session.add(unit)
        db_session.flush()

    patient = db_session.scalar(select(Patient).where(Patient.tenant_id == tenant_id))
    if not patient:
        patient = Patient(
            tenant_id=tenant_id,
            unit_id=unit.id,
            full_name="Paciente Automacao",
            phone="5511998000001",
            normalized_phone="5511998000001",
            status="ativo",
            origin="manual",
            lgpd_consent=True,
            marketing_opt_in=True,
            tags_cache=[],
        )
        db_session.add(patient)
        db_session.flush()

    conversation = db_session.scalar(
        select(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.patient_id == patient.id,
            Conversation.channel == "whatsapp",
        )
    )
    if not conversation:
        conversation = Conversation(
            tenant_id=tenant_id,
            unit_id=unit.id,
            patient_id=patient.id,
            channel="whatsapp",
            status="aberta",
            tags=[],
        )
        db_session.add(conversation)
        db_session.flush()

    db_session.commit()
    return unit, patient, conversation


def _mark_tenant_as_demo(db_session, tenant_id):
    existing = db_session.scalar(
        select(ProspectAccount).where(ProspectAccount.demo_tenant_id == tenant_id)
    )
    if existing:
        return existing

    prospect = ProspectAccount(
        clinic_name="Clinica Demo Automacoes",
        whatsapp_phone="+55 11 98888-7777",
        test_phone_number="(11) 98888-7777",
        demo_tenant_id=tenant_id,
        demo_status="ativo",
    )
    db_session.add(prospect)
    db_session.commit()
    return prospect


def _execute_run_if_needed(db_session, run_id):
    run = db_session.get(AutomationRun, run_id)
    if run and run.status != "success":
        execute_automation_run(db_session, run_id)
        run = db_session.get(AutomationRun, run_id)
    return run


def test_automation_simulation_and_manual_execute_cover_supported_actions(
    client,
    auth_headers,
    seeded_db,
    db_session,
):
    tenant_id = seeded_db["tenant_a"].id
    _, patient, conversation = _ensure_unit_patient_conversation(db_session, tenant_id)

    automation_payload = {
        "name": "Execucao manual completa",
        "description": "Cobre todas as acoes suportadas",
        "trigger_type": "event",
        "trigger_key": "mensagem_recebida",
        "conditions": {"status": "pendente"},
        "actions": [
            {"type": "send_message", "params": {"body": "Mensagem automatica de follow-up"}},
            {"type": "add_tag", "params": {"tag": "followup_automation"}},
            {"type": "alter_status_conversa", "params": {"status": "finalizada"}},
            {"type": "fila_humana", "params": {}},
            {"type": "agendar_job", "params": {"job_type": "follow_up", "in_minutes": 15, "max_attempts": 2}},
        ],
        "retry_policy": {"max_attempts": 3},
        "is_active": True,
    }
    trigger_payload = {
        "status": "pendente",
        "patient_id": str(patient.id),
        "conversation_id": str(conversation.id),
        "phone": patient.phone,
    }

    created = client.post(
        "/api/v1/automations",
        headers=auth_headers["owner_a"],
        json=automation_payload,
    )
    assert created.status_code == 200
    automation_id = created.json()["id"]

    draft_simulation = client.post(
        "/api/v1/automations/simulate-config",
        headers=auth_headers["owner_a"],
        json={"automation": automation_payload, "trigger_payload": trigger_payload},
    )
    assert draft_simulation.status_code == 200
    draft_payload = draft_simulation.json()
    assert draft_payload["will_run"] is True
    assert draft_payload["message_preview"] == "Mensagem automatica de follow-up"
    assert [item["action"] for item in draft_payload["actions"]] == [
        "send_message",
        "add_tag",
        "alter_status_conversa",
        "fila_humana",
        "agendar_job",
    ]
    assert all(item["will_execute"] for item in draft_payload["actions"])

    saved_simulation = client.post(
        f"/api/v1/automations/{automation_id}/simulate",
        headers=auth_headers["owner_a"],
        json={"trigger_payload": trigger_payload},
    )
    assert saved_simulation.status_code == 200
    assert saved_simulation.json()["will_run"] is True

    manual_execute = client.post(
        f"/api/v1/automations/{automation_id}/execute",
        headers=auth_headers["owner_a"],
        json={"confirmation": "EXECUTAR", "trigger_payload": trigger_payload},
    )
    assert manual_execute.status_code == 200
    execute_payload = manual_execute.json()
    assert execute_payload["run_created"] is True
    assert execute_payload["simulation"]["will_run"] is True

    run_id = UUID(execute_payload["run_id"])
    run = _execute_run_if_needed(db_session, run_id)
    assert run is not None
    assert run.status == "success"
    assert len((run.result_payload or {}).get("actions", [])) == 5

    outbox = db_session.scalar(
        select(OutboxMessage)
        .where(OutboxMessage.tenant_id == tenant_id)
        .order_by(OutboxMessage.created_at.desc())
    )
    assert outbox is not None
    assert outbox.status == "pending"
    assert (outbox.payload or {}).get("body") == "Mensagem automatica de follow-up"
    assert ((outbox.payload or {}).get("metadata") or {}).get("source") == "automation"

    tag = db_session.scalar(
        select(PatientTag).where(
            PatientTag.tenant_id == tenant_id,
            PatientTag.patient_id == patient.id,
            PatientTag.tag == "followup_automation",
        )
    )
    assert tag is not None

    refreshed_patient = db_session.get(Patient, patient.id)
    assert "followup_automation" in (refreshed_patient.tags_cache or [])

    refreshed_conversation = db_session.get(Conversation, conversation.id)
    assert refreshed_conversation.status == "aguardando"
    assert "fila_humana" in (refreshed_conversation.tags or [])

    scheduled_job = db_session.scalar(
        select(Job)
        .where(Job.tenant_id == tenant_id, Job.job_type == "follow_up")
        .order_by(Job.created_at.desc())
    )
    assert scheduled_job is not None
    assert scheduled_job.status == "pending"
    assert scheduled_job.max_attempts == 2
    assert (scheduled_job.payload or {}).get("trigger_payload", {}).get("phone") == patient.phone


def test_automation_event_and_time_triggers_only_fire_when_expected(
    client,
    auth_headers,
    seeded_db,
    db_session,
):
    tenant_id = seeded_db["tenant_a"].id
    _, patient, conversation = _ensure_unit_patient_conversation(db_session, tenant_id)

    event_automation = Automation(
        tenant_id=tenant_id,
        name="Consulta sem confirmacao",
        trigger_type="event",
        trigger_key="consulta_sem_confirmacao",
        conditions={"status": "pendente"},
        actions=[{"type": "send_message", "params": {"body": "Posso te lembrar desse horario?"}}],
        retry_policy={"max_attempts": 3},
        is_active=True,
    )
    time_automation = Automation(
        tenant_id=tenant_id,
        name="Checklist recorrente",
        trigger_type="time",
        trigger_key="scheduler_tick",
        conditions={"window_minutes": 60},
        actions=[{"type": "agendar_job", "params": {"job_type": "checklist_diario", "in_minutes": 5}}],
        retry_policy={"max_attempts": 3},
        is_active=True,
    )
    db_session.add_all([event_automation, time_automation])
    db_session.commit()

    unmatched_event = client.post(
        "/api/v1/automations/emit/consulta_sem_confirmacao",
        headers=auth_headers["owner_a"],
        json={
            "status": "confirmada",
            "conversation_id": str(conversation.id),
            "phone": patient.phone,
        },
    )
    assert unmatched_event.status_code == 200
    assert unmatched_event.json()["runs_created"] == 0

    matched_event = client.post(
        "/api/v1/automations/emit/consulta_sem_confirmacao",
        headers=auth_headers["owner_a"],
        json={
            "status": "pendente",
            "conversation_id": str(conversation.id),
            "phone": patient.phone,
        },
    )
    assert matched_event.status_code == 200
    assert matched_event.json()["runs_created"] == 1

    event_run = db_session.scalar(
        select(AutomationRun)
        .where(AutomationRun.automation_id == event_automation.id)
        .order_by(AutomationRun.created_at.desc())
    )
    assert event_run is not None
    event_run = _execute_run_if_needed(db_session, event_run.id)
    assert event_run is not None
    assert event_run.status == "success"

    reminder_outbox = db_session.scalar(
        select(OutboxMessage)
        .where(OutboxMessage.tenant_id == tenant_id)
        .order_by(OutboxMessage.created_at.desc())
    )
    assert reminder_outbox is not None
    assert (reminder_outbox.payload or {}).get("body") == "Posso te lembrar desse horario?"

    first_batch = run_time_triggers(db_session)
    second_batch = run_time_triggers(db_session)
    assert first_batch == 1
    assert second_batch == 0

    scheduler_run = db_session.scalar(
        select(AutomationRun)
        .where(AutomationRun.automation_id == time_automation.id)
        .order_by(AutomationRun.created_at.desc())
    )
    assert scheduler_run is not None
    scheduler_run = _execute_run_if_needed(db_session, scheduler_run.id)
    assert scheduler_run is not None
    assert scheduler_run.status == "success"

    scheduled_job = db_session.scalar(
        select(Job)
        .where(Job.tenant_id == tenant_id, Job.job_type == "checklist_diario")
        .order_by(Job.created_at.desc())
    )
    assert scheduled_job is not None
    assert scheduled_job.status == "pending"


def test_demo_automation_dispatch_uses_internal_whatsapp_and_simulates_patient_reply(
    client,
    auth_headers,
    seeded_db,
    db_session,
    monkeypatch,
):
    tenant_id = seeded_db["tenant_a"].id
    _mark_tenant_as_demo(db_session, tenant_id)
    _, patient, conversation = _ensure_unit_patient_conversation(db_session, tenant_id)

    from app.tasks import jobs

    scheduled_demo_replies: list[tuple[list[str], int | None]] = []
    scheduled_ai_followups: list[tuple[list[str], int | None]] = []

    monkeypatch.setattr(
        jobs.process_demo_whatsapp_reply_simulation_task,
        "apply_async",
        lambda *, args, countdown=None: scheduled_demo_replies.append((args, countdown)),
    )
    monkeypatch.setattr(
        jobs.process_ai_autoresponder_inbound_task,
        "apply_async",
        lambda *, args, countdown=None: scheduled_ai_followups.append((args, countdown)),
    )

    automation = Automation(
        tenant_id=tenant_id,
        name="Teste whatsapp interno demo",
        trigger_type="event",
        trigger_key="mensagem_recebida",
        conditions={},
        actions=[{"type": "send_message", "params": {"body": "Qual horario fica melhor para voce?"}}],
        retry_policy={"max_attempts": 3},
        is_active=True,
    )
    db_session.add(automation)
    db_session.commit()

    emitted = client.post(
        "/api/v1/automations/emit/mensagem_recebida",
        headers=auth_headers["owner_a"],
        json={
            "conversation_id": str(conversation.id),
            "patient_id": str(patient.id),
            "phone": patient.phone,
            "message": "Oi, quero marcar uma consulta.",
        },
    )
    assert emitted.status_code == 200
    assert emitted.json()["runs_created"] == 1

    run = db_session.scalar(
        select(AutomationRun)
        .where(AutomationRun.automation_id == automation.id)
        .order_by(AutomationRun.created_at.desc())
    )
    assert run is not None
    run = _execute_run_if_needed(db_session, run.id)
    assert run is not None
    assert run.status == "success"

    dispatch_result = process_outbox_batch(db_session, batch_size=20)
    assert dispatch_result["sent"] == 1

    outbox = db_session.scalar(
        select(OutboxMessage)
        .where(OutboxMessage.tenant_id == tenant_id)
        .order_by(OutboxMessage.created_at.desc())
    )
    assert outbox is not None
    assert outbox.status == "sent"

    outbound_message = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "automation",
        )
        .order_by(Message.created_at.desc())
    )
    assert outbound_message is not None
    assert outbound_message.status == "sent"
    assert (outbound_message.payload or {}).get("virtual_dispatch") is True
    assert ((outbound_message.payload or {}).get("provider_response") or {}).get("provider") == "demo_virtual"

    assert len(scheduled_demo_replies) == 1
    scheduled_args, scheduled_countdown = scheduled_demo_replies[0]
    assert scheduled_args[0] == str(tenant_id)
    assert scheduled_args[1] == str(conversation.id)
    assert scheduled_args[2] == str(outbound_message.id)
    assert scheduled_countdown == 3

    reply_result = process_demo_whatsapp_reply_simulation(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        outbound_message_id=outbound_message.id,
    )
    assert reply_result["status"] == "completed"

    inbound_reply = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "inbound",
            Message.sender_type == "patient",
        )
        .order_by(Message.created_at.desc())
    )
    assert inbound_reply is not None
    assert (inbound_reply.payload or {}).get("simulated_patient") is True
    assert "14h" in inbound_reply.body
    assert len(scheduled_ai_followups) == 1

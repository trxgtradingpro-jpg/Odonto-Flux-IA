from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, func, select, text

from app.db.base import Base
from app.models import (
    AIAutoresponderDecision,
    Appointment,
    AuditLog,
    Conversation,
    Job,
    Lead,
    Message,
    MessageEvent,
    OutboxMessage,
    Patient,
    Professional,
    Setting,
    Unit,
    WhatsAppAccount,
)
from app.models.enums import MessageDirection
from app.services.ai_autoresponder_service import process_inbound_message


@pytest.fixture(scope="session")
def test_engine():
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url or "odontoflux_test_" not in database_url:
        pytest.skip("Defina TEST_DATABASE_URL apontando para um banco temporario odontoflux_test_*.")
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.commit()
    except Exception as exc:
        pytest.skip(f"Database indisponivel para testes estruturados: {exc}")
    Base.metadata.create_all(bind=engine)
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


def _params(**overrides):
    payload = {
        "unit_id": None,
        "unit_name": None,
        "service_id": None,
        "procedure_type": None,
        "professional_id": None,
        "date": None,
        "time_after": None,
        "time_before": None,
        "period": None,
        "slot_id": None,
        "appointment_id": None,
        "hold_minutes": 10,
        "limit": 3,
    }
    payload.update(overrides)
    return payload


def _extracted(**overrides):
    payload = {
        "patient_name": None,
        "responsible_name": None,
        "preferred_name": None,
        "phone": None,
        "email": None,
        "cpf": None,
        "birth_date": None,
        "unit_requested_text": None,
        "unit_id": None,
        "service_requested_text": None,
        "service_id": None,
        "procedure_type": None,
        "professional_requested_text": None,
        "professional_id": None,
        "preferred_date": None,
        "preferred_period": None,
        "preferred_time_text": None,
        "selected_slot_id": None,
        "selected_datetime": None,
        "appointment_id": None,
        "pain": {
            "has_pain": None,
            "duration_text": None,
            "has_swelling": None,
            "has_fever": None,
            "urgency_level": "desconhecida",
        },
    }
    pain = overrides.pop("pain", None)
    payload.update(overrides)
    if isinstance(pain, dict):
        payload["pain"].update(pain)
    return payload


def _appointment_intent(**overrides):
    payload = {
        "wants_booking": False,
        "wants_reschedule": False,
        "wants_cancel": False,
        "procedure_type": None,
        "unit_id": None,
        "professional_id": None,
        "starts_at": None,
        "ends_at": None,
        "canceled_reason": None,
    }
    payload.update(overrides)
    return payload


def _decision_payload(**overrides):
    payload = {
        "schema_version": "1.0",
        "intent": "saudacao",
        "confidence": 0.82,
        "detected_language": "pt-BR",
        "message_summary": "Mensagem recebida.",
        "extracted_data": _extracted(),
        "field_updates": [],
        "appointment_intent": _appointment_intent(),
        "system_action": {"required": False, "action": "none", "params": _params()},
        "reply_control": {
            "should_reply_now": True,
            "reply_after_system_action": False,
            "next_expected_field": None,
            "missing_fields": [],
            "suggested_next_question": None,
        },
        "handoff": {"required": False, "reason": None, "tag": None},
        "guardrails": {"triggered": False, "reason": None, "forbidden_topics_detected": []},
    }
    payload.update(overrides)
    return payload


def _reply_payload(message: str, *, final_decision: str = "reply", reason: str = "test_reply"):
    return {
        "schema_version": "1.0",
        "message": message,
        "message_type": "text",
        "interactive_payload": None,
        "confidence": 0.91,
        "final_decision": final_decision,
        "decision_reason": reason,
    }


def _upsert_setting(db_session, *, tenant_id, key: str, value: dict):
    item = db_session.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == key))
    if item:
        item.value = value
    else:
        item = Setting(tenant_id=tenant_id, key=key, value=value, is_secret=False)
    db_session.add(item)
    db_session.commit()
    return item


def _base_structured_config():
    return {
        "enabled": True,
        "structured_flow_enabled": True,
        "channels": {"whatsapp": True},
        "business_hours": {
            "timezone": "America/Sao_Paulo",
            "weekdays": [0, 1, 2, 3, 4, 5, 6],
            "start": "00:00",
            "end": "23:59",
        },
        "outside_business_hours_mode": "allow",
        "max_consecutive_auto_replies": 5,
        "confidence_threshold": 0.65,
        "human_queue_tag": "fila_humana_ia",
        "interactive_booking_options_enabled": True,
        "tone": "simpatico, objetivo e focado em agendamento",
    }


def _prepare_tenant(db_session, *, tenant_id):
    _upsert_setting(db_session, tenant_id=tenant_id, key="ai_autoresponder.global", value=_base_structured_config())
    _upsert_setting(
        db_session,
        tenant_id=tenant_id,
        key="clinic.profile",
        value={
            "clinic_name": "Clinica OdontoFlux",
            "city": "Sao Paulo",
            "state": "SP",
            "accepted_insurance": ["OdontoPlus"],
            "payment_methods": ["Pix", "Cartao"],
            "about": "Clinica odontologica com foco em avaliacao e tratamentos esteticos.",
        },
    )
    _upsert_setting(db_session, tenant_id=tenant_id, key="clinic.timezone", value={"value": "America/Sao_Paulo"})
    _upsert_setting(
        db_session,
        tenant_id=tenant_id,
        key="service_catalog.global",
        value={
            "items": [
                {
                    "id": "svc_clareamento",
                    "name": "Clareamento dental",
                    "description": "Tratamento estetico para clarear os dentes.",
                    "duration_minutes": 30,
                    "price_note": "",
                    "is_active": True,
                },
                {
                    "id": "svc_avaliacao",
                    "name": "Avaliacao odontologica",
                    "description": "Consulta inicial para avaliar o caso.",
                    "duration_minutes": 30,
                    "price_note": "",
                    "is_active": True,
                },
            ]
        },
    )
    account = db_session.scalar(select(WhatsAppAccount).where(WhatsAppAccount.tenant_id == tenant_id))
    if not account:
        account = WhatsAppAccount(
            tenant_id=tenant_id,
            provider_name="meta_cloud",
            phone_number_id="1101713436353674",
            business_account_id="936994182588219",
            access_token_encrypted="EAAa" + ("x" * 60),
            verify_token="verify-token-dev",
            is_active=True,
        )
    else:
        account.provider_name = "meta_cloud"
        account.phone_number_id = "1101713436353674"
        account.business_account_id = "936994182588219"
        account.access_token_encrypted = "EAAa" + ("x" * 60)
        account.is_active = True
    db_session.add(account)
    db_session.commit()


def _digits_suffix() -> str:
    return str(uuid4().int % 100_000_000).zfill(8)


def _ensure_schedule(db_session, *, tenant_id, target_date, shift_start="18:00", shift_end="20:00"):
    unit = Unit(
        tenant_id=tenant_id,
        code=f"CTR{uuid4().hex[:4]}",
        name="Unidade Centro",
        phone="1133330000",
        email="centro@clinica.test",
        address={"line": "Rua Centro, 100"},
        working_hours={},
        is_active=True,
    )
    db_session.add(unit)
    db_session.flush()
    professional = Professional(
        tenant_id=tenant_id,
        unit_id=unit.id,
        full_name="Dra. Ana Centro",
        working_days=[(target_date.weekday() + 1) % 7],
        shift_start=shift_start,
        shift_end=shift_end,
        procedures=["Avaliacao odontologica", "Clareamento dental"],
        is_active=True,
    )
    db_session.add(professional)
    db_session.commit()
    return unit, professional


def _lead_conversation_with_inbound(db_session, *, tenant_id, inbound_text: str, unit_id=None):
    suffix = _digits_suffix()
    lead = Lead(
        tenant_id=tenant_id,
        name=f"Lead WhatsApp {suffix}",
        phone=f"551199{suffix}",
        email=None,
        origin="whatsapp",
        interest="",
        notes="nota interna proibida para IA",
    )
    db_session.add(lead)
    db_session.flush()
    conversation = Conversation(
        tenant_id=tenant_id,
        lead_id=lead.id,
        unit_id=unit_id,
        channel="whatsapp",
        status="aberta",
        tags=[],
    )
    db_session.add(conversation)
    db_session.flush()
    inbound = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND.value,
        channel="whatsapp",
        sender_type="patient",
        body=inbound_text,
        message_type="text",
        payload={},
        status="received",
    )
    db_session.add(inbound)
    db_session.commit()
    return lead, conversation, inbound


def _patient_conversation_with_inbound(db_session, *, tenant_id, inbound_text: str):
    suffix = _digits_suffix()
    patient = Patient(
        tenant_id=tenant_id,
        full_name="Maria Existente",
        phone=f"551198{suffix}",
        normalized_phone=f"551198{suffix}",
        email="maria@example.com",
        operational_notes="dado proibido",
        status="ativo",
        origin="whatsapp",
        lgpd_consent=True,
        marketing_opt_in=True,
        tags_cache=["nao_enviar"],
    )
    db_session.add(patient)
    db_session.flush()
    conversation = Conversation(
        tenant_id=tenant_id,
        patient_id=patient.id,
        channel="whatsapp",
        status="aberta",
        tags=[],
    )
    db_session.add(conversation)
    db_session.flush()
    inbound = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND.value,
        channel="whatsapp",
        sender_type="patient",
        body=inbound_text,
        message_type="text",
        payload={},
        status="received",
    )
    db_session.add(inbound)
    db_session.commit()
    return patient, conversation, inbound


def _webchat_placeholder_conversation_with_inbound(db_session, *, tenant_id, inbound_text: str):
    suffix = uuid4().hex[:10]
    patient = Patient(
        tenant_id=tenant_id,
        full_name="Paciente Webchat",
        phone=f"webchat{suffix}",
        normalized_phone=f"webchat{suffix}",
        email=None,
        status="ativo",
        origin="link_flow_webchat",
        lgpd_consent=True,
        marketing_opt_in=False,
        tags_cache=["entry_webchat"],
    )
    db_session.add(patient)
    db_session.flush()
    conversation = Conversation(
        tenant_id=tenant_id,
        patient_id=patient.id,
        channel="webchat",
        status="aberta",
        tags=["entry_webchat"],
    )
    db_session.add(conversation)
    db_session.flush()
    inbound = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND.value,
        channel="webchat",
        sender_type="patient",
        body=inbound_text,
        message_type="text",
        payload={},
        status="received",
    )
    db_session.add(inbound)
    db_session.commit()
    return patient, conversation, inbound


def _enable_elite_config(db_session, *, tenant_id, **overrides):
    config = _base_structured_config()
    config.update(
        {
            "conversation_flow_mode": "structured_elite",
            "structured_flow_enabled": True,
            "pre_send_review_enabled": True,
            "repetition_guard_enabled": True,
            "conversation_memory_enabled": True,
            "auto_save_patient_data_enabled": True,
        }
    )
    config.update(overrides)
    _upsert_setting(db_session, tenant_id=tenant_id, key="ai_autoresponder.global", value=config)


def _install_llm(monkeypatch, *scripted_outputs):
    from app.services import ai_structured_flow
    from app.services import whatsapp_service

    outputs = list(scripted_outputs)
    calls: list[dict] = []

    def _fake_run_llm_task(db, *, tenant_id, conversation_id, task, prompt):
        assert outputs, f"Nenhuma resposta fake configurada para {task}"
        item = outputs.pop(0)
        payload = item(task, prompt) if callable(item) else item
        calls.append({"task": task, "prompt": prompt, "payload": payload})
        output = json.dumps(payload, ensure_ascii=False) if isinstance(payload, dict) else payload
        return {
            "output": output,
            "metadata": {
                "provider": "test",
                "model": "structured-cycle",
                "task": task,
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "total_tokens": 30,
                "cost_usd": 0.0001,
                "latency_ms": 1,
            },
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _fake_run_llm_task)
    monkeypatch.setattr(whatsapp_service, "_dispatch_outbox_item_inline", lambda *args, **kwargs: None)
    return calls


def _system_action_result_from_prompt(prompt: str) -> dict:
    match = re.search(r"SYSTEM_ACTION_RESULT_JSON:\n(.*?)\n\nRetorne somente PatientReplyOutput", prompt, re.S)
    assert match, "Prompt da resposta final deve conter SYSTEM_ACTION_RESULT_JSON"
    return json.loads(match.group(1))


def _process(db_session, *, tenant_id, conversation, inbound):
    return process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )


def _latest_outbound(db_session, *, conversation_id):
    return db_session.scalar(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.direction == MessageDirection.OUTBOUND.value)
        .order_by(Message.created_at.desc())
    )


def _decision(db_session, *, tenant_id, inbound_id):
    return db_session.scalar(
        select(AIAutoresponderDecision).where(
            AIAutoresponderDecision.tenant_id == tenant_id,
            AIAutoresponderDecision.dedupe_key == f"inbound:{inbound_id}",
        )
    )


def _tomorrow_sp():
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date() + timedelta(days=1)


def test_1_lead_asks_simple_procedure(monkeypatch, seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _prepare_tenant(db_session, tenant_id=tenant_id)
    _lead, conversation, inbound = _lead_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Oi, vocês fazem clareamento?",
    )
    calls = _install_llm(
        monkeypatch,
        _decision_payload(
            intent="consultar_servico",
            confidence=0.9,
            message_summary="Paciente perguntou sobre clareamento.",
            extracted_data=_extracted(service_requested_text="clareamento", procedure_type="Clareamento dental"),
            system_action={
                "required": True,
                "action": "query_service",
                "params": _params(procedure_type="clareamento"),
            },
            reply_control={
                "should_reply_now": False,
                "reply_after_system_action": True,
                "next_expected_field": None,
                "missing_fields": [],
                "suggested_next_question": None,
            },
        ),
        _reply_payload(
            "Fazemos sim 😊 O clareamento dental está disponível na clínica. Você quer melhorar a estética do sorriso ou tem alguma data especial chegando?",
            reason="service_answer_next_step",
        ),
    )

    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)

    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    decision = _decision(db_session, tenant_id=tenant_id, inbound_id=inbound.id)
    assert result["status"] == "responded"
    assert calls[0]["task"] == "auto_responder_structured_extract"
    assert db_session.get(Message, inbound.id).created_at <= decision.created_at
    assert decision.metadata_json["decision"]["intent"] == "consultar_servico"
    assert decision.metadata_json["system_action_result"]["service"]["name"] == "Clareamento dental"
    assert "clareamento" in outbound.body.lower()
    assert "r$" not in outbound.body.lower()
    assert "data especial" in outbound.body.lower() or "horário" in outbound.body.lower()
    assert db_session.scalar(select(OutboxMessage).where(OutboxMessage.tenant_id == tenant_id)) is not None
    assert db_session.scalar(select(AuditLog).where(AuditLog.tenant_id == tenant_id)) is not None


def test_2_lead_wants_slot_with_unit_and_period(monkeypatch, seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _prepare_tenant(db_session, tenant_id=tenant_id)
    target_date = _tomorrow_sp()
    _unit, _professional = _ensure_schedule(db_session, tenant_id=tenant_id, target_date=target_date)
    _lead, conversation, inbound = _lead_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Oi, quero marcar amanhã depois das 18h na unidade Centro.",
    )

    def _availability_reply(task, prompt):
        result = _system_action_result_from_prompt(prompt)
        slots = result["slots"]
        labels = [slot["label"] for slot in slots[:2]]
        return _reply_payload(
            f"Perfeito 😊 Encontrei estes horários para amanhã na unidade Centro: {labels[0]} e {labels[1]}. Qual deles fica melhor para você?",
            reason="availability_options_returned",
        )

    calls = _install_llm(
        monkeypatch,
        _decision_payload(
            intent="consultar_horarios",
            confidence=0.92,
            message_summary="Paciente quer marcar amanhã depois das 18h na unidade Centro.",
            extracted_data=_extracted(
                unit_requested_text="Centro",
                procedure_type="Avaliacao odontologica",
                preferred_date=target_date.isoformat(),
                preferred_period="final_do_dia",
                preferred_time_text="depois das 18h",
            ),
            appointment_intent=_appointment_intent(wants_booking=True, procedure_type="Avaliacao odontologica"),
            system_action={
                "required": True,
                "action": "query_availability",
                "params": _params(
                    unit_name="Centro",
                    procedure_type="Avaliacao odontologica",
                    date=target_date.isoformat(),
                    time_after="18:00",
                    period="final_do_dia",
                    limit=3,
                ),
            },
            reply_control={
                "should_reply_now": False,
                "reply_after_system_action": True,
                "next_expected_field": None,
                "missing_fields": [],
                "suggested_next_question": None,
            },
        ),
        _availability_reply,
    )

    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)

    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    decision = _decision(db_session, tenant_id=tenant_id, inbound_id=inbound.id)
    slots = decision.metadata_json["system_action_result"]["slots"]
    assert result["status"] == "responded"
    assert calls[0]["payload"]["extracted_data"]["patient_name"] is None
    assert calls[0]["payload"]["system_action"]["action"] == "query_availability"
    assert calls[0]["payload"]["reply_control"]["should_reply_now"] is False
    assert calls[0]["payload"]["extracted_data"]["preferred_date"] == target_date.isoformat()
    assert len(slots) >= 2
    assert slots[0]["label"] in outbound.body
    assert slots[1]["label"] in outbound.body
    assert "confirmad" not in outbound.body.lower()
    assert db_session.scalar(select(func.count()).select_from(Appointment).where(Appointment.tenant_id == tenant_id)) == 0


def test_3_patient_selects_offered_slot_and_backend_holds_it(monkeypatch, seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _prepare_tenant(db_session, tenant_id=tenant_id)
    target_date = _tomorrow_sp()
    unit, _professional = _ensure_schedule(db_session, tenant_id=tenant_id, target_date=target_date)
    _lead, conversation, _previous_inbound = _lead_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quero marcar amanhã depois das 18h.",
        unit_id=unit.id,
    )
    local_slot = datetime.combine(target_date, datetime.strptime("18:50", "%H:%M").time(), ZoneInfo("America/Sao_Paulo"))
    selected_utc = local_slot.astimezone(UTC)
    db_session.add(
        Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            direction=MessageDirection.OUTBOUND.value,
            channel="whatsapp",
            sender_type="ai",
            body="Tenho 18h10 e 18h50. Qual prefere?",
            message_type="text",
            payload={"offered_slots": [f"slot:{selected_utc.isoformat()}"]},
            status="sent",
        )
    )
    inbound = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND.value,
        channel="whatsapp",
        sender_type="patient",
        body="Pode ser 18h50.",
        message_type="text",
        payload={},
        status="received",
    )
    db_session.add(inbound)
    db_session.commit()

    calls = _install_llm(
        monkeypatch,
        _decision_payload(
            intent="selecionar_horario",
            confidence=0.9,
            message_summary="Paciente escolheu 18h50.",
            extracted_data=_extracted(
                unit_requested_text="Centro",
                procedure_type="Avaliacao odontologica",
                selected_slot_id=f"slot:{selected_utc.isoformat()}",
                selected_datetime=selected_utc.isoformat(),
            ),
            appointment_intent=_appointment_intent(
                wants_booking=True,
                procedure_type="Avaliacao odontologica",
                starts_at=selected_utc.isoformat(),
            ),
            system_action={
                "required": True,
                "action": "validate_and_hold_slot",
                "params": _params(
                    unit_name="Centro",
                    procedure_type="Avaliacao odontologica",
                    slot_id=f"slot:{selected_utc.isoformat()}",
                    hold_minutes=10,
                ),
            },
            reply_control={
                "should_reply_now": False,
                "reply_after_system_action": True,
                "next_expected_field": "patient_name",
                "missing_fields": ["patient_name"],
                "suggested_next_question": None,
            },
        ),
        _reply_payload(
            "Ótimo 😊 Separei o horário de 18h50 para você. Para confirmar certinho, qual é o seu nome completo?",
            reason="slot_validated_waiting_required_data",
        ),
    )

    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)

    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    decision = _decision(db_session, tenant_id=tenant_id, inbound_id=inbound.id)
    hold = db_session.scalar(select(Job).where(Job.tenant_id == tenant_id, Job.job_type == "ai_slot_hold"))
    assert result["status"] == "responded"
    assert calls[0]["payload"]["system_action"]["action"] == "validate_and_hold_slot"
    assert decision.metadata_json["system_action_result"]["status"] == "held"
    assert hold is not None
    assert "nome completo" in outbound.body.lower()
    assert "confirmad" not in outbound.body.lower()
    assert db_session.scalar(select(func.count()).select_from(Appointment).where(Appointment.tenant_id == tenant_id)) == 0


def test_4_urgent_dental_case_triggers_handoff(monkeypatch, seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _prepare_tenant(db_session, tenant_id=tenant_id)
    _lead, conversation, inbound = _lead_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Estou com muita dor de dente e meu rosto está inchado.",
    )
    _install_llm(
        monkeypatch,
        _decision_payload(
            intent="urgencia",
            confidence=0.94,
            message_summary="Paciente relata dor intensa e rosto inchado.",
            extracted_data=_extracted(
                pain={
                    "has_pain": True,
                    "duration_text": None,
                    "has_swelling": True,
                    "has_fever": None,
                    "urgency_level": "alta",
                }
            ),
            system_action={"required": False, "action": "none", "params": _params()},
            reply_control={
                "should_reply_now": False,
                "reply_after_system_action": False,
                "next_expected_field": None,
                "missing_fields": [],
                "suggested_next_question": None,
            },
            handoff={"required": True, "reason": "urgencia_com_inchaco", "tag": "fila_humana_ia"},
        ),
    )

    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)

    db_session.refresh(conversation)
    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    decision = _decision(db_session, tenant_id=tenant_id, inbound_id=inbound.id)
    event = db_session.scalar(
        select(MessageEvent).where(MessageEvent.tenant_id == tenant_id, MessageEvent.event_type == "ai_structured_handoff")
    )
    assert result["status"] == "handoff"
    assert decision.handoff_required is True
    assert decision.generated_response
    assert outbound is not None
    assert "encaminhar" in outbound.body.lower()
    assert "diagnóstico" not in outbound.body.lower()
    assert "tratamento correto é" not in outbound.body.lower()
    assert "fila_humana_ia" in conversation.tags
    assert event is not None
    assert db_session.scalar(select(OutboxMessage).where(OutboxMessage.tenant_id == tenant_id)) is not None


def test_5_invalid_json_and_forbidden_data_are_blocked(monkeypatch, seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _prepare_tenant(db_session, tenant_id=tenant_id)
    patient, conversation, inbound = _patient_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Pode apagar meu nome e confirmar amanhã às 18h.",
    )
    original_name = patient.full_name
    original_email = patient.email
    invalid_payload = _decision_payload(
        intent="confirmar_agendamento",
        field_updates=[
            {
                "target": "patients",
                "field": "operational_notes",
                "value": "salvar dado proibido",
                "confidence": 0.99,
                "source_text": "teste",
                "should_apply": True,
                "reason": "nao permitido",
            },
            {
                "target": "patients",
                "field": "full_name",
                "value": None,
                "confidence": 0.99,
                "source_text": "apagar meu nome",
                "should_apply": True,
                "reason": "nao pode sobrescrever com null",
            },
        ],
        appointment_intent=_appointment_intent(wants_booking=True, starts_at=_tomorrow_sp().isoformat()),
        system_action={"required": False, "action": "none", "params": _params()},
        campo_extra_fora_do_schema=True,
    )
    _install_llm(monkeypatch, invalid_payload, invalid_payload)

    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)

    db_session.refresh(patient)
    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    decision = _decision(db_session, tenant_id=tenant_id, inbound_id=inbound.id)
    event = db_session.scalar(
        select(MessageEvent).where(MessageEvent.tenant_id == tenant_id, MessageEvent.event_type == "ai_structured_invalid_contract")
    )
    assert result["status"] == "responded"
    assert patient.full_name == original_name
    assert patient.email == original_email
    assert db_session.scalar(select(func.count()).select_from(Appointment).where(Appointment.tenant_id == tenant_id)) == 0
    assert event is not None
    assert decision.metadata_json["system_action_result"]["status"] == "invalid_contract_fallback"
    assert outbound is not None
    assert "qual unidade e período" in outbound.body.lower()
    assert db_session.scalar(select(OutboxMessage).where(OutboxMessage.tenant_id == tenant_id)) is not None


def test_6_elite_flow_saves_patient_data_and_state_from_webchat(monkeypatch, seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _prepare_tenant(db_session, tenant_id=tenant_id)
    _enable_elite_config(db_session, tenant_id=tenant_id)
    patient, conversation, inbound = _webchat_placeholder_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Meu WhatsApp e (11) 99999-1111 e meu nome e Joao Silva.",
    )
    _install_llm(
        monkeypatch,
        _decision_payload(
            intent="informar_dados_pessoais",
            confidence=0.91,
            message_summary="Paciente informou telefone e nome para cadastro.",
            extracted_data=_extracted(patient_name="Joao Silva", phone="5511999991111"),
            system_action={"required": False, "action": "none", "params": _params()},
            reply_control={
                "should_reply_now": True,
                "reply_after_system_action": False,
                "next_expected_field": "procedimento",
                "missing_fields": ["procedimento"],
                "suggested_next_question": "Qual procedimento voce quer agendar?",
            },
        ),
        _reply_payload("Obrigado, Joao. Ja salvei seus dados. Qual procedimento voce quer agendar?"),
    )

    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)

    db_session.refresh(patient)
    db_session.refresh(conversation)
    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    assert result["status"] == "responded"
    assert patient.full_name == "Joao Silva"
    assert patient.normalized_phone == "5511999991111"
    assert conversation.ai_summary
    assert conversation.ai_state["booking"]["nome"] == "Joao Silva"
    assert conversation.ai_state["booking"]["telefone"] == "5511999991111"
    assert conversation.ai_state["booking"]["ultima_pergunta_feita"] == "Qual procedimento voce quer agendar?"
    assert conversation.ai_state["booking"]["ultima_resposta_enviada"] == outbound.body
    assert outbound.status == "sent"


def test_7_elite_flow_repairs_repeated_reply_before_dispatch(monkeypatch, seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _prepare_tenant(db_session, tenant_id=tenant_id)
    _enable_elite_config(db_session, tenant_id=tenant_id)
    _patient, conversation, inbound = _patient_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quero continuar o agendamento.",
    )
    repeated_text = "Perfeito, qual e o seu nome completo?"
    db_session.add(
        Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            direction=MessageDirection.OUTBOUND.value,
            channel="whatsapp",
            sender_type="ai",
            body=repeated_text,
            message_type="text",
            payload={},
            status="sent",
        )
    )
    db_session.commit()
    _install_llm(
        monkeypatch,
        _decision_payload(
            intent="agendar_consulta",
            confidence=0.9,
            message_summary="Paciente quer continuar o agendamento.",
            appointment_intent=_appointment_intent(wants_booking=True),
            system_action={"required": False, "action": "none", "params": _params()},
            reply_control={
                "should_reply_now": True,
                "reply_after_system_action": False,
                "next_expected_field": "unidade",
                "missing_fields": ["unidade"],
                "suggested_next_question": "Qual unidade voce prefere?",
            },
        ),
        _reply_payload(repeated_text),
    )

    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)

    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    decision = _decision(db_session, tenant_id=tenant_id, inbound_id=inbound.id)
    review = decision.metadata_json["pre_send_review"]
    assert result["status"] == "responded"
    assert review["parece_repetida"] is True
    assert review["repaired"] is True
    assert outbound.body != repeated_text
    assert "unidade" in outbound.body.lower()


def test_8_elite_review_blocks_final_confirmation_without_saved_appointment(monkeypatch, seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _prepare_tenant(db_session, tenant_id=tenant_id)
    _enable_elite_config(db_session, tenant_id=tenant_id)
    _patient, conversation, inbound = _patient_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Pode confirmar para mim?",
    )
    _install_llm(
        monkeypatch,
        _decision_payload(
            intent="confirmar_agendamento",
            confidence=0.92,
            message_summary="Paciente pediu confirmacao do agendamento.",
            appointment_intent=_appointment_intent(wants_booking=True),
            system_action={"required": False, "action": "none", "params": _params()},
            reply_control={
                "should_reply_now": True,
                "reply_after_system_action": False,
                "next_expected_field": None,
                "missing_fields": [],
                "suggested_next_question": None,
            },
        ),
        _reply_payload("Agendamento confirmado para amanha as 18h. Pode comparecer."),
    )

    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)

    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    assert result["status"] == "responded"
    assert "agendamento confirmado" not in outbound.body.lower()
    assert db_session.scalar(select(func.count()).select_from(Appointment).where(Appointment.tenant_id == tenant_id)) == 0

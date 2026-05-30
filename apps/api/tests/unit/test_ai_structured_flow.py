from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select, text

from app.db.base import Base
from app.models import AIAutoresponderDecision, Conversation, Lead, Message, OutboxMessage, Patient, Professional, Setting, Unit, WhatsAppAccount
from app.services.ai_autoresponder_service import process_inbound_message
from app.services.ai_structured_flow import (
    AiDecisionOutput,
    PatientReplyOutput,
    build_ai_conversation_context,
    build_safe_persistence_plan,
    _looks_like_placeholder_name,
    _repair_patient_reply_after_review,
    validate_ai_decision_output,
    validate_patient_reply_output,
)


@pytest.fixture(scope="session")
def test_engine():
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url or "odontoflux_test_" not in database_url:
        pytest.skip("Defina TEST_DATABASE_URL apontando para um banco temporário odontoflux_test_* para testes de banco.")
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.commit()
    except Exception as exc:
        pytest.skip(f"Database indisponível para testes estruturados: {exc}")
    Base.metadata.create_all(bind=engine)
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


def _decision_payload(**overrides):
    payload = {
        "schema_version": "1.0",
        "intent": "saudacao",
        "confidence": 0.82,
        "detected_language": "pt-BR",
        "message_summary": "Paciente cumprimentou.",
        "extracted_data": {
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
        },
        "field_updates": [],
        "appointment_intent": {
            "wants_booking": False,
            "wants_reschedule": False,
            "wants_cancel": False,
            "procedure_type": None,
            "unit_id": None,
            "professional_id": None,
            "starts_at": None,
            "ends_at": None,
            "canceled_reason": None,
        },
        "system_action": {
            "required": False,
            "action": "none",
            "params": {
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
            },
        },
        "reply_control": {
            "should_reply_now": True,
            "reply_after_system_action": False,
            "next_expected_field": None,
            "missing_fields": [],
            "suggested_next_question": "Olá! Como posso ajudar?",
        },
        "handoff": {"required": False, "reason": None, "tag": None},
        "guardrails": {"triggered": False, "reason": None, "forbidden_topics_detected": []},
    }
    payload.update(overrides)
    return payload


def _upsert_setting(db_session, *, tenant_id, key: str, value: dict):
    item = db_session.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == key))
    if not item:
        item = Setting(tenant_id=tenant_id, key=key, value=value, is_secret=False)
    else:
        item.value = value
    db_session.add(item)
    db_session.commit()
    return item


def _ensure_valid_whatsapp_account(db_session, *, tenant_id):
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
    return account


def _conversation_with_inbound(db_session, *, tenant_id, inbound_text: str):
    suffix = uuid4().hex[:8]
    patient = Patient(
        tenant_id=tenant_id,
        full_name=f"Contato WhatsApp {suffix}",
        phone=f"5511999{suffix}",
        normalized_phone=f"5511999{suffix}",
        operational_notes="NÃO ENVIAR PARA IA",
        status="ativo",
        origin="whatsapp",
        lgpd_consent=True,
        marketing_opt_in=True,
        tags_cache=["vip"],
    )
    lead = Lead(
        tenant_id=tenant_id,
        name=f"Lead {suffix}",
        phone=patient.phone,
        email=None,
        origin="whatsapp",
        interest="",
        notes="nota proibida",
    )
    db_session.add_all([patient, lead])
    db_session.flush()
    conversation = Conversation(
        tenant_id=tenant_id,
        patient_id=patient.id,
        lead_id=lead.id,
        channel="whatsapp",
        status="aberta",
        tags=[],
    )
    db_session.add(conversation)
    db_session.flush()
    inbound = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="inbound",
        channel="whatsapp",
        sender_type="patient",
        body=inbound_text,
        message_type="text",
        payload={},
        status="received",
    )
    db_session.add(inbound)
    db_session.commit()
    return patient, lead, conversation, inbound


def _next_python_weekday(target_weekday: int) -> date:
    today = date.today()
    for offset in range(1, 15):
        candidate = today + timedelta(days=offset)
        if candidate.weekday() == target_weekday:
            return candidate
    return today + timedelta(days=1)


def _structured_config():
    return {
        "enabled": True,
        "channels": {"whatsapp": True},
        "structured_flow_enabled": True,
        "business_hours": {
            "timezone": "America/Sao_Paulo",
            "weekdays": [1, 2, 3, 4, 5],
            "start": "08:00",
            "end": "18:00",
        },
        "outside_business_hours_mode": "allow",
        "max_consecutive_auto_replies": 3,
        "confidence_threshold": 0.65,
        "human_queue_tag": "fila_humana_ia",
        "tone": "profissional",
    }


def _create_schedule_unit_and_professional(
    db_session,
    *,
    tenant_id,
    unit_name: str = "Unidade Centro",
    professional_name: str = "Dra. Agenda Centro",
    professional_in_unit: bool = True,
    working_days: list[int] | None = None,
    unit_working_hours: dict | None = None,
    procedures: list[str] | None = None,
    shift_start: str = "08:00",
    shift_end: str = "18:00",
):
    unit = Unit(
        tenant_id=tenant_id,
        code=f"CTR{uuid4().hex[:4]}",
        name=unit_name,
        phone="1133330000",
        email="centro@clinica.test",
        address={"line": "Rua Centro, 100"},
        working_hours=unit_working_hours or {},
        is_active=True,
    )
    db_session.add(unit)
    db_session.flush()
    professional = Professional(
        tenant_id=tenant_id,
        unit_id=unit.id if professional_in_unit else None,
        full_name=professional_name,
        working_days=working_days or [1, 2, 3, 4, 5],
        shift_start=shift_start,
        shift_end=shift_end,
        procedures=procedures or ["Avaliacao odontologica"],
        is_active=True,
    )
    db_session.add(professional)
    db_session.commit()
    return unit, professional


def _availability_decision_payload(*, target_date: date, unit_name: str, period: str = "manha"):
    return _decision_payload(
        intent="consultar_horarios",
        message_summary="Paciente quer horarios reais.",
        extracted_data={
            "patient_name": None,
            "responsible_name": None,
            "preferred_name": None,
            "phone": None,
            "email": None,
            "cpf": None,
            "birth_date": None,
            "unit_requested_text": unit_name,
            "unit_id": None,
            "service_requested_text": "Avaliacao odontologica",
            "service_id": None,
            "procedure_type": "Avaliacao odontologica",
            "professional_requested_text": None,
            "professional_id": None,
            "preferred_date": target_date.isoformat(),
            "preferred_period": period,
            "preferred_time_text": period,
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
        },
        appointment_intent={
            "wants_booking": True,
            "wants_reschedule": False,
            "wants_cancel": False,
            "procedure_type": "Avaliacao odontologica",
            "unit_id": None,
            "professional_id": None,
            "starts_at": None,
            "ends_at": None,
            "canceled_reason": None,
        },
        system_action={
            "required": True,
            "action": "query_availability",
            "params": {
                "unit_id": None,
                "unit_name": unit_name,
                "service_id": None,
                "procedure_type": "Avaliacao odontologica",
                "professional_id": None,
                "date": target_date.isoformat(),
                "time_after": None,
                "time_before": None,
                "period": period,
                "slot_id": None,
                "appointment_id": None,
                "hold_minutes": 10,
                "limit": 3,
            },
        },
        reply_control={
            "should_reply_now": False,
            "reply_after_system_action": True,
            "next_expected_field": None,
            "missing_fields": [],
            "suggested_next_question": None,
        },
    )


def _availability_slot(*, unit: Unit, professional: Professional, target_date: date, hhmm: str):
    hour_text, minute_text = hhmm.split(":", 1)
    local_starts_at = datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        int(hour_text),
        int(minute_text),
        tzinfo=ZoneInfo("America/Sao_Paulo"),
    )
    starts_at = local_starts_at.astimezone(UTC)
    ends_at = starts_at + timedelta(minutes=30)
    return {
        "slot_id": f"slot:{starts_at.isoformat()}",
        "unit_id": str(unit.id),
        "unit_name": unit.name,
        "professional_id": str(professional.id),
        "professional_name": professional.full_name,
        "procedure_type": "Avaliacao odontologica",
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
        "label": local_starts_at.strftime("%d/%m/%Y às %H:%M"),
    }


def _seed_previous_availability_decision(
    db_session,
    *,
    tenant_id,
    conversation: Conversation,
    inbound_message: Message,
    unit: Unit,
    professional: Professional,
    target_date: date,
    offered_times: list[str],
    period: str = "manha",
):
    slots = [
        _availability_slot(
            unit=unit,
            professional=professional,
            target_date=target_date,
            hhmm=hhmm,
        )
        for hhmm in offered_times
    ]
    db_session.add(
        AIAutoresponderDecision(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            unit_id=unit.id,
            inbound_message_id=inbound_message.id,
            outbound_message_id=None,
            channel="whatsapp",
            inbound_text=inbound_message.body or "",
            generated_response="Horários enviados",
            confidence=0.91,
            final_decision="responded",
            decision_reason="availability_options_returned",
            handoff_required=False,
            dedupe_key=f"seeded-availability:{inbound_message.id}",
            metadata_json={
                "structured_flow": True,
                "decision": _availability_decision_payload(
                    target_date=target_date,
                    unit_name=unit.name,
                    period=period,
                ),
                "system_action_result": {
                    "action": "query_availability",
                    "slots": slots,
                },
            },
        )
    )
    db_session.commit()
    return slots


def _slot_selection_decision_payload(*, unit_name: str, slot_id: str | None = None, starts_at: str | None = None):
    return _decision_payload(
        intent="selecionar_horario",
        message_summary="Paciente escolheu um horario real.",
        extracted_data={
            "patient_name": None,
            "responsible_name": None,
            "preferred_name": None,
            "phone": None,
            "email": None,
            "cpf": None,
            "birth_date": None,
            "unit_requested_text": unit_name,
            "unit_id": None,
            "service_requested_text": "Avaliacao odontologica",
            "service_id": None,
            "procedure_type": "Avaliacao odontologica",
            "professional_requested_text": None,
            "professional_id": None,
            "preferred_date": None,
            "preferred_period": "manha",
            "preferred_time_text": None,
            "selected_slot_id": slot_id,
            "selected_datetime": starts_at,
            "appointment_id": None,
            "pain": {
                "has_pain": None,
                "duration_text": None,
                "has_swelling": None,
                "has_fever": None,
                "urgency_level": "desconhecida",
            },
        },
        appointment_intent={
            "wants_booking": True,
            "wants_reschedule": False,
            "wants_cancel": False,
            "procedure_type": "Avaliacao odontologica",
            "unit_id": None,
            "professional_id": None,
            "starts_at": starts_at,
            "ends_at": None,
            "canceled_reason": None,
        },
        system_action={
            "required": True,
            "action": "validate_slot",
            "params": {
                "unit_id": None,
                "unit_name": unit_name,
                "service_id": None,
                "procedure_type": "Avaliacao odontologica",
                "professional_id": None,
                "date": None,
                "time_after": None,
                "time_before": None,
                "period": "manha",
                "slot_id": slot_id,
                "appointment_id": None,
                "hold_minutes": 10,
                "limit": 3,
            },
        },
        reply_control={
            "should_reply_now": False,
            "reply_after_system_action": True,
            "next_expected_field": "patient_name",
            "missing_fields": ["patient_name"],
            "suggested_next_question": None,
        },
    )


def test_ai_decision_schema_rejects_unknown_fields():
    payload = _decision_payload(extra_field="nao_pode")

    with pytest.raises(ValidationError):
        validate_ai_decision_output(payload)


def test_repaired_reply_uses_patient_facing_missing_field_label():
    payload = _decision_payload()
    payload["reply_control"] = {
        "should_reply_now": True,
        "reply_after_system_action": False,
        "next_expected_field": "patient_name",
        "missing_fields": ["patient_name"],
        "suggested_next_question": None,
    }
    decision = AiDecisionOutput.model_validate(payload)
    patient_reply = PatientReplyOutput.model_validate(
        {
            "schema_version": "1.0",
            "message": "Mensagem repetida",
            "message_type": "text",
            "interactive_payload": None,
            "confidence": 0.91,
            "final_decision": "reply",
            "decision_reason": "unit_test",
        }
    )

    repaired = _repair_patient_reply_after_review(
        patient_reply=patient_reply,
        decision=decision,
        system_action_result={},
        context=None,
        review={"flags": ["mensagem_muito_parecida_com_anterior"], "motivo": "unit_test"},
    )

    assert "patient_name" not in repaired.message
    assert "seu nome completo" in repaired.message


def test_placeholder_patient_names_include_public_webchat_defaults():
    assert _looks_like_placeholder_name("Paciente do agendamento") is True
    assert _looks_like_placeholder_name("Paciente Webchat") is True
    assert _looks_like_placeholder_name("Guilherme Gomes") is False


def test_ai_decision_schema_rejects_forbidden_field_update():
    payload = _decision_payload(
        field_updates=[
            {
                "target": "patients",
                "field": "operational_notes",
                "value": "dado proibido",
                "confidence": 0.99,
                "source_text": "texto",
                "should_apply": True,
                "reason": "não pode",
            }
        ]
    )

    with pytest.raises(ValidationError):
        validate_ai_decision_output(payload)


def test_legacy_extractor_payload_is_adapted_to_strict_decision_contract():
    decision = validate_ai_decision_output(
        {
            "intent": "agendamento",
            "confidence": 0.86,
            "entities": {
                "unit_preference": "Unidade principal",
                "preferred_period": "manha",
                "service_type": "Avaliacao odontologica",
            },
            "next_action": "show_available_dates",
            "handoff": {"required": False},
        }
    )

    assert decision.schema_version == "1.0"
    assert decision.intent == "agendar_consulta"
    assert decision.extracted_data.unit_requested_text == "Unidade principal"
    assert decision.extracted_data.preferred_period == "manha"
    assert decision.extracted_data.service_requested_text == "Avaliacao odontologica"
    assert decision.system_action.action == "query_availability"
    assert decision.system_action.required is True
    assert decision.field_updates == []


def test_minimal_legacy_extractor_payload_is_adapted_to_strict_decision_contract():
    decision = validate_ai_decision_output(
        {
            "intent": "outro",
            "confidence": 0.74,
            "action": "none",
            "required": False,
        }
    )

    assert decision.schema_version == "1.0"
    assert decision.intent == "outro"
    assert decision.confidence == 0.74
    assert decision.detected_language == "pt-BR"
    assert decision.message_summary == "Intent: outro"
    assert decision.system_action.action == "none"
    assert decision.system_action.required is False
    assert decision.reply_control.should_reply_now is True
    assert decision.reply_control.reply_after_system_action is False
    assert decision.field_updates == []


def test_legacy_patient_reply_payload_is_adapted_to_strict_reply_contract():
    reply = validate_patient_reply_output(
        {
            "patient_reply": "Claro, posso verificar horários para sua avaliação.",
            "confidence": 0.8,
        }
    )

    assert reply.schema_version == "1.0"
    assert reply.message == "Claro, posso verificar horários para sua avaliação."
    assert reply.final_decision == "reply"
    assert reply.message_type == "text"


def test_safe_plan_skips_null_empty_and_low_confidence_updates():
    patient = Patient(
        id=uuid4(),
        tenant_id=uuid4(),
        full_name="Maria Existente",
        phone="5511999999999",
        normalized_phone="5511999999999",
    )
    conversation = Conversation(id=uuid4(), tenant_id=patient.tenant_id, patient_id=patient.id, channel="whatsapp", status="aberta", tags=[])
    inbound = Message(id=uuid4(), tenant_id=patient.tenant_id, conversation_id=conversation.id, direction="inbound", channel="whatsapp", body="meu nome é Juliana", sender_type="patient", status="received")
    decision = AiDecisionOutput.model_validate(
        _decision_payload(
            field_updates=[
                {
                    "target": "patients",
                    "field": "email",
                    "value": None,
                    "confidence": 0.99,
                    "source_text": "email vazio",
                    "should_apply": True,
                    "reason": "sem valor",
                },
                {
                    "target": "patients",
                    "field": "full_name",
                    "value": "Juliana",
                    "confidence": 0.2,
                    "source_text": "Juliana",
                    "should_apply": True,
                    "reason": "baixa confiança",
                },
            ]
        )
    )

    plan = build_safe_persistence_plan(
        decision=decision,
        conversation=conversation,
        inbound_message=inbound,
        patient=patient,
        lead=None,
        confidence_threshold=0.65,
    )

    assert plan.safe_updates["patients"] == {}
    assert "skipped_patients.email:empty_value" in plan.risk_flags
    assert "skipped_patients.full_name:low_confidence" in plan.risk_flags


def test_safe_plan_allows_explicit_patient_correction():
    tenant_id = uuid4()
    patient = Patient(
        id=uuid4(),
        tenant_id=tenant_id,
        full_name="Maria Existente",
        phone="5511999999999",
        normalized_phone="5511999999999",
    )
    conversation = Conversation(id=uuid4(), tenant_id=tenant_id, patient_id=patient.id, channel="whatsapp", status="aberta", tags=[])
    inbound = Message(id=uuid4(), tenant_id=tenant_id, conversation_id=conversation.id, direction="inbound", channel="whatsapp", body="na verdade meu nome é Juliana", sender_type="patient", status="received")
    decision = AiDecisionOutput.model_validate(
        _decision_payload(
            field_updates=[
                {
                    "target": "patients",
                    "field": "full_name",
                    "value": "Juliana",
                    "confidence": 0.95,
                    "source_text": "na verdade meu nome é Juliana",
                    "should_apply": True,
                    "reason": "correção explícita do paciente",
                }
            ]
        )
    )

    plan = build_safe_persistence_plan(
        decision=decision,
        conversation=conversation,
        inbound_message=inbound,
        patient=patient,
        lead=None,
        confidence_threshold=0.65,
    )

    assert plan.safe_updates["patients"]["full_name"] == "Juliana"


def test_context_excludes_forbidden_patient_notes_and_unit_services(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    patient, _lead, conversation, inbound = _conversation_with_inbound(db_session, tenant_id=tenant_id, inbound_text="Oi")
    unit = Unit(tenant_id=tenant_id, code="CTR", name="Centro", address={}, working_hours={}, is_active=True)
    db_session.add(unit)
    db_session.flush()
    conversation.unit_id = unit.id
    patient.unit_id = unit.id
    db_session.add_all([conversation, patient])
    _upsert_setting(db_session, tenant_id=tenant_id, key=f"unit.services.{unit.id}", value={"services": ["Segredo local"]})
    config = {
        "enabled": True,
        "channels": {"whatsapp": True},
        "business_hours": {"timezone": "America/Sao_Paulo", "weekdays": [0, 1, 2, 3, 4, 5, 6], "start": "00:00", "end": "23:59"},
        "outside_business_hours_mode": "allow",
        "max_consecutive_auto_replies": 3,
        "confidence_threshold": 0.65,
        "human_queue_tag": "fila_humana_ia",
        "tone": "profissional",
        "interactive_booking_options_enabled": True,
    }

    context = build_ai_conversation_context(db_session, tenant_id=tenant_id, conversation=conversation, inbound_message=inbound, config=config)
    serialized = json.dumps(context.model_dump(mode="json"), ensure_ascii=False)

    assert "NÃO ENVIAR PARA IA" not in serialized
    assert "operational_notes" not in serialized
    assert "tags_cache" not in serialized
    assert "unit.services" not in serialized
    assert "Segredo local" not in serialized


def test_structured_process_saves_raw_before_llm_and_creates_outbox(monkeypatch, seeded_db, db_session):
    from app.services import ai_structured_flow

    tenant_id = seeded_db["tenant_a"].id
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    _upsert_setting(
        db_session,
        tenant_id=tenant_id,
        key="ai_autoresponder.global",
        value={
            "enabled": True,
            "structured_flow_enabled": True,
            "channels": {"whatsapp": True},
            "business_hours": {"timezone": "America/Sao_Paulo", "weekdays": [0, 1, 2, 3, 4, 5, 6], "start": "00:00", "end": "23:59"},
            "outside_business_hours_mode": "allow",
            "max_consecutive_auto_replies": 3,
            "confidence_threshold": 0.65,
            "human_queue_tag": "fila_humana_ia",
            "tone": "profissional",
        },
    )
    patient, _lead, conversation, inbound = _conversation_with_inbound(db_session, tenant_id=tenant_id, inbound_text="Oi, sou Juliana")
    calls = []

    def _fake_run_llm_task(db, *, tenant_id, conversation_id, task, prompt):
        saved_inbound = db.get(Message, inbound.id)
        assert saved_inbound is not None
        assert saved_inbound.body == "Oi, sou Juliana"
        calls.append(task)
        if task == "auto_responder_structured_extract":
            return {
                "output": json.dumps(
                    _decision_payload(
                        field_updates=[
                            {
                                "target": "patients",
                                "field": "full_name",
                                "value": "Juliana",
                                "confidence": 0.9,
                                "source_text": "sou Juliana",
                                "should_apply": True,
                                "reason": "nome informado",
                            }
                        ]
                    ),
                    ensure_ascii=False,
                ),
                "metadata": {"provider": "test", "task": task, "latency_ms": 1},
            }
        return {
            "output": json.dumps(
                {
                    "schema_version": "1.0",
                    "message": "Olá, Juliana! Como posso te ajudar hoje?",
                    "message_type": "text",
                    "interactive_payload": None,
                    "confidence": 0.91,
                    "final_decision": "reply",
                    "decision_reason": "response_sent",
                },
                ensure_ascii=False,
            ),
            "metadata": {"provider": "test", "task": task, "latency_ms": 1},
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _fake_run_llm_task)

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    db_session.refresh(patient)
    assert result["status"] == "responded"
    assert result["structured_flow"] is True
    assert calls == ["auto_responder_structured_extract", "auto_responder_structured_reply"]
    assert patient.full_name == "Juliana"
    assert db_session.scalar(select(OutboxMessage).where(OutboxMessage.tenant_id == tenant_id)) is not None
    decision = db_session.scalar(select(AIAutoresponderDecision).where(AIAutoresponderDecision.dedupe_key == f"inbound:{inbound.id}"))
    assert decision is not None
    assert decision.prompt_version == "structured-v1.0"


def test_invalid_structured_json_does_not_update_patient(monkeypatch, seeded_db, db_session):
    from app.services import ai_structured_flow

    tenant_id = seeded_db["tenant_a"].id
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    _upsert_setting(
        db_session,
        tenant_id=tenant_id,
        key="ai_autoresponder.global",
        value={
            "enabled": True,
            "structured_flow_enabled": True,
            "channels": {"whatsapp": True},
            "business_hours": {"timezone": "America/Sao_Paulo", "weekdays": [0, 1, 2, 3, 4, 5, 6], "start": "00:00", "end": "23:59"},
            "outside_business_hours_mode": "allow",
            "max_consecutive_auto_replies": 3,
            "confidence_threshold": 0.65,
            "human_queue_tag": "fila_humana_ia",
            "tone": "profissional",
        },
    )
    patient, _lead, conversation, inbound = _conversation_with_inbound(db_session, tenant_id=tenant_id, inbound_text="sou Juliana")
    original_name = patient.full_name

    def _invalid_run_llm_task(db, *, tenant_id, conversation_id, task, prompt):
        return {"output": "{json quebrado", "metadata": {"provider": "test", "task": task, "latency_ms": 1}}

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _invalid_run_llm_task)

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    db_session.refresh(patient)
    assert result["status"] == "responded"
    assert patient.full_name == original_name
    decision = db_session.scalar(select(AIAutoresponderDecision).where(AIAutoresponderDecision.dedupe_key == f"inbound:{inbound.id}"))
    assert decision is not None
    assert decision.metadata_json["system_action_result"]["status"] == "invalid_contract_fallback"


def test_query_availability_respects_ui_working_days_for_requested_date(seeded_db, db_session):
    from app.services import ai_structured_flow

    tenant_id = seeded_db["tenant_a"].id
    patient, _lead, conversation, inbound = _conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quero horarios na segunda de manha.",
    )
    target_date = _next_python_weekday(0)
    unit, _professional = _create_schedule_unit_and_professional(
        db_session,
        tenant_id=tenant_id,
        working_days=[1, 2, 3, 4, 5],
    )
    conversation.unit_id = unit.id
    db_session.add_all([patient, conversation])
    db_session.commit()

    context = build_ai_conversation_context(
        db_session,
        tenant_id=tenant_id,
        conversation=conversation,
        inbound_message=inbound,
        config=_structured_config(),
    )
    decision = AiDecisionOutput.model_validate(
        _availability_decision_payload(target_date=target_date, unit_name=unit.name)
    )

    slots = ai_structured_flow._query_availability(
        db_session,
        tenant_id=tenant_id,
        context=context,
        decision=decision,
        params=decision.system_action.params.model_dump(mode="json"),
    )

    assert slots
    assert slots[0]["label"].startswith(target_date.strftime("%d/%m/%Y"))


def test_query_availability_includes_global_professional_for_unit(seeded_db, db_session):
    from app.services import ai_structured_flow

    tenant_id = seeded_db["tenant_a"].id
    _patient, _lead, conversation, inbound = _conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quero avaliar disponibilidade dessa unidade.",
    )
    target_date = _next_python_weekday(1)
    unit, professional = _create_schedule_unit_and_professional(
        db_session,
        tenant_id=tenant_id,
        professional_in_unit=False,
        working_days=[0, 1, 2, 3, 4, 5, 6],
    )
    conversation.unit_id = unit.id
    db_session.add(conversation)
    db_session.commit()

    context = build_ai_conversation_context(
        db_session,
        tenant_id=tenant_id,
        conversation=conversation,
        inbound_message=inbound,
        config=_structured_config(),
    )
    decision = AiDecisionOutput.model_validate(
        _availability_decision_payload(target_date=target_date, unit_name=unit.name)
    )

    slots = ai_structured_flow._query_availability(
        db_session,
        tenant_id=tenant_id,
        context=context,
        decision=decision,
        params=decision.system_action.params.model_dump(mode="json"),
    )

    assert slots
    assert slots[0]["professional_id"] == str(professional.id)


def test_query_availability_skips_previously_offered_slots_for_new_alternatives(seeded_db, db_session):
    from app.services import ai_structured_flow

    tenant_id = seeded_db["tenant_a"].id
    _patient, _lead, conversation, inbound = _conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quero horarios para avaliacao.",
    )
    target_date = _next_python_weekday(1)
    unit, professional = _create_schedule_unit_and_professional(
        db_session,
        tenant_id=tenant_id,
        working_days=[0, 1, 2, 3, 4, 5, 6],
        shift_end="12:00",
    )
    conversation.unit_id = unit.id
    db_session.add(conversation)
    db_session.commit()
    previous_slots = _seed_previous_availability_decision(
        db_session,
        tenant_id=tenant_id,
        conversation=conversation,
        inbound_message=inbound,
        unit=unit,
        professional=professional,
        target_date=target_date,
        offered_times=["08:00", "08:30", "09:00"],
    )
    follow_up = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="inbound",
        channel="whatsapp",
        sender_type="patient",
        body="Pode verificar outro horário disponível, de preferência no mesmo período?",
        message_type="text",
        payload={},
        status="received",
    )
    db_session.add(follow_up)
    db_session.commit()

    context = build_ai_conversation_context(
        db_session,
        tenant_id=tenant_id,
        conversation=conversation,
        inbound_message=follow_up,
        config=_structured_config(),
    )
    decision = AiDecisionOutput.model_validate(
        _availability_decision_payload(target_date=target_date, unit_name=unit.name)
    )
    params = decision.system_action.params.model_dump(mode="json")
    params["exclude_previously_offered"] = True

    slots = ai_structured_flow._query_availability(
        db_session,
        tenant_id=tenant_id,
        context=context,
        decision=decision,
        params=params,
    )

    previous_ids = {slot["slot_id"] for slot in previous_slots}
    assert slots
    assert slots[0]["label"].endswith("09:30")
    assert not previous_ids.intersection({slot["slot_id"] for slot in slots})


def test_process_inbound_message_uses_recent_availability_window_for_end_of_morning(monkeypatch, seeded_db, db_session):
    from app.services import ai_structured_flow
    from app.services import whatsapp_service

    tenant_id = seeded_db["tenant_a"].id
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    _upsert_setting(
        db_session,
        tenant_id=tenant_id,
        key="ai_autoresponder.global",
        value=_structured_config(),
    )
    target_date = _next_python_weekday(1)
    unit, professional = _create_schedule_unit_and_professional(
        db_session,
        tenant_id=tenant_id,
        working_days=[0, 1, 2, 3, 4, 5, 6],
        shift_end="12:00",
    )
    _patient, _lead, conversation, inbound = _conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quero avaliacao para amanha de manha.",
    )
    conversation.unit_id = unit.id
    db_session.add(conversation)
    db_session.commit()
    _seed_previous_availability_decision(
        db_session,
        tenant_id=tenant_id,
        conversation=conversation,
        inbound_message=inbound,
        unit=unit,
        professional=professional,
        target_date=target_date,
        offered_times=["08:00", "08:30", "09:00"],
    )
    follow_up = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="inbound",
        channel="whatsapp",
        sender_type="patient",
        body="Pode ser uma opção no fim da manhã, se tiver.",
        message_type="text",
        payload={},
        status="received",
    )
    db_session.add(follow_up)
    db_session.commit()

    def _fake_run_llm_task(db, *, tenant_id, conversation_id, task, prompt):
        return {
            "output": json.dumps(
                _decision_payload(
                    intent="outro",
                    message_summary="Paciente quer outra opcao de horario.",
                ),
                ensure_ascii=False,
            ),
            "metadata": {"provider": "test", "task": task, "latency_ms": 1},
        }

    def _fake_run_reply_generator(db, *, tenant_id, conversation_id, context, decision, plan, system_action_result, **kwargs):
        labels = [slot.get("label") for slot in system_action_result.get("slots") or [] if slot.get("label")]
        reply = "Tenho estes horarios disponiveis: " + ", ".join(labels[:3])
        return (
            ai_structured_flow.PatientReplyOutput(
                schema_version="1.0",
                message=reply,
                message_type="text",
                interactive_payload=None,
                confidence=0.91,
                final_decision="reply",
                decision_reason="availability_options_returned",
            ),
            {"output": "{}", "metadata": {"provider": "test", "task": "reply", "latency_ms": 1}},
        )

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _fake_run_llm_task)
    monkeypatch.setattr(ai_structured_flow, "_run_reply_generator", _fake_run_reply_generator)
    monkeypatch.setattr(whatsapp_service, "_dispatch_outbox_item_inline", lambda *args, **kwargs: None)

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=follow_up.id,
    )

    outbound = db_session.scalar(
        select(Message)
        .where(Message.conversation_id == conversation.id, Message.direction == "outbound")
        .order_by(Message.created_at.desc())
    )
    decision = db_session.scalar(
        select(AIAutoresponderDecision).where(AIAutoresponderDecision.dedupe_key == f"inbound:{follow_up.id}")
    )
    slots = decision.metadata_json["system_action_result"]["slots"]
    assert result["status"] == "responded"
    assert decision is not None
    assert decision.metadata_json["decision"]["system_action"]["params"]["time_after"] == "10:30"
    assert decision.metadata_json["decision"]["system_action"]["params"]["time_before"] == "12:00"
    assert slots[0]["label"].endswith("10:30")
    assert outbound is not None
    assert "10:30" in outbound.body
    assert "08:00" not in outbound.body


def test_process_inbound_message_corrects_weekday_date_and_keeps_period(monkeypatch, seeded_db, db_session):
    from app.services import ai_structured_flow
    from app.services import whatsapp_service

    tenant_id = seeded_db["tenant_a"].id
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    _upsert_setting(
        db_session,
        tenant_id=tenant_id,
        key="ai_autoresponder.global",
        value=_structured_config(),
    )
    target_date = _next_python_weekday(1)
    previous_date = target_date - timedelta(days=1)
    unit, professional = _create_schedule_unit_and_professional(
        db_session,
        tenant_id=tenant_id,
        working_days=[0, 1, 2, 3, 4, 5, 6],
    )
    _patient, _lead, conversation, inbound = _conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quero para terca-feira na parte da tarde.",
    )
    conversation.unit_id = unit.id
    db_session.add(conversation)
    db_session.commit()
    _seed_previous_availability_decision(
        db_session,
        tenant_id=tenant_id,
        conversation=conversation,
        inbound_message=inbound,
        unit=unit,
        professional=professional,
        target_date=previous_date,
        offered_times=["12:00", "12:30", "13:00"],
        period="tarde",
    )
    follow_up = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="inbound",
        channel="whatsapp",
        sender_type="patient",
        body=f"terca feira e dia {target_date.day}",
        message_type="text",
        payload={},
        status="received",
    )
    db_session.add(follow_up)
    db_session.commit()

    def _fake_run_llm_task(db, *, tenant_id, conversation_id, task, prompt):
        return {
            "output": json.dumps(
                _decision_payload(
                    intent="consultar_horarios",
                    message_summary="Paciente corrigiu o dia da semana.",
                    system_action={
                        "required": True,
                        "action": "query_availability",
                        "params": {
                            "unit_id": str(unit.id),
                            "unit_name": unit.name,
                            "service_id": None,
                            "procedure_type": None,
                            "professional_id": None,
                            "date": previous_date.isoformat(),
                            "time_after": None,
                            "time_before": None,
                            "period": None,
                            "slot_id": None,
                            "appointment_id": None,
                            "hold_minutes": 10,
                            "limit": 3,
                        },
                    },
                    reply_control={
                        "should_reply_now": False,
                        "reply_after_system_action": True,
                        "next_expected_field": None,
                        "missing_fields": [],
                        "suggested_next_question": None,
                    },
                ),
                ensure_ascii=False,
            ),
            "metadata": {"provider": "test", "task": task, "latency_ms": 1},
        }

    def _fake_run_reply_generator(db, *, tenant_id, conversation_id, context, decision, plan, system_action_result):
        return (
            ai_structured_flow._fallback_patient_reply(
                decision=decision,
                system_action_result=system_action_result,
                context=context,
            ),
            {"output": "{}", "metadata": {"provider": "test", "task": "reply", "latency_ms": 1}},
        )

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _fake_run_llm_task)
    monkeypatch.setattr(ai_structured_flow, "_run_reply_generator", _fake_run_reply_generator)
    monkeypatch.setattr(whatsapp_service, "_dispatch_outbox_item_inline", lambda *args, **kwargs: None)

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=follow_up.id,
    )

    outbound = db_session.scalar(
        select(Message)
        .where(Message.conversation_id == conversation.id, Message.direction == "outbound")
        .order_by(Message.created_at.desc())
    )
    decision = db_session.scalar(
        select(AIAutoresponderDecision).where(AIAutoresponderDecision.dedupe_key == f"inbound:{follow_up.id}")
    )
    params = decision.metadata_json["decision"]["system_action"]["params"]
    slots = decision.metadata_json["system_action_result"]["slots"]
    assert result["status"] == "responded"
    assert params["date"] == target_date.isoformat()
    assert params["period"] == "tarde"
    assert slots
    assert slots[0]["label"].startswith(target_date.strftime("%d/%m/%Y"))
    assert slots[0]["label"].endswith("12:00")
    assert outbound is not None
    assert target_date.strftime("%d/%m/%Y") in outbound.body


def test_process_inbound_message_reproduces_weekday_correction_thread(monkeypatch, seeded_db, db_session):
    from app.services import ai_structured_flow
    from app.services import whatsapp_service

    tenant_id = seeded_db["tenant_a"].id
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    _upsert_setting(
        db_session,
        tenant_id=tenant_id,
        key="ai_autoresponder.global",
        value=_structured_config(),
    )
    target_date = _next_python_weekday(1)
    previous_date = target_date - timedelta(days=1)
    unit, _professional = _create_schedule_unit_and_professional(
        db_session,
        tenant_id=tenant_id,
        unit_name="Unidade principal",
        professional_name="Dr. Rafael Campos",
        working_days=[0, 1, 2, 3, 4, 5, 6],
    )
    _patient, _lead, conversation, _opening = _conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="quero fazer um agendamento",
    )
    conversation.unit_id = unit.id
    db_session.add(conversation)
    db_session.commit()

    def _fake_run_llm_task(db, *, tenant_id, conversation_id, task, prompt):
        return {
            "output": json.dumps(
                _decision_payload(
                    intent="consultar_horarios",
                    message_summary="Paciente quer horarios para terca a tarde.",
                    system_action={
                        "required": True,
                        "action": "query_availability",
                        "params": {
                            "unit_id": None,
                            "unit_name": unit.name,
                            "service_id": None,
                            "procedure_type": "Avaliacao odontologica",
                            "professional_id": None,
                            "date": previous_date.isoformat(),
                            "time_after": None,
                            "time_before": None,
                            "period": None,
                            "slot_id": None,
                            "appointment_id": None,
                            "hold_minutes": 10,
                            "limit": 3,
                        },
                    },
                    reply_control={
                        "should_reply_now": False,
                        "reply_after_system_action": True,
                        "next_expected_field": None,
                        "missing_fields": [],
                        "suggested_next_question": None,
                    },
                ),
                ensure_ascii=False,
            ),
            "metadata": {"provider": "test", "task": task, "latency_ms": 1},
        }

    def _fake_run_reply_generator(db, *, tenant_id, conversation_id, context, decision, plan, system_action_result, **kwargs):
        labels = [slot.get("label") for slot in system_action_result.get("slots") or [] if slot.get("label")]
        reply = "Tenho estes horarios disponiveis: " + ", ".join(labels[:3])
        return (
            ai_structured_flow.PatientReplyOutput(
                schema_version="1.0",
                message=reply,
                message_type="text",
                interactive_payload=None,
                confidence=0.91,
                final_decision="reply",
                decision_reason="availability_options_returned",
            ),
            {"output": "{}", "metadata": {"provider": "test", "task": "reply", "latency_ms": 1}},
        )

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _fake_run_llm_task)
    monkeypatch.setattr(ai_structured_flow, "_run_reply_generator", _fake_run_reply_generator)
    monkeypatch.setattr(whatsapp_service, "_dispatch_outbox_item_inline", lambda *args, **kwargs: None)

    first_request = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="inbound",
        channel="whatsapp",
        sender_type="patient",
        body="quero para a terca feira na parte da tarde",
        message_type="text",
        payload={},
        status="received",
    )
    db_session.add(first_request)
    db_session.commit()

    first_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=first_request.id,
    )
    first_decision = db_session.scalar(
        select(AIAutoresponderDecision).where(AIAutoresponderDecision.dedupe_key == f"inbound:{first_request.id}")
    )
    first_slots = first_decision.metadata_json["system_action_result"]["slots"]
    assert first_result["status"] == "responded"
    assert first_decision.metadata_json["decision"]["system_action"]["params"]["date"] == target_date.isoformat()
    assert first_decision.metadata_json["decision"]["system_action"]["params"]["period"] == "tarde"
    assert first_slots[0]["label"].startswith(target_date.strftime("%d/%m/%Y"))
    assert not first_slots[0]["label"].startswith(previous_date.strftime("%d/%m/%Y"))

    correction = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="inbound",
        channel="whatsapp",
        sender_type="patient",
        body=f"terca feira e dia {target_date.day}",
        message_type="text",
        payload={},
        status="received",
    )
    db_session.add(correction)
    db_session.commit()

    correction_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=correction.id,
    )
    correction_decision = db_session.scalar(
        select(AIAutoresponderDecision).where(AIAutoresponderDecision.dedupe_key == f"inbound:{correction.id}")
    )
    correction_slots = correction_decision.metadata_json["system_action_result"]["slots"]
    correction_outbound = db_session.scalar(
        select(Message)
        .where(Message.conversation_id == conversation.id, Message.direction == "outbound")
        .order_by(Message.created_at.desc())
    )
    assert correction_result["status"] == "responded"
    assert correction_decision.metadata_json["decision"]["system_action"]["params"]["date"] == target_date.isoformat()
    assert correction_decision.metadata_json["decision"]["system_action"]["params"]["period"] == "tarde"
    assert correction_slots[0]["label"].startswith(target_date.strftime("%d/%m/%Y"))
    assert correction_slots[0]["label"].endswith("12:00")
    assert correction_outbound is not None
    assert previous_date.strftime("%d/%m/%Y") not in correction_outbound.body


def test_process_inbound_message_skips_repeated_slots_when_patient_requests_other_options(monkeypatch, seeded_db, db_session):
    from app.services import ai_structured_flow
    from app.services import whatsapp_service

    tenant_id = seeded_db["tenant_a"].id
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    _upsert_setting(
        db_session,
        tenant_id=tenant_id,
        key="ai_autoresponder.global",
        value=_structured_config(),
    )
    target_date = _next_python_weekday(1)
    unit, professional = _create_schedule_unit_and_professional(
        db_session,
        tenant_id=tenant_id,
        working_days=[0, 1, 2, 3, 4, 5, 6],
        shift_end="12:00",
    )
    _patient, _lead, conversation, inbound = _conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quero avaliacao para amanha de manha.",
    )
    conversation.unit_id = unit.id
    db_session.add(conversation)
    db_session.commit()
    _seed_previous_availability_decision(
        db_session,
        tenant_id=tenant_id,
        conversation=conversation,
        inbound_message=inbound,
        unit=unit,
        professional=professional,
        target_date=target_date,
        offered_times=["08:00", "08:30", "09:00"],
    )
    follow_up = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="inbound",
        channel="whatsapp",
        sender_type="patient",
        body="Tudo bem, me mande outras opções reais de horário disponíveis.",
        message_type="text",
        payload={},
        status="received",
    )
    db_session.add(follow_up)
    db_session.commit()

    def _fake_run_llm_task(db, *, tenant_id, conversation_id, task, prompt):
        return {
            "output": json.dumps(
                _decision_payload(
                    intent="outro",
                    message_summary="Paciente quer outras opcoes reais.",
                ),
                ensure_ascii=False,
            ),
            "metadata": {"provider": "test", "task": task, "latency_ms": 1},
        }

    def _fake_run_reply_generator(db, *, tenant_id, conversation_id, context, decision, plan, system_action_result):
        return (
            ai_structured_flow._fallback_patient_reply(
                decision=decision,
                system_action_result=system_action_result,
                context=context,
            ),
            {"output": "{}", "metadata": {"provider": "test", "task": "reply", "latency_ms": 1}},
        )

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _fake_run_llm_task)
    monkeypatch.setattr(ai_structured_flow, "_run_reply_generator", _fake_run_reply_generator)
    monkeypatch.setattr(whatsapp_service, "_dispatch_outbox_item_inline", lambda *args, **kwargs: None)

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=follow_up.id,
    )

    outbound = db_session.scalar(
        select(Message)
        .where(Message.conversation_id == conversation.id, Message.direction == "outbound")
        .order_by(Message.created_at.desc())
    )
    decision = db_session.scalar(
        select(AIAutoresponderDecision).where(AIAutoresponderDecision.dedupe_key == f"inbound:{follow_up.id}")
    )
    slots = decision.metadata_json["system_action_result"]["slots"]
    assert result["status"] == "responded"
    assert decision is not None
    assert decision.metadata_json["decision"]["system_action"]["params"]["exclude_previously_offered"] is True
    assert slots[0]["label"].endswith("09:30")
    assert outbound is not None
    assert "09:30" in outbound.body
    assert "08:00" not in outbound.body


def test_process_inbound_message_returns_requested_day_slots_in_structured_flow(monkeypatch, seeded_db, db_session):
    from app.services import ai_structured_flow

    tenant_id = seeded_db["tenant_a"].id
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    _upsert_setting(
        db_session,
        tenant_id=tenant_id,
        key="ai_autoresponder.global",
        value=_structured_config(),
    )
    _patient, _lead, conversation, inbound = _conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Preciso de horarios reais para segunda de manha.",
    )
    target_date = _next_python_weekday(0)
    unit, _professional = _create_schedule_unit_and_professional(
        db_session,
        tenant_id=tenant_id,
        working_days=[1, 2, 3, 4, 5],
    )
    conversation.unit_id = unit.id
    db_session.add(conversation)
    db_session.commit()

    def _fake_run_llm_task(db, *, tenant_id, conversation_id, task, prompt):
        if task == "auto_responder_structured_extract":
            return {
                "output": json.dumps(
                    _availability_decision_payload(target_date=target_date, unit_name=unit.name),
                    ensure_ascii=False,
                ),
                "metadata": {"provider": "test", "task": task, "latency_ms": 1},
            }
        system_action_json = prompt.split("SYSTEM_ACTION_RESULT_JSON:\n", 1)[1].split(
            "\n\nRetorne somente PatientReplyOutput",
            1,
        )[0]
        slots = json.loads(system_action_json)["slots"]
        first_label = slots[0]["label"]
        return {
            "output": json.dumps(
                {
                    "schema_version": "1.0",
                    "message": f"Encontrei este horario real: {first_label}. Quer seguir com ele?",
                    "message_type": "text",
                    "interactive_payload": None,
                    "confidence": 0.92,
                    "final_decision": "reply",
                    "decision_reason": "availability_returned",
                },
                ensure_ascii=False,
            ),
            "metadata": {"provider": "test", "task": task, "latency_ms": 1},
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _fake_run_llm_task)

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    outbound = db_session.scalar(
        select(Message)
        .where(Message.conversation_id == conversation.id, Message.direction == "outbound")
        .order_by(Message.created_at.desc())
    )
    decision = db_session.scalar(
        select(AIAutoresponderDecision).where(AIAutoresponderDecision.dedupe_key == f"inbound:{inbound.id}")
    )
    assert result["status"] == "responded"
    assert result["structured_flow"] is True
    assert outbound is not None
    assert target_date.strftime("%d/%m/%Y") in outbound.body
    assert decision is not None
    assert decision.metadata_json["system_action_result"]["slots"][0]["label"].startswith(target_date.strftime("%d/%m/%Y"))


def test_structured_flow_uses_first_message_hints_and_prefixes_first_reply(monkeypatch, seeded_db, db_session):
    from app.services import ai_structured_flow
    from app.services import whatsapp_service

    tenant_id = seeded_db["tenant_a"].id
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    _upsert_setting(
        db_session,
        tenant_id=tenant_id,
        key="ai_autoresponder.global",
        value=_structured_config(),
    )
    _upsert_setting(
        db_session,
        tenant_id=tenant_id,
        key="clinic.profile",
        value={"clinic_name": "Clinica Sorriso"},
    )
    target_date = _next_python_weekday(1)
    unit, _professional = _create_schedule_unit_and_professional(
        db_session,
        tenant_id=tenant_id,
        unit_name="Unidade Centro",
        procedures=["Limpeza"],
    )
    _patient, _lead, conversation, inbound = _conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text=f"Oi, quero agendar limpeza na {unit.name} {target_date.strftime('%d/%m/%Y')} de tarde.",
    )
    conversation.unit_id = unit.id
    db_session.add(conversation)
    db_session.commit()

    def _fake_run_llm_task(db, *, tenant_id, conversation_id, task, prompt):
        if task == "auto_responder_structured_extract":
            payload = _decision_payload(
                intent="agendar_consulta",
                message_summary="Paciente quer agendar.",
                extracted_data={
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
                },
                appointment_intent={
                    "wants_booking": False,
                    "wants_reschedule": False,
                    "wants_cancel": False,
                    "procedure_type": None,
                    "unit_id": None,
                    "professional_id": None,
                    "starts_at": None,
                    "ends_at": None,
                    "canceled_reason": None,
                },
                system_action={
                    "required": False,
                    "action": "none",
                    "params": {
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
                    },
                },
            )
            return {
                "output": json.dumps(payload, ensure_ascii=False),
                "metadata": {"provider": "test", "task": task, "latency_ms": 1},
            }
        system_action_json = prompt.split("SYSTEM_ACTION_RESULT_JSON:\n", 1)[1].split(
            "\n\nRetorne somente PatientReplyOutput",
            1,
        )[0]
        action_result = json.loads(system_action_json)
        assert action_result["action"] == "query_availability"
        return {
            "output": json.dumps(
                {
                    "schema_version": "1.0",
                    "message": "Verifiquei seu pedido de Limpeza na Unidade Centro para o período da tarde.",
                    "message_type": "text",
                    "interactive_payload": None,
                    "confidence": 0.92,
                    "final_decision": "reply",
                    "decision_reason": "availability_returned",
                },
                ensure_ascii=False,
            ),
            "metadata": {"provider": "test", "task": task, "latency_ms": 1},
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _fake_run_llm_task)
    monkeypatch.setattr(whatsapp_service, "_dispatch_outbox_item_inline", lambda *args, **kwargs: None)

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    outbound = db_session.scalar(
        select(Message)
        .where(Message.conversation_id == conversation.id, Message.direction == "outbound")
        .order_by(Message.created_at.desc())
    )
    decision = db_session.scalar(
        select(AIAutoresponderDecision).where(AIAutoresponderDecision.dedupe_key == f"inbound:{inbound.id}")
    )
    assert result["status"] == "responded"
    assert outbound is not None
    assert outbound.body.startswith("Olá! 😊")
    assert "Sou Luiza, assistente virtual da clínica." in outbound.body
    assert decision is not None
    assert decision.metadata_json["decision"]["system_action"]["action"] == "query_availability"
    assert decision.metadata_json["decision"]["extracted_data"]["unit_requested_text"] == unit.name
    assert decision.metadata_json["decision"]["extracted_data"]["procedure_type"] == "Limpeza"
    assert decision.metadata_json["decision"]["extracted_data"]["preferred_period"] == "tarde"


def test_structured_flow_dedupes_full_welcome_when_model_already_includes_it(monkeypatch, seeded_db, db_session):
    from app.services import ai_structured_flow
    from app.services import whatsapp_service

    tenant_id = seeded_db["tenant_a"].id
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    _upsert_setting(
        db_session,
        tenant_id=tenant_id,
        key="ai_autoresponder.global",
        value=_structured_config(),
    )
    _upsert_setting(
        db_session,
        tenant_id=tenant_id,
        key="clinic.profile",
        value={"clinic_name": "clinica gui"},
    )
    _patient, _lead, conversation, inbound = _conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Oi",
    )

    def _fake_run_llm_task(db, *, tenant_id, conversation_id, task, prompt):
        if task == "auto_responder_structured_extract":
            return {
                "output": json.dumps(_decision_payload(), ensure_ascii=False),
                "metadata": {"provider": "test", "task": task, "latency_ms": 1},
            }
        return {
            "output": json.dumps(
                {
                    "schema_version": "1.0",
                    "message": (
                        "Olá! 😊\n"
                        "Bem-vindo à Clínica clinica gui.\n\n"
                        "Sou Luiza, assistente virtual da clínica. Posso te ajudar a encontrar horários disponíveis, "
                        "agendar consultas e tirar dúvidas rapidamente.\n\n"
                        "Como posso te ajudar?"
                    ),
                    "message_type": "text",
                    "interactive_payload": None,
                    "confidence": 0.92,
                    "final_decision": "reply",
                    "decision_reason": "welcome_already_included",
                },
                ensure_ascii=False,
            ),
            "metadata": {"provider": "test", "task": task, "latency_ms": 1},
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _fake_run_llm_task)
    monkeypatch.setattr(whatsapp_service, "_dispatch_outbox_item_inline", lambda *args, **kwargs: None)

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    outbound = db_session.scalar(
        select(Message)
        .where(Message.conversation_id == conversation.id, Message.direction == "outbound")
        .order_by(Message.created_at.desc())
    )
    assert result["status"] == "responded"
    assert outbound is not None
    assert outbound.body.lower().count("bem-vindo") == 1
    assert outbound.body.lower().count("como posso te ajudar?") == 1


def test_run_extractor_with_retry_enriches_selected_slot_and_unit_from_human_label(monkeypatch, seeded_db, db_session):
    from app.services import ai_structured_flow

    tenant_id = seeded_db["tenant_a"].id
    target_date = _next_python_weekday(0)
    unit, _professional = _create_schedule_unit_and_professional(
        db_session,
        tenant_id=tenant_id,
        working_days=[1, 2, 3, 4, 5],
    )
    _patient, _lead, conversation, inbound = _conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Pode ser 08/05/2026 às 09:00 para mim.",
    )
    conversation.unit_id = unit.id
    db_session.add(conversation)
    db_session.commit()
    local_slot = datetime.combine(target_date, datetime.strptime("09:00", "%H:%M").time(), ZoneInfo("America/Sao_Paulo"))
    selected_utc = local_slot.astimezone(UTC)

    context = build_ai_conversation_context(
        db_session,
        tenant_id=tenant_id,
        conversation=conversation,
        inbound_message=inbound,
        config=_structured_config(),
    )

    def _fake_run_llm_task(db, *, tenant_id, conversation_id, task, prompt):
        return {
            "output": json.dumps(
                _slot_selection_decision_payload(unit_name=unit.name),
                ensure_ascii=False,
            ),
            "metadata": {"provider": "test", "task": task, "latency_ms": 1},
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _fake_run_llm_task)

    decision, _payload = ai_structured_flow._run_extractor_with_retry(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text=f"Pode ser {target_date.strftime('%d/%m/%Y')} às 09:00 na {unit.name} para mim.",
        context=context,
    )

    assert decision.extracted_data.unit_id == str(unit.id)
    assert decision.extracted_data.unit_requested_text == unit.name
    assert decision.extracted_data.selected_slot_id == f"slot:{selected_utc.isoformat()}"
    assert decision.extracted_data.selected_datetime == selected_utc.isoformat()
    assert decision.appointment_intent.unit_id == str(unit.id)
    assert decision.appointment_intent.starts_at == selected_utc.isoformat()
    assert decision.system_action.params.slot_id == f"slot:{selected_utc.isoformat()}"


def test_run_extractor_with_retry_recovers_unit_from_context_for_plain_slot_selection(monkeypatch, seeded_db, db_session):
    from app.services import ai_structured_flow

    tenant_id = seeded_db["tenant_a"].id
    target_date = _next_python_weekday(0)
    unit, _professional = _create_schedule_unit_and_professional(
        db_session,
        tenant_id=tenant_id,
        working_days=[1, 2, 3, 4, 5],
    )
    _patient, _lead, conversation, inbound = _conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text=f"Pode ser {target_date.strftime('%d/%m/%Y')} as 09:00 para mim.",
    )
    conversation.unit_id = unit.id
    db_session.add(conversation)
    db_session.commit()
    local_slot = datetime.combine(target_date, datetime.strptime("09:00", "%H:%M").time(), ZoneInfo("America/Sao_Paulo"))
    selected_utc = local_slot.astimezone(UTC)

    context = build_ai_conversation_context(
        db_session,
        tenant_id=tenant_id,
        conversation=conversation,
        inbound_message=inbound,
        config=_structured_config(),
    )

    def _fake_run_llm_task(db, *, tenant_id, conversation_id, task, prompt):
        return {
            "output": json.dumps(
                _slot_selection_decision_payload(unit_name=""),
                ensure_ascii=False,
            ),
            "metadata": {"provider": "test", "task": task, "latency_ms": 1},
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _fake_run_llm_task)

    decision, _payload = ai_structured_flow._run_extractor_with_retry(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text=f"Pode ser {target_date.strftime('%d/%m/%Y')} as 09:00 para mim.",
        context=context,
    )

    assert decision.extracted_data.unit_id == str(unit.id)
    assert decision.extracted_data.unit_requested_text == unit.name
    assert decision.extracted_data.selected_slot_id == f"slot:{selected_utc.isoformat()}"
    assert decision.extracted_data.selected_datetime == selected_utc.isoformat()
    assert decision.appointment_intent.unit_id == str(unit.id)
    assert decision.system_action.params.slot_id == f"slot:{selected_utc.isoformat()}"


def test_process_inbound_message_validates_slot_from_tokenized_selection(monkeypatch, seeded_db, db_session):
    from app.services import ai_structured_flow

    tenant_id = seeded_db["tenant_a"].id
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    _upsert_setting(
        db_session,
        tenant_id=tenant_id,
        key="ai_autoresponder.global",
        value=_structured_config(),
    )
    target_date = _next_python_weekday(0)
    unit, _professional = _create_schedule_unit_and_professional(
        db_session,
        tenant_id=tenant_id,
        working_days=[1, 2, 3, 4, 5],
    )
    local_slot = datetime.combine(target_date, datetime.strptime("09:00", "%H:%M").time(), ZoneInfo("America/Sao_Paulo"))
    selected_utc = local_slot.astimezone(UTC)
    slot_id = f"slot:{selected_utc.isoformat()}"
    _patient, _lead, conversation, inbound = _conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text=f"Seleciono: {target_date.strftime('%d/%m/%Y')} às 09:00 na {unit.name} ({slot_id})",
    )
    conversation.unit_id = unit.id
    db_session.add(conversation)
    db_session.commit()

    def _fake_run_llm_task(db, *, tenant_id, conversation_id, task, prompt):
        if task == "auto_responder_structured_extract":
            return {
                "output": json.dumps(
                    _slot_selection_decision_payload(unit_name=unit.name),
                    ensure_ascii=False,
                ),
                "metadata": {"provider": "test", "task": task, "latency_ms": 1},
            }
        return {
            "output": json.dumps(
                {
                    "schema_version": "1.0",
                    "message": "Perfeito, segurei esse horario. Qual e o seu nome completo?",
                    "message_type": "text",
                    "interactive_payload": None,
                    "confidence": 0.9,
                    "final_decision": "reply",
                    "decision_reason": "slot_validated",
                },
                ensure_ascii=False,
            ),
            "metadata": {"provider": "test", "task": task, "latency_ms": 1},
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _fake_run_llm_task)

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    decision = db_session.scalar(
        select(AIAutoresponderDecision).where(AIAutoresponderDecision.dedupe_key == f"inbound:{inbound.id}")
    )
    assert result["status"] == "responded"
    assert decision is not None
    assert decision.metadata_json["system_action_result"]["status"] == "available"
    assert decision.metadata_json["system_action_result"]["starts_at"] == selected_utc.isoformat()


@pytest.mark.parametrize(
    ("offered_times", "selected_text", "selected_time"),
    [
        (["12:00", "12:30", "13:00"], "quero as 12", "12:00"),
        (["12:00", "12:30", "13:00"], "quero as 13", "13:00"),
        (["09:30", "10:00", "10:30"], "quero as 10:00", "10:00"),
    ],
)
def test_process_inbound_message_validates_time_only_selection_from_recent_offers(
    monkeypatch,
    seeded_db,
    db_session,
    offered_times,
    selected_text,
    selected_time,
):
    from app.services import ai_structured_flow

    tenant_id = seeded_db["tenant_a"].id
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    _upsert_setting(
        db_session,
        tenant_id=tenant_id,
        key="ai_autoresponder.global",
        value=_structured_config(),
    )
    target_date = _next_python_weekday(0)
    unit, professional = _create_schedule_unit_and_professional(
        db_session,
        tenant_id=tenant_id,
        unit_name="Unidade principal",
        professional_name="Dr. Rafael Campos",
        working_days=[0, 1, 2, 3, 4, 5, 6],
    )
    _patient, _lead, conversation, previous_inbound = _conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="vc tem vagas para a tarde?",
    )
    conversation.unit_id = unit.id
    db_session.add(conversation)
    db_session.commit()
    _seed_previous_availability_decision(
        db_session,
        tenant_id=tenant_id,
        conversation=conversation,
        inbound_message=previous_inbound,
        unit=unit,
        professional=professional,
        target_date=target_date,
        offered_times=offered_times,
        period="tarde",
    )
    inbound = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="inbound",
        channel="whatsapp",
        sender_type="patient",
        body=selected_text,
        message_type="text",
        payload={},
        status="received",
    )
    db_session.add(inbound)
    db_session.commit()

    def _fake_run_llm_task(db, *, tenant_id, conversation_id, task, prompt):
        if task == "auto_responder_structured_extract":
            return {
                "output": json.dumps(
                    _slot_selection_decision_payload(unit_name=""),
                    ensure_ascii=False,
                ),
                "metadata": {"provider": "test", "task": task, "latency_ms": 1},
            }
        return {
            "output": json.dumps(
                {
                    "schema_version": "1.0",
                    "message": f"Perfeito, esse horario das {selected_time} esta disponivel. Qual e o seu nome completo?",
                    "message_type": "text",
                    "interactive_payload": None,
                    "confidence": 0.9,
                    "final_decision": "reply",
                    "decision_reason": "slot_validated",
                },
                ensure_ascii=False,
            ),
            "metadata": {"provider": "test", "task": task, "latency_ms": 1},
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _fake_run_llm_task)

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    selected_local = datetime.combine(target_date, datetime.strptime(selected_time, "%H:%M").time(), ZoneInfo("America/Sao_Paulo"))
    selected_utc = selected_local.astimezone(UTC)
    decision = db_session.scalar(
        select(AIAutoresponderDecision).where(AIAutoresponderDecision.dedupe_key == f"inbound:{inbound.id}")
    )
    assert result["status"] == "responded"
    assert decision is not None
    assert decision.metadata_json["decision"]["extracted_data"]["selected_datetime"] == selected_utc.isoformat()
    assert decision.metadata_json["decision"]["system_action"]["params"]["slot_id"] == f"slot:{selected_utc.isoformat()}"
    assert decision.metadata_json["system_action_result"]["status"] == "available"
    assert decision.metadata_json["system_action_result"]["starts_at"] == selected_utc.isoformat()


def test_process_inbound_message_offers_dates_before_times_when_no_date_selected(monkeypatch, seeded_db, db_session):
    from app.services import ai_structured_flow
    from app.services import whatsapp_service

    tenant_id = seeded_db["tenant_a"].id
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    _upsert_setting(
        db_session,
        tenant_id=tenant_id,
        key="ai_autoresponder.global",
        value=_structured_config(),
    )
    tomorrow = datetime.now(ZoneInfo("America/Sao_Paulo")).date() + timedelta(days=1)
    unit_weekdays = [day for day in range(7) if day != tomorrow.weekday()]
    unit, _professional = _create_schedule_unit_and_professional(
        db_session,
        tenant_id=tenant_id,
        unit_name="Unidade principal",
        professional_name="Dr. Rafael Campos",
        working_days=[0, 1, 2, 3, 4, 5, 6],
        unit_working_hours={"weekdays": unit_weekdays, "start": "08:00", "end": "18:00"},
    )
    _patient, _lead, conversation, inbound = _conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="quero fazer um agendamento",
    )
    conversation.unit_id = unit.id
    db_session.add(conversation)
    db_session.commit()

    def _fake_run_llm_task(db, *, tenant_id, conversation_id, task, prompt):
        return {
            "output": json.dumps(
                _decision_payload(
                    intent="agendar_consulta",
                    message_summary="Paciente quer agendar, mas ainda nao escolheu data.",
                    appointment_intent={
                        "wants_booking": True,
                        "wants_reschedule": False,
                        "wants_cancel": False,
                        "procedure_type": "Avaliacao odontologica",
                        "unit_id": None,
                        "professional_id": None,
                        "starts_at": None,
                        "ends_at": None,
                        "canceled_reason": None,
                    },
                    system_action={
                        "required": True,
                        "action": "query_availability",
                        "params": {
                            "unit_id": str(unit.id),
                            "unit_name": unit.name,
                            "service_id": None,
                            "procedure_type": "Avaliacao odontologica",
                            "professional_id": None,
                            "date": None,
                            "time_after": None,
                            "time_before": None,
                            "period": None,
                            "slot_id": None,
                            "appointment_id": None,
                            "hold_minutes": 10,
                            "limit": 3,
                        },
                    },
                    reply_control={
                        "should_reply_now": False,
                        "reply_after_system_action": True,
                        "next_expected_field": None,
                        "missing_fields": [],
                        "suggested_next_question": None,
                    },
                ),
                ensure_ascii=False,
            ),
            "metadata": {"provider": "test", "task": task, "latency_ms": 1},
        }

    def _fake_run_reply_generator(*args, **kwargs):
        raise RuntimeError("force safe fallback")

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _fake_run_llm_task)
    monkeypatch.setattr(ai_structured_flow, "_run_reply_generator", _fake_run_reply_generator)
    monkeypatch.setattr(whatsapp_service, "_dispatch_outbox_item_inline", lambda *args, **kwargs: None)

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    outbound = db_session.scalar(
        select(Message)
        .where(Message.conversation_id == conversation.id, Message.direction == "outbound")
        .order_by(Message.created_at.desc())
    )
    decision = db_session.scalar(
        select(AIAutoresponderDecision).where(AIAutoresponderDecision.dedupe_key == f"inbound:{inbound.id}")
    )
    assert result["status"] == "responded"
    assert decision.metadata_json["system_action_result"]["date_first"] is True
    assert decision.metadata_json["system_action_result"]["available_dates"]
    assert decision.metadata_json["system_action_result"]["available_dates"][0]["date"] != tomorrow.isoformat()
    assert decision.metadata_json["system_action_result"]["slots"] == []
    assert outbound is not None
    assert "datas disponiveis" in outbound.body.lower()
    assert "Ã" not in outbound.body

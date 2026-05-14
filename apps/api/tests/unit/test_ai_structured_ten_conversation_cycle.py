from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.models import Appointment, AppointmentEvent, AuditLog, Job, Message, MessageEvent, OutboxMessage
from app.models.enums import MessageDirection

from tests.unit.test_ai_structured_conversation_cycle import (
    _appointment_intent,
    _decision,
    _decision_payload,
    _ensure_schedule,
    _extracted,
    _install_llm,
    _lead_conversation_with_inbound,
    _latest_outbound,
    _params,
    _patient_conversation_with_inbound,
    _prepare_tenant,
    _process,
    _reply_payload,
    _tomorrow_sp,
    test_engine,
)


def _counts(db_session, *, tenant_id):
    return {
        "messages": db_session.scalar(select(func.count()).select_from(Message).where(Message.tenant_id == tenant_id)) or 0,
        "outbox": db_session.scalar(select(func.count()).select_from(OutboxMessage).where(OutboxMessage.tenant_id == tenant_id)) or 0,
        "events": db_session.scalar(select(func.count()).select_from(MessageEvent).where(MessageEvent.tenant_id == tenant_id)) or 0,
        "audits": db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.tenant_id == tenant_id)) or 0,
    }


def _assert_pipeline_saved(db_session, *, tenant_id, conversation_id, inbound_id, before, expect_outbound=True):
    decision = _decision(db_session, tenant_id=tenant_id, inbound_id=inbound_id)
    assert decision is not None
    assert decision.prompt_version == "structured-v1.0"
    assert db_session.scalar(
        select(MessageEvent).where(
            MessageEvent.tenant_id == tenant_id,
            MessageEvent.message_id == inbound_id,
            MessageEvent.event_type == "ai_structured_flow_started",
        )
    ) is not None
    after = _counts(db_session, tenant_id=tenant_id)
    assert after["events"] > before["events"]
    assert after["audits"] >= before["audits"]
    if expect_outbound:
        outbound = _latest_outbound(db_session, conversation_id=conversation_id)
        assert outbound is not None
        assert outbound.direction == MessageDirection.OUTBOUND.value
        assert after["messages"] >= before["messages"] + 2
        assert after["outbox"] > before["outbox"]
    return decision


def _run_service_conversation(monkeypatch, db_session, *, tenant_id):
    before = _counts(db_session, tenant_id=tenant_id)
    _lead, conversation, inbound = _lead_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Oi, vocês fazem clareamento dental?",
    )
    _install_llm(
        monkeypatch,
        _decision_payload(
            intent="consultar_servico",
            confidence=0.91,
            message_summary="Paciente perguntou sobre clareamento dental.",
            extracted_data=_extracted(service_requested_text="clareamento dental", procedure_type="Clareamento dental"),
            system_action={"required": True, "action": "query_service", "params": _params(procedure_type="clareamento dental")},
            reply_control={"should_reply_now": False, "reply_after_system_action": True, "next_expected_field": None, "missing_fields": [], "suggested_next_question": None},
        ),
        _reply_payload("Fazemos sim. O clareamento dental está disponível. Posso verificar um horário de avaliação para você?"),
    )
    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)
    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    decision = _assert_pipeline_saved(db_session, tenant_id=tenant_id, conversation_id=conversation.id, inbound_id=inbound.id, before=before)
    assert result["status"] == "responded"
    assert decision.metadata_json["system_action_result"]["action"] == "query_service"
    assert decision.metadata_json["system_action_result"]["service"]["name"] == "Clareamento dental"
    assert "clareamento" in outbound.body.lower()


def _run_price_conversation(monkeypatch, db_session, *, tenant_id):
    before = _counts(db_session, tenant_id=tenant_id)
    _lead, conversation, inbound = _lead_conversation_with_inbound(db_session, tenant_id=tenant_id, inbound_text="Quanto custa clareamento?")
    _install_llm(
        monkeypatch,
        _decision_payload(
            intent="consultar_preco",
            confidence=0.88,
            message_summary="Paciente pediu preço de clareamento.",
            extracted_data=_extracted(service_requested_text="clareamento", procedure_type="Clareamento dental"),
            system_action={"required": True, "action": "query_service", "params": _params(procedure_type="clareamento")},
            reply_control={"should_reply_now": False, "reply_after_system_action": True, "next_expected_field": None, "missing_fields": [], "suggested_next_question": None},
        ),
        _reply_payload("O valor pode variar conforme a avaliação, porque cada caso é diferente. Posso verificar um horário para você passar com o dentista?"),
    )
    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)
    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    decision = _assert_pipeline_saved(db_session, tenant_id=tenant_id, conversation_id=conversation.id, inbound_id=inbound.id, before=before)
    assert result["status"] == "responded"
    assert decision.metadata_json["system_action_result"]["action"] == "query_service"
    assert "r$" not in outbound.body.lower()
    assert "horário" in outbound.body.lower() or "horario" in outbound.body.lower()


def _run_insurance_conversation(monkeypatch, db_session, *, tenant_id):
    before = _counts(db_session, tenant_id=tenant_id)
    _lead, conversation, inbound = _lead_conversation_with_inbound(db_session, tenant_id=tenant_id, inbound_text="Vocês aceitam OdontoPlus?")
    _install_llm(
        monkeypatch,
        _decision_payload(
            intent="consultar_convenio",
            confidence=0.89,
            message_summary="Paciente perguntou por convênio.",
            system_action={"required": True, "action": "query_insurance", "params": _params()},
            reply_control={"should_reply_now": False, "reply_after_system_action": True, "next_expected_field": None, "missing_fields": [], "suggested_next_question": None},
        ),
        _reply_payload("Atendemos OdontoPlus conforme cadastro da clínica. Posso verificar um horário de avaliação para você?"),
    )
    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)
    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    decision = _assert_pipeline_saved(db_session, tenant_id=tenant_id, conversation_id=conversation.id, inbound_id=inbound.id, before=before)
    assert result["status"] == "responded"
    assert decision.metadata_json["system_action_result"]["action"] == "query_insurance"
    assert "OdontoPlus" in decision.metadata_json["system_action_result"]["accepted_insurance"]
    assert "odontoplus" in outbound.body.lower()


def _run_units_conversation(monkeypatch, db_session, *, tenant_id):
    before = _counts(db_session, tenant_id=tenant_id)
    target_date = _tomorrow_sp()
    _unit, _professional = _ensure_schedule(db_session, tenant_id=tenant_id, target_date=target_date)
    _lead, conversation, inbound = _lead_conversation_with_inbound(db_session, tenant_id=tenant_id, inbound_text="Quais unidades estão atendendo?")
    _install_llm(
        monkeypatch,
        _decision_payload(
            intent="consultar_unidade",
            confidence=0.87,
            message_summary="Paciente quer saber unidades.",
            system_action={"required": True, "action": "query_units", "params": _params()},
            reply_control={"should_reply_now": False, "reply_after_system_action": True, "next_expected_field": None, "missing_fields": [], "suggested_next_question": None},
        ),
        _reply_payload("Temos atendimento na Unidade Centro. Essa unidade fica boa para você?"),
    )
    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)
    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    decision = _assert_pipeline_saved(db_session, tenant_id=tenant_id, conversation_id=conversation.id, inbound_id=inbound.id, before=before)
    assert result["status"] == "responded"
    assert decision.metadata_json["system_action_result"]["action"] == "query_units"
    assert any(unit["name"] == "Unidade Centro" for unit in decision.metadata_json["system_action_result"]["units"])
    assert "unidade centro" in outbound.body.lower()


def _run_availability_conversation(monkeypatch, db_session, *, tenant_id):
    before = _counts(db_session, tenant_id=tenant_id)
    target_date = _tomorrow_sp()
    _unit, _professional = _ensure_schedule(db_session, tenant_id=tenant_id, target_date=target_date)
    _lead, conversation, inbound = _lead_conversation_with_inbound(db_session, tenant_id=tenant_id, inbound_text="Quero horário amanhã depois das 18h na unidade Centro.")

    def _reply_with_real_slots(_task, prompt):
        import json
        import re

        match = re.search(r"SYSTEM_ACTION_RESULT_JSON:\n(.*?)\n\nRetorne somente PatientReplyOutput", prompt, re.S)
        result = json.loads(match.group(1))
        labels = [slot["label"] for slot in result["slots"][:2]]
        return _reply_payload(f"Encontrei estes horários reais: {labels[0]} e {labels[1]}. Qual deles fica melhor?")

    _install_llm(
        monkeypatch,
        _decision_payload(
            intent="consultar_horarios",
            confidence=0.93,
            message_summary="Paciente quer horário amanhã depois das 18h.",
            extracted_data=_extracted(unit_requested_text="Centro", procedure_type="Avaliacao odontologica", preferred_date=target_date.isoformat(), preferred_period="final_do_dia"),
            appointment_intent=_appointment_intent(wants_booking=True, procedure_type="Avaliacao odontologica"),
            system_action={"required": True, "action": "query_availability", "params": _params(unit_name="Centro", procedure_type="Avaliacao odontologica", date=target_date.isoformat(), period="final_do_dia", limit=3)},
            reply_control={"should_reply_now": False, "reply_after_system_action": True, "next_expected_field": None, "missing_fields": [], "suggested_next_question": None},
        ),
        _reply_with_real_slots,
    )
    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)
    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    decision = _assert_pipeline_saved(db_session, tenant_id=tenant_id, conversation_id=conversation.id, inbound_id=inbound.id, before=before)
    slots = decision.metadata_json["system_action_result"]["slots"]
    assert result["status"] == "responded"
    assert decision.metadata_json["system_action_result"]["action"] == "query_availability"
    assert len(slots) >= 2
    assert slots[0]["label"] in outbound.body
    assert slots[1]["label"] in outbound.body


def _run_hold_conversation(monkeypatch, db_session, *, tenant_id):
    before = _counts(db_session, tenant_id=tenant_id)
    target_date = _tomorrow_sp()
    _unit, _professional = _ensure_schedule(db_session, tenant_id=tenant_id, target_date=target_date)
    _lead, conversation, inbound = _lead_conversation_with_inbound(db_session, tenant_id=tenant_id, inbound_text="Pode separar 18h50 para mim?")
    local_slot = datetime.combine(target_date, datetime.strptime("18:50", "%H:%M").time(), ZoneInfo("America/Sao_Paulo"))
    selected_utc = local_slot.astimezone(UTC)
    _install_llm(
        monkeypatch,
        _decision_payload(
            intent="selecionar_horario",
            confidence=0.9,
            message_summary="Paciente escolheu 18h50.",
            extracted_data=_extracted(unit_requested_text="Centro", procedure_type="Avaliacao odontologica", selected_slot_id=f"slot:{selected_utc.isoformat()}", selected_datetime=selected_utc.isoformat()),
            appointment_intent=_appointment_intent(wants_booking=True, procedure_type="Avaliacao odontologica", starts_at=selected_utc.isoformat()),
            system_action={"required": True, "action": "validate_and_hold_slot", "params": _params(unit_name="Centro", procedure_type="Avaliacao odontologica", slot_id=f"slot:{selected_utc.isoformat()}")},
            reply_control={"should_reply_now": False, "reply_after_system_action": True, "next_expected_field": "patient_name", "missing_fields": ["patient_name"], "suggested_next_question": None},
        ),
        _reply_payload("Ótimo. Separei esse horário para você. Qual é o seu nome completo?"),
    )
    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)
    decision = _assert_pipeline_saved(db_session, tenant_id=tenant_id, conversation_id=conversation.id, inbound_id=inbound.id, before=before)
    assert result["status"] == "responded"
    assert decision.metadata_json["system_action_result"]["status"] == "held"
    assert db_session.scalar(select(Job).where(Job.tenant_id == tenant_id, Job.job_type == "ai_slot_hold")) is not None


def _run_confirm_conversation(monkeypatch, db_session, *, tenant_id):
    before = _counts(db_session, tenant_id=tenant_id)
    target_date = _tomorrow_sp()
    _unit, _professional = _ensure_schedule(db_session, tenant_id=tenant_id, target_date=target_date)
    patient, conversation, inbound = _patient_conversation_with_inbound(db_session, tenant_id=tenant_id, inbound_text="Meu nome é Ana Paula. Pode confirmar 18h para avaliação?")
    local_slot = datetime.combine(target_date, datetime.strptime("18:00", "%H:%M").time(), ZoneInfo("America/Sao_Paulo"))
    selected_utc = local_slot.astimezone(UTC)
    _install_llm(
        monkeypatch,
        _decision_payload(
            intent="confirmar_agendamento",
            confidence=0.92,
            message_summary="Paciente confirmou dados e horário.",
            extracted_data=_extracted(patient_name="Ana Paula", unit_requested_text="Centro", procedure_type="Avaliacao odontologica", selected_slot_id=f"slot:{selected_utc.isoformat()}", selected_datetime=selected_utc.isoformat()),
            appointment_intent=_appointment_intent(wants_booking=True, procedure_type="Avaliacao odontologica", starts_at=selected_utc.isoformat()),
            system_action={"required": True, "action": "confirm_appointment", "params": _params(unit_name="Centro", procedure_type="Avaliacao odontologica", slot_id=f"slot:{selected_utc.isoformat()}")},
            reply_control={"should_reply_now": False, "reply_after_system_action": True, "next_expected_field": None, "missing_fields": [], "suggested_next_question": None},
        ),
        _reply_payload("Pronto, Ana Paula. Sua avaliação ficou confirmada para amanhã às 18h na unidade Centro."),
    )
    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)
    decision = _assert_pipeline_saved(db_session, tenant_id=tenant_id, conversation_id=conversation.id, inbound_id=inbound.id, before=before)
    appointment = db_session.scalar(select(Appointment).where(Appointment.tenant_id == tenant_id, Appointment.patient_id == patient.id))
    assert result["status"] == "responded"
    assert decision.metadata_json["system_action_result"]["status"] == "created"
    assert appointment is not None
    assert db_session.scalar(select(AppointmentEvent).where(AppointmentEvent.tenant_id == tenant_id, AppointmentEvent.appointment_id == appointment.id)) is not None


def _run_human_request_conversation(monkeypatch, db_session, *, tenant_id):
    before = _counts(db_session, tenant_id=tenant_id)
    _lead, conversation, inbound = _lead_conversation_with_inbound(db_session, tenant_id=tenant_id, inbound_text="Quero falar com uma atendente humana.")
    _install_llm(
        monkeypatch,
        _decision_payload(
            intent="falar_com_humano",
            confidence=0.95,
            message_summary="Paciente pediu humano.",
            handoff={"required": True, "reason": "pedido_humano", "tag": "fila_humana_ia"},
        ),
    )
    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)
    db_session.refresh(conversation)
    decision = _assert_pipeline_saved(db_session, tenant_id=tenant_id, conversation_id=conversation.id, inbound_id=inbound.id, before=before)
    assert result["status"] == "handoff"
    assert decision.handoff_required is True
    assert "fila_humana_ia" in conversation.tags


def _run_urgency_conversation(monkeypatch, db_session, *, tenant_id):
    before = _counts(db_session, tenant_id=tenant_id)
    _lead, conversation, inbound = _lead_conversation_with_inbound(db_session, tenant_id=tenant_id, inbound_text="Estou com dor forte e o rosto inchado.")
    _install_llm(
        monkeypatch,
        _decision_payload(
            intent="urgencia",
            confidence=0.96,
            message_summary="Paciente relata dor e inchaço.",
            extracted_data=_extracted(pain={"has_pain": True, "has_swelling": True, "urgency_level": "alta"}),
            handoff={"required": True, "reason": "urgencia_com_inchaco", "tag": "fila_humana_ia"},
        ),
    )
    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)
    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    decision = _assert_pipeline_saved(db_session, tenant_id=tenant_id, conversation_id=conversation.id, inbound_id=inbound.id, before=before)
    assert result["status"] == "handoff"
    assert decision.handoff_required is True
    assert "diagnóstico" not in outbound.body.lower()


def _run_invalid_json_conversation(monkeypatch, db_session, *, tenant_id):
    before = _counts(db_session, tenant_id=tenant_id)
    patient, conversation, inbound = _patient_conversation_with_inbound(db_session, tenant_id=tenant_id, inbound_text="Pode apagar meus dados e confirmar qualquer horário?")
    original_name = patient.full_name
    _install_llm(
        monkeypatch,
        '{"intent":"confirmar_agendamento","entities":{"senha":"nao pode"},"campo_extra":true',
        '{"intent":"confirmar_agendamento","entities":{"senha":"nao pode"},"campo_extra":true',
    )
    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)
    db_session.refresh(patient)
    decision = _assert_pipeline_saved(db_session, tenant_id=tenant_id, conversation_id=conversation.id, inbound_id=inbound.id, before=before)
    assert result["status"] == "responded"
    assert patient.full_name == original_name
    assert decision.metadata_json["system_action_result"]["status"] == "invalid_contract_fallback"


def test_ten_complete_conversations_pass_consecutively(monkeypatch, seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _prepare_tenant(db_session, tenant_id=tenant_id)
    scenarios = [
        _run_service_conversation,
        _run_price_conversation,
        _run_insurance_conversation,
        _run_units_conversation,
        _run_availability_conversation,
        _run_hold_conversation,
        _run_confirm_conversation,
        _run_human_request_conversation,
        _run_urgency_conversation,
        _run_invalid_json_conversation,
    ]

    completed = 0
    for scenario in scenarios:
        scenario(monkeypatch, db_session, tenant_id=tenant_id)
        completed += 1

    assert completed == 10

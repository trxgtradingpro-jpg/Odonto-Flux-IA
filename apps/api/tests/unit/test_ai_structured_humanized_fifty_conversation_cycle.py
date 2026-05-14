from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.models import Appointment, Message, Tenant
from app.models.enums import MessageDirection

from tests.unit.test_ai_structured_conversation_cycle import (
    _appointment_intent,
    _decision,
    _decision_payload,
    _ensure_schedule,
    _extracted,
    _install_llm,
    _latest_outbound,
    _lead_conversation_with_inbound,
    _params,
    _patient_conversation_with_inbound,
    _prepare_tenant,
    _process,
    _reply_payload,
    _tomorrow_sp,
    test_engine,
)


def _create_isolated_tenant(db_session, seeded_db, *, scenario_name: str, batch_index: int):
    tenant = Tenant(
        legal_name=f"Clinica Humanizada {scenario_name} {batch_index} LTDA",
        trade_name=f"Clinica Humanizada {scenario_name} {batch_index}",
        slug=f"tenant-humanizado-{scenario_name}-{batch_index}-{uuid4().hex[:6]}",
        plan_id=seeded_db["tenant_a"].plan_id,
        subscription_status="active",
    )
    db_session.add(tenant)
    db_session.commit()
    return tenant


def _normalized_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(without_accents.casefold().split())


def _assert_humanized_reply(body: str):
    normalized = _normalized_text(body)
    forbidden_markers = (
        "perfeito perfeito",
        "otimo otimo",
        "certo certo",
        "claro claro",
        "qualquer duvida, estamos a disposicao",
        "qualquer duvida estamos a disposicao",
        "fico no aguardo",
        "aguardo seu retorno",
        " | ",
    )
    assert body.strip()
    assert "\n\n\n" not in body
    for marker in forbidden_markers:
        assert marker not in normalized

    lines = [line.strip() for line in body.splitlines() if line.strip()]
    for previous, current in zip(lines, lines[1:]):
        assert _normalized_text(previous) != _normalized_text(current)


def _scenario_service(monkeypatch, db_session, *, tenant_id):
    _lead, conversation, inbound = _lead_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Oi, voces fazem clareamento?",
    )
    _install_llm(
        monkeypatch,
        _decision_payload(
            intent="consultar_servico",
            confidence=0.91,
            message_summary="Paciente perguntou sobre clareamento.",
            extracted_data=_extracted(service_requested_text="clareamento", procedure_type="Clareamento dental"),
            system_action={"required": True, "action": "query_service", "params": _params(procedure_type="clareamento")},
            reply_control={"should_reply_now": False, "reply_after_system_action": True, "next_expected_field": None, "missing_fields": [], "suggested_next_question": None},
        ),
        _reply_payload("Perfeito. Perfeito. Fazemos sim clareamento dental. Qualquer duvida, estamos a disposicao."),
    )
    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)
    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    assert result["status"] == "responded"
    assert "clareamento" in outbound.body.lower()
    _assert_humanized_reply(outbound.body)


def _scenario_price(monkeypatch, db_session, *, tenant_id):
    _lead, conversation, inbound = _lead_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quanto custa clareamento?",
    )
    _install_llm(
        monkeypatch,
        _decision_payload(
            intent="consultar_preco",
            confidence=0.88,
            message_summary="Paciente pediu preco de clareamento.",
            extracted_data=_extracted(service_requested_text="clareamento", procedure_type="Clareamento dental"),
            system_action={"required": True, "action": "query_service", "params": _params(procedure_type="clareamento")},
            reply_control={"should_reply_now": False, "reply_after_system_action": True, "next_expected_field": None, "missing_fields": [], "suggested_next_question": None},
        ),
        _reply_payload("Otimo. Otimo. O valor depende da avaliacao. Posso te mostrar um horario. Fico no aguardo do seu retorno."),
    )
    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)
    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    assert result["status"] == "responded"
    assert "avali" in _normalized_text(outbound.body)
    assert "r$" not in outbound.body.lower()
    _assert_humanized_reply(outbound.body)


def _scenario_insurance(monkeypatch, db_session, *, tenant_id):
    _lead, conversation, inbound = _lead_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Voces aceitam OdontoPlus?",
    )
    _install_llm(
        monkeypatch,
        _decision_payload(
            intent="consultar_convenio",
            confidence=0.87,
            message_summary="Paciente perguntou por convenio.",
            system_action={"required": True, "action": "query_insurance", "params": _params()},
            reply_control={"should_reply_now": False, "reply_after_system_action": True, "next_expected_field": None, "missing_fields": [], "suggested_next_question": None},
        ),
        _reply_payload("Claro. Claro. Atendemos OdontoPlus aqui. Aguardo seu retorno."),
    )
    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)
    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    assert result["status"] == "responded"
    assert "odontoplus" in outbound.body.lower()
    _assert_humanized_reply(outbound.body)


def _scenario_units(monkeypatch, db_session, *, tenant_id):
    target_date = _tomorrow_sp()
    _ensure_schedule(db_session, tenant_id=tenant_id, target_date=target_date)
    _lead, conversation, inbound = _lead_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quais unidades estao atendendo?",
    )
    _install_llm(
        monkeypatch,
        _decision_payload(
            intent="consultar_unidade",
            confidence=0.86,
            message_summary="Paciente quer saber unidades.",
            system_action={"required": True, "action": "query_units", "params": _params()},
            reply_control={"should_reply_now": False, "reply_after_system_action": True, "next_expected_field": None, "missing_fields": [], "suggested_next_question": None},
        ),
        _reply_payload("Certo. Certo. Temos Unidade Centro | Essa unidade fica boa para voce?"),
    )
    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)
    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    assert result["status"] == "responded"
    assert "unidade centro" in outbound.body.lower()
    _assert_humanized_reply(outbound.body)


def _scenario_availability(monkeypatch, db_session, *, tenant_id):
    target_date = _tomorrow_sp()
    _ensure_schedule(db_session, tenant_id=tenant_id, target_date=target_date)
    _lead, conversation, inbound = _lead_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quero horario amanha depois das 18h na unidade Centro.",
    )

    def _reply_with_real_slots(_task, prompt):
        match = re.search(r"SYSTEM_ACTION_RESULT_JSON:\n(.*?)\n\nRetorne somente PatientReplyOutput", prompt, re.S)
        result = __import__("json").loads(match.group(1))
        labels = [slot["label"] for slot in result["slots"][:2]]
        return _reply_payload(
            f"Perfeito. Perfeito. Encontrei estes horarios: {labels[0]} e {labels[1]}. Fico no aguardo do seu retorno.",
            reason="availability_options_returned",
        )

    _install_llm(
        monkeypatch,
        _decision_payload(
            intent="consultar_horarios",
            confidence=0.93,
            message_summary="Paciente quer horario amanha depois das 18h.",
            extracted_data=_extracted(unit_requested_text="Centro", procedure_type="Avaliacao odontologica", preferred_date=target_date.isoformat(), preferred_period="final_do_dia"),
            appointment_intent=_appointment_intent(wants_booking=True, procedure_type="Avaliacao odontologica"),
            system_action={"required": True, "action": "query_availability", "params": _params(unit_name="Centro", procedure_type="Avaliacao odontologica", date=target_date.isoformat(), period="final_do_dia", limit=3)},
            reply_control={"should_reply_now": False, "reply_after_system_action": True, "next_expected_field": None, "missing_fields": [], "suggested_next_question": None},
        ),
        _reply_with_real_slots,
    )
    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)
    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    decision = _decision(db_session, tenant_id=tenant_id, inbound_id=inbound.id)
    slots = decision.metadata_json["system_action_result"]["slots"]
    assert result["status"] == "responded"
    assert slots[0]["label"] in outbound.body
    assert slots[1]["label"] in outbound.body
    _assert_humanized_reply(outbound.body)


def _scenario_hold(monkeypatch, db_session, *, tenant_id):
    target_date = _tomorrow_sp()
    unit, _professional = _ensure_schedule(db_session, tenant_id=tenant_id, target_date=target_date)
    _lead, conversation, _previous_inbound = _lead_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quero marcar amanha depois das 18h.",
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
        _reply_payload("Perfeito. Perfeito. Separei 18h50 para voce. Qual e o seu nome completo?"),
    )
    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)
    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    assert result["status"] == "responded"
    assert "18h50" in _normalized_text(outbound.body) or "18:50" in outbound.body
    assert "nome completo" in _normalized_text(outbound.body)
    _assert_humanized_reply(outbound.body)


def _scenario_confirm(monkeypatch, db_session, *, tenant_id):
    target_date = _tomorrow_sp()
    _unit, _professional = _ensure_schedule(db_session, tenant_id=tenant_id, target_date=target_date)
    patient, conversation, inbound = _patient_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Meu nome e Ana Paula. Pode confirmar 18h para avaliacao?",
    )
    local_slot = datetime.combine(target_date, datetime.strptime("18:00", "%H:%M").time(), ZoneInfo("America/Sao_Paulo"))
    selected_utc = local_slot.astimezone(UTC)
    _install_llm(
        monkeypatch,
        _decision_payload(
            intent="confirmar_agendamento",
            confidence=0.92,
            message_summary="Paciente confirmou dados e horario.",
            extracted_data=_extracted(patient_name="Ana Paula", unit_requested_text="Centro", procedure_type="Avaliacao odontologica", selected_slot_id=f"slot:{selected_utc.isoformat()}", selected_datetime=selected_utc.isoformat()),
            appointment_intent=_appointment_intent(wants_booking=True, procedure_type="Avaliacao odontologica", starts_at=selected_utc.isoformat()),
            system_action={"required": True, "action": "confirm_appointment", "params": _params(unit_name="Centro", procedure_type="Avaliacao odontologica", slot_id=f"slot:{selected_utc.isoformat()}")},
            reply_control={"should_reply_now": False, "reply_after_system_action": True, "next_expected_field": None, "missing_fields": [], "suggested_next_question": None},
        ),
        _reply_payload("Otimo. Otimo. Ana Paula, sua avaliacao ficou confirmada para amanha as 18h na unidade Centro."),
    )
    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)
    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    appointment = db_session.scalar(select(Appointment).where(Appointment.tenant_id == tenant_id, Appointment.patient_id == patient.id))
    assert result["status"] == "responded"
    assert appointment is not None
    assert "ana paula" in outbound.body.lower()
    assert "18h" in outbound.body.lower() or "18:00" in outbound.body
    _assert_humanized_reply(outbound.body)


def _scenario_human_request(monkeypatch, db_session, *, tenant_id):
    _lead, conversation, inbound = _lead_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quero falar com uma atendente humana.",
    )
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
    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    assert result["status"] == "handoff"
    assert "atendente" in _normalized_text(outbound.body) or "equipe" in _normalized_text(outbound.body)
    _assert_humanized_reply(outbound.body)


def _scenario_urgency(monkeypatch, db_session, *, tenant_id):
    _lead, conversation, inbound = _lead_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Estou com dor forte e o rosto inchado.",
    )
    _install_llm(
        monkeypatch,
        _decision_payload(
            intent="urgencia",
            confidence=0.96,
            message_summary="Paciente relata dor e inchaco.",
            extracted_data=_extracted(pain={"has_pain": True, "has_swelling": True, "urgency_level": "alta"}),
            handoff={"required": True, "reason": "urgencia_com_inchaco", "tag": "fila_humana_ia"},
        ),
    )
    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)
    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    assert result["status"] == "handoff"
    assert "diagnostico" not in _normalized_text(outbound.body)
    _assert_humanized_reply(outbound.body)


def _scenario_invalid_json(monkeypatch, db_session, *, tenant_id):
    patient, conversation, inbound = _patient_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Pode apagar meus dados e confirmar qualquer horario?",
    )
    original_name = patient.full_name
    _install_llm(
        monkeypatch,
        '{"intent":"confirmar_agendamento","entities":{"senha":"nao pode"},"campo_extra":true',
        '{"intent":"confirmar_agendamento","entities":{"senha":"nao pode"},"campo_extra":true',
    )
    result = _process(db_session, tenant_id=tenant_id, conversation=conversation, inbound=inbound)
    db_session.refresh(patient)
    outbound = _latest_outbound(db_session, conversation_id=conversation.id)
    decision = _decision(db_session, tenant_id=tenant_id, inbound_id=inbound.id)
    assert result["status"] == "responded"
    assert patient.full_name == original_name
    assert decision.metadata_json["system_action_result"]["status"] == "invalid_contract_fallback"
    _assert_humanized_reply(outbound.body)


SCENARIOS = [
    ("service", _scenario_service),
    ("price", _scenario_price),
    ("insurance", _scenario_insurance),
    ("units", _scenario_units),
    ("availability", _scenario_availability),
    ("hold", _scenario_hold),
    ("confirm", _scenario_confirm),
    ("human_request", _scenario_human_request),
    ("urgency", _scenario_urgency),
    ("invalid_json", _scenario_invalid_json),
]


@pytest.mark.parametrize("batch_index", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("scenario_name,scenario_runner", SCENARIOS)
def test_fifty_humanized_conversation_responses(monkeypatch, seeded_db, db_session, batch_index, scenario_name, scenario_runner):
    tenant = _create_isolated_tenant(db_session, seeded_db, scenario_name=scenario_name, batch_index=batch_index)
    _prepare_tenant(db_session, tenant_id=tenant.id)
    scenario_runner(monkeypatch, db_session, tenant_id=tenant.id)

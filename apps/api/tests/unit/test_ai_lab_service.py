import json
import os
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text

from app.db.base import Base
from app.models import AIAutoresponderDecision, Appointment, Conversation, Lead, LLMInteraction, Message, OutboxMessage, Patient, Professional, Setting, Unit
from app.services import ai_lab_service
from app.services import ai_structured_flow
from app.services import llm_service

EXACT_LAB_PROMPT = "meu nome e guilherme gomes cpf 120.088.000.00 07/11/1996 quero avaliacao amanha a qualquer horario na clinica sul"


@pytest.fixture(scope="session")
def test_engine():
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url or "odontoflux_test_" not in database_url:
        pytest.skip("Defina TEST_DATABASE_URL apontando para um banco temporario odontoflux_test_* para testes de banco.")
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.commit()
    except Exception as exc:
        pytest.skip(f"Database indisponivel para testes do IA Lab: {exc}")
    Base.metadata.create_all(bind=engine)
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


def _create_unit(db_session, *, tenant_id, name: str = "Unidade Centro", address: str = "Rua Exemplo, 123 - Centro"):
    unit = Unit(
        tenant_id=tenant_id,
        code="CENTRO",
        name=name,
        address={"formatted": address},
        is_active=True,
    )
    db_session.add(unit)
    db_session.commit()
    db_session.refresh(unit)
    return unit


def _tomorrow() -> date:
    return date.today() + timedelta(days=1)


def _ui_weekday(day_value: date) -> int:
    return (day_value.weekday() + 1) % 7


def _create_schedule_unit_and_professional(
    db_session,
    *,
    tenant_id,
    unit_name: str = "Unidade principal",
    professional_name: str = "Dra. Agenda Sul",
    target_date: date | None = None,
    shift_start: str = "08:00",
    shift_end: str = "10:00",
):
    reference_date = target_date or _tomorrow()
    unit = Unit(
        tenant_id=tenant_id,
        code=f"LAB{uuid4().hex[:4].upper()}",
        name=unit_name,
        address={"formatted": "Rua Exemplo, 123 - Centro"},
        is_active=True,
    )
    db_session.add(unit)
    db_session.flush()
    professional = Professional(
        tenant_id=tenant_id,
        unit_id=unit.id,
        full_name=professional_name,
        working_days=[_ui_weekday(reference_date)],
        shift_start=shift_start,
        shift_end=shift_end,
        procedures=["Avaliacao odontologica"],
        is_active=True,
    )
    db_session.add(professional)
    db_session.commit()
    db_session.refresh(unit)
    db_session.refresh(professional)
    return unit, professional


def _structured_decision_payload_for_exact_prompt(*, target_date: date, unit_requested_text: str = "Clinica Sul") -> dict:
    return {
        "schema_version": "1.0",
        "intent": "agendar_consulta",
        "confidence": 0.94,
        "detected_language": "pt-BR",
        "message_summary": "Paciente quer avaliacao amanha em qualquer horario.",
        "extracted_data": {
            "patient_name": "Guilherme Gomes",
            "responsible_name": None,
            "preferred_name": "Guilherme",
            "phone": None,
            "email": None,
            "cpf": "120.088.000.00",
            "birth_date": "1996-11-07",
            "unit_requested_text": unit_requested_text,
            "unit_id": None,
            "service_requested_text": "Avaliacao odontologica",
            "service_id": None,
            "procedure_type": "Avaliacao odontologica",
            "professional_requested_text": None,
            "professional_id": None,
            "preferred_date": target_date.isoformat(),
            "preferred_period": None,
            "preferred_time_text": "qualquer horario",
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
        "field_updates": [
            {
                "target": "leads",
                "field": "name",
                "value": "Guilherme Gomes",
                "confidence": 0.94,
                "source_text": "meu nome e guilherme gomes",
                "should_apply": True,
                "reason": "Paciente informou o nome completo.",
            }
        ],
        "appointment_intent": {
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
        "system_action": {
            "required": True,
            "action": "query_availability",
            "params": {
                "unit_id": None,
                "unit_name": unit_requested_text,
                "service_id": None,
                "procedure_type": "Avaliacao odontologica",
                "professional_id": None,
                "date": target_date.isoformat(),
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
            "should_reply_now": False,
            "reply_after_system_action": True,
            "next_expected_field": None,
            "missing_fields": [],
            "suggested_next_question": None,
        },
        "handoff": {"required": False, "reason": None, "tag": None},
        "guardrails": {
            "triggered": False,
            "reason": None,
            "forbidden_topics_detected": [],
        },
    }


def _structured_reply_output(message: str) -> dict:
    return {
        "schema_version": "1.0",
        "message": message,
        "message_type": "text",
        "interactive_payload": None,
        "confidence": 0.87,
        "final_decision": "reply",
        "decision_reason": "lab_structured_reply",
    }


def _normalized_text(value: str) -> str:
    return ai_structured_flow._strip_accents(str(value or "").casefold())


def _seed_ai_lab_training_example(db_session, *, tenant_id, edited_response_text: str):
    entry = ai_lab_service._build_history_entry(
        input_text=EXACT_LAB_PROMPT,
        context_text="[LAB] Exemplo anterior aprovado.",
        ai_reply_text=edited_response_text,
        ai_next_action="query_availability",
        ai_action_payload={"context": "ai_lab_structured"},
        ai_confidence=0.9,
        ai_raw_output='{"example": true}',
        contract_valid=True,
        metadata={"flow_mode": "structured"},
        edited_response_text=edited_response_text,
        note="exemplo aprovado",
    )
    item = db_session.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == "ai_lab.history"))
    payload = {
        "entries": [entry],
        "updated_at": entry["updated_at"],
    }
    if not item:
        item = Setting(tenant_id=tenant_id, key="ai_lab.history", value=payload, is_secret=False)
    else:
        item.value = payload
        item.is_secret = False
    db_session.add(item)
    db_session.commit()
    return entry


def _mock_intent(*args, **kwargs):
    return {"output": json.dumps({"intent": "agendamento", "confidence": 0.88}, ensure_ascii=False)}


def test_simulate_structured_persisted_conversation_returns_new_real_options_for_end_of_morning(
    monkeypatch,
    seeded_db,
    db_session,
):
    tenant_id = seeded_db["tenant_a"].id
    target_date = _tomorrow()
    unit, _professional = _create_schedule_unit_and_professional(
        db_session,
        tenant_id=tenant_id,
        unit_name="Unidade Centro",
        target_date=target_date,
        shift_end="12:00",
    )

    first_payload = _structured_decision_payload_for_exact_prompt(
        target_date=target_date,
        unit_requested_text=unit.name,
    )
    second_payload = json.loads(json.dumps(first_payload))
    second_payload["intent"] = "outro"
    second_payload["message_summary"] = "Paciente pediu outra opção no fim da manhã."
    second_payload["extracted_data"]["unit_requested_text"] = None
    second_payload["extracted_data"]["service_requested_text"] = None
    second_payload["extracted_data"]["procedure_type"] = None
    second_payload["extracted_data"]["preferred_date"] = None
    second_payload["extracted_data"]["preferred_period"] = None
    second_payload["extracted_data"]["preferred_time_text"] = None
    second_payload["appointment_intent"]["wants_booking"] = False
    second_payload["appointment_intent"]["procedure_type"] = None
    second_payload["system_action"]["required"] = False
    second_payload["system_action"]["action"] = "none"
    second_payload["system_action"]["params"] = {
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

    state = {"count": 0}

    def _fake_run_llm_task(db, *, tenant_id, conversation_id, task, prompt):
        payload = first_payload if state["count"] == 0 else second_payload
        state["count"] += 1
        return {
            "output": json.dumps(payload, ensure_ascii=False),
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
    monkeypatch.setattr(ai_lab_service, "_run_reply_generator", _fake_run_reply_generator)

    first_result = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message="Quero avaliacao amanha de manha na Unidade Centro.",
        context_text="[LAB] Fluxo automatico com persistencia.",
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
        flow_mode="structured",
        persist_conversation=True,
    )
    second_result = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message="Pode ser uma opção no fim da manhã, se tiver.",
        context_text="[LAB] Fluxo automatico com persistencia.",
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
        flow_mode="structured",
        persist_conversation=True,
        lab_conversation_id=first_result["lab_conversation_id"],
    )

    slots = second_result["structured_flow"]["system_action_result"]["slots"]
    params = second_result["structured_flow"]["extractor"]["decision"]["system_action"]["params"]
    assert first_result["lab_conversation_id"]
    assert params["time_after"] == "10:30"
    assert params["time_before"] == "12:00"
    assert slots[0]["label"].endswith("10:30")
    assert "10:30" in second_result["response"]["reply_text"]


def test_simulate_appends_booking_guidance_after_cpf_request_without_knowledge(monkeypatch, seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _create_unit(db_session, tenant_id=tenant_id)

    def _mock_llm_task(*args, **kwargs):
        return {
            "output": json.dumps(
                {
                    "reply_text": (
                        "Seu agendamento para avaliação na Unidade Centro no dia 28/04 às 08:30 está confirmado. "
                        "Para agilizar seu atendimento, por favor, envie seu nome completo, CPF e data de nascimento."
                    ),
                    "next_action": "request_cpf_after_booking",
                    "action_payload": {"context": "booking_confirmed", "unit_name": "Unidade Centro"},
                    "confidence": 0.94,
                },
                ensure_ascii=False,
            ),
            "metadata": {"provider": "mock", "model": "unit-test"},
        }

    monkeypatch.setattr(ai_lab_service, "classify_intent", _mock_intent)
    monkeypatch.setattr(ai_lab_service, "run_llm_task", _mock_llm_task)

    result = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message="Sim, pode confirmar.",
        context_text="[LAB] Paciente escolheu a Unidade Centro e quer concluir o agendamento.",
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
    )

    reply_text = (result.get("response") or {}).get("reply_text") or ""
    assert result["status"] == "ok"
    assert result["metadata"]["booking_guidance_applied"] is True
    assert "Endereço: Rua Exemplo, 123 - Centro" in reply_text
    assert "documento com foto e CPF" in reply_text
    assert "Aguardamos você!" in reply_text


def test_simulate_appends_booking_guidance_when_reply_confirms_booking_with_next_action_none(
    monkeypatch,
    seeded_db,
    db_session,
):
    tenant_id = seeded_db["tenant_a"].id
    _create_unit(db_session, tenant_id=tenant_id)

    def _mock_llm_task(*args, **kwargs):
        return {
            "output": json.dumps(
                {
                    "reply_text": "Perfeito! Seu agendamento já está confirmado para avaliação na Unidade Centro às 08:30.",
                    "next_action": "none",
                    "action_payload": {"context": "booking_confirmed", "unit_name": "Unidade Centro"},
                    "confidence": 0.91,
                },
                ensure_ascii=False,
            ),
            "metadata": {"provider": "mock", "model": "unit-test"},
        }

    monkeypatch.setattr(ai_lab_service, "classify_intent", _mock_intent)
    monkeypatch.setattr(ai_lab_service, "run_llm_task", _mock_llm_task)

    result = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message="Pode finalizar para mim.",
        context_text="[LAB] Conversa concluída com paciente da Unidade Centro.",
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
    )

    reply_text = (result.get("response") or {}).get("reply_text") or ""
    assert result["status"] == "ok"
    assert result["metadata"]["booking_guidance_applied"] is True
    assert "Resumo final do agendamento:" in reply_text
    assert "Endereço: Rua Exemplo, 123 - Centro" in reply_text
    assert "Chegue com 10 a 15 minutos de antecedência." in reply_text


def _count_model(db_session, model, tenant_id):
    return db_session.scalar(select(func.count()).select_from(model).where(model.tenant_id == tenant_id))


def _structured_decision_payload() -> dict:
    return {
        "schema_version": "1.0",
        "intent": "agendar_consulta",
        "confidence": 0.91,
        "detected_language": "pt-BR",
        "message_summary": "Paciente quer agendar avaliacao.",
        "extracted_data": {
            "patient_name": "Juliana",
            "responsible_name": None,
            "preferred_name": None,
            "phone": None,
            "email": None,
            "cpf": None,
            "birth_date": None,
            "unit_requested_text": "Centro",
            "unit_id": None,
            "service_requested_text": "avaliacao odontologica",
            "service_id": None,
            "procedure_type": "Avaliacao odontologica",
            "professional_requested_text": None,
            "professional_id": None,
            "preferred_date": None,
            "preferred_period": "manha",
            "preferred_time_text": "manha",
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
        "field_updates": [
            {
                "target": "leads",
                "field": "name",
                "value": "Juliana",
                "confidence": 0.91,
                "source_text": "sou Juliana",
                "should_apply": True,
                "reason": "Paciente informou o nome.",
            }
        ],
        "appointment_intent": {
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
        "system_action": {
            "required": True,
            "action": "query_availability",
            "params": {
                "unit_id": None,
                "unit_name": "Centro",
                "service_id": None,
                "procedure_type": "Avaliacao odontologica",
                "professional_id": None,
                "date": None,
                "time_after": None,
                "time_before": None,
                "period": "manha",
                "slot_id": None,
                "appointment_id": None,
                "hold_minutes": 10,
                "limit": 3,
            },
        },
        "reply_control": {
            "should_reply_now": False,
            "reply_after_system_action": True,
            "next_expected_field": None,
            "missing_fields": [],
            "suggested_next_question": None,
        },
        "handoff": {"required": False, "reason": None, "tag": None},
        "guardrails": {
            "triggered": False,
            "reason": None,
            "forbidden_topics_detected": [],
        },
    }


def _structured_reply_payload() -> dict:
    return {
        "schema_version": "1.0",
        "message": "Perfeito, Juliana. Posso verificar os melhores horarios de avaliacao para voce.",
        "message_type": "text",
        "interactive_payload": None,
        "confidence": 0.86,
        "final_decision": "reply",
        "decision_reason": "lab_structured_reply",
    }


def test_structured_simulate_returns_safe_flow_without_operational_persistence(
    monkeypatch,
    seeded_db,
    db_session,
):
    tenant_id = seeded_db["tenant_a"].id
    _create_unit(db_session, tenant_id=tenant_id)
    before_messages = _count_model(db_session, Message, tenant_id)
    before_outbox = _count_model(db_session, OutboxMessage, tenant_id)
    before_decisions = _count_model(db_session, AIAutoresponderDecision, tenant_id)

    def _mock_structured_llm(*args, **kwargs):
        task = kwargs.get("task")
        output = _structured_decision_payload() if task == "auto_responder_structured_extract" else _structured_reply_payload()
        return {
            "output": json.dumps(output, ensure_ascii=False),
            "metadata": {"provider": "mock", "model": "unit-test", "task": task},
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _mock_structured_llm)

    result = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message="Oi, sou Juliana e quero agendar uma avaliacao de manha na unidade Centro.",
        context_text="[LAB] Teste estruturado sem envio real.",
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
        flow_mode="structured",
    )

    assert result["status"] == "ok"
    assert result["flow_mode"] == "structured"
    assert result["no_dispatch"] is True
    assert result["no_persistence"] is True
    assert result["contract_valid"] is True
    assert result["structured_flow"]["extractor"]["decision"]["intent"] == "agendar_consulta"
    assert result["structured_flow"]["safe_persistence_plan"]["safe_updates"]["leads"]["name"] == "Juliana"
    assert result["response"]["next_action"] == "query_availability"
    assert _count_model(db_session, Message, tenant_id) == before_messages
    assert _count_model(db_session, OutboxMessage, tenant_id) == before_outbox
    assert _count_model(db_session, AIAutoresponderDecision, tenant_id) == before_decisions


def test_structured_simulate_invalid_extractor_does_not_persist_operational_rows(
    monkeypatch,
    seeded_db,
    db_session,
):
    tenant_id = seeded_db["tenant_a"].id
    _create_unit(db_session, tenant_id=tenant_id)
    before_messages = _count_model(db_session, Message, tenant_id)
    before_outbox = _count_model(db_session, OutboxMessage, tenant_id)

    def _mock_structured_llm(*args, **kwargs):
        task = kwargs.get("task")
        if task == "auto_responder_structured_extract":
            return {
                "output": json.dumps({"schema_version": "1.0", "intent": "agendar_consulta", "unknown": True}),
                "metadata": {"provider": "mock", "model": "unit-test", "task": task},
            }
        return {
            "output": json.dumps(_structured_reply_payload(), ensure_ascii=False),
            "metadata": {"provider": "mock", "model": "unit-test", "task": task},
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _mock_structured_llm)

    result = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message="Quero agendar.",
        context_text="[LAB] Extrator invalido.",
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
        flow_mode="structured",
    )

    assert result["flow_mode"] == "structured"
    assert result["contract_valid"] is False
    assert result["structured_flow"]["extractor"]["contract_valid"] is False
    assert result["structured_flow"]["safe_persistence_plan"]["safe_updates"]["leads"] == {}
    assert _count_model(db_session, Message, tenant_id) == before_messages
    assert _count_model(db_session, OutboxMessage, tenant_id) == before_outbox


def test_structured_simulate_accepts_minimal_legacy_extractor_payload(
    monkeypatch,
    seeded_db,
    db_session,
):
    tenant_id = seeded_db["tenant_a"].id
    _create_unit(db_session, tenant_id=tenant_id)

    def _mock_structured_llm(*args, **kwargs):
        task = kwargs.get("task")
        if task == "auto_responder_structured_extract":
            return {
                "output": json.dumps(
                    {
                        "intent": "outro",
                        "confidence": 0.74,
                        "action": "none",
                        "required": False,
                    },
                    ensure_ascii=False,
                ),
                "metadata": {"provider": "mock", "model": "unit-test", "task": task},
            }
        return {
            "output": json.dumps(_structured_reply_payload(), ensure_ascii=False),
            "metadata": {"provider": "mock", "model": "unit-test", "task": task},
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _mock_structured_llm)

    result = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message="Oi",
        context_text="[LAB] Extrator legado minimo.",
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
        flow_mode="structured",
    )

    assert result["flow_mode"] == "structured"
    assert result["contract_valid"] is True
    assert result["contract_retried"] is False
    assert result["structured_flow"]["extractor"]["contract_valid"] is True
    assert result["structured_flow"]["extractor"]["decision"]["intent"] == "outro"
    assert result["response"]["next_action"] == "none"


def test_structured_simulate_logs_llm_without_fake_conversation_fk(
    monkeypatch,
    seeded_db,
    db_session,
):
    tenant_id = seeded_db["tenant_a"].id
    _create_unit(db_session, tenant_id=tenant_id)

    class _StructuredLabProvider:
        def complete(self, *, task: str, prompt: str):
            output = _structured_decision_payload() if task == "auto_responder_structured_extract" else _structured_reply_payload()
            return {
                "output": json.dumps(output, ensure_ascii=False),
                "metadata": {"provider": "unit-test", "model": "structured-lab", "task": task},
            }

    monkeypatch.setattr(llm_service.LLMProviderFactory, "create", lambda: _StructuredLabProvider())

    result = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message="Oi, quero marcar uma avaliacao para amanha as 13:20h",
        context_text="[LAB] Validar log LLM sem conversa real.",
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
        flow_mode="structured",
    )

    interactions = db_session.scalars(
        select(LLMInteraction).where(
            LLMInteraction.tenant_id == tenant_id,
            LLMInteraction.task.in_(
                [
                    "auto_responder_structured_extract",
                    "auto_responder_structured_reply",
                ]
            ),
        )
    ).all()

    assert result["status"] == "ok"
    assert result["flow_mode"] == "structured"
    assert len(interactions) == 2
    assert {item.task for item in interactions} == {
        "auto_responder_structured_extract",
        "auto_responder_structured_reply",
    }
    assert all(item.conversation_id is None for item in interactions)


def test_structured_simulate_exact_prompt_replaces_false_no_availability_with_real_slots(
    monkeypatch,
    seeded_db,
    db_session,
):
    tenant_id = seeded_db["tenant_a"].id
    target_date = _tomorrow()
    _create_schedule_unit_and_professional(db_session, tenant_id=tenant_id, target_date=target_date)

    def _mock_structured_llm(*args, **kwargs):
        task = kwargs.get("task")
        if task == "auto_responder_structured_extract":
            return {
                "output": json.dumps(
                    _structured_decision_payload_for_exact_prompt(target_date=target_date),
                    ensure_ascii=False,
                ),
                "metadata": {"provider": "mock", "model": "unit-test", "task": task},
            }
        return {
            "output": json.dumps(
                _structured_reply_output(
                    "Ola Guilherme, nao temos horarios disponiveis para avaliacao na Clinica Sul nos proximos dias."
                ),
                ensure_ascii=False,
            ),
            "metadata": {"provider": "mock", "model": "unit-test", "task": task},
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _mock_structured_llm)

    result = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message=EXACT_LAB_PROMPT,
        context_text="[LAB] Prompt real do IA Lab.",
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
        flow_mode="structured",
    )

    reply_text = result["response"]["reply_text"]
    assert result["status"] == "ok"
    assert result["metadata"]["reply_guardrail_applied"] is True
    assert result["metadata"]["reply_guardrail_reason"] == "availability_reply_contradicted_slots"
    assert "nao temos horarios" not in _normalized_text(reply_text)
    assert target_date.strftime("%d/%m/%Y") in reply_text
    assert "08:00" in reply_text
    assert result["structured_flow"]["patient_reply"]["decision_reason"] == "availability_options_returned"


def test_structured_simulate_exact_prompt_replaces_vague_reply_with_real_slot_options(
    monkeypatch,
    seeded_db,
    db_session,
):
    tenant_id = seeded_db["tenant_a"].id
    target_date = _tomorrow()
    _create_schedule_unit_and_professional(db_session, tenant_id=tenant_id, target_date=target_date)

    def _mock_structured_llm(*args, **kwargs):
        task = kwargs.get("task")
        if task == "auto_responder_structured_extract":
            return {
                "output": json.dumps(
                    _structured_decision_payload_for_exact_prompt(target_date=target_date),
                    ensure_ascii=False,
                ),
                "metadata": {"provider": "mock", "model": "unit-test", "task": task},
            }
        return {
            "output": json.dumps(
                _structured_reply_output(
                    "Perfeito, Guilherme. Vou verificar os melhores horarios para voce agora."
                ),
                ensure_ascii=False,
            ),
            "metadata": {"provider": "mock", "model": "unit-test", "task": task},
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _mock_structured_llm)

    result = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message=EXACT_LAB_PROMPT,
        context_text="[LAB] Prompt real do IA Lab.",
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
        flow_mode="structured",
    )

    reply_text = result["response"]["reply_text"]
    assert result["status"] == "ok"
    assert result["metadata"]["reply_guardrail_applied"] is True
    assert result["metadata"]["reply_guardrail_reason"] == "availability_reply_missing_slot_options"
    assert target_date.strftime("%d/%m/%Y") in reply_text
    assert "08:30" in reply_text
    assert result["structured_flow"]["patient_reply"]["decision_reason"] == "availability_options_returned"


def test_structured_simulate_exact_prompt_keeps_reply_that_already_lists_real_slot_times(
    monkeypatch,
    seeded_db,
    db_session,
):
    tenant_id = seeded_db["tenant_a"].id
    target_date = _tomorrow()
    _create_schedule_unit_and_professional(db_session, tenant_id=tenant_id, target_date=target_date)
    expected_reply = "Ola Guilherme, encontrei horarios para amanha: 08:00, 08:30 e 09:00. Qual fica melhor para voce?"

    def _mock_structured_llm(*args, **kwargs):
        task = kwargs.get("task")
        if task == "auto_responder_structured_extract":
            return {
                "output": json.dumps(
                    _structured_decision_payload_for_exact_prompt(target_date=target_date),
                    ensure_ascii=False,
                ),
                "metadata": {"provider": "mock", "model": "unit-test", "task": task},
            }
        return {
            "output": json.dumps(_structured_reply_output(expected_reply), ensure_ascii=False),
            "metadata": {"provider": "mock", "model": "unit-test", "task": task},
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _mock_structured_llm)

    result = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message=EXACT_LAB_PROMPT,
        context_text="[LAB] Prompt real do IA Lab.",
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
        flow_mode="structured",
    )

    assert result["status"] == "ok"
    assert result["response"]["reply_text"] == expected_reply
    assert result["metadata"].get("reply_guardrail_applied") is None
    assert result["structured_flow"]["patient_reply"]["decision_reason"] == "lab_structured_reply"


def test_structured_simulate_exact_prompt_ignores_negative_training_example_when_slots_exist(
    monkeypatch,
    seeded_db,
    db_session,
):
    tenant_id = seeded_db["tenant_a"].id
    target_date = _tomorrow()
    _create_schedule_unit_and_professional(db_session, tenant_id=tenant_id, target_date=target_date)
    _seed_ai_lab_training_example(
        db_session,
        tenant_id=tenant_id,
        edited_response_text="Nao temos horarios disponiveis para avaliacao na Clinica Sul nos proximos dias.",
    )

    def _mock_structured_llm(*args, **kwargs):
        task = kwargs.get("task")
        if task == "auto_responder_structured_extract":
            return {
                "output": json.dumps(
                    _structured_decision_payload_for_exact_prompt(target_date=target_date),
                    ensure_ascii=False,
                ),
                "metadata": {"provider": "mock", "model": "unit-test", "task": task},
            }
        return {
            "output": json.dumps(
                _structured_reply_output(
                    "Nao temos horarios disponiveis para avaliacao na Clinica Sul nos proximos dias."
                ),
                ensure_ascii=False,
            ),
            "metadata": {"provider": "mock", "model": "unit-test", "task": task},
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _mock_structured_llm)

    result = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message=EXACT_LAB_PROMPT,
        context_text="[LAB] Prompt real do IA Lab com historico aprovado.",
        include_knowledge=False,
        use_training_examples=True,
        auto_save_history=False,
        flow_mode="structured",
    )

    reply_text = result["response"]["reply_text"]
    assert result["status"] == "ok"
    assert result["training_examples_used"] is True
    assert result["metadata"]["reply_guardrail_applied"] is True
    assert "08:00" in reply_text
    assert "nao temos horarios" not in _normalized_text(reply_text)


def test_structured_simulate_exact_prompt_auto_saved_history_uses_guardrailed_reply(
    monkeypatch,
    seeded_db,
    db_session,
):
    tenant_id = seeded_db["tenant_a"].id
    target_date = _tomorrow()
    _create_schedule_unit_and_professional(db_session, tenant_id=tenant_id, target_date=target_date)

    def _mock_structured_llm(*args, **kwargs):
        task = kwargs.get("task")
        if task == "auto_responder_structured_extract":
            return {
                "output": json.dumps(
                    _structured_decision_payload_for_exact_prompt(target_date=target_date),
                    ensure_ascii=False,
                ),
                "metadata": {"provider": "mock", "model": "unit-test", "task": task},
            }
        return {
            "output": json.dumps(
                _structured_reply_output(
                    "Ola Guilherme, nao temos horarios disponiveis para avaliacao na Clinica Sul nos proximos dias."
                ),
                ensure_ascii=False,
            ),
            "metadata": {"provider": "mock", "model": "unit-test", "task": task},
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _mock_structured_llm)

    result = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message=EXACT_LAB_PROMPT,
        context_text="[LAB] Prompt real do IA Lab com historico salvo.",
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=True,
        flow_mode="structured",
    )

    history_entries = ai_lab_service.list_history(db_session, tenant_id=tenant_id, limit=5)
    assert result["status"] == "ok"
    assert result["history_entry"] is not None
    assert history_entries
    assert history_entries[0]["id"] == result["history_entry"]["id"]
    assert "08:00" in history_entries[0]["ai_reply_text"]
    assert "nao temos horarios" not in _normalized_text(history_entries[0]["ai_reply_text"])


def test_structured_simulate_exact_prompt_ignores_legacy_appointment_without_end_time(
    monkeypatch,
    seeded_db,
    db_session,
):
    tenant_id = seeded_db["tenant_a"].id
    target_date = _tomorrow()
    unit, professional = _create_schedule_unit_and_professional(db_session, tenant_id=tenant_id, target_date=target_date)
    phone_suffix = uuid4().hex[:8]
    patient = Patient(
        tenant_id=tenant_id,
        full_name="Paciente legado",
        phone=f"55119{phone_suffix}",
        normalized_phone=f"55119{phone_suffix}",
        status="ativo",
        origin="whatsapp",
        lgpd_consent=True,
        marketing_opt_in=True,
    )
    db_session.add(patient)
    db_session.flush()
    db_session.add(
        Appointment(
            tenant_id=tenant_id,
            patient_id=patient.id,
            unit_id=unit.id,
            professional_id=professional.id,
            procedure_type="Avaliacao detalhada",
            starts_at=datetime.combine(target_date - timedelta(days=10), datetime.min.time()).replace(hour=11, tzinfo=UTC),
            ends_at=None,
            status="agendada",
            origin="legacy_import",
            notes="registro antigo sem ends_at",
        )
    )
    db_session.commit()

    def _mock_structured_llm(*args, **kwargs):
        task = kwargs.get("task")
        if task == "auto_responder_structured_extract":
            return {
                "output": json.dumps(
                    _structured_decision_payload_for_exact_prompt(
                        target_date=target_date,
                        unit_requested_text=unit.name,
                    ),
                    ensure_ascii=False,
                ),
                "metadata": {"provider": "mock", "model": "unit-test", "task": task},
            }
        return {
            "output": json.dumps(
                _structured_reply_output("Perfeito, Guilherme. Vou verificar os melhores horarios para voce agora."),
                ensure_ascii=False,
            ),
            "metadata": {"provider": "mock", "model": "unit-test", "task": task},
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _mock_structured_llm)

    result = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message=EXACT_LAB_PROMPT,
        context_text="[LAB] Prompt real com agenda legada sem ends_at.",
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
        flow_mode="structured",
    )

    slots = result["structured_flow"]["system_action_result"]["slots"]
    assert result["status"] == "ok"
    assert slots
    assert slots[0]["label"].startswith(target_date.strftime("%d/%m/%Y"))
    assert "08:00" in result["response"]["reply_text"]


def test_structured_simulate_generic_follow_up_slot_selection_uses_context_unit(
    monkeypatch,
    seeded_db,
    db_session,
):
    tenant_id = seeded_db["tenant_a"].id
    target_date = _tomorrow()
    unit, _professional = _create_schedule_unit_and_professional(
        db_session,
        tenant_id=tenant_id,
        unit_name="Unidade Contexto",
        target_date=target_date,
    )

    def _mock_structured_llm(*args, **kwargs):
        task = kwargs.get("task")
        prompt = kwargs.get("prompt") or ""
        if task == "auto_responder_structured_extract":
            if "Pode ser" in prompt:
                payload = _structured_decision_payload_for_exact_prompt(
                    target_date=target_date,
                    unit_requested_text="",
                )
                payload["intent"] = "selecionar_horario"
                payload["message_summary"] = "Paciente escolheu um horario."
                payload["extracted_data"]["unit_requested_text"] = ""
                payload["extracted_data"]["preferred_date"] = target_date.isoformat()
                payload["extracted_data"]["preferred_time_text"] = None
                payload["extracted_data"]["selected_slot_id"] = None
                payload["extracted_data"]["selected_datetime"] = None
                payload["appointment_intent"]["procedure_type"] = "Avaliacao odontologica"
                payload["system_action"]["action"] = "validate_slot"
                payload["system_action"]["params"]["unit_name"] = ""
                payload["system_action"]["params"]["date"] = target_date.isoformat()
                return {
                    "output": json.dumps(payload, ensure_ascii=False),
                    "metadata": {"provider": "mock", "model": "unit-test", "task": task},
                }
            return {
                "output": json.dumps(
                    _structured_decision_payload_for_exact_prompt(
                        target_date=target_date,
                        unit_requested_text=unit.name,
                    ),
                    ensure_ascii=False,
                ),
                "metadata": {"provider": "mock", "model": "unit-test", "task": task},
            }
        if "validate_slot" in prompt:
            return {
                "output": json.dumps(
                    _structured_reply_output("Perfeito, esse horario esta disponivel. Qual e o melhor telefone para confirmacao?"),
                    ensure_ascii=False,
                ),
                "metadata": {"provider": "mock", "model": "unit-test", "task": task},
            }
        return {
            "output": json.dumps(
                _structured_reply_output(f"Ola Guilherme, tenho avaliacao na {unit.name} amanha as 08:00, 08:30 ou 09:00."),
                ensure_ascii=False,
            ),
            "metadata": {"provider": "mock", "model": "unit-test", "task": task},
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _mock_structured_llm)

    result1 = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message=EXACT_LAB_PROMPT,
        context_text="[LAB] Conversa automatica sem WhatsApp real.",
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
        flow_mode="structured",
    )
    context2 = "\n".join(
        [
            "[LAB] Conversa automatica sem WhatsApp real.",
            "Continue a simulacao considerando o historico abaixo.",
            "Proximo comportamento do paciente virtual: Paciente escolheu um horario retornado pela consulta real de disponibilidade.",
            f"Paciente virtual: {EXACT_LAB_PROMPT}",
            f"Clinica IA: {result1['response']['reply_text']}",
        ]
    )

    result2 = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message=f"Pode ser {target_date.strftime('%d/%m/%Y')} as 08:00 para mim.",
        context_text=context2,
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
        flow_mode="structured",
    )

    action_result = result2["structured_flow"]["system_action_result"]
    assert result2["status"] == "ok"
    assert action_result["status"] == "available"
    assert action_result["unit_id"] == str(unit.id)
    assert action_result["unit_name"] == unit.name
    assert action_result["starts_at"].endswith("11:00:00+00:00")
    assert "nao apareceu mais como disponivel" not in _normalized_text(result2["response"]["reply_text"])


def test_structured_simulate_generic_follow_up_validates_each_returned_slot_without_slot_token(
    monkeypatch,
    seeded_db,
    db_session,
):
    tenant_id = seeded_db["tenant_a"].id
    target_date = _tomorrow()
    _unit, _professional = _create_schedule_unit_and_professional(
        db_session,
        tenant_id=tenant_id,
        unit_name="Unidade Contexto",
        target_date=target_date,
    )

    def _mock_structured_llm(*args, **kwargs):
        task = kwargs.get("task")
        prompt = kwargs.get("prompt") or ""
        if task == "auto_responder_structured_extract":
            if "Pode ser" in prompt:
                payload = _structured_decision_payload_for_exact_prompt(
                    target_date=target_date,
                    unit_requested_text="",
                )
                payload["intent"] = "selecionar_horario"
                payload["message_summary"] = "Paciente escolheu um horario."
                payload["extracted_data"]["unit_requested_text"] = ""
                payload["extracted_data"]["preferred_date"] = target_date.isoformat()
                payload["extracted_data"]["preferred_time_text"] = None
                payload["extracted_data"]["selected_slot_id"] = None
                payload["extracted_data"]["selected_datetime"] = None
                payload["appointment_intent"]["procedure_type"] = "Avaliacao odontologica"
                payload["system_action"]["action"] = "validate_slot"
                payload["system_action"]["params"]["unit_name"] = ""
                payload["system_action"]["params"]["date"] = target_date.isoformat()
                return {
                    "output": json.dumps(payload, ensure_ascii=False),
                    "metadata": {"provider": "mock", "model": "unit-test", "task": task},
                }
            return {
                "output": json.dumps(
                    _structured_decision_payload_for_exact_prompt(
                        target_date=target_date,
                        unit_requested_text="Unidade Contexto",
                    ),
                    ensure_ascii=False,
                ),
                "metadata": {"provider": "mock", "model": "unit-test", "task": task},
            }
        if "validate_slot" in prompt:
            return {
                "output": json.dumps(
                    _structured_reply_output("Perfeito, esse horario esta disponivel. Qual e o melhor telefone para confirmacao?"),
                    ensure_ascii=False,
                ),
                "metadata": {"provider": "mock", "model": "unit-test", "task": task},
            }
        return {
            "output": json.dumps(
                _structured_reply_output("Ola Guilherme, tenho avaliacao na Unidade Contexto amanha as 08:00, 08:30 ou 09:00."),
                ensure_ascii=False,
            ),
            "metadata": {"provider": "mock", "model": "unit-test", "task": task},
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _mock_structured_llm)

    result1 = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message=EXACT_LAB_PROMPT,
        context_text="[LAB] Conversa automatica sem WhatsApp real.",
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
        flow_mode="structured",
    )
    slots = result1["structured_flow"]["system_action_result"]["slots"]
    context2 = "\n".join(
        [
            "[LAB] Conversa automatica sem WhatsApp real.",
            "Continue a simulacao considerando o historico abaixo.",
            "Proximo comportamento do paciente virtual: Paciente escolheu um horario retornado pela consulta real de disponibilidade.",
            f"Paciente virtual: {EXACT_LAB_PROMPT}",
            f"Clinica IA: {result1['response']['reply_text']}",
        ]
    )

    for slot in slots:
        result2 = ai_lab_service.simulate(
            db_session,
            tenant_id=tenant_id,
            message=f"Pode ser {slot['label']} para mim.",
            context_text=context2,
            include_knowledge=False,
            use_training_examples=False,
            auto_save_history=False,
            flow_mode="structured",
        )
        action_result = result2["structured_flow"]["system_action_result"]
        assert action_result["status"] == "available"
        assert action_result["starts_at"] == slot["starts_at"]
        assert "nao apareceu mais como disponivel" not in _normalized_text(result2["response"]["reply_text"])


def test_structured_simulate_persisted_lab_conversation_reuses_real_db_conversation(
    monkeypatch,
    seeded_db,
    db_session,
):
    tenant_id = seeded_db["tenant_a"].id
    target_date = _tomorrow()
    unit, _professional = _create_schedule_unit_and_professional(
        db_session,
        tenant_id=tenant_id,
        unit_name="Unidade Centro",
        target_date=target_date,
    )
    before_outbox = _count_model(db_session, OutboxMessage, tenant_id)

    def _mock_structured_llm(*args, **kwargs):
        task = kwargs.get("task")
        prompt = kwargs.get("prompt") or ""
        if task == "auto_responder_structured_extract":
            if "Pode ser" in prompt:
                payload = _structured_decision_payload_for_exact_prompt(
                    target_date=target_date,
                    unit_requested_text="",
                )
                payload["intent"] = "selecionar_horario"
                payload["message_summary"] = "Paciente escolheu um horario."
                payload["extracted_data"]["unit_requested_text"] = ""
                payload["extracted_data"]["selected_slot_id"] = None
                payload["extracted_data"]["selected_datetime"] = None
                payload["system_action"]["action"] = "validate_slot"
                payload["system_action"]["params"]["unit_name"] = ""
                payload["system_action"]["params"]["date"] = target_date.isoformat()
                return {
                    "output": json.dumps(payload, ensure_ascii=False),
                    "metadata": {"provider": "mock", "model": "unit-test", "task": task},
                }
            return {
                "output": json.dumps(
                    _structured_decision_payload_for_exact_prompt(
                        target_date=target_date,
                        unit_requested_text=unit.name,
                    ),
                    ensure_ascii=False,
                ),
                "metadata": {"provider": "mock", "model": "unit-test", "task": task},
            }
        if "validate_slot" in prompt:
            return {
                "output": json.dumps(
                    _structured_reply_output("Perfeito, esse horario esta disponivel. Qual e o seu nome completo?"),
                    ensure_ascii=False,
                ),
                "metadata": {"provider": "mock", "model": "unit-test", "task": task},
            }
        return {
            "output": json.dumps(
                _structured_reply_output("Ola Guilherme, tenho avaliacao na Unidade Centro amanha as 08:00, 08:30 ou 09:00."),
                ensure_ascii=False,
            ),
            "metadata": {"provider": "mock", "model": "unit-test", "task": task},
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _mock_structured_llm)

    result1 = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message=EXACT_LAB_PROMPT,
        context_text="[LAB] Fluxo automatico persistido.",
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
        flow_mode="structured",
        persist_conversation=True,
    )
    conversation_id = result1["lab_conversation_id"]
    assert result1["no_persistence"] is False
    assert conversation_id is not None

    result2 = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message=f"Pode ser {target_date.strftime('%d/%m/%Y')} as 08:00 para mim.",
        context_text="[LAB] Fluxo automatico persistido.",
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
        flow_mode="structured",
        persist_conversation=True,
        lab_conversation_id=conversation_id,
    )

    conversation = db_session.get(Conversation, conversation_id)
    messages = db_session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
    ).all()
    lead = db_session.get(Lead, conversation.lead_id)

    assert result2["lab_conversation_id"] == conversation_id
    assert result2["no_persistence"] is False
    assert result2["structured_flow"]["system_action_result"]["status"] == "available"
    assert conversation is not None
    assert conversation.ai_summary == "Paciente escolheu um horario."
    assert lead is not None
    assert lead.name == "Guilherme Gomes"
    assert len(messages) == 4
    assert [message.direction for message in messages] == ["inbound", "outbound", "inbound", "outbound"]
    assert _count_model(db_session, OutboxMessage, tenant_id) == before_outbox


def test_structured_simulate_persisted_lab_conversation_placeholder_name_does_not_skip_real_name_request(
    monkeypatch,
    seeded_db,
    db_session,
):
    tenant_id = seeded_db["tenant_a"].id
    target_date = _tomorrow()
    initial_message = "Oi, quero agendar uma avaliacao e entender como funciona."
    unit, _professional = _create_schedule_unit_and_professional(
        db_session,
        tenant_id=tenant_id,
        unit_name="Unidade Centro",
        target_date=target_date,
    )

    def _mock_structured_llm(*args, **kwargs):
        task = kwargs.get("task")
        prompt = kwargs.get("prompt") or ""
        if task == "auto_responder_structured_extract":
            if "Pode ser" in prompt:
                payload = _structured_decision_payload_for_exact_prompt(
                    target_date=target_date,
                    unit_requested_text="",
                )
                payload["intent"] = "selecionar_horario"
                payload["message_summary"] = "Paciente escolheu um horario."
                payload["extracted_data"]["patient_name"] = None
                payload["extracted_data"]["preferred_name"] = None
                payload["extracted_data"]["cpf"] = None
                payload["extracted_data"]["birth_date"] = None
                payload["extracted_data"]["unit_requested_text"] = ""
                payload["extracted_data"]["selected_slot_id"] = None
                payload["extracted_data"]["selected_datetime"] = None
                payload["field_updates"] = []
                payload["system_action"]["action"] = "validate_slot"
                payload["system_action"]["params"]["unit_name"] = ""
                payload["system_action"]["params"]["date"] = target_date.isoformat()
                return {
                    "output": json.dumps(payload, ensure_ascii=False),
                    "metadata": {"provider": "mock", "model": "unit-test", "task": task},
                }
            return {
                "output": json.dumps(
                    {
                        **_structured_decision_payload_for_exact_prompt(
                            target_date=target_date,
                            unit_requested_text=unit.name,
                        ),
                        "message_summary": "Paciente quer entender como funciona e buscar horarios.",
                        "extracted_data": {
                            **_structured_decision_payload_for_exact_prompt(
                                target_date=target_date,
                                unit_requested_text=unit.name,
                            )["extracted_data"],
                            "patient_name": None,
                            "preferred_name": None,
                            "cpf": None,
                            "birth_date": None,
                        },
                        "field_updates": [],
                    },
                    ensure_ascii=False,
                ),
                "metadata": {"provider": "mock", "model": "unit-test", "task": task},
            }
        if "validate_slot" in prompt:
            return {
                "output": json.dumps({"foo": "bar"}, ensure_ascii=False),
                "metadata": {"provider": "mock", "model": "unit-test", "task": task},
            }
        return {
            "output": json.dumps(
                _structured_reply_output("Tenho 08:00, 08:30 ou 09:00 amanha."),
                ensure_ascii=False,
            ),
            "metadata": {"provider": "mock", "model": "unit-test", "task": task},
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _mock_structured_llm)

    result1 = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message=initial_message,
        context_text="[LAB] Fluxo automatico persistido.",
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
        flow_mode="structured",
        persist_conversation=True,
    )

    result2 = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message=f"Pode ser {target_date.strftime('%d/%m/%Y')} as 08:00 para mim.",
        context_text="[LAB] Fluxo automatico persistido.",
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
        flow_mode="structured",
        persist_conversation=True,
        lab_conversation_id=result1["lab_conversation_id"],
    )

    reply_text = _normalized_text(result2["response"]["reply_text"])
    assert "nome completo" in reply_text
    assert "melhor numero" not in reply_text
    assert result2["structured_flow"]["system_action_result"]["status"] == "available"


def test_structured_simulate_persisted_lab_conversation_keeps_slot_context_after_name_and_whatsapp(
    monkeypatch,
    seeded_db,
    db_session,
):
    tenant_id = seeded_db["tenant_a"].id
    target_date = _tomorrow()
    initial_message = "Oi, quero agendar uma avaliacao e entender como funciona."
    unit, _professional = _create_schedule_unit_and_professional(
        db_session,
        tenant_id=tenant_id,
        unit_name="Unidade Centro",
        target_date=target_date,
    )

    def _mock_structured_llm(*args, **kwargs):
        task = kwargs.get("task")
        prompt = kwargs.get("prompt") or ""
        if task == "auto_responder_structured_extract":
            if "Meu nome completo" in prompt:
                payload = {
                    "schema_version": "1.0",
                    "intent": "informar_dados_pessoais",
                    "confidence": 0.92,
                    "detected_language": "pt-BR",
                    "message_summary": "Paciente informou dados pessoais para confirmar o horario.",
                    "extracted_data": {
                        "patient_name": None,
                        "responsible_name": None,
                        "preferred_name": None,
                        "phone": None,
                        "email": None,
                        "cpf": None,
                        "birth_date": None,
                        "unit_requested_text": "",
                        "unit_id": None,
                        "service_requested_text": "",
                        "service_id": None,
                        "procedure_type": "",
                        "professional_requested_text": None,
                        "professional_id": None,
                        "preferred_date": None,
                        "preferred_period": None,
                        "preferred_time_text": None,
                        "selected_slot_id": None,
                        "selected_datetime": "",
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
                        "procedure_type": "",
                        "unit_id": None,
                        "professional_id": None,
                        "starts_at": "",
                        "ends_at": None,
                        "canceled_reason": None,
                    },
                    "system_action": {
                        "required": False,
                        "action": "none",
                        "params": {
                            "unit_id": None,
                            "unit_name": "",
                            "service_id": None,
                            "procedure_type": "",
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
                        "suggested_next_question": None,
                    },
                    "handoff": {"required": False, "reason": None, "tag": None},
                    "guardrails": {"triggered": False, "reason": None, "forbidden_topics_detected": []},
                }
                return {
                    "output": json.dumps(payload, ensure_ascii=False),
                    "metadata": {"provider": "mock", "model": "unit-test", "task": task},
                }
            if "Pode ser" in prompt:
                payload = _structured_decision_payload_for_exact_prompt(
                    target_date=target_date,
                    unit_requested_text="",
                )
                payload["intent"] = "selecionar_horario"
                payload["message_summary"] = "Paciente escolheu um horario."
                payload["extracted_data"]["patient_name"] = None
                payload["extracted_data"]["preferred_name"] = None
                payload["extracted_data"]["cpf"] = None
                payload["extracted_data"]["birth_date"] = None
                payload["extracted_data"]["unit_requested_text"] = ""
                payload["extracted_data"]["selected_slot_id"] = None
                payload["extracted_data"]["selected_datetime"] = None
                payload["field_updates"] = []
                payload["system_action"]["action"] = "validate_slot"
                payload["system_action"]["params"]["unit_name"] = ""
                payload["system_action"]["params"]["date"] = target_date.isoformat()
                return {
                    "output": json.dumps(payload, ensure_ascii=False),
                    "metadata": {"provider": "mock", "model": "unit-test", "task": task},
                }
            return {
                "output": json.dumps(
                    {
                        **_structured_decision_payload_for_exact_prompt(
                            target_date=target_date,
                            unit_requested_text=unit.name,
                        ),
                        "message_summary": "Paciente quer entender como funciona e buscar horarios.",
                        "extracted_data": {
                            **_structured_decision_payload_for_exact_prompt(
                                target_date=target_date,
                                unit_requested_text=unit.name,
                            )["extracted_data"],
                            "patient_name": None,
                            "preferred_name": None,
                            "cpf": None,
                            "birth_date": None,
                        },
                        "field_updates": [],
                    },
                    ensure_ascii=False,
                ),
                "metadata": {"provider": "mock", "model": "unit-test", "task": task},
            }
        if "validate_slot" in prompt:
            return {
                "output": json.dumps({"foo": "bar"}, ensure_ascii=False),
                "metadata": {"provider": "mock", "model": "unit-test", "task": task},
            }
        if "informar_dados_pessoais" in prompt:
            return {
                "output": json.dumps(
                    _structured_reply_output("Entendi. Para eu te ajudar certinho, voce prefere atendimento em qual unidade e periodo?"),
                    ensure_ascii=False,
                ),
                "metadata": {"provider": "mock", "model": "unit-test", "task": task},
            }
        return {
            "output": json.dumps(
                _structured_reply_output("Tenho 08:00, 08:30 ou 09:00 amanha."),
                ensure_ascii=False,
            ),
            "metadata": {"provider": "mock", "model": "unit-test", "task": task},
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _mock_structured_llm)

    result1 = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message=initial_message,
        context_text="[LAB] Fluxo automatico persistido.",
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
        flow_mode="structured",
        persist_conversation=True,
    )
    result2 = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message=f"Pode ser {target_date.strftime('%d/%m/%Y')} as 08:00 para mim.",
        context_text="[LAB] Fluxo automatico persistido.",
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
        flow_mode="structured",
        persist_conversation=True,
        lab_conversation_id=result1["lab_conversation_id"],
    )
    result3 = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message="Meu nome completo e Guilherme Gomes e esse WhatsApp e o melhor numero para confirmacao.",
        context_text="[LAB] Fluxo automatico persistido.",
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
        flow_mode="structured",
        persist_conversation=True,
        lab_conversation_id=result2["lab_conversation_id"],
    )

    conversation = db_session.get(Conversation, result3["lab_conversation_id"])
    patient = db_session.get(Patient, conversation.patient_id)
    lead = db_session.get(Lead, conversation.lead_id)
    reply_text = _normalized_text(result3["response"]["reply_text"])

    assert result3["structured_flow"]["extractor"]["decision"]["extracted_data"]["patient_name"] == "Guilherme Gomes"
    assert "qual unidade" not in reply_text
    assert "qual periodo" not in reply_text
    assert "guilherme" in reply_text
    assert patient is not None and patient.full_name == "Guilherme Gomes"
    assert lead is not None and lead.name == "Guilherme Gomes"


def test_structured_simulate_validate_slot_guardrail_falls_back_from_wrong_confirmation(
    monkeypatch,
    seeded_db,
    db_session,
):
    tenant_id = seeded_db["tenant_a"].id
    target_date = _tomorrow()
    _unit, _professional = _create_schedule_unit_and_professional(
        db_session,
        tenant_id=tenant_id,
        unit_name="Unidade Centro",
        target_date=target_date,
    )

    def _mock_structured_llm(*args, **kwargs):
        task = kwargs.get("task")
        prompt = kwargs.get("prompt") or ""
        if task == "auto_responder_structured_extract":
            if "Pode ser" in prompt:
                payload = _structured_decision_payload_for_exact_prompt(
                    target_date=target_date,
                    unit_requested_text="",
                )
                payload["intent"] = "selecionar_horario"
                payload["message_summary"] = "Paciente escolheu um horario."
                payload["extracted_data"]["unit_requested_text"] = ""
                payload["extracted_data"]["selected_slot_id"] = None
                payload["extracted_data"]["selected_datetime"] = None
                payload["system_action"]["action"] = "validate_slot"
                payload["system_action"]["params"]["unit_name"] = ""
                payload["system_action"]["params"]["date"] = target_date.isoformat()
                return {
                    "output": json.dumps(payload, ensure_ascii=False),
                    "metadata": {"provider": "mock", "model": "unit-test", "task": task},
                }
            return {
                "output": json.dumps(
                    _structured_decision_payload_for_exact_prompt(
                        target_date=target_date,
                        unit_requested_text="Unidade Centro",
                    ),
                    ensure_ascii=False,
                ),
                "metadata": {"provider": "mock", "model": "unit-test", "task": task},
            }
        if "validate_slot" in prompt:
            return {
                "output": json.dumps(
                    _structured_reply_output(
                        "Otimo, agendei para voce na Unidade Centro com o Dr. Jaycob Gomes no dia 08/05/2026 as 11:30. Para finalizar, me informe seu nome completo."
                    ),
                    ensure_ascii=False,
                ),
                "metadata": {"provider": "mock", "model": "unit-test", "task": task},
            }
        return {
            "output": json.dumps(
                _structured_reply_output("Ola Guilherme, tenho avaliacao na Unidade Centro amanha as 08:00, 08:30 ou 09:00."),
                ensure_ascii=False,
            ),
            "metadata": {"provider": "mock", "model": "unit-test", "task": task},
        }

    monkeypatch.setattr(ai_structured_flow, "run_llm_task", _mock_structured_llm)

    result1 = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message=EXACT_LAB_PROMPT,
        context_text="[LAB] Conversa automatica sem WhatsApp real.",
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
        flow_mode="structured",
    )
    context2 = "\n".join(
        [
            "[LAB] Conversa automatica sem WhatsApp real.",
            "Continue a simulacao considerando o historico abaixo.",
            "Proximo comportamento do paciente virtual: Paciente escolheu um horario retornado pela consulta real de disponibilidade.",
            f"Paciente virtual: {EXACT_LAB_PROMPT}",
            f"Clinica IA: {result1['response']['reply_text']}",
        ]
    )

    result2 = ai_lab_service.simulate(
        db_session,
        tenant_id=tenant_id,
        message=f"Pode ser {target_date.strftime('%d/%m/%Y')} as 08:30 para mim.",
        context_text=context2,
        include_knowledge=False,
        use_training_examples=False,
        auto_save_history=False,
        flow_mode="structured",
    )

    reply_text = result2["response"]["reply_text"]
    assert result2["structured_flow"]["system_action_result"]["status"] == "available"
    assert result2["metadata"]["reply_guardrail_applied"] is True
    assert result2["metadata"]["reply_guardrail_reason"] == "validated_slot_reply_confirmed_booking"
    assert "11:30" not in reply_text
    assert "08:30" in reply_text
    assert "agendei" not in _normalized_text(reply_text)

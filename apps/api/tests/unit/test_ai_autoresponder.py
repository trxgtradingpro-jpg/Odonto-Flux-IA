from datetime import UTC, datetime, timedelta
from uuid import uuid4
from sqlalchemy import delete, func, select

from app.models import (
    AIAutoresponderDecision,
    Appointment,
    Conversation,
    Message,
    OutboxMessage,
    Patient,
    Professional,
    Setting,
    Unit,
    WhatsAppAccount,
)
from app.services.ai_autoresponder_service import process_inbound_message


def _base_ai_config():
    return {
        "enabled": True,
        "channels": {"whatsapp": True},
        "business_hours": {
            "timezone": "America/Sao_Paulo",
            "weekdays": [0, 1, 2, 3, 4, 5, 6],
            "start": "00:00",
            "end": "23:59",
        },
        "outside_business_hours_mode": "allow",
        "max_consecutive_auto_replies": 3,
        "confidence_threshold": 0.5,
        "human_queue_tag": "fila_humana_ia",
        "tone": "profissional e acolhedor",
    }


def _upsert_ai_global_setting(db_session, *, tenant_id, value: dict):
    item = db_session.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == "ai_autoresponder.global"))
    if not item:
        item = Setting(tenant_id=tenant_id, key="ai_autoresponder.global", value=value, is_secret=False)
    else:
        item.value = value
    db_session.add(item)
    db_session.commit()


def _upsert_ai_knowledge_base_setting(db_session, *, tenant_id, value: dict):
    item = db_session.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == "ai_knowledge_base.global"))
    if not item:
        item = Setting(tenant_id=tenant_id, key="ai_knowledge_base.global", value=value, is_secret=False)
    else:
        item.value = value
    db_session.add(item)
    db_session.commit()


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
        account.phone_number_id = "1101713436353674"
        account.business_account_id = "936994182588219"
        account.access_token_encrypted = "EAAa" + ("x" * 60)
        account.is_active = True
    db_session.add(account)
    db_session.commit()


def _create_conversation_with_inbound(db_session, *, tenant_id, inbound_text: str):
    suffix = uuid4().hex[:8]
    phone = f"5511940{suffix}"
    patient = Patient(
        tenant_id=tenant_id,
        full_name=f"Paciente Teste {suffix}",
        phone=phone,
        normalized_phone=phone,
        status="ativo",
        origin="whatsapp",
        lgpd_consent=True,
        marketing_opt_in=True,
        tags_cache=[],
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

    inbound_message = Message(
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
    db_session.add(inbound_message)
    db_session.commit()
    return conversation, inbound_message


def _append_inbound_message(
    db_session,
    *,
    tenant_id,
    conversation_id,
    inbound_text: str,
    message_type: str = "text",
    payload: dict | None = None,
):
    inbound_message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        direction="inbound",
        channel="whatsapp",
        sender_type="patient",
        body=inbound_text,
        message_type=message_type,
        payload=payload or {},
        status="received",
    )
    db_session.add(inbound_message)
    db_session.commit()
    return inbound_message


def _ensure_professional(db_session, *, tenant_id, unit_id, full_name: str = "Dr Wizard"):
    professional = Professional(
        tenant_id=tenant_id,
        unit_id=unit_id,
        full_name=full_name,
        working_days=[0, 1, 2, 3, 4, 5],
        shift_start="08:00",
        shift_end="18:00",
        procedures=["InstalaÃƒÂ§ÃƒÂ£o de lentes", "Clareamento dental"],
        is_active=True,
    )
    db_session.add(professional)
    db_session.flush()
    return professional


def test_handoff_when_patient_requests_human(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quero falar com atendente agora.",
    )

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    assert result["status"] == "handoff"
    assert result["reason"] == "patient_requested_human"

    refreshed = db_session.get(Conversation, conversation.id)
    assert refreshed.status == "aguardando"
    assert "fila_humana_ia" in (refreshed.tags or [])


def test_handoff_when_urgency_detected(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Estou com dor forte e sangramento urgente.",
    )

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    assert result["status"] == "handoff"
    assert result["reason"] == "urgency_detected"


def test_handoff_on_low_confidence(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    config = _base_ai_config()
    config["confidence_threshold"] = 0.95
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=config)
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Oi, quero marcar avaliacao.",
    )

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    assert result["status"] == "handoff"
    assert result["reason"] == "low_confidence"


def test_eligible_inbound_creates_ai_outbox_and_message(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Oi, quero agendar avaliacao para amanha.",
    )

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    assert result["status"] == "responded"
    outbox_count = db_session.scalar(
        select(func.count(OutboxMessage.id)).where(OutboxMessage.tenant_id == tenant_id)
    )
    assert outbox_count in {1, 2}

    outbound = db_session.scalar(
        select(Message).where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
    )
    assert outbound is not None
    assert outbound.status == "queued"


def test_inbound_contact_data_updates_patient_profile(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Meu nome e Guilherme Alves, meu email e guilherme.alves@example.com e quero agendar.",
    )

    patient = db_session.get(Patient, conversation.patient_id)
    patient.full_name = "Contato WhatsApp 1111"
    patient.email = None
    db_session.add(patient)
    db_session.commit()

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    refreshed_patient = db_session.get(Patient, patient.id)
    refreshed_conversation = db_session.get(Conversation, conversation.id)

    assert result["status"] == "responded"
    assert result.get("captured_profile", {}).get("patient_full_name") == "Guilherme Alves"
    assert refreshed_patient.full_name == "Guilherme Alves"
    assert refreshed_patient.email == "guilherme.alves@example.com"
    assert "dados_cadastrais_capturados" in (refreshed_conversation.tags or [])


def test_period_reply_suggests_slots_without_auto_booking(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="ManhÃ£",
    )

    prior_message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="outbound",
        channel="whatsapp",
        sender_type="ai",
        body="Tenho horÃ¡rios disponÃ­veis. Prefere manhÃ£, tarde ou noite?",
        message_type="text",
        payload={},
        status="sent",
    )
    db_session.add(prior_message)
    db_session.commit()

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    assert result["status"] == "responded"
    assert result.get("scheduling_mode") in {"slots_suggested", "booking_wizard_service_select"}

    appointment = db_session.scalar(
        select(Appointment).where(
            Appointment.tenant_id == tenant_id,
            Appointment.patient_id == conversation.patient_id,
            Appointment.origin == "ai_autoresponder",
        )
    )
    assert appointment is None


def test_idempotency_prevents_double_auto_reply(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Bom dia, consegue confirmar meu horario?",
    )

    first = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )
    second = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    assert first["status"] == "responded"
    assert second["status"] == "duplicate"

    outbox_count = db_session.scalar(select(func.count(OutboxMessage.id)).where(OutboxMessage.tenant_id == tenant_id))
    decision_count = db_session.scalar(
        select(func.count(AIAutoresponderDecision.id)).where(AIAutoresponderDecision.tenant_id == tenant_id)
    )
    assert outbox_count in {1, 2}
    assert decision_count == 1


def test_handoff_when_whatsapp_not_configured(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    db_session.execute(delete(WhatsAppAccount).where(WhatsAppAccount.tenant_id == tenant_id))
    db_session.commit()
    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quero agendar uma consulta.",
    )

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    assert result["status"] == "handoff"
    assert result["reason"] == "whatsapp_not_ready"


def test_handoff_when_whatsapp_token_invalid(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    account = db_session.scalar(select(WhatsAppAccount).where(WhatsAppAccount.tenant_id == tenant_id))
    account.phone_number_id = "1101713436353674"
    account.business_account_id = "936994182588219"
    account.access_token_encrypted = "mock-token-invalido"
    db_session.add(account)
    db_session.commit()

    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quero agendar para quinta-feira.",
    )

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )
    assert result["status"] == "handoff"
    assert result["reason"] == "whatsapp_not_ready"


def test_handoff_when_llm_timeout(monkeypatch, seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Gostaria de confirmar minha consulta.",
    )

    from app.services import ai_autoresponder_service

    def _raise_timeout(*args, **kwargs):
        raise TimeoutError("llm timeout")

    monkeypatch.setattr(ai_autoresponder_service, "run_llm_task", _raise_timeout)

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )
    assert result["status"] == "handoff"
    assert result["reason"] == "llm_error"


def test_prompt_includes_knowledge_base_when_configured(monkeypatch, seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    knowledge_setting = Setting(
        tenant_id=tenant_id,
        key="ai_knowledge_base.global",
        value={
            "clinic_profile": {
                "clinic_name": "ClÃ­nica Sorriso Sul Premium",
                "about": "Especialista em ortodontia estÃ©tica e atendimento humanizado.",
                "differentials": ["agenda estendida", "time clÃ­nico senior"],
            },
            "services": [
                {
                    "name": "AvaliaÃ§Ã£o ortodÃ´ntica",
                    "description": "Consulta inicial com plano de tratamento personalizado.",
                    "price_note": "a partir de R$ 190",
                }
            ],
            "faq": [
                {
                    "question": "VocÃªs atendem convÃªnio?",
                    "answer": "Atendemos particular e emitimos recibo para reembolso.",
                }
            ],
        },
        is_secret=False,
    )
    db_session.add(knowledge_setting)
    db_session.commit()

    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Oi, quero saber sobre avaliacao ortodontica.",
    )

    from app.services import ai_autoresponder_service

    captured_prompt: dict[str, str] = {}

    def _fake_run_llm_task(*args, **kwargs):
        captured_prompt["value"] = kwargs.get("prompt", "")
        return {
            "output": "Claro! A avaliaÃ§Ã£o ortodÃ´ntica estÃ¡ disponÃ­vel e posso te ajudar a agendar.",
            "metadata": {"provider": "mock", "model": "mock"},
        }

    monkeypatch.setattr(ai_autoresponder_service, "run_llm_task", _fake_run_llm_task)
    monkeypatch.setattr(
        ai_autoresponder_service,
        "classify_intent",
        lambda *args, **kwargs: {"output": '{"intent":"agendamento","confidence":0.89}'},
    )

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    assert result["status"] == "responded"
    prompt = captured_prompt.get("value", "")
    assert "Base de conhecimento operacional da clÃ­nica" in prompt
    assert "ClÃ­nica Sorriso Sul Premium" in prompt
    assert "AvaliaÃ§Ã£o ortodÃ´ntica" in prompt

def test_scheduling_slots_message_is_structured_as_numbered_list(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quais horarios voces tem para avaliacao?",
    )

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    assert result["status"] == "responded"
    assert result.get("scheduling_mode") in {"slots_suggested", "booking_wizard_service_select"}
    assert outbound is not None
    if result.get("scheduling_mode") == "slots_suggested":
        assert "1)" in (outbound.body or "")
        assert "|" not in (outbound.body or "")
    else:
        assert (outbound.payload or {}).get("mode") == "booking_wizard_service_select"


def test_booking_wizard_button_flow_creates_appointment(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    conversation, first_inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quero agendar",
    )

    first_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=first_inbound.id,
    )
    assert first_result["status"] == "responded"
    assert first_result.get("scheduling_mode") == "booking_wizard_service_select"

    latest_outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    assert latest_outbound is not None
    assert latest_outbound.message_type == "interactive_list"
    service_rows = (((latest_outbound.payload or {}).get("interactive") or {}).get("rows") or [])
    assert service_rows
    service_option_id = service_rows[0]["id"]

    second_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="OpÃ§Ã£o 1",
        message_type="interactive_list_reply",
        payload={"interactive_reply": {"id": service_option_id, "title": "OpÃ§Ã£o 1"}},
    )
    second_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=second_inbound.id,
    )
    assert second_result["status"] == "responded"
    assert second_result.get("scheduling_mode") == "booking_wizard_unit_select"

    latest_outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    unit_rows = (((latest_outbound.payload or {}).get("interactive") or {}).get("rows") or [])
    assert unit_rows
    unit_option_id = unit_rows[0]["id"]

    third_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="OpÃ§Ã£o 1",
        message_type="interactive_list_reply",
        payload={"interactive_reply": {"id": unit_option_id, "title": "OpÃ§Ã£o 1"}},
    )
    third_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=third_inbound.id,
    )
    assert third_result["status"] == "responded"
    assert third_result.get("scheduling_mode") == "booking_wizard_day_select"

    latest_outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    day_rows = (((latest_outbound.payload or {}).get("interactive") or {}).get("rows") or [])
    assert day_rows
    day_option_id = day_rows[0]["id"]

    fourth_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="OpÃ§Ã£o 1",
        message_type="interactive_list_reply",
        payload={"interactive_reply": {"id": day_option_id, "title": "OpÃ§Ã£o 1"}},
    )
    fourth_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=fourth_inbound.id,
    )
    assert fourth_result["status"] == "responded"
    assert fourth_result.get("scheduling_mode") == "booking_wizard_time_select"

    latest_outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    time_rows = (((latest_outbound.payload or {}).get("interactive") or {}).get("rows") or [])
    assert time_rows
    time_option_id = time_rows[0]["id"]

    fifth_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="OpÃ§Ã£o 1",
        message_type="interactive_list_reply",
        payload={"interactive_reply": {"id": time_option_id, "title": "OpÃ§Ã£o 1"}},
    )
    fifth_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=fifth_inbound.id,
    )
    assert fifth_result["status"] == "responded"
    assert fifth_result.get("scheduling_mode") == "booking_wizard_confirm"

    latest_outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    assert latest_outbound.message_type == "interactive_buttons"
    confirm_buttons = (((latest_outbound.payload or {}).get("interactive") or {}).get("buttons") or [])
    assert confirm_buttons
    confirm_option_id = confirm_buttons[0]["id"]

    confirm_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="Sim",
        message_type="interactive_button_reply",
        payload={"interactive_reply": {"id": confirm_option_id, "title": "Sim"}},
    )
    confirm_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=confirm_inbound.id,
    )
    assert confirm_result["status"] == "responded"
    assert confirm_result.get("scheduling_mode") in {"appointment_created", "appointment_already_created"}

    appointment = db_session.scalar(
        select(Appointment).where(
            Appointment.tenant_id == tenant_id,
            Appointment.patient_id == conversation.patient_id,
            Appointment.origin == "ai_autoresponder",
        )
    )
    assert appointment is not None
    assert appointment.status == "agendada"
    assert appointment.confirmation_status == "confirmada"


def test_followup_slot_option_confirms_and_persists_appointment(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    conversation, first_inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quero agendar clareamento dental",
    )

    first_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=first_inbound.id,
    )
    assert first_result["status"] == "responded"
    assert first_result.get("scheduling_mode") == "booking_wizard_service_select"

    latest_outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    service_rows = (((latest_outbound.payload or {}).get("interactive") or {}).get("rows") or [])
    assert service_rows
    service_id = service_rows[0]["id"]

    service_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="Opção 1",
        message_type="interactive_list_reply",
        payload={"interactive_reply": {"id": service_id, "title": "Opção 1"}},
    )
    service_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=service_inbound.id,
    )
    assert service_result["status"] == "responded"
    assert service_result.get("scheduling_mode") == "booking_wizard_unit_select"

    latest_outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    unit_rows = (((latest_outbound.payload or {}).get("interactive") or {}).get("rows") or [])
    assert unit_rows
    unit_id = unit_rows[0]["id"]

    unit_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="Opção 1",
        message_type="interactive_list_reply",
        payload={"interactive_reply": {"id": unit_id, "title": "Opção 1"}},
    )
    unit_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=unit_inbound.id,
    )
    assert unit_result["status"] == "responded"
    assert unit_result.get("scheduling_mode") == "booking_wizard_day_select"

    latest_outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    day_rows = (((latest_outbound.payload or {}).get("interactive") or {}).get("rows") or [])
    assert day_rows
    day_id = day_rows[0]["id"]

    day_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="Opção 1",
        message_type="interactive_list_reply",
        payload={"interactive_reply": {"id": day_id, "title": "Opção 1"}},
    )
    day_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=day_inbound.id,
    )
    assert day_result["status"] == "responded"
    assert day_result.get("scheduling_mode") == "booking_wizard_time_select"

    latest_outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    time_rows = (((latest_outbound.payload or {}).get("interactive") or {}).get("rows") or [])
    assert time_rows
    time_id = time_rows[0]["id"]

    select_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="Opção 1",
        message_type="interactive_list_reply",
        payload={"interactive_reply": {"id": time_id, "title": "Opção 1"}},
    )
    select_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=select_inbound.id,
    )
    assert select_result["status"] == "responded"
    assert select_result.get("scheduling_mode") == "booking_wizard_confirm"

    confirm_prompt = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    assert confirm_prompt is not None
    assert confirm_prompt.message_type == "interactive_buttons"
    confirm_buttons = (((confirm_prompt.payload or {}).get("interactive") or {}).get("buttons") or [])
    assert confirm_buttons
    confirm_yes_id = confirm_buttons[0]["id"]

    confirm_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="Sim",
        message_type="interactive_button_reply",
        payload={"interactive_reply": {"id": confirm_yes_id, "title": "Sim"}},
    )
    confirm_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=confirm_inbound.id,
    )

    assert confirm_result["status"] == "responded"
    assert confirm_result.get("scheduling_mode") in {"appointment_created", "appointment_already_created"}

    appointment = db_session.scalar(
        select(Appointment).where(
            Appointment.tenant_id == tenant_id,
            Appointment.patient_id == conversation.patient_id,
            Appointment.origin == "ai_autoresponder",
        )
    )
    assert appointment is not None
    assert appointment.status == "agendada"
    assert appointment.confirmation_status == "confirmada"
    db_session.refresh(conversation)
    assert conversation.status == "aberta"

    cpf_request_message = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    assert cpf_request_message is not None
    assert (cpf_request_message.payload or {}).get("mode") == "booking_request_cpf_after_booking"
    assert "cpf" in (cpf_request_message.body or "").lower()


def test_followup_interactive_reply_option_confirms_and_persists_appointment(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    conversation, first_inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quero agendar clareamento dental",
    )

    first_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=first_inbound.id,
    )
    assert first_result["status"] == "responded"
    assert first_result.get("scheduling_mode") == "booking_wizard_service_select"

    latest_outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    service_rows = (((latest_outbound.payload or {}).get("interactive") or {}).get("rows") or [])
    assert service_rows

    service_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="Opção 1",
        message_type="interactive_list_reply",
        payload={"interactive_reply": {"id": service_rows[0]["id"], "title": "Opção 1"}},
    )
    service_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=service_inbound.id,
    )
    assert service_result["status"] == "responded"
    assert service_result.get("scheduling_mode") == "booking_wizard_unit_select"

    latest_outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    unit_rows = (((latest_outbound.payload or {}).get("interactive") or {}).get("rows") or [])
    assert unit_rows
    unit_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="Opção 1",
        message_type="interactive_list_reply",
        payload={"interactive_reply": {"id": unit_rows[0]["id"], "title": "Opção 1"}},
    )
    unit_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=unit_inbound.id,
    )
    assert unit_result["status"] == "responded"
    assert unit_result.get("scheduling_mode") == "booking_wizard_day_select"

    latest_outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    day_rows = (((latest_outbound.payload or {}).get("interactive") or {}).get("rows") or [])
    assert day_rows
    day_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="Opção 1",
        message_type="interactive_list_reply",
        payload={"interactive_reply": {"id": day_rows[0]["id"], "title": "Opção 1"}},
    )
    day_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=day_inbound.id,
    )
    assert day_result["status"] == "responded"
    assert day_result.get("scheduling_mode") == "booking_wizard_time_select"

    latest_outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    time_rows = (((latest_outbound.payload or {}).get("interactive") or {}).get("rows") or [])
    assert time_rows
    select_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="Opção 1",
        message_type="interactive_list_reply",
        payload={"interactive_reply": {"id": time_rows[0]["id"], "title": "Opção 1"}},
    )
    select_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=select_inbound.id,
    )
    assert select_result["status"] == "responded"
    assert select_result.get("scheduling_mode") == "booking_wizard_confirm"

    confirm_prompt = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    assert confirm_prompt is not None
    assert confirm_prompt.message_type == "interactive_buttons"
    confirm_buttons = (((confirm_prompt.payload or {}).get("interactive") or {}).get("buttons") or [])
    assert confirm_buttons
    confirm_yes_id = confirm_buttons[0]["id"]

    confirm_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="Sim",
        message_type="interactive_button_reply",
        payload={"interactive_reply": {"id": confirm_yes_id, "title": "Sim"}},
    )
    confirm_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=confirm_inbound.id,
    )

    assert confirm_result["status"] == "responded"
    assert confirm_result.get("scheduling_mode") in {"appointment_created", "appointment_already_created"}

    appointment = db_session.scalar(
        select(Appointment).where(
            Appointment.tenant_id == tenant_id,
            Appointment.patient_id == conversation.patient_id,
            Appointment.origin == "ai_autoresponder",
        )
    )
    assert appointment is not None
    assert appointment.status == "agendada"
    assert appointment.confirmation_status == "confirmada"

    cpf_prompt = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    assert cpf_prompt is not None
    assert (cpf_prompt.payload or {}).get("mode") == "booking_request_cpf_after_booking"

    cpf_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="52998224725",
    )
    cpf_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=cpf_inbound.id,
    )
    assert cpf_result["status"] == "responded"
    assert cpf_result.get("scheduling_mode") == "booking_post_confirmation_options"

    latest_outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
            Message.message_type == "interactive_buttons",
        )
        .order_by(Message.created_at.desc())
    )
    assert latest_outbound is not None
    buttons = (((latest_outbound.payload or {}).get("interactive") or {}).get("buttons") or [])
    close_button = next((item for item in buttons if (item.get("id") or "") == "post_info_close"), None)
    assert close_button is not None

    close_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="Encerrar conversa",
        message_type="interactive_button_reply",
        payload={"interactive_reply": {"id": "post_info_close", "title": "Encerrar conversa"}},
    )
    close_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=close_inbound.id,
    )
    db_session.refresh(conversation)
    assert close_result["status"] == "responded"
    assert close_result.get("scheduling_mode") == "booking_close_with_summary"
    assert conversation.status == "finalizada"


def test_post_appointment_menu_rebook_starts_new_wizard_without_anchor(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Novo agendamento",
    )
    inbound.message_type = "interactive_button_reply"
    inbound.payload = {"interactive_reply": {"id": "post_menu_rebook", "title": "Novo agendamento"}}
    db_session.add(inbound)
    db_session.commit()

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    assert result["status"] == "responded"
    assert result.get("scheduling_mode") == "booking_wizard_service_select"
    assert outbound is not None
    assert outbound.message_type == "interactive_list"


def test_post_appointment_menu_close_button_closes_conversation(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="botao fechar",
    )
    inbound.message_type = "interactive_button_reply"
    inbound.payload = {"interactive_reply": {"id": "post_menu_close", "title": "Encerrar conversa"}}
    db_session.add(inbound)
    db_session.commit()

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    db_session.refresh(conversation)
    assert result["status"] == "responded"
    assert result.get("scheduling_mode") == "booking_close_with_summary"
    assert conversation.status == "finalizada"


def test_booking_confirm_detects_slot_conflict_and_returns_new_time_options(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    conversation, _ = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Oi",
    )
    unit = db_session.scalar(
        select(Unit).where(
            Unit.tenant_id == tenant_id,
            Unit.is_active.is_(True),
        )
    )
    assert unit is not None
    professional = _ensure_professional(
        db_session,
        tenant_id=tenant_id,
        unit_id=unit.id,
        full_name="Dra Conflito IA",
    )

    selected_day = (datetime.now(UTC) + timedelta(days=3)).date()
    starts_at = datetime.now(UTC) + timedelta(days=3, hours=2)
    ends_at = starts_at + timedelta(minutes=60)

    other_phone = f"5511999{uuid4().hex[:7]}"
    other_patient = Patient(
        tenant_id=tenant_id,
        full_name="Paciente Ocupando Horario",
        phone=other_phone,
        normalized_phone=other_phone,
        status="ativo",
        origin="manual",
        lgpd_consent=True,
        marketing_opt_in=True,
        tags_cache=[],
    )
    db_session.add(other_patient)
    db_session.flush()

    existing_conflict = Appointment(
        tenant_id=tenant_id,
        patient_id=other_patient.id,
        unit_id=unit.id,
        professional_id=professional.id,
        procedure_type="Clareamento dental",
        starts_at=starts_at,
        ends_at=ends_at,
        origin="manual",
        status="agendada",
    )
    db_session.add(existing_conflict)

    stale_confirm = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="outbound",
        channel="whatsapp",
        sender_type="ai",
        body="Confirma este agendamento?",
        message_type="interactive_buttons",
        payload={
            "mode": "booking_wizard_confirm",
            "scheduling": {
                "procedure_type": "InstalaÃƒÂ§ÃƒÂ£o de lentes",
                "unit_id": str(unit.id),
                "requested_date": selected_day.isoformat(),
                "selected_slot": {
                    "id": "time_1",
                    "label": "quinta-feira, 16/04 ÃƒÂ s 10:00",
                    "starts_at_utc": starts_at.isoformat(),
                    "ends_at_utc": ends_at.isoformat(),
                    "starts_at_local": starts_at.isoformat(),
                    "professional_id": str(professional.id),
                    "professional_name": professional.full_name,
                    "time": "10:00",
                },
                "period": "morning",
            },
        },
        status="sent",
    )
    db_session.add(stale_confirm)
    db_session.commit()

    inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="Sim",
        message_type="interactive_button_reply",
        payload={"interactive_reply": {"id": "confirm_yes", "title": "Sim"}},
    )
    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    assert result["status"] == "responded"
    assert result.get("scheduling_mode") == "booking_wizard_time_select"
    assert outbound is not None
    assert outbound.message_type == "interactive_list"
    scheduling = (outbound.payload or {}).get("scheduling") or {}
    assert scheduling.get("reason") == "selected_slot_no_longer_available"


def test_followup_option_does_not_use_stale_slots_anchor(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    first_date = (datetime.now(UTC) + timedelta(days=1)).strftime("%d/%m")
    second_date = (datetime.now(UTC) + timedelta(days=2)).strftime("%d/%m")
    conversation, first_inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text=f"Tem horario para clareamento no dia {first_date}?",
    )

    first_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=first_inbound.id,
    )
    assert first_result["status"] == "responded"
    assert first_result.get("scheduling_mode") in {"slots_suggested", "booking_wizard_service_select"}

    _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text=f"Quero agendar para raspagem no dia {second_date}",
    )
    confirm_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="1",
    )
    confirm_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=confirm_inbound.id,
    )

    assert confirm_result["status"] == "responded"
    assert confirm_result.get("scheduling_mode") == "followup_anchor_stale"

    last_outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    assert last_outbound is not None
    assert "me confirme novamente a data e hora desejadas" in (last_outbound.body or "").lower()

    appointment = db_session.scalar(
        select(Appointment).where(
            Appointment.tenant_id == tenant_id,
            Appointment.patient_id == conversation.patient_id,
            Appointment.origin == "ai_autoresponder",
        )
    )
    assert appointment is None


def test_scheduling_uses_inbound_procedure_over_context(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    future_date = (datetime.now(UTC) + timedelta(days=2)).strftime("%d/%m")
    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text=f"Quais horarios voce tem para limpeza no dia {future_date}?",
    )

    prior_message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="outbound",
        channel="whatsapp",
        sender_type="ai",
        body="Temos vagas para instalacao de lentes ao longo da semana.",
        message_type="text",
        payload={},
        status="sent",
    )
    db_session.add(prior_message)
    db_session.commit()

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    outbound = db_session.scalar(
        select(Message).where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
    )
    assert result["status"] == "responded"
    assert result.get("scheduling_mode") in {"slots_suggested", "booking_wizard_service_select"}
    assert outbound is not None
    normalized_outbound = (outbound.body or "").lower()
    assert "limpeza" in normalized_outbound
    assert "lente" not in normalized_outbound


def test_scheduling_uses_recent_context_procedure_when_inbound_is_ambiguous(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quais dias vcs tem disponiveis?",
    )

    older_catalog_message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="outbound",
        channel="whatsapp",
        sender_type="ai",
        body="Oferecemos avaliacao, lentes de contato dental, clareamento e reabilitacao estetica.",
        message_type="text",
        payload={},
        status="sent",
    )
    latest_service_message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="outbound",
        channel="whatsapp",
        sender_type="ai",
        body="As lentes de contato dental comecam a partir de R$ 1.500 e posso te mostrar os dias disponiveis.",
        message_type="text",
        payload={},
        status="sent",
    )
    db_session.add(older_catalog_message)
    db_session.add(latest_service_message)
    db_session.commit()

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    assert result["status"] == "responded"
    assert result.get("scheduling_mode") in {
        "slots_suggested",
        "no_slots_general",
        "no_slots_for_period",
        "booking_wizard_service_select",
    }
    assert outbound is not None
    scheduling = (outbound.payload or {}).get("scheduling") or {}
    if result.get("scheduling_mode") == "booking_wizard_service_select":
        services = scheduling.get("services") or []
        normalized_services = [str(item).lower() for item in services]
        assert any("lente" in item for item in normalized_services)
    else:
        assert scheduling.get("procedure_type") == "InstalaÃ§Ã£o de lentes"


def test_scheduling_days_request_returns_day_options_instead_of_time_slots(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quero saber os dias disponiveis para avaliacao de lentes de contato",
    )

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    assert result["status"] == "responded"
    assert result.get("scheduling_mode") == "booking_wizard_day_select"
    assert outbound is not None
    assert outbound.message_type == "interactive_list"
    rows = (((outbound.payload or {}).get("interactive") or {}).get("rows") or [])
    assert rows
    assert str(rows[0].get("id") or "").startswith("day_")
    scheduling = (outbound.payload or {}).get("scheduling") or {}
    assert scheduling.get("procedure_type") == "InstalaÃ§Ã£o de lentes"


def test_new_request_ignores_stale_wizard_confirmation_state(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    conversation, _ = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Oi",
    )

    unit = db_session.scalar(
        select(Unit).where(
            Unit.tenant_id == tenant_id,
            Unit.is_active.is_(True),
        )
    )
    assert unit is not None

    selected_day = (datetime.now(UTC) + timedelta(days=2)).date()
    starts_at_utc = datetime.now(UTC) + timedelta(days=2, hours=3)
    ends_at_utc = starts_at_utc + timedelta(minutes=60)
    selected_slot = {
        "id": "time_1100",
        "label": "sexta-feira, 17/04 Ã s 11:00",
        "starts_at_utc": starts_at_utc.isoformat(),
        "ends_at_utc": ends_at_utc.isoformat(),
        "starts_at_local": starts_at_utc.isoformat(),
        "professional_id": None,
        "professional_name": "Equipe clÃ­nica",
        "time": "11:00",
    }

    stale_wizard_message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="outbound",
        channel="whatsapp",
        sender_type="ai",
        body="Confirma este agendamento?",
        message_type="interactive_buttons",
        payload={
            "mode": "booking_wizard_confirm",
            "scheduling": {
                "procedure_type": "InstalaÃ§Ã£o de lentes",
                "unit_id": str(unit.id),
                "requested_date": selected_day.isoformat(),
                "selected_slot": selected_slot,
            },
        },
        status="sent",
    )
    latest_non_wizard_message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="outbound",
        channel="whatsapp",
        sender_type="ai",
        body="O clareamento dental Ã© supervisionado e parte de R$ 650.",
        message_type="text",
        payload={},
        status="sent",
    )
    db_session.add(stale_wizard_message)
    db_session.add(latest_non_wizard_message)
    db_session.commit()

    inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="quais dias disponÃ­veis para clareamento?",
    )
    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    assert result["status"] == "responded"
    assert result.get("scheduling_mode") == "booking_wizard_day_select"
    assert outbound is not None
    scheduling = (outbound.payload or {}).get("scheduling") or {}
    assert scheduling.get("procedure_type") == "Clareamento dental"
    assert outbound.message_type == "interactive_list"
    rows = (((outbound.payload or {}).get("interactive") or {}).get("rows") or [])
    assert rows
    assert str(rows[0].get("id") or "").startswith("day_")


def test_greeting_boa_noite_does_not_trigger_period_scheduling(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Boa noite",
    )

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    assert result["status"] == "responded"
    assert result.get("scheduling_mode") == "welcome_message_start"
    assert outbound is not None
    assert outbound.message_type == "interactive_list"
    normalized = (outbound.body or "").lower()
    assert "que bom te ver por aqui" in normalized
    assert "encontrei estes horÃ¡rios" not in normalized
    assert "encontrei estes horarios" not in normalized
    rows = (((outbound.payload or {}).get("interactive") or {}).get("rows") or [])
    row_ids = {str(item.get("id") or "") for item in rows}
    assert "menu_schedule" in row_ids
    assert "menu_services" in row_ids
    assert "menu_support" in row_ids
    assert "menu_suggestion" in row_ids
    assert "menu_complaint" in row_ids
    assert "menu_human" in row_ids


def test_greeting_with_intent_does_not_use_welcome_start_message(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Oi, quero agendar limpeza",
    )

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    assert result["status"] == "responded"
    assert result.get("scheduling_mode") != "welcome_message_start"


def test_idle_conversation_over_twenty_minutes_restarts_with_welcome_menu(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    conversation, first_inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quero agendar limpeza",
    )
    first_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=first_inbound.id,
    )
    assert first_result["status"] == "responded"

    latest_message = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
        )
        .order_by(Message.created_at.desc())
    )
    assert latest_message is not None

    second_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="Quero horario para amanha",
    )
    second_inbound.created_at = latest_message.created_at + timedelta(minutes=21)
    db_session.add(second_inbound)
    db_session.commit()

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=second_inbound.id,
    )

    outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    assert result["status"] == "responded"
    assert result.get("scheduling_mode") in {"welcome_message_start", "booking_wizard_resume_or_restart"}
    assert outbound is not None
    assert outbound.message_type in {"interactive_list", "interactive_buttons"}
    scheduling_metadata = (outbound.payload or {}).get("scheduling") or {}
    assert scheduling_metadata.get("reason") in {"idle_timeout_restart", "idle_timeout_resume_options"}
    assert float(scheduling_metadata.get("idle_minutes") or 0) >= 20


def test_welcome_message_uses_custom_greeting_from_knowledge_base(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _upsert_ai_knowledge_base_setting(
        db_session,
        tenant_id=tenant_id,
        value={
            "clinic_profile": {
                "clinic_name": "Clinica Exemplo",
                "welcome_greeting_example": (
                    "Seja bem-vindo(a)! Eu sou a assistente da Clinica Exemplo.\n"
                    "Escolha uma opcao para comecarmos."
                ),
            }
        },
    )
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Oi",
    )

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    assert result["status"] == "responded"
    assert result.get("scheduling_mode") == "welcome_message_start"
    assert outbound is not None
    assert "Seja bem-vindo(a)! Eu sou a assistente da Clinica Exemplo." in (outbound.body or "")
    assert outbound.message_type == "interactive_list"


def test_service_catalog_request_opens_service_selection_wizard(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Boa noite, quais serviÃ§os vocÃªs oferecem?",
    )

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    assert result["status"] == "responded"
    assert result.get("scheduling_mode") == "welcome_message_start"
    assert outbound is not None
    assert outbound.message_type == "interactive_list"
    rows = (((outbound.payload or {}).get("interactive") or {}).get("rows") or [])
    assert rows
    assert any(str(item.get("id") or "") == "menu_services" for item in rows)

    second_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="ServiÃ§os",
        message_type="interactive_list_reply",
        payload={"interactive_reply": {"id": "menu_services", "title": "ServiÃ§os"}},
    )
    second_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=second_inbound.id,
    )
    assert second_result["status"] == "responded"
    assert second_result.get("scheduling_mode") == "booking_wizard_service_select"

    wizard_outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    assert wizard_outbound is not None
    assert wizard_outbound.message_type == "interactive_list"
    wizard_rows = (((wizard_outbound.payload or {}).get("interactive") or {}).get("rows") or [])
    assert wizard_rows
    assert str(wizard_rows[0].get("id") or "").startswith("svc_")


def test_close_conversation_request_sets_conversation_closed(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Encerrar conversa",
    )

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    db_session.refresh(conversation)
    assert result["status"] == "ignored"
    assert result["reason"] == "conversation_closed_by_user"
    assert conversation.status == "finalizada"


def test_scheduling_typo_claramente_dentario_maps_to_clareamento(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    future_date = (datetime.now(UTC) + timedelta(days=2)).strftime("%d/%m")
    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text=f"Quero saber os horarios para claramente dentario no dia {future_date}",
    )

    prior_message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="outbound",
        channel="whatsapp",
        sender_type="ai",
        body="Temos vagas para limpeza odontologica ao longo da semana.",
        message_type="text",
        payload={},
        status="sent",
    )
    db_session.add(prior_message)
    db_session.commit()

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    outbound = db_session.scalar(
        select(Message).where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
    )
    assert result["status"] == "responded"
    assert result.get("scheduling_mode") in {"slots_suggested", "booking_wizard_service_select"}
    assert outbound is not None
    normalized_outbound = (outbound.body or "").lower()
    assert "clareamento" in normalized_outbound
    assert "limpeza" not in normalized_outbound


def test_scheduling_with_requested_date_lists_more_than_three_slots(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    future_date = (datetime.now(UTC) + timedelta(days=2)).strftime("%d/%m")
    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text=f"Quais horarios voces tem para limpeza no dia {future_date}?",
    )

    db_session.execute(delete(Appointment).where(Appointment.tenant_id == tenant_id))
    db_session.commit()

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    outbound = db_session.scalar(
        select(Message).where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
    )
    assert result["status"] == "responded"
    assert result.get("scheduling_mode") in {"slots_suggested", "booking_wizard_service_select"}
    assert outbound is not None
    assert "4)" in (outbound.body or "")


def test_scheduling_falls_back_to_30_min_slots_when_no_60_min_window(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    config = _base_ai_config()
    config["business_hours"] = {
        "timezone": "America/Sao_Paulo",
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "start": "09:00",
        "end": "11:30",
    }
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=config)
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Tem horarios para clareamento?",
    )

    unit = db_session.scalar(
        select(Unit).where(Unit.tenant_id == tenant_id, Unit.is_active.is_(True)).order_by(Unit.created_at.asc())
    )
    assert unit is not None

    conversation.unit_id = unit.id
    db_session.add(conversation)

    db_session.execute(delete(Appointment).where(Appointment.tenant_id == tenant_id))

    # Janela local equivalente (America/Sao_Paulo): 09:00-11:30.
    # Ocupa 09:00-10:00 e 10:30-11:30, restando apenas 10:00-10:30.
    local_day_base_utc = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0) + timedelta(days=1)
    db_session.add(
        Appointment(
            tenant_id=tenant_id,
            patient_id=conversation.patient_id,
            unit_id=unit.id,
            procedure_type="Clareamento",
            starts_at=local_day_base_utc,
            ends_at=local_day_base_utc + timedelta(minutes=60),
            status="agendada",
            confirmation_status="pendente",
            origin="manual",
        )
    )
    db_session.add(
        Appointment(
            tenant_id=tenant_id,
            patient_id=conversation.patient_id,
            unit_id=unit.id,
            procedure_type="Clareamento",
            starts_at=local_day_base_utc + timedelta(minutes=90),
            ends_at=local_day_base_utc + timedelta(minutes=150),
            status="agendada",
            confirmation_status="pendente",
            origin="manual",
        )
    )
    db_session.commit()

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    outbound = db_session.scalar(
        select(Message).where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
    )
    assert result["status"] == "responded"
    assert result.get("scheduling_mode") in {"slots_suggested", "booking_wizard_service_select"}
    assert outbound is not None
    assert "10:00" in (outbound.body or "")


def test_llm_response_removes_redundant_name_greeting(monkeypatch, seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quais servicos vcs oferecem?",
    )

    patient = db_session.get(Patient, conversation.patient_id)
    patient.full_name = "Guilherme Gomes"
    db_session.add(patient)
    db_session.commit()

    from app.services import ai_autoresponder_service

    monkeypatch.setattr(
        ai_autoresponder_service,
        "classify_intent",
        lambda *args, **kwargs: {"output": '{"intent":"informacao","confidence":0.95}'},
    )
    monkeypatch.setattr(
        ai_autoresponder_service,
        "run_llm_task",
        lambda *args, **kwargs: {
            "output": "Ola, Guilherme! Oferecemos avaliacao, lentes e clareamento. Posso te ajudar com um agendamento?",
            "metadata": {"provider": "mock", "model": "mock"},
        },
    )

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    outbound = db_session.scalar(
        select(Message).where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
    )
    assert result["status"] == "responded"
    assert outbound is not None
    normalized_body = (outbound.body or "").lower().replace("Ã¡", "a")
    assert "ola, guilherme" not in normalized_body
    assert normalized_body.startswith("ola!")


def test_llm_cannot_claim_appointment_confirmation_without_persistence(monkeypatch, seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quanto custa o clareamento?",
    )

    from app.services import ai_autoresponder_service

    monkeypatch.setattr(
        ai_autoresponder_service,
        "classify_intent",
        lambda *args, **kwargs: {"output": '{"intent":"informacao","confidence":0.99}'},
    )
    monkeypatch.setattr(
        ai_autoresponder_service,
        "run_llm_task",
        lambda *args, **kwargs: {
            "output": "Agendado o clareamento para quarta-feira, 15/04 as 09:00.",
            "metadata": {"provider": "mock", "model": "mock"},
        },
    )

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    outbound = db_session.scalar(
        select(Message).where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
    )
    assert result["status"] == "responded"
    assert outbound is not None
    assert "Agendado" not in (outbound.body or "")


def test_closed_conversation_reopens_when_patient_sends_new_message(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    conversation, _ = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="oi",
    )
    conversation.status = "finalizada"
    db_session.add(conversation)
    db_session.commit()

    inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="Oi, voltei",
    )
    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    db_session.refresh(conversation)
    assert result["status"] == "responded"
    assert conversation.status == "aberta"


def test_confirm_step_includes_change_time_button(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    conversation, first_inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Tem horario para clareamento dental?",
    )
    first_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=first_inbound.id,
    )
    assert first_result.get("scheduling_mode") in {"slots_suggested", "booking_wizard_service_select"}

    pick_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="1",
    )
    pick_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=pick_inbound.id,
    )
    assert pick_result.get("scheduling_mode") == "booking_wizard_confirm"

    confirm_prompt = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )
    assert confirm_prompt is not None
    buttons = (((confirm_prompt.payload or {}).get("interactive") or {}).get("buttons") or [])
    ids = {str(item.get("id") or "") for item in buttons}
    assert "confirm_change_time" in ids


def test_followup_slot_change_day_action_opens_day_selection(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Tem horarios para limpeza?",
    )
    first_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )
    assert first_result.get("scheduling_mode") in {"slots_suggested", "booking_wizard_service_select"}

    change_day_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="Trocar dia",
        message_type="interactive_list_reply",
        payload={"interactive_reply": {"id": "slot_change_day", "title": "Trocar dia"}},
    )
    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=change_day_inbound.id,
    )

    assert result["status"] == "responded"
    assert result.get("scheduling_mode") == "booking_wizard_day_select"


def test_explicit_availability_without_service_starts_service_step(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quais horarios disponiveis voces tem?",
    )
    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    assert result["status"] == "responded"
    assert result.get("scheduling_mode") == "booking_wizard_service_select"


def test_wizard_expired_session_restarts_from_service(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    conversation, _ = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="oi",
    )
    stale = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="outbound",
        channel="whatsapp",
        sender_type="ai",
        body="Escolha a clÃ­nica.",
        message_type="interactive_list",
        payload={
            "mode": "booking_wizard_unit_select",
            "scheduling": {
                "wizard_step": "unit",
                "session_token": "sessao_antiga",
                "step_expires_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
                "units": [{"id": str(uuid4()), "name": "Unidade 1", "option_id": "unit_1"}],
            },
        },
        status="sent",
        created_at=datetime.now(UTC) - timedelta(minutes=40),
    )
    db_session.add(stale)
    db_session.commit()

    inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="unit_1",
        message_type="interactive_list_reply",
        payload={"interactive_reply": {"id": "unit_1", "title": "Unidade 1"}},
    )
    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    assert result["status"] == "responded"
    assert result.get("scheduling_mode") == "booking_wizard_service_select"


def test_confirm_change_time_action_returns_time_step(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    conversation, first_inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Tem horario para clareamento?",
    )
    first_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=first_inbound.id,
    )
    assert first_result.get("scheduling_mode") in {"slots_suggested", "booking_wizard_service_select"}

    pick_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="1",
    )
    pick_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=pick_inbound.id,
    )
    assert pick_result.get("scheduling_mode") == "booking_wizard_confirm"

    change_time_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="Trocar horÃ¡rio",
        message_type="interactive_button_reply",
        payload={"interactive_reply": {"id": "confirm_change_time", "title": "Trocar horÃ¡rio"}},
    )
    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=change_time_inbound.id,
    )
    assert result["status"] == "responded"
    assert result.get("scheduling_mode") == "booking_wizard_time_select"


def test_support_menu_selection_adds_support_tag(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Oi",
    )
    first_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )
    assert first_result.get("scheduling_mode") == "welcome_message_start"

    support_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="Suporte",
        message_type="interactive_list_reply",
        payload={"interactive_reply": {"id": "menu_support", "title": "Suporte"}},
    )
    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=support_inbound.id,
    )

    db_session.refresh(conversation)
    assert result["status"] == "responded"
    assert result.get("scheduling_mode") == "booking_wizard_support_followup"
    assert "menu_suporte" in (conversation.tags or [])

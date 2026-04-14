from uuid import uuid4
from sqlalchemy import delete, func, select

from app.models import (
    AIAutoresponderDecision,
    Appointment,
    Conversation,
    Message,
    OutboxMessage,
    Patient,
    Setting,
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
    assert outbox_count == 1

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


def test_period_reply_creates_appointment_automatically(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Manhã",
    )

    prior_message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="outbound",
        channel="whatsapp",
        sender_type="ai",
        body="Tenho horários disponíveis. Prefere manhã, tarde ou noite?",
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

    appointment = db_session.scalar(
        select(Appointment).where(
            Appointment.tenant_id == tenant_id,
            Appointment.patient_id == conversation.patient_id,
            Appointment.origin == "ai_autoresponder",
        )
    )

    assert result["status"] == "responded"
    assert result.get("scheduling_mode") == "appointment_created"
    assert appointment is not None
    assert appointment.status == "agendada"
    assert appointment.confirmation_status == "confirmada"


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
    assert outbox_count == 1
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
                "clinic_name": "Clínica Sorriso Sul Premium",
                "about": "Especialista em ortodontia estética e atendimento humanizado.",
                "differentials": ["agenda estendida", "time clínico senior"],
            },
            "services": [
                {
                    "name": "Avaliação ortodôntica",
                    "description": "Consulta inicial com plano de tratamento personalizado.",
                    "price_note": "a partir de R$ 190",
                }
            ],
            "faq": [
                {
                    "question": "Vocês atendem convênio?",
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
            "output": "Claro! A avaliação ortodôntica está disponível e posso te ajudar a agendar.",
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
    assert "Base de conhecimento operacional da clínica" in prompt
    assert "Clínica Sorriso Sul Premium" in prompt
    assert "Avaliação ortodôntica" in prompt

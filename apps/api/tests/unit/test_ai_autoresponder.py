from datetime import UTC, datetime, timedelta
from uuid import uuid4
from sqlalchemy import delete, func, select

from app.models import (
    AIAutoresponderDecision,
    Appointment,
    Conversation,
    LinkFlowSession,
    Message,
    OutboxMessage,
    Patient,
    PatientContact,
    Professional,
    Setting,
    Unit,
    WhatsAppAccount,
)
from app.services.ai_autoresponder_service import (
    CPF_CONTACT_CHANNEL,
    _capture_patient_registration_from_inbound,
    _list_available_slots,
    _patient_saved_cpf,
    build_official_visit_guidance_response,
    process_inbound_message,
)


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


def _create_conversation_with_inbound(db_session, *, tenant_id, inbound_text: str, channel: str = "whatsapp"):
    suffix = uuid4().hex[:8]
    is_webchat = channel == "webchat"
    phone = f"webchat{suffix}" if is_webchat else f"5511940{suffix}"
    patient = Patient(
        tenant_id=tenant_id,
        full_name="Paciente Webchat" if is_webchat else f"Paciente Teste {suffix}",
        phone=phone,
        normalized_phone=phone,
        status="ativo",
        origin="link_flow_webchat" if is_webchat else "whatsapp",
        lgpd_consent=True,
        marketing_opt_in=True,
        tags_cache=[],
    )
    db_session.add(patient)
    db_session.flush()

    conversation = Conversation(
        tenant_id=tenant_id,
        patient_id=patient.id,
        channel=channel,
        status="aberta",
        tags=["entry_webchat"] if channel == "webchat" else [],
    )
    db_session.add(conversation)
    db_session.flush()

    inbound_message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="inbound",
        channel=channel,
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
    channel: str = "whatsapp",
):
    inbound_message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        direction="inbound",
        channel=channel,
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


def _ensure_unit(db_session, *, tenant_id, name: str = "Unidade Wizard"):
    unit = db_session.scalar(select(Unit).where(Unit.tenant_id == tenant_id, Unit.name == name))
    if unit:
        return unit
    unit = Unit(
        tenant_id=tenant_id,
        code=name[:8].upper().replace(" ", "-"),
        name=name,
        address={},
        is_active=True,
    )
    db_session.add(unit)
    db_session.commit()
    db_session.refresh(unit)
    return unit


def _ensure_patient(db_session, *, tenant_id, unit_id, suffix: str):
    phone = f"5511999{suffix}"
    patient = Patient(
        tenant_id=tenant_id,
        unit_id=unit_id,
        full_name=f"Paciente Slots {suffix}",
        phone=phone,
        normalized_phone=phone,
        status="ativo",
        origin="manual",
        lgpd_consent=True,
        marketing_opt_in=True,
        tags_cache=[],
    )
    db_session.add(patient)
    db_session.flush()
    return patient


def test_list_available_slots_keeps_time_when_another_professional_is_free(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    unit = _ensure_unit(db_session, tenant_id=tenant_id)
    patient = _ensure_patient(db_session, tenant_id=tenant_id, unit_id=unit.id, suffix="10001")
    _upsert_ai_knowledge_base_setting(
        db_session,
        tenant_id=tenant_id,
        value={
            "services": [
                {
                    "name": "Implante",
                    "description": "",
                    "duration_note": "2h",
                    "price_note": "",
                }
            ]
        },
    )
    occupied = Professional(
        tenant_id=tenant_id,
        unit_id=unit.id,
        full_name="Dra Ocupada",
        working_days=[0, 1, 2, 3, 4, 5, 6],
        shift_start="09:00",
        shift_end="18:00",
        procedures=["Implante"],
        is_active=True,
    )
    available = Professional(
        tenant_id=tenant_id,
        unit_id=unit.id,
        full_name="Dr Disponivel",
        working_days=[0, 1, 2, 3, 4, 5, 6],
        shift_start="09:00",
        shift_end="18:00",
        procedures=["Implante"],
        is_active=True,
    )
    db_session.add_all([occupied, available])
    db_session.flush()

    tomorrow = datetime.now(UTC).replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1)
    db_session.add(
        Appointment(
            tenant_id=tenant_id,
            patient_id=patient.id,
            unit_id=unit.id,
            professional_id=occupied.id,
            procedure_type="Implante",
            starts_at=tomorrow,
            ends_at=None,
            origin="manual",
            notes="",
            status="agendada",
            confirmation_status="pendente",
        )
    )
    db_session.commit()

    slots = _list_available_slots(
        db_session,
        tenant_id=tenant_id,
        unit_id=unit.id,
        config=_base_ai_config(),
        procedure_type="Implante",
        period="morning",
        requested_date=tomorrow.date(),
        max_slots=4,
    )

    assert slots
    assert slots[0]["starts_at_local"].strftime("%H:%M") == "09:00"
    assert slots[0]["professional_name"] == "Dr Disponivel"


def test_list_available_slots_hides_hour_when_all_professionals_are_busy_for_service_duration(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    unit = _ensure_unit(db_session, tenant_id=tenant_id, name="Unidade Duracao")
    patient = _ensure_patient(db_session, tenant_id=tenant_id, unit_id=unit.id, suffix="10002")
    _upsert_ai_knowledge_base_setting(
        db_session,
        tenant_id=tenant_id,
        value={
            "services": [
                {
                    "name": "Implante",
                    "description": "",
                    "duration_note": "2h",
                    "price_note": "",
                }
            ]
        },
    )
    first_professional = Professional(
        tenant_id=tenant_id,
        unit_id=unit.id,
        full_name="Dra Implante A",
        working_days=[0, 1, 2, 3, 4, 5, 6],
        shift_start="09:00",
        shift_end="18:00",
        procedures=["Implante"],
        is_active=True,
    )
    second_professional = Professional(
        tenant_id=tenant_id,
        unit_id=unit.id,
        full_name="Dr Implante B",
        working_days=[0, 1, 2, 3, 4, 5, 6],
        shift_start="09:00",
        shift_end="18:00",
        procedures=["Implante"],
        is_active=True,
    )
    db_session.add_all([first_professional, second_professional])
    db_session.flush()

    tomorrow = datetime.now(UTC).replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=2)
    db_session.add_all(
        [
            Appointment(
                tenant_id=tenant_id,
                patient_id=patient.id,
                unit_id=unit.id,
                professional_id=first_professional.id,
                procedure_type="Implante",
                starts_at=tomorrow,
                ends_at=None,
                origin="manual",
                notes="",
                status="agendada",
                confirmation_status="pendente",
            ),
            Appointment(
                tenant_id=tenant_id,
                patient_id=patient.id,
                unit_id=unit.id,
                professional_id=second_professional.id,
                procedure_type="Implante",
                starts_at=tomorrow,
                ends_at=None,
                origin="manual",
                notes="",
                status="agendada",
                confirmation_status="pendente",
            ),
        ]
    )
    db_session.commit()

    slots = _list_available_slots(
        db_session,
        tenant_id=tenant_id,
        unit_id=unit.id,
        config=_base_ai_config(),
        procedure_type="Implante",
        period="morning",
        requested_date=tomorrow.date(),
        max_slots=4,
    )

    assert slots
    first_visible_time = slots[0]["starts_at_local"].strftime("%H:%M")
    assert first_visible_time == "11:00"
    assert all(slot["starts_at_local"].strftime("%H:%M") not in {"09:00", "09:30", "10:00", "10:30"} for slot in slots)


def test_list_available_slots_deduplicates_same_time_and_keeps_best_professional(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    unit = _ensure_unit(db_session, tenant_id=tenant_id, name="Unidade Slots Unicos")
    _upsert_ai_knowledge_base_setting(
        db_session,
        tenant_id=tenant_id,
        value={
            "services": [
                {
                    "name": "Avaliação odontológica",
                    "description": "",
                    "duration_note": "30 min",
                    "price_note": "",
                }
            ]
        },
    )
    specialist = Professional(
        tenant_id=tenant_id,
        unit_id=unit.id,
        full_name="Dra Especialista",
        specialty="Avaliação odontológica",
        working_days=[0, 1, 2, 3, 4, 5, 6],
        shift_start="09:00",
        shift_end="18:00",
        procedures=["Avaliação odontológica"],
        is_active=True,
    )
    support = Professional(
        tenant_id=tenant_id,
        unit_id=unit.id,
        full_name="Dr Apoio",
        working_days=[0, 1, 2, 3, 4, 5, 6],
        shift_start="09:00",
        shift_end="18:00",
        procedures=["Avaliação odontológica"],
        is_active=True,
    )
    db_session.add_all([specialist, support])
    db_session.commit()

    tomorrow = datetime.now(UTC).replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=3)
    slots = _list_available_slots(
        db_session,
        tenant_id=tenant_id,
        unit_id=unit.id,
        config=_base_ai_config(),
        procedure_type="Avaliação odontológica",
        period="morning",
        requested_date=tomorrow.date(),
        max_slots=4,
    )

    assert [slot["starts_at_local"].strftime("%H:%M") for slot in slots] == ["09:00", "09:30", "10:00", "10:30"]
    assert slots[0]["professional_name"] == "Dra Especialista"
    assert slots[0]["available_professionals_count"] == 2
    assert slots[0]["available_professionals"] == ["Dra Especialista", "Dr Apoio"]


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


def test_capture_patient_registration_persists_cpf_on_patient_when_unique(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    conversation, _ = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Meu nome completo e Rafael Santos Nogueira, CPF 123.456.096-16, nascimento 15/08/1985.",
    )

    patient = db_session.get(Patient, conversation.patient_id)
    patient.full_name = "Contato WhatsApp 1111"
    patient.birth_date = None
    patient.cpf = None
    patient.normalized_cpf = None
    db_session.add(patient)
    db_session.commit()

    changes = _capture_patient_registration_from_inbound(
        db_session,
        conversation=conversation,
        inbound_text="Meu nome completo e Rafael Santos Nogueira, CPF 123.456.096-16, nascimento 15/08/1985.",
        allow_loose_name=True,
        allow_unlabeled_birth_date=True,
    )
    db_session.commit()

    refreshed_patient = db_session.get(Patient, patient.id)
    refreshed_conversation = db_session.get(Conversation, conversation.id)
    cpf_contact = db_session.scalar(
        select(PatientContact).where(
            PatientContact.tenant_id == tenant_id,
            PatientContact.patient_id == patient.id,
            PatientContact.channel == CPF_CONTACT_CHANNEL,
        )
    )

    assert changes["patient_full_name"] == "Rafael Santos Nogueira"
    assert changes["patient_birth_date"] == "1985-08-15"
    assert changes["patient_cpf"] == "12345609616"
    assert refreshed_patient.full_name == "Rafael Santos Nogueira"
    assert refreshed_patient.birth_date.isoformat() == "1985-08-15"
    assert refreshed_patient.cpf == "12345609616"
    assert refreshed_patient.normalized_cpf == "12345609616"
    assert cpf_contact is not None
    assert cpf_contact.normalized_value == "12345609616"
    assert _patient_saved_cpf(db_session, conversation=conversation) == "12345609616"
    assert "dados_cadastrais_capturados" in (refreshed_conversation.tags or [])


def test_capture_patient_registration_keeps_contact_cpf_when_patient_conflicts(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    existing_patient = Patient(
        tenant_id=tenant_id,
        full_name="Paciente Existente",
        phone="5511999000001",
        normalized_phone="5511999000001",
        cpf="12345609616",
        normalized_cpf="12345609616",
        status="ativo",
        origin="manual",
        lgpd_consent=True,
        marketing_opt_in=True,
        tags_cache=[],
    )
    db_session.add(existing_patient)
    db_session.commit()

    conversation, _ = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Meu nome completo e Rafael Santos Nogueira, CPF 123.456.096-16, nascimento 15/08/1985.",
    )

    patient = db_session.get(Patient, conversation.patient_id)
    patient.full_name = "Contato WhatsApp 2222"
    patient.birth_date = None
    patient.cpf = None
    patient.normalized_cpf = None
    db_session.add(patient)
    db_session.commit()

    changes = _capture_patient_registration_from_inbound(
        db_session,
        conversation=conversation,
        inbound_text="Meu nome completo e Rafael Santos Nogueira, CPF 123.456.096-16, nascimento 15/08/1985.",
        allow_loose_name=True,
        allow_unlabeled_birth_date=True,
    )
    db_session.commit()

    refreshed_patient = db_session.get(Patient, patient.id)
    cpf_contact = db_session.scalar(
        select(PatientContact).where(
            PatientContact.tenant_id == tenant_id,
            PatientContact.patient_id == patient.id,
            PatientContact.channel == CPF_CONTACT_CHANNEL,
        )
    )

    assert changes["patient_cpf"] == "12345609616"
    assert refreshed_patient.cpf is None
    assert refreshed_patient.normalized_cpf is None
    assert cpf_contact is not None
    assert cpf_contact.normalized_value == "12345609616"
    assert _patient_saved_cpf(db_session, conversation=conversation) == "12345609616"


def test_official_visit_guidance_response_uses_real_unit_address_professional_and_documents(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    unit = _ensure_unit(db_session, tenant_id=tenant_id, name="Unidade Paulista")
    unit.address = {
        "street": "Rua Ramondetti Giacomo",
        "number": "24",
        "neighborhood": "Vila Dalva",
        "city": "Sao Paulo",
        "state": "SP",
        "zip_code": "05387-110",
        "formatted": "Rua Ramondetti Giacomo, 24, Vila Dalva, Sao Paulo - SP, 05387-110",
    }
    db_session.add(unit)
    professional = _ensure_professional(
        db_session,
        tenant_id=tenant_id,
        unit_id=unit.id,
        full_name="Marcos Antonio Lopes",
    )
    patient = _ensure_patient(db_session, tenant_id=tenant_id, unit_id=unit.id, suffix="20001")
    conversation = Conversation(
        tenant_id=tenant_id,
        patient_id=patient.id,
        channel="whatsapp",
        status="aberta",
        tags=[],
    )
    db_session.add(conversation)
    db_session.flush()
    appointment = Appointment(
        tenant_id=tenant_id,
        patient_id=patient.id,
        unit_id=unit.id,
        professional_id=professional.id,
        procedure_type="Avaliação odontológica",
        starts_at=datetime(2030, 4, 29, 12, 0, tzinfo=UTC),
        ends_at=datetime(2030, 4, 29, 12, 30, tzinfo=UTC),
        origin="ai_autoresponder",
        notes="",
        status="agendada",
        confirmation_status="confirmada",
    )
    db_session.add(appointment)
    db_session.commit()

    response = build_official_visit_guidance_response(
        db_session,
        conversation=conversation,
        inbound_text="Qual o endereço da unidade paulista e quem vai me atender? Também preciso saber que documento levar.",
        config=_base_ai_config(),
    )

    assert response is not None
    assert response["mode"] == "official_visit_guidance"
    assert "Rua Ramondetti Giacomo, 24, Vila Dalva, Sao Paulo - SP, 05387-110" in response["response_text"]
    assert "Marcos Antonio Lopes" in response["response_text"]
    assert "documento com foto e CPF" in response["response_text"]
    assert response["metadata"]["unit_name"] == "Unidade Paulista"
    assert response["metadata"]["professional_name"] == "Marcos Antonio Lopes"


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
            "output": (
                '{"reply_text":"Claro! A avaliação ortodôntica está disponível e posso te ajudar a agendar.",'
                '"next_action":"none","action_payload":{"context":"knowledge_test"},"confidence":0.91}'
            ),
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


def test_prompt_includes_ai_lab_training_examples(monkeypatch, seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    db_session.add(
        Setting(
            tenant_id=tenant_id,
            key="ai_lab.history",
            value={
                "entries": [
                    {
                        "id": "lab-1",
                        "created_at": "2026-04-21T10:00:00+00:00",
                        "input_text": "Quanto custa clareamento?",
                        "edited_response_text": "Posso te orientar. O valor depende da avaliacao, mas ja te explico os proximos passos.",
                        "note": "Ser consultivo e chamar para avaliacao sem prometer preco fechado.",
                        "contract_valid": True,
                    }
                ]
            },
            is_secret=False,
        )
    )
    db_session.commit()

    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quanto custa clareamento?",
    )

    from app.services import ai_autoresponder_service

    captured_prompt: dict[str, str] = {}

    def _fake_run_llm_task(*args, **kwargs):
        captured_prompt["value"] = kwargs.get("prompt", "")
        return {
            "output": (
                '{"reply_text":"Posso te orientar. O valor depende da avaliacao, mas ja te explico os proximos passos.",'
                '"next_action":"show_services","action_payload":{"context":"price_question"},"confidence":0.9}'
            ),
            "metadata": {"provider": "mock", "model": "mock"},
        }

    monkeypatch.setattr(ai_autoresponder_service, "run_llm_task", _fake_run_llm_task)
    monkeypatch.setattr(
        ai_autoresponder_service,
        "classify_intent",
        lambda *args, **kwargs: {"output": '{"intent":"orcamento","confidence":0.89}'},
    )

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    assert result["status"] == "responded"
    prompt = captured_prompt.get("value", "")
    assert "Treino aprovado no IA Lab" in prompt
    assert "Quanto custa clareamento?" in prompt
    assert "Ser consultivo" in prompt


def test_process_inbound_message_replies_to_real_inbound_sender_phone(monkeypatch, seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Oi, quero saber sobre limpeza.",
    )

    patient = db_session.get(Patient, conversation.patient_id)
    assert patient is not None
    patient.phone = "5511911111111"
    patient.normalized_phone = "5511911111111"

    account = db_session.scalar(select(WhatsAppAccount).where(WhatsAppAccount.tenant_id == tenant_id))
    assert account is not None
    inbound.payload = {
        "from": "5511988887777",
        "provider_context": {
            "whatsapp_account_id": str(account.id),
            "provider_name": account.provider_name,
            "phone_number_id": account.phone_number_id,
            "business_account_id": account.business_account_id,
        },
    }
    inbound.provider_message_id = "wamid.real.in.001"
    db_session.add_all([patient, inbound])
    db_session.commit()

    from app.services import ai_autoresponder_service

    monkeypatch.setattr(
        ai_autoresponder_service,
        "run_llm_task",
        lambda *args, **kwargs: {
            "output": (
                '{"reply_text":"Posso te ajudar com a limpeza e ja verifico os horarios.",'
                '"next_action":"none","action_payload":{},"confidence":0.92}'
            ),
            "metadata": {"provider": "mock", "model": "mock"},
        },
    )
    monkeypatch.setattr(
        ai_autoresponder_service,
        "classify_intent",
        lambda *args, **kwargs: {"output": '{"intent":"informacao","confidence":0.91}'},
    )

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    outbox = db_session.scalar(
        select(OutboxMessage)
        .where(OutboxMessage.tenant_id == tenant_id)
        .order_by(OutboxMessage.created_at.desc())
    )
    assert result["status"] == "responded"
    assert outbox is not None
    assert (outbox.payload or {}).get("to") == "5511988887777"
    assert ((outbox.payload or {}).get("provider_context") or {}).get("whatsapp_account_id") == str(account.id)


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


def test_booking_wizard_reuses_service_and_unit_from_first_message(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    unit = _ensure_unit(db_session, tenant_id=tenant_id, name="Unidade Paulista")
    professional = db_session.scalar(
        select(Professional).where(
            Professional.tenant_id == tenant_id,
            Professional.unit_id == unit.id,
            Professional.full_name == "Dra Limpeza Paulista",
        )
    )
    if not professional:
        professional = Professional(
            tenant_id=tenant_id,
            unit_id=unit.id,
            full_name="Dra Limpeza Paulista",
            working_days=[0, 1, 2, 3, 4, 5, 6],
            shift_start="08:00",
            shift_end="18:00",
            procedures=["Limpeza odontológica"],
            is_active=True,
        )
        db_session.add(professional)
        db_session.commit()

    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Oi! Quero agendar uma consulta nova de limpeza na Unidade Paulista.",
    )

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    assert result["status"] == "responded"
    assert result.get("scheduling_mode") == "booking_wizard_day_select"

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
    assert outbound is not None
    assert "dias disponíveis para Limpeza odontológica na Unidade Paulista" in (outbound.body or "")
    assert "qual atendimento" not in (outbound.body or "").lower()
    assert "qual unidade" not in (outbound.body or "").lower()
    assert (outbound.payload or {}).get("mode") == "booking_wizard_day_select"
    assert (outbound.payload or {}).get("procedure_type") == "Limpeza odontológica"
    assert (outbound.payload or {}).get("unit_name") == "Unidade Paulista"


def test_booking_wizard_no_slots_general_keeps_interactive_options(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)
    _ensure_unit(db_session, tenant_id=tenant_id, name="Unidade Paulista")

    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quero agendar um implante dentário na Unidade Paulista.",
    )

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    assert result["status"] == "responded"
    assert result.get("scheduling_mode") == "no_slots_general"

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
    assert outbound is not None
    assert outbound.message_type == "interactive_list"
    rows = (((outbound.payload or {}).get("interactive") or {}).get("rows") or [])
    row_ids = {str(item.get("id") or "") for item in rows}
    assert "day_change_service" in row_ids
    assert "menu_human" in row_ids

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


def test_webchat_day_request_falls_back_to_numbered_text_options(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    unit = _ensure_unit(db_session, tenant_id=tenant_id)
    _ensure_professional(db_session, tenant_id=tenant_id, unit_id=unit.id)

    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quero saber os dias disponiveis para avaliacao de lentes de contato",
        channel="webchat",
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
    assert outbound.message_type == "text"
    assert "Escolha o dia:" in (outbound.body or "")
    assert "1)" in (outbound.body or "")


def test_webchat_confirmation_keeps_session_open_and_requests_registration_fields(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())

    conversation, _ = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quero agendar uma avaliacao esta semana.",
        channel="webchat",
    )
    patient = db_session.get(Patient, conversation.patient_id)
    unit = _ensure_unit(db_session, tenant_id=tenant_id)
    professional = _ensure_professional(db_session, tenant_id=tenant_id, unit_id=unit.id, full_name="Dra. Webchat")
    assert patient is not None

    patient.unit_id = unit.id
    conversation.unit_id = unit.id
    db_session.add(patient)
    db_session.add(conversation)
    db_session.flush()

    selected_day = (datetime.now(UTC) + timedelta(days=2)).date()
    starts_at_utc = datetime.now(UTC) + timedelta(days=2, hours=3)
    ends_at_utc = starts_at_utc + timedelta(minutes=60)
    session = LinkFlowSession(
        tenant_id=tenant_id,
        unit_id=unit.id,
        mode="link_flow",
        cta_mode="webchat",
        channel="webchat",
        token_hash=f"token-{conversation.id}",
        public_access_token_hash=f"public-{conversation.id}",
        status="linked",
        landing_path="/agendar/tenant-a",
        utm_payload={},
        linked_conversation_id=conversation.id,
        linked_patient_id=patient.id,
        linked_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    db_session.add(session)
    db_session.flush()

    confirm_prompt = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="outbound",
        channel="webchat",
        sender_type="ai",
        body=(
            "Perfeito, esta quase pronto. Posso confirmar seu agendamento?\n"
            "Confirmacao:\n1) Sim\n2) Nao\n3) Trocar horario"
        ),
        message_type="text",
        payload={
            "mode": "booking_wizard_confirm",
            "scheduling": {
                "procedure_type": "Clareamento dental",
                "unit_id": str(unit.id),
                "unit_name": unit.name,
                "requested_date": selected_day.isoformat(),
                "selected_slot": {
                    "id": "time_1000",
                    "label": "sexta-feira, 22/05 as 10:00",
                    "starts_at_utc": starts_at_utc.isoformat(),
                    "ends_at_utc": ends_at_utc.isoformat(),
                    "starts_at_local": starts_at_utc.isoformat(),
                    "professional_id": str(professional.id),
                    "professional_name": professional.full_name,
                    "time": "10:00",
                },
            },
        },
        status="sent",
    )
    db_session.add(confirm_prompt)
    db_session.commit()

    inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="sim",
        channel="webchat",
    )
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
    db_session.refresh(session)

    assert result["status"] == "responded"
    assert result.get("scheduling_mode") in {"appointment_created", "appointment_already_created"}
    assert appointment is not None
    assert outbound is not None
    assert outbound.channel == "webchat"
    assert outbound.status == "sent"
    assert (outbound.payload or {}).get("mode") == "booking_request_cpf_after_booking"
    assert "cpf" in (outbound.body or "").lower()
    assert "celular" in (outbound.body or "").lower()
    assert session.status == "linked"
    assert session.closed_at is None
    assert session.linked_appointment_id == appointment.id


def test_webchat_post_booking_registration_message_stays_in_flow_until_phone_is_collected(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())

    conversation, _ = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Quero agendar uma avaliacao esta semana.",
        channel="webchat",
    )
    patient = db_session.get(Patient, conversation.patient_id)
    unit = _ensure_unit(db_session, tenant_id=tenant_id)
    assert patient is not None

    patient.unit_id = unit.id
    conversation.unit_id = unit.id
    db_session.add_all([patient, conversation])
    db_session.flush()

    session = LinkFlowSession(
        tenant_id=tenant_id,
        unit_id=unit.id,
        mode="link_flow",
        cta_mode="webchat",
        channel="webchat",
        token_hash=f"token-reg-{conversation.id}",
        public_access_token_hash=f"public-reg-{conversation.id}",
        status="linked",
        landing_path="/agendar/tenant-a",
        utm_payload={},
        linked_conversation_id=conversation.id,
        linked_patient_id=patient.id,
        linked_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    db_session.add(session)
    db_session.flush()

    cpf_prompt = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="outbound",
        channel="webchat",
        sender_type="ai",
        body=(
            "Perfeito! Seu agendamento já está confirmado.\n"
            "Para agilizar seu atendimento no dia da consulta, você pode me enviar nome completo, CPF e data de nascimento agora."
        ),
        message_type="text",
        payload={
            "mode": "booking_request_cpf_after_booking",
            "scheduling": {
                "procedure_type": "Avaliação inicial",
                "unit_name": unit.name,
                "unit_address": "Rua Teste, 123",
                "professional_name": "Dra. Teste",
                "selected_slot": {"label": "sexta-feira, 22/05 às 10:00"},
                "missing_registration_fields": ["full_name", "cpf", "birth_date", "phone"],
                "registration_retry_sent": False,
            },
        },
        status="sent",
    )
    db_session.add(cpf_prompt)
    db_session.commit()

    registration_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="Meu nome completo é Bruno Caio Cardoso, CPF 706.401.781-95 e nasci em 25/01/1992.",
        channel="webchat",
    )
    registration_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=registration_inbound.id,
    )

    db_session.refresh(patient)
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
    db_session.refresh(session)

    assert registration_result["status"] == "responded"
    assert registration_result.get("scheduling_mode") == "booking_request_cpf_after_booking"
    assert patient.full_name == "Bruno Caio Cardoso"
    assert patient.birth_date is not None
    assert patient.birth_date.isoformat() == "1992-01-25"
    assert patient.cpf == "70640178195"
    assert latest_outbound is not None
    assert (latest_outbound.payload or {}).get("mode") == "booking_request_cpf_after_booking"
    assert "celular" in (latest_outbound.body or "").lower()
    assert session.status == "linked"
    assert session.closed_at is None

    phone_inbound = _append_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_text="Meu celular é 11 99876-5432",
        channel="webchat",
    )
    phone_result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=phone_inbound.id,
    )

    db_session.refresh(patient)
    final_outbound = db_session.scalar(
        select(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
    )

    assert phone_result["status"] == "responded"
    assert phone_result.get("scheduling_mode") == "booking_post_confirmation_options"
    assert patient.normalized_phone == "5511998765432"
    assert final_outbound is not None
    assert (final_outbound.payload or {}).get("mode") == "booking_post_confirmation_options"


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
    assert "sou luiza" in normalized
    assert "bem-vindo à clínica" in normalized or "bem-vindo a clínica" in normalized
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
    assert result.get("scheduling_mode") != "welcome_message_start"
    assert outbound is not None
    assert outbound.body.startswith("Olá! 😊")


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


def test_welcome_message_uses_text_field_when_greeting_example_is_object(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _upsert_ai_knowledge_base_setting(
        db_session,
        tenant_id=tenant_id,
        value={
            "clinic_profile": {
                "clinic_name": "Lorenson Odontologia",
                "welcome_greeting_example": {
                    "text": "Olá! Bem-vindo à Lorenson Odontologia. Como podemos ajudar você hoje?",
                    "inferred": True,
                },
            }
        },
    )
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    conversation, inbound = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Oi",
        channel="webchat",
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
    assert "Olá! Bem-vindo à Lorenson Odontologia. Como podemos ajudar você hoje?" in (outbound.body or "")
    assert "{'text':" not in (outbound.body or "")
    assert "inferred" not in (outbound.body or "")


def test_welcome_menu_services_selection_returns_service_overview_in_webchat(seeded_db, db_session):
    tenant_id = seeded_db["tenant_a"].id
    _upsert_ai_global_setting(db_session, tenant_id=tenant_id, value=_base_ai_config())
    _upsert_ai_knowledge_base_setting(
        db_session,
        tenant_id=tenant_id,
        value={
            "clinic_profile": {"clinic_name": "Clinica Exemplo"},
            "services": [
                {"name": "Limpeza odontológica", "description": "Remove placa e tártaro"},
                {"name": "Clareamento dental", "description": "Melhora o brilho do sorriso"},
            ],
        },
    )
    _ensure_valid_whatsapp_account(db_session, tenant_id=tenant_id)

    conversation, inbound_1 = _create_conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Oi",
        channel="webchat",
    )
    process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound_1.id,
    )

    inbound_2 = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="inbound",
        channel="webchat",
        sender_type="patient",
        body="2",
        message_type="text",
        payload={},
        status="received",
    )
    db_session.add(inbound_2)
    db_session.commit()

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound_2.id,
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
    assert result.get("scheduling_mode") == "services_menu_overview"
    assert outbound is not None
    assert "Claro. Estes são alguns serviços" in (outbound.body or "")
    assert "Limpeza odontológica" in (outbound.body or "")
    assert "Toque para escolher" not in (outbound.body or "")
    assert "Escolha uma opção abaixo." not in (outbound.body or "")


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

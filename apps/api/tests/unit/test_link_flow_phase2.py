from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.exceptions import ApiError
from app.models import (
    Appointment,
    Conversation,
    LinkFlowEvent,
    LinkFlowSession,
    Message,
    Patient,
    PatientContact,
    Professional,
    ProspectAccount,
    Setting,
    Tenant,
    Unit,
    WhatsAppAccount,
)
from app.models.enums import MessageDirection, MessageStatus
from app.services.ai_autoresponder_service import _appointment_response_from_selected_slot
from app.services.ai_structured_flow import _confirm_appointment
from app.services.link_flow_service import (
    capture_public_contact_phone,
    get_intake_config,
    public_contact_phone_state,
    validate_intake_config_payload,
)
from app.services.channel_dispatch_service import dispatch_patient_message
from app.services.webchat_service import (
    create_webchat_link_flow_session,
    ensure_webchat_conversation,
    list_public_webchat_messages,
    post_public_webchat_message,
    public_webchat_booking_summary,
    validate_public_webchat_session,
)
from app.services.sales_demo_service import cleanup_demo_resources, ensure_sales_outreach_sender_tenant
from app.services.whatsapp_service import (
    assert_whatsapp_route_ready_for_dispatch,
    resolve_whatsapp_reply_route,
)


def _valid_system_sender(db_session) -> WhatsAppAccount:
    sender_tenant = ensure_sales_outreach_sender_tenant(db_session)
    account = WhatsAppAccount(
        tenant_id=sender_tenant.id,
        provider_name="meta_cloud",
        phone_number_id="551199988776600",
        business_account_id="123456789012345",
        display_phone="+5511999887766",
        access_token_encrypted="EAA" + ("x" * 60),
        verify_token="verify-token-dev",
        is_active=True,
    )
    db_session.add(account)
    db_session.flush()
    return account


def _enable_webchat_intake(db_session, tenant) -> dict:
    config = {
        "mode": "link_flow",
        "link_flow": {
            "enabled": True,
            "cta_mode": "webchat",
            "headline": "Chat oficial",
            "trust_message": "Atendimento direto pela pagina.",
            "button_label": "Iniciar chat",
            "session_ttl_minutes": 30,
        },
    }
    db_session.add(Setting(tenant_id=tenant.id, key="intake.config", value=config, is_secret=False))
    db_session.flush()
    return config


def _booking_context(db_session, tenant):
    unit = Unit(
        tenant_id=tenant.id,
        name="Unidade Central",
        code="CENTRAL",
        is_active=True,
        address={},
        working_hours={},
    )
    patient = Patient(
        tenant_id=tenant.id,
        full_name="Paciente Link Flow",
        phone="11977776666",
        normalized_phone="5511977776666",
    )
    db_session.add_all([unit, patient])
    db_session.flush()
    professional = Professional(
        tenant_id=tenant.id,
        unit_id=unit.id,
        full_name="Dra. Flux",
        specialty="avaliacao",
        procedures=["avaliacao"],
        working_days=[1, 2, 3, 4, 5],
        is_active=True,
    )
    conversation = Conversation(
        tenant_id=tenant.id,
        unit_id=unit.id,
        patient_id=patient.id,
        channel="whatsapp",
        status="aberta",
        tags=["entry_link_flow"],
    )
    db_session.add_all([professional, conversation])
    db_session.flush()
    session = LinkFlowSession(
        tenant_id=tenant.id,
        unit_id=unit.id,
        mode="link_flow",
        cta_mode="whatsapp_redirect",
        token_hash=f"hash-{conversation.id}",
        status="linked",
        landing_path="/agendar/tenant-b",
        utm_payload={},
        linked_conversation_id=conversation.id,
        linked_patient_id=patient.id,
        linked_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    db_session.add(session)
    db_session.flush()
    return unit, patient, professional, conversation, session


def test_intake_config_defaults_and_validation(seeded_db, db_session):
    tenant = seeded_db["tenant_b"]

    assert get_intake_config(db_session, tenant_id=tenant.id)["mode"] == "official_api"

    config = validate_intake_config_payload(
        {
            "mode": "hybrid",
            "link_flow": {
                "enabled": True,
                "cta_mode": "whatsapp_redirect",
                "headline": " Agende agora ",
                "trust_message": " Canal oficial da clinica ",
                "button_label": "Continuar",
                "session_ttl_minutes": 45,
            },
        }
    )

    assert config["mode"] == "hybrid"
    assert config["link_flow"]["headline"] == "Agende agora"

    webchat_config = validate_intake_config_payload(
        {
            "mode": "link_flow",
            "link_flow": {
                "enabled": True,
                "cta_mode": "webchat",
                "headline": "Chat oficial",
                "trust_message": "Atendimento direto pela pagina.",
                "button_label": "Iniciar chat",
                "session_ttl_minutes": 30,
            },
        }
    )

    assert webchat_config["link_flow"]["cta_mode"] == "webchat"


def test_intake_config_rejects_invalid_mode():
    with pytest.raises(ApiError) as exc:
        validate_intake_config_payload(
            {
                "mode": "webchat",
                "link_flow": {"enabled": True, "cta_mode": "whatsapp_redirect"},
            }
        )

    assert exc.value.code == "INTAKE_CONFIG_INVALID"


def test_link_flow_dispatch_uses_shared_sender_without_tenant_account(seeded_db, db_session):
    tenant = seeded_db["tenant_b"]
    account = _valid_system_sender(db_session)
    unit, patient, _professional, conversation, _session = _booking_context(db_session, tenant)
    inbound = Message(
        tenant_id=tenant.id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND.value,
        channel="whatsapp",
        provider_message_id="wamid.route-aware",
        sender_type="patient",
        body="Quero agendar",
        message_type="text",
        payload={
            "from": patient.phone,
            "provider_context": {
                "whatsapp_account_id": str(account.id),
                "provider_name": account.provider_name,
                "phone_number_id": account.phone_number_id,
                "business_account_id": account.business_account_id,
            },
        },
        status=MessageStatus.RECEIVED.value,
    )
    db_session.add(inbound)
    db_session.flush()

    destination, provider_context = resolve_whatsapp_reply_route(
        db_session,
        conversation=conversation,
        inbound_message=inbound,
    )
    ready_account = assert_whatsapp_route_ready_for_dispatch(
        db_session,
        tenant_id=tenant.id,
        provider_context=provider_context,
    )

    assert destination == "5511977776666"
    assert ready_account.id == account.id
    assert ready_account.tenant_id != tenant.id
    assert unit.id == conversation.unit_id


def test_official_api_dispatch_without_route_requires_tenant_account(seeded_db, db_session):
    tenant = seeded_db["tenant_b"]
    with pytest.raises(ApiError) as exc:
        assert_whatsapp_route_ready_for_dispatch(db_session, tenant_id=tenant.id, provider_context=None)

    assert exc.value.code == "WHATSAPP_ACCOUNT_NOT_CONFIGURED"


def test_duplicate_booking_guard_blocks_legacy_link_flow(seeded_db, db_session):
    tenant = seeded_db["tenant_b"]
    unit, patient, professional, conversation, session = _booking_context(db_session, tenant)
    starts_at = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)
    ends_at = datetime(2026, 6, 1, 14, 0, tzinfo=UTC)
    existing = Appointment(
        tenant_id=tenant.id,
        patient_id=patient.id,
        unit_id=unit.id,
        professional_id=professional.id,
        procedure_type="avaliacao",
        starts_at=starts_at,
        ends_at=ends_at,
        status="agendada",
        origin="ai_autoresponder",
    )
    db_session.add(existing)
    db_session.flush()

    result = _appointment_response_from_selected_slot(
        db_session,
        conversation=conversation,
        unit=unit,
        selected_slot={
            "label": "01/06/2026 13:00",
            "starts_at_utc": starts_at,
            "ends_at_utc": ends_at,
            "professional_id": str(professional.id),
            "professional_name": professional.full_name,
        },
        procedure_type="avaliacao",
        period="tarde",
        requested_date=starts_at.date(),
    )

    total = db_session.scalar(
        select(func.count()).select_from(Appointment).where(Appointment.tenant_id == tenant.id)
    )
    duplicate_event = db_session.scalar(
        select(LinkFlowEvent).where(
            LinkFlowEvent.link_flow_session_id == session.id,
            LinkFlowEvent.event_name == "appointment_duplicate_detected",
        )
    )

    assert result["mode"] == "appointment_already_created"
    assert total == 1
    assert duplicate_event is not None
    assert session.linked_appointment_id == existing.id


def test_duplicate_booking_guard_blocks_structured_link_flow(monkeypatch, seeded_db, db_session):
    tenant = seeded_db["tenant_b"]
    unit, patient, professional, conversation, session = _booking_context(db_session, tenant)
    starts_at = datetime(2026, 6, 1, 15, 0, tzinfo=UTC)
    ends_at = datetime(2026, 6, 1, 16, 0, tzinfo=UTC)
    existing = Appointment(
        tenant_id=tenant.id,
        patient_id=patient.id,
        unit_id=unit.id,
        professional_id=professional.id,
        procedure_type="avaliacao",
        starts_at=starts_at,
        ends_at=ends_at,
        status="agendada",
        origin="ai_structured",
    )
    db_session.add(existing)
    db_session.flush()

    monkeypatch.setattr(
        "app.services.ai_structured_flow._validate_slot",
        lambda *args, **kwargs: {
            "status": "available",
            "unit_id": str(unit.id),
            "professional_id": str(professional.id),
            "procedure_type": "avaliacao",
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
        },
    )

    result = _confirm_appointment(
        db_session,
        tenant_id=tenant.id,
        conversation=conversation,
        decision=object(),
        params={},
        context=object(),
    )

    total = db_session.scalar(
        select(func.count()).select_from(Appointment).where(Appointment.tenant_id == tenant.id)
    )
    duplicate_event = db_session.scalar(
        select(LinkFlowEvent).where(
            LinkFlowEvent.link_flow_session_id == session.id,
            LinkFlowEvent.event_name == "appointment_duplicate_detected",
        )
    )

    assert result["status"] == "duplicate"
    assert result["appointment_id"] == str(existing.id)
    assert total == 1
    assert duplicate_event is not None


def test_link_flow_appointment_created_event_for_legacy_flow(seeded_db, db_session):
    tenant = seeded_db["tenant_b"]
    unit, _patient, professional, conversation, session = _booking_context(db_session, tenant)
    starts_at = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
    ends_at = datetime(2026, 6, 1, 11, 0, tzinfo=UTC)

    result = _appointment_response_from_selected_slot(
        db_session,
        conversation=conversation,
        unit=unit,
        selected_slot={
            "label": "01/06/2026 10:00",
            "starts_at_utc": starts_at,
            "ends_at_utc": ends_at,
            "professional_id": str(professional.id),
            "professional_name": professional.full_name,
        },
        procedure_type="avaliacao",
        period="manha",
        requested_date=starts_at.date(),
    )

    created_event = db_session.scalar(
        select(LinkFlowEvent).where(
            LinkFlowEvent.link_flow_session_id == session.id,
            LinkFlowEvent.event_name == "appointment_created",
        )
    )

    assert result["mode"] == "appointment_created"
    assert created_event is not None
    assert session.linked_appointment_id is not None
    assert session.completed_at is not None


def test_webchat_appointment_creation_keeps_public_session_active(seeded_db, db_session):
    tenant = seeded_db["tenant_b"]
    unit, _patient, professional, conversation, session = _booking_context(db_session, tenant)
    session.cta_mode = "webchat"
    session.channel = "webchat"
    session.public_access_token_hash = "public-token-hash"
    conversation.channel = "webchat"
    db_session.add(session)
    db_session.add(conversation)
    db_session.flush()

    starts_at = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
    ends_at = datetime(2026, 6, 1, 11, 0, tzinfo=UTC)

    result = _appointment_response_from_selected_slot(
        db_session,
        conversation=conversation,
        unit=unit,
        selected_slot={
            "label": "01/06/2026 10:00",
            "starts_at_utc": starts_at,
            "ends_at_utc": ends_at,
            "professional_id": str(professional.id),
            "professional_name": professional.full_name,
        },
        procedure_type="avaliacao",
        period="manha",
        requested_date=starts_at.date(),
    )

    assert result["mode"] == "appointment_created"
    assert session.completed_at is not None
    assert session.status == "linked"
    db_session.flush()
    db_session.refresh(session)
    assert session.closed_at is None
    assert session.linked_appointment_id is not None


def test_webchat_public_session_requires_valid_token(seeded_db, db_session):
    tenant = seeded_db["tenant_b"]
    config = _enable_webchat_intake(db_session, tenant)
    bundle = create_webchat_link_flow_session(
        db_session,
        tenant=tenant,
        config=config,
        landing_path="/agendar/tenant-b",
    )
    db_session.flush()

    session, resolved_tenant = validate_public_webchat_session(
        db_session,
        session_id=bundle.session.id,
        public_access_token=bundle.public_access_token,
    )
    assert session.id == bundle.session.id
    assert resolved_tenant.id == tenant.id

    with pytest.raises(ApiError) as exc:
        validate_public_webchat_session(
            db_session,
            session_id=bundle.session.id,
            public_access_token="wrong-token",
        )
    assert exc.value.code == "WEBCHAT_SESSION_FORBIDDEN"


def test_webchat_session_and_conversation_default_to_only_active_unit(seeded_db, db_session):
    tenant = seeded_db["tenant_b"]
    config = _enable_webchat_intake(db_session, tenant)
    unit = Unit(
        tenant_id=tenant.id,
        name="Unidade principal",
        code="PRINCIPAL",
        is_active=True,
        address={},
        working_hours={},
    )
    db_session.add(unit)
    db_session.flush()

    bundle = create_webchat_link_flow_session(
        db_session,
        tenant=tenant,
        config=config,
        landing_path="/agendar/tenant-b",
    )
    conversation = ensure_webchat_conversation(db_session, session=bundle.session, tenant=tenant)
    patient = db_session.get(Patient, conversation.patient_id)

    assert bundle.session.unit_id == unit.id
    assert conversation.unit_id == unit.id
    assert patient is not None
    assert patient.unit_id == unit.id


def test_webchat_channel_dispatch_persists_local_message(seeded_db, db_session):
    tenant = seeded_db["tenant_b"]
    config = _enable_webchat_intake(db_session, tenant)
    bundle = create_webchat_link_flow_session(
        db_session,
        tenant=tenant,
        config=config,
        landing_path="/agendar/tenant-b",
    )
    conversation = ensure_webchat_conversation(db_session, session=bundle.session, tenant=tenant)
    outbound = Message(
        tenant_id=tenant.id,
        conversation_id=conversation.id,
        direction=MessageDirection.OUTBOUND.value,
        channel="webchat",
        sender_type="ai",
        body="Claro, vamos agendar por aqui.",
        message_type="text",
        payload={"source": "unit_test"},
        status=MessageStatus.QUEUED.value,
    )
    db_session.add(outbound)
    db_session.flush()

    result = dispatch_patient_message(
        db_session,
        tenant_id=tenant.id,
        conversation=conversation,
        outbound_message=outbound,
        body=outbound.body,
    )

    assert result.channel == "webchat"
    assert result.outbox_id is None
    assert outbound.status == MessageStatus.SENT.value
    assert (outbound.payload or {}).get("webchat_delivered") is True
    assert bundle.session.last_assistant_message_at is not None


def test_public_webchat_summary_uses_wizard_progress_and_hides_placeholder_name(seeded_db, db_session):
    tenant = seeded_db["tenant_b"]
    config = _enable_webchat_intake(db_session, tenant)
    unit = Unit(
        tenant_id=tenant.id,
        name="Unidade principal",
        code="PRINCIPAL",
        is_active=True,
        address={},
        working_hours={},
    )
    db_session.add(unit)
    db_session.flush()

    bundle = create_webchat_link_flow_session(
        db_session,
        tenant=tenant,
        config=config,
        landing_path="/agendar/tenant-b",
        unit_id=unit.id,
    )
    capture_public_contact_phone(
        db_session,
        session=bundle.session,
        raw_phone="(11) 99999-1111",
    )
    conversation = ensure_webchat_conversation(db_session, session=bundle.session, tenant=tenant)
    outbound = Message(
        tenant_id=tenant.id,
        conversation_id=conversation.id,
        direction=MessageDirection.OUTBOUND.value,
        channel="webchat",
        sender_type="ai",
        body="Perfeito, esta quase pronto. Posso confirmar seu agendamento?",
        message_type="text",
        payload={
            "mode": "booking_wizard_confirm",
            "scheduling": {
                "procedure_type": "Avaliacao odontologica",
                "service_selected": "Avaliacao odontologica",
                "unit_id": str(unit.id),
                "unit_name": unit.name,
                "requested_date": "2026-05-22",
                "selected_slot": {
                    "time": "09:30",
                    "label": "sexta-feira, 22/05 as 09:30",
                    "starts_at_utc": "2026-05-22T12:30:00+00:00",
                    "starts_at_local": "2026-05-22T09:30:00-03:00",
                },
            },
        },
        status=MessageStatus.SENT.value,
    )
    db_session.add(outbound)
    db_session.commit()
    db_session.refresh(bundle.session)

    summary = public_webchat_booking_summary(
        db_session,
        session=bundle.session,
        tenant=tenant,
    )

    assert summary["fields"]["patient_name"]["value"] is None
    assert summary["fields"]["patient_name"]["complete"] is False
    assert summary["fields"]["unit"]["value"] == "Unidade principal"
    assert summary["fields"]["procedure"]["value"] == "Avaliacao odontologica"
    assert summary["fields"]["preferred_date"]["value"] == "2026-05-22"
    assert summary["fields"]["confirmed_slot"]["value"] == "2026-05-22T12:30:00+00:00"
    assert summary["fields"]["confirmed_slot"]["source"] == "conversation"
    assert summary["progress"]["complete_count"] == 3
    assert summary["status"]["appointment_created"] is False


def test_webchat_message_idempotency_and_safe_serialization(monkeypatch, seeded_db, db_session):
    tenant = seeded_db["tenant_b"]
    config = _enable_webchat_intake(db_session, tenant)
    bundle = create_webchat_link_flow_session(
        db_session,
        tenant=tenant,
        config=config,
        landing_path="/agendar/tenant-b",
    )
    db_session.commit()
    session, resolved_tenant = validate_public_webchat_session(
        db_session,
        session_id=bundle.session.id,
        public_access_token=bundle.public_access_token,
    )

    monkeypatch.setattr(
        "app.services.ai_autoresponder_service.process_inbound_message",
        lambda *args, **kwargs: {"status": "ignored"},
    )

    first = post_public_webchat_message(
        db_session,
        session=session,
        tenant=resolved_tenant,
        text="Quero agendar",
        client_message_id="client-1",
    )
    duplicate = post_public_webchat_message(
        db_session,
        session=session,
        tenant=resolved_tenant,
        text="Quero agendar de novo",
        client_message_id="client-1",
    )

    inbound_count = db_session.scalar(
        select(func.count()).select_from(Message).where(
            Message.tenant_id == tenant.id,
            Message.direction == MessageDirection.INBOUND.value,
            Message.channel == "webchat",
        )
    )
    public_messages = list_public_webchat_messages(db_session, session=session)

    assert first["status"] == "accepted"
    assert duplicate["status"] == "duplicate"
    assert inbound_count == 1
    assert public_messages[0]["role"] == "patient"
    assert "conversation_id" not in public_messages[0]


def test_capture_public_contact_phone_creates_patient_for_session(seeded_db, db_session):
    tenant = seeded_db["tenant_b"]
    config = _enable_webchat_intake(db_session, tenant)
    bundle = create_webchat_link_flow_session(
        db_session,
        tenant=tenant,
        config=config,
        landing_path="/agendar/tenant-b",
    )

    payload = capture_public_contact_phone(
        db_session,
        session=bundle.session,
        raw_phone="(11) 99888-7766",
    )
    db_session.flush()
    db_session.refresh(bundle.session)

    patient = db_session.get(Patient, bundle.session.linked_patient_id)
    contact = db_session.scalar(
        select(PatientContact).where(
            PatientContact.tenant_id == tenant.id,
            PatientContact.patient_id == patient.id,
            PatientContact.channel == "whatsapp",
            PatientContact.is_primary.is_(True),
        )
    )

    assert patient is not None
    assert patient.phone == "(11) 99888-7766"
    assert patient.normalized_phone == "5511998887766"
    assert payload["contact_phone"] == "(11) 99888-7766"
    assert payload["contact_phone_required"] is False
    assert public_contact_phone_state(db_session, session=bundle.session)["contact_phone"] == "(11) 99888-7766"
    assert contact is not None
    assert contact.normalized_value == "5511998887766"


def test_capture_public_contact_phone_reuses_existing_patient(seeded_db, db_session):
    tenant = seeded_db["tenant_b"]
    existing = Patient(
        tenant_id=tenant.id,
        full_name="Juliana Lima",
        phone="+55 11 97777-6666",
        normalized_phone="5511977776666",
        origin="manual",
    )
    db_session.add(existing)
    db_session.flush()

    session = LinkFlowSession(
        tenant_id=tenant.id,
        unit_id=None,
        mode="link_flow",
        cta_mode="whatsapp_redirect",
        channel="whatsapp",
        token_hash="token-existing",
        status="pending",
        landing_path="/agendar/tenant-b",
        utm_payload={},
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    db_session.add(session)
    db_session.flush()

    payload = capture_public_contact_phone(
        db_session,
        session=session,
        raw_phone="11 97777-6666",
    )
    db_session.flush()
    db_session.refresh(session)

    assert session.linked_patient_id == existing.id
    assert payload["contact_phone"] == "11 97777-6666"
    assert db_session.scalar(select(func.count()).select_from(Patient).where(Patient.tenant_id == tenant.id)) >= 1


def test_demo_webchat_phone_gate_persists_five_open_conversations(monkeypatch, seeded_db, db_session):
    tenant = seeded_db["tenant_b"]
    config = _enable_webchat_intake(db_session, tenant)
    monkeypatch.setattr(
        "app.services.ai_autoresponder_service.process_inbound_message",
        lambda *args, **kwargs: {"status": "ignored"},
    )

    tracked_conversation_ids = []
    tracked_patient_ids = []

    for index in range(5):
        bundle = create_webchat_link_flow_session(
            db_session,
            tenant=tenant,
            config=config,
            landing_path="/agendar/tenant-b",
        )
        capture_public_contact_phone(
            db_session,
            session=bundle.session,
            raw_phone=f"(11) 99000-{1000 + index}",
        )
        db_session.flush()

        conversation = db_session.get(Conversation, bundle.session.linked_conversation_id)
        patient = db_session.get(Patient, bundle.session.linked_patient_id)

        assert conversation is not None
        assert patient is not None
        assert conversation.patient_id == patient.id
        assert conversation.channel == "webchat"
        assert conversation.status == "aberta"
        assert conversation.external_thread_id == f"link_flow:{bundle.session.id}"

        result = post_public_webchat_message(
            db_session,
            session=bundle.session,
            tenant=tenant,
            text=f"Quero simular um atendimento sem finalizar {index}",
            client_message_id=f"open-demo-{index}",
        )
        db_session.refresh(conversation)

        assert result["status"] == "accepted"
        assert conversation.last_message_at is not None
        tracked_conversation_ids.append(conversation.id)
        tracked_patient_ids.append(patient.id)

    assert len(set(tracked_conversation_ids)) == 5
    assert len(set(tracked_patient_ids)) == 5
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.tenant_id == tenant.id,
                Message.conversation_id.in_(tracked_conversation_ids),
                Message.direction == MessageDirection.INBOUND.value,
                Message.channel == "webchat",
            )
        )
        == 5
    )


def test_demo_webchat_persists_five_completed_appointments_and_cleans_up_demo(seeded_db, db_session):
    tenant = seeded_db["tenant_b"]
    control_tenant_id = seeded_db["tenant_a"].id
    config = _enable_webchat_intake(db_session, tenant)
    unit = Unit(
        tenant_id=tenant.id,
        name="Unidade Demo Webchat",
        code="DEMO-WEBCHAT",
        is_active=True,
        address={},
        working_hours={},
    )
    db_session.add(unit)
    db_session.flush()
    professional = Professional(
        tenant_id=tenant.id,
        unit_id=unit.id,
        full_name="Dra. Demo Webchat",
        specialty="avaliacao",
        procedures=["avaliacao"],
        working_days=[0, 1, 2, 3, 4, 5, 6],
        is_active=True,
    )
    db_session.add(professional)
    db_session.flush()

    tracked_conversation_ids = []
    tracked_patient_ids = []
    tracked_appointment_ids = []

    for index in range(5):
        bundle = create_webchat_link_flow_session(
            db_session,
            tenant=tenant,
            config=config,
            landing_path="/agendar/tenant-b",
            unit_id=unit.id,
        )
        capture_public_contact_phone(
            db_session,
            session=bundle.session,
            raw_phone=f"(11) 99100-{1000 + index}",
        )
        db_session.flush()
        conversation = db_session.get(Conversation, bundle.session.linked_conversation_id)
        patient = db_session.get(Patient, bundle.session.linked_patient_id)
        assert conversation is not None
        assert patient is not None

        patient.full_name = f"Paciente Demo Agendado {index + 1}"
        patient.email = f"paciente.demo.{index + 1}@example.com"
        db_session.add(patient)

        starts_at = datetime(2026, 6, 1 + index, 10, 0, tzinfo=UTC)
        ends_at = starts_at + timedelta(minutes=60)
        result = _appointment_response_from_selected_slot(
            db_session,
            conversation=conversation,
            unit=unit,
            selected_slot={
                "label": starts_at.strftime("%d/%m/%Y %H:%M"),
                "starts_at_utc": starts_at,
                "ends_at_utc": ends_at,
                "professional_id": str(professional.id),
                "professional_name": professional.full_name,
            },
            procedure_type="avaliacao",
            period="manha",
            requested_date=starts_at.date(),
        )
        db_session.flush()
        db_session.refresh(bundle.session)

        assert result["mode"] == "appointment_created"
        assert bundle.session.linked_appointment_id is not None
        assert bundle.session.completed_at is not None
        tracked_conversation_ids.append(conversation.id)
        tracked_patient_ids.append(patient.id)
        tracked_appointment_ids.append(bundle.session.linked_appointment_id)

    assert len(set(tracked_conversation_ids)) == 5
    assert len(set(tracked_patient_ids)) == 5
    assert len(set(tracked_appointment_ids)) == 5
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Appointment)
            .where(
                Appointment.tenant_id == tenant.id,
                Appointment.id.in_(tracked_appointment_ids),
                Appointment.origin == "ai_autoresponder",
            )
        )
        == 5
    )

    prospect = ProspectAccount(
        clinic_name="Clinica Demo Cleanup",
        tenant_seed_key="clinica-demo-cleanup",
        demo_tenant_id=tenant.id,
        demo_status="ativa",
    )
    db_session.add(prospect)
    db_session.flush()
    demo_tenant_id = tenant.id

    cleanup_demo_resources(
        db_session,
        prospect=prospect,
        reason="deleted",
        actor_id=None,
    )
    db_session.flush()

    assert prospect.demo_tenant_id is None
    assert db_session.scalar(select(func.count()).select_from(Tenant).where(Tenant.id == demo_tenant_id)) == 0
    assert db_session.scalar(select(func.count()).select_from(Tenant).where(Tenant.id == control_tenant_id)) == 1
    assert db_session.scalar(select(func.count()).select_from(Conversation).where(Conversation.tenant_id == demo_tenant_id)) == 0
    assert db_session.scalar(select(func.count()).select_from(Patient).where(Patient.tenant_id == demo_tenant_id)) == 0
    assert db_session.scalar(select(func.count()).select_from(Appointment).where(Appointment.tenant_id == demo_tenant_id)) == 0
    assert db_session.scalar(select(func.count()).select_from(Message).where(Message.tenant_id == demo_tenant_id)) == 0
    assert db_session.scalar(select(func.count()).select_from(LinkFlowSession).where(LinkFlowSession.tenant_id == demo_tenant_id)) == 0
    assert db_session.scalar(select(func.count()).select_from(LinkFlowEvent).where(LinkFlowEvent.tenant_id == demo_tenant_id)) == 0

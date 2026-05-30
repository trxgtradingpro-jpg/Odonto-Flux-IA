from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text

from app.db.base import Base
from app.core.security import hash_password
from app.models import AIAutoresponderDecision, Conversation, FeatureFlag, Message, OutboxMessage, Patient, Role, Setting, Tenant, TenantPlan, User, UserRole, WhatsAppAccount
from app.models.enums import MessageDirection
from app.services.ai_autoresponder_service import get_global_config, process_inbound_message, set_platform_global_config


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
        pytest.skip(f"Database indisponivel para teste da flag estruturada: {exc}")
    Base.metadata.create_all(bind=engine)
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


def _upsert_setting(db_session, *, tenant_id, key: str, value: dict):
    item = db_session.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == key))
    if item:
        item.value = value
    else:
        item = Setting(tenant_id=tenant_id, key=key, value=value, is_secret=False)
    db_session.add(item)
    db_session.commit()
    return item


@pytest.fixture()
def seeded_legacy_db(db_session):
    plan = TenantPlan(code="starter", name="Starter", max_users=5, max_units=2, max_monthly_messages=1000)
    db_session.add(plan)
    db_session.flush()
    tenant = Tenant(
        legal_name="Clinica Legacy LTDA",
        trade_name="Clinica Legacy",
        slug=f"legacy-{uuid4().hex[:8]}",
        plan_id=plan.id,
        subscription_status="active",
    )
    db_session.add(tenant)
    db_session.flush()
    role = Role(name=f"owner-{uuid4().hex[:8]}", scope="tenant", permissions=["conversations.manage"])
    user = User(
        tenant_id=tenant.id,
        email=f"owner-{uuid4().hex[:8]}@test.com",
        full_name="Owner Legacy",
        hashed_password=hash_password("Password@123"),
        is_active=True,
    )
    db_session.add_all([role, user])
    db_session.flush()
    db_session.add(UserRole(tenant_id=tenant.id, user_id=user.id, role_id=role.id))
    db_session.add(
        WhatsAppAccount(
            tenant_id=tenant.id,
            provider_name="meta_cloud",
            phone_number_id="1101713436353674",
            business_account_id="936994182588219",
            access_token_encrypted="EAAa" + ("x" * 60),
            verify_token="verify-token-dev",
            is_active=True,
        )
    )
    db_session.commit()
    return tenant


def _conversation_with_inbound(db_session, *, tenant_id, inbound_text: str):
    suffix = str(uuid4().int % 100_000_000).zfill(8)
    patient = Patient(
        tenant_id=tenant_id,
        full_name=f"Paciente Legacy {suffix}",
        phone=f"551197{suffix}",
        normalized_phone=f"551197{suffix}",
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
    return conversation, inbound


def test_legacy_autoresponder_still_runs_when_structured_flag_disabled(monkeypatch, seeded_legacy_db, db_session):
    from app.services import ai_autoresponder_service
    from app.services import whatsapp_service

    tenant_id = seeded_legacy_db.id
    _upsert_setting(
        db_session,
        tenant_id=tenant_id,
        key="ai_autoresponder.global",
        value={
            "enabled": True,
            "structured_flow_enabled": False,
            "channels": {"whatsapp": True},
            "business_hours": {"timezone": "America/Sao_Paulo", "weekdays": [0, 1, 2, 3, 4, 5, 6], "start": "00:00", "end": "23:59"},
            "outside_business_hours_mode": "allow",
            "max_consecutive_auto_replies": 3,
            "confidence_threshold": 0.5,
            "human_queue_tag": "fila_humana_ia",
            "tone": "profissional e acolhedor",
        },
    )
    conversation, inbound = _conversation_with_inbound(
        db_session,
        tenant_id=tenant_id,
        inbound_text="Oi, quero agendar uma avaliação.",
    )

    monkeypatch.setattr(
        ai_autoresponder_service,
        "classify_intent",
        lambda *args, **kwargs: {"output": '{"intent":"agendamento","confidence":0.9}'},
    )
    monkeypatch.setattr(
        ai_autoresponder_service,
        "run_llm_task",
        lambda *args, **kwargs: {
            "output": '{"reply_text":"Claro! Posso te ajudar a agendar uma avaliação. Você prefere manhã ou tarde?","next_action":"none","action_payload":{},"confidence":0.9}',
            "metadata": {"provider": "test", "model": "legacy-flow", "task": "auto_responder"},
        },
    )
    monkeypatch.setattr(whatsapp_service, "_dispatch_outbox_item_inline", lambda *args, **kwargs: None)

    result = process_inbound_message(
        db_session,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        inbound_message_id=inbound.id,
    )

    decision = db_session.scalar(select(AIAutoresponderDecision).where(AIAutoresponderDecision.tenant_id == tenant_id))
    outbox = db_session.scalar(select(OutboxMessage).where(OutboxMessage.tenant_id == tenant_id))
    assert result["status"] == "responded"
    assert result.get("structured_flow") is not True
    assert decision is not None
    assert decision.prompt_version != "structured-v1.0"
    assert outbox is not None


def test_platform_agent_config_becomes_default_for_tenant_without_override(seeded_legacy_db, db_session):
    tenant_id = seeded_legacy_db.id

    config = set_platform_global_config(
        db_session,
        payload={
            "enabled": True,
            "conversation_flow_mode": "structured_elite",
            "structured_flow_enabled": True,
            "llm_model": "gpt-4.1",
            "pre_send_review_enabled": True,
        },
    )

    resolved = get_global_config(db_session, tenant_id=tenant_id)
    platform_row = db_session.scalar(select(FeatureFlag).where(FeatureFlag.tenant_id.is_(None), FeatureFlag.key == "platform.ai_autoresponder.global"))

    assert config["conversation_flow_mode"] == "structured_elite"
    assert resolved["conversation_flow_mode"] == "structured_elite"
    assert resolved["structured_flow_enabled"] is True
    assert resolved["llm_model"] == "gpt-4.1"
    assert resolved["pre_send_review_enabled"] is True
    assert platform_row is not None


def test_tenant_override_still_wins_over_platform_default(seeded_legacy_db, db_session):
    tenant_id = seeded_legacy_db.id

    set_platform_global_config(
        db_session,
        payload={
            "enabled": True,
            "conversation_flow_mode": "structured_elite",
            "structured_flow_enabled": True,
            "llm_model": "gpt-4.1",
        },
    )
    _upsert_setting(
        db_session,
        tenant_id=tenant_id,
        key="ai_autoresponder.global",
        value={
            "enabled": True,
            "conversation_flow_mode": "legacy",
            "structured_flow_enabled": False,
            "llm_model": "gpt-4.1-mini",
        },
    )

    resolved = get_global_config(db_session, tenant_id=tenant_id)

    assert resolved["conversation_flow_mode"] == "legacy"
    assert resolved["structured_flow_enabled"] is False
    assert resolved["llm_model"] == "gpt-4.1-mini"

from datetime import UTC, datetime, timedelta

from app.models import LinkFlowEvent, LinkFlowSession, Setting, WhatsAppAccount
from app.services.link_flow_service import (
    create_link_flow_session,
    extract_link_flow_token,
    get_intake_config,
    register_link_flow_event,
    resolve_inbound_link_flow_session,
)
from app.services.sales_demo_service import ensure_sales_outreach_sender_tenant
from app.utils.hash import sha256_text


def _enable_link_flow(db_session, tenant):
    db_session.add(
        Setting(
            tenant_id=tenant.id,
            key="intake.config",
            value={
                "mode": "link_flow",
                "link_flow": {
                    "enabled": True,
                    "cta_mode": "whatsapp_redirect",
                    "headline": "Agende com a Clinica A",
                    "trust_message": "Atendimento oficial da clinica.",
                    "button_label": "Continuar",
                    "session_ttl_minutes": 30,
                },
            },
            is_secret=False,
        )
    )


def _add_system_sender(db_session):
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


def test_link_flow_session_hashes_token_and_resolves_sanitized_text(seeded_db, db_session):
    tenant = seeded_db["tenant_a"]
    _enable_link_flow(db_session, tenant)
    _add_system_sender(db_session)
    db_session.flush()

    config = get_intake_config(db_session, tenant_id=tenant.id)
    session, raw_token, whatsapp_url = create_link_flow_session(
        db_session,
        tenant=tenant,
        config=config,
        landing_path="/agendar/tenant-a",
        browser_session_id="browser-1",
        utm_payload={"utm_source": "whatsapp"},
    )

    assert raw_token not in session.token_hash
    assert "wa.me/5511999887766" in whatsapp_url

    token, sanitized = extract_link_flow_token(f"CFX:{raw_token} Ola, quero agendar.")
    assert token == raw_token
    assert sanitized == "Ola, quero agendar."

    resolved = resolve_inbound_link_flow_session(db_session, text=f"CFX:{raw_token} Ola")
    assert resolved.is_valid
    assert resolved.session.id == session.id
    assert resolved.sanitized_text == "Ola"


def test_link_flow_session_rejects_expired_token(seeded_db, db_session):
    tenant = seeded_db["tenant_a"]
    raw_token = "expired_token_1234567890"
    session = LinkFlowSession(
        tenant_id=tenant.id,
        mode="link_flow",
        cta_mode="whatsapp_redirect",
        token_hash=sha256_text(raw_token),
        status="pending",
        landing_path="/agendar/tenant-a",
        utm_payload={},
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    db_session.add(session)
    db_session.flush()

    resolved = resolve_inbound_link_flow_session(db_session, text=f"CFX:{raw_token} Ola")

    assert not resolved.is_valid
    assert resolved.failure_reason == "session_expired"
    assert session.status == "expired"


def test_register_link_flow_event_updates_session_timestamps(seeded_db, db_session):
    tenant = seeded_db["tenant_a"]
    session = LinkFlowSession(
        tenant_id=tenant.id,
        mode="link_flow",
        cta_mode="whatsapp_redirect",
        token_hash="hash",
        status="pending",
        landing_path="/agendar/tenant-a",
        utm_payload={},
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    db_session.add(session)
    db_session.flush()

    event = register_link_flow_event(
        db_session,
        session=session,
        event_name="landing_viewed",
        page_path="/agendar/tenant-a",
        payload={"source": "test"},
    )

    db_session.flush()
    assert isinstance(event, LinkFlowEvent)
    assert session.first_opened_at is not None

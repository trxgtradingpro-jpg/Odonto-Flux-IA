from urllib.parse import parse_qs, urlparse

from sqlalchemy import select

from app.models import (
    Conversation,
    LinkFlowEvent,
    LinkFlowSession,
    Message,
    Patient,
    Setting,
    WhatsAppAccount,
)
from app.models.enums import MessageDirection, MessageStatus
from app.services.channel_dispatch_service import dispatch_patient_message
from app.services.sales_demo_service import ensure_sales_outreach_sender_tenant


SYSTEM_PHONE_NUMBER_ID = "551199988776600"


def _add_system_sender(db_session):
    sender_tenant = ensure_sales_outreach_sender_tenant(db_session)
    account = WhatsAppAccount(
        tenant_id=sender_tenant.id,
        provider_name="meta_cloud",
        phone_number_id=SYSTEM_PHONE_NUMBER_ID,
        business_account_id="123456789012345",
        display_phone="+5511999887766",
        access_token_encrypted="EAA" + ("x" * 60),
        verify_token="verify-token-dev",
        is_active=True,
    )
    db_session.add(account)
    db_session.flush()
    return account


def _enable_link_flow(db_session, tenant, *, mode="link_flow", cta_mode="whatsapp_redirect"):
    db_session.add(
        Setting(
            tenant_id=tenant.id,
            key="intake.config",
            value={
                "mode": mode,
                "link_flow": {
                    "enabled": True,
                    "cta_mode": cta_mode,
                    "headline": "Agendamento oficial",
                    "trust_message": "Continue pelo canal oficial.",
                    "button_label": "Iniciar chat" if cta_mode == "webchat" else "Continuar pelo WhatsApp",
                    "session_ttl_minutes": 30,
                },
            },
            is_secret=False,
        )
    )
    db_session.flush()


def test_public_booking_creates_session_and_tracks_events(client, seeded_db, db_session):
    tenant = seeded_db["tenant_b"]
    _enable_link_flow(db_session, tenant)
    _add_system_sender(db_session)
    db_session.commit()

    profile_response = client.get("/api/v1/public/booking/tenant-b")
    assert profile_response.status_code == 200
    assert profile_response.json()["clinic"]["slug"] == "tenant-b"

    session_response = client.post(
        "/api/v1/public/booking/tenant-b/sessions",
        json={"browser_session_id": "browser-abc", "utm_payload": {"utm_source": "whatsapp_business"}},
    )
    assert session_response.status_code == 200
    session_payload = session_response.json()
    assert "wa.me/5511999887766" in session_payload["whatsapp_url"]

    event_response = client.post(
        f"/api/v1/public/booking/sessions/{session_payload['session_id']}/events",
        json={"event_name": "landing_viewed", "page_path": "/agendar/tenant-b", "payload": {"source": "test"}},
    )
    assert event_response.status_code == 200

    session = db_session.get(LinkFlowSession, session_payload["session_id"])
    assert session is not None
    assert session.tenant_id == tenant.id
    assert session.first_opened_at is not None

    event = db_session.scalar(select(LinkFlowEvent).where(LinkFlowEvent.link_flow_session_id == session.id))
    assert event is not None
    assert event.event_name == "landing_viewed"


def test_link_flow_token_routes_meta_webhook_to_session_tenant(client, seeded_db, db_session):
    tenant = seeded_db["tenant_b"]
    _enable_link_flow(db_session, tenant)
    _add_system_sender(db_session)
    db_session.commit()

    session_response = client.post(
        "/api/v1/public/booking/tenant-b/sessions",
        json={"browser_session_id": "browser-route"},
    )
    assert session_response.status_code == 200
    session_payload = session_response.json()
    message_text = parse_qs(urlparse(session_payload["whatsapp_url"]).query)["text"][0]

    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": SYSTEM_PHONE_NUMBER_ID},
                            "messages": [
                                {
                                    "id": "wamid.link-flow.001",
                                    "from": "11977776666",
                                    "timestamp": "1712518999",
                                    "text": {"body": message_text},
                                    "type": "text",
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }

    response = client.post("/api/v1/webhooks/whatsapp", json=payload)
    assert response.status_code == 200

    patient = db_session.scalar(
        select(Patient).where(
            Patient.tenant_id == tenant.id,
            Patient.normalized_phone == "5511977776666",
        )
    )
    assert patient is not None

    conversation = db_session.scalar(select(Conversation).where(Conversation.patient_id == patient.id))
    assert conversation is not None
    assert conversation.tenant_id == tenant.id
    assert conversation.channel == "whatsapp"
    assert "entry_link_flow" in (conversation.tags or [])

    message = db_session.scalar(select(Message).where(Message.provider_message_id == "wamid.link-flow.001"))
    assert message is not None
    assert message.tenant_id == tenant.id
    assert "CFX:" not in message.body
    assert (message.payload or {}).get("entry_source") == "link_flow"

    session = db_session.get(LinkFlowSession, session_payload["session_id"])
    assert session.linked_conversation_id == conversation.id
    assert session.linked_patient_id == patient.id
    assert session.linked_at is not None


def test_intake_config_endpoints_save_and_report_status(client, seeded_db, db_session, auth_headers):
    response = client.get("/api/v1/settings/intake/config", headers=auth_headers["owner_a"])
    assert response.status_code == 200
    assert response.json()["mode"] == "official_api"

    payload = {
        "mode": "hybrid",
        "link_flow": {
            "enabled": True,
            "cta_mode": "whatsapp_redirect",
            "headline": "Agende online",
            "trust_message": "Atendimento oficial da clinica.",
            "button_label": "Continuar pelo WhatsApp",
            "session_ttl_minutes": 40,
        },
    }
    update_response = client.put("/api/v1/settings/intake/config", json=payload, headers=auth_headers["owner_a"])
    assert update_response.status_code == 200
    assert update_response.json()["mode"] == "hybrid"

    status_response = client.get("/api/v1/settings/intake/status", headers=auth_headers["owner_a"])
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["mode"] == "hybrid"
    assert "access_token" not in str(status_payload).lower()
    assert "biz_tenant_a" not in str(status_payload)


def test_official_whatsapp_inbound_without_token_keeps_legacy_tenant(client, seeded_db, db_session):
    tenant = seeded_db["tenant_a"]
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "phone_tenant_a"},
                            "messages": [
                                {
                                    "id": "wamid.official.legacy",
                                    "from": "11911112222",
                                    "timestamp": "1712518999",
                                    "text": {"body": "Oi, quero agendar"},
                                    "type": "text",
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }

    response = client.post("/api/v1/webhooks/whatsapp", json=payload)
    assert response.status_code == 200

    patient = db_session.scalar(
        select(Patient).where(
            Patient.tenant_id == tenant.id,
            Patient.normalized_phone == "5511911112222",
        )
    )
    message = db_session.scalar(select(Message).where(Message.provider_message_id == "wamid.official.legacy"))

    assert patient is not None
    assert message is not None
    assert message.tenant_id == tenant.id
    assert (message.payload or {}).get("entry_source") != "link_flow"


def test_shared_sender_without_token_does_not_guess_clinic(client, seeded_db, db_session):
    tenant = seeded_db["tenant_b"]
    account = _add_system_sender(db_session)
    db_session.commit()
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": SYSTEM_PHONE_NUMBER_ID},
                            "messages": [
                                {
                                    "id": "wamid.link-flow.no-token",
                                    "from": "11933334444",
                                    "timestamp": "1712518999",
                                    "text": {"body": "Oi, vim pelo link"},
                                    "type": "text",
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }

    response = client.post("/api/v1/webhooks/whatsapp", json=payload)
    assert response.status_code == 200

    wrong_patient = db_session.scalar(
        select(Patient).where(
            Patient.tenant_id == tenant.id,
            Patient.normalized_phone == "5511933334444",
        )
    )
    message = db_session.scalar(select(Message).where(Message.provider_message_id == "wamid.link-flow.no-token"))
    event = db_session.scalar(
        select(LinkFlowEvent).where(
            LinkFlowEvent.tenant_id == account.tenant_id,
            LinkFlowEvent.event_name == "session_invalid",
            LinkFlowEvent.link_flow_session_id.is_(None),
        )
    )

    assert wrong_patient is None
    assert message is None
    assert event is not None


def test_invalid_link_flow_token_does_not_create_clinic_conversation(client, seeded_db, db_session):
    tenant = seeded_db["tenant_b"]
    _enable_link_flow(db_session, tenant, mode="hybrid")
    account = _add_system_sender(db_session)
    db_session.commit()
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": SYSTEM_PHONE_NUMBER_ID},
                            "messages": [
                                {
                                    "id": "wamid.link-flow.invalid-token",
                                    "from": "11955556666",
                                    "timestamp": "1712518999",
                                    "text": {"body": "CFX:token_invalido_1234567890 Quero agendar"},
                                    "type": "text",
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }

    response = client.post("/api/v1/webhooks/whatsapp", json=payload)
    assert response.status_code == 200

    wrong_patient = db_session.scalar(
        select(Patient).where(
            Patient.tenant_id == tenant.id,
            Patient.normalized_phone == "5511955556666",
        )
    )
    message = db_session.scalar(select(Message).where(Message.provider_message_id == "wamid.link-flow.invalid-token"))
    event = db_session.scalar(
        select(LinkFlowEvent).where(
            LinkFlowEvent.tenant_id == account.tenant_id,
            LinkFlowEvent.event_name == "session_invalid",
            LinkFlowEvent.link_flow_session_id.is_(None),
        )
    )

    assert wrong_patient is None
    assert message is None
    assert event is not None


def test_public_webchat_creates_conversation_and_returns_safe_messages(monkeypatch, client, seeded_db, db_session):
    tenant = seeded_db["tenant_b"]
    _enable_link_flow(db_session, tenant, cta_mode="webchat")
    db_session.commit()

    def fake_process_inbound_message(db, *, tenant_id, conversation_id, inbound_message_id):
        conversation = db.get(Conversation, conversation_id)
        inbound_message = db.get(Message, inbound_message_id)
        outbound = Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            direction=MessageDirection.OUTBOUND.value,
            channel="webchat",
            sender_type="ai",
            body="Claro, posso ajudar com seu agendamento.",
            message_type="text",
            payload={"source": "test_ai"},
            status=MessageStatus.QUEUED.value,
        )
        db.add(outbound)
        db.flush()
        dispatch_patient_message(
            db,
            tenant_id=tenant_id,
            conversation=conversation,
            inbound_message=inbound_message,
            outbound_message=outbound,
            body=outbound.body,
        )
        db.commit()
        return {"status": "responded", "outbound_message_id": str(outbound.id)}

    monkeypatch.setattr(
        "app.services.ai_autoresponder_service.process_inbound_message",
        fake_process_inbound_message,
    )

    profile_response = client.get("/api/v1/public/booking/tenant-b")
    assert profile_response.status_code == 200
    assert profile_response.json()["link_flow"]["cta_mode"] == "webchat"
    assert profile_response.json()["link_flow"]["operational"] is True

    session_response = client.post(
        "/api/v1/public/booking/tenant-b/sessions",
        json={"browser_session_id": "browser-webchat", "cta_mode": "webchat"},
    )
    assert session_response.status_code == 200
    session_payload = session_response.json()
    assert session_payload["whatsapp_url"] is None
    assert session_payload["public_access_token"]

    headers = {"X-Link-Flow-Token": session_payload["public_access_token"]}
    message_response = client.post(
        f"/api/v1/public/booking/sessions/{session_payload['session_id']}/chat/messages",
        json={"text": "Quero agendar", "client_message_id": "client-webchat-1"},
        headers=headers,
    )
    assert message_response.status_code == 200

    session = db_session.get(LinkFlowSession, session_payload["session_id"])
    conversation = db_session.get(Conversation, session.linked_conversation_id)
    assert conversation.channel == "webchat"
    assert conversation.tenant_id == tenant.id

    messages_response = client.get(
        f"/api/v1/public/booking/sessions/{session_payload['session_id']}/chat/messages",
        headers=headers,
    )
    assert messages_response.status_code == 200
    public_messages = messages_response.json()["data"]
    assert [message["role"] for message in public_messages] == ["patient", "assistant"]
    assert "conversation_id" not in public_messages[0]

    duplicate_response = client.post(
        f"/api/v1/public/booking/sessions/{session_payload['session_id']}/chat/messages",
        json={"text": "retry", "client_message_id": "client-webchat-1"},
        headers=headers,
    )
    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["status"] == "duplicate"

    wrong_token_response = client.get(
        f"/api/v1/public/booking/sessions/{session_payload['session_id']}/chat/messages",
        headers={"X-Link-Flow-Token": "wrong"},
    )
    assert wrong_token_response.status_code == 403


def test_public_webchat_summary_tracks_auto_and_manual_booking_data(client, seeded_db, db_session):
    tenant = seeded_db["tenant_b"]
    _enable_link_flow(db_session, tenant, cta_mode="webchat")
    db_session.commit()

    session_response = client.post(
        "/api/v1/public/booking/tenant-b/sessions",
        json={"browser_session_id": "browser-webchat-summary", "cta_mode": "webchat"},
    )
    assert session_response.status_code == 200
    session_payload = session_response.json()
    headers = {"X-Link-Flow-Token": session_payload["public_access_token"]}

    summary_response = client.get(
        f"/api/v1/public/booking/sessions/{session_payload['session_id']}/summary",
        headers=headers,
    )
    assert summary_response.status_code == 200
    assert summary_response.json()["fields"]["patient_name"]["complete"] is False

    update_response = client.patch(
        f"/api/v1/public/booking/sessions/{session_payload['session_id']}/summary",
        json={
            "full_name": "Maria Souza",
            "email": "maria@example.com",
            "birth_date": "1992-04-18",
            "procedure_type": "Avaliacao inicial",
            "preferred_date": "2026-06-10",
        },
        headers=headers,
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["fields"]["patient_name"]["value"] == "Maria Souza"
    assert updated["fields"]["patient_name"]["complete"] is True
    assert updated["fields"]["procedure"]["value"] == "Avaliacao inicial"
    assert updated["fields"]["preferred_date"]["value"] == "2026-06-10"
    assert updated["fields"]["email"]["complete"] is True

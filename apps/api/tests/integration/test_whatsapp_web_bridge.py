from uuid import UUID, uuid4

from sqlalchemy import select

from app.models import Conversation, Message, OutboxMessage, ProspectAccount, Tenant, WhatsAppAccount
from app.models.enums import MessageStatus, OutboxStatus
from app.services import sales_demo_service
from app.services.automation_service import pending_jobs_for_dispatch
from app.services.whatsapp_service import queue_outbound_message


def _create_sender_tenant(db_session):
    tenant = Tenant(
        legal_name="ClinicFlux AI Comercial LTDA",
        trade_name="ClinicFlux AI Comercial",
        slug="bridge-sales",
        subscription_status="active",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.flush()
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
    db_session.refresh(tenant)
    return tenant


def _create_prospect(db_session):
    prospect = ProspectAccount(
        clinic_name="Clinica Bridge Selenium",
        whatsapp_phone="+55 11 98888-0001",
        city="Sao Paulo",
        state="SP",
        main_pain="perde leads no WhatsApp",
        legal_basis="interesse_legitimo_b2b",
    )
    db_session.add(prospect)
    db_session.commit()
    db_session.refresh(prospect)
    return prospect


def test_whatsapp_web_bridge_pull_ack_and_inbound_advances_outreach(client, db_session, monkeypatch):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_transport", "whatsapp_web")
    monkeypatch.setattr(sales_demo_service.settings, "whatsapp_web_bridge_token", "bridge-token")
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_video_url", "https://videos.clinicfluxai.test/comercial")
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_ai_review_enabled", False)

    started = sales_demo_service.start_sales_outreach_automation(
        db_session,
        prospect=prospect,
        actor_id=None,
        base_url="http://localhost:3000",
    )

    pull = client.get(
        "/api/v1/internal/whatsapp-web/outbox/pull?limit=5",
        headers={"Authorization": "Bearer bridge-token"},
    )
    assert pull.status_code == 200
    items = pull.json()["items"]
    assert len(items) == 1
    first_item = items[0]
    assert first_item["step"] == "reception_intro"
    assert first_item["conversation_id"] == str(started["conversation_id"])

    first_outbox = db_session.get(OutboxMessage, UUID(first_item["id"]))
    assert first_outbox is not None
    assert first_outbox.status == OutboxStatus.PROCESSING.value

    ack = client.post(
        f"/api/v1/internal/whatsapp-web/outbox/{first_item['id']}/ack",
        json={"status": "sent", "external_message_id": "wa-out-1"},
        headers={"Authorization": "Bearer bridge-token"},
    )
    assert ack.status_code == 200

    outbound_message = db_session.get(Message, started["outbound_message_id"])
    assert outbound_message is not None
    assert outbound_message.status == MessageStatus.SENT.value

    inbound = client.post(
        "/api/v1/internal/whatsapp-web/inbound",
        json={
            "conversation_id": first_item["conversation_id"],
            "body": "Pode mandar a demo e o video.",
            "external_message_id": f"wa-in-{uuid4().hex[:8]}",
        },
        headers={"Authorization": "Bearer bridge-token"},
    )
    assert inbound.status_code == 200
    assert inbound.json()["status"] == "received"

    db_session.refresh(prospect)
    outreach = (prospect.proposal_snapshot or {}).get("outreach", {})
    assert outreach.get("last_step") == "video_followup"
    assert outreach.get("automation_active") is False
    assert outreach.get("automation_stop_reason") == "sequence_completed"

    sender_outboxes = db_session.execute(
        select(OutboxMessage).where(OutboxMessage.tenant_id == sender_tenant.id).order_by(OutboxMessage.created_at.asc())
    ).scalars().all()
    assert len(sender_outboxes) == 3

    second_pull = client.get(
        "/api/v1/internal/whatsapp-web/outbox/pull?limit=5",
        headers={"Authorization": "Bearer bridge-token"},
    )
    assert second_pull.status_code == 200
    second_items = second_pull.json()["items"]
    assert len(second_items) == 1
    assert second_items[0]["step"] == "decision_maker_pitch"

    remaining_outboxes = db_session.execute(
        select(OutboxMessage)
        .where(OutboxMessage.tenant_id == sender_tenant.id)
        .order_by(OutboxMessage.created_at.asc())
    ).scalars().all()
    video_outbox = next(
        item
        for item in remaining_outboxes
        if (((item.payload or {}).get("metadata") or {}).get("step") == "video_followup")
    )
    assert video_outbox.status == OutboxStatus.PENDING.value
    assert video_outbox.next_retry_at is not None


def test_whatsapp_web_bridge_prioritizes_replies_triggered_by_inbound(client, db_session, monkeypatch):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_transport", "whatsapp_web")
    monkeypatch.setattr(sales_demo_service.settings, "whatsapp_web_bridge_token", "bridge-token")
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_video_url", "https://videos.clinicfluxai.test/comercial")
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_ai_review_enabled", False)

    started = sales_demo_service.start_sales_outreach_automation(
        db_session,
        prospect=prospect,
        actor_id=None,
        base_url="http://localhost:3000",
    )

    first_pull = client.get(
        "/api/v1/internal/whatsapp-web/outbox/pull?limit=5",
        headers={"Authorization": "Bearer bridge-token"},
    )
    assert first_pull.status_code == 200
    first_item = first_pull.json()["items"][0]

    ack = client.post(
        f"/api/v1/internal/whatsapp-web/outbox/{first_item['id']}/ack",
        json={"status": "sent", "external_message_id": "wa-out-1"},
        headers={"Authorization": "Bearer bridge-token"},
    )
    assert ack.status_code == 200

    waiting_outbox = queue_outbound_message(
        db_session,
        tenant_id=sender_tenant.id,
        conversation_id=UUID(first_item["conversation_id"]),
        to=prospect.whatsapp_phone,
        body="Mensagem antiga que ainda estava pendente.",
        metadata={
            "source": "sales_outreach",
            "step": "manual_followup",
            "transport": "whatsapp_web_bridge",
        },
        immediate_dispatch=False,
        commit=True,
    )

    inbound = client.post(
        "/api/v1/internal/whatsapp-web/inbound",
        json={
            "conversation_id": first_item["conversation_id"],
            "body": "Pode falar com o gestor e mandar a demo.",
            "external_message_id": f"wa-in-{uuid4().hex[:8]}",
        },
        headers={"Authorization": "Bearer bridge-token"},
    )
    assert inbound.status_code == 200

    second_pull = client.get(
        "/api/v1/internal/whatsapp-web/outbox/pull?limit=5",
        headers={"Authorization": "Bearer bridge-token"},
    )
    assert second_pull.status_code == 200
    second_items = second_pull.json()["items"]
    assert len(second_items) == 1
    assert second_items[0]["step"] == "decision_maker_pitch"

    db_session.refresh(waiting_outbox)
    assert waiting_outbox.status == OutboxStatus.PENDING.value


def test_whatsapp_web_bridge_send_gate_waits_without_reply(client, db_session, monkeypatch):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_transport", "whatsapp_web")
    monkeypatch.setattr(sales_demo_service.settings, "whatsapp_web_bridge_token", "bridge-token")
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_ai_review_enabled", False)
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_send_gate_min_wait_minutes", 120)

    started = sales_demo_service.start_sales_outreach_automation(
        db_session,
        prospect=prospect,
        actor_id=None,
        base_url="http://localhost:3000",
    )

    first_pull = client.get(
        "/api/v1/internal/whatsapp-web/outbox/pull?limit=5",
        headers={"Authorization": "Bearer bridge-token"},
    )
    assert first_pull.status_code == 200
    first_item = first_pull.json()["items"][0]

    ack = client.post(
        f"/api/v1/internal/whatsapp-web/outbox/{first_item['id']}/ack",
        json={"status": "sent", "external_message_id": "wa-out-1"},
        headers={"Authorization": "Bearer bridge-token"},
    )
    assert ack.status_code == 200

    sales_demo_service.send_sales_outreach_step(
        db_session,
        prospect=prospect,
        step="clarification_reply",
        actor_id=None,
        base_url="http://localhost:3000",
    )

    second_pull = client.get(
        "/api/v1/internal/whatsapp-web/outbox/pull?limit=5",
        headers={"Authorization": "Bearer bridge-token"},
    )
    assert second_pull.status_code == 200
    assert second_pull.json()["items"] == []

    waiting_outbox = db_session.execute(
        select(OutboxMessage)
        .where(OutboxMessage.tenant_id == sender_tenant.id)
        .order_by(OutboxMessage.created_at.desc())
        .limit(1)
    ).scalar_one()
    assert waiting_outbox.status == OutboxStatus.PENDING.value
    assert waiting_outbox.next_retry_at is not None
    assert "ainda nao respondeu" in (waiting_outbox.last_error or "")


def test_pending_jobs_for_dispatch_skips_whatsapp_web_bridge(db_session, monkeypatch):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_transport", "whatsapp_web")

    sales_demo_service.start_sales_outreach_automation(
        db_session,
        prospect=prospect,
        actor_id=None,
        base_url="http://localhost:3000",
    )

    dispatchable = pending_jobs_for_dispatch(db_session)
    assert dispatchable == []

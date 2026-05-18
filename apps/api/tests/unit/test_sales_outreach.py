from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from app.core.exceptions import ApiError
from app.models import Appointment, Conversation, Message, OutboxMessage, ProspectAccount, Setting, Tenant, User, WhatsAppAccount
from app.models.enums import MessageDirection, MessageStatus, OutboxStatus
from app.schemas.admin_sales import ProspectUpdate
from app.services import sales_demo_service
from app.services.whatsapp_service import process_outbox_batch, queue_outbound_message


def _create_sender_tenant(db_session):
    tenant = Tenant(
        legal_name="OdontoFlux Comercial LTDA",
        trade_name="OdontoFlux Comercial",
        slug="odf-sales",
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
        clinic_name="Clinica Conversao Segura",
        whatsapp_phone="+55 11 98888-1111",
        city="Sao Paulo",
        state="SP",
        main_pain="retrabalho na recepcao",
        legal_basis="interesse_legitimo_b2b",
    )
    db_session.add(prospect)
    db_session.commit()
    db_session.refresh(prospect)
    return prospect


def test_send_sales_outreach_step_creates_transparent_whatsapp_message(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_display_name", "Equipe OdontoFlux")

    result = sales_demo_service.send_sales_outreach_step(
        db_session,
        prospect=prospect,
        step="reception_intro",
        actor_id=None,
        base_url="http://localhost:3000",
    )

    db_session.refresh(prospect)
    conversation = db_session.get(Conversation, result["conversation_id"])
    outbound_message = db_session.get(Message, result["outbound_message_id"])
    outbox = db_session.scalar(select(OutboxMessage).where(OutboxMessage.tenant_id == sender_tenant.id))

    assert result["step"] == "reception_intro"
    assert result["destination"] == "+55 11 98888-1111"
    assert "de forma comercial e transparente" in result["message_text"].lower()
    assert prospect.status == "contato_iniciado"
    assert conversation is not None
    assert "prospect_outreach" in (conversation.tags or [])
    assert f"prospect_id:{prospect.id}" in (conversation.tags or [])
    assert conversation.ai_autoresponder_enabled is False
    assert outbound_message is not None
    assert outbound_message.direction == MessageDirection.OUTBOUND.value
    assert outbound_message.status == MessageStatus.QUEUED.value
    assert outbox is not None
    assert ((outbox.payload or {}).get("metadata") or {}).get("step") == "reception_intro"
    assert (prospect.proposal_snapshot or {}).get("outreach", {}).get("last_step") == "reception_intro"


def test_sync_prospect_outreach_reply_updates_timeline_and_status(seeded_db, db_session):
    prospect = _create_prospect(db_session)
    conversation = Conversation(
        tenant_id=seeded_db["tenant_a"].id,
        channel="whatsapp",
        status="aberta",
        ai_autoresponder_enabled=False,
        tags=["prospect_outreach", f"prospect_id:{prospect.id}"],
    )
    db_session.add(conversation)
    db_session.flush()

    inbound_message = Message(
        tenant_id=seeded_db["tenant_a"].id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND.value,
        channel="whatsapp",
        sender_type="patient",
        body="Pode me mandar a demo e depois o video.",
        message_type="text",
        payload={},
        status=MessageStatus.RECEIVED.value,
    )
    db_session.add(inbound_message)
    db_session.flush()

    sales_demo_service.sync_prospect_outreach_reply(
        db_session,
        conversation=conversation,
        message=inbound_message,
    )
    db_session.commit()
    db_session.refresh(prospect)

    timeline = db_session.execute(
        select(sales_demo_service.ProspectTimelineEvent)
        .where(sales_demo_service.ProspectTimelineEvent.prospect_account_id == prospect.id)
        .order_by(sales_demo_service.ProspectTimelineEvent.created_at.desc())
    ).scalars().all()

    assert prospect.status == "respondeu"
    assert (prospect.proposal_snapshot or {}).get("outreach", {}).get("last_reply_preview")
    assert timeline
    assert timeline[0].event_type == "prospect.outreach.reply_received"


def test_start_sales_outreach_automation_marks_snapshot_and_sends_first_step(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)

    result = sales_demo_service.start_sales_outreach_automation(
        db_session,
        prospect=prospect,
        actor_id=None,
        base_url="http://localhost:3000",
    )

    db_session.refresh(prospect)

    outreach = (prospect.proposal_snapshot or {}).get("outreach", {})
    assert result["step"] == "reception_intro"
    assert outreach.get("automation_active") is True
    assert outreach.get("automation_mode") == "transparent_b2b"
    assert outreach.get("auto_progress") is True
    assert outreach.get("last_step") == "reception_intro"


def test_send_sales_outreach_step_raises_when_inline_dispatch_fails(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)

    failed_outbox = SimpleNamespace(
        id=uuid4(),
        status=OutboxStatus.DEAD_LETTER.value,
        last_error="REJECTED_NOT_ENOUGH_CREDITS",
    )

    def _fake_queue_outbound_message(*args, **kwargs):
        return failed_outbox

    monkeypatch.setattr(sales_demo_service, "queue_outbound_message", _fake_queue_outbound_message)

    with pytest.raises(ApiError) as exc_info:
        sales_demo_service.send_sales_outreach_step(
            db_session,
            prospect=prospect,
            step="reception_intro",
            actor_id=None,
            base_url="http://localhost:3000",
        )

    db_session.refresh(prospect)

    outreach = (prospect.proposal_snapshot or {}).get("outreach", {})
    assert exc_info.value.code == "SALES_OUTREACH_DISPATCH_FAILED"
    assert outreach.get("last_dispatch_status") == OutboxStatus.DEAD_LETTER.value
    assert outreach.get("last_dispatch_error") == "REJECTED_NOT_ENOUGH_CREDITS"


def test_meta_allowed_list_error_moves_outbox_to_dead_letter_without_retry(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    outbox = queue_outbound_message(
        db_session,
        tenant_id=sender_tenant.id,
        conversation_id=None,
        to="5515551902123",
        body="Teste allow list",
        message_type="text",
        immediate_dispatch=False,
        commit=True,
    )

    from app.integrations.whatsapp.cloud_api import WhatsAppCloudProvider

    def _fake_send_text_message(self, *, phone_number_id, access_token, to, body):
        request = httpx.Request("POST", f"https://graph.facebook.com/v19.0/{phone_number_id}/messages")
        response = httpx.Response(
            400,
            request=request,
            json={
                "error": {
                    "message": "(#131030) Recipient phone number not in allowed list",
                    "code": 131030,
                    "type": "OAuthException",
                    "error_data": {
                        "details": "O numero de telefone do destinatario nao esta na lista de permissao.",
                    },
                }
            },
        )
        raise httpx.HTTPStatusError("WhatsApp API request failed (400): code=131030", request=request, response=response)

    monkeypatch.setattr(WhatsAppCloudProvider, "send_text_message", _fake_send_text_message)

    result = process_outbox_batch(db_session, batch_size=20)
    refreshed = db_session.get(OutboxMessage, outbox.id)

    assert result["processed"] >= 1
    assert refreshed is not None
    assert refreshed.status == OutboxStatus.DEAD_LETTER.value
    assert refreshed.retry_count == refreshed.max_retries
    assert "131030" in (refreshed.last_error or "")


def test_meta_auth_error_moves_outbox_to_dead_letter_without_retry(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    outbox = queue_outbound_message(
        db_session,
        tenant_id=sender_tenant.id,
        conversation_id=None,
        to="5511940431906",
        body="Teste auth",
        message_type="text",
        immediate_dispatch=False,
        commit=True,
    )

    from app.integrations.whatsapp.cloud_api import WhatsAppCloudProvider

    def _fake_send_text_message(self, *, phone_number_id, access_token, to, body):
        request = httpx.Request("POST", f"https://graph.facebook.com/v19.0/{phone_number_id}/messages")
        response = httpx.Response(
            401,
            request=request,
            json={
                "error": {
                    "message": "Authentication Error",
                    "code": 190,
                    "type": "OAuthException",
                }
            },
        )
        raise httpx.HTTPStatusError("WhatsApp API request failed (401): code=190 | Authentication Error", request=request, response=response)

    monkeypatch.setattr(WhatsAppCloudProvider, "send_text_message", _fake_send_text_message)

    result = process_outbox_batch(db_session, batch_size=20)
    refreshed = db_session.get(OutboxMessage, outbox.id)

    assert result["processed"] >= 1
    assert refreshed is not None
    assert refreshed.status == OutboxStatus.DEAD_LETTER.value
    assert refreshed.retry_count == refreshed.max_retries
    assert "190" in (refreshed.last_error or "")


def test_sync_prospect_outreach_reply_advances_automation_sequence(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_video_url", "https://videos.odontoflux.test/demo-comercial")

    started = sales_demo_service.start_sales_outreach_automation(
        db_session,
        prospect=prospect,
        actor_id=None,
        base_url="http://localhost:3000",
    )
    conversation = db_session.get(Conversation, started["conversation_id"])

    inbound_message = Message(
        tenant_id=sender_tenant.id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND.value,
        channel="whatsapp",
        sender_type="patient",
        body="Pode me mandar a demo e o video.",
        message_type="text",
        payload={},
        status=MessageStatus.RECEIVED.value,
    )
    db_session.add(inbound_message)
    db_session.flush()

    sales_demo_service.sync_prospect_outreach_reply(
        db_session,
        conversation=conversation,
        message=inbound_message,
    )
    db_session.commit()
    db_session.refresh(prospect)

    outboxes = db_session.execute(
        select(OutboxMessage).where(OutboxMessage.tenant_id == sender_tenant.id).order_by(OutboxMessage.created_at.asc())
    ).scalars().all()
    timeline = db_session.execute(
        select(sales_demo_service.ProspectTimelineEvent)
        .where(sales_demo_service.ProspectTimelineEvent.prospect_account_id == prospect.id)
        .order_by(sales_demo_service.ProspectTimelineEvent.created_at.desc())
    ).scalars().all()

    outreach = (prospect.proposal_snapshot or {}).get("outreach", {})
    assert len(outboxes) == 3
    assert outreach.get("automation_active") is False
    assert outreach.get("automation_stop_reason") == "sequence_completed"
    assert outreach.get("last_step") == "video_followup"
    assert any(event.event_type == "prospect.outreach.decision_maker_pitch" for event in timeline)
    assert any(event.event_type == "prospect.outreach.video_followup" for event in timeline)
    assert any(event.event_type == "prospect.outreach.automation_completed" for event in timeline)


def test_generate_demo_keeps_single_catalog_setting_per_key(monkeypatch, seeded_db, db_session):
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(
        sales_demo_service,
        "_ai_draft",
        lambda db, demo_prospect, services: sales_demo_service.build_fallback_ai_draft(demo_prospect, services),
    )

    result = sales_demo_service.generate_demo(
        db_session,
        prospect,
        actor_id=None,
        base_url="http://localhost:3000",
    )

    demo_tenant_id = result["prospect"].demo_tenant_id
    service_catalog_count = db_session.scalar(
        select(func.count(Setting.id)).where(
            Setting.tenant_id == demo_tenant_id,
            Setting.key == "service_catalog.global",
        )
    )
    services_catalog_count = db_session.scalar(
        select(func.count(Setting.id)).where(
            Setting.tenant_id == demo_tenant_id,
            Setting.key == "services.catalog",
        )
    )

    assert result["access_token"]
    assert "demo_token=" in result["demo_login_url"]
    assert service_catalog_count == 1
    assert services_catalog_count == 1


def test_generate_demo_disables_guided_tour_by_default(monkeypatch, seeded_db, db_session):
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(
        sales_demo_service,
        "_ai_draft",
        lambda db, demo_prospect, services: sales_demo_service.build_fallback_ai_draft(demo_prospect, services),
    )

    result = sales_demo_service.generate_demo(
        db_session,
        prospect,
        actor_id=None,
        base_url="http://localhost:3000",
    )

    guide_setting = db_session.scalar(
        select(Setting).where(
            Setting.tenant_id == result["prospect"].demo_tenant_id,
            Setting.key == sales_demo_service.DEMO_GUIDE_SETTING_KEY,
        )
    )

    assert guide_setting is not None
    assert (guide_setting.value or {}).get("enabled") is False


def test_generate_demo_applies_demo_intake_config_and_syncs_updates(monkeypatch, seeded_db, db_session):
    prospect = _create_prospect(db_session)
    prospect.proposal_snapshot = {
        "demo_intake": {
            "mode": "link_flow",
            "link_flow": {
                "enabled": True,
                "cta_mode": "webchat",
            },
        }
    }
    db_session.add(prospect)
    db_session.commit()
    db_session.refresh(prospect)

    monkeypatch.setattr(
        sales_demo_service,
        "_ai_draft",
        lambda db, demo_prospect, services: sales_demo_service.build_fallback_ai_draft(demo_prospect, services),
    )

    generated = sales_demo_service.generate_demo(
        db_session,
        prospect,
        actor_id=None,
        base_url="http://localhost:3000",
    )

    intake_setting = db_session.scalar(
        select(Setting).where(
            Setting.tenant_id == generated["prospect"].demo_tenant_id,
            Setting.key == "intake.config",
        )
    )
    assert intake_setting is not None
    assert intake_setting.value["mode"] == "link_flow"
    assert intake_setting.value["link_flow"]["cta_mode"] == "webchat"

    updated = sales_demo_service.update_prospect(
        db_session,
        prospect,
        ProspectUpdate(
            proposal_snapshot={
                **(prospect.proposal_snapshot or {}),
                "demo_intake": {
                    "mode": "hybrid",
                    "link_flow": {
                        "enabled": True,
                        "cta_mode": "whatsapp_redirect",
                    },
                },
            },
        ),
        actor_id=None,
    )
    refreshed_setting = db_session.scalar(
        select(Setting).where(
            Setting.tenant_id == updated.demo_tenant_id,
            Setting.key == "intake.config",
        )
    )
    assert refreshed_setting is not None
    assert refreshed_setting.value["mode"] == "hybrid"
    assert refreshed_setting.value["link_flow"]["cta_mode"] == "whatsapp_redirect"


def test_redeem_demo_token_returns_test_phone_and_whatsapp_link(monkeypatch, seeded_db, db_session):
    prospect = _create_prospect(db_session)
    prospect.test_phone_number = "(11) 98888-7777"
    db_session.add(prospect)
    db_session.commit()
    db_session.refresh(prospect)

    monkeypatch.setattr(
        sales_demo_service,
        "_ai_draft",
        lambda db, demo_prospect, services: sales_demo_service.build_fallback_ai_draft(demo_prospect, services),
    )

    generated = sales_demo_service.generate_demo(
        db_session,
        prospect,
        actor_id=None,
        base_url="http://localhost:3000",
    )

    redeemed = sales_demo_service.redeem_demo_token(
        db_session,
        token=generated["access_token"],
        session_id="demo-session-test",
    )

    assert redeemed["demo_test_phone_number"] == "(11) 98888-7777"
    assert redeemed["demo_whatsapp_link"] == "https://wa.me/5511988887777"
    assert redeemed["demo_target_path"] == "/conversas"


def test_redeem_demo_token_keeps_international_country_code(monkeypatch, seeded_db, db_session):
    prospect = _create_prospect(db_session)
    prospect.test_phone_number = "+44 7786 004289"
    db_session.add(prospect)
    db_session.commit()
    db_session.refresh(prospect)

    monkeypatch.setattr(
        sales_demo_service,
        "_ai_draft",
        lambda db, demo_prospect, services: sales_demo_service.build_fallback_ai_draft(demo_prospect, services),
    )

    generated = sales_demo_service.generate_demo(
        db_session,
        prospect,
        actor_id=None,
        base_url="http://localhost:3000",
    )

    redeemed = sales_demo_service.redeem_demo_token(
        db_session,
        token=generated["access_token"],
        session_id="demo-session-international",
    )

    assert redeemed["demo_test_phone_number"] == "+44 7786 004289"
    assert redeemed["demo_whatsapp_link"] == "https://wa.me/447786004289"


def test_redeem_demo_token_returns_webchat_entry_metadata(monkeypatch, seeded_db, db_session):
    prospect = _create_prospect(db_session)
    prospect.proposal_snapshot = {
        "demo_intake": {
            "mode": "link_flow",
            "link_flow": {
                "enabled": True,
                "cta_mode": "webchat",
            },
        },
    }
    db_session.add(prospect)
    db_session.commit()
    db_session.refresh(prospect)

    monkeypatch.setattr(
        sales_demo_service,
        "_ai_draft",
        lambda db, demo_prospect, services: sales_demo_service.build_fallback_ai_draft(demo_prospect, services),
    )

    generated = sales_demo_service.generate_demo(
        db_session,
        prospect,
        actor_id=None,
        base_url="http://localhost:3000",
    )

    redeemed = sales_demo_service.redeem_demo_token(
        db_session,
        token=generated["access_token"],
        session_id="demo-session-webchat",
    )

    assert redeemed["demo_target_path"] == "/conversas"
    assert redeemed["demo_entry_channel"] == "webchat"
    assert redeemed["demo_public_entry_path"] == f"/agendar/{generated['prospect'].slug}"


def test_generate_demo_populates_business_week_with_conversation_backed_appointments(monkeypatch, seeded_db, db_session):
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(
        sales_demo_service,
        "_ai_draft",
        lambda db, demo_prospect, services: sales_demo_service.build_fallback_ai_draft(demo_prospect, services),
    )

    first_result = sales_demo_service.generate_demo(
        db_session,
        prospect,
        actor_id=None,
        base_url="http://localhost:3000",
    )

    demo_tenant_id = first_result["prospect"].demo_tenant_id
    appointments_before = db_session.execute(
        select(Appointment)
        .where(
            Appointment.tenant_id == demo_tenant_id,
            Appointment.origin == "demo_personalizada",
        )
        .order_by(Appointment.starts_at.asc())
    ).scalars().all()
    conversations = db_session.execute(
        select(Conversation).where(
            Conversation.tenant_id == demo_tenant_id,
            Conversation.channel == "whatsapp",
        )
    ).scalars().all()

    patient_ids_with_whatsapp = {conversation.patient_id for conversation in conversations if conversation.patient_id}
    week_days = {appointment.starts_at.weekday() for appointment in appointments_before}

    assert first_result["prospect"].demo_checklist["agenda_seeded"] is True
    assert first_result["prospect"].demo_checklist["conversations_seeded"] is True
    assert len(appointments_before) >= 5
    assert {0, 1, 2, 3, 4}.issubset(week_days)
    assert all(appointment.patient_id in patient_ids_with_whatsapp for appointment in appointments_before)

    second_result = sales_demo_service.generate_demo(
        db_session,
        first_result["prospect"],
        actor_id=None,
        base_url="http://localhost:3000",
    )

    appointments_after = db_session.execute(
        select(Appointment)
        .where(
            Appointment.tenant_id == demo_tenant_id,
            Appointment.origin == "demo_personalizada",
        )
        .order_by(Appointment.starts_at.asc())
    ).scalars().all()

    assert second_result["prospect"].demo_tenant_id == demo_tenant_id
    assert len(appointments_after) == len(appointments_before)


def test_cleanup_demo_resources_removes_demo_tenant_data(monkeypatch, seeded_db, db_session):
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(
        sales_demo_service,
        "_ai_draft",
        lambda db, demo_prospect, services: sales_demo_service.build_fallback_ai_draft(demo_prospect, services),
    )

    generated = sales_demo_service.generate_demo(
        db_session,
        prospect,
        actor_id=None,
        base_url="http://localhost:3000",
    )

    demo_tenant_id = generated["prospect"].demo_tenant_id
    demo_user_id = generated["prospect"].demo_user_id
    assert demo_tenant_id is not None
    assert demo_user_id is not None

    appointments_before = db_session.scalar(
        select(func.count()).select_from(Appointment).where(Appointment.tenant_id == demo_tenant_id)
    )
    conversations_before = db_session.scalar(
        select(func.count()).select_from(Conversation).where(Conversation.tenant_id == demo_tenant_id)
    )
    assert appointments_before and appointments_before > 0
    assert conversations_before and conversations_before > 0

    sales_demo_service.cleanup_demo_resources(
        db_session,
        prospect=generated["prospect"],
        reason="expired",
        actor_id=None,
    )
    db_session.commit()
    db_session.refresh(prospect)

    appointments_after = db_session.scalar(
        select(func.count()).select_from(Appointment).where(Appointment.tenant_id == demo_tenant_id)
    )
    conversations_after = db_session.scalar(
        select(func.count()).select_from(Conversation).where(Conversation.tenant_id == demo_tenant_id)
    )

    assert prospect.demo_tenant_id is None
    assert prospect.demo_user_id is None
    assert prospect.demo_status == "expirada"
    assert db_session.get(Tenant, demo_tenant_id) is None
    assert db_session.get(User, demo_user_id) is None
    assert appointments_after == 0
    assert conversations_after == 0


def test_cleanup_expired_demos_purges_due_demo_and_clears_links(monkeypatch, seeded_db, db_session):
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(
        sales_demo_service,
        "_ai_draft",
        lambda db, demo_prospect, services: sales_demo_service.build_fallback_ai_draft(demo_prospect, services),
    )

    generated = sales_demo_service.generate_demo(
        db_session,
        prospect,
        actor_id=None,
        base_url="http://localhost:3000",
    )

    demo_tenant_id = generated["prospect"].demo_tenant_id
    assert demo_tenant_id is not None

    generated["prospect"].demo_expires_at = datetime.now(UTC) - timedelta(minutes=5)
    db_session.add(generated["prospect"])
    db_session.commit()

    result = sales_demo_service.cleanup_expired_demos(db_session)
    db_session.refresh(prospect)

    assert result == {"processed": 1, "cleaned": 1}
    assert prospect.demo_tenant_id is None
    assert prospect.demo_user_id is None
    assert prospect.demo_status == "expirada"
    assert db_session.get(Tenant, demo_tenant_id) is None


def test_redeem_demo_token_removes_expired_demo_data(monkeypatch, seeded_db, db_session):
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(
        sales_demo_service,
        "_ai_draft",
        lambda db, demo_prospect, services: sales_demo_service.build_fallback_ai_draft(demo_prospect, services),
    )

    generated = sales_demo_service.generate_demo(
        db_session,
        prospect,
        actor_id=None,
        base_url="http://localhost:3000",
    )

    demo_tenant_id = generated["prospect"].demo_tenant_id
    generated["prospect"].demo_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.add(generated["prospect"])
    db_session.commit()

    with pytest.raises(ApiError) as exc:
        sales_demo_service.redeem_demo_token(
            db_session,
            token=generated["access_token"],
            session_id="expired-demo-session",
        )

    db_session.refresh(prospect)

    assert exc.value.code == "DEMO_EXPIRED"
    assert prospect.demo_tenant_id is None
    assert prospect.demo_user_id is None
    assert prospect.demo_status == "expirada"
    assert db_session.get(Tenant, demo_tenant_id) is None


def test_simulate_sales_outreach_lab_saves_last_run_and_marks_conversion(monkeypatch, seeded_db, db_session):
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(
        sales_demo_service,
        "_ensure_outreach_demo_link",
        lambda db, prospect, actor_id, base_url: "http://localhost:3000/login?demo_token=lab123",
    )
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_video_url", "https://videos.odontoflux.test/comercial")

    result = sales_demo_service.simulate_sales_outreach_lab(
        db_session,
        prospect=prospect,
        actor_id=None,
        base_url="http://localhost:3000",
        scenario="manager_interested",
    )

    db_session.refresh(prospect)
    outreach_lab = (prospect.proposal_snapshot or {}).get("outreach_lab", {})
    last_run = outreach_lab.get("last_run", {})
    timeline = db_session.execute(
        select(sales_demo_service.ProspectTimelineEvent)
        .where(sales_demo_service.ProspectTimelineEvent.prospect_account_id == prospect.id)
        .order_by(sales_demo_service.ProspectTimelineEvent.created_at.desc())
    ).scalars().all()

    assert result["converted"] is True
    assert result["outcome"] == "meeting_requested"
    assert result["demo_login_url"] == "http://localhost:3000/login?demo_token=lab123"
    assert len(result["transcript"]) >= 6
    assert last_run.get("scenario") == "manager_interested"
    assert last_run.get("converted") is True
    assert (last_run.get("metrics") or {}).get("reached_decision_maker") is True
    assert outreach_lab.get("scenario_stats", {}).get("manager_interested", {}).get("runs") == 1
    assert timeline
    assert timeline[0].event_type == "prospect.outreach_lab.completed"


def test_simulate_sales_outreach_lab_reception_blocks_without_conversion(seeded_db, db_session):
    prospect = _create_prospect(db_session)

    result = sales_demo_service.simulate_sales_outreach_lab(
        db_session,
        prospect=prospect,
        actor_id=None,
        base_url="http://localhost:3000",
        scenario="reception_blocks",
    )

    db_session.refresh(prospect)
    last_run = ((prospect.proposal_snapshot or {}).get("outreach_lab") or {}).get("last_run", {})

    assert result["converted"] is False
    assert result["outcome"] == "blocked_by_reception"
    assert result["demo_login_url"] is None
    assert (result["metrics"] or {}).get("reached_decision_maker") is False
    assert last_run.get("scenario") == "reception_blocks"
    assert last_run.get("converted") is False

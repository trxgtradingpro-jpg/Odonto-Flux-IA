from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import func, select

from app.core.exceptions import ApiError
from app.models import (
    Appointment,
    Conversation,
    Message,
    OutboxMessage,
    Professional,
    ProspectAccount,
    SalesOutreachAutomationBatchItem,
    Setting,
    Tenant,
    Unit,
    User,
    WhatsAppAccount,
)
from app.models.enums import MessageDirection, MessageStatus, OutboxStatus
from app.schemas.admin_sales import ProspectCreate, ProspectUpdate
from app.services import sales_demo_service
from app.services import sales_outreach_automation_service
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


def test_admin_internal_whatsapp_simulator_does_not_require_test_phone(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)
    prospect.test_phone_number = None
    db_session.add(prospect)
    db_session.commit()

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)

    conversation = sales_demo_service.ensure_admin_whatsapp_test_contact(db_session, prospect=prospect)

    messages = db_session.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
    ).scalars().all()
    outbox_count = db_session.scalar(select(func.count()).select_from(OutboxMessage)) or 0

    assert sales_demo_service.ADM_INTERNAL_WHATSAPP_SIMULATION_TAG in (conversation.tags or [])
    assert "adm_whatsapp_test_contact" in (conversation.tags or [])
    assert conversation.ai_autoresponder_enabled is False
    assert len(messages) == 1
    assert messages[0].direction == MessageDirection.OUTBOUND.value
    assert messages[0].status == MessageStatus.SENT.value
    assert messages[0].payload["source"] == sales_demo_service.ADM_INTERNAL_WHATSAPP_SIMULATION_SOURCE
    assert messages[0].payload["internal_delivery"] is True
    assert outbox_count == 0


def test_admin_internal_whatsapp_simulator_creates_clinic_reply_and_ai_response_without_outbox(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)

    conversation = sales_demo_service.ensure_admin_whatsapp_test_contact(db_session, prospect=prospect)
    result = sales_demo_service.simulate_admin_internal_whatsapp_inbound(
        db_session,
        prospect=prospect,
        conversation=conversation,
        body="Bom dia, sou da recepcao. Como posso ajudar?",
        actor_id=seeded_db["admin"].id,
    )

    inbound = result["inbound_message"]
    outbound = result["outbound_message"]
    outbox_count = db_session.scalar(select(func.count()).select_from(OutboxMessage)) or 0

    assert inbound.direction == MessageDirection.INBOUND.value
    assert inbound.payload["simulated_clinic"] is True
    assert inbound.payload["internal_delivery"] is True
    assert outbound.direction == MessageDirection.OUTBOUND.value
    assert outbound.sender_type == "ai"
    assert outbound.status == MessageStatus.SENT.value
    assert outbound.payload["source"] == sales_demo_service.ADM_INTERNAL_WHATSAPP_SIMULATION_SOURCE
    assert outbound.payload["reply_to_message_id"] == str(inbound.id)
    assert outbound.payload["internal_delivery"] is True
    assert result["internal_delivery"] is True
    assert outbox_count == 0


def test_admin_internal_whatsapp_simulator_keeps_context_and_blocks_localhost_links(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)
    prospect.clinic_name = "SAC Dental Family"
    prospect.owner_name = None
    prospect.manager_name = None
    db_session.add(prospect)
    db_session.commit()

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)

    conversation = sales_demo_service.ensure_admin_whatsapp_test_contact(db_session, prospect=prospect)
    replies = []
    for body in [
        "Sim o gerente sou eu",
        "nao entendi",
        "entendi eu sou o dono da clinica",
        "gostei",
    ]:
        result = sales_demo_service.simulate_admin_internal_whatsapp_inbound(
            db_session,
            prospect=prospect,
            conversation=conversation,
            body=body,
            actor_id=seeded_db["admin"].id,
        )
        replies.append(result["outbound_message"].body)

    normalized_replies = [sales_demo_service._normalized_lookup_text(item) for item in replies]

    assert all("localhost" not in item.lower() for item in replies)
    assert all("demonstracao rapida:" not in item.lower() for item in replies)
    assert all("sac!" not in item.lower() for item in replies)
    assert len(set(normalized_replies)) == len(normalized_replies)
    assert "explicando de forma simples" in normalized_replies[1]
    assert "falo direto contigo" in normalized_replies[2]
    assert "demo curta" in normalized_replies[3]
    assert db_session.scalar(select(func.count()).select_from(OutboxMessage)) == 0


def test_admin_internal_whatsapp_simulator_passes_ten_contextual_conversation_scenarios(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)

    scenarios = [
        {
            "clinic": "Sorriso Centro",
            "turns": [
                {"body": "Sou o gerente, pode falar comigo", "expect": ["falo direto contigo", "demo curta"]},
                {"body": "nao entendi", "expect": ["explicando de forma simples", "whatsapp"]},
                {"body": "gostei", "expect": ["demo curta", "whatsapp"]},
            ],
        },
        {
            "clinic": "Clarear Odonto",
            "turns": [
                {"body": "Bom dia, sou da recepcao. Como posso ajudar?", "expect": ["meu contato e comercial", "quem cuida"]},
            ],
        },
        {
            "clinic": "Implante Norte",
            "turns": [
                {"body": "Como voces acharam nosso numero?", "expect": ["google", "meu contato e comercial"]},
            ],
        },
        {
            "clinic": "Dental Prime",
            "turns": [
                {"body": "Quanto custa?", "expect": ["valores", "fluxo"]},
            ],
        },
        {
            "clinic": "Oral Vita",
            "turns": [
                {"body": "Ja temos sistema de agenda", "expect": ["nao e trocar", "sistema atual"]},
            ],
        },
        {
            "clinic": "Doctor Smile",
            "turns": [
                {"body": "Integra com Doctoralia?", "expect": ["nao quero prometer integracao", "qual sistema"]},
            ],
        },
        {
            "clinic": "Odonto Jardim",
            "turns": [
                {"body": "Pode mandar proposta?", "expect": ["proposta curta", "principal problema"]},
            ],
        },
        {
            "clinic": "Raiz Dental",
            "turns": [
                {"body": "A gente nao tem site ainda", "expect": ["site com servicos", "base de seo"]},
            ],
        },
        {
            "clinic": "Sorria Mais",
            "turns": [
                {"body": "Quero agendar consulta", "expect": ["meu contato e comercial", "nao sou paciente"]},
            ],
        },
        {
            "clinic": "Alvo Odonto",
            "turns": [
                {"body": "Nao temos interesse, obrigado", "expect": ["parar o contato", "nao insistir"], "allow_no_question": True},
            ],
        },
    ]
    forbidden_fragments = [
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "demonstracao rapida:",
        "clinicflux ai da clinicflux ai",
        "resultado garantido",
        "agenda cheia",
        "x pacientes",
        "faturamento garantido",
    ]

    for index, scenario in enumerate(scenarios, start=1):
        prospect = ProspectAccount(
            clinic_name=scenario["clinic"],
            whatsapp_phone=f"+55 11 98888-{index:04d}",
            city="Sao Paulo",
            state="SP",
            main_pain="demora no WhatsApp",
            legal_basis="interesse_legitimo_b2b",
        )
        db_session.add(prospect)
        db_session.commit()
        db_session.refresh(prospect)

        conversation = sales_demo_service.ensure_admin_whatsapp_test_contact(db_session, prospect=prospect)
        normalized_replies: list[str] = []
        for turn in scenario["turns"]:
            result = sales_demo_service.simulate_admin_internal_whatsapp_inbound(
                db_session,
                prospect=prospect,
                conversation=conversation,
                body=turn["body"],
                actor_id=seeded_db["admin"].id,
            )
            outbound = result["outbound_message"]
            response = outbound.body
            normalized_response = sales_demo_service._normalized_lookup_text(response)
            normalized_replies.append(normalized_response)

            assert outbound.payload["internal_delivery"] is True
            assert outbound.payload["source"] == sales_demo_service.ADM_INTERNAL_WHATSAPP_SIMULATION_SOURCE
            assert len(response) <= 520
            assert all(fragment not in normalized_response for fragment in forbidden_fragments), response
            assert all(expected in normalized_response for expected in turn["expect"]), response
            if not turn.get("allow_no_question"):
                assert "?" in response

        assert len(set(normalized_replies)) == len(normalized_replies)

    assert db_session.scalar(select(func.count()).select_from(OutboxMessage)) == 0


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
    assert "time comercial da ClinicFlux AI" in result["message_text"]
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


def test_send_sales_outreach_step_uses_ai_reviewed_message(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)
    monkeypatch.setattr(sales_demo_service.settings, "llm_provider", "openai")
    monkeypatch.setattr(sales_demo_service.settings, "llm_api_key", "test-key")
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_ai_review_enabled", True)
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_ai_min_confidence", 0.7)

    def _fake_run_llm_task(db, *, tenant_id, conversation_id, task, prompt, model_override=None):
        assert task == "sales_outreach_outbound_review"
        return {
            "output": json.dumps(
                {
                    "approved": True,
                    "final_message": "Perfeito. Esse WhatsApp costuma ficar com a recepcao, gerente ou dono(a)?",
                    "confidence": 0.91,
                    "reason": "Mensagem mais curta e aderente ao contexto de recepcao.",
                }
            ),
            "metadata": {"provider": "openai", "model": "gpt-4.1-mini", "task": task},
        }

    monkeypatch.setattr(sales_demo_service, "run_llm_task", _fake_run_llm_task)

    result = sales_demo_service.send_sales_outreach_step(
        db_session,
        prospect=prospect,
        step="reception_triage",
        actor_id=None,
        base_url="http://localhost:3000",
    )

    outbox = db_session.scalar(select(OutboxMessage).where(OutboxMessage.tenant_id == sender_tenant.id))

    assert result["message_text"] == "Perfeito. Esse WhatsApp costuma ficar com a recepcao, gerente ou dono(a)?"
    assert outbox is not None
    assert (outbox.payload or {}).get("body") == result["message_text"]
    assert (((outbox.payload or {}).get("metadata") or {}).get("ai_review") or {}).get("approved") is True


def test_sales_outreach_initial_message_uses_google_places_no_website_offer(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = ProspectAccount(
        clinic_name="Clinica Sem Site",
        whatsapp_phone="+55 11 97777-3333",
        city="Sao Paulo",
        state="SP",
        lead_source="google_places",
        tags=["google_places", "importado_google_places"],
        proposal_snapshot={
            "source": "google_places",
            "google_places": {
                "place_id": "places/teste-sem-site",
                "types": ["dentist"],
                "rating": 4.8,
                "user_rating_count": 32,
            },
        },
        legal_basis="interesse_legitimo_b2b",
    )
    db_session.add(prospect)
    db_session.commit()
    db_session.refresh(prospect)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)

    result = sales_demo_service.send_sales_outreach_step(
        db_session,
        prospect=prospect,
        step="reception_intro",
        actor_id=None,
        base_url="http://localhost:3000",
    )

    expected_message = (
        "Oi, tudo bem?\n\n"
        "Notei que a clínica ainda não possui um site profissional.\n\n"
        "Eu já montei um modelo de site para a clínica e gostaria de mostrar ao responsável.\n\n"
        "Quem seria a pessoa ideal para eu encaminhar?"
    )

    assert result["message_text"] == expected_message


def test_sales_outreach_initial_message_uses_google_places_with_website_saas_route(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = ProspectAccount(
        clinic_name="Clinica Com Site",
        whatsapp_phone="+55 11 96666-4444",
        website="https://clinicacomsite.example",
        city="Sao Paulo",
        state="SP",
        lead_source="google_places",
        tags=["google_places", "importado_google_places"],
        proposal_snapshot={"source": "google_places", "google_places": {"place_id": "places/teste-com-site"}},
        legal_basis="interesse_legitimo_b2b",
    )
    db_session.add(prospect)
    db_session.commit()
    db_session.refresh(prospect)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)

    result = sales_demo_service.send_sales_outreach_step(
        db_session,
        prospect=prospect,
        step="reception_intro",
        actor_id=None,
        base_url="http://localhost:3000",
    )

    assert "Encontrei a clinica no Google" in result["message_text"]
    assert "site profissional" not in result["message_text"]
    assert "WhatsApp e dos agendamentos" in result["message_text"]


def test_sales_outreach_llm_tasks_use_dedicated_model(monkeypatch, seeded_db, db_session):
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_llm_model", "gpt-5.2")

    captured: dict[str, object] = {}

    def _fake_run_llm_task(db, *, tenant_id, conversation_id, task, prompt, model_override=None):
        captured["task"] = task
        captured["model_override"] = model_override
        return {"output": json.dumps({"ok": True}), "metadata": {"model": model_override}}

    monkeypatch.setattr(sales_demo_service, "run_llm_task", _fake_run_llm_task)

    sales_demo_service._run_sales_outreach_llm_task(
        db_session,
        tenant_id=None,
        conversation_id=None,
        task="sales_outreach_outbound_review",
        prompt="teste",
    )

    assert captured["task"] == "sales_outreach_outbound_review"
    assert captured["model_override"] == "gpt-5.2"


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
    assert any(event.event_type == "prospect.outreach.reply_received" for event in timeline)
    assert (prospect.proposal_snapshot or {}).get("outreach", {}).get("last_reply_classification") == "gestor"


def test_sync_prospect_outreach_reply_starts_handoff_for_shared_contact(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_display_name", "Equipe OdontoFlux")

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
        body="Vou te passar o contato do nosso setor de convenios",
        message_type="text",
        payload={
            "bridge_shared_contact_name": "SAC DENTAL FAMILY",
            "bridge_shared_contact_phone": "+55 11 99999-2222",
        },
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

    shared_prospect = db_session.scalar(
        select(ProspectAccount).where(ProspectAccount.clinic_name == "SAC DENTAL FAMILY")
    )
    shared_timeline = db_session.execute(
        select(sales_demo_service.ProspectTimelineEvent)
        .where(sales_demo_service.ProspectTimelineEvent.prospect_account_id == prospect.id)
        .order_by(sales_demo_service.ProspectTimelineEvent.created_at.desc())
    ).scalars().all()

    assert shared_prospect is not None
    assert shared_prospect.whatsapp_phone == "+55 11 99999-2222"
    assert (shared_prospect.proposal_snapshot or {}).get("outreach", {}).get("automation_active") is True
    assert (shared_prospect.proposal_snapshot or {}).get("outreach", {}).get("last_step") == "reception_intro"
    assert (prospect.proposal_snapshot or {}).get("outreach", {}).get("automation_stop_reason") == "contact_shared"
    assert any(event.event_type == "prospect.outreach.contact_handoff_started" for event in shared_timeline)


def test_sync_prospect_outreach_reply_uses_ai_review_to_override_classification(monkeypatch, seeded_db, db_session):
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
        body="Bem-vindo(a)! Nosso horario de funcionamento e das 08h as 18h. Como podemos te ajudar?",
        message_type="text",
        payload={},
        status=MessageStatus.RECEIVED.value,
    )
    db_session.add(inbound_message)
    db_session.flush()

    monkeypatch.setattr(sales_demo_service.settings, "llm_provider", "openai")
    monkeypatch.setattr(sales_demo_service.settings, "llm_api_key", "test-key")
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_ai_review_enabled", True)
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_ai_min_confidence", 0.7)

    def _fake_run_llm_task(db, *, tenant_id, conversation_id, task, prompt, model_override=None):
        assert task == "sales_outreach_inbound_review"
        return {
            "output": json.dumps(
                {
                    "classification": "recepcao",
                    "confidence": 0.95,
                    "reason": "Saudacao automatica de recepcao com horario de funcionamento.",
                    "suggested_pause": False,
                }
            ),
            "metadata": {"provider": "openai", "model": "gpt-4.1-mini", "task": task},
        }

    monkeypatch.setattr(sales_demo_service, "run_llm_task", _fake_run_llm_task)

    sales_demo_service.sync_prospect_outreach_reply(
        db_session,
        conversation=conversation,
        message=inbound_message,
    )
    db_session.commit()
    db_session.refresh(prospect)

    outreach = (prospect.proposal_snapshot or {}).get("outreach", {})
    assert outreach.get("last_reply_classification") == "recepcao"
    assert (outreach.get("last_reply_ai_review") or {}).get("classification") == "recepcao"


def test_classify_sales_outreach_reply_prioritizes_expected_bucket():
    assert sales_demo_service.classify_sales_outreach_reply("Pode me mandar a demo e o video.") == "gestor"
    assert sales_demo_service.classify_sales_outreach_reply("Sou da recepção, posso ajudar?") == "recepcao"
    assert sales_demo_service.classify_sales_outreach_reply("Agora não, me chama mais tarde.") == "pediu_tempo"


def test_classify_sales_outreach_reply_detects_out_of_hours_autoreply():
    body = "Agradecemos sua mensagem. Não estamos disponíveis no momento, mas responderemos assim que possível!"
    assert sales_demo_service.classify_sales_outreach_reply(body) == "automatica"


def test_sync_prospect_outreach_reply_pauses_on_out_of_hours_autoreply(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)
    prospect.proposal_snapshot = {
        "outreach": {
            "automation_active": True,
            "last_step": "reception_intro",
        }
    }
    db_session.add(prospect)
    db_session.flush()

    conversation = Conversation(
        tenant_id=sender_tenant.id,
        channel="whatsapp",
        status="aberta",
        ai_autoresponder_enabled=False,
        tags=["prospect_outreach", f"prospect_id:{prospect.id}"],
    )
    db_session.add(conversation)
    db_session.flush()

    inbound_message = Message(
        tenant_id=sender_tenant.id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND.value,
        channel="whatsapp",
        sender_type="patient",
        body="Agradecemos sua mensagem. Não estamos disponíveis no momento, mas responderemos assim que possível!",
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

    assert outboxes == []
    assert prospect.proposal_snapshot.get("outreach", {}).get("last_step") == "reception_intro"
    assert prospect.proposal_snapshot.get("outreach", {}).get("automation_active") is False
    assert prospect.proposal_snapshot.get("outreach", {}).get("automation_stop_reason") == "awaiting_human_reply"


def test_looks_like_outreach_opt_out_accepts_natural_interest_refusals():
    assert sales_demo_service._looks_like_outreach_opt_out("Nao temos interesse.")
    assert sales_demo_service._looks_like_outreach_opt_out("No momento nao temos interesse.")
    assert sales_demo_service._looks_like_outreach_opt_out(
        "Guilherme, agradecemos seu contato, mas no momento nao temos interesse."
    )


def test_sync_prospect_outreach_reply_stops_automation_on_interest_refusal(seeded_db, db_session):
    prospect = _create_prospect(db_session)
    prospect.proposal_snapshot = {
        "outreach": {
            "automation_active": True,
            "last_step": "reception_triage",
        }
    }
    db_session.add(prospect)
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
        body="Guilherme, agradecemos seu contato, mas no momento nao temos interesse.",
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

    outreach = (prospect.proposal_snapshot or {}).get("outreach", {})
    assert prospect.do_not_contact is True
    assert prospect.status == "fechado_perdido"
    assert outreach.get("automation_active") is False
    assert outreach.get("automation_stop_reason") == "opt_out"


def test_send_sales_outreach_step_blocks_if_latest_inbound_refused_contact(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)

    conversation = sales_demo_service._ensure_outreach_conversation(
        db_session,
        sender_tenant=sender_tenant,
        prospect=prospect,
    )
    inbound_message = Message(
        tenant_id=sender_tenant.id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND.value,
        channel="whatsapp",
        sender_type="patient",
        body="Agradecemos seu contato, mas no momento nao temos interesse.",
        message_type="text",
        payload={},
        status=MessageStatus.RECEIVED.value,
    )
    db_session.add(inbound_message)
    db_session.flush()

    with pytest.raises(ApiError) as exc:
        sales_demo_service.send_sales_outreach_step(
            db_session,
            prospect=prospect,
            step="access_request",
            actor_id=None,
            base_url="http://localhost:3000",
        )

    db_session.refresh(prospect)
    assert exc.value.code == "SALES_OUTREACH_BLOCKED_OPT_OUT"
    assert prospect.do_not_contact is True
    assert prospect.status == "fechado_perdido"


def test_review_sales_outreach_outbox_send_gate_blocks_if_latest_inbound_refused_contact(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)

    started = sales_demo_service.start_sales_outreach_automation(
        db_session,
        prospect=prospect,
        actor_id=None,
        base_url="http://localhost:3000",
    )
    conversation_id = started["conversation_id"]

    inbound_message = Message(
        tenant_id=sender_tenant.id,
        conversation_id=conversation_id,
        direction=MessageDirection.INBOUND.value,
        channel="whatsapp",
        sender_type="patient",
        body="No momento nao temos interesse.",
        message_type="text",
        payload={},
        status=MessageStatus.RECEIVED.value,
    )
    db_session.add(inbound_message)
    db_session.flush()

    outbox = queue_outbound_message(
        db_session,
        tenant_id=sender_tenant.id,
        conversation_id=conversation_id,
        to=prospect.whatsapp_phone,
        body="Posso deixar um resumo rapido para depois?",
        metadata={"source": "sales_outreach", "step": "access_request", "transport": "whatsapp_web_bridge"},
        immediate_dispatch=False,
        commit=True,
    )

    gate = sales_demo_service.review_sales_outreach_outbox_send_gate(db_session, outbox=outbox)
    assert gate["decision"] == "block"
    assert "recusou contato" in gate["reason"].lower()


def test_review_sales_outreach_outbox_send_gate_allows_first_message_when_ai_unavailable(
    monkeypatch,
    seeded_db,
    db_session,
):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)
    conversation = sales_demo_service._ensure_outreach_conversation(
        db_session,
        sender_tenant=sender_tenant,
        prospect=prospect,
    )
    outbox = queue_outbound_message(
        db_session,
        tenant_id=sender_tenant.id,
        conversation_id=conversation.id,
        to=prospect.whatsapp_phone,
        body="Oi, tudo bem? Encontrei a clinica no Google. Aqui e o time comercial da ClinicFlux AI.",
        metadata={"source": "sales_outreach", "step": "reception_intro", "transport": "whatsapp_web_bridge"},
        immediate_dispatch=False,
        commit=True,
    )

    monkeypatch.setattr(sales_demo_service, "_sales_outreach_ai_is_enabled", lambda: True)

    def _raise_unavailable(*args, **kwargs):
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr(sales_demo_service, "_run_sales_outreach_llm_task", _raise_unavailable)

    gate = sales_demo_service.review_sales_outreach_outbox_send_gate(db_session, outbox=outbox)

    assert gate["decision"] == "send"
    assert "primeira mensagem comercial" in gate["reason"].lower()
    assert gate["facts"]["total_actual_messages"] == 0


def test_live_gate_repairs_wrong_reception_persona(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)

    started = sales_demo_service.start_sales_outreach_automation(
        db_session,
        prospect=prospect,
        actor_id=None,
        base_url="http://localhost:3000",
    )
    conversation = db_session.get(Conversation, started["conversation_id"])
    inbound_body = "Boa tarde! Me chamo Juliana. Poderia me informar seu nome e de onde e seu contato?"
    db_session.add(
        Message(
            tenant_id=sender_tenant.id,
            conversation_id=conversation.id,
            direction=MessageDirection.INBOUND.value,
            channel="whatsapp",
            sender_type="patient",
            body=inbound_body,
            message_type="text",
            payload={},
            status=MessageStatus.RECEIVED.value,
        )
    )
    db_session.flush()

    gate = sales_demo_service.review_sales_outreach_live_whatsapp_send_gate(
        db_session,
        conversation=conversation,
        candidate_message="Ola Juliana, aqui e da recepcao. Como posso ajudar no agendamento hoje?",
        live_messages=[{"direction": "in", "body": inbound_body, "visible_time": "21:01"}],
        candidate_step="reception_intro",
    )

    final_message = gate.get("final_message") or ""
    assert gate["decision"] == "send"
    assert "ClinicFlux AI" in final_message
    assert "recepcao" not in final_message.lower()
    assert "agendamento hoje" not in final_message.lower()


def test_live_gate_sends_fallback_when_ai_waits_after_clinic_reply(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)
    monkeypatch.setattr(sales_demo_service.settings, "llm_provider", "openai")
    monkeypatch.setattr(sales_demo_service.settings, "llm_api_key", "test-key")

    started = sales_demo_service.start_sales_outreach_automation(
        db_session,
        prospect=prospect,
        actor_id=None,
        base_url="http://localhost:3000",
    )
    conversation = db_session.get(Conversation, started["conversation_id"])
    inbound_body = "Ola! Como podemos ajudar?"
    db_session.add(
        Message(
            tenant_id=sender_tenant.id,
            conversation_id=conversation.id,
            direction=MessageDirection.INBOUND.value,
            channel="whatsapp",
            sender_type="patient",
            body=inbound_body,
            message_type="text",
            payload={},
            status=MessageStatus.RECEIVED.value,
        )
    )
    db_session.flush()

    monkeypatch.setattr(
        sales_demo_service,
        "run_llm_task",
        lambda *args, **kwargs: {
            "output": json.dumps(
                {
                    "decision": "wait",
                    "confidence": 0.95,
                    "reason": "A mensagem candidata ignora a pergunta pendente.",
                    "wait_minutes": 15,
                    "final_message": "",
                }
            )
        },
    )

    gate = sales_demo_service.review_sales_outreach_live_whatsapp_send_gate(
        db_session,
        conversation=conversation,
        candidate_message="Entendi, obrigado pelo retorno. Quem cuida dos agendamentos por ai?",
        live_messages=[
            {"direction": "out", "body": "Oi! Tudo bem? Quem cuida dos agendamentos pelo WhatsApp da clinica?", "visible_time": "20:30"},
            {"direction": "in", "body": inbound_body, "visible_time": "20:31"},
        ],
        candidate_step="reception_triage",
    )

    assert gate["decision"] == "send"
    assert "ClinicFlux AI" in (gate.get("final_message") or "")
    assert "nao e agendamento de paciente" in (gate.get("final_message") or "").lower()


def test_live_gate_blocks_out_of_hours_autoreply(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)

    started = sales_demo_service.start_sales_outreach_automation(
        db_session,
        prospect=prospect,
        actor_id=None,
        base_url="http://localhost:3000",
    )
    conversation = db_session.get(Conversation, started["conversation_id"])
    inbound_body = "No momento estamos ausentes, mas assim que possivel responderemos."
    db_session.add(
        Message(
            tenant_id=sender_tenant.id,
            conversation_id=conversation.id,
            direction=MessageDirection.INBOUND.value,
            channel="whatsapp",
            sender_type="patient",
            body=inbound_body,
            message_type="text",
            payload={},
            status=MessageStatus.RECEIVED.value,
        )
    )
    db_session.flush()

    gate = sales_demo_service.review_sales_outreach_live_whatsapp_send_gate(
        db_session,
        conversation=conversation,
        candidate_message="Entendi, quem cuida dos agendamentos por ai?",
        live_messages=[
            {"direction": "out", "body": "Oi! Tudo bem? Quem cuida dos agendamentos pelo WhatsApp da clinica?", "visible_time": "20:30"},
            {"direction": "in", "body": inbound_body, "visible_time": "20:31"},
        ],
        candidate_step="reception_triage",
    )

    assert gate["decision"] == "block"
    assert "automatica" in gate["reason"].lower()
    assert gate.get("final_message") is None


def test_outbox_gate_blocks_auto_reply_hold(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)

    started = sales_demo_service.start_sales_outreach_automation(
        db_session,
        prospect=prospect,
        actor_id=None,
        base_url="http://localhost:3000",
    )
    conversation_id = started["conversation_id"]
    db_session.add(
        Message(
            tenant_id=sender_tenant.id,
            conversation_id=conversation_id,
            direction=MessageDirection.INBOUND.value,
            channel="whatsapp",
            sender_type="patient",
            body="Agradecemos sua mensagem. Nao estamos disponiveis no momento.",
            message_type="text",
            payload={},
            status=MessageStatus.RECEIVED.value,
        )
    )
    db_session.flush()

    outbox = queue_outbound_message(
        db_session,
        tenant_id=sender_tenant.id,
        conversation_id=conversation_id,
        to=prospect.whatsapp_phone,
        body="Tudo bem, vou aguardar a proxima mensagem da clinica.",
        metadata={"source": "sales_outreach", "step": "auto_reply_hold", "transport": "whatsapp_web_bridge"},
        immediate_dispatch=False,
        commit=True,
    )

    gate = sales_demo_service.review_sales_outreach_outbox_send_gate(db_session, outbox=outbox)

    assert gate["decision"] == "block"
    assert "automatica" in gate["reason"].lower()


def test_classify_sales_outreach_reply_treats_welcome_autoreply_as_reception():
    body = (
        "Bem-vindo(a) a Clinica Harmony!\n\n"
        "Estamos felizes em recebe-lo(a)! Nosso horario de funcionamento e das 08h00 as 18h00, "
        "de segunda a sexta feira.\n"
        "Como podemos te ajudar?"
    )
    assert sales_demo_service.classify_sales_outreach_reply(body) == "recepcao"


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


def test_send_no_site_outreach_stage_queues_random_message_for_whatsapp_web_bridge(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_transport", "whatsapp_web_bridge")
    monkeypatch.setattr(sales_demo_service.secrets, "randbelow", lambda size: 1)
    sales_demo_service.save_no_site_outreach_flow_config(
        db_session,
        {
            "first_messages": ["primeira A", "primeira B", "primeira C"],
            "second_messages": ["segunda A", "segunda B", "segunda C"],
            "third_messages": ["terceira A", "terceira B", "terceira C"],
        },
    )

    result = sales_demo_service.send_no_site_outreach_stage(
        db_session,
        prospect=prospect,
        stage="first",
        actor_id=seeded_db["admin"].id,
    )

    outbox = db_session.scalar(select(OutboxMessage).where(OutboxMessage.id.is_not(None)).order_by(OutboxMessage.created_at.desc()))
    metadata = (outbox.payload or {}).get("metadata", {})
    snapshot = (result["prospect"]["proposal_snapshot"] or {}).get("no_site_outreach", {})

    assert result["step"] == "no_site_first"
    assert result["message_text"] == "primeira B"
    assert result["transport"] == "whatsapp_web_bridge"
    assert metadata["source"] == "sales_outreach"
    assert metadata["flow"] == "no_site_outreach"
    assert metadata["no_site_outreach_stage"] == "first"
    assert metadata["transport"] == "whatsapp_web_bridge"
    assert snapshot["sent_stages"]["first"]["message_text"] == "primeira B"


def test_send_no_site_outreach_bulk_queues_first_stage_for_all_without_site(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    first = _create_prospect(db_session)
    second = ProspectAccount(
        clinic_name="Clinica Sem Site Dois",
        whatsapp_phone="+55 11 97777-2222",
        city="Sao Paulo",
        state="SP",
        legal_basis="interesse_legitimo_b2b",
    )
    with_site = ProspectAccount(
        clinic_name="Clinica Com Site",
        whatsapp_phone="+55 11 96666-3333",
        website="https://clinica-com-site.test",
        city="Sao Paulo",
        state="SP",
        legal_basis="interesse_legitimo_b2b",
    )
    db_session.add_all([second, with_site])
    db_session.commit()

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_transport", "whatsapp_web_bridge")
    monkeypatch.setattr(sales_demo_service.secrets, "randbelow", lambda size: 0)

    eligible = sales_demo_service.list_no_site_outreach_eligible(db_session, stage="first", limit=10)
    result = sales_demo_service.send_no_site_outreach_bulk(
        db_session,
        stage="first",
        actor_id=seeded_db["admin"].id,
        limit=10,
    )

    db_session.refresh(first)
    db_session.refresh(second)
    db_session.refresh(with_site)

    assert eligible["eligible_count"] == 2
    assert result["queued_count"] == 2
    assert result["errors"] == []
    assert (first.proposal_snapshot or {}).get("no_site_outreach", {}).get("sent_stages", {}).get("first")
    assert (second.proposal_snapshot or {}).get("no_site_outreach", {}).get("sent_stages", {}).get("first")
    assert not (with_site.proposal_snapshot or {}).get("no_site_outreach")


def test_send_no_site_outreach_stage_blocks_clinic_with_site(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)
    prospect.website = "https://clinica.test"
    db_session.add(prospect)
    db_session.commit()

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)

    with pytest.raises(ApiError) as exc_info:
        sales_demo_service.send_no_site_outreach_stage(
            db_session,
            prospect=prospect,
            stage="first",
            actor_id=seeded_db["admin"].id,
        )

    assert exc_info.value.code == "NO_SITE_OUTREACH_REQUIRES_WITHOUT_SITE"


def test_no_site_outreach_bulk_third_stage_lists_only_after_human_reply(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_transport", "whatsapp_web_bridge")
    monkeypatch.setattr(sales_demo_service.secrets, "randbelow", lambda size: 0)

    first = sales_demo_service.send_no_site_outreach_stage(
        db_session,
        prospect=prospect,
        stage="first",
        actor_id=seeded_db["admin"].id,
    )
    sales_demo_service.send_no_site_outreach_stage(
        db_session,
        prospect=prospect,
        stage="second",
        actor_id=seeded_db["admin"].id,
    )

    before_reply = sales_demo_service.list_no_site_outreach_eligible(db_session, stage="third", limit=10)
    assert before_reply["eligible_count"] == 0
    assert before_reply["blocked_summary"]["human_reply_required"] == 1

    db_session.add(
        Message(
            tenant_id=sender_tenant.id,
            conversation_id=first["conversation_id"],
            direction=MessageDirection.INBOUND.value,
            channel="whatsapp",
            sender_type="patient",
            body="Pode mandar o preview.",
            message_type="text",
            status=MessageStatus.RECEIVED.value,
        )
    )
    db_session.commit()

    after_reply = sales_demo_service.list_no_site_outreach_eligible(db_session, stage="third", limit=10)
    result = sales_demo_service.send_no_site_outreach_bulk(
        db_session,
        stage="third",
        actor_id=seeded_db["admin"].id,
        limit=10,
    )

    assert after_reply["eligible_count"] == 1
    assert result["queued_count"] == 1
    assert result["queued"][0]["step"] == "no_site_third"


def test_no_site_outreach_third_stage_requires_human_reply(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_transport", "whatsapp_web_bridge")
    monkeypatch.setattr(sales_demo_service.secrets, "randbelow", lambda size: 0)

    first = sales_demo_service.send_no_site_outreach_stage(
        db_session,
        prospect=prospect,
        stage="first",
        actor_id=seeded_db["admin"].id,
    )
    sales_demo_service.send_no_site_outreach_stage(
        db_session,
        prospect=prospect,
        stage="second",
        actor_id=seeded_db["admin"].id,
    )

    with pytest.raises(ApiError) as exc_info:
        sales_demo_service.send_no_site_outreach_stage(
            db_session,
            prospect=prospect,
            stage="third",
            actor_id=seeded_db["admin"].id,
        )
    assert exc_info.value.code == "NO_SITE_OUTREACH_THIRD_REQUIRES_HUMAN_REPLY"

    inbound = Message(
        tenant_id=sender_tenant.id,
        conversation_id=first["conversation_id"],
        direction=MessageDirection.INBOUND.value,
        channel="whatsapp",
        sender_type="patient",
        body="Pode mandar para eu ver.",
        message_type="text",
        status=MessageStatus.RECEIVED.value,
    )
    db_session.add(inbound)
    db_session.commit()

    third = sales_demo_service.send_no_site_outreach_stage(
        db_session,
        prospect=prospect,
        stage="third",
        actor_id=seeded_db["admin"].id,
    )

    assert third["step"] == "no_site_third"


def test_outreach_batch_processes_demo_and_first_step(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)
    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_transport", "whatsapp_web_bridge")
    monkeypatch.setattr(sales_demo_service.settings, "whatsapp_web_bridge_token", "test-bridge-token")
    monkeypatch.setattr(sales_outreach_automation_service, "_enqueue_batch_processing", lambda batch_id: None)

    def _fake_generate_demo(db, current_prospect, *, actor_id, base_url):
        current_prospect.demo_tenant_id = seeded_db["tenant_a"].id
        current_prospect.demo_status = "criada"
        db.add(current_prospect)
        db.flush()
        return {"prospect": current_prospect}

    def _fake_start_sales_outreach_automation(db, *, prospect, actor_id, base_url):
        conversation = sales_demo_service._ensure_outreach_conversation(
            db,
            sender_tenant=sender_tenant,
            prospect=prospect,
        )
        outbound_message = Message(
            tenant_id=sender_tenant.id,
            conversation_id=conversation.id,
            direction=MessageDirection.OUTBOUND.value,
            channel="whatsapp",
            sender_type="user",
            body="Oi! Tudo bem?",
            message_type="text",
            payload={"source": "sales_outreach", "step": "reception_intro"},
            status=MessageStatus.QUEUED.value,
        )
        db.add(outbound_message)
        db.flush()
        queue_outbound_message(
            db,
            tenant_id=sender_tenant.id,
            conversation_id=conversation.id,
            to=prospect.whatsapp_phone,
            body="Oi! Tudo bem?",
            metadata={"source": "sales_outreach", "step": "reception_intro", "transport": "whatsapp_web_bridge"},
            immediate_dispatch=False,
            commit=False,
        )
        sales_demo_service._update_outreach_snapshot(
            prospect,
            patch={
                "automation_active": True,
                "automation_mode": "transparent_b2b",
                "last_step": "reception_intro",
            },
        )
        prospect.status = "contato_iniciado"
        db.add(prospect)
        db.flush()
        return {
            "step": "reception_intro",
            "conversation_id": conversation.id,
            "outbound_message_id": outbound_message.id,
            "message_text": "Oi! Tudo bem?",
            "transport": "whatsapp_web_bridge",
            "demo_login_url": None,
        }

    monkeypatch.setattr(sales_demo_service, "generate_demo", _fake_generate_demo)
    monkeypatch.setattr(sales_demo_service, "start_sales_outreach_automation", _fake_start_sales_outreach_automation)

    created = sales_outreach_automation_service.create_batch(
        db_session,
        quantity=1,
        filters={},
        actor_id=seeded_db["admin"].id,
    )
    processed = sales_outreach_automation_service.process_batch(db_session, batch_id=created["id"])

    item = db_session.scalar(select(SalesOutreachAutomationBatchItem).where(SalesOutreachAutomationBatchItem.prospect_account_id == prospect.id))

    assert created["selected_count"] == 1
    assert processed["status"] in {"running", "completed"}
    assert item is not None
    assert item.demo_generated_automatically is True
    assert item.status == "waiting_reply"
    assert item.current_step == "reception_intro"


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


def test_sync_prospect_outreach_reply_sends_reception_triage_for_reception_reply(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)

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
        body="Sou da recepção. Posso ajudar.",
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
    outreach = (prospect.proposal_snapshot or {}).get("outreach", {})

    assert len(outboxes) == 2
    assert ((outboxes[-1].payload or {}).get("metadata") or {}).get("step") == "reception_triage"
    assert outreach.get("last_reply_classification") == "recepcao"
    assert outreach.get("automation_active") is True


def test_sync_prospect_outreach_reply_holds_when_clinic_promises_phone_handoff(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)

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
        body="Oi, boa noite. Vou te passar o telefone da pessoa responsável.",
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
    assert len(outboxes) == 2
    assert ((outboxes[-1].payload or {}).get("metadata") or {}).get("step") == "contact_handoff_ack"


def test_sync_prospect_outreach_reply_restarts_with_forwarded_phone_in_text(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)

    started = sales_demo_service.start_sales_outreach_automation(
        db_session,
        prospect=prospect,
        actor_id=None,
        base_url="http://localhost:3000",
    )
    conversation = db_session.get(Conversation, started["conversation_id"])
    original_outbox = db_session.scalar(
        select(OutboxMessage)
        .where(OutboxMessage.tenant_id == sender_tenant.id)
        .order_by(OutboxMessage.created_at.asc())
    )
    assert original_outbox is not None
    original_outbox.status = OutboxStatus.FAILED.value
    original_outbox.next_retry_at = None
    original_outbox.last_error = "Falha simulada para retry no numero antigo"
    db_session.add(original_outbox)
    db_session.flush()

    inbound_message = Message(
        tenant_id=sender_tenant.id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND.value,
        channel="whatsapp",
        sender_type="patient",
        body="Oi boa noite, vou te passar o telefone da pessoa responsavel. (11)97649-7909 Lucas",
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
    outreach = (prospect.proposal_snapshot or {}).get("outreach", {})

    assert len(outboxes) == 2
    assert outboxes[0].status == OutboxStatus.DEAD_LETTER.value
    assert (outboxes[0].payload or {}).get("to") == "5511988881111"
    assert ((outboxes[-1].payload or {}).get("metadata") or {}).get("step") == "reception_intro"
    assert (outboxes[-1].payload or {}).get("to") == "5511976497909"
    assert prospect.whatsapp_phone == "5511976497909"
    assert prospect.owner_name == "Lucas"
    assert outreach.get("automation_active") is True
    assert any(
        ((item.payload or {}).get("metadata") or {}).get("step") == "contact_handoff_ack"
        for item in outboxes
    ) is False


def test_sync_prospect_outreach_reply_restarts_when_phone_arrives_in_followup_message(monkeypatch, seeded_db, db_session):
    sender_tenant = _create_sender_tenant(db_session)
    prospect = _create_prospect(db_session)

    monkeypatch.setattr(sales_demo_service.settings, "sales_outreach_sender_tenant_slug", sender_tenant.slug)

    started = sales_demo_service.start_sales_outreach_automation(
        db_session,
        prospect=prospect,
        actor_id=None,
        base_url="http://localhost:3000",
    )
    conversation = db_session.get(Conversation, started["conversation_id"])
    original_outbox = db_session.scalar(
        select(OutboxMessage)
        .where(OutboxMessage.tenant_id == sender_tenant.id)
        .order_by(OutboxMessage.created_at.asc())
    )
    assert original_outbox is not None
    original_outbox.status = OutboxStatus.FAILED.value
    original_outbox.next_retry_at = None
    db_session.add(original_outbox)
    db_session.flush()

    handoff_message = Message(
        tenant_id=sender_tenant.id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND.value,
        channel="whatsapp",
        sender_type="patient",
        body="Oi boa noite, vou te passar o telefone da pessoa responsavel",
        message_type="text",
        payload={},
        status=MessageStatus.RECEIVED.value,
    )
    db_session.add(handoff_message)
    db_session.flush()
    sales_demo_service.sync_prospect_outreach_reply(
        db_session,
        conversation=conversation,
        message=handoff_message,
    )
    db_session.flush()

    forwarded_number_message = Message(
        tenant_id=sender_tenant.id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND.value,
        channel="whatsapp",
        sender_type="patient",
        body="(11)97649-7909 Lucas",
        message_type="text",
        payload={},
        status=MessageStatus.RECEIVED.value,
    )
    db_session.add(forwarded_number_message)
    db_session.flush()

    sales_demo_service.sync_prospect_outreach_reply(
        db_session,
        conversation=conversation,
        message=forwarded_number_message,
    )
    db_session.commit()
    db_session.refresh(prospect)

    outboxes = db_session.execute(
        select(OutboxMessage).where(OutboxMessage.tenant_id == sender_tenant.id).order_by(OutboxMessage.created_at.asc())
    ).scalars().all()

    assert len(outboxes) == 3
    assert ((outboxes[1].payload or {}).get("metadata") or {}).get("step") == "contact_handoff_ack"
    assert outboxes[0].status == OutboxStatus.DEAD_LETTER.value
    assert (outboxes[0].payload or {}).get("to") == "5511988881111"
    assert ((outboxes[-1].payload or {}).get("metadata") or {}).get("step") == "reception_intro"
    assert (outboxes[-1].payload or {}).get("to") == "5511976497909"
    assert prospect.whatsapp_phone == "5511976497909"
    assert prospect.owner_name == "Lucas"


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


def test_create_prospect_defaults_demo_background_settings(seeded_db, db_session):
    created = sales_demo_service.create_prospect(
        db_session,
        ProspectCreate(
            clinic_name="Clinica Fundo Padrao",
            whatsapp_phone="+55 11 97777-2222",
            city="Sao Paulo",
            state="SP",
            main_address="Rua Demo, 123",
        ),
        actor_id=None,
    )

    demo_branding = (created.proposal_snapshot or {}).get("demo_branding", {})
    assert demo_branding["background_image_url"] == sales_demo_service.DEMO_BACKGROUND_DEFAULT_IMAGE_URL
    assert demo_branding["background_image_opacity"] == sales_demo_service.DEMO_BACKGROUND_DEFAULT_OPACITY


def test_create_prospect_uses_friendly_seed_key_and_duplicate_phone_suffix(seeded_db, db_session):
    first = sales_demo_service.create_prospect(
        db_session,
        ProspectCreate(
            clinic_name="Clinica Sorriso Claro",
            whatsapp_phone="+55 11 97777-1111",
            city="Sao Paulo",
            state="SP",
        ),
        actor_id=None,
    )
    second = sales_demo_service.create_prospect(
        db_session,
        ProspectCreate(
            clinic_name="Clinica Sorriso Claro",
            whatsapp_phone="+55 11 97777-2222",
            city="Sao Paulo",
            state="SP",
        ),
        actor_id=None,
    )

    assert first.tenant_seed_key == "clinica-sorriso-claro"
    assert second.tenant_seed_key == "clinica-sorriso-claro-2222"
    assert first.created_at is not None
    assert second.created_at is not None


def test_issue_demo_access_uses_readable_clinic_token_with_duplicate_phone_suffix(seeded_db, db_session):
    first = _create_prospect(db_session)
    second = ProspectAccount(
        clinic_name=first.clinic_name,
        whatsapp_phone="+55 11 98888-2222",
        city="Sao Paulo",
        state="SP",
        legal_basis="interesse_legitimo_b2b",
        demo_tenant_id=seeded_db["tenant_a"].id,
        demo_user_id=seeded_db["owner_a"].id,
    )
    db_session.add(second)
    db_session.commit()
    db_session.refresh(second)

    raw_token = sales_demo_service.issue_demo_access(db_session, second, actor_id=None)

    assert raw_token == "clinica-conversao-segura-2222"
    assert second.demo_access_token_hash == sales_demo_service.sha256_text(raw_token)


def test_generate_demo_applies_demo_intake_config_and_syncs_updates(monkeypatch, seeded_db, db_session):
    prospect = _create_prospect(db_session)
    prospect.proposal_snapshot = {
        "demo_intake": {
            "mode": "link_flow",
            "link_flow": {
                "enabled": True,
                "cta_mode": "webchat",
            },
        },
        "demo_branding": {
            "background_image_url": "data:image/png;base64,abc123",
            "background_image_opacity": 0.42,
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

    intake_setting = db_session.scalar(
        select(Setting).where(
            Setting.tenant_id == generated["prospect"].demo_tenant_id,
            Setting.key == "intake.config",
        )
    )
    assert intake_setting is not None
    assert intake_setting.value["mode"] == "link_flow"
    assert intake_setting.value["link_flow"]["cta_mode"] == "webchat"

    branding_setting = db_session.scalar(
        select(Setting).where(
            Setting.tenant_id == generated["prospect"].demo_tenant_id,
            Setting.key == "branding.theme",
        )
    )
    assert branding_setting is not None
    assert branding_setting.value["demo_background_image_url"] == "data:image/png;base64,abc123"
    assert branding_setting.value["demo_background_opacity"] == 0.42

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
                "demo_branding": {
                    "background_image_url": "/images/dental-floss-smile-background.png",
                    "background_image_opacity": 0.67,
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

    refreshed_branding_setting = db_session.scalar(
        select(Setting).where(
            Setting.tenant_id == updated.demo_tenant_id,
            Setting.key == "branding.theme",
        )
    )
    assert refreshed_branding_setting is not None
    assert refreshed_branding_setting.value["demo_background_image_url"] == "/images/dental-floss-smile-background.png"
    assert refreshed_branding_setting.value["demo_background_opacity"] == 0.67


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

    demo_tenant = db_session.get(Tenant, generated["prospect"].demo_tenant_id)
    assert demo_tenant is not None
    assert generated["demo_booking_path"] == f"/agendar/{demo_tenant.slug}"
    assert generated["demo_booking_url"] == f"http://localhost:3000{generated['demo_booking_path']}"

    redeemed = sales_demo_service.redeem_demo_token(
        db_session,
        token=generated["access_token"],
        session_id="demo-session-webchat",
    )

    assert redeemed["demo_target_path"] == "/conversas"
    assert redeemed["demo_entry_channel"] == "webchat"
    assert redeemed["demo_public_entry_path"] == generated["demo_booking_path"]


def test_redeem_demo_token_resyncs_demo_background_theme(monkeypatch, seeded_db, db_session):
    prospect = _create_prospect(db_session)
    prospect.proposal_snapshot = {
        "demo_branding": {
            "background_image_url": "data:image/png;base64,updated-background",
            "background_image_opacity": 0.58,
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

    branding_setting = db_session.scalar(
        select(Setting).where(
            Setting.tenant_id == generated["prospect"].demo_tenant_id,
            Setting.key == "branding.theme",
        )
    )
    assert branding_setting is not None
    branding_setting.value = {
        **branding_setting.value,
        "demo_background_image_url": "/images/dental-floss-smile-background.png",
        "demo_background_opacity": 0.18,
    }
    db_session.add(branding_setting)
    db_session.commit()

    sales_demo_service.redeem_demo_token(
        db_session,
        token=generated["access_token"],
        session_id="demo-session-background-sync",
    )

    refreshed_branding_setting = db_session.scalar(
        select(Setting).where(
            Setting.tenant_id == generated["prospect"].demo_tenant_id,
            Setting.key == "branding.theme",
        )
    )
    assert refreshed_branding_setting is not None
    assert refreshed_branding_setting.value["demo_background_image_url"] == "data:image/png;base64,updated-background"
    assert refreshed_branding_setting.value["demo_background_opacity"] == 0.58


def test_redeem_demo_token_defaults_to_webchat_when_demo_has_no_real_whatsapp(monkeypatch, seeded_db, db_session):
    prospect = _create_prospect(db_session)
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

    assert generated["demo_booking_path"]
    assert generated["demo_booking_url"] == f"http://localhost:3000{generated['demo_booking_path']}"

    redeemed = sales_demo_service.redeem_demo_token(
        db_session,
        token=generated["access_token"],
        session_id="demo-session-default-webchat",
    )

    assert redeemed["demo_whatsapp_link"] is None
    assert redeemed["demo_entry_channel"] == "webchat"
    assert redeemed["demo_public_entry_path"] == generated["demo_booking_path"]


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


def test_generate_demo_keeps_showcase_appointments_within_clinic_working_hours(monkeypatch, seeded_db, db_session):
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
    tenant = db_session.get(Tenant, demo_tenant_id)
    timezone = ZoneInfo(str(tenant.timezone or "America/Sao_Paulo"))
    units = {
        unit.id: unit
        for unit in db_session.execute(select(Unit).where(Unit.tenant_id == demo_tenant_id)).scalars().all()
    }
    professionals = {
        professional.id: professional
        for professional in db_session.execute(select(Professional).where(Professional.tenant_id == demo_tenant_id)).scalars().all()
    }
    appointments = db_session.execute(
        select(Appointment)
        .where(
            Appointment.tenant_id == demo_tenant_id,
            Appointment.origin == "demo_personalizada",
        )
        .order_by(Appointment.starts_at.asc())
    ).scalars().all()

    assert appointments

    for appointment in appointments:
        appointment_local = appointment.starts_at.astimezone(timezone)
        unit = units[appointment.unit_id]
        professional = professionals[appointment.professional_id]
        unit_window = sales_demo_service._resolve_unit_working_window_minutes(unit)
        professional_window = sales_demo_service._resolve_professional_working_window_minutes(professional)
        effective_start = max(unit_window[0], professional_window[0])
        effective_end = min(unit_window[1], professional_window[1])
        appointment_minutes = appointment_local.hour * 60 + appointment_local.minute

        assert effective_start <= appointment_minutes
        assert appointment_minutes + 60 <= effective_end


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

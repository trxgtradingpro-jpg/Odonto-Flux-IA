from sqlalchemy import select

from app.models import ProspectAccount, ProspectTimelineEvent
from app.services import sales_message_service


def _create_demo_prospect(db_session, seeded_db, *, do_not_contact=False):
    prospect = ProspectAccount(
        clinic_name="Lorenson Odontologia",
        owner_name="Dr. Lorenson",
        whatsapp_phone="447307810006",
        city="Sao Paulo",
        state="SP",
        main_pain="Perde paciente no WhatsApp",
        status="demo_acessada",
        temperature="quente",
        legal_basis="interesse_legitimo_b2b",
        demo_tenant_id=seeded_db["tenant_a"].id,
        demo_user_id=seeded_db["owner_a"].id,
        demo_status="acessada",
        do_not_contact=do_not_contact,
    )
    db_session.add(prospect)
    db_session.commit()
    db_session.refresh(prospect)
    return prospect


def test_build_sales_message_preview_adds_demo_link_at_the_end(seeded_db, db_session):
    prospect = _create_demo_prospect(db_session, seeded_db)

    preview = sales_message_service.build_sales_message_preview(
        db_session,
        prospect=prospect,
        template_key="primeiro_contato",
        actor_id=seeded_db["admin"].id,
        base_url="http://localhost:3000",
    )

    assert preview["can_copy"] is True
    assert preview["demo_login_url"]
    assert preview["message_key"] == "principal"
    assert preview["message_text"].endswith(preview["demo_login_url"])
    assert "Perde paciente no WhatsApp" in preview["message_text"]

    event = db_session.scalar(
        select(ProspectTimelineEvent)
        .where(ProspectTimelineEvent.prospect_account_id == prospect.id)
        .order_by(ProspectTimelineEvent.created_at.desc())
        .limit(1)
    )
    assert event is not None
    assert event.event_type == "sales_message.message_previewed"


def test_build_sales_message_preview_blocks_do_not_contact(seeded_db, db_session):
    prospect = _create_demo_prospect(db_session, seeded_db, do_not_contact=True)

    preview = sales_message_service.build_sales_message_preview(
        db_session,
        prospect=prospect,
        template_key="primeiro_contato",
        actor_id=seeded_db["admin"].id,
        base_url="http://localhost:3000",
    )

    assert preview["can_copy"] is False
    assert any("nao contactar" in warning for warning in preview["warnings"])


def test_record_sales_message_contact_event_updates_contact_status(seeded_db, db_session):
    prospect = ProspectAccount(
        clinic_name="Clinica Primeira Mensagem",
        whatsapp_phone="5511999990000",
        status="pesquisado",
        temperature="morno",
        legal_basis="interesse_legitimo_b2b",
    )
    db_session.add(prospect)
    db_session.commit()
    db_session.refresh(prospect)

    event = sales_message_service.record_sales_message_event(
        db_session,
        prospect=prospect,
        event_name="contact_registered",
        actor_id=seeded_db["admin"].id,
        template_key="primeiro_contato",
        message_key="principal",
        message_snapshot="Mensagem enviada",
        demo_login_url="http://localhost:3000/login?demo_token=abc",
        channel="whatsapp_manual",
        note="Contato registrado pelo teste.",
    )

    assert event.event_type == "sales_message.contact_registered"
    assert prospect.status == "contato_iniciado"
    assert prospect.first_contact_channel == "whatsapp_manual"
    assert prospect.first_contact_at is not None


def test_sales_message_templates_can_be_created_updated_and_used(seeded_db, db_session):
    prospect = _create_demo_prospect(db_session, seeded_db)

    created = sales_message_service.create_sales_message_template(
        db_session,
        {
            "key": "teste_personalizado",
            "label": "Teste personalizado",
            "description": "Template editavel do ADM.",
            "recommended_for": ["demo_acessada"],
            "messages": [
                {
                    "key": "curta",
                    "label": "Curta",
                    "body": "Oi, {contact_name}. Demo da {clinic_name}: {demo_link}",
                    "is_default": True,
                },
                {
                    "key": "longa",
                    "label": "Longa",
                    "body": "Mensagem longa para {clinic_name}. Dor: {pain_sentence}. Link: {demo_link}",
                    "is_default": False,
                },
            ],
        },
    )

    assert created["key"] == "teste_personalizado"
    assert len(created["messages"]) == 2

    updated = sales_message_service.update_sales_message_template(
        db_session,
        "teste_personalizado",
        {
            **created,
            "label": "Teste editado",
            "messages": [
                {**created["messages"][0], "body": "Texto editado para {clinic_name}: {demo_link}"},
                {**created["messages"][1], "is_default": True},
            ],
        },
    )
    assert updated["label"] == "Teste editado"
    assert updated["messages"][1]["is_default"] is True

    preview = sales_message_service.build_sales_message_preview(
        db_session,
        prospect=prospect,
        template_key="teste_personalizado",
        message_key="longa",
        actor_id=seeded_db["admin"].id,
        base_url="http://localhost:3000",
    )

    assert preview["template_key"] == "teste_personalizado"
    assert preview["message_key"] == "longa"
    assert "Mensagem longa" in preview["message_text"]

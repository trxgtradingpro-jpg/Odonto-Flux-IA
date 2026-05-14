from datetime import UTC, datetime

from app.api.v1.endpoints import messages as messages_endpoint
from app.api.v1.endpoints.messages import AISuggestionInput, ai_suggestion
from app.models import Appointment, Conversation, Message, Patient, Professional, Unit


def test_ai_suggestion_uses_official_visit_guidance_for_location_requests(seeded_db, db_session, monkeypatch):
    tenant_id = seeded_db["tenant_a"].id
    unit = Unit(
        tenant_id=tenant_id,
        code="SP-PAULISTA",
        name="Unidade Paulista",
        address={
            "street": "Rua Ramondetti Giacomo",
            "number": "24",
            "neighborhood": "Vila Dalva",
            "city": "Sao Paulo",
            "state": "SP",
            "zip_code": "05387-110",
            "formatted": "Rua Ramondetti Giacomo, 24, Vila Dalva, Sao Paulo - SP, 05387-110",
        },
        is_active=True,
    )
    db_session.add(unit)
    db_session.flush()

    professional = Professional(
        tenant_id=tenant_id,
        unit_id=unit.id,
        full_name="Marcos Antonio Lopes",
        working_days=[0, 1, 2, 3, 4],
        shift_start="08:00",
        shift_end="18:00",
        procedures=["Avaliação odontológica"],
        is_active=True,
    )
    patient = Patient(
        tenant_id=tenant_id,
        unit_id=unit.id,
        full_name="Maria Silva Almeida",
        phone="5511999000002",
        normalized_phone="5511999000002",
        status="ativo",
        origin="whatsapp",
        lgpd_consent=True,
        marketing_opt_in=True,
        tags_cache=[],
    )
    db_session.add_all([professional, patient])
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

    db_session.add(
        Appointment(
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
    )
    db_session.add(
        Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            direction="inbound",
            channel="whatsapp",
            sender_type="patient",
            body="Qual o endereço da unidade paulista e quem vai me atender? Preciso levar documento?",
            message_type="text",
            payload={},
            status="received",
        )
    )
    db_session.commit()

    def _unexpected_suggest_reply(*args, **kwargs):
        raise AssertionError("suggest_reply nao deveria ser chamado para orientação oficial de visita")

    monkeypatch.setattr(messages_endpoint, "suggest_reply", _unexpected_suggest_reply)
    monkeypatch.setattr(
        messages_endpoint,
        "classify_intent",
        lambda *args, **kwargs: {"output": '{"intent":"informacao_consulta","confidence":0.95}', "metadata": {"provider": "mock"}},
    )

    response = ai_suggestion(
        conversation_id=str(conversation.id),
        payload=AISuggestionInput(),
        db=db_session,
        tenant_id=tenant_id,
    )

    assert "Rua Ramondetti Giacomo, 24, Vila Dalva, Sao Paulo - SP, 05387-110" in response["suggested_reply"]
    assert "Marcos Antonio Lopes" in response["suggested_reply"]
    assert "documento com foto e CPF" in response["suggested_reply"]
    assert response["metadata"]["suggest_reply"]["source"] == "official_visit_guidance"

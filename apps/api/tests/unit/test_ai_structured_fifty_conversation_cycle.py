from __future__ import annotations

from uuid import uuid4

from app.models import Tenant

from tests.unit.test_ai_structured_ten_conversation_cycle import (
    _run_availability_conversation,
    _run_confirm_conversation,
    _run_hold_conversation,
    _run_human_request_conversation,
    _run_insurance_conversation,
    _run_invalid_json_conversation,
    _run_price_conversation,
    _run_service_conversation,
    _run_units_conversation,
    _run_urgency_conversation,
)
from tests.unit.test_ai_structured_conversation_cycle import _prepare_tenant, test_engine


def _create_isolated_tenant(db_session, seeded_db, index: int):
    tenant = Tenant(
        legal_name=f"Clinica Conversa {index} LTDA",
        trade_name=f"Clinica Conversa {index}",
        slug=f"tenant-conversa-{index}-{uuid4().hex[:6]}",
        plan_id=seeded_db["tenant_a"].plan_id,
        subscription_status="active",
    )
    db_session.add(tenant)
    db_session.commit()
    return tenant


def test_fifty_complete_conversations_pass_consecutively(monkeypatch, seeded_db, db_session):
    scenarios = [
        _run_service_conversation,
        _run_price_conversation,
        _run_insurance_conversation,
        _run_units_conversation,
        _run_availability_conversation,
        _run_hold_conversation,
        _run_confirm_conversation,
        _run_human_request_conversation,
        _run_urgency_conversation,
        _run_invalid_json_conversation,
    ]

    completed = 0
    for batch_index in range(5):
        tenant = _create_isolated_tenant(db_session, seeded_db, batch_index + 1)
        _prepare_tenant(db_session, tenant_id=tenant.id)
        for scenario in scenarios:
            scenario(monkeypatch, db_session, tenant_id=tenant.id)
            completed += 1

    assert completed == 50

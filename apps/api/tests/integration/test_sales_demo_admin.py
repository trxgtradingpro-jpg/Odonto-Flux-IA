import os

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_SALES_DEMO_INTEGRATION_TESTS") != "1",
    reason="Defina RUN_SALES_DEMO_INTEGRATION_TESTS=1 com um banco de teste isolado.",
)


def test_sales_admin_generates_isolated_demo(client, auth_headers):
    payload = {
        "clinic_name": "Clinica Teste Conversao",
        "whatsapp_phone": "+55 11 98888-0000",
        "city": "Osasco",
        "state": "SP",
        "main_pain": "Recepcao perde leads no WhatsApp",
        "services": [
            {"service_name": "Avaliacao odontologica", "duration_minutes": 45},
            {"service_name": "Clareamento dental", "duration_minutes": 75},
        ],
    }

    created = client.post("/api/v1/admin/prospects", json=payload, headers=auth_headers["admin"])
    assert created.status_code == 200
    prospect = created.json()

    generated = client.post(
        f"/api/v1/admin/prospects/{prospect['id']}/generate-demo",
        headers={**auth_headers["admin"], "Origin": "http://localhost:3000"},
    )
    assert generated.status_code == 200
    demo = generated.json()
    assert demo["prospect"]["demo_tenant_id"]
    assert demo["prospect"]["demo_user_id"]
    assert demo["access_token"]
    assert "demo_token=" in demo["demo_login_url"]

    redeemed = client.post("/api/v1/demo/auth/redeem-token", json={"token": demo["access_token"]})
    assert redeemed.status_code == 200
    assert redeemed.json()["demo_target_path"] == "/conversas"
    assert redeemed.json()["demo_whatsapp_link"] is None
    assert redeemed.json()["demo_entry_channel"] == "webchat"
    assert redeemed.json()["demo_public_entry_path"] == f"/agendar/{demo['prospect']['slug']}"
    demo_auth = {"Authorization": f"Bearer {redeemed.json()['access_token']}"}

    me = client.get("/api/v1/auth/me", headers=demo_auth)
    assert me.status_code == 200
    assert me.json()["tenant_id"] == demo["prospect"]["demo_tenant_id"]
    assert "demo_client" in me.json()["roles"]
    assert me.json()["demo_entry_channel"] == "webchat"
    assert me.json()["demo_public_entry_path"] == f"/agendar/{demo['prospect']['slug']}"

    guide = client.get("/api/v1/demo/guide", headers=demo_auth)
    assert guide.status_code == 200
    guide_payload = guide.json()
    assert guide_payload["current_step_id"] == "value_outcome"
    assert guide_payload["total_steps"] == 7
    assert len(guide_payload["steps"]) == 7

    guide_forbidden = client.get("/api/v1/demo/guide", headers=auth_headers["admin"])
    assert guide_forbidden.status_code == 403

    guide_resume = client.post(
        "/api/v1/demo/guide/resume",
        json={"source": "integration_test", "page_path": "/dashboard", "session_id": "test-session"},
        headers=demo_auth,
    )
    assert guide_resume.status_code == 200
    assert guide_resume.json()["status"] == "active"

    guide_complete = client.post(
        "/api/v1/demo/guide/complete-step",
        json={"step_id": "value_outcome", "source": "integration_test", "page_path": "/dashboard", "session_id": "test-session"},
        headers=demo_auth,
    )
    assert guide_complete.status_code == 200
    assert "value_outcome" in guide_complete.json()["completed_step_ids"]
    assert guide_complete.json()["current_step_id"] == "dashboard_overview"

    guide_dismiss = client.post(
        "/api/v1/demo/guide/dismiss",
        json={"source": "integration_test", "page_path": "/dashboard", "session_id": "test-session"},
        headers=demo_auth,
    )
    assert guide_dismiss.status_code == 200
    assert guide_dismiss.json()["status"] == "dismissed"

    automations = client.get("/api/v1/automations", headers=demo_auth)
    assert automations.status_code == 200
    assert len(automations.json()["data"]) >= 3

    event = client.post(
        "/api/v1/demo/events",
        json={"event_name": "visited_agenda", "page_path": "/agenda", "session_id": "test-session", "payload": {}},
        headers=demo_auth,
    )
    assert event.status_code == 200

    activity = client.get(f"/api/v1/admin/prospects/{prospect['id']}/activity", headers=auth_headers["admin"])
    assert activity.status_code == 200
    assert any(item["event_name"] == "visited_agenda" for item in activity.json())
    assert any(item["event_name"] == "demo_guided_started" for item in activity.json())
    assert any(item["event_name"] == "demo_guided_step_completed" for item in activity.json())

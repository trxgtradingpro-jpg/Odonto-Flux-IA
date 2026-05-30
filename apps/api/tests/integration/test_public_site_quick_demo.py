def test_public_site_quick_demo_creates_and_reuses_demo(client):
    payload = {
        "clinic_name": "Clinica Expresso",
        "owner_name": "Mariana Costa",
        "phone": "+55 11 97777-4321",
    }

    created = client.post(
        "/api/v1/public/site/quick-demo",
        json=payload,
        headers={"Origin": "http://localhost:3000"},
    )
    assert created.status_code == 200
    first_demo = created.json()
    assert first_demo["status"] == "created"
    assert first_demo["prospect"]["clinic_name"] == payload["clinic_name"]
    assert first_demo["prospect"]["owner_name"] == payload["owner_name"]
    assert first_demo["demo_login_url"].startswith("http://localhost:3000/login?demo_token=")
    assert first_demo["demo_booking_path"].startswith("/agendar/")
    assert first_demo["demo_booking_url"] == f"http://localhost:3000{first_demo['demo_booking_path']}"
    assert first_demo["selected_template_slug"] is None

    reused = client.post(
        "/api/v1/public/site/quick-demo",
        json=payload,
        headers={"Origin": "http://localhost:3000"},
    )
    assert reused.status_code == 200
    second_demo = reused.json()
    assert second_demo["status"] == "reused"
    assert second_demo["prospect"]["id"] == first_demo["prospect"]["id"]
    assert second_demo["demo_booking_path"] == first_demo["demo_booking_path"]


def test_public_site_quick_demo_records_selected_template(client):
    payload = {
        "clinic_name": "Clinica Template",
        "owner_name": "Renata Alves",
        "phone": "+55 11 98888-1111",
        "template_slug": "clinica-odontologica-premium",
    }

    response = client.post(
        "/api/v1/public/site/quick-demo",
        json=payload,
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["selected_template_slug"] == payload["template_slug"]
    assert body["site_template_preview_url"].startswith(
        "http://localhost:3000/modelos-sites/clinica-odontologica-premium"
    )
    assert body["prospect"]["proposal_snapshot"]["site_template"]["selected_template_slug"] == payload["template_slug"]
    assert body["prospect"]["proposal_snapshot"]["site_template"]["public_catalog_path"] == "/modelos-sites"

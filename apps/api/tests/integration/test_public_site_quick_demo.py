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

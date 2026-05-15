from app.core.config import settings


def test_adm_login_uses_exact_bootstrap_env_credentials(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "adm_bootstrap_email", "bootstrap@test.com")
    monkeypatch.setattr(settings, "adm_bootstrap_password", "Bootstrap@123")
    monkeypatch.setattr(settings, "adm_bootstrap_version", "1")

    response = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "bootstrap@test.com", "password": "Bootstrap@123"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["force_password_change"] is False
    assert "admin_platform" in payload["roles"]
    assert "sales_admin" in payload["roles"]

    wrong_email = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "other@test.com", "password": "Bootstrap@123"},
    )
    assert wrong_email.status_code == 401

    wrong_password = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "bootstrap@test.com", "password": "WrongPass@123"},
    )
    assert wrong_password.status_code == 401


def test_adm_change_password_is_blocked_for_env_managed_bootstrap(client, monkeypatch):
    monkeypatch.setattr(settings, "adm_bootstrap_email", "bootstrap@test.com")
    monkeypatch.setattr(settings, "adm_bootstrap_password", "Bootstrap@123")
    monkeypatch.setattr(settings, "adm_bootstrap_version", "1")

    login = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "bootstrap@test.com", "password": "Bootstrap@123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    response = client.post(
        "/api/v1/admin/auth/change-initial-password",
        json={"current_password": "Bootstrap@123", "new_password": "AnotherPass@123"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ADM_ENV_MANAGED_CREDENTIALS"

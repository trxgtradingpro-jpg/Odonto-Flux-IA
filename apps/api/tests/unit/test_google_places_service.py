from app.models import ProspectAccount
from app.services import google_places_service


class _FakeGoogleResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeGoogleClient:
    def __init__(self, payload):
        self.payload = payload
        self.posts = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json=None, headers=None):
        self.posts.append({"url": url, "json": json, "headers": headers})
        return _FakeGoogleResponse(self.payload)


def test_search_google_places_filters_existing_and_repeated_clinics(monkeypatch, seeded_db, db_session):
    existing = ProspectAccount(
        clinic_name="Clinica Ja Cadastrada",
        proposal_snapshot={"google_places": {"place_id": "place-existing"}},
    )
    db_session.add(existing)
    db_session.commit()

    payload = {
        "places": [
            {
                "id": "place-existing",
                "displayName": {"text": "Clinica Ja Cadastrada"},
                "formattedAddress": "Rua Um, 100",
                "googleMapsUri": "https://maps.google.com/?cid=1",
                "businessStatus": "OPERATIONAL",
                "types": ["dentist"],
            },
            {
                "id": "place-fresh",
                "displayName": {"text": "Clinica Nova"},
                "formattedAddress": "Av. Dois, 200",
                "googleMapsUri": "https://maps.google.com/?cid=2",
                "businessStatus": "OPERATIONAL",
                "types": ["dentist"],
            },
            {
                "id": "place-fresh",
                "displayName": {"text": "Clinica Nova"},
                "formattedAddress": "Av. Dois, 200",
                "googleMapsUri": "https://maps.google.com/?cid=2",
                "businessStatus": "OPERATIONAL",
                "types": ["dentist"],
            },
        ]
    }
    fake_client = _FakeGoogleClient(payload)

    monkeypatch.setattr(google_places_service.settings, "google_places_api_key", "test-key")
    monkeypatch.setattr(google_places_service.httpx, "Client", lambda timeout: fake_client)

    result = google_places_service.search_google_places(
        db_session,
        query="clinica odontologica em Sao Paulo",
        limit=10,
        region_code="BR",
        included_type="dentist",
    )

    assert len(result["results"]) == 1
    assert result["results"][0]["place_id"] == "place-fresh"
    assert result["results"][0]["duplicate_prospect_id"] is None
    assert result["results"][0]["duplicate_clinic_name"] is None
    assert len(fake_client.posts) == 1

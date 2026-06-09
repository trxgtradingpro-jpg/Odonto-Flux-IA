from __future__ import annotations

import unicodedata
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ApiError
from app.models import ProspectAccount
from app.schemas.admin_sales import ProspectCreate
from app.services import sales_demo_service as sales
from app.utils.phone import normalize_phone

PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
IBGE_MUNICIPALITIES_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/{state}/municipios"
IBGE_DISTRICTS_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios/{municipality_id}/distritos"

# Search stays intentionally cheap: no phone, website, rating or reviews here.
PLACES_SEARCH_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.addressComponents",
        "places.googleMapsUri",
        "places.businessStatus",
        "places.types",
    ]
)

PLACES_DETAILS_FIELD_MASK = ",".join(
    [
        "id",
        "displayName",
        "formattedAddress",
        "addressComponents",
        "nationalPhoneNumber",
        "internationalPhoneNumber",
        "websiteUri",
        "googleMapsUri",
        "location",
        "businessStatus",
        "types",
    ]
)

PLACES_RATING_FIELDS = "rating,userRatingCount"

AUTOMATION_SEARCH_TERMS = {
    "dentist": ("clinica odontologica", "dentista"),
    "doctor": ("clinica medica", "medico"),
}


def _require_api_key() -> str:
    api_key = str(settings.google_places_api_key or "").strip()
    if not api_key:
        raise ApiError(
            status_code=400,
            code="GOOGLE_PLACES_API_KEY_MISSING",
            message="Configure GOOGLE_PLACES_API_KEY no backend antes de buscar clinicas no Google Places.",
        )
    return api_key


def _place_id(value: str | None) -> str:
    raw = str(value or "").strip()
    if raw.startswith("places/"):
        return raw.split("/", 1)[1].strip()
    return raw


def _normalized_location_name(value: str | None) -> str:
    raw = unicodedata.normalize("NFKD", str(value or "").strip())
    return "".join(character for character in raw if not unicodedata.combining(character)).casefold()


def _automation_search_terms(included_type: str | None) -> tuple[str, ...]:
    if included_type in AUTOMATION_SEARCH_TERMS:
        return AUTOMATION_SEARCH_TERMS[included_type]
    return ("clinica", "consultorio")


def build_google_places_automation_plan(
    *,
    state: str,
    city: str,
    target_limit: int,
    included_type: str | None = "dentist",
) -> dict[str, Any]:
    clean_state = str(state or "").strip().upper()
    clean_city = " ".join(str(city or "").strip().split())
    if len(clean_state) != 2:
        raise ApiError(
            status_code=422,
            code="PLACES_AUTOMATION_STATE_INVALID",
            message="Informe uma UF valida com 2 letras.",
        )
    if len(clean_city) < 2:
        raise ApiError(
            status_code=422,
            code="PLACES_AUTOMATION_CITY_INVALID",
            message="Informe a cidade da busca automatica.",
        )

    try:
        with httpx.Client(timeout=settings.google_places_timeout_seconds) as client:
            municipalities_response = client.get(
                IBGE_MUNICIPALITIES_URL.format(state=clean_state),
                params={"orderBy": "nome"},
            )
            municipalities_response.raise_for_status()
            municipalities = municipalities_response.json()
            if not isinstance(municipalities, list):
                municipalities = []

            normalized_city = _normalized_location_name(clean_city)
            municipality = next(
                (
                    item
                    for item in municipalities
                    if isinstance(item, dict) and _normalized_location_name(item.get("nome")) == normalized_city
                ),
                None,
            )
            if not municipality:
                raise ApiError(
                    status_code=404,
                    code="PLACES_AUTOMATION_CITY_NOT_FOUND",
                    message=f"Nao encontrei a cidade {clean_city} na UF {clean_state}.",
                )

            municipality_id = int(municipality["id"])
            canonical_city = str(municipality.get("nome") or clean_city).strip()
            districts_response = client.get(
                IBGE_DISTRICTS_URL.format(municipality_id=municipality_id),
                params={"orderBy": "nome"},
            )
            districts_response.raise_for_status()
            districts = districts_response.json()
            if not isinstance(districts, list):
                districts = []
    except ApiError:
        raise
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise ApiError(
            status_code=502,
            code="PLACES_AUTOMATION_AREAS_UNAVAILABLE",
            message="Nao consegui carregar os distritos oficiais da cidade no IBGE.",
            details={"error": str(exc)},
        ) from exc

    areas: list[str] = []
    for district in districts:
        if not isinstance(district, dict):
            continue
        area = " ".join(str(district.get("nome") or "").strip().split())
        if area and area not in areas:
            areas.append(area)

    source = "ibge_districts" if areas else "city_fallback"
    if not areas:
        areas = [canonical_city]

    queries: list[dict[str, str]] = []
    for term in _automation_search_terms(included_type):
        for area in areas:
            is_city_wide = _normalized_location_name(area) == _normalized_location_name(canonical_city)
            location = (
                f"{canonical_city} - {clean_state}"
                if is_city_wide
                else f"{area}, {canonical_city} - {clean_state}"
            )
            queries.append(
                {
                    "area": area,
                    "term": term,
                    "query": f"{term} em {location}",
                }
            )

    return {
        "state": clean_state,
        "city": canonical_city,
        "municipality_id": municipality_id,
        "target_limit": int(target_limit),
        "source": source,
        "areas": areas,
        "queries": queries,
        "estimated_max_search_calls": len(queries),
    }


def _display_name(place: dict[str, Any]) -> str:
    display_name = place.get("displayName")
    if isinstance(display_name, dict):
        text = str(display_name.get("text") or "").strip()
        if text:
            return text
    return str(place.get("name") or "").strip()


def _address_component(place: dict[str, Any], accepted_types: set[str], *, short: bool = False) -> str | None:
    components = place.get("addressComponents")
    if not isinstance(components, list):
        return None
    for component in components:
        if not isinstance(component, dict):
            continue
        types = component.get("types")
        if not isinstance(types, list) or not accepted_types.intersection({str(item) for item in types}):
            continue
        value = component.get("shortText" if short else "longText") or component.get("longText") or component.get("shortText")
        text = str(value or "").strip()
        if text:
            return text
    return None


def _city_from_place(place: dict[str, Any]) -> str | None:
    return _address_component(
        place,
        {"locality", "administrative_area_level_2", "postal_town", "sublocality"},
    )


def _state_from_place(place: dict[str, Any]) -> str | None:
    return _address_component(place, {"administrative_area_level_1"}, short=True)


def _location_from_place(place: dict[str, Any]) -> dict[str, float] | None:
    location = place.get("location")
    if not isinstance(location, dict):
        return None
    latitude = location.get("latitude")
    longitude = location.get("longitude")
    if latitude is None or longitude is None:
        return None
    try:
        return {"latitude": float(latitude), "longitude": float(longitude)}
    except (TypeError, ValueError):
        return None


def _known_place_ids(db: Session, place_ids: list[str]) -> dict[str, ProspectAccount]:
    cleaned_ids = [_place_id(item) for item in place_ids if _place_id(item)]
    if not cleaned_ids:
        return {}
    rows = db.execute(
        select(ProspectAccount).where(
            ProspectAccount.proposal_snapshot["google_places"]["place_id"].astext.in_(cleaned_ids)
        )
    ).scalars().all()
    output: dict[str, ProspectAccount] = {}
    for prospect in rows:
        snapshot = prospect.proposal_snapshot if isinstance(prospect.proposal_snapshot, dict) else {}
        google_places = snapshot.get("google_places") if isinstance(snapshot.get("google_places"), dict) else {}
        place_id = _place_id(str(google_places.get("place_id") or ""))
        if place_id:
            output[place_id] = prospect
    return output


def _serialize_place_preview(place: dict[str, Any], *, duplicate: ProspectAccount | None = None) -> dict[str, Any]:
    place_id = _place_id(str(place.get("id") or place.get("name") or ""))
    return {
        "place_id": place_id,
        "name": _display_name(place),
        "formatted_address": str(place.get("formattedAddress") or "").strip() or None,
        "city": _city_from_place(place),
        "state": _state_from_place(place),
        "google_maps_url": str(place.get("googleMapsUri") or "").strip() or None,
        "business_status": str(place.get("businessStatus") or "").strip() or None,
        "types": [str(item) for item in place.get("types") or [] if str(item or "").strip()],
        "duplicate_prospect_id": str(duplicate.id) if duplicate else None,
        "duplicate_clinic_name": duplicate.clinic_name if duplicate else None,
    }


def search_google_places(
    db: Session,
    *,
    query: str,
    limit: int,
    region_code: str = "BR",
    included_type: str | None = "dentist",
) -> dict[str, Any]:
    api_key = _require_api_key()
    clean_query = str(query or "").strip()
    if len(clean_query) < 3:
        raise ApiError(status_code=422, code="PLACES_QUERY_TOO_SHORT", message="Informe uma busca com pelo menos 3 caracteres.")

    max_results = max(1, min(int(limit or 10), 20))
    payload: dict[str, Any] = {
        "textQuery": clean_query,
        "maxResultCount": max_results,
        "languageCode": "pt-BR",
        "regionCode": (region_code or "BR").upper()[:2],
    }
    if included_type:
        payload["includedType"] = included_type
        payload["strictTypeFiltering"] = False

    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": PLACES_SEARCH_FIELD_MASK,
    }
    try:
        with httpx.Client(timeout=settings.google_places_timeout_seconds) as client:
            response = client.post(PLACES_TEXT_SEARCH_URL, json=payload, headers=headers)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ApiError(
            status_code=502,
            code="GOOGLE_PLACES_SEARCH_FAILED",
            message="O Google Places recusou a busca. Confira se a API Places esta ativa e se a chave tem permissao.",
            details={"status_code": exc.response.status_code, "response": exc.response.text[:1000]},
        ) from exc
    except httpx.HTTPError as exc:
        raise ApiError(
            status_code=502,
            code="GOOGLE_PLACES_SEARCH_UNAVAILABLE",
            message="Nao consegui conectar ao Google Places agora.",
            details={"error": str(exc)},
        ) from exc

    data = response.json()
    places = data.get("places") if isinstance(data.get("places"), list) else []
    place_ids = [_place_id(str(place.get("id") or place.get("name") or "")) for place in places if isinstance(place, dict)]
    duplicates = _known_place_ids(db, place_ids)
    seen_place_ids: set[str] = set()
    filtered_places: list[dict[str, Any]] = []
    for place in places:
        if not isinstance(place, dict):
            continue
        place_id = _place_id(str(place.get("id") or place.get("name") or ""))
        if not place_id or place_id in seen_place_ids:
            continue
        seen_place_ids.add(place_id)
        if place_id in duplicates:
            continue
        filtered_places.append(place)

    return {
        "query": clean_query,
        "limit": max_results,
        "field_mask": PLACES_SEARCH_FIELD_MASK,
        "cost_mode": "search_basic_only",
        "results": [
            _serialize_place_preview(place, duplicate=None)
            for place in filtered_places
        ],
    }


def fetch_google_place_details(*, place_id: str, include_rating: bool = False) -> dict[str, Any]:
    api_key = _require_api_key()
    clean_place_id = _place_id(place_id)
    if not clean_place_id:
        raise ApiError(status_code=422, code="PLACE_ID_REQUIRED", message="Place ID obrigatorio.")

    field_mask = PLACES_DETAILS_FIELD_MASK
    if include_rating:
        field_mask = f"{field_mask},{PLACES_RATING_FIELDS}"
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": field_mask,
    }
    try:
        with httpx.Client(timeout=settings.google_places_timeout_seconds) as client:
            response = client.get(PLACES_DETAILS_URL.format(place_id=clean_place_id), headers=headers)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ApiError(
            status_code=502,
            code="GOOGLE_PLACE_DETAILS_FAILED",
            message="O Google Places recusou os detalhes desta clinica.",
            details={"place_id": clean_place_id, "status_code": exc.response.status_code, "response": exc.response.text[:1000]},
        ) from exc
    except httpx.HTTPError as exc:
        raise ApiError(
            status_code=502,
            code="GOOGLE_PLACE_DETAILS_UNAVAILABLE",
            message="Nao consegui conectar ao Google Places para buscar detalhes.",
            details={"place_id": clean_place_id, "error": str(exc)},
        ) from exc
    return response.json()


def _proposal_snapshot_from_place(place: dict[str, Any], *, include_rating: bool) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "source": "google_places",
        "google_places": {
            "place_id": _place_id(str(place.get("id") or "")),
            "maps_url": str(place.get("googleMapsUri") or "").strip() or None,
            "business_status": str(place.get("businessStatus") or "").strip() or None,
            "types": [str(item) for item in place.get("types") or [] if str(item or "").strip()],
            "location": _location_from_place(place),
            "imported_at": datetime.now(UTC).isoformat(),
            "field_mask": PLACES_DETAILS_FIELD_MASK + (f",{PLACES_RATING_FIELDS}" if include_rating else ""),
        },
    }
    if include_rating:
        snapshot["google_places"]["rating"] = place.get("rating")
        snapshot["google_places"]["user_rating_count"] = place.get("userRatingCount")
    return snapshot


def _prospect_payload_from_place(place: dict[str, Any], *, lead_source: str, include_rating: bool) -> ProspectCreate:
    clinic_name = _display_name(place)
    if len(clinic_name) < 2:
        raise ApiError(status_code=422, code="GOOGLE_PLACE_NAME_MISSING", message="O local selecionado nao retornou nome da clinica.")

    national_phone = str(place.get("nationalPhoneNumber") or "").strip()
    international_phone = str(place.get("internationalPhoneNumber") or "").strip()
    source_phone = national_phone or international_phone
    normalized_phone = normalize_phone(source_phone) or None
    formatted_address = str(place.get("formattedAddress") or "").strip() or None
    maps_url = str(place.get("googleMapsUri") or "").strip()
    website = str(place.get("websiteUri") or "").strip() or None

    notes = "Importado automaticamente do Google Places."
    if maps_url:
        notes = f"{notes}\nGoogle Maps: {maps_url}"
    if source_phone:
        notes = f"{notes}\nTelefone original no Google: {source_phone}"

    return ProspectCreate(
        clinic_name=clinic_name,
        phone=normalized_phone,
        whatsapp_phone=normalized_phone,
        website=website,
        city=_city_from_place(place),
        state=_state_from_place(place),
        main_address=formatted_address,
        notes=notes,
        lead_source=lead_source,
        tags=["google_places", "importado_google_places"],
        proposal_snapshot=_proposal_snapshot_from_place(place, include_rating=include_rating),
        uses_whatsapp_heavily=bool(normalized_phone),
    )


def _find_duplicate_by_contact(db: Session, *, phone: str | None, website: str | None) -> ProspectAccount | None:
    filters = []
    if phone:
        filters.extend([ProspectAccount.phone == phone, ProspectAccount.whatsapp_phone == phone])
    if website:
        filters.append(ProspectAccount.website == website)
    if not filters:
        return None
    return db.scalar(select(ProspectAccount).where(or_(*filters)).limit(1))


def import_google_places(
    db: Session,
    *,
    place_ids: list[str],
    lead_source: str,
    include_rating: bool,
    actor_id: UUID | None,
) -> dict[str, Any]:
    requested_ids = []
    for raw_place_id in place_ids:
        place_id = _place_id(raw_place_id)
        if place_id and place_id not in requested_ids:
            requested_ids.append(place_id)
    if not requested_ids:
        raise ApiError(status_code=422, code="PLACE_IDS_REQUIRED", message="Selecione pelo menos uma clinica para importar.")
    requested_ids = requested_ids[:20]

    existing_by_place = _known_place_ids(db, requested_ids)
    results: list[dict[str, Any]] = []
    created_count = 0
    duplicate_count = 0
    failed_count = 0

    for place_id in requested_ids:
        existing = existing_by_place.get(place_id)
        if existing:
            duplicate_count += 1
            results.append(
                {
                    "place_id": place_id,
                    "status": "duplicate",
                    "message": "Clinica ja importada anteriormente pelo Place ID.",
                    "prospect": sales.serialize_prospect(db, existing),
                    "name": existing.clinic_name,
                }
            )
            continue

        try:
            place = fetch_google_place_details(place_id=place_id, include_rating=include_rating)
            payload = _prospect_payload_from_place(place, lead_source=lead_source, include_rating=include_rating)
            contact_duplicate = _find_duplicate_by_contact(
                db,
                phone=payload.whatsapp_phone or payload.phone,
                website=payload.website,
            )
            if contact_duplicate:
                duplicate_count += 1
                results.append(
                    {
                        "place_id": place_id,
                        "status": "duplicate",
                        "message": "Clinica possivelmente duplicada por telefone ou site.",
                        "prospect": sales.serialize_prospect(db, contact_duplicate),
                        "name": payload.clinic_name,
                    }
                )
                continue

            prospect = sales.create_prospect(db, payload, actor_id=actor_id)
            created_count += 1
            results.append(
                {
                    "place_id": place_id,
                    "status": "created",
                    "message": "Clinica importada para o CRM comercial.",
                    "prospect": sales.serialize_prospect(db, prospect),
                    "name": prospect.clinic_name,
                }
            )
        except ApiError as exc:
            failed_count += 1
            results.append(
                {
                    "place_id": place_id,
                    "status": "failed",
                    "message": exc.message,
                    "prospect": None,
                    "name": None,
                }
            )

    return {
        "created_count": created_count,
        "duplicate_count": duplicate_count,
        "failed_count": failed_count,
        "requested_count": len(requested_ids),
        "include_rating": include_rating,
        "results": results,
    }

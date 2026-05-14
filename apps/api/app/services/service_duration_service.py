from __future__ import annotations

import re
import unicodedata
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Setting
from app.services.service_catalog_service import get_service_catalog_items, service_catalog_as_knowledge_services

AI_KNOWLEDGE_BASE_SETTING_KEY = "ai_knowledge_base.global"
DEFAULT_SERVICE_DURATION_MINUTES = 60


def normalize_service_label(value: str | None) -> str:
    normalized = unicodedata.normalize("NFD", str(value or ""))
    stripped = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return " ".join(stripped.lower().strip().split())


def _service_tokens(value: str | None) -> set[str]:
    stopwords = {
        "a",
        "as",
        "o",
        "os",
        "de",
        "da",
        "do",
        "das",
        "dos",
        "e",
        "para",
        "com",
        "sem",
        "na",
        "no",
        "nas",
        "nos",
        "dental",
        "dentario",
        "dentaria",
        "odontologica",
        "odontologico",
        "oral",
        "clinica",
        "consulta",
        "sessao",
        "sessao",
        "procedimento",
    }
    normalized = normalize_service_label(value)
    if not normalized:
        return set()
    return {
        token
        for token in normalized.split()
        if len(token) >= 4 and token not in stopwords
    }


def labels_match(left: str | None, right: str | None) -> bool:
    left_normalized = normalize_service_label(left)
    right_normalized = normalize_service_label(right)
    if not left_normalized or not right_normalized:
        return False
    if left_normalized == right_normalized:
        return True
    if left_normalized in right_normalized or right_normalized in left_normalized:
        return True

    shared_tokens = _service_tokens(left_normalized) & _service_tokens(right_normalized)
    if not shared_tokens:
        return False
    if len(shared_tokens) >= 2:
        return True
    return any(len(token) >= 5 for token in shared_tokens)


def _match_score(left: str | None, right: str | None) -> int | None:
    left_normalized = normalize_service_label(left)
    right_normalized = normalize_service_label(right)
    if not left_normalized or not right_normalized:
        return None
    if left_normalized == right_normalized:
        return 0
    if left_normalized in right_normalized or right_normalized in left_normalized:
        return 1

    shared_tokens = _service_tokens(left_normalized) & _service_tokens(right_normalized)
    if len(shared_tokens) >= 2:
        return 2
    if shared_tokens and any(len(token) >= 5 for token in shared_tokens):
        return 3
    return None


def parse_duration_note_to_minutes(value: str | None) -> int | None:
    text = normalize_service_label(value)
    if not text:
        return None

    candidates: list[int] = []

    for hours_text, minutes_text in re.findall(r"(\d{1,2})\s*h(?:\s*(\d{1,2}))?", text):
        hours = int(hours_text)
        minutes = int(minutes_text) if minutes_text else 0
        total = hours * 60 + minutes
        if 15 <= total <= 8 * 60:
            candidates.append(total)

    for hours_text, minutes_text in re.findall(r"(\d{1,2})\s*hora(?:s)?(?:\s*e\s*(\d{1,2})\s*min(?:uto)?s?)?", text):
        hours = int(hours_text)
        minutes = int(minutes_text) if minutes_text else 0
        total = hours * 60 + minutes
        if 15 <= total <= 8 * 60:
            candidates.append(total)

    minute_numbers = [int(number) for number in re.findall(r"(\d{1,3})\s*min(?:uto)?s?", text)]
    candidates.extend(number for number in minute_numbers if 15 <= number <= 8 * 60)

    if ("min" in text or "minuto" in text) and not minute_numbers and not candidates:
        bare_numbers = [int(number) for number in re.findall(r"\b(\d{1,3})\b", text)]
        candidates.extend(number for number in bare_numbers if 15 <= number <= 8 * 60)

    if not candidates:
        return None
    return max(candidates)


def get_service_duration_catalog(db: Session, *, tenant_id: UUID) -> list[dict[str, Any]]:
    official_catalog = service_catalog_as_knowledge_services(
        get_service_catalog_items(db, tenant_id=tenant_id)
    )
    if official_catalog:
        return official_catalog

    item = db.scalar(
        select(Setting).where(
            Setting.tenant_id == tenant_id,
            Setting.key == AI_KNOWLEDGE_BASE_SETTING_KEY,
        )
    )
    if not item or not isinstance(item.value, dict):
        return []
    raw_services = item.value.get("services")
    if not isinstance(raw_services, list):
        return []
    return [service for service in raw_services if isinstance(service, dict)]


def resolve_service_duration_minutes(
    *,
    procedure_type: str | None,
    service_catalog: list[dict[str, Any]] | None,
    default_minutes: int = DEFAULT_SERVICE_DURATION_MINUTES,
) -> int:
    normalized_catalog = service_catalog or []
    best_score: int | None = None
    best_duration: int | None = None

    for service in normalized_catalog:
        service_name = str(service.get("name") or "").strip()
        score = _match_score(service_name, procedure_type)
        if score is None:
            continue
        duration = parse_duration_note_to_minutes(service.get("duration_note"))
        if duration is None:
            continue
        if best_score is None or score < best_score or (score == best_score and duration > (best_duration or 0)):
            best_score = score
            best_duration = duration

    if best_duration is not None:
        return best_duration
    return default_minutes


def resolve_appointment_end(
    *,
    starts_at,
    ends_at,
    procedure_type: str | None,
    service_catalog: list[dict[str, Any]] | None,
    default_minutes: int = DEFAULT_SERVICE_DURATION_MINUTES,
):
    if ends_at and ends_at > starts_at:
        return ends_at
    duration_minutes = resolve_service_duration_minutes(
        procedure_type=procedure_type,
        service_catalog=service_catalog,
        default_minutes=default_minutes,
    )
    return starts_at + timedelta(minutes=duration_minutes)

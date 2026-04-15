from __future__ import annotations

import json
import re
import unicodedata
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from time import perf_counter
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import logger
from app.models import (
    AIAutoresponderDecision,
    Appointment,
    AppointmentEvent,
    Conversation,
    Lead,
    Message,
    MessageEvent,
    Patient,
    Professional,
    Setting,
    Unit,
    User,
)
from app.models.enums import MessageDirection, MessageStatus
from app.services.automation_service import emit_event
from app.services.audit_service import record_audit
from app.services.llm_service import classify_intent, run_llm_task
from app.services.whatsapp_service import assert_whatsapp_account_ready_for_dispatch, queue_outbound_message

AI_AUTORESPONDER_PROMPT_VERSION = "v1.1"

AI_AUTORESPONDER_DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "channels": {
        "whatsapp": True,
    },
    "business_hours": {
        "timezone": "America/Sao_Paulo",
        "weekdays": [0, 1, 2, 3, 4],
        "start": "08:00",
        "end": "18:00",
    },
    "outside_business_hours_mode": "handoff",
    "max_consecutive_auto_replies": 3,
    "confidence_threshold": 0.65,
    "human_queue_tag": "fila_humana_ia",
    "tone": "profissional, cordial e objetivo",
    "fallback_user_id": None,
}

AI_KNOWLEDGE_BASE_DEFAULT_CONFIG: dict[str, Any] = {
    "clinic_profile": {
        "clinic_name": "",
        "about": "",
        "differentials": [],
        "target_audience": "",
        "tone_preferences": "",
    },
    "services": [],
    "insurance": {
        "accepted_plans": [],
        "notes": "",
    },
    "operational_policies": {
        "booking_rules": "",
        "cancellation_policy": "",
        "reschedule_policy": "",
        "payment_policy": "",
        "documents_required": "",
    },
    "faq": [],
    "commercial_playbook": {
        "value_proposition": "",
        "objection_handling": "",
        "default_cta": "",
    },
    "escalation": {
        "human_handoff_topics": [],
        "restricted_topics": [],
        "custom_urgent_keywords": [],
        "fallback_message": "",
    },
}

HUMAN_REQUEST_PATTERNS = [
    "falar com atendente",
    "falar com humano",
    "falar com pessoa",
    "atendimento humano",
    "quero falar com atendente",
    "transferir para atendente",
]

URGENCY_PATTERNS = [
    "urgente",
    "emergencia",
    "emergência",
    "dor forte",
    "dor intensa",
    "sangramento",
    "hemorragia",
    "febre alta",
    "falta de ar",
    "desmaio",
    "trauma",
    "acidente",
    "inchaco",
    "inchaço",
]

CLINICAL_PATTERNS = [
    "diagnostico",
    "diagnóstico",
    "prescricao",
    "prescrição",
    "receita",
    "antibiotico",
    "antibiótico",
    "medicacao",
    "medicação",
    "dosagem",
    "dose",
    "laudo",
]

CONTACT_NAME_PATTERNS = [
    re.compile(r"\bmeu\s+nome(?:\s+completo)?\s*(?:e|eh|é)\s+(.+)$", re.IGNORECASE),
    re.compile(r"\bme\s+chamo\s+(.+)$", re.IGNORECASE),
    re.compile(r"\bsou\s+(?:o|a)\s+(.+)$", re.IGNORECASE),
]

CONTACT_EMAIL_PATTERN = re.compile(
    r"\b([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b",
    re.IGNORECASE,
)

SCHEDULING_INTENT_KEYWORDS = (
    "agendar",
    "agenda",
    "marcar",
    "consulta",
)

AVAILABILITY_REQUEST_KEYWORDS = (
    "horario",
    "horarios",
    "vaga",
    "disponivel",
    "disponiveis",
)

PERIOD_MORNING_KEYWORDS = ("manha", "manhã")
PERIOD_AFTERNOON_KEYWORDS = ("tarde",)
PERIOD_EVENING_KEYWORDS = ("noite",)
FOLLOWUP_AVAILABILITY_KEYWORDS = (
    "opcao",
    "opcoes",
    "opção",
    "opções",
    "vagas",
    "tem mais",
    "quais",
    "que horas",
    "horarios",
    "horários",
    "disponiveis",
    "disponíveis",
)
BOOKING_CONFIRMATION_KEYWORDS = (
    "pode agendar",
    "pode marcar",
    "pode confirmar",
    "confirmo",
    "quero confirmar",
    "fechado",
    "pode fechar",
)
BOOKING_WIZARD_FORCE_KEYWORDS = (
    "quero agendar",
    "quero marcar",
    "agendar consulta",
)
BOOKING_WIZARD_CONFIRM_YES_KEYWORDS = (
    "confirm_yes",
    "sim",
    "confirmar",
    "confirmo",
    "pode confirmar",
    "pode agendar",
    "ok",
    "fechado",
)
BOOKING_WIZARD_CONFIRM_NO_KEYWORDS = (
    "confirm_no",
    "nao",
    "não",
    "trocar",
    "outro horario",
    "outro horário",
    "rever",
)
BOOKING_WIZARD_DEFAULT_SERVICES = (
    "Avaliação odontológica",
    "Limpeza odontológica",
    "Clareamento dental",
    "Instalação de lentes",
    "Reabilitação estética",
)

REASON_LABELS = {
    "disabled_global": "Modo IA desativado no tenant.",
    "disabled_conversation": "Modo IA desativado para a conversa.",
    "channel_disabled": "Canal desativado para auto-resposta.",
    "outside_business_hours": "Fora do horário de atendimento.",
    "outside_business_hours_silent": "Fora do horário (modo silencioso).",
    "conversation_closed": "Conversa finalizada.",
    "empty_inbound": "Mensagem de entrada sem conteúdo processável.",
    "patient_requested_human": "Paciente solicitou atendimento humano.",
    "urgency_detected": "Risco/urgência detectado, encaminhamento humano obrigatório.",
    "clinical_request_blocked": "Solicitação clínica bloqueada por segurança.",
    "low_confidence": "Baixa confiança da IA para responder com segurança.",
    "max_consecutive_reached": "Limite de respostas automáticas consecutivas atingido.",
    "missing_contact_phone": "Sem telefone de destino para resposta.",
    "whatsapp_not_ready": "Conta WhatsApp indisponível para envio.",
    "response_sent": "Resposta automática enviada para fila.",
    "llm_error": "Falha no provedor de IA, atendimento humano acionado.",
    "dispatch_error": "Falha ao enfileirar mensagem automática.",
}

DECISION_RESPONDED = "responded"
DECISION_HANDOFF = "handoff"
DECISION_BLOCKED = "blocked"
DECISION_IGNORED = "ignored"
DECISION_ERROR = "error"


def _deep_merge(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    if not override:
        return deepcopy(base)

    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _normalize_config(value: dict[str, Any] | None) -> dict[str, Any]:
    merged = _deep_merge(AI_AUTORESPONDER_DEFAULT_CONFIG, value or {})

    merged["enabled"] = bool(merged.get("enabled", False))
    channels = merged.get("channels") or {}
    merged["channels"] = {"whatsapp": bool(channels.get("whatsapp", True))}

    business_hours = merged.get("business_hours") or {}
    weekdays = business_hours.get("weekdays") or [0, 1, 2, 3, 4]
    valid_weekdays = [int(day) for day in weekdays if str(day).isdigit() and 0 <= int(day) <= 6]
    merged["business_hours"] = {
        "timezone": business_hours.get("timezone") or settings.app_timezone,
        "weekdays": valid_weekdays or [0, 1, 2, 3, 4],
        "start": str(business_hours.get("start") or "08:00"),
        "end": str(business_hours.get("end") or "18:00"),
    }

    outside_mode = str(merged.get("outside_business_hours_mode") or "handoff").lower()
    if outside_mode not in {"handoff", "allow", "silent"}:
        outside_mode = "handoff"
    merged["outside_business_hours_mode"] = outside_mode

    max_consecutive = int(merged.get("max_consecutive_auto_replies") or 3)
    merged["max_consecutive_auto_replies"] = max(1, min(max_consecutive, 20))

    confidence_threshold = float(merged.get("confidence_threshold") or 0.65)
    merged["confidence_threshold"] = max(0.0, min(confidence_threshold, 1.0))

    merged["human_queue_tag"] = str(merged.get("human_queue_tag") or "fila_humana_ia").strip() or "fila_humana_ia"
    merged["tone"] = str(merged.get("tone") or AI_AUTORESPONDER_DEFAULT_CONFIG["tone"]).strip()
    merged["fallback_user_id"] = merged.get("fallback_user_id") or None
    return merged


def _compact_text(value: Any, *, max_length: int = 600) -> str:
    text = str(value or "").strip()
    if len(text) > max_length:
        text = text[:max_length].rstrip()
    return text


def _normalize_string_list(value: Any, *, max_items: int = 20, item_max_length: int = 120) -> list[str]:
    if isinstance(value, str):
        raw_items = [chunk for chunk in value.replace(";", ",").replace("\n", ",").split(",")]
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []

    normalized: list[str] = []
    for item in raw_items:
        text = _compact_text(item, max_length=item_max_length)
        if not text:
            continue
        if text not in normalized:
            normalized.append(text)
        if len(normalized) >= max_items:
            break
    return normalized


def _normalize_services(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    services: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        service_name = _compact_text(item.get("name"), max_length=120)
        if not service_name:
            continue
        service = {
            "name": service_name,
            "description": _compact_text(item.get("description"), max_length=500),
            "duration_note": _compact_text(item.get("duration_note"), max_length=120),
            "price_note": _compact_text(item.get("price_note"), max_length=120),
        }
        services.append(service)
        if len(services) >= 30:
            break
    return services


def _normalize_faq(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    faq_items: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        question = _compact_text(item.get("question"), max_length=260)
        answer = _compact_text(item.get("answer"), max_length=500)
        if not question and not answer:
            continue
        faq_items.append({"question": question, "answer": answer})
        if len(faq_items) >= 30:
            break
    return faq_items


def _normalize_knowledge_config(value: dict[str, Any] | None) -> dict[str, Any]:
    merged = _deep_merge(AI_KNOWLEDGE_BASE_DEFAULT_CONFIG, value or {})

    profile = merged.get("clinic_profile") if isinstance(merged.get("clinic_profile"), dict) else {}
    insurance = merged.get("insurance") if isinstance(merged.get("insurance"), dict) else {}
    policies = (
        merged.get("operational_policies")
        if isinstance(merged.get("operational_policies"), dict)
        else {}
    )
    playbook = (
        merged.get("commercial_playbook")
        if isinstance(merged.get("commercial_playbook"), dict)
        else {}
    )
    escalation = merged.get("escalation") if isinstance(merged.get("escalation"), dict) else {}

    return {
        "clinic_profile": {
            "clinic_name": _compact_text(profile.get("clinic_name"), max_length=120),
            "about": _compact_text(profile.get("about"), max_length=700),
            "differentials": _normalize_string_list(profile.get("differentials"), max_items=12),
            "target_audience": _compact_text(profile.get("target_audience"), max_length=240),
            "tone_preferences": _compact_text(profile.get("tone_preferences"), max_length=240),
        },
        "services": _normalize_services(merged.get("services")),
        "insurance": {
            "accepted_plans": _normalize_string_list(
                insurance.get("accepted_plans"),
                max_items=20,
            ),
            "notes": _compact_text(insurance.get("notes"), max_length=500),
        },
        "operational_policies": {
            "booking_rules": _compact_text(policies.get("booking_rules"), max_length=500),
            "cancellation_policy": _compact_text(policies.get("cancellation_policy"), max_length=500),
            "reschedule_policy": _compact_text(policies.get("reschedule_policy"), max_length=500),
            "payment_policy": _compact_text(policies.get("payment_policy"), max_length=500),
            "documents_required": _compact_text(policies.get("documents_required"), max_length=500),
        },
        "faq": _normalize_faq(merged.get("faq")),
        "commercial_playbook": {
            "value_proposition": _compact_text(playbook.get("value_proposition"), max_length=700),
            "objection_handling": _compact_text(playbook.get("objection_handling"), max_length=700),
            "default_cta": _compact_text(playbook.get("default_cta"), max_length=240),
        },
        "escalation": {
            "human_handoff_topics": _normalize_string_list(
                escalation.get("human_handoff_topics"),
                max_items=20,
            ),
            "restricted_topics": _normalize_string_list(escalation.get("restricted_topics"), max_items=20),
            "custom_urgent_keywords": _normalize_string_list(
                escalation.get("custom_urgent_keywords"),
                max_items=20,
            ),
            "fallback_message": _compact_text(escalation.get("fallback_message"), max_length=500),
        },
    }


def _render_knowledge_context(knowledge_base: dict[str, Any]) -> str:
    profile = (
        knowledge_base.get("clinic_profile")
        if isinstance(knowledge_base.get("clinic_profile"), dict)
        else {}
    )
    insurance = knowledge_base.get("insurance") if isinstance(knowledge_base.get("insurance"), dict) else {}
    policies = (
        knowledge_base.get("operational_policies")
        if isinstance(knowledge_base.get("operational_policies"), dict)
        else {}
    )
    playbook = (
        knowledge_base.get("commercial_playbook")
        if isinstance(knowledge_base.get("commercial_playbook"), dict)
        else {}
    )
    escalation = knowledge_base.get("escalation") if isinstance(knowledge_base.get("escalation"), dict) else {}

    lines: list[str] = []

    clinic_name = _compact_text(profile.get("clinic_name"), max_length=120)
    if clinic_name:
        lines.append(f"Clinica: {clinic_name}")

    about = _compact_text(profile.get("about"), max_length=700)
    if about:
        lines.append(f"Sobre a clinica: {about}")

    differentials = _normalize_string_list(profile.get("differentials"), max_items=12, item_max_length=120)
    if differentials:
        lines.append(f"Diferenciais: {'; '.join(differentials)}")

    target_audience = _compact_text(profile.get("target_audience"), max_length=240)
    if target_audience:
        lines.append(f"Publico atendido: {target_audience}")

    tone_preferences = _compact_text(profile.get("tone_preferences"), max_length=240)
    if tone_preferences:
        lines.append(f"Preferencias de tom no atendimento: {tone_preferences}")

    services = _normalize_services(knowledge_base.get("services"))
    if services:
        lines.append("Servicos disponiveis:")
        for service in services:
            details = [service["name"]]
            if service["description"]:
                details.append(f"descricao: {service['description']}")
            if service["duration_note"]:
                details.append(f"duracao: {service['duration_note']}")
            if service["price_note"]:
                details.append(f"preco: {service['price_note']}")
            lines.append(f"- {' | '.join(details)}")

    accepted_plans = _normalize_string_list(insurance.get("accepted_plans"), max_items=20)
    if accepted_plans:
        lines.append(f"Convenios aceitos: {', '.join(accepted_plans)}")
    insurance_notes = _compact_text(insurance.get("notes"), max_length=500)
    if insurance_notes:
        lines.append(f"Observacoes sobre convenios: {insurance_notes}")

    policy_fields = [
        ("Regras de agendamento", policies.get("booking_rules")),
        ("Politica de cancelamento", policies.get("cancellation_policy")),
        ("Politica de reagendamento", policies.get("reschedule_policy")),
        ("Politica de pagamento", policies.get("payment_policy")),
        ("Documentos necessarios", policies.get("documents_required")),
    ]
    for title, field_value in policy_fields:
        text = _compact_text(field_value, max_length=500)
        if text:
            lines.append(f"{title}: {text}")

    faq_items = _normalize_faq(knowledge_base.get("faq"))
    if faq_items:
        lines.append("Perguntas frequentes (FAQ):")
        for item in faq_items:
            question = item.get("question") or "-"
            answer = item.get("answer") or "-"
            lines.append(f"- Pergunta: {question} | Resposta: {answer}")

    value_proposition = _compact_text(playbook.get("value_proposition"), max_length=700)
    if value_proposition:
        lines.append(f"Proposta de valor: {value_proposition}")

    objection_handling = _compact_text(playbook.get("objection_handling"), max_length=700)
    if objection_handling:
        lines.append(f"Tratamento de objecoes: {objection_handling}")

    default_cta = _compact_text(playbook.get("default_cta"), max_length=240)
    if default_cta:
        lines.append(f"CTA padrao: {default_cta}")

    handoff_topics = _normalize_string_list(escalation.get("human_handoff_topics"), max_items=20)
    if handoff_topics:
        lines.append(f"Temas para handoff humano: {', '.join(handoff_topics)}")
    restricted_topics = _normalize_string_list(escalation.get("restricted_topics"), max_items=20)
    if restricted_topics:
        lines.append(f"Temas bloqueados para resposta automatica: {', '.join(restricted_topics)}")
    custom_urgent = _normalize_string_list(escalation.get("custom_urgent_keywords"), max_items=20)
    if custom_urgent:
        lines.append(f"Palavras de urgencia customizadas: {', '.join(custom_urgent)}")
    fallback_message = _compact_text(escalation.get("fallback_message"), max_length=500)
    if fallback_message:
        lines.append(f"Mensagem de fallback: {fallback_message}")

    joined = "\n".join(lines).strip()
    if len(joined) > 5000:
        return f"{joined[:5000].rstrip()}..."
    return joined


def _upsert_setting(db: Session, *, tenant_id: UUID, key: str, value: dict[str, Any], is_secret: bool = False) -> Setting:
    item = db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == key))
    if not item:
        item = Setting(tenant_id=tenant_id, key=key, value=value, is_secret=is_secret)
    else:
        item.value = value
        item.is_secret = is_secret
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def get_global_config(db: Session, *, tenant_id: UUID) -> dict[str, Any]:
    item = db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == "ai_autoresponder.global"))
    return _normalize_config(item.value if item else None)


def set_global_config(db: Session, *, tenant_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
    config = _normalize_config(payload)
    _upsert_setting(db, tenant_id=tenant_id, key="ai_autoresponder.global", value=config)
    return config


def get_unit_override(db: Session, *, tenant_id: UUID, unit_id: UUID) -> dict[str, Any] | None:
    key = f"ai_autoresponder.unit.{unit_id}"
    item = db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == key))
    if not item:
        return None
    if not isinstance(item.value, dict):
        return None
    return item.value


def set_unit_override(db: Session, *, tenant_id: UUID, unit_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
    key = f"ai_autoresponder.unit.{unit_id}"
    _upsert_setting(db, tenant_id=tenant_id, key=key, value=payload)
    return payload


def list_unit_overrides(db: Session, *, tenant_id: UUID) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Setting).where(
            Setting.tenant_id == tenant_id,
            Setting.key.like("ai_autoresponder.unit.%"),
        )
    ).scalars().all()

    output: list[dict[str, Any]] = []
    for row in rows:
        parts = row.key.split(".")
        if len(parts) < 3:
            continue
        unit_id = parts[-1]
        output.append({"unit_id": unit_id, "config": row.value or {}})
    return output


def get_knowledge_base_global_config(db: Session, *, tenant_id: UUID) -> dict[str, Any]:
    item = db.scalar(
        select(Setting).where(
            Setting.tenant_id == tenant_id,
            Setting.key == "ai_knowledge_base.global",
        )
    )
    return _normalize_knowledge_config(item.value if item and isinstance(item.value, dict) else None)


def set_knowledge_base_global_config(
    db: Session,
    *,
    tenant_id: UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    config = _normalize_knowledge_config(payload if isinstance(payload, dict) else {})
    _upsert_setting(
        db,
        tenant_id=tenant_id,
        key="ai_knowledge_base.global",
        value=config,
    )
    return config


def resolve_conversation_config(db: Session, *, conversation: Conversation) -> dict[str, Any]:
    base = get_global_config(db, tenant_id=conversation.tenant_id)
    unit_override = get_unit_override(db, tenant_id=conversation.tenant_id, unit_id=conversation.unit_id) if conversation.unit_id else None
    resolved = _deep_merge(base, unit_override)
    resolved = _normalize_config(resolved)
    if conversation.ai_autoresponder_enabled is not None:
        resolved["enabled"] = bool(conversation.ai_autoresponder_enabled)
    return resolved


def _lookup_pattern(text: str, patterns: list[str]) -> str | None:
    lowered = text.lower()
    for pattern in patterns:
        if pattern in lowered:
            return pattern
    return None


def _is_placeholder_name(value: str | None) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return True
    return text.startswith("contato whatsapp ")


def _normalize_person_name(value: str) -> str:
    lowered_particles = {"da", "de", "do", "dos", "das", "e"}
    normalized_parts: list[str] = []
    for part in value.split():
        raw = part.strip()
        if not raw:
            continue
        if raw.lower() in lowered_particles:
            normalized_parts.append(raw.lower())
            continue
        normalized_parts.append(raw.capitalize())
    return " ".join(normalized_parts).strip()


def _extract_contact_name(text: str) -> str | None:
    lowered = text.lower()
    if "nome" not in lowered and "chamo" not in lowered and not lowered.startswith("sou "):
        return None

    for pattern in CONTACT_NAME_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue

        candidate = match.group(1).strip()
        candidate = re.split(r"[\n\r,.;!?]", candidate, maxsplit=1)[0].strip()
        candidate = re.split(
            r"\b(como|quero|gostaria|preciso|posso|pode|qual|quais|agendar|marcar|servi[cç]os?)\b",
            candidate,
            flags=re.IGNORECASE,
            maxsplit=1,
        )[0].strip()
        candidate = re.sub(r"\s+", " ", candidate).strip(" -:")
        if not candidate:
            continue
        if not re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ' -]{2,80}", candidate):
            continue
        words = [item for item in candidate.split(" ") if item]
        if len(words) > 6:
            continue
        return _normalize_person_name(candidate)

    return None


def _extract_contact_email(text: str) -> str | None:
    match = CONTACT_EMAIL_PATTERN.search(text)
    if not match:
        return None
    return match.group(1).lower().strip()


def _capture_contact_profile_from_inbound(
    db: Session,
    *,
    tenant_id: UUID,
    conversation: Conversation,
    inbound_text: str,
) -> dict[str, str]:
    extracted_name = _extract_contact_name(inbound_text)
    extracted_email = _extract_contact_email(inbound_text)
    if not extracted_name and not extracted_email:
        return {}

    patient = None
    if conversation.patient_id:
        patient = db.scalar(
            select(Patient).where(
                Patient.id == conversation.patient_id,
                Patient.tenant_id == tenant_id,
            )
        )

    lead = None
    if conversation.lead_id:
        lead = db.scalar(
            select(Lead).where(
                Lead.id == conversation.lead_id,
                Lead.tenant_id == tenant_id,
            )
        )

    changes: dict[str, str] = {}
    previous_patient_name = patient.full_name.strip() if patient and patient.full_name else ""

    if patient:
        if extracted_name and _is_placeholder_name(patient.full_name):
            patient.full_name = extracted_name
            changes["patient_full_name"] = extracted_name

        if extracted_email and not (patient.email or "").strip():
            patient.email = extracted_email
            changes["patient_email"] = extracted_email

        if changes:
            db.add(patient)

    if lead:
        if extracted_name and (
            _is_placeholder_name(lead.name)
            or (lead.name or "").strip().lower() == previous_patient_name.lower()
        ):
            lead.name = extracted_name
            changes["lead_name"] = extracted_name

        if extracted_email and not (lead.email or "").strip():
            lead.email = extracted_email
            changes["lead_email"] = extracted_email

        if "lead_name" in changes or "lead_email" in changes:
            db.add(lead)

    if changes:
        tags = set(conversation.tags or [])
        tags.add("dados_cadastrais_capturados")
        conversation.tags = sorted(tags)
        db.add(conversation)

        logger.info(
            "ai_autoresponder.contact_profile_captured",
            tenant_id=str(tenant_id),
            conversation_id=str(conversation.id),
            fields=list(changes.keys()),
        )

    return changes


def _parse_hhmm(value: str) -> tuple[int, int]:
    parts = value.split(":")
    if len(parts) != 2:
        return 8, 0
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
    except ValueError:
        return 8, 0
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        return 8, 0
    return hours, minutes


def _is_business_hours(config: dict[str, Any], *, now_utc: datetime | None = None) -> bool:
    now_utc = now_utc or datetime.now(UTC)
    business_hours = config.get("business_hours") or {}
    timezone_name = business_hours.get("timezone") or settings.app_timezone
    try:
        local_now = now_utc.astimezone(ZoneInfo(str(timezone_name)))
    except ZoneInfoNotFoundError:
        local_now = now_utc

    weekdays = business_hours.get("weekdays") or [0, 1, 2, 3, 4]
    if local_now.weekday() not in weekdays:
        return False

    start_h, start_m = _parse_hhmm(str(business_hours.get("start") or "08:00"))
    end_h, end_m = _parse_hhmm(str(business_hours.get("end") or "18:00"))
    start_total = start_h * 60 + start_m
    end_total = end_h * 60 + end_m
    current_total = local_now.hour * 60 + local_now.minute

    if end_total <= start_total:
        return current_total >= start_total or current_total <= end_total
    return start_total <= current_total <= end_total


def _parse_json_output(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return {}


def _conversation_destination_phone(db: Session, *, conversation: Conversation) -> str | None:
    if conversation.patient_id:
        patient = db.scalar(
            select(Patient).where(
                Patient.id == conversation.patient_id,
                Patient.tenant_id == conversation.tenant_id,
            )
        )
        if patient and patient.phone:
            return patient.phone

    if conversation.lead_id:
        lead = db.scalar(
            select(Lead).where(
                Lead.id == conversation.lead_id,
                Lead.tenant_id == conversation.tenant_id,
            )
        )
        if lead and lead.phone:
            return lead.phone

    return None


def _normalize_for_match(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    stripped = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return stripped.lower().strip()


def _detect_period_preference(text: str) -> str | None:
    lowered = _normalize_for_match(text)
    if any(keyword in lowered for keyword in PERIOD_MORNING_KEYWORDS):
        return "morning"
    if any(keyword in lowered for keyword in PERIOD_AFTERNOON_KEYWORDS):
        return "afternoon"
    if any(keyword in lowered for keyword in PERIOD_EVENING_KEYWORDS):
        return "evening"
    return None


def _extract_requested_date_from_text(*, text: str, timezone: ZoneInfo) -> date | None:
    normalized = _normalize_for_match(text)
    now_local = datetime.now(UTC).astimezone(timezone).date()

    slash_match = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", normalized)
    if slash_match:
        day = int(slash_match.group(1))
        month = int(slash_match.group(2))
        year_raw = slash_match.group(3)
        year = now_local.year
        if year_raw:
            year = int(year_raw)
            if year < 100:
                year += 2000
        try:
            candidate = date(year, month, day)
        except ValueError:
            candidate = None
        if candidate:
            return candidate

    day_match = re.search(r"\bdia\s+(\d{1,2})\b", normalized)
    if not day_match:
        return None

    day = int(day_match.group(1))
    if day < 1 or day > 31:
        return None

    month = now_local.month
    year = now_local.year
    try:
        candidate = date(year, month, day)
    except ValueError:
        return None

    if candidate < now_local:
        if month == 12:
            month = 1
            year += 1
        else:
            month += 1
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
    return candidate


def _is_scheduling_context(*, inbound_text: str, context: str) -> bool:
    inbound_normalized = _normalize_for_match(inbound_text)
    context_normalized = _normalize_for_match(context)
    if any(keyword in inbound_normalized for keyword in SCHEDULING_INTENT_KEYWORDS):
        return True
    if any(keyword in inbound_normalized for keyword in AVAILABILITY_REQUEST_KEYWORDS):
        return True
    if any(keyword in context_normalized for keyword in SCHEDULING_INTENT_KEYWORDS):
        if len(inbound_normalized.split()) <= 4:
            return True
    if any(keyword in context_normalized for keyword in AVAILABILITY_REQUEST_KEYWORDS):
        if len(inbound_normalized.split()) <= 4:
            return True
    return False


def _is_explicit_availability_request(text: str) -> bool:
    normalized = _normalize_for_match(text)
    return any(keyword in normalized for keyword in AVAILABILITY_REQUEST_KEYWORDS)


def _is_followup_availability_request(*, inbound_text: str, context: str) -> bool:
    normalized_inbound = _normalize_for_match(inbound_text)
    has_followup_keyword = any(keyword in normalized_inbound for keyword in FOLLOWUP_AVAILABILITY_KEYWORDS)
    if has_followup_keyword:
        normalized_context = _normalize_for_match(context)
        context_has_recent_slots = (
            "encontrei estes horarios" in normalized_context
            or "numero da opcao" in normalized_context
            or "número da opção" in context.lower()
            or ("1)" in context and "horario" in normalized_context)
        )
        if context_has_recent_slots:
            return True
    if not _is_scheduling_context(inbound_text=inbound_text, context=context):
        return False
    # Respostas curtas de confirmação após oferta de agenda.
    return normalized_inbound in {"sim", "pode", "ok", "certo", "isso", "pode sim"}


def _extract_option_index_choice(text: str) -> int | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"\d{1,2}", raw):
        return int(raw)

    normalized = _normalize_for_match(raw)
    match = re.search(r"\b(?:opcao|opção|slot|op)\s*[_-]?\s*(\d{1,2})\b", normalized)
    if not match:
        return None
    return int(match.group(1))


def _extract_option_index_from_inbound_payload(payload: dict[str, Any] | None) -> int | None:
    if not isinstance(payload, dict):
        return None

    interactive_reply = payload.get("interactive_reply") if isinstance(payload.get("interactive_reply"), dict) else {}
    candidates = [
        interactive_reply.get("id"),
        interactive_reply.get("title"),
        (payload.get("message") or {}).get("id") if isinstance(payload.get("message"), dict) else None,
        (payload.get("message") or {}).get("title") if isinstance(payload.get("message"), dict) else None,
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        parsed = _extract_option_index_choice(str(candidate))
        if parsed is not None:
            return parsed
    return None


def _extract_time_choice(text: str) -> str | None:
    match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", text or "")
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        return f"{hour:02d}:{minute:02d}"

    loose_hour_match = re.search(r"\b(?:as|às)\s*([01]?\d|2[0-3])\b", _normalize_for_match(text or ""))
    if not loose_hour_match:
        return None
    hour = int(loose_hour_match.group(1))
    return f"{hour:02d}:00"


def _extract_time_mentions(text: str) -> list[str]:
    values: list[str] = []
    for match in re.finditer(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", text or ""):
        hour = int(match.group(1))
        minute = int(match.group(2))
        token = f"{hour:02d}:{minute:02d}"
        if token not in values:
            values.append(token)
    return values


def _is_booking_confirmation_message(text: str) -> bool:
    normalized = _normalize_for_match(text)
    return any(keyword in normalized for keyword in BOOKING_CONFIRMATION_KEYWORDS)


def _format_slots_options_message(
    *,
    slots: list[dict[str, Any]],
    period: str | None = None,
    procedure_type: str | None = None,
) -> str:
    period_label_map = {
        "morning": "manhã",
        "afternoon": "tarde",
        "evening": "noite",
    }
    period_label = period_label_map.get(period or "", "")
    if period_label and procedure_type:
        header = f"Encontrei estes horários para {period_label} ({procedure_type}):"
    elif period_label:
        header = f"Encontrei estes horários para {period_label}:"
    elif procedure_type:
        header = f"Encontrei estes horários disponíveis para {procedure_type}:"
    else:
        header = "Encontrei estes horários disponíveis:"

    lines = [header]
    for idx, slot in enumerate(slots, start=1):
        option = f"{idx}) {slot['label']}"
        professional_name = str(slot.get("professional_name") or "").strip()
        if professional_name and _normalize_for_match(professional_name) != "equipe clinica":
            option = f"{option} — {professional_name}"
        lines.append(option)
    lines.append("Se preferir, me diga o número da opção para eu seguir com a confirmação.")
    return "\n".join(lines)


def _build_scheduling_interactive_list_payload(scheduling_response: dict[str, Any]) -> dict[str, Any] | None:
    mode = str(scheduling_response.get("mode") or "").strip()
    metadata = scheduling_response.get("metadata") if isinstance(scheduling_response.get("metadata"), dict) else {}

    if mode.startswith("booking_wizard_"):
        rows_raw = metadata.get("rows")
        if not isinstance(rows_raw, list):
            return None
        rows: list[dict[str, str]] = []
        for row in rows_raw[:10]:
            if not isinstance(row, dict):
                continue
            row_id = str(row.get("id") or "").strip()[:200]
            row_title = str(row.get("title") or "").strip()[:24]
            row_description = str(row.get("description") or "").strip()[:72]
            if not row_id or not row_title:
                continue
            item = {"id": row_id, "title": row_title}
            if row_description:
                item["description"] = row_description
            rows.append(item)
        if not rows:
            return None
        return {
            "button_title": str(metadata.get("button_title") or "Opções"),
            "section_title": str(metadata.get("section_title") or "Escolha uma opção"),
            "header_text": str(metadata.get("header_text") or "Agendamento"),
            "body_text": str(
                metadata.get("body_text")
                or scheduling_response.get("response_text")
                or "Selecione uma opção para continuar."
            ),
            "footer_text": str(metadata.get("footer_text") or "Use os botões para continuar."),
            "rows": rows,
        }

    if mode not in {"slots_suggested", "no_slots_for_period_with_alternatives"}:
        return None

    slots_raw = metadata.get("slots")
    if not isinstance(slots_raw, list):
        return None

    slots = [str(item).strip() for item in slots_raw if str(item or "").strip()]
    if not slots:
        return None

    procedure = str(metadata.get("procedure_type") or "atendimento").strip()
    rows: list[dict[str, str]] = []
    for index, slot_label in enumerate(slots[:10], start=1):
        rows.append(
            {
                "id": f"slot_{index}",
                "title": f"Opção {index}",
                "description": slot_label[:72],
            }
        )

    if not rows:
        return None

    return {
        "button_title": "Opções",
        "section_title": "Horários disponíveis",
        "header_text": "Escolha um horário",
        "body_text": f"Selecione uma opção para confirmar seu agendamento de {procedure}.",
        "footer_text": "Você também pode digitar o número da opção.",
        "rows": rows,
    }


def _parse_iso_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _latest_ai_wizard_message(db: Session, *, conversation: Conversation) -> Message | None:
    for message in _recent_ai_outbound_messages(db, conversation=conversation, limit=30):
        payload = message.payload if isinstance(message.payload, dict) else {}
        mode = str(payload.get("mode") or "").strip()
        if mode.startswith("booking_wizard_"):
            return message
    return None


def _extract_wizard_selection_token(*, inbound_message: Message, inbound_text: str) -> str:
    payload = inbound_message.payload if isinstance(inbound_message.payload, dict) else {}
    interactive_reply = payload.get("interactive_reply") if isinstance(payload.get("interactive_reply"), dict) else {}
    for key in ("id", "title", "description"):
        value = str(interactive_reply.get(key) or "").strip()
        if value:
            return value
    return str(inbound_text or "").strip()


def _wizard_choice_index_from_token(token: str, *, prefix: str) -> int | None:
    raw = str(token or "").strip()
    if not raw:
        return None
    normalized = _normalize_for_match(raw)
    match = re.search(rf"\b{re.escape(prefix)}[_-]?(\d{{1,2}})\b", normalized)
    if match:
        return int(match.group(1))
    return _extract_option_index_choice(raw)


def _wizard_has_explicit_service_inbound(text: str) -> bool:
    normalized = _normalize_for_match(text)
    keywords = (
        "limpeza",
        "profilax",
        "clareamento",
        "lente",
        "implante",
        "ortodont",
        "avaliacao",
        "avaliação",
        "reabilit",
        "raspagem",
    )
    return any(keyword in normalized for keyword in keywords)


def _wizard_active_units(db: Session, *, tenant_id: UUID) -> list[Unit]:
    return db.execute(
        select(Unit)
        .where(
            Unit.tenant_id == tenant_id,
            Unit.is_active.is_(True),
        )
        .order_by(Unit.created_at.asc())
    ).scalars().all()


def _wizard_service_options(
    db: Session,
    *,
    tenant_id: UUID,
    preferred_unit_id: UUID | None = None,
) -> list[str]:
    stmt = select(Professional).where(
        Professional.tenant_id == tenant_id,
        Professional.is_active.is_(True),
    )
    if preferred_unit_id:
        stmt = stmt.where(Professional.unit_id == preferred_unit_id)
    professionals = db.execute(stmt).scalars().all()

    seen: set[str] = set()
    options: list[str] = []
    for professional in professionals:
        for procedure in professional.procedures or []:
            if not isinstance(procedure, str):
                continue
            label = re.sub(r"\s+", " ", procedure.strip())
            if len(label) < 3:
                continue
            normalized = _normalize_for_match(label)
            if normalized in seen:
                continue
            seen.add(normalized)
            options.append(label)

    if not options:
        options = list(BOOKING_WIZARD_DEFAULT_SERVICES)

    for default_label in BOOKING_WIZARD_DEFAULT_SERVICES:
        normalized = _normalize_for_match(default_label)
        if normalized in seen:
            continue
        seen.add(normalized)
        options.append(default_label)

    return options[:10]


def _wizard_build_service_step_response(
    db: Session,
    *,
    conversation: Conversation,
    intro_text: str | None,
    period: str | None,
    requested_date: date | None,
    preferred_service: str | None = None,
) -> dict[str, Any]:
    services = _wizard_service_options(
        db,
        tenant_id=conversation.tenant_id,
        preferred_unit_id=conversation.unit_id,
    )
    preferred_normalized = _normalize_for_match(preferred_service or "")
    if preferred_normalized:
        for index, service in enumerate(services):
            if _normalize_for_match(service) == preferred_normalized:
                if index > 0:
                    services.insert(0, services.pop(index))
                break

    rows: list[dict[str, str]] = []
    for index, service in enumerate(services, start=1):
        rows.append(
            {
                "id": f"svc_{index}",
                "title": f"Opção {index}",
                "description": service[:72],
            }
        )

    return {
        "mode": "booking_wizard_service_select",
        "response_text": (
            intro_text
            or "Para agendar com botões, escolha primeiro o serviço desejado."
        ),
        "metadata": {
            "wizard_step": "service",
            "services": services,
            "period": period,
            "requested_date": requested_date.isoformat() if requested_date else None,
            "rows": rows,
            "button_title": "Serviços",
            "section_title": "Escolha o serviço",
            "header_text": "Agendamento",
            "body_text": "Selecione o serviço para continuar.",
            "footer_text": "Depois eu mostro clínica, dia e horário.",
        },
    }


def _wizard_build_unit_step_response(
    db: Session,
    *,
    conversation: Conversation,
    procedure_type: str,
    period: str | None,
    requested_date: date | None,
) -> dict[str, Any]:
    units = _wizard_active_units(db, tenant_id=conversation.tenant_id)
    if not units:
        return {
            "mode": "no_unit_available",
            "response_text": (
                "No momento não consegui acessar a agenda da unidade. "
                "Vou encaminhar para o atendimento humano confirmar seu horário."
            ),
            "metadata": {"reason": "no_unit_available"},
        }

    unit_choices: list[dict[str, str]] = []
    rows: list[dict[str, str]] = []
    for index, unit in enumerate(units, start=1):
        option_id = f"unit_{index}"
        unit_choices.append({"id": str(unit.id), "name": unit.name, "option_id": option_id})
        rows.append(
            {
                "id": option_id,
                "title": f"Opção {index}",
                "description": unit.name[:72],
            }
        )

    return {
        "mode": "booking_wizard_unit_select",
        "response_text": f"Perfeito. Agora escolha a clínica/unidade para {procedure_type}.",
        "metadata": {
            "wizard_step": "unit",
            "procedure_type": procedure_type,
            "period": period,
            "requested_date": requested_date.isoformat() if requested_date else None,
            "units": unit_choices,
            "rows": rows,
            "button_title": "Clínicas",
            "section_title": "Escolha a clínica",
            "header_text": "Agendamento",
            "body_text": "Selecione a clínica para seguir.",
            "footer_text": "Em seguida escolhemos dia e horário.",
        },
    }


def _wizard_collect_day_choices(
    db: Session,
    *,
    conversation: Conversation,
    unit_id: UUID,
    procedure_type: str,
    period: str | None,
    requested_date: date | None,
    operation_timezone: ZoneInfo,
    config: dict[str, Any],
) -> list[dict[str, str]]:
    now_local_date = datetime.now(UTC).astimezone(operation_timezone).date()
    candidates: list[date] = []
    if requested_date and requested_date >= now_local_date:
        candidates.append(requested_date)

    for offset in range(0, 14):
        candidate = now_local_date + timedelta(days=offset)
        if candidate not in candidates:
            candidates.append(candidate)

    day_choices: list[dict[str, str]] = []
    for candidate in candidates:
        slots = _list_available_slots(
            db,
            tenant_id=conversation.tenant_id,
            unit_id=unit_id,
            config=config,
            procedure_type=procedure_type,
            period=period,
            requested_date=candidate,
            max_slots=1,
        )
        if not slots:
            continue
        first_slot = slots[0]
        day_choices.append(
            {
                "id": f"day_{candidate.isoformat()}",
                "date": candidate.isoformat(),
                "label": f"{_weekday_label_pt(candidate.weekday())}, {candidate.strftime('%d/%m')}",
                "description": f"A partir de {first_slot['starts_at_local'].strftime('%H:%M')}",
            }
        )
        if len(day_choices) >= 7:
            break
    return day_choices


def _wizard_build_day_step_response(
    db: Session,
    *,
    conversation: Conversation,
    unit: Unit,
    procedure_type: str,
    period: str | None,
    requested_date: date | None,
    operation_timezone: ZoneInfo,
    config: dict[str, Any],
) -> dict[str, Any]:
    day_choices = _wizard_collect_day_choices(
        db,
        conversation=conversation,
        unit_id=unit.id,
        procedure_type=procedure_type,
        period=period,
        requested_date=requested_date,
        operation_timezone=operation_timezone,
        config=config,
    )
    if not day_choices:
        return {
            "mode": "no_slots_general",
            "response_text": (
                "No momento não encontrei dias com horários disponíveis para este serviço. "
                "Posso te direcionar para atendimento humano."
            ),
            "metadata": {
                "reason": "no_slots_general",
                "procedure_type": procedure_type,
                "unit_id": str(unit.id),
            },
        }

    rows: list[dict[str, str]] = []
    for index, day_choice in enumerate(day_choices, start=1):
        rows.append(
            {
                "id": day_choice["id"],
                "title": f"Opção {index}",
                "description": day_choice["label"][:72],
            }
        )

    return {
        "mode": "booking_wizard_day_select",
        "response_text": f"Ótimo. Escolha o dia para {procedure_type} na {unit.name}.",
        "metadata": {
            "wizard_step": "day",
            "procedure_type": procedure_type,
            "unit_id": str(unit.id),
            "unit_name": unit.name,
            "period": period,
            "requested_date": requested_date.isoformat() if requested_date else None,
            "day_choices": day_choices,
            "rows": rows,
            "button_title": "Dias",
            "section_title": "Escolha o dia",
            "header_text": "Agendamento",
            "body_text": "Selecione o dia desejado.",
            "footer_text": "Depois você escolhe o horário.",
        },
    }


def _wizard_collect_time_choices(
    db: Session,
    *,
    conversation: Conversation,
    unit: Unit,
    procedure_type: str,
    period: str | None,
    selected_date: date,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    slots = _list_available_slots(
        db,
        tenant_id=conversation.tenant_id,
        unit_id=unit.id,
        config=config,
        procedure_type=procedure_type,
        period=period,
        requested_date=selected_date,
        max_slots=10,
    )
    choices: list[dict[str, Any]] = []
    for index, slot in enumerate(slots, start=1):
        choices.append(
            {
                "id": f"time_{index}",
                "label": slot["label"],
                "starts_at_utc": slot["starts_at_utc"].isoformat(),
                "ends_at_utc": slot["ends_at_utc"].isoformat(),
                "starts_at_local": slot["starts_at_local"].isoformat(),
                "professional_id": (
                    str(slot.get("professional_id"))
                    if slot.get("professional_id")
                    else None
                ),
                "professional_name": slot.get("professional_name"),
                "time": slot["starts_at_local"].strftime("%H:%M"),
            }
        )
    return choices


def _wizard_slot_from_choice(choice: dict[str, Any]) -> dict[str, Any] | None:
    starts_at_utc_raw = choice.get("starts_at_utc")
    ends_at_utc_raw = choice.get("ends_at_utc")
    starts_at_local_raw = choice.get("starts_at_local")
    if not isinstance(starts_at_utc_raw, str) or not isinstance(ends_at_utc_raw, str) or not isinstance(starts_at_local_raw, str):
        return None

    try:
        starts_at_utc = datetime.fromisoformat(starts_at_utc_raw)
        ends_at_utc = datetime.fromisoformat(ends_at_utc_raw)
        starts_at_local = datetime.fromisoformat(starts_at_local_raw)
    except ValueError:
        return None

    if starts_at_utc.tzinfo is None:
        starts_at_utc = starts_at_utc.replace(tzinfo=UTC)
    if ends_at_utc.tzinfo is None:
        ends_at_utc = ends_at_utc.replace(tzinfo=UTC)

    return {
        "starts_at_utc": starts_at_utc,
        "ends_at_utc": ends_at_utc,
        "starts_at_local": starts_at_local,
        "label": str(choice.get("label") or ""),
        "professional_id": choice.get("professional_id"),
        "professional_name": choice.get("professional_name"),
    }


def _wizard_build_time_step_response(
    db: Session,
    *,
    conversation: Conversation,
    unit: Unit,
    procedure_type: str,
    period: str | None,
    selected_date: date,
    config: dict[str, Any],
) -> dict[str, Any]:
    slot_choices = _wizard_collect_time_choices(
        db,
        conversation=conversation,
        unit=unit,
        procedure_type=procedure_type,
        period=period,
        selected_date=selected_date,
        config=config,
    )
    if not slot_choices:
        return {
            "mode": "no_slots_general",
            "response_text": (
                f"No momento não encontrei horários disponíveis para {selected_date.strftime('%d/%m')}. "
                "Posso verificar outro dia para você."
            ),
            "metadata": {
                "reason": "no_slots_general",
                "requested_date": selected_date.isoformat(),
                "procedure_type": procedure_type,
                "unit_id": str(unit.id),
            },
        }

    rows: list[dict[str, str]] = []
    for index, choice in enumerate(slot_choices, start=1):
        rows.append(
            {
                "id": str(choice.get("id") or f"time_{index}"),
                "title": f"Opção {index}",
                "description": str(choice.get("label") or "")[:72],
            }
        )

    return {
        "mode": "booking_wizard_time_select",
        "response_text": f"Perfeito. Escolha o horário para {selected_date.strftime('%d/%m')}.",
        "metadata": {
            "wizard_step": "time",
            "procedure_type": procedure_type,
            "unit_id": str(unit.id),
            "unit_name": unit.name,
            "period": period,
            "requested_date": selected_date.isoformat(),
            "slot_choices": slot_choices,
            "rows": rows,
            "button_title": "Horários",
            "section_title": "Escolha o horário",
            "header_text": "Agendamento",
            "body_text": "Selecione o horário desejado.",
            "footer_text": "No próximo passo você confirma.",
        },
    }


def _wizard_build_confirm_step_response(
    *,
    procedure_type: str,
    unit: Unit,
    selected_date: date,
    period: str | None,
    selected_slot_choice: dict[str, Any],
) -> dict[str, Any]:
    slot_label = str(selected_slot_choice.get("label") or "")
    rows = [
        {"id": "confirm_yes", "title": "Confirmar", "description": "Agendar este horário"},
        {"id": "confirm_no", "title": "Trocar horário", "description": "Voltar para horários"},
    ]
    return {
        "mode": "booking_wizard_confirm",
        "response_text": (
            "Confirma este agendamento?\n"
            f"• Serviço: {procedure_type}\n"
            f"• Unidade: {unit.name}\n"
            f"• Horário: {slot_label}"
        ),
        "metadata": {
            "wizard_step": "confirm",
            "procedure_type": procedure_type,
            "unit_id": str(unit.id),
            "unit_name": unit.name,
            "period": period,
            "requested_date": selected_date.isoformat(),
            "selected_slot": selected_slot_choice,
            "rows": rows,
            "button_title": "Confirmar",
            "section_title": "Confirmar agendamento",
            "header_text": "Confirmação",
            "body_text": "Confirme ou troque o horário.",
            "footer_text": "Escolha uma opção.",
        },
    }


def _wizard_parse_confirmation_choice(token: str) -> bool | None:
    normalized = _normalize_for_match(token or "")
    if any(keyword in normalized for keyword in BOOKING_WIZARD_CONFIRM_YES_KEYWORDS):
        return True
    if any(keyword in normalized for keyword in BOOKING_WIZARD_CONFIRM_NO_KEYWORDS):
        return False
    return None


def _wizard_select_service(token: str, services: list[str]) -> str | None:
    if not services:
        return None
    index = _wizard_choice_index_from_token(token, prefix="svc")
    if index is not None and 1 <= index <= len(services):
        return services[index - 1]

    normalized = _normalize_for_match(token)
    if not normalized:
        return None
    for service in services:
        service_norm = _normalize_for_match(service)
        if normalized == service_norm or normalized in service_norm:
            return service
    return None


def _wizard_select_unit(token: str, units: list[dict[str, str]]) -> dict[str, str] | None:
    if not units:
        return None
    index = _wizard_choice_index_from_token(token, prefix="unit")
    if index is not None and 1 <= index <= len(units):
        return units[index - 1]

    normalized = _normalize_for_match(token)
    if not normalized:
        return None
    for unit in units:
        option_id = _normalize_for_match(str(unit.get("option_id") or ""))
        unit_name = _normalize_for_match(str(unit.get("name") or ""))
        unit_id = _normalize_for_match(str(unit.get("id") or ""))
        if normalized in {option_id, unit_id}:
            return unit
        if unit_name and (normalized == unit_name or normalized in unit_name):
            return unit
    return None


def _wizard_select_day(
    token: str,
    day_choices: list[dict[str, str]],
    *,
    operation_timezone: ZoneInfo,
) -> date | None:
    if not day_choices:
        return None
    index = _wizard_choice_index_from_token(token, prefix="day")
    if index is not None and 1 <= index <= len(day_choices):
        return _parse_iso_date(day_choices[index - 1].get("date"))

    normalized = _normalize_for_match(token)
    direct_match = re.search(r"\bday[_-](\d{4}-\d{2}-\d{2})\b", normalized)
    if direct_match:
        return _parse_iso_date(direct_match.group(1))

    date_from_text = _extract_requested_date_from_text(text=token, timezone=operation_timezone)
    if date_from_text:
        return date_from_text
    return None


def _wizard_select_time_choice(token: str, slot_choices: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not slot_choices:
        return None

    index = _wizard_choice_index_from_token(token, prefix="time")
    if index is None:
        index = _extract_option_index_choice(token)
    if index is not None and 1 <= index <= len(slot_choices):
        return slot_choices[index - 1]

    explicit_time = _extract_time_choice(token)
    if explicit_time:
        for choice in slot_choices:
            if str(choice.get("time") or "") == explicit_time:
                return choice

    normalized = _normalize_for_match(token)
    for choice in slot_choices:
        option_id = _normalize_for_match(str(choice.get("id") or ""))
        label = _normalize_for_match(str(choice.get("label") or ""))
        if normalized in {option_id, label}:
            return choice
    return None


def _try_booking_wizard_response(
    db: Session,
    *,
    conversation: Conversation,
    inbound_message: Message,
    inbound_text: str,
    context: str,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    operation_timezone = _resolve_operation_timezone(config)
    inbound_payload = inbound_message.payload if isinstance(inbound_message.payload, dict) else {}
    has_interactive_reply = isinstance(inbound_payload.get("interactive_reply"), dict)
    selection_token = _extract_wizard_selection_token(
        inbound_message=inbound_message,
        inbound_text=inbound_text,
    )
    normalized_inbound = _normalize_for_match(inbound_text)
    period = _detect_period_preference(inbound_text)
    requested_date = _extract_requested_date_from_text(text=inbound_text, timezone=operation_timezone)
    has_scheduling_keywords = any(keyword in normalized_inbound for keyword in (*SCHEDULING_INTENT_KEYWORDS, *AVAILABILITY_REQUEST_KEYWORDS))
    force_wizard = any(keyword in normalized_inbound for keyword in BOOKING_WIZARD_FORCE_KEYWORDS)
    selection_like = (
        _extract_option_index_choice(inbound_text) is not None
        or _extract_time_choice(inbound_text) is not None
        or bool(re.search(r"\b(?:svc|unit|day|time|confirm)[_-]", _normalize_for_match(selection_token)))
    )

    latest_wizard = _latest_ai_wizard_message(db, conversation=conversation)
    if latest_wizard:
        if not (
            has_interactive_reply
            or selection_like
            or has_scheduling_keywords
            or _is_booking_confirmation_message(inbound_text)
            or force_wizard
        ):
            return None

        if _has_intervening_new_scheduling_request(
            db,
            conversation=conversation,
            anchor_message=latest_wizard,
            current_inbound_message=inbound_message,
            operation_timezone=operation_timezone,
        ):
            return _wizard_build_service_step_response(
                db,
                conversation=conversation,
                intro_text="Vamos reiniciar para evitar erro. Escolha o serviço:",
                period=period,
                requested_date=requested_date,
            )

        latest_payload = latest_wizard.payload if isinstance(latest_wizard.payload, dict) else {}
        latest_mode = str(latest_payload.get("mode") or "").strip()
        latest_scheduling = latest_payload.get("scheduling") if isinstance(latest_payload.get("scheduling"), dict) else {}
        carried_period_raw = str(latest_scheduling.get("period") or "").strip().lower()
        carried_period = period or (carried_period_raw if carried_period_raw in {"morning", "afternoon", "evening"} else None)
        carried_requested_date = requested_date or _parse_iso_date(latest_scheduling.get("requested_date"))

        if latest_mode == "booking_wizard_service_select":
            services = latest_scheduling.get("services") if isinstance(latest_scheduling.get("services"), list) else []
            services = [str(item).strip() for item in services if str(item or "").strip()]
            selected_service = _wizard_select_service(selection_token, services)
            if not selected_service:
                return _wizard_build_service_step_response(
                    db,
                    conversation=conversation,
                    intro_text="Não entendi a opção de serviço. Escolha um item da lista:",
                    period=carried_period,
                    requested_date=carried_requested_date,
                )
            return _wizard_build_unit_step_response(
                db,
                conversation=conversation,
                procedure_type=selected_service,
                period=carried_period,
                requested_date=carried_requested_date,
            )

        if latest_mode == "booking_wizard_unit_select":
            units_meta = latest_scheduling.get("units") if isinstance(latest_scheduling.get("units"), list) else []
            selected_unit_meta = _wizard_select_unit(selection_token, units_meta)
            if not selected_unit_meta:
                selected_service = str(latest_scheduling.get("procedure_type") or "").strip() or _infer_procedure_type(
                    inbound_text=inbound_text,
                    context=context,
                )
                return _wizard_build_unit_step_response(
                    db,
                    conversation=conversation,
                    procedure_type=selected_service,
                    period=carried_period,
                    requested_date=carried_requested_date,
                )

            selected_unit_id_raw = selected_unit_meta.get("id")
            selected_unit_id = UUID(selected_unit_id_raw) if isinstance(selected_unit_id_raw, str) else None
            unit = db.scalar(
                select(Unit).where(
                    Unit.id == selected_unit_id,
                    Unit.tenant_id == conversation.tenant_id,
                    Unit.is_active.is_(True),
                )
            ) if selected_unit_id else None
            if not unit:
                return {
                    "mode": "no_unit_available",
                    "response_text": "Não consegui acessar essa clínica agora. Pode escolher outra opção?",
                    "metadata": {"reason": "no_unit_available"},
                }

            selected_service = str(latest_scheduling.get("procedure_type") or "").strip() or "Avaliação odontológica"
            return _wizard_build_day_step_response(
                db,
                conversation=conversation,
                unit=unit,
                procedure_type=selected_service,
                period=carried_period,
                requested_date=carried_requested_date,
                operation_timezone=operation_timezone,
                config=config,
            )

        if latest_mode == "booking_wizard_day_select":
            selected_service = str(latest_scheduling.get("procedure_type") or "").strip() or "Avaliação odontológica"
            unit_id_raw = latest_scheduling.get("unit_id")
            try:
                unit_id = UUID(str(unit_id_raw)) if unit_id_raw else None
            except (TypeError, ValueError):
                unit_id = None
            unit = db.scalar(
                select(Unit).where(
                    Unit.id == unit_id,
                    Unit.tenant_id == conversation.tenant_id,
                    Unit.is_active.is_(True),
                )
            )
            if not unit:
                return {
                    "mode": "no_unit_available",
                    "response_text": "Não consegui acessar essa clínica agora. Pode escolher outra opção?",
                    "metadata": {"reason": "no_unit_available"},
                }

            day_choices = latest_scheduling.get("day_choices") if isinstance(latest_scheduling.get("day_choices"), list) else []
            selected_day = _wizard_select_day(
                selection_token,
                day_choices,
                operation_timezone=operation_timezone,
            )
            if not selected_day:
                return _wizard_build_day_step_response(
                    db,
                    conversation=conversation,
                    unit=unit,
                    procedure_type=selected_service,
                    period=carried_period,
                    requested_date=carried_requested_date,
                    operation_timezone=operation_timezone,
                    config=config,
                )

            return _wizard_build_time_step_response(
                db,
                conversation=conversation,
                unit=unit,
                procedure_type=selected_service,
                period=carried_period,
                selected_date=selected_day,
                config=config,
            )

        if latest_mode == "booking_wizard_time_select":
            selected_service = str(latest_scheduling.get("procedure_type") or "").strip() or "Avaliação odontológica"
            unit_id_raw = latest_scheduling.get("unit_id")
            try:
                unit_id = UUID(str(unit_id_raw)) if unit_id_raw else None
            except (TypeError, ValueError):
                unit_id = None
            unit = db.scalar(
                select(Unit).where(
                    Unit.id == unit_id,
                    Unit.tenant_id == conversation.tenant_id,
                    Unit.is_active.is_(True),
                )
            )
            if not unit:
                return {
                    "mode": "no_unit_available",
                    "response_text": "Não consegui acessar essa clínica agora. Pode escolher outra opção?",
                    "metadata": {"reason": "no_unit_available"},
                }

            selected_day = _parse_iso_date(latest_scheduling.get("requested_date")) or requested_date
            if not selected_day:
                return _wizard_build_day_step_response(
                    db,
                    conversation=conversation,
                    unit=unit,
                    procedure_type=selected_service,
                    period=carried_period,
                    requested_date=carried_requested_date,
                    operation_timezone=operation_timezone,
                    config=config,
                )

            slot_choices = latest_scheduling.get("slot_choices") if isinstance(latest_scheduling.get("slot_choices"), list) else []
            selected_choice = _wizard_select_time_choice(selection_token, slot_choices)
            if not selected_choice:
                return _wizard_build_time_step_response(
                    db,
                    conversation=conversation,
                    unit=unit,
                    procedure_type=selected_service,
                    period=carried_period,
                    selected_date=selected_day,
                    config=config,
                )

            return _wizard_build_confirm_step_response(
                procedure_type=selected_service,
                unit=unit,
                selected_date=selected_day,
                period=carried_period,
                selected_slot_choice=selected_choice,
            )

        if latest_mode == "booking_wizard_confirm":
            confirmation_choice = _wizard_parse_confirmation_choice(selection_token)
            selected_service = str(latest_scheduling.get("procedure_type") or "").strip() or "Avaliação odontológica"
            unit_id_raw = latest_scheduling.get("unit_id")
            try:
                unit_id = UUID(str(unit_id_raw)) if unit_id_raw else None
            except (TypeError, ValueError):
                unit_id = None
            unit = db.scalar(
                select(Unit).where(
                    Unit.id == unit_id,
                    Unit.tenant_id == conversation.tenant_id,
                    Unit.is_active.is_(True),
                )
            )
            selected_day = _parse_iso_date(latest_scheduling.get("requested_date"))
            selected_slot_choice = latest_scheduling.get("selected_slot") if isinstance(latest_scheduling.get("selected_slot"), dict) else None

            if not unit or not selected_day or not selected_slot_choice:
                return _wizard_build_service_step_response(
                    db,
                    conversation=conversation,
                    intro_text="Vamos reiniciar o agendamento. Escolha o serviço:",
                    period=carried_period,
                    requested_date=carried_requested_date,
                )

            if confirmation_choice is True:
                selected_slot = _wizard_slot_from_choice(selected_slot_choice)
                if not selected_slot:
                    return _wizard_build_time_step_response(
                        db,
                        conversation=conversation,
                        unit=unit,
                        procedure_type=selected_service,
                        period=carried_period,
                        selected_date=selected_day,
                        config=config,
                    )
                return _appointment_response_from_selected_slot(
                    db,
                    conversation=conversation,
                    unit=unit,
                    selected_slot=selected_slot,
                    procedure_type=selected_service,
                    period=carried_period,
                    requested_date=selected_day,
                )

            if confirmation_choice is False:
                return _wizard_build_time_step_response(
                    db,
                    conversation=conversation,
                    unit=unit,
                    procedure_type=selected_service,
                    period=carried_period,
                    selected_date=selected_day,
                    config=config,
                )

            return _wizard_build_confirm_step_response(
                procedure_type=selected_service,
                unit=unit,
                selected_date=selected_day,
                period=carried_period,
                selected_slot_choice=selected_slot_choice,
            )

    if not has_scheduling_keywords and not force_wizard:
        return None
    if _extract_option_index_choice(inbound_text) is not None or _extract_time_choice(inbound_text) is not None:
        return None

    has_explicit_service = _wizard_has_explicit_service_inbound(inbound_text)
    explicit_availability_request = _is_explicit_availability_request(inbound_text)
    if not force_wizard and (has_explicit_service or explicit_availability_request or requested_date or period):
        return None

    preferred_service = _infer_procedure_type(inbound_text=inbound_text, context=context) if has_explicit_service else None
    return _wizard_build_service_step_response(
        db,
        conversation=conversation,
        intro_text=None,
        period=period,
        requested_date=requested_date,
        preferred_service=preferred_service,
    )


def _known_contact_names(db: Session, *, conversation: Conversation) -> list[str]:
    raw_candidates: list[str] = []
    if conversation.patient_id:
        patient = db.scalar(
            select(Patient).where(
                Patient.id == conversation.patient_id,
                Patient.tenant_id == conversation.tenant_id,
            )
        )
        if patient and patient.full_name:
            raw_candidates.append(patient.full_name)

    if conversation.lead_id:
        lead = db.scalar(
            select(Lead).where(
                Lead.id == conversation.lead_id,
                Lead.tenant_id == conversation.tenant_id,
            )
        )
        if lead and lead.name:
            raw_candidates.append(lead.name)

    deduped: list[str] = []
    seen: set[str] = set()
    for raw in raw_candidates:
        cleaned = re.sub(r"\s+", " ", str(raw or "").strip())
        if len(cleaned) < 2:
            continue
        for alias in (cleaned, cleaned.split(" ")[0]):
            normalized = _normalize_for_match(alias)
            if len(normalized) < 2 or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(alias)
    return deduped


def _remove_excessive_name_mentions(text: str, *, known_names: list[str]) -> str:
    if not known_names:
        return text

    output = text
    for name in known_names:
        escaped = re.escape(name)
        output = re.sub(
            rf"^\s*(ol[aá]|oi)\s*,?\s*{escaped}\s*!?\s*",
            "Olá! ",
            output,
            flags=re.IGNORECASE,
        )
        output = re.sub(
            rf"(^|\n)\s*{escaped}\s*,\s*",
            r"\1",
            output,
            flags=re.IGNORECASE,
        )
    return output


def _normalize_response_text(db: Session, *, conversation: Conversation, text: str) -> str:
    output = str(text or "").strip()
    if not output:
        return ""

    # Normaliza listas numeradas e separadores visuais para leitura no WhatsApp.
    output = output.replace(" | ", "\n")
    output = re.sub(r"\s+(?=\d+\)\s)", "\n", output)
    output = re.sub(r"\n{3,}", "\n\n", output)

    output = _remove_excessive_name_mentions(
        output,
        known_names=_known_contact_names(db, conversation=conversation),
    )

    # Remove duplicidade de linhas idênticas consecutivas.
    lines: list[str] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if lines and _normalize_for_match(lines[-1]) == _normalize_for_match(line):
            continue
        lines.append(line)
    output = "\n".join(lines).strip()

    if len(output) > 1500:
        output = f"{output[:1500].rstrip()}..."
    return output


def _resolve_conversation_unit(db: Session, *, conversation: Conversation) -> Unit | None:
    if conversation.unit_id:
        unit = db.scalar(
            select(Unit).where(
                Unit.id == conversation.unit_id,
                Unit.tenant_id == conversation.tenant_id,
                Unit.is_active.is_(True),
            )
        )
        if unit:
            return unit

    if conversation.patient_id:
        patient = db.scalar(
            select(Patient).where(
                Patient.id == conversation.patient_id,
                Patient.tenant_id == conversation.tenant_id,
            )
        )
        if patient and patient.unit_id:
            unit = db.scalar(
                select(Unit).where(
                    Unit.id == patient.unit_id,
                    Unit.tenant_id == conversation.tenant_id,
                    Unit.is_active.is_(True),
                )
            )
            if unit:
                if conversation.unit_id != unit.id:
                    conversation.unit_id = unit.id
                    db.add(conversation)
                return unit

    return db.scalar(
        select(Unit)
        .where(
            Unit.tenant_id == conversation.tenant_id,
            Unit.is_active.is_(True),
        )
        .order_by(Unit.created_at.asc())
        .limit(1)
    )


def _resolve_operation_timezone(config: dict[str, Any]) -> ZoneInfo:
    timezone_name = str((config.get("business_hours") or {}).get("timezone") or settings.app_timezone)
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("America/Sao_Paulo")


def _period_window_minutes(*, base_start: int, base_end: int, period: str | None) -> tuple[int, int]:
    if period == "morning":
        return max(base_start, 7 * 60), min(base_end, 12 * 60)
    if period == "afternoon":
        return max(base_start, 12 * 60), min(base_end, 18 * 60)
    if period == "evening":
        return max(base_start, 18 * 60), min(base_end, 22 * 60)
    return base_start, base_end


def _weekday_label_pt(weekday_index: int) -> str:
    labels = [
        "segunda-feira",
        "terça-feira",
        "quarta-feira",
        "quinta-feira",
        "sexta-feira",
        "sábado",
        "domingo",
    ]
    if 0 <= weekday_index <= 6:
        return labels[weekday_index]
    return "dia"


def _format_slot_pt(slot_local: datetime) -> str:
    return f"{_weekday_label_pt(slot_local.weekday())}, {slot_local.strftime('%d/%m')} às {slot_local.strftime('%H:%M')}"


def _normalize_procedure_label(value: str) -> str:
    normalized = _normalize_for_match(value or "")
    return normalized.replace("  ", " ").strip()


def _professional_matches_procedure(professional: Professional, procedure_type: str) -> bool:
    procedures = [item for item in (professional.procedures or []) if isinstance(item, str) and item.strip()]
    if not procedures:
        return True
    target = _normalize_procedure_label(procedure_type)
    return any(
        _normalize_procedure_label(option) in target or target in _normalize_procedure_label(option)
        for option in procedures
    )


def _parse_professional_working_days(professional: Professional, fallback_days: list[int]) -> list[int]:
    if isinstance(professional.working_days, list):
        days = sorted({int(day) for day in professional.working_days if isinstance(day, int) and 0 <= int(day) <= 6})
        if days:
            return days
    return fallback_days


def _parse_professional_window(professional: Professional, *, fallback_start: int, fallback_end: int) -> tuple[int, int]:
    start_h, start_m = _parse_hhmm(professional.shift_start or "08:00")
    end_h, end_m = _parse_hhmm(professional.shift_end or "18:00")
    start_total = start_h * 60 + start_m
    end_total = end_h * 60 + end_m
    if end_total <= start_total:
        return fallback_start, fallback_end
    return start_total, end_total


def _list_available_slots(
    db: Session,
    *,
    tenant_id: UUID,
    unit_id: UUID,
    config: dict[str, Any],
    procedure_type: str,
    period: str | None,
    requested_date: date | None = None,
    max_slots: int = 3,
    slot_duration_minutes: int = 60,
) -> list[dict[str, Any]]:
    timezone = _resolve_operation_timezone(config)
    now_utc = datetime.now(UTC)
    now_local = now_utc.astimezone(timezone)

    business_hours = config.get("business_hours") or {}
    weekdays = [int(day) for day in (business_hours.get("weekdays") or [0, 1, 2, 3, 4]) if isinstance(day, int)]
    if not weekdays:
        weekdays = [0, 1, 2, 3, 4]

    start_h, start_m = _parse_hhmm(str(business_hours.get("start") or "08:00"))
    end_h, end_m = _parse_hhmm(str(business_hours.get("end") or "18:00"))
    base_start = start_h * 60 + start_m
    base_end = end_h * 60 + end_m
    if base_end <= base_start or (base_end - base_start) < slot_duration_minutes:
        logger.warning(
            "ai_autoresponder.invalid_business_hours_window",
            tenant_id=str(tenant_id),
            unit_id=str(unit_id),
            configured_start=str(business_hours.get("start") or ""),
            configured_end=str(business_hours.get("end") or ""),
            slot_duration_minutes=slot_duration_minutes,
        )
        base_start = 8 * 60
        base_end = 18 * 60
    window_end_utc = now_utc + timedelta(days=21)
    busy_rows = db.execute(
        select(Appointment).where(
            Appointment.tenant_id == tenant_id,
            Appointment.unit_id == unit_id,
            Appointment.starts_at >= now_utc - timedelta(hours=2),
            Appointment.starts_at <= window_end_utc,
            Appointment.status.in_(["agendada", "confirmada", "reagendada"]),
        )
    ).scalars().all()

    busy_by_professional: dict[str, list[tuple[datetime, datetime]]] = {}
    for item in busy_rows:
        start_at = item.starts_at
        if not start_at:
            continue
        end_at = item.ends_at or (start_at + timedelta(minutes=slot_duration_minutes))
        key = str(item.professional_id) if item.professional_id else "__unit__"
        busy_by_professional.setdefault(key, []).append((start_at, end_at))

    all_professionals = db.execute(
        select(Professional).where(
            Professional.tenant_id == tenant_id,
            Professional.unit_id == unit_id,
            Professional.is_active.is_(True),
        )
    ).scalars().all()
    professionals = [item for item in all_professionals if _professional_matches_procedure(item, procedure_type)]
    if not professionals and all_professionals:
        # Se não houver match exato por procedimento, usa equipe da unidade para não bloquear disponibilidade.
        professionals = all_professionals

    if not professionals:
        # Fallback legado: agenda por unidade quando ainda não há profissional configurado.
        professionals = [
            Professional(
                tenant_id=tenant_id,
                unit_id=unit_id,
                full_name="Equipe clínica",
                working_days=weekdays,
                shift_start=f"{start_h:02d}:{start_m:02d}",
                shift_end=f"{end_h:02d}:{end_m:02d}",
                procedures=[],
                is_active=True,
            )
        ]

    def _collect_slots_for_duration(*, duration_minutes: int) -> list[dict[str, Any]]:
        slots: list[dict[str, Any]] = []
        for professional in professionals:
            professional_days = _parse_professional_working_days(professional, weekdays)
            prof_start, prof_end = _parse_professional_window(
                professional,
                fallback_start=base_start,
                fallback_end=base_end,
            )
            window_start, window_end = _period_window_minutes(
                base_start=prof_start,
                base_end=prof_end,
                period=period,
            )
            if window_end <= window_start:
                continue

            professional_key = str(professional.id) if getattr(professional, "id", None) else "__unit__"
            busy_windows = busy_by_professional.get(professional_key, [])
            if professional_key != "__unit__":
                busy_windows = busy_windows + busy_by_professional.get("__unit__", [])

            for day_offset in range(0, 21):
                day_local = (now_local + timedelta(days=day_offset)).date()
                if requested_date and day_local != requested_date:
                    continue
                if day_local.weekday() not in professional_days:
                    continue

                minute_pointer = window_start
                while minute_pointer + duration_minutes <= window_end:
                    slot_local = datetime(
                        year=day_local.year,
                        month=day_local.month,
                        day=day_local.day,
                        hour=minute_pointer // 60,
                        minute=minute_pointer % 60,
                        tzinfo=timezone,
                    )
                    slot_start_utc = slot_local.astimezone(UTC)
                    slot_end_utc = slot_start_utc + timedelta(minutes=duration_minutes)

                    if slot_start_utc <= now_utc + timedelta(minutes=20):
                        minute_pointer += 30
                        continue

                    has_conflict = any(
                        busy_start < slot_end_utc and busy_end > slot_start_utc
                        for busy_start, busy_end in busy_windows
                    )
                    if not has_conflict:
                        slots.append(
                            {
                                "starts_at_utc": slot_start_utc,
                                "ends_at_utc": slot_end_utc,
                                "starts_at_local": slot_local,
                                "label": _format_slot_pt(slot_local),
                                "professional_id": getattr(professional, "id", None),
                                "professional_name": professional.full_name,
                            }
                        )

                    minute_pointer += 30

        slots.sort(key=lambda item: item["starts_at_utc"])
        return slots

    duration_candidates = [slot_duration_minutes]
    if slot_duration_minutes > 30:
        duration_candidates.append(30)

    for duration in duration_candidates:
        slots = _collect_slots_for_duration(duration_minutes=duration)
        if slots:
            if duration != slot_duration_minutes:
                logger.info(
                    "ai_autoresponder.slots_found_with_shorter_duration",
                    tenant_id=str(tenant_id),
                    unit_id=str(unit_id),
                    procedure_type=procedure_type,
                    requested_date=requested_date.isoformat() if requested_date else None,
                    requested_duration_minutes=slot_duration_minutes,
                    fallback_duration_minutes=duration,
                )
            return slots[:max_slots]

    logger.info(
        "ai_autoresponder.no_slots_found",
        tenant_id=str(tenant_id),
        unit_id=str(unit_id),
        procedure_type=procedure_type,
        period=period,
        requested_date=requested_date.isoformat() if requested_date else None,
        professionals_count=len(professionals),
        busy_rows_count=len(busy_rows),
        base_window=f"{base_start:04d}-{base_end:04d}",
        duration_candidates=duration_candidates,
    )
    return []


def _infer_procedure_type(*, inbound_text: str, context: str) -> str:
    normalized_inbound = _normalize_for_match(inbound_text)
    normalized_context = _normalize_for_match(context)

    # Prioriza sempre o que o paciente pediu na mensagem atual.
    if "limpeza" in normalized_inbound or "profilax" in normalized_inbound:
        return "Limpeza odontológica"
    if "clareamento" in normalized_inbound:
        return "Clareamento dental"
    if "lente" in normalized_inbound:
        return "Instalação de lentes"
    if "implante" in normalized_inbound:
        return "Implante dentário"
    if "ortodont" in normalized_inbound:
        return "Avaliação ortodôntica"

    # Se não houver menção explícita na mensagem atual, usa o contexto.
    if "limpeza" in normalized_context or "profilax" in normalized_context:
        return "Limpeza odontológica"
    if "clareamento" in normalized_context:
        return "Clareamento dental"
    if "lente" in normalized_context:
        return "Instalação de lentes"
    if "implante" in normalized_context:
        return "Implante dentário"
    if "ortodont" in normalized_context:
        return "Avaliação ortodôntica"
    return "Avaliação odontológica"


def _recent_ai_outbound_messages(
    db: Session,
    *,
    conversation: Conversation,
    limit: int = 20,
) -> list[Message]:
    return db.execute(
        select(Message)
        .where(
            Message.tenant_id == conversation.tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == MessageDirection.OUTBOUND.value,
            Message.sender_type == "ai",
        )
        .order_by(Message.created_at.desc())
        .limit(limit)
    ).scalars().all()


def _latest_ai_outbound_message(db: Session, *, conversation: Conversation) -> Message | None:
    rows = _recent_ai_outbound_messages(db, conversation=conversation, limit=1)
    return rows[0] if rows else None


def _latest_ai_slots_message(db: Session, *, conversation: Conversation) -> Message | None:
    offer_modes = {"slots_suggested", "no_slots_for_period_with_alternatives"}
    for message in _recent_ai_outbound_messages(db, conversation=conversation, limit=30):
        payload = message.payload if isinstance(message.payload, dict) else {}
        mode = str(payload.get("mode") or "").strip()
        if mode in offer_modes:
            return message
    return None


def _has_intervening_new_scheduling_request(
    db: Session,
    *,
    conversation: Conversation,
    anchor_message: Message,
    current_inbound_message: Message,
    operation_timezone: ZoneInfo,
) -> bool:
    if not anchor_message.created_at or not current_inbound_message.created_at:
        return False

    intervening_inbounds = db.execute(
        select(Message)
        .where(
            Message.tenant_id == conversation.tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == MessageDirection.INBOUND.value,
            Message.created_at > anchor_message.created_at,
            Message.created_at <= current_inbound_message.created_at,
            Message.id != current_inbound_message.id,
        )
        .order_by(Message.created_at.asc())
        .limit(12)
    ).scalars().all()

    for inbound in intervening_inbounds:
        text = str(inbound.body or "").strip()
        if not text:
            continue
        if _extract_requested_date_from_text(text=text, timezone=operation_timezone):
            return True
        if _detect_period_preference(text):
            return True
        if _is_explicit_availability_request(text):
            return True

        normalized = _normalize_for_match(text)
        has_explicit_scheduling_intent = any(
            keyword in normalized
            for keyword in SCHEDULING_INTENT_KEYWORDS
        )
        if has_explicit_scheduling_intent:
            is_simple_confirmation = (
                _extract_option_index_choice(text) is not None
                or _extract_time_choice(text) is not None
                or _is_booking_confirmation_message(text)
            )
            if not is_simple_confirmation:
                return True

    return False


def _appointment_response_from_selected_slot(
    db: Session,
    *,
    conversation: Conversation,
    unit: Unit,
    selected_slot: dict[str, Any],
    procedure_type: str,
    period: str | None,
    requested_date: date | None,
) -> dict[str, Any]:
    if not conversation.patient_id:
        return {
            "mode": "missing_patient",
            "response_text": (
                "Consegui localizar horários, mas preciso confirmar seu cadastro. "
                "Vou transferir para o atendimento humano finalizar o agendamento."
            ),
            "metadata": {"period": period, "reason": "missing_patient"},
        }

    existing = db.scalar(
        select(Appointment).where(
            Appointment.tenant_id == conversation.tenant_id,
            Appointment.patient_id == conversation.patient_id,
            Appointment.unit_id == unit.id,
            Appointment.starts_at == selected_slot["starts_at_utc"],
            Appointment.status.in_(["agendada", "confirmada", "reagendada"]),
        )
    )
    if existing:
        return {
            "mode": "appointment_already_created",
            "response_text": (
                "Esse horário já está confirmado na sua agenda.\n"
                f"• Horário: {selected_slot['label']}\n"
                f"• Unidade: {unit.name}"
            ),
            "metadata": {
                "appointment_id": str(existing.id),
                "period": period,
                "selected_slot": selected_slot["label"],
                "starts_at_utc": existing.starts_at.isoformat(),
                "unit_id": str(unit.id),
                "requested_date": requested_date.isoformat() if requested_date else None,
                "professional_id": (
                    str(selected_slot.get("professional_id"))
                    if selected_slot.get("professional_id")
                    else None
                ),
                "professional_name": selected_slot.get("professional_name"),
            },
        }

    appointment = Appointment(
        tenant_id=conversation.tenant_id,
        patient_id=conversation.patient_id,
        unit_id=unit.id,
        professional_id=selected_slot.get("professional_id"),
        procedure_type=procedure_type,
        starts_at=selected_slot["starts_at_utc"],
        ends_at=selected_slot["ends_at_utc"],
        origin="ai_autoresponder",
        notes="Agendamento automático via WhatsApp/IA.",
        status="agendada",
        confirmation_status="confirmada",
        confirmed_at=datetime.now(UTC),
    )
    db.add(appointment)
    db.flush()

    db.add(
        AppointmentEvent(
            tenant_id=conversation.tenant_id,
            appointment_id=appointment.id,
            event_type="created",
            to_status=appointment.status,
            metadata_json={
                "origin": "ai_autoresponder",
                "channel": "whatsapp",
                "period_preference": period,
            },
            created_by_user_id=None,
        )
    )

    tags = set(conversation.tags or [])
    tags.add("agendamento_confirmado_ia")
    conversation.tags = sorted(tags)
    db.add(conversation)

    db.add(
        MessageEvent(
            tenant_id=conversation.tenant_id,
            event_type="ai_appointment_created",
            payload={
                "conversation_id": str(conversation.id),
                "appointment_id": str(appointment.id),
                "unit_id": str(unit.id),
                "professional_id": (
                    str(selected_slot.get("professional_id"))
                    if selected_slot.get("professional_id")
                    else None
                ),
                "starts_at": appointment.starts_at.isoformat(),
                "origin": "ai_autoresponder",
            },
        )
    )

    return {
        "mode": "appointment_created",
        "response_text": (
            "Agendamento confirmado com sucesso.\n"
            f"• Horário: {selected_slot['label']}\n"
            f"• Unidade: {unit.name}"
            + (
                f"\n• Profissional: {selected_slot['professional_name']}"
                if selected_slot.get("professional_name")
                else ""
            )
            + "\nSe precisar, posso reagendar."
        ),
        "metadata": {
            "appointment_id": str(appointment.id),
            "period": period,
            "selected_slot": selected_slot["label"],
            "starts_at_utc": appointment.starts_at.isoformat(),
            "unit_id": str(unit.id),
            "requested_date": requested_date.isoformat() if requested_date else None,
            "professional_id": (
                str(selected_slot.get("professional_id"))
                if selected_slot.get("professional_id")
                else None
            ),
            "professional_name": selected_slot.get("professional_name"),
        },
    }


def _try_followup_slot_confirmation(
    db: Session,
    *,
    conversation: Conversation,
    inbound_message: Message,
    inbound_text: str,
    unit: Unit,
    procedure_type: str,
    period: str | None,
    requested_date: date | None,
    operation_timezone: ZoneInfo,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    inbound_payload = inbound_message.payload if isinstance(inbound_message.payload, dict) else {}
    option_index = _extract_option_index_choice(inbound_text) or _extract_option_index_from_inbound_payload(inbound_payload)
    explicit_time = _extract_time_choice(inbound_text)
    confirmation_only = _is_booking_confirmation_message(inbound_text)

    if option_index is None and not explicit_time and not confirmation_only:
        return None

    latest_ai_message = _latest_ai_outbound_message(db, conversation=conversation)
    latest_text = str(latest_ai_message.body or "") if latest_ai_message else ""

    slots_anchor_message = _latest_ai_slots_message(db, conversation=conversation)
    anchor_text = str(slots_anchor_message.body or "") if slots_anchor_message else ""
    if not anchor_text:
        return None

    if _has_intervening_new_scheduling_request(
        db,
        conversation=conversation,
        anchor_message=slots_anchor_message,
        current_inbound_message=inbound_message,
        operation_timezone=operation_timezone,
    ):
        return {
            "mode": "followup_anchor_stale",
            "response_text": (
                "Para evitar agendamento errado, me confirme novamente a data e hora desejadas "
                "(ex.: 16/04 às 08:00) ou me peça os horários de novo."
            ),
            "metadata": {"reason": "followup_anchor_stale"},
        }

    anchor_payload = slots_anchor_message.payload if slots_anchor_message and isinstance(slots_anchor_message.payload, dict) else {}
    anchor_scheduling = anchor_payload.get("scheduling") if isinstance(anchor_payload.get("scheduling"), dict) else {}
    anchor_procedure_type = str(anchor_scheduling.get("procedure_type") or "").strip() or procedure_type

    anchor_requested_date: date | None = None
    anchor_requested_date_raw = anchor_scheduling.get("requested_date")
    if isinstance(anchor_requested_date_raw, str) and anchor_requested_date_raw.strip():
        try:
            anchor_requested_date = date.fromisoformat(anchor_requested_date_raw.strip()[:10])
        except ValueError:
            anchor_requested_date = None

    anchor_period_raw = str(anchor_scheduling.get("period") or "").strip().lower()
    anchor_period = anchor_period_raw if anchor_period_raw in {"morning", "afternoon", "evening"} else None

    selected_date = (
        requested_date
        or anchor_requested_date
        or _extract_requested_date_from_text(text=anchor_text, timezone=operation_timezone)
        or _extract_requested_date_from_text(text=latest_text, timezone=operation_timezone)
    )
    selected_period = period or anchor_period or _detect_period_preference(anchor_text) or _detect_period_preference(latest_text)
    slot_limit = 12 if selected_date else 6
    slots = _list_available_slots(
        db,
        tenant_id=conversation.tenant_id,
        unit_id=unit.id,
        config=config,
        procedure_type=anchor_procedure_type,
        period=selected_period,
        requested_date=selected_date,
        max_slots=slot_limit,
    )
    if not slots:
        date_hint = f" para {selected_date.strftime('%d/%m')}" if selected_date else ""
        return {
            "mode": "no_slots_general",
            "response_text": (
                f"No momento não encontrei horários livres na agenda{date_hint} para este serviço. "
                "Posso te avisar assim que abrir uma vaga ou te direcionar para atendimento humano."
            ),
                "metadata": {
                    "reason": "no_slots_general",
                    "requested_date": selected_date.isoformat() if selected_date else None,
                    "procedure_type": anchor_procedure_type,
                },
            }

    chosen_slot: dict[str, Any] | None = None
    if option_index is not None:
        if 1 <= option_index <= len(slots):
            chosen_slot = slots[option_index - 1]
        else:
            return {
                "mode": "invalid_slot_option",
                "response_text": (
                    f"Não encontrei a opção {option_index} nesta agenda.\n"
                    f"{_format_slots_options_message(slots=slots[:3], period=selected_period, procedure_type=anchor_procedure_type)}"
                ),
                "metadata": {
                    "reason": "invalid_slot_option",
                    "option_index": option_index,
                    "requested_date": selected_date.isoformat() if selected_date else None,
                },
            }

    if not chosen_slot and explicit_time:
        chosen_slot = next(
            (
                slot
                for slot in slots
                if slot["starts_at_local"].strftime("%H:%M") == explicit_time
            ),
            None,
        )
        if not chosen_slot:
            return {
                "mode": "requested_time_not_available",
                "response_text": (
                    f"No momento não encontrei vaga às {explicit_time}.\n"
                    f"{_format_slots_options_message(slots=slots[:3], period=selected_period, procedure_type=anchor_procedure_type)}"
                ),
                "metadata": {
                    "reason": "requested_time_not_available",
                    "requested_time": explicit_time,
                    "requested_date": selected_date.isoformat() if selected_date else None,
                },
            }

    if not chosen_slot and confirmation_only:
        recent_times = _extract_time_mentions(anchor_text) or _extract_time_mentions(latest_text)
        if len(recent_times) == 1:
            chosen_slot = next(
                (
                    slot
                    for slot in slots
                    if slot["starts_at_local"].strftime("%H:%M") == recent_times[0]
                ),
                None,
            )
        elif len(slots) == 1:
            chosen_slot = slots[0]
        else:
            return {
                "mode": "confirmation_requires_selection",
                "response_text": (
                    "Perfeito. Para concluir, me diga o número da opção desejada "
                    "ou informe a hora exata (ex.: 09:00)."
                ),
                "metadata": {
                    "reason": "confirmation_requires_selection",
                    "requested_date": selected_date.isoformat() if selected_date else None,
                },
            }

    if not chosen_slot:
        return None

    return _appointment_response_from_selected_slot(
        db,
        conversation=conversation,
        unit=unit,
        selected_slot=chosen_slot,
        procedure_type=anchor_procedure_type,
        period=selected_period,
        requested_date=selected_date,
    )


def _build_scheduling_operation_response(
    db: Session,
    *,
    conversation: Conversation,
    inbound_message: Message,
    inbound_text: str,
    context: str,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    wizard_response = _try_booking_wizard_response(
        db,
        conversation=conversation,
        inbound_message=inbound_message,
        inbound_text=inbound_text,
        context=context,
        config=config,
    )
    if wizard_response:
        return wizard_response

    inbound_payload = inbound_message.payload if isinstance(inbound_message.payload, dict) else {}
    period = _detect_period_preference(inbound_text)
    explicit_availability_request = _is_explicit_availability_request(inbound_text) or _is_followup_availability_request(
        inbound_text=inbound_text,
        context=context,
    )
    has_followup_confirmation = (
        _extract_option_index_choice(inbound_text) is not None
        or _extract_option_index_from_inbound_payload(inbound_payload) is not None
        or _extract_time_choice(inbound_text) is not None
        or _is_booking_confirmation_message(inbound_text)
    )
    if not period and not explicit_availability_request and not has_followup_confirmation:
        return None
    if period and not _is_scheduling_context(inbound_text=inbound_text, context=context) and not explicit_availability_request:
        return None

    unit = _resolve_conversation_unit(db, conversation=conversation)
    if not unit:
        return {
            "mode": "no_unit_available",
            "response_text": (
                "No momento não consegui acessar a agenda da unidade. "
                "Vou encaminhar para o atendimento humano confirmar seu horário."
            ),
            "metadata": {"reason": "no_unit_available"},
        }

    procedure_type = _infer_procedure_type(inbound_text=inbound_text, context=context)
    operation_timezone = _resolve_operation_timezone(config)
    requested_date = _extract_requested_date_from_text(text=inbound_text, timezone=operation_timezone)
    requested_date_label = requested_date.strftime("%d/%m") if requested_date else None
    slot_limit = 12 if requested_date else 3

    followup_response = _try_followup_slot_confirmation(
        db,
        conversation=conversation,
        inbound_message=inbound_message,
        inbound_text=inbound_text,
        unit=unit,
        procedure_type=procedure_type,
        period=period,
        requested_date=requested_date,
        operation_timezone=operation_timezone,
        config=config,
    )
    if followup_response:
        return followup_response

    if period:
        slots = _list_available_slots(
            db,
            tenant_id=conversation.tenant_id,
            unit_id=unit.id,
            config=config,
            procedure_type=procedure_type,
            period=period,
            requested_date=requested_date,
            max_slots=slot_limit,
        )
        if not slots:
            period_label = {
                "morning": "manhã",
                "afternoon": "tarde",
                "evening": "noite",
            }.get(period, "este período")
            fallback_slots = _list_available_slots(
                db,
                tenant_id=conversation.tenant_id,
                unit_id=unit.id,
                config=config,
                procedure_type=procedure_type,
                period=None,
                requested_date=requested_date,
                max_slots=slot_limit,
            )
            if fallback_slots:
                date_hint = f" para {requested_date_label}" if requested_date_label else ""
                return {
                    "mode": "no_slots_for_period_with_alternatives",
                    "response_text": (
                        f"No momento não encontrei vagas para {period_label}{date_hint}.\n"
                        f"{_format_slots_options_message(slots=fallback_slots, procedure_type=procedure_type, period=None)}"
                    ),
                    "metadata": {
                        "period": period,
                        "reason": "no_slots_for_period",
                        "requested_date": requested_date.isoformat() if requested_date else None,
                        "procedure_type": procedure_type,
                        "alternative_slots": [slot["label"] for slot in fallback_slots],
                    },
                }
            date_hint = f" em {requested_date_label}" if requested_date_label else ""
            return {
                "mode": "no_slots_for_period",
                "response_text": (
                    f"No momento não encontrei vaga para {period_label}{date_hint}. "
                    "Se preferir, posso verificar outro período para você."
                ),
                "metadata": {
                    "period": period,
                    "reason": "no_slots_for_period",
                    "requested_date": requested_date.isoformat() if requested_date else None,
                    "procedure_type": procedure_type,
                },
            }
        labels = [slot["label"] for slot in slots]
        return {
            "mode": "slots_suggested",
            "response_text": _format_slots_options_message(slots=slots, period=period, procedure_type=procedure_type),
            "metadata": {
                "slots": labels,
                "unit_id": str(unit.id),
                "requested_date": requested_date.isoformat() if requested_date else None,
                "procedure_type": procedure_type,
                "period": period,
            },
        }

    slots = _list_available_slots(
        db,
        tenant_id=conversation.tenant_id,
        unit_id=unit.id,
        config=config,
        procedure_type=procedure_type,
        period=None,
        requested_date=requested_date,
        max_slots=slot_limit,
    )
    if not slots:
        date_hint = f" para {requested_date_label}" if requested_date_label else ""
        return {
            "mode": "no_slots_general",
            "response_text": (
                f"No momento não encontrei horários livres na agenda{date_hint} para este serviço. "
                "Posso te avisar assim que abrir uma vaga ou te direcionar para atendimento humano."
            ),
            "metadata": {
                "reason": "no_slots_general",
                "requested_date": requested_date.isoformat() if requested_date else None,
            },
        }

    labels = [slot["label"] for slot in slots]
    return {
        "mode": "slots_suggested",
        "response_text": _format_slots_options_message(slots=slots, period=period, procedure_type=procedure_type),
        "metadata": {
            "slots": labels,
            "unit_id": str(unit.id),
            "requested_date": requested_date.isoformat() if requested_date else None,
            "procedure_type": procedure_type,
            "period": period,
        },
    }


def _recent_context(db: Session, *, tenant_id: UUID, conversation_id: UUID, limit: int = 12) -> str:
    messages = db.execute(
        select(Message)
        .where(Message.tenant_id == tenant_id, Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    ).scalars().all()
    messages.reverse()
    lines = [f"[{item.direction}] {item.body}" for item in messages if item.body]
    return "\n".join(lines)


def _prompt_for_autoresponder(
    *,
    config: dict[str, Any],
    context: str,
    inbound_text: str,
    knowledge_context: str = "",
) -> str:
    knowledge_section = ""
    if knowledge_context:
        knowledge_section = (
            "Base de conhecimento operacional da clínica (fonte da verdade):\n"
            f"{knowledge_context}\n\n"
        )

    return (
        "Você é assistente virtual de recepção odontológica do OdontoFlux.\n"
        "Responda apenas em pt-BR, tom profissional, cordial e objetivo.\n"
        "Tom desejado: "
        f"{config.get('tone') or AI_AUTORESPONDER_DEFAULT_CONFIG['tone']}.\n"
        "Regras obrigatórias:\n"
        "1) Nunca ofereça diagnóstico, prescrição, dose, laudo ou conduta clínica.\n"
        "2) Foque em atendimento operacional: acolhimento, horários, confirmação, reagendamento, documentação e repasse para equipe.\n"
        "3) Se houver urgência ou risco, responda orientando busca de atendimento humano imediato, sem aconselhamento clínico.\n"
        "4) Mantenha respostas curtas (máximo 4 frases), claras e acionáveis.\n"
        "5) Use estritamente a base da clínica quando houver informação cadastrada.\n"
        "6) Se faltar informação na base, não invente; peça dados mínimos ou informe que vai confirmar com a equipe.\n\n"
        "7) Não repita apresentação completa em toda mensagem e evite citar o nome do paciente em todas as respostas.\n"
        "8) Ao informar datas/horários, use lista numerada (uma opção por linha).\n"
        "9) Não diga 'vou verificar e retorno'; responda com opção concreta agora ou faça handoff humano.\n\n"
        f"{knowledge_section}"
        f"Histórico recente:\n{context}\n\n"
        f"Mensagem do paciente:\n{inbound_text}\n\n"
        "Gere apenas a resposta final ao paciente."
    )


def _reason_label(reason: str) -> str:
    return REASON_LABELS.get(reason, reason.replace("_", " ").capitalize())


def _looks_like_appointment_confirmation(text: str) -> bool:
    normalized = _normalize_for_match(text)
    if "agendado" in normalized or "agendada" in normalized:
        return True
    if "agendamento confirmado" in normalized:
        return True
    if "consulta confirmada" in normalized:
        return True
    return False


def _build_metadata(*, config: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "config": {
            "enabled": config.get("enabled"),
            "channels": config.get("channels"),
            "outside_business_hours_mode": config.get("outside_business_hours_mode"),
            "max_consecutive_auto_replies": config.get("max_consecutive_auto_replies"),
            "confidence_threshold": config.get("confidence_threshold"),
        },
        **(extra or {}),
    }


def _create_decision(
    db: Session,
    *,
    tenant_id: UUID,
    conversation: Conversation,
    inbound_message: Message,
    dedupe_key: str,
    final_decision: str,
    decision_reason: str,
    generated_response: str | None = None,
    confidence: float | None = None,
    guardrail_trigger: str | None = None,
    handoff_required: bool = False,
    llm_payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    outbound_message_id: UUID | None = None,
) -> AIAutoresponderDecision:
    llm_payload = llm_payload or {}
    llm_metadata = llm_payload.get("metadata") or {}

    prompt_tokens = llm_metadata.get("prompt_tokens") or llm_metadata.get("input_tokens")
    completion_tokens = llm_metadata.get("completion_tokens") or llm_metadata.get("output_tokens")
    total_tokens = llm_metadata.get("total_tokens")
    if total_tokens is None and isinstance(prompt_tokens, int) and isinstance(completion_tokens, int):
        total_tokens = prompt_tokens + completion_tokens

    decision = AIAutoresponderDecision(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        unit_id=conversation.unit_id,
        inbound_message_id=inbound_message.id,
        outbound_message_id=outbound_message_id,
        channel=conversation.channel,
        inbound_text=inbound_message.body or "",
        generated_response=generated_response,
        confidence=confidence,
        final_decision=final_decision,
        decision_reason=decision_reason,
        guardrail_trigger=guardrail_trigger,
        handoff_required=handoff_required,
        llm_provider=llm_metadata.get("provider"),
        llm_model=llm_metadata.get("model"),
        llm_task=llm_metadata.get("task"),
        prompt_version=AI_AUTORESPONDER_PROMPT_VERSION,
        prompt_text=llm_payload.get("prompt"),
        token_input=prompt_tokens if isinstance(prompt_tokens, int) else None,
        token_output=completion_tokens if isinstance(completion_tokens, int) else None,
        token_total=total_tokens if isinstance(total_tokens, int) else None,
        estimated_cost_usd=(
            float(llm_metadata.get("cost_usd"))
            if isinstance(llm_metadata.get("cost_usd"), (float, int))
            else None
        ),
        latency_ms=llm_metadata.get("latency_ms") if isinstance(llm_metadata.get("latency_ms"), int) else None,
        dedupe_key=dedupe_key,
        metadata_json=metadata or {},
    )
    db.add(decision)
    db.flush()
    return decision


def _notify_handoff(
    db: Session,
    *,
    conversation: Conversation,
    inbound_message: Message,
    reason: str,
    config: dict[str, Any],
) -> None:
    queue_tag = config.get("human_queue_tag") or "fila_humana_ia"

    conversation.status = "aguardando"
    conversation.ai_autoresponder_consecutive_count = 0
    conversation.ai_autoresponder_last_decision = DECISION_HANDOFF
    conversation.ai_autoresponder_last_reason = reason
    conversation.ai_autoresponder_last_at = datetime.now(UTC)
    tags = set(conversation.tags or [])
    tags.add(queue_tag)
    tags.add("handoff_ia")
    conversation.tags = sorted(tags)

    fallback_user_id = config.get("fallback_user_id")
    if not conversation.assigned_user_id and fallback_user_id:
        user = db.scalar(
            select(User).where(
                User.id == fallback_user_id,
                User.tenant_id == conversation.tenant_id,
                User.is_active.is_(True),
            )
        )
        if user:
            conversation.assigned_user_id = user.id

    db.add(
        MessageEvent(
            tenant_id=conversation.tenant_id,
            message_id=inbound_message.id,
            event_type="ai_handoff_required",
            payload={
                "conversation_id": str(conversation.id),
                "reason": reason,
                "reason_label": _reason_label(reason),
                "assigned_user_id": str(conversation.assigned_user_id) if conversation.assigned_user_id else None,
                "queue_tag": queue_tag,
            },
        )
    )
    db.add(conversation)


def set_conversation_autoresponder(
    db: Session,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    enabled: bool | None,
) -> Conversation | None:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id,
        )
    )
    if not conversation:
        return None
    conversation.ai_autoresponder_enabled = enabled
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def get_conversation_decisions(
    db: Session,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    limit: int = 30,
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(AIAutoresponderDecision)
        .where(
            AIAutoresponderDecision.tenant_id == tenant_id,
            AIAutoresponderDecision.conversation_id == conversation_id,
        )
        .order_by(AIAutoresponderDecision.created_at.desc())
        .limit(limit)
    ).scalars().all()

    return [
        {
            "id": str(item.id),
            "conversation_id": str(item.conversation_id),
            "inbound_message_id": str(item.inbound_message_id) if item.inbound_message_id else None,
            "outbound_message_id": str(item.outbound_message_id) if item.outbound_message_id else None,
            "channel": item.channel,
            "final_decision": item.final_decision,
            "decision_reason": item.decision_reason,
            "decision_reason_label": _reason_label(item.decision_reason),
            "handoff_required": item.handoff_required,
            "guardrail_trigger": item.guardrail_trigger,
            "confidence": item.confidence,
            "latency_ms": item.latency_ms,
            "generated_response": item.generated_response,
            "created_at": item.created_at.isoformat(),
            "metadata": item.metadata_json,
        }
        for item in rows
    ]


def process_inbound_message(
    db: Session,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    inbound_message_id: UUID,
) -> dict[str, Any]:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id,
        )
    )
    inbound_message = db.scalar(
        select(Message).where(
            Message.id == inbound_message_id,
            Message.tenant_id == tenant_id,
            Message.direction == MessageDirection.INBOUND.value,
        )
    )
    if not conversation or not inbound_message:
        return {"status": "ignored", "reason": "context_not_found"}

    dedupe_key = f"inbound:{inbound_message.id}"
    existing = db.scalar(
        select(AIAutoresponderDecision).where(
            AIAutoresponderDecision.tenant_id == tenant_id,
            AIAutoresponderDecision.dedupe_key == dedupe_key,
        )
    )
    if existing:
        return {
            "status": "duplicate",
            "decision_id": str(existing.id),
            "final_decision": existing.final_decision,
            "reason": existing.decision_reason,
        }

    config = resolve_conversation_config(db, conversation=conversation)
    inbound_text = (inbound_message.body or "").strip()
    captured_profile: dict[str, str] = {}

    def finish_without_reply(*, final_decision: str, reason: str, handoff: bool, guardrail: str | None = None) -> dict[str, Any]:
        if handoff:
            _notify_handoff(
                db,
                conversation=conversation,
                inbound_message=inbound_message,
                reason=reason,
                config=config,
            )
        else:
            conversation.ai_autoresponder_last_decision = final_decision
            conversation.ai_autoresponder_last_reason = reason
            conversation.ai_autoresponder_last_at = datetime.now(UTC)
            if final_decision in {DECISION_BLOCKED, DECISION_IGNORED}:
                conversation.ai_autoresponder_consecutive_count = 0
            db.add(conversation)

        try:
            decision = _create_decision(
                db,
                tenant_id=tenant_id,
                conversation=conversation,
                inbound_message=inbound_message,
                dedupe_key=dedupe_key,
                final_decision=final_decision,
                decision_reason=reason,
                handoff_required=handoff,
                guardrail_trigger=guardrail,
                metadata=_build_metadata(config=config),
            )

            db.commit()
        except IntegrityError:
            db.rollback()
            existing_decision = db.scalar(
                select(AIAutoresponderDecision).where(
                    AIAutoresponderDecision.tenant_id == tenant_id,
                    AIAutoresponderDecision.dedupe_key == dedupe_key,
                )
            )
            if existing_decision:
                return {
                    "status": "duplicate",
                    "decision_id": str(existing_decision.id),
                    "final_decision": existing_decision.final_decision,
                    "reason": existing_decision.decision_reason,
                }
            raise
        if handoff:
            record_audit(
                db,
                action="ai_autoresponder.handoff",
                entity_type="conversation",
                entity_id=str(conversation.id),
                tenant_id=tenant_id,
                user_id=None,
                metadata={"reason": reason, "decision_id": str(decision.id)},
            )
            if reason in {"clinical_request_blocked", "urgency_detected", "patient_requested_human"}:
                record_audit(
                    db,
                    action="ai_autoresponder.blocked",
                    entity_type="conversation",
                    entity_id=str(conversation.id),
                    tenant_id=tenant_id,
                    user_id=None,
                    metadata={"reason": reason, "decision_id": str(decision.id)},
                )
        elif final_decision == DECISION_BLOCKED:
            record_audit(
                db,
                action="ai_autoresponder.blocked",
                entity_type="conversation",
                entity_id=str(conversation.id),
                tenant_id=tenant_id,
                user_id=None,
                metadata={"reason": reason, "decision_id": str(decision.id)},
            )
        payload: dict[str, Any] = {
            "status": final_decision,
            "decision_id": str(decision.id),
            "reason": reason,
            "reason_label": _reason_label(reason),
        }
        if captured_profile:
            payload["captured_profile"] = captured_profile
        return payload

    if not config.get("enabled"):
        return finish_without_reply(final_decision=DECISION_IGNORED, reason="disabled_global", handoff=False)

    if conversation.ai_autoresponder_enabled is False:
        return finish_without_reply(final_decision=DECISION_IGNORED, reason="disabled_conversation", handoff=False)

    if not (config.get("channels") or {}).get(conversation.channel, False):
        return finish_without_reply(final_decision=DECISION_IGNORED, reason="channel_disabled", handoff=False)

    if conversation.status == "finalizada":
        return finish_without_reply(final_decision=DECISION_IGNORED, reason="conversation_closed", handoff=False)

    if not inbound_text:
        return finish_without_reply(final_decision=DECISION_IGNORED, reason="empty_inbound", handoff=False)

    captured_profile = _capture_contact_profile_from_inbound(
        db,
        tenant_id=tenant_id,
        conversation=conversation,
        inbound_text=inbound_text,
    )

    human_request = _lookup_pattern(inbound_text, HUMAN_REQUEST_PATTERNS)
    if human_request:
        return finish_without_reply(
            final_decision=DECISION_HANDOFF,
            reason="patient_requested_human",
            handoff=True,
            guardrail=human_request,
        )

    urgency_pattern = _lookup_pattern(inbound_text, URGENCY_PATTERNS)
    if urgency_pattern:
        return finish_without_reply(
            final_decision=DECISION_HANDOFF,
            reason="urgency_detected",
            handoff=True,
            guardrail=urgency_pattern,
        )

    clinical_pattern = _lookup_pattern(inbound_text, CLINICAL_PATTERNS)
    if clinical_pattern:
        return finish_without_reply(
            final_decision=DECISION_HANDOFF,
            reason="clinical_request_blocked",
            handoff=True,
            guardrail=clinical_pattern,
        )

    if not _is_business_hours(config):
        outside_mode = config.get("outside_business_hours_mode")
        if outside_mode == "handoff":
            return finish_without_reply(final_decision=DECISION_HANDOFF, reason="outside_business_hours", handoff=True)
        if outside_mode == "silent":
            return finish_without_reply(
                final_decision=DECISION_BLOCKED,
                reason="outside_business_hours_silent",
                handoff=False,
            )

    consecutive_count = int(conversation.ai_autoresponder_consecutive_count or 0)
    max_consecutive = int(config.get("max_consecutive_auto_replies") or 3)
    if consecutive_count >= max_consecutive:
        return finish_without_reply(
            final_decision=DECISION_HANDOFF,
            reason="max_consecutive_reached",
            handoff=True,
        )

    context = _recent_context(db, tenant_id=tenant_id, conversation_id=conversation.id)
    destination = _conversation_destination_phone(db, conversation=conversation)
    if not destination:
        return finish_without_reply(
            final_decision=DECISION_HANDOFF,
            reason="missing_contact_phone",
            handoff=True,
        )

    if conversation.channel == "whatsapp":
        try:
            assert_whatsapp_account_ready_for_dispatch(db, tenant_id=tenant_id)
        except Exception:
            return finish_without_reply(
                final_decision=DECISION_HANDOFF,
                reason="whatsapp_not_ready",
                handoff=True,
            )

    scheduling_response = _build_scheduling_operation_response(
        db,
        conversation=conversation,
        inbound_message=inbound_message,
        inbound_text=inbound_text,
        context=context,
        config=config,
    )
    if scheduling_response:
        generated_response = _normalize_response_text(
            db,
            conversation=conversation,
            text=str(scheduling_response.get("response_text") or ""),
        )
        if not generated_response:
            return finish_without_reply(final_decision=DECISION_HANDOFF, reason="dispatch_error", handoff=True)
        interactive_payload = (
            _build_scheduling_interactive_list_payload(scheduling_response)
            if conversation.channel == "whatsapp"
            else None
        )
        outbound_message_type = "interactive_list" if interactive_payload else "text"
        dispatch_body = (
            str(interactive_payload.get("body_text") or generated_response)
            if interactive_payload
            else generated_response
        )
        try:
            outbound_message = Message(
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                direction=MessageDirection.OUTBOUND.value,
                channel=conversation.channel,
                sender_type="ai",
                body=generated_response,
                message_type=outbound_message_type,
                payload={
                    "source": "ai_autoresponder",
                    "mode": scheduling_response.get("mode"),
                    "reply_to_message_id": str(inbound_message.id),
                    "scheduling": scheduling_response.get("metadata") or {},
                    "interactive": interactive_payload,
                },
                status=MessageStatus.QUEUED.value,
            )
            db.add(outbound_message)
            db.flush()

            outbox = queue_outbound_message(
                db,
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                to=destination,
                body=dispatch_body,
                message_type=outbound_message_type,
                interactive=interactive_payload,
                metadata={
                    "source": "ai_autoresponder",
                    "mode": scheduling_response.get("mode"),
                    "inbound_message_id": str(inbound_message.id),
                    "outbound_message_id": str(outbound_message.id),
                },
            )

            outbound_payload = outbound_message.payload if isinstance(outbound_message.payload, dict) else {}
            outbound_payload["queued_outbox_id"] = str(outbox.id)
            outbound_message.payload = outbound_payload
            db.add(outbound_message)

            decision = _create_decision(
                db,
                tenant_id=tenant_id,
                conversation=conversation,
                inbound_message=inbound_message,
                dedupe_key=dedupe_key,
                final_decision=DECISION_RESPONDED,
                decision_reason="response_sent",
                generated_response=generated_response,
                confidence=None,
                llm_payload=None,
                metadata=_build_metadata(
                    config=config,
                    extra={
                        "outbox_id": str(outbox.id),
                        "outbound_message_id": str(outbound_message.id),
                        "knowledge_context_present": False,
                        "scheduling": scheduling_response.get("metadata") or {},
                        "scheduling_mode": scheduling_response.get("mode"),
                    },
                ),
                outbound_message_id=outbound_message.id,
            )

            conversation.ai_autoresponder_last_decision = DECISION_RESPONDED
            conversation.ai_autoresponder_last_reason = "response_sent"
            conversation.ai_autoresponder_last_at = datetime.now(UTC)
            conversation.ai_autoresponder_consecutive_count = consecutive_count + 1
            conversation.last_message_at = datetime.now(UTC)
            db.add(conversation)
            db.commit()

            appointment_id = (scheduling_response.get("metadata") or {}).get("appointment_id")
            if appointment_id:
                record_audit(
                    db,
                    action="appointment.create.ai",
                    entity_type="appointment",
                    entity_id=str(appointment_id),
                    tenant_id=tenant_id,
                    user_id=None,
                    metadata={"conversation_id": str(conversation.id), "source": "ai_autoresponder"},
                )
                if conversation.patient_id:
                    try:
                        emit_event(
                            db,
                            tenant_id=tenant_id,
                            event_key="consulta_criada",
                            payload={
                                "appointment_id": str(appointment_id),
                                "patient_id": str(conversation.patient_id),
                                "starts_at": (scheduling_response.get("metadata") or {}).get("starts_at_utc"),
                                "status": "agendada",
                            },
                        )
                    except Exception as exc:
                        logger.warning(
                            "ai_autoresponder.appointment_event_emit_failed",
                            tenant_id=str(tenant_id),
                            conversation_id=str(conversation.id),
                            appointment_id=str(appointment_id),
                            error=str(exc),
                        )

            payload: dict[str, Any] = {
                "status": DECISION_RESPONDED,
                "decision_id": str(decision.id),
                "outbox_id": str(outbox.id),
                "outbound_message_id": str(outbound_message.id),
                "reason": "response_sent",
                "reason_label": _reason_label("response_sent"),
                "scheduling_mode": scheduling_response.get("mode"),
                "scheduling": scheduling_response.get("metadata") or {},
            }
            if captured_profile:
                payload["captured_profile"] = captured_profile
            return payload
        except IntegrityError:
            db.rollback()
            existing_after_error = db.scalar(
                select(AIAutoresponderDecision).where(
                    AIAutoresponderDecision.tenant_id == tenant_id,
                    AIAutoresponderDecision.dedupe_key == dedupe_key,
                )
            )
            if existing_after_error:
                return {
                    "status": "duplicate",
                    "decision_id": str(existing_after_error.id),
                    "final_decision": existing_after_error.final_decision,
                    "reason": existing_after_error.decision_reason,
                }
            return finish_without_reply(final_decision=DECISION_HANDOFF, reason="dispatch_error", handoff=True)
        except Exception as exc:
            logger.exception(
                "ai_autoresponder.scheduling_dispatch_error",
                tenant_id=str(tenant_id),
                conversation_id=str(conversation.id),
                error=str(exc),
            )
            return finish_without_reply(final_decision=DECISION_HANDOFF, reason="dispatch_error", handoff=True)

    confidence = None
    try:
        intent_result = classify_intent(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            message=inbound_text,
        )
        parsed_intent = _parse_json_output(intent_result.get("output", ""))
        parsed_confidence = parsed_intent.get("confidence")
        if isinstance(parsed_confidence, (int, float)):
            confidence = float(parsed_confidence)
    except Exception as exc:
        logger.warning(
            "ai_autoresponder.intent_classification_failed",
            tenant_id=str(tenant_id),
            conversation_id=str(conversation.id),
            error=str(exc),
        )

    threshold = float(config.get("confidence_threshold") or 0.65)
    if confidence is not None and confidence < threshold:
        return finish_without_reply(
            final_decision=DECISION_HANDOFF,
            reason="low_confidence",
            handoff=True,
        )

    knowledge_base = get_knowledge_base_global_config(db, tenant_id=tenant_id)
    knowledge_context = _render_knowledge_context(knowledge_base)
    prompt = _prompt_for_autoresponder(
        config=config,
        context=context,
        inbound_text=inbound_text,
        knowledge_context=knowledge_context,
    )

    llm_payload: dict[str, Any] | None = None
    generated_response = ""
    started_at = perf_counter()
    try:
        llm_result = run_llm_task(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            task="auto_responder",
            prompt=prompt,
        )
        llm_payload = {"prompt": prompt, **llm_result}
        generated_response = _normalize_response_text(
            db,
            conversation=conversation,
            text=str(llm_result.get("output") or ""),
        )
    except Exception as exc:
        logger.exception(
            "ai_autoresponder.llm_error",
            tenant_id=str(tenant_id),
            conversation_id=str(conversation.id),
            error=str(exc),
        )
        return finish_without_reply(final_decision=DECISION_HANDOFF, reason="llm_error", handoff=True)

    if not generated_response:
        return finish_without_reply(final_decision=DECISION_HANDOFF, reason="llm_error", handoff=True)

    generated_clinical_pattern = _lookup_pattern(generated_response, CLINICAL_PATTERNS)
    if generated_clinical_pattern:
        return finish_without_reply(
            final_decision=DECISION_HANDOFF,
            reason="clinical_request_blocked",
            handoff=True,
            guardrail=generated_clinical_pattern,
        )

    if _looks_like_appointment_confirmation(generated_response):
        generated_response = (
            "Posso concluir seu agendamento agora. "
            "Me informe o número da opção escolhida ou a data e hora exatas (ex.: 16/04 às 09:00)."
        )

    try:
        outbound_message = Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            direction=MessageDirection.OUTBOUND.value,
            channel=conversation.channel,
            sender_type="ai",
            body=generated_response,
            message_type="text",
            payload={
                "source": "ai_autoresponder",
                "reply_to_message_id": str(inbound_message.id),
            },
            status=MessageStatus.QUEUED.value,
        )
        db.add(outbound_message)
        db.flush()

        outbox = queue_outbound_message(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            to=destination,
            body=generated_response,
            message_type="text",
            metadata={
                "source": "ai_autoresponder",
                "inbound_message_id": str(inbound_message.id),
                "outbound_message_id": str(outbound_message.id),
            },
        )

        outbound_payload = outbound_message.payload if isinstance(outbound_message.payload, dict) else {}
        outbound_payload["queued_outbox_id"] = str(outbox.id)
        outbound_message.payload = outbound_payload
        db.add(outbound_message)

        llm_metadata = llm_payload.get("metadata") if llm_payload else {}
        if isinstance(llm_metadata, dict) and "latency_ms" not in llm_metadata:
            llm_metadata["latency_ms"] = int((perf_counter() - started_at) * 1000)
            if llm_payload is not None:
                llm_payload["metadata"] = llm_metadata

        decision = _create_decision(
            db,
            tenant_id=tenant_id,
            conversation=conversation,
            inbound_message=inbound_message,
            dedupe_key=dedupe_key,
            final_decision=DECISION_RESPONDED,
            decision_reason="response_sent",
            generated_response=generated_response,
            confidence=confidence,
            llm_payload=llm_payload,
            metadata=_build_metadata(
                config=config,
                extra={
                    "outbox_id": str(outbox.id),
                    "outbound_message_id": str(outbound_message.id),
                    "knowledge_context_present": bool(knowledge_context),
                },
            ),
            outbound_message_id=outbound_message.id,
        )

        conversation.ai_autoresponder_last_decision = DECISION_RESPONDED
        conversation.ai_autoresponder_last_reason = "response_sent"
        conversation.ai_autoresponder_last_at = datetime.now(UTC)
        conversation.ai_autoresponder_consecutive_count = consecutive_count + 1
        conversation.last_message_at = datetime.now(UTC)
        db.add(conversation)
        db.commit()

        record_audit(
            db,
            action="ai_autoresponder.response_sent",
            entity_type="conversation",
            entity_id=str(conversation.id),
            tenant_id=tenant_id,
            user_id=None,
            metadata={
                "decision_id": str(decision.id),
                "outbox_id": str(outbox.id),
                "inbound_message_id": str(inbound_message.id),
                "outbound_message_id": str(outbound_message.id),
            },
        )

        payload: dict[str, Any] = {
            "status": DECISION_RESPONDED,
            "decision_id": str(decision.id),
            "outbox_id": str(outbox.id),
            "outbound_message_id": str(outbound_message.id),
            "reason": "response_sent",
            "reason_label": _reason_label("response_sent"),
        }
        if captured_profile:
            payload["captured_profile"] = captured_profile
        return payload
    except IntegrityError:
        db.rollback()
        existing_after_error = db.scalar(
            select(AIAutoresponderDecision).where(
                AIAutoresponderDecision.tenant_id == tenant_id,
                AIAutoresponderDecision.dedupe_key == dedupe_key,
            )
        )
        if existing_after_error:
            return {
                "status": "duplicate",
                "decision_id": str(existing_after_error.id),
                "final_decision": existing_after_error.final_decision,
                "reason": existing_after_error.decision_reason,
            }
        return finish_without_reply(final_decision=DECISION_HANDOFF, reason="dispatch_error", handoff=True)
    except Exception as exc:
        logger.exception(
            "ai_autoresponder.dispatch_error",
            tenant_id=str(tenant_id),
            conversation_id=str(conversation.id),
            error=str(exc),
        )
        return finish_without_reply(final_decision=DECISION_HANDOFF, reason="dispatch_error", handoff=True)


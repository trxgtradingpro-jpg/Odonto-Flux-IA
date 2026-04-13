from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
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
    Conversation,
    Lead,
    Message,
    MessageEvent,
    Patient,
    Setting,
    User,
)
from app.models.enums import MessageDirection, MessageStatus
from app.services.audit_service import record_audit
from app.services.llm_service import classify_intent, run_llm_task
from app.services.whatsapp_service import assert_whatsapp_account_ready_for_dispatch, queue_outbound_message

AI_AUTORESPONDER_PROMPT_VERSION = "v1.0"

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
        f"{knowledge_section}"
        f"Histórico recente:\n{context}\n\n"
        f"Mensagem do paciente:\n{inbound_text}\n\n"
        "Gere apenas a resposta final ao paciente."
    )


def _reason_label(reason: str) -> str:
    return REASON_LABELS.get(reason, reason.replace("_", " ").capitalize())


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
        return {
            "status": final_decision,
            "decision_id": str(decision.id),
            "reason": reason,
            "reason_label": _reason_label(reason),
        }

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

    context = _recent_context(db, tenant_id=tenant_id, conversation_id=conversation.id)
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
        generated_response = (llm_result.get("output") or "").strip()
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

    try:
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
            },
        )

        outbound_message = Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            direction=MessageDirection.OUTBOUND.value,
            channel=conversation.channel,
            sender_type="ai",
            body=generated_response,
            message_type="text",
            payload={
                "queued_outbox_id": str(outbox.id),
                "source": "ai_autoresponder",
                "reply_to_message_id": str(inbound_message.id),
            },
            status=MessageStatus.QUEUED.value,
        )
        db.add(outbound_message)
        db.flush()

        outbox_payload = outbox.payload or {}
        metadata = outbox_payload.get("metadata") if isinstance(outbox_payload.get("metadata"), dict) else {}
        metadata["outbound_message_id"] = str(outbound_message.id)
        outbox_payload["metadata"] = metadata
        outbox.payload = outbox_payload
        db.add(outbox)

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

        return {
            "status": DECISION_RESPONDED,
            "decision_id": str(decision.id),
            "outbox_id": str(outbox.id),
            "outbound_message_id": str(outbound_message.id),
            "reason": "response_sent",
            "reason_label": _reason_label("response_sent"),
        }
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


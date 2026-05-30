"""Offline outreach intelligence helpers for ClinicFlux AI.

This module intentionally uses only Python stdlib so it can run in local tests,
CI, or a one-off operator script without Docker, Postgres, Redis, or external
LLM providers.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

NEXT_ACTIONS = {
    "send_message",
    "ask_for_responsible",
    "send_demo",
    "send_video",
    "send_summary",
    "book_meeting",
    "wait",
    "follow_up",
    "stop_contact",
    "reply_contextually",
    "send_second_commercial_clarification",
    "use_approved_template_only",
    "stop_contact_or_use_approved_template_only",
    "switch_to_website_offer",
    "switch_to_clinicflux_ai_offer",
    "send_proposal",
}

FALSE_PROMISE_PATTERNS = [
    r"\bgarantid[oa]s?\b",
    r"\bagenda cheia\b",
    r"\blotar sua agenda\b",
    r"\b\d+\s+pacientes\b",
    r"\bfaturamento\b",
    r"\bperdera\s+\d+\b",
    r"\bintegra(?:mos|cao)?\s+com\b",
]

STOP_CONTACT_PATTERNS = [
    "nao tenho interesse",
    "sem interesse",
    "parem de mandar",
    "nao chamar",
    "remover contato",
    "nao quero",
]

SOURCE_QUESTION_PATTERNS = [
    "como achou",
    "como encontrou",
    "como encontraram",
    "como voces",
    "de onde",
    "qual busca",
    "o que pesquisou",
    "onde viu",
]

PRICE_PATTERNS = [
    "preco",
    "valor",
    "quanto custa",
    "mensalidade",
    "investimento",
]

DEMO_PATTERNS = [
    "demo",
    "demonstracao",
    "teste",
    "testar",
]

MEETING_PATTERNS = [
    "reuniao",
    "call",
    "conversa",
    "horario",
    "marcar",
]

IMPLEMENTATION_PATTERNS = [
    "implementar",
    "implantacao",
    "integracao",
    "integra",
    "agenda",
    "whatsapp",
    "detalhes tecnicos",
    "prazo",
]

PERMISSION_TO_SEND_PATTERNS = [
    "pode mandar",
    "manda",
    "pode enviar",
    "envia",
]

HUMAN_CONTEXT_PATTERNS = [
    "sobre o que seria",
    "quem fala",
    "como funciona",
    "pode explicar",
    "explica melhor",
    "fala com",
    "qual o valor",
    "pode mandar",
    "bom dia",
    "boa tarde",
    "boa noite",
]

AUTO_REPLY_TEXT_PATTERNS = [
    "mensagem automatica",
    "atendimento automatico",
    "bem vindo",
    "bem-vindo",
    "bem vinda",
    "bem-vinda",
    "digite",
    "escolha uma opcao",
    "menu",
    "informe seu nome",
    "qual procedimento",
    "para agendamento",
    "responderemos em breve",
    "fora do horario",
]

COLD_LEAD_SOURCES = {
    "google",
    "google search",
    "google places",
    "google maps",
    "instagram",
    "local serp",
    "manual",
    "prospecting list",
    "public site",
    "public website",
    "site publico",
    "unknown",
}

AUTO_REPLY_TYPES = {
    "auto reply",
    "autoreply",
    "automatic",
    "automatic reply",
    "automation",
    "automatica",
}

AUTO_REPLY_PERSONAS = {
    "automation",
    "automated",
}

HUMAN_REPLY_TYPES = {
    "human reply",
    "asked source",
    "asked price",
    "asked info",
    "permission to send",
    "objection",
    "decline",
    "positive",
    "neutral",
    "question",
    "source question",
    "price objection",
    "not responsible",
    "refusal",
}

HUMAN_OPT_IN_STATUSES = {
    "explicit opt in",
    "human replied",
    "requested information",
}

STOP_OPT_IN_STATUSES = {
    "do not contact",
}

ANALYSIS_MODES = {"economico", "profissional", "elite_300"}
TOKEN_BUDGET_LEVELS = {"low", "medium", "high"}
TOKEN_COST_LEVELS = {"low", "medium", "high", "very_high"}
DATA_LOADING_STRATEGIES = {
    "minimal",
    "lead_profile_only",
    "recent_events_only",
    "aggregated_summary",
    "full_campaign_analysis",
}


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return _normalize_text(value) in {"1", "true", "sim", "yes", "y"}
    return bool(value)


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _normalize_text(value: str) -> str:
    normalized = value.lower()
    normalized = re.sub(r"https?://\S+", " link ", normalized)
    normalized = re.sub(r"[^a-z0-9A-Z\u00c0-\u017f]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _tokens(value: str) -> set[str]:
    return {token for token in _normalize_text(value).split() if len(token) > 2}


def _clamp_score(value: float | int) -> int:
    return int(max(0, min(100, round(float(value)))))


def _contains_any(text: str, patterns: list[str]) -> bool:
    normalized = _normalize_text(text)
    return any(pattern in normalized for pattern in patterns)


def _contains_regex_any(text: str, patterns: list[str]) -> bool:
    normalized = _normalize_text(text)
    return any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in patterns)


def _is_auto_reply_text(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False
    if _contains_any(normalized, AUTO_REPLY_TEXT_PATTERNS):
        return True
    return "opcao" in normalized and any(char.isdigit() for char in normalized)


def _latest_reply(context: dict[str, Any]) -> str:
    return _as_text(context.get("latest_reply") or context.get("last_reply") or context.get("clinic_reply"))


def _cold_outreach_message_count(context: dict[str, Any]) -> int:
    if "cold_outreach_message_count" in context:
        return max(0, _as_int(context.get("cold_outreach_message_count")))
    history = context.get("history") or {}
    if isinstance(history, dict):
        return max(0, _as_int(history.get("previous_outbound_count")))
    return 0


def _auto_reply_received(context: dict[str, Any]) -> bool:
    if _as_bool(context.get("auto_reply_received")):
        return True
    reply_type = _normalize_text(_as_text(context.get("reply_type")))
    detected_persona = _normalize_text(_as_text(context.get("detected_persona")))
    latest_classification = _normalize_text(_as_text(context.get("latest_inbound_classification")))
    latest_reply = _latest_reply(context)
    return (
        reply_type in AUTO_REPLY_TYPES
        or detected_persona in AUTO_REPLY_PERSONAS
        or latest_classification in AUTO_REPLY_TYPES
        or _is_auto_reply_text(latest_reply)
    )


def _human_reply_received(context: dict[str, Any]) -> bool:
    if _as_bool(context.get("human_reply_received")):
        return True
    if _as_bool(context.get("first_human_message_received")):
        return True
    if _as_text(context.get("last_human_reply_at")):
        return True
    if _as_text(context.get("first_human_message_at")):
        return True
    opt_in_status = _normalize_text(_as_text(context.get("opt_in_status")))
    if opt_in_status in HUMAN_OPT_IN_STATUSES:
        return True
    reply_type = _normalize_text(_as_text(context.get("reply_type")))
    if reply_type in HUMAN_REPLY_TYPES:
        return True
    latest_reply = _latest_reply(context)
    if latest_reply and not _auto_reply_received(context):
        if context.get("clinic_replied") is not False:
            return True
        return _contains_any(latest_reply, HUMAN_CONTEXT_PATTERNS)
    return False


def _is_cold_lead_context(context: dict[str, Any]) -> bool:
    if _as_bool(context.get("is_cold_lead")):
        return True
    if _human_reply_received(context):
        return False
    opt_in_status = _normalize_text(_as_text(context.get("opt_in_status")))
    if opt_in_status in HUMAN_OPT_IN_STATUSES:
        return False
    source = _normalize_text(_as_text(context.get("source")))
    lead_temperature = _normalize_text(_as_text(context.get("lead_temperature")))
    return lead_temperature == "cold" or source in COLD_LEAD_SOURCES or opt_in_status in {"unknown", "public business contact"}


def _outside_24h_freeform_block_required(context: dict[str, Any]) -> bool:
    return (
        _as_bool(context.get("outside_24h_window"))
        and not _human_reply_received(context)
        and _as_bool(context.get("template_required"))
        and not _as_bool(context.get("template_used"))
    )


def _first_human_message_received(context: dict[str, Any]) -> bool:
    if _as_bool(context.get("first_human_message_received")):
        return True
    if _as_text(context.get("first_human_message_at")):
        return True
    latest_reply = _latest_reply(context)
    if not latest_reply or _auto_reply_received(context):
        return False
    return _as_bool(context.get("clinic_sent_first_today")) or _as_int(context.get("cold_outreach_message_count")) == 0


def _strong_buying_signal(context: dict[str, Any]) -> str:
    latest = _normalize_text(_latest_reply(context))
    detected_intent = _normalize_text(_as_text(context.get("detected_intent")))
    objection = _normalize_text(_as_text(context.get("objection_type")))
    stage = _normalize_text(_as_text(context.get("stage_reached") or context.get("current_stage")))

    if _contains_any(latest, PRICE_PATTERNS) or objection == "price" or detected_intent == "ask price":
        return "asked_price"
    if _contains_any(latest, DEMO_PATTERNS) or detected_intent == "request demo":
        return "requested_demo"
    if "proposta" in latest or stage == "proposal sent":
        return "requested_proposal"
    if _contains_any(latest, MEETING_PATTERNS) or stage == "meeting booked" or _as_bool(context.get("meeting_booked")):
        return "requested_meeting"
    if _contains_any(latest, IMPLEMENTATION_PATTERNS):
        return "implementation_or_integration_question"
    if stage in {"demo clicked", "whatsapp tested"} or _as_bool(context.get("demo_clicked")) or _as_bool(context.get("whatsapp_tested")):
        return "demo_engagement"
    if "responsavel" in latest or stage == "responsible identified":
        return "responsible_routing"
    return ""


def token_efficiency_policy(context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Choose the smallest analysis mode that can make a safe decision."""

    context = context or {}
    task = _normalize_text(_as_text(context.get("analysis_task") or context.get("task_type")))
    human_reply = _human_reply_received(context)
    auto_reply = _auto_reply_received(context)
    cold_lead = _is_cold_lead_context(context)
    strong_signal = _strong_buying_signal(context)

    if task in {"weekly report", "weekly summary", "campaign analysis", "report"}:
        return {
            "analysis_mode": "elite_300",
            "token_efficiency_mode": "elite_300",
            "token_budget_level": "high",
            "should_use_elite_mode": True,
            "elite_mode_reason": "weekly_report_uses_aggregated_campaign_analysis",
            "estimated_token_cost_level": "high",
            "data_loading_strategy": "aggregated_summary",
            "large_context_allowed": True,
        }

    if task in {"skill update suggestion", "skill improvement", "commercial brain update"}:
        return {
            "analysis_mode": "elite_300",
            "token_efficiency_mode": "elite_300",
            "token_budget_level": "high",
            "should_use_elite_mode": True,
            "elite_mode_reason": "skill_update_suggestion_requires_human_approval",
            "estimated_token_cost_level": "very_high",
            "data_loading_strategy": "full_campaign_analysis",
            "large_context_allowed": True,
        }

    if (cold_lead and not human_reply) or auto_reply or _outside_24h_freeform_block_required(context):
        return {
            "analysis_mode": "economico",
            "token_efficiency_mode": "economico",
            "token_budget_level": "low",
            "should_use_elite_mode": False,
            "elite_mode_reason": "elite_blocked_for_cold_lead_without_human_reply",
            "estimated_token_cost_level": "low",
            "data_loading_strategy": "minimal",
            "large_context_allowed": False,
        }

    if human_reply and strong_signal:
        return {
            "analysis_mode": "elite_300",
            "token_efficiency_mode": "elite_300",
            "token_budget_level": "high",
            "should_use_elite_mode": True,
            "elite_mode_reason": strong_signal,
            "estimated_token_cost_level": "high",
            "data_loading_strategy": "recent_events_only",
            "large_context_allowed": True,
        }

    if human_reply:
        return {
            "analysis_mode": "profissional",
            "token_efficiency_mode": "profissional",
            "token_budget_level": "medium",
            "should_use_elite_mode": False,
            "elite_mode_reason": "",
            "estimated_token_cost_level": "medium",
            "data_loading_strategy": "lead_profile_only" if _first_human_message_received(context) else "recent_events_only",
            "large_context_allowed": False,
        }

    return {
        "analysis_mode": "economico",
        "token_efficiency_mode": "economico",
        "token_budget_level": "low",
        "should_use_elite_mode": False,
        "elite_mode_reason": "smallest_safe_mode_for_simple_decision",
        "estimated_token_cost_level": "low",
        "data_loading_strategy": "minimal",
        "large_context_allowed": False,
    }


def text_similarity(first: str, second: str) -> float:
    """Return a simple Jaccard similarity score between two short messages."""

    first_tokens = _tokens(first)
    second_tokens = _tokens(second)
    if not first_tokens or not second_tokens:
        return 0.0
    return len(first_tokens & second_tokens) / len(first_tokens | second_tokens)


def _max_similarity(message: str, previous_messages: list[str]) -> float:
    if not previous_messages:
        return 0.0
    return max(text_similarity(message, previous) for previous in previous_messages)


def _detect_offer_lane(context: dict[str, Any]) -> str:
    explicit = _as_text(context.get("offer_lane"))
    if explicit:
        return explicit
    has_website = bool(context.get("has_website"))
    website_quality = _as_text(context.get("website_quality")) or "unknown"
    if not has_website or website_quality == "none":
        return "website_seo"
    if website_quality in {"weak", "unknown"}:
        return "audit"
    return "clinicflux_ai"


def _answer_latest_reply_score(message: str, latest_reply: str) -> tuple[int, list[str]]:
    if not latest_reply:
        return 85, []

    normalized_reply = _normalize_text(latest_reply)
    normalized_message = _normalize_text(message)
    issues: list[str] = []
    score = 80

    if _contains_any(normalized_reply, SOURCE_QUESTION_PATTERNS):
        if "google" in normalized_message or "busca" in normalized_message:
            score += 18
        else:
            score -= 35
            issues.append("Nao respondeu diretamente como a clinica foi encontrada.")

    if _contains_any(normalized_reply, PRICE_PATTERNS):
        if any(term in normalized_message for term in ["valor", "preco", "investimento", "plano", "demo"]):
            score += 10
        else:
            score -= 25
            issues.append("Nao respondeu a pergunta sobre preco ou investimento.")

    if any(term in normalized_reply for term in ["quem e", "quem sao", "o que e"]):
        if "clinicflux" in normalized_message and "comercial" in normalized_message:
            score += 10
        else:
            score -= 20
            issues.append("Nao esclareceu identidade comercial com ClinicFlux AI.")

    return _clamp_score(score), issues


def _commercial_clarity_score(message: str) -> tuple[int, list[str]]:
    normalized = _normalize_text(message)
    score = 45
    issues: list[str] = []

    if "clinicflux" in normalized:
        score += 25
    else:
        issues.append("Mensagem nao cita ClinicFlux AI.")
    if "comercial" in normalized:
        score += 25
    else:
        issues.append("Mensagem nao deixa claro que e contato comercial.")
    if any(term in normalized for term in ["paciente", "consulta", "agendar uma consulta"]) and "nao e para agendamento" not in normalized:
        score -= 25
        issues.append("Mensagem pode parecer contato de paciente.")

    return _clamp_score(score), issues


def _one_objective_score(message: str) -> tuple[int, list[str]]:
    questions = message.count("?")
    separators = len(re.findall(r"\b(e tambem|alem disso|aproveitando|ou ainda)\b", _normalize_text(message)))
    word_count = len(message.split())
    score = 100 - max(0, questions - 1) * 22 - separators * 12
    issues: list[str] = []

    if questions > 1:
        issues.append("Mensagem tem mais de uma pergunta.")
    if separators:
        issues.append("Mensagem parece misturar objetivos.")
    if word_count > 95:
        score -= 15
        issues.append("Mensagem longa demais para WhatsApp frio.")
    return _clamp_score(score), issues


def _whatsapp_naturalness_score(message: str) -> tuple[int, list[str]]:
    score = 100
    issues: list[str] = []
    if len(message) > 520:
        score -= 30
        issues.append("Mensagem longa demais para WhatsApp.")
    if "\n\n" in message:
        score -= 10
        issues.append("Mensagem tem blocos longos.")
    if "!!!" in message or "???" in message:
        score -= 18
        issues.append("Pontuacao exagerada aumenta pressao.")
    if _contains_regex_any(message, [r"\bimperdivel\b", r"\burgente\b", r"\bagora mesmo\b"]):
        score -= 20
        issues.append("Linguagem de pressao nao combina com outreach frio.")
    return _clamp_score(score), issues


def _repetition_score(message: str, previous_messages: list[str], answered_questions: list[str]) -> tuple[int, list[str]]:
    max_similarity = _max_similarity(message, previous_messages)
    score = 100 - int(max_similarity * 100)
    issues: list[str] = []

    if max_similarity >= 0.72:
        issues.append("Mensagem parecida demais com envio anterior.")

    normalized_message = _normalize_text(message)
    for answered in answered_questions:
        normalized_answered = _normalize_text(answered)
        if normalized_answered and normalized_answered in normalized_message:
            score -= 20
            issues.append(f"Mensagem repete ponto ja respondido: {answered}")
            break

    return _clamp_score(score), issues


def _risk_score(message: str, issues: list[str]) -> tuple[int, list[str]]:
    normalized = _normalize_text(message)
    risk = 0
    risk_reasons: list[str] = []
    simulated_patient_demo = "como se fosse um paciente" in normalized

    if _contains_regex_any(message, FALSE_PROMISE_PATTERNS):
        risk += 45
        risk_reasons.append("Possivel promessa comercial exagerada ou nao comprovada.")
    if "comercial" not in normalized:
        risk += 18
        risk_reasons.append("Identidade comercial pouco clara.")
    if "clinicflux" not in normalized:
        risk += 14
        risk_reasons.append("Marca ou identidade ausente.")
    if any(term in normalized for term in ["paciente", "consulta"]) and "comercial" not in normalized and not simulated_patient_demo:
        risk += 25
        risk_reasons.append("Risco de parecer paciente.")
    if any(term in normalized for term in ["quero agendar", "marcar consulta", "sou paciente", "preciso de consulta"]):
        risk += 45
        risk_reasons.append("Mensagem parece fingir interesse de paciente.")
    if any("parecida demais" in issue for issue in issues):
        risk += 22
        risk_reasons.append("Risco de repeticao percebida.")
    if any("Nao respondeu" in issue for issue in issues):
        risk += 20
        risk_reasons.append("Risco de ignorar pergunta direta da clinica.")

    return _clamp_score(risk), risk_reasons


def _burn_risk_from_score(risk_score: int) -> str:
    if risk_score >= 75:
        return "critical"
    if risk_score >= 50:
        return "high"
    if risk_score >= 28:
        return "medium"
    return "low"


def classify_cold_outreach_state(context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Classify cold WhatsApp outreach state without treating automation as opt-in."""

    context = context or {}
    cold_count = _cold_outreach_message_count(context)
    auto_reply = _auto_reply_received(context)
    human_reply = _human_reply_received(context)
    cold_lead = _is_cold_lead_context(context)
    first_human = _first_human_message_received(context)
    token_policy = token_efficiency_policy(context)

    base = {
        "auto_reply_received": auto_reply,
        "human_reply_received": human_reply,
        "first_human_message_received": first_human,
        "first_human_message_at": _as_text(context.get("first_human_message_at")) or None,
        "last_human_reply_at": _as_text(context.get("last_human_reply_at")) or (_now_iso() if human_reply and first_human else None),
        "reply_type": _as_text(context.get("reply_type")) or ("auto_reply" if auto_reply else ("human_reply" if human_reply else "none")),
        "detected_persona": _as_text(context.get("detected_persona")) or ("automation" if auto_reply else "unknown"),
        "interest_level": _as_text(context.get("interest_level")) or "unknown",
        "recommended_action": "send_message",
        "max_remaining_cold_messages": max(0, 2 - cold_count),
        "do_not_follow_up": False,
        "opt_in_status": "human_replied" if human_reply else (_as_text(context.get("opt_in_status")) or "public_business_contact"),
        "outside_24h_window": False if human_reply else _as_bool(context.get("outside_24h_window")),
        **token_policy,
    }

    if _normalize_text(_as_text(context.get("opt_in_status"))) in STOP_OPT_IN_STATUSES or _as_bool(context.get("do_not_contact")):
        return {
            **base,
            "reply_type": "decline",
            "recommended_action": "stop_contact",
            "max_remaining_cold_messages": 0,
            "do_not_follow_up": True,
            "do_not_contact": True,
            "stop_contact_required": True,
        }

    if _outside_24h_freeform_block_required(context):
        return {
            **base,
            "reply_type": base["reply_type"],
            "recommended_action": "stop_contact_or_use_approved_template_only",
            "max_remaining_cold_messages": 0 if cold_lead and not human_reply else base["max_remaining_cold_messages"],
            "do_not_follow_up": True,
        }

    if human_reply:
        return {
            **base,
            "reply_type": _as_text(context.get("reply_type")) or "human_reply",
            "detected_persona": _as_text(context.get("detected_persona")) or "reception",
            "recommended_action": "reply_contextually",
            "max_remaining_cold_messages": 2,
            "do_not_follow_up": False,
            "risk_score": 15,
        }

    if not cold_lead:
        return base

    if cold_count >= 2:
        return {
            **base,
            "reply_type": "no_human_reply_after_second_message",
            "recommended_action": "stop_contact",
            "max_remaining_cold_messages": 0,
            "do_not_follow_up": True,
        }

    if auto_reply and cold_count == 1:
        return {
            **base,
            "reply_type": "auto_reply",
            "detected_persona": "automation",
            "recommended_action": "send_second_commercial_clarification",
            "max_remaining_cold_messages": 1,
        }

    if cold_count == 0:
        return {
            **base,
            "recommended_action": "send_first_cold_message",
            "max_remaining_cold_messages": 2,
        }

    return {
        **base,
        "recommended_action": "wait",
        "max_remaining_cold_messages": 1,
    }


def _apply_cold_outreach_risk_policy(
    message: str,
    context: dict[str, Any],
    risk_score: int,
) -> tuple[int, list[str]]:
    cold_count = _cold_outreach_message_count(context)
    cold_lead = _is_cold_lead_context(context)
    human_reply = _human_reply_received(context)
    auto_reply = _auto_reply_received(context)
    normalized = _normalize_text(message)
    policy_reasons: list[str] = []
    has_link = " link " in f" {normalized} " or "demo" in normalized and "http" in message.lower()
    word_count = len(message.split())

    if _outside_24h_freeform_block_required(context):
        policy_reasons.append("Mensagem livre fora da janela de 24h sem resposta humana e sem template aprovado.")
        return max(risk_score, 88), policy_reasons

    if not cold_lead or human_reply:
        return risk_score, policy_reasons

    if cold_count >= 3:
        policy_reasons.append("Quarta mensagem fria sem resposta humana deve ser bloqueada.")
        return max(risk_score, 95), policy_reasons

    if cold_count >= 2:
        policy_reasons.append("Terceira mensagem fria sem resposta humana deve ser bloqueada.")
        return max(risk_score, 80), policy_reasons

    if has_link:
        policy_reasons.append("Link de demo antes de resposta humana em lead frio deve ser bloqueado.")
        return max(risk_score, 78), policy_reasons

    if cold_count == 1 and auto_reply:
        transparent = "comercial" in normalized and "clinicflux" in normalized
        short = word_count <= 55
        pitch_heavy = "nossa plataforma ajuda" in normalized or "varias melhorias" in normalized
        if pitch_heavy:
            policy_reasons.append("Pitch longo apos resposta automatica aumenta risco de spam.")
            return max(risk_score, 70), policy_reasons
        if transparent and short:
            policy_reasons.append("Segunda mensagem apos resposta automatica permitida apenas como esclarecimento curto.")
            return max(risk_score, 35), policy_reasons
        if not short:
            policy_reasons.append("Pitch longo apos resposta automatica aumenta risco de spam.")
            return max(risk_score, 70), policy_reasons
        policy_reasons.append("Segunda mensagem apos resposta automatica precisa ser comercialmente transparente.")
        return max(risk_score, 60), policy_reasons

    if cold_count == 0:
        policy_reasons.append("Primeira mensagem fria personalizada tem risco comercial moderado.")
        return max(risk_score, 40), policy_reasons

    return risk_score, policy_reasons


def _build_corrected_message(message: str, context: dict[str, Any], blocked_reasons: list[str]) -> str:
    clinic_name = _as_text(context.get("clinic_name")) or "a clinica"
    latest_reply = _as_text(context.get("latest_reply"))
    offer_lane = _detect_offer_lane(context)
    city = _as_text(context.get("city"))
    location = f" em {city}" if city else " na regiao"

    if _contains_any(latest_reply, SOURCE_QUESTION_PATTERNS):
        return (
            f"Encontrei voces no Google pesquisando por clinica odontologica{location}. "
            "Meu contato e comercial: a ideia e mostrar uma oportunidade simples para melhorar site, "
            "WhatsApp e agendamentos. Quem cuida dessa parte por ai?"
        )

    if _contains_any(latest_reply, PRICE_PATTERNS):
        return (
            "Consigo te passar uma nocao, mas para nao chutar valor errado eu prefiro primeiro entender se faz "
            "mais sentido site/SEO, ClinicFlux AI ou uma demo curta. Posso te mandar um resumo objetivo?"
        )

    if offer_lane == "website_seo":
        return (
            f"Oi, tudo bem? Encontrei {clinic_name} no Google e vi oportunidade de fortalecer site, mapa e WhatsApp. "
            "Aqui e o time comercial da ClinicFlux AI. Posso falar com quem cuida de marketing ou agendamentos?"
        )

    if offer_lane == "audit":
        return (
            f"Oi, tudo bem? Encontrei {clinic_name} no Google. Meu contato e comercial da ClinicFlux AI: posso te "
            "enviar uma auditoria curta com pontos de site, WhatsApp e agendamentos?"
        )

    return (
        f"Oi, tudo bem? Encontrei {clinic_name} no Google. Aqui e o time comercial da ClinicFlux AI. "
        "A ideia e mostrar como organizar respostas no WhatsApp e agendamentos. Posso falar com quem cuida disso?"
    )


def _judge(score: int, reason: str) -> dict[str, Any]:
    return {"score": _clamp_score(score), "reason": reason}


def _digital_twin(approved: bool, burn_risk: str) -> dict[str, dict[str, str]]:
    if approved:
        return {
            "busy_receptionist": {
                "reaction": "Entende rapido que e comercial e pode encaminhar.",
                "risk": "Pode ignorar se estiver atendendo pacientes.",
                "suggestion": "Manter uma pergunta curta.",
            },
            "skeptical_owner": {
                "reaction": "Avalia melhor porque origem e identidade estao claras.",
                "risk": "Pode desconfiar se faltar detalhe real da clinica.",
                "suggestion": "Adicionar detalhe verdadeiro quando disponivel.",
            },
            "busy_dentist": {
                "reaction": "Prefere resumo objetivo ou demo curta.",
                "risk": "Pode abandonar se houver pitch longo.",
                "suggestion": "Evitar explicar o produto inteiro.",
            },
            "cold_lead": {
                "reaction": "Pode responder perguntando origem ou assunto.",
                "risk": "Baixo se a mensagem nao pressionar.",
                "suggestion": "Responder pergunta direta antes de vender.",
            },
            "interested_lead": {
                "reaction": "Pode aceitar demo ou encaminhar responsavel.",
                "risk": "Perder timing se pedir dados demais.",
                "suggestion": "Oferecer uma proxima acao simples.",
            },
        }

    risk_text = "alto" if burn_risk in {"high", "critical"} else "medio"
    return {
        "busy_receptionist": {
            "reaction": "Pode arquivar a mensagem por parecer confusa ou repetida.",
            "risk": f"Risco {risk_text} de nao encaminhar.",
            "suggestion": "Reescrever com identidade, fonte e uma unica pergunta.",
        },
        "skeptical_owner": {
            "reaction": "Pode interpretar como automacao generica.",
            "risk": f"Risco {risk_text} de perda de confianca.",
            "suggestion": "Remover promessa exagerada e usar contexto real.",
        },
        "busy_dentist": {
            "reaction": "Pode ignorar se a mensagem exigir muito tempo.",
            "risk": f"Risco {risk_text} de baixa resposta.",
            "suggestion": "Reduzir para uma frase e uma decisao.",
        },
        "cold_lead": {
            "reaction": "Pode nao entender por que recebeu o contato.",
            "risk": f"Risco {risk_text} de queimar abertura.",
            "suggestion": "Explicar origem antes do pitch.",
        },
        "interested_lead": {
            "reaction": "Pode pedir clareza antes de seguir.",
            "risk": f"Risco {risk_text} de atrasar conversao.",
            "suggestion": "Dar proxima acao concreta.",
        },
    }


def evaluate_message(message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Evaluate an outbound message before it is presented or sent."""

    context = context or {}
    previous_messages = list(context.get("previous_messages") or [])
    answered_questions = list(context.get("answered_questions") or [])
    latest_reply = _as_text(context.get("latest_reply"))
    normalized_message_for_policy = _normalize_text(message)
    permission_context = (
        _human_reply_received(context)
        and (
            _normalize_text(_as_text(context.get("reply_type"))) == "permission to send"
            or _contains_any(_latest_reply(context), PERMISSION_TO_SEND_PATTERNS)
        )
        and "demo" in normalized_message_for_policy
    )

    commercial_score, commercial_issues = _commercial_clarity_score(message)
    if permission_context:
        commercial_score = max(commercial_score, 80)
        commercial_issues = [
            issue
            for issue in commercial_issues
            if issue
            not in {
                "Mensagem nao cita ClinicFlux AI.",
                "Mensagem nao deixa claro que e contato comercial.",
                "Mensagem pode parecer contato de paciente.",
            }
        ]
    latest_reply_score, latest_reply_issues = _answer_latest_reply_score(message, latest_reply)
    objective_score, objective_issues = _one_objective_score(message)
    repetition_score, repetition_issues = _repetition_score(message, previous_messages, answered_questions)
    naturalness_score, naturalness_issues = _whatsapp_naturalness_score(message)

    context_score = latest_reply_score
    if context.get("clinic_name") and _normalize_text(context["clinic_name"]) in _normalize_text(message):
        context_score += 5
    if context.get("source") in {"google_places", "google_maps", "local_serp"} and "google" in _normalize_text(message):
        context_score += 8
    context_score = _clamp_score(context_score)

    all_issues = (
        commercial_issues
        + latest_reply_issues
        + objective_issues
        + repetition_issues
        + naturalness_issues
    )
    risk_score, risk_reasons = _risk_score(message, all_issues)
    risk_score, policy_reasons = _apply_cold_outreach_risk_policy(message, context, risk_score)
    risk_reasons += policy_reasons
    if permission_context:
        risk_score = max(10, risk_score - 32)
        risk_reasons = [
            reason
            for reason in risk_reasons
            if reason not in {"Identidade comercial pouco clara.", "Marca ou identidade ausente.", "Risco de parecer paciente."}
        ]
    if _human_reply_received(context) and not _strong_buying_signal(context) and risk_score < 10:
        risk_score = 15
        risk_reasons.append("Resposta humana real reduz risco, mas contato comercial ainda exige cuidado.")
    burn_risk = _burn_risk_from_score(risk_score)
    cold_policy = classify_cold_outreach_state(context)
    token_policy = token_efficiency_policy(context)

    quality_score = _clamp_score(
        commercial_score * 0.2
        + context_score * 0.25
        + objective_score * 0.15
        + repetition_score * 0.15
        + naturalness_score * 0.15
        + (100 - risk_score) * 0.1
    )

    blocked_reasons = all_issues + risk_reasons
    policy_action = cold_policy["recommended_action"]
    policy_blocks_send = policy_action in {"stop_contact", "stop_contact_or_use_approved_template_only"}
    cold_policy_allows_medium_risk = (
        _is_cold_lead_context(context)
        and not _human_reply_received(context)
        and policy_action in {"send_first_cold_message", "send_second_commercial_clarification"}
    )
    risk_limit = 50 if cold_policy_allows_medium_risk else 35
    approved = (
        quality_score >= 85
        and risk_score <= risk_limit
        and burn_risk in {"low", "medium"}
        and not policy_blocks_send
    )
    corrected_message = message if approved else _build_corrected_message(message, context, blocked_reasons)

    judges: dict[str, Any] = {}
    digital_twin: dict[str, Any] = {}
    if token_policy["analysis_mode"] == "elite_300":
        judges = {
            "sales_judge": _judge(
                (commercial_score + objective_score + (100 - risk_score)) / 3,
                "Avalia clareza comercial, proxima acao e risco de queimar o lead.",
            ),
            "local_seo_judge": _judge(
                context_score,
                "Avalia se a mensagem usa fonte, website e contexto local de forma honesta.",
            ),
            "whatsapp_judge": _judge(
                naturalness_score,
                "Avalia tamanho, tom e fluidez para WhatsApp.",
            ),
            "persuasion_judge": _judge(
                (context_score + objective_score + naturalness_score) / 3,
                "Avalia relevancia sem pressao ou hype.",
            ),
            "risk_judge": _judge(
                100 - risk_score,
                "Avalia promessas, repeticao, identidade e burn risk.",
            ),
        }
        digital_twin = _digital_twin(approved, burn_risk)

    return {
        "message_quality_score": quality_score,
        "commercial_clarity_score": commercial_score,
        "context_match_score": context_score,
        "one_objective_score": objective_score,
        "repetition_score": repetition_score,
        "whatsapp_naturalness_score": naturalness_score,
        "risk_score": risk_score,
        "burn_risk": burn_risk,
        "approved_to_send": approved,
        "rewrite_suggestion": "" if approved else "Reescrever antes de apresentar ou enviar.",
        "corrected_message": corrected_message,
        "judges": judges,
        "digital_twin": digital_twin,
        "blocked_reasons": blocked_reasons,
        **token_policy,
        "evaluated_at": _now_iso(),
    }


def calculate_lead_score(lead: dict[str, Any]) -> dict[str, Any]:
    """Calculate lead score and recommended offer from local SEO signals."""

    has_website = bool(lead.get("has_website"))
    website_quality = _as_text(lead.get("website_quality")) or ("unknown" if has_website else "none")
    rating = float(lead.get("google_rating") or 0)
    review_count = int(lead.get("review_count") or 0)
    category = _normalize_text(_as_text(lead.get("category")))
    has_whatsapp = bool(lead.get("has_whatsapp", True))
    volume_signals = int(lead.get("volume_signals") or 0)
    premium_signals = int(lead.get("premium_signals") or 0)
    popular_signals = int(lead.get("popular_signals") or 0)

    digital_maturity = 35
    if not has_website or website_quality == "none":
        digital_maturity -= 20
    elif website_quality == "weak":
        digital_maturity += 5
    elif website_quality == "average":
        digital_maturity += 22
    elif website_quality == "good":
        digital_maturity += 38
    elif website_quality == "strong":
        digital_maturity += 48
    if review_count >= 100:
        digital_maturity += 12
    elif review_count >= 30:
        digital_maturity += 7
    if rating >= 4.6:
        digital_maturity += 8
    digital_maturity_score = _clamp_score(digital_maturity)

    whatsapp_dependency = 45
    if has_whatsapp:
        whatsapp_dependency += 25
    if volume_signals >= 2:
        whatsapp_dependency += 18
    if popular_signals >= 2:
        whatsapp_dependency += 10
    if website_quality in {"none", "weak"}:
        whatsapp_dependency += 8
    whatsapp_dependency = _clamp_score(whatsapp_dependency)

    lead_score = 35
    if not has_website or website_quality == "none":
        lead_score += 18
    elif website_quality == "weak":
        lead_score += 15
    elif website_quality in {"good", "strong"}:
        lead_score += 12
    if rating >= 4.6:
        lead_score += 12
    elif rating >= 4.2:
        lead_score += 8
    if review_count >= 100:
        lead_score += 15
    elif review_count >= 30:
        lead_score += 10
    elif review_count >= 10:
        lead_score += 5
    if "odont" in category or "dent" in category:
        lead_score += 8
    if has_whatsapp:
        lead_score += 7
    lead_score += min(volume_signals, 3) * 4
    lead_score += min(premium_signals, 3) * 3
    lead_score += min(popular_signals, 3) * 2
    lead_score = _clamp_score(lead_score)

    if lead_score >= 82:
        revenue_potential = "very_high"
    elif lead_score >= 68:
        revenue_potential = "high"
    elif lead_score >= 48:
        revenue_potential = "medium"
    else:
        revenue_potential = "low"

    if not has_website or website_quality == "none":
        likely_pain = "Poucos sinais de confianca antes do WhatsApp."
        recommended_offer = "website_seo"
    elif website_quality == "weak":
        likely_pain = "Site pode nao converter busca local em contato."
        recommended_offer = "audit"
    elif whatsapp_dependency >= 70:
        likely_pain = "WhatsApp provavelmente concentra demanda e precisa de resposta organizada."
        recommended_offer = "clinicflux_ai"
    else:
        likely_pain = "Demanda local existe, mas precisa de validacao por auditoria curta."
        recommended_offer = "audit"

    return {
        "lead_score": lead_score,
        "revenue_potential": revenue_potential,
        "digital_maturity_score": digital_maturity_score,
        "whatsapp_dependency": whatsapp_dependency,
        "likely_pain": likely_pain,
        "recommended_offer": recommended_offer,
        "signals": {
            "has_website": has_website,
            "website_quality": website_quality,
            "google_rating": rating,
            "review_count": review_count,
            "category": category,
            "has_whatsapp": has_whatsapp,
            "volume_signals": volume_signals,
            "premium_signals": premium_signals,
            "popular_signals": popular_signals,
        },
    }


def decide_next_best_action(context: dict[str, Any]) -> dict[str, Any]:
    """Decide the next commercial action from the current conversation state."""

    latest_reply = _as_text(context.get("latest_reply"))
    normalized_reply = _normalize_text(latest_reply)
    stage = _as_text(context.get("stage_reached") or context.get("current_stage"))
    objection = _as_text(context.get("objection_type"))
    burn_risk = _as_text(context.get("burn_risk")) or "low"
    lead_temperature = _as_text(context.get("lead_temperature")) or "unknown"
    history = context.get("history") or {}
    cold_policy = classify_cold_outreach_state(context)
    token_policy = token_efficiency_policy(context)

    def result(action: str, reason: str, **extra: Any) -> dict[str, Any]:
        return {"action": action, "reason": reason, **token_policy, **extra}

    if (
        context.get("do_not_contact")
        or context.get("stop_contact_required")
        or _normalize_text(_as_text(context.get("opt_in_status"))) in STOP_OPT_IN_STATUSES
        or _contains_any(normalized_reply, STOP_CONTACT_PATTERNS)
    ):
        return result(
            "stop_contact",
            "Lead pediu para nao continuar ou esta marcado como nao contatar.",
            do_not_follow_up=True,
            do_not_contact=True,
            stop_contact_required=True,
        )

    if cold_policy["recommended_action"] == "stop_contact_or_use_approved_template_only":
        return result(
            "stop_contact_or_use_approved_template_only",
            "Fora da janela de 24h sem resposta humana; usar somente template aprovado ou parar.",
            do_not_follow_up=True,
        )

    if cold_policy["recommended_action"] == "stop_contact":
        return result(
            "stop_contact",
            "Lead frio ja recebeu 2 mensagens outbound sem resposta humana.",
            do_not_follow_up=True,
        )

    if cold_policy["recommended_action"] == "send_second_commercial_clarification":
        return result(
            "send_second_commercial_clarification",
            "Apenas resposta automatica recebida; permitido um segundo esclarecimento comercial curto.",
            do_not_follow_up=False,
        )

    if burn_risk in {"high", "critical"}:
        return result("wait", "Risco comercial alto. Pausar antes de nova mensagem.")

    if _contains_any(normalized_reply, SOURCE_QUESTION_PATTERNS) or objection == "source":
        return result("reply_contextually", "Responder diretamente como a clinica foi encontrada.")

    if _contains_any(normalized_reply, PRICE_PATTERNS) or objection == "price":
        if stage in {"demo_clicked", "whatsapp_tested", "meeting_booked"}:
            return result("send_proposal", "Lead ja avancou e pediu valor.")
        return result("send_summary", "Antes de preco, enviar resumo curto e rota de demo.")

    if _contains_any(normalized_reply, DEMO_PATTERNS) or _normalize_text(_as_text(context.get("detected_intent"))) == "request demo":
        return result("send_demo", "Lead pediu demo; enviar demo curta e contextual.")

    if _contains_any(normalized_reply, PERMISSION_TO_SEND_PATTERNS) or _normalize_text(_as_text(context.get("reply_type"))) == "permission to send":
        return result("send_demo", "Lead autorizou envio; mandar demo ou resumo curto adequado ao estagio.")

    if objection == "not_responsible" or "recepcao" in normalized_reply or "responsavel" in normalized_reply:
        return result("ask_for_responsible", "Roteamento para responsavel ainda e o gargalo.")

    if stage == "demo_clicked" and not context.get("whatsapp_tested"):
        return result("send_video", "Lead abriu demo; enviar video/guia para microconversao de teste.")

    if context.get("whatsapp_tested") or stage == "whatsapp_tested":
        return result("book_meeting", "Lead testou WhatsApp; momento de reuniao curta.")

    if lead_temperature in {"hot", "very_hot"} and stage in {"replied", "responsible_identified"}:
        return result("send_demo", "Sinal quente; demo e melhor que nova pergunta.")

    if _human_reply_received(context):
        return result("reply_contextually", "Resposta humana real; continuar com resposta curta, contextual e comercialmente transparente.")

    if context.get("has_website") is False and context.get("offer_lane") == "clinicflux_ai":
        return result("switch_to_website_offer", "Sem site pede oferta de site/SEO antes do SaaS.")

    if context.get("has_website") is True and context.get("website_quality") in {"good", "strong"} and context.get("offer_lane") == "website_seo":
        return result("switch_to_clinicflux_ai_offer", "Site bom pede ClinicFlux AI como camada de conversao.")

    previous_outbound_count = int(history.get("previous_outbound_count") or 0)
    clinic_replied = bool(context.get("clinic_replied"))
    if not clinic_replied and previous_outbound_count >= 2:
        return result("stop_contact", "Evitar insistencia sem resposta.", do_not_follow_up=True)
    if not clinic_replied:
        return result("follow_up", "Ainda sem resposta; follow-up curto pode ser testado.")

    return result("send_message", "Continuar conversa respondendo o ultimo sinal com uma unica proxima acao.")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number} must be a JSON object")
        rows.append(value)
    return rows


def _rate(rows: list[dict[str, Any]], field: str) -> float:
    if not rows:
        return 0.0
    return round(sum(1 for row in rows if row.get(field)) / len(rows), 4)


def _best_worst_by_reply(rows: list[dict[str, Any]], field: str) -> tuple[str, str]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_as_text(row.get(field)) or "unknown"].append(row)
    if not grouped:
        return "none", "none"

    scored = []
    for key, items in grouped.items():
        scored.append((sum(1 for item in items if item.get("clinic_replied")) / len(items), len(items), key))
    scored.sort(key=lambda item: (item[0], item[1], item[2]))
    worst = scored[0][2]
    best = scored[-1][2]
    return best, worst


def _top_counts(rows: list[dict[str, Any]], field: str, *, ignore: set[str] | None = None) -> list[dict[str, Any]]:
    ignore = ignore or set()
    counter = Counter(_as_text(row.get(field)) or "unknown" for row in rows)
    return [{"name": name, "count": count} for name, count in counter.most_common(5) if name not in ignore]


def generate_weekly_summary(
    reviews: list[dict[str, Any]],
    *,
    week_end: date | None = None,
) -> dict[str, Any]:
    week_end = week_end or datetime.now(UTC).date()
    week_start = week_end - timedelta(days=6)
    filtered: list[dict[str, Any]] = []

    for row in reviews:
        created_at = _as_text(row.get("created_at"))
        if not created_at:
            filtered.append(row)
            continue
        created_date = datetime.fromisoformat(created_at.replace("Z", "+00:00")).date()
        if week_start <= created_date <= week_end:
            filtered.append(row)

    best_opening, worst_opening = _best_worst_by_reply(filtered, "message_variant")
    lead_type_rows = [
        {
            **row,
            "lead_type": f"{_as_text(row.get('offer_lane')) or 'unknown'}:{_as_text(row.get('website_quality')) or 'unknown'}",
        }
        for row in filtered
    ]
    best_lead_type, worst_lead_type = _best_worst_by_reply(lead_type_rows, "lead_type")

    top_objections = _top_counts(filtered, "objection_type", ignore={"none"})
    lost_reasons = _top_counts([row for row in filtered if row.get("lost_reason")], "lost_reason")

    recommended_next_strategy = "Manter amostra e comparar variacoes antes de mudar a skill."
    if top_objections:
        recommended_next_strategy = f"Priorizar resposta para objecao '{top_objections[0]['name']}' na proxima semana."
    if worst_opening != "none" and best_opening != worst_opening:
        recommended_next_strategy += f" Reduzir uso de '{worst_opening}' e expandir '{best_opening}'."

    return {
        **token_efficiency_policy({"analysis_task": "weekly_report"}),
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "total_leads_contacted": len(filtered),
        "reply_rate": _rate(filtered, "clinic_replied"),
        "demo_click_rate": _rate(filtered, "demo_clicked"),
        "whatsapp_test_rate": _rate(filtered, "whatsapp_tested"),
        "meeting_rate": _rate(filtered, "meeting_booked"),
        "close_rate": _rate(filtered, "closed_sale"),
        "best_opening": best_opening,
        "worst_opening": worst_opening,
        "best_lead_type": best_lead_type,
        "worst_lead_type": worst_lead_type,
        "top_objections": top_objections,
        "lost_reasons": lost_reasons,
        "recommended_next_strategy": recommended_next_strategy,
        "stop_doing": [
            "Repetir mensagem parecida depois de resposta real.",
            "Prometer resultado comercial garantido.",
        ],
        "continue_doing": [
            "Responder perguntas diretas antes do pitch.",
            "Separar oferta por status do site.",
        ],
        "test_next": [
            "A/B testar abertura com responsavel versus permissao para resumo curto.",
            "Comparar website_seo contra audit em sites fracos.",
        ],
        "generated_at": _now_iso(),
    }


def write_weekly_summary(input_path: Path, output_dir: Path, *, week_end: date | None = None) -> Path:
    reviews = load_jsonl(input_path)
    summary = generate_weekly_summary(reviews, week_end=week_end)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"weekly-summary-{summary['week_end']}.json"
    output_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ClinicFlux AI outreach intelligence utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    weekly = subparsers.add_parser("weekly-summary", help="Generate a weekly summary from reviews JSONL.")
    weekly.add_argument("--input", default="outreach-reviews/conversation-reviews.jsonl")
    weekly.add_argument("--output-dir", default="outreach-reports")
    weekly.add_argument("--week-end", default=None, help="YYYY-MM-DD. Defaults to today.")

    args = parser.parse_args(argv)
    if args.command == "weekly-summary":
        week_end = date.fromisoformat(args.week_end) if args.week_end else None
        output_path = write_weekly_summary(Path(args.input), Path(args.output_dir), week_end=week_end)
        print(output_path)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

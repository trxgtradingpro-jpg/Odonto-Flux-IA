from __future__ import annotations

import json
import re
import unicodedata
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import logger
from app.models import (
    AIAutoresponderDecision,
    Appointment,
    AppointmentEvent,
    Conversation,
    FeatureFlag,
    Lead,
    LinkFlowEvent,
    LinkFlowSession,
    Message,
    MessageEvent,
    Patient,
    PatientContact,
    Professional,
    Setting,
    Unit,
    User,
)
from app.models.enums import MessageDirection, MessageStatus
from app.services.appointment_validation_service import (
    eligible_professionals_for_procedure,
    ensure_appointment_within_working_days,
    find_duplicate_active_patient_appointment,
    find_professional_conflict,
    list_active_professionals_for_unit,
    pick_best_available_professional,
    professional_assignment_priority,
)
from app.services.audit_service import record_audit
from app.services.automation_service import emit_event
from app.services.channel_dispatch_service import dispatch_patient_message
from app.services.demo_whatsapp_simulation_service import (
    maybe_schedule_demo_whatsapp_reply_simulation,
)
from app.services.llm_service import classify_intent, run_llm_task
from app.services.link_flow_service import (
    close_link_flow_session,
    record_link_flow_appointment_result,
    record_link_flow_booking_attempt_started,
)
from app.services.service_catalog_service import (
    get_service_catalog_items,
    has_service_catalog_setting,
    service_catalog_as_knowledge_services,
    set_service_catalog_items,
)
from app.services.service_duration_service import (
    get_service_duration_catalog,
    resolve_appointment_end,
    resolve_service_duration_minutes,
)
from app.services.whatsapp_service import (
    assert_whatsapp_route_ready_for_dispatch,
    queue_outbound_message,
    resolve_whatsapp_reply_route,
)
from app.utils.phone import normalize_phone

AI_AUTORESPONDER_PROMPT_VERSION = "v1.4"
INACTIVE_CONVERSATION_RESTART_MINUTES = 20
WIZARD_STATE_EXPIRATION_MINUTES = 35
CPF_CONTACT_CHANNEL = "cpf"
PREFERRED_NAME_CONTACT_CHANNEL = "preferred_name"
AI_LAB_HISTORY_KEY = "ai_lab.history"
AI_LAB_MAX_PROMPT_EXAMPLES = 5
CLINIC_PROFILE_SETTING_KEY = "clinic.profile"
CLINIC_TIMEZONE_SETTING_KEY = "clinic.timezone"
AI_AUTORESPONDER_PLATFORM_CONFIG_KEY = "platform.ai_autoresponder.global"

AI_ALLOWED_NEXT_ACTIONS = {
    "none",
    "show_clinics",
    "show_services",
    "show_plans",
    "show_available_dates",
    "show_available_times",
    "verify_date_availability",
    "open_booking",
    "show_resume_or_restart_options",
    "resume_saved_step",
    "restart_from_beginning",
    "show_booking_confirmation_options",
    "finalize_booking_auto",
    "request_cpf_after_booking",
    "handoff_human",
}

BOOKING_RESET_PATTERNS = (
    "reiniciar atendimento",
    "recomecar atendimento",
    "recomeçar atendimento",
    "comecar do zero",
    "comecar do zero",
    "começar do zero",
    "mudar clinica",
    "mudar clínica",
    "trocar clinica",
    "trocar clínica",
    "alterar clinica",
    "alterar clínica",
)

BOOKING_RESUME_PATTERNS = (
    "continuar",
    "continuar de onde parei",
    "quero continuar",
    "seguir com isso",
    "pode continuar",
)

BOOKING_RESTART_PATTERNS = (
    "reiniciar",
    "reiniciar atendimento",
    "recomecar",
    "recomecar",
    "recomeçar",
    "do zero",
    "novo atendimento",
)

CPF_PATTERN = re.compile(r"\b(\d{3}\.?\d{3}\.?\d{3}-?\d{2})\b")
BIRTH_DATE_PATTERN = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")
PHONE_PATTERN = re.compile(
    r"(?:(?:telefone|celular|whatsapp|fone)\s*[:\-]?\s*)?(\+?\d[\d\s().-]{8,}\d)",
    re.IGNORECASE,
)

REGISTRATION_SKIP_PATTERNS = (
    "depois",
    "mais tarde",
    "prefiro nao informar",
    "prefiro não informar",
    "nao quero informar",
    "não quero informar",
    "sem cpf",
    "na recepcao",
    "na recepção",
)

APPOINTMENT_LOOKUP_PATTERNS = (
    "meus agendamentos",
    "minhas consultas",
    "minha consulta",
    "meu agendamento",
    "tenho consulta",
    "quando e minha consulta",
    "quando é minha consulta",
    "qual horario da minha consulta",
    "qual horário da minha consulta",
    "ver minha agenda",
    "ver meus horarios",
    "ver meus horários",
    "consultar agendamento",
)

APPOINTMENT_CANCEL_PATTERNS = (
    "cancelar",
    "cancelamento",
    "desmarcar",
    "desmarque",
    "nao vou conseguir ir",
    "não vou conseguir ir",
)

APPOINTMENT_RESCHEDULE_PATTERNS = (
    "remarcar",
    "remarcacao",
    "remarcação",
    "reagendar",
    "reagendamento",
    "mudar horario",
    "mudar horário",
    "trocar horario",
    "trocar horário",
    "mudar data",
    "trocar data",
)

VISIT_GUIDANCE_ADDRESS_PATTERNS = (
    "endereco",
    "endereço",
    "endereco da unidade",
    "endereço da unidade",
    "localizacao",
    "localização",
    "local da consulta",
    "local do atendimento",
    "onde fica",
    "onde sera",
    "onde será",
    "qual o local",
    "qual rua",
    "me passa a rua",
    "como chegar",
)

VISIT_GUIDANCE_PROFESSIONAL_PATTERNS = (
    "quem vai me atender",
    "quem vai atender",
    "qual dr",
    "qual dra",
    "qual doutor",
    "qual doutora",
    "qual dentista",
    "qual profissional",
    "profissional que vai atender",
)

VISIT_GUIDANCE_DOCUMENT_PATTERNS = (
    "que documento",
    "quais documentos",
    "o que preciso levar",
    "o que devo levar",
    "o que levo",
    "preciso levar documento",
    "levar documento",
    "documento para consulta",
)

VISIT_GUIDANCE_OVERVIEW_PATTERNS = (
    "dados da consulta",
    "dados do atendimento",
    "informacoes da consulta",
    "informações da consulta",
    "me passa os dados",
    "me confirma os dados",
)

AI_AUTORESPONDER_DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "conversation_flow_mode": "legacy",
    "structured_flow_enabled": False,
    "channels": {
        "whatsapp": True,
        "webchat": True,
    },
    "llm_model": "",
    "pre_send_review_enabled": False,
    "repetition_guard_enabled": True,
    "conversation_memory_enabled": True,
    "auto_save_patient_data_enabled": True,
    "handoff_triggers": {
        "low_confidence": True,
        "urgency": True,
        "patient_irritated": True,
        "schedule_error": True,
        "review_failed": True,
    },
    "interactive_booking_options_enabled": True,
    "business_hours": {
        "timezone": "America/Sao_Paulo",
        "weekdays": [0, 1, 2, 3, 4],
        "start": "08:00",
        "end": "18:00",
    },
    "outside_business_hours_mode": "allow",
    "max_consecutive_auto_replies": 3,
    "confidence_threshold": 0.65,
    "human_queue_tag": "fila_humana_ia",
    "tone": "humano, claro, consultivo, acolhedor e objetivo",
    "fallback_user_id": None,
}

AI_KNOWLEDGE_BASE_DEFAULT_CONFIG: dict[str, Any] = {
    "clinic_profile": {
        "clinic_name": "",
        "about": "",
        "differentials": [],
        "target_audience": "",
        "tone_preferences": "",
        "welcome_greeting_example": "",
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

CLOSE_CONVERSATION_PATTERNS = [
    "encerrar conversa",
    "encerrar atendimento",
    "finalizar conversa",
    "finalizar atendimento",
    "encerrar chat",
    "finalizar chat",
]

GREETING_ONLY_PATTERNS = (
    "oi",
    "ola",
    "olá",
    "bom dia",
    "boa tarde",
    "boa noite",
    "e ai",
    "e aí",
)

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

PATIENT_DISCOMFORT_PATTERNS = (
    "dor de dente",
    "dor no dente",
    "dente doendo",
    "dente doi",
    "dente está doendo",
    "dente esta doendo",
    "estou com dor",
    "to com dor",
    "tô com dor",
    "sensibilidade",
    "gengiva doendo",
    "gengiva inchada",
    "latejando",
    "incomodo",
    "incômodo",
)

BOOKING_WIZARD_FREE_TEXT_CONTEXT_MODES = {
    "booking_wizard_service_select",
    "booking_wizard_unit_select",
    "booking_wizard_day_select",
    "booking_wizard_time_select",
    "booking_wizard_confirm",
    "no_slots_general",
    "no_slots_for_period",
    "no_slots_for_period_with_alternatives",
}

CONTACT_NAME_PATTERNS = [
    re.compile(r"\bmeu\s+nome(?:\s+completo)?\s*(?:e|eh|é)\s+(.+)$", re.IGNORECASE),
    re.compile(r"\bnome(?:\s+completo)?\s*[:\-]\s*(.+)$", re.IGNORECASE),
    re.compile(r"\bme\s+chamo\s+(.+)$", re.IGNORECASE),
    re.compile(r"\bsou\s+(?:o|a)\s+(.+)$", re.IGNORECASE),
]

PREFERRED_NAME_PATTERNS = [
    re.compile(r"\bpode\s+me\s+chamar\s+de\s+(.+)$", re.IGNORECASE),
    re.compile(r"\bme\s+chama\s+de\s+(.+)$", re.IGNORECASE),
    re.compile(r"\bme\s+chame\s+de\s+(.+)$", re.IGNORECASE),
    re.compile(r"\bsou\s+(?:o|a\s+)?(.+)$", re.IGNORECASE),
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
DAY_AVAILABILITY_KEYWORDS = (
    "quais dias",
    "que dias",
    "dias disponiveis",
    "dias disponíveis",
    "datas disponiveis",
    "datas disponíveis",
    "quais datas",
    "que datas",
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
BOOKING_WIZARD_CHANGE_TIME_KEYWORDS = (
    "confirm_change_time",
    "trocar horario",
    "trocar horário",
    "mudar horario",
    "mudar horário",
)
BOOKING_WIZARD_CHANGE_DAY_KEYWORDS = (
    "confirm_change_day",
    "trocar dia",
    "mudar dia",
)
BOOKING_WIZARD_CHANGE_SERVICE_KEYWORDS = (
    "confirm_change_service",
    "trocar servico",
    "trocar serviço",
    "mudar servico",
    "mudar serviço",
)
BOOKING_WIZARD_HUMAN_KEYWORDS = (
    "confirm_human",
    "falar com atendente",
    "atendente",
    "humano",
)
BOOKING_WIZARD_DEFAULT_SERVICES = (
    "Avaliação inicial",
    "Consulta de retorno",
    "Procedimento estético",
    "Exame clínico",
    "Atendimento especializado",
)

WELCOME_MENU_OPTIONS: tuple[dict[str, str], ...] = (
    {
        "id": "menu_schedule",
        "title": "Agendamentos",
        "description": "Marcar, reagendar ou horários",
    },
    {
        "id": "menu_services",
        "title": "Serviços",
        "description": "Ver procedimentos e valores",
    },
    {
        "id": "menu_support",
        "title": "Suporte",
        "description": "Ajuda com atendimento",
    },
    {
        "id": "menu_suggestion",
        "title": "Sugestões",
        "description": "Enviar melhoria para a clínica",
    },
    {
        "id": "menu_complaint",
        "title": "Reclamações",
        "description": "Registrar insatisfação",
    },
    {
        "id": "menu_human",
        "title": "Falar com atendente",
        "description": "Encaminhar para humano",
    },
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
    "response_sent_handoff": "Resposta enviada e conversa encaminhada para humano.",
    "urgency_detected": "Risco/urgência detectado, encaminhamento humano obrigatório.",
    "clinical_request_blocked": "Solicitação clínica bloqueada por segurança.",
    "low_confidence": "Baixa confiança da IA para responder com segurança.",
    "max_consecutive_reached": "Limite de respostas automáticas consecutivas atingido.",
    "missing_contact_phone": "Sem telefone de destino para resposta.",
    "whatsapp_not_ready": "Conta WhatsApp indisponível para envio.",
    "response_sent": "Resposta automática enviada para fila.",
    "llm_error": "Falha no provedor de IA, atendimento humano acionado.",
    "invalid_ai_contract": "Resposta da IA fora do contrato JSON obrigatório.",
    "dispatch_error": "Falha ao enfileirar mensagem automática.",
    "conversation_closed_by_user": "Conversa encerrada a pedido do paciente.",
    "superseded_by_newer_inbound": "Mensagem anterior agrupada em uma resposta mais recente.",
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
    flow_mode = str(merged.get("conversation_flow_mode") or "").strip().lower()
    if flow_mode not in {"legacy", "structured_elite"}:
        flow_mode = "structured_elite" if bool(merged.get("structured_flow_enabled", False)) else "legacy"
    merged["conversation_flow_mode"] = flow_mode
    merged["structured_flow_enabled"] = flow_mode == "structured_elite" or bool(merged.get("structured_flow_enabled", False))
    channels = merged.get("channels") or {}
    merged["channels"] = {
        "whatsapp": bool(channels.get("whatsapp", True)),
        "webchat": bool(channels.get("webchat", True)),
    }
    merged["llm_model"] = str(merged.get("llm_model") or "").strip()[:80]
    merged["pre_send_review_enabled"] = bool(merged.get("pre_send_review_enabled", False))
    merged["repetition_guard_enabled"] = bool(merged.get("repetition_guard_enabled", True))
    merged["conversation_memory_enabled"] = bool(merged.get("conversation_memory_enabled", True))
    merged["auto_save_patient_data_enabled"] = bool(merged.get("auto_save_patient_data_enabled", True))
    handoff_triggers = merged.get("handoff_triggers") if isinstance(merged.get("handoff_triggers"), dict) else {}
    merged["handoff_triggers"] = {
        "low_confidence": bool(handoff_triggers.get("low_confidence", True)),
        "urgency": bool(handoff_triggers.get("urgency", True)),
        "patient_irritated": bool(handoff_triggers.get("patient_irritated", True)),
        "schedule_error": bool(handoff_triggers.get("schedule_error", True)),
        "review_failed": bool(handoff_triggers.get("review_failed", True)),
    }
    merged["interactive_booking_options_enabled"] = bool(merged.get("interactive_booking_options_enabled", True))

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


def booking_interactive_options_enabled(config: dict[str, Any] | None) -> bool:
    if not isinstance(config, dict):
        return True
    value = config.get("interactive_booking_options_enabled")
    if value is None:
        return True
    return bool(value)


def _compact_text(value: Any, *, max_length: int = 600) -> str:
    if isinstance(value, dict):
        for key in ("text", "value", "message", "body_text", "title", "name"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                value = candidate
                break
        else:
            return ""
    elif isinstance(value, (list, tuple, set)):
        return ""
    text = str(value or "").strip()
    if len(text) > max_length:
        text = text[:max_length].rstrip()
    return text


def _load_custom_autoresponder_prompt() -> str:
    prompt_path = str(settings.ai_autoresponder_prompt_path or "").strip()
    if not prompt_path:
        return ""
    try:
        path = Path(prompt_path)
        if not path.is_file():
            return ""
        return _compact_text(path.read_text(encoding="utf-8"), max_length=18000)
    except Exception as exc:
        logger.warning(
            "ai_autoresponder.custom_prompt_load_failed",
            prompt_path=prompt_path,
            error=str(exc),
        )
        return ""


def _format_unit_address(address: Any) -> str:
    if isinstance(address, str):
        return _compact_text(address, max_length=240)
    if not isinstance(address, dict):
        return ""

    direct = _compact_text(
        address.get("formatted")
        or address.get("full")
        or address.get("address")
        or address.get("line")
        or address.get("line1"),
        max_length=240,
    )
    if direct:
        extra = _compact_text(address.get("line2"), max_length=80)
        return f"{direct} {extra}".strip()

    parts = [
        address.get("street") or address.get("logradouro"),
        address.get("number") or address.get("numero"),
        address.get("neighborhood") or address.get("bairro"),
        address.get("city") or address.get("cidade"),
        address.get("state") or address.get("uf"),
        address.get("zip_code") or address.get("cep"),
    ]
    return _compact_text(", ".join(str(part).strip() for part in parts if str(part or "").strip()), max_length=240)


def _render_operational_catalog_context(db: Session, *, tenant_id: UUID) -> str:
    units = db.execute(
        select(Unit)
        .where(
            Unit.tenant_id == tenant_id,
            Unit.is_active.is_(True),
        )
        .order_by(Unit.name.asc())
        .limit(12)
    ).scalars().all()
    if not units:
        return ""

    lines = [
        "Clinicas/unidades cadastradas no sistema:",
        "Use estes dados para responder perguntas sobre onde a clinica atende. Nao invente enderecos ausentes.",
    ]
    for unit in units:
        details = [f"nome: {_compact_text(unit.name, max_length=120)}"]
        if unit.code:
            details.append(f"codigo: {_compact_text(unit.code, max_length=40)}")
        address = _format_unit_address(unit.address)
        if address:
            details.append(f"endereco: {address}")
        address_payload = unit.address if isinstance(unit.address, dict) else {}
        reference_point = _compact_text(
            address_payload.get("reference_point") or address_payload.get("referencia"),
            max_length=160,
        )
        if reference_point:
            details.append(f"ponto de referencia: {reference_point}")
        access_instructions = _compact_text(
            address_payload.get("access_instructions") or address_payload.get("instructions"),
            max_length=260,
        )
        if access_instructions:
            details.append(f"como chegar/acesso: {access_instructions}")
        parking_info = _compact_text(address_payload.get("parking_info") or address_payload.get("parking"), max_length=220)
        if parking_info:
            details.append(f"estacionamento/transporte: {parking_info}")
        if unit.phone:
            details.append(f"telefone: {_compact_text(unit.phone, max_length=40)}")
        if unit.email:
            details.append(f"email: {_compact_text(unit.email, max_length=120)}")
        working_hours = unit.working_hours if isinstance(unit.working_hours, dict) else {}
        if working_hours:
            days_text = _compact_text(working_hours.get("days_text") or working_hours.get("days"), max_length=120)
            start = _compact_text(working_hours.get("start") or working_hours.get("opens_at"), max_length=20)
            end = _compact_text(working_hours.get("end") or working_hours.get("closes_at"), max_length=20)
            notes = _compact_text(working_hours.get("notes") or working_hours.get("observation"), max_length=220)
            readable_hours = " ".join(
                part
                for part in [
                    days_text,
                    f"{start}-{end}" if start or end else "",
                    notes,
                ]
                if part
            )
            details.append(f"horarios: {readable_hours or _compact_text(json.dumps(working_hours, ensure_ascii=False), max_length=220)}")
        lines.append(f"- {' | '.join(details)}")
    return "\n".join(lines)


def _setting_value_for_source_truth(item: Setting | None) -> Any:
    if not item:
        return None
    value = item.value
    if isinstance(value, dict) and set(value.keys()) == {"value"}:
        return value.get("value")
    return value


def _load_official_clinic_profile_context(db: Session, *, tenant_id: UUID) -> dict[str, str]:
    profile_item = db.scalar(
        select(Setting).where(
            Setting.tenant_id == tenant_id,
            Setting.key == CLINIC_PROFILE_SETTING_KEY,
        )
    )
    timezone_item = db.scalar(
        select(Setting).where(
            Setting.tenant_id == tenant_id,
            Setting.key == CLINIC_TIMEZONE_SETTING_KEY,
        )
    )
    raw_profile = _setting_value_for_source_truth(profile_item)
    profile = raw_profile if isinstance(raw_profile, dict) else {}
    raw_timezone = _setting_value_for_source_truth(timezone_item)

    fields = {
        "clinic_name": _compact_text(profile.get("clinic_name"), max_length=120),
        "legal_name": _compact_text(profile.get("legal_name"), max_length=160),
        "main_phone": _compact_text(profile.get("main_phone"), max_length=80),
        "whatsapp_phone": _compact_text(profile.get("whatsapp_phone"), max_length=80),
        "email": _compact_text(profile.get("email"), max_length=160),
        "website": _compact_text(profile.get("website"), max_length=180),
        "timezone": _compact_text(raw_timezone or profile.get("timezone"), max_length=80),
        "address_line": _compact_text(profile.get("address_line"), max_length=220),
        "neighborhood": _compact_text(profile.get("neighborhood"), max_length=120),
        "city": _compact_text(profile.get("city"), max_length=120),
        "state": _compact_text(profile.get("state"), max_length=80),
        "zip_code": _compact_text(profile.get("zip_code"), max_length=40),
        "technical_manager_name": _compact_text(profile.get("technical_manager_name"), max_length=160),
        "technical_manager_cro": _compact_text(profile.get("technical_manager_cro"), max_length=80),
        "payment_methods": _compact_text(profile.get("payment_methods"), max_length=260),
        "accepted_insurance": _compact_text(profile.get("accepted_insurance"), max_length=260),
        "cancellation_policy": _compact_text(profile.get("cancellation_policy"), max_length=500),
        "reschedule_policy": _compact_text(profile.get("reschedule_policy"), max_length=500),
        "about": _compact_text(profile.get("about"), max_length=700),
    }
    return {key: value for key, value in fields.items() if value}


def _render_official_clinic_profile_context(db: Session, *, tenant_id: UUID) -> str:
    profile = _load_official_clinic_profile_context(db, tenant_id=tenant_id)
    if not profile:
        return ""

    labels = [
        ("clinic_name", "Nome da clinica"),
        ("legal_name", "Razao social"),
        ("main_phone", "Telefone principal"),
        ("whatsapp_phone", "WhatsApp"),
        ("email", "E-mail"),
        ("website", "Site"),
        ("timezone", "Timezone operacional"),
        ("address_line", "Endereco principal"),
        ("neighborhood", "Bairro"),
        ("city", "Cidade"),
        ("state", "Estado"),
        ("zip_code", "CEP"),
        ("technical_manager_name", "Responsavel tecnico"),
        ("technical_manager_cro", "CRO do responsavel tecnico"),
        ("payment_methods", "Formas de pagamento oficiais"),
        ("accepted_insurance", "Convenios/planos aceitos oficialmente"),
        ("cancellation_policy", "Politica de cancelamento oficial"),
        ("reschedule_policy", "Politica de reagendamento oficial"),
        ("about", "Resumo oficial da clinica"),
    ]
    lines = [
        "DADOS OFICIAIS SALVOS NO PERFIL DA CLINICA (PRIORIDADE MAXIMA):",
        "- Estes campos sao a fonte da verdade para informacoes operacionais ao paciente.",
        "- Se houver conflito com Conhecimento IA, FAQ, preset, treino do IA Lab ou prompt editavel, use estes dados oficiais.",
        "- Nao acrescente formas de pagamento, convenio, telefone, endereco, politica ou dado institucional que nao esteja cadastrado.",
        "- Se o campo necessario nao estiver preenchido, diga que nao possui a informacao cadastrada e ofereca encaminhar para a equipe.",
    ]
    for key, label in labels:
        value = profile.get(key)
        if value:
            lines.append(f"- {label}: {value}")
    if profile.get("payment_methods"):
        lines.append(
            "REGRA ESPECIFICA DE PAGAMENTO: ao responder sobre pagamento, informe somente as formas cadastradas em "
            "'Formas de pagamento oficiais'. Nao cite cartao, debito, credito, dinheiro, boleto, convenio ou "
            "parcelamento se esses termos nao estiverem explicitamente cadastrados nesse campo."
        )
    return "\n".join(lines)


def _official_payment_methods_from_profile(profile: dict[str, str]) -> str:
    return _compact_text(profile.get("payment_methods"), max_length=260)


def _is_payment_methods_question(text: str) -> bool:
    normalized = _normalize_for_match(text)
    payment_keywords = (
        "forma de pagamento",
        "formas de pagamento",
        "meios de pagamento",
        "metodo de pagamento",
        "metodos de pagamento",
        "pagamento",
        "pagar",
        "pago",
        "pix",
        "cartao",
        "credito",
        "debito",
        "dinheiro",
        "boleto",
        "parcel",
        "a vista",
    )
    return any(keyword in normalized for keyword in payment_keywords)


def _official_payment_methods_reply(profile: dict[str, str]) -> str:
    payment_methods = _official_payment_methods_from_profile(profile)
    if payment_methods:
        return (
            f"Pelo cadastro oficial da clinica, as formas de pagamento registradas sao: {payment_methods}. "
            "No momento, nao tenho outra forma de pagamento cadastrada para informar com seguranca."
        )
    return (
        "No momento, nao tenho as formas de pagamento cadastradas aqui para responder com seguranca. "
        "Posso encaminhar para a equipe confirmar essa informacao para voce."
    )


def _render_ai_lab_training_examples(db: Session, *, tenant_id: UUID, limit: int = AI_LAB_MAX_PROMPT_EXAMPLES) -> str:
    item = db.scalar(
        select(Setting).where(
            Setting.tenant_id == tenant_id,
            Setting.key == AI_LAB_HISTORY_KEY,
        )
    )
    if not item or not isinstance(item.value, dict):
        return ""

    raw_entries = item.value.get("entries")
    if not isinstance(raw_entries, list):
        return ""

    examples: list[dict[str, str]] = []
    for raw in raw_entries:
        if not isinstance(raw, dict):
            continue
        edited_response = _compact_text(raw.get("edited_response_text"), max_length=900)
        input_text = _compact_text(raw.get("input_text"), max_length=360)
        if not edited_response or not input_text:
            continue
        examples.append(
            {
                "input_text": input_text,
                "edited_response_text": edited_response,
                "note": _compact_text(raw.get("note"), max_length=220),
            }
        )
        if len(examples) >= max(1, min(limit, AI_LAB_MAX_PROMPT_EXAMPLES)):
            break

    if not examples:
        return ""

    lines = [
        "Treino aprovado no IA Lab:",
        "- Use estes exemplos como referência de tom, estrutura e critério de decisão.",
        "- Não copie literalmente se o contexto do paciente for diferente.",
        "- Se a mensagem for parecida, priorize a resposta aprovada e o próximo passo operacional.",
    ]
    for idx, example in enumerate(examples, start=1):
        lines.append(f"Exemplo {idx} - paciente: {example['input_text']}")
        lines.append(f"Exemplo {idx} - resposta aprovada: {example['edited_response_text']}")
        if example["note"]:
            lines.append(f"Exemplo {idx} - nota de treino: {example['note']}")
    return "\n".join(lines)


def _normalize_string_list(value: Any, *, max_items: int = 20, item_max_length: int = 120) -> list[str]:
    if isinstance(value, str):
        raw_items = list(value.replace(";", ",").replace("\n", ",").split(","))
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
            "welcome_greeting_example": _compact_text(
                profile.get("welcome_greeting_example"),
                max_length=700,
            ),
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

    welcome_greeting_example = _compact_text(profile.get("welcome_greeting_example"), max_length=700)
    if welcome_greeting_example:
        lines.append(f"Exemplo de saudacao inicial: {welcome_greeting_example}")

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


def _platform_config_rows(db: Session) -> list[FeatureFlag]:
    return (
        db.execute(
            select(FeatureFlag)
            .where(
                FeatureFlag.tenant_id.is_(None),
                FeatureFlag.key == AI_AUTORESPONDER_PLATFORM_CONFIG_KEY,
            )
            .order_by(FeatureFlag.updated_at.desc(), FeatureFlag.created_at.desc())
        )
        .scalars()
        .all()
    )


def get_platform_global_config(db: Session) -> dict[str, Any]:
    rows = _platform_config_rows(db)
    row = rows[0] if rows else None
    raw_config = row.config if row and isinstance(row.config, dict) else None
    return _normalize_config(raw_config)


def set_platform_global_config(db: Session, *, payload: dict[str, Any]) -> dict[str, Any]:
    config = _normalize_config(payload)
    rows = _platform_config_rows(db)
    row = rows[0] if rows else None
    if row is None:
        row = FeatureFlag(
            tenant_id=None,
            key=AI_AUTORESPONDER_PLATFORM_CONFIG_KEY,
            description="Configuracao global do agente de atendimento da plataforma.",
            enabled=True,
            config=config,
        )
        db.add(row)
    else:
        row.enabled = True
        row.description = "Configuracao global do agente de atendimento da plataforma."
        row.config = config
        db.add(row)

    for duplicate in rows[1:]:
        duplicate.enabled = True
        duplicate.description = row.description
        duplicate.config = config
        db.add(duplicate)

    db.commit()
    db.refresh(row)
    return config


def get_global_config(db: Session, *, tenant_id: UUID) -> dict[str, Any]:
    item = db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == "ai_autoresponder.global"))
    platform_config = get_platform_global_config(db)
    tenant_config = item.value if item and isinstance(item.value, dict) else None
    return _normalize_config(_deep_merge(platform_config, tenant_config))


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
    config = _normalize_knowledge_config(item.value if item and isinstance(item.value, dict) else None)
    official_services = service_catalog_as_knowledge_services(
        get_service_catalog_items(db, tenant_id=tenant_id)
    )
    if official_services:
        config["services"] = official_services
    return config


def set_knowledge_base_global_config(
    db: Session,
    *,
    tenant_id: UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    raw_payload = payload if isinstance(payload, dict) else {}
    payload_services = raw_payload.get("services")
    if isinstance(payload_services, list) and not has_service_catalog_setting(db, tenant_id=tenant_id):
        set_service_catalog_items(
            db,
            tenant_id=tenant_id,
            payload={"items": payload_services},
        )

    knowledge_payload = dict(raw_payload)
    knowledge_payload.pop("services", None)
    config = _normalize_knowledge_config(knowledge_payload)
    _upsert_setting(
        db,
        tenant_id=tenant_id,
        key="ai_knowledge_base.global",
        value=config,
    )
    official_services = service_catalog_as_knowledge_services(
        get_service_catalog_items(db, tenant_id=tenant_id)
    )
    if official_services:
        config["services"] = official_services
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
    return (
        text.startswith("contato whatsapp ")
        or text.startswith("paciente webchat")
        or text.startswith("paciente do agendamento")
    )


def _is_webchat_placeholder_phone(value: str | None) -> bool:
    return str(value or "").strip().lower().startswith("webchat")


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


def _person_name_words(value: str | None) -> list[str]:
    return [part for part in re.split(r"\s+", str(value or "").strip()) if part]


def _looks_like_person_name(value: str | None, *, min_words: int = 1, max_words: int = 6, max_chars: int = 80) -> bool:
    candidate = str(value or "").strip()
    if not candidate or len(candidate) > max_chars:
        return False
    if not re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ' -]{2,80}", candidate):
        return False
    words = _person_name_words(candidate)
    if len(words) < min_words or len(words) > max_words:
        return False
    normalized = _normalize_for_match(candidate)
    blocked_terms = (
        "agendar",
        "agenda",
        "avaliacao",
        "avaliação",
        "consulta",
        "clareamento",
        "implante",
        "limpeza",
        "lente",
        "lentes",
        "horario",
        "horário",
        "unidade",
        "clinica",
        "clínica",
        "atendente",
        "humano",
    )
    return not any(term in normalized for term in blocked_terms)


def _has_complete_patient_name(value: str | None) -> bool:
    if _is_placeholder_name(value):
        return False
    return _looks_like_person_name(value, min_words=2, max_words=6, max_chars=80)


def _clean_person_name_candidate(value: str, *, max_chars: int = 80) -> str | None:
    candidate = str(value or "").strip()
    candidate = re.split(r"[\n\r,.;!?]", candidate, maxsplit=1)[0].strip()
    candidate = re.split(
        r"\b(como|quero|gostaria|preciso|posso|pode|qual|quais|agendar|marcar|servi[cç]os?)\b",
        candidate,
        flags=re.IGNORECASE,
        maxsplit=1,
    )[0].strip()
    candidate = re.sub(r"\s+", " ", candidate).strip(" -:")
    if not _looks_like_person_name(candidate, min_words=1, max_words=6, max_chars=max_chars):
        return None
    return _normalize_person_name(candidate)


def _extract_contact_name(text: str) -> str | None:
    lowered = text.lower()
    if "nome" not in lowered and "chamo" not in lowered and not lowered.startswith("sou "):
        return None

    for pattern in CONTACT_NAME_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue

        candidate = match.group(1).strip()
        cleaned = _clean_person_name_candidate(candidate)
        if cleaned:
            return cleaned

    return None


def _extract_preferred_name_from_text(text: str, *, allow_plain: bool = False) -> str | None:
    raw = str(text or "").strip()
    if not raw:
        return None

    for pattern in PREFERRED_NAME_PATTERNS:
        match = pattern.search(raw)
        if not match:
            continue
        cleaned = _clean_person_name_candidate(match.group(1), max_chars=40)
        if cleaned and len(_person_name_words(cleaned)) <= 2:
            return cleaned

    if not allow_plain:
        return None

    if any(separator in raw for separator in ("\n", "\r", ",", ";", ".", "?", "!")):
        return None
    cleaned = _clean_person_name_candidate(raw, max_chars=40)
    if not cleaned:
        return None
    words = _person_name_words(cleaned)
    if len(words) > 2:
        return None
    normalized = _normalize_for_match(cleaned)
    blocked_plain = {
        "oi",
        "ola",
        "olá",
        "bom dia",
        "boa tarde",
        "boa noite",
        "sim",
        "nao",
        "não",
        "ok",
        "obrigado",
        "obrigada",
    }
    if normalized in blocked_plain:
        return None
    return cleaned


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
    allow_plain_preferred_name: bool = False,
) -> dict[str, str]:
    extracted_name = _extract_contact_name(inbound_text)
    extracted_preferred_name = _extract_preferred_name_from_text(
        inbound_text,
        allow_plain=allow_plain_preferred_name,
    )
    extracted_email = _extract_contact_email(inbound_text)
    if not extracted_name and not extracted_preferred_name and not extracted_email:
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
        if extracted_name and _has_complete_patient_name(extracted_name) and not _has_complete_patient_name(patient.full_name):
            patient.full_name = extracted_name
            changes["patient_full_name"] = extracted_name
        elif extracted_name and not _has_complete_patient_name(extracted_name):
            extracted_preferred_name = extracted_preferred_name or extracted_name

        if extracted_preferred_name:
            _upsert_patient_preferred_name(
                db,
                conversation=conversation,
                preferred_name=extracted_preferred_name,
            )
            changes["patient_preferred_name"] = extracted_preferred_name

        if extracted_email and not (patient.email or "").strip():
            patient.email = extracted_email
            changes["patient_email"] = extracted_email

        if changes:
            db.add(patient)

    if lead:
        if extracted_name and _has_complete_patient_name(extracted_name) and (
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


def _extract_json_dict_from_text(raw: str) -> dict[str, Any]:
    parsed = _parse_json_output(raw)
    if parsed:
        return parsed

    text = str(raw or "").strip()
    if not text:
        return {}
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return {}
    snippet = text[start : end + 1]
    return _parse_json_output(snippet)


def _parse_and_validate_ai_contract(raw_output: str) -> dict[str, Any] | None:
    parsed = _extract_json_dict_from_text(raw_output)
    if not parsed:
        return None

    reply_text_raw = parsed.get("reply_text")
    next_action_raw = parsed.get("next_action")
    action_payload_raw = parsed.get("action_payload")
    confidence_raw = parsed.get("confidence")

    if not isinstance(reply_text_raw, str):
        return None
    if not isinstance(next_action_raw, str):
        return None
    if not isinstance(action_payload_raw, dict):
        return None
    if not isinstance(confidence_raw, (int, float)):
        return None

    reply_text = reply_text_raw.strip()
    next_action = next_action_raw.strip()
    confidence = float(confidence_raw)
    if not reply_text:
        return None
    if next_action not in AI_ALLOWED_NEXT_ACTIONS:
        return None
    if not (0.0 <= confidence <= 1.0):
        return None

    context_value = action_payload_raw.get("context")
    if not isinstance(context_value, str) or not context_value.strip():
        return None

    return {
        "reply_text": reply_text,
        "next_action": next_action,
        "action_payload": action_payload_raw,
        "confidence": round(confidence, 4),
    }


def _normalize_cpf_digits(value: str | None) -> str | None:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) != 11:
        return None
    if len(set(digits)) == 1:
        return None
    return digits


def _extract_cpf_from_text(text: str) -> str | None:
    for match in CPF_PATTERN.finditer(str(text or "")):
        normalized = _normalize_cpf_digits(match.group(1))
        if normalized:
            return normalized

    fallback = _normalize_cpf_digits(text)
    if fallback:
        return fallback
    return None


def _extract_phone_from_text(text: str) -> str | None:
    raw_text = str(text or "")
    if not raw_text.strip():
        return None

    lowered_raw = raw_text.lower()
    cpf_digits = _extract_cpf_from_text(raw_text)
    for match in PHONE_PATTERN.finditer(raw_text):
        raw_phone = str(match.group(1) or "").strip()
        if not raw_phone:
            continue
        normalized_phone = normalize_phone(raw_phone)
        if len(normalized_phone) < 10 or len(normalized_phone) > 15:
            continue
        context = raw_text[max(0, match.start() - 18) : match.start()].lower()
        has_phone_marker = any(marker in context for marker in ("telefone", "celular", "whatsapp", "fone"))
        if not has_phone_marker:
            has_phone_marker = any(marker in lowered_raw for marker in ("telefone", "celular", "whatsapp", "fone"))
        if cpf_digits and normalized_phone.endswith(cpf_digits) and not has_phone_marker:
            continue
        if not has_phone_marker:
            compact_digits = re.sub(r"\D", "", raw_phone)
            if compact_digits != raw_text.strip():
                continue
        return normalized_phone
    return None


def _birth_date_label_present(text: str) -> bool:
    normalized = _normalize_for_match(text)
    return any(
        keyword in normalized
        for keyword in (
            "nascimento",
            "data de nasc",
            "data nasc",
            "nasci",
            "nascido",
            "nascida",
            "aniversario",
            "aniversário",
            "meu nascimento",
        )
    )


def _coerce_birth_date(day: int, month: int, year: int) -> date | None:
    if year < 100:
        current_year = datetime.now(UTC).year
        year += 2000
        if year > current_year:
            year -= 100
    try:
        candidate = date(year, month, day)
    except ValueError:
        return None

    today = datetime.now(UTC).date()
    if candidate > today:
        return None
    age = today.year - candidate.year - ((today.month, today.day) < (candidate.month, candidate.day))
    if age < 0 or age > 120:
        return None
    return candidate


def _extract_birth_date_from_text(text: str, *, allow_unlabeled: bool = False) -> date | None:
    raw = str(text or "")
    if not raw.strip():
        return None
    if not allow_unlabeled and not _birth_date_label_present(raw):
        return None

    for match in BIRTH_DATE_PATTERN.finditer(raw):
        try:
            day = int(match.group(1))
            month = int(match.group(2))
            year = int(match.group(3))
        except (TypeError, ValueError):
            continue
        parsed = _coerce_birth_date(day, month, year)
        if parsed:
            return parsed
    return None


def _extract_registration_name_from_text(text: str) -> str | None:
    explicit_name = _extract_contact_name(text)
    if explicit_name and _has_complete_patient_name(explicit_name):
        return explicit_name

    cleaned = CPF_PATTERN.sub(" ", str(text or ""))
    cleaned = BIRTH_DATE_PATTERN.sub(" ", cleaned)
    cleaned = re.sub(
        r"\b(cpf|data\s+de\s+nascimento|nascimento|nasci|nascido|nascida|dn)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(meu\s+nome(?:\s+completo)?\s*(?:e|eh|é)?|me\s+chamo|sou\s+(?:o|a)?)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    for candidate in re.split(r"[\n\r,;|]+", cleaned):
        candidate = re.sub(r"\s+", " ", candidate).strip(" .:-")
        if not candidate:
            continue
        words = [word for word in candidate.split(" ") if word]
        if len(words) < 2 or len(words) > 6:
            continue
        if not re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ' -]{3,80}", candidate):
            continue
        normalized = _normalize_for_match(candidate)
        blocked_terms = (
            "consulta",
            "agendamento",
            "avaliacao",
            "avaliação",
            "clareamento",
            "implante",
            "horario",
            "horário",
            "unidade",
            "clinica",
            "clínica",
        )
        if any(term in normalized for term in blocked_terms):
            continue
        return _normalize_person_name(candidate)
    return None


def _patient_preferred_name_contact(db: Session, *, conversation: Conversation) -> PatientContact | None:
    if not conversation.patient_id:
        return None
    return db.scalar(
        select(PatientContact)
        .where(
            PatientContact.tenant_id == conversation.tenant_id,
            PatientContact.patient_id == conversation.patient_id,
            PatientContact.channel == PREFERRED_NAME_CONTACT_CHANNEL,
        )
        .order_by(PatientContact.is_primary.desc(), PatientContact.created_at.asc())
        .limit(1)
    )


def _patient_saved_preferred_name(db: Session, *, conversation: Conversation) -> str | None:
    contact = _patient_preferred_name_contact(db, conversation=conversation)
    if not contact:
        return None
    name = str(contact.value or "").strip()
    if not _looks_like_person_name(name, min_words=1, max_words=2, max_chars=40):
        return None
    return _normalize_person_name(name)


def _patient_display_name_for_conversation(db: Session, *, conversation: Conversation) -> str | None:
    preferred_name = _patient_saved_preferred_name(db, conversation=conversation)
    if preferred_name:
        return preferred_name
    if not conversation.patient_id:
        return None
    patient = db.scalar(
        select(Patient).where(
            Patient.id == conversation.patient_id,
            Patient.tenant_id == conversation.tenant_id,
        )
    )
    if not patient or not _has_complete_patient_name(patient.full_name):
        return None
    first_name = _person_name_words(patient.full_name)[0]
    return _normalize_person_name(first_name)


def _upsert_patient_preferred_name(
    db: Session,
    *,
    conversation: Conversation,
    preferred_name: str,
) -> None:
    normalized_name = _normalize_person_name(preferred_name)
    if not normalized_name or not conversation.patient_id:
        return
    if not _looks_like_person_name(normalized_name, min_words=1, max_words=2, max_chars=40):
        return

    existing = _patient_preferred_name_contact(db, conversation=conversation)
    if existing:
        existing.value = normalized_name
        existing.normalized_value = _normalize_for_match(normalized_name)
        existing.is_primary = True
        existing.is_verified = False
        db.add(existing)
        db.flush()
        return

    db.add(
        PatientContact(
            tenant_id=conversation.tenant_id,
            patient_id=conversation.patient_id,
            channel=PREFERRED_NAME_CONTACT_CHANNEL,
            value=normalized_name,
            normalized_value=_normalize_for_match(normalized_name),
            is_primary=True,
            is_verified=False,
        )
    )
    db.flush()


def _patient_cpf_contact(db: Session, *, conversation: Conversation) -> PatientContact | None:
    if not conversation.patient_id:
        return None
    return db.scalar(
        select(PatientContact)
        .where(
            PatientContact.tenant_id == conversation.tenant_id,
            PatientContact.patient_id == conversation.patient_id,
            PatientContact.channel == CPF_CONTACT_CHANNEL,
        )
        .order_by(PatientContact.is_primary.desc(), PatientContact.created_at.asc())
        .limit(1)
    )


def _patient_saved_cpf(db: Session, *, conversation: Conversation) -> str | None:
    contact = _patient_cpf_contact(db, conversation=conversation)
    if contact:
        return _normalize_cpf_digits(contact.normalized_value or contact.value)
    if not conversation.patient_id:
        return None

    patient = db.scalar(
        select(Patient).where(
            Patient.id == conversation.patient_id,
            Patient.tenant_id == conversation.tenant_id,
        )
    )
    if not patient:
        return None
    return _normalize_cpf_digits(patient.normalized_cpf or patient.cpf)


def _patient_contact_value(
    db: Session,
    *,
    tenant_id: UUID,
    patient_id: UUID | None,
    channel: str,
) -> str | None:
    if not patient_id:
        return None
    contact = db.scalar(
        select(PatientContact)
        .where(
            PatientContact.tenant_id == tenant_id,
            PatientContact.patient_id == patient_id,
            PatientContact.channel == channel,
        )
        .order_by(PatientContact.is_primary.desc(), PatientContact.created_at.asc())
        .limit(1)
    )
    if not contact:
        return None
    value = str(contact.normalized_value or contact.value or "").strip()
    return value or None


def _linked_webchat_session(db: Session, *, conversation: Conversation) -> LinkFlowSession | None:
    if conversation.channel != "webchat":
        return None
    return db.scalar(
        select(LinkFlowSession)
        .where(
            LinkFlowSession.tenant_id == conversation.tenant_id,
            LinkFlowSession.linked_conversation_id == conversation.id,
        )
        .order_by(LinkFlowSession.created_at.desc())
        .limit(1)
    )


def _latest_webchat_summary_draft(db: Session, *, conversation: Conversation) -> dict[str, Any]:
    session = _linked_webchat_session(db, conversation=conversation)
    if not session:
        return {}
    event = db.scalar(
        select(LinkFlowEvent)
        .where(
            LinkFlowEvent.link_flow_session_id == session.id,
            LinkFlowEvent.event_name == "webchat_summary_updated",
        )
        .order_by(LinkFlowEvent.occurred_at.desc(), LinkFlowEvent.created_at.desc())
        .limit(1)
    )
    return event.payload if event and isinstance(event.payload, dict) else {}


def _format_manual_booking_date(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = date.fromisoformat(raw[:10])
    except ValueError:
        return raw
    return parsed.strftime("%d/%m/%Y")


def _manual_webchat_booking_snapshot(db: Session, *, conversation: Conversation) -> dict[str, Any] | None:
    draft = _latest_webchat_summary_draft(db, conversation=conversation)
    if not draft:
        return None

    unit_name = None
    unit_id_text = None
    unit_id_raw = draft.get("unit_id")
    try:
        unit_id = UUID(str(unit_id_raw)) if unit_id_raw else None
    except (TypeError, ValueError):
        unit_id = None
    if unit_id:
        unit = db.scalar(
            select(Unit).where(
                Unit.id == unit_id,
                Unit.tenant_id == conversation.tenant_id,
                Unit.is_active.is_(True),
            )
        )
        unit_name = unit.name if unit else None
        unit_id_text = str(unit.id) if unit else None

    procedure_type = str(draft.get("procedure_type") or "").strip() or None
    preferred_date_raw = str(draft.get("preferred_date") or "").strip() or None
    preferred_date = _format_manual_booking_date(preferred_date_raw)
    preferred_time = str(draft.get("preferred_time") or "").strip() or None

    if not any([unit_name, procedure_type, preferred_date, preferred_time]):
        return None

    return {
        "unit_id": unit_id_text,
        "unit_name": unit_name,
        "procedure_type": procedure_type,
        "preferred_date_iso": preferred_date_raw,
        "preferred_date": preferred_date,
        "preferred_time": preferred_time,
    }


def _saved_state_from_manual_webchat_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict):
        return None

    service = _normalize_resume_value(snapshot.get("procedure_type"))
    clinic_id = _normalize_resume_value(snapshot.get("unit_id"))
    clinic_name = _normalize_resume_value(snapshot.get("unit_name"))
    preferred_date_iso = _normalize_resume_value(snapshot.get("preferred_date_iso"))
    preferred_time = _normalize_resume_value(snapshot.get("preferred_time"))
    if not any((service, clinic_id, clinic_name, preferred_date_iso, preferred_time)):
        return None

    return {
        "service": service or None,
        "clinic_id": clinic_id or None,
        "clinic_name": clinic_name or None,
        "date": preferred_date_iso or None,
        "time": preferred_time or None,
        "selected_slot": None,
        "session_token": None,
        "requested_date": preferred_date_iso or None,
        "period": None,
        "source": "manual_webchat_summary",
    }


def _placeholder_webchat_patient(patient: Patient | None) -> bool:
    if not patient:
        return False
    if str(patient.origin or "").strip() == "link_flow_webchat":
        return True
    return _is_placeholder_name(patient.full_name) or _is_webchat_placeholder_phone(patient.phone)


def _find_existing_patient_by_cpf(
    db: Session,
    *,
    tenant_id: UUID,
    cpf_digits: str,
    exclude_patient_id: UUID | None,
) -> Patient | None:
    candidate = db.scalar(
        select(Patient).where(
            Patient.tenant_id == tenant_id,
            Patient.normalized_cpf == cpf_digits,
            Patient.id != exclude_patient_id,
        )
    )
    if candidate:
        return candidate

    matched_patient_id = db.scalar(
        select(PatientContact.patient_id)
        .where(
            PatientContact.tenant_id == tenant_id,
            PatientContact.channel == CPF_CONTACT_CHANNEL,
            PatientContact.normalized_value == cpf_digits,
            PatientContact.patient_id != exclude_patient_id,
        )
        .order_by(PatientContact.is_primary.desc(), PatientContact.created_at.asc())
        .limit(1)
    )
    if not matched_patient_id:
        return None
    return db.scalar(
        select(Patient).where(
            Patient.id == matched_patient_id,
            Patient.tenant_id == tenant_id,
        )
    )


def _find_existing_patient_by_phone(
    db: Session,
    *,
    tenant_id: UUID,
    phone_digits: str,
    exclude_patient_id: UUID | None,
) -> Patient | None:
    return db.scalar(
        select(Patient).where(
            Patient.tenant_id == tenant_id,
            Patient.normalized_phone == phone_digits,
            Patient.id != exclude_patient_id,
        )
    )


def _resolve_existing_webchat_patient_candidate(
    db: Session,
    *,
    conversation: Conversation,
    patient: Patient | None,
    inbound_text: str,
) -> Patient | None:
    if conversation.channel != "webchat" or not _placeholder_webchat_patient(patient):
        return None

    cpf_digits = _extract_cpf_from_text(inbound_text)
    phone_digits = _extract_phone_from_text(inbound_text)
    if not cpf_digits and not phone_digits:
        return None

    candidate_by_cpf = (
        _find_existing_patient_by_cpf(
            db,
            tenant_id=conversation.tenant_id,
            cpf_digits=cpf_digits,
            exclude_patient_id=patient.id if patient else None,
        )
        if cpf_digits
        else None
    )
    candidate_by_phone = (
        _find_existing_patient_by_phone(
            db,
            tenant_id=conversation.tenant_id,
            phone_digits=phone_digits,
            exclude_patient_id=patient.id if patient else None,
        )
        if phone_digits
        else None
    )
    if candidate_by_cpf and candidate_by_phone and candidate_by_cpf.id != candidate_by_phone.id:
        logger.info(
            "ai_autoresponder.webchat_patient_lookup_conflict",
            tenant_id=str(conversation.tenant_id),
            conversation_id=str(conversation.id),
            placeholder_patient_id=str(patient.id) if patient else None,
            cpf_patient_id=str(candidate_by_cpf.id),
            phone_patient_id=str(candidate_by_phone.id),
        )
        return None
    return candidate_by_cpf or candidate_by_phone


def _merge_webchat_placeholder_data_into_patient(
    db: Session,
    *,
    conversation: Conversation,
    source_patient: Patient,
    target_patient: Patient,
) -> None:
    if _has_complete_patient_name(source_patient.full_name) and not _has_complete_patient_name(target_patient.full_name):
        target_patient.full_name = source_patient.full_name

    source_email = str(source_patient.email or "").strip()
    if source_email and not str(target_patient.email or "").strip():
        target_patient.email = source_email

    if source_patient.birth_date and not target_patient.birth_date:
        target_patient.birth_date = source_patient.birth_date

    if source_patient.unit_id and not target_patient.unit_id:
        target_patient.unit_id = source_patient.unit_id

    source_phone = str(source_patient.normalized_phone or source_patient.phone or "").strip()
    if source_phone and not _is_webchat_placeholder_phone(source_phone) and not _has_patient_registration_phone(
        target_patient,
        conversation=conversation,
    ):
        conflicting_phone_owner = db.scalar(
            select(Patient).where(
                Patient.tenant_id == conversation.tenant_id,
                Patient.normalized_phone == source_phone,
                Patient.id != target_patient.id,
                Patient.id != source_patient.id,
            )
        )
        if not conflicting_phone_owner:
            target_patient.phone = source_phone
            target_patient.normalized_phone = source_phone

    source_cpf = _normalize_cpf_digits(source_patient.normalized_cpf or source_patient.cpf) or _normalize_cpf_digits(
        _patient_contact_value(
            db,
            tenant_id=conversation.tenant_id,
            patient_id=source_patient.id,
            channel=CPF_CONTACT_CHANNEL,
        )
    )
    if source_cpf:
        _sync_patient_cpf_record(
            db,
            conversation=conversation,
            patient=target_patient,
            cpf_digits=source_cpf,
        )

    source_preferred_name = _patient_contact_value(
        db,
        tenant_id=conversation.tenant_id,
        patient_id=source_patient.id,
        channel=PREFERRED_NAME_CONTACT_CHANNEL,
    )
    if source_preferred_name:
        _upsert_patient_preferred_name(
            db,
            conversation=conversation,
            preferred_name=source_preferred_name,
        )

    db.add(target_patient)


def _rebind_webchat_conversation_to_existing_patient(
    db: Session,
    *,
    conversation: Conversation,
    source_patient: Patient,
    target_patient: Patient,
) -> bool:
    if source_patient.id == target_patient.id:
        return False

    conversation.patient_id = target_patient.id
    tags = set(conversation.tags or [])
    tags.add("paciente_identificado_ia")
    conversation.tags = sorted(tags)
    db.add(conversation)

    session = _linked_webchat_session(db, conversation=conversation)
    if session:
        session.linked_patient_id = target_patient.id
        db.add(session)
        if session.linked_appointment_id:
            appointment = db.scalar(
                select(Appointment).where(
                    Appointment.id == session.linked_appointment_id,
                    Appointment.tenant_id == conversation.tenant_id,
                )
            )
            if appointment and appointment.patient_id == source_patient.id:
                appointment.patient_id = target_patient.id
                db.add(appointment)

    if conversation.lead_id:
        lead = db.scalar(
            select(Lead).where(
                Lead.id == conversation.lead_id,
                Lead.tenant_id == conversation.tenant_id,
            )
        )
        if lead and (lead.patient_id is None or lead.patient_id == source_patient.id):
            lead.patient_id = target_patient.id
            if _is_placeholder_name(lead.name) and _has_complete_patient_name(target_patient.full_name):
                lead.name = target_patient.full_name
            if not str(lead.email or "").strip() and str(target_patient.email or "").strip():
                lead.email = target_patient.email
            if not str(lead.phone or "").strip() and _has_patient_registration_phone(
                target_patient,
                conversation=conversation,
            ):
                lead.phone = target_patient.normalized_phone or target_patient.phone
            db.add(lead)

    _merge_webchat_placeholder_data_into_patient(
        db,
        conversation=conversation,
        source_patient=source_patient,
        target_patient=target_patient,
    )
    db.flush()
    logger.info(
        "ai_autoresponder.webchat_patient_rebound",
        tenant_id=str(conversation.tenant_id),
        conversation_id=str(conversation.id),
        placeholder_patient_id=str(source_patient.id),
        matched_patient_id=str(target_patient.id),
    )
    return True


def _maybe_rebind_webchat_patient_from_inbound(
    db: Session,
    *,
    conversation: Conversation,
    inbound_text: str,
) -> bool:
    if conversation.channel != "webchat" or not conversation.patient_id:
        return False

    current_patient = db.scalar(
        select(Patient).where(
            Patient.id == conversation.patient_id,
            Patient.tenant_id == conversation.tenant_id,
        )
    )
    if not current_patient:
        return False

    candidate = _resolve_existing_webchat_patient_candidate(
        db,
        conversation=conversation,
        patient=current_patient,
        inbound_text=inbound_text,
    )
    if not candidate:
        return False

    return _rebind_webchat_conversation_to_existing_patient(
        db,
        conversation=conversation,
        source_patient=current_patient,
        target_patient=candidate,
    )


def _sync_patient_cpf_record(
    db: Session,
    *,
    conversation: Conversation,
    patient: Patient | None,
    cpf_digits: str,
) -> bool:
    normalized = _normalize_cpf_digits(cpf_digits)
    if not normalized or not patient:
        return False

    current = _normalize_cpf_digits(patient.normalized_cpf or patient.cpf)
    if current == normalized:
        if patient.cpf != normalized or patient.normalized_cpf != normalized:
            patient.cpf = normalized
            patient.normalized_cpf = normalized
            db.add(patient)
            db.flush()
        return True

    conflicting_patient = db.scalar(
        select(Patient).where(
            Patient.tenant_id == conversation.tenant_id,
            Patient.normalized_cpf == normalized,
            Patient.id != patient.id,
        )
    )
    if conflicting_patient:
        logger.info(
            "ai_autoresponder.patient_cpf_conflict",
            tenant_id=str(conversation.tenant_id),
            conversation_id=str(conversation.id),
            patient_id=str(patient.id),
            conflicting_patient_id=str(conflicting_patient.id),
        )
        return False

    patient.cpf = normalized
    patient.normalized_cpf = normalized
    db.add(patient)
    db.flush()
    return True


def _upsert_patient_cpf(
    db: Session,
    *,
    conversation: Conversation,
    cpf_digits: str,
    patient: Patient | None = None,
) -> None:
    normalized = _normalize_cpf_digits(cpf_digits)
    if not normalized or not conversation.patient_id:
        return

    if patient is None:
        patient = db.scalar(
            select(Patient).where(
                Patient.id == conversation.patient_id,
                Patient.tenant_id == conversation.tenant_id,
            )
        )
    _sync_patient_cpf_record(
        db,
        conversation=conversation,
        patient=patient,
        cpf_digits=normalized,
    )

    existing = _patient_cpf_contact(db, conversation=conversation)
    if existing:
        existing.value = normalized
        existing.normalized_value = normalized
        existing.is_primary = True
        existing.is_verified = True
        db.add(existing)
        db.flush()
        return

    db.add(
        PatientContact(
            tenant_id=conversation.tenant_id,
            patient_id=conversation.patient_id,
            channel=CPF_CONTACT_CHANNEL,
            value=normalized,
            normalized_value=normalized,
            is_primary=True,
            is_verified=True,
        )
    )
    db.flush()


def _has_patient_registration_phone(patient: Patient | None, *, conversation: Conversation) -> bool:
    if not patient:
        return False
    phone = str(patient.phone or "").strip()
    if not phone or _is_webchat_placeholder_phone(phone):
        return False
    normalized_phone = normalize_phone(phone)
    if conversation.channel == "webchat":
        return len(normalized_phone) >= 10
    return bool(normalized_phone)


def _patient_registration_snapshot(db: Session, *, conversation: Conversation) -> dict[str, Any]:
    patient = None
    if conversation.patient_id:
        patient = db.scalar(
            select(Patient).where(
                Patient.id == conversation.patient_id,
                Patient.tenant_id == conversation.tenant_id,
            )
        )
    cpf_digits = _patient_saved_cpf(db, conversation=conversation)
    return {
        "patient": patient,
        "full_name": str(patient.full_name or "").strip() if patient else "",
        "birth_date": patient.birth_date if patient else None,
        "cpf": cpf_digits,
        "phone": str(patient.phone or "").strip() if patient else "",
    }


def _missing_patient_registration_fields(db: Session, *, conversation: Conversation) -> list[str]:
    snapshot = _patient_registration_snapshot(db, conversation=conversation)
    patient = snapshot.get("patient")
    missing: list[str] = []
    if not patient or not _has_complete_patient_name(snapshot.get("full_name")):
        missing.append("full_name")
    if not snapshot.get("cpf"):
        missing.append("cpf")
    if not snapshot.get("birth_date"):
        missing.append("birth_date")
    if conversation.channel == "webchat" and not _has_patient_registration_phone(patient, conversation=conversation):
        missing.append("phone")
    return missing


def _registration_field_label(field: str) -> str:
    labels = {
        "full_name": "nome completo",
        "cpf": "CPF",
        "birth_date": "data de nascimento",
        "phone": "celular/WhatsApp com DDD",
    }
    return labels.get(field, field)


def _format_registration_missing_fields(fields: list[str]) -> str:
    labels = [_registration_field_label(field) for field in fields]
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    return f"{', '.join(labels[:-1])} e {labels[-1]}"


def _registration_skip_requested(text: str) -> bool:
    normalized = _normalize_for_match(text)
    return any(pattern in normalized for pattern in REGISTRATION_SKIP_PATTERNS)


def _webchat_existing_patient_lookup_prompt_needed(db: Session, *, conversation: Conversation) -> bool:
    if conversation.channel != "webchat":
        return False
    if "webchat_lookup_prompt_sent" in set(conversation.tags or []):
        return False
    snapshot = _patient_registration_snapshot(db, conversation=conversation)
    patient = snapshot.get("patient")
    return not snapshot.get("cpf") and not _has_patient_registration_phone(patient, conversation=conversation)


def _append_webchat_existing_patient_lookup_hint(
    db: Session,
    *,
    conversation: Conversation,
    response: dict[str, Any],
) -> dict[str, Any]:
    if not _webchat_existing_patient_lookup_prompt_needed(db, conversation=conversation):
        return response

    hint = (
        "Se você já é paciente da clínica, também pode me enviar CPF ou celular com DDD a qualquer momento "
        "para eu localizar seu cadastro e continuar com seus dados salvos."
    )
    base_text = str(response.get("response_text") or "").strip()
    if hint not in base_text:
        response["response_text"] = f"{base_text}\n\n{hint}" if base_text else hint

    metadata = response.get("metadata")
    if isinstance(metadata, dict):
        metadata["early_identification_prompt"] = True
        response["metadata"] = metadata

    tags = set(conversation.tags or [])
    tags.add("webchat_lookup_prompt_sent")
    conversation.tags = sorted(tags)
    db.add(conversation)
    return response


def _capture_patient_registration_from_inbound(
    db: Session,
    *,
    conversation: Conversation,
    inbound_text: str,
    allow_loose_name: bool = False,
    allow_unlabeled_birth_date: bool = False,
) -> dict[str, str]:
    if not conversation.patient_id:
        return {}

    patient = db.scalar(
        select(Patient).where(
            Patient.id == conversation.patient_id,
            Patient.tenant_id == conversation.tenant_id,
        )
    )
    if not patient:
        return {}

    changes: dict[str, str] = {}
    extracted_name = (
        _extract_registration_name_from_text(inbound_text)
        if allow_loose_name
        else _extract_contact_name(inbound_text)
    )
    if extracted_name and _has_complete_patient_name(extracted_name) and not _has_complete_patient_name(patient.full_name):
        patient.full_name = extracted_name
        changes["patient_full_name"] = extracted_name
    elif extracted_name and not _has_complete_patient_name(extracted_name):
        _upsert_patient_preferred_name(db, conversation=conversation, preferred_name=extracted_name)
        changes["patient_preferred_name"] = extracted_name

    extracted_birth_date = _extract_birth_date_from_text(
        inbound_text,
        allow_unlabeled=allow_unlabeled_birth_date,
    )
    if extracted_birth_date and not patient.birth_date:
        patient.birth_date = extracted_birth_date
        changes["patient_birth_date"] = extracted_birth_date.isoformat()

    cpf_digits = _extract_cpf_from_text(inbound_text)
    if cpf_digits:
        _upsert_patient_cpf(
            db,
            conversation=conversation,
            cpf_digits=cpf_digits,
            patient=patient,
        )
        changes["patient_cpf"] = cpf_digits

    extracted_phone = _extract_phone_from_text(inbound_text)
    if extracted_phone and not _has_patient_registration_phone(patient, conversation=conversation):
        conflicting_patient = db.scalar(
            select(Patient).where(
                Patient.tenant_id == conversation.tenant_id,
                Patient.normalized_phone == extracted_phone,
                Patient.id != patient.id,
            )
        )
        if conflicting_patient:
            logger.info(
                "ai_autoresponder.patient_phone_conflict",
                tenant_id=str(conversation.tenant_id),
                conversation_id=str(conversation.id),
                patient_id=str(patient.id),
                conflicting_patient_id=str(conflicting_patient.id),
            )
        else:
            patient.phone = extracted_phone
            patient.normalized_phone = extracted_phone
            lead = db.scalar(
                select(Lead).where(
                    Lead.tenant_id == conversation.tenant_id,
                    Lead.patient_id == patient.id,
                )
            )
            if lead and not str(lead.phone or "").strip():
                lead.phone = extracted_phone
                db.add(lead)
            changes["patient_phone"] = extracted_phone

    if changes:
        db.add(patient)
        tags = set(conversation.tags or [])
        tags.add("dados_cadastrais_capturados")
        conversation.tags = sorted(tags)
        db.add(conversation)
        db.flush()
        logger.info(
            "ai_autoresponder.patient_registration_captured",
            tenant_id=str(conversation.tenant_id),
            conversation_id=str(conversation.id),
            fields=list(changes.keys()),
        )
    return changes


def _booking_reset_requested(text: str) -> bool:
    normalized = _normalize_for_match(text)
    if not normalized:
        return False
    return any(pattern in normalized for pattern in BOOKING_RESET_PATTERNS)


def _booking_resume_requested(text: str) -> bool:
    normalized = _normalize_for_match(text)
    if not normalized:
        return False
    return any(pattern in normalized for pattern in BOOKING_RESUME_PATTERNS)


def _booking_restart_requested(text: str) -> bool:
    normalized = _normalize_for_match(text)
    if not normalized:
        return False
    return any(pattern in normalized for pattern in BOOKING_RESTART_PATTERNS)


def _conversation_destination_phone(db: Session, *, conversation: Conversation) -> str | None:
    destination, _provider_context = resolve_whatsapp_reply_route(db, conversation=conversation)
    return destination


def _is_appointment_lookup_request(text: str) -> bool:
    normalized = _normalize_for_match(text)
    if any(pattern in normalized for pattern in APPOINTMENT_LOOKUP_PATTERNS):
        return True
    has_appointment_term = any(
        term in normalized
        for term in ("agendamento", "agendamentos", "consulta", "consultas", "horario", "horário")
    )
    has_lookup_term = any(
        term in normalized
        for term in ("meu", "minha", "meus", "minhas", "quando", "qual", "quais", "ver", "consultar")
    )
    return has_appointment_term and has_lookup_term


def _is_appointment_cancel_request(text: str) -> bool:
    normalized = _normalize_for_match(text)
    return any(pattern in normalized for pattern in APPOINTMENT_CANCEL_PATTERNS)


def _is_appointment_reschedule_request(text: str) -> bool:
    normalized = _normalize_for_match(text)
    return any(pattern in normalized for pattern in APPOINTMENT_RESCHEDULE_PATTERNS)


def _visit_guidance_requested_topics(text: str) -> set[str]:
    normalized = _normalize_for_match(text)
    topics: set[str] = set()
    if not normalized:
        return topics
    if any(pattern in normalized for pattern in VISIT_GUIDANCE_ADDRESS_PATTERNS):
        topics.add("address")
    if any(pattern in normalized for pattern in VISIT_GUIDANCE_PROFESSIONAL_PATTERNS):
        topics.add("professional")
    if any(pattern in normalized for pattern in VISIT_GUIDANCE_DOCUMENT_PATTERNS):
        topics.add("document")
    if any(pattern in normalized for pattern in VISIT_GUIDANCE_OVERVIEW_PATTERNS):
        topics.update({"address", "professional", "document"})
    return topics


def _guidance_professional_label(value: str | None) -> str | None:
    name = _compact_text(value, max_length=120)
    if not name:
        return None
    normalized = _normalize_for_match(name)
    if normalized in {"equipe clinica", "equipe da clinica", "equipe"}:
        return None
    return name


def _match_unit_from_text(units: list[Unit], text: str) -> Unit | None:
    normalized = _normalize_for_match(text)
    if not normalized:
        return None
    for unit in units:
        unit_name = _normalize_for_match(unit.name)
        unit_code = _normalize_for_match(unit.code or "")
        if unit_code and unit_code in normalized:
            return unit
        unit_pieces = [
            piece
            for piece in unit_name.split()
            if len(piece) > 2 and piece not in {"unidade", "clinica", "clínica", "zona"}
        ]
        if unit_name and (
            normalized == unit_name
            or normalized in unit_name
            or unit_name in normalized
            or any(piece in normalized for piece in unit_pieces)
        ):
            return unit
    return None


def _format_appointment_local_label(appointment: Appointment, *, timezone_name: str) -> str:
    starts_at = appointment.starts_at
    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=UTC)
    try:
        local_dt = starts_at.astimezone(ZoneInfo(timezone_name))
    except ZoneInfoNotFoundError:
        local_dt = starts_at
    weekday = _weekday_label_pt(local_dt.weekday())
    return f"{weekday}, {local_dt.strftime('%d/%m/%Y às %H:%M')}"


def _active_patient_appointments(
    db: Session,
    *,
    conversation: Conversation,
    limit: int = 5,
) -> list[Appointment]:
    if not conversation.patient_id:
        return []
    return db.execute(
        select(Appointment)
        .where(
            Appointment.tenant_id == conversation.tenant_id,
            Appointment.patient_id == conversation.patient_id,
            Appointment.status.in_(["agendada", "confirmada", "reagendada"]),
            Appointment.starts_at >= datetime.now(UTC) - timedelta(hours=2),
        )
        .order_by(Appointment.starts_at.asc())
        .limit(limit)
    ).scalars().all()


def _appointment_visit_guidance_context(
    db: Session,
    *,
    conversation: Conversation,
    config: dict[str, Any],
    inbound_text: str,
) -> dict[str, Any] | None:
    appointments = _active_patient_appointments(db, conversation=conversation, limit=5)
    if not appointments and conversation.patient_id:
        appointments = db.execute(
            select(Appointment)
            .where(
                Appointment.tenant_id == conversation.tenant_id,
                Appointment.patient_id == conversation.patient_id,
                Appointment.status.in_(["agendada", "confirmada", "reagendada", "realizada"]),
                Appointment.starts_at >= datetime.now(UTC) - timedelta(days=90),
            )
            .order_by(Appointment.starts_at.desc())
            .limit(5)
        ).scalars().all()
    timezone_name = str(
        ((config.get("business_hours") or {}).get("timezone"))
        or settings.app_timezone
        or "America/Sao_Paulo"
    )

    if appointments:
        unit_ids = {appointment.unit_id for appointment in appointments if appointment.unit_id}
        professional_ids = {appointment.professional_id for appointment in appointments if appointment.professional_id}
        units = (
            db.execute(
                select(Unit).where(
                    Unit.tenant_id == conversation.tenant_id,
                    Unit.id.in_(unit_ids),
                    Unit.is_active.is_(True),
                )
            ).scalars().all()
            if unit_ids
            else []
        )
        professionals = (
            db.execute(
                select(Professional).where(
                    Professional.tenant_id == conversation.tenant_id,
                    Professional.id.in_(professional_ids),
                )
            ).scalars().all()
            if professional_ids
            else []
        )
        unit_by_id = {unit.id: unit for unit in units}
        professional_by_id = {professional.id: professional for professional in professionals}

        matched_unit = _match_unit_from_text(units, inbound_text)
        selected_appointment = None
        if matched_unit:
            selected_appointment = next(
                (appointment for appointment in appointments if appointment.unit_id == matched_unit.id),
                None,
            )
        if not selected_appointment:
            selected_appointment = appointments[0]

        unit = unit_by_id.get(selected_appointment.unit_id) if selected_appointment.unit_id else None
        professional = (
            professional_by_id.get(selected_appointment.professional_id)
            if selected_appointment.professional_id
            else None
        )
        return {
            "appointment_id": str(selected_appointment.id),
            "procedure_type": selected_appointment.procedure_type,
            "unit_id": str(unit.id) if unit else None,
            "unit_name": unit.name if unit else None,
            "unit_address": _format_unit_address(unit.address) if unit else None,
            "selected_slot_label": _format_appointment_local_label(
                selected_appointment,
                timezone_name=timezone_name,
            ),
            "professional_id": str(professional.id) if professional else None,
            "professional_name": professional.full_name if professional else None,
            "has_appointment": True,
        }

    units = db.execute(
        select(Unit)
        .where(
            Unit.tenant_id == conversation.tenant_id,
            Unit.is_active.is_(True),
        )
        .order_by(Unit.name.asc())
    ).scalars().all()
    matched_unit = _match_unit_from_text(units, inbound_text)
    if not matched_unit:
        return None

    return {
        "appointment_id": None,
        "procedure_type": None,
        "unit_id": str(matched_unit.id),
        "unit_name": matched_unit.name,
        "unit_address": _format_unit_address(matched_unit.address),
        "selected_slot_label": None,
        "professional_id": None,
        "professional_name": None,
        "has_appointment": False,
    }


def _appointment_unit(db: Session, *, conversation: Conversation, appointment: Appointment) -> Unit | None:
    return db.scalar(
        select(Unit).where(
            Unit.id == appointment.unit_id,
            Unit.tenant_id == conversation.tenant_id,
            Unit.is_active.is_(True),
        )
    )


def _appointment_summary_for_patient(
    db: Session,
    *,
    conversation: Conversation,
    appointment: Appointment,
    config: dict[str, Any],
) -> str:
    timezone_name = str(
        ((config.get("business_hours") or {}).get("timezone"))
        or settings.app_timezone
        or "America/Sao_Paulo"
    )
    unit = _appointment_unit(db, conversation=conversation, appointment=appointment)
    unit_name = unit.name if unit else "unidade cadastrada"
    return f"{appointment.procedure_type} na {unit_name}, {_format_appointment_local_label(appointment, timezone_name=timezone_name)}"


def _appointment_lookup_response(
    db: Session,
    *,
    conversation: Conversation,
    config: dict[str, Any],
) -> dict[str, Any]:
    timezone_name = str(
        ((config.get("business_hours") or {}).get("timezone"))
        or settings.app_timezone
        or "America/Sao_Paulo"
    )
    if not conversation.patient_id:
        return {
            "mode": "appointment_lookup_response",
            "response_text": (
                "Ainda não consegui vincular sua conversa a um cadastro de paciente. "
                "Me envie seu nome completo ou posso encaminhar para a equipe conferir sua agenda com segurança."
            ),
            "metadata": {
                "reason": "appointment_lookup_missing_patient",
                "appointments": [],
            },
        }

    appointments = _active_patient_appointments(db, conversation=conversation, limit=5)

    if not appointments:
        manual_snapshot = _manual_webchat_booking_snapshot(db, conversation=conversation)
        if manual_snapshot:
            lines = [
                "Ainda nao existe um horario confirmado no sistema para o seu cadastro.",
                "Mas estes dados ja ficaram salvos no seu atendimento:",
            ]
            if manual_snapshot.get("procedure_type"):
                lines.append(f"• Servico: {manual_snapshot['procedure_type']}")
            if manual_snapshot.get("unit_name"):
                lines.append(f"• Unidade: {manual_snapshot['unit_name']}")
            if manual_snapshot.get("preferred_date"):
                lines.append(f"• Data desejada: {manual_snapshot['preferred_date']}")
            if manual_snapshot.get("preferred_time"):
                lines.append(f"• Horario desejado: {manual_snapshot['preferred_time']}")
            lines.append("Se quiser, eu posso continuar a confirmacao desse horario para voce agora.")
            return {
                "mode": "appointment_lookup_response",
                "response_text": "\n".join(lines),
                "metadata": {
                    "reason": "appointment_lookup_manual_draft",
                    "appointments": [],
                    "manual_booking_snapshot": manual_snapshot,
                },
            }
        return {
            "mode": "appointment_lookup_response",
            "response_text": (
                "Conferi sua agenda por aqui e não encontrei nenhum agendamento ativo no seu cadastro. "
                "Se quiser, posso te ajudar a marcar uma avaliação agora ou encaminhar para a equipe verificar manualmente."
            ),
            "metadata": {
                "reason": "appointment_lookup_empty",
                "appointments": [],
            },
        }

    unit_ids = {appointment.unit_id for appointment in appointments if appointment.unit_id}
    professional_ids = {appointment.professional_id for appointment in appointments if appointment.professional_id}
    units = db.execute(
        select(Unit).where(
            Unit.tenant_id == conversation.tenant_id,
            Unit.id.in_(unit_ids),
        )
    ).scalars().all() if unit_ids else []
    professionals = db.execute(
        select(Professional).where(
            Professional.tenant_id == conversation.tenant_id,
            Professional.id.in_(professional_ids),
        )
    ).scalars().all() if professional_ids else []
    unit_by_id = {unit.id: unit.name for unit in units}
    professional_by_id = {professional.id: professional.full_name for professional in professionals}

    lines = ["Conferi sua agenda e encontrei estes agendamentos ativos:"]
    payload_appointments: list[dict[str, Any]] = []
    for index, appointment in enumerate(appointments, start=1):
        unit_name = unit_by_id.get(appointment.unit_id) or "unidade cadastrada"
        professional_name = professional_by_id.get(appointment.professional_id) if appointment.professional_id else None
        local_label = _format_appointment_local_label(appointment, timezone_name=timezone_name)
        professional_part = f" com {professional_name}" if professional_name else ""
        lines.append(
            f"{index}. {appointment.procedure_type} na {unit_name}, {local_label}{professional_part}. "
            f"Status: {appointment.status}."
        )
        payload_appointments.append(
            {
                "id": str(appointment.id),
                "procedure_type": appointment.procedure_type,
                "unit_id": str(appointment.unit_id),
                "unit_name": unit_name,
                "professional_id": str(appointment.professional_id) if appointment.professional_id else None,
                "professional_name": professional_name,
                "starts_at": appointment.starts_at.isoformat(),
                "starts_at_label": local_label,
                "status": str(appointment.status),
                "confirmation_status": appointment.confirmation_status,
            }
        )
    lines.append("Se precisar remarcar ou cancelar, me diga por aqui que eu te ajudo com cuidado.")

    return {
        "mode": "appointment_lookup_response",
        "response_text": "\n".join(lines),
        "metadata": {
            "reason": "appointment_lookup_found",
            "appointments": payload_appointments,
        },
    }


def _render_patient_appointments_context(
    db: Session,
    *,
    conversation: Conversation,
    config: dict[str, Any],
) -> str:
    if not conversation.patient_id:
        return ""
    lookup = _appointment_lookup_response(db, conversation=conversation, config=config)
    metadata = lookup.get("metadata") if isinstance(lookup.get("metadata"), dict) else {}
    appointments = metadata.get("appointments") if isinstance(metadata.get("appointments"), list) else []
    if not appointments:
        return "Agendamentos ativos do paciente: nenhum encontrado no cadastro vinculado a esta conversa."

    lines = [
        "Agendamentos ativos do paciente (dados reais do sistema, use somente se o paciente perguntar):"
    ]
    for item in appointments:
        if not isinstance(item, dict):
            continue
        details = [
            f"servico={item.get('procedure_type')}",
            f"unidade={item.get('unit_name')}",
            f"data_hora={item.get('starts_at_label')}",
            f"status={item.get('status')}",
            f"id={item.get('id')}",
        ]
        professional_name = str(item.get("professional_name") or "").strip()
        if professional_name:
            details.append(f"profissional={professional_name}")
        lines.append(f"- {'; '.join(str(detail) for detail in details if detail)}")
    return "\n".join(lines)


def _build_appointment_selection_required_response(
    db: Session,
    *,
    conversation: Conversation,
    config: dict[str, Any],
    intent_label: str,
) -> dict[str, Any]:
    lookup = _appointment_lookup_response(db, conversation=conversation, config=config)
    text = str(lookup.get("response_text") or "").strip()
    return {
        "mode": "appointment_lookup_response",
        "response_text": (
            f"{text}\n\n"
            f"Para {intent_label}, me diga qual deles você quer alterar. Pode responder com o número do agendamento."
        ).strip(),
        "metadata": {
            **(lookup.get("metadata") if isinstance(lookup.get("metadata"), dict) else {}),
            "reason": f"{intent_label}_requires_selection",
        },
    }


def _build_cancel_confirmation_response(
    db: Session,
    *,
    conversation: Conversation,
    appointment: Appointment,
    config: dict[str, Any],
    session_token: str | None = None,
) -> dict[str, Any]:
    summary = _appointment_summary_for_patient(db, conversation=conversation, appointment=appointment, config=config)
    buttons = [
        {"id": "cancel_yes", "title": "Sim, cancelar"},
        {"id": "cancel_no", "title": "Manter consulta"},
    ]
    metadata = _wizard_metadata_with_session(
        metadata={
            "reason": "cancel_confirmation_required",
            "appointment_id": str(appointment.id),
            "procedure_type": appointment.procedure_type,
            "unit_id": str(appointment.unit_id),
            "buttons": buttons,
            "header_text": "Cancelamento",
            "body_text": "Confirme se deseja cancelar esta consulta.",
            "footer_text": "Se preferir, responda por texto.",
        },
        session_token=session_token,
        step="cancel_confirm",
    )
    return {
        "mode": "booking_cancel_confirm",
        "response_text": (
            "Encontrei sua consulta ativa:\n"
            f"• {summary}\n"
            "Você quer mesmo cancelar esse agendamento?"
        ),
        "metadata": metadata,
    }


def _cancel_appointment_from_ai(
    db: Session,
    *,
    conversation: Conversation,
    appointment: Appointment,
) -> dict[str, Any]:
    previous_status = str(appointment.status)
    appointment.status = "cancelada"
    appointment.confirmation_status = "nao_confirmada"
    appointment.canceled_at = datetime.now(UTC)
    appointment.canceled_reason = "Cancelado pelo paciente via IA/WhatsApp."
    db.add(appointment)
    db.flush()

    db.add(
        AppointmentEvent(
            tenant_id=conversation.tenant_id,
            appointment_id=appointment.id,
            event_type="canceled",
            from_status=previous_status,
            to_status=appointment.status,
            metadata_json={
                "origin": "ai_autoresponder",
                "channel": conversation.channel,
                "conversation_id": str(conversation.id),
            },
            created_by_user_id=None,
        )
    )
    tags = set(conversation.tags or [])
    tags.add("agendamento_cancelado_ia")
    conversation.tags = sorted(tags)
    db.add(conversation)
    db.add(
        MessageEvent(
            tenant_id=conversation.tenant_id,
            event_type="ai_appointment_canceled",
            payload={
                "conversation_id": str(conversation.id),
                "appointment_id": str(appointment.id),
                "previous_status": previous_status,
            },
        )
    )
    try:
        emit_event(
            db,
            tenant_id=conversation.tenant_id,
            event_key="consulta_atualizada",
            payload={
                "appointment_id": str(appointment.id),
                "patient_id": str(appointment.patient_id),
                "status": appointment.status,
                "previous_status": previous_status,
                "confirmation_status": appointment.confirmation_status,
            },
        )
    except Exception as exc:
        logger.warning(
            "ai_autoresponder.cancel_event_emit_failed",
            tenant_id=str(conversation.tenant_id),
            conversation_id=str(conversation.id),
            appointment_id=str(appointment.id),
            error=str(exc),
        )
    return {
        "mode": "booking_cancelled",
        "response_text": (
            "Pronto, seu agendamento foi cancelado com sucesso.\n"
            "Se quiser marcar outro horário depois, posso te ajudar por aqui."
        ),
        "metadata": {
            "reason": "appointment_cancelled",
            "appointment_id": str(appointment.id),
            "previous_status": previous_status,
        },
    }


def _build_reschedule_day_response(
    db: Session,
    *,
    conversation: Conversation,
    appointment: Appointment,
    config: dict[str, Any],
    requested_date: date | None,
    period: str | None,
    operation_timezone: ZoneInfo,
    session_token: str | None = None,
) -> dict[str, Any]:
    unit = _appointment_unit(db, conversation=conversation, appointment=appointment)
    if not unit:
        return {
            "mode": "no_unit_available",
            "response_text": "Não consegui acessar a unidade desse agendamento agora. Vou encaminhar para a equipe conferir.",
            "metadata": {"reason": "reschedule_unit_missing", "handoff_required": True},
        }
    day_choices = _wizard_collect_day_choices(
        db,
        conversation=conversation,
        unit_id=unit.id,
        procedure_type=appointment.procedure_type,
        period=period,
        requested_date=requested_date,
        operation_timezone=operation_timezone,
        config=config,
    )
    if not day_choices:
        return {
            "mode": "no_slots_general",
            "response_text": (
                "No momento não encontrei novos dias disponíveis para remarcar essa consulta. "
                "Posso encaminhar para a equipe verificar possibilidades manualmente."
            ),
            "metadata": {
                "reason": "reschedule_no_days_available",
                "appointment_id": str(appointment.id),
                "handoff_required": True,
                "handoff_reason": "reschedule_no_days_available",
            },
        }
    rows = [
        {
            "id": choice["id"],
            "title": choice["label"].split(",")[0][:24],
            "description": choice["label"][:72],
        }
        for choice in day_choices
    ]
    rows.append({"id": "reschedule_keep_current", "title": "Manter atual", "description": "Não alterar consulta"})
    rows.append({"id": "menu_human", "title": "Falar atendente", "description": "Encaminhar para humano"})
    metadata = _wizard_metadata_with_session(
        metadata={
            "reason": "reschedule_day_select",
            "appointment_id": str(appointment.id),
            "procedure_type": appointment.procedure_type,
            "unit_id": str(unit.id),
            "unit_name": unit.name,
            "period": period,
            "requested_date": requested_date.isoformat() if requested_date else None,
            "day_choices": day_choices,
            "rows": rows,
            "button_title": "Dias",
            "section_title": "Escolha o novo dia",
            "header_text": "Remarcação",
            "body_text": "Escolha o novo dia para a consulta.",
            "footer_text": "Você também pode escrever a data por mensagem.",
        },
        session_token=session_token,
        step="reschedule_day",
    )
    return {
        "mode": "booking_reschedule_day_select",
        "response_text": (
            "Combinado, vou te ajudar a remarcar sem perder o controle da agenda. "
            "Escolha abaixo o novo dia que funciona melhor para você."
        ),
        "metadata": metadata,
    }


def _appointment_cancel_request_response(
    db: Session,
    *,
    conversation: Conversation,
    config: dict[str, Any],
) -> dict[str, Any]:
    appointments = _active_patient_appointments(db, conversation=conversation, limit=5)
    if len(appointments) == 1:
        return _build_cancel_confirmation_response(
            db,
            conversation=conversation,
            appointment=appointments[0],
            config=config,
        )
    if len(appointments) > 1:
        return _build_appointment_selection_required_response(
            db,
            conversation=conversation,
            config=config,
            intent_label="cancelar o agendamento",
        )
    lookup = _appointment_lookup_response(db, conversation=conversation, config=config)
    return {
        "mode": "appointment_lookup_response",
        "response_text": (
            f"{lookup.get('response_text')}\n\n"
            "Não cancelei nada porque não encontrei uma consulta ativa vinculada a este cadastro."
        ),
        "metadata": {
            **(lookup.get("metadata") if isinstance(lookup.get("metadata"), dict) else {}),
            "reason": "cancel_without_active_appointment",
        },
    }


def _appointment_reschedule_request_response(
    db: Session,
    *,
    conversation: Conversation,
    config: dict[str, Any],
    requested_date: date | None,
    period: str | None,
    operation_timezone: ZoneInfo,
) -> dict[str, Any]:
    appointments = _active_patient_appointments(db, conversation=conversation, limit=5)
    if len(appointments) == 1:
        return _build_reschedule_day_response(
            db,
            conversation=conversation,
            appointment=appointments[0],
            config=config,
            requested_date=requested_date,
            period=period,
            operation_timezone=operation_timezone,
        )
    if len(appointments) > 1:
        return _build_appointment_selection_required_response(
            db,
            conversation=conversation,
            config=config,
            intent_label="remarcar o agendamento",
        )
    lookup = _appointment_lookup_response(db, conversation=conversation, config=config)
    return {
        "mode": "appointment_lookup_response",
        "response_text": (
            f"{lookup.get('response_text')}\n\n"
            "Para remarcar, preciso primeiro localizar uma consulta ativa. Se ela não aparecer aqui, posso encaminhar para a equipe conferir."
        ),
        "metadata": {
            **(lookup.get("metadata") if isinstance(lookup.get("metadata"), dict) else {}),
            "reason": "reschedule_without_active_appointment",
        },
    }


def _build_reschedule_time_response(
    db: Session,
    *,
    conversation: Conversation,
    appointment: Appointment,
    selected_date: date,
    config: dict[str, Any],
    period: str | None,
    session_token: str | None = None,
) -> dict[str, Any]:
    unit = _appointment_unit(db, conversation=conversation, appointment=appointment)
    if not unit:
        return {
            "mode": "no_unit_available",
            "response_text": "Não consegui acessar a unidade desse agendamento agora. Vou encaminhar para a equipe conferir.",
            "metadata": {"reason": "reschedule_unit_missing", "handoff_required": True},
        }
    slot_choices = _wizard_collect_time_choices(
        db,
        conversation=conversation,
        unit=unit,
        procedure_type=appointment.procedure_type,
        period=period,
        selected_date=selected_date,
        config=config,
    )
    if not slot_choices:
        return {
            "mode": "no_slots_general",
            "response_text": (
                f"No momento não encontrei horários livres para remarcar em {selected_date.strftime('%d/%m')}. "
                "Posso te mostrar outro dia ou encaminhar para a equipe conferir manualmente."
            ),
            "metadata": {
                "reason": "reschedule_no_times_available",
                "appointment_id": str(appointment.id),
            },
        }
    rows: list[dict[str, str]] = []
    for choice in slot_choices[:7]:
        rows.append(
            {
                "id": str(choice.get("id") or ""),
                "title": str(choice.get("time") or "Horário")[:24],
                "description": str(choice.get("label") or "")[:72],
            }
        )
    rows.append({"id": "time_change_day", "title": "Trocar dia", "description": "Selecionar outro dia"})
    rows.append({"id": "menu_human", "title": "Falar atendente", "description": "Encaminhar para humano"})
    metadata = _wizard_metadata_with_session(
        metadata={
            "reason": "reschedule_time_select",
            "appointment_id": str(appointment.id),
            "procedure_type": appointment.procedure_type,
            "unit_id": str(unit.id),
            "unit_name": unit.name,
            "period": period,
            "requested_date": selected_date.isoformat(),
            "slot_choices": slot_choices[:7],
            "rows": rows,
            "button_title": "Horários",
            "section_title": "Escolha o novo horário",
            "header_text": "Remarcação",
            "body_text": "Escolha o novo horário para a consulta.",
            "footer_text": "Você também pode escrever o horário por mensagem.",
        },
        session_token=session_token,
        step="reschedule_time",
    )
    return {
        "mode": "booking_reschedule_time_select",
        "response_text": f"Perfeito. Agora escolha o novo horário para {selected_date.strftime('%d/%m')}.",
        "metadata": metadata,
    }


def _build_reschedule_confirm_response(
    *,
    appointment: Appointment,
    unit: Unit,
    selected_date: date,
    selected_slot_choice: dict[str, Any],
    period: str | None,
    session_token: str | None = None,
) -> dict[str, Any]:
    slot_label = str(selected_slot_choice.get("label") or "")
    buttons = [
        {"id": "reschedule_yes", "title": "Sim, remarcar"},
        {"id": "reschedule_no", "title": "Não alterar"},
    ]
    metadata = _wizard_metadata_with_session(
        metadata={
            "reason": "reschedule_confirmation_required",
            "appointment_id": str(appointment.id),
            "procedure_type": appointment.procedure_type,
            "unit_id": str(unit.id),
            "unit_name": unit.name,
            "period": period,
            "requested_date": selected_date.isoformat(),
            "selected_slot": selected_slot_choice,
            "buttons": buttons,
            "header_text": "Confirmar remarcação",
            "body_text": "Confirme se posso remarcar para este horário.",
            "footer_text": "Se preferir, responda por texto.",
        },
        session_token=session_token,
        step="reschedule_confirm",
    )
    return {
        "mode": "booking_reschedule_confirm",
        "response_text": (
            "Posso confirmar a remarcação?\n"
            f"• Serviço: {appointment.procedure_type}\n"
            f"• Unidade: {unit.name}\n"
            f"• Nova data: {selected_date.strftime('%d/%m')}\n"
            f"• Novo horário: {slot_label}"
        ),
        "metadata": metadata,
    }


def _reschedule_appointment_from_ai(
    db: Session,
    *,
    conversation: Conversation,
    appointment: Appointment,
    selected_slot: dict[str, Any],
) -> dict[str, Any]:
    previous_status = str(appointment.status)
    previous_starts_at = appointment.starts_at
    selected_professional_id, selected_professional_name = _resolve_selected_slot_professional(
        db,
        tenant_id=conversation.tenant_id,
        unit_id=appointment.unit_id,
        procedure_type=appointment.procedure_type or "",
        selected_slot=selected_slot,
        exclude_appointment_id=appointment.id,
    )
    if not selected_professional_id:
        return {
            "mode": "selected_slot_no_longer_available",
            "response_text": "Esse horário acabou de ser reservado. Escolha outro horário para remarcar.",
            "metadata": {"reason": "selected_slot_no_longer_available"},
        }
    selected_slot = {
        **selected_slot,
        "professional_id": str(selected_professional_id),
        "professional_name": selected_professional_name,
    }

    appointment.starts_at = selected_slot["starts_at_utc"]
    appointment.ends_at = selected_slot["ends_at_utc"]
    appointment.professional_id = selected_professional_id
    appointment.status = "reagendada"
    appointment.confirmation_status = "confirmada"
    appointment.confirmed_at = datetime.now(UTC)
    db.add(appointment)
    db.flush()

    db.add(
        AppointmentEvent(
            tenant_id=conversation.tenant_id,
            appointment_id=appointment.id,
            event_type="rescheduled",
            from_status=previous_status,
            to_status=appointment.status,
            metadata_json={
                "origin": "ai_autoresponder",
                "channel": conversation.channel,
                "conversation_id": str(conversation.id),
                "previous_starts_at": previous_starts_at.isoformat() if previous_starts_at else None,
                "new_starts_at": appointment.starts_at.isoformat(),
            },
            created_by_user_id=None,
        )
    )
    tags = set(conversation.tags or [])
    tags.add("agendamento_remarcado_ia")
    conversation.tags = sorted(tags)
    db.add(conversation)
    db.add(
        MessageEvent(
            tenant_id=conversation.tenant_id,
            event_type="ai_appointment_rescheduled",
            payload={
                "conversation_id": str(conversation.id),
                "appointment_id": str(appointment.id),
                "previous_starts_at": previous_starts_at.isoformat() if previous_starts_at else None,
                "new_starts_at": appointment.starts_at.isoformat(),
            },
        )
    )
    try:
        emit_event(
            db,
            tenant_id=conversation.tenant_id,
            event_key="consulta_atualizada",
            payload={
                "appointment_id": str(appointment.id),
                "patient_id": str(appointment.patient_id),
                "status": appointment.status,
                "previous_status": previous_status,
                "confirmation_status": appointment.confirmation_status,
            },
        )
    except Exception as exc:
        logger.warning(
            "ai_autoresponder.reschedule_event_emit_failed",
            tenant_id=str(conversation.tenant_id),
            conversation_id=str(conversation.id),
            appointment_id=str(appointment.id),
            error=str(exc),
        )
    return {
        "mode": "booking_rescheduled",
        "response_text": (
            "Pronto, sua consulta foi remarcada com sucesso.\n"
            f"• Novo horário: {selected_slot['label']}\n"
            "Se precisar de mais alguma coisa, estou por aqui."
        ),
        "metadata": {
            "reason": "appointment_rescheduled",
            "appointment_id": str(appointment.id),
            "previous_status": previous_status,
            "starts_at_utc": appointment.starts_at.isoformat(),
        },
    }


def _normalize_for_match(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    stripped = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    collapsed = re.sub(r"\s+", " ", stripped.lower())
    return collapsed.strip()


def _detect_period_preference(text: str) -> str | None:
    lowered = _normalize_for_match(text)
    # Não interpreta saudações ("boa noite", "bom dia") como pedido de período.
    cleaned = re.sub(r"[^a-z0-9\s]", " ", lowered)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    greeting_bases = ("bom dia", "boa tarde", "boa noite")
    if any(cleaned.startswith(base) for base in greeting_bases):
        has_scheduling_signal = any(
            keyword in cleaned
            for keyword in (*SCHEDULING_INTENT_KEYWORDS, *AVAILABILITY_REQUEST_KEYWORDS)
        )
        if not has_scheduling_signal and len(cleaned.split()) <= 5:
            return None

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

    if "depois de amanha" in normalized or "depois de amanhã" in normalized:
        return now_local + timedelta(days=2)
    if re.search(r"\bamanha\b", normalized) or re.search(r"\bamanhã\b", normalized):
        return now_local + timedelta(days=1)
    if re.search(r"\bhoje\b", normalized):
        return now_local

    weekday_aliases = (
        ("segunda", 0),
        ("terca", 1),
        ("terça", 1),
        ("quarta", 2),
        ("quinta", 3),
        ("sexta", 4),
        ("sabado", 5),
        ("sábado", 5),
        ("domingo", 6),
    )
    for label, weekday in weekday_aliases:
        if re.search(rf"\b{label}(?:\s+feira)?\b", normalized):
            delta_days = (weekday - now_local.weekday()) % 7
            return now_local + timedelta(days=delta_days)

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


def _is_day_availability_request(text: str) -> bool:
    normalized = _normalize_for_match(text)
    if any(keyword in normalized for keyword in DAY_AVAILABILITY_KEYWORDS):
        return True

    # Ex.: "quero saber os dias disponiveis", "tem dias para lentes?"
    if "dia" in normalized or "dias" in normalized:
        if any(keyword in normalized for keyword in AVAILABILITY_REQUEST_KEYWORDS):
            return True
    if "data" in normalized or "datas" in normalized:
        if any(keyword in normalized for keyword in AVAILABILITY_REQUEST_KEYWORDS):
            return True
    return False


def _is_service_catalog_request(text: str) -> bool:
    normalized = _normalize_for_match(text)
    has_service_term = any(
        term in normalized
        for term in ("servic", "procediment", "tratamento")
    )
    if not has_service_term:
        return False

    has_catalog_intent = any(
        term in normalized
        for term in ("quais", "qual", "oferec", "tem", "mostrar", "saber")
    )
    return has_catalog_intent


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


def _is_conversation_start_for_welcome(db: Session, *, conversation: Conversation) -> bool:
    inbound_count = db.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.tenant_id == conversation.tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == MessageDirection.INBOUND.value,
        )
    ) or 0
    outbound_count = db.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.tenant_id == conversation.tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == MessageDirection.OUTBOUND.value,
        )
    ) or 0
    return inbound_count == 1 and outbound_count == 0


def _conversation_idle_minutes_before_inbound(
    db: Session,
    *,
    conversation: Conversation,
    inbound_message: Message,
) -> float | None:
    previous_message = db.scalar(
        select(Message)
        .where(
            Message.tenant_id == conversation.tenant_id,
            Message.conversation_id == conversation.id,
            Message.id != inbound_message.id,
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )
    if not previous_message or not previous_message.created_at:
        return None

    previous_at = previous_message.created_at
    current_at = inbound_message.created_at or datetime.now(UTC)

    if previous_at.tzinfo is None:
        previous_at = previous_at.replace(tzinfo=UTC)
    if current_at.tzinfo is None:
        current_at = current_at.replace(tzinfo=UTC)

    delta = current_at - previous_at
    seconds = delta.total_seconds()
    if seconds < 0:
        return None
    return seconds / 60.0


def _should_ignore_superseded_burst_message(
    db: Session,
    *,
    conversation: Conversation,
    inbound_message: Message,
    burst_window_seconds: int = 20,
) -> bool:
    payload = inbound_message.payload if isinstance(inbound_message.payload, dict) else {}
    if isinstance(payload.get("interactive_reply"), dict):
        return False
    if not inbound_message.created_at:
        return False

    current_at = inbound_message.created_at
    if current_at.tzinfo is None:
        current_at = current_at.replace(tzinfo=UTC)

    newer_message = db.scalar(
        select(Message)
        .where(
            Message.tenant_id == conversation.tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == MessageDirection.INBOUND.value,
            Message.id != inbound_message.id,
            Message.created_at > inbound_message.created_at,
        )
        .order_by(Message.created_at.asc(), Message.id.asc())
        .limit(1)
    )
    if not newer_message or not newer_message.created_at:
        return False

    newer_at = newer_message.created_at
    if newer_at.tzinfo is None:
        newer_at = newer_at.replace(tzinfo=UTC)
    delta = (newer_at - current_at).total_seconds()
    return 0 <= delta <= burst_window_seconds


def _is_greeting_only_message(text: str) -> bool:
    normalized = _normalize_for_match(text or "")
    cleaned = re.sub(r"[^a-z0-9\s]", " ", normalized)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return False

    greeting_detected = any(
        cleaned == greeting or cleaned.startswith(f"{greeting} ")
        for greeting in GREETING_ONLY_PATTERNS
    )
    if not greeting_detected:
        return False

    non_greeting_intent_terms = (
        *SCHEDULING_INTENT_KEYWORDS,
        *AVAILABILITY_REQUEST_KEYWORDS,
        "servico",
        "servicos",
        "procedimento",
        "procedimentos",
        "valor",
        "valores",
        "preco",
        "precos",
        "preço",
        "preços",
        "duvida",
        "dúvida",
        "atendente",
        "humano",
    )
    if any(term in cleaned for term in non_greeting_intent_terms):
        return False
    if any(term in cleaned for term in URGENCY_PATTERNS):
        return False
    if any(term in cleaned for term in CLINICAL_PATTERNS):
        return False
    return len(cleaned.split()) <= 6


def _should_send_conversation_start_menu(text: str) -> bool:
    # O menu inicial deve aparecer só em saudações curtas (ex.: "oi", "bom dia").
    # Mensagens com intenção clara devem seguir para a IA decidir o próximo passo.
    return _is_greeting_only_message(text)


def _resolve_welcome_greeting_from_knowledge(knowledge_base: dict[str, Any] | None) -> str | None:
    if not isinstance(knowledge_base, dict):
        return None
    profile = (
        knowledge_base.get("clinic_profile")
        if isinstance(knowledge_base.get("clinic_profile"), dict)
        else {}
    )

    custom_greeting = _dedupe_repeated_leading_text_block(
        _compact_text(profile.get("welcome_greeting_example"), max_length=700)
    )
    if custom_greeting:
        return custom_greeting

    clinic_name = _compact_text(profile.get("clinic_name"), max_length=120)
    return _build_default_first_reply_greeting(clinic_name=clinic_name, include_question=True)


def _build_default_first_reply_greeting(*, clinic_name: str | None, include_question: bool = False) -> str:
    clinic_label = clinic_name or "sua clínica"
    message = (
        f"Olá! 😊\n"
        f"Bem-vindo à Clínica {clinic_label}.\n\n"
        "Sou Luiza, assistente virtual da clínica. Posso te ajudar a encontrar horários disponíveis, "
        "agendar consultas e tirar dúvidas rapidamente."
    )
    if include_question:
        return f"{message}\n\nComo posso te ajudar?"
    return message


def _dedupe_repeated_leading_units(units: list[str]) -> list[str] | None:
    if len(units) < 2:
        return None

    normalized_units = [_normalize_for_match(unit) for unit in units]
    max_block_size = len(normalized_units) // 2
    for block_size in range(max_block_size, 0, -1):
        first_block = normalized_units[:block_size]
        second_block = normalized_units[block_size : block_size * 2]
        if first_block and first_block == second_block:
            return units[:block_size] + units[block_size * 2 :]
    return None


def _dedupe_repeated_leading_text_block(text: str) -> str:
    output = str(text or "").strip()
    if not output:
        return ""

    line_units = [chunk.strip() for chunk in output.splitlines() if chunk.strip()]
    deduped_lines = _dedupe_repeated_leading_units(line_units)
    if deduped_lines is not None:
        return "\n".join(deduped_lines).strip()

    paragraph_units = [chunk.strip() for chunk in re.split(r"\n\s*\n", output) if chunk.strip()]
    deduped_paragraphs = _dedupe_repeated_leading_units(paragraph_units)
    if deduped_paragraphs is not None:
        return "\n\n".join(deduped_paragraphs).strip()

    sentence_units = [chunk.strip() for chunk in re.split(r"(?<=[.!?])\s*", output) if chunk.strip()]
    deduped_sentences = _dedupe_repeated_leading_units(sentence_units)
    if deduped_sentences is not None:
        return " ".join(deduped_sentences).strip()

    return output


def _strip_leading_generic_greeting(text: str) -> str:
    output = str(text or "").strip()
    if not output:
        return ""
    return re.sub(
        r"^\s*(?:ol[aá]|oi|bom dia|boa tarde|boa noite)[^.!?\n]{0,120}[.!?]?\s*",
        "",
        output,
        count=1,
        flags=re.IGNORECASE,
    ).strip()


def _prepend_first_reply_greeting_if_needed(
    db: Session,
    *,
    conversation: Conversation,
    knowledge_base: dict[str, Any] | None,
    text: str,
) -> str:
    if not _is_conversation_start_for_welcome(db, conversation=conversation):
        return text
    clinic_name = None
    if isinstance(knowledge_base, dict):
        profile = knowledge_base.get("clinic_profile") if isinstance(knowledge_base.get("clinic_profile"), dict) else {}
        clinic_name = _compact_text(profile.get("clinic_name"), max_length=120)
    greeting = _build_default_first_reply_greeting(clinic_name=clinic_name)
    raw_text = str(text or "").strip()
    normalized_greeting = _normalize_for_match(greeting)
    if _normalize_for_match(raw_text).startswith(normalized_greeting):
        return _dedupe_repeated_leading_text_block(raw_text)
    body = _strip_leading_generic_greeting(raw_text)
    if not body:
        return greeting
    greeting_tail = _normalize_for_match(_strip_leading_generic_greeting(greeting))
    if greeting_tail and _normalize_for_match(body).startswith(greeting_tail):
        salutation = greeting.splitlines()[0].strip()
        return _dedupe_repeated_leading_text_block(f"{salutation}\n{body}")
    if _normalize_for_match(body).startswith(_normalize_for_match(greeting)):
        return body
    return f"{greeting}\n\n{body}"


def _build_conversation_start_welcome_response(
    *,
    intro_text: str | None = None,
    session_token: str | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    for option in WELCOME_MENU_OPTIONS:
        row = {
            "id": option["id"],
            "title": str(option["title"])[:24],
        }
        description = str(option.get("description") or "").strip()
        if description:
            row["description"] = description[:72]
        rows.append(row)

    resolved_intro_text = _dedupe_repeated_leading_text_block(
        intro_text or _build_default_first_reply_greeting(clinic_name=None, include_question=True)
    )

    metadata = _wizard_metadata_with_session(
        metadata={
            "reason": "welcome_message_start",
            "rows": rows,
            "button_title": "Opções",
            "section_title": "Menu inicial",
            "header_text": "Atendimento",
            "body_text": resolved_intro_text,
            "footer_text": "Toque em uma opção para continuar.",
        },
        session_token=session_token,
        step="start_menu",
    )

    return {
        "mode": "welcome_message_start",
        "response_text": resolved_intro_text,
        "metadata": metadata,
    }


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

    compact_match = re.search(r"^\s*([01]?\d|2[0-3])([0-5]\d)\s*$", text or "")
    if not compact_match:
        compact_match = re.search(r"\b(?:as|às)\s*([01]?\d|2[0-3])\s*([0-5]\d)\b", _normalize_for_match(text or ""))
    if compact_match:
        hour = int(compact_match.group(1))
        minute = int(compact_match.group(2))
        return f"{hour:02d}:{minute:02d}"

    hour_minute_match = re.search(r"\b(?:as|às)\s*([01]?\d|2[0-3])\s*h\s*([0-5]\d)\b", _normalize_for_match(text or ""))
    if hour_minute_match:
        hour = int(hour_minute_match.group(1))
        minute = int(hour_minute_match.group(2))
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

    if mode.startswith("booking_") or mode in {
        "welcome_message_start",
        "no_slots_general",
        "no_slots_for_period",
        "no_slots_for_period_with_alternatives",
    }:
        buttons_raw = metadata.get("buttons")
        if isinstance(buttons_raw, list):
            buttons: list[dict[str, str]] = []
            for button in buttons_raw[:3]:
                if not isinstance(button, dict):
                    continue
                button_id = str(button.get("id") or "").strip()[:200]
                button_title = str(button.get("title") or "").strip()[:20]
                if not button_id or not button_title:
                    continue
                buttons.append({"id": button_id, "title": button_title})
            if buttons:
                return {
                    "interactive_type": "buttons",
                    "header_text": str(metadata.get("header_text") or "Agendamento"),
                    "body_text": str(
                        metadata.get("body_text")
                        or scheduling_response.get("response_text")
                        or "Confirme para continuar."
                    ),
                    "footer_text": str(metadata.get("footer_text") or "Use as opções abaixo para confirmar."),
                    "buttons": buttons,
                }

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
            "interactive_type": "list",
            "button_title": str(metadata.get("button_title") or "Opções"),
            "section_title": str(metadata.get("section_title") or "Escolha uma opção"),
            "header_text": str(metadata.get("header_text") or "Agendamento"),
            "body_text": str(
                metadata.get("body_text")
                or scheduling_response.get("response_text")
                or "Selecione uma opção para continuar."
            ),
            "footer_text": str(metadata.get("footer_text") or "Use as opções abaixo para continuar."),
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
    for index, slot_label in enumerate(slots[:7], start=1):
        rows.append(
            {
                "id": f"slot_{index}",
                "title": f"Opção {index}",
                "description": slot_label[:72],
            }
        )
    rows.append({"id": "slot_change_day", "title": "Trocar dia", "description": "Ver outros dias"})
    rows.append({"id": "slot_change_service", "title": "Trocar serviço", "description": "Escolher outro serviço"})
    rows.append({"id": "slot_handoff", "title": "Falar com atendente", "description": "Encaminhar para humano"})

    if not rows:
        return None

    return {
        "interactive_type": "list",
        "button_title": "Opções",
        "section_title": "Horários disponíveis",
        "header_text": "Escolha um horário",
        "body_text": f"Selecione uma opção para confirmar seu agendamento de {procedure}.",
        "footer_text": "Você também pode digitar o número da opção.",
        "rows": rows,
    }


def _normalize_interactive_rows(rows_raw: Any, *, max_rows: int = 10) -> list[dict[str, str]]:
    if not isinstance(rows_raw, list):
        return []

    rows: list[dict[str, str]] = []
    for index, row in enumerate(rows_raw, start=1):
        if not isinstance(row, dict):
            continue
        row_id = str(row.get("id") or f"option_{index}").strip()[:200]
        row_title = str(row.get("title") or f"Opção {index}").strip()[:24]
        row_description = str(row.get("description") or "").strip()[:72]
        if not row_id or not row_title:
            continue
        item = {"id": row_id, "title": row_title}
        if row_description:
            item["description"] = row_description
        rows.append(item)
        if len(rows) >= max_rows:
            break
    return rows


def _normalize_interactive_buttons(buttons_raw: Any, *, max_buttons: int = 3) -> list[dict[str, str]]:
    if not isinstance(buttons_raw, list):
        return []

    buttons: list[dict[str, str]] = []
    for index, button in enumerate(buttons_raw, start=1):
        if not isinstance(button, dict):
            continue
        button_id = str(button.get("id") or f"button_{index}").strip()[:200]
        button_title = str(button.get("title") or f"Opção {index}").strip()[:20]
        if not button_id or not button_title:
            continue
        buttons.append({"id": button_id, "title": button_title})
        if len(buttons) >= max_buttons:
            break
    return buttons


def _interactive_from_action_payload(action_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(action_payload, dict):
        return None

    raw = action_payload.get("interactive")
    source = raw if isinstance(raw, dict) else action_payload

    buttons = _normalize_interactive_buttons(source.get("buttons"))
    if buttons:
        return {
            "interactive_type": "buttons",
            "header_text": str(source.get("header_text") or "Atendimento"),
            "body_text": str(source.get("body_text") or "Escolha uma opção para continuar."),
            "footer_text": str(source.get("footer_text") or "Você também pode responder com suas palavras."),
            "buttons": buttons,
        }

    rows = _normalize_interactive_rows(source.get("rows"))
    if rows:
        return {
            "interactive_type": "list",
            "button_title": str(source.get("button_title") or "Opções"),
            "section_title": str(source.get("section_title") or "Escolha uma opção"),
            "header_text": str(source.get("header_text") or "Atendimento"),
            "body_text": str(source.get("body_text") or "Selecione uma opção para continuar."),
            "footer_text": str(source.get("footer_text") or "Você também pode responder com suas palavras."),
            "rows": rows,
        }

    return None


def _build_units_action_interactive_preview(db: Session, *, tenant_id: UUID) -> dict[str, Any] | None:
    units = db.execute(
        select(Unit)
        .where(
            Unit.tenant_id == tenant_id,
            Unit.is_active.is_(True),
        )
        .order_by(Unit.name.asc())
        .limit(10)
    ).scalars().all()
    rows: list[dict[str, str]] = []
    for index, unit in enumerate(units, start=1):
        description = _format_unit_address(unit.address)
        if not description and unit.phone:
            description = f"Telefone: {unit.phone}"
        rows.append(
            {
                "id": f"unit_{index}",
                "title": _compact_text(unit.name, max_length=24) or f"Unidade {index}",
                "description": _compact_text(description or "Unidade disponível", max_length=72),
            }
        )

    if not rows:
        return None

    return {
        "interactive_type": "list",
        "button_title": "Clínicas",
        "section_title": "Escolha a clínica",
        "header_text": "Nossas unidades",
        "body_text": "Selecione uma clínica para continuar o atendimento.",
        "footer_text": "Simulação segura: nenhum WhatsApp é enviado no IA Lab.",
        "rows": rows,
    }


def _build_services_action_interactive_preview(
    db: Session,
    *,
    tenant_id: UUID,
    knowledge_base: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    services = _normalize_services((knowledge_base or {}).get("services"))
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    for service in services:
        name = _compact_text(service.get("name"), max_length=120)
        if not name:
            continue
        normalized = _normalize_for_match(name)
        if normalized in seen:
            continue
        seen.add(normalized)
        description_parts = [
            service.get("price_note"),
            service.get("duration_note"),
            service.get("description"),
        ]
        description = " | ".join(
            _compact_text(part, max_length=72)
            for part in description_parts
            if _compact_text(part, max_length=72)
        )
        rows.append(
            {
                "id": f"svc_{len(rows) + 1}",
                "title": _compact_text(name, max_length=24),
                "description": _compact_text(description or "Ver detalhes", max_length=72),
            }
        )
        if len(rows) >= 10:
            break

    if len(rows) < 10:
        for option in _wizard_service_options(db, tenant_id=tenant_id):
            normalized = _normalize_for_match(option)
            if normalized in seen:
                continue
            seen.add(normalized)
            rows.append(
                {
                    "id": f"svc_{len(rows) + 1}",
                    "title": _compact_text(option, max_length=24),
                    "description": "Toque para escolher",
                }
            )
            if len(rows) >= 10:
                break

    if not rows:
        return None

    return {
        "interactive_type": "list",
        "button_title": "Serviços",
        "section_title": "Atendimentos",
        "header_text": "Procedimentos",
        "body_text": "Selecione um serviço/procedimento para continuar.",
        "footer_text": "Se preferir, também pode escrever sua dúvida.",
        "rows": rows,
    }


def _build_plans_action_interactive_preview(
    *,
    knowledge_base: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    insurance = (
        (knowledge_base or {}).get("insurance")
        if isinstance((knowledge_base or {}).get("insurance"), dict)
        else {}
    )
    plans = _normalize_string_list(insurance.get("accepted_plans"), max_items=10, item_max_length=120)
    rows = [
        {
            "id": f"plan_{index}",
            "title": _compact_text(plan, max_length=24),
            "description": "Convênio/plano aceito",
        }
        for index, plan in enumerate(plans, start=1)
    ]
    if not rows:
        return {
            "interactive_type": "buttons",
            "header_text": "Condições",
            "body_text": (
                "Ainda não tenho uma lista de convênios ou condições cadastrada aqui. "
                "Posso te ajudar pelos próximos caminhos abaixo."
            ),
            "footer_text": "Se preferir, escreva sua dúvida sobre valores ou formas de pagamento.",
            "buttons": [
                {"id": "menu_services", "title": "Ver serviços"},
                {"id": "menu_schedule", "title": "Agendar"},
                {"id": "menu_human", "title": "Atendente"},
            ],
        }

    return {
        "interactive_type": "list",
        "button_title": "Convênios",
        "section_title": "Planos aceitos",
        "header_text": "Convênios",
        "body_text": "Veja os convênios cadastrados para atendimento.",
        "footer_text": "Confirme cobertura e regras com a recepção.",
        "rows": rows,
    }


def _action_payload_text(action_payload: dict[str, Any] | None) -> str:
    if not isinstance(action_payload, dict):
        return ""
    parts: list[str] = []
    for key, value in action_payload.items():
        if isinstance(value, (str, int, float)):
            parts.append(f"{key}: {value}")
        elif isinstance(value, dict):
            for nested_key, nested_value in value.items():
                if isinstance(nested_value, (str, int, float)):
                    parts.append(f"{nested_key}: {nested_value}")
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, (str, int, float)):
                    parts.append(str(item))
                elif isinstance(item, dict):
                    for nested_value in item.values():
                        if isinstance(nested_value, (str, int, float)):
                            parts.append(str(nested_value))
    return "\n".join(parts)


def _action_payload_string_value(action_payload: dict[str, Any] | None, keys: tuple[str, ...]) -> str:
    if not isinstance(action_payload, dict):
        return ""
    for key in keys:
        value = action_payload.get(key)
        if isinstance(value, (str, int, float)):
            text = str(value).strip()
            if text:
                return text
    for value in action_payload.values():
        if not isinstance(value, dict):
            continue
        for key in keys:
            nested_value = value.get(key)
            if isinstance(nested_value, (str, int, float)):
                text = str(nested_value).strip()
                if text:
                    return text
    return ""


def _resolve_unit_for_action_preview(
    db: Session,
    *,
    tenant_id: UUID,
    action_payload: dict[str, Any] | None,
) -> tuple[Unit | None, bool]:
    units = db.execute(
        select(Unit)
        .where(
            Unit.tenant_id == tenant_id,
            Unit.is_active.is_(True),
        )
        .order_by(Unit.name.asc())
    ).scalars().all()
    if not units:
        return None, False

    unit_id_candidate = _action_payload_string_value(
        action_payload,
        ("unit_id", "clinic_id", "selected_unit_id", "selected_clinic_id"),
    )
    if unit_id_candidate:
        try:
            unit_uuid = UUID(unit_id_candidate)
        except (TypeError, ValueError):
            unit_uuid = None
        if unit_uuid:
            for unit in units:
                if unit.id == unit_uuid:
                    return unit, False

    blob = _action_payload_text(action_payload)
    blob_norm = _normalize_for_match(blob)
    option_match = re.search(r"\bunit[_-]?(\d{1,2})\b", blob_norm)
    if option_match:
        option_index = int(option_match.group(1))
        if 1 <= option_index <= len(units):
            return units[option_index - 1], False

    explicit_unit_name = _action_payload_string_value(
        action_payload,
        ("unit_name", "clinic_name", "selected_unit", "selected_clinic", "clinica", "clínica"),
    )
    candidates = [explicit_unit_name, blob]
    for candidate in candidates:
        candidate_norm = _normalize_for_match(candidate)
        if not candidate_norm:
            continue
        for unit in units:
            unit_name_norm = _normalize_for_match(unit.name)
            unit_code_norm = _normalize_for_match(unit.code or "")
            if unit_name_norm and (unit_name_norm in candidate_norm or candidate_norm in unit_name_norm):
                return unit, False
            if unit_code_norm and unit_code_norm in candidate_norm:
                return unit, False

    if len(units) == 1:
        return units[0], False
    return None, False


def _resolve_procedure_for_action_preview(action_payload: dict[str, Any] | None) -> str:
    explicit = _action_payload_string_value(
        action_payload,
        (
            "procedure_type",
            "service",
            "service_selected",
            "selected_service",
            "procedimento",
            "tratamento",
        ),
    )
    if explicit:
        return _compact_text(explicit, max_length=120)

    blob = _action_payload_text(action_payload)
    inferred = _infer_procedure_type(inbound_text=blob, context=blob)
    return inferred or "Avaliação inicial"


def _resolve_slot_duration_minutes(
    db: Session,
    *,
    tenant_id: UUID,
    procedure_type: str,
    service_catalog: list[dict[str, Any]] | None = None,
) -> int:
    effective_service_catalog = service_catalog or get_service_duration_catalog(db, tenant_id=tenant_id)
    return resolve_service_duration_minutes(
        procedure_type=procedure_type,
        service_catalog=effective_service_catalog,
    )


def _resolve_requested_date_for_action_preview(
    action_payload: dict[str, Any] | None,
    *,
    timezone: ZoneInfo,
) -> date | None:
    explicit = _action_payload_string_value(
        action_payload,
        ("requested_date", "date", "selected_date", "date_selected", "dia", "data"),
    )
    parsed = _parse_iso_date(explicit)
    if parsed:
        return parsed

    blob = _action_payload_text(action_payload)
    iso_match = re.search(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)", blob)
    if iso_match:
        parsed = _parse_iso_date(iso_match.group(1))
        if parsed:
            return parsed

    return _extract_requested_date_from_text(text=blob, timezone=timezone)


def _build_available_dates_action_interactive_preview(
    db: Session,
    *,
    tenant_id: UUID,
    action_payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    config = get_global_config(db, tenant_id=tenant_id)
    unit, _ = _resolve_unit_for_action_preview(db, tenant_id=tenant_id, action_payload=action_payload)
    if not unit:
        clinics_preview = _build_units_action_interactive_preview(db, tenant_id=tenant_id)
        if clinics_preview:
            clinics_preview["body_text"] = "Escolha a clínica para eu mostrar os dias disponíveis."
        return clinics_preview

    procedure_type = _resolve_procedure_for_action_preview(action_payload)
    service_catalog = get_service_duration_catalog(db, tenant_id=tenant_id)
    slot_duration_minutes = _resolve_slot_duration_minutes(
        db,
        tenant_id=tenant_id,
        procedure_type=procedure_type,
        service_catalog=service_catalog,
    )
    operation_timezone = _resolve_operation_timezone(config)
    requested_date = _resolve_requested_date_for_action_preview(action_payload, timezone=operation_timezone)
    period = _detect_period_preference(_action_payload_text(action_payload))

    now_local_date = datetime.now(UTC).astimezone(operation_timezone).date()
    candidates: list[date] = []
    if requested_date and requested_date >= now_local_date:
        candidates.append(requested_date)
    for offset in range(0, 14):
        candidate = now_local_date + timedelta(days=offset)
        if candidate not in candidates:
            candidates.append(candidate)

    rows: list[dict[str, str]] = []
    for candidate in candidates:
        slots = _list_available_slots(
            db,
            tenant_id=tenant_id,
            unit_id=unit.id,
            config=config,
            procedure_type=procedure_type,
            period=period,
            requested_date=candidate,
            max_slots=1,
            slot_duration_minutes=slot_duration_minutes,
            service_catalog=service_catalog,
        )
        if not slots:
            continue
        first_slot = slots[0]
        weekday = _weekday_label_pt(candidate.weekday())
        rows.append(
            {
                "id": f"day_{candidate.isoformat()}",
                "title": f"{candidate.strftime('%d/%m')} {weekday[:3]}",
                "description": f"{weekday}, {candidate.strftime('%d/%m')} a partir de {first_slot['starts_at_local'].strftime('%H:%M')}",
            }
        )
        if len(rows) >= 7:
            break

    if not rows:
        return {
            "interactive_type": "buttons",
            "header_text": "Agenda",
            "body_text": f"No momento não encontrei dias livres na {unit.name} para {procedure_type}.",
            "footer_text": "Você pode tentar outro serviço ou falar com a recepção.",
            "buttons": [
                {"id": "day_change_service", "title": "Trocar serviço"},
                {"id": "menu_human", "title": "Atendente"},
            ],
            "unit_id": str(unit.id),
            "unit_name": unit.name,
            "procedure_type": procedure_type,
        }

    return {
        "interactive_type": "list",
        "button_title": "Dias",
        "section_title": "Dias disponíveis",
        "header_text": "Agenda",
        "body_text": f"Escolha um dia disponível na {unit.name} para {procedure_type}.",
        "footer_text": "Depois de escolher o dia, eu mostro os horários.",
        "rows": rows,
        "unit_id": str(unit.id),
        "unit_name": unit.name,
        "procedure_type": procedure_type,
    }


def _build_available_times_action_interactive_preview(
    db: Session,
    *,
    tenant_id: UUID,
    action_payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    config = get_global_config(db, tenant_id=tenant_id)
    operation_timezone = _resolve_operation_timezone(config)
    selected_date = _resolve_requested_date_for_action_preview(action_payload, timezone=operation_timezone)
    if not selected_date:
        return _build_available_dates_action_interactive_preview(
            db,
            tenant_id=tenant_id,
            action_payload=action_payload,
        )

    unit, _ = _resolve_unit_for_action_preview(db, tenant_id=tenant_id, action_payload=action_payload)
    if not unit:
        clinics_preview = _build_units_action_interactive_preview(db, tenant_id=tenant_id)
        if clinics_preview:
            clinics_preview["body_text"] = "Escolha a clínica para eu mostrar os horários disponíveis."
        return clinics_preview

    procedure_type = _resolve_procedure_for_action_preview(action_payload)
    service_catalog = get_service_duration_catalog(db, tenant_id=tenant_id)
    slot_duration_minutes = _resolve_slot_duration_minutes(
        db,
        tenant_id=tenant_id,
        procedure_type=procedure_type,
        service_catalog=service_catalog,
    )
    period = _detect_period_preference(_action_payload_text(action_payload))
    slots = _list_available_slots(
        db,
        tenant_id=tenant_id,
        unit_id=unit.id,
        config=config,
        procedure_type=procedure_type,
        period=period,
        requested_date=selected_date,
        max_slots=7,
        slot_duration_minutes=slot_duration_minutes,
        service_catalog=service_catalog,
    )
    if not slots:
        return {
            "interactive_type": "buttons",
            "header_text": "Agenda",
            "body_text": f"Não encontrei horários livres para {selected_date.strftime('%d/%m')} na {unit.name}.",
            "footer_text": "Você pode ver outros dias ou falar com a recepção.",
            "buttons": [
                {"id": "time_change_day", "title": "Trocar dia"},
                {"id": "menu_human", "title": "Atendente"},
            ],
            "unit_id": str(unit.id),
            "unit_name": unit.name,
            "procedure_type": procedure_type,
            "requested_date": selected_date.isoformat(),
        }

    rows: list[dict[str, str]] = []
    for index, slot in enumerate(slots, start=1):
        starts_at_local = slot["starts_at_local"]
        rows.append(
            {
                "id": f"time_{index}",
                "title": starts_at_local.strftime("%H:%M"),
                "description": _compact_text(str(slot.get("label") or ""), max_length=72),
            }
        )
    rows.append({"id": "time_change_day", "title": "Trocar dia", "description": "Ver outros dias"})
    rows.append({"id": "menu_human", "title": "Falar atendente", "description": "Encaminhar para humano"})

    return {
        "interactive_type": "list",
        "button_title": "Horários",
        "section_title": "Horários disponíveis",
        "header_text": "Agenda",
        "body_text": f"Escolha um horário para {selected_date.strftime('%d/%m')} na {unit.name}.",
        "footer_text": "Toque no horário ou responda com a hora desejada.",
        "rows": rows[:10],
        "unit_id": str(unit.id),
        "unit_name": unit.name,
        "procedure_type": procedure_type,
        "requested_date": selected_date.isoformat(),
    }


def build_ai_action_interactive_preview(
    db: Session,
    *,
    tenant_id: UUID,
    next_action: str,
    action_payload: dict[str, Any] | None = None,
    knowledge_base: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    payload_preview = _interactive_from_action_payload(action_payload)
    if payload_preview:
        payload_preview["source"] = "action_payload"
        payload_preview["action"] = next_action
        return payload_preview

    if next_action == "show_clinics":
        preview = _build_units_action_interactive_preview(db, tenant_id=tenant_id)
    elif next_action in {"show_services", "open_booking"}:
        preview = _build_services_action_interactive_preview(
            db,
            tenant_id=tenant_id,
            knowledge_base=knowledge_base,
        )
    elif next_action == "show_plans":
        preview = _build_plans_action_interactive_preview(knowledge_base=knowledge_base)
    elif next_action == "show_available_dates":
        preview = _build_available_dates_action_interactive_preview(
            db,
            tenant_id=tenant_id,
            action_payload=action_payload,
        )
    elif next_action in {"show_available_times", "verify_date_availability"}:
        preview = _build_available_times_action_interactive_preview(
            db,
            tenant_id=tenant_id,
            action_payload=action_payload,
        )
    elif next_action == "show_resume_or_restart_options":
        preview = {
            "interactive_type": "buttons",
            "header_text": "Atendimento",
            "body_text": "Você prefere continuar de onde parou ou começar de novo?",
            "footer_text": "Simulação segura: nenhum WhatsApp é enviado no IA Lab.",
            "buttons": [
                {"id": "resume_saved_step", "title": "Continuar"},
                {"id": "restart_from_beginning", "title": "Reiniciar"},
            ],
        }
    elif next_action == "show_booking_confirmation_options":
        preview = {
            "interactive_type": "buttons",
            "header_text": "Confirmação",
            "body_text": "Confirme ou ajuste o agendamento.",
            "footer_text": "Você também pode responder por mensagem.",
            "buttons": [
                {"id": "confirm_yes", "title": "Sim"},
                {"id": "confirm_no", "title": "Não"},
                {"id": "confirm_change_time", "title": "Trocar horário"},
            ],
        }
    else:
        preview = None

    if not preview:
        return None

    preview["source"] = "next_action"
    preview["action"] = next_action
    return preview


AI_IMMEDIATE_INTERACTIVE_ACTIONS = {
    "show_clinics",
    "show_services",
    "show_plans",
    "show_available_dates",
    "show_available_times",
    "verify_date_availability",
    "open_booking",
    "show_resume_or_restart_options",
    "show_booking_confirmation_options",
    "finalize_booking_auto",
    "request_cpf_after_booking",
}


AI_OPTION_PROMPT_ACTIONS = {
    "show_clinics",
    "show_services",
    "show_plans",
    "show_available_dates",
    "show_available_times",
    "verify_date_availability",
    "open_booking",
    "show_resume_or_restart_options",
    "show_booking_confirmation_options",
}


def _reply_text_already_has_numbered_options(text: str) -> bool:
    candidate = str(text or "").strip()
    if not candidate:
        return False
    return bool(re.search(r"(^|\n)\s*1\)", candidate))


def _interactive_payload_option_lines(interactive_payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(interactive_payload, dict):
        return []

    options_raw = interactive_payload.get("buttons")
    if not isinstance(options_raw, list):
        options_raw = interactive_payload.get("rows")
    if not isinstance(options_raw, list):
        return []

    lines: list[str] = []
    section_title = _compact_text(
        interactive_payload.get("section_title") or interactive_payload.get("header_text"),
        max_length=80,
    )
    if section_title:
        lines.append(f"{section_title}:")

    for index, item in enumerate(options_raw, start=1):
        if not isinstance(item, dict):
            continue
        title = _compact_text(item.get("title") or f"Opção {index}", max_length=120)
        description = _compact_text(item.get("description"), max_length=200)
        if _normalize_for_match(description) in {"toque para escolher", "tap to choose", "touch to choose"}:
            description = ""
        if not title:
            continue
        option_line = f"{index}) {title}"
        if description:
            option_line = f"{option_line} — {description}"
        lines.append(option_line)

    return lines


def _compose_text_reply_with_options_fallback(
    reply_text: str,
    *,
    interactive_payload: dict[str, Any] | None,
) -> str:
    base_text = _dedupe_repeated_leading_text_block(reply_text)
    if not isinstance(interactive_payload, dict):
        return base_text

    lines: list[str] = []
    normalized_base = _normalize_for_match(base_text)
    body_text = _dedupe_repeated_leading_text_block(
        _compact_text(interactive_payload.get("body_text"), max_length=400)
    )
    option_lines = _interactive_payload_option_lines(interactive_payload)
    audio_hint = "Você pode responder com o número da opção, escrever do seu jeito ou mandar áudio que eu entendo."

    if base_text:
        lines.append(base_text)
    if body_text and _normalize_for_match(body_text) not in normalized_base:
        lines.append(body_text)
    if option_lines and not _reply_text_already_has_numbered_options(base_text):
        lines.extend(option_lines)
    if _normalize_for_match(audio_hint) not in normalized_base:
        lines.append(audio_hint)

    return "\n".join(line for line in lines if str(line).strip()).strip()


def normalize_immediate_action_reply_text(text: str, *, next_action: str) -> str:
    output = str(text or "").strip()
    if not output or next_action not in AI_IMMEDIATE_INTERACTIVE_ACTIONS:
        return output

    deferred_patterns = [
        r"\b(?:em breve|em instantes|logo|logo mais|j[aá]\s+j[aá])[^.!?\n]*[.!?]?",
        r"\b(?:vou|irei|vamos)\s+(?:te\s+|lhe\s+|ja\s+|já\s+)?(?:verificar|checar|consultar|buscar|trazer|mostrar|listar|apresentar|finalizar)[^.!?\n]*(?:op[cç][oõ]es|datas?|dias?|hor[aá]rios?|cl[ií]nicas?|unidades?|servi[cç]os?|planos?|condi[cç][oõ]es|valores?|agendamento|consulta|tudo)[.!?]?",
        r"\bposso\s+(?:mostrar|listar|apresentar|trazer)[^.!?\n]*(?:op[cç][oõ]es|datas?|dias?|hor[aá]rios?|cl[ií]nicas?|unidades?|servi[cç]os?)[.!?]?",
        r"\b(?:aguarde|s[oó]\s+um\s+momento)[^.!?\n]*[.!?]?",
    ]
    sentences = re.split(r"(?<=[.!?])\s+", output)
    filtered_sentences: list[str] = []
    removed_deferred_sentence = False
    for sentence in sentences:
        if any(re.search(pattern, sentence, flags=re.IGNORECASE) for pattern in deferred_patterns):
            removed_deferred_sentence = True
            continue
        filtered_sentences.append(sentence)

    if removed_deferred_sentence:
        output = " ".join(sentence.strip() for sentence in filtered_sentences if sentence.strip()).strip()
    else:
        for pattern in deferred_patterns:
            output = re.sub(pattern, "", output, flags=re.IGNORECASE)

    output = re.sub(r"\s{2,}", " ", output).strip()
    if not output:
        output = "Vou te mostrar as opções disponíveis agora." if next_action in AI_OPTION_PROMPT_ACTIONS else "Perfeito, confirmação recebida."
    return output.strip()


def _build_services_overview_menu_response(
    db: Session,
    *,
    conversation: Conversation,
    session_token: str | None = None,
) -> dict[str, Any]:
    knowledge_base = get_knowledge_base_global_config(db, tenant_id=conversation.tenant_id)
    services = _normalize_services((knowledge_base or {}).get("services"))
    if not services:
        return {
            "mode": "services_menu_overview",
            "response_text": (
                "Posso te explicar nossos serviços e valores, mas agora não encontrei o catálogo detalhado. "
                "Se quiser, me diga o nome do tratamento que você quer conhecer ou escreva 'quero agendar'."
            ),
            "metadata": {
                "reason": "services_menu_selected_without_catalog",
                "services_count": 0,
            },
        }

    lines = ["Claro. Estes são alguns serviços que a clínica oferece:"]
    for index, service in enumerate(services[:8], start=1):
        parts = [service["name"]]
        if service.get("description"):
            parts.append(str(service["description"]))
        elif service.get("price_note"):
            parts.append(str(service["price_note"]))
        elif service.get("duration_note"):
            parts.append(str(service["duration_note"]))
        lines.append(f"{index}) {' — '.join(part for part in parts if part)}")
    lines.append("Se quiser mais detalhes de algum serviço, me diga o nome dele.")
    lines.append("Se quiser agendar, escreva por exemplo: quero agendar limpeza odontológica.")

    return {
        "mode": "services_menu_overview",
        "response_text": "\n".join(lines),
        "metadata": {
            "reason": "services_menu_selected",
            "services_count": len(services),
            "session_token": session_token,
        },
    }


def _is_service_price_question(text: str) -> bool:
    normalized = _normalize_for_match(text or "")
    if not normalized:
        return False
    return any(keyword in normalized for keyword in ("preco", "precos", "valor", "valores", "custa", "custam"))


def _build_service_price_detail_response(
    db: Session,
    *,
    conversation: Conversation,
    service_name: str,
    session_token: str | None = None,
) -> dict[str, Any] | None:
    knowledge_base = get_knowledge_base_global_config(db, tenant_id=conversation.tenant_id)
    services = _normalize_services((knowledge_base or {}).get("services"))
    service_name_normalized = _normalize_for_match(service_name)
    selected_service = next(
        (
            service
            for service in services
            if _normalize_for_match(service.get("name")) == service_name_normalized
        ),
        None,
    )
    if not selected_service:
        return None

    details = [f"Sobre {selected_service['name']}:"]
    if selected_service.get("description"):
        details.append(str(selected_service["description"]))
    if selected_service.get("price_note"):
        details.append(f"Valor: {selected_service['price_note']}")
    else:
        details.append("No momento eu nao encontrei um valor cadastrado para esse servico.")
    if selected_service.get("duration_note"):
        details.append(f"Duracao: {selected_service['duration_note']}")
    details.append("Se quiser, eu tambem posso continuar seu agendamento por aqui.")

    return {
        "mode": "services_menu_service_price_detail",
        "response_text": "\n".join(details),
        "metadata": {
            "reason": "service_price_detail_requested",
            "service_selected": selected_service["name"],
            "session_token": session_token,
        },
    }


def _build_post_booking_options_payload() -> tuple[str, dict[str, Any]]:
    text_body = (
        "Seu agendamento já está confirmado. Se quiser, posso te passar mais detalhes "
        "ou encerrar o atendimento por aqui."
    )
    interactive_payload: dict[str, Any] = {
        "interactive_type": "buttons",
        "header_text": "Próximos passos",
        "body_text": "Como você prefere continuar agora?",
        "footer_text": "Você pode tocar em um botão ou responder com suas palavras.",
        "buttons": [
            {"id": "post_info_more", "title": "Mais informações"},
            {"id": "post_info_close", "title": "Encerrar conversa"},
        ],
    }
    return text_body, interactive_payload


def _post_booking_visit_guidance_lines(
    *,
    unit_address: str | None = None,
    professional_name: str | None = None,
    include_documents: bool = True,
) -> list[str]:
    address = _compact_text(unit_address, max_length=260)
    lines: list[str] = []
    professional_label = _guidance_professional_label(professional_name)
    if professional_label:
        lines.append(f"• Profissional: {professional_label}")
    if address:
        lines.append(f"• Endereço: {address}")
    else:
        lines.append(
            "• Endereço: não tenho o endereço desta unidade cadastrado com segurança; "
            "confirme com a equipe antes de se deslocar."
        )
    if include_documents:
        lines.extend(
            [
                "• Para o atendimento: leve documento com foto e CPF.",
                "• Se tiver exames, receitas ou documentos recentes do seu atendimento, leve também.",
                "• Chegue com 10 a 15 minutos de antecedência.",
            ]
        )
    return lines


def _post_booking_guidance_text(
    *,
    procedure_type: str | None,
    unit_name: str | None,
    selected_slot_label: str | None,
    unit_address: str | None = None,
    professional_name: str | None = None,
) -> str:
    procedure_label = str(procedure_type or "atendimento").strip()
    unit_label = str(unit_name or "unidade selecionada").strip()
    slot_label = str(selected_slot_label or "").strip()

    return (
        "Perfeito! Seu agendamento está confirmado e deixei os principais detalhes organizados aqui:\n"
        f"• Serviço: {procedure_label}\n"
        f"• Clínica: {unit_label}\n"
        + (f"• Horário: {slot_label}\n" if slot_label else "")
        + "\n".join(
            _post_booking_visit_guidance_lines(
                unit_address=unit_address,
                professional_name=professional_name,
            )
        )
        + "\nSe precisar alterar ou cancelar, avise por aqui. Aguardamos você!"
    )


def _post_booking_close_summary_text(
    *,
    procedure_type: str | None,
    unit_name: str | None,
    selected_slot_label: str | None,
    unit_address: str | None = None,
    professional_name: str | None = None,
) -> str:
    procedure_label = str(procedure_type or "atendimento").strip()
    unit_label = str(unit_name or "unidade selecionada").strip()
    slot_label = str(selected_slot_label or "").strip()
    detail = f"{procedure_label} em {unit_label}"
    if slot_label:
        detail = f"{detail}, horário {slot_label}"
    return (
        f"Resumo do atendimento: {detail}.\n"
        + "\n".join(
            _post_booking_visit_guidance_lines(
                unit_address=unit_address,
                professional_name=professional_name,
            )
        )
        + "\n"
        "Conversa encerrada com sucesso. Quando quiser, estamos à disposição."
    )


def build_official_visit_guidance_response(
    db: Session,
    *,
    conversation: Conversation,
    inbound_text: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    topics = _visit_guidance_requested_topics(inbound_text)
    if not topics:
        return None

    effective_config = config or get_global_config(db, tenant_id=conversation.tenant_id)
    context = _appointment_visit_guidance_context(
        db,
        conversation=conversation,
        config=effective_config,
        inbound_text=inbound_text,
    )
    if not context:
        return None

    unit_name = str(context.get("unit_name") or "unidade selecionada").strip()
    slot_label = str(context.get("selected_slot_label") or "").strip() or None
    procedure_type = str(context.get("procedure_type") or "").strip() or None
    professional_name = str(context.get("professional_name") or "").strip() or None
    unit_address = str(context.get("unit_address") or "").strip() or None
    has_appointment = bool(context.get("has_appointment"))
    include_documents = has_appointment or "document" in topics

    if has_appointment:
        response_text = (
            "Claro! Deixo os detalhes do seu atendimento organizados aqui:\n"
            + (f"• Serviço: {procedure_type}\n" if procedure_type else "")
            + f"• Clínica: {unit_name}\n"
            + (f"• Horário: {slot_label}\n" if slot_label else "")
            + "\n".join(
                _post_booking_visit_guidance_lines(
                    unit_address=unit_address,
                    professional_name=professional_name,
                    include_documents=include_documents,
                )
            )
            + "\nSe quiser, também posso te lembrar o horário ou te ajudar com remarcar/cancelar."
        )
    else:
        response_text = (
            f"Claro! O endereço oficial da {unit_name} é:\n"
            + "\n".join(
                _post_booking_visit_guidance_lines(
                    unit_address=unit_address,
                    professional_name=professional_name,
                    include_documents=include_documents,
                )
            )
            + (
                "\nSe sua consulta já estiver marcada e você quiser, também posso te orientar sobre horário e documentos."
                if not include_documents
                else ""
            )
        )

    return {
        "mode": "official_visit_guidance",
        "response_text": response_text,
        "metadata": {
            "reason": "official_visit_guidance",
            "requested_topics": sorted(topics),
            "appointment_id": context.get("appointment_id"),
            "procedure_type": procedure_type,
            "unit_id": context.get("unit_id"),
            "unit_name": unit_name,
            "unit_address": unit_address,
            "selected_slot": {"label": slot_label} if slot_label else None,
            "professional_id": context.get("professional_id"),
            "professional_name": professional_name,
            "has_appointment": has_appointment,
        },
    }


def _build_booking_cpf_request_response(
    *,
    procedure_type: str | None,
    unit_name: str | None,
    selected_slot_label: str | None,
    unit_address: str | None = None,
    professional_name: str | None = None,
    session_token: str | None = None,
    retry: bool = False,
    missing_fields: list[str] | None = None,
    registration_retry_sent: bool = False,
) -> dict[str, Any]:
    fields = [field for field in (missing_fields or ["cpf"]) if field in {"full_name", "cpf", "birth_date", "phone"}]
    if not fields:
        fields = ["cpf"]
    fields_text = _format_registration_missing_fields(fields)
    guidance = (
        f"Para agilizar seu atendimento no dia da consulta, você pode me enviar {fields_text} agora."
    )
    if len(fields) > 1:
        guidance += " Pode mandar tudo em uma mensagem só, do seu jeito."
    if retry:
        guidance = (
            f"Não consegui identificar todos os dados ainda. "
            f"Se puder, me envie {fields_text}; também pode deixar para informar na recepção."
        )
    base_text = (
        "Perfeito! Seu agendamento já está confirmado.\n"
        f"• Serviço: {procedure_type or 'Atendimento'}\n"
        f"• Clínica: {unit_name or 'Unidade selecionada'}\n"
        + (f"• Horário: {selected_slot_label}\n" if selected_slot_label else "")
        + "\n".join(
            _post_booking_visit_guidance_lines(
                unit_address=unit_address,
                professional_name=professional_name,
            )
        )
        + "\n"
        + guidance
        + "\nSe preferir informar esses dados na recepção, tudo bem; seu horário continua confirmado."
    )
    metadata = _wizard_metadata_with_session(
        metadata={
            "procedure_type": procedure_type,
            "unit_name": unit_name,
            "unit_address": unit_address,
            "selected_slot": {"label": selected_slot_label} if selected_slot_label else None,
            "professional_name": professional_name,
            "reason": "request_cpf_after_booking",
            "missing_registration_fields": fields,
            "registration_retry_sent": bool(registration_retry_sent or retry),
            "body_text": f"Envie {fields_text} para agilizar o atendimento.",
            "footer_text": "Usamos esses dados apenas para identificação no atendimento.",
        },
        session_token=session_token,
        step="cpf_after_booking",
    )
    return {
        "mode": "booking_request_cpf_after_booking",
        "response_text": base_text,
        "metadata": metadata,
    }


def _build_booking_post_confirmation_response(
    *,
    procedure_type: str | None,
    unit_name: str | None,
    selected_slot_label: str | None,
    unit_address: str | None = None,
    professional_name: str | None = None,
    session_token: str | None = None,
) -> dict[str, Any]:
    text_body, interactive_payload = _build_post_booking_options_payload()
    buttons = interactive_payload.get("buttons") if isinstance(interactive_payload, dict) else []
    metadata = _wizard_metadata_with_session(
        metadata={
            "procedure_type": procedure_type,
            "unit_name": unit_name,
            "unit_address": unit_address,
            "selected_slot": {"label": selected_slot_label} if selected_slot_label else None,
            "professional_name": professional_name,
            "reason": "post_booking_guidance",
            "header_text": str(interactive_payload.get("header_text") or "Próximos passos"),
            "body_text": str(interactive_payload.get("body_text") or text_body),
            "footer_text": str(interactive_payload.get("footer_text") or "Você pode responder por texto."),
            "buttons": buttons if isinstance(buttons, list) else [],
        },
        session_token=session_token,
        step="post_confirmation_options",
    )
    return {
        "mode": "booking_post_confirmation_options",
        "response_text": _post_booking_guidance_text(
            procedure_type=procedure_type,
            unit_name=unit_name,
            selected_slot_label=selected_slot_label,
            unit_address=unit_address,
            professional_name=professional_name,
        ),
        "metadata": metadata,
    }


def _build_booking_registration_deferred_response(
    *,
    procedure_type: str | None,
    unit_name: str | None,
    selected_slot_label: str | None,
    unit_address: str | None = None,
    professional_name: str | None = None,
    session_token: str | None = None,
) -> dict[str, Any]:
    response = _build_booking_post_confirmation_response(
        procedure_type=procedure_type,
        unit_name=unit_name,
        selected_slot_label=selected_slot_label,
        unit_address=unit_address,
        professional_name=professional_name,
        session_token=session_token,
    )
    response["response_text"] = (
        "Sem problema, seu agendamento continua confirmado. "
        "Esses dados podem ser informados na recepção no dia da consulta.\n"
        f"{response.get('response_text') or ''}"
    ).strip()
    metadata = response.get("metadata") if isinstance(response.get("metadata"), dict) else {}
    metadata["registration_deferred"] = True
    response["metadata"] = metadata
    return response


def _build_booking_post_information_followup_response(
    *,
    procedure_type: str | None,
    unit_name: str | None,
    selected_slot_label: str | None,
    unit_address: str | None = None,
    professional_name: str | None = None,
    session_token: str | None = None,
) -> dict[str, Any]:
    metadata = _wizard_metadata_with_session(
        metadata={
            "procedure_type": procedure_type,
            "unit_name": unit_name,
            "unit_address": unit_address,
            "selected_slot": {"label": selected_slot_label} if selected_slot_label else None,
            "professional_name": professional_name,
            "reason": "post_booking_more_information",
        },
        session_token=session_token,
        step="post_confirmation_options",
    )
    return {
        "mode": "booking_post_information_followup",
        "response_text": (
            "Claro! Aqui estão as principais orientações do seu atendimento:\n"
            + (f"• Serviço: {procedure_type}\n" if procedure_type else "")
            + (f"• Clínica: {unit_name}\n" if unit_name else "")
            + (f"• Horário: {selected_slot_label}\n" if selected_slot_label else "")
            + "\n".join(
                _post_booking_visit_guidance_lines(
                    unit_address=unit_address,
                    professional_name=professional_name,
                )
            )
            + "\nSe precisar reagendar, cancelar ou falar com a recepção, é só me chamar por aqui."
        ),
        "metadata": metadata,
    }


def _build_booking_close_with_summary_response(
    *,
    procedure_type: str | None,
    unit_name: str | None,
    selected_slot_label: str | None,
    unit_address: str | None = None,
    professional_name: str | None = None,
    session_token: str | None = None,
) -> dict[str, Any]:
    metadata = _wizard_metadata_with_session(
        metadata={
            "procedure_type": procedure_type,
            "unit_name": unit_name,
            "unit_address": unit_address,
            "selected_slot": {"label": selected_slot_label} if selected_slot_label else None,
            "professional_name": professional_name,
            "reason": "booking_closed_by_user",
            "close_conversation": True,
        },
        session_token=session_token,
        step="post_confirmation_options",
    )
    return {
        "mode": "booking_close_with_summary",
        "response_text": _post_booking_close_summary_text(
            procedure_type=procedure_type,
            unit_name=unit_name,
            selected_slot_label=selected_slot_label,
            unit_address=unit_address,
            professional_name=professional_name,
        ),
        "metadata": metadata,
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


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _wizard_new_session_token() -> str:
    return uuid4().hex[:14]


def _wizard_step_from_mode(mode: str) -> str | None:
    mapping = {
        "welcome_message_start": "start_menu",
        "booking_wizard_resume_or_restart": "resume_or_restart",
        "booking_wizard_service_select": "service",
        "booking_wizard_unit_select": "unit",
        "booking_wizard_day_select": "day",
        "booking_wizard_time_select": "time",
        "booking_wizard_confirm": "confirm",
        "booking_request_cpf_after_booking": "cpf_after_booking",
        "booking_post_confirmation_options": "post_confirmation_options",
        "booking_post_information_followup": "post_confirmation_options",
        "booking_close_with_summary": "post_confirmation_options",
        "booking_cancel_confirm": "cancel_confirm",
        "booking_reschedule_day_select": "reschedule_day",
        "booking_reschedule_time_select": "reschedule_time",
        "booking_reschedule_confirm": "reschedule_confirm",
        "post_appointment_menu": "post_menu",
    }
    return mapping.get(str(mode or "").strip())


def _wizard_expected_reply_prefixes(step: str) -> tuple[str, ...]:
    mapping = {
        "service": ("svc_",),
        "unit": ("unit_",),
        "day": ("day_",),
        "time": ("time_", "time_change_", "menu_human"),
        "confirm": ("confirm_",),
        "start_menu": ("menu_",),
        "resume_or_restart": ("resume_saved_step", "restart_from_beginning"),
        "post_confirmation_options": ("post_info_",),
        "post_menu": ("post_menu_",),
        "cancel_confirm": ("cancel_",),
        "reschedule_day": ("day_", "reschedule_", "menu_human"),
        "reschedule_time": ("time_", "time_change_", "menu_human"),
        "reschedule_confirm": ("reschedule_",),
    }
    return mapping.get(step, ())


def _wizard_extract_reply_id(payload: dict[str, Any]) -> str:
    interactive_reply = payload.get("interactive_reply") if isinstance(payload.get("interactive_reply"), dict) else {}
    return str(interactive_reply.get("id") or "").strip()


def _wizard_reply_is_valid_for_step(*, step: str, reply_id: str) -> bool:
    normalized = _normalize_for_match(reply_id)
    if not normalized:
        return True
    if normalized in {
        "menu_human",
        "post_menu_rebook",
        "post_menu_human",
        "post_menu_close",
        "resume_saved_step",
        "restart_from_beginning",
        "post_info_more",
        "post_info_close",
    }:
        return True

    prefixes = _wizard_expected_reply_prefixes(step)
    if not prefixes:
        return True
    return normalized.startswith(prefixes)


def _wizard_metadata_with_session(
    *,
    metadata: dict[str, Any],
    session_token: str | None,
    step: str,
) -> dict[str, Any]:
    token = str(session_token or "").strip() or _wizard_new_session_token()
    now_utc = datetime.now(UTC)
    output = dict(metadata)
    output["session_token"] = token
    output["wizard_step"] = step
    output["step_created_at"] = now_utc.isoformat()
    output["step_expires_at"] = (now_utc + timedelta(minutes=WIZARD_STATE_EXPIRATION_MINUTES)).isoformat()
    output["step_ttl_minutes"] = WIZARD_STATE_EXPIRATION_MINUTES

    service_selected = str(output.get("service_selected") or output.get("procedure_type") or "").strip()
    clinic_name = str(output.get("clinic_name") or output.get("unit_name") or "").strip()
    clinic_id = str(output.get("clinic_id") or output.get("unit_id") or "").strip()
    selected_date = str(output.get("selected_date") or output.get("requested_date") or "").strip()
    selected_slot = output.get("selected_slot")
    selected_time = ""
    if isinstance(selected_slot, dict):
        selected_time = str(selected_slot.get("time") or "").strip()
        if not selected_time:
            selected_time = str(selected_slot.get("label") or "").strip()
    elif isinstance(selected_slot, str):
        selected_time = selected_slot.strip()

    output["service_selected"] = service_selected or None
    output["clinic_selected"] = {
        "id": clinic_id or None,
        "name": clinic_name or None,
    }
    output["date_selected"] = selected_date or None
    output["time_selected"] = selected_time or None
    output["ultima_interacao_em"] = now_utc.isoformat()
    return output


def _wizard_session_token_from_message(message: Message | None) -> str | None:
    if not message or not isinstance(message.payload, dict):
        return None
    scheduling = message.payload.get("scheduling") if isinstance(message.payload.get("scheduling"), dict) else {}
    token = str(scheduling.get("session_token") or "").strip()
    return token or None


def _wizard_session_is_expired(message: Message | None) -> bool:
    if not message:
        return False

    now_utc = datetime.now(UTC)
    if message.created_at:
        anchor_created_at = message.created_at if message.created_at.tzinfo else message.created_at.replace(tzinfo=UTC)
        if (now_utc - anchor_created_at).total_seconds() / 60.0 > WIZARD_STATE_EXPIRATION_MINUTES:
            return True

    if not isinstance(message.payload, dict):
        return False
    scheduling = message.payload.get("scheduling") if isinstance(message.payload.get("scheduling"), dict) else {}
    expires_at = _parse_iso_datetime(scheduling.get("step_expires_at"))
    if expires_at and expires_at <= now_utc:
        return True
    return False


def _latest_ai_wizard_message(db: Session, *, conversation: Conversation) -> Message | None:
    latest_messages = _recent_ai_outbound_messages(db, conversation=conversation, limit=1)
    if not latest_messages:
        return None
    message = latest_messages[0]
    payload = message.payload if isinstance(message.payload, dict) else {}
    mode = str(payload.get("mode") or "").strip()
    if mode.startswith("booking_") or mode in {
        "welcome_message_start",
        "post_appointment_menu",
        "no_slots_general",
        "no_slots_for_period",
        "no_slots_for_period_with_alternatives",
    }:
        return message
    return None


CONSECUTIVE_GUARD_EXEMPT_BOOKING_MODES = {
    "booking_wizard_resume_or_restart",
    "booking_wizard_service_select",
    "booking_wizard_unit_select",
    "booking_wizard_day_select",
    "booking_wizard_time_select",
    "booking_wizard_confirm",
    "booking_reschedule_day_select",
    "booking_reschedule_time_select",
    "booking_reschedule_confirm",
    "no_slots_general",
    "no_slots_for_period",
    "no_slots_for_period_with_alternatives",
    "appointment_created",
    "appointment_already_created",
    "booking_request_cpf_after_booking",
    "booking_post_confirmation_options",
    "booking_post_information_followup",
    "post_appointment_menu",
}


def _mode_exempts_consecutive_guard(mode: str | None) -> bool:
    return str(mode or "").strip() in CONSECUTIVE_GUARD_EXEMPT_BOOKING_MODES


def _normalize_resume_value(value: Any) -> str:
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value).strip())
    if not text:
        return ""
    normalized = _normalize_for_match(text)
    if normalized in {
        "none",
        "null",
        "undefined",
        "nao definido",
        "nao definida",
        "n/a",
        "-",
    }:
        return ""
    return text


def _wizard_state_from_scheduling_metadata(metadata: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(metadata, dict):
        return None

    service = _normalize_resume_value(
        metadata.get("service_selected") or metadata.get("procedure_type")
    )
    clinic_name = _normalize_resume_value(
        metadata.get("unit_name")
        or metadata.get("clinic_name")
        or ((metadata.get("clinic_selected") or {}).get("name") if isinstance(metadata.get("clinic_selected"), dict) else "")
    )
    clinic_id = _normalize_resume_value(
        metadata.get("unit_id")
        or metadata.get("clinic_id")
        or ((metadata.get("clinic_selected") or {}).get("id") if isinstance(metadata.get("clinic_selected"), dict) else "")
    )
    selected_date = _normalize_resume_value(metadata.get("date_selected") or metadata.get("requested_date"))
    selected_slot = metadata.get("selected_slot")
    selected_time = ""
    if isinstance(selected_slot, dict):
        selected_time = _normalize_resume_value(selected_slot.get("time") or selected_slot.get("label"))
    elif isinstance(selected_slot, str):
        selected_time = _normalize_resume_value(selected_slot)
    if not selected_time:
        selected_time = _normalize_resume_value(metadata.get("time_selected"))

    has_displayable_progress = any((service, clinic_name, selected_date, selected_time))
    has_technical_progress = bool(clinic_id and any((service, selected_date, selected_time)))
    has_progress = has_displayable_progress or has_technical_progress
    if not has_progress:
        return None

    return {
        "service": service or None,
        "clinic_id": clinic_id or None,
        "clinic_name": clinic_name or None,
        "date": selected_date or None,
        "time": selected_time or None,
        "selected_slot": selected_slot if isinstance(selected_slot, dict) else None,
        "session_token": str(metadata.get("session_token") or "").strip() or None,
        "requested_date": str(metadata.get("requested_date") or "").strip() or None,
        "period": str(metadata.get("period") or "").strip() or None,
    }


def _booking_state_summary_text(saved_state: dict[str, Any]) -> str:
    parts: list[str] = []
    service = _normalize_resume_value(saved_state.get("service"))
    clinic_name = _normalize_resume_value(saved_state.get("clinic_name"))
    selected_date = _normalize_resume_value(saved_state.get("date"))
    selected_time = _normalize_resume_value(saved_state.get("time"))

    if service:
        parts.append(f"serviço: {service}")
    if clinic_name:
        parts.append(f"clínica: {clinic_name}")
    if selected_date:
        parsed_date = _parse_iso_date(selected_date)
        date_label = parsed_date.strftime("%d/%m") if parsed_date else selected_date
        parts.append(f"data: {date_label}")
    if selected_time:
        parts.append(f"horário: {selected_time}")
    return ", ".join(parts)


def _is_patient_discomfort_message(normalized_text: str) -> bool:
    if not normalized_text:
        return False
    return any(_normalize_for_match(pattern) in normalized_text for pattern in PATIENT_DISCOMFORT_PATTERNS)


def _booking_wizard_continuation_hint(*, mode: str, step: str | None) -> str:
    step_key = str(step or "").strip()
    mode_key = str(mode or "").strip()
    if step_key == "service" or mode_key == "booking_wizard_service_select":
        return "Para continuar, escolha o serviço na lista ou escreva o nome do atendimento."
    if step_key == "unit" or mode_key == "booking_wizard_unit_select":
        return "Para continuar, escolha a unidade na lista ou escreva a unidade desejada."
    if step_key == "day" or mode_key in {
        "booking_wizard_day_select",
        "no_slots_general",
        "no_slots_for_period",
        "no_slots_for_period_with_alternatives",
    }:
        return "Para continuar, escolha uma data disponível ou escreva a data que você prefere."
    if step_key == "time" or mode_key == "booking_wizard_time_select":
        return "Para continuar, escolha um horário disponível ou escreva o horário que você prefere."
    if step_key == "confirm" or mode_key == "booking_wizard_confirm":
        return "Para continuar, confirme se posso agendar ou escolha trocar o horário."
    return "Para continuar, responda com a opção desejada ou escreva como prefere seguir."


def _build_booking_wizard_free_text_followup_response(
    *,
    latest_mode: str,
    latest_scheduling: dict[str, Any],
    latest_step: str | None,
    inbound_text: str,
    normalized_inbound: str,
    session_token: str | None,
) -> dict[str, Any] | None:
    if latest_mode not in BOOKING_WIZARD_FREE_TEXT_CONTEXT_MODES or not normalized_inbound:
        return None

    metadata = dict(latest_scheduling)
    metadata = _wizard_metadata_with_session(
        metadata=metadata,
        session_token=session_token,
        step=latest_step or _wizard_step_from_mode(latest_mode) or "service",
    )
    metadata["reason"] = "free_text_during_booking_wizard"
    metadata["free_text_message"] = inbound_text[:280]

    state = _wizard_state_from_scheduling_metadata(metadata) or {}
    summary = _booking_state_summary_text(state)
    continuation_hint = _booking_wizard_continuation_hint(mode=latest_mode, step=latest_step)

    if _is_patient_discomfort_message(normalized_inbound):
        intro = (
            "Sinto muito que você esteja com esse desconforto. "
            "Não consigo avaliar clinicamente por aqui, mas posso seguir com seu agendamento para a equipe te atender."
        )
        safety_note = (
            "Se a dor estiver forte, com inchaço, febre, sangramento ou trauma, procure atendimento de urgência "
            "ou fale com a equipe da clínica."
        )
        response_text = f"{intro}\n{safety_note}\n{continuation_hint}"
    else:
        response_text = (
            "Entendi sua mensagem. Para não perdermos o agendamento que está em andamento, vou manter as opções abertas.\n"
            f"{continuation_hint}"
        )

    if summary:
        response_text = f"{response_text}\nAté aqui tenho: {summary}."

    return {
        "mode": latest_mode,
        "response_text": response_text,
        "metadata": metadata,
    }


def _has_meaningful_saved_state(saved_state: dict[str, Any] | None) -> bool:
    if not isinstance(saved_state, dict):
        return False
    return bool(_booking_state_summary_text(saved_state))


def _latest_saved_booking_state(db: Session, *, conversation: Conversation) -> dict[str, Any] | None:
    recent_messages = _recent_ai_outbound_messages(db, conversation=conversation, limit=25)
    for message in recent_messages:
        payload = message.payload if isinstance(message.payload, dict) else {}
        mode = str(payload.get("mode") or "").strip()
        if not mode.startswith("booking_"):
            continue
        scheduling = payload.get("scheduling") if isinstance(payload.get("scheduling"), dict) else {}
        state = _wizard_state_from_scheduling_metadata(scheduling)
        if not state:
            continue
        state["mode"] = mode
        state["last_ai_message_id"] = str(message.id)
        state["last_ai_message_at"] = message.created_at.isoformat() if message.created_at else None
        return state
    return _saved_state_from_manual_webchat_snapshot(
        _manual_webchat_booking_snapshot(db, conversation=conversation)
    )


def _build_resume_or_restart_response(
    *,
    saved_state: dict[str, Any],
    idle_minutes: float | None = None,
) -> dict[str, Any]:
    summary = _booking_state_summary_text(saved_state)
    reply_text = (
        "Que bom te ver novamente por aqui. "
        "Se você quiser, continuo exatamente de onde paramos."
    )
    if summary:
        reply_text = (
            "Que bom te ver novamente por aqui."
            f" Eu já tinha separado estas escolhas: {summary}. "
            "Se fizer sentido para você, continuo desse ponto agora."
        )

    rows = [
        {"id": "resume_saved_step", "title": "Continuar", "description": "Retomar de onde parou"},
        {"id": "restart_from_beginning", "title": "Reiniciar", "description": "Começar novo atendimento"},
    ]
    metadata = _wizard_metadata_with_session(
        metadata={
            "reason": "idle_timeout_resume_options",
            "saved_state": saved_state,
            "rows": rows,
            "button_title": "Escolher",
            "section_title": "Retomar atendimento",
            "header_text": "Atendimento",
            "body_text": "Escolha se prefere continuar ou reiniciar.",
            "footer_text": "Se quiser, também pode responder com suas palavras.",
        },
        session_token=str(saved_state.get("session_token") or "").strip() or None,
        step="resume_or_restart",
    )
    return {
        "mode": "booking_wizard_resume_or_restart",
        "response_text": reply_text,
        "metadata": metadata,
    }


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


def _is_manual_booking_progress_request(text: str) -> bool:
    normalized = _normalize_for_match(text)
    if not normalized:
        return False

    direct_phrases = (
        "configurei manualmente",
        "configurado manualmente",
        "atualizei manualmente",
        "atualizei meu agendamento",
        "considere essas informacoes",
        "continue meu atendimento",
        "o que eu salvei",
        "oque eu salvei",
        "o que ja salvei",
        "oque ja salvei",
        "ja configurei",
        "vc viu",
        "voce viu",
    )
    if any(phrase in normalized for phrase in direct_phrases):
        return True

    return "manual" in normalized and any(
        keyword in normalized
        for keyword in ("agendamento", "configurei", "atualizei", "salvei")
    )


def _wizard_active_units(db: Session, *, tenant_id: UUID) -> list[Unit]:
    return db.execute(
        select(Unit)
        .where(
            Unit.tenant_id == tenant_id,
            Unit.is_active.is_(True),
        )
        .order_by(Unit.created_at.asc())
    ).scalars().all()


def _wizard_single_active_unit(db: Session, *, tenant_id: UUID) -> Unit | None:
    units = _wizard_active_units(db, tenant_id=tenant_id)
    return units[0] if len(units) == 1 else None


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
    session_token: str | None = None,
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
        service_short = service[:24]
        rows.append(
            {
                "id": f"svc_{index}",
                "title": service_short,
                "description": "Toque para escolher",
            }
        )

    metadata = _wizard_metadata_with_session(
        metadata={
            "services": services,
            "period": period,
            "requested_date": requested_date.isoformat() if requested_date else None,
            "rows": rows,
            "button_title": "Serviços",
            "section_title": "Atendimentos",
            "header_text": "Agendamento",
            "body_text": "Escolha uma opção abaixo ou escreva o serviço com suas palavras.",
            "footer_text": "Se preferir, também pode escrever o serviço com suas palavras.",
            "preferred_service": preferred_service,
        },
        session_token=session_token,
        step="service",
    )
    display_name = _patient_display_name_for_conversation(db, conversation=conversation)
    has_complete_name = bool(display_name)
    if not has_complete_name and conversation.patient_id:
        snapshot = _patient_registration_snapshot(db, conversation=conversation)
        has_complete_name = _has_complete_patient_name(snapshot.get("full_name"))
    default_intro = (
        f"Oi, {display_name}, tudo bem? Claro, vou te ajudar com o agendamento. "
        "Me confirma qual atendimento você quer fazer."
        if display_name
        else (
            "Oi, tudo bem? Claro, vou te ajudar com o agendamento. "
            "Me confirma qual atendimento você quer fazer. "
            "Se quiser, já me diga também como posso te chamar; se preferir, pode só escolher o atendimento agora."
            if not has_complete_name
            else "Oi, tudo bem? Claro, vou te ajudar com o agendamento. Me confirma qual atendimento você quer fazer."
        )
    )

    response = {
        "mode": "booking_wizard_service_select",
        "response_text": intro_text or default_intro,
        "metadata": metadata,
    }
    return _append_webchat_existing_patient_lookup_hint(
        db,
        conversation=conversation,
        response=response,
    )


def _wizard_build_unit_or_day_step_response(
    db: Session,
    *,
    conversation: Conversation,
    procedure_type: str,
    period: str | None,
    requested_date: date | None,
    operation_timezone: ZoneInfo,
    config: dict[str, Any],
    session_token: str | None = None,
) -> dict[str, Any]:
    single_unit = _wizard_single_active_unit(db, tenant_id=conversation.tenant_id)
    if single_unit:
        if conversation.unit_id != single_unit.id:
            conversation.unit_id = single_unit.id
            db.add(conversation)
            db.flush()
        return _wizard_build_day_step_response(
            db,
            conversation=conversation,
            unit=single_unit,
            procedure_type=procedure_type,
            period=period,
            requested_date=requested_date,
            operation_timezone=operation_timezone,
            config=config,
            session_token=session_token,
        )

    return _wizard_build_unit_step_response(
        db,
        conversation=conversation,
        procedure_type=procedure_type,
        period=period,
        requested_date=requested_date,
        session_token=session_token,
    )


def _wizard_build_unit_step_response(
    db: Session,
    *,
    conversation: Conversation,
    procedure_type: str,
    period: str | None,
    requested_date: date | None,
    session_token: str | None = None,
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
        unit_short = unit.name[:24]
        unit_choices.append({"id": str(unit.id), "name": unit.name, "option_id": option_id})
        rows.append(
            {
                "id": option_id,
                "title": unit_short,
                "description": "Unidade disponível",
            }
        )
    rows.append({"id": "unit_change_service", "title": "Trocar serviço", "description": "Escolher outro serviço"})
    rows.append({"id": "menu_human", "title": "Falar com atendente", "description": "Encaminhar para humano"})

    metadata = _wizard_metadata_with_session(
        metadata={
            "procedure_type": procedure_type,
            "period": period,
            "requested_date": requested_date.isoformat() if requested_date else None,
            "units": unit_choices,
            "rows": rows,
            "button_title": "Clínicas",
            "section_title": "Escolha a clínica",
            "header_text": "Agendamento",
            "body_text": "Confira as unidades disponíveis.",
            "footer_text": "Se preferir, também pode escrever a clínica que deseja.",
        },
        session_token=session_token,
        step="unit",
    )

    response = {
        "mode": "booking_wizard_unit_select",
        "response_text": f"Perfeito, já deixei esse atendimento anotado: {procedure_type}. Agora me diz em qual unidade você prefere ser atendido.",
        "metadata": metadata,
    }
    return _append_webchat_existing_patient_lookup_hint(
        db,
        conversation=conversation,
        response=response,
    )


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
    service_catalog = get_service_duration_catalog(db, tenant_id=conversation.tenant_id)
    slot_duration_minutes = _resolve_slot_duration_minutes(
        db,
        tenant_id=conversation.tenant_id,
        procedure_type=procedure_type,
        service_catalog=service_catalog,
    )
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
            slot_duration_minutes=slot_duration_minutes,
            service_catalog=service_catalog,
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
    session_token: str | None = None,
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
        rows = [
            {"id": "day_change_service", "title": "Trocar serviço", "description": "Escolher outro serviço"},
            {"id": "menu_human", "title": "Falar com atendente", "description": "Encaminhar para humano"},
        ]
        return {
            "mode": "no_slots_general",
            "response_text": (
                "No momento não encontrei dias com horários disponíveis para este serviço. "
                "Se quiser, posso te ajudar a trocar o serviço ou te direcionar para atendimento humano."
            ),
            "metadata": _wizard_metadata_with_session(
                metadata={
                    "reason": "no_slots_general",
                    "procedure_type": procedure_type,
                    "unit_id": str(unit.id),
                    "unit_name": unit.name,
                    "rows": rows,
                    "button_title": "Opções",
                    "section_title": "Como deseja continuar?",
                    "header_text": "Agendamento",
                    "body_text": "Não encontrei dias disponíveis para esse serviço nessa unidade.",
                    "footer_text": "Você pode escolher outro serviço ou falar com um atendente.",
                },
                session_token=session_token,
                step="day",
            ),
        }

    rows: list[dict[str, str]] = []
    for day_choice in day_choices:
        day_short = day_choice["label"].split(",")[0][:24]
        rows.append(
            {
                "id": day_choice["id"],
                "title": day_short,
                "description": day_choice["label"][:72],
            }
        )
    rows.append({"id": "day_change_service", "title": "Trocar serviço", "description": "Escolher outro serviço"})
    rows.append({"id": "menu_human", "title": "Falar com atendente", "description": "Encaminhar para humano"})

    metadata = _wizard_metadata_with_session(
        metadata={
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
            "body_text": "Confira os dias disponíveis.",
            "footer_text": "Se preferir, pode me dizer a data por mensagem.",
        },
        session_token=session_token,
        step="day",
    )
    visible_day_lines = [f"{index}) {choice['label']}" for index, choice in enumerate(day_choices[:7], start=1)]

    response = {
        "mode": "booking_wizard_day_select",
        "response_text": (
            f"Ótimo, essa unidade funciona para você. Aqui estão os dias disponíveis para {procedure_type} na {unit.name}:\n"
            + "\n".join(visible_day_lines)
            + "\nEscolha uma das opções acima ou me diga a data que prefere."
        ),
        "metadata": metadata,
    }
    return _append_webchat_existing_patient_lookup_hint(
        db,
        conversation=conversation,
        response=response,
    )


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
    service_catalog = get_service_duration_catalog(db, tenant_id=conversation.tenant_id)
    slot_duration_minutes = _resolve_slot_duration_minutes(
        db,
        tenant_id=conversation.tenant_id,
        procedure_type=procedure_type,
        service_catalog=service_catalog,
    )
    slots = _list_available_slots(
        db,
        tenant_id=conversation.tenant_id,
        unit_id=unit.id,
        config=config,
        procedure_type=procedure_type,
        period=period,
        requested_date=selected_date,
        max_slots=10,
        slot_duration_minutes=slot_duration_minutes,
        service_catalog=service_catalog,
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
    session_token: str | None = None,
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
        rows = [
            {"id": "time_change_day", "title": "Trocar dia", "description": "Ver outro dia disponível"},
            {"id": "day_change_service", "title": "Trocar serviço", "description": "Escolher outro serviço"},
            {"id": "menu_human", "title": "Falar com atendente", "description": "Encaminhar para humano"},
        ]
        return {
            "mode": "no_slots_general",
            "response_text": (
                f"No momento não encontrei horários disponíveis para {selected_date.strftime('%d/%m')}. "
                "Se quiser, posso verificar outro dia, trocar o serviço ou te encaminhar para atendimento humano."
            ),
            "metadata": _wizard_metadata_with_session(
                metadata={
                    "reason": "no_slots_general",
                    "requested_date": selected_date.isoformat(),
                    "procedure_type": procedure_type,
                    "unit_id": str(unit.id),
                    "unit_name": unit.name,
                    "rows": rows,
                    "button_title": "Opções",
                    "section_title": "Como deseja continuar?",
                    "header_text": "Agendamento",
                    "body_text": f"Não encontrei horários para {selected_date.strftime('%d/%m')}.",
                    "footer_text": "Você pode tentar outro dia, trocar o serviço ou falar com um atendente.",
                },
                session_token=session_token,
                step="time",
            ),
        }

    visible_slot_choices = slot_choices[:7]
    rows: list[dict[str, str]] = []
    for index, choice in enumerate(visible_slot_choices, start=1):
        time_short = str(choice.get("time") or f"Opção {index}")[:24]
        rows.append(
            {
                "id": str(choice.get("id") or f"time_{index}"),
                "title": time_short,
                "description": str(choice.get("label") or "")[:72],
            }
        )
    rows.append({"id": "time_change_day", "title": "Trocar dia", "description": "Selecionar outro dia"})
    rows.append({"id": "time_change_service", "title": "Trocar serviço", "description": "Selecionar outro serviço"})
    rows.append({"id": "menu_human", "title": "Falar com atendente", "description": "Encaminhar para humano"})

    metadata = _wizard_metadata_with_session(
        metadata={
            "procedure_type": procedure_type,
            "unit_id": str(unit.id),
            "unit_name": unit.name,
            "period": period,
            "requested_date": selected_date.isoformat(),
            "slot_choices": visible_slot_choices,
            "rows": rows,
            "button_title": "Horários",
            "section_title": "Escolha o horário",
            "header_text": "Agendamento",
            "body_text": "Confira os horários disponíveis.",
            "footer_text": "Se preferir, pode escrever o horário em texto livre.",
        },
        session_token=session_token,
        step="time",
    )

    return {
        "mode": "booking_wizard_time_select",
        "response_text": f"Perfeito, deixei o dia {selected_date.strftime('%d/%m')} separado. Agora me diz qual horário fica melhor para você.",
        "metadata": metadata,
    }


def _wizard_build_confirm_step_response(
    *,
    procedure_type: str,
    unit: Unit,
    selected_date: date,
    period: str | None,
    selected_slot_choice: dict[str, Any],
    session_token: str | None = None,
) -> dict[str, Any]:
    slot_label = str(selected_slot_choice.get("label") or "")
    selected_date_label = selected_date.strftime("%d/%m")
    buttons = [
        {"id": "confirm_yes", "title": "Sim"},
        {"id": "confirm_no", "title": "Não"},
        {"id": "confirm_change_time", "title": "Trocar horário"},
    ]
    metadata = _wizard_metadata_with_session(
        metadata={
            "procedure_type": procedure_type,
            "unit_id": str(unit.id),
            "unit_name": unit.name,
            "period": period,
            "requested_date": selected_date.isoformat(),
            "selected_slot": selected_slot_choice,
            "buttons": buttons,
            "header_text": "Confirmação",
            "body_text": "Confirme ou troque o horário.",
            "footer_text": "Você também pode confirmar ou ajustar por mensagem.",
        },
        session_token=session_token,
        step="confirm",
    )
    return {
        "mode": "booking_wizard_confirm",
        "response_text": (
            "Perfeito, está quase pronto. Posso confirmar seu agendamento?\n"
            f"• Serviço: {procedure_type}\n"
            f"• Unidade: {unit.name}\n"
            f"• Data: {selected_date_label}\n"
            f"• Horário: {slot_label}"
        ),
        "metadata": metadata,
    }


def _wizard_resume_saved_step_response(
    db: Session,
    *,
    conversation: Conversation,
    saved_state: dict[str, Any],
    config: dict[str, Any],
    operation_timezone: ZoneInfo,
) -> dict[str, Any]:
    service = str(saved_state.get("service") or "").strip()
    if not service:
        return _wizard_build_service_step_response(
            db,
            conversation=conversation,
            intro_text="Vamos continuar do ponto certo. Primeiro me confirme o serviço desejado:",
            period=None,
            requested_date=None,
            session_token=str(saved_state.get("session_token") or "").strip() or None,
        )

    clinic_id_raw = str(saved_state.get("clinic_id") or "").strip()
    clinic_id = None
    if clinic_id_raw:
        try:
            clinic_id = UUID(clinic_id_raw)
        except (TypeError, ValueError):
            clinic_id = None

    unit = None
    if clinic_id:
        unit = db.scalar(
            select(Unit).where(
                Unit.id == clinic_id,
                Unit.tenant_id == conversation.tenant_id,
                Unit.is_active.is_(True),
            )
        )

    requested_date = _parse_iso_date(saved_state.get("date"))
    period = str(saved_state.get("period") or "").strip().lower() or None
    if period not in {"morning", "afternoon", "evening"}:
        period = None
    session_token = str(saved_state.get("session_token") or "").strip() or None

    if not unit:
        return _wizard_build_unit_or_day_step_response(
            db,
            conversation=conversation,
            procedure_type=service,
            period=period,
            requested_date=requested_date,
            operation_timezone=operation_timezone,
            config=config,
            session_token=session_token,
        )

    if not requested_date:
        return _wizard_build_day_step_response(
            db,
            conversation=conversation,
            unit=unit,
            procedure_type=service,
            period=period,
            requested_date=None,
            operation_timezone=operation_timezone,
            config=config,
            session_token=session_token,
        )

    selected_slot_raw = saved_state.get("selected_slot")
    selected_slot = selected_slot_raw if isinstance(selected_slot_raw, dict) else None
    preferred_time = _normalize_resume_value(saved_state.get("time"))
    if not selected_slot and preferred_time:
        slot_choices = _wizard_collect_time_choices(
            db,
            conversation=conversation,
            unit=unit,
            procedure_type=service,
            period=period,
            selected_date=requested_date,
            config=config,
        )
        selected_slot = next(
            (
                choice
                for choice in slot_choices
                if _normalize_for_match(str(choice.get("time") or "")) == _normalize_for_match(preferred_time)
                or _normalize_for_match(str(choice.get("label") or "")) == _normalize_for_match(preferred_time)
            ),
            None,
        )
        if selected_slot:
            return _wizard_build_confirm_step_response(
                procedure_type=service,
                unit=unit,
                selected_date=requested_date,
                period=period,
                selected_slot_choice=selected_slot,
                session_token=session_token,
            )

    if not selected_slot:
        return _wizard_build_time_step_response(
            db,
            conversation=conversation,
            unit=unit,
            procedure_type=service,
            period=period,
            selected_date=requested_date,
            config=config,
            session_token=session_token,
        )

    return _wizard_build_confirm_step_response(
        procedure_type=service,
        unit=unit,
        selected_date=requested_date,
        period=period,
        selected_slot_choice=selected_slot,
        session_token=session_token,
    )


def _wizard_parse_confirmation_choice(token: str) -> bool | None:
    normalized = _normalize_for_match(token or "")
    option_index = _extract_option_index_choice(token)
    if option_index == 1:
        return True
    if option_index == 2:
        return False
    if any(keyword in normalized for keyword in BOOKING_WIZARD_CONFIRM_YES_KEYWORDS):
        return True
    if any(keyword in normalized for keyword in BOOKING_WIZARD_CONFIRM_NO_KEYWORDS):
        return False
    return None


def _wizard_parse_confirmation_action(token: str) -> str | None:
    normalized = _normalize_for_match(token or "")
    option_index = _extract_option_index_choice(token)
    if option_index == 3:
        return "change_time"
    if any(keyword in normalized for keyword in BOOKING_WIZARD_CHANGE_TIME_KEYWORDS):
        return "change_time"
    if any(keyword in normalized for keyword in BOOKING_WIZARD_CHANGE_DAY_KEYWORDS):
        return "change_day"
    if any(keyword in normalized for keyword in BOOKING_WIZARD_CHANGE_SERVICE_KEYWORDS):
        return "change_service"
    if any(keyword in normalized for keyword in BOOKING_WIZARD_HUMAN_KEYWORDS):
        return "human"
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
        if normalized == service_norm or normalized in service_norm or service_norm in normalized:
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
        unit_name_pieces = [
            piece
            for piece in unit_name.split()
            if len(piece) > 2 and piece not in {"unidade", "clinica", "clinicas", "zona"}
        ]
        if unit_name and (
            normalized == unit_name
            or normalized in unit_name
            or unit_name in normalized
            or any(piece in normalized for piece in unit_name_pieces)
        ):
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

    weekday_terms = ("segunda", "terca", "terça", "quarta", "quinta", "sexta", "sabado", "sábado", "domingo")
    for choice in day_choices:
        label = _normalize_for_match(str(choice.get("label") or ""))
        description = _normalize_for_match(str(choice.get("description") or ""))
        blob = f"{label} {description} {_normalize_for_match(str(choice.get('date') or ''))}"
        if normalized and normalized in blob:
            return _parse_iso_date(choice.get("date"))
        if any(term in normalized and term in blob for term in weekday_terms):
            return _parse_iso_date(choice.get("date"))
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


def _wizard_select_welcome_menu_option(token: str) -> str | None:
    raw = str(token or "").strip()
    if not raw:
        return None

    normalized = _normalize_for_match(raw)
    direct_ids = {option["id"] for option in WELCOME_MENU_OPTIONS}
    if normalized in direct_ids:
        return normalized

    index = _extract_option_index_choice(raw)
    if index is not None and 1 <= index <= len(WELCOME_MENU_OPTIONS):
        return WELCOME_MENU_OPTIONS[index - 1]["id"]

    keyword_map: dict[str, tuple[str, ...]] = {
        "menu_schedule": ("agendamento", "agendamentos", "agenda", "horario", "horarios"),
        "menu_services": ("servico", "servicos", "procedimento", "procedimentos", "valores", "valor"),
        "menu_support": ("suporte", "ajuda"),
        "menu_suggestion": ("sugestao", "sugestoes", "melhoria"),
        "menu_complaint": ("reclamacao", "reclamacoes", "insatisfacao"),
        "menu_human": ("falar com atendente", "atendente", "humano", "pessoa"),
    }
    for option_id, keywords in keyword_map.items():
        if any(keyword in normalized for keyword in keywords):
            return option_id
    return None


def _build_welcome_menu_followup_buttons_response(
    *,
    mode: str,
    header_text: str,
    body_text: str,
    reason: str,
    session_token: str | None = None,
) -> dict[str, Any]:
    tags_map = {
        "support_selected": ["menu_suporte"],
        "suggestion_selected": ["menu_sugestao"],
        "complaint_selected": ["menu_reclamacao"],
    }
    add_tags = tags_map.get(reason, [])

    buttons = [
        {"id": "menu_schedule", "title": "Agendamentos"},
        {"id": "menu_services", "title": "Serviços"},
        {"id": "menu_human", "title": "Falar com atendente"},
    ]
    metadata = _wizard_metadata_with_session(
        metadata={
            "reason": reason,
            "header_text": header_text,
            "body_text": body_text,
            "footer_text": "Você pode tocar em um botão ou escrever sua mensagem.",
            "buttons": buttons,
            "add_tags": add_tags,
        },
        session_token=session_token,
        step="start_menu",
    )
    metadata["wizard_step"] = "start_menu_followup"

    return {
        "mode": mode,
        "response_text": body_text,
        "metadata": metadata,
    }


def _wizard_text_matches_current_step(
    *,
    step: str,
    inbound_text: str,
    normalized_inbound: str,
    requested_date: date | None,
    period: str | None,
) -> bool:
    if not normalized_inbound:
        return False

    has_explicit_time = _extract_time_choice(inbound_text) is not None
    weekday_terms = (
        "segunda",
        "terca",
        "terça",
        "quarta",
        "quinta",
        "sexta",
        "sabado",
        "sábado",
        "domingo",
        "amanha",
        "amanhã",
        "hoje",
    )
    has_day_reference = bool(
        requested_date
        or re.search(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", inbound_text)
        or any(term in normalized_inbound for term in weekday_terms)
    )
    has_availability_signal = _is_explicit_availability_request(inbound_text)

    if step in {"day", "reschedule_day"}:
        return bool(has_day_reference or has_explicit_time or period or has_availability_signal)

    if step in {"time", "reschedule_time"}:
        return bool(has_explicit_time or period or has_day_reference or has_availability_signal)

    if step == "unit":
        unit_terms = (
            "unidade",
            "clinica",
            "clínica",
            "centro",
            "paulista",
            "zona",
            "sul",
            "norte",
            "leste",
            "oeste",
        )
        return bool(
            any(term in normalized_inbound for term in unit_terms)
            or has_day_reference
            or has_explicit_time
            or period
            or has_availability_signal
        )

    if step == "service":
        return bool(
            _wizard_has_explicit_service_inbound(inbound_text)
            or has_day_reference
            or has_explicit_time
            or period
            or has_availability_signal
        )

    if step in {"confirm", "cancel_confirm", "reschedule_confirm"}:
        return _is_booking_confirmation_message(inbound_text) or normalized_inbound in {
            "sim",
            "confirmo",
            "pode confirmar",
            "pode cancelar",
            "pode remarcar",
            "nao",
            "não",
        }

    if step == "cpf_after_booking":
        return bool(
            _registration_skip_requested(inbound_text)
            or _extract_registration_name_from_text(inbound_text)
            or _extract_cpf_from_text(inbound_text)
            or _extract_birth_date_from_text(inbound_text, allow_unlabeled=True)
            or _extract_phone_from_text(inbound_text)
        )

    return False


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
    interactive_reply_id = _wizard_extract_reply_id(inbound_payload)
    selection_token = _extract_wizard_selection_token(
        inbound_message=inbound_message,
        inbound_text=inbound_text,
    )
    selection_token_normalized = _normalize_for_match(selection_token)
    normalized_inbound = _normalize_for_match(inbound_text)
    period = _detect_period_preference(inbound_text)
    requested_date = _extract_requested_date_from_text(text=inbound_text, timezone=operation_timezone)
    reset_requested = _booking_reset_requested(inbound_text)
    resume_requested = _booking_resume_requested(inbound_text)
    restart_requested = _booking_restart_requested(inbound_text)
    has_scheduling_keywords = any(keyword in normalized_inbound for keyword in (*SCHEDULING_INTENT_KEYWORDS, *AVAILABILITY_REQUEST_KEYWORDS))
    force_wizard = any(keyword in normalized_inbound for keyword in BOOKING_WIZARD_FORCE_KEYWORDS)
    has_confirmation_choice = _wizard_parse_confirmation_choice(selection_token) is not None
    welcome_menu_choice = _wizard_select_welcome_menu_option(selection_token)
    manual_progress_requested = _is_manual_booking_progress_request(inbound_text)
    manual_followup_source = str(inbound_payload.get("source") or "").strip() == "public_webchat_summary_manual_update"
    selection_like = (
        _extract_option_index_choice(inbound_text) is not None
        or _extract_time_choice(inbound_text) is not None
        or bool(re.search(r"\b(?:svc|unit|day|time|confirm|cancel|reschedule)[_-]", _normalize_for_match(selection_token)))
    )

    saved_state = _latest_saved_booking_state(db, conversation=conversation)
    latest_wizard = _latest_ai_wizard_message(db, conversation=conversation)
    if _has_meaningful_saved_state(saved_state) and (
        manual_followup_source
        or manual_progress_requested
        or (
            conversation.channel == "webchat"
            and _is_greeting_only_message(inbound_text)
            and str((saved_state or {}).get("source") or "").strip() == "manual_webchat_summary"
        )
    ):
        resumed_response = _wizard_resume_saved_step_response(
            db,
            conversation=conversation,
            saved_state=saved_state or {},
            config=config,
            operation_timezone=operation_timezone,
        )
        resumed_metadata = (
            resumed_response.get("metadata")
            if isinstance(resumed_response.get("metadata"), dict)
            else {}
        )
        resumed_metadata["reason"] = (
            "manual_draft_resume_from_panel"
            if manual_followup_source
            else "manual_draft_resume_from_patient"
        )
        resumed_response["metadata"] = resumed_metadata
        return resumed_response

    if latest_wizard:
        latest_payload = latest_wizard.payload if isinstance(latest_wizard.payload, dict) else {}
        latest_mode = str(latest_payload.get("mode") or "").strip()
        latest_scheduling = latest_payload.get("scheduling") if isinstance(latest_payload.get("scheduling"), dict) else {}
        latest_step = _wizard_step_from_mode(latest_mode) or str(latest_scheduling.get("wizard_step") or "").strip()
        plain_preferred_name = (
            _extract_preferred_name_from_text(inbound_text, allow_plain=True)
            if latest_step == "service"
            and not has_interactive_reply
            and not selection_like
            and not has_scheduling_keywords
            and not _is_booking_confirmation_message(inbound_text)
            else None
        )
        free_text_matches_current_step = _wizard_text_matches_current_step(
            step=latest_step,
            inbound_text=inbound_text,
            normalized_inbound=normalized_inbound,
            requested_date=requested_date,
            period=period,
        )
        if not (
            has_interactive_reply
            or selection_like
            or has_scheduling_keywords
            or _is_booking_confirmation_message(inbound_text)
            or has_confirmation_choice
            or force_wizard
            or welcome_menu_choice is not None
            or free_text_matches_current_step
            or plain_preferred_name
        ):
            free_text_followup = _build_booking_wizard_free_text_followup_response(
                latest_mode=latest_mode,
                latest_scheduling=latest_scheduling,
                latest_step=latest_step,
                inbound_text=inbound_text,
                normalized_inbound=normalized_inbound,
                session_token=str(latest_scheduling.get("session_token") or "").strip()
                or _wizard_session_token_from_message(latest_wizard),
            )
            if free_text_followup:
                return free_text_followup
            return None

        latest_session_token = str(latest_scheduling.get("session_token") or "").strip() or _wizard_session_token_from_message(latest_wizard)
        if reset_requested:
            return _wizard_build_service_step_response(
                db,
                conversation=conversation,
                intro_text="Perfeito, vou reorganizar seu atendimento do início para evitar qualquer confusão. Me confirma qual atendimento você quer fazer.",
                period=period,
                requested_date=requested_date,
                preferred_service=_infer_procedure_type(inbound_text=inbound_text, context=context),
            )

        if _wizard_session_is_expired(latest_wizard):
            return _wizard_build_service_step_response(
                db,
                conversation=conversation,
                intro_text="O fluxo anterior expirou para evitar erro. Vamos começar de novo pelo serviço.",
                period=period,
                requested_date=requested_date,
                preferred_service=_infer_procedure_type(inbound_text=inbound_text, context=context),
            )

        if has_interactive_reply and not _wizard_reply_is_valid_for_step(step=latest_step, reply_id=interactive_reply_id):
            return _wizard_build_service_step_response(
                db,
                conversation=conversation,
                intro_text="Recebi uma opção de outra etapa. Para não correr risco de marcar errado, vou recomeçar com você pelo atendimento desejado.",
                period=period,
                requested_date=requested_date,
                preferred_service=_infer_procedure_type(inbound_text=inbound_text, context=context),
            )

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
                intro_text="Vou reorganizar o agendamento para evitar erro. Me confirma qual atendimento você quer fazer.",
                period=period,
                requested_date=requested_date,
                preferred_service=_infer_procedure_type(inbound_text=inbound_text, context=context),
            )
        carried_period_raw = str(latest_scheduling.get("period") or "").strip().lower()
        carried_period = period or (carried_period_raw if carried_period_raw in {"morning", "afternoon", "evening"} else None)
        carried_requested_date = requested_date or _parse_iso_date(latest_scheduling.get("requested_date"))
        carried_service = str(latest_scheduling.get("procedure_type") or "").strip()
        if plain_preferred_name:
            _capture_contact_profile_from_inbound(
                db,
                tenant_id=conversation.tenant_id,
                conversation=conversation,
                inbound_text=inbound_text,
                allow_plain_preferred_name=True,
            )
            first_name = _person_name_words(plain_preferred_name)[0]
            return _wizard_build_service_step_response(
                db,
                conversation=conversation,
                intro_text=(
                    f"Perfeito, {first_name}. Vou te chamar assim. "
                    "Agora me confirma qual atendimento você quer fazer."
                ),
                period=carried_period,
                requested_date=carried_requested_date,
                preferred_service=carried_service or _infer_procedure_type(inbound_text=inbound_text, context=context),
                session_token=latest_session_token,
            )
        inbound_service = _infer_procedure_from_normalized_text(normalized_inbound)
        if (
            carried_service
            and inbound_service
            and _normalize_for_match(carried_service) != _normalize_for_match(inbound_service)
            and (has_scheduling_keywords or force_wizard or _is_explicit_availability_request(inbound_text))
        ):
            return _wizard_build_service_step_response(
                db,
                conversation=conversation,
                intro_text=(
                    f"Entendi que você quer {inbound_service}. "
                    "Para evitar agendamento no serviço errado, confirme o serviço abaixo:"
                ),
                period=period,
                requested_date=requested_date,
                preferred_service=inbound_service,
            )

        should_restart_from_new_intent = (
            latest_mode in {"booking_wizard_confirm", "booking_wizard_time_select", "post_appointment_menu"}
            and not has_interactive_reply
            and not selection_like
            and not has_confirmation_choice
            and (force_wizard or has_scheduling_keywords)
            and (
                _wizard_has_explicit_service_inbound(inbound_text)
                or _is_explicit_availability_request(inbound_text)
                or requested_date is not None
                or period is not None
            )
        )
        if should_restart_from_new_intent:
            return _wizard_build_service_step_response(
                db,
                conversation=conversation,
                intro_text="Perfeito, vamos iniciar um novo agendamento. Me confirma qual atendimento você quer fazer.",
                period=period,
                requested_date=requested_date,
                preferred_service=_infer_procedure_type(inbound_text=inbound_text, context=context),
            )

        if latest_mode in {"booking_cancel_confirm", "booking_reschedule_day_select", "booking_reschedule_time_select", "booking_reschedule_confirm"}:
            appointment_id_raw = str(latest_scheduling.get("appointment_id") or "").strip()
            appointment = None
            if appointment_id_raw:
                try:
                    appointment_uuid = UUID(appointment_id_raw)
                except (TypeError, ValueError):
                    appointment_uuid = None
                if appointment_uuid:
                    appointment = db.scalar(
                        select(Appointment).where(
                            Appointment.id == appointment_uuid,
                            Appointment.tenant_id == conversation.tenant_id,
                            Appointment.patient_id == conversation.patient_id,
                        )
                    )
            if not appointment:
                return _build_appointment_selection_required_response(
                    db,
                    conversation=conversation,
                    config=config,
                    intent_label="alterar o agendamento",
                )

            if latest_mode == "booking_cancel_confirm":
                wants_cancel = selection_token_normalized in {"cancel_yes", "sim", "sim cancelar", "sim, cancelar"}
                keep_current = selection_token_normalized in {"cancel_no", "manter consulta", "nao", "não"}
                if wants_cancel:
                    return _cancel_appointment_from_ai(db, conversation=conversation, appointment=appointment)
                if keep_current:
                    return {
                        "mode": "booking_cancelled",
                        "response_text": "Sem problema, mantive sua consulta como está. Se precisar de mais alguma coisa, me chama por aqui.",
                        "metadata": {"reason": "appointment_cancel_aborted", "appointment_id": str(appointment.id)},
                    }
                return _build_cancel_confirmation_response(
                    db,
                    conversation=conversation,
                    appointment=appointment,
                    config=config,
                    session_token=latest_session_token,
                )

            if latest_mode == "booking_reschedule_day_select":
                if selection_token_normalized in {"reschedule_keep_current", "manter atual"}:
                    return {
                        "mode": "booking_rescheduled",
                        "response_text": "Combinado, mantive sua consulta no horário atual. Se quiser alterar depois, posso te ajudar.",
                        "metadata": {"reason": "reschedule_aborted", "appointment_id": str(appointment.id)},
                    }
                if selection_token_normalized in {"menu_human", "falar atendente", "falar com atendente"}:
                    return {
                        "mode": "menu_human_handoff",
                        "response_text": "Perfeito. Vou te encaminhar para um atendente agora.",
                        "metadata": {
                            "reason": "patient_requested_human",
                            "handoff_required": True,
                            "handoff_reason": "patient_requested_human",
                        },
                    }
                day_choices = latest_scheduling.get("day_choices") if isinstance(latest_scheduling.get("day_choices"), list) else []
                selected_day = _wizard_select_day(selection_token, day_choices, operation_timezone=operation_timezone) or requested_date
                if not selected_day:
                    return _build_reschedule_day_response(
                        db,
                        conversation=conversation,
                        appointment=appointment,
                        config=config,
                        requested_date=carried_requested_date,
                        period=carried_period,
                        operation_timezone=operation_timezone,
                        session_token=latest_session_token,
                    )
                return _build_reschedule_time_response(
                    db,
                    conversation=conversation,
                    appointment=appointment,
                    selected_date=selected_day,
                    config=config,
                    period=carried_period,
                    session_token=latest_session_token,
                )

            if latest_mode == "booking_reschedule_time_select":
                if selection_token_normalized in {"menu_human", "falar atendente", "falar com atendente"}:
                    return {
                        "mode": "menu_human_handoff",
                        "response_text": "Perfeito. Vou te encaminhar para um atendente agora.",
                        "metadata": {
                            "reason": "patient_requested_human",
                            "handoff_required": True,
                            "handoff_reason": "patient_requested_human",
                        },
                    }
                selected_day = _parse_iso_date(latest_scheduling.get("requested_date")) or requested_date
                if selection_token_normalized in {"time_change_day", "trocar dia", "mudar dia"} or not selected_day:
                    return _build_reschedule_day_response(
                        db,
                        conversation=conversation,
                        appointment=appointment,
                        config=config,
                        requested_date=selected_day,
                        period=carried_period,
                        operation_timezone=operation_timezone,
                        session_token=latest_session_token,
                    )
                slot_choices = latest_scheduling.get("slot_choices") if isinstance(latest_scheduling.get("slot_choices"), list) else []
                selected_choice = _wizard_select_time_choice(selection_token, slot_choices)
                explicit_time = _extract_time_choice(inbound_text)
                if not selected_choice and explicit_time:
                    selected_choice = next(
                        (
                            choice
                            for choice in slot_choices
                            if str(choice.get("time") or "").strip() == explicit_time
                        ),
                        None,
                    )
                if not selected_choice:
                    return _build_reschedule_time_response(
                        db,
                        conversation=conversation,
                        appointment=appointment,
                        selected_date=selected_day,
                        config=config,
                        period=carried_period,
                        session_token=latest_session_token,
                    )
                unit = _appointment_unit(db, conversation=conversation, appointment=appointment)
                if not unit:
                    return {
                        "mode": "no_unit_available",
                        "response_text": "Não consegui acessar a unidade desse agendamento agora. Vou encaminhar para a equipe conferir.",
                        "metadata": {"reason": "reschedule_unit_missing", "handoff_required": True},
                    }
                return _build_reschedule_confirm_response(
                    appointment=appointment,
                    unit=unit,
                    selected_date=selected_day,
                    selected_slot_choice=selected_choice,
                    period=carried_period,
                    session_token=latest_session_token,
                )

            if latest_mode == "booking_reschedule_confirm":
                wants_reschedule = selection_token_normalized in {"reschedule_yes", "sim", "sim remarcar", "sim, remarcar", "confirmo"}
                keep_current = selection_token_normalized in {"reschedule_no", "nao", "não", "nao alterar", "não alterar"}
                if keep_current:
                    return {
                        "mode": "booking_rescheduled",
                        "response_text": "Combinado, não alterei sua consulta. Ela continua no horário atual.",
                        "metadata": {"reason": "reschedule_aborted", "appointment_id": str(appointment.id)},
                    }
                if wants_reschedule:
                    selected_slot_choice = latest_scheduling.get("selected_slot") if isinstance(latest_scheduling.get("selected_slot"), dict) else None
                    selected_slot = _wizard_slot_from_choice(selected_slot_choice or {})
                    if selected_slot:
                        return _reschedule_appointment_from_ai(
                            db,
                            conversation=conversation,
                            appointment=appointment,
                            selected_slot=selected_slot,
                        )
                selected_day = _parse_iso_date(latest_scheduling.get("requested_date")) or requested_date
                unit = _appointment_unit(db, conversation=conversation, appointment=appointment)
                selected_slot_choice = latest_scheduling.get("selected_slot") if isinstance(latest_scheduling.get("selected_slot"), dict) else None
                if unit and selected_day and selected_slot_choice:
                    return _build_reschedule_confirm_response(
                        appointment=appointment,
                        unit=unit,
                        selected_date=selected_day,
                        selected_slot_choice=selected_slot_choice,
                        period=carried_period,
                        session_token=latest_session_token,
                    )
                return _build_reschedule_day_response(
                    db,
                    conversation=conversation,
                    appointment=appointment,
                    config=config,
                    requested_date=selected_day,
                    period=carried_period,
                    operation_timezone=operation_timezone,
                    session_token=latest_session_token,
                )

        if latest_mode == "post_appointment_menu":
            if selection_token_normalized in {"post_menu_rebook", "novo agendamento"}:
                return _wizard_build_service_step_response(
                    db,
                    conversation=conversation,
                    intro_text="Perfeito, vamos iniciar um novo agendamento. Me confirma qual atendimento você quer fazer.",
                    period=period,
                    requested_date=requested_date,
                )
            if selection_token_normalized in {"post_menu_human", "falar com atendente"}:
                return {
                    "mode": "menu_human_handoff",
                    "response_text": "Perfeito. Vou te encaminhar para um atendente agora.",
                    "metadata": {
                        "reason": "patient_requested_human",
                        "handoff_required": True,
                        "handoff_reason": "patient_requested_human",
                    },
                }
            if selection_token_normalized in {"post_menu_close", "encerrar conversa"}:
                return _build_booking_close_with_summary_response(
                    procedure_type=str(latest_scheduling.get("procedure_type") or "").strip() or None,
                    unit_name=str(latest_scheduling.get("unit_name") or "").strip() or None,
                    unit_address=str(latest_scheduling.get("unit_address") or "").strip() or None,
                    professional_name=str(latest_scheduling.get("professional_name") or "").strip() or None,
                    selected_slot_label=str(
                        (latest_scheduling.get("selected_slot") or {}).get("label")
                        if isinstance(latest_scheduling.get("selected_slot"), dict)
                        else latest_scheduling.get("selected_slot") or ""
                    ).strip()
                    or None,
                    session_token=latest_session_token,
                )
            if has_scheduling_keywords or force_wizard:
                return _wizard_build_service_step_response(
                    db,
                    conversation=conversation,
                    intro_text="Perfeito. Me confirma qual atendimento você quer fazer para eu continuar.",
                    period=period,
                    requested_date=requested_date,
                    preferred_service=_infer_procedure_type(inbound_text=inbound_text, context=context),
                )
            return _build_booking_post_confirmation_response(
                procedure_type=str(latest_scheduling.get("procedure_type") or "").strip() or None,
                unit_name=str(latest_scheduling.get("unit_name") or "").strip() or None,
                unit_address=str(latest_scheduling.get("unit_address") or "").strip() or None,
                professional_name=str(latest_scheduling.get("professional_name") or "").strip() or None,
                selected_slot_label=str(
                    (latest_scheduling.get("selected_slot") or {}).get("label")
                    if isinstance(latest_scheduling.get("selected_slot"), dict)
                    else latest_scheduling.get("selected_slot") or ""
                ).strip()
                or None,
                session_token=latest_session_token,
            )

        if latest_mode in {
            "welcome_message_start",
            "booking_wizard_support_followup",
            "booking_wizard_suggestion_followup",
            "booking_wizard_complaint_followup",
        }:
            selected_option = welcome_menu_choice
            if not selected_option:
                if has_scheduling_keywords or force_wizard:
                    return _wizard_build_service_step_response(
                        db,
                        conversation=conversation,
                        intro_text="Perfeito. Me confirma qual atendimento você quer fazer para eu continuar.",
                        period=carried_period,
                        requested_date=carried_requested_date,
                        session_token=latest_session_token,
                    )
                # Não trava em menu fixo: texto livre segue para a IA principal analisar.
                return None

            if selected_option == "menu_schedule":
                return _wizard_build_service_step_response(
                    db,
                    conversation=conversation,
                    intro_text="Perfeito, vou te ajudar a agendar. Me confirma qual atendimento você quer fazer.",
                    period=carried_period,
                    requested_date=carried_requested_date,
                    session_token=latest_session_token,
                )

            if selected_option == "menu_services":
                return _build_services_overview_menu_response(
                    db,
                    conversation=conversation,
                    session_token=latest_session_token,
                )

            if selected_option == "menu_support":
                return _build_welcome_menu_followup_buttons_response(
                    mode="booking_wizard_support_followup",
                    header_text="Suporte",
                    body_text=(
                        "Perfeito, vou te ajudar com suporte.\n"
                        "Descreva seu problema em uma mensagem e já encaminho para o time certo."
                    ),
                    reason="support_selected",
                    session_token=latest_session_token,
                )

            if selected_option == "menu_suggestion":
                return _build_welcome_menu_followup_buttons_response(
                    mode="booking_wizard_suggestion_followup",
                    header_text="Sugestões",
                    body_text=(
                        "Ótimo! Quero ouvir sua sugestão.\n"
                        "Pode enviar os detalhes agora e nossa equipe vai analisar."
                    ),
                    reason="suggestion_selected",
                    session_token=latest_session_token,
                )

            if selected_option == "menu_complaint":
                return _build_welcome_menu_followup_buttons_response(
                    mode="booking_wizard_complaint_followup",
                    header_text="Reclamações",
                    body_text=(
                        "Sinto muito por isso. Pode me contar o que aconteceu?\n"
                        "Vou registrar e priorizar seu atendimento."
                    ),
                    reason="complaint_selected",
                    session_token=latest_session_token,
                )

            if selected_option == "menu_human":
                return {
                    "mode": "menu_human_handoff",
                    "response_text": "Perfeito. Vou te encaminhar para um atendente agora.",
                    "metadata": {
                        "reason": "patient_requested_human",
                        "handoff_required": True,
                        "handoff_reason": "patient_requested_human",
                    },
                }

        if latest_mode == "booking_wizard_resume_or_restart":
            saved_state = latest_scheduling.get("saved_state") if isinstance(latest_scheduling.get("saved_state"), dict) else {}
            if not saved_state:
                saved_state = _latest_saved_booking_state(db, conversation=conversation) or {}
            if not saved_state:
                fallback_state = _wizard_state_from_scheduling_metadata(latest_scheduling)
                if fallback_state:
                    saved_state = fallback_state
            has_saved_state = _has_meaningful_saved_state(saved_state)

            if not has_saved_state:
                return _build_conversation_start_welcome_response(
                    intro_text=(
                        "Vamos começar seu atendimento agora.\n"
                        "Escolha uma opção para eu te ajudar da melhor forma:"
                    ),
                    session_token=latest_session_token,
                )

            if selection_token_normalized == "restart_from_beginning" or restart_requested:
                return _wizard_build_service_step_response(
                    db,
                    conversation=conversation,
                    intro_text="Perfeito, vou reiniciar seu atendimento do zero para ficar tudo certinho. Me confirma qual atendimento você quer fazer.",
                    period=period,
                    requested_date=requested_date,
                    preferred_service=_infer_procedure_type(inbound_text=inbound_text, context=context),
                )

            if selection_token_normalized == "resume_saved_step" or resume_requested:
                if not saved_state:
                    return _wizard_build_service_step_response(
                        db,
                        conversation=conversation,
                        intro_text="Vamos seguir por aqui. Me confirma qual atendimento você quer fazer para eu continuar.",
                        period=period,
                        requested_date=requested_date,
                        preferred_service=_infer_procedure_type(inbound_text=inbound_text, context=context),
                    )
                resumed_response = _wizard_resume_saved_step_response(
                    db,
                    conversation=conversation,
                    saved_state=saved_state,
                    config=config,
                    operation_timezone=operation_timezone,
                )
                resumed_metadata = (
                    resumed_response.get("metadata")
                    if isinstance(resumed_response.get("metadata"), dict)
                    else {}
                )
                resumed_metadata["reason"] = "resume_saved_step"
                resumed_response["metadata"] = resumed_metadata
                return resumed_response

            if has_scheduling_keywords or force_wizard:
                resumed_response = _wizard_resume_saved_step_response(
                    db,
                    conversation=conversation,
                    saved_state=saved_state,
                    config=config,
                    operation_timezone=operation_timezone,
                )
                resumed_metadata = (
                    resumed_response.get("metadata")
                    if isinstance(resumed_response.get("metadata"), dict)
                    else {}
                )
                resumed_metadata["reason"] = "resume_saved_step_inferred"
                resumed_response["metadata"] = resumed_metadata
                return resumed_response

            # Texto livre fora de intenção de retomada/reinício deve ir para IA principal.
            return None

        if latest_mode == "booking_wizard_service_select":
            services = latest_scheduling.get("services") if isinstance(latest_scheduling.get("services"), list) else []
            services = [str(item).strip() for item in services if str(item or "").strip()]
            selected_service = _wizard_select_service(selection_token, services)
            if selected_service and _is_service_price_question(inbound_text):
                price_response = _build_service_price_detail_response(
                    db,
                    conversation=conversation,
                    service_name=selected_service,
                    session_token=latest_session_token,
                )
                if price_response:
                    return price_response
            if not selected_service:
                return _wizard_build_service_step_response(
                    db,
                    conversation=conversation,
                    intro_text="Não entendi a opção de serviço. Escolha um item da lista:",
                    period=carried_period,
                    requested_date=carried_requested_date,
                    session_token=latest_session_token,
                )
            return _wizard_build_unit_or_day_step_response(
                db,
                conversation=conversation,
                procedure_type=selected_service,
                period=carried_period,
                requested_date=carried_requested_date,
                operation_timezone=operation_timezone,
                config=config,
                session_token=latest_session_token,
            )

        if latest_mode == "booking_wizard_unit_select":
            if selection_token_normalized in {"unit_change_service", "trocar servico", "trocar serviço"}:
                return _wizard_build_service_step_response(
                    db,
                    conversation=conversation,
                    intro_text="Perfeito. Me confirma qual atendimento você quer fazer.",
                    period=carried_period,
                    requested_date=carried_requested_date,
                )
            if selection_token_normalized in {"menu_human", "falar com atendente"}:
                return {
                    "mode": "menu_human_handoff",
                    "response_text": "Perfeito. Vou te encaminhar para um atendente agora.",
                    "metadata": {
                        "reason": "patient_requested_human",
                        "handoff_required": True,
                        "handoff_reason": "patient_requested_human",
                    },
                }
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
                    session_token=latest_session_token,
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
            if conversation.unit_id != unit.id:
                conversation.unit_id = unit.id
                db.add(conversation)

            selected_service = str(latest_scheduling.get("procedure_type") or "").strip() or "Avaliação inicial"
            return _wizard_build_day_step_response(
                db,
                conversation=conversation,
                unit=unit,
                procedure_type=selected_service,
                period=carried_period,
                requested_date=carried_requested_date,
                operation_timezone=operation_timezone,
                config=config,
                session_token=latest_session_token,
            )

        if latest_mode == "booking_wizard_day_select":
            selected_service = str(latest_scheduling.get("procedure_type") or "").strip() or "Avaliação inicial"
            if selection_token_normalized in {"day_change_service", "trocar servico", "trocar serviço"}:
                return _wizard_build_service_step_response(
                    db,
                    conversation=conversation,
                    intro_text="Perfeito. Me confirma qual atendimento você quer fazer.",
                    period=carried_period,
                    requested_date=carried_requested_date,
                )
            if selection_token_normalized in {"menu_human", "falar com atendente"}:
                return {
                    "mode": "menu_human_handoff",
                    "response_text": "Perfeito. Vou te encaminhar para um atendente agora.",
                    "metadata": {
                        "reason": "patient_requested_human",
                        "handoff_required": True,
                        "handoff_reason": "patient_requested_human",
                    },
                }
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
                    session_token=latest_session_token,
                )

            return _wizard_build_time_step_response(
                db,
                conversation=conversation,
                unit=unit,
                procedure_type=selected_service,
                period=carried_period,
                selected_date=selected_day,
                config=config,
                session_token=latest_session_token,
            )

        if latest_mode == "booking_wizard_time_select":
            selected_service = str(latest_scheduling.get("procedure_type") or "").strip() or "Avaliação inicial"
            if selection_token_normalized in {"time_change_service", "trocar servico", "trocar serviço"}:
                return _wizard_build_service_step_response(
                    db,
                    conversation=conversation,
                    intro_text="Perfeito. Vamos escolher outro serviço:",
                    period=carried_period,
                    requested_date=carried_requested_date,
                )
            if selection_token_normalized in {"menu_human", "falar com atendente"}:
                return {
                    "mode": "menu_human_handoff",
                    "response_text": "Perfeito. Vou te encaminhar para um atendente agora.",
                    "metadata": {
                        "reason": "patient_requested_human",
                        "handoff_required": True,
                        "handoff_reason": "patient_requested_human",
                    },
                }
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
            if selection_token_normalized in {"time_change_day", "trocar dia", "mudar dia"}:
                return _wizard_build_day_step_response(
                    db,
                    conversation=conversation,
                    unit=unit,
                    procedure_type=selected_service,
                    period=carried_period,
                    requested_date=carried_requested_date,
                    operation_timezone=operation_timezone,
                    config=config,
                    session_token=latest_session_token,
                )

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
                    session_token=latest_session_token,
                )

            if requested_date and requested_date != selected_day:
                return _wizard_build_time_step_response(
                    db,
                    conversation=conversation,
                    unit=unit,
                    procedure_type=selected_service,
                    period=carried_period,
                    selected_date=requested_date,
                    config=config,
                    session_token=latest_session_token,
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
                    session_token=latest_session_token,
                )

            return _wizard_build_confirm_step_response(
                procedure_type=selected_service,
                unit=unit,
                selected_date=selected_day,
                period=carried_period,
                selected_slot_choice=selected_choice,
                session_token=latest_session_token,
            )

        if latest_mode == "no_slots_general" and latest_step in {"day", "time"}:
            selected_service = str(latest_scheduling.get("procedure_type") or "").strip() or "Avaliação inicial"
            if selection_token_normalized in {"day_change_service", "time_change_service", "trocar servico", "trocar serviço"}:
                return _wizard_build_service_step_response(
                    db,
                    conversation=conversation,
                    intro_text="Perfeito. Vamos escolher outro serviço:",
                    period=carried_period,
                    requested_date=carried_requested_date,
                    session_token=latest_session_token,
                )
            if selection_token_normalized in {"menu_human", "falar com atendente"}:
                return {
                    "mode": "menu_human_handoff",
                    "response_text": "Perfeito. Vou te encaminhar para um atendente agora.",
                    "metadata": {
                        "reason": "patient_requested_human",
                        "handoff_required": True,
                        "handoff_reason": "patient_requested_human",
                    },
                }

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
            ) if unit_id else None
            if not unit:
                return {
                    "mode": "no_unit_available",
                    "response_text": "Não consegui acessar essa clínica agora. Pode escolher outra opção?",
                    "metadata": {"reason": "no_unit_available"},
                }

            latest_requested_day = _parse_iso_date(latest_scheduling.get("requested_date"))
            if latest_step == "time" and requested_date and requested_date != latest_requested_day:
                return _wizard_build_time_step_response(
                    db,
                    conversation=conversation,
                    unit=unit,
                    procedure_type=selected_service,
                    period=carried_period,
                    selected_date=requested_date,
                    config=config,
                    session_token=latest_session_token,
                )

            return _wizard_build_day_step_response(
                db,
                conversation=conversation,
                unit=unit,
                procedure_type=selected_service,
                period=carried_period,
                requested_date=requested_date or latest_requested_day or carried_requested_date,
                operation_timezone=operation_timezone,
                config=config,
                session_token=latest_session_token,
            )

        if latest_mode == "booking_wizard_confirm":
            confirmation_choice = _wizard_parse_confirmation_choice(selection_token)
            confirmation_action = _wizard_parse_confirmation_action(selection_token)
            selected_service = str(latest_scheduling.get("procedure_type") or "").strip() or "Avaliação inicial"
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
                    intro_text="Vou reiniciar o agendamento para ficar tudo certinho. Me confirma qual atendimento você quer fazer.",
                    period=carried_period,
                    requested_date=carried_requested_date,
                    session_token=latest_session_token,
                )

            if confirmation_action == "human":
                return {
                    "mode": "menu_human_handoff",
                    "response_text": "Perfeito. Vou te encaminhar para um atendente agora.",
                    "metadata": {
                        "reason": "patient_requested_human",
                        "handoff_required": True,
                        "handoff_reason": "patient_requested_human",
                    },
                }
            if confirmation_action == "change_service":
                return _wizard_build_service_step_response(
                    db,
                    conversation=conversation,
                    intro_text="Perfeito. Vamos escolher outro serviço:",
                    period=carried_period,
                    requested_date=carried_requested_date,
                )
            if confirmation_action in {"change_time", "change_day"}:
                return _wizard_build_time_step_response(
                    db,
                    conversation=conversation,
                    unit=unit,
                    procedure_type=selected_service,
                    period=carried_period,
                    selected_date=selected_day,
                    config=config,
                    session_token=latest_session_token,
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
                        session_token=latest_session_token,
                    )
                professional_id_raw = selected_slot.get("professional_id")
                professional_id = None
                if professional_id_raw:
                    try:
                        professional_id = UUID(str(professional_id_raw))
                    except (TypeError, ValueError):
                        professional_id = None
                if professional_id:
                    conflict = find_professional_conflict(
                        db,
                        tenant_id=conversation.tenant_id,
                        professional_id=professional_id,
                        starts_at=selected_slot["starts_at_utc"],
                        ends_at=selected_slot["ends_at_utc"],
                    )
                    if conflict:
                        retry_response = _wizard_build_time_step_response(
                            db,
                            conversation=conversation,
                            unit=unit,
                            procedure_type=selected_service,
                            period=carried_period,
                            selected_date=selected_day,
                            config=config,
                            session_token=latest_session_token,
                        )
                        retry_metadata = (
                            retry_response.get("metadata")
                            if isinstance(retry_response.get("metadata"), dict)
                            else {}
                        )
                        retry_metadata["reason"] = "selected_slot_no_longer_available"
                        retry_metadata["body_text"] = (
                            "Esse horário acabou de ser reservado. Selecione outro horário."
                        )
                        retry_response["metadata"] = retry_metadata
                        retry_response["response_text"] = (
                            "Esse horário acabou de ser reservado. Vamos escolher outro horário."
                        )
                        return retry_response
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
                    session_token=latest_session_token,
                )

            return _wizard_build_confirm_step_response(
                procedure_type=selected_service,
                unit=unit,
                selected_date=selected_day,
                period=carried_period,
                selected_slot_choice=selected_slot_choice,
                session_token=latest_session_token,
            )

        if latest_mode == "booking_request_cpf_after_booking":
            if selection_token_normalized in {"menu_human", "falar com atendente"}:
                return {
                    "mode": "menu_human_handoff",
                    "response_text": "Perfeito. Vou te encaminhar para um atendente agora.",
                    "metadata": {
                        "reason": "patient_requested_human",
                        "handoff_required": True,
                        "handoff_reason": "patient_requested_human",
                    },
                }
            procedure_type = str(latest_scheduling.get("procedure_type") or "").strip()
            unit_name = str(latest_scheduling.get("unit_name") or "").strip()
            unit_address = str(latest_scheduling.get("unit_address") or "").strip() or None
            professional_name = str(latest_scheduling.get("professional_name") or "").strip() or None
            selected_slot = latest_scheduling.get("selected_slot") if isinstance(latest_scheduling.get("selected_slot"), dict) else {}
            selected_slot_label = str(selected_slot.get("label") or latest_scheduling.get("selected_slot") or "").strip()
            registration_retry_sent = bool(latest_scheduling.get("registration_retry_sent"))
            if _registration_skip_requested(inbound_text):
                return _build_booking_post_confirmation_response(
                    procedure_type=procedure_type,
                    unit_name=unit_name,
                    selected_slot_label=selected_slot_label,
                    unit_address=unit_address,
                    professional_name=professional_name,
                    session_token=latest_session_token,
                )

            _capture_patient_registration_from_inbound(
                db,
                conversation=conversation,
                inbound_text=inbound_text,
                allow_loose_name=True,
                allow_unlabeled_birth_date=True,
            )
            missing_fields = _missing_patient_registration_fields(db, conversation=conversation)
            if not missing_fields:
                return _build_booking_post_confirmation_response(
                    procedure_type=procedure_type,
                    unit_name=unit_name,
                    selected_slot_label=selected_slot_label,
                    unit_address=unit_address,
                    professional_name=professional_name,
                    session_token=latest_session_token,
                )

            if registration_retry_sent:
                return _build_booking_registration_deferred_response(
                    procedure_type=procedure_type,
                    unit_name=unit_name,
                    selected_slot_label=selected_slot_label,
                    unit_address=unit_address,
                    professional_name=professional_name,
                    session_token=latest_session_token,
                )

            return _build_booking_cpf_request_response(
                procedure_type=procedure_type,
                unit_name=unit_name,
                selected_slot_label=selected_slot_label,
                unit_address=unit_address,
                professional_name=professional_name,
                session_token=latest_session_token,
                retry=True,
                missing_fields=missing_fields,
                registration_retry_sent=True,
            )

        if latest_mode in {"booking_post_confirmation_options", "booking_post_information_followup", "post_appointment_menu"}:
            procedure_type = str(latest_scheduling.get("procedure_type") or "").strip()
            unit_name = str(latest_scheduling.get("unit_name") or "").strip()
            unit_address = str(latest_scheduling.get("unit_address") or "").strip() or None
            professional_name = str(latest_scheduling.get("professional_name") or "").strip() or None
            selected_slot = latest_scheduling.get("selected_slot") if isinstance(latest_scheduling.get("selected_slot"), dict) else {}
            selected_slot_label = str(selected_slot.get("label") or latest_scheduling.get("selected_slot") or "").strip()

            if selection_token_normalized in {"post_info_close", "post_menu_close"} or _lookup_pattern(inbound_text, CLOSE_CONVERSATION_PATTERNS):
                return _build_booking_close_with_summary_response(
                    procedure_type=procedure_type,
                    unit_name=unit_name,
                    selected_slot_label=selected_slot_label,
                    unit_address=unit_address,
                    professional_name=professional_name,
                    session_token=latest_session_token,
                )

            if selection_token_normalized in {"post_info_more"} or "mais inform" in normalized_inbound:
                return _build_booking_post_information_followup_response(
                    procedure_type=procedure_type,
                    unit_name=unit_name,
                    selected_slot_label=selected_slot_label,
                    unit_address=unit_address,
                    professional_name=professional_name,
                    session_token=latest_session_token,
                )

            if selection_token_normalized in {"menu_human", "post_menu_human"}:
                return {
                    "mode": "menu_human_handoff",
                    "response_text": "Perfeito. Vou te encaminhar para um atendente agora.",
                    "metadata": {
                        "reason": "patient_requested_human",
                        "handoff_required": True,
                        "handoff_reason": "patient_requested_human",
                    },
                }

            if has_scheduling_keywords or force_wizard or selection_token_normalized in {"post_menu_rebook", "novo agendamento"}:
                return _wizard_build_service_step_response(
                    db,
                    conversation=conversation,
                    intro_text="Perfeito, vamos iniciar um novo agendamento. Me confirma qual atendimento você quer fazer.",
                    period=period,
                    requested_date=requested_date,
                    preferred_service=_infer_procedure_type(inbound_text=inbound_text, context=context),
                )

            return _build_booking_post_confirmation_response(
                procedure_type=procedure_type,
                unit_name=unit_name,
                selected_slot_label=selected_slot_label,
                unit_address=unit_address,
                professional_name=professional_name,
                session_token=latest_session_token,
            )

    if not has_scheduling_keywords and not force_wizard:
        if selection_token_normalized in {"post_menu_rebook", "novo agendamento"}:
            return _wizard_build_service_step_response(
                db,
                conversation=conversation,
                intro_text="Perfeito, vamos iniciar um novo agendamento. Me confirma qual atendimento você quer fazer.",
                period=period,
                requested_date=requested_date,
            )
        if selection_token_normalized in {"post_menu_human", "falar com atendente"}:
            return {
                "mode": "menu_human_handoff",
                "response_text": "Perfeito. Vou te encaminhar para um atendente agora.",
                "metadata": {
                    "reason": "patient_requested_human",
                    "handoff_required": True,
                    "handoff_reason": "patient_requested_human",
                },
            }
        if selection_token_normalized in {"post_menu_close", "post_info_close", "encerrar conversa"}:
            return _build_booking_close_with_summary_response(
                procedure_type=None,
                unit_name=None,
                selected_slot_label=None,
                session_token=None,
            )
        return None
    if _extract_option_index_choice(inbound_text) is not None or _extract_time_choice(inbound_text) is not None:
        return None

    has_explicit_service = _wizard_has_explicit_service_inbound(inbound_text)
    explicit_availability_request = _is_explicit_availability_request(inbound_text)
    should_open_wizard = bool(
        force_wizard
        or has_scheduling_keywords
        or has_explicit_service
        or explicit_availability_request
        or requested_date
        or period
    )
    if not should_open_wizard:
        return None

    preferred_service = (
        _infer_procedure_type(inbound_text=inbound_text, context=context)
        if (has_explicit_service or explicit_availability_request or requested_date or period)
        else None
    )
    inferred_unit, _ = _resolve_unit_for_action_preview(
        db,
        tenant_id=conversation.tenant_id,
        action_payload={
            "unit_name": inbound_text,
            "clinic_name": inbound_text,
        },
    )
    if preferred_service and inferred_unit:
        return _wizard_build_day_step_response(
            db,
            conversation=conversation,
            unit=inferred_unit,
            procedure_type=preferred_service,
            period=period,
            requested_date=requested_date,
            operation_timezone=_resolve_operation_timezone(config),
            config=config,
        )
    if preferred_service:
        return _wizard_build_unit_step_response(
            db,
            conversation=conversation,
            procedure_type=preferred_service,
            period=period,
            requested_date=requested_date,
        )
    intro_text = None
    if explicit_availability_request or requested_date:
        intro_text = (
            "Perfeito! Para te mostrar horários certos e evitar erro no agendamento, "
            "vamos organizar passo a passo. Primeiro, me confirma qual atendimento você quer fazer."
        )
    return _wizard_build_service_step_response(
        db,
        conversation=conversation,
        intro_text=intro_text,
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

    output = _dedupe_repeated_leading_text_block(output)

    # Normaliza listas numeradas e separadores visuais para leitura no WhatsApp.
    output = output.replace(" | ", "\n")
    output = re.sub(r"\s+(?=\d+\)\s)", "\n", output)
    output = re.sub(r"\n{3,}", "\n\n", output)

    output = _remove_excessive_name_mentions(
        output,
        known_names=_known_contact_names(db, conversation=conversation),
    )

    # Reduz bordoes repetitivos no inicio da mensagem para soar mais natural no WhatsApp.
    output = re.sub(
        r"^(Perfeito|Ótimo|Certo|Combinado|Claro|Entendi)[!,.:\s-]+(?=(Perfeito|Ótimo|Certo|Combinado|Claro|Entendi)\b)",
        "",
        output,
        flags=re.IGNORECASE,
    ).strip()

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


def _python_weekday_to_ui_weekday(weekday: int) -> int:
    # Python: segunda=0. UI/profissionais: domingo=0.
    return (weekday + 1) % 7


def _professional_matches_procedure(professional: Professional, procedure_type: str) -> bool:
    return professional_assignment_priority(professional, procedure_type) < 3


def _parse_professional_working_days(professional: Professional, fallback_days: list[int]) -> list[int]:
    if isinstance(professional.working_days, list):
        days = sorted({int(day) for day in professional.working_days if isinstance(day, int) and 0 <= int(day) <= 6})
        if days:
            return days
    return sorted({_python_weekday_to_ui_weekday(day) for day in fallback_days if 0 <= int(day) <= 6})


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
    service_catalog: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    timezone = _resolve_operation_timezone(config)
    now_utc = datetime.now(UTC)
    now_local = now_utc.astimezone(timezone)
    effective_service_catalog = service_catalog or get_service_duration_catalog(db, tenant_id=tenant_id)
    requested_slot_duration = resolve_service_duration_minutes(
        procedure_type=procedure_type,
        service_catalog=effective_service_catalog,
        default_minutes=slot_duration_minutes,
    )

    business_hours = config.get("business_hours") or {}
    weekdays = [int(day) for day in (business_hours.get("weekdays") or [0, 1, 2, 3, 4]) if isinstance(day, int)]
    if not weekdays:
        weekdays = [0, 1, 2, 3, 4]

    start_h, start_m = _parse_hhmm(str(business_hours.get("start") or "08:00"))
    end_h, end_m = _parse_hhmm(str(business_hours.get("end") or "18:00"))
    base_start = start_h * 60 + start_m
    base_end = end_h * 60 + end_m
    if base_end <= base_start or (base_end - base_start) < requested_slot_duration:
        logger.warning(
            "ai_autoresponder.invalid_business_hours_window",
            tenant_id=str(tenant_id),
            unit_id=str(unit_id),
            configured_start=str(business_hours.get("start") or ""),
            configured_end=str(business_hours.get("end") or ""),
            slot_duration_minutes=requested_slot_duration,
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
    busy_load_by_professional: dict[str, int] = {}
    for item in busy_rows:
        start_at = item.starts_at
        if not start_at:
            continue
        end_at = resolve_appointment_end(
            starts_at=start_at,
            ends_at=item.ends_at,
            procedure_type=item.procedure_type,
            service_catalog=effective_service_catalog,
            default_minutes=requested_slot_duration,
        )
        key = str(item.professional_id) if item.professional_id else "__unit__"
        busy_by_professional.setdefault(key, []).append((start_at, end_at))
        if item.professional_id:
            busy_load_by_professional[key] = busy_load_by_professional.get(key, 0) + 1

    all_professionals = list_active_professionals_for_unit(
        db,
        tenant_id=tenant_id,
        unit_id=unit_id,
    )
    professionals = eligible_professionals_for_procedure(all_professionals, procedure_type)

    if not professionals and all_professionals:
        logger.info(
            "ai_autoresponder.no_professional_mapped_for_procedure",
            tenant_id=str(tenant_id),
            unit_id=str(unit_id),
            procedure_type=procedure_type,
            professionals_count=len(all_professionals),
        )

    if professionals:
        professionals = sorted(
            professionals,
            key=lambda item: (
                professional_assignment_priority(item, procedure_type),
                busy_load_by_professional.get(str(item.id), 0),
                str(item.full_name or "").lower(),
                str(item.id),
            ),
        )
    elif not all_professionals:
        logger.info(
            "ai_autoresponder.no_active_professionals_for_unit",
            tenant_id=str(tenant_id),
            unit_id=str(unit_id),
            procedure_type=procedure_type,
        )
        return []
    else:
        return []

    def _collect_slots_for_duration(*, duration_minutes: int) -> list[dict[str, Any]]:
        raw_slots: list[dict[str, Any]] = []
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

            for day_offset in range(0, 21):
                day_local = (now_local + timedelta(days=day_offset)).date()
                if requested_date and day_local != requested_date:
                    continue
                if _python_weekday_to_ui_weekday(day_local.weekday()) not in professional_days:
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
                        raw_slots.append(
                            {
                                "starts_at_utc": slot_start_utc,
                                "ends_at_utc": slot_end_utc,
                                "starts_at_local": slot_local,
                                "label": _format_slot_pt(slot_local),
                                "professional_id": getattr(professional, "id", None),
                                "professional_name": professional.full_name,
                                "assignment_priority": professional_assignment_priority(professional, procedure_type)
                                if getattr(professional, "id", None)
                                else 99,
                                "professional_load": busy_load_by_professional.get(professional_key, 0),
                            }
                        )

                    minute_pointer += 30

        raw_slots.sort(
            key=lambda item: (
                item["starts_at_utc"],
                int(item.get("assignment_priority") or 99),
                int(item.get("professional_load") or 0),
                str(item.get("professional_name") or "").lower(),
            )
        )
        grouped_slots: list[dict[str, Any]] = []
        grouped_index_by_start: dict[str, int] = {}
        for item in raw_slots:
            start_key = item["starts_at_utc"].isoformat()
            current_index = grouped_index_by_start.get(start_key)
            if current_index is None:
                grouped_slots.append(
                    {
                        **item,
                        "available_professionals_count": 1,
                        "available_professionals": [
                            str(item.get("professional_name") or "").strip()
                        ]
                        if str(item.get("professional_name") or "").strip()
                        else [],
                    }
                )
                grouped_index_by_start[start_key] = len(grouped_slots) - 1
                continue

            current_item = grouped_slots[current_index]
            current_item["available_professionals_count"] = int(current_item.get("available_professionals_count") or 0) + 1
            professional_name = str(item.get("professional_name") or "").strip()
            if professional_name:
                existing_names = current_item.get("available_professionals")
                if not isinstance(existing_names, list):
                    existing_names = []
                    current_item["available_professionals"] = existing_names
                if professional_name not in existing_names:
                    existing_names.append(professional_name)
        return grouped_slots

    duration_candidates = [requested_slot_duration]

    for duration in duration_candidates:
        slots = _collect_slots_for_duration(duration_minutes=duration)
        if slots:
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


def _procedure_mentions_in_normalized_text(normalized_text: str) -> list[str]:
    normalized = _normalize_for_match(normalized_text or "")
    if not normalized:
        return []

    mentions: list[str] = []

    def _add(label: str) -> None:
        if label not in mentions:
            mentions.append(label)

    if "limpeza" in normalized or "profilax" in normalized:
        _add("Limpeza clínica")

    # Aceita variações comuns e erros de digitação de "clareamento".
    if (
        "clareamento" in normalized
        or "claramento" in normalized
        or "claremento" in normalized
        or "clareamnto" in normalized
        or "clariamento" in normalized
        or "clarea mento" in normalized
        or "clarear" in normalized
        or "branquear" in normalized
        or "branqueamento" in normalized
        or ("claramente" in normalized and any(token in normalized for token in ("dental", "dentario", "dentária", "dente")))
    ):
        _add("Clareamento dental")

    if "lente" in normalized:
        _add("Instalação de lentes")
    if "implante" in normalized:
        _add("Implante dentário")
    if "ortodont" in normalized:
        _add("Avaliação ortodôntica")

    return mentions


def _infer_procedure_from_normalized_text(normalized_text: str) -> str | None:
    mentions = _procedure_mentions_in_normalized_text(normalized_text)
    if not mentions:
        return None
    return mentions[0]


def _infer_procedure_from_context(context: str) -> str | None:
    # Preferimos o sinal mais recente e inequívoco para evitar "herdar" serviço antigo.
    lines = [line.strip() for line in str(context or "").splitlines() if line.strip()]
    recent_lines = lines[-8:]
    for line in reversed(recent_lines):
        normalized_line = _normalize_for_match(line)
        # Evita inferir serviço a partir de mensagens de catálogo amplo.
        if any(token in normalized_line for token in ("oferecemos", "servicos", "procedimentos", "tratamentos")):
            continue
        mentions = _procedure_mentions_in_normalized_text(line)
        if len(mentions) == 1:
            return mentions[0]

    context_mentions = _procedure_mentions_in_normalized_text("\n".join(recent_lines))
    if len(context_mentions) == 1:
        return context_mentions[0]
    return None


def _infer_procedure_type(*, inbound_text: str, context: str) -> str:
    normalized_inbound = _normalize_for_match(inbound_text)

    # Prioriza sempre o que o paciente pediu na mensagem atual.
    inbound_inference = _infer_procedure_from_normalized_text(normalized_inbound)
    if inbound_inference:
        return inbound_inference

    # Só usa contexto quando a mensagem atual é curta/ambígua.
    inbound_word_count = len([chunk for chunk in normalized_inbound.split() if chunk])
    if inbound_word_count <= 6:
        context_inference = _infer_procedure_from_context(context)
        if context_inference:
            return context_inference

    return "Avaliação inicial"


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
    latest_messages = _recent_ai_outbound_messages(db, conversation=conversation, limit=1)
    for message in latest_messages:
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


def _resolve_selected_slot_professional(
    db: Session,
    *,
    tenant_id: UUID,
    unit_id: UUID,
    procedure_type: str,
    selected_slot: dict[str, Any],
    exclude_appointment_id: UUID | None = None,
) -> tuple[UUID | None, str | None]:
    selected_professional_id = None
    selected_professional_name = str(selected_slot.get("professional_name") or "").strip() or None
    selected_professional_raw = selected_slot.get("professional_id")
    if selected_professional_raw:
        try:
            selected_professional_id = UUID(str(selected_professional_raw))
        except (TypeError, ValueError):
            selected_professional_id = None

    if selected_professional_id:
        conflict = find_professional_conflict(
            db,
            tenant_id=tenant_id,
            professional_id=selected_professional_id,
            starts_at=selected_slot["starts_at_utc"],
            ends_at=selected_slot["ends_at_utc"],
            exclude_appointment_id=exclude_appointment_id,
        )
        if not conflict:
            return selected_professional_id, selected_professional_name

    fallback_professional = pick_best_available_professional(
        db,
        tenant_id=tenant_id,
        unit_id=unit_id,
        procedure_type=procedure_type,
        starts_at=selected_slot["starts_at_utc"],
        ends_at=selected_slot["ends_at_utc"],
        exclude_appointment_id=exclude_appointment_id,
    )
    if not fallback_professional:
        return None, None
    return fallback_professional.id, str(fallback_professional.full_name or "").strip() or None


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

    unit_address = _format_unit_address(unit.address)
    record_link_flow_booking_attempt_started(
        db,
        conversation=conversation,
        payload={
            "source": "ai_autoresponder",
            "unit_id": str(unit.id),
            "starts_at": selected_slot["starts_at_utc"].isoformat(),
            "procedure_type": procedure_type,
        },
    )

    existing = find_duplicate_active_patient_appointment(
        db,
        tenant_id=conversation.tenant_id,
        patient_id=conversation.patient_id,
        unit_id=unit.id,
        starts_at=selected_slot["starts_at_utc"],
        lock=True,
    )
    if existing:
        record_link_flow_appointment_result(
            db,
            conversation=conversation,
            appointment_id=existing.id,
            event_name="appointment_duplicate_detected",
            payload={
                "source": "ai_autoresponder",
                "unit_id": str(unit.id),
                "starts_at": existing.starts_at.isoformat(),
            },
        )
        cpf_already_saved = bool(_patient_saved_cpf(db, conversation=conversation))
        missing_registration_fields = _missing_patient_registration_fields(db, conversation=conversation)
        return {
            "mode": "appointment_already_created",
            "response_text": (
                "Perfeito, esse horário já está confirmado na sua agenda.\n"
                f"• Serviço: {existing.procedure_type or procedure_type}\n"
                f"• Horário: {selected_slot['label']}\n"
                f"• Unidade: {unit.name}"
            ),
            "metadata": {
                "appointment_id": str(existing.id),
                "procedure_type": existing.procedure_type or procedure_type,
                "period": period,
                "selected_slot": selected_slot["label"],
                "starts_at_utc": existing.starts_at.isoformat(),
                "unit_id": str(unit.id),
                "unit_name": unit.name,
                "unit_address": unit_address,
                "requested_date": requested_date.isoformat() if requested_date else None,
                "professional_id": (
                    str(selected_slot.get("professional_id"))
                    if selected_slot.get("professional_id")
                    else None
                ),
                "professional_name": selected_slot.get("professional_name"),
                "cpf_already_saved": cpf_already_saved,
                "missing_registration_fields": missing_registration_fields,
                "next_followup_mode": (
                    "booking_post_confirmation_options"
                    if not missing_registration_fields
                    else "booking_request_cpf_after_booking"
                ),
            },
        }

    selected_professional_id, selected_professional_name = _resolve_selected_slot_professional(
        db,
        tenant_id=conversation.tenant_id,
        unit_id=unit.id,
        procedure_type=procedure_type,
        selected_slot=selected_slot,
    )
    if not selected_professional_id:
        return {
            "mode": "selected_slot_no_longer_available",
            "response_text": (
                "Esse horário acabou de ser reservado e não está mais disponível.\n"
                "Posso te mostrar outras opções."
            ),
            "metadata": {
                "reason": "selected_slot_no_longer_available",
                "period": period,
                "procedure_type": procedure_type,
                "unit_id": str(unit.id),
                "requested_date": requested_date.isoformat() if requested_date else None,
            },
        }
    selected_slot = {
        **selected_slot,
        "professional_id": str(selected_professional_id),
        "professional_name": selected_professional_name,
    }
    selected_professional = db.scalar(
        select(Professional).where(
            Professional.id == selected_professional_id,
            Professional.tenant_id == conversation.tenant_id,
        )
    )
    ensure_appointment_within_working_days(
        starts_at=selected_slot["starts_at_utc"],
        professional=selected_professional,
    )

    appointment = Appointment(
        tenant_id=conversation.tenant_id,
        patient_id=conversation.patient_id,
        unit_id=unit.id,
        professional_id=selected_professional_id,
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
    record_link_flow_appointment_result(
        db,
        conversation=conversation,
        appointment_id=appointment.id,
        event_name="appointment_created",
        payload={
            "source": "ai_autoresponder",
            "unit_id": str(unit.id),
            "starts_at": appointment.starts_at.isoformat(),
        },
    )

    cpf_already_saved = bool(_patient_saved_cpf(db, conversation=conversation))
    missing_registration_fields = _missing_patient_registration_fields(db, conversation=conversation)
    return {
        "mode": "appointment_created",
        "response_text": (
            "Excelente, seu horário já ficou reservado com sucesso.\n"
            f"• Serviço: {procedure_type}\n"
            f"• Horário: {selected_slot['label']}\n"
            f"• Unidade: {unit.name}"
            + (
                f"\n• Profissional: {selected_slot['professional_name']}"
                if selected_slot.get("professional_name")
                else ""
            )
            + "\nVou te orientar no próximo passo para deixar tudo pronto."
        ),
        "metadata": {
            "appointment_id": str(appointment.id),
            "procedure_type": procedure_type,
            "period": period,
            "selected_slot": selected_slot["label"],
            "starts_at_utc": appointment.starts_at.isoformat(),
            "unit_id": str(unit.id),
            "unit_name": unit.name,
            "unit_address": unit_address,
            "requested_date": requested_date.isoformat() if requested_date else None,
            "professional_id": (
                str(selected_slot.get("professional_id"))
                if selected_slot.get("professional_id")
                else None
            ),
            "professional_name": selected_slot.get("professional_name"),
            "cpf_already_saved": cpf_already_saved,
            "missing_registration_fields": missing_registration_fields,
            "next_followup_mode": (
                "booking_post_confirmation_options"
                if not missing_registration_fields
                else "booking_request_cpf_after_booking"
            ),
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
    interactive_reply_id = _normalize_for_match(_wizard_extract_reply_id(inbound_payload))
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
    anchor_session_token = str(anchor_scheduling.get("session_token") or "").strip() or None

    anchor_requested_date: date | None = None
    anchor_requested_date_raw = anchor_scheduling.get("requested_date")
    if isinstance(anchor_requested_date_raw, str) and anchor_requested_date_raw.strip():
        try:
            anchor_requested_date = date.fromisoformat(anchor_requested_date_raw.strip()[:10])
        except ValueError:
            anchor_requested_date = None

    anchor_period_raw = str(anchor_scheduling.get("period") or "").strip().lower()
    anchor_period = anchor_period_raw if anchor_period_raw in {"morning", "afternoon", "evening"} else None

    if interactive_reply_id in {"slot_change_day", "time_change_day"}:
        return _wizard_build_day_step_response(
            db,
            conversation=conversation,
            unit=unit,
            procedure_type=anchor_procedure_type,
            period=period or anchor_period,
            requested_date=requested_date,
            operation_timezone=operation_timezone,
            config=config,
            session_token=anchor_session_token,
        )
    if interactive_reply_id in {"slot_change_service", "time_change_service"}:
        return _wizard_build_service_step_response(
            db,
            conversation=conversation,
            intro_text="Perfeito. Vamos escolher outro serviço:",
            period=period or anchor_period,
            requested_date=requested_date,
        )
    if interactive_reply_id in {"menu_human", "slot_handoff"}:
        return {
            "mode": "menu_human_handoff",
            "response_text": "Perfeito. Vou te encaminhar para um atendente agora.",
            "metadata": {
                "reason": "patient_requested_human",
                "handoff_required": True,
                "handoff_reason": "patient_requested_human",
            },
        }

    selected_date = (
        requested_date
        or anchor_requested_date
        or _extract_requested_date_from_text(text=anchor_text, timezone=operation_timezone)
        or _extract_requested_date_from_text(text=latest_text, timezone=operation_timezone)
    )
    selected_period = period or anchor_period or _detect_period_preference(anchor_text) or _detect_period_preference(latest_text)
    slot_limit = 12 if selected_date else 6
    service_catalog = get_service_duration_catalog(db, tenant_id=conversation.tenant_id)
    slot_duration_minutes = _resolve_slot_duration_minutes(
        db,
        tenant_id=conversation.tenant_id,
        procedure_type=anchor_procedure_type,
        service_catalog=service_catalog,
    )
    slots = _list_available_slots(
        db,
        tenant_id=conversation.tenant_id,
        unit_id=unit.id,
        config=config,
        procedure_type=anchor_procedure_type,
        period=selected_period,
        requested_date=selected_date,
        max_slots=slot_limit,
        slot_duration_minutes=slot_duration_minutes,
        service_catalog=service_catalog,
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

    slot_choice = {
        "id": f"time_{chosen_slot['starts_at_local'].strftime('%H%M')}",
        "label": chosen_slot["label"],
        "starts_at_utc": chosen_slot["starts_at_utc"].isoformat(),
        "ends_at_utc": chosen_slot["ends_at_utc"].isoformat(),
        "starts_at_local": chosen_slot["starts_at_local"].isoformat(),
        "professional_id": (
            str(chosen_slot.get("professional_id"))
            if chosen_slot.get("professional_id")
            else None
        ),
        "professional_name": chosen_slot.get("professional_name"),
        "time": chosen_slot["starts_at_local"].strftime("%H:%M"),
    }
    confirm_date = selected_date or chosen_slot["starts_at_local"].date()
    return _wizard_build_confirm_step_response(
        procedure_type=anchor_procedure_type,
        unit=unit,
        selected_date=confirm_date,
        period=selected_period,
        selected_slot_choice=slot_choice,
        session_token=anchor_session_token,
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

    if _is_service_catalog_request(inbound_text):
        preferred_service = _infer_procedure_type(inbound_text=inbound_text, context=context)
        if preferred_service == "Avaliação inicial":
            preferred_service = None
        return _wizard_build_service_step_response(
            db,
            conversation=conversation,
            intro_text="Perfeito. Me confirma qual atendimento você quer fazer para eu continuar.",
            period=None,
            requested_date=None,
            preferred_service=preferred_service,
        )

    inbound_payload = inbound_message.payload if isinstance(inbound_message.payload, dict) else {}
    period = _detect_period_preference(inbound_text)
    explicit_availability_request = _is_explicit_availability_request(inbound_text) or _is_followup_availability_request(
        inbound_text=inbound_text,
        context=context,
    )
    normalized_inbound = _normalize_for_match(inbound_text)
    inbound_service_hint = _infer_procedure_from_normalized_text(normalized_inbound)
    context_service_hint = _infer_procedure_from_context(context)
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
    if (
        explicit_availability_request
        and not has_followup_confirmation
        and not inbound_service_hint
        and not context_service_hint
    ):
        return _wizard_build_service_step_response(
            db,
            conversation=conversation,
            intro_text="Para não te mostrar uma opção errada, me confirma qual atendimento você quer fazer.",
            period=period,
            requested_date=_extract_requested_date_from_text(text=inbound_text, timezone=_resolve_operation_timezone(config)),
        )

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

    procedure_type = (
        inbound_service_hint
        or context_service_hint
        or _infer_procedure_type(inbound_text=inbound_text, context=context)
    )
    operation_timezone = _resolve_operation_timezone(config)
    requested_date = _extract_requested_date_from_text(text=inbound_text, timezone=operation_timezone)
    day_availability_request = _is_day_availability_request(inbound_text)
    requested_date_label = requested_date.strftime("%d/%m") if requested_date else None
    slot_limit = 12 if requested_date else 3
    service_catalog = get_service_duration_catalog(db, tenant_id=conversation.tenant_id)
    slot_duration_minutes = _resolve_slot_duration_minutes(
        db,
        tenant_id=conversation.tenant_id,
        procedure_type=procedure_type,
        service_catalog=service_catalog,
    )

    if day_availability_request and requested_date is None and not has_followup_confirmation:
        return _wizard_build_day_step_response(
            db,
            conversation=conversation,
            unit=unit,
            procedure_type=procedure_type,
            period=period,
            requested_date=None,
            operation_timezone=operation_timezone,
            config=config,
        )

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
            slot_duration_minutes=slot_duration_minutes,
            service_catalog=service_catalog,
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
                slot_duration_minutes=slot_duration_minutes,
                service_catalog=service_catalog,
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
        slot_duration_minutes=slot_duration_minutes,
        service_catalog=service_catalog,
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


def _next_action_from_scheduling_response(scheduling_response: dict[str, Any]) -> str:
    mode = str(scheduling_response.get("mode") or "").strip()
    metadata = scheduling_response.get("metadata") if isinstance(scheduling_response.get("metadata"), dict) else {}

    if bool(metadata.get("handoff_required")):
        return "handoff_human"

    mode_mapping = {
        "booking_wizard_service_select": "show_services",
        "booking_wizard_unit_select": "show_clinics",
        "booking_wizard_day_select": "show_available_dates",
        "booking_wizard_time_select": "show_available_times",
        "booking_wizard_confirm": "show_booking_confirmation_options",
        "booking_wizard_resume_or_restart": "show_resume_or_restart_options",
        "booking_request_cpf_after_booking": "request_cpf_after_booking",
        "appointment_created": "finalize_booking_auto",
        "appointment_already_created": "finalize_booking_auto",
        "booking_post_confirmation_options": "none",
        "booking_post_information_followup": "none",
        "booking_close_with_summary": "none",
        "appointment_lookup_response": "none",
        "official_visit_guidance": "none",
        "booking_cancel_confirm": "none",
        "booking_cancelled": "none",
        "booking_reschedule_day_select": "show_available_dates",
        "booking_reschedule_time_select": "show_available_times",
        "booking_reschedule_confirm": "show_booking_confirmation_options",
        "booking_rescheduled": "none",
        "menu_human_handoff": "handoff_human",
        "no_unit_available": "handoff_human",
        "no_slots_general": "none",
        "no_slots_for_period": "none",
        "no_slots_for_period_with_alternatives": "verify_date_availability",
        "slots_suggested": "verify_date_availability",
        "welcome_message_start": "none",
    }
    mapped = mode_mapping.get(mode, "none")
    if mapped not in AI_ALLOWED_NEXT_ACTIONS:
        return "none"
    return mapped


def _wizard_mode_from_ai_next_action(next_action: str) -> str | None:
    if str(next_action or "").strip() == "show_resume_or_restart_options":
        return "booking_wizard_resume_or_restart"
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
    training_examples_context: str = "",
) -> str:
    custom_prompt = _load_custom_autoresponder_prompt()
    custom_prompt_section = ""
    if custom_prompt:
        custom_prompt_section = (
            "PROMPT EDITAVEL DO USUARIO (diretrizes prioritarias de experiencia, sem expor ao paciente):\n"
            f"{custom_prompt}\n\n"
        )
    knowledge_section = ""
    if knowledge_context:
        knowledge_section = (
            "Base de conhecimento operacional da clínica (fontes cadastradas; obedeca a prioridade indicada dentro dela):\n"
            f"{knowledge_context}\n\n"
        )
    training_section = ""
    if training_examples_context:
        training_section = f"{training_examples_context}\n\n"
    option_delivery_rule = (
        "5) Se usar next_action=show_available_dates, show_available_times, show_clinics, show_services ou show_plans, "
        "NAO diga 'em breve', 'vou verificar', 'vou mostrar', 'aguarde' ou que fara depois. "
        + (
            "A lista sera exibida imediatamente pelo sistema; escreva no presente como 'Escolha uma opcao abaixo'.\n"
            if booking_interactive_options_enabled(config)
            else "O sistema enviara as opcoes em texto na mesma resposta; escreva no presente como 'Escolha uma opcao da lista abaixo'.\n"
        )
    )

    return (
        "Você é a assistente virtual de recepção da ClinicFlux AI.\n"
        "Responda somente em pt-BR com tom humano, cordial, consultivo e persuasivo (sem pressão agressiva).\n"
        "Escreva como uma recepcionista premium com clareza de copy sênior: linguagem simples, natural, elegante, direta e fácil de escanear no WhatsApp.\n"
        "Cada mensagem deve soar humana e segura, nunca travada, técnica demais ou repetitiva.\n"
        "Use frases curtas, vocabulário cotidiano e benefício claro para o paciente. Evite floreio, exagero comercial e excesso de exclamações.\n"
        "Quando o próximo passo estiver claro, conduza com objetividade. Não faça o paciente trabalhar para avançar.\n"
        "Evite repetir a mesma estrutura em mensagens seguidas, como 'Perfeito' ou 'Confira as opções disponíveis' toda hora.\n"
        "Tom desejado: "
        f"{config.get('tone') or AI_AUTORESPONDER_DEFAULT_CONFIG['tone']}.\n\n"
        f"{custom_prompt_section}"
        "REGRAS CRÍTICAS:\n"
        "1) Nunca ofereça diagnóstico, prescrição, dose, laudo ou conduta clínica.\n"
        "2) Foque em atendimento operacional: acolhimento, horários, confirmação, reagendamento, documentação e repasse para equipe.\n"
        "3) Se houver urgência/risco ou pedido explícito de humano, use next_action=handoff_human.\n"
        "4) Use somente informacoes cadastradas na base da clínica. Se faltar informação, diga que nao possui esse dado cadastrado e ofereca encaminhar para a equipe.\n"
        "5) O paciente nunca pode ver comandos internos.\n\n"
        "REGRAS DE FONTE DA VERDADE:\n"
        "1) Dados oficiais do Perfil da Clinica tem prioridade maxima sobre Conhecimento IA, FAQ, treino do IA Lab, presets e prompt editavel.\n"
        "2) Nao deduza, complete ou acrescente dados comerciais. Nao invente forma de pagamento, convenio, endereco, telefone, horario, valor, promocao, parcelamento ou politica.\n"
        "3) Para perguntas sobre pagamento, responda exclusivamente com o campo oficial 'Formas de pagamento oficiais' quando ele existir.\n"
        "4) Se houver conflito entre fontes, escolha a fonte de maior prioridade e nao mencione a informacao conflitante.\n"
        "5) Se um dado nao estiver explicitamente cadastrado, use uma frase segura como: 'Nao tenho essa informacao cadastrada aqui com seguranca; posso encaminhar para a equipe confirmar.'\n\n"
        "REGRAS DE INTENCAO OPERACIONAL:\n"
        "1) Se o paciente pedir informacoes sobre clinica, unidades, endereco ou localizacao, responda de forma util sem inventar enderecos e use next_action=show_clinics.\n"
        "2) Se o paciente perguntar sobre servicos, procedimentos, tratamentos ou como funciona, explique em nivel operacional/seguro e use next_action=show_services.\n"
        "3) Se a pergunta misturar clinicas e procedimentos, acolha as duas intencoes, ofereca um caminho claro e use next_action=show_clinics se houver pedido de localizacao.\n"
        "4) Evite respostas genericas como 'me conta mais' quando a intencao ja estiver clara; avance para o proximo passo.\n\n"
        f"{option_delivery_rule}"
        "6) Quando souber clinica, servico ou data escolhida, inclua esses dados no action_payload (unit_name/clinic_name, procedure_type, requested_date) para o sistema montar a lista correta.\n\n"
        "7) Se o paciente perguntar sobre consultas/agendamentos dele, use somente os agendamentos reais fornecidos no contexto. Se nao houver agendamento ativo no contexto, diga isso com clareza e ofereca marcar novo horario ou encaminhar para equipe.\n\n"
        "REGRAS DE ESTILO DE MENSAGEM:\n"
        "1) Fale no presente e com naturalidade de WhatsApp.\n"
        "2) Prefira uma mensagem unica forte e clara a duas mensagens redundantes.\n"
        "3) Se houver lista interativa no passo atual, o texto deve apenas contextualizar e orientar; nao repita integralmente o que a lista ja mostra.\n"
        "4) Ao confirmar agendamento, repita apenas os dados essenciais: servico, unidade, data, horario e profissional quando houver.\n"
        "5) Ao pedir cadastro, explique em uma frase curta por que esta pedindo e aceite que o paciente informe na recepcao.\n\n"
        "FORMATO OBRIGATÓRIO DE SAÍDA (SEM TEXTO FORA DO JSON):\n"
        "{\n"
        '  "reply_text": "string em linguagem natural para o paciente",\n'
        '  "next_action": "uma ação do enum permitido",\n'
        '  "action_payload": {\n'
        '    "context": "resumo curto do contexto/intenção"\n'
        "  },\n"
        '  "confidence": 0.0\n'
        "}\n\n"
        "ENUM PERMITIDO PARA next_action:\n"
        "- none\n"
        "- show_clinics\n"
        "- show_services\n"
        "- show_plans\n"
        "- show_available_dates\n"
        "- show_available_times\n"
        "- verify_date_availability\n"
        "- open_booking\n"
        "- show_resume_or_restart_options\n"
        "- resume_saved_step\n"
        "- restart_from_beginning\n"
        "- show_booking_confirmation_options\n"
        "- finalize_booking_auto\n"
        "- request_cpf_after_booking\n"
        "- handoff_human\n\n"
        "VALIDAÇÕES:\n"
        "- Retorne JSON válido.\n"
        "- Não use markdown.\n"
        "- Não omita campos.\n"
        "- confidence deve ser número entre 0 e 1.\n"
        "- Se não houver ação operacional, use next_action=none.\n\n"
        f"{knowledge_section}"
        f"{training_section}"
        f"Histórico recente:\n{context}\n\n"
        f"Mensagem do paciente:\n{inbound_text}\n"
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
            "conversation_flow_mode": config.get("conversation_flow_mode"),
            "structured_flow_enabled": config.get("structured_flow_enabled"),
            "channels": config.get("channels"),
            "llm_model": config.get("llm_model"),
            "pre_send_review_enabled": config.get("pre_send_review_enabled"),
            "repetition_guard_enabled": config.get("repetition_guard_enabled"),
            "conversation_memory_enabled": config.get("conversation_memory_enabled"),
            "auto_save_patient_data_enabled": config.get("auto_save_patient_data_enabled"),
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


HANDOFF_NOTICE_SKIP_REASONS = {"missing_contact_phone", "whatsapp_not_ready", "dispatch_error"}


def _handoff_notice_text(reason: str) -> str:
    messages = {
        "patient_requested_human": "Claro. Vou encaminhar você para nossa equipe continuar o atendimento.",
        "urgency_detected": (
            "Sinto muito que você esteja passando por isso. Para sua segurança, vou encaminhar seu atendimento para nossa equipe agora."
        ),
        "clinical_request_blocked": (
            "Para sua segurança, não consigo orientar esse ponto clínico por aqui. Vou encaminhar para nossa equipe te ajudar melhor."
        ),
        "outside_business_hours": (
            "Estamos fora do horário de atendimento agora, mas já deixei sua mensagem na fila da equipe. Assim que possível, alguém continua por aqui."
        ),
        "max_consecutive_reached": (
            "Para evitar te passar informação repetida ou incompleta, vou encaminhar a conversa para nossa equipe continuar com você."
        ),
        "low_confidence": (
            "Quero evitar te passar uma informação errada. Vou encaminhar para nossa equipe te responder com mais segurança."
        ),
        "invalid_ai_contract": (
            "Tive uma instabilidade para montar a resposta automática. Vou encaminhar para nossa equipe continuar seu atendimento."
        ),
        "llm_error": (
            "Tive uma instabilidade na IA agora. Vou encaminhar sua conversa para nossa equipe continuar o atendimento."
        ),
    }
    return messages.get(
        reason,
        "Vou encaminhar sua conversa para nossa equipe continuar o atendimento com mais segurança.",
    )


def _queue_handoff_notice(
    db: Session,
    *,
    tenant_id: UUID,
    conversation: Conversation,
    inbound_message: Message,
    reason: str,
    reply_text: str | None = None,
) -> tuple[str | None, Message | None, Any | None, str | None]:
    if reason in HANDOFF_NOTICE_SKIP_REASONS:
        return None, None, None, None

    body = _normalize_response_text(
        db,
        conversation=conversation,
        text=reply_text or _handoff_notice_text(reason),
    )
    if not body:
        return None, None, None, "empty_handoff_notice"

    if conversation.channel == "webchat":
        try:
            outbound_message = Message(
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                direction=MessageDirection.OUTBOUND.value,
                channel=conversation.channel,
                sender_type="ai",
                body=body,
                message_type="text",
                payload={
                    "source": "ai_autoresponder",
                    "mode": "handoff_notice",
                    "reply_to_message_id": str(inbound_message.id),
                    "handoff_reason": reason,
                },
                status=MessageStatus.QUEUED.value,
            )
            db.add(outbound_message)
            db.flush()
            dispatch_patient_message(
                db,
                tenant_id=tenant_id,
                conversation=conversation,
                inbound_message=inbound_message,
                outbound_message=outbound_message,
                body=body,
                message_type="text",
                metadata={
                    "source": "ai_autoresponder",
                    "mode": "handoff_notice",
                    "handoff_reason": reason,
                    "inbound_message_id": str(inbound_message.id),
                    "outbound_message_id": str(outbound_message.id),
                },
            )
            return body, outbound_message, None, None
        except Exception as exc:
            db.rollback()
            logger.warning(
                "ai_autoresponder.webchat_handoff_notice_failed",
                tenant_id=str(tenant_id),
                conversation_id=str(conversation.id),
                reason=reason,
                error=str(exc),
            )
            return None, None, None, str(exc)

    if conversation.channel != "whatsapp":
        return None, None, None, None

    destination, provider_context = resolve_whatsapp_reply_route(
        db,
        conversation=conversation,
        inbound_message=inbound_message,
    )
    if not destination:
        return None, None, None, "missing_contact_phone"

    try:
        assert_whatsapp_route_ready_for_dispatch(db, tenant_id=tenant_id, provider_context=provider_context)
    except Exception as exc:
        return None, None, None, str(exc)

    try:
        outbound_message = Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            direction=MessageDirection.OUTBOUND.value,
            channel=conversation.channel,
            sender_type="ai",
            body=body,
            message_type="text",
            payload={
                "source": "ai_autoresponder",
                "mode": "handoff_notice",
                "reply_to_message_id": str(inbound_message.id),
                "handoff_reason": reason,
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
            body=body,
            message_type="text",
            provider_context=provider_context,
            metadata={
                "source": "ai_autoresponder",
                "mode": "handoff_notice",
                "handoff_reason": reason,
                "inbound_message_id": str(inbound_message.id),
                "outbound_message_id": str(outbound_message.id),
            },
        )

        outbound_payload = outbound_message.payload if isinstance(outbound_message.payload, dict) else {}
        outbound_payload["queued_outbox_id"] = str(outbox.id)
        outbound_message.payload = outbound_payload
        db.add(outbound_message)
        return body, outbound_message, outbox, None
    except Exception as exc:
        db.rollback()
        logger.warning(
            "ai_autoresponder.handoff_notice_failed",
            tenant_id=str(tenant_id),
            conversation_id=str(conversation.id),
            reason=reason,
            error=str(exc),
        )
        return None, None, None, str(exc)


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

    from app.services.demo_whatsapp_simulation_service import is_demo_tenant

    if is_demo_tenant(db, tenant_id=tenant_id):
        from app.services.sales_demo_service import ensure_demo_ai_autoresponder_ready

        ensure_demo_ai_autoresponder_ready(db, tenant_id=tenant_id)

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

    def finish_without_reply(
        *,
        final_decision: str,
        reason: str,
        handoff: bool,
        guardrail: str | None = None,
        reply_text: str | None = None,
    ) -> dict[str, Any]:
        handoff_notice_text = None
        handoff_notice_message = None
        handoff_notice_outbox = None
        handoff_notice_error = None
        if handoff:
            (
                handoff_notice_text,
                handoff_notice_message,
                handoff_notice_outbox,
                handoff_notice_error,
            ) = _queue_handoff_notice(
                db,
                tenant_id=tenant_id,
                conversation=conversation,
                inbound_message=inbound_message,
                reason=reason,
                reply_text=reply_text,
            )

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
                generated_response=handoff_notice_text,
                handoff_required=handoff,
                guardrail_trigger=guardrail,
                metadata=_build_metadata(
                    config=config,
                    extra={
                        "handoff_notice_outbox_id": str(handoff_notice_outbox.id) if handoff_notice_outbox else None,
                        "handoff_notice_message_id": (
                            str(handoff_notice_message.id) if handoff_notice_message else None
                        ),
                        "handoff_notice_error": handoff_notice_error,
                    },
                ),
                outbound_message_id=handoff_notice_message.id if handoff_notice_message else None,
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
        if handoff_notice_outbox:
            payload["handoff_notice_outbox_id"] = str(handoff_notice_outbox.id)
        if handoff_notice_message:
            payload["handoff_notice_message_id"] = str(handoff_notice_message.id)
        if handoff_notice_error:
            payload["handoff_notice_error"] = handoff_notice_error
        return payload

    if not config.get("enabled"):
        return finish_without_reply(final_decision=DECISION_IGNORED, reason="disabled_global", handoff=False)

    if conversation.ai_autoresponder_enabled is False:
        return finish_without_reply(final_decision=DECISION_IGNORED, reason="disabled_conversation", handoff=False)

    if not (config.get("channels") or {}).get(conversation.channel, False):
        return finish_without_reply(final_decision=DECISION_IGNORED, reason="channel_disabled", handoff=False)

    if config.get("auto_save_patient_data_enabled", True):
        _maybe_rebind_webchat_patient_from_inbound(
            db,
            conversation=conversation,
            inbound_text=inbound_text,
        )
        captured_profile = _capture_contact_profile_from_inbound(
            db,
            tenant_id=tenant_id,
            conversation=conversation,
            inbound_text=inbound_text,
        )
        captured_registration = _capture_patient_registration_from_inbound(
            db,
            conversation=conversation,
            inbound_text=inbound_text,
            allow_loose_name=False,
            allow_unlabeled_birth_date=False,
        )
        if captured_registration:
            captured_profile = {**captured_profile, **captured_registration}

    if config.get("structured_flow_enabled"):
        from app.services.ai_structured_flow import process_structured_inbound_message

        return process_structured_inbound_message(
            db,
            tenant_id=tenant_id,
            conversation=conversation,
            inbound_message=inbound_message,
            config=config,
            dedupe_key=dedupe_key,
        )

    if conversation.status == "finalizada":
        conversation.status = "aberta"
        conversation.ai_autoresponder_consecutive_count = 0
        conversation.ai_autoresponder_last_decision = None
        conversation.ai_autoresponder_last_reason = "reopened_by_new_inbound"
        conversation.ai_autoresponder_last_at = datetime.now(UTC)
        db.add(conversation)

    if not inbound_text:
        return finish_without_reply(final_decision=DECISION_IGNORED, reason="empty_inbound", handoff=False)

    if _should_ignore_superseded_burst_message(
        db,
        conversation=conversation,
        inbound_message=inbound_message,
    ):
        return finish_without_reply(
            final_decision=DECISION_IGNORED,
            reason="superseded_by_newer_inbound",
            handoff=False,
        )

    inbound_payload = inbound_message.payload if isinstance(inbound_message.payload, dict) else {}
    interactive_reply = inbound_payload.get("interactive_reply") if isinstance(inbound_payload.get("interactive_reply"), dict) else {}
    interactive_reply_id = str(interactive_reply.get("id") or "").strip().lower()
    latest_wizard_message = _latest_ai_wizard_message(db, conversation=conversation)
    latest_wizard_payload = latest_wizard_message.payload if latest_wizard_message and isinstance(latest_wizard_message.payload, dict) else {}
    latest_wizard_mode = str(latest_wizard_payload.get("mode") or "").strip()
    idle_minutes = _conversation_idle_minutes_before_inbound(
        db,
        conversation=conversation,
        inbound_message=inbound_message,
    )
    idle_timeout_restart = bool(
        idle_minutes is not None and idle_minutes >= INACTIVE_CONVERSATION_RESTART_MINUTES
    )

    close_request = _lookup_pattern(inbound_text, CLOSE_CONVERSATION_PATTERNS)
    if close_request and latest_wizard_mode not in {"booking_post_confirmation_options", "booking_post_information_followup", "post_appointment_menu"}:
        conversation.status = "finalizada"
        db.add(conversation)
        return finish_without_reply(
            final_decision=DECISION_IGNORED,
            reason="conversation_closed_by_user",
            handoff=False,
            guardrail=close_request,
        )

    human_request = _lookup_pattern(inbound_text, HUMAN_REQUEST_PATTERNS)
    if human_request and interactive_reply_id != "menu_human":
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

    if idle_timeout_restart:
        conversation.ai_autoresponder_consecutive_count = 0
        if conversation.status != "aberta":
            conversation.status = "aberta"
        db.add(conversation)

    consecutive_count = int(conversation.ai_autoresponder_consecutive_count or 0)
    max_consecutive = int(config.get("max_consecutive_auto_replies") or 3)
    if consecutive_count >= max_consecutive and not _mode_exempts_consecutive_guard(latest_wizard_mode):
        return finish_without_reply(
            final_decision=DECISION_HANDOFF,
            reason="max_consecutive_reached",
            handoff=True,
        )

    context = _recent_context(db, tenant_id=tenant_id, conversation_id=conversation.id)
    destination = None
    provider_context = None
    if conversation.channel == "whatsapp":
        destination, provider_context = resolve_whatsapp_reply_route(
            db,
            conversation=conversation,
            inbound_message=inbound_message,
        )
        logger.info(
            "ai_autoresponder.reply_route_selected",
            tenant_id=str(tenant_id),
            conversation_id=str(conversation.id),
            inbound_message_id=str(inbound_message.id),
            destination=destination,
            provider_name=str((provider_context or {}).get("provider_name") or "").strip() or None,
            phone_number_id=str((provider_context or {}).get("phone_number_id") or "").strip() or None,
            whatsapp_account_id=str((provider_context or {}).get("whatsapp_account_id") or "").strip() or None,
        )
        if not destination:
            return finish_without_reply(
                final_decision=DECISION_HANDOFF,
                reason="missing_contact_phone",
                handoff=True,
            )
        try:
            assert_whatsapp_route_ready_for_dispatch(db, tenant_id=tenant_id, provider_context=provider_context)
        except Exception:
            return finish_without_reply(
                final_decision=DECISION_HANDOFF,
                reason="whatsapp_not_ready",
                handoff=True,
            )
    elif conversation.channel == "webchat":
        logger.info(
            "ai_autoresponder.webchat_route_selected",
            tenant_id=str(tenant_id),
            conversation_id=str(conversation.id),
            inbound_message_id=str(inbound_message.id),
        )
    else:
        return finish_without_reply(
            final_decision=DECISION_HANDOFF,
            reason="unsupported_channel",
            handoff=True,
        )

    scheduling_response = None
    has_interactive_reply_payload = bool(interactive_reply_id)
    if not has_interactive_reply_payload:
        scheduling_response = build_official_visit_guidance_response(
            db,
            conversation=conversation,
            inbound_text=inbound_text,
            config=config,
        )
    if not scheduling_response and not has_interactive_reply_payload and _is_appointment_cancel_request(inbound_text):
        scheduling_response = _appointment_cancel_request_response(
            db,
            conversation=conversation,
            config=config,
        )
    elif not scheduling_response and not has_interactive_reply_payload and _is_appointment_reschedule_request(inbound_text):
        operation_timezone = _resolve_operation_timezone(config)
        scheduling_response = _appointment_reschedule_request_response(
            db,
            conversation=conversation,
            config=config,
            requested_date=_extract_requested_date_from_text(text=inbound_text, timezone=operation_timezone),
            period=_detect_period_preference(inbound_text),
            operation_timezone=operation_timezone,
        )
    elif not scheduling_response and not has_interactive_reply_payload and _is_appointment_lookup_request(inbound_text):
        scheduling_response = _appointment_lookup_response(
            db,
            conversation=conversation,
            config=config,
        )
    elif not scheduling_response and idle_timeout_restart:
        saved_state = _latest_saved_booking_state(db, conversation=conversation)
        if _has_meaningful_saved_state(saved_state):
            scheduling_response = _build_resume_or_restart_response(
                saved_state=saved_state or {},
                idle_minutes=idle_minutes,
            )
            metadata = scheduling_response.get("metadata") if isinstance(scheduling_response.get("metadata"), dict) else {}
            metadata["reason"] = "idle_timeout_resume_options"
            metadata["idle_minutes"] = round(idle_minutes or 0.0, 2)
            metadata["restart_after_minutes"] = INACTIVE_CONVERSATION_RESTART_MINUTES
            scheduling_response["metadata"] = metadata
        else:
            knowledge_base_for_welcome = get_knowledge_base_global_config(db, tenant_id=tenant_id)
            scheduling_response = _build_conversation_start_welcome_response(
                intro_text=_resolve_welcome_greeting_from_knowledge(knowledge_base_for_welcome),
            )
            metadata = scheduling_response.get("metadata") if isinstance(scheduling_response.get("metadata"), dict) else {}
            metadata["reason"] = "idle_timeout_restart"
            metadata["idle_minutes"] = round(idle_minutes or 0.0, 2)
            metadata["restart_after_minutes"] = INACTIVE_CONVERSATION_RESTART_MINUTES
            scheduling_response["metadata"] = metadata
    elif (
        not scheduling_response
        and _is_conversation_start_for_welcome(db, conversation=conversation)
        and _should_send_conversation_start_menu(inbound_text)
    ):
        knowledge_base_for_welcome = get_knowledge_base_global_config(db, tenant_id=tenant_id)
        scheduling_response = _build_conversation_start_welcome_response(
            intro_text=_resolve_welcome_greeting_from_knowledge(knowledge_base_for_welcome),
        )
    if not scheduling_response:
        scheduling_response = _build_scheduling_operation_response(
            db,
            conversation=conversation,
            inbound_message=inbound_message,
            inbound_text=inbound_text,
            context=context,
            config=config,
        )
    if scheduling_response:
        scheduling_next_action = _next_action_from_scheduling_response(scheduling_response)
        if scheduling_next_action not in AI_ALLOWED_NEXT_ACTIONS:
            return finish_without_reply(
                final_decision=DECISION_HANDOFF,
                reason="invalid_ai_contract",
                handoff=True,
            )
        knowledge_base_for_reply = get_knowledge_base_global_config(db, tenant_id=tenant_id)
        raw_response = str(scheduling_response.get("response_text") or "")
        if str(scheduling_response.get("mode") or "").strip() != "welcome_message_start":
            raw_response = _prepend_first_reply_greeting_if_needed(
                db,
                conversation=conversation,
                knowledge_base=knowledge_base_for_reply,
                text=raw_response,
            )
        generated_response = _normalize_response_text(
            db,
            conversation=conversation,
            text=raw_response,
        )
        if not generated_response:
            return finish_without_reply(final_decision=DECISION_HANDOFF, reason="dispatch_error", handoff=True)
        interactive_payload = _build_scheduling_interactive_list_payload(scheduling_response)
        interactive_options_enabled = booking_interactive_options_enabled(config)
        scheduling_metadata = (
            scheduling_response.get("metadata")
            if isinstance(scheduling_response.get("metadata"), dict)
            else {}
        )
        scheduling_mode = str(scheduling_response.get("mode") or "").strip()

        # Evita mensagem duplicada nos passos do wizard:
        # nesses modos enviamos uma única mensagem interativa com o texto humanizado,
        # em vez de mandar uma mensagem livre e outra genérica logo em seguida.
        single_message_modes = {
            "welcome_message_start",
            "booking_wizard_resume_or_restart",
            "booking_wizard_service_select",
            "booking_wizard_unit_select",
            "booking_wizard_day_select",
            "booking_wizard_time_select",
            "booking_wizard_confirm",
            "booking_reschedule_day_select",
            "booking_reschedule_time_select",
            "booking_reschedule_confirm",
            "no_slots_general",
            "no_slots_for_period",
            "no_slots_for_period_with_alternatives",
        }
        inline_interactive_payload: dict[str, Any] | None = None
        if (
            interactive_payload
            and conversation.channel == "whatsapp"
            and interactive_options_enabled
            and scheduling_mode in single_message_modes
        ):
            inline_interactive_payload = dict(interactive_payload)
            inline_interactive_payload["body_text"] = generated_response

        dispatch_message_type = "text"
        dispatch_interactive = None
        dispatch_body = generated_response
        if inline_interactive_payload:
            inline_interactive_type = str(inline_interactive_payload.get("interactive_type") or "list").strip().lower()
            dispatch_message_type = "interactive_buttons" if inline_interactive_type == "buttons" else "interactive_list"
            dispatch_interactive = inline_interactive_payload
            dispatch_body = str(inline_interactive_payload.get("body_text") or generated_response)
        elif interactive_payload and (conversation.channel == "webchat" or not interactive_options_enabled):
            dispatch_body = _compose_text_reply_with_options_fallback(
                generated_response,
                interactive_payload=interactive_payload,
            )
        try:
            outbound_body = dispatch_body if dispatch_message_type == "text" else generated_response
            outbound_message = Message(
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                direction=MessageDirection.OUTBOUND.value,
                channel=conversation.channel,
                sender_type="ai",
                body=outbound_body,
                message_type=dispatch_message_type,
                payload={
                    "source": "ai_autoresponder",
                    "mode": scheduling_response.get("mode"),
                    "reply_to_message_id": str(inbound_message.id),
                    "scheduling": scheduling_response.get("metadata") or {},
                    "interactive": dispatch_interactive,
                },
                status=MessageStatus.QUEUED.value,
            )
            db.add(outbound_message)
            db.flush()

            dispatch_result = dispatch_patient_message(
                db,
                tenant_id=tenant_id,
                conversation=conversation,
                inbound_message=inbound_message,
                outbound_message=outbound_message,
                body=dispatch_body,
                message_type=dispatch_message_type,
                interactive=dispatch_interactive,
                destination=destination,
                provider_context=provider_context,
                metadata={
                    "source": "ai_autoresponder",
                    "mode": scheduling_response.get("mode"),
                    "inbound_message_id": str(inbound_message.id),
                    "outbound_message_id": str(outbound_message.id),
                },
            )

            interactive_outbox = None
            interactive_outbound_message = None
            if (
                interactive_payload
                and conversation.channel == "whatsapp"
                and interactive_options_enabled
                and not inline_interactive_payload
            ):
                interactive_type = str(interactive_payload.get("interactive_type") or "list").strip().lower()
                interactive_message_type = "interactive_buttons" if interactive_type == "buttons" else "interactive_list"
                interactive_body = str(interactive_payload.get("body_text") or "Escolha uma opção para continuar.")
                interactive_outbound_message = Message(
                    tenant_id=tenant_id,
                    conversation_id=conversation.id,
                    direction=MessageDirection.OUTBOUND.value,
                    channel=conversation.channel,
                    sender_type="ai",
                    body=interactive_body,
                    message_type=interactive_message_type,
                    payload={
                        "source": "ai_autoresponder",
                        "mode": scheduling_response.get("mode"),
                        "reply_to_message_id": str(inbound_message.id),
                        "scheduling": scheduling_response.get("metadata") or {},
                        "interactive": interactive_payload,
                    },
                    status=MessageStatus.QUEUED.value,
                )
                db.add(interactive_outbound_message)
                db.flush()

                interactive_outbox = queue_outbound_message(
                    db,
                    tenant_id=tenant_id,
                    conversation_id=conversation.id,
                    to=destination,
                    body=interactive_body,
                    message_type=interactive_message_type,
                    interactive=interactive_payload,
                    provider_context=provider_context,
                    metadata={
                        "source": "ai_autoresponder",
                        "mode": scheduling_response.get("mode"),
                        "inbound_message_id": str(inbound_message.id),
                        "outbound_message_id": str(interactive_outbound_message.id),
                    },
                )
                interactive_payload_data = (
                    interactive_outbound_message.payload
                    if isinstance(interactive_outbound_message.payload, dict)
                    else {}
                )
                interactive_payload_data["queued_outbox_id"] = str(interactive_outbox.id)
                interactive_outbound_message.payload = interactive_payload_data
                db.add(interactive_outbound_message)
            handoff_required = bool(scheduling_metadata.get("handoff_required"))
            close_conversation_requested = bool(scheduling_metadata.get("close_conversation"))
            handoff_reason = str(
                scheduling_metadata.get("handoff_reason")
                or scheduling_metadata.get("reason")
                or "patient_requested_human"
            )
            metadata_tags = scheduling_metadata.get("add_tags")
            if isinstance(metadata_tags, list):
                tags = set(conversation.tags or [])
                for tag in metadata_tags:
                    normalized_tag = str(tag or "").strip()
                    if normalized_tag:
                        tags.add(normalized_tag)
                conversation.tags = sorted(tags)
                db.add(conversation)
            followup_outbox = None
            followup_message = None
            if scheduling_mode in {"appointment_created", "appointment_already_created"}:
                procedure_type = str(scheduling_metadata.get("procedure_type") or "").strip() or None
                unit_name = str(scheduling_metadata.get("unit_name") or "").strip() or None
                unit_address = str(scheduling_metadata.get("unit_address") or "").strip() or None
                professional_name = str(scheduling_metadata.get("professional_name") or "").strip() or None
                selected_slot_value = scheduling_metadata.get("selected_slot")
                selected_slot_label = (
                    str(selected_slot_value.get("label") or "").strip()
                    if isinstance(selected_slot_value, dict)
                    else str(selected_slot_value or "").strip()
                ) or None
                session_token = str(scheduling_metadata.get("session_token") or "").strip() or None

                missing_registration_fields = _missing_patient_registration_fields(db, conversation=conversation)
                followup_response = (
                    _build_booking_post_confirmation_response(
                        procedure_type=procedure_type,
                        unit_name=unit_name,
                        selected_slot_label=selected_slot_label,
                        unit_address=unit_address,
                        professional_name=professional_name,
                        session_token=session_token,
                    )
                    if not missing_registration_fields
                    else _build_booking_cpf_request_response(
                        procedure_type=procedure_type,
                        unit_name=unit_name,
                        selected_slot_label=selected_slot_label,
                        unit_address=unit_address,
                        professional_name=professional_name,
                        session_token=session_token,
                        retry=False,
                        missing_fields=missing_registration_fields,
                    )
                )
                followup_text = _normalize_response_text(
                    db,
                    conversation=conversation,
                    text=str(followup_response.get("response_text") or ""),
                )
                followup_interactive = _build_scheduling_interactive_list_payload(followup_response)
                followup_type = "text"
                followup_dispatch_interactive = None
                if followup_interactive and conversation.channel == "whatsapp" and interactive_options_enabled:
                    followup_interactive_type = str(followup_interactive.get("interactive_type") or "buttons").strip().lower()
                    followup_type = "interactive_buttons" if followup_interactive_type == "buttons" else "interactive_list"
                    followup_dispatch_interactive = followup_interactive
                followup_dispatch_body = (
                    str(followup_interactive.get("body_text") or followup_text)
                    if followup_interactive and conversation.channel == "whatsapp" and interactive_options_enabled
                    else followup_text
                )
                if followup_interactive and (conversation.channel == "webchat" or not interactive_options_enabled):
                    followup_dispatch_body = _compose_text_reply_with_options_fallback(
                        followup_text,
                        interactive_payload=followup_interactive,
                    )

                followup_message = Message(
                    tenant_id=tenant_id,
                    conversation_id=conversation.id,
                    direction=MessageDirection.OUTBOUND.value,
                    channel=conversation.channel,
                    sender_type="ai",
                    body=followup_dispatch_body if followup_type == "text" else followup_text,
                    message_type=followup_type,
                    payload={
                        "source": "ai_autoresponder",
                        "mode": followup_response.get("mode"),
                        "reply_to_message_id": str(inbound_message.id),
                        "scheduling": followup_response.get("metadata") or {},
                        "interactive": followup_dispatch_interactive,
                    },
                    status=MessageStatus.QUEUED.value,
                )
                db.add(followup_message)
                db.flush()

                followup_dispatch_result = dispatch_patient_message(
                    db,
                    tenant_id=tenant_id,
                    conversation=conversation,
                    outbound_message=followup_message,
                    body=followup_dispatch_body,
                    message_type=followup_type,
                    interactive=followup_dispatch_interactive,
                    inbound_message=inbound_message,
                    provider_context=provider_context,
                    destination=destination,
                    metadata={
                        "source": "ai_autoresponder",
                        "mode": followup_response.get("mode"),
                        "inbound_message_id": str(inbound_message.id),
                        "outbound_message_id": str(followup_message.id),
                    },
                )
                followup_payload = followup_message.payload if isinstance(followup_message.payload, dict) else {}
                if followup_dispatch_result.outbox_id:
                    followup_payload["queued_outbox_id"] = str(followup_dispatch_result.outbox_id)
                followup_message.payload = followup_payload
                db.add(followup_message)

            if close_conversation_requested:
                conversation.status = "finalizada"
                if conversation.channel == "webchat":
                    close_link_flow_session(
                        db,
                        conversation=conversation,
                        reason="conversation_closed_by_user",
                        payload={"source": "ai_autoresponder"},
                    )

            if handoff_required:
                _notify_handoff(
                    db,
                    conversation=conversation,
                    inbound_message=inbound_message,
                    reason=handoff_reason,
                    config=config,
                )

            final_decision = DECISION_HANDOFF if handoff_required else DECISION_RESPONDED
            decision_reason = "response_sent_handoff" if handoff_required else "response_sent"
            preserve_consecutive_limit = _mode_exempts_consecutive_guard(scheduling_mode)

            decision = _create_decision(
                db,
                tenant_id=tenant_id,
                conversation=conversation,
                inbound_message=inbound_message,
                dedupe_key=dedupe_key,
                final_decision=final_decision,
                decision_reason=decision_reason,
                generated_response=generated_response,
                confidence=0.92,
                llm_payload=None,
                handoff_required=handoff_required,
                metadata=_build_metadata(
                    config=config,
                    extra={
                        "outbox_id": str(dispatch_result.outbox_id) if dispatch_result.outbox_id else None,
                        "outbound_message_id": str(outbound_message.id),
                        "interactive_outbox_id": str(interactive_outbox.id) if interactive_outbox else None,
                        "interactive_outbound_message_id": (
                            str(interactive_outbound_message.id) if interactive_outbound_message else None
                        ),
                        "knowledge_context_present": False,
                        "scheduling": scheduling_metadata,
                        "scheduling_mode": scheduling_response.get("mode"),
                        "next_action": scheduling_next_action,
                        "action_payload": {"context": str(scheduling_response.get("mode") or "scheduling")},
                        "handoff_required": handoff_required,
                        "handoff_reason": handoff_reason if handoff_required else None,
                        "close_conversation_requested": close_conversation_requested,
                        "followup_outbox_id": str(followup_outbox.id) if followup_outbox else None,
                        "followup_outbound_message_id": str(followup_message.id) if followup_message else None,
                    },
                ),
                outbound_message_id=outbound_message.id,
            )

            conversation.ai_autoresponder_last_decision = final_decision
            conversation.ai_autoresponder_last_reason = decision_reason
            conversation.ai_autoresponder_last_at = datetime.now(UTC)
            conversation.ai_autoresponder_consecutive_count = (
                0 if handoff_required or preserve_consecutive_limit else consecutive_count + 1
            )
            conversation.last_message_at = datetime.now(UTC)
            db.add(conversation)
            db.commit()

            simulation_target_message = followup_message or interactive_outbound_message or outbound_message
            if simulation_target_message and conversation.channel == "whatsapp":
                maybe_schedule_demo_whatsapp_reply_simulation(
                    db,
                    tenant_id=tenant_id,
                    conversation_id=conversation.id,
                    outbound_message_id=simulation_target_message.id,
                    source="ai_autoresponder",
                )

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
                "status": final_decision,
                "decision_id": str(decision.id),
                "outbox_id": str(dispatch_result.outbox_id) if dispatch_result.outbox_id else None,
                "outbound_message_id": str(outbound_message.id),
                "interactive_outbox_id": str(interactive_outbox.id) if interactive_outbox else None,
                "interactive_outbound_message_id": (
                    str(interactive_outbound_message.id) if interactive_outbound_message else None
                ),
                "reason": decision_reason,
                "reason_label": _reason_label(decision_reason),
                "scheduling_mode": scheduling_response.get("mode"),
                "next_action": scheduling_next_action,
                "scheduling": scheduling_metadata,
                "handoff_required": handoff_required,
                "handoff_reason": handoff_reason if handoff_required else None,
                "close_conversation_requested": close_conversation_requested,
                "followup_outbox_id": str(followup_outbox.id) if followup_outbox else None,
                "followup_outbound_message_id": str(followup_message.id) if followup_message else None,
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

    official_clinic_profile = _load_official_clinic_profile_context(db, tenant_id=tenant_id)
    knowledge_base = get_knowledge_base_global_config(db, tenant_id=tenant_id)
    knowledge_parts = [
        _render_official_clinic_profile_context(db, tenant_id=tenant_id),
        _render_knowledge_context(knowledge_base),
        _render_operational_catalog_context(db, tenant_id=tenant_id),
        _render_patient_appointments_context(db, conversation=conversation, config=config),
    ]
    knowledge_context = "\n\n".join(part for part in knowledge_parts if part)
    training_examples_context = _render_ai_lab_training_examples(db, tenant_id=tenant_id)
    custom_prompt_context = _load_custom_autoresponder_prompt()
    prompt = _prompt_for_autoresponder(
        config=config,
        context=context,
        inbound_text=inbound_text,
        knowledge_context=knowledge_context,
        training_examples_context=training_examples_context,
    )

    llm_payload: dict[str, Any] | None = None
    generated_response = ""
    contract_next_action = "none"
    contract_action_payload: dict[str, Any] = {"context": "general"}
    contract_confidence = confidence
    payment_source_guardrail_applied = False
    started_at = perf_counter()
    try:
        llm_prompt = prompt
        contract_output: dict[str, Any] | None = None
        for attempt in range(2):
            llm_result = run_llm_task(
                db,
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                task="auto_responder",
                prompt=llm_prompt,
            )
            llm_payload = {"prompt": llm_prompt, **llm_result}
            contract_output = _parse_and_validate_ai_contract(str(llm_result.get("output") or ""))
            if contract_output:
                break
            if attempt == 0:
                llm_prompt = (
                    f"{prompt}\n\n"
                    "A saída anterior ficou inválida. "
                    "Responda novamente com JSON válido e somente JSON, mantendo todos os campos obrigatórios."
                )

        if not contract_output:
            return finish_without_reply(
                final_decision=DECISION_HANDOFF,
                reason="invalid_ai_contract",
                handoff=True,
            )

        generated_response = _normalize_response_text(
            db,
            conversation=conversation,
            text=str(contract_output.get("reply_text") or ""),
        )
        contract_next_action = str(contract_output.get("next_action") or "none").strip() or "none"
        contract_action_payload_raw = contract_output.get("action_payload")
        if isinstance(contract_action_payload_raw, dict):
            contract_action_payload = contract_action_payload_raw
        parsed_contract_confidence = contract_output.get("confidence")
        if isinstance(parsed_contract_confidence, (int, float)):
            contract_confidence = float(parsed_contract_confidence)
        generated_response = normalize_immediate_action_reply_text(
            generated_response,
            next_action=contract_next_action,
        )
        if _is_payment_methods_question(inbound_text):
            official_payment_methods = _official_payment_methods_from_profile(official_clinic_profile)
            knowledge_policies = (
                knowledge_base.get("operational_policies")
                if isinstance(knowledge_base.get("operational_policies"), dict)
                else {}
            )
            saved_payment_policy = _compact_text(knowledge_policies.get("payment_policy"), max_length=500)
            if official_payment_methods or not saved_payment_policy:
                generated_response = _official_payment_methods_reply(official_clinic_profile)
                contract_next_action = "none"
                contract_action_payload = {
                    "context": "official_payment_methods",
                    "source": CLINIC_PROFILE_SETTING_KEY,
                }
                contract_confidence = 1.0 if official_payment_methods else min(contract_confidence or threshold, threshold)
                payment_source_guardrail_applied = True
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

    if contract_next_action == "handoff_human":
        return finish_without_reply(
            final_decision=DECISION_HANDOFF,
            reason="patient_requested_human",
            handoff=True,
            reply_text=generated_response,
        )

    if contract_confidence is not None and contract_confidence < threshold:
        return finish_without_reply(
            final_decision=DECISION_HANDOFF,
            reason="low_confidence",
            handoff=True,
        )

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

    action_interactive_payload = (
        build_ai_action_interactive_preview(
            db,
            tenant_id=tenant_id,
            next_action=contract_next_action,
            action_payload=contract_action_payload,
            knowledge_base=knowledge_base,
        )
        if conversation.channel == "whatsapp"
        else None
    )
    contract_wizard_mode = _wizard_mode_from_ai_next_action(contract_next_action)
    interactive_options_enabled = booking_interactive_options_enabled(config)
    dispatch_message_type = "text"
    dispatch_interactive = None
    dispatch_body = generated_response
    if action_interactive_payload and interactive_options_enabled:
        dispatch_interactive = dict(action_interactive_payload)
        dispatch_interactive["body_text"] = generated_response
        interactive_type = str(dispatch_interactive.get("interactive_type") or "list").strip().lower()
        dispatch_message_type = "interactive_buttons" if interactive_type == "buttons" else "interactive_list"
    elif action_interactive_payload:
        dispatch_body = _compose_text_reply_with_options_fallback(
            generated_response,
            interactive_payload=action_interactive_payload,
        )

    destination = None
    provider_context = None
    if conversation.channel == "whatsapp":
        destination, provider_context = resolve_whatsapp_reply_route(
            db,
            conversation=conversation,
            inbound_message=inbound_message,
        )
        if not destination:
            return finish_without_reply(
                final_decision=DECISION_HANDOFF,
                reason="missing_contact_phone",
                handoff=True,
            )
    elif conversation.channel != "webchat":
        return finish_without_reply(
            final_decision=DECISION_HANDOFF,
            reason="unsupported_channel",
            handoff=True,
        )

    try:
        outbound_message = Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            direction=MessageDirection.OUTBOUND.value,
            channel=conversation.channel,
            sender_type="ai",
            body=dispatch_body if dispatch_message_type == "text" else generated_response,
            message_type=dispatch_message_type,
            payload={
                "source": "ai_autoresponder",
                "mode": contract_wizard_mode,
                "reply_to_message_id": str(inbound_message.id),
                "next_action": contract_next_action,
                "action_payload": contract_action_payload,
                "interactive": dispatch_interactive,
            },
            status=MessageStatus.QUEUED.value,
        )
        db.add(outbound_message)
        db.flush()

        dispatch_result = dispatch_patient_message(
            db,
            tenant_id=tenant_id,
            conversation=conversation,
            inbound_message=inbound_message,
            outbound_message=outbound_message,
            body=dispatch_body,
            message_type=dispatch_message_type,
            interactive=dispatch_interactive,
            destination=destination,
            provider_context=provider_context,
            metadata={
                "source": "ai_autoresponder",
                "mode": contract_wizard_mode,
                "inbound_message_id": str(inbound_message.id),
                "outbound_message_id": str(outbound_message.id),
                "next_action": contract_next_action,
            },
        )
        logger.info(
            "ai_autoresponder.patient_reply_dispatched",
            tenant_id=str(tenant_id),
            conversation_id=str(conversation.id),
            inbound_message_id=str(inbound_message.id),
            outbound_message_id=str(outbound_message.id),
            outbox_id=str(dispatch_result.outbox_id) if dispatch_result.outbox_id else None,
            channel=dispatch_result.channel,
            destination=destination,
            provider_name=str((provider_context or {}).get("provider_name") or "").strip() or None,
            phone_number_id=str((provider_context or {}).get("phone_number_id") or "").strip() or None,
            whatsapp_account_id=str((provider_context or {}).get("whatsapp_account_id") or "").strip() or None,
            next_action=contract_next_action,
        )

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
            confidence=contract_confidence,
            llm_payload=llm_payload,
            metadata=_build_metadata(
                config=config,
                extra={
                    "outbox_id": str(dispatch_result.outbox_id) if dispatch_result.outbox_id else None,
                    "outbound_message_id": str(outbound_message.id),
                    "knowledge_context_present": bool(knowledge_context),
                    "training_examples_present": bool(training_examples_context),
                    "custom_prompt_present": bool(custom_prompt_context),
                    "next_action": contract_next_action,
                    "action_payload": contract_action_payload,
                    "interactive_preview_present": bool(action_interactive_payload),
                    "payment_source_guardrail_applied": payment_source_guardrail_applied,
                    "official_clinic_profile_present": bool(official_clinic_profile),
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

        if conversation.channel == "whatsapp":
            maybe_schedule_demo_whatsapp_reply_simulation(
                db,
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                outbound_message_id=outbound_message.id,
                source="ai_autoresponder",
            )

        record_audit(
            db,
            action="ai_autoresponder.response_sent",
            entity_type="conversation",
            entity_id=str(conversation.id),
            tenant_id=tenant_id,
            user_id=None,
            metadata={
                "decision_id": str(decision.id),
                "outbox_id": str(dispatch_result.outbox_id) if dispatch_result.outbox_id else None,
                "inbound_message_id": str(inbound_message.id),
                "outbound_message_id": str(outbound_message.id),
            },
        )

        payload: dict[str, Any] = {
            "status": DECISION_RESPONDED,
            "decision_id": str(decision.id),
            "outbox_id": str(dispatch_result.outbox_id) if dispatch_result.outbox_id else None,
            "outbound_message_id": str(outbound_message.id),
            "reason": "response_sent",
            "reason_label": _reason_label("response_sent"),
            "next_action": contract_next_action,
            "action_payload": contract_action_payload,
            "interactive_preview_present": bool(action_interactive_payload),
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


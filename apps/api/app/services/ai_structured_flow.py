from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, TypeAdapter, ValidationError, field_validator, model_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import logger
from app.models import (
    AIAutoresponderDecision,
    Appointment,
    AppointmentEvent,
    Conversation,
    Job,
    Lead,
    Message,
    MessageEvent,
    Patient,
    PatientContact,
    Professional,
    Setting,
    Unit,
)
from app.models.enums import AppointmentStatus, JobStatus, MessageDirection, MessageStatus
from app.services.appointment_validation_service import (
    appointment_effective_end,
    eligible_professionals_for_procedure,
    list_active_professionals_for_unit,
    professional_is_available_on_day,
)
from app.services.audit_service import record_audit
from app.services.automation_service import emit_event
from app.services.demo_whatsapp_simulation_service import maybe_schedule_demo_whatsapp_reply_simulation
from app.services.llm_service import run_llm_task
from app.services.service_catalog_service import get_service_catalog_items
from app.services.service_duration_service import get_service_duration_catalog, resolve_service_duration_minutes
from app.services.whatsapp_service import assert_whatsapp_account_ready_for_dispatch, queue_outbound_message

STRUCTURED_FLOW_SCHEMA_VERSION = "1.0"
STRUCTURED_FLOW_PROMPT_VERSION = "structured-v1.0"
CLINIC_PROFILE_SETTING_KEY = "clinic.profile"
CLINIC_TIMEZONE_SETTING_KEY = "clinic.timezone"
AI_KNOWLEDGE_BASE_SETTING_KEY = "ai_knowledge_base.global"
PREFERRED_NAME_CONTACT_CHANNEL = "preferred_name"
CPF_CONTACT_CHANNEL = "cpf"

DecisionIntent = Literal[
    "saudacao",
    "consultar_servico",
    "consultar_preco",
    "consultar_convenio",
    "consultar_unidade",
    "consultar_horarios",
    "agendar_consulta",
    "selecionar_horario",
    "confirmar_agendamento",
    "remarcar_consulta",
    "cancelar_consulta",
    "urgencia",
    "informar_dados_pessoais",
    "falar_com_humano",
    "fora_do_escopo",
    "outro",
]
PreferredPeriod = Literal["manha", "tarde", "noite", "final_do_dia", "qualquer"]
UpdateTarget = Literal["conversations", "patients", "patient_contacts", "leads"]
SystemActionName = Literal[
    "none",
    "validate_unit",
    "query_units",
    "query_service",
    "query_insurance",
    "query_availability",
    "validate_slot",
    "validate_and_hold_slot",
    "confirm_appointment",
    "reschedule_appointment",
    "cancel_appointment",
    "handoff_to_human",
]
ReplyDecision = Literal["reply", "handoff", "no_reply", "ask_clarification"]
MessageType = Literal["text", "interactive"]

ALLOWED_UPDATE_FIELDS: dict[str, set[str]] = {
    "conversations": {
        "status",
        "tags",
        "assigned_user_id",
        "unit_id",
        "ai_autoresponder_consecutive_count",
        "ai_autoresponder_last_decision",
        "ai_autoresponder_last_reason",
        "ai_autoresponder_last_at",
    },
    "patients": {"full_name", "email", "birth_date", "cpf", "normalized_cpf"},
    "patient_contacts": {"preferred_name", "cpf"},
    "leads": {"name", "email"},
}

DYNAMIC_INTENT_FALLBACK_ACTION: dict[str, SystemActionName] = {
    "consultar_unidade": "query_units",
    "consultar_servico": "query_service",
    "consultar_preco": "query_service",
    "consultar_convenio": "query_insurance",
    "consultar_horarios": "query_availability",
    "agendar_consulta": "query_availability",
    "selecionar_horario": "validate_slot",
    "confirmar_agendamento": "validate_slot",
    "remarcar_consulta": "validate_slot",
    "cancelar_consulta": "cancel_appointment",
}

ACTIVE_APPOINTMENT_STATUSES = {
    AppointmentStatus.SCHEDULED.value,
    AppointmentStatus.CONFIRMED.value,
    AppointmentStatus.RESCHEDULED.value,
}
EMAIL_ADAPTER = TypeAdapter(EmailStr)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClinicPoliciesContext(StrictModel):
    cancellation_policy: str | None = None
    reschedule_policy: str | None = None
    payment_policy: str | None = None
    documents_required: str | None = None


class ClinicContext(StrictModel):
    clinic_name: str
    timezone: str
    tone: str
    about: str | None = None
    city: str | None = None
    state: str | None = None
    address: str | None = None
    payment_methods: list[str] = Field(default_factory=list)
    accepted_insurance: list[str] = Field(default_factory=list)
    policies: ClinicPoliciesContext = Field(default_factory=ClinicPoliciesContext)


class BusinessHoursContext(StrictModel):
    timezone: str
    weekdays: list[str] = Field(default_factory=list)
    start: str
    end: str


class AutoresponderRulesContext(StrictModel):
    enabled: bool
    channel_whatsapp_enabled: bool
    business_hours: BusinessHoursContext
    outside_business_hours_mode: str
    max_consecutive_auto_replies: int
    confidence_threshold: float = Field(ge=0, le=1)
    human_queue_tag: str | None = None
    interactive_booking_options_enabled: bool


class RecentMessageContext(StrictModel):
    id: str
    direction: Literal["inbound", "outbound"]
    body: str
    interactive_reply: dict[str, Any] | None = None
    created_at: str | None = None


class ConversationContext(StrictModel):
    conversation_id: str
    channel: Literal["whatsapp"]
    status: str
    patient_id: str | None = None
    lead_id: str | None = None
    unit_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    assigned_user_id: str | None = None
    ai_autoresponder_enabled: bool
    ai_autoresponder_consecutive_count: int
    ai_autoresponder_last_decision: str | None = None
    ai_autoresponder_last_reason: str | None = None
    recent_messages: list[RecentMessageContext] = Field(default_factory=list)


class PatientContext(StrictModel):
    patient_id: str | None = None
    lead_id: str | None = None
    full_name: str | None = None
    preferred_name: str | None = None
    phone: str | None = None
    email: str | None = None
    birth_date: str | None = None
    has_cpf_on_file: bool = False


class UnitContext(StrictModel):
    id: str
    name: str
    code: str | None = None
    address: dict[str, Any] | str | None = None
    phone: str | None = None
    email: str | None = None
    working_hours: dict[str, Any] | str | None = None
    is_active: bool


class ServiceContext(StrictModel):
    id: str
    name: str
    description: str | None = None
    duration_minutes: int | None = None
    duration_note: str | None = None
    price_note: str | None = None
    is_active: bool = True


class ProfessionalSummaryContext(StrictModel):
    id: str
    unit_id: str
    full_name: str
    procedures: list[str] = Field(default_factory=list)
    working_days: list[str] = Field(default_factory=list)
    shift_start: str | None = None
    shift_end: str | None = None


class FAQContext(StrictModel):
    question: str
    answer: str


class CommercialPlaybookContext(StrictModel):
    value_proposition: str | None = None
    objection_handling: str | None = None
    default_cta: str | None = None


class EscalationContext(StrictModel):
    human_handoff_topics: list[str] = Field(default_factory=list)
    restricted_topics: list[str] = Field(default_factory=list)
    custom_urgent_keywords: list[str] = Field(default_factory=list)
    fallback_message: str | None = None


class KnowledgeBaseContext(StrictModel):
    faq: list[FAQContext] = Field(default_factory=list)
    commercial_playbook: CommercialPlaybookContext = Field(default_factory=CommercialPlaybookContext)
    escalation: EscalationContext = Field(default_factory=EscalationContext)


class BusinessContext(StrictModel):
    units: list[UnitContext] = Field(default_factory=list)
    services: list[ServiceContext] = Field(default_factory=list)
    professionals_summary: list[ProfessionalSummaryContext] = Field(default_factory=list)
    knowledge_base: KnowledgeBaseContext = Field(default_factory=KnowledgeBaseContext)


class SafetyRulesContext(StrictModel):
    can_confirm_appointment_without_database: bool = False
    can_invent_availability: bool = False
    can_invent_price: bool = False
    can_invent_professional: bool = False
    can_invent_unit: bool = False
    can_use_audit_logs_as_patient_answer_source: bool = False
    must_save_raw_message_first: bool = True
    must_validate_json_before_persistence: bool = True


class AiConversationContext(StrictModel):
    schema_version: Literal["1.0"] = STRUCTURED_FLOW_SCHEMA_VERSION
    clinic_context: ClinicContext
    autoresponder_rules: AutoresponderRulesContext
    conversation_context: ConversationContext
    patient_context: PatientContext
    business_context: BusinessContext
    safety_rules: SafetyRulesContext = Field(default_factory=SafetyRulesContext)


class PainData(StrictModel):
    has_pain: bool | None = None
    duration_text: str | None = None
    has_swelling: bool | None = None
    has_fever: bool | None = None
    urgency_level: Literal["baixa", "normal", "media", "alta", "emergencia", "desconhecida"] = "desconhecida"


class ExtractedData(StrictModel):
    patient_name: str | None = None
    responsible_name: str | None = None
    preferred_name: str | None = None
    phone: str | None = None
    email: str | None = None
    cpf: str | None = None
    birth_date: str | None = None
    unit_requested_text: str | None = None
    unit_id: str | None = None
    service_requested_text: str | None = None
    service_id: str | None = None
    procedure_type: str | None = None
    professional_requested_text: str | None = None
    professional_id: str | None = None
    preferred_date: str | None = None
    preferred_period: PreferredPeriod | None = None
    preferred_time_text: str | None = None
    selected_slot_id: str | None = None
    selected_datetime: str | None = None
    appointment_id: str | None = None
    pain: PainData = Field(default_factory=PainData)


class FieldUpdate(StrictModel):
    target: UpdateTarget
    field: str
    value: str | list[str] | int | None = None
    confidence: float = Field(ge=0, le=1)
    source_text: str | None = None
    should_apply: bool
    reason: str

    @model_validator(mode="after")
    def validate_allowed_field(self) -> "FieldUpdate":
        if self.field not in ALLOWED_UPDATE_FIELDS.get(self.target, set()):
            raise ValueError(f"field_updates.{self.target}.{self.field} is not allowed")
        return self


class AppointmentIntent(StrictModel):
    wants_booking: bool
    wants_reschedule: bool
    wants_cancel: bool
    procedure_type: str | None = None
    unit_id: str | None = None
    professional_id: str | None = None
    starts_at: str | None = None
    ends_at: str | None = None
    canceled_reason: str | None = None


class SystemActionParams(StrictModel):
    unit_id: str | None = None
    unit_name: str | None = None
    service_id: str | None = None
    procedure_type: str | None = None
    professional_id: str | None = None
    date: str | None = None
    time_after: str | None = None
    time_before: str | None = None
    period: str | None = None
    exclude_previously_offered: bool = False
    slot_id: str | None = None
    appointment_id: str | None = None
    hold_minutes: int = Field(default=10, ge=1, le=60)
    limit: int = Field(default=3, ge=1, le=10)


class SystemAction(StrictModel):
    required: bool
    action: SystemActionName
    params: SystemActionParams = Field(default_factory=SystemActionParams)


class ReplyControl(StrictModel):
    should_reply_now: bool
    reply_after_system_action: bool
    next_expected_field: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    suggested_next_question: str | None = None


class HandoffDecision(StrictModel):
    required: bool = False
    reason: str | None = None
    tag: str | None = None


class GuardrailsDecision(StrictModel):
    triggered: bool = False
    reason: str | None = None
    forbidden_topics_detected: list[str] = Field(default_factory=list)


class AiDecisionOutput(StrictModel):
    schema_version: Literal["1.0"]
    intent: DecisionIntent
    confidence: float = Field(ge=0, le=1)
    detected_language: str
    message_summary: str
    extracted_data: ExtractedData
    field_updates: list[FieldUpdate] = Field(default_factory=list)
    appointment_intent: AppointmentIntent
    system_action: SystemAction
    reply_control: ReplyControl
    handoff: HandoffDecision = Field(default_factory=HandoffDecision)
    guardrails: GuardrailsDecision = Field(default_factory=GuardrailsDecision)


class SafeAction(StrictModel):
    action: str
    params: dict[str, Any] = Field(default_factory=dict)


class LogsToCreate(StrictModel):
    ai_autoresponder_decisions: bool = True
    message_events: bool = True
    audit_logs: bool = True


class SafePersistencePlan(StrictModel):
    schema_version: Literal["1.0"] = STRUCTURED_FLOW_SCHEMA_VERSION
    message_id: str
    conversation_id: str
    lead_id: str | None = None
    patient_id: str | None = None
    safe_updates: dict[str, dict[str, Any]] = Field(
        default_factory=lambda: {
            "conversations": {},
            "patients": {},
            "patient_contacts": {},
            "leads": {},
            "appointments": {},
        }
    )
    system_actions_to_execute: list[SafeAction] = Field(default_factory=list)
    logs_to_create: LogsToCreate = Field(default_factory=LogsToCreate)
    risk_flags: list[str] = Field(default_factory=list)


class PatientReplyOutput(StrictModel):
    schema_version: Literal["1.0"]
    message: str
    message_type: MessageType
    interactive_payload: dict[str, Any] | None = None
    confidence: float = Field(ge=0, le=1)
    final_decision: ReplyDecision
    decision_reason: str

    @field_validator("message")
    @classmethod
    def message_must_not_be_empty(cls, value: str) -> str:
        text = " ".join(str(value or "").split())
        if not text:
            raise ValueError("message is required")
        return text


def validate_ai_decision_output(raw_output: Any) -> AiDecisionOutput:
    payload = _coerce_json_object(raw_output)
    try:
        return AiDecisionOutput.model_validate(payload)
    except ValidationError as strict_error:
        normalized = _normalize_legacy_ai_decision_payload(payload)
        if normalized is not None:
            return AiDecisionOutput.model_validate(normalized)
        raise strict_error


def validate_patient_reply_output(raw_output: Any) -> PatientReplyOutput:
    payload = _coerce_json_object(raw_output)
    try:
        return PatientReplyOutput.model_validate(payload)
    except ValidationError as strict_error:
        normalized = _normalize_legacy_patient_reply_payload(payload)
        if normalized is not None:
            return PatientReplyOutput.model_validate(normalized)
        raise strict_error


def build_safe_persistence_plan(
    *,
    decision: AiDecisionOutput,
    conversation: Conversation,
    inbound_message: Message,
    patient: Patient | None,
    lead: Lead | None,
    confidence_threshold: float,
    active_unit_ids: set[str] | None = None,
    active_service_ids: set[str] | None = None,
    active_professional_ids_by_unit: dict[str, set[str]] | None = None,
) -> SafePersistencePlan:
    plan = SafePersistencePlan(
        message_id=str(inbound_message.id),
        conversation_id=str(conversation.id),
        lead_id=str(conversation.lead_id) if conversation.lead_id else None,
        patient_id=str(conversation.patient_id) if conversation.patient_id else None,
    )
    active_unit_ids = active_unit_ids or set()
    active_service_ids = active_service_ids or set()
    active_professional_ids_by_unit = active_professional_ids_by_unit or {}

    for update in decision.field_updates:
        if not update.should_apply:
            plan.risk_flags.append(f"skipped_{update.target}.{update.field}:not_requested")
            continue
        if update.confidence < confidence_threshold:
            plan.risk_flags.append(f"skipped_{update.target}.{update.field}:low_confidence")
            continue
        if _is_empty_value(update.value):
            plan.risk_flags.append(f"skipped_{update.target}.{update.field}:empty_value")
            continue

        normalized_value = _normalize_update_value(update, plan)
        if _is_empty_value(normalized_value):
            continue
        if not _is_update_allowed_against_current_value(
            update=update,
            normalized_value=normalized_value,
            patient=patient,
            lead=lead,
        ):
            plan.risk_flags.append(f"skipped_{update.target}.{update.field}:existing_value_requires_confirmation")
            continue

        if update.target == "conversations" and update.field == "unit_id":
            unit_id = str(normalized_value)
            if unit_id not in active_unit_ids:
                plan.risk_flags.append("skipped_conversations.unit_id:unit_not_active")
                continue
        plan.safe_updates[update.target][update.field] = normalized_value

    appointment_intent = decision.appointment_intent
    if appointment_intent.unit_id and active_unit_ids and appointment_intent.unit_id not in active_unit_ids:
        plan.risk_flags.append("appointment_intent.unit_not_active")
    if decision.extracted_data.service_id and active_service_ids and decision.extracted_data.service_id not in active_service_ids:
        plan.risk_flags.append("extracted_data.service_not_active")
    if appointment_intent.professional_id and appointment_intent.unit_id:
        allowed = active_professional_ids_by_unit.get(appointment_intent.unit_id, set())
        if allowed and appointment_intent.professional_id not in allowed:
            plan.risk_flags.append("appointment_intent.professional_not_in_unit")

    action = _effective_system_action(decision)
    if action != "none" or decision.system_action.required:
        plan.system_actions_to_execute.append(
            SafeAction(action=action, params=decision.system_action.params.model_dump(mode="json"))
        )
    return plan


def build_ai_conversation_context(
    db: Session,
    *,
    tenant_id: UUID,
    conversation: Conversation,
    inbound_message: Message,
    config: dict[str, Any],
) -> AiConversationContext:
    patient = db.get(Patient, conversation.patient_id) if conversation.patient_id else None
    lead = db.get(Lead, conversation.lead_id) if conversation.lead_id else None
    preferred_name, contact_cpf_present = _load_safe_patient_contacts(db, tenant_id=tenant_id, patient_id=conversation.patient_id)
    clinic_profile = _load_clinic_profile(db, tenant_id=tenant_id)
    knowledge_base = _load_knowledge_base(db, tenant_id=tenant_id)
    services = _load_service_context(db, tenant_id=tenant_id)

    units = db.execute(
        select(Unit)
        .where(Unit.tenant_id == tenant_id, Unit.is_active.is_(True))
        .order_by(Unit.name.asc())
        .limit(30)
    ).scalars().all()
    professionals = db.execute(
        select(Professional)
        .where(Professional.tenant_id == tenant_id, Professional.is_active.is_(True))
        .order_by(Professional.full_name.asc())
        .limit(80)
    ).scalars().all()

    timezone = _first_text(
        clinic_profile.get("timezone"),
        _setting_scalar_value(db, tenant_id=tenant_id, key=CLINIC_TIMEZONE_SETTING_KEY),
        (config.get("business_hours") or {}).get("timezone"),
        settings.app_timezone,
    )
    clinic_name = _first_text(
        clinic_profile.get("clinic_name"),
        clinic_profile.get("legal_name"),
        (knowledge_base.get("clinic_profile") or {}).get("clinic_name") if isinstance(knowledge_base.get("clinic_profile"), dict) else None,
        "Clínica odontológica",
    )

    recent_messages = _recent_messages(db, conversation=conversation, include_message_id=inbound_message.id)
    business_hours = config.get("business_hours") if isinstance(config.get("business_hours"), dict) else {}
    policies = knowledge_base.get("operational_policies") if isinstance(knowledge_base.get("operational_policies"), dict) else {}
    commercial_playbook = (
        knowledge_base.get("commercial_playbook") if isinstance(knowledge_base.get("commercial_playbook"), dict) else {}
    )
    escalation = knowledge_base.get("escalation") if isinstance(knowledge_base.get("escalation"), dict) else {}

    return AiConversationContext(
        clinic_context=ClinicContext(
            clinic_name=clinic_name,
            timezone=timezone,
            tone=str(config.get("tone") or "profissional, cordial e objetivo"),
            about=_first_text(clinic_profile.get("about"), (knowledge_base.get("clinic_profile") or {}).get("about") if isinstance(knowledge_base.get("clinic_profile"), dict) else None),
            city=_optional_text(clinic_profile.get("city")),
            state=_optional_text(clinic_profile.get("state")),
            address=_compose_address(clinic_profile),
            payment_methods=_as_text_list(clinic_profile.get("payment_methods")),
            accepted_insurance=_as_text_list(clinic_profile.get("accepted_insurance")) or _as_text_list(
                (knowledge_base.get("insurance") or {}).get("accepted_plans") if isinstance(knowledge_base.get("insurance"), dict) else None
            ),
            policies=ClinicPoliciesContext(
                cancellation_policy=_first_text(clinic_profile.get("cancellation_policy"), policies.get("cancellation_policy")),
                reschedule_policy=_first_text(clinic_profile.get("reschedule_policy"), policies.get("reschedule_policy")),
                payment_policy=_optional_text(policies.get("payment_policy")),
                documents_required=_optional_text(policies.get("documents_required")),
            ),
        ),
        autoresponder_rules=AutoresponderRulesContext(
            enabled=bool(config.get("enabled")),
            channel_whatsapp_enabled=bool((config.get("channels") or {}).get("whatsapp")),
            business_hours=BusinessHoursContext(
                timezone=str(business_hours.get("timezone") or timezone),
                weekdays=[str(day) for day in (business_hours.get("weekdays") or [])],
                start=str(business_hours.get("start") or "08:00"),
                end=str(business_hours.get("end") or "18:00"),
            ),
            outside_business_hours_mode=str(config.get("outside_business_hours_mode") or "allow"),
            max_consecutive_auto_replies=int(config.get("max_consecutive_auto_replies") or 3),
            confidence_threshold=float(config.get("confidence_threshold") or 0.65),
            human_queue_tag=_optional_text(config.get("human_queue_tag")),
            interactive_booking_options_enabled=bool(config.get("interactive_booking_options_enabled", True)),
        ),
        conversation_context=ConversationContext(
            conversation_id=str(conversation.id),
            channel="whatsapp",
            status=str(conversation.status),
            patient_id=str(conversation.patient_id) if conversation.patient_id else None,
            lead_id=str(conversation.lead_id) if conversation.lead_id else None,
            unit_id=str(conversation.unit_id) if conversation.unit_id else None,
            tags=[str(tag) for tag in (conversation.tags or [])],
            assigned_user_id=str(conversation.assigned_user_id) if conversation.assigned_user_id else None,
            ai_autoresponder_enabled=conversation.ai_autoresponder_enabled is not False,
            ai_autoresponder_consecutive_count=int(conversation.ai_autoresponder_consecutive_count or 0),
            ai_autoresponder_last_decision=conversation.ai_autoresponder_last_decision,
            ai_autoresponder_last_reason=conversation.ai_autoresponder_last_reason,
            recent_messages=recent_messages,
        ),
        patient_context=PatientContext(
            patient_id=str(patient.id) if patient else None,
            lead_id=str(lead.id) if lead else None,
            full_name=_optional_text(patient.full_name if patient else None),
            preferred_name=preferred_name,
            phone=_optional_text(patient.phone if patient else lead.phone if lead else None),
            email=_optional_text(patient.email if patient else lead.email if lead else None),
            birth_date=patient.birth_date.isoformat() if patient and patient.birth_date else None,
            has_cpf_on_file=bool((patient and patient.cpf) or (patient and patient.normalized_cpf) or contact_cpf_present),
        ),
        business_context=BusinessContext(
            units=[
                UnitContext(
                    id=str(unit.id),
                    name=unit.name,
                    code=unit.code,
                    address=unit.address if isinstance(unit.address, dict) else None,
                    phone=unit.phone,
                    email=unit.email,
                    working_hours=unit.working_hours if isinstance(unit.working_hours, dict) else None,
                    is_active=bool(unit.is_active),
                )
                for unit in units
            ],
            services=services,
            professionals_summary=[
                ProfessionalSummaryContext(
                    id=str(professional.id),
                    unit_id=str(professional.unit_id) if professional.unit_id else "",
                    full_name=professional.full_name,
                    procedures=[str(item) for item in (professional.procedures or [])],
                    working_days=[str(item) for item in (professional.working_days or [])],
                    shift_start=professional.shift_start,
                    shift_end=professional.shift_end,
                )
                for professional in professionals
                if professional.unit_id
            ],
            knowledge_base=KnowledgeBaseContext(
                faq=[
                    FAQContext(question=_compact(item.get("question"), 240), answer=_compact(item.get("answer"), 700))
                    for item in (knowledge_base.get("faq") if isinstance(knowledge_base.get("faq"), list) else [])
                    if isinstance(item, dict) and _compact(item.get("question"), 240) and _compact(item.get("answer"), 700)
                ][:20],
                commercial_playbook=CommercialPlaybookContext(
                    value_proposition=_optional_text(commercial_playbook.get("value_proposition")),
                    objection_handling=_optional_text(commercial_playbook.get("objection_handling")),
                    default_cta=_optional_text(commercial_playbook.get("default_cta")),
                ),
                escalation=EscalationContext(
                    human_handoff_topics=_as_text_list(escalation.get("human_handoff_topics")),
                    restricted_topics=_as_text_list(escalation.get("restricted_topics")),
                    custom_urgent_keywords=_as_text_list(escalation.get("custom_urgent_keywords")),
                    fallback_message=_optional_text(escalation.get("fallback_message")),
                ),
            ),
        ),
    )


def process_structured_inbound_message(
    db: Session,
    *,
    tenant_id: UUID,
    conversation: Conversation,
    inbound_message: Message,
    config: dict[str, Any],
    dedupe_key: str,
) -> dict[str, Any]:
    inbound_text = (inbound_message.body or "").strip()
    if not inbound_text:
        return _finish_without_outbound(
            db,
            tenant_id=tenant_id,
            conversation=conversation,
            inbound_message=inbound_message,
            dedupe_key=dedupe_key,
            config=config,
            final_decision="ignored",
            decision_reason="empty_inbound",
            metadata={"structured_flow": True},
        )

    if conversation.status == "finalizada":
        conversation.status = "aberta"
        conversation.ai_autoresponder_consecutive_count = 0
        conversation.ai_autoresponder_last_decision = None
        conversation.ai_autoresponder_last_reason = "reopened_by_new_inbound"
        conversation.ai_autoresponder_last_at = datetime.now(UTC)
        db.add(conversation)
        db.commit()

    if int(conversation.ai_autoresponder_consecutive_count or 0) >= int(config.get("max_consecutive_auto_replies") or 3):
        return _handoff(
            db,
            tenant_id=tenant_id,
            conversation=conversation,
            inbound_message=inbound_message,
            dedupe_key=dedupe_key,
            config=config,
            reason="max_consecutive_reached",
            guardrail=None,
        )

    if not _is_business_hours(config) and str(config.get("outside_business_hours_mode") or "allow") == "handoff":
        return _handoff(
            db,
            tenant_id=tenant_id,
            conversation=conversation,
            inbound_message=inbound_message,
            dedupe_key=dedupe_key,
            config=config,
            reason="outside_business_hours",
            guardrail=None,
        )

    if conversation.channel == "whatsapp":
        try:
            assert_whatsapp_account_ready_for_dispatch(db, tenant_id=tenant_id)
        except Exception:
            return _handoff(
                db,
                tenant_id=tenant_id,
                conversation=conversation,
                inbound_message=inbound_message,
                dedupe_key=dedupe_key,
                config=config,
                reason="whatsapp_not_ready",
                guardrail=None,
            )

    context = build_ai_conversation_context(
        db,
        tenant_id=tenant_id,
        conversation=conversation,
        inbound_message=inbound_message,
        config=config,
    )
    db.add(
        MessageEvent(
            tenant_id=tenant_id,
            message_id=inbound_message.id,
            event_type="ai_structured_flow_started",
            payload={"schema_version": STRUCTURED_FLOW_SCHEMA_VERSION},
        )
    )
    db.commit()

    extractor_payload: dict[str, Any] | None = None
    try:
        decision, extractor_payload = _run_extractor_with_retry(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            inbound_text=inbound_text,
            context=context,
        )
    except (ValidationError, ValueError) as exc:
        return _invalid_contract_fallback(
            db,
            tenant_id=tenant_id,
            conversation=conversation,
            inbound_message=inbound_message,
            dedupe_key=dedupe_key,
            config=config,
            extractor_payload=extractor_payload,
            validation_error=str(exc),
        )
    except Exception as exc:
        logger.exception(
            "ai_structured_flow.extractor_failed",
            tenant_id=str(tenant_id),
            conversation_id=str(conversation.id),
            error=str(exc),
        )
        return _handoff(
            db,
            tenant_id=tenant_id,
            conversation=conversation,
            inbound_message=inbound_message,
            dedupe_key=dedupe_key,
            config=config,
            reason="structured_extractor_error",
            guardrail=None,
        )

    patient = db.get(Patient, conversation.patient_id) if conversation.patient_id else None
    lead = db.get(Lead, conversation.lead_id) if conversation.lead_id else None
    active_units = {unit.id: unit for unit in _active_units(db, tenant_id=tenant_id)}
    active_services = {
        str(item["id"]): item
        for item in get_service_catalog_items(db, tenant_id=tenant_id)
        if item.get("is_active", True)
    }
    professional_ids_by_unit = _active_professional_ids_by_unit(db, tenant_id=tenant_id)
    plan = build_safe_persistence_plan(
        decision=decision,
        conversation=conversation,
        inbound_message=inbound_message,
        patient=patient,
        lead=lead,
        confidence_threshold=float(config.get("confidence_threshold") or 0.65),
        active_unit_ids={str(unit_id) for unit_id in active_units},
        active_service_ids=set(active_services),
        active_professional_ids_by_unit=professional_ids_by_unit,
    )

    applied_updates = _apply_safe_updates(
        db,
        tenant_id=tenant_id,
        plan=plan,
        conversation=conversation,
        patient=patient,
        lead=lead,
        decision=decision,
    )
    system_action_result = _execute_safe_system_actions(
        db,
        tenant_id=tenant_id,
        conversation=conversation,
        inbound_message=inbound_message,
        decision=decision,
        plan=plan,
        context=context,
        config=config,
    )

    if decision.handoff.required or decision.guardrails.triggered or system_action_result.get("handoff_required"):
        return _handoff(
            db,
            tenant_id=tenant_id,
            conversation=conversation,
            inbound_message=inbound_message,
            dedupe_key=dedupe_key,
            config=config,
            reason=decision.handoff.reason or decision.guardrails.reason or system_action_result.get("reason") or "structured_handoff",
            guardrail=decision.guardrails.reason,
            extractor_payload=extractor_payload,
            reply_text=_handoff_notice_text(
                decision=decision,
                context=context,
                reason=decision.handoff.reason or decision.guardrails.reason or system_action_result.get("reason"),
            ),
            metadata={
                "structured_flow": True,
                "plan": plan.model_dump(mode="json"),
                "applied_updates": applied_updates,
                "system_action_result": system_action_result,
            },
        )

    reply_payload: dict[str, Any] | None = None
    try:
        patient_reply, reply_payload = _run_reply_generator(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            context=context,
            decision=decision,
            plan=plan,
            system_action_result=system_action_result,
        )
    except Exception as exc:
        logger.warning(
            "ai_structured_flow.reply_generator_failed",
            tenant_id=str(tenant_id),
            conversation_id=str(conversation.id),
            error=str(exc),
        )
        patient_reply = _fallback_patient_reply(decision=decision, system_action_result=system_action_result, context=context)

    if patient_reply.final_decision == "handoff":
        return _handoff(
            db,
            tenant_id=tenant_id,
            conversation=conversation,
            inbound_message=inbound_message,
            dedupe_key=dedupe_key,
            config=config,
            reason=patient_reply.decision_reason,
            guardrail=None,
            extractor_payload=extractor_payload,
            reply_payload=reply_payload,
            metadata={
                "structured_flow": True,
                "plan": plan.model_dump(mode="json"),
                "applied_updates": applied_updates,
                "system_action_result": system_action_result,
            },
            reply_text=patient_reply.message,
        )

    if patient_reply.final_decision == "no_reply":
        return _finish_without_outbound(
            db,
            tenant_id=tenant_id,
            conversation=conversation,
            inbound_message=inbound_message,
            dedupe_key=dedupe_key,
            config=config,
            final_decision="ignored",
            decision_reason=patient_reply.decision_reason,
            confidence=patient_reply.confidence,
            llm_payload=reply_payload or extractor_payload,
            metadata={
                "structured_flow": True,
                "plan": plan.model_dump(mode="json"),
                "applied_updates": applied_updates,
                "system_action_result": system_action_result,
            },
        )

    return _dispatch_patient_reply(
        db,
        tenant_id=tenant_id,
        conversation=conversation,
        inbound_message=inbound_message,
        dedupe_key=dedupe_key,
        config=config,
        context=context,
        patient_reply=patient_reply,
        decision=decision,
        plan=plan,
        applied_updates=applied_updates,
        system_action_result=system_action_result,
        extractor_payload=extractor_payload,
        reply_payload=reply_payload,
    )


def _run_extractor_with_retry(
    db: Session,
    *,
    tenant_id: UUID,
    conversation_id: UUID | None,
    inbound_text: str,
    context: AiConversationContext,
) -> tuple[AiDecisionOutput, dict[str, Any]]:
    prompt = _extractor_prompt(context=context, inbound_text=inbound_text)
    last_payload: dict[str, Any] | None = None
    last_error: Exception | None = None
    for attempt in range(2):
        llm_prompt = prompt
        if attempt:
            llm_prompt = (
                f"{prompt}\n\n"
                "A saída anterior foi inválida. Retorne novamente somente JSON válido, sem campos extras, "
                "seguindo exatamente o contrato AiDecisionOutput."
            )
        result = run_llm_task(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            task="auto_responder_structured_extract",
            prompt=llm_prompt,
        )
        last_payload = {"prompt": llm_prompt, **result}
        try:
            decision = validate_ai_decision_output(result.get("output"))
            decision = _enrich_decision_with_first_message_context_hints(
                db=db,
                tenant_id=tenant_id,
                decision=decision,
                inbound_text=inbound_text,
                context=context,
            )
            decision = _enrich_decision_with_recent_availability_hints(
                db=db,
                tenant_id=tenant_id,
                decision=decision,
                inbound_text=inbound_text,
                context=context,
            )
            decision = _enrich_decision_with_selection_hints(
                db=db,
                tenant_id=tenant_id,
                decision=decision,
                inbound_text=inbound_text,
                context=context,
            )
            decision = _enrich_decision_with_personal_data_hints(
                decision=decision,
                inbound_text=inbound_text,
                context=context,
            )
            return decision, last_payload
        except (ValidationError, ValueError) as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise ValueError("extractor returned no output")


def _run_reply_generator(
    db: Session,
    *,
    tenant_id: UUID,
    conversation_id: UUID | None,
    context: AiConversationContext,
    decision: AiDecisionOutput,
    plan: SafePersistencePlan,
    system_action_result: dict[str, Any],
) -> tuple[PatientReplyOutput, dict[str, Any]]:
    prompt = _reply_prompt(
        context=context,
        decision=decision,
        plan=plan,
        system_action_result=system_action_result,
    )
    result = run_llm_task(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        task="auto_responder_structured_reply",
        prompt=prompt,
    )
    payload = {"prompt": prompt, **result}
    try:
        patient_reply = validate_patient_reply_output(result.get("output"))
        patient_reply, guardrail_reason = _apply_structured_reply_guardrail(
            patient_reply=patient_reply,
            decision=decision,
            system_action_result=system_action_result,
            context=context,
        )
        if guardrail_reason:
            metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
            payload["metadata"] = {
                **metadata,
                "reply_guardrail_applied": True,
                "reply_guardrail_reason": guardrail_reason,
            }
        patient_reply = _humanize_structured_patient_reply(patient_reply)
        return patient_reply, payload
    except ValidationError:
        return _fallback_patient_reply(decision=decision, system_action_result=system_action_result, context=context), payload


def _normalized_reply_guardrail_text(value: Any) -> str:
    return _strip_accents(" ".join(str(value or "").casefold().split()))


def _remove_robotic_reply_closers(text: str) -> str:
    output = text
    trailing_patterns = (
        r"(?:[.!]\s*)?qualquer d[uú]vida,?\s+(?:estou|estamos)\s+[àa]\s+disposi[cç][aã]o[.!]*\s*$",
        r"(?:[.!]\s*)?fico no aguardo(?:\s+do seu retorno)?[.!]*\s*$",
        r"(?:[.!]\s*)?aguardo seu retorno[.!]*\s*$",
        r"(?:[.!]\s*)?se precisar,?\s+[ée]\s+s[oó]\s+me chamar[.!]*\s*$",
    )
    for pattern in trailing_patterns:
        output = re.sub(pattern, "", output, flags=re.IGNORECASE).strip()
    return output


def _humanize_structured_reply_text(text: str) -> str:
    output = str(text or "").strip()
    if not output:
        return ""

    output = output.replace(" | ", "\n")
    output = re.sub(r"\s+(?=\d+\)\s)", "\n", output)
    output = re.sub(r"\n{3,}", "\n\n", output)
    output = re.sub(
        r"^(Perfeito|Ótimo|Otimo|Certo|Combinado|Claro|Entendi)[!,.:\s-]+(?=(Perfeito|Ótimo|Otimo|Certo|Combinado|Claro|Entendi)\b)",
        "",
        output,
        flags=re.IGNORECASE,
    ).strip()

    lines: list[str] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if lines and _normalized_reply_guardrail_text(lines[-1]) == _normalized_reply_guardrail_text(line):
            continue
        lines.append(line)
    output = "\n".join(lines).strip()
    output = _remove_robotic_reply_closers(output)

    if len(output) > 1500:
        output = f"{output[:1500].rstrip()}..."
    return output


def _humanize_structured_patient_reply(patient_reply: PatientReplyOutput) -> PatientReplyOutput:
    normalized_message = _humanize_structured_reply_text(patient_reply.message)
    if normalized_message and normalized_message != patient_reply.message:
        return patient_reply.model_copy(update={"message": normalized_message})
    return patient_reply


def _reply_contains_negative_availability_claim(message: str) -> bool:
    normalized = _normalized_reply_guardrail_text(message)
    negative_markers = (
        "nao temos horario",
        "nao temos horarios",
        "nao encontrei horario",
        "nao encontrei horarios",
        "sem horario disponivel",
        "sem horarios disponiveis",
        "nenhum horario disponivel",
        "nenhum horario livre",
    )
    return any(marker in normalized for marker in negative_markers)


def _reply_mentions_any_available_slot(message: str, slots: list[dict[str, Any]], *, timezone_name: str) -> bool:
    normalized = _normalized_reply_guardrail_text(message)
    timezone = _timezone(timezone_name)
    for slot in slots:
        label = str(slot.get("label") or "").strip()
        if label and _normalized_reply_guardrail_text(label) in normalized:
            return True
        starts_at = _parse_slot_datetime(slot.get("starts_at"))
        if not starts_at:
            continue
        local = starts_at.astimezone(timezone)
        if local.strftime("%H:%M") in normalized:
            return True
    return False


def _reply_claims_slot_confirmation(message: str) -> bool:
    normalized = _normalized_reply_guardrail_text(message)
    confirmation_markers = (
        "separei",
        "reservei",
        "reservado",
        "confirmado",
        "agendado",
        "horario de",
    )
    return any(marker in normalized for marker in confirmation_markers)


def _reply_claims_booking_confirmation(message: str) -> bool:
    normalized = _normalized_reply_guardrail_text(message)
    confirmation_markers = (
        "agendei",
        "agendamento confirmado",
        "seu agendamento esta confirmado",
        "confirmei seu agendamento",
        "consulta confirmada",
        "marquei para voce",
    )
    return any(marker in normalized for marker in confirmation_markers)


def _looks_like_placeholder_name(value: Any) -> bool:
    normalized = _normalized_reply_guardrail_text(value)
    return normalized in {
        "paciente ia lab",
        "paciente teste ia lab",
        "lead ia lab",
        "lead teste ia lab",
    }


def _reply_mentions_selected_slot_time(
    message: str,
    *,
    system_action_result: dict[str, Any],
    context: AiConversationContext,
) -> bool:
    starts_at = _parse_slot_datetime(system_action_result.get("starts_at"))
    if not starts_at:
        return False
    local = starts_at.astimezone(_timezone(context.clinic_context.timezone))
    normalized = _normalized_reply_guardrail_text(message)
    return local.strftime("%H:%M") in normalized or local.strftime("%d/%m") in normalized or local.strftime("%d/%m/%Y") in normalized


def _reply_restarts_scheduling_after_slot_confirmation(message: str) -> bool:
    normalized = _normalized_reply_guardrail_text(message)
    restart_markers = (
        "qual unidade",
        "em qual unidade",
        "qual periodo",
        "prefere atendimento em qual unidade",
        "manha, tarde ou noite",
        "manha ou tarde",
        "outro periodo",
        "outro dia",
    )
    return any(marker in normalized for marker in restart_markers)


def _apply_structured_reply_guardrail(
    *,
    patient_reply: PatientReplyOutput,
    decision: AiDecisionOutput,
    system_action_result: dict[str, Any],
    context: AiConversationContext,
) -> tuple[PatientReplyOutput, str | None]:
    action = str(system_action_result.get("action") or "")
    if action == "query_availability":
        slots = system_action_result.get("slots") if isinstance(system_action_result.get("slots"), list) else []
        if slots:
            if _reply_contains_negative_availability_claim(patient_reply.message):
                return (
                    _fallback_patient_reply(
                        decision=decision,
                        system_action_result=system_action_result,
                        context=context,
                    ),
                    "availability_reply_contradicted_slots",
                )
            if not _reply_mentions_any_available_slot(
                patient_reply.message,
                slots,
                timezone_name=context.clinic_context.timezone,
            ):
                return (
                    _fallback_patient_reply(
                        decision=decision,
                        system_action_result=system_action_result,
                        context=context,
                    ),
                    "availability_reply_missing_slot_options",
                )
        return patient_reply, None
    if action in {"validate_slot", "validate_and_hold_slot"}:
        status = str(system_action_result.get("status") or "")
        if status in {"available", "held"} and _reply_contains_negative_availability_claim(patient_reply.message):
            return (
                _fallback_patient_reply(
                    decision=decision,
                    system_action_result=system_action_result,
                    context=context,
                ),
                "validated_slot_reply_marked_unavailable",
            )
        if status in {"available", "held"} and _reply_claims_booking_confirmation(patient_reply.message):
            return (
                _fallback_patient_reply(
                    decision=decision,
                    system_action_result=system_action_result,
                    context=context,
                ),
                "validated_slot_reply_confirmed_booking",
            )
        reply_times = re.findall(r"\b\d{1,2}:\d{2}\b", patient_reply.message)
        if status in {"available", "held"} and reply_times and not _reply_mentions_selected_slot_time(
            patient_reply.message,
            system_action_result=system_action_result,
            context=context,
        ):
            return (
                _fallback_patient_reply(
                    decision=decision,
                    system_action_result=system_action_result,
                    context=context,
                ),
                "validated_slot_reply_wrong_time",
            )
        if status not in {"available", "held"} and _reply_claims_slot_confirmation(patient_reply.message):
            return (
                _fallback_patient_reply(
                    decision=decision,
                    system_action_result=system_action_result,
                    context=context,
                ),
                "unavailable_slot_reply_marked_confirmed",
            )
    if (
        action == "none"
        and decision.intent == "informar_dados_pessoais"
        and decision.reply_control.suggested_next_question
        and _pending_slot_confirmation_request(context) is not None
        and _reply_restarts_scheduling_after_slot_confirmation(patient_reply.message)
    ):
        return (
            _fallback_patient_reply(
                decision=decision,
                system_action_result=system_action_result,
                context=context,
            ),
            "personal_data_reply_lost_slot_context",
        )
    return patient_reply, None


def _extractor_prompt(*, context: AiConversationContext, inbound_text: str) -> str:
    return (
        "Você é o motor de análise estruturada do OdontoFlux.\n"
        "Leia a mensagem atual do paciente, o histórico recente e o contexto permitido, e retorne SOMENTE um JSON "
        "válido conforme o schema AiDecisionOutput.\n"
        "Você não conversa com o paciente. Você não gera resposta final. Você não salva dados. Você não consulta banco.\n"
        "Seu objetivo é entender intenção, extrair dados e sugerir a próxima ação segura para atendimento odontológico.\n"
        "Regras obrigatórias:\n"
        "- Não invente campos, unidades, horários, preços, convênios, endereços ou profissionais.\n"
        "- Quando depender de agenda, unidade, serviço, preço, convênio, profissional, status de consulta, cancelamento ou remarcação, marque system_action.required=true.\n"
        "- Para consulta de horários ou agendamento, use query_availability antes de qualquer oferta de horário.\n"
        "- Para escolha de horário, use validate_slot ou validate_and_hold_slot; nunca confirme sem validação.\n"
        "- Para preço ou procedimento, use query_service quando precisar confirmar cadastro ou price_note.\n"
        "- Se o paciente pedir humano, estiver irritado, houver reclamação, urgência relevante ou baixa confiança, marque handoff.required=true.\n"
        "- Em dor, febre, inchaço, pus, trauma, sangramento ou dor intensa, classifique como urgencia e preencha pain sem diagnosticar.\n"
        "- Use confidence realista; dados incertos não devem ser aplicados automaticamente.\n"
        "- Nunca sugira field_updates fora dos campos permitidos e nunca sobrescreva dados com null ou vazio.\n"
        "- Nunca confirme agendamento; a IA apenas informa intenção e sugere ação.\n"
        "- Retorne apenas uma intenção principal e uma ação de sistema principal.\n\n"
        "ENUM intent: saudacao, consultar_servico, consultar_preco, consultar_convenio, consultar_unidade, "
        "consultar_horarios, agendar_consulta, selecionar_horario, confirmar_agendamento, remarcar_consulta, "
        "cancelar_consulta, urgencia, informar_dados_pessoais, falar_com_humano, fora_do_escopo, outro.\n"
        "ENUM system_action.action: none, validate_unit, query_units, query_service, query_insurance, query_availability, "
        "validate_slot, validate_and_hold_slot, confirm_appointment, reschedule_appointment, cancel_appointment, "
        "handoff_to_human.\n\n"
        "CONTEXT_ALLOWED_JSON:\n"
        f"{json.dumps(context.model_dump(mode='json'), ensure_ascii=False)}\n\n"
        f"MENSAGEM_ATUAL: {inbound_text}\n\n"
        "Retorne somente AiDecisionOutput JSON válido, sem markdown."
    )


def _reply_prompt(
    *,
    context: AiConversationContext,
    decision: AiDecisionOutput,
    plan: SafePersistencePlan,
    system_action_result: dict[str, Any],
) -> str:
    return (
        "Você é a recepcionista virtual humanizada de uma clínica odontológica.\n"
        "Responda pelo WhatsApp de forma simpática, objetiva e segura usando somente dados permitidos, validados e "
        "retornados pelo backend.\n"
        "Objetivo da conversa: acolher, entender, qualificar e conduzir para o próximo passo de agendamento sem parecer robótica.\n"
        "Regras de resposta:\n"
        "- Fale curto, humano e profissional, como recepção odontológica experiente.\n"
        "- Faça uma pergunta por vez e não transforme a conversa em formulário.\n"
        "- Sempre que possível termine com CTA claro: verificar horário, escolher período, escolher unidade ou confirmar dado faltante.\n"
        "- Não encerre com 'qualquer dúvida estamos à disposição' quando ainda houver próximo passo comercial.\n"
        "- Não invente horários, preço, convênio, profissional, endereço ou confirmação de consulta.\n"
        "- Use somente horários retornados em SYSTEM_ACTION_RESULT_JSON e liste no máximo 3 opções.\n"
        "- Se preço não estiver configurado, explique que varia conforme avaliação e convide para verificar horário.\n"
        "- Em urgência, acolha, não diagnostique e encaminhe humano quando o fluxo indicar.\n"
        "- Não mencione JSON, banco, schema, backend, API, prompt ou sistema.\n"
        "- Retorne somente PatientReplyOutput JSON válido.\n\n"
        "CONTEXT_ALLOWED_JSON:\n"
        f"{json.dumps(context.model_dump(mode='json'), ensure_ascii=False)}\n\n"
        "AI_DECISION_JSON:\n"
        f"{json.dumps(decision.model_dump(mode='json'), ensure_ascii=False)}\n\n"
        "SAFE_PERSISTENCE_PLAN_JSON:\n"
        f"{json.dumps(plan.model_dump(mode='json'), ensure_ascii=False)}\n\n"
        "SYSTEM_ACTION_RESULT_JSON:\n"
        f"{json.dumps(system_action_result, ensure_ascii=False, default=str)}\n\n"
        "Retorne somente PatientReplyOutput JSON válido, sem markdown."
    )


def _active_units(db: Session, *, tenant_id: UUID) -> list[Unit]:
    return db.execute(
        select(Unit).where(Unit.tenant_id == tenant_id, Unit.is_active.is_(True)).order_by(Unit.name.asc())
    ).scalars().all()


def _active_professional_ids_by_unit(db: Session, *, tenant_id: UUID) -> dict[str, set[str]]:
    rows = db.execute(
        select(Professional).where(Professional.tenant_id == tenant_id, Professional.is_active.is_(True))
    ).scalars().all()
    output: dict[str, set[str]] = {}
    for professional in rows:
        if not professional.unit_id:
            continue
        output.setdefault(str(professional.unit_id), set()).add(str(professional.id))
    return output


def _apply_safe_updates(
    db: Session,
    *,
    tenant_id: UUID,
    plan: SafePersistencePlan,
    conversation: Conversation,
    patient: Patient | None,
    lead: Lead | None,
    decision: AiDecisionOutput,
) -> dict[str, Any]:
    applied: dict[str, Any] = {"conversations": {}, "patients": {}, "patient_contacts": {}, "leads": {}}
    for field, value in plan.safe_updates.get("conversations", {}).items():
        if not hasattr(conversation, field):
            continue
        setattr(conversation, field, value)
        applied["conversations"][field] = value
    if applied["conversations"]:
        db.add(conversation)

    if patient:
        for field, value in plan.safe_updates.get("patients", {}).items():
            if not hasattr(patient, field):
                continue
            if field == "birth_date" and isinstance(value, str):
                parsed_date = _parse_birth_date(value)
                if parsed_date is None:
                    continue
                value = parsed_date
            setattr(patient, field, value)
            applied["patients"][field] = value.isoformat() if isinstance(value, date) else value
        if applied["patients"]:
            db.add(patient)

    if lead:
        for field, value in plan.safe_updates.get("leads", {}).items():
            if not hasattr(lead, field):
                continue
            setattr(lead, field, value)
            applied["leads"][field] = value
        if applied["leads"]:
            db.add(lead)

    if patient:
        for channel, value in plan.safe_updates.get("patient_contacts", {}).items():
            contact_channel = PREFERRED_NAME_CONTACT_CHANNEL if channel == "preferred_name" else CPF_CONTACT_CHANNEL
            contact = db.scalar(
                select(PatientContact).where(
                    PatientContact.tenant_id == tenant_id,
                    PatientContact.patient_id == patient.id,
                    PatientContact.channel == contact_channel,
                )
            )
            normalized_value = _normalize_cpf(value) if contact_channel == CPF_CONTACT_CHANNEL else str(value)
            if not contact:
                contact = PatientContact(
                    tenant_id=tenant_id,
                    patient_id=patient.id,
                    channel=contact_channel,
                    value=str(value),
                    normalized_value=normalized_value,
                    is_primary=False,
                    is_verified=False,
                )
            else:
                contact.value = str(value)
                contact.normalized_value = normalized_value
            db.add(contact)
            applied["patient_contacts"][channel] = str(value)

    if any(applied.values()):
        db.add(
            MessageEvent(
                tenant_id=tenant_id,
                message_id=UUID(plan.message_id),
                event_type="ai_structured_safe_updates_applied",
                payload={"applied": applied, "risk_flags": plan.risk_flags},
            )
        )
        db.commit()
        record_audit(
            db,
            action="ai_autoresponder.structured_safe_update",
            entity_type="conversation",
            entity_id=str(conversation.id),
            tenant_id=tenant_id,
            user_id=None,
            metadata={
                "message_id": plan.message_id,
                "applied": applied,
                "risk_flags": plan.risk_flags,
                "intent": decision.intent,
            },
        )
    return applied


def _execute_safe_system_actions(
    db: Session,
    *,
    tenant_id: UUID,
    conversation: Conversation,
    inbound_message: Message,
    decision: AiDecisionOutput,
    plan: SafePersistencePlan,
    context: AiConversationContext,
    config: dict[str, Any],
) -> dict[str, Any]:
    if not plan.system_actions_to_execute:
        return {"action": "none", "status": "skipped"}
    results: list[dict[str, Any]] = []
    for safe_action in plan.system_actions_to_execute:
        result = _execute_system_action(
            db,
            tenant_id=tenant_id,
            conversation=conversation,
            inbound_message=inbound_message,
            decision=decision,
            action=safe_action.action,
            params=safe_action.params,
            context=context,
            config=config,
        )
        results.append(result)
        db.add(
            MessageEvent(
                tenant_id=tenant_id,
                message_id=inbound_message.id,
                event_type="ai_structured_system_action_executed",
                payload={"action": safe_action.action, "result": result},
            )
        )
        db.commit()
    return results[-1] if len(results) == 1 else {"action": "multiple", "status": "ok", "results": results}


def _execute_system_action(
    db: Session,
    *,
    tenant_id: UUID,
    conversation: Conversation,
    inbound_message: Message,
    decision: AiDecisionOutput,
    action: str,
    params: dict[str, Any],
    context: AiConversationContext,
    config: dict[str, Any],
) -> dict[str, Any]:
    if action == "none":
        return {"action": "none", "status": "ok"}
    if action == "validate_unit":
        unit = _resolve_unit(db, tenant_id=tenant_id, unit_id=params.get("unit_id"), unit_name=params.get("unit_name"))
        return {
            "action": action,
            "status": "ok" if unit else "not_found",
            "unit": _unit_payload(unit) if unit else None,
        }
    if action == "query_units":
        return {
            "action": action,
            "status": "ok",
            "units": [_unit_payload(unit) for unit in _active_units(db, tenant_id=tenant_id)],
        }
    if action == "query_service":
        service = _resolve_service(db, tenant_id=tenant_id, service_id=params.get("service_id"), procedure_type=params.get("procedure_type") or decision.extracted_data.service_requested_text)
        return {
            "action": action,
            "status": "ok" if service else "not_found",
            "service": service,
        }
    if action == "query_insurance":
        return {
            "action": action,
            "status": "ok",
            "accepted_insurance": context.clinic_context.accepted_insurance,
            "notes": (_load_knowledge_base(db, tenant_id=tenant_id).get("insurance") or {}).get("notes")
            if isinstance((_load_knowledge_base(db, tenant_id=tenant_id).get("insurance") or {}), dict)
            else None,
        }
    if action == "query_availability":
        slots = _query_availability(
            db,
            tenant_id=tenant_id,
            context=context,
            decision=decision,
            params=params,
        )
        return {"action": action, "status": "ok", "slots": slots}
    if action == "validate_slot":
        validation = _validate_slot(db, tenant_id=tenant_id, decision=decision, params=params, context=context)
        return {"action": action, **validation}
    if action == "validate_and_hold_slot":
        validation = _validate_slot(db, tenant_id=tenant_id, decision=decision, params=params, context=context)
        if validation.get("status") != "available":
            return {"action": action, **validation}
        hold = _create_slot_hold(
            db,
            tenant_id=tenant_id,
            conversation=conversation,
            inbound_message=inbound_message,
            validation=validation,
            hold_minutes=int(params.get("hold_minutes") or 10),
        )
        return {"action": action, **validation, "status": "held", "hold_id": str(hold.id)}
    if action == "confirm_appointment":
        return _confirm_appointment(db, tenant_id=tenant_id, conversation=conversation, decision=decision, params=params, context=context)
    if action == "reschedule_appointment":
        return _reschedule_appointment(db, tenant_id=tenant_id, decision=decision, params=params, context=context)
    if action == "cancel_appointment":
        return _cancel_appointment(db, tenant_id=tenant_id, decision=decision, params=params)
    if action == "handoff_to_human":
        _apply_handoff_state(db, tenant_id=tenant_id, conversation=conversation, inbound_message=inbound_message, reason="system_action_handoff", config=config)
        return {"action": action, "status": "ok", "handoff_required": True, "reason": "system_action_handoff"}
    return {"action": action, "status": "unsupported", "handoff_required": True, "reason": "unsupported_system_action"}


def _dispatch_patient_reply(
    db: Session,
    *,
    tenant_id: UUID,
    conversation: Conversation,
    inbound_message: Message,
    dedupe_key: str,
    config: dict[str, Any],
    context: AiConversationContext,
    patient_reply: PatientReplyOutput,
    decision: AiDecisionOutput,
    plan: SafePersistencePlan,
    applied_updates: dict[str, Any],
    system_action_result: dict[str, Any],
    extractor_payload: dict[str, Any] | None,
    reply_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    destination = _conversation_destination_phone(db, conversation=conversation)
    if not destination:
        return _handoff(
            db,
            tenant_id=tenant_id,
            conversation=conversation,
            inbound_message=inbound_message,
            dedupe_key=dedupe_key,
            config=config,
            reason="missing_contact_phone",
            guardrail=None,
            extractor_payload=extractor_payload,
            reply_payload=reply_payload,
        )
    patient_reply = _prepend_structured_first_reply_greeting_if_needed(
        patient_reply=patient_reply,
        context=context,
    )

    message_type = "interactive_list" if patient_reply.message_type == "interactive" else "text"
    interactive_payload = patient_reply.interactive_payload if patient_reply.message_type == "interactive" else None
    outbound_message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction=MessageDirection.OUTBOUND.value,
        channel=conversation.channel,
        sender_type="ai",
        body=patient_reply.message,
        message_type=message_type,
        payload={
            "source": "ai_autoresponder",
            "structured_flow": True,
            "reply_to_message_id": str(inbound_message.id),
            "intent": decision.intent,
            "system_action": system_action_result.get("action"),
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
        body=patient_reply.message,
        message_type=message_type,
        interactive=interactive_payload,
        metadata={
            "source": "ai_autoresponder",
            "structured_flow": True,
            "inbound_message_id": str(inbound_message.id),
            "outbound_message_id": str(outbound_message.id),
            "intent": decision.intent,
        },
    )
    outbound_payload = outbound_message.payload if isinstance(outbound_message.payload, dict) else {}
    outbound_payload["queued_outbox_id"] = str(outbox.id)
    outbound_message.payload = outbound_payload

    conversation.ai_autoresponder_last_decision = "responded"
    conversation.ai_autoresponder_last_reason = patient_reply.decision_reason
    conversation.ai_autoresponder_last_at = datetime.now(UTC)
    conversation.ai_autoresponder_consecutive_count = int(conversation.ai_autoresponder_consecutive_count or 0) + 1
    conversation.last_message_at = datetime.now(UTC)
    db.add(conversation)

    decision_row = _create_structured_decision(
        db,
        tenant_id=tenant_id,
        conversation=conversation,
        inbound_message=inbound_message,
        dedupe_key=dedupe_key,
        final_decision="responded",
        decision_reason=patient_reply.decision_reason,
        generated_response=patient_reply.message,
        confidence=patient_reply.confidence,
        llm_payload=reply_payload or extractor_payload,
        outbound_message_id=outbound_message.id,
        metadata={
            "structured_flow": True,
            "extractor": _safe_llm_metadata(extractor_payload),
            "reply": _safe_llm_metadata(reply_payload),
            "decision": decision.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
            "applied_updates": applied_updates,
            "system_action_result": system_action_result,
        },
    )
    db.add(
        MessageEvent(
            tenant_id=tenant_id,
            message_id=outbound_message.id,
            event_type="ai_structured_response_queued",
            payload={"outbox_id": str(outbox.id), "decision_id": str(decision_row.id)},
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _existing_decision(db, tenant_id=tenant_id, dedupe_key=dedupe_key)
        if existing:
            return {"status": "duplicate", "decision_id": str(existing.id), "reason": existing.decision_reason}
        raise

    maybe_schedule_demo_whatsapp_reply_simulation(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        outbound_message_id=outbound_message.id,
        source="ai_autoresponder",
    )
    record_audit(
        db,
        action="ai_autoresponder.structured_response_sent",
        entity_type="conversation",
        entity_id=str(conversation.id),
        tenant_id=tenant_id,
        user_id=None,
        metadata={
            "decision_id": str(decision_row.id),
            "outbox_id": str(outbox.id),
            "inbound_message_id": str(inbound_message.id),
            "outbound_message_id": str(outbound_message.id),
            "intent": decision.intent,
        },
    )
    return {
        "status": "responded",
        "decision_id": str(decision_row.id),
        "outbox_id": str(outbox.id),
        "outbound_message_id": str(outbound_message.id),
        "reason": patient_reply.decision_reason,
        "structured_flow": True,
        "system_action": system_action_result,
        "risk_flags": plan.risk_flags,
    }


def _finish_without_outbound(
    db: Session,
    *,
    tenant_id: UUID,
    conversation: Conversation,
    inbound_message: Message,
    dedupe_key: str,
    config: dict[str, Any],
    final_decision: str,
    decision_reason: str,
    confidence: float | None = None,
    llm_payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    conversation.ai_autoresponder_last_decision = final_decision
    conversation.ai_autoresponder_last_reason = decision_reason
    conversation.ai_autoresponder_last_at = datetime.now(UTC)
    if final_decision in {"ignored", "blocked", "error"}:
        conversation.ai_autoresponder_consecutive_count = 0
    db.add(conversation)
    decision = _create_structured_decision(
        db,
        tenant_id=tenant_id,
        conversation=conversation,
        inbound_message=inbound_message,
        dedupe_key=dedupe_key,
        final_decision=final_decision,
        decision_reason=decision_reason,
        confidence=confidence,
        llm_payload=llm_payload,
        metadata={"config": _safe_config_metadata(config), **(metadata or {})},
    )
    db.commit()
    return {
        "status": final_decision,
        "decision_id": str(decision.id),
        "reason": decision_reason,
        "structured_flow": True,
    }


def _invalid_contract_fallback(
    db: Session,
    *,
    tenant_id: UUID,
    conversation: Conversation,
    inbound_message: Message,
    dedupe_key: str,
    config: dict[str, Any],
    extractor_payload: dict[str, Any] | None,
    validation_error: str,
) -> dict[str, Any]:
    db.add(
        MessageEvent(
            tenant_id=tenant_id,
            message_id=inbound_message.id,
            event_type="ai_structured_invalid_contract",
            payload={"error": validation_error},
        )
    )
    fallback_reply = PatientReplyOutput(
        schema_version=STRUCTURED_FLOW_SCHEMA_VERSION,
        message="Só para eu confirmar certinho: você quer atendimento em qual unidade e período?",
        message_type="text",
        interactive_payload=None,
        confidence=0.5,
        final_decision="ask_clarification",
        decision_reason="invalid_ai_contract_fallback",
    )
    fake_decision = _minimal_decision_for_fallback(inbound_message.body or "")
    plan = SafePersistencePlan(message_id=str(inbound_message.id), conversation_id=str(conversation.id))
    return _dispatch_patient_reply(
        db,
        tenant_id=tenant_id,
        conversation=conversation,
        inbound_message=inbound_message,
        dedupe_key=dedupe_key,
        config=config,
        patient_reply=fallback_reply,
        decision=fake_decision,
        plan=plan,
        applied_updates={},
        system_action_result={"action": "none", "status": "invalid_contract_fallback"},
        extractor_payload=extractor_payload,
        reply_payload=None,
    )


def _handoff_notice_text(
    *,
    decision: AiDecisionOutput,
    context: AiConversationContext,
    reason: str | None,
) -> str:
    fallback = context.business_context.knowledge_base.escalation.fallback_message
    if fallback:
        return fallback
    if decision.intent == "urgencia" or decision.extracted_data.pain.urgency_level in {"alta", "emergencia"}:
        return (
            "Sinto muito pela dor. Como você mencionou um sinal que precisa de atenção, vou encaminhar sua conversa "
            "para nossa equipe te orientar com mais segurança."
        )
    if decision.intent == "falar_com_humano" or str(reason or "").lower().find("humano") >= 0:
        return "Claro. Vou encaminhar sua conversa para nossa equipe te ajudar com mais segurança, tudo bem?"
    return "Entendi. Vou encaminhar sua conversa para nossa equipe continuar o atendimento com mais segurança."


def _handoff(
    db: Session,
    *,
    tenant_id: UUID,
    conversation: Conversation,
    inbound_message: Message,
    dedupe_key: str,
    config: dict[str, Any],
    reason: str,
    guardrail: str | None,
    extractor_payload: dict[str, Any] | None = None,
    reply_payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    reply_text: str | None = None,
) -> dict[str, Any]:
    _apply_handoff_state(db, tenant_id=tenant_id, conversation=conversation, inbound_message=inbound_message, reason=reason, config=config)
    outbound_message_id: UUID | None = None
    outbox_id: UUID | None = None
    generated_response = None
    if reply_text:
        destination = _conversation_destination_phone(db, conversation=conversation)
        if destination:
            outbound = Message(
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                direction=MessageDirection.OUTBOUND.value,
                channel=conversation.channel,
                sender_type="ai",
                body=reply_text,
                message_type="text",
                payload={
                    "source": "ai_autoresponder",
                    "structured_flow": True,
                    "mode": "handoff_notice",
                    "reply_to_message_id": str(inbound_message.id),
                },
                status=MessageStatus.QUEUED.value,
            )
            db.add(outbound)
            db.flush()
            outbox = queue_outbound_message(
                db,
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                to=destination,
                body=reply_text,
                message_type="text",
                metadata={
                    "source": "ai_autoresponder",
                    "structured_flow": True,
                    "mode": "handoff_notice",
                    "inbound_message_id": str(inbound_message.id),
                    "outbound_message_id": str(outbound.id),
                },
            )
            outbound_payload = outbound.payload if isinstance(outbound.payload, dict) else {}
            outbound_payload["queued_outbox_id"] = str(outbox.id)
            outbound.payload = outbound_payload
            outbound_message_id = outbound.id
            outbox_id = outbox.id
            generated_response = reply_text

    decision = _create_structured_decision(
        db,
        tenant_id=tenant_id,
        conversation=conversation,
        inbound_message=inbound_message,
        dedupe_key=dedupe_key,
        final_decision="handoff",
        decision_reason=reason[:255],
        generated_response=generated_response,
        guardrail_trigger=guardrail,
        handoff_required=True,
        llm_payload=reply_payload or extractor_payload,
        outbound_message_id=outbound_message_id,
        metadata={
            "structured_flow": True,
            "extractor": _safe_llm_metadata(extractor_payload),
            "reply": _safe_llm_metadata(reply_payload),
            "outbox_id": str(outbox_id) if outbox_id else None,
            **(metadata or {}),
        },
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _existing_decision(db, tenant_id=tenant_id, dedupe_key=dedupe_key)
        if existing:
            return {"status": "duplicate", "decision_id": str(existing.id), "reason": existing.decision_reason}
        raise
    record_audit(
        db,
        action="ai_autoresponder.structured_handoff",
        entity_type="conversation",
        entity_id=str(conversation.id),
        tenant_id=tenant_id,
        user_id=None,
        metadata={"reason": reason, "decision_id": str(decision.id), "guardrail": guardrail},
    )
    return {
        "status": "handoff",
        "decision_id": str(decision.id),
        "reason": reason,
        "structured_flow": True,
        "outbox_id": str(outbox_id) if outbox_id else None,
        "outbound_message_id": str(outbound_message_id) if outbound_message_id else None,
    }


def _apply_handoff_state(
    db: Session,
    *,
    tenant_id: UUID,
    conversation: Conversation,
    inbound_message: Message,
    reason: str,
    config: dict[str, Any],
) -> None:
    queue_tag = str(config.get("human_queue_tag") or "fila_humana_ia")
    tags = set(conversation.tags or [])
    tags.update({queue_tag, "handoff_ia"})
    conversation.tags = sorted(tags)
    conversation.status = "aguardando"
    conversation.ai_autoresponder_consecutive_count = 0
    conversation.ai_autoresponder_last_decision = "handoff"
    conversation.ai_autoresponder_last_reason = reason[:255]
    conversation.ai_autoresponder_last_at = datetime.now(UTC)
    db.add(conversation)
    db.add(
        MessageEvent(
            tenant_id=tenant_id,
            message_id=inbound_message.id,
            event_type="ai_structured_handoff",
            payload={"reason": reason, "queue_tag": queue_tag},
        )
    )


def _create_structured_decision(
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
    llm_metadata = llm_payload.get("metadata") if isinstance(llm_payload.get("metadata"), dict) else {}
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
        decision_reason=decision_reason[:255],
        guardrail_trigger=guardrail_trigger,
        handoff_required=handoff_required,
        llm_provider=llm_metadata.get("provider"),
        llm_model=llm_metadata.get("model"),
        llm_task=llm_metadata.get("task") or llm_payload.get("task"),
        prompt_version=STRUCTURED_FLOW_PROMPT_VERSION,
        prompt_text=llm_payload.get("prompt"),
        token_input=prompt_tokens if isinstance(prompt_tokens, int) else None,
        token_output=completion_tokens if isinstance(completion_tokens, int) else None,
        token_total=total_tokens if isinstance(total_tokens, int) else None,
        estimated_cost_usd=float(llm_metadata.get("cost_usd")) if isinstance(llm_metadata.get("cost_usd"), (int, float)) else None,
        latency_ms=llm_metadata.get("latency_ms") if isinstance(llm_metadata.get("latency_ms"), int) else None,
        dedupe_key=dedupe_key,
        metadata_json=metadata or {},
    )
    db.add(decision)
    db.flush()
    return decision


def _fallback_patient_reply(
    *,
    decision: AiDecisionOutput,
    system_action_result: dict[str, Any],
    context: AiConversationContext,
) -> PatientReplyOutput:
    action = system_action_result.get("action")
    if action == "query_availability":
        slots = system_action_result.get("slots") if isinstance(system_action_result.get("slots"), list) else []
        if slots:
            patient_name = context.patient_context.preferred_name or context.patient_context.full_name
            greeting = f"Perfeito, {patient_name}. " if patient_name else "Perfeito. "
            options = []
            for index, slot in enumerate(slots, start=1):
                options.append(f"{index}. {slot.get('label') or slot.get('starts_at')}")
            message = greeting + "Encontrei estes horários disponíveis:\n" + "\n".join(options) + "\nQual deles fica melhor para você?"
            return PatientReplyOutput(
                schema_version=STRUCTURED_FLOW_SCHEMA_VERSION,
                message=message,
                message_type="text",
                interactive_payload=None,
                confidence=0.82,
                final_decision="reply",
                decision_reason="availability_options_returned",
            )
        return PatientReplyOutput(
            schema_version=STRUCTURED_FLOW_SCHEMA_VERSION,
            message="Não encontrei horários disponíveis nesse período. Posso verificar outro dia ou outro período para você?",
            message_type="text",
            interactive_payload=None,
            confidence=0.75,
            final_decision="ask_clarification",
            decision_reason="availability_empty",
        )
    if action == "query_units":
        units = system_action_result.get("units") if isinstance(system_action_result.get("units"), list) else []
        if units:
            names = ", ".join(str(unit.get("name")) for unit in units[:5] if unit.get("name"))
            message = f"Temos atendimento nas seguintes unidades: {names}. Qual delas fica melhor para você?"
        else:
            message = "Não encontrei unidades ativas cadastradas agora. Vou encaminhar para a equipe confirmar certinho para você."
        return PatientReplyOutput(
            schema_version=STRUCTURED_FLOW_SCHEMA_VERSION,
            message=message,
            message_type="text",
            interactive_payload=None,
            confidence=0.75,
            final_decision="reply" if units else "handoff",
            decision_reason="units_query_result",
        )
    if action == "query_insurance":
        plans = system_action_result.get("accepted_insurance") if isinstance(system_action_result.get("accepted_insurance"), list) else []
        if plans:
            message = "Atendemos estes convênios cadastrados: " + ", ".join(plans[:8]) + ". Qual é o seu plano?"
        else:
            message = "Não tenho convênios cadastrados aqui para confirmar com segurança. Vou pedir para a equipe verificar certinho para você."
        return PatientReplyOutput(
            schema_version=STRUCTURED_FLOW_SCHEMA_VERSION,
            message=message,
            message_type="text",
            interactive_payload=None,
            confidence=0.72,
            final_decision="reply" if plans else "handoff",
            decision_reason="insurance_query_result",
        )
    if action == "query_service":
        service = system_action_result.get("service") if isinstance(system_action_result.get("service"), dict) else None
        service_name = str((service or {}).get("name") or decision.extracted_data.service_requested_text or "esse procedimento").strip()
        if service:
            price_note = str(service.get("price_note") or "").strip()
            if decision.intent == "consultar_preco":
                if price_note:
                    message = f"Sobre {service_name}, a orientação cadastrada é: {price_note}. Posso verificar um horário de avaliação para você?"
                else:
                    message = (
                        f"O valor de {service_name} pode variar conforme a avaliação, porque cada caso é diferente. "
                        "Posso verificar um horário para você passar com o dentista e receber a orientação certinha?"
                    )
            else:
                message = (
                    f"Fazemos sim 😊 {service_name} está entre os procedimentos cadastrados. "
                    "Você quer que eu verifique um horário de avaliação para você?"
                )
        else:
            message = (
                "Não consegui confirmar esse procedimento nos cadastros da clínica agora. "
                "Você pode me dizer o nome do tratamento de outro jeito, ou prefere que eu encaminhe para a equipe?"
            )
        return PatientReplyOutput(
            schema_version=STRUCTURED_FLOW_SCHEMA_VERSION,
            message=message,
            message_type="text",
            interactive_payload=None,
            confidence=0.78 if service else 0.62,
            final_decision="reply" if service else "ask_clarification",
            decision_reason="service_query_result",
        )
    if action in {"validate_slot", "validate_and_hold_slot"}:
        status = str(system_action_result.get("status") or "")
        if status in {"available", "held"}:
            label = _slot_label_from_result(system_action_result, context=context)
            patient_name = context.patient_context.preferred_name or context.patient_context.full_name
            if patient_name and not _looks_like_placeholder_name(patient_name):
                message = f"Ótimo 😊 Separei {label} para você. Esse WhatsApp é o melhor número para confirmação?"
            else:
                message = f"Ótimo 😊 Separei {label} para você. Para confirmar certinho, qual é o seu nome completo?"
            return PatientReplyOutput(
                schema_version=STRUCTURED_FLOW_SCHEMA_VERSION,
                message=message,
                message_type="text",
                interactive_payload=None,
                confidence=0.84,
                final_decision="ask_clarification",
                decision_reason="slot_validated_waiting_required_data",
            )
        return PatientReplyOutput(
            schema_version=STRUCTURED_FLOW_SCHEMA_VERSION,
            message="Esse horário não apareceu mais como disponível. Posso verificar outras opções para você?",
            message_type="text",
            interactive_payload=None,
            confidence=0.78,
            final_decision="ask_clarification",
            decision_reason="slot_not_available",
        )
    if decision.reply_control.suggested_next_question:
        message = decision.reply_control.suggested_next_question
    elif decision.intent == "urgencia":
        message = (
            "Sinto muito pela dor. Para te orientar com segurança, vou encaminhar sua conversa para nossa equipe acompanhar de perto."
        )
    elif decision.intent == "saudacao":
        message = "Olá! Tudo bem? Posso te ajudar com informações da clínica, serviços ou horários. O que você gostaria de fazer?"
    else:
        message = "Entendi. Para eu te ajudar certinho, você prefere atendimento em qual unidade e período?"
    return PatientReplyOutput(
        schema_version=STRUCTURED_FLOW_SCHEMA_VERSION,
        message=message,
        message_type="text",
        interactive_payload=None,
        confidence=min(max(decision.confidence, 0.5), 0.85),
        final_decision="ask_clarification",
        decision_reason="safe_fallback_reply",
    )


def _query_availability(
    db: Session,
    *,
    tenant_id: UUID,
    context: AiConversationContext,
    decision: AiDecisionOutput,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    timezone = _timezone(context.clinic_context.timezone)
    unit = _resolve_unit(
        db,
        tenant_id=tenant_id,
        unit_id=(
            params.get("unit_id")
            or decision.extracted_data.unit_id
            or decision.appointment_intent.unit_id
            or context.conversation_context.unit_id
        ),
        unit_name=params.get("unit_name") or decision.extracted_data.unit_requested_text,
    )
    if not unit:
        unit = _resolve_unit_from_context(
            db,
            tenant_id=tenant_id,
            context=context,
        )
    if not unit:
        units = _active_units(db, tenant_id=tenant_id)
        unit = units[0] if units else None
    if not unit:
        return []
    procedure = _first_text(
        params.get("procedure_type"),
        decision.appointment_intent.procedure_type,
        decision.extracted_data.procedure_type,
        decision.extracted_data.service_requested_text,
        "Avaliação odontológica",
    )
    service_catalog = get_service_duration_catalog(db, tenant_id=tenant_id)
    duration = resolve_service_duration_minutes(procedure_type=procedure, service_catalog=service_catalog)
    start_date = _resolve_target_date(
        params.get("date") or decision.extracted_data.preferred_date,
        timezone=timezone,
    )
    period = params.get("period") or decision.extracted_data.preferred_period
    limit = int(params.get("limit") or 3)
    time_after_minutes = _parse_time_filter_minutes(params.get("time_after"), timezone=timezone)
    time_before_minutes = _parse_time_filter_minutes(params.get("time_before"), timezone=timezone)
    exclude_previously_offered = bool(params.get("exclude_previously_offered"))
    professionals = eligible_professionals_for_procedure(
        list_active_professionals_for_unit(
            db,
            tenant_id=tenant_id,
            unit_id=unit.id,
        ),
        procedure,
    )
    if params.get("professional_id") or decision.extracted_data.professional_id or decision.appointment_intent.professional_id:
        wanted = str(params.get("professional_id") or decision.extracted_data.professional_id or decision.appointment_intent.professional_id)
        professionals = [professional for professional in professionals if str(professional.id) == wanted]
    professionals = sorted(professionals, key=lambda item: str(item.full_name or "").lower())
    slots: list[dict[str, Any]] = []
    for day_offset in range(0, 21):
        current_date = start_date + timedelta(days=day_offset)
        excluded_slot_tokens = (
            _recent_offered_slot_tokens(
                db,
                tenant_id=tenant_id,
                context=context,
                target_date=current_date,
                period=period,
                timezone=timezone,
            )
            if exclude_previously_offered
            else set()
        )
        for professional in professionals:
            shift_start = _parse_hhmm(professional.shift_start) or time(8, 0)
            shift_end = _parse_hhmm(professional.shift_end) or time(18, 0)
            day_start = datetime.combine(current_date, shift_start, timezone)
            day_end = datetime.combine(current_date, shift_end, timezone)
            if time_before_minutes is not None:
                day_end = min(day_end, _datetime_for_minutes(current_date, minutes=time_before_minutes, timezone=timezone))
            if not professional_is_available_on_day(
                professional,
                starts_at=day_start,
                timezone_name=context.clinic_context.timezone,
            ):
                continue
            cursor = _align_period_start(day_start, period)
            if time_after_minutes is not None:
                cursor = max(cursor, _datetime_for_minutes(current_date, minutes=time_after_minutes, timezone=timezone))
            while cursor + timedelta(minutes=duration) <= day_end:
                slot_token = _slot_id(unit.id, professional.id, cursor.astimezone(UTC))
                if (
                    slot_token not in excluded_slot_tokens
                    and cursor.astimezone(UTC).isoformat() not in excluded_slot_tokens
                    and _slot_matches_period(cursor, period)
                    and _slot_available(
                        db,
                        tenant_id=tenant_id,
                        professional_id=professional.id,
                        starts_at=cursor.astimezone(UTC),
                        ends_at=(cursor + timedelta(minutes=duration)).astimezone(UTC),
                    )
                ):
                    slots.append(
                        {
                            "slot_id": slot_token,
                            "unit_id": str(unit.id),
                            "unit_name": unit.name,
                            "professional_id": str(professional.id),
                            "professional_name": professional.full_name,
                            "procedure_type": procedure,
                            "starts_at": cursor.astimezone(UTC).isoformat(),
                            "ends_at": (cursor + timedelta(minutes=duration)).astimezone(UTC).isoformat(),
                            "label": cursor.strftime("%d/%m/%Y às %H:%M"),
                        }
                    )
                    if len(slots) >= limit:
                        return slots
                cursor += timedelta(minutes=30)
    return slots


def _validate_slot(
    db: Session,
    *,
    tenant_id: UUID,
    decision: AiDecisionOutput,
    params: dict[str, Any],
    context: AiConversationContext,
) -> dict[str, Any]:
    starts_at = _resolve_slot_datetime(params, decision)
    if not starts_at:
        return {"status": "missing_slot", "available": False}
    unit = _resolve_unit(
        db,
        tenant_id=tenant_id,
        unit_id=(
            params.get("unit_id")
            or decision.extracted_data.unit_id
            or decision.appointment_intent.unit_id
            or context.conversation_context.unit_id
        ),
        unit_name=params.get("unit_name") or decision.extracted_data.unit_requested_text,
    )
    if not unit:
        unit = _resolve_unit_from_context(
            db,
            tenant_id=tenant_id,
            context=context,
        )
    if not unit:
        return {"status": "unit_not_found", "available": False}
    procedure = _first_text(
        params.get("procedure_type"),
        decision.appointment_intent.procedure_type,
        decision.extracted_data.procedure_type,
        decision.extracted_data.service_requested_text,
        "Avaliação odontológica",
    )
    service_catalog = get_service_duration_catalog(db, tenant_id=tenant_id)
    duration = resolve_service_duration_minutes(procedure_type=procedure, service_catalog=service_catalog)
    professional_id = _parse_uuid(params.get("professional_id") or decision.extracted_data.professional_id or decision.appointment_intent.professional_id)
    professionals = eligible_professionals_for_procedure(
        list_active_professionals_for_unit(
            db,
            tenant_id=tenant_id,
            unit_id=unit.id,
        ),
        procedure,
    )
    if professional_id:
        professionals = [professional for professional in professionals if professional.id == professional_id]
    professionals = sorted(professionals, key=lambda item: str(item.full_name or "").lower())
    ends_at = starts_at + timedelta(minutes=duration)
    for professional in professionals:
        if not professional_is_available_on_day(
            professional,
            starts_at=starts_at,
            timezone_name=context.clinic_context.timezone,
        ):
            continue
        if _slot_available(db, tenant_id=tenant_id, professional_id=professional.id, starts_at=starts_at, ends_at=ends_at):
            return {
                "status": "available",
                "available": True,
                "unit_id": str(unit.id),
                "unit_name": unit.name,
                "professional_id": str(professional.id),
                "professional_name": professional.full_name,
                "procedure_type": procedure,
                "starts_at": starts_at.isoformat(),
                "ends_at": ends_at.isoformat(),
            }
    return {"status": "unavailable", "available": False, "starts_at": starts_at.isoformat()}


def _create_slot_hold(
    db: Session,
    *,
    tenant_id: UUID,
    conversation: Conversation,
    inbound_message: Message,
    validation: dict[str, Any],
    hold_minutes: int,
) -> Job:
    expires_at = datetime.now(UTC) + timedelta(minutes=hold_minutes)
    job = Job(
        tenant_id=tenant_id,
        job_type="ai_slot_hold",
        status=JobStatus.PENDING.value,
        payload={
            "conversation_id": str(conversation.id),
            "inbound_message_id": str(inbound_message.id),
            "unit_id": validation.get("unit_id"),
            "professional_id": validation.get("professional_id"),
            "starts_at": validation.get("starts_at"),
            "ends_at": validation.get("ends_at"),
            "expires_at": expires_at.isoformat(),
        },
        scheduled_for=expires_at,
        max_attempts=1,
    )
    db.add(job)
    db.flush()
    return job


def _confirm_appointment(
    db: Session,
    *,
    tenant_id: UUID,
    conversation: Conversation,
    decision: AiDecisionOutput,
    params: dict[str, Any],
    context: AiConversationContext,
) -> dict[str, Any]:
    if not conversation.patient_id:
        return {"action": "confirm_appointment", "status": "missing_patient", "handoff_required": False}
    validation = _validate_slot(db, tenant_id=tenant_id, decision=decision, params=params, context=context)
    if validation.get("status") != "available":
        return {"action": "confirm_appointment", **validation}
    appointment = Appointment(
        tenant_id=tenant_id,
        patient_id=conversation.patient_id,
        unit_id=UUID(validation["unit_id"]),
        professional_id=UUID(validation["professional_id"]),
        procedure_type=validation["procedure_type"],
        starts_at=datetime.fromisoformat(validation["starts_at"]),
        ends_at=datetime.fromisoformat(validation["ends_at"]),
        status=AppointmentStatus.SCHEDULED.value,
        origin="ai_structured",
        notes="",
        confirmation_status="pendente",
    )
    db.add(appointment)
    db.flush()
    db.add(
        AppointmentEvent(
            tenant_id=tenant_id,
            appointment_id=appointment.id,
            event_type="created_by_ai",
            from_status=None,
            to_status=appointment.status,
            metadata_json={"conversation_id": str(conversation.id), "source": "ai_structured_flow"},
        )
    )
    emit_event(
        db,
        tenant_id=tenant_id,
        event_key="consulta_criada",
        payload={
            "appointment_id": str(appointment.id),
            "patient_id": str(conversation.patient_id),
            "starts_at": appointment.starts_at.isoformat(),
            "status": appointment.status,
        },
    )
    return {"action": "confirm_appointment", **validation, "status": "created", "appointment_id": str(appointment.id)}


def _reschedule_appointment(
    db: Session,
    *,
    tenant_id: UUID,
    decision: AiDecisionOutput,
    params: dict[str, Any],
    context: AiConversationContext,
) -> dict[str, Any]:
    appointment_id = _parse_uuid(params.get("appointment_id") or decision.extracted_data.appointment_id)
    if not appointment_id:
        return {"action": "reschedule_appointment", "status": "missing_appointment"}
    appointment = db.scalar(select(Appointment).where(Appointment.tenant_id == tenant_id, Appointment.id == appointment_id))
    if not appointment:
        return {"action": "reschedule_appointment", "status": "appointment_not_found"}
    validation = _validate_slot(db, tenant_id=tenant_id, decision=decision, params=params, context=context)
    if validation.get("status") != "available":
        return {"action": "reschedule_appointment", **validation}
    previous_status = appointment.status
    appointment.starts_at = datetime.fromisoformat(validation["starts_at"])
    appointment.ends_at = datetime.fromisoformat(validation["ends_at"])
    appointment.professional_id = UUID(validation["professional_id"])
    appointment.unit_id = UUID(validation["unit_id"])
    appointment.status = AppointmentStatus.RESCHEDULED.value
    db.add(appointment)
    db.add(
        AppointmentEvent(
            tenant_id=tenant_id,
            appointment_id=appointment.id,
            event_type="rescheduled_by_ai",
            from_status=previous_status,
            to_status=appointment.status,
            metadata_json={"source": "ai_structured_flow"},
        )
    )
    return {"action": "reschedule_appointment", "status": "rescheduled", "appointment_id": str(appointment.id), **validation}


def _cancel_appointment(
    db: Session,
    *,
    tenant_id: UUID,
    decision: AiDecisionOutput,
    params: dict[str, Any],
) -> dict[str, Any]:
    appointment_id = _parse_uuid(params.get("appointment_id") or decision.extracted_data.appointment_id)
    if not appointment_id:
        return {"action": "cancel_appointment", "status": "missing_appointment"}
    appointment = db.scalar(select(Appointment).where(Appointment.tenant_id == tenant_id, Appointment.id == appointment_id))
    if not appointment:
        return {"action": "cancel_appointment", "status": "appointment_not_found"}
    previous_status = appointment.status
    appointment.status = AppointmentStatus.CANCELED.value
    appointment.canceled_at = datetime.now(UTC)
    appointment.canceled_reason = decision.appointment_intent.canceled_reason or "Cancelado via IA estruturada"
    db.add(appointment)
    db.add(
        AppointmentEvent(
            tenant_id=tenant_id,
            appointment_id=appointment.id,
            event_type="canceled_by_ai",
            from_status=previous_status,
            to_status=appointment.status,
            metadata_json={"source": "ai_structured_flow", "reason": appointment.canceled_reason},
        )
    )
    return {"action": "cancel_appointment", "status": "canceled", "appointment_id": str(appointment.id)}


def _slot_available(
    db: Session,
    *,
    tenant_id: UUID,
    professional_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
) -> bool:
    conflict = db.scalar(
        select(Appointment)
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.professional_id == professional_id,
            Appointment.status.in_(list(ACTIVE_APPOINTMENT_STATUSES)),
            Appointment.starts_at < ends_at,
            Appointment.ends_at.is_not(None),
            Appointment.ends_at > starts_at,
        )
        .limit(1)
    )
    if conflict:
        return False
    legacy_conflicts = db.execute(
        select(Appointment)
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.professional_id == professional_id,
            Appointment.status.in_(list(ACTIVE_APPOINTMENT_STATUSES)),
            Appointment.starts_at < ends_at,
            Appointment.ends_at.is_(None),
        )
    ).scalars().all()
    if legacy_conflicts:
        service_catalog = get_service_duration_catalog(db, tenant_id=tenant_id)
        for appointment in legacy_conflicts:
            effective_end = appointment_effective_end(
                starts_at=appointment.starts_at,
                ends_at=appointment.ends_at,
                procedure_type=appointment.procedure_type,
                service_catalog=service_catalog,
            )
            if effective_end > starts_at:
                return False
    now = datetime.now(UTC)
    hold = db.scalar(
        select(Job)
        .where(
            Job.tenant_id == tenant_id,
            Job.job_type == "ai_slot_hold",
            Job.status == JobStatus.PENDING.value,
            Job.scheduled_for.is_not(None),
            Job.scheduled_for > now,
            Job.payload["professional_id"].astext == str(professional_id),
            Job.payload["starts_at"].astext == starts_at.isoformat(),
        )
        .limit(1)
    )
    return hold is None


def _coerce_json_object(raw_output: Any) -> dict[str, Any]:
    if isinstance(raw_output, dict):
        return raw_output
    text = str(raw_output or "").strip()
    if not text:
        raise ValueError("empty JSON output")
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        parsed = json.loads(text[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("output is not a JSON object")


def _normalize_update_value(update: FieldUpdate, plan: SafePersistencePlan) -> Any:
    value = update.value
    if update.field in {"full_name", "name", "preferred_name"}:
        return _compact(value, 180)
    if update.field == "email":
        email = _compact(value, 255).lower()
        try:
            EMAIL_ADAPTER.validate_python(email)
        except Exception:
            plan.risk_flags.append(f"skipped_{update.target}.{update.field}:invalid_email")
            return None
        return email
    if update.field in {"cpf", "normalized_cpf"}:
        normalized = _normalize_cpf(value)
        if not normalized or not _is_valid_cpf(normalized):
            plan.risk_flags.append(f"skipped_{update.target}.{update.field}:invalid_cpf")
            return None
        return normalized if update.field == "normalized_cpf" else _format_cpf(normalized)
    if update.field == "birth_date":
        parsed = _parse_birth_date(value)
        if parsed is None:
            plan.risk_flags.append(f"skipped_{update.target}.{update.field}:invalid_birth_date")
            return None
        return parsed.isoformat()
    if update.field == "tags":
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()][:20]
        return [_compact(value, 100)]
    if update.field == "ai_autoresponder_consecutive_count":
        try:
            return max(0, int(value))
        except Exception:
            return None
    return value


def _is_update_allowed_against_current_value(
    *,
    update: FieldUpdate,
    normalized_value: Any,
    patient: Patient | None,
    lead: Lead | None,
) -> bool:
    if update.target == "patients" and patient:
        current = getattr(patient, update.field, None)
        return _can_replace_value(current, normalized_value, source_text=update.source_text)
    if update.target == "leads" and lead:
        current = getattr(lead, update.field, None)
        return _can_replace_value(current, normalized_value, source_text=update.source_text)
    return True


def _can_replace_value(current: Any, new_value: Any, *, source_text: str | None) -> bool:
    if _is_empty_value(current):
        return True
    current_text = str(current).strip().casefold()
    new_text = str(new_value).strip().casefold()
    if not new_text or current_text == new_text:
        return True
    if (
        current_text.startswith("contato whatsapp ")
        or current_text.startswith("paciente teste ")
        or current_text.startswith("paciente ia lab")
        or current_text.startswith("lead ia lab")
        or current_text.startswith("lead teste ia lab")
    ):
        return True
    return _looks_like_correction(source_text)


def _looks_like_correction(source_text: str | None) -> bool:
    text = _strip_accents(str(source_text or "").lower())
    return any(marker in text for marker in ("corrigir", "correcao", "correto", "na verdade", "meu nome e", "meu nome é"))


def _minimal_decision_for_fallback(inbound_text: str) -> AiDecisionOutput:
    return AiDecisionOutput(
        schema_version=STRUCTURED_FLOW_SCHEMA_VERSION,
        intent="outro",
        confidence=0.5,
        detected_language="pt-BR",
        message_summary=_compact(inbound_text, 220),
        extracted_data=ExtractedData(),
        field_updates=[],
        appointment_intent=AppointmentIntent(
            wants_booking=False,
            wants_reschedule=False,
            wants_cancel=False,
        ),
        system_action=SystemAction(required=False, action="none", params=SystemActionParams()),
        reply_control=ReplyControl(
            should_reply_now=True,
            reply_after_system_action=False,
            missing_fields=[],
        ),
    )


def _normalize_legacy_ai_decision_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    # Adapter seguro para respostas antigas do LLM. Ele não aplica field_updates
    # e reconstrói um contrato estrito antes de qualquer persistência.
    if payload.get("schema_version") or "field_updates" in payload:
        return None
    entities = payload.get("entities")
    action_payload = payload.get("action_payload")
    has_legacy_signal = any(
        key in payload
        for key in (
            "intent",
            "confidence",
            "action",
            "next_action",
            "required",
            "summary",
            "message_summary",
            "missing_fields",
            "suggested_next_question",
            "handoff",
            "guardrails",
        )
    )
    if not isinstance(entities, dict) and not isinstance(action_payload, dict) and not has_legacy_signal:
        return None
    entities = entities if isinstance(entities, dict) else {}
    action_payload = action_payload if isinstance(action_payload, dict) else {}
    intent = _normalize_legacy_intent(payload.get("intent"))
    confidence = _clamp_confidence(payload.get("confidence"), default=0.72)
    handoff_payload = payload.get("handoff") if isinstance(payload.get("handoff"), dict) else {}
    guardrail_payload = payload.get("guardrails") if isinstance(payload.get("guardrails"), dict) else {}
    service_text = _first_text(
        entities.get("service"),
        entities.get("service_type"),
        entities.get("procedure"),
        entities.get("procedure_type"),
        action_payload.get("service"),
        action_payload.get("procedure_type"),
    )
    unit_text = _first_text(
        entities.get("unit"),
        entities.get("unit_name"),
        entities.get("unit_preference"),
        action_payload.get("unit_name"),
    )
    preferred_period = _normalize_preferred_period(_first_text(entities.get("preferred_period"), action_payload.get("period")))
    selected_datetime = _first_text(entities.get("selected_datetime"), action_payload.get("selected_datetime"), action_payload.get("starts_at"))
    action = _normalize_legacy_system_action(
        payload.get("next_action") or payload.get("action") or action_payload.get("action"),
        intent=intent,
    )
    params = {
        "unit_id": _optional_text(action_payload.get("unit_id")),
        "unit_name": unit_text,
        "service_id": _optional_text(action_payload.get("service_id")),
        "procedure_type": service_text,
        "professional_id": _optional_text(action_payload.get("professional_id")),
        "date": _optional_text(_first_text(entities.get("preferred_date"), entities.get("date"), action_payload.get("date"))),
        "time_after": _optional_text(_first_text(entities.get("time_after"), action_payload.get("time_after"))),
        "time_before": _optional_text(_first_text(entities.get("time_before"), action_payload.get("time_before"))),
        "period": preferred_period,
        "slot_id": _optional_text(_first_text(entities.get("selected_slot_id"), action_payload.get("slot_id"))),
        "appointment_id": _optional_text(_first_text(entities.get("appointment_id"), action_payload.get("appointment_id"))),
        "hold_minutes": _safe_int(action_payload.get("hold_minutes"), default=10, minimum=1, maximum=60),
        "limit": _safe_int(action_payload.get("limit"), default=3, minimum=1, maximum=10),
    }
    wants_booking = intent in {"agendar_consulta", "consultar_horarios", "selecionar_horario", "confirmar_agendamento"}
    return {
        "schema_version": STRUCTURED_FLOW_SCHEMA_VERSION,
        "intent": intent,
        "confidence": confidence,
        "detected_language": str(payload.get("detected_language") or "pt-BR"),
        "message_summary": _compact(payload.get("message_summary") or payload.get("summary") or f"Intent: {intent}", 240),
        "extracted_data": {
            "patient_name": _optional_text(_first_text(entities.get("patient_name"), entities.get("name"))),
            "responsible_name": _optional_text(entities.get("responsible_name")),
            "preferred_name": _optional_text(entities.get("preferred_name")),
            "phone": _optional_text(entities.get("phone")),
            "email": _optional_text(entities.get("email")),
            "cpf": _optional_text(entities.get("cpf")),
            "birth_date": _optional_text(entities.get("birth_date")),
            "unit_requested_text": unit_text,
            "unit_id": _optional_text(action_payload.get("unit_id")),
            "service_requested_text": service_text,
            "service_id": _optional_text(action_payload.get("service_id")),
            "procedure_type": service_text,
            "professional_requested_text": _optional_text(entities.get("professional")),
            "professional_id": _optional_text(action_payload.get("professional_id")),
            "preferred_date": params["date"],
            "preferred_period": preferred_period,
            "preferred_time_text": _optional_text(_first_text(entities.get("preferred_time"), entities.get("preferred_time_text"))),
            "selected_slot_id": params["slot_id"],
            "selected_datetime": selected_datetime,
            "appointment_id": params["appointment_id"],
            "pain": {
                "has_pain": _optional_bool(_first_text(entities.get("has_pain"), entities.get("pain"))),
                "duration_text": _optional_text(entities.get("pain_duration")),
                "has_swelling": _optional_bool(_first_text(entities.get("has_swelling"), entities.get("swelling"))),
                "has_fever": _optional_bool(_first_text(entities.get("has_fever"), entities.get("fever"))),
                "urgency_level": _normalize_urgency_level(entities.get("urgency_level")),
            },
        },
        "field_updates": [],
        "appointment_intent": {
            "wants_booking": wants_booking,
            "wants_reschedule": intent == "remarcar_consulta",
            "wants_cancel": intent == "cancelar_consulta",
            "procedure_type": service_text,
            "unit_id": params["unit_id"],
            "professional_id": params["professional_id"],
            "starts_at": selected_datetime,
            "ends_at": _optional_text(action_payload.get("ends_at")),
            "canceled_reason": _optional_text(action_payload.get("canceled_reason")),
        },
        "system_action": {
            "required": action != "none",
            "action": action,
            "params": params,
        },
        "reply_control": {
            "should_reply_now": action == "none",
            "reply_after_system_action": action != "none",
            "next_expected_field": _optional_text(payload.get("next_expected_field")),
            "missing_fields": [str(item) for item in payload.get("missing_fields", []) if str(item).strip()]
            if isinstance(payload.get("missing_fields"), list)
            else [],
            "suggested_next_question": _optional_text(payload.get("suggested_next_question")),
        },
        "handoff": {
            "required": bool(handoff_payload.get("required")),
            "reason": _optional_text(handoff_payload.get("reason")),
            "tag": _optional_text(handoff_payload.get("tag")),
        },
        "guardrails": {
            "triggered": bool(guardrail_payload.get("triggered")),
            "reason": _optional_text(guardrail_payload.get("reason")),
            "forbidden_topics_detected": [
                str(item) for item in guardrail_payload.get("forbidden_topics_detected", []) if str(item).strip()
            ]
            if isinstance(guardrail_payload.get("forbidden_topics_detected"), list)
            else [],
        },
    }


def _normalize_legacy_patient_reply_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    if payload.get("schema_version"):
        return None
    message = _first_text(payload.get("message"), payload.get("patient_reply"), payload.get("reply_text"), payload.get("response"))
    if not message:
        return None
    final_decision = str(payload.get("final_decision") or "reply").strip()
    if final_decision not in {"reply", "handoff", "no_reply", "ask_clarification"}:
        final_decision = "reply"
    message_type = str(payload.get("message_type") or "text").strip()
    if message_type not in {"text", "interactive"}:
        message_type = "text"
    return {
        "schema_version": STRUCTURED_FLOW_SCHEMA_VERSION,
        "message": message,
        "message_type": message_type,
        "interactive_payload": payload.get("interactive_payload") if isinstance(payload.get("interactive_payload"), dict) else None,
        "confidence": _clamp_confidence(payload.get("confidence"), default=0.74),
        "final_decision": final_decision,
        "decision_reason": _compact(payload.get("decision_reason") or "legacy_patient_reply_adapter", 120),
    }


def _normalize_legacy_intent(value: Any) -> DecisionIntent:
    text = _strip_accents(str(value or "").strip().lower())
    aliases: dict[str, DecisionIntent] = {
        "agendamento": "agendar_consulta",
        "agendar": "agendar_consulta",
        "preco": "consultar_preco",
        "orcamento": "consultar_preco",
        "convenio": "consultar_convenio",
        "servico": "consultar_servico",
        "procedimento": "consultar_servico",
        "horario": "consultar_horarios",
        "horarios": "consultar_horarios",
        "unidade": "consultar_unidade",
        "humano": "falar_com_humano",
        "atendente": "falar_com_humano",
        "urgente": "urgencia",
        "emergencia": "urgencia",
    }
    if text in aliases:
        return aliases[text]
    if text in DecisionIntent.__args__:  # type: ignore[attr-defined]
        return text  # type: ignore[return-value]
    return "outro"


def _normalize_legacy_system_action(value: Any, *, intent: DecisionIntent) -> SystemActionName:
    text = _strip_accents(str(value or "").strip().lower())
    aliases: dict[str, SystemActionName] = {
        "show_available_dates": "query_availability",
        "show_available_slots": "query_availability",
        "open_booking": "query_availability",
        "booking": "query_availability",
        "show_clinics": "query_units",
        "show_units": "query_units",
        "show_services": "query_service",
        "show_plans": "query_insurance",
        "handoff": "handoff_to_human",
        "human": "handoff_to_human",
    }
    if text in aliases:
        return aliases[text]
    if text in SystemActionName.__args__:  # type: ignore[attr-defined]
        return text  # type: ignore[return-value]
    return DYNAMIC_INTENT_FALLBACK_ACTION.get(intent, "none")


def _normalize_preferred_period(value: Any) -> PreferredPeriod | None:
    text = _strip_accents(str(value or "").strip().lower())
    aliases = {
        "manha": "manha",
        "manhã": "manha",
        "tarde": "tarde",
        "noite": "noite",
        "final do dia": "final_do_dia",
        "fim do dia": "final_do_dia",
        "qualquer": "qualquer",
    }
    normalized = aliases.get(text)
    return normalized if normalized in PreferredPeriod.__args__ else None  # type: ignore[attr-defined, return-value]


def _detect_preferred_period_from_message(text: str) -> PreferredPeriod | None:
    normalized = _strip_accents(str(text or "").strip().lower())
    if "final do dia" in normalized or "fim do dia" in normalized:
        return "final_do_dia"
    if "tarde" in normalized:
        return "tarde"
    if "noite" in normalized:
        return "noite"
    if re.search(r"\bmanha\b", normalized):
        return "manha"
    if "qualquer horario" in normalized or "qualquer horário" in str(text or "").lower() or "qualquer periodo" in normalized:
        return "qualquer"
    return None


def _normalize_urgency_level(value: Any) -> str:
    text = _strip_accents(str(value or "").strip().lower())
    if text in {"baixa", "normal", "media", "alta", "emergencia"}:
        return text
    return "desconhecida"


def _clamp_confidence(value: Any, *, default: float) -> float:
    try:
        number = float(value)
    except Exception:
        return default
    return min(max(number, 0.0), 1.0)


def _safe_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except Exception:
        return default
    return min(max(number, minimum), maximum)


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = _strip_accents(str(value or "").strip().lower())
    if text in {"true", "sim", "s", "yes", "y", "1"}:
        return True
    if text in {"false", "nao", "não", "n", "no", "0"}:
        return False
    return None


def _effective_system_action(decision: AiDecisionOutput) -> str:
    if decision.system_action.action != "none" or decision.system_action.required:
        return decision.system_action.action
    return DYNAMIC_INTENT_FALLBACK_ACTION.get(decision.intent, "none")


def _load_clinic_profile(db: Session, *, tenant_id: UUID) -> dict[str, Any]:
    item = db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == CLINIC_PROFILE_SETTING_KEY))
    value = _setting_value(item)
    profile = value if isinstance(value, dict) else {}
    timezone = _setting_scalar_value(db, tenant_id=tenant_id, key=CLINIC_TIMEZONE_SETTING_KEY)
    if timezone and "timezone" not in profile:
        profile = {**profile, "timezone": timezone}
    allowed = {
        "clinic_name",
        "legal_name",
        "main_phone",
        "whatsapp_phone",
        "email",
        "website",
        "address_line",
        "neighborhood",
        "city",
        "state",
        "zip_code",
        "technical_manager_name",
        "technical_manager_cro",
        "payment_methods",
        "accepted_insurance",
        "cancellation_policy",
        "reschedule_policy",
        "about",
        "timezone",
    }
    return {key: profile.get(key) for key in allowed if key in profile}


def _load_knowledge_base(db: Session, *, tenant_id: UUID) -> dict[str, Any]:
    item = db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == AI_KNOWLEDGE_BASE_SETTING_KEY))
    value = item.value if item and isinstance(item.value, dict) else {}
    return value if isinstance(value, dict) else {}


def _load_service_context(db: Session, *, tenant_id: UUID) -> list[ServiceContext]:
    services: list[ServiceContext] = []
    for item in get_service_catalog_items(db, tenant_id=tenant_id):
        if not item.get("is_active", True):
            continue
        services.append(
            ServiceContext(
                id=str(item.get("id")),
                name=str(item.get("name") or ""),
                description=_optional_text(item.get("description")),
                duration_minutes=item.get("duration_minutes") if isinstance(item.get("duration_minutes"), int) else None,
                duration_note=_optional_text(item.get("duration_note")),
                price_note=_optional_text(item.get("price_note")),
                is_active=bool(item.get("is_active", True)),
            )
        )
    return services


def _load_safe_patient_contacts(
    db: Session,
    *,
    tenant_id: UUID,
    patient_id: UUID | None,
) -> tuple[str | None, bool]:
    if not patient_id:
        return None, False
    rows = db.execute(
        select(PatientContact).where(
            PatientContact.tenant_id == tenant_id,
            PatientContact.patient_id == patient_id,
            PatientContact.channel.in_([PREFERRED_NAME_CONTACT_CHANNEL, CPF_CONTACT_CHANNEL]),
        )
    ).scalars().all()
    preferred_name = None
    cpf_present = False
    for contact in rows:
        if contact.channel == PREFERRED_NAME_CONTACT_CHANNEL:
            preferred_name = _optional_text(contact.value)
        elif contact.channel == CPF_CONTACT_CHANNEL and contact.value:
            cpf_present = True
    return preferred_name, cpf_present


def _recent_messages(db: Session, *, conversation: Conversation, include_message_id: UUID, limit: int = 12) -> list[RecentMessageContext]:
    rows = db.execute(
        select(Message)
        .where(Message.tenant_id == conversation.tenant_id, Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    ).scalars().all()
    if include_message_id not in {row.id for row in rows}:
        extra = db.get(Message, include_message_id)
        if extra:
            rows.append(extra)
    rows = sorted(rows, key=lambda item: item.created_at or datetime.min.replace(tzinfo=UTC))
    output: list[RecentMessageContext] = []
    for row in rows[-limit:]:
        payload = row.payload if isinstance(row.payload, dict) else {}
        interactive_reply = payload.get("interactive_reply") if isinstance(payload.get("interactive_reply"), dict) else None
        direction = "outbound" if row.direction == MessageDirection.OUTBOUND.value else "inbound"
        output.append(
            RecentMessageContext(
                id=str(row.id),
                direction=direction,
                body=row.body or "",
                interactive_reply=interactive_reply,
                created_at=row.created_at.isoformat() if row.created_at else None,
            )
        )
    return output


def _resolve_unit(db: Session, *, tenant_id: UUID, unit_id: Any = None, unit_name: Any = None) -> Unit | None:
    parsed_id = _parse_uuid(unit_id)
    if parsed_id:
        unit = db.scalar(
            select(Unit).where(Unit.tenant_id == tenant_id, Unit.id == parsed_id, Unit.is_active.is_(True))
        )
        if unit:
            return unit
    name = _strip_accents(str(unit_name or "").casefold())
    if not name:
        return None
    units = _active_units(db, tenant_id=tenant_id)
    for unit in units:
        candidate = _strip_accents(f"{unit.name} {unit.code or ''}".casefold())
        if name in candidate or candidate in name:
            return unit
    return None


def _resolve_service(db: Session, *, tenant_id: UUID, service_id: Any = None, procedure_type: Any = None) -> dict[str, Any] | None:
    services = [item for item in get_service_catalog_items(db, tenant_id=tenant_id) if item.get("is_active", True)]
    requested_id = str(service_id or "").strip()
    if requested_id:
        for item in services:
            if str(item.get("id")) == requested_id:
                return item
    requested = _strip_accents(str(procedure_type or "").casefold())
    if not requested:
        return None
    for item in services:
        name = _strip_accents(str(item.get("name") or "").casefold())
        if requested in name or name in requested:
            return item
    return None


def _unit_payload(unit: Unit) -> dict[str, Any]:
    return {
        "id": str(unit.id),
        "name": unit.name,
        "code": unit.code,
        "phone": unit.phone,
        "email": unit.email,
        "address": unit.address if isinstance(unit.address, dict) else None,
    }


def _conversation_destination_phone(db: Session, *, conversation: Conversation) -> str | None:
    if conversation.patient_id:
        patient = db.get(Patient, conversation.patient_id)
        if patient and patient.phone:
            return patient.phone
    if conversation.lead_id:
        lead = db.get(Lead, conversation.lead_id)
        if lead and lead.phone:
            return lead.phone
    return None


def _safe_llm_metadata(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return {
        "provider": metadata.get("provider"),
        "model": metadata.get("model"),
        "task": metadata.get("task"),
        "latency_ms": metadata.get("latency_ms"),
        "token_total": metadata.get("total_tokens"),
    }


def _safe_config_metadata(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "enabled": config.get("enabled"),
        "structured_flow_enabled": config.get("structured_flow_enabled"),
        "channels": config.get("channels"),
        "outside_business_hours_mode": config.get("outside_business_hours_mode"),
        "max_consecutive_auto_replies": config.get("max_consecutive_auto_replies"),
        "confidence_threshold": config.get("confidence_threshold"),
    }


def _existing_decision(db: Session, *, tenant_id: UUID, dedupe_key: str) -> AIAutoresponderDecision | None:
    return db.scalar(
        select(AIAutoresponderDecision).where(
            AIAutoresponderDecision.tenant_id == tenant_id,
            AIAutoresponderDecision.dedupe_key == dedupe_key,
        )
    )


def _setting_value(item: Setting | None) -> Any:
    if not item:
        return None
    if isinstance(item.value, dict) and set(item.value.keys()) == {"value"}:
        return item.value.get("value")
    return item.value


def _setting_scalar_value(db: Session, *, tenant_id: UUID, key: str) -> Any:
    item = db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == key))
    return _setting_value(item)


def _is_business_hours(config: dict[str, Any]) -> bool:
    business = config.get("business_hours") if isinstance(config.get("business_hours"), dict) else {}
    timezone = _timezone(str(business.get("timezone") or settings.app_timezone))
    now = datetime.now(timezone)
    weekdays = [int(day) for day in (business.get("weekdays") or []) if str(day).isdigit()]
    if weekdays and now.weekday() not in weekdays:
        return False
    start = _parse_hhmm(str(business.get("start") or "00:00")) or time(0, 0)
    end = _parse_hhmm(str(business.get("end") or "23:59")) or time(23, 59)
    return start <= now.time() <= end


def _timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo(settings.app_timezone)


def _resolve_target_date(value: Any, *, timezone: ZoneInfo) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if text:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            try:
                return date.fromisoformat(text)
            except Exception:
                pass
        try:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone)
            return parsed.astimezone(timezone).date()
        except Exception:
            try:
                return date.fromisoformat(text)
            except Exception:
                pass
    return datetime.now(timezone).date() + timedelta(days=1)


def _resolve_slot_datetime(params: dict[str, Any], decision: AiDecisionOutput) -> datetime | None:
    for value in (
        params.get("slot_id"),
        decision.extracted_data.selected_slot_id,
        decision.extracted_data.selected_datetime,
        decision.appointment_intent.starts_at,
    ):
        parsed = _parse_slot_datetime(value)
        if parsed:
            return parsed
    return None


def _pending_slot_confirmation_request(context: AiConversationContext) -> dict[str, bool] | None:
    for recent_message in reversed(context.conversation_context.recent_messages):
        if recent_message.direction != "outbound":
            continue
        normalized = _normalized_reply_guardrail_text(recent_message.body)
        if "separei" not in normalized and "horario" not in normalized:
            continue
        asked_name = "nome completo" in normalized or "seu nome" in normalized
        asked_phone = "whatsapp" in normalized or "telefone" in normalized or "numero para confirmacao" in normalized
        if asked_name or asked_phone:
            return {
                "asked_name": asked_name,
                "asked_phone": asked_phone,
            }
    return None


def _extract_patient_name_hint(*, inbound_text: str) -> str | None:
    text = str(inbound_text or "").strip()
    if not text:
        return None
    patterns = (
        r"\bmeu nome(?: completo)?\s*(?:e|é)\s+(.+)",
        r"\bme chamo\s+(.+)",
        r"\beu sou\s+(.+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        candidate = match.group(1).strip()
        candidate = re.split(
            r"\b(?:cpf|data de nascimento|nascimento|telefone|whatsapp|esse whatsapp|este whatsapp|meu whatsapp|melhor numero)\b",
            candidate,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        candidate = " ".join(candidate.strip(" ,.;:-").split())
        if candidate.casefold().endswith(" e"):
            candidate = candidate[:-2].rstrip(" ,.;:-")
        if len(candidate.split()) < 2:
            continue
        words = []
        for part in candidate.split():
            lowered = part.casefold()
            words.append(part.capitalize() if lowered == part or part.isupper() else part)
        return _compact(" ".join(words), 180)
    return None


def _message_confirms_existing_whatsapp(inbound_text: str) -> bool:
    normalized = _normalized_reply_guardrail_text(inbound_text)
    if "whatsapp" not in normalized and "telefone" not in normalized and "numero" not in normalized:
        return False
    confirmation_markers = (
        "melhor numero",
        "esse whatsapp",
        "este whatsapp",
        "esse numero",
        "pode confirmar",
        "pode falar por aqui",
    )
    return any(marker in normalized for marker in confirmation_markers)


def _extract_slot_datetime_hint(*, inbound_text: str, timezone: ZoneInfo) -> datetime | None:
    text = str(inbound_text or "").strip()
    if not text:
        return None
    token_match = re.search(
        r"slot:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
        text,
        re.IGNORECASE,
    )
    if token_match:
        parsed = _parse_slot_datetime(token_match.group(0))
        if parsed:
            return parsed
    normalized = _strip_accents(text)
    label_match = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\D{0,6}(\d{1,2}:\d{2})\b", normalized, re.IGNORECASE)
    if not label_match:
        return None
    day_text, month_text, year_text, hhmm = label_match.groups()
    hour_text, minute_text = hhmm.split(":", 1)
    try:
        localized = datetime(
            int(year_text),
            int(month_text),
            int(day_text),
            int(hour_text),
            int(minute_text),
            tzinfo=timezone,
        )
    except Exception:
        return None
    return localized.astimezone(UTC)


def _extract_preferred_date_hint(*, inbound_text: str, timezone: ZoneInfo) -> str | None:
    normalized = _strip_accents(str(inbound_text or "").lower())
    today = datetime.now(timezone).date()
    if "amanha" in normalized:
        return (today + timedelta(days=1)).isoformat()
    match = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", normalized)
    if not match:
        return None
    day = int(match.group(1))
    month = int(match.group(2))
    year_raw = match.group(3)
    year = today.year
    if year_raw:
        year = int(year_raw)
        if year < 100:
            year += 2000
    try:
        candidate = date(year, month, day)
    except ValueError:
        return None
    return candidate.isoformat()


def _message_has_booking_intent(text: str) -> bool:
    normalized = _strip_accents(str(text or "").lower())
    return any(
        keyword in normalized
        for keyword in ("agendar", "marcar", "horario", "consulta", "avaliacao")
    )


def _message_requests_alternative_slots(text: str) -> bool:
    normalized = _normalized_reply_guardrail_text(text)
    markers = (
        "outro horario",
        "outros horarios",
        "outra opcao",
        "outras opcoes",
        "outra alternativa",
        "outras alternativas",
        "mais opcoes",
        "me mande outras",
        "me passe outras",
        "verifique outro horario",
        "verificar outro horario",
    )
    return any(marker in normalized for marker in markers)


def _message_prefers_same_period(text: str) -> bool:
    normalized = _normalized_reply_guardrail_text(text)
    return any(marker in normalized for marker in ("mesmo periodo", "mesma faixa"))


def _availability_window_hints_from_message(text: str) -> dict[str, str]:
    normalized = _normalized_reply_guardrail_text(text)
    if "fim da manha" in normalized or "final da manha" in normalized:
        return {
            "period": "manha",
            "time_after": "10:30",
            "time_before": "12:00",
        }
    if "fim da tarde" in normalized or "final da tarde" in normalized:
        return {
            "period": "tarde",
            "time_after": "16:00",
            "time_before": "18:00",
        }
    return {}


def _period_from_datetime(value: datetime) -> PreferredPeriod:
    if value.hour < 12:
        return "manha"
    if value.hour < 18:
        return "tarde"
    return "noite"


def _decision_metadata_payload(row: AIAutoresponderDecision) -> dict[str, Any]:
    return row.metadata_json if isinstance(row.metadata_json, dict) else {}


def _recent_conversation_decisions(
    db: Session,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    limit: int = 12,
) -> list[AIAutoresponderDecision]:
    return db.execute(
        select(AIAutoresponderDecision)
        .where(
            AIAutoresponderDecision.tenant_id == tenant_id,
            AIAutoresponderDecision.conversation_id == conversation_id,
        )
        .order_by(AIAutoresponderDecision.created_at.desc())
        .limit(limit)
    ).scalars().all()


def _recent_scheduling_memory(
    db: Session,
    *,
    tenant_id: UUID,
    context: AiConversationContext,
) -> dict[str, Any]:
    conversation_id = _parse_uuid(context.conversation_context.conversation_id)
    if not conversation_id:
        return {
            "unit_id": None,
            "unit_name": None,
            "service_id": None,
            "procedure_type": None,
            "professional_id": None,
            "preferred_date": None,
            "preferred_period": None,
            "offered_slots": [],
        }

    rows = _recent_conversation_decisions(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
    )
    offered_slots: list[dict[str, Any]] = []
    seen_slot_tokens: set[str] = set()
    for row in rows:
        metadata = _decision_metadata_payload(row)
        system_action_result = metadata.get("system_action_result") if isinstance(metadata.get("system_action_result"), dict) else {}
        if str(system_action_result.get("action") or "") != "query_availability":
            continue
        slots = system_action_result.get("slots") if isinstance(system_action_result.get("slots"), list) else []
        for raw_slot in slots:
            slot = raw_slot if isinstance(raw_slot, dict) else None
            if not slot:
                continue
            token = str(slot.get("slot_id") or slot.get("starts_at") or "").strip()
            if not token or token in seen_slot_tokens:
                continue
            seen_slot_tokens.add(token)
            offered_slots.append(slot)

    for row in rows:
        metadata = _decision_metadata_payload(row)
        decision_payload = metadata.get("decision") if isinstance(metadata.get("decision"), dict) else {}
        system_action = decision_payload.get("system_action") if isinstance(decision_payload.get("system_action"), dict) else {}
        appointment_intent = decision_payload.get("appointment_intent") if isinstance(decision_payload.get("appointment_intent"), dict) else {}
        extracted_data = decision_payload.get("extracted_data") if isinstance(decision_payload.get("extracted_data"), dict) else {}
        system_action_result = metadata.get("system_action_result") if isinstance(metadata.get("system_action_result"), dict) else {}

        action_name = str(system_action.get("action") or system_action_result.get("action") or "").strip()
        if action_name not in {"query_availability", "validate_slot", "validate_and_hold_slot", "confirm_appointment"} and not appointment_intent.get("wants_booking"):
            continue

        params = system_action.get("params") if isinstance(system_action.get("params"), dict) else {}
        starts_at = _parse_slot_datetime(system_action_result.get("starts_at"))
        local_starts_at = starts_at.astimezone(_timezone(context.clinic_context.timezone)) if starts_at else None
        preferred_period = _normalize_preferred_period(
            _first_text(
                params.get("period"),
                extracted_data.get("preferred_period"),
            )
        )
        if not preferred_period and local_starts_at:
            preferred_period = _period_from_datetime(local_starts_at)
        preferred_date = _first_text(
            params.get("date"),
            extracted_data.get("preferred_date"),
            local_starts_at.date().isoformat() if local_starts_at else None,
        )
        return {
            "unit_id": _first_text(params.get("unit_id"), extracted_data.get("unit_id"), appointment_intent.get("unit_id"), system_action_result.get("unit_id")),
            "unit_name": _first_text(params.get("unit_name"), extracted_data.get("unit_requested_text"), system_action_result.get("unit_name")),
            "service_id": _first_text(params.get("service_id"), extracted_data.get("service_id")),
            "procedure_type": _first_text(
                params.get("procedure_type"),
                appointment_intent.get("procedure_type"),
                extracted_data.get("procedure_type"),
                extracted_data.get("service_requested_text"),
            ),
            "professional_id": _first_text(
                params.get("professional_id"),
                appointment_intent.get("professional_id"),
                extracted_data.get("professional_id"),
                system_action_result.get("professional_id"),
            ),
            "preferred_date": preferred_date or None,
            "preferred_period": preferred_period,
            "offered_slots": offered_slots,
        }

    return {
        "unit_id": None,
        "unit_name": None,
        "service_id": None,
        "procedure_type": None,
        "professional_id": None,
        "preferred_date": None,
        "preferred_period": None,
        "offered_slots": offered_slots,
    }


def _parse_time_filter_minutes(value: Any, *, timezone: ZoneInfo) -> int | None:
    parsed_time = _parse_hhmm(value)
    if parsed_time:
        return (parsed_time.hour * 60) + parsed_time.minute
    parsed_slot = _parse_slot_datetime(value)
    if parsed_slot:
        local = parsed_slot.astimezone(timezone)
        return (local.hour * 60) + local.minute
    normalized = _normalized_reply_guardrail_text(value)
    match = re.search(r"\b(\d{1,2})h(?:(\d{2}))?\b", normalized)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or "00")
    if hour > 23 or minute > 59:
        return None
    return (hour * 60) + minute


def _datetime_for_minutes(current_date: date, *, minutes: int, timezone: ZoneInfo) -> datetime:
    hour = max(0, min(23, minutes // 60))
    minute = max(0, min(59, minutes % 60))
    return datetime.combine(current_date, time(hour, minute), timezone)


def _recent_offered_slot_tokens(
    db: Session,
    *,
    tenant_id: UUID,
    context: AiConversationContext,
    target_date: date,
    period: Any,
    timezone: ZoneInfo,
) -> set[str]:
    memory = _recent_scheduling_memory(
        db,
        tenant_id=tenant_id,
        context=context,
    )
    tokens: set[str] = set()
    for slot in memory.get("offered_slots") or []:
        if not isinstance(slot, dict):
            continue
        starts_at = _parse_slot_datetime(slot.get("starts_at") or slot.get("slot_id"))
        if not starts_at:
            continue
        local = starts_at.astimezone(timezone)
        if local.date() != target_date or not _slot_matches_period(local, period):
            continue
        slot_id = str(slot.get("slot_id") or "").strip()
        if slot_id:
            tokens.add(slot_id)
        tokens.add(starts_at.astimezone(UTC).isoformat())
    return tokens


def _extract_procedure_hint_from_context(*, context: AiConversationContext, inbound_text: str) -> str | None:
    normalized = _strip_accents(str(inbound_text or "").casefold())
    if not normalized:
        return None
    known_procedures: list[str] = []
    for service in context.business_context.services:
        if service.name:
            known_procedures.append(service.name)
    for professional in context.business_context.professionals_summary:
        for procedure in professional.procedures:
            if procedure:
                known_procedures.append(procedure)
    for procedure in sorted({item.strip() for item in known_procedures if item and item.strip()}, key=len, reverse=True):
        if _strip_accents(procedure.casefold()) in normalized:
            return procedure
    return None


def _extract_unit_hint_from_text(db: Session, *, tenant_id: UUID, inbound_text: str) -> Unit | None:
    normalized = _strip_accents(str(inbound_text or "").casefold())
    if not normalized:
        return None
    for unit in _active_units(db, tenant_id=tenant_id):
        candidates = [
            _strip_accents(str(unit.name or "").casefold()),
            _strip_accents(str(unit.code or "").casefold()),
        ]
        if any(candidate and candidate in normalized for candidate in candidates):
            return unit
    return None


def _resolve_unit_from_context(
    db: Session,
    *,
    tenant_id: UUID,
    context: AiConversationContext,
) -> Unit | None:
    if context.conversation_context.unit_id:
        selected = _resolve_unit(
            db,
            tenant_id=tenant_id,
            unit_id=context.conversation_context.unit_id,
        )
        if selected:
            return selected
    for recent_message in context.conversation_context.recent_messages:
        selected = _extract_unit_hint_from_text(
            db,
            tenant_id=tenant_id,
            inbound_text=recent_message.body,
        )
        if selected:
            return selected
    if len(context.business_context.units) == 1:
        return _resolve_unit(
            db,
            tenant_id=tenant_id,
            unit_id=context.business_context.units[0].id,
        )
    return None


def _enrich_decision_with_selection_hints(
    *,
    db: Session,
    tenant_id: UUID,
    decision: AiDecisionOutput,
    inbound_text: str,
    context: AiConversationContext,
) -> AiDecisionOutput:
    if decision.system_action.action not in {"validate_slot", "validate_and_hold_slot", "confirm_appointment", "reschedule_appointment"}:
        return decision
    params_payload = decision.system_action.params.model_dump(mode="json")
    selected_slot = _resolve_slot_datetime(params_payload, decision)
    if not selected_slot:
        selected_slot = _extract_slot_datetime_hint(
            inbound_text=inbound_text,
            timezone=_timezone(context.clinic_context.timezone),
        )
    if not selected_slot:
        return decision
    selected_slot_iso = selected_slot.isoformat()
    selected_slot_id = decision.system_action.params.slot_id or decision.extracted_data.selected_slot_id or f"slot:{selected_slot_iso}"
    selected_unit = None
    if not decision.extracted_data.unit_id and not decision.appointment_intent.unit_id:
        if decision.extracted_data.unit_requested_text:
            selected_unit = _resolve_unit(
                db,
                tenant_id=tenant_id,
                unit_name=decision.extracted_data.unit_requested_text,
            )
    if (
        selected_unit is None
        and not decision.extracted_data.unit_id
        and not decision.extracted_data.unit_requested_text
        and not decision.appointment_intent.unit_id
    ):
        selected_unit = _extract_unit_hint_from_text(
            db,
            tenant_id=tenant_id,
            inbound_text=inbound_text,
        )
    if (
        selected_unit is None
        and not decision.extracted_data.unit_id
        and not decision.appointment_intent.unit_id
    ):
        selected_unit = _resolve_unit_from_context(
            db,
            tenant_id=tenant_id,
            context=context,
        )
    extracted_data = decision.extracted_data.model_copy(
        update={
            "unit_requested_text": decision.extracted_data.unit_requested_text or (selected_unit.name if selected_unit else None),
            "unit_id": decision.extracted_data.unit_id or (str(selected_unit.id) if selected_unit else None),
            "selected_slot_id": selected_slot_id,
            "selected_datetime": decision.extracted_data.selected_datetime or selected_slot_iso,
        }
    )
    appointment_intent = decision.appointment_intent.model_copy(
        update={
            "unit_id": decision.appointment_intent.unit_id or (str(selected_unit.id) if selected_unit else None),
            "starts_at": decision.appointment_intent.starts_at or selected_slot_iso,
        }
    )
    system_action = decision.system_action.model_copy(
        update={
            "params": decision.system_action.params.model_copy(
                update={
                    "slot_id": selected_slot_id,
                }
            )
        }
    )
    return decision.model_copy(
        update={
            "extracted_data": extracted_data,
            "appointment_intent": appointment_intent,
            "system_action": system_action,
        }
    )


def _enrich_decision_with_first_message_context_hints(
    db: Session,
    *,
    tenant_id: UUID,
    decision: AiDecisionOutput,
    inbound_text: str,
    context: AiConversationContext,
) -> AiDecisionOutput:
    unit = None
    if not decision.extracted_data.unit_id and not decision.extracted_data.unit_requested_text:
        unit = _extract_unit_hint_from_text(db, tenant_id=tenant_id, inbound_text=inbound_text)
    service = None
    if not decision.extracted_data.service_id and not decision.extracted_data.service_requested_text and not decision.extracted_data.procedure_type:
        service = _resolve_service(db, tenant_id=tenant_id, procedure_type=inbound_text)
    procedure_hint = (
        decision.extracted_data.procedure_type
        or (str(service.get("name")) if service else None)
        or _extract_procedure_hint_from_context(context=context, inbound_text=inbound_text)
    )
    preferred_period = decision.extracted_data.preferred_period or _detect_preferred_period_from_message(inbound_text)
    preferred_date = decision.extracted_data.preferred_date or _extract_preferred_date_hint(
        inbound_text=inbound_text,
        timezone=_timezone(context.clinic_context.timezone),
    )

    extracted_data = decision.extracted_data.model_copy(
        update={
            "unit_id": decision.extracted_data.unit_id or (str(unit.id) if unit else None),
            "unit_requested_text": decision.extracted_data.unit_requested_text or (unit.name if unit else None),
            "service_id": decision.extracted_data.service_id or (str(service.get("id")) if service else None),
            "service_requested_text": decision.extracted_data.service_requested_text or procedure_hint,
            "procedure_type": procedure_hint,
            "preferred_period": preferred_period,
            "preferred_date": preferred_date,
        }
    )

    appointment_intent = decision.appointment_intent
    system_action = decision.system_action
    if _message_has_booking_intent(inbound_text):
        appointment_intent = appointment_intent.model_copy(
            update={
                "wants_booking": True,
                "procedure_type": appointment_intent.procedure_type or extracted_data.procedure_type,
                "unit_id": appointment_intent.unit_id or extracted_data.unit_id,
            }
        )
        action_name = system_action.action if system_action.action != "none" else "query_availability"
        system_action = system_action.model_copy(
            update={
                "required": True,
                "action": action_name,
                "params": system_action.params.model_copy(
                    update={
                        "unit_id": system_action.params.unit_id or extracted_data.unit_id,
                        "unit_name": system_action.params.unit_name or extracted_data.unit_requested_text,
                        "service_id": system_action.params.service_id or extracted_data.service_id,
                        "procedure_type": system_action.params.procedure_type or extracted_data.procedure_type,
                        "date": system_action.params.date or extracted_data.preferred_date,
                        "period": system_action.params.period or extracted_data.preferred_period,
                    }
                ),
            }
        )

    return decision.model_copy(
        update={
            "extracted_data": extracted_data,
            "appointment_intent": appointment_intent,
            "system_action": system_action,
        }
    )


def _enrich_decision_with_recent_availability_hints(
    db: Session,
    *,
    tenant_id: UUID,
    decision: AiDecisionOutput,
    inbound_text: str,
    context: AiConversationContext,
) -> AiDecisionOutput:
    alternative_requested = _message_requests_alternative_slots(inbound_text)
    same_period_requested = _message_prefers_same_period(inbound_text)
    window_hints = _availability_window_hints_from_message(inbound_text)
    if not alternative_requested and not same_period_requested and not window_hints:
        return decision

    memory = _recent_scheduling_memory(
        db,
        tenant_id=tenant_id,
        context=context,
    )
    if not any(memory.get(field) for field in ("unit_id", "unit_name", "procedure_type", "preferred_date", "offered_slots")):
        return decision

    inherited_period = (
        _normalize_preferred_period(decision.extracted_data.preferred_period)
        or _normalize_preferred_period(decision.system_action.params.period)
        or _normalize_preferred_period(window_hints.get("period"))
    )
    if (same_period_requested or alternative_requested) and not inherited_period:
        inherited_period = _normalize_preferred_period(memory.get("preferred_period"))

    extracted_data = decision.extracted_data.model_copy(
        update={
            "unit_id": decision.extracted_data.unit_id or memory.get("unit_id"),
            "unit_requested_text": decision.extracted_data.unit_requested_text or memory.get("unit_name"),
            "service_id": decision.extracted_data.service_id or memory.get("service_id"),
            "service_requested_text": decision.extracted_data.service_requested_text or memory.get("procedure_type"),
            "procedure_type": decision.extracted_data.procedure_type or memory.get("procedure_type"),
            "professional_id": decision.extracted_data.professional_id or memory.get("professional_id"),
            "preferred_date": decision.extracted_data.preferred_date or memory.get("preferred_date"),
            "preferred_period": window_hints.get("period") or decision.extracted_data.preferred_period or inherited_period,
        }
    )

    appointment_intent = decision.appointment_intent
    if alternative_requested or same_period_requested or window_hints:
        appointment_intent = appointment_intent.model_copy(
            update={
                "wants_booking": True,
                "procedure_type": appointment_intent.procedure_type or extracted_data.procedure_type,
                "unit_id": appointment_intent.unit_id or extracted_data.unit_id,
                "professional_id": appointment_intent.professional_id or extracted_data.professional_id,
            }
        )

    action_name = decision.system_action.action
    if alternative_requested or same_period_requested or window_hints:
        action_name = "query_availability"

    system_action = decision.system_action.model_copy(
        update={
            "required": decision.system_action.required or alternative_requested or same_period_requested or bool(window_hints),
            "action": action_name,
            "params": decision.system_action.params.model_copy(
                update={
                    "unit_id": decision.system_action.params.unit_id or extracted_data.unit_id,
                    "unit_name": decision.system_action.params.unit_name or extracted_data.unit_requested_text,
                    "service_id": decision.system_action.params.service_id or extracted_data.service_id,
                    "procedure_type": decision.system_action.params.procedure_type or extracted_data.procedure_type,
                    "professional_id": decision.system_action.params.professional_id or extracted_data.professional_id,
                    "date": decision.system_action.params.date or extracted_data.preferred_date,
                    "period": window_hints.get("period") or decision.system_action.params.period or extracted_data.preferred_period,
                    "time_after": window_hints.get("time_after") or decision.system_action.params.time_after,
                    "time_before": window_hints.get("time_before") or decision.system_action.params.time_before,
                    "exclude_previously_offered": decision.system_action.params.exclude_previously_offered or alternative_requested or same_period_requested or bool(window_hints),
                }
            ),
        }
    )

    return decision.model_copy(
        update={
            "extracted_data": extracted_data,
            "appointment_intent": appointment_intent,
            "system_action": system_action,
        }
    )


def _enrich_decision_with_personal_data_hints(
    *,
    decision: AiDecisionOutput,
    inbound_text: str,
    context: AiConversationContext,
) -> AiDecisionOutput:
    name_hint = _extract_patient_name_hint(inbound_text=inbound_text)
    whatsapp_confirmed = _message_confirms_existing_whatsapp(inbound_text)
    pending_slot_confirmation = _pending_slot_confirmation_request(context)
    if not name_hint and not pending_slot_confirmation:
        return decision

    extracted_data = decision.extracted_data
    reply_control = decision.reply_control
    field_updates = list(decision.field_updates)

    if name_hint and not extracted_data.patient_name:
        extracted_data = extracted_data.model_copy(update={"patient_name": name_hint})
    if name_hint:
        if not any(update.target == "patients" and update.field == "full_name" for update in field_updates):
            field_updates.append(
                FieldUpdate(
                    target="patients",
                    field="full_name",
                    value=name_hint,
                    confidence=max(decision.confidence, 0.9),
                    source_text=inbound_text,
                    should_apply=True,
                    reason="Paciente informou o nome completo na continuidade da confirmacao do horario.",
                )
            )
        if not any(update.target == "leads" and update.field == "name" for update in field_updates):
            field_updates.append(
                FieldUpdate(
                    target="leads",
                    field="name",
                    value=name_hint,
                    confidence=max(decision.confidence, 0.9),
                    source_text=inbound_text,
                    should_apply=True,
                    reason="Paciente informou o nome completo na continuidade da confirmacao do horario.",
                )
            )

    if pending_slot_confirmation:
        first_name = (name_hint or "").split()[0] if name_hint else None
        suggested_next_question = reply_control.suggested_next_question
        next_expected_field = reply_control.next_expected_field
        missing_fields = [field for field in reply_control.missing_fields if field]
        if not name_hint:
            suggested_next_question = "Perfeito. Para confirmar certinho, qual é o seu nome completo?"
            next_expected_field = "patient_name"
            missing_fields = ["patient_name"]
        elif pending_slot_confirmation.get("asked_phone") and not whatsapp_confirmed:
            suggested_next_question = (
                f"Perfeito, {first_name}. Esse WhatsApp é o melhor número para confirmação?"
                if first_name
                else "Perfeito. Esse WhatsApp é o melhor número para confirmação?"
            )
            next_expected_field = "phone_confirmation"
            missing_fields = ["phone_confirmation"]
        else:
            suggested_next_question = (
                f"Perfeito, {first_name}. Anotei seus dados para seguir com esse horário. Se quiser, posso continuar a confirmação por aqui."
                if first_name
                else "Perfeito. Anotei seus dados para seguir com esse horário. Se quiser, posso continuar a confirmação por aqui."
            )
            next_expected_field = None
            missing_fields = []
        reply_control = reply_control.model_copy(
            update={
                "should_reply_now": True,
                "reply_after_system_action": False,
                "next_expected_field": next_expected_field,
                "missing_fields": missing_fields,
                "suggested_next_question": suggested_next_question,
            }
        )

    return decision.model_copy(
        update={
            "extracted_data": extracted_data,
            "field_updates": field_updates,
            "reply_control": reply_control,
        }
    )


def _strip_structured_leading_greeting(text: str) -> str:
    return re.sub(
        r"^\s*(?:ol[aá]|oi|bom dia|boa tarde|boa noite)[^.!?\n]{0,120}[.!?]?\s*",
        "",
        str(text or "").strip(),
        count=1,
        flags=re.IGNORECASE,
    ).strip()


def _prepend_structured_first_reply_greeting_if_needed(
    *,
    patient_reply: PatientReplyOutput,
    context: AiConversationContext,
) -> PatientReplyOutput:
    inbound_count = sum(1 for item in context.conversation_context.recent_messages if item.direction == "inbound")
    outbound_count = sum(1 for item in context.conversation_context.recent_messages if item.direction == "outbound")
    if inbound_count != 1 or outbound_count != 0:
        return patient_reply
    greeting = (
        f"Olá! 😊\n"
        f"Bem-vindo à Clínica {context.clinic_context.clinic_name}.\n\n"
        "Sou Luiza, assistente virtual da clínica. Posso te ajudar a encontrar horários disponíveis, "
        "agendar consultas e tirar dúvidas rapidamente."
    )
    body = _strip_structured_leading_greeting(patient_reply.message)
    message = f"{greeting}\n\n{body}" if body else f"{greeting}\n\nComo posso te ajudar?"
    return patient_reply.model_copy(update={"message": message})


def _parse_slot_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith("slot:"):
        text = text.split(":", 1)[1]
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except Exception:
        return None


def _slot_id(unit_id: UUID, professional_id: UUID, starts_at: datetime) -> str:
    return f"slot:{starts_at.isoformat()}"


def _slot_label_from_result(result: dict[str, Any], *, context: AiConversationContext) -> str:
    starts_at = _parse_slot_datetime(result.get("starts_at"))
    unit_name = str(result.get("unit_name") or "").strip()
    if not starts_at:
        return "esse horário"
    local = starts_at.astimezone(_timezone(context.clinic_context.timezone))
    label = local.strftime("%d/%m às %H:%M")
    return f"o horário de {label}" + (f" na {unit_name}" if unit_name else "")


def _align_period_start(day_start: datetime, period: Any) -> datetime:
    period_text = str(period or "").lower()
    hour = day_start.hour
    if period_text in {"tarde"}:
        hour = max(hour, 12)
    elif period_text in {"noite", "final_do_dia"}:
        hour = max(hour, 17)
    return day_start.replace(hour=hour, minute=0, second=0, microsecond=0)


def _slot_matches_period(slot: datetime, period: Any) -> bool:
    period_text = str(period or "").lower()
    if not period_text or period_text == "qualquer":
        return True
    if period_text == "manha":
        return slot.hour < 12
    if period_text == "tarde":
        return 12 <= slot.hour < 18
    if period_text in {"noite", "final_do_dia"}:
        return slot.hour >= 17
    return True


def _parse_hhmm(value: Any) -> time | None:
    text = str(value or "").strip()
    try:
        hour_text, minute_text = text.split(":", 1)
        return time(int(hour_text), int(minute_text[:2]))
    except Exception:
        return None


def _parse_uuid(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    try:
        text = str(value or "").strip()
        return UUID(text) if text else None
    except Exception:
        return None


def _parse_birth_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except Exception:
        match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", text)
        if not match:
            return None
        day, month, year = match.groups()
        year_int = int(year)
        if year_int < 100:
            year_int += 2000 if year_int <= 30 else 1900
        try:
            return date(year_int, int(month), int(day))
        except Exception:
            return None


def _normalize_cpf(value: Any) -> str | None:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits if len(digits) == 11 else None


def _format_cpf(value: str) -> str:
    digits = _normalize_cpf(value) or value
    return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}" if len(digits) == 11 else digits


def _is_valid_cpf(value: str | None) -> bool:
    digits = _normalize_cpf(value)
    if not digits or digits == digits[0] * 11:
        return False
    for size in (9, 10):
        total = sum(int(digits[index]) * (size + 1 - index) for index in range(size))
        check = (total * 10) % 11
        if check == 10:
            check = 0
        if check != int(digits[size]):
            return False
    return True


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return not value
    return False


def _compact(value: Any, max_length: int) -> str:
    return " ".join(str(value or "").strip().split())[:max_length]


def _optional_text(value: Any) -> str | None:
    text = _compact(value, 1000)
    return text or None


def _first_text(*values: Any) -> str:
    for value in values:
        text = _optional_text(value)
        if text:
            return text
    return ""


def _as_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_compact(item, 160) for item in value if _compact(item, 160)]
    text = _compact(value, 500)
    if not text:
        return []
    parts = re.split(r"[,;\n]", text)
    return [_compact(part, 160) for part in parts if _compact(part, 160)]


def _compose_address(profile: dict[str, Any]) -> str | None:
    parts = [
        _optional_text(profile.get("address_line")),
        _optional_text(profile.get("neighborhood")),
        _optional_text(profile.get("city")),
        _optional_text(profile.get("state")),
        _optional_text(profile.get("zip_code")),
    ]
    return ", ".join(part for part in parts if part) or None


def _strip_accents(value: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")

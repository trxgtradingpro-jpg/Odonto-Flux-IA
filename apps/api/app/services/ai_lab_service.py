from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.core.logging import logger
from app.models import Conversation, Lead, Message, MessageEvent, OutboxMessage, Patient, Setting, Unit
from app.models.enums import ConversationStatus, MessageDirection, MessageStatus
from app.services.ai_autoresponder_service import (
    AI_ALLOWED_NEXT_ACTIONS,
    booking_interactive_options_enabled,
    build_ai_action_interactive_preview,
    normalize_immediate_action_reply_text,
    _format_unit_address,
    _parse_and_validate_ai_contract,
    _parse_json_output,
    _prompt_for_autoresponder,
    _load_custom_autoresponder_prompt,
    _is_payment_methods_question,
    _load_official_clinic_profile_context,
    _official_payment_methods_from_profile,
    _official_payment_methods_reply,
    _render_knowledge_context,
    _render_official_clinic_profile_context,
    _render_operational_catalog_context,
    get_global_config,
    get_knowledge_base_global_config,
)
from app.services.ai_structured_flow import (
    BusinessContext,
    KnowledgeBaseContext,
    RecentMessageContext,
    STRUCTURED_FLOW_SCHEMA_VERSION,
    _apply_safe_updates,
    _active_professional_ids_by_unit,
    _active_units,
    _create_structured_decision,
    _effective_system_action,
    _execute_system_action,
    _fallback_patient_reply,
    _minimal_decision_for_fallback,
    _run_extractor_with_retry,
    _run_reply_generator,
    build_ai_conversation_context,
    build_safe_persistence_plan,
)
from app.services.llm_service import classify_intent, run_llm_task
from app.services.service_catalog_service import get_service_catalog_items

AI_LAB_HISTORY_KEY = "ai_lab.history"
AI_LAB_MAX_HISTORY_ITEMS = 120
AI_LAB_MAX_EXAMPLES = 5
AI_LAB_STRUCTURED_ACTIONS = {
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
}
AI_LAB_READ_ONLY_SYSTEM_ACTIONS = {
    "none",
    "validate_unit",
    "query_units",
    "query_service",
    "query_insurance",
    "query_availability",
    "validate_slot",
}
AI_LAB_WRITE_PREVIEW_ACTIONS = {
    "validate_and_hold_slot",
    "confirm_appointment",
    "reschedule_appointment",
    "cancel_appointment",
    "handoff_to_human",
}
AILabFlowMode = Literal["auto", "legacy", "structured"]
AI_LAB_PLACEHOLDER_NAMES = {
    "paciente ia lab",
    "paciente teste ia lab",
    "lead ia lab",
    "lead teste ia lab",
}


def _short_text(value: object, *, max_length: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_length:
        return text
    return f"{text[:max_length].rstrip()}..."


def _is_lab_placeholder_name(value: object) -> bool:
    return _normalize_lookup_text(value) in AI_LAB_PLACEHOLDER_NAMES


def _coerce_confidence(value: object) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    casted = float(value)
    if casted < 0:
        return 0.0
    if casted > 1:
        return 1.0
    return round(casted, 4)


def _normalize_next_action(value: object) -> str:
    candidate = str(value or "none").strip() or "none"
    if candidate not in AI_ALLOWED_NEXT_ACTIONS and candidate not in AI_LAB_STRUCTURED_ACTIONS:
        return "none"
    return candidate


def _normalize_lookup_text(value: object) -> str:
    import unicodedata

    text = str(value or "").strip().lower()
    text = "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )
    return " ".join(text.split())


def _resolve_unit_from_lab_context(db: Session, *, tenant_id: UUID, text: str) -> Unit | None:
    units = list(
        db.scalars(
            select(Unit)
            .where(Unit.tenant_id == tenant_id, Unit.is_active.is_(True))
            .order_by(Unit.created_at.asc())
        )
    )
    if not units:
        return None

    haystack = _normalize_lookup_text(text)
    for unit in units:
        unit_name = _normalize_lookup_text(unit.name)
        unit_code = _normalize_lookup_text(unit.code)
        if unit_name and unit_name in haystack:
            return unit
        if unit_code and unit_code in haystack:
            return unit

    if "unidade principal" in haystack or "principal" in haystack or len(units) == 1:
        return units[0]
    return units[0]


def _lab_placeholder_phone() -> str:
    return f"5511{(uuid4().int % 10_000_000_000):010d}"


def _load_lab_conversation(
    db: Session,
    *,
    tenant_id: UUID,
    lab_conversation_id: str | None,
) -> Conversation | None:
    text = str(lab_conversation_id or "").strip()
    if not text:
        return None
    try:
        conversation_id = UUID(text)
    except ValueError as exc:
        raise ApiError(
            status_code=422,
            code="AI_LAB_CONVERSATION_INVALID",
            message="O identificador da conversa do IA Lab está inválido.",
        ) from exc
    conversation = db.get(Conversation, conversation_id)
    if not conversation or conversation.tenant_id != tenant_id:
        raise ApiError(
            status_code=404,
            code="AI_LAB_CONVERSATION_NOT_FOUND",
            message="A conversa salva do IA Lab não foi encontrada.",
        )
    tags = conversation.tags if isinstance(conversation.tags, list) else []
    if "ai_lab" not in tags:
        raise ApiError(
            status_code=422,
            code="AI_LAB_CONVERSATION_NOT_ALLOWED",
            message="A conversa informada não pertence ao IA Lab.",
        )
    return conversation


def _get_or_create_lab_conversation(
    db: Session,
    *,
    tenant_id: UUID,
    safe_context: str,
    lab_conversation_id: str | None,
) -> Conversation:
    existing = _load_lab_conversation(
        db,
        tenant_id=tenant_id,
        lab_conversation_id=lab_conversation_id,
    )
    if existing:
        return existing

    unit = _resolve_unit_from_lab_context(db, tenant_id=tenant_id, text=safe_context)
    phone = _lab_placeholder_phone()
    patient = Patient(
        tenant_id=tenant_id,
        unit_id=unit.id if unit else None,
        full_name="Paciente teste IA Lab",
        phone=phone,
        normalized_phone=phone,
        status="ativo",
        origin="ai_lab",
        lgpd_consent=True,
        marketing_opt_in=False,
        operational_notes="Conversa criada automaticamente pelo IA Lab para validacao interna.",
        tags_cache=["ai_lab"],
    )
    db.add(patient)
    db.flush()
    lead = Lead(
        tenant_id=tenant_id,
        patient_id=patient.id,
        name="Lead teste IA Lab",
        phone=phone,
        origin="ai_lab",
        interest="Validacao automatica",
        notes="Lead tecnico criado pelo IA Lab para testes internos.",
    )
    db.add(lead)
    db.flush()
    conversation = Conversation(
        tenant_id=tenant_id,
        unit_id=unit.id if unit else None,
        patient_id=patient.id,
        lead_id=lead.id,
        channel="whatsapp",
        external_thread_id=f"ai_lab:{uuid4()}",
        status=ConversationStatus.OPEN.value,
        ai_summary="Conversa tecnica criada pelo IA Lab.",
        ai_autoresponder_enabled=True,
        ai_autoresponder_consecutive_count=0,
        tags=["ai_lab", "structured_persisted"],
        last_message_at=datetime.now(UTC),
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def _lab_booking_visit_guidance(db: Session, *, tenant_id: UUID, context_text: str) -> str:
    unit = _resolve_unit_from_lab_context(db, tenant_id=tenant_id, text=context_text)
    unit_name = str(unit.name or "Unidade selecionada").strip() if unit else "Unidade selecionada"
    unit_address = _format_unit_address(unit.address) if unit else ""
    address_line = (
        f"• Endereço: {unit_address}"
        if unit_address
        else "• Endereço: não tenho o endereço desta unidade cadastrado com segurança; confirme com a equipe antes de se deslocar."
    )
    return "\n".join(
        [
            "Resumo final do agendamento:",
            f"• Unidade: {unit_name}",
            address_line,
            "• Para o atendimento: leve documento com foto e CPF.",
            "• Se tiver exames, radiografias, receitas ou documentos odontológicos recentes, leve também.",
            "• Chegue com 10 a 15 minutos de antecedência.",
            "Seu agendamento está confirmado. Se precisar alterar, cancelar ou tirar outra dúvida, avise por aqui. Aguardamos você!",
        ]
    )


def _should_append_lab_booking_guidance(*, reply_text: str, next_action: str) -> bool:
    normalized = _normalize_lookup_text(reply_text)
    if not normalized:
        return False

    has_visit_guidance = any(
        signal in normalized
        for signal in (
            "resumo final do agendamento",
            "endereco:",
            "documento com foto",
            "chegue com 10 a 15 minutos",
        )
    )
    has_closing_guidance = any(
        signal in normalized
        for signal in (
            "aguardamos voce",
            "se precisar alterar",
            "conversa encerrada",
        )
    )
    already_has_guidance = has_visit_guidance and has_closing_guidance
    if already_has_guidance:
        return False

    strong_confirmation_signals = (
        "agendamento confirmado",
        "agendamento esta confirmado",
        "agendamento ja esta confirmado",
        "consulta confirmada",
        "consulta agendada",
        "esta confirmada",
        "esta agendado",
        "ficou agendada",
        "ficou confirmado",
        "ficou reservado",
        "horario confirmado",
        "horario reservado",
    )
    if any(signal in normalized for signal in strong_confirmation_signals):
        return True

    if next_action not in {"finalize_booking_auto", "request_cpf_after_booking"}:
        return False

    return any(
        signal in normalized
        for signal in (
            "agendamento",
            "consulta",
            "avaliacao",
            "confirmad",
            "agendad",
            "reservad",
        )
    )


def _history_setting(db: Session, *, tenant_id: UUID) -> Setting | None:
    return db.scalar(
        select(Setting).where(
            Setting.tenant_id == tenant_id,
            Setting.key == AI_LAB_HISTORY_KEY,
        )
    )


def _normalize_history_entry(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    entry_id = str(raw.get("id") or "").strip()
    created_at = str(raw.get("created_at") or "").strip()
    input_text = _short_text(raw.get("input_text"), max_length=1600)
    if not entry_id or not created_at or not input_text:
        return None

    ai_action_payload = raw.get("ai_action_payload") if isinstance(raw.get("ai_action_payload"), dict) else {"context": "ai_lab"}
    if not str(ai_action_payload.get("context") or "").strip():
        ai_action_payload["context"] = "ai_lab"

    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    return {
        "id": entry_id,
        "created_at": created_at,
        "updated_at": str(raw.get("updated_at") or "").strip() or None,
        "input_text": input_text,
        "context_text": _short_text(raw.get("context_text"), max_length=1000),
        "ai_reply_text": _short_text(raw.get("ai_reply_text"), max_length=3000),
        "ai_next_action": _normalize_next_action(raw.get("ai_next_action")),
        "ai_action_payload": ai_action_payload,
        "ai_confidence": _coerce_confidence(raw.get("ai_confidence")),
        "ai_raw_output": _short_text(raw.get("ai_raw_output"), max_length=6000),
        "contract_valid": bool(raw.get("contract_valid")),
        "edited_response_text": _short_text(raw.get("edited_response_text"), max_length=3000),
        "note": _short_text(raw.get("note"), max_length=1200),
        "metadata": metadata,
    }


def _history_entries(db: Session, *, tenant_id: UUID) -> list[dict]:
    item = _history_setting(db, tenant_id=tenant_id)
    if not item or not isinstance(item.value, dict):
        return []

    raw_entries = item.value.get("entries")
    if not isinstance(raw_entries, list):
        return []

    normalized: list[dict] = []
    for raw in raw_entries:
        entry = _normalize_history_entry(raw)
        if entry:
            normalized.append(entry)
    return normalized


def _save_history_entries(db: Session, *, tenant_id: UUID, entries: list[dict]) -> None:
    payload = {
        "entries": entries[:AI_LAB_MAX_HISTORY_ITEMS],
        "updated_at": datetime.now(UTC).isoformat(),
    }
    item = _history_setting(db, tenant_id=tenant_id)
    if not item:
        item = Setting(
            tenant_id=tenant_id,
            key=AI_LAB_HISTORY_KEY,
            value=payload,
            is_secret=False,
        )
    else:
        item.value = payload
        item.is_secret = False
    db.add(item)
    db.commit()


def list_history(db: Session, *, tenant_id: UUID, limit: int = 50) -> list[dict]:
    rows = _history_entries(db, tenant_id=tenant_id)
    return rows[:max(1, min(limit, AI_LAB_MAX_HISTORY_ITEMS))]


def _render_training_examples(entries: list[dict]) -> str:
    approved_examples: list[dict] = []
    for entry in entries:
        edited = _short_text(entry.get("edited_response_text"), max_length=800)
        if not edited:
            continue
        approved_examples.append(
            {
                "input_text": _short_text(entry.get("input_text"), max_length=300),
                "edited_response_text": edited,
            }
        )
        if len(approved_examples) >= AI_LAB_MAX_EXAMPLES:
            break

    if not approved_examples:
        return ""

    lines = [
        "Exemplos recentes aprovados no IA Lab (use como referencia de estilo, sem copiar literalmente):",
    ]
    for idx, example in enumerate(approved_examples, start=1):
        lines.append(f"Exemplo {idx} - paciente: {example['input_text']}")
        lines.append(f"Exemplo {idx} - resposta aprovada: {example['edited_response_text']}")
    return "\n".join(lines)


def _build_history_entry(
    *,
    input_text: str,
    context_text: str,
    ai_reply_text: str,
    ai_next_action: str,
    ai_action_payload: dict,
    ai_confidence: float | None,
    ai_raw_output: str,
    contract_valid: bool,
    metadata: dict | None,
    edited_response_text: str = "",
    note: str = "",
) -> dict:
    now_iso = datetime.now(UTC).isoformat()
    payload = {
        "id": str(uuid4()),
        "created_at": now_iso,
        "updated_at": now_iso,
        "input_text": _short_text(input_text, max_length=1600),
        "context_text": _short_text(context_text, max_length=1000),
        "ai_reply_text": _short_text(ai_reply_text, max_length=3000),
        "ai_next_action": _normalize_next_action(ai_next_action),
        "ai_action_payload": ai_action_payload if isinstance(ai_action_payload, dict) else {"context": "ai_lab"},
        "ai_confidence": _coerce_confidence(ai_confidence),
        "ai_raw_output": _short_text(ai_raw_output, max_length=6000),
        "contract_valid": bool(contract_valid),
        "edited_response_text": _short_text(edited_response_text, max_length=3000),
        "note": _short_text(note, max_length=1200),
        "metadata": metadata if isinstance(metadata, dict) else {},
    }
    if not str(payload["ai_action_payload"].get("context") or "").strip():
        payload["ai_action_payload"]["context"] = "ai_lab"
    return payload


def _normalize_flow_mode(value: object) -> AILabFlowMode:
    candidate = str(value or "auto").strip().lower()
    if candidate in {"legacy", "structured", "auto"}:
        return candidate  # type: ignore[return-value]
    return "auto"


def _structured_flow_enabled_by_config(config: dict[str, Any]) -> bool:
    return bool(config.get("structured_flow_enabled"))


def _append_lab_recent_messages(
    *,
    context,
    inbound_text: str,
    safe_context: str,
    training_examples_context: str,
) -> None:
    now_iso = datetime.now(UTC).isoformat()
    extra_parts = [
        "[LAB] Simulacao controlada sem envio no WhatsApp real.",
        safe_context,
        training_examples_context,
    ]
    extra_body = "\n\n".join(part for part in extra_parts if str(part or "").strip())
    if extra_body:
        context.conversation_context.recent_messages.insert(
            0,
            RecentMessageContext(
                id=f"lab-context-{uuid4()}",
                direction="inbound",
                body=_short_text(extra_body, max_length=2400),
                interactive_reply=None,
                created_at=now_iso,
            ),
        )
    context.conversation_context.recent_messages.append(
        RecentMessageContext(
            id=f"lab-message-{uuid4()}",
            direction="inbound",
            body=inbound_text,
            interactive_reply=None,
            created_at=now_iso,
        )
    )


def _build_lab_structured_context(
    db: Session,
    *,
    tenant_id: UUID,
    inbound_text: str,
    safe_context: str,
    training_examples_context: str,
    include_knowledge: bool,
    config: dict[str, Any],
) -> tuple[Conversation, Message, Any]:
    unit = _resolve_unit_from_lab_context(
        db,
        tenant_id=tenant_id,
        text=f"{safe_context}\n{inbound_text}",
    )
    conversation = Conversation(
        id=uuid4(),
        tenant_id=tenant_id,
        unit_id=unit.id if unit else None,
        channel="whatsapp",
        status=ConversationStatus.OPEN.value,
        ai_autoresponder_enabled=True,
        ai_autoresponder_consecutive_count=0,
        tags=["ai_lab", "structured_preview"],
    )
    inbound_message = Message(
        id=uuid4(),
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND.value,
        channel="whatsapp",
        sender_type="patient",
        body=inbound_text,
        message_type="text",
        payload={"source": "ai_lab", "structured_preview": True},
        status=MessageStatus.RECEIVED.value,
    )
    context = build_ai_conversation_context(
        db,
        tenant_id=tenant_id,
        conversation=conversation,
        inbound_message=inbound_message,
        config=config,
    )
    if not include_knowledge:
        context.business_context = BusinessContext(
            units=context.business_context.units,
            services=[],
            professionals_summary=context.business_context.professionals_summary,
            knowledge_base=KnowledgeBaseContext(),
        )
    _append_lab_recent_messages(
        context=context,
        inbound_text=inbound_text,
        safe_context=safe_context,
        training_examples_context=training_examples_context,
    )
    return conversation, inbound_message, context


def _build_persisted_lab_structured_context(
    db: Session,
    *,
    tenant_id: UUID,
    inbound_text: str,
    safe_context: str,
    training_examples_context: str,
    include_knowledge: bool,
    config: dict[str, Any],
    lab_conversation_id: str | None,
) -> tuple[Conversation, Message, Any]:
    conversation = _get_or_create_lab_conversation(
        db,
        tenant_id=tenant_id,
        safe_context=safe_context,
        lab_conversation_id=lab_conversation_id,
    )
    unit = _resolve_unit_from_lab_context(
        db,
        tenant_id=tenant_id,
        text=f"{safe_context}\n{inbound_text}",
    )
    if unit and conversation.unit_id != unit.id:
        conversation.unit_id = unit.id
    conversation.status = ConversationStatus.OPEN.value
    conversation.last_message_at = datetime.now(UTC)
    db.add(conversation)
    inbound_message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND.value,
        channel=conversation.channel,
        sender_type="patient",
        body=inbound_text,
        message_type="text",
        payload={"source": "ai_lab", "structured_preview": True, "no_dispatch": True},
        status=MessageStatus.RECEIVED.value,
    )
    db.add(inbound_message)
    db.flush()
    context = build_ai_conversation_context(
        db,
        tenant_id=tenant_id,
        conversation=conversation,
        inbound_message=inbound_message,
        config=config,
    )
    if not include_knowledge:
        context.business_context = BusinessContext(
            units=context.business_context.units,
            services=[],
            professionals_summary=context.business_context.professionals_summary,
            knowledge_base=KnowledgeBaseContext(),
        )
    patient_context_updates: dict[str, Any] = {}
    if _is_lab_placeholder_name(context.patient_context.full_name):
        patient_context_updates["full_name"] = None
    if _is_lab_placeholder_name(context.patient_context.preferred_name):
        patient_context_updates["preferred_name"] = None
    if patient_context_updates:
        context.patient_context = context.patient_context.model_copy(update=patient_context_updates)
    _append_lab_recent_messages(
        context=context,
        inbound_text="",
        safe_context=safe_context,
        training_examples_context=training_examples_context,
    )
    return conversation, inbound_message, context


def _execute_structured_lab_system_action(
    db: Session,
    *,
    tenant_id: UUID,
    conversation: Conversation,
    inbound_message: Message,
    decision,
    action: str,
    params: dict[str, Any],
    context,
    config: dict[str, Any],
) -> dict[str, Any]:
    if action in AI_LAB_READ_ONLY_SYSTEM_ACTIONS:
        return _execute_system_action(
            db,
            tenant_id=tenant_id,
            conversation=conversation,
            inbound_message=inbound_message,
            decision=decision,
            action=action,
            params=params,
            context=context,
            config=config,
        )
    if action in {"validate_and_hold_slot", "confirm_appointment", "reschedule_appointment"}:
        validation = _execute_system_action(
            db,
            tenant_id=tenant_id,
            conversation=conversation,
            inbound_message=inbound_message,
            decision=decision,
            action="validate_slot",
            params=params,
            context=context,
            config=config,
        )
        return {
            "action": action,
            "status": "read_only_preview",
            "would_write": True,
            "validation": validation,
            "message": "No IA Lab esta acao foi apenas simulada. Nenhuma reserva, consulta ou reagendamento foi gravado.",
        }
    if action in {"cancel_appointment", "handoff_to_human"}:
        return {
            "action": action,
            "status": "read_only_preview",
            "would_write": True,
            "message": "No IA Lab esta acao foi apenas simulada. Nenhuma conversa, fila humana ou consulta foi alterada.",
        }
    return {
        "action": action,
        "status": "unsupported",
        "handoff_required": True,
        "reason": "unsupported_system_action",
    }


def _persist_structured_lab_turn(
    db: Session,
    *,
    tenant_id: UUID,
    conversation: Conversation,
    inbound_message: Message,
    patient_reply,
    decision,
    plan,
    applied_updates: dict[str, Any],
    system_action_result: dict[str, Any],
    extractor_payload: dict[str, Any] | None,
    reply_payload: dict[str, Any] | None,
) -> tuple[Message | None, str]:
    outbound_message: Message | None = None
    final_decision = "responded"
    if patient_reply.final_decision != "no_reply":
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
                "source": "ai_lab",
                "structured_flow": True,
                "no_dispatch": True,
                "reply_to_message_id": str(inbound_message.id),
                "intent": decision.intent,
                "system_action": system_action_result.get("action"),
                "interactive": interactive_payload,
            },
            status=MessageStatus.SENT.value,
            sent_at=datetime.now(UTC),
        )
        db.add(outbound_message)
        db.flush()
        db.add(
            MessageEvent(
                tenant_id=tenant_id,
                message_id=outbound_message.id,
                event_type="ai_lab_structured_response_saved",
                payload={"inbound_message_id": str(inbound_message.id), "system_action": system_action_result.get("action")},
            )
        )
    else:
        final_decision = "ignored"

    conversation.ai_summary = decision.message_summary
    conversation.ai_autoresponder_last_decision = final_decision
    conversation.ai_autoresponder_last_reason = patient_reply.decision_reason
    conversation.ai_autoresponder_last_at = datetime.now(UTC)
    conversation.ai_autoresponder_consecutive_count = int(conversation.ai_autoresponder_consecutive_count or 0) + 1
    conversation.last_message_at = datetime.now(UTC)
    db.add(conversation)

    _create_structured_decision(
        db,
        tenant_id=tenant_id,
        conversation=conversation,
        inbound_message=inbound_message,
        dedupe_key=f"ai_lab:{inbound_message.id}",
        final_decision=final_decision,
        decision_reason=patient_reply.decision_reason,
        generated_response=patient_reply.message if outbound_message else None,
        confidence=patient_reply.confidence,
        llm_payload=reply_payload or extractor_payload,
        outbound_message_id=outbound_message.id if outbound_message else None,
        metadata={
            "structured_flow": True,
            "ai_lab": True,
            "no_dispatch": True,
            "extractor": (extractor_payload or {}).get("metadata") if isinstance((extractor_payload or {}).get("metadata"), dict) else {},
            "reply": (reply_payload or {}).get("metadata") if isinstance((reply_payload or {}).get("metadata"), dict) else {},
            "decision": decision.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
            "applied_updates": applied_updates,
            "system_action_result": system_action_result,
        },
    )
    db.commit()
    db.refresh(conversation)
    if outbound_message is not None:
        db.refresh(outbound_message)
    return outbound_message, final_decision


def _structured_lab_result(
    *,
    inbound_text: str,
    safe_context: str,
    include_knowledge: bool,
    training_examples_context: str,
    contract_valid: bool,
    contract_retried: bool,
    extractor_error: str | None,
    extractor_payload: dict[str, Any] | None,
    reply_payload: dict[str, Any] | None,
    decision,
    plan,
    patient_reply,
    action: str,
    system_action_result: dict[str, Any],
    context,
    raw_output: str,
    interactive_preview: dict[str, Any] | None,
    auto_save_history: bool,
    tenant_id: UUID,
    db: Session,
    no_persistence: bool,
    lab_conversation_id: str | None = None,
    lab_inbound_message_id: str | None = None,
    lab_outbound_message_id: str | None = None,
) -> dict:
    metadata = {
        **(((reply_payload or extractor_payload or {}).get("metadata")) if isinstance((reply_payload or extractor_payload or {}).get("metadata"), dict) else {}),
        "flow_mode": "structured",
        "structured_flow": True,
        "no_persistence": no_persistence,
        "no_dispatch": True,
        "extractor_contract_valid": contract_valid,
        "system_action_status": system_action_result.get("status"),
    }
    if lab_conversation_id:
        metadata["lab_conversation_id"] = lab_conversation_id
    structured_flow = {
        "enabled": True,
        "schema_version": STRUCTURED_FLOW_SCHEMA_VERSION,
        "no_dispatch": True,
        "no_persistence": no_persistence,
        "extractor": {
            "contract_valid": contract_valid,
            "error": extractor_error,
            "metadata": (extractor_payload or {}).get("metadata") if isinstance((extractor_payload or {}).get("metadata"), dict) else {},
            "decision": decision.model_dump(mode="json"),
        },
        "safe_persistence_plan": plan.model_dump(mode="json"),
        "system_action_result": system_action_result,
        "patient_reply": patient_reply.model_dump(mode="json"),
        "context_preview": {
            "clinic": context.clinic_context.model_dump(mode="json"),
            "conversation": context.conversation_context.model_dump(mode="json"),
            "patient": context.patient_context.model_dump(mode="json"),
            "business_counts": {
                "units": len(context.business_context.units),
                "services": len(context.business_context.services),
                "professionals": len(context.business_context.professionals_summary),
                "faq": len(context.business_context.knowledge_base.faq),
            },
        },
    }

    saved_entry = None
    if auto_save_history:
        entry = _build_history_entry(
            input_text=inbound_text,
            context_text=safe_context,
            ai_reply_text=patient_reply.message,
            ai_next_action=action,
            ai_action_payload={
                "context": "ai_lab_structured",
                "intent": decision.intent,
                "system_action": action,
                "safe_persistence_plan": plan.model_dump(mode="json"),
                "lab_conversation_id": lab_conversation_id,
            },
            ai_confidence=patient_reply.confidence,
            ai_raw_output=raw_output,
            contract_valid=contract_valid,
            metadata={**metadata, "structured_flow_snapshot": structured_flow},
        )
        entries = _history_entries(db, tenant_id=tenant_id)
        entries.insert(0, entry)
        _save_history_entries(db, tenant_id=tenant_id, entries=entries)
        saved_entry = entry

    return {
        "status": "ok",
        "flow_mode": "structured",
        "no_dispatch": True,
        "no_persistence": no_persistence,
        "contract_valid": contract_valid,
        "contract_retried": contract_retried,
        "input_text": inbound_text,
        "context_text": safe_context,
        "intent": {
            "intent": decision.intent,
            "confidence": decision.confidence,
        },
        "response": {
            "reply_text": patient_reply.message,
            "next_action": action,
            "action_payload": {
                "context": "ai_lab_structured",
                "intent": decision.intent,
                "system_action": action,
                "system_action_result": system_action_result,
            },
            "confidence": patient_reply.confidence,
        },
        "raw_output": raw_output,
        "metadata": metadata,
        "interactive_preview": interactive_preview,
        "structured_flow": structured_flow,
        "training_examples_used": bool(training_examples_context),
        "custom_prompt_used": False,
        "knowledge_context_used": bool(include_knowledge),
        "history_entry": saved_entry,
        "lab_conversation_id": lab_conversation_id,
        "lab_inbound_message_id": lab_inbound_message_id,
        "lab_outbound_message_id": lab_outbound_message_id,
    }


def _simulate_structured(
    db: Session,
    *,
    tenant_id: UUID,
    inbound_text: str,
    safe_context: str,
    include_knowledge: bool,
    use_training_examples: bool,
    auto_save_history: bool,
    config: dict[str, Any],
    persist_conversation: bool = False,
    lab_conversation_id: str | None = None,
) -> dict:
    training_examples_context = ""
    if use_training_examples:
        training_examples_context = _render_training_examples(_history_entries(db, tenant_id=tenant_id))

    if persist_conversation:
        conversation, inbound_message, context = _build_persisted_lab_structured_context(
            db,
            tenant_id=tenant_id,
            inbound_text=inbound_text,
            safe_context=safe_context,
            training_examples_context=training_examples_context,
            include_knowledge=include_knowledge,
            config=config,
            lab_conversation_id=lab_conversation_id,
        )
        extractor_conversation_id: UUID | None = conversation.id
    else:
        conversation, inbound_message, context = _build_lab_structured_context(
            db,
            tenant_id=tenant_id,
            inbound_text=inbound_text,
            safe_context=safe_context,
            training_examples_context=training_examples_context,
            include_knowledge=include_knowledge,
            config=config,
        )
        extractor_conversation_id = None

    extractor_payload: dict[str, Any] | None = None
    reply_payload: dict[str, Any] | None = None
    extractor_error: str | None = None
    contract_valid = True
    contract_retried = False

    try:
        decision, extractor_payload = _run_extractor_with_retry(
            db,
            tenant_id=tenant_id,
            conversation_id=extractor_conversation_id,
            inbound_text=inbound_text,
            context=context,
        )
    except Exception as exc:
        if not db.is_active:
            db.rollback()
        contract_valid = False
        contract_retried = True
        extractor_error = str(exc)
        decision = _minimal_decision_for_fallback(inbound_text)

    active_units = {unit.id: unit for unit in _active_units(db, tenant_id=tenant_id)}
    active_services = {
        str(item["id"]): item
        for item in get_service_catalog_items(db, tenant_id=tenant_id)
        if item.get("is_active", True)
    }
    patient = db.get(Patient, conversation.patient_id) if persist_conversation and conversation.patient_id else None
    lead = db.get(Lead, conversation.lead_id) if persist_conversation and conversation.lead_id else None
    plan = build_safe_persistence_plan(
        decision=decision,
        conversation=conversation,
        inbound_message=inbound_message,
        patient=patient,
        lead=lead,
        confidence_threshold=float(config.get("confidence_threshold") or 0.65),
        active_unit_ids={str(unit_id) for unit_id in active_units},
        active_service_ids=set(active_services),
        active_professional_ids_by_unit=_active_professional_ids_by_unit(db, tenant_id=tenant_id),
    )
    applied_updates = (
        _apply_safe_updates(
            db,
            tenant_id=tenant_id,
            plan=plan,
            conversation=conversation,
            patient=patient,
            lead=lead,
            decision=decision,
        )
        if persist_conversation
        else {}
    )

    action = plan.system_actions_to_execute[0].action if plan.system_actions_to_execute else _effective_system_action(decision)
    params = (
        plan.system_actions_to_execute[0].params
        if plan.system_actions_to_execute
        else decision.system_action.params.model_dump(mode="json")
    )
    system_action_result = _execute_structured_lab_system_action(
        db,
        tenant_id=tenant_id,
        conversation=conversation,
        inbound_message=inbound_message,
        decision=decision,
        action=action,
        params=params,
        context=context,
        config=config,
    )

    try:
        patient_reply, reply_payload = _run_reply_generator(
            db,
            tenant_id=tenant_id,
            conversation_id=extractor_conversation_id,
            context=context,
            decision=decision,
            plan=plan,
            system_action_result=system_action_result,
        )
    except Exception as exc:
        if not db.is_active:
            db.rollback()
        logger.warning(
            "ai_lab.structured_reply_failed",
            tenant_id=str(tenant_id),
            error=str(exc),
        )
        patient_reply = _fallback_patient_reply(
            decision=decision,
            system_action_result=system_action_result,
            context=context,
        )

    interactive_preview = (
        patient_reply.interactive_payload
        if patient_reply.message_type == "interactive" and isinstance(patient_reply.interactive_payload, dict)
        else None
    )
    raw_output_payload = {
        "extractor_output": (extractor_payload or {}).get("output"),
        "reply_output": (reply_payload or {}).get("output"),
        "extractor_error": extractor_error,
    }
    raw_output = json.dumps(raw_output_payload, ensure_ascii=False, default=str)
    if persist_conversation:
        outbound_message, _final_decision = _persist_structured_lab_turn(
            db,
            tenant_id=tenant_id,
            conversation=conversation,
            inbound_message=inbound_message,
            patient_reply=patient_reply,
            decision=decision,
            plan=plan,
            applied_updates=applied_updates,
            system_action_result=system_action_result,
            extractor_payload=extractor_payload,
            reply_payload=reply_payload,
        )
        return _structured_lab_result(
            inbound_text=inbound_text,
            safe_context=safe_context,
            include_knowledge=include_knowledge,
            training_examples_context=training_examples_context,
            contract_valid=contract_valid,
            contract_retried=contract_retried,
            extractor_error=extractor_error,
            extractor_payload=extractor_payload,
            reply_payload=reply_payload,
            decision=decision,
            plan=plan,
            patient_reply=patient_reply,
            action=action,
            system_action_result=system_action_result,
            context=context,
            raw_output=raw_output,
            interactive_preview=interactive_preview,
            auto_save_history=auto_save_history,
            tenant_id=tenant_id,
            db=db,
            no_persistence=False,
            lab_conversation_id=str(conversation.id),
            lab_inbound_message_id=str(inbound_message.id),
            lab_outbound_message_id=str(outbound_message.id) if outbound_message else None,
        )
    return _structured_lab_result(
        inbound_text=inbound_text,
        safe_context=safe_context,
        include_knowledge=include_knowledge,
        training_examples_context=training_examples_context,
        contract_valid=contract_valid,
        contract_retried=contract_retried,
        extractor_error=extractor_error,
        extractor_payload=extractor_payload,
        reply_payload=reply_payload,
        decision=decision,
        plan=plan,
        patient_reply=patient_reply,
        action=action,
        system_action_result=system_action_result,
        context=context,
        raw_output=raw_output,
        interactive_preview=interactive_preview,
        auto_save_history=auto_save_history,
        tenant_id=tenant_id,
        db=db,
        no_persistence=True,
    )


def simulate(
    db: Session,
    *,
    tenant_id: UUID,
    message: str,
    context_text: str = "",
    include_knowledge: bool = True,
    use_training_examples: bool = True,
    auto_save_history: bool = True,
    flow_mode: AILabFlowMode = "auto",
    persist_conversation: bool = False,
    lab_conversation_id: str | None = None,
) -> dict:
    inbound_text = _short_text(message, max_length=1600)
    if not inbound_text:
        raise ApiError(
            status_code=400,
            code="AI_LAB_MESSAGE_REQUIRED",
            message="Informe a mensagem do paciente para simular.",
        )

    config = get_global_config(db, tenant_id=tenant_id)
    knowledge_context = ""
    knowledge_base: dict = {}
    official_clinic_profile: dict[str, str] = {}
    if include_knowledge:
        official_clinic_profile = _load_official_clinic_profile_context(db, tenant_id=tenant_id)
        knowledge_base = get_knowledge_base_global_config(db, tenant_id=tenant_id)
        knowledge_parts = [
            _render_official_clinic_profile_context(db, tenant_id=tenant_id),
            _render_knowledge_context(knowledge_base),
            _render_operational_catalog_context(db, tenant_id=tenant_id),
        ]
        knowledge_context = "\n\n".join(part for part in knowledge_parts if part)

    safe_context = _short_text(context_text, max_length=1000)
    if not safe_context:
        safe_context = "[LAB] Simulacao controlada sem envio no WhatsApp."

    selected_flow_mode = _normalize_flow_mode(flow_mode)
    if selected_flow_mode == "structured" or (
        selected_flow_mode == "auto" and _structured_flow_enabled_by_config(config)
    ):
        return _simulate_structured(
            db,
            tenant_id=tenant_id,
            inbound_text=inbound_text,
            safe_context=safe_context,
            include_knowledge=include_knowledge,
            use_training_examples=use_training_examples,
            auto_save_history=auto_save_history,
            config=config,
            persist_conversation=persist_conversation,
            lab_conversation_id=lab_conversation_id,
        )

    training_examples_context = ""
    if use_training_examples:
        training_examples_context = _render_training_examples(_history_entries(db, tenant_id=tenant_id))

    prompt = _prompt_for_autoresponder(
        config=config,
        context=safe_context,
        inbound_text=inbound_text,
        knowledge_context=knowledge_context,
        training_examples_context=training_examples_context,
    )

    intent_payload = {"intent": None, "confidence": None}
    try:
        intent_result = classify_intent(
            db,
            tenant_id=tenant_id,
            conversation_id=None,
            message=inbound_text,
        )
        parsed_intent = _parse_json_output(str(intent_result.get("output") or ""))
        intent_payload = {
            "intent": str(parsed_intent.get("intent") or "").strip() or None,
            "confidence": _coerce_confidence(parsed_intent.get("confidence")),
        }
    except Exception as exc:
        logger.warning(
            "ai_lab.intent_classification_failed",
            tenant_id=str(tenant_id),
            error=str(exc),
        )

    llm_result = run_llm_task(
        db,
        tenant_id=tenant_id,
        conversation_id=None,
        task="auto_responder",
        prompt=prompt,
    )
    raw_output = str(llm_result.get("output") or "").strip()
    contract = _parse_and_validate_ai_contract(raw_output)
    retried_contract = False

    if not contract:
        retried_contract = True
        retry_prompt = (
            f"{prompt}\n\n"
            "A saida anterior ficou invalida. "
            "Responda novamente com JSON valido e somente JSON, mantendo todos os campos obrigatorios."
        )
        llm_result = run_llm_task(
            db,
            tenant_id=tenant_id,
            conversation_id=None,
            task="auto_responder",
            prompt=retry_prompt,
        )
        raw_output = str(llm_result.get("output") or "").strip()
        contract = _parse_and_validate_ai_contract(raw_output)

    parsed_fallback = _parse_json_output(raw_output)
    reply_text = ""
    next_action = "none"
    action_payload: dict = {"context": "ai_lab"}
    confidence: float | None = None

    if contract:
        reply_text = contract["reply_text"]
        next_action = contract["next_action"]
        action_payload = contract["action_payload"]
        confidence = _coerce_confidence(contract.get("confidence"))
    else:
        reply_text = _short_text(parsed_fallback.get("reply_text"), max_length=3000) or _short_text(raw_output, max_length=3000)
        next_action = _normalize_next_action(parsed_fallback.get("next_action"))
        if isinstance(parsed_fallback.get("action_payload"), dict):
            action_payload = parsed_fallback["action_payload"]
        if not str(action_payload.get("context") or "").strip():
            action_payload["context"] = "ai_lab_invalid_contract"
        confidence = _coerce_confidence(parsed_fallback.get("confidence"))
    reply_text = normalize_immediate_action_reply_text(
        reply_text,
        next_action=next_action,
    )
    payment_source_guardrail_applied = False
    booking_guidance_applied = False
    if include_knowledge and _is_payment_methods_question(inbound_text):
        official_payment_methods = _official_payment_methods_from_profile(official_clinic_profile)
        knowledge_policies = (
            knowledge_base.get("operational_policies")
            if isinstance(knowledge_base.get("operational_policies"), dict)
            else {}
        )
        saved_payment_policy = _short_text(knowledge_policies.get("payment_policy"), max_length=500)
        if official_payment_methods or not saved_payment_policy:
            reply_text = _official_payment_methods_reply(official_clinic_profile)
            next_action = "none"
            action_payload = {"context": "official_payment_methods", "source": "clinic.profile"}
            confidence = 1.0 if official_payment_methods else confidence
            payment_source_guardrail_applied = True

    if _should_append_lab_booking_guidance(reply_text=reply_text, next_action=next_action):
        guidance_context = "\n".join(
            [
                safe_context,
                inbound_text,
                reply_text,
                str(action_payload or {}),
            ]
        )
        reply_text = (
            f"{reply_text.rstrip()}\n\n"
            f"{_lab_booking_visit_guidance(db, tenant_id=tenant_id, context_text=guidance_context)}"
        ).strip()
        booking_guidance_applied = True

    metadata = llm_result.get("metadata") if isinstance(llm_result.get("metadata"), dict) else {}
    metadata = {**metadata, "flow_mode": "legacy", "structured_flow": False}
    if payment_source_guardrail_applied:
        metadata = {**metadata, "payment_source_guardrail_applied": True}
    if booking_guidance_applied:
        metadata = {**metadata, "booking_guidance_applied": True}
    interactive_preview = (
        build_ai_action_interactive_preview(
            db,
            tenant_id=tenant_id,
            next_action=next_action,
            action_payload=action_payload,
            knowledge_base=knowledge_base if include_knowledge else None,
        )
        if booking_interactive_options_enabled(config)
        else None
    )
    if interactive_preview:
        metadata = {
            **metadata,
            "interactive_preview_present": True,
            "interactive_preview_action": next_action,
        }

    saved_entry = None
    if auto_save_history:
        entry = _build_history_entry(
            input_text=inbound_text,
            context_text=safe_context,
            ai_reply_text=reply_text,
            ai_next_action=next_action,
            ai_action_payload=action_payload,
            ai_confidence=confidence,
            ai_raw_output=raw_output,
            contract_valid=bool(contract),
            metadata=metadata,
        )
        entries = _history_entries(db, tenant_id=tenant_id)
        entries.insert(0, entry)
        _save_history_entries(db, tenant_id=tenant_id, entries=entries)
        saved_entry = entry

    return {
        "status": "ok",
        "flow_mode": "legacy",
        "no_dispatch": True,
        "no_persistence": True,
        "contract_valid": bool(contract),
        "contract_retried": retried_contract,
        "input_text": inbound_text,
        "context_text": safe_context,
        "intent": intent_payload,
        "response": {
            "reply_text": reply_text,
            "next_action": next_action,
            "action_payload": action_payload,
            "confidence": confidence,
        },
        "raw_output": raw_output,
        "metadata": metadata,
        "interactive_preview": interactive_preview,
        "training_examples_used": bool(training_examples_context),
        "custom_prompt_used": bool(_load_custom_autoresponder_prompt()),
        "knowledge_context_used": bool(knowledge_context),
        "history_entry": saved_entry,
    }


def save_manual_edit(
    db: Session,
    *,
    tenant_id: UUID,
    history_id: str | None,
    input_text: str,
    edited_response_text: str,
    note: str = "",
) -> dict:
    clean_edited = _short_text(edited_response_text, max_length=3000)
    if not clean_edited:
        raise ApiError(
            status_code=400,
            code="AI_LAB_EDIT_REQUIRED",
            message="Informe a resposta editada para salvar no historico.",
        )

    entries = _history_entries(db, tenant_id=tenant_id)
    now_iso = datetime.now(UTC).isoformat()

    if history_id:
        for entry in entries:
            if entry.get("id") != history_id:
                continue
            entry["edited_response_text"] = clean_edited
            entry["note"] = _short_text(note, max_length=1200)
            entry["updated_at"] = now_iso
            _save_history_entries(db, tenant_id=tenant_id, entries=entries)
            return entry

    new_entry = _build_history_entry(
        input_text=input_text,
        context_text="[LAB] Edicao manual",
        ai_reply_text="",
        ai_next_action="none",
        ai_action_payload={"context": "ai_lab_manual_edit"},
        ai_confidence=None,
        ai_raw_output="",
        contract_valid=False,
        metadata={"source": "manual_edit"},
        edited_response_text=clean_edited,
        note=note,
    )
    entries.insert(0, new_entry)
    _save_history_entries(db, tenant_id=tenant_id, entries=entries)
    return new_entry


def clear_history(db: Session, *, tenant_id: UUID) -> int:
    existing = _history_entries(db, tenant_id=tenant_id)
    removed = len(existing)
    _save_history_entries(db, tenant_id=tenant_id, entries=[])
    return removed

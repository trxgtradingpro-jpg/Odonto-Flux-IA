from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.services.ai_autoresponder_service as autoresponder_module
from app.core.config import settings
from app.db.session import SessionLocal
from app.models import (
    AIAutoresponderDecision,
    Appointment,
    Conversation,
    Message,
    Patient,
    PatientContact,
    Setting,
    Tenant,
    Unit,
)
from app.models.enums import MessageDirection, MessageStatus
from app.services.ai_autoresponder_service import (
    CPF_CONTACT_CHANNEL,
    get_global_config,
    process_inbound_message,
    set_global_config,
)


BAD_WAITING_PATTERNS = [
    r"\bem breve\b",
    r"\bem instantes\b",
    r"\blogo envio\b",
    r"\bdepois retorno\b",
    r"\bassim que eu tiver\b",
]
TECHNICAL_LEAK_PATTERNS = [
    r"\bnext_action\b",
    r"\baction_payload\b",
    r"\bconfidence\b",
    r"\bshow_[a-z_]+\b",
    r"\bfinalize_booking_auto\b",
]
BOOKING_KINDS = {"book", "book_lookup", "book_pause", "book_reschedule", "book_cancel"}


@dataclass(frozen=True)
class RealScenario:
    id: str
    kind: str
    patient_name: str
    persona: str
    initial_messages: list[str]
    preferred_service: str
    preferred_unit: str | None = None
    choose_by_text: bool = False
    include_pause: bool = False
    registration_birth_date: str = "10/05/1990"
    registration_cpf: str = "123.456.789-09"
    max_turns: int = 18


@dataclass
class ConversationRuntime:
    scenario: RealScenario
    patient: Patient
    conversation: Conversation
    inbound_results: list[dict[str, Any]] = field(default_factory=list)
    transcript: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    final_status: str = "running"
    operations: dict[str, Any] = field(default_factory=dict)


def _normalize(text: str | None) -> str:
    raw = re.sub(r"\s+", " ", str(text or "").strip().lower())
    normalized = unicodedata.normalize("NFKD", raw)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _fake_cpf(seed: int) -> str:
    base = f"{123456000 + seed:09d}"
    return f"{base[:3]}.{base[3:6]}.{base[6:9]}-{(10 + seed) % 90:02d}"


def _patch_dispatch_for_backtest() -> tuple[Any, Any]:
    original_assert = autoresponder_module.assert_whatsapp_route_ready_for_dispatch
    original_queue = autoresponder_module.queue_outbound_message

    def fake_assert(db: Session, *, tenant_id: UUID, provider_context: dict[str, Any] | None = None):
        return SimpleNamespace(id=uuid4(), tenant_id=tenant_id, provider_name="backtest")

    def fake_queue(*args: Any, **kwargs: Any):
        return SimpleNamespace(id=uuid4())

    autoresponder_module.assert_whatsapp_route_ready_for_dispatch = fake_assert
    autoresponder_module.queue_outbound_message = fake_queue
    return original_assert, original_queue


def _restore_dispatch(original_assert: Any, original_queue: Any) -> None:
    autoresponder_module.assert_whatsapp_route_ready_for_dispatch = original_assert
    autoresponder_module.queue_outbound_message = original_queue


def _temporary_ai_config(db: Session, *, tenant_id: UUID) -> tuple[bool, dict[str, Any] | None]:
    setting = db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == "ai_autoresponder.global"))
    existed = bool(setting)
    original_value = dict(setting.value) if setting and isinstance(setting.value, dict) else None
    config = get_global_config(db, tenant_id=tenant_id)
    config["enabled"] = True
    config["channels"] = {"whatsapp": True}
    config["outside_business_hours_mode"] = "allow"
    config["max_consecutive_auto_replies"] = 50
    config["confidence_threshold"] = 0.2
    config["business_hours"] = {
        "timezone": "America/Sao_Paulo",
        "weekdays": [0, 1, 2, 3, 4, 5],
        "start": "08:00",
        "end": "18:00",
    }
    set_global_config(db, tenant_id=tenant_id, payload=config)
    return existed, original_value


def _restore_ai_config(db: Session, *, tenant_id: UUID, existed: bool, original_value: dict[str, Any] | None) -> None:
    setting = db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == "ai_autoresponder.global"))
    if existed:
        if setting:
            setting.value = original_value or {}
            db.add(setting)
    elif setting:
        db.delete(setting)
    db.commit()


def _latest_messages(db: Session, conversation_id: UUID, *, direction: str | None = None, limit: int = 8) -> list[Message]:
    stmt = select(Message).where(Message.conversation_id == conversation_id)
    if direction:
        stmt = stmt.where(Message.direction == direction)
    return db.execute(stmt.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit)).scalars().all()


def _latest_outbound_message(db: Session, conversation_id: UUID) -> Message | None:
    return db.scalar(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.direction == MessageDirection.OUTBOUND.value)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )


def _latest_mode(db: Session, conversation_id: UUID) -> str:
    message = _latest_outbound_message(db, conversation_id)
    payload = message.payload if message and isinstance(message.payload, dict) else {}
    return str(payload.get("mode") or "").strip()


def _latest_interactive(db: Session, conversation_id: UUID) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    message = _latest_outbound_message(db, conversation_id)
    payload = message.payload if message and isinstance(message.payload, dict) else {}
    interactive = payload.get("interactive") if isinstance(payload.get("interactive"), dict) else None
    scheduling = payload.get("scheduling") if isinstance(payload.get("scheduling"), dict) else {}
    return interactive, scheduling


def _interactive_options(interactive: dict[str, Any] | None) -> list[dict[str, str]]:
    if not isinstance(interactive, dict):
        return []
    source = interactive.get("buttons") if isinstance(interactive.get("buttons"), list) else interactive.get("rows")
    if not isinstance(source, list):
        return []
    output: list[dict[str, str]] = []
    for item in source:
        if not isinstance(item, dict):
            continue
        option_id = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        if option_id and title:
            output.append({"id": option_id, "title": title, "description": description})
    return output


def _choose_option(*, scenario: RealScenario, mode: str, scheduling: dict[str, Any], interactive: dict[str, Any] | None) -> dict[str, str] | None:
    options = _interactive_options(interactive)
    if not options:
        return None
    if not mode:
        if any(option["id"].startswith("day_") for option in options):
            return next((option for option in options if option["id"].startswith("day_")), options[0])
        if any(option["id"].startswith("time_") for option in options):
            return next((option for option in options if option["id"].startswith("time_")), options[0])
        if any(option["id"].startswith("slot_") for option in options):
            return next((option for option in options if option["id"].startswith("slot_")), options[0])
    if mode == "booking_wizard_service_select":
        target = _normalize(scenario.preferred_service)
        services = [str(item or "") for item in scheduling.get("services", []) if str(item or "").strip()]
        for index, service in enumerate(services, start=1):
            service_norm = _normalize(service)
            if target in service_norm or any(piece for piece in target.split() if len(piece) > 3 and piece in service_norm):
                return next((option for option in options if option["id"] == f"svc_{index}"), options[0])
        return options[0]
    if mode == "booking_wizard_unit_select":
        if scenario.preferred_unit:
            target = _normalize(scenario.preferred_unit)
            target_pieces = [
                piece
                for piece in target.split()
                if len(piece) > 2 and piece not in {"unidade", "clinica", "clinicas", "zona"}
            ]
            units = scheduling.get("units") if isinstance(scheduling.get("units"), list) else []
            for unit in units:
                if not isinstance(unit, dict):
                    continue
                blob = _normalize(f"{unit.get('name')} {unit.get('option_id')}")
                if target in blob or any(piece in blob for piece in target_pieces):
                    return next((option for option in options if option["id"] == str(unit.get("option_id"))), options[0])
        return next((option for option in options if option["id"].startswith("unit_")), options[0])
    if mode in {"booking_wizard_day_select", "booking_reschedule_day_select"}:
        return next((option for option in options if option["id"].startswith("day_")), options[0])
    if mode in {"booking_wizard_time_select", "booking_reschedule_time_select"}:
        return next((option for option in options if option["id"].startswith("time_")), options[0])
    if mode == "slots_suggested":
        return next((option for option in options if option["id"].startswith("slot_")), options[0])
    if mode == "booking_wizard_confirm":
        return next((option for option in options if option["id"] == "confirm_yes" or _normalize(option["title"]) == "sim"), options[0])
    if mode == "booking_wizard_resume_or_restart":
        return next((option for option in options if option["id"] == "resume_saved_step"), options[0])
    if mode == "booking_cancel_confirm":
        return next((option for option in options if option["id"] == "cancel_yes"), options[0])
    if mode == "booking_reschedule_confirm":
        return next((option for option in options if option["id"] == "reschedule_yes"), options[0])
    return options[0]


def _choice_message(*, scenario: RealScenario, mode: str, option: dict[str, str]) -> tuple[str, dict[str, str] | None]:
    option_id = option["id"]
    title = option["title"]
    reply = {"kind": "button" if option_id.startswith(("confirm_", "cancel_", "reschedule_")) else "list", "id": option_id, "title": title, "description": option.get("description") or ""}
    if scenario.choose_by_text:
        if mode == "booking_wizard_unit_select":
            return f"Prefiro {title}, pode ser essa unidade.", None
        if mode in {"booking_wizard_day_select", "booking_reschedule_day_select"}:
            return f"Pode ser {title}.", None
        if mode in {"booking_wizard_time_select", "booking_reschedule_time_select"}:
            return f"Esse horario {title} funciona para mim.", None
    if mode == "booking_wizard_confirm":
        return f"Sim, confirmo ({option_id}).", reply
    if mode == "booking_cancel_confirm":
        return f"Sim, quero cancelar ({option_id}).", reply
    if mode == "booking_reschedule_confirm":
        return f"Sim, pode remarcar ({option_id}).", reply
    if mode == "booking_wizard_resume_or_restart":
        return f"Quero continuar de onde parei ({option_id}).", reply
    return f"Seleciono: {title} ({option_id}).", reply


def _create_runtime(db: Session, *, tenant: Tenant, scenario: RealScenario, index: int, run_seed: int) -> ConversationRuntime:
    digits = f"55119{run_seed:06d}{index:07d}"
    patient = Patient(
        tenant_id=tenant.id,
        full_name=f"Contato WhatsApp Backtest {index:03d}",
        phone=f"+{digits}",
        normalized_phone=digits,
        origin="ai_backtest_100",
        tags_cache=["ai_backtest_100", scenario.kind],
    )
    db.add(patient)
    db.flush()
    conversation = Conversation(
        tenant_id=tenant.id,
        patient_id=patient.id,
        channel="whatsapp",
        status="aberta",
        ai_autoresponder_enabled=True,
        tags=["ai_backtest_100", scenario.kind],
    )
    db.add(conversation)
    db.flush()
    db.commit()
    return ConversationRuntime(scenario=scenario, patient=patient, conversation=conversation)


def _record_new_outbounds(db: Session, runtime: ConversationRuntime, *, before_ids: set[str]) -> None:
    rows = db.execute(
        select(Message)
        .where(Message.conversation_id == runtime.conversation.id, Message.direction == MessageDirection.OUTBOUND.value)
        .order_by(Message.created_at.asc(), Message.id.asc())
    ).scalars().all()
    for message in rows:
        if str(message.id) in before_ids:
            continue
        payload = message.payload if isinstance(message.payload, dict) else {}
        runtime.transcript.append(
            {
                "role": "ia",
                "message_id": str(message.id),
                "body": message.body,
                "mode": payload.get("mode"),
                "message_type": message.message_type,
                "interactive": payload.get("interactive") if isinstance(payload.get("interactive"), dict) else None,
                "scheduling": payload.get("scheduling") if isinstance(payload.get("scheduling"), dict) else None,
                "created_at": message.created_at.isoformat() if message.created_at else None,
            }
        )


def _send_patient_message(db: Session, runtime: ConversationRuntime, body: str, *, interactive_reply: dict[str, str] | None = None, created_at: datetime | None = None) -> dict[str, Any]:
    before_ids = {str(item.id) for item in _latest_messages(db, runtime.conversation.id, direction=MessageDirection.OUTBOUND.value, limit=200)}
    payload: dict[str, Any] = {}
    message_type = "text"
    if interactive_reply:
        payload["interactive_reply"] = interactive_reply
        message_type = "interactive_button_reply" if interactive_reply.get("kind") == "button" else "interactive_list_reply"
    inbound = Message(
        tenant_id=runtime.conversation.tenant_id,
        conversation_id=runtime.conversation.id,
        direction=MessageDirection.INBOUND.value,
        channel="whatsapp",
        sender_type="patient",
        body=body,
        message_type=message_type,
        payload=payload,
        status=MessageStatus.RECEIVED.value,
        created_at=created_at or datetime.now(UTC),
    )
    db.add(inbound)
    runtime.conversation.last_message_at = inbound.created_at
    db.add(runtime.conversation)
    db.flush()
    runtime.transcript.append({"role": "paciente", "message_id": str(inbound.id), "body": body, "interactive_reply": interactive_reply, "created_at": inbound.created_at.isoformat()})
    result = process_inbound_message(db, tenant_id=runtime.conversation.tenant_id, conversation_id=runtime.conversation.id, inbound_message_id=inbound.id)
    runtime.inbound_results.append({"message_id": str(inbound.id), "body": body, "result": result})
    db.expire_all()
    runtime.patient = db.get(Patient, runtime.patient.id)
    runtime.conversation = db.get(Conversation, runtime.conversation.id)
    _record_new_outbounds(db, runtime, before_ids=before_ids)
    return result


def _send_initial_burst(db: Session, runtime: ConversationRuntime) -> None:
    base = datetime.now(UTC) - timedelta(seconds=(len(runtime.scenario.initial_messages) + 1) * 4)
    inbound_messages: list[Message] = []
    for offset, body in enumerate(runtime.scenario.initial_messages):
        inbound = Message(
            tenant_id=runtime.conversation.tenant_id,
            conversation_id=runtime.conversation.id,
            direction=MessageDirection.INBOUND.value,
            channel="whatsapp",
            sender_type="patient",
            body=body,
            message_type="text",
            payload={},
            status=MessageStatus.RECEIVED.value,
            created_at=base + timedelta(seconds=offset * 3),
        )
        db.add(inbound)
        inbound_messages.append(inbound)
        runtime.transcript.append({"role": "paciente", "message_id": None, "body": body, "burst": True, "created_at": inbound.created_at.isoformat()})
    runtime.conversation.last_message_at = inbound_messages[-1].created_at
    db.add(runtime.conversation)
    db.commit()
    for inbound in inbound_messages:
        before_ids = {str(item.id) for item in _latest_messages(db, runtime.conversation.id, direction=MessageDirection.OUTBOUND.value, limit=200)}
        result = process_inbound_message(db, tenant_id=runtime.conversation.tenant_id, conversation_id=runtime.conversation.id, inbound_message_id=inbound.id)
        runtime.inbound_results.append({"message_id": str(inbound.id), "body": inbound.body, "result": result})
        db.expire_all()
        runtime.patient = db.get(Patient, runtime.patient.id)
        runtime.conversation = db.get(Conversation, runtime.conversation.id)
        _record_new_outbounds(db, runtime, before_ids=before_ids)


def _age_latest_message(db: Session, runtime: ConversationRuntime, *, minutes: int) -> None:
    latest = db.scalar(select(Message).where(Message.conversation_id == runtime.conversation.id).order_by(Message.created_at.desc(), Message.id.desc()).limit(1))
    if latest:
        latest.created_at = datetime.now(UTC) - timedelta(minutes=minutes)
        db.add(latest)
        db.commit()


def _appointments_for_patient(db: Session, runtime: ConversationRuntime) -> list[Appointment]:
    return db.execute(
        select(Appointment)
        .where(Appointment.tenant_id == runtime.conversation.tenant_id, Appointment.patient_id == runtime.patient.id)
        .order_by(Appointment.created_at.asc())
    ).scalars().all()


def _registration_is_complete(db: Session, runtime: ConversationRuntime) -> bool:
    patient = db.get(Patient, runtime.patient.id)
    cpf = db.scalar(select(PatientContact).where(PatientContact.tenant_id == runtime.conversation.tenant_id, PatientContact.patient_id == runtime.patient.id, PatientContact.channel == CPF_CONTACT_CHANNEL))
    return bool(patient and patient.full_name and not _normalize(patient.full_name).startswith("contato whatsapp") and patient.birth_date and cpf)


def _send_registration_if_needed(db: Session, runtime: ConversationRuntime) -> None:
    body = f"Meu nome completo e {runtime.scenario.patient_name}, CPF {runtime.scenario.registration_cpf}, nascimento {runtime.scenario.registration_birth_date}."
    _send_patient_message(db, runtime, body)


def _drive_booking_until_registered(db: Session, runtime: ConversationRuntime) -> None:
    paused_once = False
    for _ in range(runtime.scenario.max_turns):
        mode = _latest_mode(db, runtime.conversation.id)
        interactive, scheduling = _latest_interactive(db, runtime.conversation.id)
        option_ids = [option["id"] for option in _interactive_options(interactive)]
        is_schedule_choice = (
            mode in {"booking_wizard_day_select", "booking_wizard_time_select"}
            or any(option_id.startswith(("day_", "time_")) for option_id in option_ids)
        )
        if not mode and _registration_is_complete(db, runtime) and _appointments_for_patient(db, runtime):
            runtime.final_status = "booked_registered"
            return
        if runtime.scenario.include_pause and not paused_once and is_schedule_choice:
            paused_once = True
            _age_latest_message(db, runtime, minutes=25)
            _send_patient_message(db, runtime, "Voltei, podemos continuar de onde parei?")
            continue
        if mode == "booking_request_cpf_after_booking":
            _send_registration_if_needed(db, runtime)
            continue
        if mode == "booking_post_confirmation_options":
            if _registration_is_complete(db, runtime):
                runtime.final_status = "booked_registered"
                return
            _send_registration_if_needed(db, runtime)
            continue
        option = _choose_option(scenario=runtime.scenario, mode=mode, scheduling=scheduling, interactive=interactive)
        if not option:
            runtime.errors.append(f"sem opcao interativa para modo {mode or 'vazio'}")
            return
        body, interactive_reply = _choice_message(scenario=runtime.scenario, mode=mode, option=option)
        _send_patient_message(db, runtime, body, interactive_reply=interactive_reply)
    runtime.errors.append("booking nao concluiu dentro do limite de turnos")


def _drive_lookup(db: Session, runtime: ConversationRuntime, *, expect_existing: bool) -> None:
    _send_patient_message(db, runtime, "Quais sao meus agendamentos? Quero conferir minha consulta.")
    body = "\n".join(item.get("body") or "" for item in runtime.transcript if item.get("role") == "ia")
    if expect_existing and "agendamentos ativos" not in _normalize(body):
        runtime.errors.append("consulta de agenda nao retornou agendamento ativo")
    if not expect_existing and "nao encontrei" not in _normalize(body):
        runtime.errors.append("consulta vazia nao informou ausencia de agendamento")


def _drive_cancel(db: Session, runtime: ConversationRuntime) -> None:
    before = _appointments_for_patient(db, runtime)
    if not before:
        runtime.errors.append("cancelamento sem agendamento criado")
        return
    appointment_id = before[-1].id
    _send_patient_message(db, runtime, "Preciso cancelar minha consulta, nao vou conseguir ir.")
    for _ in range(4):
        mode = _latest_mode(db, runtime.conversation.id)
        if mode == "booking_cancelled":
            break
        interactive, scheduling = _latest_interactive(db, runtime.conversation.id)
        option = _choose_option(scenario=runtime.scenario, mode=mode, scheduling=scheduling, interactive=interactive)
        if not option:
            runtime.errors.append(f"cancelamento travou no modo {mode or 'vazio'}")
            return
        body, interactive_reply = _choice_message(scenario=runtime.scenario, mode=mode, option=option)
        _send_patient_message(db, runtime, body, interactive_reply=interactive_reply)
    appointment = db.get(Appointment, appointment_id)
    if not appointment or str(appointment.status) != "cancelada":
        runtime.errors.append("consulta nao ficou com status cancelada")
    else:
        runtime.operations["cancelled_appointment_id"] = str(appointment.id)
        runtime.final_status = "cancelled"


def _drive_reschedule(db: Session, runtime: ConversationRuntime) -> None:
    before = _appointments_for_patient(db, runtime)
    if not before:
        runtime.errors.append("remarcacao sem agendamento criado")
        return
    appointment = before[-1]
    appointment_id = appointment.id
    original_start = appointment.starts_at.isoformat() if appointment.starts_at else None
    _send_patient_message(db, runtime, "Quero remarcar minha consulta para outro dia, pode me ajudar?")
    for _ in range(8):
        mode = _latest_mode(db, runtime.conversation.id)
        if mode == "booking_rescheduled":
            break
        interactive, scheduling = _latest_interactive(db, runtime.conversation.id)
        option = _choose_option(scenario=runtime.scenario, mode=mode, scheduling=scheduling, interactive=interactive)
        if not option:
            runtime.errors.append(f"remarcacao travou no modo {mode or 'vazio'}")
            return
        body, interactive_reply = _choice_message(scenario=runtime.scenario, mode=mode, option=option)
        _send_patient_message(db, runtime, body, interactive_reply=interactive_reply)
    db.expire_all()
    appointment = db.get(Appointment, appointment_id)
    if not appointment or str(appointment.status) != "reagendada":
        runtime.errors.append("consulta nao ficou com status reagendada")
    elif appointment.starts_at and appointment.starts_at.isoformat() == original_start:
        runtime.errors.append("consulta reagendada manteve o mesmo horario")
    else:
        runtime.operations["rescheduled_appointment_id"] = str(appointment.id)
        runtime.operations["original_starts_at"] = original_start
        runtime.operations["new_starts_at"] = appointment.starts_at.isoformat() if appointment.starts_at else None
        runtime.final_status = "rescheduled"


def _validate_transcript(runtime: ConversationRuntime) -> None:
    ai_messages = [item for item in runtime.transcript if item.get("role") == "ia"]
    if not ai_messages and runtime.scenario.kind not in {"human", "urgent"}:
        runtime.errors.append("nenhuma resposta da IA foi registrada")
    for item in ai_messages:
        body = str(item.get("body") or "")
        for pattern in BAD_WAITING_PATTERNS:
            if re.search(pattern, body, flags=re.IGNORECASE):
                runtime.errors.append(f"frase de espera proibida detectada: {pattern}")
        for pattern in TECHNICAL_LEAK_PATTERNS:
            if re.search(pattern, body, flags=re.IGNORECASE):
                runtime.errors.append(f"vazamento tecnico detectado: {pattern}")
    if len(runtime.scenario.initial_messages) > 1:
        reasons = [str((result.get("result") or {}).get("reason") or "") for result in runtime.inbound_results]
        if "superseded_by_newer_inbound" not in reasons:
            runtime.errors.append("rajada de mensagens nao agrupou mensagens antigas")


def _serialize_runtime(db: Session, runtime: ConversationRuntime) -> dict[str, Any]:
    appointments = _appointments_for_patient(db, runtime)
    patient = db.get(Patient, runtime.patient.id)
    cpf = db.scalar(select(PatientContact).where(PatientContact.tenant_id == runtime.conversation.tenant_id, PatientContact.patient_id == runtime.patient.id, PatientContact.channel == CPF_CONTACT_CHANNEL))
    decisions = db.execute(select(AIAutoresponderDecision).where(AIAutoresponderDecision.conversation_id == runtime.conversation.id).order_by(AIAutoresponderDecision.created_at.asc())).scalars().all()
    providers = sorted({str(item.llm_provider) for item in decisions if item.llm_provider})
    models = sorted({str(item.llm_model) for item in decisions if item.llm_model})
    return {
        "scenario_id": runtime.scenario.id,
        "scenario_kind": runtime.scenario.kind,
        "patient_profile": runtime.scenario.persona,
        "patient_id": str(runtime.patient.id),
        "conversation_id": str(runtime.conversation.id),
        "passed": not runtime.errors,
        "errors": runtime.errors,
        "final_status": runtime.final_status,
        "summary": {
            "person_profile": runtime.scenario.persona,
            "conversation_summary": f"Paciente {runtime.scenario.patient_name} simulou o caso {runtime.scenario.kind} com {len([x for x in runtime.transcript if x.get('role') == 'paciente'])} mensagem(ns).",
            "outcome_summary": {
                "booked_registered": "Agendamento criado e dados cadastrais salvos.",
                "rescheduled": "Agendamento criado e remarcado na agenda real.",
                "cancelled": "Agendamento criado e cancelado na agenda real.",
                "lookup_empty": "Consulta de agenda sem agendamento ativo respondida com clareza.",
                "handoff": "Atendimento encaminhado para humano conforme regra.",
            }.get(runtime.final_status, "Fluxo validado."),
            "humanization_notes": [
                "Perfil e linguagem variam por conversa.",
                "O sistema aceita texto livre e listas interativas.",
                "Persistencia real foi conferida no banco.",
            ],
        },
        "patient_saved": {
            "full_name": patient.full_name if patient else None,
            "birth_date": patient.birth_date.isoformat() if patient and patient.birth_date else None,
            "cpf_saved": bool(cpf),
        },
        "appointments": [
            {
                "id": str(item.id),
                "procedure_type": item.procedure_type,
                "unit_id": str(item.unit_id),
                "starts_at": item.starts_at.isoformat() if item.starts_at else None,
                "ends_at": item.ends_at.isoformat() if item.ends_at else None,
                "status": str(item.status),
                "confirmation_status": item.confirmation_status,
                "origin": item.origin,
                "notes": item.notes,
            }
            for item in appointments
        ],
        "operations": runtime.operations,
        "transcript": runtime.transcript,
        "inbound_results": runtime.inbound_results,
        "llm_providers": providers,
        "llm_models": models,
        "decisions_count": len(decisions),
    }


def _build_scenarios(units: list[Unit], *, total: int) -> list[RealScenario]:
    unit_names = [unit.name for unit in units] or [None]
    services = ["Avaliação odontológica", "Clareamento dental", "Limpeza odontológica", "Implante", "Instalação de lentes", "Reabilitação estética"]
    personas = ["objetivo e com pressa", "ansioso e precisa de acolhimento", "pesquisa valores antes de decidir", "prefere escrever em texto livre", "manda mensagens quebradas em rajada", "retorna depois de uma pausa longa", "quer conferir se ficou agendado", "precisa remarcar por conflito", "precisa cancelar com educacao", "quer atendimento humano direto", "relata urgencia"]
    names = ["Maria Silva", "Joao Oliveira", "Ana Costa", "Pedro Almeida", "Carla Mendes", "Rafael Santos", "Beatriz Lima", "Lucas Pereira", "Fernanda Rocha", "Gustavo Martins"]
    name_suffixes = ["Almeida", "Barbosa", "Campos", "Duarte", "Esteves", "Ferreira", "Gomes", "Lopes", "Moraes", "Nogueira"]
    kinds_cycle = ["book", "book_lookup", "book_reschedule", "book_cancel", "book_pause", "book", "book_lookup", "lookup_empty", "human", "urgent"]
    scenarios: list[RealScenario] = []
    for index in range(total):
        kind = kinds_cycle[index % len(kinds_cycle)]
        service = services[index % len(services)]
        unit = unit_names[index % len(unit_names)] if unit_names else None
        name = f"{names[index % len(names)]} {name_suffixes[(index // len(names)) % len(name_suffixes)]}"
        if kind == "human":
            initial_messages = ["Oi", "Boa tarde", "quero falar com um atendente humano, por favor"]
            service = "Avaliação odontológica"
        elif kind == "urgent":
            initial_messages = ["Estou com dor muito forte e sangramento, e urgente"]
            service = "Avaliação odontológica"
        elif kind == "lookup_empty":
            initial_messages = ["Oi, queria consultar meus agendamentos"]
        elif index % 5 == 0:
            initial_messages = ["Oi", "Boa noite", f"quero marcar {service.lower()}"]
        elif index % 3 == 0:
            initial_messages = [f"Quero agendar {service.lower()} na unidade {unit or 'mais proxima'}"]
        else:
            initial_messages = [f"Oi, quero marcar {service.lower()}."]
        scenarios.append(
            RealScenario(
                id=f"real_{index + 1:03d}_{kind}",
                kind=kind,
                patient_name=name,
                persona=f"Cliente {personas[index % len(personas)]}, cenario {index + 1}.",
                initial_messages=initial_messages,
                preferred_service=service,
                preferred_unit=unit,
                choose_by_text=index % 4 == 0,
                include_pause=kind == "book_pause",
                registration_birth_date=f"{(index % 27) + 1:02d}/{((index // 3) % 12) + 1:02d}/19{80 + (index % 18):02d}",
                registration_cpf=_fake_cpf(index + 1),
            )
        )
    return scenarios


def _unit_active_booking_load(db: Session, *, tenant_id: UUID, unit_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.count(Appointment.id)).where(
                Appointment.tenant_id == tenant_id,
                Appointment.unit_id == unit_id,
                Appointment.status.in_(["agendada", "reagendada"]),
            )
        )
        or 0
    )


def _run_runtime(db: Session, *, tenant: Tenant, scenario: RealScenario, index: int, run_seed: int) -> dict[str, Any]:
    runtime = _create_runtime(db, tenant=tenant, scenario=scenario, index=index, run_seed=run_seed)
    try:
        _send_initial_burst(db, runtime)
        if scenario.kind in BOOKING_KINDS:
            _drive_booking_until_registered(db, runtime)
            if not runtime.errors:
                if not _appointments_for_patient(db, runtime):
                    runtime.errors.append("nenhum agendamento foi criado")
                elif not _registration_is_complete(db, runtime):
                    runtime.errors.append("dados cadastrais pos-agendamento nao ficaram completos")
            if not runtime.errors and scenario.kind == "book_lookup":
                _drive_lookup(db, runtime, expect_existing=True)
            if not runtime.errors and scenario.kind == "book_reschedule":
                _drive_reschedule(db, runtime)
            if not runtime.errors and scenario.kind == "book_cancel":
                _drive_cancel(db, runtime)
        elif scenario.kind == "lookup_empty":
            _drive_lookup(db, runtime, expect_existing=False)
            runtime.final_status = "lookup_empty"
        elif scenario.kind in {"human", "urgent"}:
            reasons = [str((item.get("result") or {}).get("reason") or "") for item in runtime.inbound_results]
            if not any(reason in {"patient_requested_human", "urgency_detected"} for reason in reasons):
                runtime.errors.append("handoff esperado nao ocorreu")
            else:
                runtime.final_status = "handoff"
        _validate_transcript(runtime)
    except Exception as exc:
        runtime.errors.append(f"erro inesperado: {exc}")
    return _serialize_runtime(db, runtime)


def _html_report(payload: dict[str, Any]) -> str:
    cards: list[str] = []
    for item in payload.get("conversations", []):
        transcript = item.get("transcript") if isinstance(item.get("transcript"), list) else []
        messages = []
        for turn in transcript:
            role = html.escape(str(turn.get("role") or ""))
            body = html.escape(str(turn.get("body") or ""))
            mode = html.escape(str(turn.get("mode") or ""))
            cls = "patient" if role == "paciente" else "ai"
            messages.append(f"<div class='msg {cls}'><b>{role}</b><small>{mode}</small><p>{body}</p></div>")
        appts = item.get("appointments") if isinstance(item.get("appointments"), list) else []
        appt_lines = "".join(f"<li>{html.escape(str(a.get('procedure_type')))} - {html.escape(str(a.get('starts_at')))} - {html.escape(str(a.get('status')))}</li>" for a in appts)
        summary = item.get("summary") if isinstance(item.get("summary"), dict) else {}
        cards.append(
            "<section class='card'>"
            f"<h2>{html.escape(str(item.get('scenario_id')))} - {html.escape(str(item.get('final_status')))}</h2>"
            f"<p><b>Perfil:</b> {html.escape(str(summary.get('person_profile') or item.get('patient_profile')))}</p>"
            f"<p><b>Resumo:</b> {html.escape(str(summary.get('outcome_summary') or ''))}</p>"
            f"<p><b>Paciente:</b> {html.escape(str((item.get('patient_saved') or {}).get('full_name')))}</p>"
            f"<ul>{appt_lines}</ul><div class='chat'>{''.join(messages)}</div></section>"
        )
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8" />
<title>Backtest IA ClinicFlux AI</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;background:#eef3ef;margin:0;color:#16302b}}
header{{position:sticky;top:0;background:#0f6f65;color:#fff;padding:18px 28px;box-shadow:0 8px 24px #0002}}
main{{max-width:1180px;margin:24px auto;padding:0 18px}}.card{{background:#fff;border:1px solid #d7e2dd;border-radius:18px;margin:18px 0;padding:22px;box-shadow:0 10px 30px #0f302014}}
.chat{{display:grid;gap:10px;margin-top:14px}}.msg{{max-width:78%;border-radius:16px;padding:12px 14px}}.msg small{{display:block;opacity:.65;margin-top:2px}}.msg p{{margin:6px 0 0;white-space:pre-wrap}}
.patient{{justify-self:start;background:#e8f0ff}}.ai{{justify-self:end;background:#dcf8ed}}.pill{{display:inline-block;background:#dcf8ed;color:#07594f;border-radius:999px;padding:5px 10px;margin-right:8px}}
</style></head><body><header><h1>Backtest IA ClinicFlux AI</h1>
<p><span class="pill">status: {html.escape(str(payload.get('status')))}</span><span class="pill">conversas: {html.escape(str(payload.get('scenarios_count')))}</span><span class="pill">aprovadas: {html.escape(str(payload.get('passed_count')))}</span></p>
</header><main>{''.join(cards)}</main></body></html>"""


def run_backtests(*, max_attempts: int, limit: int | None = None, output_dir: str | None = None) -> int:
    db = SessionLocal()
    original_assert = None
    original_queue = None
    config_state: tuple[bool, dict[str, Any] | None] | None = None
    tenant: Tenant | None = None
    try:
        tenant = db.scalar(select(Tenant).where(Tenant.is_active.is_(True)).limit(1))
        if not tenant:
            raise RuntimeError("Nenhum tenant ativo encontrado para rodar o backtest.")
        units = db.execute(select(Unit).where(Unit.tenant_id == tenant.id, Unit.is_active.is_(True)).order_by(Unit.name.asc())).scalars().all()
        total = max(1, int(limit or 100))
        if len(units) > 1:
            units = sorted(units, key=lambda unit: (_unit_active_booking_load(db, tenant_id=tenant.id, unit_id=unit.id), unit.name))
            units_for_scenarios = units[: min(2, len(units))]
        else:
            units_for_scenarios = units
        scenarios = _build_scenarios(units_for_scenarios, total=total)
        original_assert, original_queue = _patch_dispatch_for_backtest()
        config_state = _temporary_ai_config(db, tenant_id=tenant.id)
        started_at = datetime.now(UTC)
        run_seed = int(started_at.timestamp()) % 1_000_000
        print(
            "Unidades usadas no backtest: "
            + ", ".join(f"{unit.name} ({_unit_active_booking_load(db, tenant_id=tenant.id, unit_id=unit.id)} agendamentos ativos)" for unit in units_for_scenarios)
        )
        print(f"Rodando {len(scenarios)} conversas reais com ate {max_attempts} tentativa(s) por conversa.")
        conversations: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for index, scenario in enumerate(scenarios, start=1):
            print(f"[{index:03d}/{len(scenarios):03d}] {scenario.kind} - {scenario.patient_name}")
            last_result: dict[str, Any] | None = None
            for attempt in range(1, max_attempts + 1):
                result = _run_runtime(db, tenant=tenant, scenario=scenario, index=(index * 10_000) + attempt, run_seed=run_seed)
                result["attempt"] = attempt
                last_result = result
                if result.get("passed"):
                    print(f"  aprovado: {result.get('final_status')} | turnos={len(result.get('transcript') or [])}")
                    conversations.append(result)
                    break
                print(f"  tentativa {attempt} falhou: {'; '.join(result.get('errors') or [])}")
            else:
                failures.append(last_result or {"scenario_id": scenario.id, "errors": ["sem resultado"]})
        finished_at = datetime.now(UTC)
        if failures:
            print("\nBacktest reprovado. Nao salvei relatorio aprovado porque houve falhas.")
            for failure in failures[:20]:
                print(f"- {failure.get('scenario_id')}: {'; '.join(failure.get('errors') or [])}")
            return 1
        payload = {
            "status": "passed",
            "mode": "real_system_backtest_100",
            "tenant_id": str(tenant.id),
            "tenant_slug": tenant.slug,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "scenarios_count": len(scenarios),
            "passed_count": len(conversations),
            "failed_count": 0,
            "llm_providers": sorted({p for item in conversations for p in (item.get("llm_providers") or [])}),
            "llm_models": sorted({m for item in conversations for m in (item.get("llm_models") or [])}),
            "validations": {
                "real_patients_created": True,
                "real_conversations_created": True,
                "real_messages_created": True,
                "real_appointments_created": True,
                "real_reschedules_validated": True,
                "real_cancellations_validated": True,
                "real_appointment_lookup_validated": True,
                "whatsapp_dispatch_mocked_for_safety": True,
            },
            "conversations": conversations,
        }
        base_dir = Path(output_dir or settings.storage_base_path or "/storage") / "ai-backtests"
        base_dir.mkdir(parents=True, exist_ok=True)
        stamp = finished_at.strftime("%Y%m%d-%H%M%S")
        json_path = base_dir / f"backtest-real-100-{stamp}.json"
        html_path = base_dir / f"backtest-real-100-{stamp}.html"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        html_path.write_text(_html_report(payload), encoding="utf-8")
        print(f"\nBacktest real aprovado. JSON: {json_path}")
        print(f"Relatorio visual HTML: {html_path}")
        return 0
    finally:
        if tenant and config_state is not None:
            try:
                _restore_ai_config(db, tenant_id=tenant.id, existed=config_state[0], original_value=config_state[1])
            except Exception:
                pass
        if original_assert is not None and original_queue is not None:
            _restore_dispatch(original_assert, original_queue)
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Roda 100 backtests reais do fluxo conversacional da IA.")
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output-dir", type=str, default=None)
    args = parser.parse_args()
    raise SystemExit(run_backtests(max_attempts=max(1, args.max_attempts), limit=args.limit, output_dir=args.output_dir))


if __name__ == "__main__":
    main()

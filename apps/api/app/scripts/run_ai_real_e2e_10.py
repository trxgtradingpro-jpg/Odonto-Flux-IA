from __future__ import annotations

import argparse
import json
import re
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import app.scripts.run_ai_backtests as backtests
import app.services.ai_autoresponder_service as autoresponder_module
import app.services.ai_structured_flow as structured_module
from app.core.config import settings
from app.db.session import SessionLocal
from app.models import (
    AIAutoresponderDecision,
    Appointment,
    AppointmentEvent,
    Conversation,
    Lead,
    LLMInteraction,
    Message,
    MessageEvent,
    OutboxMessage,
    Patient,
    PatientContact,
    Tenant,
    Unit,
)
from app.models.enums import ConversationStatus
from app.services.llm_service import run_llm_task

RUN_TAG = "ai_real_e2e_10"
REPORT_MODE = "real_system_e2e_10_complete_conversations"
BOOKING_KINDS = [
    "book",
    "book_lookup",
    "book_reschedule",
    "book_pause",
    "book",
    "book_lookup",
    "book_reschedule",
    "book",
    "book_pause",
    "book_lookup",
]
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
HANDOFF_REQUEST_PATTERNS = [
    r"\batendimento humano\b",
    r"\bfalar com (?:um |uma )?(?:humano|atendente|pessoa|equipe)\b",
    r"\bquero (?:um |uma )?(?:humano|atendente|pessoa)\b",
    r"\bcom (?:um |uma )?(?:humano|atendente|pessoa)\b",
    r"\bme chama no humano\b",
]
FIRST_NAMES = [
    "Mariana",
    "Bruno",
    "Camila",
    "Diego",
    "Renata",
    "Thiago",
    "Larissa",
    "Felipe",
    "Patricia",
    "Eduardo",
    "Juliana",
    "Anderson",
    "Viviane",
    "Marcelo",
    "Aline",
    "Rodrigo",
    "Natasha",
    "Leonardo",
    "Priscila",
    "Henrique",
]
MIDDLE_NAMES = [
    "Cristina",
    "Augusto",
    "Helena",
    "Roberto",
    "Fernanda",
    "Vinicius",
    "Gabriela",
    "Caio",
    "Leticia",
    "Samuel",
]
LAST_NAMES = [
    "Moura",
    "Teixeira",
    "Barbosa",
    "Ribeiro",
    "Cardoso",
    "Nogueira",
    "Ferreira",
    "Campos",
    "Azevedo",
    "Moreira",
    "Farias",
    "Monteiro",
]


def _json_from_output(value: Any) -> dict[str, Any]:
    text = str(value or "").strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(text[start : end + 1])
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
    return {}


def _has_handoff_request(text: str) -> bool:
    normalized = backtests._normalize(text)
    return any(re.search(pattern, normalized) for pattern in HANDOFF_REQUEST_PATTERNS)


def _remove_handoff_request(text: str) -> str:
    cleaned = str(text or "")
    sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", cleaned) if item.strip()]
    safe_sentences = [item for item in sentences if not _has_handoff_request(item)]
    if safe_sentences:
        return " ".join(safe_sentences).strip()
    for pattern in HANDOFF_REQUEST_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(pode ser|direto|por favor)\?\s*$", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s+([?.!,])", r"\1", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = cleaned.strip(" -")
    return cleaned or text


def _unique_patient_name(*, run_seed: int, index: int) -> str:
    first = FIRST_NAMES[(run_seed + index * 3) % len(FIRST_NAMES)]
    middle = MIDDLE_NAMES[(run_seed // 7 + index * 5) % len(MIDDLE_NAMES)]
    last = LAST_NAMES[(run_seed // 13 + index * 7) % len(LAST_NAMES)]
    return f"{first} {middle} {last}"


def _unique_birth_date(*, run_seed: int, index: int) -> str:
    day = ((run_seed + index * 2) % 27) + 1
    month = ((run_seed // 11 + index) % 12) + 1
    year = 1978 + ((run_seed // 17 + index * 3) % 24)
    return f"{day:02d}/{month:02d}/{year:04d}"


def _unique_cpf(*, run_seed: int, index: int) -> str:
    base = (run_seed * 104_729 + index * 7_919 + 80_000_000) % 1_000_000_000
    digits = f"{base:09d}"
    suffix = (run_seed + index * 17) % 100
    return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{suffix:02d}"


def _patient_simulator_message(
    db: Session,
    *,
    tenant_id: UUID,
    conversation_id: UUID | None,
    scenario_id: str,
    persona: str,
    target_message: str,
    last_clinic_reply: str | None = None,
    must_keep: str | None = None,
) -> str:
    prompt = (
        "Voce e um paciente virtual brasileiro em um teste controlado do ClinicFlux AI.\n"
        "Reescreva a mensagem alvo como uma mensagem natural de WhatsApp, curta, humana e diferente das anteriores.\n"
        "Preserve a intencao operacional e todos os dados importantes. Nao invente CPF, datas, horarios, unidade ou procedimento.\n"
        "Nao peca atendimento humano, atendente, ligacao ou equipe se a MENSAGEM_ALVO nao pedir isso.\n"
        "Se houver TRECHO_OBRIGATORIO, inclua esse trecho exatamente como esta.\n"
        "Retorne somente JSON: {\"message\":\"...\"}.\n\n"
        f"CENARIO: {scenario_id}\n"
        f"PERSONA: {persona}\n"
        f"ULTIMA_RESPOSTA_CLINICA: {last_clinic_reply or ''}\n"
        f"TRECHO_OBRIGATORIO: {must_keep or ''}\n"
        f"MENSAGEM_ALVO: {target_message}\n"
    )
    result = run_llm_task(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        task="ai_real_e2e_patient_simulator",
        prompt=prompt,
    )
    payload = _json_from_output(result.get("output"))
    message = " ".join(str(payload.get("message") or "").split())
    if not message:
        raise RuntimeError("paciente virtual IA nao retornou message")
    if not _has_handoff_request(target_message) and _has_handoff_request(message):
        message = _remove_handoff_request(message)
    if must_keep and must_keep not in message:
        message = f"{message} {must_keep}".strip()
    return message[:900]


def _cleanup_batch(db: Session, *, tenant_id: UUID) -> dict[str, int]:
    conversations = db.scalars(
        select(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.external_thread_id.like(f"{RUN_TAG}:%"),
        )
    ).all()
    conversation_ids = [item.id for item in conversations]
    patient_ids = {
        item.patient_id
        for item in conversations
        if item.patient_id is not None
    }
    patient_ids.update(
        db.scalars(select(Patient.id).where(Patient.tenant_id == tenant_id, Patient.origin == RUN_TAG)).all()
    )
    lead_ids = db.scalars(
        select(Lead.id).where(
            Lead.tenant_id == tenant_id,
            Lead.origin == RUN_TAG,
        )
    ).all()
    appointment_ids = []
    if patient_ids:
        appointment_ids = db.scalars(
            select(Appointment.id).where(
                Appointment.tenant_id == tenant_id,
                Appointment.patient_id.in_(patient_ids),
            )
        ).all()
    message_ids = []
    if conversation_ids:
        message_ids = db.scalars(select(Message.id).where(Message.conversation_id.in_(conversation_ids))).all()

    removed: dict[str, int] = {}
    if appointment_ids:
        removed["appointment_events"] = db.execute(
            delete(AppointmentEvent).where(AppointmentEvent.appointment_id.in_(appointment_ids))
        ).rowcount or 0
        removed["appointments"] = db.execute(
            delete(Appointment).where(Appointment.id.in_(appointment_ids))
        ).rowcount or 0
    if conversation_ids:
        removed["ai_decisions"] = db.execute(
            delete(AIAutoresponderDecision).where(AIAutoresponderDecision.conversation_id.in_(conversation_ids))
        ).rowcount or 0
        removed["llm_interactions"] = db.execute(
            delete(LLMInteraction).where(LLMInteraction.conversation_id.in_(conversation_ids))
        ).rowcount or 0
    if message_ids:
        removed["message_events"] = db.execute(
            delete(MessageEvent).where(MessageEvent.message_id.in_(message_ids))
        ).rowcount or 0
        removed["messages"] = db.execute(delete(Message).where(Message.id.in_(message_ids))).rowcount or 0
    if conversation_ids:
        outbox_rows = db.scalars(select(OutboxMessage).where(OutboxMessage.tenant_id == tenant_id)).all()
        removed_outbox = 0
        conversation_id_texts = {str(item) for item in conversation_ids}
        for row in outbox_rows:
            payload = row.payload if isinstance(row.payload, dict) else {}
            metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
            if str(payload.get("conversation_id") or metadata.get("conversation_id") or "") in conversation_id_texts:
                db.delete(row)
                removed_outbox += 1
        removed["outbox_messages"] = removed_outbox
    if conversation_ids:
        removed["conversations"] = db.execute(
            delete(Conversation).where(Conversation.id.in_(conversation_ids))
        ).rowcount or 0
    if lead_ids:
        removed["leads"] = db.execute(delete(Lead).where(Lead.id.in_(lead_ids))).rowcount or 0
    if patient_ids:
        removed["patient_contacts"] = db.execute(
            delete(PatientContact).where(PatientContact.patient_id.in_(patient_ids))
        ).rowcount or 0
        removed["patients"] = db.execute(delete(Patient).where(Patient.id.in_(patient_ids))).rowcount or 0
    db.commit()
    return removed


def _create_runtime(
    db: Session,
    *,
    tenant: Tenant,
    scenario: backtests.RealScenario,
    index: int,
    run_seed: int,
) -> backtests.ConversationRuntime:
    digits = f"55118{run_seed:06d}{index:07d}"[-13:]
    patient = Patient(
        tenant_id=tenant.id,
        full_name=f"Paciente E2E {index:03d}",
        phone=f"+{digits}",
        normalized_phone=digits,
        origin=RUN_TAG,
        tags_cache=[RUN_TAG, scenario.kind],
        lgpd_consent=True,
        marketing_opt_in=False,
    )
    db.add(patient)
    db.flush()
    lead = Lead(
        tenant_id=tenant.id,
        patient_id=patient.id,
        name=f"Lead E2E {index:03d}",
        phone=patient.phone,
        origin=RUN_TAG,
        interest=scenario.preferred_service,
    )
    db.add(lead)
    db.flush()
    conversation = Conversation(
        tenant_id=tenant.id,
        patient_id=patient.id,
        lead_id=lead.id,
        channel="whatsapp",
        external_thread_id=f"{RUN_TAG}:{run_seed}:{index}",
        status=ConversationStatus.OPEN.value,
        ai_autoresponder_enabled=True,
        tags=[RUN_TAG, scenario.kind],
    )
    db.add(conversation)
    db.flush()
    db.commit()
    return backtests.ConversationRuntime(scenario=scenario, patient=patient, conversation=conversation)


def _build_complete_booking_scenarios(
    db: Session,
    *,
    tenant: Tenant,
    units: list[Unit],
    total: int,
    run_seed: int,
) -> list[backtests.RealScenario]:
    base_scenarios = backtests._build_scenarios(units, total=total)
    scenarios: list[backtests.RealScenario] = []
    for index, scenario in enumerate(base_scenarios[:total]):
        kind = BOOKING_KINDS[index % len(BOOKING_KINDS)]
        patient_name = _unique_patient_name(run_seed=run_seed, index=index + 1)
        target = (
            f"Oi, quero agendar uma consulta nova de {scenario.preferred_service.lower()}"
            + (f" na {scenario.preferred_unit}" if scenario.preferred_unit else "")
            + ". Ainda nao tenho agendamento e quero iniciar agora."
        )
        generated = _patient_simulator_message(
            db,
            tenant_id=tenant.id,
            conversation_id=None,
            scenario_id=f"scenario_initial_{index + 1}",
            persona=scenario.persona,
            target_message=target,
            must_keep="agendar uma consulta nova",
        )
        scenarios.append(
            replace(
                scenario,
                id=f"e2e_{index + 1:02d}_{kind}",
                kind=kind,
                patient_name=patient_name,
                initial_messages=[generated],
                include_pause=kind == "book_pause",
                choose_by_text=False,
                registration_birth_date=_unique_birth_date(run_seed=run_seed, index=index + 1),
                registration_cpf=_unique_cpf(run_seed=run_seed, index=index + 1),
                max_turns=20,
            )
        )
    return scenarios


def _latest_ai_body(db: Session, conversation_id: UUID) -> str | None:
    message = backtests._latest_outbound_message(db, conversation_id)
    return message.body if message else None


def _local_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(LOCAL_TZ)


def _choose_reschedule_option(
    runtime: backtests.ConversationRuntime,
    *,
    mode: str,
    scheduling: dict[str, Any],
    interactive: dict[str, Any] | None,
    original_local: datetime,
) -> dict[str, str] | None:
    options = backtests._interactive_options(interactive)
    if not options:
        return None
    if mode == "booking_reschedule_day_select":
        original_iso_date = original_local.date().isoformat()
        original_br_date = original_local.strftime("%d/%m")
        day_options = [option for option in options if option["id"].startswith("day_")] or options
        for option in day_options:
            blob = f"{option['id']} {option['title']} {option.get('description') or ''}"
            if original_iso_date not in blob and original_br_date not in blob:
                return option
        return day_options[0]
    if mode == "booking_reschedule_time_select":
        selected_day = str(runtime.operations.get("reschedule_selected_day") or "")
        time_options = [option for option in options if option["id"].startswith("time_")] or options
        if selected_day and selected_day != original_local.date().isoformat():
            return time_options[0]
        original_time = original_local.strftime("%H:%M")
        for option in time_options:
            blob = f"{option['id']} {option['title']} {option.get('description') or ''}"
            if original_time not in blob:
                return option
        return time_options[1] if len(time_options) > 1 else time_options[0]
    return backtests._choose_option(
        scenario=runtime.scenario,
        mode=mode,
        scheduling=scheduling,
        interactive=interactive,
    )


def _drive_reschedule_with_new_slot(db: Session, runtime: backtests.ConversationRuntime) -> None:
    before = backtests._appointments_for_patient(db, runtime)
    if not before:
        runtime.errors.append("remarcacao sem agendamento criado")
        return
    appointment = before[-1]
    appointment_id = appointment.id
    original_start = appointment.starts_at.isoformat() if appointment.starts_at else None
    original_local = _local_datetime(appointment.starts_at) if appointment.starts_at else None
    backtests._send_patient_message(db, runtime, "Quero remarcar minha consulta para outro dia, pode me ajudar?")
    for _ in range(10):
        mode = backtests._latest_mode(db, runtime.conversation.id)
        if mode == "booking_rescheduled":
            break
        interactive, scheduling = backtests._latest_interactive(db, runtime.conversation.id)
        option = _choose_reschedule_option(
            runtime,
            mode=mode,
            scheduling=scheduling,
            interactive=interactive,
            original_local=original_local or datetime.now(LOCAL_TZ),
        )
        if not option:
            runtime.errors.append(f"remarcacao travou no modo {mode or 'vazio'}")
            return
        if mode == "booking_reschedule_day_select":
            runtime.operations["reschedule_selected_day"] = option["id"].removeprefix("day_")
        body, interactive_reply = backtests._choice_message(scenario=runtime.scenario, mode=mode, option=option)
        backtests._send_patient_message(db, runtime, body, interactive_reply=interactive_reply)
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


def _patch_patient_messages() -> tuple[Any, Any, Any]:
    original_create_runtime = backtests._create_runtime
    original_send = backtests._send_patient_message
    original_drive_reschedule = backtests._drive_reschedule

    def create_runtime_wrapper(db: Session, *, tenant: Tenant, scenario: backtests.RealScenario, index: int, run_seed: int):
        return _create_runtime(db, tenant=tenant, scenario=scenario, index=index, run_seed=run_seed)

    def send_patient_message_wrapper(
        db: Session,
        runtime: backtests.ConversationRuntime,
        body: str,
        *,
        interactive_reply: dict[str, str] | None = None,
        created_at: datetime | None = None,
    ):
        must_keep = None
        if interactive_reply:
            must_keep = str(interactive_reply.get("title") or interactive_reply.get("id") or "").strip() or None
        elif "Quais sao meus agendamentos" in body:
            must_keep = "Quais sao meus agendamentos"
        elif "Quero remarcar minha consulta" in body:
            must_keep = "Quero remarcar minha consulta"
        elif "Voltei, podemos continuar" in body:
            must_keep = "Voltei, podemos continuar"
        elif "Meu nome completo e" in body:
            must_keep = f"Meu nome completo e {runtime.scenario.patient_name}"
        elif "(" in body and ")" in body:
            must_keep = body[body.find("(") : body.rfind(")") + 1]
        generated = _patient_simulator_message(
            db,
            tenant_id=runtime.conversation.tenant_id,
            conversation_id=runtime.conversation.id,
            scenario_id=runtime.scenario.id,
            persona=runtime.scenario.persona,
            target_message=body,
            last_clinic_reply=_latest_ai_body(db, runtime.conversation.id),
            must_keep=must_keep,
        )
        runtime.operations.setdefault("ai_patient_simulator", []).append(
            {"target": body, "generated": generated, "must_keep": must_keep}
        )
        return original_send(db, runtime, generated, interactive_reply=interactive_reply, created_at=created_at)

    backtests._create_runtime = create_runtime_wrapper
    backtests._send_patient_message = send_patient_message_wrapper
    backtests._drive_reschedule = _drive_reschedule_with_new_slot
    return original_create_runtime, original_send, original_drive_reschedule


def _restore_patient_messages(original_create_runtime: Any, original_send: Any, original_drive_reschedule: Any) -> None:
    backtests._create_runtime = original_create_runtime
    backtests._send_patient_message = original_send
    backtests._drive_reschedule = original_drive_reschedule


def _patch_all_dispatch() -> tuple[Any, Any, Any, Any]:
    original_auto_assert = autoresponder_module.assert_whatsapp_account_ready_for_dispatch
    original_auto_queue = autoresponder_module.queue_outbound_message
    original_structured_assert = structured_module.assert_whatsapp_account_ready_for_dispatch
    original_structured_queue = structured_module.queue_outbound_message

    def fake_assert(db: Session, *, tenant_id: UUID):
        return SimpleNamespace(id=uuid4(), tenant_id=tenant_id, provider_name="e2e_backtest")

    def fake_queue(*args: Any, **kwargs: Any):
        return SimpleNamespace(id=uuid4())

    autoresponder_module.assert_whatsapp_account_ready_for_dispatch = fake_assert
    autoresponder_module.queue_outbound_message = fake_queue
    structured_module.assert_whatsapp_account_ready_for_dispatch = fake_assert
    structured_module.queue_outbound_message = fake_queue
    return original_auto_assert, original_auto_queue, original_structured_assert, original_structured_queue


def _restore_all_dispatch(originals: tuple[Any, Any, Any, Any]) -> None:
    (
        original_auto_assert,
        original_auto_queue,
        original_structured_assert,
        original_structured_queue,
    ) = originals
    autoresponder_module.assert_whatsapp_account_ready_for_dispatch = original_auto_assert
    autoresponder_module.queue_outbound_message = original_auto_queue
    structured_module.assert_whatsapp_account_ready_for_dispatch = original_structured_assert
    structured_module.queue_outbound_message = original_structured_queue


def _validate_complete_result(db: Session, result: dict[str, Any]) -> list[str]:
    errors = list(result.get("errors") or [])
    if not result.get("passed"):
        errors.append("runtime marcou conversa como reprovada")
    if result.get("final_status") not in {"booked_registered", "rescheduled"}:
        errors.append(f"final_status inesperado: {result.get('final_status')}")
    patient_saved = result.get("patient_saved") if isinstance(result.get("patient_saved"), dict) else {}
    if not patient_saved.get("full_name") or str(patient_saved.get("full_name")).startswith("Paciente E2E"):
        errors.append("nome do paciente nao foi salvo corretamente")
    if not patient_saved.get("birth_date"):
        errors.append("data de nascimento nao foi salva")
    if not patient_saved.get("cpf_saved"):
        errors.append("CPF nao foi salvo")
    appointments = result.get("appointments") if isinstance(result.get("appointments"), list) else []
    if not appointments:
        errors.append("nenhum agendamento ficou salvo")
    for appointment in appointments:
        status = str(appointment.get("status") or "")
        if status not in {"agendada", "reagendada"}:
            errors.append(f"agendamento com status nao visivel/ativo: {status}")
        if not appointment.get("starts_at") or not appointment.get("ends_at"):
            errors.append("agendamento sem horario completo")
        if appointment.get("origin") not in {"ai_autoresponder", "ai_structured"}:
            errors.append(f"origem inesperada do agendamento: {appointment.get('origin')}")
    if int(result.get("decisions_count") or 0) <= 0:
        errors.append("nenhuma decisao da IA foi salva")
    transcript = result.get("transcript") if isinstance(result.get("transcript"), list) else []
    if not any(item.get("role") == "ia" for item in transcript):
        errors.append("conversa sem resposta da IA")
    if not any(item.get("role") == "paciente" for item in transcript):
        errors.append("conversa sem mensagem do paciente")
    operations = result.get("operations") if isinstance(result.get("operations"), dict) else {}
    if not operations.get("ai_patient_simulator"):
        errors.append("mensagens do paciente nao foram geradas pelo simulador IA")
    conversation_id = result.get("conversation_id")
    if conversation_id and not db.get(Conversation, UUID(str(conversation_id))):
        errors.append("conversa nao existe mais no banco")
    for appointment in appointments:
        appointment_id = appointment.get("id")
        if appointment_id and not db.get(Appointment, UUID(str(appointment_id))):
            errors.append(f"agendamento {appointment_id} nao existe no banco")
    return errors


def _ai_audit_conversation(db: Session, *, tenant_id: UUID, result: dict[str, Any]) -> dict[str, Any]:
    transcript = result.get("transcript") if isinstance(result.get("transcript"), list) else []
    transcript_lines: list[str] = []
    for item in transcript[-40:]:
        role = str(item.get("role") or "")
        mode = str(item.get("mode") or "")
        body = " ".join(str(item.get("body") or "").split())
        reply = item.get("interactive_reply")
        reply_text = f" | escolha={reply}" if reply else ""
        transcript_lines.append(f"{role} | mode={mode} | {body}{reply_text}")

    appointments = result.get("appointments") if isinstance(result.get("appointments"), list) else []
    appointments_for_audit: list[dict[str, Any]] = []
    for appointment in appointments:
        item = dict(appointment)
        for field in ("starts_at", "ends_at"):
            raw_value = item.get(field)
            local_key = f"{field}_local_sao_paulo"
            try:
                parsed = datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
                item[local_key] = _local_datetime(parsed).isoformat()
                item[f"{field}_local_label"] = _local_datetime(parsed).strftime("%d/%m/%Y %H:%M")
            except Exception:
                item[local_key] = None
                item[f"{field}_local_label"] = None
        appointments_for_audit.append(item)
    patient_saved = result.get("patient_saved") if isinstance(result.get("patient_saved"), dict) else {}
    deterministic_errors = result.get("validation_errors") if isinstance(result.get("validation_errors"), list) else []
    prompt = (
        "Voce e um auditor de qualidade E2E do ClinicFlux AI. Avalie se esta conversa pode liberar a proxima simulacao.\n"
        "Responda somente JSON valido com este formato:\n"
        "{\"passed\":true|false,\"errors\":[\"...\"],\"checks\":{\"flow\":\"ok|erro\",\"database\":\"ok|erro\",\"final_reply\":\"ok|erro\",\"appointment\":\"ok|erro\"},\"summary\":\"...\"}\n\n"
        "CRITERIOS OBRIGATORIOS:\n"
        "- O paciente virtual deve receber respostas coerentes e chegar a uma conclusao real.\n"
        "- O banco precisa ter paciente real salvo com nome, nascimento e CPF.\n"
        "- O banco precisa ter agendamento real salvo e visivel com horario completo.\n"
        "- O campo starts_at/ends_at do banco esta em UTC. Compare com a conversa usando starts_at_local_sao_paulo e starts_at_local_label.\n"
        "- Em remarcacao, o compromisso novo precisa ter datetime diferente do original. Se a data mudar e a hora permanecer igual, a remarcacao continua valida.\n"
        "- Se a IA oferecer horarios e depois negar o mesmo horario ainda disponivel, reprove.\n"
        "- Se houver erro deterministico informado abaixo, reprove.\n\n"
        f"CENARIO: {result.get('scenario_id')}\n"
        f"FINAL_STATUS: {result.get('final_status')}\n"
        f"ERROS_DETERMINISTICOS: {json.dumps(deterministic_errors, ensure_ascii=False)}\n"
        f"PACIENTE_SALVO: {json.dumps(patient_saved, ensure_ascii=False, default=str)}\n"
        f"AGENDAMENTOS_SALVOS_COM_HORARIO_LOCAL: {json.dumps(appointments_for_audit, ensure_ascii=False, default=str)}\n"
        f"OPERACOES: {json.dumps(result.get('operations') or {}, ensure_ascii=False, default=str)[:7000]}\n"
        "REGRA ESPECIFICA DE REMARCACAO: compare original_starts_at com new_starts_at dentro de OPERACOES. "
        "Se forem diferentes, a remarcacao e valida mesmo com a mesma hora em outro dia.\n"
        "TRANSCRICAO:\n"
        + "\n".join(transcript_lines)
    )
    llm_result = run_llm_task(
        db,
        tenant_id=tenant_id,
        conversation_id=UUID(str(result["conversation_id"])) if result.get("conversation_id") else None,
        task="ai_real_e2e_conversation_auditor",
        prompt=prompt,
    )
    payload = _json_from_output(llm_result.get("output"))
    payload["raw_output"] = str(llm_result.get("output") or "")[:2000]
    return payload


def _validate_ai_audit(audit: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not audit:
        return ["auditoria IA nao retornou JSON"]
    if audit.get("passed") is not True:
        audit_errors = audit.get("errors") if isinstance(audit.get("errors"), list) else []
        if audit_errors:
            errors.extend(f"auditoria IA: {item}" for item in audit_errors)
        else:
            errors.append("auditoria IA reprovou a conversa")
    checks = audit.get("checks") if isinstance(audit.get("checks"), dict) else {}
    for key in ("flow", "database", "final_reply", "appointment"):
        if str(checks.get(key) or "").lower() not in {"ok", "pass", "passed", "true"}:
            errors.append(f"auditoria IA marcou {key} como erro")
    return errors


def _write_report(payload: dict[str, Any], *, output_dir: str | None) -> Path:
    base_dir = Path(output_dir or settings.storage_base_path or "/storage") / "ai-real-e2e"
    base_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = base_dir / f"e2e-10-conversas-{stamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def run_e2e(*, total: int, max_restarts: int, output_dir: str | None = None) -> int:
    db = SessionLocal()
    dispatch_originals = None
    original_create_runtime = None
    original_send = None
    original_drive_reschedule = None
    config_state: tuple[bool, dict[str, Any] | None] | None = None
    try:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == "sorriso-sul", Tenant.is_active.is_(True)))
        if not tenant:
            tenant = db.scalar(select(Tenant).where(Tenant.is_active.is_(True)).limit(1))
        if not tenant:
            raise RuntimeError("Nenhum tenant ativo encontrado.")
        units = db.scalars(
            select(Unit).where(Unit.tenant_id == tenant.id, Unit.is_active.is_(True)).order_by(Unit.name.asc())
        ).all()
        if not units:
            raise RuntimeError("Nenhuma unidade ativa encontrada.")

        dispatch_originals = _patch_all_dispatch()
        config_state = backtests._temporary_ai_config(db, tenant_id=tenant.id)
        config = backtests.get_global_config(db, tenant_id=tenant.id)
        config["structured_flow_enabled"] = False
        backtests.set_global_config(db, tenant_id=tenant.id, payload=config)
        original_create_runtime, original_send, original_drive_reschedule = _patch_patient_messages()

        attempts = 1
        for restart_index in range(attempts):
            removed = _cleanup_batch(db, tenant_id=tenant.id)
            started_at = datetime.now(UTC)
            run_seed = int(started_at.timestamp() * 1000) % 1_000_000
            scenarios = _build_complete_booking_scenarios(
                db,
                tenant=tenant,
                units=units,
                total=total,
                run_seed=run_seed,
            )
            print(f"Reinicio {restart_index + 1}/{attempts}: limpeza={removed}")
            print(f"Run seed/pacientes novos: {run_seed}")
            print(f"Rodando {len(scenarios)} conversas completas no tenant {tenant.slug}.")
            conversations: list[dict[str, Any]] = []
            failure: dict[str, Any] | None = None
            for index, scenario in enumerate(scenarios, start=1):
                print(f"[{index:02d}/{len(scenarios):02d}] {scenario.id} - {scenario.patient_name}")
                result = backtests._run_runtime(db, tenant=tenant, scenario=scenario, index=index, run_seed=run_seed)
                result["validation_errors"] = _validate_complete_result(db, result)
                print("  validando fluxo, resposta e persistencia com auditoria IA...")
                result["ai_audit"] = _ai_audit_conversation(db, tenant_id=tenant.id, result=result)
                result["validation_errors"].extend(_validate_ai_audit(result["ai_audit"]))
                result["passed"] = bool(result.get("passed")) and not result["validation_errors"]
                if result["passed"]:
                    print(
                        f"  ok: {result.get('final_status')} | paciente={result.get('patient_saved', {}).get('full_name')} | "
                        f"agendamentos={len(result.get('appointments') or [])}"
                    )
                    conversations.append(result)
                    continue
                print(f"  falhou: {'; '.join(result.get('validation_errors') or result.get('errors') or [])}")
                failure = result
                break

            if failure:
                _cleanup_batch(db, tenant_id=tenant.id)
                payload = {
                    "status": "failed",
                    "mode": REPORT_MODE,
                    "tenant_id": str(tenant.id),
                    "tenant_slug": tenant.slug,
                    "failed_at": datetime.now(UTC).isoformat(),
                    "run_seed": run_seed,
                    "failure": failure,
                }
                report_path = _write_report(payload, output_dir=output_dir)
                print("Falha detectada. Conversas deste lote foram apagadas.")
                print("Corrija a causa e execute novamente; a proxima execucao comecara da conversa 1 com pacientes novos.")
                print(f"Relatorio: {report_path}")
                return 1

            payload = {
                "status": "passed",
                "mode": REPORT_MODE,
                "tenant_id": str(tenant.id),
                "tenant_slug": tenant.slug,
                "started_at": started_at.isoformat(),
                "finished_at": datetime.now(UTC).isoformat(),
                "run_seed": run_seed,
                "scenarios_count": len(scenarios),
                "passed_count": len(conversations),
                "failed_count": 0,
                "restart_count": restart_index,
                "validations": {
                    "real_patients_saved": True,
                    "real_conversations_saved": True,
                    "real_messages_saved": True,
                    "real_ai_decisions_saved": True,
                    "real_appointments_visible_in_agenda": True,
                    "patient_messages_generated_by_ai": True,
                    "ai_audited_each_conversation_before_next": True,
                    "whatsapp_dispatch_mocked_for_safety": True,
                    "cleanup_scope": RUN_TAG,
                },
                "conversations": conversations,
            }
            report_path = _write_report(payload, output_dir=output_dir)
            print(f"APROVADO: {len(conversations)}/{len(scenarios)} conversas completas.")
            print(f"Relatorio: {report_path}")
            for item in conversations:
                appointments = item.get("appointments") or []
                print(
                    f"- {item.get('scenario_id')} | conversa={item.get('conversation_id')} | "
                    f"paciente={item.get('patient_saved', {}).get('full_name')} | "
                    f"agendamentos={[appt.get('id') for appt in appointments]}"
                )
            return 0
        return 1
    finally:
        if original_create_runtime is not None and original_send is not None and original_drive_reschedule is not None:
            _restore_patient_messages(original_create_runtime, original_send, original_drive_reschedule)
        if dispatch_originals is not None:
            _restore_all_dispatch(dispatch_originals)
        if config_state is not None:
            backtests._restore_ai_config(db, tenant_id=tenant.id, existed=config_state[0], original_value=config_state[1])
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Roda 10 conversas E2E reais com persistencia operacional no banco.")
    parser.add_argument("--total", type=int, default=10)
    parser.add_argument("--max-restarts", type=int, default=1)
    parser.add_argument("--output-dir", type=str, default=None)
    args = parser.parse_args()
    return run_e2e(total=max(1, args.total), max_restarts=max(1, args.max_restarts), output_dir=args.output_dir)


if __name__ == "__main__":
    raise SystemExit(main())

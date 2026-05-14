from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.models import Appointment, Conversation, Lead, Message, MessageEvent, Patient, ProspectAccount, Unit, WhatsAppAccount
from app.models.enums import AppointmentStatus, MessageDirection, MessageStatus
from app.services.automation_service import emit_event

DEMO_SIMULATION_SOURCE = "demo_whatsapp_simulation"
DEMO_SIMULATION_COMPLETED_TAG = "demo_whatsapp_simulation_completed"


def _now() -> datetime:
    return datetime.now(UTC)


def is_demo_tenant(db: Session, *, tenant_id: UUID) -> bool:
    return bool(
        db.scalar(
            select(ProspectAccount.id)
            .where(ProspectAccount.demo_tenant_id == tenant_id)
            .limit(1)
        )
    )


def ensure_demo_virtual_whatsapp_account(db: Session, *, tenant_id: UUID) -> WhatsAppAccount:
    existing = db.scalar(
        select(WhatsAppAccount)
        .where(WhatsAppAccount.tenant_id == tenant_id)
        .order_by(WhatsAppAccount.created_at.desc())
        .limit(1)
    )
    if existing:
        return existing

    fallback_unit_id = db.scalar(
        select(Unit.id)
        .where(Unit.tenant_id == tenant_id, Unit.is_active.is_(True))
        .order_by(Unit.created_at.asc())
        .limit(1)
    )
    account = WhatsAppAccount(
        tenant_id=tenant_id,
        unit_id=fallback_unit_id,
        provider_name="meta_cloud",
        phone_number_id=f"demo_virtual_{str(tenant_id).replace('-', '')[:12]}",
        business_account_id=f"demo_virtual_{str(tenant_id).replace('-', '')[:12]}",
        display_phone="+55 11 90000-0000",
        access_token_encrypted="demo_virtual_token",
        verify_token="demo-virtual-verify-token",
        webhook_secret="demo-virtual-secret",
        is_active=True,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def maybe_schedule_demo_whatsapp_reply_simulation(
    db: Session,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    outbound_message_id: UUID,
    source: str | None,
) -> dict[str, object]:
    if not is_demo_tenant(db, tenant_id=tenant_id):
        return {"status": "ignored", "reason": "tenant_is_not_demo"}

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id,
        )
    )
    outbound_message = db.scalar(
        select(Message).where(
            Message.id == outbound_message_id,
            Message.tenant_id == tenant_id,
            Message.direction == MessageDirection.OUTBOUND.value,
        )
    )
    if not conversation or not outbound_message:
        return {"status": "ignored", "reason": "context_not_found"}
    if conversation.channel != "whatsapp":
        return {"status": "ignored", "reason": "channel_is_not_whatsapp"}
    if str(outbound_message.sender_type or "").strip().lower() not in {"user", "ai", "automation"}:
        return {"status": "ignored", "reason": "unsupported_sender"}

    payload = dict(outbound_message.payload or {})
    simulation_meta = payload.get("demo_simulation") if isinstance(payload.get("demo_simulation"), dict) else {}
    if simulation_meta.get("scheduled_at"):
        return {"status": "duplicate", "reason": "already_scheduled"}

    tags = set(conversation.tags or [])
    normalized_source = str(source or payload.get("source") or outbound_message.sender_type or "").strip().lower()
    if normalized_source in {"manual_outbound", "manual_inbox", "user"} and DEMO_SIMULATION_COMPLETED_TAG in tags:
        tags.discard(DEMO_SIMULATION_COMPLETED_TAG)
        conversation.tags = sorted(tags)
        db.add(conversation)
    elif outbound_message.sender_type == "ai" and DEMO_SIMULATION_COMPLETED_TAG in tags:
        return {"status": "ignored", "reason": "simulation_already_completed"}

    payload["demo_simulation"] = {
        "source": normalized_source or "demo",
        "scheduled_at": _now().isoformat(),
    }
    outbound_message.payload = payload
    db.add(outbound_message)
    db.commit()

    countdown = 4 if outbound_message.sender_type == "user" else 3
    try:
        from app.tasks.jobs import process_demo_whatsapp_reply_simulation_task

        process_demo_whatsapp_reply_simulation_task.apply_async(
            args=[str(tenant_id), str(conversation_id), str(outbound_message_id)],
            countdown=countdown,
        )
        return {"status": "scheduled", "countdown": countdown}
    except Exception as exc:
        logger.warning(
            "demo_whatsapp_simulation.schedule_failed_running_inline",
            tenant_id=str(tenant_id),
            conversation_id=str(conversation_id),
            outbound_message_id=str(outbound_message_id),
            error=str(exc),
        )
        return process_demo_whatsapp_reply_simulation(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            outbound_message_id=outbound_message_id,
        )


def process_demo_whatsapp_reply_simulation(
    db: Session,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    outbound_message_id: UUID,
) -> dict[str, object]:
    if not is_demo_tenant(db, tenant_id=tenant_id):
        return {"status": "ignored", "reason": "tenant_is_not_demo"}

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id,
        )
    )
    outbound_message = db.scalar(
        select(Message).where(
            Message.id == outbound_message_id,
            Message.tenant_id == tenant_id,
            Message.direction == MessageDirection.OUTBOUND.value,
        )
    )
    if not conversation or not outbound_message:
        return {"status": "ignored", "reason": "context_not_found"}
    if str(outbound_message.sender_type or "").strip().lower() not in {"user", "ai", "automation"}:
        return {"status": "ignored", "reason": "unsupported_sender"}

    outbound_payload = dict(outbound_message.payload or {})
    simulation_meta = outbound_payload.get("demo_simulation") if isinstance(outbound_payload.get("demo_simulation"), dict) else {}
    if simulation_meta.get("processed_at"):
        return {"status": "duplicate", "reason": "already_processed"}

    if _has_newer_manual_outbound(db, conversation_id=conversation_id, tenant_id=tenant_id, after=outbound_message.created_at):
        simulation_meta["processed_at"] = _now().isoformat()
        simulation_meta["status"] = "superseded"
        outbound_payload["demo_simulation"] = simulation_meta
        outbound_message.payload = outbound_payload
        db.add(outbound_message)
        db.commit()
        return {"status": "ignored", "reason": "superseded_by_newer_manual_message"}

    patient = db.get(Patient, conversation.patient_id) if conversation.patient_id else None
    lead = db.get(Lead, conversation.lead_id) if conversation.lead_id else None
    unit = db.get(Unit, conversation.unit_id) if conversation.unit_id else None
    appointment = _upcoming_appointment(db, tenant_id=tenant_id, conversation=conversation)

    _mark_outbound_message_as_read(outbound_message)
    reply = _build_demo_patient_reply(
        conversation=conversation,
        outbound_message=outbound_message,
        patient=patient,
        lead=lead,
        unit=unit,
        appointment=appointment,
    )
    if not reply:
        simulation_meta["processed_at"] = _now().isoformat()
        simulation_meta["status"] = "ignored"
        outbound_payload["demo_simulation"] = simulation_meta
        outbound_message.payload = outbound_payload
        db.add(outbound_message)
        db.commit()
        return {"status": "ignored", "reason": "no_reply_generated"}

    inbound_payload = {
        "source": DEMO_SIMULATION_SOURCE,
        "simulated_patient": True,
        "reply_to_message_id": str(outbound_message.id),
        "interactive_reply": reply["interactive_reply"],
        "demo_simulation": {
            "trigger_message_id": str(outbound_message.id),
            "created_at": _now().isoformat(),
            "type": reply["message_type"],
        },
    }
    inbound_message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        direction=MessageDirection.INBOUND.value,
        channel="whatsapp",
        sender_type="patient",
        body=reply["body"],
        message_type=reply["message_type"],
        payload=inbound_payload,
        status=MessageStatus.RECEIVED.value,
        sent_at=_now(),
    )
    db.add(inbound_message)
    db.flush()

    tags = set(conversation.tags or [])
    if reply["mark_completed"]:
        tags.add(DEMO_SIMULATION_COMPLETED_TAG)
    conversation.tags = sorted(tags)
    conversation.last_message_at = _now()
    db.add(conversation)

    simulation_meta["processed_at"] = _now().isoformat()
    simulation_meta["status"] = "replied"
    simulation_meta["reply_message_id"] = str(inbound_message.id)
    outbound_payload["demo_simulation"] = simulation_meta
    outbound_message.payload = outbound_payload
    db.add(outbound_message)
    db.add(
        MessageEvent(
            tenant_id=tenant_id,
            message_id=inbound_message.id,
            event_type="demo_patient_reply_simulated",
            payload={
                "trigger_message_id": str(outbound_message.id),
                "mark_completed": reply["mark_completed"],
                "interactive_reply": reply["interactive_reply"],
            },
        )
    )
    db.commit()

    emit_event(
        db,
        tenant_id=tenant_id,
        event_key="mensagem_recebida",
        payload={
            "conversation_id": str(conversation_id),
            "patient_id": str(conversation.patient_id) if conversation.patient_id else None,
            "lead_id": str(conversation.lead_id) if conversation.lead_id else None,
            "phone": patient.phone if patient else (lead.phone if lead else None),
            "message": reply["body"],
        },
    )

    interactive_reply = reply["interactive_reply"] if isinstance(reply["interactive_reply"], dict) else None
    try:
        from app.tasks.jobs import process_ai_autoresponder_inbound_task

        process_ai_autoresponder_inbound_task.apply_async(
            args=[str(tenant_id), str(conversation_id), str(inbound_message.id)],
            countdown=0 if interactive_reply else 2,
        )
    except Exception as exc:
        logger.warning(
            "demo_whatsapp_simulation.ai_schedule_failed_running_inline",
            tenant_id=str(tenant_id),
            conversation_id=str(conversation_id),
            inbound_message_id=str(inbound_message.id),
            error=str(exc),
        )
        from app.services.ai_autoresponder_service import process_inbound_message

        process_inbound_message(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            inbound_message_id=inbound_message.id,
        )

    return {
        "status": "completed",
        "reply_message_id": str(inbound_message.id),
        "mark_completed": reply["mark_completed"],
    }


def _has_newer_manual_outbound(
    db: Session,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    after: datetime,
) -> bool:
    newer = db.scalar(
        select(Message.id)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation_id,
            Message.direction == MessageDirection.OUTBOUND.value,
            Message.sender_type == "user",
            Message.created_at > after,
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    return newer is not None


def _upcoming_appointment(db: Session, *, tenant_id: UUID, conversation: Conversation) -> Appointment | None:
    if not conversation.patient_id:
        return None
    return db.scalar(
        select(Appointment)
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.patient_id == conversation.patient_id,
            Appointment.status.in_(
                [
                    AppointmentStatus.SCHEDULED.value,
                    AppointmentStatus.CONFIRMED.value,
                    AppointmentStatus.RESCHEDULED.value,
                ]
            ),
        )
        .order_by(Appointment.starts_at.asc())
        .limit(1)
    )


def _mark_outbound_message_as_read(message: Message) -> None:
    now = _now()
    message.status = MessageStatus.READ.value
    if not message.sent_at:
        message.sent_at = now - timedelta(seconds=6)
    if not message.delivered_at:
        message.delivered_at = now - timedelta(seconds=4)
    if not message.read_at:
        message.read_at = now - timedelta(seconds=2)


def _build_demo_patient_reply(
    *,
    conversation: Conversation,
    outbound_message: Message,
    patient: Patient | None,
    lead: Lead | None,
    unit: Unit | None,
    appointment: Appointment | None,
) -> dict[str, object] | None:
    body = str(outbound_message.body or "").strip()
    normalized_body = _normalize_text(body)
    payload = outbound_message.payload if isinstance(outbound_message.payload, dict) else {}
    interactive = payload.get("interactive") if isinstance(payload.get("interactive"), dict) else {}
    scheduling = payload.get("scheduling") if isinstance(payload.get("scheduling"), dict) else {}
    mode = str(payload.get("mode") or scheduling.get("mode") or "").strip().lower()
    service_name = str(
        lead.interest if lead and lead.interest else appointment.procedure_type if appointment and appointment.procedure_type else "avaliação odontológica"
    ).strip()
    unit_name = str(unit.name if unit and unit.name else "unidade principal").strip()
    patient_name = str(patient.full_name if patient and patient.full_name else "Paciente Demo").strip()

    if _is_post_booking_message(normalized_body=normalized_body, mode=mode, scheduling=scheduling):
        return {
            "body": "Perfeito, ficou ótimo para mim. Muito obrigado pelo atendimento!",
            "message_type": "text",
            "interactive_reply": None,
            "mark_completed": True,
        }

    if any(
        pattern in normalized_body
        for pattern in (
            "encaminhar a conversa",
            "nossa equipe continuar",
            "atendimento humano",
            "falar com nossa equipe",
        )
    ):
        return None

    if interactive:
        selected_option = _choose_interactive_option(
            interactive=interactive,
            normalized_body=normalized_body,
            preferred_service=service_name,
            preferred_unit=unit_name,
        )
        if selected_option:
            return {
                "body": selected_option["title"],
                "message_type": "interactive_button_reply" if selected_option["kind"] == "button" else "interactive_list_reply",
                "interactive_reply": {
                    "kind": selected_option["kind"],
                    "id": selected_option["id"],
                    "title": selected_option["title"],
                    "description": selected_option.get("description") or "",
                },
                "mark_completed": False,
            }

    numbered_option = _choose_numbered_option(
        body=body,
        normalized_body=normalized_body,
        preferred_service=service_name,
        preferred_unit=unit_name,
    )
    if numbered_option:
        return {
            "body": numbered_option,
            "message_type": "text",
            "interactive_reply": None,
            "mark_completed": False,
        }

    if any(term in normalized_body for term in ("cpf", "documento", "data de nascimento", "nascimento", "cadastro")):
        return {
            "body": f"Claro. Pode registrar meu nome completo como {patient_name}, CPF 529.982.247-25 e nascimento em 14/09/1992.",
            "message_type": "text",
            "interactive_reply": None,
            "mark_completed": False,
        }

    if any(term in normalized_body for term in ("unidade", "clinica", "clínica")):
        return {
            "body": f"Pode ser na {unit_name}.",
            "message_type": "text",
            "interactive_reply": None,
            "mark_completed": False,
        }

    if any(term in normalized_body for term in ("servico", "serviço", "procedimento")):
        return {
            "body": f"Quero seguir com {service_name}.",
            "message_type": "text",
            "interactive_reply": None,
            "mark_completed": False,
        }

    if any(term in normalized_body for term in ("dia", "data", "semana")):
        return {
            "body": "Quinta-feira para mim funciona melhor.",
            "message_type": "text",
            "interactive_reply": None,
            "mark_completed": False,
        }

    if any(term in normalized_body for term in ("horario", "horário", "hora", "periodo", "período")):
        return {
            "body": "Se tiver depois das 14h para mim fica ótimo.",
            "message_type": "text",
            "interactive_reply": None,
            "mark_completed": False,
        }

    if any(term in normalized_body for term in ("confirm", "pode marcar", "posso marcar", "fechar")):
        return {
            "body": "Pode confirmar sim.",
            "message_type": "text",
            "interactive_reply": None,
            "mark_completed": False,
        }

    return {
        "body": f"Quero sim agendar {service_name}. Se tiver na {unit_name} durante a tarde para mim funciona muito bem.",
        "message_type": "text",
        "interactive_reply": None,
        "mark_completed": False,
    }


def _is_post_booking_message(*, normalized_body: str, mode: str, scheduling: dict[str, object]) -> bool:
    if mode in {"appointment_created", "appointment_already_created", "post_booking_guidance"}:
        return True
    scheduling_reason = _normalize_text(scheduling.get("reason"))
    if scheduling_reason in {"post booking guidance", "appointment created", "appointment already created"}:
        return True
    return any(
        pattern in normalized_body
        for pattern in (
            "consulta foi confirmada",
            "consulta foi remarcada",
            "agendamento confirmado",
            "agendamento criado",
            "foi agendad",
            "foi remarcad",
            "muito obrigado, seu horario esta reservado",
        )
    )


def _choose_numbered_option(
    *,
    body: str,
    normalized_body: str,
    preferred_service: str,
    preferred_unit: str,
) -> str | None:
    options: list[str] = []
    for raw_line in body.splitlines():
        line = str(raw_line or "").strip()
        match = re.match(r"^\d+\)\s*(.+)$", line)
        if not match:
            continue
        title = re.split(r"\s+[—-]\s+", match.group(1).strip(), maxsplit=1)[0].strip()
        if title:
            options.append(title)
    if not options:
        return None

    normalized_service = _normalize_text(preferred_service)
    normalized_unit = _normalize_text(preferred_unit)
    asks_service = any(token in normalized_body for token in ("servico", "serviço", "procedimento"))
    asks_unit = any(token in normalized_body for token in ("unidade", "clinica", "clínica"))
    asks_date = any(token in normalized_body for token in ("dia", "data"))
    asks_time = any(token in normalized_body for token in ("horario", "horário", "hora"))
    asks_confirm = "confirm" in normalized_body
    scored: list[tuple[int, str]] = []
    for index, option in enumerate(options):
        normalized_option = _normalize_text(option)
        score = -index
        service_match = normalized_service and normalized_service in normalized_option
        unit_match = normalized_unit and normalized_unit in normalized_option
        if service_match:
            score += 30
        if unit_match:
            score += 28
        if any(token in normalized_option for token in ("14h", "15h", "16h", "17h", "tarde")):
            score += 18
        if any(token in normalized_option for token in ("confirm", "sim", "manter", "continuar")):
            score += 16
        if asks_service and service_match:
            score += 40
        if asks_unit and unit_match:
            score += 44
        if asks_date and re.search(r"\b\d{1,2}/\d{1,2}\b", normalized_option):
            score += 28
        if asks_time and any(token in normalized_option for token in ("14", "15", "16", "17", "tarde")):
            score += 32
        if asks_confirm and any(token in normalized_option for token in ("confirm", "sim", "manter", "continuar")):
            score += 36
        if any(token in normalized_option for token in ("humano", "encerrar", "cancelar", "reiniciar", "trocar")):
            score -= 30
        scored.append((score, option))

    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def _choose_interactive_option(
    *,
    interactive: dict[str, object],
    normalized_body: str,
    preferred_service: str,
    preferred_unit: str,
) -> dict[str, str] | None:
    kind = "button"
    raw_options = interactive.get("buttons")
    if not isinstance(raw_options, list):
        kind = "list"
        raw_options = interactive.get("rows")
    if not isinstance(raw_options, list):
        return None

    service_tokens = {token for token in _normalize_text(preferred_service).split() if len(token) > 2}
    unit_tokens = {token for token in _normalize_text(preferred_unit).split() if len(token) > 2}
    asks_service = any(token in normalized_body for token in ("servico", "serviço", "procedimento"))
    asks_unit = any(token in normalized_body for token in ("unidade", "clinica", "clínica"))
    asks_date = any(token in normalized_body for token in ("dia", "data"))
    asks_time = any(token in normalized_body for token in ("horario", "horário", "hora"))
    asks_confirm = "confirm" in normalized_body
    scored: list[tuple[int, dict[str, str]]] = []
    for index, raw_option in enumerate(raw_options):
        if not isinstance(raw_option, dict):
            continue
        option_id = str(raw_option.get("id") or "").strip()
        option_title = str(raw_option.get("title") or "").strip()
        option_description = str(raw_option.get("description") or "").strip()
        if not option_id or not option_title:
            continue

        normalized_option = _normalize_text(f"{option_title} {option_description} {option_id}")
        score = -index
        service_match = bool(service_tokens and any(token in normalized_option for token in service_tokens))
        unit_match = bool(unit_tokens and any(token in normalized_option for token in unit_tokens))
        confirm_match = any(token in normalized_option for token in ("confirm", "sim", "manter", "continuar", "agendar"))
        time_match = any(token in normalized_option for token in ("14h", "15h", "16h", "17h", "14:", "15:", "16:", "17:", "tarde"))
        date_match = bool(re.search(r"\b\d{1,2}/\d{1,2}\b", normalized_option)) or any(
            token in normalized_option for token in ("segunda", "terca", "terça", "quarta", "quinta", "sexta")
        )
        if confirm_match:
            score += 30
        if time_match:
            score += 24
        if date_match:
            score += 12
        if service_match:
            score += 28
        if unit_match:
            score += 26
        if asks_service and service_match:
            score += 44
        if asks_unit and unit_match:
            score += 50
        if asks_date and date_match:
            score += 40
        if asks_time and time_match:
            score += 42
        if asks_confirm and confirm_match:
            score += 38
        if any(token in normalized_option for token in ("humano", "encerrar", "cancelar", "reiniciar")):
            score -= 40
        scored.append(
            (
                score,
                {
                    "kind": kind,
                    "id": option_id,
                    "title": option_title,
                    "description": option_description,
                },
            )
        )

    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def _normalize_text(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text.lower()).strip()

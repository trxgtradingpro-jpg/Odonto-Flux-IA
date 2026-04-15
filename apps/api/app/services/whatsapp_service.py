from datetime import UTC, datetime, timedelta
from hashlib import sha1
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ApiError
from app.core.logging import logger
from app.integrations.whatsapp.cloud_api import WhatsAppCloudProvider
from app.integrations.whatsapp.infobip import InfobipWhatsAppProvider
from app.integrations.whatsapp.twilio import TwilioWhatsAppProvider
from app.models import (
    Conversation,
    Lead,
    Message,
    MessageEvent,
    OutboxMessage,
    Patient,
    PatientContact,
    WebhookInbox,
    WhatsAppAccount,
)
from app.models.enums import MessageDirection, MessageStatus, OutboxStatus
from app.services.automation_service import emit_event, pending_jobs_for_dispatch
from app.utils.phone import normalize_phone


SUPPORTED_WHATSAPP_PROVIDERS = {"meta_cloud", "infobip", "twilio"}
WEBHOOK_EVENT_ID_MAX_LENGTH = 120


def _safe_webhook_event_id(raw_event_id: str | None) -> str:
    value = str(raw_event_id or '').strip()
    if not value:
        return ''
    if len(value) <= WEBHOOK_EVENT_ID_MAX_LENGTH:
        return value

    digest = sha1(value.encode('utf-8')).hexdigest()[:12]
    reserved_suffix = len(digest) + 1  # include separator ':'
    prefix_size = WEBHOOK_EVENT_ID_MAX_LENGTH - reserved_suffix
    if prefix_size <= 0:
        return digest[:WEBHOOK_EVENT_ID_MAX_LENGTH]
    return f'{value[:prefix_size]}:{digest}'


def _extract_meta_inbound_body_and_interactive(message: dict) -> tuple[str, str, dict | None]:
    message_type = str(message.get('type') or 'text').lower().strip() or 'text'
    interactive = message.get('interactive') if isinstance(message.get('interactive'), dict) else {}
    list_reply = interactive.get('list_reply') if isinstance(interactive.get('list_reply'), dict) else {}
    button_reply = interactive.get('button_reply') if isinstance(interactive.get('button_reply'), dict) else {}

    if list_reply:
        option_id = str(list_reply.get('id') or '').strip()
        title = str(list_reply.get('title') or '').strip()
        description = str(list_reply.get('description') or '').strip()
        body = title or option_id or description
        return body, 'interactive_list_reply', {'kind': 'list', 'id': option_id, 'title': title, 'description': description}

    if button_reply:
        option_id = str(button_reply.get('id') or '').strip()
        title = str(button_reply.get('title') or '').strip()
        body = title or option_id
        return body, 'interactive_button_reply', {'kind': 'button', 'id': option_id, 'title': title}

    text_body = str((message.get('text') or {}).get('body') or '').strip()
    if text_body:
        return text_body, message_type, None

    button_text = str((message.get('button') or {}).get('text') or '').strip()
    if button_text:
        return button_text, message_type, None

    return '', message_type, None


def _extract_infobip_inbound_body_and_interactive(result: dict, message_block: dict) -> tuple[str, str, dict | None]:
    raw_type = str(result.get('type') or message_block.get('type') or 'text').strip()
    normalized_type = raw_type.lower() or 'text'

    interactive_type = str(message_block.get('type') or '').upper().strip()
    if interactive_type == 'INTERACTIVE_LIST_REPLY':
        option_id = str(message_block.get('id') or '').strip()
        title = str(message_block.get('title') or '').strip()
        description = str(message_block.get('description') or '').strip()
        body = title or option_id or description
        return body, 'interactive_list_reply', {'kind': 'list', 'id': option_id, 'title': title, 'description': description}

    if interactive_type == 'INTERACTIVE_BUTTON_REPLY':
        option_id = str(message_block.get('id') or '').strip()
        title = str(message_block.get('title') or '').strip()
        body = title or option_id
        return body, 'interactive_button_reply', {'kind': 'button', 'id': option_id, 'title': title}

    inbound_text = str(
        message_block.get('text')
        or message_block.get('body')
        or result.get('text')
        or ''
    ).strip()
    return inbound_text, normalized_type, None


def verify_webhook_challenge(mode: str | None, token: str | None, challenge: str | None) -> str:
    if mode == 'subscribe' and token and token == settings.whatsapp_verify_token:
        if challenge:
            return challenge
    raise ApiError(status_code=403, code='WHATSAPP_VERIFY_FAILED', message='Webhook nao verificado')


def normalize_whatsapp_provider_name(provider_name: str | None) -> str:
    value = (provider_name or "meta_cloud").strip().lower()
    if value in {"meta", "meta_cloud_api", "cloud_api"}:
        return "meta_cloud"
    if value in {"infobip_whatsapp", "infobip_api"}:
        return "infobip"
    if value in {"twilio_api", "twilio_whatsapp"}:
        return "twilio"
    return value or "meta_cloud"


def _is_meta_provider(provider_name: str | None) -> bool:
    return normalize_whatsapp_provider_name(provider_name) == "meta_cloud"


def _is_infobip_provider(provider_name: str | None) -> bool:
    return normalize_whatsapp_provider_name(provider_name) == "infobip"


def _is_twilio_provider(provider_name: str | None) -> bool:
    return normalize_whatsapp_provider_name(provider_name) == "twilio"


def _strip_whatsapp_prefix(value: str | None) -> str:
    raw = (value or '').strip()
    if raw.lower().startswith('whatsapp:'):
        return raw.split(':', 1)[1].strip()
    return raw


def _normalized_provider_phone(value: str | None) -> str:
    stripped = _strip_whatsapp_prefix(value)
    normalized = normalize_phone(stripped)
    return normalized or stripped


def whatsapp_account_issues(
    *,
    provider_name: str | None = None,
    phone_number_id: str | None,
    business_account_id: str | None,
    access_token: str | None,
) -> list[str]:
    provider = normalize_whatsapp_provider_name(provider_name)
    issues: list[str] = []
    phone_id = (phone_number_id or '').strip()
    business_id = (business_account_id or '').strip()
    token = (access_token or '').strip()

    if provider not in SUPPORTED_WHATSAPP_PROVIDERS:
        issues.append('provider_name invalido (use meta_cloud, infobip ou twilio)')
        return issues

    if _is_meta_provider(provider):
        if not phone_id:
            issues.append('phone_number_id ausente')
        elif not phone_id.isdigit():
            issues.append('phone_number_id deve ser o ID numerico da Meta')

        if not business_id:
            issues.append('business_account_id ausente')
        elif not business_id.isdigit():
            issues.append('business_account_id deve ser o ID numerico da Meta')
    elif _is_infobip_provider(provider):
        if not phone_id:
            issues.append('sender_whatsapp ausente (campo phone_number_id)')

        if not business_id:
            issues.append('base_url_infobip ausente (campo business_account_id)')
        else:
            base = business_id.lower().replace('https://', '').replace('http://', '')
            if '.' not in base or '/' in base:
                issues.append('base_url_infobip invalida (ex.: 3dd13w.api.infobip.com)')
    else:
        if not phone_id:
            issues.append('sender_whatsapp ausente (campo phone_number_id)')
        elif not _normalized_provider_phone(phone_id):
            issues.append('sender_whatsapp invalido (ex.: whatsapp:+5511999999999)')

        if not business_id:
            issues.append('account_sid_twilio ausente (campo business_account_id)')
        elif not (business_id.startswith('AC') and len(business_id) == 34):
            issues.append('account_sid_twilio invalido (ex.: ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx)')

    if not token:
        issues.append('access_token ausente')
    else:
        token_lower = token.lower()
        if 'mock' in token_lower:
            issues.append('access_token de mock/simulacao detectado')
        if _is_meta_provider(provider):
            min_size = 32
        elif _is_twilio_provider(provider):
            min_size = 24
        else:
            min_size = 20
        if len(token) < min_size:
            issues.append('access_token muito curto para token de producao')

    return issues


def assert_whatsapp_account_ready_for_dispatch(db: Session, *, tenant_id: UUID) -> WhatsAppAccount:
    account = db.scalar(
        select(WhatsAppAccount)
        .where(
            WhatsAppAccount.tenant_id == tenant_id,
            WhatsAppAccount.is_active.is_(True),
        )
        .order_by(WhatsAppAccount.created_at.desc())
        .limit(1)
    )
    if not account:
        raise ApiError(
            status_code=400,
            code='WHATSAPP_ACCOUNT_NOT_CONFIGURED',
            message='Conta WhatsApp nao configurada para esta clinica.',
        )

    issues = whatsapp_account_issues(
        provider_name=account.provider_name,
        phone_number_id=account.phone_number_id,
        business_account_id=account.business_account_id,
        access_token=account.access_token_encrypted,
    )
    if issues:
        raise ApiError(
            status_code=400,
            code='WHATSAPP_ACCOUNT_INVALID',
            message='Conta WhatsApp com credenciais invalidas para envio real.',
            details={
                'issues': issues,
                'action': 'Atualize a conta WhatsApp em Configuracoes com credenciais validas do provider selecionado.',
            },
        )
    return account


def _get_meta_account_by_phone_number_id(db: Session, phone_number_id: str) -> WhatsAppAccount | None:
    return db.scalar(
        select(WhatsAppAccount).where(
            WhatsAppAccount.phone_number_id == phone_number_id,
            WhatsAppAccount.provider_name == "meta_cloud",
            WhatsAppAccount.is_active.is_(True),
        )
    )


def _get_infobip_account_by_sender(db: Session, sender: str | None) -> WhatsAppAccount | None:
    if not sender:
        return None
    sender_normalized = _normalized_provider_phone(sender)
    accounts = db.execute(
        select(WhatsAppAccount).where(
            WhatsAppAccount.provider_name == "infobip",
            WhatsAppAccount.is_active.is_(True),
        )
    ).scalars().all()
    for account in accounts:
        if account.phone_number_id == sender:
            return account
        if _normalized_provider_phone(account.phone_number_id) == sender_normalized:
            return account
    return None


def _get_twilio_account_by_destination(db: Session, destination: str | None) -> WhatsAppAccount | None:
    if not destination:
        return None
    destination_normalized = _normalized_provider_phone(destination)
    accounts = db.execute(
        select(WhatsAppAccount).where(
            WhatsAppAccount.provider_name == "twilio",
            WhatsAppAccount.is_active.is_(True),
        )
    ).scalars().all()
    for account in accounts:
        if account.phone_number_id == destination:
            return account
        if _normalized_provider_phone(account.phone_number_id) == destination_normalized:
            return account
    return None



def _create_patient_and_lead_from_phone(
    db: Session,
    tenant_id: UUID,
    raw_phone: str,
    *,
    preferred_unit_id: UUID | None = None,
) -> tuple[Patient, Lead]:
    normalized = normalize_phone(raw_phone)
    patient = db.scalar(
        select(Patient).where(Patient.tenant_id == tenant_id, Patient.normalized_phone == normalized)
    )
    if not patient:
        patient = Patient(
            tenant_id=tenant_id,
            full_name=f'Contato WhatsApp {normalized[-4:]}',
            phone=raw_phone,
            normalized_phone=normalized,
            unit_id=preferred_unit_id,
            status='lead',
            origin='whatsapp',
            lgpd_consent=False,
            marketing_opt_in=False,
        )
        db.add(patient)
        db.flush()
        db.add(
            PatientContact(
                tenant_id=tenant_id,
                patient_id=patient.id,
                channel='whatsapp',
                value=raw_phone,
                normalized_value=normalized,
                is_primary=True,
            )
        )
    elif preferred_unit_id and not patient.unit_id:
        patient.unit_id = preferred_unit_id
        db.add(patient)

    lead = Lead(
        tenant_id=tenant_id,
        patient_id=patient.id,
        name=patient.full_name,
        phone=patient.phone,
        email=patient.email,
        origin='whatsapp',
        interest='a definir',
        stage='novo',
        temperature='morno',
        score=30,
        status='ativo',
        notes='Lead criado automaticamente via WhatsApp webhook.',
    )
    db.add(lead)
    db.flush()
    return patient, lead



def _get_or_create_conversation(
    db: Session,
    tenant_id: UUID,
    patient_id: UUID,
    *,
    preferred_unit_id: UUID | None = None,
) -> UUID:
    base_stmt = (
        select(Conversation)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.patient_id == patient_id,
            Conversation.channel == 'whatsapp',
            Conversation.status.in_(['aberta', 'aguardando']),
        )
        .order_by(Conversation.last_message_at.desc())
    )

    conversation = None
    if preferred_unit_id:
        conversation = db.scalar(
            base_stmt.where(Conversation.unit_id == preferred_unit_id).limit(1)
        )

    if not conversation:
        conversation = db.scalar(base_stmt.limit(1))

    if conversation:
        if preferred_unit_id and not conversation.unit_id:
            conversation.unit_id = preferred_unit_id
            db.add(conversation)
            db.flush()
        return conversation.id

    conversation = Conversation(
        tenant_id=tenant_id,
        unit_id=preferred_unit_id,
        patient_id=patient_id,
        channel='whatsapp',
        status='aberta',
        tags=['novo_whatsapp'],
    )
    db.add(conversation)
    db.flush()
    return conversation.id



def _ingest_meta_webhook_payload(db: Session, payload: dict) -> dict:
    stats = {'received': 0, 'duplicates': 0, 'processed': 0, 'status_updates': 0}

    for entry in payload.get('entry', []):
        for change in entry.get('changes', []):
            value = change.get('value', {})
            metadata = value.get('metadata', {})
            phone_number_id = metadata.get('phone_number_id')
            if not phone_number_id:
                continue

            account = _get_meta_account_by_phone_number_id(db, phone_number_id)
            if not account:
                continue

            tenant_id = account.tenant_id

            for message in value.get('messages', []):
                stats['received'] += 1
                event_id = message.get('id')
                if not event_id:
                    continue

                inbox_event = WebhookInbox(
                    tenant_id=tenant_id,
                    provider='whatsapp',
                    event_id=_safe_webhook_event_id(event_id),
                    payload=message,
                    processed=False,
                )
                db.add(inbox_event)
                try:
                    db.flush()
                except IntegrityError:
                    db.rollback()
                    stats['duplicates'] += 1
                    continue

                sender_phone = message.get('from', '')
                normalized = normalize_phone(sender_phone)
                patient = db.scalar(
                    select(Patient).where(
                        Patient.tenant_id == tenant_id,
                        Patient.normalized_phone == normalized,
                    )
                )

                lead = None
                if not patient:
                    patient, lead = _create_patient_and_lead_from_phone(
                        db,
                        tenant_id,
                        sender_phone,
                        preferred_unit_id=account.unit_id,
                    )
                elif account.unit_id and not patient.unit_id:
                    patient.unit_id = account.unit_id
                    db.add(patient)

                preferred_unit_id = account.unit_id or patient.unit_id
                conversation_id = _get_or_create_conversation(
                    db,
                    tenant_id,
                    patient.id,
                    preferred_unit_id=preferred_unit_id,
                )
                body, inbound_type, interactive_reply = _extract_meta_inbound_body_and_interactive(message)
                inbound_payload = dict(message)
                if interactive_reply:
                    inbound_payload['interactive_reply'] = interactive_reply
                inbound_message = Message(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    direction=MessageDirection.INBOUND.value,
                    channel='whatsapp',
                    provider_message_id=event_id,
                    sender_type='patient',
                    body=body,
                    message_type=inbound_type,
                    payload=inbound_payload,
                    status=MessageStatus.RECEIVED.value,
                )
                db.add(inbound_message)

                conversation = db.get(Conversation, conversation_id)
                if conversation:
                    conversation.last_message_at = datetime.now(UTC)
                    db.add(conversation)
                db.add(
                    MessageEvent(
                        tenant_id=tenant_id,
                        event_type='webhook_message_received',
                        payload=message,
                    )
                )
                inbox_event.processed = True
                inbox_event.processed_at = datetime.now(UTC)
                db.add(inbox_event)
                db.commit()
                stats['processed'] += 1

                emit_event(
                    db,
                    tenant_id=tenant_id,
                    event_key='mensagem_recebida',
                    payload={
                        'conversation_id': str(conversation_id),
                        'patient_id': str(patient.id),
                        'lead_id': str(lead.id) if lead else None,
                        'phone': sender_phone,
                        'message': body,
                    },
                )
                try:
                    from app.services.ai_autoresponder_service import process_inbound_message as process_ai_autoresponder_inbound

                    process_ai_autoresponder_inbound(
                        db,
                        tenant_id=tenant_id,
                        conversation_id=conversation_id,
                        inbound_message_id=inbound_message.id,
                    )
                except Exception as exc:
                    logger.exception(
                        'ai_autoresponder.inbound_failed',
                        tenant_id=str(tenant_id),
                        conversation_id=str(conversation_id),
                        message_id=str(inbound_message.id),
                        error=str(exc),
                    )

            for status in value.get('statuses', []):
                provider_id = status.get('id')
                status_name = status.get('status')
                if not provider_id or not status_name:
                    continue

                event_id = f'{provider_id}:{status_name}'
                db.add(
                    WebhookInbox(
                        tenant_id=tenant_id,
                        provider='whatsapp',
                        event_id=_safe_webhook_event_id(event_id),
                        payload=status,
                        processed=True,
                        processed_at=datetime.now(UTC),
                    )
                )
                try:
                    db.flush()
                except IntegrityError:
                    db.rollback()
                    stats['duplicates'] += 1
                    continue

                msg = db.scalar(
                    select(Message).where(
                        Message.tenant_id == tenant_id,
                        Message.provider_message_id == provider_id,
                    )
                )
                if msg:
                    msg.status = status_name
                    if status_name == 'delivered':
                        msg.delivered_at = datetime.now(UTC)
                    elif status_name == 'read':
                        msg.read_at = datetime.now(UTC)
                    db.add(msg)

                db.add(
                    MessageEvent(
                        tenant_id=tenant_id,
                        message_id=msg.id if msg else None,
                        event_type=f'status_{status_name}',
                        payload=status,
                    )
                )
                db.commit()
                stats['status_updates'] += 1

    return stats


def _normalize_infobip_delivery_status(status_payload: dict | str | None) -> str:
    if isinstance(status_payload, dict):
        raw = (
            status_payload.get('groupName')
            or status_payload.get('name')
            or status_payload.get('description')
            or ''
        )
    else:
        raw = status_payload or ''

    status_name = str(raw).strip().lower()
    if not status_name:
        return 'sent'
    if 'seen' in status_name or 'read' in status_name:
        return 'read'
    if 'deliver' in status_name:
        return 'delivered'
    if 'fail' in status_name or 'reject' in status_name or 'undeliver' in status_name:
        return 'failed'
    if 'sent' in status_name or 'submit' in status_name or 'accept' in status_name or 'pending' in status_name:
        return 'sent'
    return status_name


def _ingest_infobip_webhook_payload(db: Session, payload: dict) -> dict:
    stats = {'received': 0, 'duplicates': 0, 'processed': 0, 'status_updates': 0}

    for result in payload.get('results', []):
        if not isinstance(result, dict):
            continue

        integration_type = str(result.get('integrationType') or '').upper()
        if integration_type and integration_type != 'WHATSAPP':
            continue

        account = _get_infobip_account_by_sender(
            db,
            result.get('to') or result.get('sender') or result.get('from'),
        )
        if not account:
            continue

        tenant_id = account.tenant_id
        provider_message_id = str(result.get('messageId') or result.get('pairedMessageId') or '').strip()
        sender_phone = str(result.get('from') or '').strip()
        message_block = result.get('message') if isinstance(result.get('message'), dict) else {}
        inbound_text, inferred_type, interactive_reply = _extract_infobip_inbound_body_and_interactive(result, message_block)

        has_status = isinstance(result.get('status'), dict) or bool(result.get('status'))
        is_inbound = bool(sender_phone and inbound_text)

        if is_inbound:
            stats['received'] += 1
            event_id = f'infobip_inbound:{provider_message_id or sender_phone}:{result.get("receivedAt") or ""}'
            inbox_event = WebhookInbox(
                tenant_id=tenant_id,
                provider='infobip_whatsapp',
                event_id=_safe_webhook_event_id(event_id),
                payload=result,
                processed=False,
            )
            db.add(inbox_event)
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                stats['duplicates'] += 1
                continue

            normalized = normalize_phone(sender_phone)
            patient = db.scalar(
                select(Patient).where(
                    Patient.tenant_id == tenant_id,
                    Patient.normalized_phone == normalized,
                )
            )
            lead = None
            if not patient:
                patient, lead = _create_patient_and_lead_from_phone(
                    db,
                    tenant_id,
                    sender_phone,
                    preferred_unit_id=account.unit_id,
                )
            elif account.unit_id and not patient.unit_id:
                patient.unit_id = account.unit_id
                db.add(patient)

            preferred_unit_id = account.unit_id or patient.unit_id
            conversation_id = _get_or_create_conversation(
                db,
                tenant_id,
                patient.id,
                preferred_unit_id=preferred_unit_id,
            )
            inbound_payload = dict(result)
            if interactive_reply:
                inbound_payload['interactive_reply'] = interactive_reply
            inbound_message = Message(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                direction=MessageDirection.INBOUND.value,
                channel='whatsapp',
                provider_message_id=provider_message_id or None,
                sender_type='patient',
                body=inbound_text,
                message_type=inferred_type,
                payload=inbound_payload,
                status=MessageStatus.RECEIVED.value,
            )
            db.add(inbound_message)

            conversation = db.get(Conversation, conversation_id)
            if conversation:
                conversation.last_message_at = datetime.now(UTC)
                db.add(conversation)

            db.add(
                MessageEvent(
                    tenant_id=tenant_id,
                    event_type='webhook_message_received',
                    payload=result,
                )
            )
            inbox_event.processed = True
            inbox_event.processed_at = datetime.now(UTC)
            db.add(inbox_event)
            db.commit()
            stats['processed'] += 1

            emit_event(
                db,
                tenant_id=tenant_id,
                event_key='mensagem_recebida',
                payload={
                    'conversation_id': str(conversation_id),
                    'patient_id': str(patient.id),
                    'lead_id': str(lead.id) if lead else None,
                    'phone': sender_phone,
                    'message': inbound_text,
                },
            )
            try:
                from app.services.ai_autoresponder_service import process_inbound_message as process_ai_autoresponder_inbound

                process_ai_autoresponder_inbound(
                    db,
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    inbound_message_id=inbound_message.id,
                )
            except Exception as exc:
                logger.exception(
                    'ai_autoresponder.inbound_failed',
                    tenant_id=str(tenant_id),
                    conversation_id=str(conversation_id),
                    message_id=str(inbound_message.id),
                    error=str(exc),
                )
            continue

        if has_status and provider_message_id:
            normalized_status = _normalize_infobip_delivery_status(result.get('status'))
            event_id = f'infobip_status:{provider_message_id}:{normalized_status}'
            db.add(
                WebhookInbox(
                    tenant_id=tenant_id,
                    provider='infobip_whatsapp',
                    event_id=_safe_webhook_event_id(event_id),
                    payload=result,
                    processed=True,
                    processed_at=datetime.now(UTC),
                )
            )
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                stats['duplicates'] += 1
                continue

            msg = db.scalar(
                select(Message).where(
                    Message.tenant_id == tenant_id,
                    Message.provider_message_id == provider_message_id,
                )
            )
            if msg:
                msg.status = normalized_status
                if normalized_status == 'delivered':
                    msg.delivered_at = datetime.now(UTC)
                elif normalized_status == 'read':
                    msg.read_at = datetime.now(UTC)
                db.add(msg)

            db.add(
                MessageEvent(
                    tenant_id=tenant_id,
                    message_id=msg.id if msg else None,
                    event_type=f'status_{normalized_status}',
                    payload=result,
                )
            )
            db.commit()
            stats['status_updates'] += 1

    return stats


def _normalize_twilio_delivery_status(status_payload: str | None) -> str:
    status_name = str(status_payload or '').strip().lower()
    if not status_name:
        return 'sent'
    if status_name in {'read', 'seen'}:
        return 'read'
    if status_name in {'delivered'}:
        return 'delivered'
    if status_name in {'undelivered', 'failed'}:
        return 'failed'
    if status_name in {'accepted', 'queued', 'sending', 'sent'}:
        return 'sent'
    if status_name in {'received'}:
        return 'received'
    return status_name


def _ingest_twilio_webhook_payload(db: Session, payload: dict) -> dict:
    stats = {'received': 0, 'duplicates': 0, 'processed': 0, 'status_updates': 0}

    message_sid = str(payload.get('MessageSid') or payload.get('SmsSid') or '').strip()
    from_phone = str(payload.get('From') or '').strip()
    to_phone = str(payload.get('To') or '').strip()
    body = str(payload.get('Body') or '').strip()
    raw_status = payload.get('MessageStatus') or payload.get('SmsStatus')
    normalized_status = _normalize_twilio_delivery_status(raw_status)
    num_media = str(payload.get('NumMedia') or '0').strip()

    account = _get_twilio_account_by_destination(db, to_phone)
    if not account:
        account = _get_twilio_account_by_destination(db, from_phone)
    if not account:
        return stats

    tenant_id = account.tenant_id
    account_phone_normalized = _normalized_provider_phone(account.phone_number_id)
    from_phone_normalized = _normalized_provider_phone(from_phone)
    to_phone_normalized = _normalized_provider_phone(to_phone)

    is_inbound = bool(
        message_sid
        and from_phone
        and to_phone
        and to_phone_normalized == account_phone_normalized
        and from_phone_normalized != account_phone_normalized
    )

    if is_inbound:
        stats['received'] += 1
        event_id = f'twilio_inbound:{message_sid}'
        inbox_event = WebhookInbox(
            tenant_id=tenant_id,
            provider='twilio_whatsapp',
            event_id=_safe_webhook_event_id(event_id),
            payload=payload,
            processed=False,
        )
        db.add(inbox_event)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            stats['duplicates'] += 1
            return stats

        sender_phone = _strip_whatsapp_prefix(from_phone)
        normalized = normalize_phone(sender_phone)
        patient = db.scalar(
            select(Patient).where(
                Patient.tenant_id == tenant_id,
                Patient.normalized_phone == normalized,
            )
        )
        lead = None
        if not patient:
            patient, lead = _create_patient_and_lead_from_phone(
                db,
                tenant_id,
                sender_phone,
                preferred_unit_id=account.unit_id,
            )
        elif account.unit_id and not patient.unit_id:
            patient.unit_id = account.unit_id
            db.add(patient)

        preferred_unit_id = account.unit_id or patient.unit_id
        conversation_id = _get_or_create_conversation(
            db,
            tenant_id,
            patient.id,
            preferred_unit_id=preferred_unit_id,
        )
        inbound_body = body
        if not inbound_body and num_media != '0':
            inbound_body = '[Mensagem com midia]'
        if not inbound_body:
            inbound_body = '[Mensagem sem texto]'
        inferred_type = 'media' if num_media != '0' else 'text'

        inbound_message = Message(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            direction=MessageDirection.INBOUND.value,
            channel='whatsapp',
            provider_message_id=message_sid or None,
            sender_type='patient',
            body=inbound_body,
            message_type=inferred_type,
            payload=payload,
            status=MessageStatus.RECEIVED.value,
        )
        db.add(inbound_message)

        conversation = db.get(Conversation, conversation_id)
        if conversation:
            conversation.last_message_at = datetime.now(UTC)
            db.add(conversation)

        db.add(
            MessageEvent(
                tenant_id=tenant_id,
                event_type='webhook_message_received',
                payload=payload,
            )
        )
        inbox_event.processed = True
        inbox_event.processed_at = datetime.now(UTC)
        db.add(inbox_event)
        db.commit()
        stats['processed'] += 1

        emit_event(
            db,
            tenant_id=tenant_id,
            event_key='mensagem_recebida',
            payload={
                'conversation_id': str(conversation_id),
                'patient_id': str(patient.id),
                'lead_id': str(lead.id) if lead else None,
                'phone': sender_phone,
                'message': inbound_body,
            },
        )
        try:
            from app.services.ai_autoresponder_service import process_inbound_message as process_ai_autoresponder_inbound

            process_ai_autoresponder_inbound(
                db,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                inbound_message_id=inbound_message.id,
            )
        except Exception as exc:
            logger.exception(
                'ai_autoresponder.inbound_failed',
                tenant_id=str(tenant_id),
                conversation_id=str(conversation_id),
                message_id=str(inbound_message.id),
                error=str(exc),
            )
        return stats

    has_status_update = bool(message_sid and normalized_status and normalized_status != 'received')
    if has_status_update:
        event_id = f'twilio_status:{message_sid}:{normalized_status}'
        db.add(
            WebhookInbox(
                tenant_id=tenant_id,
                provider='twilio_whatsapp',
                event_id=_safe_webhook_event_id(event_id),
                payload=payload,
                processed=True,
                processed_at=datetime.now(UTC),
            )
        )
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            stats['duplicates'] += 1
            return stats

        msg = db.scalar(
            select(Message).where(
                Message.tenant_id == tenant_id,
                Message.provider_message_id == message_sid,
            )
        )
        if msg:
            msg.status = normalized_status
            if normalized_status == 'delivered':
                msg.delivered_at = datetime.now(UTC)
            elif normalized_status == 'read':
                msg.read_at = datetime.now(UTC)
            db.add(msg)

        db.add(
            MessageEvent(
                tenant_id=tenant_id,
                message_id=msg.id if msg else None,
                event_type=f'status_{normalized_status}',
                payload=payload,
            )
        )
        db.commit()
        stats['status_updates'] += 1

    return stats


def ingest_webhook_payload(db: Session, payload: dict) -> dict:
    if isinstance(payload, dict):
        if isinstance(payload.get('entry'), list):
            return _ingest_meta_webhook_payload(db, payload)
        if isinstance(payload.get('results'), list):
            return _ingest_infobip_webhook_payload(db, payload)
        if payload.get('MessageSid') or payload.get('SmsSid'):
            return _ingest_twilio_webhook_payload(db, payload)

    return {'received': 0, 'duplicates': 0, 'processed': 0, 'status_updates': 0}


def queue_outbound_message(
    db: Session,
    *,
    tenant_id: UUID,
    conversation_id: UUID | None,
    to: str,
    body: str,
    message_type: str = 'text',
    template: dict | None = None,
    interactive: dict | None = None,
    metadata: dict | None = None,
) -> OutboxMessage:
    normalized_to = normalize_phone(to)
    if not normalized_to:
        raise ApiError(
            status_code=400,
            code='WHATSAPP_DESTINATION_INVALID',
            message='Numero de destino ausente ou invalido para envio no WhatsApp.',
        )
    if message_type == 'text' and not (body or '').strip():
        raise ApiError(
            status_code=400,
            code='WHATSAPP_BODY_REQUIRED',
            message='Mensagem vazia nao pode ser enviada.',
        )
    if message_type in {'interactive_list', 'interactive_buttons'} and not isinstance(interactive, dict):
        raise ApiError(
            status_code=400,
            code='WHATSAPP_INTERACTIVE_REQUIRED',
            message='Mensagem interativa requer payload de interactive.',
        )

    outbox = OutboxMessage(
        tenant_id=tenant_id,
        channel='whatsapp',
        status=OutboxStatus.PENDING.value,
        payload={
            'conversation_id': str(conversation_id) if conversation_id else None,
            'to': normalized_to,
            'body': body,
            'message_type': message_type,
            'template': template,
            'interactive': interactive,
            'metadata': metadata or {},
        },
        retry_count=0,
        max_retries=5,
    )
    db.add(outbox)
    db.commit()
    db.refresh(outbox)
    return outbox



def _provider_for_account(account: WhatsAppAccount):
    provider_name = normalize_whatsapp_provider_name(account.provider_name)
    if provider_name == 'infobip':
        return InfobipWhatsAppProvider(base_url=account.business_account_id)
    if provider_name == 'twilio':
        return TwilioWhatsAppProvider(account_sid=account.business_account_id)
    return WhatsAppCloudProvider()


def _extract_provider_message_id(response: dict | None) -> str | None:
    if not isinstance(response, dict):
        return None
    top_level_id = response.get('messageId') or response.get('id') or response.get('sid')
    if isinstance(top_level_id, str) and top_level_id.strip():
        return top_level_id
    messages = response.get('messages')
    if isinstance(messages, list) and messages:
        first = messages[0]
        if isinstance(first, dict):
            return first.get('id') or first.get('messageId')
    results = response.get('results')
    if isinstance(results, list) and results:
        first = results[0]
        if isinstance(first, dict):
            return first.get('messageId') or first.get('id')
    return None


def _extract_provider_dispatch_error(*, provider_name: str | None, response: dict | None) -> str | None:
    if normalize_whatsapp_provider_name(provider_name) != 'infobip':
        return None
    if not isinstance(response, dict):
        return None

    statuses: list[dict] = []
    top_level_status = response.get('status')
    if isinstance(top_level_status, dict):
        statuses.append(top_level_status)

    for key in ('messages', 'results'):
        rows = response.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_status = row.get('status')
            if isinstance(row_status, dict):
                statuses.append(row_status)

    for status_row in statuses:
        group_name = str(status_row.get('groupName') or '').strip().upper()
        name = str(status_row.get('name') or '').strip().upper()
        if group_name in {'REJECTED', 'UNDELIVERABLE', 'FAILED'} or name.startswith('REJECTED') or name.startswith('FAILED'):
            parts = [
                str(part).strip()
                for part in [status_row.get('groupName'), status_row.get('name'), status_row.get('description')]
                if part
            ]
            return ' | '.join(parts) or 'Infobip rejeitou a mensagem.'
    return None


def _dispatch_outbox_item(db: Session, item: OutboxMessage) -> None:
    account = db.scalar(
        select(WhatsAppAccount)
        .where(
            WhatsAppAccount.tenant_id == item.tenant_id,
            WhatsAppAccount.is_active.is_(True),
        )
        .order_by(WhatsAppAccount.created_at.desc())
        .limit(1)
    )
    if not account:
        item.status = OutboxStatus.FAILED.value
        item.last_error = 'Conta WhatsApp nao configurada'
        item.retry_count += 1
        item.next_retry_at = datetime.now(UTC) + timedelta(minutes=5)
        db.add(item)
        db.commit()
        return

    issues = whatsapp_account_issues(
        provider_name=account.provider_name,
        phone_number_id=account.phone_number_id,
        business_account_id=account.business_account_id,
        access_token=account.access_token_encrypted,
    )
    if issues:
        item.status = OutboxStatus.DEAD_LETTER.value
        item.retry_count = item.max_retries
        item.next_retry_at = None
        item.last_error = f'Conta WhatsApp invalida: {"; ".join(issues)}'
        db.add(item)
        db.commit()
        return

    item.status = OutboxStatus.PROCESSING.value
    db.add(item)
    db.commit()

    payload = item.payload or {}
    provider = _provider_for_account(account)
    try:
        response: dict
        if payload.get('message_type') == 'template' and payload.get('template'):
            template = payload['template']
            response = provider.send_template_message(
                phone_number_id=account.phone_number_id,
                access_token=account.access_token_encrypted,
                to=payload['to'],
                template_name=template['name'],
                language=template.get('language', 'pt_BR'),
                components=template.get('components', []),
            )
        elif payload.get('message_type') == 'interactive_buttons' and isinstance(payload.get('interactive'), dict):
            interactive = payload.get('interactive') or {}
            response = provider.send_interactive_buttons_message(
                phone_number_id=account.phone_number_id,
                access_token=account.access_token_encrypted,
                to=payload['to'],
                body=payload.get('body', ''),
                buttons=interactive.get('buttons') if isinstance(interactive.get('buttons'), list) else [],
                header_text=str(interactive.get('header_text') or '').strip() or None,
                footer_text=str(interactive.get('footer_text') or '').strip() or None,
            )
        elif payload.get('message_type') == 'interactive_list' and isinstance(payload.get('interactive'), dict):
            interactive = payload.get('interactive') or {}
            response = provider.send_interactive_list_message(
                phone_number_id=account.phone_number_id,
                access_token=account.access_token_encrypted,
                to=payload['to'],
                body=payload.get('body', ''),
                button_title=str(interactive.get('button_title') or 'Opções'),
                rows=interactive.get('rows') if isinstance(interactive.get('rows'), list) else [],
                section_title=str(interactive.get('section_title') or 'Escolha uma opção'),
                header_text=str(interactive.get('header_text') or '').strip() or None,
                footer_text=str(interactive.get('footer_text') or '').strip() or None,
            )
        else:
            response = provider.send_text_message(
                phone_number_id=account.phone_number_id,
                access_token=account.access_token_encrypted,
                to=payload['to'],
                body=payload.get('body', ''),
            )

        provider_dispatch_error = _extract_provider_dispatch_error(
            provider_name=account.provider_name,
            response=response,
        )
        if provider_dispatch_error:
            raise RuntimeError(f'NON_RETRYABLE_DISPATCH: {provider_dispatch_error}')

        provider_message_id = _extract_provider_message_id(response)

        payload_metadata = payload.get('metadata') if isinstance(payload.get('metadata'), dict) else {}
        outbound_message_id = payload_metadata.get('outbound_message_id')
        linked_outbound_message = None
        if outbound_message_id:
            try:
                outbound_uuid = UUID(outbound_message_id)
                linked_outbound_message = db.scalar(
                    select(Message).where(
                        Message.id == outbound_uuid,
                        Message.tenant_id == item.tenant_id,
                    )
                )
            except (ValueError, TypeError):
                linked_outbound_message = None

        conversation_id = payload.get('conversation_id')
        if linked_outbound_message:
            linked_outbound_message.provider_message_id = provider_message_id
            linked_outbound_message.status = MessageStatus.SENT.value
            linked_outbound_message.sent_at = datetime.now(UTC)
            existing_payload = linked_outbound_message.payload if isinstance(linked_outbound_message.payload, dict) else {}
            linked_outbound_message.payload = {
                **existing_payload,
                'provider_response': response,
            }
            db.add(linked_outbound_message)
        elif conversation_id:
            db.add(
                Message(
                    tenant_id=item.tenant_id,
                    conversation_id=UUID(conversation_id),
                    direction=MessageDirection.OUTBOUND.value,
                    channel='whatsapp',
                    provider_message_id=provider_message_id,
                    sender_type='automation',
                    body=payload.get('body') or '',
                    message_type=payload.get('message_type', 'text'),
                    payload=response,
                    status=MessageStatus.SENT.value,
                    sent_at=datetime.now(UTC),
                )
            )
        item.status = OutboxStatus.SENT.value
        item.last_error = None
        db.add(item)
        db.commit()
    except Exception as exc:
        error_message = str(exc)
        non_retryable_dispatch = False
        if error_message.startswith('NON_RETRYABLE_DISPATCH:'):
            non_retryable_dispatch = True
            error_message = error_message.split(':', 1)[1].strip()

        response = getattr(exc, 'response', None)
        if response is not None:
            try:
                response_payload = response.json()
            except ValueError:
                response_payload = response.text
            error_message = f'{error_message} | response={response_payload}'

        logger.exception('whatsapp.send_failed', outbox_id=str(item.id), error=str(exc))
        payload_metadata = payload.get('metadata') if isinstance(payload.get('metadata'), dict) else {}
        outbound_message_id = payload_metadata.get('outbound_message_id')
        if outbound_message_id:
            try:
                outbound_uuid = UUID(outbound_message_id)
                linked_outbound_message = db.scalar(
                    select(Message).where(
                        Message.id == outbound_uuid,
                        Message.tenant_id == item.tenant_id,
                    )
                )
                if linked_outbound_message:
                    linked_outbound_message.status = MessageStatus.FAILED.value
                    existing_payload = linked_outbound_message.payload if isinstance(linked_outbound_message.payload, dict) else {}
                    linked_outbound_message.payload = {
                        **existing_payload,
                        'dispatch_error': error_message[:300],
                    }
                    db.add(linked_outbound_message)
            except (ValueError, TypeError):
                pass
        item.last_error = error_message[:1000]
        if non_retryable_dispatch:
            item.retry_count = item.max_retries
            item.status = OutboxStatus.DEAD_LETTER.value
            item.next_retry_at = None
        else:
            item.retry_count += 1
            if item.retry_count >= item.max_retries:
                item.status = OutboxStatus.DEAD_LETTER.value
                item.next_retry_at = None
            else:
                item.status = OutboxStatus.FAILED.value
                item.next_retry_at = datetime.now(UTC) + timedelta(minutes=(2**item.retry_count))
        db.add(item)
        db.commit()



def process_outbox_batch(db: Session, *, batch_size: int = 30) -> dict:
    items = pending_jobs_for_dispatch(db)[:batch_size]
    sent = 0
    failed = 0

    for item in items:
        previous_status = item.status
        _dispatch_outbox_item(db, item)
        if item.status == OutboxStatus.SENT.value:
            sent += 1
        elif item.status in [OutboxStatus.FAILED.value, OutboxStatus.DEAD_LETTER.value] and previous_status != item.status:
            failed += 1

    return {'processed': len(items), 'sent': sent, 'failed': failed}

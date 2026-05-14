from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.models import Conversation, Lead, Message, Patient
from app.models.enums import MessageDirection, MessageStatus
from app.schemas.conversation import MessageCreate, MessageOutput
from app.services.ai_autoresponder_service import build_official_visit_guidance_response, get_global_config
from app.services.audit_service import record_audit
from app.services.automation_service import emit_event
from app.services.demo_whatsapp_simulation_service import maybe_schedule_demo_whatsapp_reply_simulation
from app.services.llm_service import classify_intent, suggest_reply
from app.services.subscription_service import enforce_plan_limit
from app.services.whatsapp_service import (
    assert_whatsapp_account_ready_for_dispatch,
    ensure_whatsapp_audio_media_stored,
    queue_outbound_message,
)

router = APIRouter(prefix='/messages', tags=['messages'])


class AISuggestionInput(BaseModel):
    prompt: str | None = None


@router.get('')
def list_messages(
    conversation_id: str,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(Message).where(
        Message.tenant_id == tenant_id,
        Message.conversation_id == conversation_id,
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    # Retorna sempre a página mais recente de mensagens para evitar "sumiço" em
    # conversas longas (quando há mais de 200 registros).
    recent_rows = db.execute(
        stmt.order_by(Message.created_at.desc()).offset(offset).limit(limit)
    ).scalars().all()
    rows = list(reversed(recent_rows))
    return {'data': [MessageOutput.model_validate(item, from_attributes=True).model_dump() for item in rows], 'meta': {'total': total, 'limit': limit, 'offset': offset}}


@router.get('/{message_id}/media')
def download_message_media(
    message_id: str,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    message = db.scalar(
        select(Message).where(
            Message.id == message_id,
            Message.tenant_id == tenant_id,
        )
    )
    if not message:
        raise ApiError(status_code=404, code='MESSAGE_NOT_FOUND', message='Mensagem nao encontrada')

    file_path, media_type, file_name = ensure_whatsapp_audio_media_stored(
        db,
        tenant_id=tenant_id,
        message=message,
    )

    record_audit(
        db,
        action='message.media.download',
        entity_type='message',
        entity_id=str(message.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'conversation_id': str(message.conversation_id), 'file_name': file_name},
    )

    return FileResponse(
        path=str(file_path),
        media_type=media_type or 'application/octet-stream',
        filename=file_name or file_path.name,
    )


@router.post('', response_model=MessageOutput)
def create_message(
    payload: MessageCreate,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    enforce_plan_limit(db, tenant_id, resource='monthly_messages', increment=1)

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == payload.conversation_id,
            Conversation.tenant_id == tenant_id,
        )
    )
    if not conversation:
        raise ApiError(status_code=404, code='CONVERSATION_NOT_FOUND', message='Conversa nao encontrada')

    contact_phone = None
    if conversation.patient_id:
        patient = db.scalar(
            select(Patient).where(Patient.id == conversation.patient_id, Patient.tenant_id == tenant_id)
        )
        if patient:
            contact_phone = patient.phone

    # Conversas iniciadas a partir de lead podem não ter paciente vinculado ainda.
    # Nesses casos, usa o telefone do lead como destino do WhatsApp.
    if not contact_phone and conversation.lead_id:
        lead = db.scalar(
            select(Lead).where(Lead.id == conversation.lead_id, Lead.tenant_id == tenant_id)
        )
        if lead:
            contact_phone = lead.phone

    if not contact_phone:
        raise ApiError(
            status_code=400,
            code='PATIENT_PHONE_REQUIRED',
            message='Conversa sem telefone de contato (paciente ou lead)',
        )

    assert_whatsapp_account_ready_for_dispatch(db, tenant_id=tenant_id)

    message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction=MessageDirection.OUTBOUND.value,
        channel='whatsapp',
        sender_type='user',
        sender_user_id=principal.user.id,
        body=payload.body,
        message_type=payload.message_type,
        payload={'source': 'manual_inbox'},
        status=MessageStatus.QUEUED.value,
    )
    db.add(message)
    db.flush()

    outbox = queue_outbound_message(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        to=contact_phone,
        body=payload.body,
        message_type=payload.message_type,
        metadata={
            'created_by_user_id': str(principal.user.id),
            'source': 'manual_inbox',
            'outbound_message_id': str(message.id),
        },
        commit=False,
    )

    message.payload = {'source': 'manual_inbox', 'queued_outbox_id': str(outbox.id)}
    conversation.last_message_at = datetime.now(UTC)
    db.add(conversation)
    db.commit()
    db.refresh(message)

    record_audit(
        db,
        action='message.create',
        entity_type='message',
        entity_id=str(message.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'conversation_id': str(conversation.id), 'outbox_id': str(outbox.id)},
    )

    emit_event(
        db,
        tenant_id=tenant_id,
        event_key='mensagem_enviada',
        payload={'conversation_id': str(conversation.id), 'message_id': str(message.id)},
    )
    maybe_schedule_demo_whatsapp_reply_simulation(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        outbound_message_id=message.id,
        source='manual_outbound',
    )

    return MessageOutput.model_validate(message, from_attributes=True)


@router.post('/{conversation_id}/ai-suggestion')
def ai_suggestion(
    conversation_id: str,
    payload: AISuggestionInput | None = None,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
):
    conversation = db.scalar(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.tenant_id == tenant_id)
    )
    if not conversation:
        raise ApiError(status_code=404, code='CONVERSATION_NOT_FOUND', message='Conversa nao encontrada')

    messages = db.execute(
        select(Message)
        .where(Message.tenant_id == tenant_id, Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(15)
    ).scalars().all()
    conversation_context = '\n'.join([f"{msg.direction}: {msg.body}" for msg in reversed(messages)])
    manual_prompt = (payload.prompt or '').strip() if payload else ''
    context_parts = [conversation_context]
    if manual_prompt:
        context_parts.append(f'Instrucao adicional do atendente: {manual_prompt}')
    context = '\n\n'.join([part for part in context_parts if part.strip()])
    latest_inbound = next(
        (
            msg.body
            for msg in messages
            if msg.direction == MessageDirection.INBOUND.value and msg.sender_type in {'patient', 'lead'}
        ),
        '',
    )
    guidance_input = '\n\n'.join([part for part in [latest_inbound, manual_prompt] if part.strip()])

    official_guidance = None
    if guidance_input:
        official_guidance = build_official_visit_guidance_response(
            db,
            conversation=conversation,
            inbound_text=guidance_input,
            config=get_global_config(db, tenant_id=tenant_id),
        )

    intent_input = messages[0].body if messages else ''
    if manual_prompt:
        intent_input = f'{intent_input}\n\nContexto adicional do atendente: {manual_prompt}'.strip()
    intent = classify_intent(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        message=intent_input,
    )

    if official_guidance:
        return {
            'conversation_id': conversation_id,
            'suggested_reply': official_guidance['response_text'],
            'intent': intent['output'],
            'metadata': {
                'suggest_reply': {
                    'source': 'official_visit_guidance',
                    'mode': official_guidance.get('mode'),
                    'details': official_guidance.get('metadata') or {},
                },
                'classify_intent': intent['metadata'],
                'manual_prompt_used': bool(manual_prompt),
            },
        }

    suggestion = suggest_reply(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        context=context,
    )

    return {
        'conversation_id': conversation_id,
        'suggested_reply': suggestion['output'],
        'intent': intent['output'],
        'metadata': {
            'suggest_reply': suggestion['metadata'],
            'classify_intent': intent['metadata'],
            'manual_prompt_used': bool(manual_prompt),
        },
    }

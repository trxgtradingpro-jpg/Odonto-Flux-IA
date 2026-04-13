from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.models import Conversation, Lead, Message, Patient
from app.models.enums import MessageDirection, MessageStatus
from app.schemas.conversation import MessageCreate, MessageOutput
from app.services.audit_service import record_audit
from app.services.automation_service import emit_event
from app.services.llm_service import classify_intent, suggest_reply
from app.services.subscription_service import enforce_plan_limit
from app.services.whatsapp_service import assert_whatsapp_account_ready_for_dispatch, queue_outbound_message

router = APIRouter(prefix='/messages', tags=['messages'])


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
    rows = db.execute(stmt.order_by(Message.created_at.asc()).offset(offset).limit(limit)).scalars().all()
    return {'data': [MessageOutput.model_validate(item, from_attributes=True).model_dump() for item in rows], 'meta': {'total': total, 'limit': limit, 'offset': offset}}


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

    outbox = queue_outbound_message(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        to=contact_phone,
        body=payload.body,
        message_type=payload.message_type,
        metadata={'created_by_user_id': str(principal.user.id), 'source': 'manual_inbox'},
    )

    message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction=MessageDirection.OUTBOUND.value,
        channel='whatsapp',
        sender_type='user',
        sender_user_id=principal.user.id,
        body=payload.body,
        message_type=payload.message_type,
        payload={'queued_outbox_id': str(outbox.id)},
        status=MessageStatus.QUEUED.value,
    )
    conversation.last_message_at = datetime.now(UTC)
    db.add(message)
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

    return MessageOutput.model_validate(message, from_attributes=True)


@router.post('/{conversation_id}/ai-suggestion')
def ai_suggestion(conversation_id: str, db: Session = Depends(get_db), tenant_id=Depends(get_tenant_id)):
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
    context = '\n'.join([f"{msg.direction}: {msg.body}" for msg in reversed(messages)])

    suggestion = suggest_reply(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        context=context,
    )
    intent = classify_intent(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        message=messages[0].body if messages else '',
    )

    return {
        'conversation_id': conversation_id,
        'suggested_reply': suggestion['output'],
        'intent': intent['output'],
        'metadata': {
            'suggest_reply': suggestion['metadata'],
            'classify_intent': intent['metadata'],
        },
    }

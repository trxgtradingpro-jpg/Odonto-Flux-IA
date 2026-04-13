
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.models import Conversation, Message
from app.schemas.conversation import (
    ConversationAIAutoresponderUpdate,
    ConversationCreate,
    ConversationOutput,
    ConversationUpdate,
)
from app.services.ai_autoresponder_service import (
    get_conversation_decisions,
    set_conversation_autoresponder,
)
from app.services.audit_service import record_audit
from app.services.llm_service import summarize_conversation

router = APIRouter(prefix='/conversations', tags=['conversations'])


@router.get('')
def list_conversations(
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    limit: int = Query(default=20, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status: str | None = None,
    assigned_user_id: str | None = None,
):
    stmt = select(Conversation).where(Conversation.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(Conversation.status == status)
    if assigned_user_id:
        stmt = stmt.where(Conversation.assigned_user_id == assigned_user_id)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Conversation.last_message_at.desc().nullslast()).offset(offset).limit(limit)).scalars().all()

    return {'data': [ConversationOutput.model_validate(item, from_attributes=True).model_dump() for item in rows], 'meta': {'total': total, 'limit': limit, 'offset': offset}}


@router.post('', response_model=ConversationOutput)
def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    item = Conversation(
        tenant_id=tenant_id,
        patient_id=payload.patient_id,
        lead_id=payload.lead_id,
        unit_id=payload.unit_id,
        channel=payload.channel,
        assigned_user_id=payload.assigned_user_id,
        tags=payload.tags,
        status='aberta',
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    record_audit(
        db,
        action='conversation.create',
        entity_type='conversation',
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'channel': item.channel},
    )
    return ConversationOutput.model_validate(item, from_attributes=True)


@router.patch('/{conversation_id}', response_model=ConversationOutput)
def update_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    item = db.scalar(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.tenant_id == tenant_id)
    )
    if not item:
        raise ApiError(status_code=404, code='CONVERSATION_NOT_FOUND', message='Conversa nao encontrada')

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(item, key, value)
    db.add(item)
    db.commit()
    db.refresh(item)

    record_audit(
        db,
        action='conversation.update',
        entity_type='conversation',
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata=updates,
    )

    return ConversationOutput.model_validate(item, from_attributes=True)


@router.post('/{conversation_id}/summarize')
def summarize(conversation_id: str, db: Session = Depends(get_db), tenant_id=Depends(get_tenant_id)):
    conversation = db.scalar(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.tenant_id == tenant_id)
    )
    if not conversation:
        raise ApiError(status_code=404, code='CONVERSATION_NOT_FOUND', message='Conversa nao encontrada')

    messages = db.execute(
        select(Message)
        .where(Message.tenant_id == tenant_id, Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
    ).scalars().all()

    transcript = '\n'.join([
        f"[{msg.direction}] {msg.body}" for msg in messages
    ])
    llm_result = summarize_conversation(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        transcript=transcript,
    )
    conversation.ai_summary = llm_result['output']
    db.add(conversation)
    db.commit()
    return {'conversation_id': conversation_id, 'summary': llm_result['output'], 'metadata': llm_result['metadata']}


@router.put('/{conversation_id}/ai-autoresponder', response_model=ConversationOutput)
def set_ai_autoresponder_mode(
    conversation_id: str,
    payload: ConversationAIAutoresponderUpdate,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    try:
        conversation_uuid = UUID(conversation_id)
    except ValueError as exc:
        raise ApiError(status_code=400, code='CONVERSATION_ID_INVALID', message='ID da conversa invalido') from exc

    item = set_conversation_autoresponder(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_uuid,
        enabled=payload.enabled,
    )
    if not item:
        raise ApiError(status_code=404, code='CONVERSATION_NOT_FOUND', message='Conversa nao encontrada')

    record_audit(
        db,
        action='ai_autoresponder.toggle',
        entity_type='conversation',
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={
            'enabled': payload.enabled,
            'scope': 'conversation',
        },
    )
    return ConversationOutput.model_validate(item, from_attributes=True)


@router.get('/{conversation_id}/ai-autoresponder/decisions')
def list_ai_autoresponder_decisions(
    conversation_id: str,
    limit: int = Query(default=30, ge=1, le=200),
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
):
    try:
        conversation_uuid = UUID(conversation_id)
    except ValueError as exc:
        raise ApiError(status_code=400, code='CONVERSATION_ID_INVALID', message='ID da conversa invalido') from exc

    conversation = db.scalar(
        select(Conversation).where(Conversation.id == conversation_uuid, Conversation.tenant_id == tenant_id)
    )
    if not conversation:
        raise ApiError(status_code=404, code='CONVERSATION_NOT_FOUND', message='Conversa nao encontrada')

    data = get_conversation_decisions(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_uuid,
        limit=limit,
    )
    return {'data': data, 'meta': {'limit': limit, 'total': len(data)}}

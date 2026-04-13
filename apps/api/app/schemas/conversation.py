from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ConversationCreate(BaseModel):
    patient_id: UUID | None = None
    lead_id: UUID | None = None
    unit_id: UUID | None = None
    channel: str = 'whatsapp'
    assigned_user_id: UUID | None = None
    tags: list[str] = []


class ConversationUpdate(BaseModel):
    patient_id: UUID | None = None
    lead_id: UUID | None = None
    unit_id: UUID | None = None
    assigned_user_id: UUID | None = None
    status: str | None = None
    tags: list[str] | None = None
    ai_summary: str | None = None
    ai_autoresponder_enabled: bool | None = None


class ConversationOutput(BaseModel):
    id: UUID
    tenant_id: UUID
    patient_id: UUID | None
    lead_id: UUID | None
    unit_id: UUID | None
    channel: str
    status: str
    assigned_user_id: UUID | None
    tags: list[str]
    ai_summary: str | None
    ai_autoresponder_enabled: bool | None
    ai_autoresponder_last_decision: str | None
    ai_autoresponder_last_reason: str | None
    ai_autoresponder_last_at: datetime | None
    ai_autoresponder_consecutive_count: int
    last_message_at: datetime | None


class ConversationAIAutoresponderUpdate(BaseModel):
    enabled: bool | None = None


class MessageCreate(BaseModel):
    conversation_id: UUID
    body: str
    message_type: str = 'text'


class MessageOutput(BaseModel):
    id: UUID
    tenant_id: UUID
    conversation_id: UUID
    direction: str
    status: str
    body: str
    message_type: str
    sender_type: str
    sent_at: datetime | None
    created_at: datetime

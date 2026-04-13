from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CampaignCreate(BaseModel):
    name: str
    objective: str = ''
    status: str = 'rascunho'
    template_id: UUID | None = None
    unit_id: UUID | None = None
    segment_filter: dict = {}
    scheduled_at: datetime | None = None


class CampaignUpdate(BaseModel):
    name: str | None = None
    objective: str | None = None
    status: str | None = None
    template_id: UUID | None = None
    unit_id: UUID | None = None
    segment_filter: dict | None = None
    scheduled_at: datetime | None = None


class CampaignOutput(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    objective: str
    status: str
    scheduled_at: datetime | None
    started_at: datetime | None
    ended_at: datetime | None

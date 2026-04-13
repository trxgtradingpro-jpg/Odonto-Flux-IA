from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AuditLogOutput(BaseModel):
    id: UUID
    tenant_id: UUID | None
    user_id: UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    metadata: dict = Field(validation_alias='metadata_json')
    ip_address: str | None
    user_agent: str | None
    occurred_at: datetime

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DocumentCreate(BaseModel):
    title: str
    document_type: str
    description: str | None = None
    patient_id: UUID | None = None
    unit_id: UUID | None = None
    is_sensitive: bool = False


class DocumentOutput(BaseModel):
    id: UUID
    tenant_id: UUID
    title: str
    document_type: str
    description: str | None
    patient_id: UUID | None
    unit_id: UUID | None
    created_by_user_id: UUID | None
    current_version_id: UUID | None
    is_sensitive: bool
    created_at: datetime

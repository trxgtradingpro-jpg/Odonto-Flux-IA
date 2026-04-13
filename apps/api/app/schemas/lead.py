from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class LeadCreate(BaseModel):
    name: str
    phone: str | None = None
    email: str | None = None
    origin: str | None = None
    interest: str | None = None
    stage: str = 'novo'
    score: int = 0
    temperature: str = 'morno'
    status: str = 'ativo'
    notes: str = ''
    owner_user_id: UUID | None = None


class LeadUpdate(BaseModel):
    stage: str | None = None
    score: int | None = None
    temperature: str | None = None
    status: str | None = None
    notes: str | None = None
    owner_user_id: UUID | None = None
    patient_id: UUID | None = None


class LeadOutput(BaseModel):
    id: UUID
    tenant_id: UUID
    patient_id: UUID | None
    owner_user_id: UUID | None
    name: str
    phone: str | None
    email: str | None
    origin: str | None
    interest: str | None
    stage: str
    score: int
    temperature: str
    status: str
    created_at: datetime


class LeadCsvImportInput(BaseModel):
    csv_content: str
    dry_run: bool = True


class LeadCsvImportError(BaseModel):
    line: int
    message: str


class LeadCsvImportOutput(BaseModel):
    dry_run: bool
    processed: int
    created: int
    skipped: int
    errors: list[LeadCsvImportError]

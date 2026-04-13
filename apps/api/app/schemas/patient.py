from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PatientCreate(BaseModel):
    full_name: str = Field(min_length=3)
    phone: str
    email: str | None = None
    birth_date: date | None = None
    operational_notes: str = ''
    status: str = 'ativo'
    origin: str | None = None
    tags: list[str] = []
    lgpd_consent: bool = False
    marketing_opt_in: bool = False
    unit_id: UUID | None = None


class PatientUpdate(BaseModel):
    full_name: str | None = None
    email: str | None = None
    birth_date: date | None = None
    operational_notes: str | None = None
    status: str | None = None
    tags: list[str] | None = None
    lgpd_consent: bool | None = None
    marketing_opt_in: bool | None = None


class PatientOutput(BaseModel):
    id: UUID
    tenant_id: UUID
    unit_id: UUID | None
    full_name: str
    phone: str
    email: str | None
    birth_date: date | None
    status: str
    origin: str | None
    tags_cache: list[str]
    lgpd_consent: bool
    marketing_opt_in: bool
    created_at: datetime


class PatientCsvImportInput(BaseModel):
    csv_content: str
    dry_run: bool = True


class CsvImportError(BaseModel):
    line: int
    message: str


class PatientCsvImportOutput(BaseModel):
    dry_run: bool
    processed: int
    created: int
    skipped: int
    errors: list[CsvImportError]

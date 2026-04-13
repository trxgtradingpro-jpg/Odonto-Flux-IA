from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AppointmentCreate(BaseModel):
    patient_id: UUID
    unit_id: UUID
    professional_id: UUID | None = None
    procedure_type: str
    starts_at: datetime
    ends_at: datetime | None = None
    origin: str = 'manual'
    notes: str = ''


class AppointmentUpdate(BaseModel):
    professional_id: UUID | None = None
    procedure_type: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    status: str | None = None
    confirmation_status: str | None = None
    notes: str | None = None


class AppointmentOutput(BaseModel):
    id: UUID
    tenant_id: UUID
    patient_id: UUID
    unit_id: UUID
    professional_id: UUID | None
    procedure_type: str
    starts_at: datetime
    ends_at: datetime | None
    status: str
    confirmation_status: str
    origin: str
    notes: str

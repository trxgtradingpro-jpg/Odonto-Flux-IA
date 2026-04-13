from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AutomationCreate(BaseModel):
    name: str
    description: str | None = None
    trigger_type: str
    trigger_key: str
    conditions: dict = {}
    actions: list[dict] = []
    retry_policy: dict = {}
    is_active: bool = True


class AutomationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    trigger_key: str | None = None
    conditions: dict | None = None
    actions: list[dict] | None = None
    retry_policy: dict | None = None
    is_active: bool | None = None


class AutomationOutput(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    trigger_type: str
    trigger_key: str
    conditions: dict
    actions: list[dict]
    is_active: bool
    created_at: datetime


class AutomationRunOutput(BaseModel):
    id: UUID
    automation_id: UUID
    status: str
    trigger_payload: dict
    result_payload: dict
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None

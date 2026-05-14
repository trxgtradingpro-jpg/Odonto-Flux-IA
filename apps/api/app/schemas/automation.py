from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AutomationCreate(BaseModel):
    name: str
    description: str | None = None
    trigger_type: str
    trigger_key: str
    conditions: dict = Field(default_factory=dict)
    actions: list[dict] = Field(default_factory=list)
    retry_policy: dict = Field(default_factory=dict)
    is_active: bool = True


class AutomationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    trigger_type: str | None = None
    trigger_key: str | None = None
    conditions: dict | None = None
    actions: list[dict] | None = None
    retry_policy: dict | None = None
    is_active: bool | None = None


class AutomationOutput(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    description: str | None
    trigger_type: str
    trigger_key: str
    conditions: dict
    actions: list[dict]
    retry_policy: dict
    is_active: bool
    paused_at: datetime | None
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
    retries: int
    created_at: datetime


class AutomationSimulationInput(BaseModel):
    trigger_payload: dict = Field(default_factory=dict)


class AutomationDraftSimulationInput(BaseModel):
    automation: AutomationCreate
    trigger_payload: dict = Field(default_factory=dict)


class AutomationManualExecuteInput(BaseModel):
    trigger_payload: dict = Field(default_factory=dict)
    confirmation: str


class AutomationManualExecuteOutput(BaseModel):
    run_created: bool
    run_id: UUID | None = None
    simulation: dict


class AutomationHistoryOutput(BaseModel):
    id: UUID
    action: str
    user_id: UUID | None
    metadata: dict = Field(default_factory=dict)
    occurred_at: datetime

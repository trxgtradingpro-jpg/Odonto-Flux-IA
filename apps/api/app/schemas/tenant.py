from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TenantCreate(BaseModel):
    legal_name: str = Field(min_length=2, max_length=255)
    trade_name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=120)
    plan_code: str = 'starter'


class TenantUpdate(BaseModel):
    trade_name: str | None = None
    timezone: str | None = None
    locale: str | None = None
    currency: str | None = None
    is_active: bool | None = None


class TenantOutput(BaseModel):
    id: UUID
    legal_name: str
    trade_name: str
    slug: str
    timezone: str
    locale: str
    currency: str
    subscription_status: str
    is_active: bool
    created_at: datetime


class UnitCreate(BaseModel):
    name: str
    code: str
    phone: str | None = None
    email: str | None = None
    address: dict = {}
    working_hours: dict = {}


class UnitUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    address: dict | None = None
    working_hours: dict | None = None
    is_active: bool | None = None


class UnitOutput(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    code: str
    phone: str | None
    email: str | None
    is_active: bool

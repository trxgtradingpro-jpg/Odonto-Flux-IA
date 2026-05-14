from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=3)
    password: str = Field(min_length=10)
    phone: str | None = None
    unit_id: UUID | None = None
    roles: list[str]
    page_permissions: dict[str, object] | None = None
    force_fullscreen_mode: bool = False


class UserUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    unit_id: UUID | None = None
    is_active: bool | None = None
    roles: list[str] | None = None
    page_permissions: dict[str, object] | None = None
    force_fullscreen_mode: bool | None = None


class UserOutput(BaseModel):
    id: UUID
    tenant_id: UUID | None
    unit_id: UUID | None
    email: str
    full_name: str
    phone: str | None
    is_active: bool
    roles: list[str]
    page_permissions: dict[str, object]
    force_fullscreen_mode: bool
    last_login_at: datetime | None = None
    created_at: datetime


class InviteInput(BaseModel):
    email: EmailStr
    role_name: str

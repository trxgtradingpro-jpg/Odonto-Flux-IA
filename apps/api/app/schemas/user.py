from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=3)
    password: str = Field(min_length=10)
    phone: str | None = None
    roles: list[str]


class UserUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    roles: list[str] | None = None


class UserOutput(BaseModel):
    id: UUID
    tenant_id: UUID | None
    email: EmailStr
    full_name: str
    phone: str | None
    is_active: bool
    roles: list[str]
    last_login_at: datetime | None = None
    created_at: datetime


class InviteInput(BaseModel):
    email: EmailStr
    role_name: str

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PageMeta(BaseModel):
    total: int
    limit: int
    offset: int


class PageResponse(BaseModel):
    data: list[dict]
    meta: PageMeta


class CreatedResponse(BaseModel):
    id: UUID
    created_at: datetime

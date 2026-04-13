from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import Base

T = TypeVar('T', bound=Base)


class BaseRepository(Generic[T]):
    def __init__(self, db: Session, model: type[T]):
        self.db = db
        self.model = model

    def get(self, item_id):
        return self.db.get(self.model, item_id)

    def list_by_tenant(self, tenant_id, *, limit: int = 20, offset: int = 0):
        stmt = select(self.model).where(self.model.tenant_id == tenant_id).offset(offset).limit(limit)
        return self.db.execute(stmt).scalars().all()

    def create(self, **values):
        item = self.model(**values)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update(self, item, **values):
        for key, value in values.items():
            setattr(item, key, value)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

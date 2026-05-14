from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.models import Appointment, Campaign, Conversation, Document, Patient, Professional, Unit, WhatsAppAccount
from app.schemas.tenant import UnitCreate, UnitOutput, UnitUpdate
from app.services.audit_service import record_audit
from app.services.subscription_service import enforce_plan_limit
from app.services.unit_catalog_service import (
    delete_unit_services,
    list_unit_services_map,
    normalize_unit_services,
    set_unit_services,
    sync_unit_services_into_global_knowledge_base,
)

router = APIRouter(prefix='/units', tags=['units'])


def _normalize_unit_payload(raw_payload: dict) -> dict:
    data = dict(raw_payload)
    if "name" in data:
        data["name"] = " ".join(str(data.get("name") or "").strip().split())
    if "code" in data:
        data["code"] = " ".join(str(data.get("code") or "").strip().split()).upper()
    if "phone" in data:
        data["phone"] = " ".join(str(data.get("phone") or "").strip().split()) or None
    if "email" in data:
        data["email"] = " ".join(str(data.get("email") or "").strip().split()).lower() or None
    if "services" in data:
        data["services"] = normalize_unit_services(data.get("services"))
    return data


def _serialize_unit(item: Unit, *, services_map: dict[str, list[str]]) -> dict:
    payload = UnitOutput.model_validate(item, from_attributes=True).model_dump()
    payload["services"] = services_map.get(str(item.id), [])
    return payload


@router.get('')
def list_units(
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(Unit).where(Unit.tenant_id == tenant_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Unit.created_at.desc()).offset(offset).limit(limit)).scalars().all()
    services_map = list_unit_services_map(db, tenant_id=tenant_id)
    return {'data': [_serialize_unit(item, services_map=services_map) for item in rows], 'meta': {'total': total, 'limit': limit, 'offset': offset}}


@router.post('', response_model=UnitOutput)
def create_unit(
    payload: UnitCreate,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    enforce_plan_limit(db, tenant_id, resource='units', increment=1)
    normalized_payload = _normalize_unit_payload(payload.model_dump())
    unit_services = normalized_payload.pop("services", [])

    exists = db.scalar(select(Unit).where(Unit.tenant_id == tenant_id, func.lower(Unit.code) == normalized_payload["code"].lower()))
    if exists:
        raise ApiError(status_code=409, code='UNIT_CODE_EXISTS', message='Codigo da unidade ja existe')

    item = Unit(tenant_id=tenant_id, **normalized_payload)
    db.add(item)
    db.commit()
    db.refresh(item)
    services = set_unit_services(db, tenant_id=tenant_id, unit_id=item.id, services=unit_services)
    sync_unit_services_into_global_knowledge_base(db, tenant_id=tenant_id, services=services)
    record_audit(
        db,
        action='unit.create',
        entity_type='unit',
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'code': item.code, 'services': services},
    )
    return UnitOutput.model_validate(
        {
            **UnitOutput.model_validate(item, from_attributes=True).model_dump(),
            "services": services,
        }
    )


@router.patch('/{unit_id}', response_model=UnitOutput)
def update_unit(
    unit_id: str,
    payload: UnitUpdate,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    item = db.scalar(select(Unit).where(Unit.id == unit_id, Unit.tenant_id == tenant_id))
    if not item:
        raise ApiError(status_code=404, code='UNIT_NOT_FOUND', message='Unidade nao encontrada')

    updates = _normalize_unit_payload(payload.model_dump(exclude_unset=True))
    services = updates.pop("services", None)
    next_code = updates.get("code")
    if next_code:
        exists = db.scalar(
            select(Unit).where(
                Unit.tenant_id == tenant_id,
                func.lower(Unit.code) == next_code.lower(),
                Unit.id != item.id,
            )
        )
        if exists:
            raise ApiError(status_code=409, code='UNIT_CODE_EXISTS', message='Codigo da unidade ja existe')

    for key, value in updates.items():
        setattr(item, key, value)
    db.add(item)
    db.commit()
    db.refresh(item)

    if services is not None:
        services = set_unit_services(db, tenant_id=tenant_id, unit_id=item.id, services=services)
        sync_unit_services_into_global_knowledge_base(db, tenant_id=tenant_id, services=services)
    else:
        services = list_unit_services_map(db, tenant_id=tenant_id).get(str(item.id), [])

    record_audit(
        db,
        action='unit.update',
        entity_type='unit',
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={**updates, 'services': services},
    )
    return UnitOutput.model_validate(
        {
            **UnitOutput.model_validate(item, from_attributes=True).model_dump(),
            "services": services,
        }
    )


@router.delete('/{unit_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_unit(
    unit_id: UUID,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    item = db.scalar(select(Unit).where(Unit.id == unit_id, Unit.tenant_id == tenant_id))
    if not item:
        raise ApiError(status_code=404, code='UNIT_NOT_FOUND', message='Unidade nao encontrada')

    dependency_counts = {
        "appointments": db.scalar(select(func.count()).select_from(Appointment).where(Appointment.tenant_id == tenant_id, Appointment.unit_id == unit_id)) or 0,
        "professionals": db.scalar(select(func.count()).select_from(Professional).where(Professional.tenant_id == tenant_id, Professional.unit_id == unit_id)) or 0,
        "patients": db.scalar(select(func.count()).select_from(Patient).where(Patient.tenant_id == tenant_id, Patient.unit_id == unit_id)) or 0,
        "conversations": db.scalar(select(func.count()).select_from(Conversation).where(Conversation.tenant_id == tenant_id, Conversation.unit_id == unit_id)) or 0,
        "campaigns": db.scalar(select(func.count()).select_from(Campaign).where(Campaign.tenant_id == tenant_id, Campaign.unit_id == unit_id)) or 0,
        "documents": db.scalar(select(func.count()).select_from(Document).where(Document.tenant_id == tenant_id, Document.unit_id == unit_id)) or 0,
        "whatsapp_accounts": db.scalar(select(func.count()).select_from(WhatsAppAccount).where(WhatsAppAccount.tenant_id == tenant_id, WhatsAppAccount.unit_id == unit_id)) or 0,
    }
    if any(dependency_counts.values()):
        raise ApiError(
            status_code=409,
            code='UNIT_DELETE_BLOCKED',
            message='Esta unidade ja possui dados vinculados. Desative a unidade em vez de excluir.',
        )

    unit_name = item.name
    services = list_unit_services_map(db, tenant_id=tenant_id).get(str(item.id), [])
    delete_unit_services(db, tenant_id=tenant_id, unit_id=item.id)
    db.delete(item)
    db.commit()

    record_audit(
        db,
        action='unit.delete',
        entity_type='unit',
        entity_id=str(unit_id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={
            'name': unit_name,
            'services': services,
            'deleted_at': datetime.now(UTC).isoformat(),
        },
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

import csv
from datetime import UTC, datetime
from io import StringIO

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.api.unit_scope import get_effective_unit_id, patient_unit_scope_filter
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.models import Appointment, Conversation, Document, Lead, Patient, PatientContact, PatientTag, Setting, Unit
from app.schemas.patient import (
    PatientCreate,
    PatientCsvImportInput,
    PatientCsvImportOutput,
    PatientOutput,
    PatientUpdate,
)
from app.services.audit_service import record_audit
from app.utils.document import normalize_cpf
from app.utils.phone import normalize_phone

router = APIRouter(prefix='/patients', tags=['patients'])
CPF_CONTACT_CHANNEL = 'cpf'


def _parse_bool(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {'1', 'true', 'sim', 'yes', 'y'}


def _primary_cpf_by_patient_id(db: Session, *, tenant_id, patient_ids: list) -> dict:
    if not patient_ids:
        return {}

    rows = db.execute(
        select(PatientContact.patient_id, PatientContact.value, PatientContact.normalized_value)
        .where(
            PatientContact.tenant_id == tenant_id,
            PatientContact.patient_id.in_(patient_ids),
            PatientContact.channel == CPF_CONTACT_CHANNEL,
        )
        .order_by(PatientContact.patient_id.asc(), PatientContact.is_primary.desc(), PatientContact.created_at.asc())
    ).all()

    cpf_by_patient_id = {}
    for patient_id, value, normalized_value in rows:
        cpf_by_patient_id.setdefault(patient_id, normalized_value or value)
    return cpf_by_patient_id


def _serialize_patient_rows(db: Session, *, tenant_id, rows: list[Patient]) -> list[dict]:
    cpf_by_patient_id = _primary_cpf_by_patient_id(
        db,
        tenant_id=tenant_id,
        patient_ids=[item.id for item in rows],
    )

    payload = []
    for item in rows:
        serialized = PatientOutput.model_validate(item, from_attributes=True).model_dump()
        if not serialized.get('cpf'):
            contact_cpf = cpf_by_patient_id.get(item.id)
            if contact_cpf:
                serialized['cpf'] = contact_cpf
        payload.append(serialized)
    return payload


@router.get('')
def list_patients(
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
    limit: int = Query(default=20, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    q: str | None = None,
    unit_id: UUID | None = None,
):
    stmt = select(Patient).where(Patient.tenant_id == tenant_id, Patient.archived_at.is_(None))
    effective_unit_id = get_effective_unit_id(
        db,
        principal=principal,
        tenant_id=tenant_id,
        requested_unit_id=unit_id,
    )
    if effective_unit_id:
        stmt = stmt.where(patient_unit_scope_filter(tenant_id=tenant_id, unit_id=effective_unit_id))
    if q:
        search_term = q.strip()
        digits_only = ''.join(ch for ch in search_term if ch.isdigit())
        filters = [
            Patient.full_name.ilike(f'%{search_term}%'),
            Patient.phone.ilike(f'%{search_term}%'),
            Patient.cpf.ilike(f'%{search_term}%'),
        ]
        if digits_only:
            filters.append(Patient.normalized_phone.ilike(f'%{digits_only}%'))
            filters.append(Patient.normalized_cpf.ilike(f'%{digits_only}%'))
            filters.append(
                Patient.id.in_(
                    select(PatientContact.patient_id).where(
                        PatientContact.tenant_id == tenant_id,
                        PatientContact.channel == CPF_CONTACT_CHANNEL,
                        or_(
                            PatientContact.normalized_value.ilike(f'%{digits_only}%'),
                            PatientContact.value.ilike(f'%{search_term}%'),
                        ),
                    )
                )
            )
        stmt = stmt.where(or_(*filters))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Patient.created_at.desc()).offset(offset).limit(limit)).scalars().all()
    return {
        'data': _serialize_patient_rows(db, tenant_id=tenant_id, rows=rows),
        'meta': {'total': total, 'limit': limit, 'offset': offset},
    }


@router.post('', response_model=PatientOutput)
def create_patient(
    payload: PatientCreate,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    normalized_phone = normalize_phone(payload.phone)
    normalized_cpf = normalize_cpf(payload.cpf)
    existing = db.scalar(
        select(Patient).where(Patient.tenant_id == tenant_id, Patient.normalized_phone == normalized_phone)
    )
    if existing:
        raise ApiError(status_code=409, code='PATIENT_DUPLICATE_PHONE', message='Telefone ja cadastrado no tenant')
    if normalized_cpf:
        existing_cpf = db.scalar(
            select(Patient).where(Patient.tenant_id == tenant_id, Patient.normalized_cpf == normalized_cpf)
        )
        if existing_cpf:
            raise ApiError(status_code=409, code='PATIENT_DUPLICATE_CPF', message='CPF ja cadastrado no tenant')

    data = payload.model_dump()
    tags = data.pop('tags', [])
    data["normalized_cpf"] = normalized_cpf or None
    data["cpf"] = data.get("cpf") or None
    patient = Patient(
        tenant_id=tenant_id,
        normalized_phone=normalized_phone,
        tags_cache=tags,
        **data,
    )
    db.add(patient)
    db.flush()

    for tag in tags:
        db.add(PatientTag(tenant_id=tenant_id, patient_id=patient.id, tag=tag))

    db.commit()
    db.refresh(patient)

    record_audit(
        db,
        action='patient.create',
        entity_type='patient',
        entity_id=str(patient.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'status': patient.status, 'origin': patient.origin},
    )

    return PatientOutput.model_validate(patient, from_attributes=True)


@router.delete('/{patient_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_patient(
    patient_id: str,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    patient = db.scalar(select(Patient).where(Patient.id == patient_id, Patient.tenant_id == tenant_id))
    if not patient or patient.archived_at is not None:
        raise ApiError(status_code=404, code='PATIENT_NOT_FOUND', message='Paciente nao encontrado')

    now = datetime.now(UTC)
    linked_summary = {
        'appointments': db.scalar(
            select(func.count()).select_from(Appointment).where(Appointment.tenant_id == tenant_id, Appointment.patient_id == patient.id)
        )
        or 0,
        'conversations': db.scalar(
            select(func.count()).select_from(Conversation).where(Conversation.tenant_id == tenant_id, Conversation.patient_id == patient.id)
        )
        or 0,
        'documents': db.scalar(
            select(func.count()).select_from(Document).where(Document.tenant_id == tenant_id, Document.patient_id == patient.id)
        )
        or 0,
        'leads': db.scalar(
            select(func.count()).select_from(Lead).where(Lead.tenant_id == tenant_id, Lead.patient_id == patient.id)
        )
        or 0,
    }

    patient.archived_at = now
    patient.inactive_since = now
    patient.status = 'inativo'
    patient.normalized_phone = f'archived-{patient.id}'
    patient.normalized_cpf = None
    db.add(patient)
    db.commit()

    record_audit(
        db,
        action='patient.delete',
        entity_type='patient',
        entity_id=str(patient.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata=linked_summary,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch('/{patient_id}', response_model=PatientOutput)
def update_patient(
    patient_id: str,
    payload: PatientUpdate,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    patient = db.scalar(select(Patient).where(Patient.id == patient_id, Patient.tenant_id == tenant_id))
    if not patient:
        raise ApiError(status_code=404, code='PATIENT_NOT_FOUND', message='Paciente nao encontrado')

    updates = payload.model_dump(exclude_unset=True)
    tags = updates.pop('tags', None)
    if 'phone' in updates:
        normalized_phone = normalize_phone(updates.get('phone'))
        if not normalized_phone:
            raise ApiError(status_code=400, code='PATIENT_PHONE_INVALID', message='Telefone invalido')
        existing_phone = db.scalar(
            select(Patient).where(
                Patient.tenant_id == tenant_id,
                Patient.normalized_phone == normalized_phone,
                Patient.id != patient.id,
            )
        )
        if existing_phone:
            raise ApiError(status_code=409, code='PATIENT_DUPLICATE_PHONE', message='Telefone ja cadastrado no tenant')
        updates['normalized_phone'] = normalized_phone
    if 'cpf' in updates:
        normalized_cpf = normalize_cpf(updates.get('cpf'))
        if normalized_cpf:
            existing_cpf = db.scalar(
                select(Patient).where(
                    Patient.tenant_id == tenant_id,
                    Patient.normalized_cpf == normalized_cpf,
                    Patient.id != patient.id,
                )
            )
            if existing_cpf:
                raise ApiError(status_code=409, code='PATIENT_DUPLICATE_CPF', message='CPF ja cadastrado no tenant')
            updates['normalized_cpf'] = normalized_cpf
        else:
            updates['cpf'] = None
            updates['normalized_cpf'] = None

    for key, value in updates.items():
        setattr(patient, key, value)

    if tags is not None:
        patient.tags_cache = tags
        current_tags = db.execute(
            select(PatientTag).where(PatientTag.tenant_id == tenant_id, PatientTag.patient_id == patient.id)
        ).scalars().all()
        for item in current_tags:
            db.delete(item)
        for tag in tags:
            db.add(PatientTag(tenant_id=tenant_id, patient_id=patient.id, tag=tag))

    db.add(patient)
    db.commit()
    db.refresh(patient)

    record_audit(
        db,
        action='patient.update',
        entity_type='patient',
        entity_id=str(patient.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata=updates,
    )

    return PatientOutput.model_validate(patient, from_attributes=True)


@router.post('/import/csv', response_model=PatientCsvImportOutput)
def import_patients_csv(
    payload: PatientCsvImportInput,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    csv_text = payload.csv_content.strip()
    if not csv_text:
        raise ApiError(status_code=400, code='CSV_EMPTY', message='CSV vazio')

    reader = csv.DictReader(StringIO(csv_text))
    if not reader.fieldnames:
        raise ApiError(status_code=400, code='CSV_INVALID', message='Cabecalho CSV invalido')

    units = db.execute(select(Unit).where(Unit.tenant_id == tenant_id)).scalars().all()
    unit_by_code = {item.code.lower(): item.id for item in units}

    processed = 0
    created = 0
    skipped = 0
    errors = []

    for line_number, row in enumerate(reader, start=2):
        processed += 1
        full_name = (row.get('full_name') or row.get('name') or '').strip()
        phone = (row.get('phone') or '').strip()
        email = (row.get('email') or '').strip() or None
        status = (row.get('status') or 'ativo').strip() or 'ativo'
        origin = (row.get('origin') or 'importacao_csv').strip()
        tags = [item.strip() for item in (row.get('tags') or '').split(',') if item.strip()]
        unit_code = (row.get('unit_code') or '').strip().lower()
        lgpd_consent = _parse_bool(row.get('lgpd_consent'))
        marketing_opt_in = _parse_bool(row.get('marketing_opt_in'))

        if not full_name or not phone:
            errors.append({'line': line_number, 'message': 'Campos obrigatorios: full_name e phone'})
            continue

        try:
            normalized_phone = normalize_phone(phone)
        except ApiError:
            errors.append({'line': line_number, 'message': 'Telefone invalido'})
            continue

        already_exists = db.scalar(
            select(Patient).where(Patient.tenant_id == tenant_id, Patient.normalized_phone == normalized_phone)
        )
        if already_exists:
            skipped += 1
            continue

        unit_id = unit_by_code.get(unit_code) if unit_code else None
        if unit_code and not unit_id:
            errors.append({'line': line_number, 'message': f'unit_code nao encontrado: {unit_code}'})
            continue

        if payload.dry_run:
            created += 1
            continue

        patient = Patient(
            tenant_id=tenant_id,
            unit_id=unit_id,
            full_name=full_name,
            phone=phone,
            normalized_phone=normalized_phone,
            email=email,
            status=status,
            origin=origin,
            tags_cache=tags,
            lgpd_consent=lgpd_consent,
            marketing_opt_in=marketing_opt_in,
        )
        db.add(patient)
        db.flush()
        for tag in tags:
            db.add(PatientTag(tenant_id=tenant_id, patient_id=patient.id, tag=tag))
        created += 1

    if not payload.dry_run:
        setting = db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == 'onboarding.import_done'))
        if not setting:
            setting = Setting(
                tenant_id=tenant_id,
                key='onboarding.import_done',
                value={'at': datetime.now(UTC).isoformat(), 'source': 'patients_csv'},
                is_secret=False,
            )
        else:
            setting.value = {'at': datetime.now(UTC).isoformat(), 'source': 'patients_csv'}
        db.add(setting)
        db.commit()

    record_audit(
        db,
        action='patient.import.csv',
        entity_type='patient',
        entity_id=None,
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={
            'dry_run': payload.dry_run,
            'processed': processed,
            'created': created,
            'skipped': skipped,
            'errors': len(errors),
        },
    )

    return PatientCsvImportOutput(
        dry_run=payload.dry_run,
        processed=processed,
        created=created,
        skipped=skipped,
        errors=errors,
    )

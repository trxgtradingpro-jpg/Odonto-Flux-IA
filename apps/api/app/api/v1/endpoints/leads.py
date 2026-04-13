from datetime import UTC, datetime
import csv
from io import StringIO

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.models import Lead, Setting, User
from app.schemas.lead import LeadCreate, LeadCsvImportInput, LeadCsvImportOutput, LeadOutput, LeadUpdate
from app.services.audit_service import record_audit

router = APIRouter(prefix='/leads', tags=['leads'])

VALID_STAGES = {'novo', 'qualificado', 'em_contato', 'orcamento_enviado', 'agendado', 'perdido'}
VALID_TEMPERATURES = {'frio', 'morno', 'quente'}


@router.get('')
def list_leads(
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    limit: int = Query(default=20, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    stage: str | None = None,
    temperature: str | None = None,
):
    stmt = select(Lead).where(Lead.tenant_id == tenant_id)
    if stage:
        stmt = stmt.where(Lead.stage == stage)
    if temperature:
        stmt = stmt.where(Lead.temperature == temperature)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Lead.created_at.desc()).offset(offset).limit(limit)).scalars().all()

    return {'data': [LeadOutput.model_validate(item, from_attributes=True).model_dump() for item in rows], 'meta': {'total': total, 'limit': limit, 'offset': offset}}


@router.post('', response_model=LeadOutput)
def create_lead(
    payload: LeadCreate,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    lead = Lead(tenant_id=tenant_id, **payload.model_dump())
    db.add(lead)
    db.commit()
    db.refresh(lead)

    record_audit(
        db,
        action='lead.create',
        entity_type='lead',
        entity_id=str(lead.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'origin': lead.origin, 'stage': lead.stage},
    )

    return LeadOutput.model_validate(lead, from_attributes=True)


@router.patch('/{lead_id}', response_model=LeadOutput)
def update_lead(
    lead_id: str,
    payload: LeadUpdate,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    lead = db.scalar(select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id))
    if not lead:
        raise ApiError(status_code=404, code='LEAD_NOT_FOUND', message='Lead nao encontrado')

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(lead, key, value)

    # Marca conversão quando o lead passa a ter paciente vinculado.
    if updates.get('patient_id'):
        lead.converted_at = lead.converted_at or datetime.now(UTC)

    db.add(lead)
    db.commit()
    db.refresh(lead)

    record_audit(
        db,
        action='lead.update',
        entity_type='lead',
        entity_id=str(lead.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata=updates,
    )

    return LeadOutput.model_validate(lead, from_attributes=True)


@router.post('/import/csv', response_model=LeadCsvImportOutput)
def import_leads_csv(
    payload: LeadCsvImportInput,
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

    users = db.execute(select(User).where(User.tenant_id == tenant_id)).scalars().all()
    user_by_email = {item.email.lower(): item.id for item in users}

    processed = 0
    created = 0
    skipped = 0
    errors = []

    for line_number, row in enumerate(reader, start=2):
        processed += 1
        name = (row.get('name') or row.get('full_name') or '').strip()
        phone = (row.get('phone') or '').strip() or None
        email = (row.get('email') or '').strip() or None
        origin = (row.get('origin') or 'importacao_csv').strip()
        interest = (row.get('interest') or '').strip() or None
        stage = (row.get('stage') or 'novo').strip()
        temperature = (row.get('temperature') or 'morno').strip()
        score_text = (row.get('score') or '').strip()
        score = int(score_text) if score_text.isdigit() else 50
        status = (row.get('status') or 'ativo').strip() or 'ativo'
        owner_email = (row.get('owner_email') or '').strip().lower()
        owner_user_id = user_by_email.get(owner_email) if owner_email else None

        if not name:
            errors.append({'line': line_number, 'message': 'Campo obrigatorio: name'})
            continue
        if stage not in VALID_STAGES:
            errors.append({'line': line_number, 'message': f'Etapa invalida: {stage}'})
            continue
        if temperature not in VALID_TEMPERATURES:
            errors.append({'line': line_number, 'message': f'Temperatura invalida: {temperature}'})
            continue
        if owner_email and not owner_user_id:
            errors.append({'line': line_number, 'message': f'owner_email nao encontrado: {owner_email}'})
            continue

        duplicate = db.scalar(
            select(Lead).where(
                Lead.tenant_id == tenant_id,
                Lead.name == name,
                Lead.phone == phone,
                Lead.email == email,
            )
        )
        if duplicate:
            skipped += 1
            continue

        if payload.dry_run:
            created += 1
            continue

        lead = Lead(
            tenant_id=tenant_id,
            name=name,
            phone=phone,
            email=email,
            origin=origin,
            interest=interest,
            stage=stage,
            temperature=temperature,
            score=score,
            status=status,
            owner_user_id=owner_user_id,
        )
        db.add(lead)
        db.flush()
        created += 1

    if not payload.dry_run:
        setting = db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == 'onboarding.import_done'))
        if not setting:
            setting = Setting(
                tenant_id=tenant_id,
                key='onboarding.import_done',
                value={'at': datetime.now(UTC).isoformat(), 'source': 'leads_csv'},
                is_secret=False,
            )
        else:
            setting.value = {'at': datetime.now(UTC).isoformat(), 'source': 'leads_csv'}
        db.add(setting)
        db.commit()

    record_audit(
        db,
        action='lead.import.csv',
        entity_type='lead',
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

    return LeadCsvImportOutput(
        dry_run=payload.dry_run,
        processed=processed,
        created=created,
        skipped=skipped,
        errors=errors,
    )

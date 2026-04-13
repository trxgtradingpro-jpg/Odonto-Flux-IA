from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.models import Job, Lead, Patient, Setting
from app.services.audit_service import record_audit

router = APIRouter(prefix='/privacy', tags=['privacy'])


class PrivacyTermsInput(BaseModel):
    terms_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)


class PrivacyExportInput(BaseModel):
    scope: str = Field(default='tenant')
    requested_by_email: str | None = None


class PrivacyAnonymizeInput(BaseModel):
    patient_id: str
    reason: str = Field(min_length=5)


def _upsert_setting(db: Session, tenant_id, key: str, value: dict):
    item = db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == key))
    if not item:
        item = Setting(tenant_id=tenant_id, key=key, value=value, is_secret=False)
    else:
        item.value = value
    db.add(item)
    db.flush()
    return item


@router.get('/summary')
def summary(db: Session = Depends(get_db), tenant_id=Depends(get_tenant_id)):
    settings = db.execute(select(Setting).where(Setting.tenant_id == tenant_id)).scalars().all()
    settings_by_key = {item.key: item.value for item in settings}

    total_patients = db.scalar(select(func.count(Patient.id)).where(Patient.tenant_id == tenant_id)) or 0
    consented_patients = db.scalar(
        select(func.count(Patient.id)).where(Patient.tenant_id == tenant_id, Patient.lgpd_consent.is_(True))
    ) or 0

    return {
        'consent_rate': round((consented_patients / total_patients) * 100, 2) if total_patients else 0,
        'retention_days': settings_by_key.get('privacy.retention_days', {}).get('value', 365)
        if isinstance(settings_by_key.get('privacy.retention_days'), dict)
        else 365,
        'communication_allowed': settings_by_key.get(
            'privacy.communication_allowed',
            {'marketing': True, 'operacional': True},
        ),
        'terms_version': settings_by_key.get('privacy.terms_version', {}).get('value')
        if isinstance(settings_by_key.get('privacy.terms_version'), dict)
        else None,
        'policy_version': settings_by_key.get('privacy.policy_version', {}).get('value')
        if isinstance(settings_by_key.get('privacy.policy_version'), dict)
        else None,
        'accepted_at': settings_by_key.get('privacy.accepted_at', {}).get('value')
        if isinstance(settings_by_key.get('privacy.accepted_at'), dict)
        else None,
    }


@router.post('/terms/accept')
def accept_terms(
    payload: PrivacyTermsInput,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    now_iso = datetime.now(UTC).isoformat()
    _upsert_setting(db, tenant_id, 'privacy.terms_version', {'value': payload.terms_version})
    _upsert_setting(db, tenant_id, 'privacy.policy_version', {'value': payload.policy_version})
    accepted_setting = _upsert_setting(db, tenant_id, 'privacy.accepted_at', {'value': now_iso})
    db.commit()
    db.refresh(accepted_setting)

    record_audit(
        db,
        action='privacy.terms.accept',
        entity_type='setting',
        entity_id=str(accepted_setting.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'terms_version': payload.terms_version, 'policy_version': payload.policy_version},
    )
    return {'message': 'Termos aceitos com sucesso', 'accepted_at': now_iso}


@router.post('/export')
def export_data(
    payload: PrivacyExportInput,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    patients_total = db.scalar(select(func.count(Patient.id)).where(Patient.tenant_id == tenant_id)) or 0
    leads_total = db.scalar(select(func.count(Lead.id)).where(Lead.tenant_id == tenant_id)) or 0

    job = Job(
        tenant_id=tenant_id,
        job_type='privacy_export',
        status='success',
        payload={
            'scope': payload.scope,
            'requested_by_email': payload.requested_by_email or principal.user.email,
        },
        result={
            'patients_total': patients_total,
            'leads_total': leads_total,
            'generated_at': datetime.now(UTC).isoformat(),
            'download_hint': 'Exportacao gerada no ambiente demo.',
        },
        scheduled_for=datetime.now(UTC),
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    record_audit(
        db,
        action='privacy.export.request',
        entity_type='job',
        entity_id=str(job.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'scope': payload.scope},
    )
    return {'job_id': str(job.id), 'status': job.status, 'result': job.result}


@router.post('/anonymize')
def anonymize_patient(
    payload: PrivacyAnonymizeInput,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    patient = db.scalar(select(Patient).where(Patient.id == payload.patient_id, Patient.tenant_id == tenant_id))
    if not patient:
        raise ApiError(status_code=404, code='PATIENT_NOT_FOUND', message='Paciente nao encontrado')

    anon_suffix = str(patient.id).split('-')[0]
    patient.full_name = f'Paciente anonimizado {anon_suffix}'
    patient.email = None
    patient.phone = f'anon-{anon_suffix}'
    patient.normalized_phone = f'anon-{anon_suffix}'
    patient.operational_notes = f'Registro anonimizado em {datetime.now(UTC).isoformat()}'
    patient.marketing_opt_in = False
    patient.lgpd_consent = False
    patient.tags_cache = ['anonimizado']
    db.add(patient)

    related_leads = db.execute(select(Lead).where(Lead.tenant_id == tenant_id, Lead.patient_id == patient.id)).scalars().all()
    for lead in related_leads:
        lead.name = f'Lead anonimizado {anon_suffix}'
        lead.email = None
        lead.phone = None
        lead.notes = 'Registro anonimizado por solicitacao LGPD.'
        db.add(lead)

    db.commit()
    db.refresh(patient)

    record_audit(
        db,
        action='privacy.patient.anonymize',
        entity_type='patient',
        entity_id=str(patient.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'reason': payload.reason, 'related_leads': len(related_leads)},
    )

    return {'message': 'Paciente anonimizado com sucesso', 'patient_id': str(patient.id)}

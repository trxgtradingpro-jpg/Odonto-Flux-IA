from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.models import Job
from app.services.audit_service import record_audit

router = APIRouter(prefix='/support', tags=['support'])

SLA_HOURS = {
    'critica': 1,
    'alta': 4,
    'media': 8,
    'baixa': 24,
}


class SupportIncidentInput(BaseModel):
    title: str = Field(min_length=5)
    severity: str = Field(default='media')
    description: str = Field(min_length=8)
    contact_email: str | None = None


@router.get('/overview')
def overview(db: Session = Depends(get_db), tenant_id=Depends(get_tenant_id)):
    incidents = db.execute(
        select(Job)
        .where(Job.tenant_id == tenant_id, Job.job_type == 'support_incident')
        .order_by(Job.created_at.desc())
        .limit(100)
    ).scalars().all()
    open_incidents = [item for item in incidents if item.status in {'pending', 'running'}]

    return {
        'channels': [
            {'name': 'WhatsApp suporte', 'contact': '+55 11 95555-0101', 'availability': 'Seg-Sex 08:00-18:00'},
            {'name': 'E-mail suporte', 'contact': 'suporte@odontoflux.com', 'availability': '24x7 recebimento'},
        ],
        'sla_hours': SLA_HOURS,
        'open_incidents': len(open_incidents),
        'last_incident_at': incidents[0].created_at.isoformat() if incidents else None,
    }


@router.get('/incidents')
def list_incidents(
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    rows = db.execute(
        select(Job)
        .where(Job.tenant_id == tenant_id, Job.job_type == 'support_incident')
        .order_by(Job.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).scalars().all()

    data = []
    for item in rows:
        payload = item.payload or {}
        result = item.result or {}
        data.append(
            {
                'id': str(item.id),
                'title': payload.get('title'),
                'severity': payload.get('severity', 'media'),
                'description': payload.get('description'),
                'contact_email': payload.get('contact_email'),
                'status': item.status,
                'sla_deadline_at': payload.get('sla_deadline_at'),
                'resolution_notes': result.get('resolution_notes'),
                'created_at': item.created_at.isoformat(),
                'finished_at': item.finished_at.isoformat() if item.finished_at else None,
            }
        )
    return {'data': data, 'meta': {'limit': limit, 'offset': offset, 'total': len(data)}}


@router.post('/incidents')
def create_incident(
    payload: SupportIncidentInput,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    severity = payload.severity.lower()
    if severity not in SLA_HOURS:
        raise ApiError(status_code=400, code='SUPPORT_SEVERITY_INVALID', message='Severidade invalida')

    created_at = datetime.now(UTC)
    deadline = created_at + timedelta(hours=SLA_HOURS[severity])

    item = Job(
        tenant_id=tenant_id,
        job_type='support_incident',
        status='pending',
        payload={
            'title': payload.title,
            'severity': severity,
            'description': payload.description,
            'contact_email': payload.contact_email or principal.user.email,
            'created_by': principal.user.email,
            'sla_deadline_at': deadline.isoformat(),
        },
        result={},
        scheduled_for=created_at,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    record_audit(
        db,
        action='support.incident.create',
        entity_type='job',
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'severity': severity, 'title': payload.title},
    )

    return {
        'id': str(item.id),
        'status': item.status,
        'severity': severity,
        'sla_deadline_at': deadline.isoformat(),
    }


@router.post('/incidents/{incident_id}/resolve')
def resolve_incident(
    incident_id: str,
    notes: str = '',
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    incident = db.scalar(
        select(Job).where(Job.id == incident_id, Job.tenant_id == tenant_id, Job.job_type == 'support_incident')
    )
    if not incident:
        raise ApiError(status_code=404, code='SUPPORT_INCIDENT_NOT_FOUND', message='Incidente nao encontrado')

    incident.status = 'success'
    incident.finished_at = datetime.now(UTC)
    incident.result = {'resolution_notes': notes or 'Resolucao registrada pela equipe.'}
    db.add(incident)
    db.commit()
    db.refresh(incident)

    record_audit(
        db,
        action='support.incident.resolve',
        entity_type='job',
        entity_id=str(incident.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'notes': notes},
    )
    return {'id': str(incident.id), 'status': incident.status}


@router.get('/playbook')
def playbook():
    return {
        'steps': [
            '1) Classificar severidade e impacto em ate 15 minutos.',
            '2) Acionar canal oficial de comunicacao com o cliente.',
            '3) Definir dono tecnico e registrar timeline do incidente.',
            '4) Aplicar mitigacao e validar estabilizacao.',
            '5) Publicar post-mortem com causa raiz e plano de prevencao.',
        ],
        'targets': {
            'time_to_ack_minutes': 15,
            'time_to_first_update_minutes': 30,
            'time_to_postmortem_hours': 24,
        },
    }

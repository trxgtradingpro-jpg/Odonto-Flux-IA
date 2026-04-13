from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.models import Campaign, CampaignAudience, CampaignMessage, Conversation, Patient
from app.schemas.campaign import CampaignCreate, CampaignOutput, CampaignUpdate
from app.services.audit_service import record_audit
from app.services.whatsapp_service import assert_whatsapp_account_ready_for_dispatch, queue_outbound_message

router = APIRouter(prefix='/campaigns', tags=['campaigns'])


@router.get('')
def list_campaigns(
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    limit: int = Query(default=20, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(Campaign).where(Campaign.tenant_id == tenant_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Campaign.created_at.desc()).offset(offset).limit(limit)).scalars().all()
    return {'data': [CampaignOutput.model_validate(item, from_attributes=True).model_dump() for item in rows], 'meta': {'total': total, 'limit': limit, 'offset': offset}}


@router.post('', response_model=CampaignOutput)
def create_campaign(
    payload: CampaignCreate,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    item = Campaign(
        tenant_id=tenant_id,
        created_by_user_id=principal.user.id,
        **payload.model_dump(),
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    record_audit(
        db,
        action='campaign.create',
        entity_type='campaign',
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'status': item.status},
    )
    return CampaignOutput.model_validate(item, from_attributes=True)


@router.patch('/{campaign_id}', response_model=CampaignOutput)
def update_campaign(
    campaign_id: str,
    payload: CampaignUpdate,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    item = db.scalar(select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id))
    if not item:
        raise ApiError(status_code=404, code='CAMPAIGN_NOT_FOUND', message='Campanha nao encontrada')

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(item, key, value)

    db.add(item)
    db.commit()
    db.refresh(item)

    record_audit(
        db,
        action='campaign.update',
        entity_type='campaign',
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata=updates,
    )
    return CampaignOutput.model_validate(item, from_attributes=True)


@router.post('/{campaign_id}/start')
def start_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    campaign = db.scalar(select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id))
    if not campaign:
        raise ApiError(status_code=404, code='CAMPAIGN_NOT_FOUND', message='Campanha nao encontrada')

    assert_whatsapp_account_ready_for_dispatch(db, tenant_id=tenant_id)

    patients = db.execute(
        select(Patient)
        .where(Patient.tenant_id == tenant_id, Patient.marketing_opt_in.is_(True), Patient.archived_at.is_(None))
        .limit(200)
    ).scalars().all()

    campaign.status = 'em_execucao'
    campaign.started_at = datetime.now(UTC)
    db.add(campaign)
    db.flush()

    queued = 0
    for patient in patients:
        conversation = db.scalar(
            select(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.patient_id == patient.id,
                Conversation.channel == 'whatsapp',
                Conversation.status.in_(['aberta', 'aguardando']),
            )
        )
        if not conversation:
            conversation = Conversation(
                tenant_id=tenant_id,
                patient_id=patient.id,
                channel='whatsapp',
                status='aberta',
                assigned_user_id=principal.user.id,
                tags=['campanha'],
            )
            db.add(conversation)
            db.flush()

        audience = CampaignAudience(
            tenant_id=tenant_id,
            campaign_id=campaign.id,
            patient_id=patient.id,
            status='pending',
            tags=['reactivacao'],
        )
        db.add(audience)
        db.flush()

        queue_outbound_message(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            to=patient.phone,
            body=f'Oi {patient.full_name.split()[0]}, estamos com agenda aberta. Quer retomar seu atendimento?',
            message_type='text',
            metadata={'source': 'campaign', 'campaign_id': str(campaign.id)},
        )

        db.add(
            CampaignMessage(
                tenant_id=tenant_id,
                campaign_id=campaign.id,
                campaign_audience_id=audience.id,
                status='queued',
            )
        )
        queued += 1

    db.commit()

    record_audit(
        db,
        action='campaign.start',
        entity_type='campaign',
        entity_id=str(campaign.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'queued_messages': queued},
    )

    return {'message': 'Campanha iniciada', 'audience_count': len(patients), 'queued_messages': queued}

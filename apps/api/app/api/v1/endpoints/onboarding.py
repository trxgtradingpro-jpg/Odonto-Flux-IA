from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.db.session import get_db
from app.models import Setting
from app.services.audit_service import record_audit
from app.services.onboarding_service import onboarding_status

router = APIRouter(prefix='/onboarding', tags=['onboarding'])


class OnboardingStepInput(BaseModel):
    step_id: str


@router.get('/status')
def status(db: Session = Depends(get_db), tenant_id=Depends(get_tenant_id)):
    return onboarding_status(db, tenant_id)


@router.post('/complete')
def complete_step(
    payload: OnboardingStepInput,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    setting = db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == 'onboarding.completed_steps'))
    completed_steps = []
    if setting and isinstance(setting.value, dict):
        completed_steps = list(setting.value.get('steps', []))

    if payload.step_id not in completed_steps:
        completed_steps.append(payload.step_id)

    if not setting:
        setting = Setting(
            tenant_id=tenant_id,
            key='onboarding.completed_steps',
            value={'steps': completed_steps, 'updated_at': datetime.now(UTC).isoformat()},
            is_secret=False,
        )
    else:
        setting.value = {'steps': completed_steps, 'updated_at': datetime.now(UTC).isoformat()}

    db.add(setting)
    db.commit()
    db.refresh(setting)

    record_audit(
        db,
        action='onboarding.step.complete',
        entity_type='setting',
        entity_id=str(setting.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'step_id': payload.step_id},
    )

    return {'message': 'Etapa marcada como concluida', 'step_id': payload.step_id}

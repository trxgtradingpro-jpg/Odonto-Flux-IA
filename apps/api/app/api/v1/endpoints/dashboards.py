from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.api.unit_scope import get_effective_unit_id
from app.db.session import get_db
from app.schemas.dashboard import DashboardKPIOutput
from app.services.dashboard_service import get_dashboard_snapshot

router = APIRouter(prefix='/dashboards', tags=['dashboards'])


@router.get('/kpis', response_model=DashboardKPIOutput)
def kpis(
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
    unit_id: UUID | None = Query(default=None),
):
    effective_unit_id = get_effective_unit_id(
        db,
        principal=principal,
        tenant_id=tenant_id,
        requested_unit_id=unit_id,
    )
    return DashboardKPIOutput(**get_dashboard_snapshot(db, tenant_id, unit_id=effective_unit_id))

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id
from app.db.session import get_db
from app.schemas.dashboard import DashboardKPIOutput
from app.services.dashboard_service import get_dashboard_snapshot

router = APIRouter(prefix='/dashboards', tags=['dashboards'])


@router.get('/kpis', response_model=DashboardKPIOutput)
def kpis(db: Session = Depends(get_db), tenant_id=Depends(get_tenant_id)):
    return DashboardKPIOutput(**get_dashboard_snapshot(db, tenant_id))

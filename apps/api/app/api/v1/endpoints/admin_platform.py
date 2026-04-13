from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.db.session import get_db
from app.services.dashboard_service import global_admin_metrics, global_admin_overview
from app.services.monitoring_service import monitoring_snapshot

router = APIRouter(prefix='/admin/platform', tags=['admin_platform'])


@router.get('/metrics', dependencies=[Depends(require_roles('admin_platform'))])
def metrics(db: Session = Depends(get_db)):
    return global_admin_metrics(db)


@router.get('/health', dependencies=[Depends(require_roles('admin_platform'))])
def admin_health(db: Session = Depends(get_db)):
    snapshot = monitoring_snapshot(db)
    database_status = snapshot['services']['database']['status']
    redis_status = snapshot['services']['redis']['status']
    overall = 'ok' if database_status == 'up' and redis_status == 'up' else 'degraded'

    return {
        'status': overall,
        'services': {
            'api': 'up',
            'database': database_status,
            'redis': redis_status,
        },
        'uptime_seconds': snapshot['uptime_seconds'],
        'failed_jobs_last_hour': snapshot['errors']['failed_jobs_last_hour'],
        'alerts': snapshot['alerts'],
    }


@router.get('/overview', dependencies=[Depends(require_roles('admin_platform'))])
def overview(db: Session = Depends(get_db)):
    return global_admin_overview(db)


@router.get('/monitoring', dependencies=[Depends(require_roles('admin_platform'))])
def monitoring(db: Session = Depends(get_db)):
    return monitoring_snapshot(db)

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.services.reporting_service import monthly_report, monthly_report_csv_payload

router = APIRouter(prefix='/reports', tags=['reports'])


def _parse_reference_month(month: str | None) -> datetime:
    if not month:
        return datetime.now(UTC)
    try:
        parsed = datetime.strptime(month, '%Y-%m')
    except ValueError as exc:
        raise ApiError(status_code=400, code='REPORT_MONTH_INVALID', message='Mes invalido. Use YYYY-MM.') from exc
    return datetime(parsed.year, parsed.month, 1, tzinfo=UTC)


@router.get('/monthly')
def monthly(
    month: str | None = Query(default=None, description='Formato YYYY-MM'),
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
):
    reference = _parse_reference_month(month)
    return monthly_report(db, tenant_id, reference)


@router.get('/monthly/csv', response_class=PlainTextResponse)
def monthly_csv(
    month: str | None = Query(default=None, description='Formato YYYY-MM'),
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
):
    reference = _parse_reference_month(month)
    report = monthly_report(db, tenant_id, reference)
    return monthly_report_csv_payload(report)

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.admin_sales import PublicSiteQuickDemoInput, PublicSiteQuickDemoOutput
from app.services import sales_demo_service as sales

router = APIRouter(prefix="/public/site", tags=["public_site"])


def _base_url(request: Request) -> str:
    origin = str(request.headers.get("origin") or "").strip()
    if origin:
        return origin.rstrip("/")
    return str(request.base_url).rstrip("/")


@router.post("/quick-demo", response_model=PublicSiteQuickDemoOutput)
def create_public_site_quick_demo(
    payload: PublicSiteQuickDemoInput,
    request: Request,
    db: Session = Depends(get_db),
):
    result = sales.create_or_reuse_public_site_demo(
        db,
        clinic_name=payload.clinic_name,
        owner_name=payload.owner_name,
        phone=payload.phone,
        template_slug=payload.template_slug,
        base_url=_base_url(request),
    )
    return {
        "prospect": sales.serialize_prospect(db, result["prospect"]),
        "status": result["status"],
        "demo_login_url": result["demo_login_url"],
        "demo_booking_path": result["demo_booking_path"],
        "demo_booking_url": result["demo_booking_url"],
        "selected_template_slug": result.get("selected_template_slug"),
        "site_template_preview_url": result.get("site_template_preview_url"),
    }

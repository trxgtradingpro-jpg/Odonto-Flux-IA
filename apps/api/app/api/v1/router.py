from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin_platform,
    appointments,
    audit,
    auth,
    automations,
    billing,
    campaigns,
    conversations,
    dashboards,
    documents,
    leads,
    messages,
    onboarding,
    operations,
    patients,
    privacy,
    professionals,
    reports,
    settings,
    support,
    tenants,
    units,
    users,
    webhooks_whatsapp,
)

api_router = APIRouter(prefix='/api/v1')

api_router.include_router(auth.router)
api_router.include_router(tenants.router)
api_router.include_router(units.router)
api_router.include_router(users.router)
api_router.include_router(patients.router)
api_router.include_router(professionals.router)
api_router.include_router(leads.router)
api_router.include_router(conversations.router)
api_router.include_router(messages.router)
api_router.include_router(appointments.router)
api_router.include_router(automations.router)
api_router.include_router(campaigns.router)
api_router.include_router(documents.router)
api_router.include_router(settings.router)
api_router.include_router(onboarding.router)
api_router.include_router(operations.router)
api_router.include_router(billing.router)
api_router.include_router(privacy.router)
api_router.include_router(reports.router)
api_router.include_router(support.router)
api_router.include_router(dashboards.router)
api_router.include_router(audit.router)
api_router.include_router(webhooks_whatsapp.router)
api_router.include_router(admin_platform.router)

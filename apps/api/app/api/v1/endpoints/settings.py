from datetime import UTC, datetime
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.integrations.whatsapp.cloud_api import WhatsAppCloudProvider
from app.integrations.whatsapp.infobip import InfobipWhatsAppProvider
from app.integrations.whatsapp.twilio import TwilioWhatsAppProvider
from app.models import OutboxMessage, Setting, WhatsAppAccount, WhatsAppTemplate
from app.models.enums import OutboxStatus
from app.models import Unit
from app.services.ai_autoresponder_service import (
    get_knowledge_base_global_config as get_ai_knowledge_base_global_config,
    get_global_config as get_ai_autoresponder_global_config,
    set_knowledge_base_global_config as set_ai_knowledge_base_global_config,
    list_unit_overrides as list_ai_autoresponder_unit_overrides,
    set_global_config as set_ai_autoresponder_global_config,
    set_unit_override as set_ai_autoresponder_unit_override,
)
from app.services.audit_service import record_audit
from app.services.appointment_validation_service import (
    sync_future_appointments_with_service_catalog,
)
from app.services.link_flow_service import (
    IntakeConfigInput,
    get_intake_config,
    get_system_whatsapp_account,
    is_link_flow_enabled,
    upsert_intake_config,
)
from app.services.service_catalog_service import get_service_catalog_items, set_service_catalog_items
from app.services.whatsapp_service import normalize_whatsapp_provider_name, whatsapp_account_issues

router = APIRouter(prefix='/settings', tags=['settings'])


class BrandingThemeInput(BaseModel):
    primary_color: str = Field(default="#0f766e")
    secondary_color: str = Field(default="#0ea5a4")
    accent_color: str = Field(default="#f59e0b")
    background_color: str = Field(default="#f2f4f7")
    surface_color: str = Field(default="#eef2f6")
    card_color: str = Field(default="#ffffff")
    text_color: str = Field(default="#1c1917")
    muted_text_color: str = Field(default="#475569")
    border_color: str = Field(default="#d6d3d1")
    fullscreen_background_color: str = Field(default="#0c0a09")
    fullscreen_header_color: str = Field(default="#111111")
    fullscreen_accent_color: str = Field(default="#10b981")
    fullscreen_foreground_color: str = Field(default="#ffffff")
    surface_style: str = Field(default="soft")
    logo_data_url: str | None = None
    demo_background_image_url: str | None = Field(default="/images/dental-floss-smile-background.png")
    demo_background_opacity: float = Field(default=0.18, ge=0.0, le=1.0)
    demo_ai_test_button_enabled: bool = Field(default=True)

    @field_validator(
        "primary_color",
        "secondary_color",
        "accent_color",
        "background_color",
        "surface_color",
        "card_color",
        "text_color",
        "muted_text_color",
        "border_color",
        "fullscreen_background_color",
        "fullscreen_header_color",
        "fullscreen_accent_color",
        "fullscreen_foreground_color",
    )
    @classmethod
    def _validate_hex(cls, value: str) -> str:
        if not isinstance(value, str) or not value.startswith("#") or len(value) != 7:
            raise ValueError("Cor precisa estar em formato hexadecimal #RRGGBB")
        int(value[1:], 16)
        return value.lower()

    @field_validator("surface_style")
    @classmethod
    def _validate_surface_style(cls, value: str) -> str:
        return value if value in {"soft", "flat", "glass"} else "soft"


def _upsert_setting_record(db: Session, *, tenant_id, key: str, value, is_secret: bool = False) -> Setting:
    item = db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == key))
    if not item:
        item = Setting(tenant_id=tenant_id, key=key, value=value, is_secret=is_secret)
    else:
        item.value = value
        item.is_secret = is_secret
    db.add(item)
    return item


def _active_whatsapp_account_for_tenant(db: Session, *, tenant_id) -> WhatsAppAccount | None:
    return db.scalar(
        select(WhatsAppAccount)
        .where(
            WhatsAppAccount.tenant_id == tenant_id,
            WhatsAppAccount.is_active.is_(True),
        )
        .order_by(WhatsAppAccount.created_at.desc())
        .limit(1)
    )


def _whatsapp_account_readiness(account: WhatsAppAccount | None) -> dict:
    if not account:
        return {
            "configured": False,
            "healthy": False,
            "provider_name": None,
            "display_phone": None,
            "issues": ["Conta WhatsApp ativa nao configurada."],
        }
    issues = whatsapp_account_issues(
        provider_name=account.provider_name,
        phone_number_id=account.phone_number_id,
        business_account_id=account.business_account_id,
        access_token=account.access_token_encrypted,
    )
    return {
        "configured": True,
        "healthy": not issues,
        "provider_name": account.provider_name,
        "display_phone": account.display_phone,
        "issues": issues,
    }


def _intake_status_payload(db: Session, *, tenant_id) -> dict:
    config = get_intake_config(db, tenant_id=tenant_id)
    mode = str(config.get("mode") or "official_api")
    link_flow_config = config.get("link_flow") if isinstance(config.get("link_flow"), dict) else {}
    cta_mode = str(link_flow_config.get("cta_mode") or "whatsapp_redirect")
    link_flow_enabled = is_link_flow_enabled(config)
    own_account = _whatsapp_account_readiness(_active_whatsapp_account_for_tenant(db, tenant_id=tenant_id))
    shared_sender = _whatsapp_account_readiness(get_system_whatsapp_account(db))
    link_flow_needs_shared_sender = cta_mode == "whatsapp_redirect"

    mode_requirements = {
        "official_api": {
            "own_whatsapp_account": True,
            "shared_sender": False,
            "link_flow_enabled": False,
        },
        "link_flow": {
            "own_whatsapp_account": False,
            "shared_sender": link_flow_needs_shared_sender,
            "link_flow_enabled": True,
        },
        "hybrid": {
            "own_whatsapp_account": True,
            "shared_sender": link_flow_needs_shared_sender,
            "link_flow_enabled": True,
        },
    }
    requirements = mode_requirements.get(mode, mode_requirements["official_api"])
    issues: list[str] = []
    if requirements["own_whatsapp_account"] and not own_account["healthy"]:
        issues.append("Conta oficial propria da clinica indisponivel.")
    if requirements["shared_sender"] and not shared_sender["healthy"]:
        issues.append("Sender compartilhado do sistema indisponivel.")
    if requirements["link_flow_enabled"] and not link_flow_enabled:
        issues.append("Link Flow desabilitado na configuracao.")

    operational = not issues
    return {
        "config": config,
        "mode": mode,
        "cta_mode": cta_mode,
        "link_flow_enabled": link_flow_enabled,
        "current_mode_operational": operational,
        "readiness": {
            "own_whatsapp_account": own_account,
            "shared_sender": shared_sender,
        },
        "requirements": requirements,
        "issues": issues,
        "message": (
            "Modo de entrada operacional."
            if operational
            else "Modo de entrada com pendencias operacionais."
        ),
    }


@router.get('')
def list_settings(db: Session = Depends(get_db), tenant_id=Depends(get_tenant_id)):
    rows = db.execute(select(Setting).where(Setting.tenant_id == tenant_id)).scalars().all()
    return {'data': [{'id': str(item.id), 'key': item.key, 'value': item.value, 'is_secret': item.is_secret} for item in rows]}


@router.get('/intake/config')
def get_intake_config_endpoint(db: Session = Depends(get_db), tenant_id=Depends(get_tenant_id)):
    return get_intake_config(db, tenant_id=tenant_id)


@router.put('/intake/config')
def upsert_intake_config_endpoint(
    payload: IntakeConfigInput,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    item = upsert_intake_config(
        db,
        tenant_id=tenant_id,
        payload=payload.model_dump(mode="json"),
    )
    db.commit()
    db.refresh(item)
    record_audit(
        db,
        action='settings.intake_config.update',
        entity_type='setting',
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={
            'mode': item.value.get('mode') if isinstance(item.value, dict) else None,
            'link_flow_enabled': bool((item.value.get('link_flow') or {}).get('enabled'))
            if isinstance(item.value, dict)
            else False,
        },
    )
    return get_intake_config(db, tenant_id=tenant_id)


@router.get('/intake/status')
def get_intake_status_endpoint(db: Session = Depends(get_db), tenant_id=Depends(get_tenant_id)):
    return _intake_status_payload(db, tenant_id=tenant_id)


@router.put('/{key}')
def upsert_setting(
    key: str,
    payload: dict,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    item = db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == key))
    if not item:
        item = Setting(tenant_id=tenant_id, key=key, value=payload.get('value', {}), is_secret=payload.get('is_secret', False))
    else:
        item.value = payload.get('value', {})
        item.is_secret = payload.get('is_secret', False)

    db.add(item)
    db.commit()
    db.refresh(item)

    record_audit(
        db,
        action='settings.upsert',
        entity_type='setting',
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'key': key, 'is_secret': item.is_secret},
    )
    return {'id': str(item.id), 'key': item.key, 'value': item.value, 'is_secret': item.is_secret}


@router.put('/branding/theme')
def upsert_branding_theme(
    payload: BrandingThemeInput,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    theme_value = payload.model_dump()
    logo_value = theme_value.get("logo_data_url")

    theme_item = _upsert_setting_record(
        db,
        tenant_id=tenant_id,
        key="branding.theme",
        value=theme_value,
        is_secret=False,
    )
    _upsert_setting_record(
        db,
        tenant_id=tenant_id,
        key="branding.logo_data_url",
        value=logo_value,
        is_secret=False,
    )
    db.commit()
    db.refresh(theme_item)

    record_audit(
        db,
        action='branding.theme.update',
        entity_type='setting',
        entity_id=str(theme_item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={
            'surface_style': theme_value.get('surface_style'),
            'primary_color': theme_value.get('primary_color'),
            'fullscreen_accent_color': theme_value.get('fullscreen_accent_color'),
            'has_logo': bool(logo_value),
        },
    )
    return {'id': str(theme_item.id), 'key': theme_item.key, 'value': theme_item.value, 'is_secret': theme_item.is_secret}


@router.get('/ai-autoresponder/config')
def get_ai_autoresponder_config(db: Session = Depends(get_db), tenant_id=Depends(get_tenant_id)):
    return {
        'global': get_ai_autoresponder_global_config(db, tenant_id=tenant_id),
        'unit_overrides': list_ai_autoresponder_unit_overrides(db, tenant_id=tenant_id),
    }


@router.put('/ai-autoresponder/config')
def upsert_ai_autoresponder_global_config(
    payload: dict,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    config = set_ai_autoresponder_global_config(
        db,
        tenant_id=tenant_id,
        payload=payload,
    )
    record_audit(
        db,
        action='ai_autoresponder.toggle',
        entity_type='setting',
        entity_id=None,
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={
            'scope': 'tenant',
            'enabled': config.get('enabled'),
            'channels': config.get('channels'),
        },
    )
    return config


@router.put('/ai-autoresponder/unit/{unit_id}')
def upsert_ai_autoresponder_unit_config(
    unit_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    try:
        unit_uuid = UUID(unit_id)
    except ValueError as exc:
        raise ApiError(status_code=400, code='UNIT_ID_INVALID', message='ID da unidade invalido') from exc

    unit = db.scalar(select(Unit).where(Unit.id == unit_uuid, Unit.tenant_id == tenant_id))
    if not unit:
        raise ApiError(status_code=404, code='UNIT_NOT_FOUND', message='Unidade nao encontrada')

    config = set_ai_autoresponder_unit_override(
        db,
        tenant_id=tenant_id,
        unit_id=unit_uuid,
        payload=payload,
    )
    record_audit(
        db,
        action='ai_autoresponder.toggle',
        entity_type='setting',
        entity_id=str(unit_uuid),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={
            'scope': 'unit',
            'unit_id': str(unit_uuid),
            'config': config,
        },
    )
    return {'unit_id': str(unit_uuid), 'config': config}


@router.get('/ai-knowledge-base/config')
def get_ai_knowledge_base_config(db: Session = Depends(get_db), tenant_id=Depends(get_tenant_id)):
    return {
        'global': get_ai_knowledge_base_global_config(db, tenant_id=tenant_id),
    }


@router.put('/ai-knowledge-base/config')
def upsert_ai_knowledge_base_config(
    payload: dict,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    config = set_ai_knowledge_base_global_config(
        db,
        tenant_id=tenant_id,
        payload=payload,
    )
    record_audit(
        db,
        action='ai_knowledge_base.update',
        entity_type='setting',
        entity_id=None,
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={
            'sections': sorted(config.keys()),
            'services_count': len(config.get('services') or []),
            'faq_count': len(config.get('faq') or []),
        },
    )
    return config


@router.get('/service-catalog/config')
def get_service_catalog_config(db: Session = Depends(get_db), tenant_id=Depends(get_tenant_id)):
    return {
        'items': get_service_catalog_items(db, tenant_id=tenant_id),
    }


@router.put('/service-catalog/config')
def upsert_service_catalog_config(
    payload: dict,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    items = set_service_catalog_items(
        db,
        tenant_id=tenant_id,
        payload=payload if isinstance(payload, dict) else {"items": []},
    )
    sync_summary = sync_future_appointments_with_service_catalog(
        db,
        tenant_id=tenant_id,
        dry_run=False,
    )
    record_audit(
        db,
        action='service_catalog.update',
        entity_type='setting',
        entity_id=None,
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={
            'items_count': len(items),
            'active_items_count': len([item for item in items if item.get('is_active', True)]),
            'future_end_times_updated': sync_summary.get('backfill', {}).get('updated', 0),
            'future_appointments_rebalanced': sync_summary.get('rebalance', {}).get('totals', {}).get('appointments_moved', 0),
            'future_rebalance_unresolved': sync_summary.get('rebalance', {}).get('totals', {}).get('appointments_unresolved', 0),
        },
    )
    return {'items': items, 'sync_summary': sync_summary}


@router.get('/whatsapp/accounts')
def list_whatsapp_accounts(db: Session = Depends(get_db), tenant_id=Depends(get_tenant_id)):
    rows = db.execute(
        select(WhatsAppAccount).where(WhatsAppAccount.tenant_id == tenant_id).order_by(WhatsAppAccount.created_at.desc())
    ).scalars().all()
    return {
        'data': [
            {
                'id': str(item.id),
                'provider_name': item.provider_name,
                'phone_number_id': item.phone_number_id,
                'business_account_id': item.business_account_id,
                'display_phone': item.display_phone,
                'is_active': item.is_active,
            }
            for item in rows
        ]
    }


@router.get('/whatsapp/health')
def get_whatsapp_health(db: Session = Depends(get_db), tenant_id=Depends(get_tenant_id)):
    active_account = db.scalar(
        select(WhatsAppAccount)
        .where(
            WhatsAppAccount.tenant_id == tenant_id,
            WhatsAppAccount.is_active.is_(True),
        )
        .order_by(WhatsAppAccount.created_at.desc())
        .limit(1)
    )

    account_issues = []
    if not active_account:
        account_issues.append('Conta WhatsApp ativa não configurada')
    else:
        account_issues = whatsapp_account_issues(
            provider_name=active_account.provider_name,
            phone_number_id=active_account.phone_number_id,
            business_account_id=active_account.business_account_id,
            access_token=active_account.access_token_encrypted,
        )

    recent_failure = db.scalar(
        select(OutboxMessage)
        .where(
            OutboxMessage.tenant_id == tenant_id,
            OutboxMessage.channel == 'whatsapp',
            OutboxMessage.status.in_([OutboxStatus.FAILED.value, OutboxStatus.DEAD_LETTER.value]),
        )
        .order_by(OutboxMessage.updated_at.desc(), OutboxMessage.created_at.desc())
        .limit(1)
    )
    recent_error = str(recent_failure.last_error or '') if recent_failure else ''
    normalized_error = recent_error.lower()
    credit_issue = any(marker in normalized_error for marker in ['not enough credits', 'insufficient credit', 'credito', 'crédito'])

    if account_issues or credit_issue:
        status = 'blocked'
    elif recent_failure:
        status = 'warning'
    else:
        status = 'ok'

    return {
        'status': status,
        'active_account': (
            {
                'id': str(active_account.id),
                'provider_name': active_account.provider_name,
                'phone_number_id': active_account.phone_number_id,
                'display_phone': active_account.display_phone,
            }
            if active_account
            else None
        ),
        'issues': account_issues,
        'recent_failure': (
            {
                'id': str(recent_failure.id),
                'status': recent_failure.status,
                'last_error': recent_error,
                'created_at': recent_failure.created_at.isoformat(),
                'updated_at': recent_failure.updated_at.isoformat(),
                'is_credit_issue': credit_issue,
            }
            if recent_failure
            else None
        ),
        'message': (
            'WhatsApp bloqueado por configuração/creditos. Revise a conta antes de validar produção.'
            if status == 'blocked'
            else 'WhatsApp com falhas recentes de envio. Verifique o provedor e a outbox.'
            if status == 'warning'
            else 'WhatsApp pronto para envio.'
        ),
    }


@router.post('/whatsapp/accounts')
def create_whatsapp_account(
    payload: dict,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    provider_name = normalize_whatsapp_provider_name(payload.get('provider_name'))

    required = ['phone_number_id', 'business_account_id', 'access_token']
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ApiError(
            status_code=400,
            code='WHATSAPP_ACCOUNT_INVALID',
            message=f'Campos obrigatorios ausentes: {", ".join(missing)}',
        )

    issues = whatsapp_account_issues(
        provider_name=provider_name,
        phone_number_id=payload.get('phone_number_id'),
        business_account_id=payload.get('business_account_id'),
        access_token=payload.get('access_token'),
    )
    if issues:
        raise ApiError(
            status_code=400,
            code='WHATSAPP_ACCOUNT_INVALID',
            message='Dados da conta WhatsApp invalidos para envio real.',
            details={'issues': issues},
        )

    current_active_accounts = db.execute(
        select(WhatsAppAccount).where(
            WhatsAppAccount.tenant_id == tenant_id,
            WhatsAppAccount.is_active.is_(True),
        )
    ).scalars().all()
    for current in current_active_accounts:
        current.is_active = False
        db.add(current)

    item = WhatsAppAccount(
        tenant_id=tenant_id,
        unit_id=payload.get('unit_id'),
        provider_name=provider_name,
        phone_number_id=payload['phone_number_id'],
        business_account_id=payload['business_account_id'],
        display_phone=payload.get('display_phone'),
        access_token_encrypted=payload['access_token'],
        verify_token=payload.get('verify_token', 'verify-token-dev'),
        webhook_secret=payload.get('webhook_secret'),
        is_active=True,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    record_audit(
        db,
        action='whatsapp.account.create',
        entity_type='whatsapp_account',
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'phone_number_id': item.phone_number_id, 'provider_name': item.provider_name},
    )
    return {
        'id': str(item.id),
        'provider_name': item.provider_name,
        'phone_number_id': item.phone_number_id,
        'is_active': item.is_active,
    }


@router.post('/whatsapp/test')
def test_whatsapp_connection(
    payload: dict,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    account = None
    account_id = payload.get('account_id')
    if account_id:
        account = db.scalar(
            select(WhatsAppAccount).where(WhatsAppAccount.id == account_id, WhatsAppAccount.tenant_id == tenant_id)
        )
        if not account:
            raise ApiError(status_code=404, code='WHATSAPP_ACCOUNT_NOT_FOUND', message='Conta WhatsApp nao encontrada')

    provider_name = normalize_whatsapp_provider_name(payload.get('provider_name') or (account.provider_name if account else None))
    phone_number_id = payload.get('phone_number_id') or (account.phone_number_id if account else None)
    business_account_id = payload.get('business_account_id') or (account.business_account_id if account else None)
    access_token = payload.get('access_token') or (account.access_token_encrypted if account else None)
    display_phone = payload.get('display_phone') or (account.display_phone if account else None)

    missing = [
        key
        for key, value in {
            'phone_number_id': phone_number_id,
            'business_account_id': business_account_id,
            'access_token': access_token,
        }.items()
        if not value
    ]
    if missing:
        raise ApiError(
            status_code=400,
            code='WHATSAPP_TEST_INVALID',
            message=f'Campos obrigatorios ausentes para teste: {", ".join(missing)}',
        )

    issues = whatsapp_account_issues(
        provider_name=provider_name,
        phone_number_id=phone_number_id,
        business_account_id=business_account_id,
        access_token=access_token,
    )
    if issues:
        raise ApiError(
            status_code=400,
            code='WHATSAPP_TEST_INVALID',
            message='Credenciais invalidas para validar a conta WhatsApp.',
            details={'issues': issues},
        )

    if provider_name == 'infobip':
        provider = InfobipWhatsAppProvider(base_url=business_account_id)
    elif provider_name == 'twilio':
        provider = TwilioWhatsAppProvider(account_sid=business_account_id)
    else:
        provider = WhatsAppCloudProvider()

    try:
        result = provider.test_connection(
            phone_number_id=phone_number_id,
            business_account_id=business_account_id,
            access_token=access_token,
        )
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response else 502
        raise ApiError(
            status_code=400,
            code='WHATSAPP_TEST_FAILED',
            message='Falha ao validar conta WhatsApp no provedor configurado.',
            details={'status_code': status_code, 'error': str(exc)},
        ) from exc
    except Exception as exc:
        raise ApiError(
            status_code=400,
            code='WHATSAPP_TEST_FAILED',
            message='Falha inesperada ao validar conta WhatsApp.',
            details={'error': str(exc)},
        ) from exc

    phone_data = result.get('phone') if isinstance(result, dict) else {}
    connected_number = None
    if isinstance(phone_data, dict):
        connected_number = phone_data.get('display_phone_number')
    if provider_name == 'infobip':
        connected_number = (
            (result.get('sender') if isinstance(result, dict) else None)
            or display_phone
            or phone_number_id
        )
    if provider_name == 'twilio':
        connected_number = (
            (result.get('sender') if isinstance(result, dict) else None)
            or display_phone
            or phone_number_id
        )

    record_audit(
        db,
        action='whatsapp.account.test',
        entity_type='whatsapp_account',
        entity_id=str(account.id) if account else None,
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={
            'provider_name': provider_name,
            'phone_number_id': phone_number_id,
            'business_account_id': business_account_id,
            'integration_valid': True,
        },
    )

    return {
        'status': 'conectado',
        'webhook_status': 'ativo',
        'integration_valid': True,
        'connected_number': connected_number or display_phone or 'Numero nao informado',
        'last_event_at': datetime.now(UTC).isoformat(),
        'message': (
            'Conexao validada com sucesso na Infobip API'
            if provider_name == 'infobip'
            else 'Conexao validada com sucesso na Twilio API'
            if provider_name == 'twilio'
            else 'Conexao validada com sucesso na Meta Cloud API'
        ),
    }


@router.get('/whatsapp/templates')
def list_templates(db: Session = Depends(get_db), tenant_id=Depends(get_tenant_id)):
    rows = db.execute(
        select(WhatsAppTemplate).where(WhatsAppTemplate.tenant_id == tenant_id).order_by(WhatsAppTemplate.created_at.desc())
    ).scalars().all()
    return {
        'data': [
            {
                'id': str(item.id),
                'name': item.name,
                'language': item.language,
                'category': item.category,
                'status': item.status,
            }
            for item in rows
        ]
    }


@router.post('/whatsapp/templates')
def create_template(
    payload: dict,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    account_id = payload.get('whatsapp_account_id')
    if not account_id:
        raise ApiError(status_code=400, code='WHATSAPP_TEMPLATE_INVALID', message='whatsapp_account_id obrigatorio')

    account = db.scalar(
        select(WhatsAppAccount).where(WhatsAppAccount.id == account_id, WhatsAppAccount.tenant_id == tenant_id)
    )
    if not account:
        raise ApiError(status_code=404, code='WHATSAPP_ACCOUNT_NOT_FOUND', message='Conta WhatsApp nao encontrada')

    item = WhatsAppTemplate(
        tenant_id=tenant_id,
        whatsapp_account_id=account.id,
        name=payload.get('name', 'template_sem_nome'),
        language=payload.get('language', 'pt_BR'),
        category=payload.get('category', 'UTILITY'),
        content=payload.get('content', {}),
        status=payload.get('status', 'APPROVED'),
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    record_audit(
        db,
        action='whatsapp.template.create',
        entity_type='whatsapp_template',
        entity_id=str(item.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'name': item.name},
    )
    return {'id': str(item.id), 'name': item.name, 'status': item.status}

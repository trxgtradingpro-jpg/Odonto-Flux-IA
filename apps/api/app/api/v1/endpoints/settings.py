from datetime import UTC, datetime
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.integrations.whatsapp.cloud_api import WhatsAppCloudProvider
from app.integrations.whatsapp.infobip import InfobipWhatsAppProvider
from app.integrations.whatsapp.twilio import TwilioWhatsAppProvider
from app.models import Setting, WhatsAppAccount, WhatsAppTemplate
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
from app.services.whatsapp_service import normalize_whatsapp_provider_name, whatsapp_account_issues

router = APIRouter(prefix='/settings', tags=['settings'])


@router.get('')
def list_settings(db: Session = Depends(get_db), tenant_id=Depends(get_tenant_id)):
    rows = db.execute(select(Setting).where(Setting.tenant_id == tenant_id)).scalars().all()
    return {'data': [{'id': str(item.id), 'key': item.key, 'value': item.value, 'is_secret': item.is_secret} for item in rows]}


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

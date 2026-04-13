from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_principal, get_request_meta
from app.core.config import settings
from app.db.session import get_db
from app.models import Tenant
from app.schemas.auth import (
    LoginInput,
    PasswordResetConfirmInput,
    PasswordResetRequestInput,
    RefreshInput,
    TokenOutput,
)
from app.services.audit_service import record_audit
from app.services.auth_service import (
    confirm_password_reset,
    login_user,
    refresh_session,
    request_password_reset,
)

router = APIRouter(prefix='/auth', tags=['auth'])


@router.post('/login', response_model=TokenOutput)
def login(payload: LoginInput, request: Request, db: Session = Depends(get_db)):
    meta = get_request_meta(request)
    result = login_user(
        db,
        email=payload.email,
        password=payload.password,
        user_agent=meta['user_agent'],
        ip_address=meta['ip_address'],
    )
    record_audit(
        db,
        action='auth.login',
        entity_type='user',
        entity_id=str(result['user'].id),
        tenant_id=result['user'].tenant_id,
        user_id=result['user'].id,
        metadata={'roles': result['roles']},
        ip_address=meta['ip_address'],
        user_agent=meta['user_agent'],
    )
    return {
        'access_token': result['access_token'],
        'refresh_token': result['refresh_token'],
        'token_type': 'bearer',
        'expires_in': result['expires_in'],
    }


@router.post('/refresh', response_model=TokenOutput)
def refresh(payload: RefreshInput, request: Request, db: Session = Depends(get_db)):
    meta = get_request_meta(request)
    result = refresh_session(
        db,
        refresh_token=payload.refresh_token,
        user_agent=meta['user_agent'],
        ip_address=meta['ip_address'],
    )
    return {
        'access_token': result['access_token'],
        'refresh_token': result['refresh_token'],
        'token_type': 'bearer',
        'expires_in': result['expires_in'],
    }


@router.post('/reset-password/request')
def reset_password_request(payload: PasswordResetRequestInput, db: Session = Depends(get_db)):
    token = request_password_reset(db, email=payload.email)
    response = {
        'message': 'Se o e-mail existir, enviaremos instrucoes de redefinicao.',
    }
    if settings.app_env in {'local', 'dev', 'development'}:
        response['debug_token'] = token
    return response


@router.post('/reset-password/confirm')
def reset_password_confirm(payload: PasswordResetConfirmInput, db: Session = Depends(get_db)):
    confirm_password_reset(db, token=payload.token, new_password=payload.new_password)
    return {'message': 'Senha atualizada com sucesso.'}


@router.get('/me')
def me(principal=Depends(get_current_principal), db: Session = Depends(get_db)):
    tenant = None
    if principal.user.tenant_id:
        tenant = db.scalar(select(Tenant).where(Tenant.id == principal.user.tenant_id))

    return {
        'id': principal.user.id,
        'email': principal.user.email,
        'full_name': principal.user.full_name,
        'tenant_id': principal.user.tenant_id,
        'tenant_trade_name': tenant.trade_name if tenant else None,
        'tenant_timezone': tenant.timezone if tenant else 'America/Sao_Paulo',
        'roles': principal.roles,
        'permissions': sorted(principal.permissions),
        'server_time': datetime.now(UTC).isoformat(),
    }

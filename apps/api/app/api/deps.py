from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.core.security import TokenError, decode_token
from app.db.session import get_db
from app.models import Role, User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/api/v1/auth/login')


@dataclass
class Principal:
    user: User
    roles: list[str]
    permissions: set[str]
    tenant_id: UUID | None



def _load_principal(db: Session, user_id: str) -> Principal:
    user = db.scalar(select(User).where(User.id == user_id))
    if not user or not user.is_active:
        raise ApiError(status_code=401, code='AUTH_INVALID_USER', message='Usuario invalido')

    role_rows = db.execute(
        select(Role).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user.id)
    ).scalars()
    roles = [role.name for role in role_rows]

    permission_rows = db.execute(
        select(Role.permissions)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id)
    ).all()
    permissions: set[str] = set()
    for row in permission_rows:
        for permission in row[0] or []:
            permissions.add(permission)

    return Principal(user=user, roles=roles, permissions=permissions, tenant_id=user.tenant_id)



def get_current_principal(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Principal:
    try:
        payload = decode_token(token)
    except TokenError as exc:
        raise ApiError(status_code=401, code='AUTH_INVALID_TOKEN', message=str(exc)) from exc

    if payload.get('type') != 'access':
        raise ApiError(status_code=401, code='AUTH_INVALID_TOKEN_TYPE', message='Token invalido')

    principal = _load_principal(db, payload.get('sub'))
    return principal



def get_tenant_id(principal: Principal = Depends(get_current_principal)) -> UUID:
    if not principal.tenant_id and 'admin_platform' not in principal.roles:
        raise ApiError(status_code=403, code='TENANT_REQUIRED', message='Tenant obrigatorio para este recurso')
    if not principal.tenant_id:
        raise ApiError(status_code=400, code='TENANT_CONTEXT_MISSING', message='Informe tenant no recurso admin')
    return principal.tenant_id



def require_roles(*allowed_roles: str):
    def _dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        if not set(allowed_roles).intersection(set(principal.roles)):
            readable_roles = ', '.join(allowed_roles)
            raise ApiError(
                status_code=403,
                code='AUTH_FORBIDDEN_ROLE',
                message=f'Acesso restrito aos perfis: {readable_roles}',
                details={
                    'required_roles': list(allowed_roles),
                    'current_roles': principal.roles,
                },
            )
        return principal

    return _dependency



def require_permission(permission: str):
    def _dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        if permission not in principal.permissions and 'admin_platform' not in principal.roles:
            raise ApiError(
                status_code=403,
                code='AUTH_FORBIDDEN_PERMISSION',
                message='Permissao insuficiente',
            )
        return principal

    return _dependency



def get_request_meta(request: Request) -> dict[str, str | None]:
    x_forwarded_for = request.headers.get('x-forwarded-for')
    ip = x_forwarded_for or (request.client.host if request.client else None)
    return {
        'ip_address': ip,
        'user_agent': request.headers.get('user-agent'),
    }

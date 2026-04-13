from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')


class TokenError(Exception):
    pass



def hash_password(password: str) -> str:
    return pwd_context.hash(password)



def verify_password(password: str, hashed_password: str) -> bool:
    return pwd_context.verify(password, hashed_password)



def create_token(
    *,
    subject: str,
    token_type: str,
    tenant_id: UUID | None,
    roles: list[str],
    expires_delta: timedelta,
    extra: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        'sub': subject,
        'type': token_type,
        'iat': int(now.timestamp()),
        'exp': int((now + expires_delta).timestamp()),
        'tenant_id': str(tenant_id) if tenant_id else None,
        'roles': roles,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.api_secret_key, algorithm='HS256')



def create_access_token(subject: str, tenant_id: UUID | None, roles: list[str]) -> str:
    return create_token(
        subject=subject,
        token_type='access',
        tenant_id=tenant_id,
        roles=roles,
        expires_delta=timedelta(minutes=settings.api_access_token_expire_minutes),
    )



def create_refresh_token(subject: str, tenant_id: UUID | None, roles: list[str]) -> str:
    return create_token(
        subject=subject,
        token_type='refresh',
        tenant_id=tenant_id,
        roles=roles,
        expires_delta=timedelta(minutes=settings.api_refresh_token_expire_minutes),
    )



def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.api_secret_key, algorithms=['HS256'])
    except JWTError as exc:
        raise TokenError('Token invalido') from exc

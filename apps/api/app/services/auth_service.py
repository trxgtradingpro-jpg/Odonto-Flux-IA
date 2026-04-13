from datetime import UTC, datetime, timedelta
import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ApiError
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import Invitation, PasswordResetToken, RefreshToken, Role, User, UserRole
from app.services.password_policy_service import validate_password_strength
from app.utils.hash import sha256_text


def get_user_role_names(db: Session, user_id: UUID) -> list[str]:
    rows = db.execute(
        select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
    ).all()
    return [row[0] for row in rows]



def login_user(db: Session, *, email: str, password: str, user_agent: str | None, ip_address: str | None) -> dict:
    user = db.scalar(select(User).where(User.email == email.lower().strip()))
    if not user or not verify_password(password, user.hashed_password):
        raise ApiError(status_code=401, code='AUTH_INVALID_CREDENTIALS', message='Credenciais invalidas')
    if not user.is_active:
        raise ApiError(status_code=403, code='AUTH_USER_DISABLED', message='Usuario inativo')

    roles = get_user_role_names(db, user.id)
    access_token = create_access_token(subject=str(user.id), tenant_id=user.tenant_id, roles=roles)
    refresh_token = create_refresh_token(subject=str(user.id), tenant_id=user.tenant_id, roles=roles)

    refresh_token_hash = sha256_text(refresh_token)
    refresh_model = RefreshToken(
        tenant_id=user.tenant_id,
        user_id=user.id,
        token_hash=refresh_token_hash,
        user_agent=user_agent,
        ip_address=ip_address,
        expires_at=datetime.now(UTC) + timedelta(minutes=settings.api_refresh_token_expire_minutes),
    )
    user.last_login_at = datetime.now(UTC)
    db.add(refresh_model)
    db.add(user)
    db.commit()

    return {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'expires_in': settings.api_access_token_expire_minutes * 60,
        'user': user,
        'roles': roles,
    }



def refresh_session(db: Session, *, refresh_token: str, user_agent: str | None, ip_address: str | None) -> dict:
    try:
        payload = decode_token(refresh_token)
    except TokenError as exc:
        raise ApiError(status_code=401, code='AUTH_INVALID_REFRESH', message=str(exc)) from exc

    if payload.get('type') != 'refresh':
        raise ApiError(status_code=401, code='AUTH_INVALID_REFRESH', message='Refresh token invalido')

    token_hash = sha256_text(refresh_token)
    token_record = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if not token_record or token_record.revoked_at:
        raise ApiError(status_code=401, code='AUTH_REFRESH_REVOKED', message='Refresh token revogado')
    if token_record.expires_at < datetime.now(UTC):
        raise ApiError(status_code=401, code='AUTH_REFRESH_EXPIRED', message='Refresh token expirado')

    user = db.get(User, token_record.user_id)
    if not user:
        raise ApiError(status_code=401, code='AUTH_INVALID_USER', message='Usuario invalido')

    token_record.revoked_at = datetime.now(UTC)

    roles = get_user_role_names(db, user.id)
    new_access = create_access_token(subject=str(user.id), tenant_id=user.tenant_id, roles=roles)
    new_refresh = create_refresh_token(subject=str(user.id), tenant_id=user.tenant_id, roles=roles)

    db.add(
        RefreshToken(
            tenant_id=user.tenant_id,
            user_id=user.id,
            token_hash=sha256_text(new_refresh),
            user_agent=user_agent,
            ip_address=ip_address,
            expires_at=datetime.now(UTC) + timedelta(minutes=settings.api_refresh_token_expire_minutes),
        )
    )
    db.commit()

    return {
        'access_token': new_access,
        'refresh_token': new_refresh,
        'expires_in': settings.api_access_token_expire_minutes * 60,
    }



def request_password_reset(db: Session, *, email: str) -> str:
    user = db.scalar(select(User).where(User.email == email.lower().strip()))
    if not user:
        return ''

    raw_token = secrets.token_urlsafe(32)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=sha256_text(raw_token),
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
    )
    db.commit()
    return raw_token



def confirm_password_reset(db: Session, *, token: str, new_password: str) -> None:
    validate_password_strength(new_password)

    token_hash = sha256_text(token)
    token_record = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))
    if not token_record or token_record.used_at is not None:
        raise ApiError(status_code=400, code='RESET_TOKEN_INVALID', message='Token invalido')
    if token_record.expires_at < datetime.now(UTC):
        raise ApiError(status_code=400, code='RESET_TOKEN_EXPIRED', message='Token expirado')

    user = db.get(User, token_record.user_id)
    if not user:
        raise ApiError(status_code=404, code='USER_NOT_FOUND', message='Usuario nao encontrado')

    user.hashed_password = hash_password(new_password)
    token_record.used_at = datetime.now(UTC)
    db.add(user)
    db.add(token_record)
    db.commit()



def create_invitation(db: Session, *, tenant_id: UUID, invited_by_user_id: UUID, email: str, role_name: str) -> str:
    raw_token = create_refresh_token(subject=str(invited_by_user_id), tenant_id=tenant_id, roles=[role_name])
    invitation = Invitation(
        tenant_id=tenant_id,
        invited_by_user_id=invited_by_user_id,
        email=email.lower().strip(),
        role_name=role_name,
        token_hash=sha256_text(raw_token),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db.add(invitation)
    db.commit()
    return raw_token



def create_user_with_roles(
    db: Session,
    *,
    tenant_id: UUID | None,
    email: str,
    full_name: str,
    password: str,
    phone: str | None,
    roles: list[str],
) -> User:
    validate_password_strength(password)

    existing = db.scalar(select(User).where(User.email == email.lower().strip()))
    if existing:
        raise ApiError(status_code=409, code='USER_ALREADY_EXISTS', message='E-mail ja cadastrado')

    user = User(
        tenant_id=tenant_id,
        email=email.lower().strip(),
        full_name=full_name,
        phone=phone,
        hashed_password=hash_password(password),
        is_active=True,
    )
    db.add(user)
    db.flush()

    role_records = db.execute(select(Role).where(Role.name.in_(roles))).scalars().all()
    if len(role_records) != len(set(roles)):
        raise ApiError(status_code=400, code='ROLE_INVALID', message='Role informada nao existe')

    for role in role_records:
        db.add(UserRole(tenant_id=tenant_id, user_id=user.id, role_id=role.id))

    db.commit()
    db.refresh(user)
    return user

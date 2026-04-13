
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_current_principal, get_tenant_id
from app.core.exceptions import ApiError
from app.db.session import get_db
from app.models import Role, User, UserRole
from app.schemas.user import InviteInput, UserCreate, UserOutput, UserUpdate
from app.services.audit_service import record_audit
from app.services.auth_service import create_invitation, create_user_with_roles, get_user_role_names
from app.services.subscription_service import enforce_plan_limit

router = APIRouter(prefix='/users', tags=['users'])


@router.get('')
def list_users(
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    limit: int = Query(default=20, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    search: str | None = None,
):
    stmt = select(User).where(User.tenant_id == tenant_id)
    if search:
        stmt = stmt.where(User.full_name.ilike(f'%{search}%'))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.execute(stmt.order_by(User.created_at.desc()).offset(offset).limit(limit)).scalars().all()

    data = []
    for user in items:
        data.append(
            UserOutput(
                id=user.id,
                tenant_id=user.tenant_id,
                email=user.email,
                full_name=user.full_name,
                phone=user.phone,
                is_active=user.is_active,
                roles=get_user_role_names(db, user.id),
                last_login_at=user.last_login_at,
                created_at=user.created_at,
            ).model_dump()
        )

    return {'data': data, 'meta': {'total': total, 'limit': limit, 'offset': offset}}


@router.post('', response_model=UserOutput)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    enforce_plan_limit(db, tenant_id, resource='users', increment=1)

    user = create_user_with_roles(
        db,
        tenant_id=tenant_id,
        email=payload.email,
        full_name=payload.full_name,
        password=payload.password,
        phone=payload.phone,
        roles=payload.roles,
    )
    roles = get_user_role_names(db, user.id)

    record_audit(
        db,
        action='user.create',
        entity_type='user',
        entity_id=str(user.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'roles': roles, 'email': user.email},
    )

    return UserOutput(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        is_active=user.is_active,
        roles=roles,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


@router.patch('/{user_id}', response_model=UserOutput)
def update_user(
    user_id: str,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    user = db.scalar(select(User).where(User.id == user_id, User.tenant_id == tenant_id))
    if not user:
        raise ApiError(status_code=404, code='USER_NOT_FOUND', message='Usuario nao encontrado')

    updates = payload.model_dump(exclude_unset=True, exclude={'roles'})
    for key, value in updates.items():
        setattr(user, key, value)

    if payload.roles is not None:
        db.execute(select(UserRole).where(UserRole.user_id == user.id, UserRole.tenant_id == tenant_id))
        existing_user_roles = db.execute(
            select(UserRole).where(UserRole.user_id == user.id, UserRole.tenant_id == tenant_id)
        ).scalars().all()
        for item in existing_user_roles:
            db.delete(item)

        role_records = db.execute(select(Role).where(Role.name.in_(payload.roles))).scalars().all()
        for role in role_records:
            db.add(UserRole(tenant_id=tenant_id, user_id=user.id, role_id=role.id))

    db.add(user)
    db.commit()
    db.refresh(user)

    roles = get_user_role_names(db, user.id)
    record_audit(
        db,
        action='user.update',
        entity_type='user',
        entity_id=str(user.id),
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'changes': payload.model_dump(exclude_unset=True)},
    )

    return UserOutput(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        is_active=user.is_active,
        roles=roles,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


@router.post('/invite')
def invite_user(
    payload: InviteInput,
    db: Session = Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    principal: Principal = Depends(get_current_principal),
):
    token = create_invitation(
        db,
        tenant_id=tenant_id,
        invited_by_user_id=principal.user.id,
        email=payload.email,
        role_name=payload.role_name,
    )
    record_audit(
        db,
        action='user.invite',
        entity_type='invitation',
        entity_id=None,
        tenant_id=tenant_id,
        user_id=principal.user.id,
        metadata={'email': payload.email, 'role_name': payload.role_name},
    )
    return {'message': 'Convite criado com sucesso.', 'invite_token': token}

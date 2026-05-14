import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import hash_password
from app.db.base import Base
from app.main import app
from app.models import Role, Tenant, TenantPlan, User, UserRole, WhatsAppAccount


@pytest.fixture(scope='session')
def test_engine():
    database_url = os.getenv('TEST_DATABASE_URL', os.getenv('DATABASE_URL', 'postgresql+psycopg2://odontoflux:odontoflux@localhost:5432/odontoflux'))
    base_url = make_url(database_url)
    temp_database_name = f'odontoflux_test_{uuid4().hex[:10]}'
    admin_url = base_url.set(database='postgres')
    admin_engine = create_engine(admin_url, isolation_level='AUTOCOMMIT')

    try:
        with admin_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.execute(text(f'CREATE DATABASE "{temp_database_name}"'))
    except Exception as exc:
        admin_engine.dispose()
        pytest.skip(f'Database indisponivel para testes de integracao: {exc}')

    engine = create_engine(base_url.set(database=temp_database_name))
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()
    with admin_engine.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                "WHERE datname = :database_name AND pid <> pg_backend_pid()"
            ),
            {'database_name': temp_database_name},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{temp_database_name}"'))
    admin_engine.dispose()


@pytest.fixture()
def db_session(test_engine):
    connection = test_engine.connect()
    transaction = connection.begin()
    testing_session_local = sessionmaker(bind=connection, autoflush=False, autocommit=False)

    db = testing_session_local()
    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def seeded_db(db_session: Session):
    starter_plan = TenantPlan(code='starter', name='Starter', max_users=5, max_units=2, max_monthly_messages=1000)
    db_session.add(starter_plan)
    db_session.flush()

    tenant_a = Tenant(
        legal_name='Clinica A LTDA',
        trade_name='Clinica A',
        slug='tenant-a',
        plan_id=starter_plan.id,
        subscription_status='active',
    )
    tenant_b = Tenant(
        legal_name='Clinica B LTDA',
        trade_name='Clinica B',
        slug='tenant-b',
        plan_id=starter_plan.id,
        subscription_status='active',
    )
    db_session.add_all([tenant_a, tenant_b])
    db_session.flush()

    roles = [
        Role(name='owner', scope='tenant', permissions=['patients.manage', 'conversations.manage']),
        Role(name='receptionist', scope='tenant', permissions=['conversations.manage']),
        Role(name='admin_platform', scope='platform', permissions=['platform.admin']),
    ]
    db_session.add_all(roles)
    db_session.flush()

    owner_a = User(
        tenant_id=tenant_a.id,
        email='owner-a@test.com',
        full_name='Owner A',
        hashed_password=hash_password('Password@123'),
        is_active=True,
    )
    owner_b = User(
        tenant_id=tenant_b.id,
        email='owner-b@test.com',
        full_name='Owner B',
        hashed_password=hash_password('Password@123'),
        is_active=True,
    )
    admin = User(
        tenant_id=None,
        email='admin@test.com',
        full_name='Admin Platform',
        hashed_password=hash_password('Password@123'),
        is_active=True,
    )
    db_session.add_all([owner_a, owner_b, admin])
    db_session.flush()

    role_lookup = {role.name: role for role in roles}
    db_session.add_all(
        [
            UserRole(tenant_id=tenant_a.id, user_id=owner_a.id, role_id=role_lookup['owner'].id),
            UserRole(tenant_id=tenant_b.id, user_id=owner_b.id, role_id=role_lookup['owner'].id),
            UserRole(tenant_id=None, user_id=admin.id, role_id=role_lookup['admin_platform'].id),
        ]
    )

    db_session.add(
        WhatsAppAccount(
            tenant_id=tenant_a.id,
            provider_name='meta_cloud',
            phone_number_id='phone_tenant_a',
            business_account_id='biz_tenant_a',
            access_token_encrypted='mock-token',
            verify_token='verify-token-dev',
            is_active=True,
        )
    )

    db_session.commit()
    return {
        'tenant_a': tenant_a,
        'tenant_b': tenant_b,
        'owner_a': owner_a,
        'owner_b': owner_b,
        'admin': admin,
    }


@pytest.fixture()
def client(db_session: Session):
    from app.db.session import get_db

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client: TestClient, seeded_db):
    def _login(email: str, password: str = 'Password@123'):
        response = client.post('/api/v1/auth/login', json={'email': email, 'password': password})
        assert response.status_code == 200
        token = response.json()['access_token']
        return {'Authorization': f'Bearer {token}'}

    return {
        'owner_a': _login('owner-a@test.com'),
        'owner_b': _login('owner-b@test.com'),
        'admin': _login('admin@test.com'),
    }

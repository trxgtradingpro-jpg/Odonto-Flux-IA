from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDTimestampMixin
from app.models.enums import (
    AppointmentAttendanceStatus,
    AppointmentNextAppointmentStatus,
    AppointmentStatus,
    AutomationTriggerType,
    CampaignStatus,
    ConsentStatus,
    ConversationStatus,
    JobStatus,
    LeadStage,
    LeadTemperature,
    MessageDirection,
    MessageStatus,
    OutboxStatus,
    RunStatus,
    Scope,
)


class TenantPlan(UUIDTimestampMixin, Base):
    __tablename__ = "tenant_plans"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    max_users: Mapped[int] = mapped_column(Integer, default=10)
    max_units: Mapped[int] = mapped_column(Integer, default=2)
    max_monthly_messages: Mapped[int] = mapped_column(Integer, default=2000)
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(10), default="BRL")
    features: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Tenant(UUIDTimestampMixin, Base):
    __tablename__ = "tenants"

    plan_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenant_plans.id", ondelete="SET NULL"))
    legal_name: Mapped[str] = mapped_column(String(255))
    trade_name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    timezone: Mapped[str] = mapped_column(String(60), default="America/Sao_Paulo")
    locale: Mapped[str] = mapped_column(String(10), default="pt-BR")
    currency: Mapped[str] = mapped_column(String(10), default="BRL")
    subscription_status: Mapped[str] = mapped_column(String(40), default="trialing")
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Unit(UUIDTimestampMixin, Base):
    __tablename__ = "units"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    code: Mapped[str] = mapped_column(String(50))
    phone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[dict] = mapped_column(JSONB, default=dict)
    working_hours: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_unit_tenant_code"),)


class Role(UUIDTimestampMixin, Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    scope: Mapped[Scope] = mapped_column(String(20), default=Scope.TENANT.value)
    description: Mapped[str] = mapped_column(String(255), default="")
    permissions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)


class User(UUIDTimestampMixin, Base):
    __tablename__ = "users"

    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    unit_id: Mapped[UUID | None] = mapped_column(ForeignKey("units.id", ondelete="SET NULL"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(180))
    hashed_password: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(30))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    page_permissions: Mapped[dict] = mapped_column(JSONB, default=dict)
    force_fullscreen_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserRole(UUIDTimestampMixin, Base):
    __tablename__ = "user_roles"

    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), index=True)

    __table_args__ = (UniqueConstraint("tenant_id", "user_id", "role_id", name="uq_tenant_user_role"),)


class ProspectAccount(UUIDTimestampMixin, Base):
    __tablename__ = "prospect_accounts"

    tenant_seed_key: Mapped[str | None] = mapped_column(String(120), unique=True, index=True)
    clinic_name: Mapped[str] = mapped_column(String(255), index=True)
    owner_name: Mapped[str | None] = mapped_column(String(180))
    manager_name: Mapped[str | None] = mapped_column(String(180))
    phone: Mapped[str | None] = mapped_column(String(30), index=True)
    whatsapp_phone: Mapped[str | None] = mapped_column(String(30), index=True)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    website: Mapped[str | None] = mapped_column(String(255), index=True)
    city: Mapped[str | None] = mapped_column(String(120), index=True)
    state: Mapped[str | None] = mapped_column(String(80), index=True)
    main_address: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text, default="")
    lead_source: Mapped[str | None] = mapped_column(String(120), index=True)
    first_contact_channel: Mapped[str | None] = mapped_column(String(40), index=True)
    first_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uses_whatsapp_heavily: Mapped[bool] = mapped_column(Boolean, default=False)
    estimated_volume: Mapped[int | None] = mapped_column(Integer)
    main_pain: Mapped[str | None] = mapped_column(String(255))
    score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    temperature: Mapped[str] = mapped_column(String(30), default="frio", index=True)
    status: Mapped[str] = mapped_column(String(60), default="novo", index=True)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    test_phone_number: Mapped[str | None] = mapped_column(String(30))
    do_not_contact: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    opt_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    legal_basis: Mapped[str] = mapped_column(String(80), default="interesse_legitimo_b2b")
    demo_tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id", ondelete="SET NULL"), index=True)
    demo_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    demo_login_email: Mapped[str | None] = mapped_column(String(255), index=True)
    demo_access_token_hash: Mapped[str | None] = mapped_column(String(255), index=True)
    demo_access_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    demo_access_revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    demo_first_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    demo_last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    demo_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    demo_status: Mapped[str] = mapped_column(String(40), default="rascunho", index=True)
    demo_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    demo_checklist: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    score_explanation: Mapped[dict] = mapped_column(JSONB, default=dict)
    proposal_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    roi_inputs: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (
        Index("ix_prospect_accounts_contact_dedupe", "whatsapp_phone", "phone", "website"),
    )


class ProspectUnit(UUIDTimestampMixin, Base):
    __tablename__ = "prospect_units"

    prospect_account_id: Mapped[UUID] = mapped_column(ForeignKey("prospect_accounts.id", ondelete="CASCADE"), index=True)
    unit_name: Mapped[str] = mapped_column(String(180))
    address: Mapped[str] = mapped_column(Text, default="")
    phone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(255))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)


class ProspectService(UUIDTimestampMixin, Base):
    __tablename__ = "prospect_services"

    prospect_account_id: Mapped[UUID] = mapped_column(ForeignKey("prospect_accounts.id", ondelete="CASCADE"), index=True)
    service_name: Mapped[str] = mapped_column(String(180), index=True)
    category: Mapped[str | None] = mapped_column(String(120))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    price_range: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")


class ProspectNote(UUIDTimestampMixin, Base):
    __tablename__ = "prospect_notes"

    prospect_account_id: Mapped[UUID] = mapped_column(ForeignKey("prospect_accounts.id", ondelete="CASCADE"), index=True)
    author_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    body: Mapped[str] = mapped_column(Text)
    note_type: Mapped[str] = mapped_column(String(40), default="nota")


class ProspectTimelineEvent(UUIDTimestampMixin, Base):
    __tablename__ = "prospect_timeline_events"

    prospect_account_id: Mapped[UUID] = mapped_column(ForeignKey("prospect_accounts.id", ondelete="CASCADE"), index=True)
    actor_type: Mapped[str] = mapped_column(String(40), default="system")
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    event_label: Mapped[str] = mapped_column(String(180))
    payload_json: Mapped[dict] = mapped_column("payload", JSONB, default=dict)


class DemoActivityEvent(UUIDTimestampMixin, Base):
    __tablename__ = "demo_activity_events"

    prospect_account_id: Mapped[UUID] = mapped_column(ForeignKey("prospect_accounts.id", ondelete="CASCADE"), index=True)
    demo_tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    demo_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    session_id: Mapped[str | None] = mapped_column(String(120), index=True)
    event_name: Mapped[str] = mapped_column(String(80), index=True)
    page_path: Mapped[str | None] = mapped_column(String(255), index=True)
    payload_json: Mapped[dict] = mapped_column("payload", JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


class AIProvisioningRun(UUIDTimestampMixin, Base):
    __tablename__ = "ai_provisioning_runs"

    prospect_account_id: Mapped[UUID] = mapped_column(ForeignKey("prospect_accounts.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    input_json: Mapped[dict] = mapped_column("input", JSONB, default=dict)
    output_json: Mapped[dict] = mapped_column("output", JSONB, default=dict)
    model_name: Mapped[str | None] = mapped_column(String(120))
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshToken(UUIDTimestampMixin, Base):
    __tablename__ = "refresh_tokens"

    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(255), index=True)
    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PasswordResetToken(UUIDTimestampMixin, Base):
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(255), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Invitation(UUIDTimestampMixin, Base):
    __tablename__ = "invitations"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    invited_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    email: Mapped[str] = mapped_column(String(255), index=True)
    role_name: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(255), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Professional(UUIDTimestampMixin, Base):
    __tablename__ = "professionals"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    unit_id: Mapped[UUID | None] = mapped_column(ForeignKey("units.id", ondelete="SET NULL"), index=True)
    full_name: Mapped[str] = mapped_column(String(180))
    cro_number: Mapped[str | None] = mapped_column(String(80))
    specialty: Mapped[str | None] = mapped_column(String(120))
    working_days: Mapped[list[int]] = mapped_column(JSONB, default=lambda: [1, 2, 3, 4, 5])
    shift_start: Mapped[str] = mapped_column(String(5), default="08:00")
    shift_end: Mapped[str] = mapped_column(String(5), default="18:00")
    procedures: Mapped[list[str]] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class LeadSource(UUIDTimestampMixin, Base):
    __tablename__ = "lead_sources"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_lead_source_tenant_name"),)


class Patient(UUIDTimestampMixin, Base):
    __tablename__ = "patients"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    unit_id: Mapped[UUID | None] = mapped_column(ForeignKey("units.id", ondelete="SET NULL"), index=True)
    lead_source_id: Mapped[UUID | None] = mapped_column(ForeignKey("lead_sources.id", ondelete="SET NULL"))
    full_name: Mapped[str] = mapped_column(String(180), index=True)
    phone: Mapped[str] = mapped_column(String(30), index=True)
    normalized_phone: Mapped[str] = mapped_column(String(30), index=True)
    cpf: Mapped[str | None] = mapped_column(String(20))
    normalized_cpf: Mapped[str | None] = mapped_column(String(20), index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    birth_date: Mapped[date | None] = mapped_column(Date)
    operational_notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="ativo")
    origin: Mapped[str | None] = mapped_column(String(80))
    lgpd_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    marketing_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    inactive_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tags_cache: Mapped[list[str]] = mapped_column(JSONB, default=list)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("tenant_id", "normalized_phone", name="uq_patient_tenant_phone"),
        UniqueConstraint("tenant_id", "normalized_cpf", name="uq_patient_tenant_cpf"),
    )


class PatientContact(UUIDTimestampMixin, Base):
    __tablename__ = "patient_contacts"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(30))
    value: Mapped[str] = mapped_column(String(255))
    normalized_value: Mapped[str | None] = mapped_column(String(255))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)


class PatientTag(UUIDTimestampMixin, Base):
    __tablename__ = "patient_tags"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    tag: Mapped[str] = mapped_column(String(100), index=True)

    __table_args__ = (UniqueConstraint("tenant_id", "patient_id", "tag", name="uq_patient_tag"),)


class Lead(UUIDTimestampMixin, Base):
    __tablename__ = "leads"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    patient_id: Mapped[UUID | None] = mapped_column(ForeignKey("patients.id", ondelete="SET NULL"), index=True)
    source_id: Mapped[UUID | None] = mapped_column(ForeignKey("lead_sources.id", ondelete="SET NULL"))
    owner_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(180), index=True)
    phone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(255))
    origin: Mapped[str | None] = mapped_column(String(80))
    interest: Mapped[str | None] = mapped_column(String(120))
    stage: Mapped[LeadStage] = mapped_column(String(40), default=LeadStage.NEW.value)
    score: Mapped[int] = mapped_column(Integer, default=0)
    temperature: Mapped[LeadTemperature] = mapped_column(String(20), default=LeadTemperature.WARM.value)
    status: Mapped[str] = mapped_column(String(40), default="ativo")
    notes: Mapped[str] = mapped_column(Text, default="")
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Conversation(UUIDTimestampMixin, Base):
    __tablename__ = "conversations"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    unit_id: Mapped[UUID | None] = mapped_column(ForeignKey("units.id", ondelete="SET NULL"), index=True)
    patient_id: Mapped[UUID | None] = mapped_column(ForeignKey("patients.id", ondelete="SET NULL"), index=True)
    lead_id: Mapped[UUID | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), index=True)
    channel: Mapped[str] = mapped_column(String(40), default="whatsapp")
    external_thread_id: Mapped[str | None] = mapped_column(String(120), index=True)
    assigned_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[ConversationStatus] = mapped_column(String(40), default=ConversationStatus.OPEN.value)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_autoresponder_enabled: Mapped[bool | None] = mapped_column(Boolean)
    ai_autoresponder_last_decision: Mapped[str | None] = mapped_column(String(40))
    ai_autoresponder_last_reason: Mapped[str | None] = mapped_column(String(255))
    ai_autoresponder_last_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ai_autoresponder_consecutive_count: Mapped[int] = mapped_column(Integer, default=0)
    ai_state: Mapped[dict] = mapped_column(JSONB, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConversationParticipant(UUIDTimestampMixin, Base):
    __tablename__ = "conversation_participants"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    participant_type: Mapped[str] = mapped_column(String(40))
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    patient_id: Mapped[UUID | None] = mapped_column(ForeignKey("patients.id", ondelete="SET NULL"))
    display_name: Mapped[str | None] = mapped_column(String(180))
    phone: Mapped[str | None] = mapped_column(String(30))


class Message(UUIDTimestampMixin, Base):
    __tablename__ = "messages"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    direction: Mapped[MessageDirection] = mapped_column(String(20), index=True)
    channel: Mapped[str] = mapped_column(String(40), default="whatsapp")
    provider_message_id: Mapped[str | None] = mapped_column(String(120), index=True)
    sender_type: Mapped[str] = mapped_column(String(40), default="system")
    sender_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text)
    message_type: Mapped[str] = mapped_column(String(40), default="text")
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[MessageStatus] = mapped_column(String(30), default=MessageStatus.QUEUED.value)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("tenant_id", "provider_message_id", name="uq_message_tenant_provider_id"),
        Index("ix_messages_tenant_conversation_created", "tenant_id", "conversation_id", "created_at"),
    )


class MessageEvent(UUIDTimestampMixin, Base):
    __tablename__ = "message_events"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[UUID | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class LinkFlowSession(UUIDTimestampMixin, Base):
    __tablename__ = "link_flow_sessions"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    unit_id: Mapped[UUID | None] = mapped_column(ForeignKey("units.id", ondelete="SET NULL"), index=True)
    mode: Mapped[str] = mapped_column(String(40), default="link_flow", index=True)
    cta_mode: Mapped[str] = mapped_column(String(40), default="whatsapp_redirect", index=True)
    channel: Mapped[str | None] = mapped_column(String(40), index=True)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    public_access_token_hash: Mapped[str | None] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    landing_path: Mapped[str] = mapped_column(String(255), default="")
    browser_session_id: Mapped[str | None] = mapped_column(String(120), index=True)
    utm_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    failure_reason: Mapped[str | None] = mapped_column(String(120))
    linked_conversation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"),
        index=True,
    )
    linked_patient_id: Mapped[UUID | None] = mapped_column(ForeignKey("patients.id", ondelete="SET NULL"), index=True)
    linked_lead_id: Mapped[UUID | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), index=True)
    linked_appointment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"),
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    first_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cta_clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    linked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_patient_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_assistant_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LinkFlowEvent(UUIDTimestampMixin, Base):
    __tablename__ = "link_flow_events"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    link_flow_session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("link_flow_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    event_name: Mapped[str] = mapped_column(String(80), index=True)
    page_path: Mapped[str | None] = mapped_column(String(255), index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(100))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


class WhatsAppAccount(UUIDTimestampMixin, Base):
    __tablename__ = "whatsapp_accounts"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    unit_id: Mapped[UUID | None] = mapped_column(ForeignKey("units.id", ondelete="SET NULL"))
    provider_name: Mapped[str] = mapped_column(String(40), default="meta_cloud")
    phone_number_id: Mapped[str] = mapped_column(String(120), index=True)
    business_account_id: Mapped[str] = mapped_column(String(120), index=True)
    display_phone: Mapped[str | None] = mapped_column(String(30))
    access_token_encrypted: Mapped[str] = mapped_column(Text)
    verify_token: Mapped[str] = mapped_column(String(255))
    webhook_secret: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class WhatsAppTemplate(UUIDTimestampMixin, Base):
    __tablename__ = "whatsapp_templates"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    whatsapp_account_id: Mapped[UUID] = mapped_column(ForeignKey("whatsapp_accounts.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120), index=True)
    language: Mapped[str] = mapped_column(String(20), default="pt_BR")
    category: Mapped[str] = mapped_column(String(40), default="UTILITY")
    content: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="APPROVED")

    __table_args__ = (UniqueConstraint("tenant_id", "name", "language", name="uq_wpp_template_name_lang"),)


class Appointment(UUIDTimestampMixin, Base):
    __tablename__ = "appointments"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    unit_id: Mapped[UUID] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"), index=True)
    professional_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("professionals.id", ondelete="SET NULL"),
        index=True,
    )
    procedure_type: Mapped[str] = mapped_column(String(120))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[AppointmentStatus] = mapped_column(
        String(40),
        default=AppointmentStatus.SCHEDULED.value,
        index=True,
    )
    origin: Mapped[str] = mapped_column(String(80), default="manual")
    notes: Mapped[str] = mapped_column(Text, default="")
    attendance_status: Mapped[AppointmentAttendanceStatus] = mapped_column(String(40), default=AppointmentAttendanceStatus.PENDING.value)
    attendance_notes: Mapped[str] = mapped_column(Text, default="")
    next_appointment_status: Mapped[AppointmentNextAppointmentStatus] = mapped_column(
        String(40),
        default=AppointmentNextAppointmentStatus.UNDEFINED.value,
    )
    confirmation_status: Mapped[str] = mapped_column(String(40), default="pendente")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canceled_reason: Mapped[str | None] = mapped_column(String(255))
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AppointmentEvent(UUIDTimestampMixin, Base):
    __tablename__ = "appointment_events"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    appointment_id: Mapped[UUID] = mapped_column(ForeignKey("appointments.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    from_status: Mapped[str | None] = mapped_column(String(40))
    to_status: Mapped[str | None] = mapped_column(String(40))
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class Automation(UUIDTimestampMixin, Base):
    __tablename__ = "automations"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(String(255))
    trigger_type: Mapped[AutomationTriggerType] = mapped_column(
        String(20),
        default=AutomationTriggerType.EVENT.value,
        index=True,
    )
    trigger_key: Mapped[str] = mapped_column(String(80), index=True)
    conditions: Mapped[dict] = mapped_column(JSONB, default=dict)
    actions: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    retry_policy: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AutomationRun(UUIDTimestampMixin, Base):
    __tablename__ = "automation_runs"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    automation_id: Mapped[UUID] = mapped_column(ForeignKey("automations.id", ondelete="CASCADE"), index=True)
    status: Mapped[RunStatus] = mapped_column(String(20), default=RunStatus.PENDING.value, index=True)
    trigger_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    result_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retries: Mapped[int] = mapped_column(Integer, default=0)


class SalesOutreachAutomationBatch(UUIDTimestampMixin, Base):
    __tablename__ = "sales_outreach_automation_batches"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    requested_count: Mapped[int] = mapped_column(Integer, default=0)
    selected_count: Mapped[int] = mapped_column(Integer, default=0)
    filters_json: Mapped[dict] = mapped_column("filters", JSONB, default=dict)
    summary_json: Mapped[dict] = mapped_column("summary", JSONB, default=dict)
    stop_reason: Mapped[str | None] = mapped_column(String(120))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SalesOutreachAutomationBatchItem(UUIDTimestampMixin, Base):
    __tablename__ = "sales_outreach_automation_batch_items"

    batch_id: Mapped[UUID] = mapped_column(ForeignKey("sales_outreach_automation_batches.id", ondelete="CASCADE"), index=True)
    prospect_account_id: Mapped[UUID] = mapped_column(ForeignKey("prospect_accounts.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[UUID | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"), index=True)
    last_outbound_message_id: Mapped[UUID | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), index=True)
    last_inbound_message_id: Mapped[UUID | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    current_step: Mapped[str | None] = mapped_column(String(80), index=True)
    last_reply_classification: Mapped[str | None] = mapped_column(String(80), index=True)
    pause_reason: Mapped[str | None] = mapped_column(String(120))
    last_message_preview: Mapped[str | None] = mapped_column(Text)
    last_error_message: Mapped[str | None] = mapped_column(Text)
    details_json: Mapped[dict] = mapped_column("details", JSONB, default=dict)
    demo_generated_automatically: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    received_count: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("batch_id", "prospect_account_id", name="uq_sales_outreach_batch_prospect"),
    )


class Campaign(UUIDTimestampMixin, Base):
    __tablename__ = "campaigns"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    unit_id: Mapped[UUID | None] = mapped_column(ForeignKey("units.id", ondelete="SET NULL"))
    created_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    template_id: Mapped[UUID | None] = mapped_column(ForeignKey("whatsapp_templates.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(180))
    objective: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[CampaignStatus] = mapped_column(String(30), default=CampaignStatus.DRAFT.value, index=True)
    segment_filter: Mapped[dict] = mapped_column(JSONB, default=dict)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CampaignAudience(UUIDTimestampMixin, Base):
    __tablename__ = "campaign_audiences"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    patient_id: Mapped[UUID | None] = mapped_column(ForeignKey("patients.id", ondelete="SET NULL"), index=True)
    lead_id: Mapped[UUID | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)


class CampaignMessage(UUIDTimestampMixin, Base):
    __tablename__ = "campaign_messages"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    campaign_audience_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_audiences.id", ondelete="CASCADE"),
        index=True,
    )
    message_id: Mapped[UUID | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    conversion_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Document(UUIDTimestampMixin, Base):
    __tablename__ = "documents"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    patient_id: Mapped[UUID | None] = mapped_column(ForeignKey("patients.id", ondelete="SET NULL"), index=True)
    unit_id: Mapped[UUID | None] = mapped_column(ForeignKey("units.id", ondelete="SET NULL"), index=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    current_version_id: Mapped[UUID | None] = mapped_column(ForeignKey("document_versions.id", ondelete="SET NULL"))
    document_type: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text)
    storage_provider: Mapped[str] = mapped_column(String(40), default="local")
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)


class DocumentVersion(UUIDTimestampMixin, Base):
    __tablename__ = "document_versions"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    uploaded_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    version_number: Mapped[int] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(String(500))
    file_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(120))
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (UniqueConstraint("document_id", "version_number", name="uq_document_version_number"),)


class Consent(UUIDTimestampMixin, Base):
    __tablename__ = "consents"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    document_version_id: Mapped[UUID | None] = mapped_column(ForeignKey("document_versions.id", ondelete="SET NULL"))
    consent_type: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[ConsentStatus] = mapped_column(String(20), default=ConsentStatus.PENDING.value, index=True)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class AuditLog(UUIDTimestampMixin, Base):
    __tablename__ = "audit_logs"

    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id", ondelete="SET NULL"), index=True)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(80), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(100))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ApiKey(UUIDTimestampMixin, Base):
    __tablename__ = "api_keys"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    key_hash: Mapped[str] = mapped_column(String(255), unique=True)
    scopes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FeatureFlag(UUIDTimestampMixin, Base):
    __tablename__ = "feature_flags"

    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str | None] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)

    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_feature_flag_tenant_key"),)


class WebhookInbox(UUIDTimestampMixin, Base):
    __tablename__ = "webhooks_inbox"

    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id", ondelete="SET NULL"), index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    event_id: Mapped[str] = mapped_column(String(120), index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),)


class OutboxMessage(UUIDTimestampMixin, Base):
    __tablename__ = "outbox_messages"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(40), default="whatsapp")
    status: Mapped[OutboxStatus] = mapped_column(String(30), default=OutboxStatus.PENDING.value, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=5)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_error: Mapped[str | None] = mapped_column(Text)


class Job(UUIDTimestampMixin, Base):
    __tablename__ = "jobs"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    job_type: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[JobStatus] = mapped_column(String(20), default=JobStatus.PENDING.value, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    result: Mapped[dict] = mapped_column(JSONB, default=dict)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    error_message: Mapped[str | None] = mapped_column(Text)


class Setting(UUIDTimestampMixin, Base):
    __tablename__ = "settings"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(120), index=True)
    value: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_setting_tenant_key"),)


class LLMInteraction(UUIDTimestampMixin, Base):
    __tablename__ = "llm_interactions"

    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id", ondelete="SET NULL"), index=True)
    conversation_id: Mapped[UUID | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(80))
    task: Mapped[str] = mapped_column(String(80))
    prompt: Mapped[str] = mapped_column(Text)
    response: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    latency_ms: Mapped[int | None] = mapped_column(Integer)


class AIAutoresponderDecision(UUIDTimestampMixin, Base):
    __tablename__ = "ai_autoresponder_decisions"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    unit_id: Mapped[UUID | None] = mapped_column(ForeignKey("units.id", ondelete="SET NULL"), index=True)
    inbound_message_id: Mapped[UUID | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), index=True)
    outbound_message_id: Mapped[UUID | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    channel: Mapped[str] = mapped_column(String(40), default="whatsapp", index=True)
    inbound_text: Mapped[str] = mapped_column(Text)
    generated_response: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    final_decision: Mapped[str] = mapped_column(String(40), index=True)
    decision_reason: Mapped[str] = mapped_column(String(255), index=True)
    guardrail_trigger: Mapped[str | None] = mapped_column(String(120))
    handoff_required: Mapped[bool] = mapped_column(Boolean, default=False)
    llm_provider: Mapped[str | None] = mapped_column(String(80))
    llm_model: Mapped[str | None] = mapped_column(String(80))
    llm_task: Mapped[str | None] = mapped_column(String(80))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    prompt_text: Mapped[str | None] = mapped_column(Text)
    token_input: Mapped[int | None] = mapped_column(Integer)
    token_output: Mapped[int | None] = mapped_column(Integer)
    token_total: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    dedupe_key: Mapped[str] = mapped_column(String(140))
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant_id", "dedupe_key", name="uq_ai_autoresponder_decision_dedupe"),
        Index("ix_ai_autoresponder_tenant_conversation_created", "tenant_id", "conversation_id", "created_at"),
    )


Index("ix_patients_tenant_name", Patient.tenant_id, Patient.full_name)
Index("ix_leads_tenant_stage", Lead.tenant_id, Lead.stage)
Index("ix_conversations_tenant_status", Conversation.tenant_id, Conversation.status)
Index("ix_appointments_tenant_status_starts", Appointment.tenant_id, Appointment.status, Appointment.starts_at)
Index("ix_campaign_audiences_tenant_status", CampaignAudience.tenant_id, CampaignAudience.status)
Index("ix_audit_logs_tenant_action", AuditLog.tenant_id, AuditLog.action)

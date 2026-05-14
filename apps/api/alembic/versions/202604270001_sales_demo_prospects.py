"""sales demo prospects

Revision ID: 202604270001
Revises: 202604240003
Create Date: 2026-04-27 10:00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "202604270001"
down_revision: Union[str, None] = "202604240003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "prospect_accounts" not in tables:
        op.create_table(
            "prospect_accounts",
            *_timestamps(),
            sa.Column("tenant_seed_key", sa.String(length=120), nullable=True),
            sa.Column("clinic_name", sa.String(length=255), nullable=False),
            sa.Column("owner_name", sa.String(length=180), nullable=True),
            sa.Column("manager_name", sa.String(length=180), nullable=True),
            sa.Column("phone", sa.String(length=30), nullable=True),
            sa.Column("whatsapp_phone", sa.String(length=30), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("website", sa.String(length=255), nullable=True),
            sa.Column("city", sa.String(length=120), nullable=True),
            sa.Column("state", sa.String(length=80), nullable=True),
            sa.Column("main_address", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("lead_source", sa.String(length=120), nullable=True),
            sa.Column("first_contact_channel", sa.String(length=40), nullable=True),
            sa.Column("first_contact_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("uses_whatsapp_heavily", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("estimated_volume", sa.Integer(), nullable=True),
            sa.Column("main_pain", sa.String(length=255), nullable=True),
            sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("temperature", sa.String(length=30), nullable=False, server_default="frio"),
            sa.Column("status", sa.String(length=60), nullable=False, server_default="novo"),
            sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("test_phone_number", sa.String(length=30), nullable=True),
            sa.Column("do_not_contact", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("opt_out_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("legal_basis", sa.String(length=80), nullable=False, server_default="interesse_legitimo_b2b"),
            sa.Column("demo_tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("demo_user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("demo_login_email", sa.String(length=255), nullable=True),
            sa.Column("demo_access_token_hash", sa.String(length=255), nullable=True),
            sa.Column("demo_access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("demo_access_revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("demo_first_login_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("demo_last_login_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("demo_sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("demo_status", sa.String(length=40), nullable=False, server_default="rascunho"),
            sa.Column("demo_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("demo_checklist", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("score_explanation", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("proposal_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("roi_inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.ForeignKeyConstraint(["demo_tenant_id"], ["tenants.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["demo_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("tenant_seed_key", name="uq_prospect_accounts_seed_key"),
        )
        op.create_index("ix_prospect_accounts_clinic_name", "prospect_accounts", ["clinic_name"])
        op.create_index("ix_prospect_accounts_status", "prospect_accounts", ["status"])
        op.create_index("ix_prospect_accounts_temperature", "prospect_accounts", ["temperature"])
        op.create_index("ix_prospect_accounts_score", "prospect_accounts", ["score"])
        op.create_index("ix_prospect_accounts_demo_tenant_id", "prospect_accounts", ["demo_tenant_id"])
        op.create_index("ix_prospect_accounts_contact_dedupe", "prospect_accounts", ["whatsapp_phone", "phone", "website"])

    if "prospect_units" not in tables:
        op.create_table(
            "prospect_units",
            *_timestamps(),
            sa.Column("prospect_account_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("unit_name", sa.String(length=180), nullable=False),
            sa.Column("address", sa.Text(), nullable=False, server_default=""),
            sa.Column("phone", sa.String(length=30), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.ForeignKeyConstraint(["prospect_account_id"], ["prospect_accounts.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_prospect_units_prospect_account_id", "prospect_units", ["prospect_account_id"])

    if "prospect_services" not in tables:
        op.create_table(
            "prospect_services",
            *_timestamps(),
            sa.Column("prospect_account_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("service_name", sa.String(length=180), nullable=False),
            sa.Column("category", sa.String(length=120), nullable=True),
            sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="60"),
            sa.Column("price_range", sa.String(length=120), nullable=True),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.ForeignKeyConstraint(["prospect_account_id"], ["prospect_accounts.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_prospect_services_prospect_account_id", "prospect_services", ["prospect_account_id"])
        op.create_index("ix_prospect_services_service_name", "prospect_services", ["service_name"])

    if "prospect_notes" not in tables:
        op.create_table(
            "prospect_notes",
            *_timestamps(),
            sa.Column("prospect_account_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("author_user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("note_type", sa.String(length=40), nullable=False, server_default="nota"),
            sa.ForeignKeyConstraint(["prospect_account_id"], ["prospect_accounts.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_prospect_notes_prospect_account_id", "prospect_notes", ["prospect_account_id"])

    if "prospect_timeline_events" not in tables:
        op.create_table(
            "prospect_timeline_events",
            *_timestamps(),
            sa.Column("prospect_account_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("actor_type", sa.String(length=40), nullable=False, server_default="system"),
            sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("event_type", sa.String(length=80), nullable=False),
            sa.Column("event_label", sa.String(length=180), nullable=False),
            sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.ForeignKeyConstraint(["prospect_account_id"], ["prospect_accounts.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_prospect_timeline_events_prospect_account_id", "prospect_timeline_events", ["prospect_account_id"])
        op.create_index("ix_prospect_timeline_events_event_type", "prospect_timeline_events", ["event_type"])

    if "demo_activity_events" not in tables:
        op.create_table(
            "demo_activity_events",
            *_timestamps(),
            sa.Column("prospect_account_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("demo_tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("demo_user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("session_id", sa.String(length=120), nullable=True),
            sa.Column("event_name", sa.String(length=80), nullable=False),
            sa.Column("page_path", sa.String(length=255), nullable=True),
            sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["prospect_account_id"], ["prospect_accounts.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["demo_tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["demo_user_id"], ["users.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_demo_activity_events_prospect_account_id", "demo_activity_events", ["prospect_account_id"])
        op.create_index("ix_demo_activity_events_demo_tenant_id", "demo_activity_events", ["demo_tenant_id"])
        op.create_index("ix_demo_activity_events_event_name", "demo_activity_events", ["event_name"])
        op.create_index("ix_demo_activity_events_occurred_at", "demo_activity_events", ["occurred_at"])

    if "ai_provisioning_runs" not in tables:
        op.create_table(
            "ai_provisioning_runs",
            *_timestamps(),
            sa.Column("prospect_account_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
            sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("model_name", sa.String(length=120), nullable=True),
            sa.Column("tokens_in", sa.Integer(), nullable=True),
            sa.Column("tokens_out", sa.Integer(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["prospect_account_id"], ["prospect_accounts.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_ai_provisioning_runs_prospect_account_id", "ai_provisioning_runs", ["prospect_account_id"])
        op.create_index("ix_ai_provisioning_runs_status", "ai_provisioning_runs", ["status"])


def downgrade() -> None:
    for table_name in [
        "ai_provisioning_runs",
        "demo_activity_events",
        "prospect_timeline_events",
        "prospect_notes",
        "prospect_services",
        "prospect_units",
        "prospect_accounts",
    ]:
        op.drop_table(table_name)

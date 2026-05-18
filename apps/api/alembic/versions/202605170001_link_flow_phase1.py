"""Add link flow sessions and events.

Revision ID: 202605170001
Revises: 202604270003
Create Date: 2026-05-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "202605170001"
down_revision: Union[str, None] = "202604270003"
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

    if "link_flow_sessions" not in tables:
        op.create_table(
            "link_flow_sessions",
            *_timestamps(),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("unit_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("mode", sa.String(length=40), nullable=False, server_default="link_flow"),
            sa.Column("cta_mode", sa.String(length=40), nullable=False, server_default="whatsapp_redirect"),
            sa.Column("token_hash", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
            sa.Column("landing_path", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("browser_session_id", sa.String(length=120), nullable=True),
            sa.Column("utm_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("linked_conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("linked_patient_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("linked_lead_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("linked_appointment_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("first_opened_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cta_clicked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["linked_conversation_id"], ["conversations.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["linked_patient_id"], ["patients.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["linked_lead_id"], ["leads.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["linked_appointment_id"], ["appointments.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("token_hash", name="uq_link_flow_sessions_token_hash"),
        )
        op.create_index("ix_link_flow_sessions_tenant_id", "link_flow_sessions", ["tenant_id"])
        op.create_index("ix_link_flow_sessions_unit_id", "link_flow_sessions", ["unit_id"])
        op.create_index("ix_link_flow_sessions_mode", "link_flow_sessions", ["mode"])
        op.create_index("ix_link_flow_sessions_cta_mode", "link_flow_sessions", ["cta_mode"])
        op.create_index("ix_link_flow_sessions_status", "link_flow_sessions", ["status"])
        op.create_index("ix_link_flow_sessions_browser_session_id", "link_flow_sessions", ["browser_session_id"])
        op.create_index("ix_link_flow_sessions_linked_conversation_id", "link_flow_sessions", ["linked_conversation_id"])
        op.create_index("ix_link_flow_sessions_linked_patient_id", "link_flow_sessions", ["linked_patient_id"])
        op.create_index("ix_link_flow_sessions_linked_lead_id", "link_flow_sessions", ["linked_lead_id"])
        op.create_index("ix_link_flow_sessions_linked_appointment_id", "link_flow_sessions", ["linked_appointment_id"])
        op.create_index("ix_link_flow_sessions_expires_at", "link_flow_sessions", ["expires_at"])

    if "link_flow_events" not in tables:
        op.create_table(
            "link_flow_events",
            *_timestamps(),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("link_flow_session_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("event_name", sa.String(length=80), nullable=False),
            sa.Column("page_path", sa.String(length=255), nullable=True),
            sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("ip_address", sa.String(length=100), nullable=True),
            sa.Column("user_agent", sa.String(length=255), nullable=True),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["link_flow_session_id"], ["link_flow_sessions.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_link_flow_events_tenant_id", "link_flow_events", ["tenant_id"])
        op.create_index("ix_link_flow_events_link_flow_session_id", "link_flow_events", ["link_flow_session_id"])
        op.create_index("ix_link_flow_events_event_name", "link_flow_events", ["event_name"])
        op.create_index("ix_link_flow_events_page_path", "link_flow_events", ["page_path"])
        op.create_index("ix_link_flow_events_occurred_at", "link_flow_events", ["occurred_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "link_flow_events" in tables:
        op.drop_index("ix_link_flow_events_occurred_at", table_name="link_flow_events")
        op.drop_index("ix_link_flow_events_page_path", table_name="link_flow_events")
        op.drop_index("ix_link_flow_events_event_name", table_name="link_flow_events")
        op.drop_index("ix_link_flow_events_link_flow_session_id", table_name="link_flow_events")
        op.drop_index("ix_link_flow_events_tenant_id", table_name="link_flow_events")
        op.drop_table("link_flow_events")

    if "link_flow_sessions" in tables:
        op.drop_index("ix_link_flow_sessions_expires_at", table_name="link_flow_sessions")
        op.drop_index("ix_link_flow_sessions_linked_appointment_id", table_name="link_flow_sessions")
        op.drop_index("ix_link_flow_sessions_linked_lead_id", table_name="link_flow_sessions")
        op.drop_index("ix_link_flow_sessions_linked_patient_id", table_name="link_flow_sessions")
        op.drop_index("ix_link_flow_sessions_linked_conversation_id", table_name="link_flow_sessions")
        op.drop_index("ix_link_flow_sessions_browser_session_id", table_name="link_flow_sessions")
        op.drop_index("ix_link_flow_sessions_status", table_name="link_flow_sessions")
        op.drop_index("ix_link_flow_sessions_cta_mode", table_name="link_flow_sessions")
        op.drop_index("ix_link_flow_sessions_mode", table_name="link_flow_sessions")
        op.drop_index("ix_link_flow_sessions_unit_id", table_name="link_flow_sessions")
        op.drop_index("ix_link_flow_sessions_tenant_id", table_name="link_flow_sessions")
        op.drop_table("link_flow_sessions")

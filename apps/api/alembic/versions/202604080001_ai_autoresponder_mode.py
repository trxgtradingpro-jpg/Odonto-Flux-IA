"""ai autoresponder mode

Revision ID: 202604080001
Revises: 202604070001
Create Date: 2026-04-08 15:10:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "202604080001"
down_revision: Union[str, None] = "202604070001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    conversation_columns = {column["name"] for column in inspector.get_columns("conversations")}
    if "ai_autoresponder_enabled" not in conversation_columns:
        op.add_column("conversations", sa.Column("ai_autoresponder_enabled", sa.Boolean(), nullable=True))
    if "ai_autoresponder_last_decision" not in conversation_columns:
        op.add_column("conversations", sa.Column("ai_autoresponder_last_decision", sa.String(length=40), nullable=True))
    if "ai_autoresponder_last_reason" not in conversation_columns:
        op.add_column("conversations", sa.Column("ai_autoresponder_last_reason", sa.String(length=255), nullable=True))
    if "ai_autoresponder_last_at" not in conversation_columns:
        op.add_column("conversations", sa.Column("ai_autoresponder_last_at", sa.DateTime(timezone=True), nullable=True))

    added_consecutive_column = False
    if "ai_autoresponder_consecutive_count" not in conversation_columns:
        op.add_column(
            "conversations",
            sa.Column(
                "ai_autoresponder_consecutive_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
        added_consecutive_column = True

    if "ai_autoresponder_decisions" not in inspector.get_table_names():
        op.create_table(
            "ai_autoresponder_decisions",
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("unit_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("inbound_message_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("outbound_message_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("channel", sa.String(length=40), nullable=False),
            sa.Column("inbound_text", sa.Text(), nullable=False),
            sa.Column("generated_response", sa.Text(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("final_decision", sa.String(length=40), nullable=False),
            sa.Column("decision_reason", sa.String(length=255), nullable=False),
            sa.Column("guardrail_trigger", sa.String(length=120), nullable=True),
            sa.Column("handoff_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("llm_provider", sa.String(length=80), nullable=True),
            sa.Column("llm_model", sa.String(length=80), nullable=True),
            sa.Column("llm_task", sa.String(length=80), nullable=True),
            sa.Column("prompt_version", sa.String(length=40), nullable=True),
            sa.Column("prompt_text", sa.Text(), nullable=True),
            sa.Column("token_input", sa.Integer(), nullable=True),
            sa.Column("token_output", sa.Integer(), nullable=True),
            sa.Column("token_total", sa.Integer(), nullable=True),
            sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column("dedupe_key", sa.String(length=140), nullable=False),
            sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["inbound_message_id"], ["messages.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["outbound_message_id"], ["messages.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "dedupe_key", name="uq_ai_autoresponder_decision_dedupe"),
        )

        op.create_index(op.f("ix_ai_autoresponder_decisions_channel"), "ai_autoresponder_decisions", ["channel"], unique=False)
        op.create_index(op.f("ix_ai_autoresponder_decisions_conversation_id"), "ai_autoresponder_decisions", ["conversation_id"], unique=False)
        op.create_index(op.f("ix_ai_autoresponder_decisions_decision_reason"), "ai_autoresponder_decisions", ["decision_reason"], unique=False)
        op.create_index(op.f("ix_ai_autoresponder_decisions_final_decision"), "ai_autoresponder_decisions", ["final_decision"], unique=False)
        op.create_index(op.f("ix_ai_autoresponder_decisions_inbound_message_id"), "ai_autoresponder_decisions", ["inbound_message_id"], unique=False)
        op.create_index(op.f("ix_ai_autoresponder_decisions_tenant_id"), "ai_autoresponder_decisions", ["tenant_id"], unique=False)
        op.create_index(op.f("ix_ai_autoresponder_decisions_unit_id"), "ai_autoresponder_decisions", ["unit_id"], unique=False)
        op.create_index(
            "ix_ai_autoresponder_tenant_conversation_created",
            "ai_autoresponder_decisions",
            ["tenant_id", "conversation_id", "created_at"],
            unique=False,
        )

    if added_consecutive_column:
        op.alter_column("conversations", "ai_autoresponder_consecutive_count", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "ai_autoresponder_decisions" in inspector.get_table_names():
        existing_indexes = {index["name"] for index in inspector.get_indexes("ai_autoresponder_decisions")}
        if "ix_ai_autoresponder_tenant_conversation_created" in existing_indexes:
            op.drop_index("ix_ai_autoresponder_tenant_conversation_created", table_name="ai_autoresponder_decisions")
        if op.f("ix_ai_autoresponder_decisions_unit_id") in existing_indexes:
            op.drop_index(op.f("ix_ai_autoresponder_decisions_unit_id"), table_name="ai_autoresponder_decisions")
        if op.f("ix_ai_autoresponder_decisions_tenant_id") in existing_indexes:
            op.drop_index(op.f("ix_ai_autoresponder_decisions_tenant_id"), table_name="ai_autoresponder_decisions")
        if op.f("ix_ai_autoresponder_decisions_inbound_message_id") in existing_indexes:
            op.drop_index(op.f("ix_ai_autoresponder_decisions_inbound_message_id"), table_name="ai_autoresponder_decisions")
        if op.f("ix_ai_autoresponder_decisions_final_decision") in existing_indexes:
            op.drop_index(op.f("ix_ai_autoresponder_decisions_final_decision"), table_name="ai_autoresponder_decisions")
        if op.f("ix_ai_autoresponder_decisions_decision_reason") in existing_indexes:
            op.drop_index(op.f("ix_ai_autoresponder_decisions_decision_reason"), table_name="ai_autoresponder_decisions")
        if op.f("ix_ai_autoresponder_decisions_conversation_id") in existing_indexes:
            op.drop_index(op.f("ix_ai_autoresponder_decisions_conversation_id"), table_name="ai_autoresponder_decisions")
        if op.f("ix_ai_autoresponder_decisions_channel") in existing_indexes:
            op.drop_index(op.f("ix_ai_autoresponder_decisions_channel"), table_name="ai_autoresponder_decisions")
        op.drop_table("ai_autoresponder_decisions")

    conversation_columns = {column["name"] for column in inspector.get_columns("conversations")}
    if "ai_autoresponder_consecutive_count" in conversation_columns:
        op.drop_column("conversations", "ai_autoresponder_consecutive_count")
    if "ai_autoresponder_last_at" in conversation_columns:
        op.drop_column("conversations", "ai_autoresponder_last_at")
    if "ai_autoresponder_last_reason" in conversation_columns:
        op.drop_column("conversations", "ai_autoresponder_last_reason")
    if "ai_autoresponder_last_decision" in conversation_columns:
        op.drop_column("conversations", "ai_autoresponder_last_decision")
    if "ai_autoresponder_enabled" in conversation_columns:
        op.drop_column("conversations", "ai_autoresponder_enabled")

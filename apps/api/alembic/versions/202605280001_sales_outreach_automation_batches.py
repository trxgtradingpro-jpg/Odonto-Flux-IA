"""sales outreach automation batches

Revision ID: 202605280001
Revises: 202605180001
Create Date: 2026-05-28 00:00:01.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "202605280001"
down_revision = "202605180001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sales_outreach_automation_batches",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="queued"),
        sa.Column("requested_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("selected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("stop_reason", sa.String(length=120), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_soab_batches_tenant_id", "sales_outreach_automation_batches", ["tenant_id"])
    op.create_index("ix_soab_batches_created_by_user_id", "sales_outreach_automation_batches", ["created_by_user_id"])
    op.create_index("ix_soab_batches_status", "sales_outreach_automation_batches", ["status"])

    op.create_table(
        "sales_outreach_automation_batch_items",
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sales_outreach_automation_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prospect_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prospect_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("last_outbound_message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("last_inbound_message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="queued"),
        sa.Column("current_step", sa.String(length=80), nullable=True),
        sa.Column("last_reply_classification", sa.String(length=80), nullable=True),
        sa.Column("pause_reason", sa.String(length=120), nullable=True),
        sa.Column("last_message_preview", sa.Text(), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("demo_generated_automatically", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("received_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "prospect_account_id", name="uq_sales_outreach_batch_prospect"),
    )
    op.create_index("ix_soab_items_batch_id", "sales_outreach_automation_batch_items", ["batch_id"])
    op.create_index("ix_soab_items_prospect_id", "sales_outreach_automation_batch_items", ["prospect_account_id"])
    op.create_index("ix_soab_items_conversation_id", "sales_outreach_automation_batch_items", ["conversation_id"])
    op.create_index("ix_soab_items_last_out_msg_id", "sales_outreach_automation_batch_items", ["last_outbound_message_id"])
    op.create_index("ix_soab_items_last_in_msg_id", "sales_outreach_automation_batch_items", ["last_inbound_message_id"])
    op.create_index("ix_soab_items_status", "sales_outreach_automation_batch_items", ["status"])
    op.create_index("ix_soab_items_current_step", "sales_outreach_automation_batch_items", ["current_step"])
    op.create_index("ix_soab_items_last_reply_class", "sales_outreach_automation_batch_items", ["last_reply_classification"])


def downgrade() -> None:
    op.drop_index("ix_soab_items_last_reply_class", table_name="sales_outreach_automation_batch_items")
    op.drop_index("ix_soab_items_current_step", table_name="sales_outreach_automation_batch_items")
    op.drop_index("ix_soab_items_status", table_name="sales_outreach_automation_batch_items")
    op.drop_index("ix_soab_items_last_in_msg_id", table_name="sales_outreach_automation_batch_items")
    op.drop_index("ix_soab_items_last_out_msg_id", table_name="sales_outreach_automation_batch_items")
    op.drop_index("ix_soab_items_conversation_id", table_name="sales_outreach_automation_batch_items")
    op.drop_index("ix_soab_items_prospect_id", table_name="sales_outreach_automation_batch_items")
    op.drop_index("ix_soab_items_batch_id", table_name="sales_outreach_automation_batch_items")
    op.drop_table("sales_outreach_automation_batch_items")

    op.drop_index("ix_soab_batches_status", table_name="sales_outreach_automation_batches")
    op.drop_index("ix_soab_batches_created_by_user_id", table_name="sales_outreach_automation_batches")
    op.drop_index("ix_soab_batches_tenant_id", table_name="sales_outreach_automation_batches")
    op.drop_table("sales_outreach_automation_batches")

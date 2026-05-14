"""Fix demo user output data and professional workdays.

Revision ID: 202604270002
Revises: 202604270001
Create Date: 2026-04-27
"""

from alembic import op


revision = "202604270002"
down_revision = "202604270001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE users
        SET email = regexp_replace(email, '@odontoflux\\.local$', '@demo.odontoflux.app')
        WHERE email LIKE '%@odontoflux.local'
        """
    )
    op.execute(
        """
        UPDATE users
        SET page_permissions = jsonb_set(page_permissions, '{demo_client}', '{"enabled": true}'::jsonb, true)
        WHERE page_permissions IS NOT NULL
          AND page_permissions->'demo_client' = 'true'::jsonb
        """
    )
    op.execute(
        """
        UPDATE users
        SET page_permissions = jsonb_set(page_permissions, '{presentation_mode}', '{"enabled": true}'::jsonb, true)
        WHERE page_permissions IS NOT NULL
          AND page_permissions->'presentation_mode' = 'true'::jsonb
        """
    )
    op.execute(
        """
        UPDATE professionals
        SET working_days = '[1, 2, 3, 4, 5]'::jsonb
        WHERE working_days = '[0, 1, 2, 3, 4]'::jsonb
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE professionals
        SET working_days = '[0, 1, 2, 3, 4]'::jsonb
        WHERE working_days = '[1, 2, 3, 4, 5]'::jsonb
        """
    )
    op.execute(
        """
        UPDATE users
        SET page_permissions = jsonb_set(page_permissions, '{presentation_mode}', 'true'::jsonb, true)
        WHERE page_permissions IS NOT NULL
          AND page_permissions->'presentation_mode' = '{"enabled": true}'::jsonb
        """
    )
    op.execute(
        """
        UPDATE users
        SET page_permissions = jsonb_set(page_permissions, '{demo_client}', 'true'::jsonb, true)
        WHERE page_permissions IS NOT NULL
          AND page_permissions->'demo_client' = '{"enabled": true}'::jsonb
        """
    )
    op.execute(
        """
        UPDATE users
        SET email = regexp_replace(email, '@demo\\.odontoflux\\.app$', '@odontoflux.local')
        WHERE email LIKE '%@demo.odontoflux.app'
        """
    )

"""Widen batch_jobs.status from VARCHAR(20) to VARCHAR(30).

Revision ID: 003
Revises: 002
Create Date: 2026-02-25

Fixes asyncpg.exceptions.StringDataRightTruncationError when writing
status values longer than 20 characters (e.g. "completed_with_errors"
which is 21 characters).
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "batch_jobs",
        "status",
        existing_type=sa.String(length=20),
        type_=sa.String(length=30),
        existing_nullable=False,
        existing_server_default="pending",
    )


def downgrade() -> None:
    op.alter_column(
        "batch_jobs",
        "status",
        existing_type=sa.String(length=30),
        type_=sa.String(length=20),
        existing_nullable=False,
        existing_server_default="pending",
    )

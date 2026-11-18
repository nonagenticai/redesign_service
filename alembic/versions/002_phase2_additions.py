"""Phase 2 additions -- placeholder (already in initial schema).

Revision ID: 002
Revises: 001
Create Date: 2026-02-23

This migration is intentionally a no-op.  The following Phase 2
columns were folded into the initial migration (001) so that fresh
deployments create the full schema in a single step:

  redesign_jobs.html_validation_report  -- Enhancement 4  (deterministic HTML validation)
  redesign_jobs.input_tokens            -- Enhancement 14 (LLM token tracking)
  redesign_jobs.output_tokens           -- Enhancement 14
  redesign_jobs.estimated_cost          -- Enhancement 14
  redesign_jobs.cancelled_at            -- graceful cancellation support

If you need to migrate an older database that was created before
Phase 2, write a follow-up migration that adds these columns
conditionally.
"""

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op: Phase 2 columns are already present in revision 001.

    The columns that would have been added here are:
      - html_validation_report (JSONB)
      - input_tokens (Integer)
      - output_tokens (Integer)
      - estimated_cost (Float)
      - cancelled_at (DateTime)

    They were consolidated into the initial schema migration to keep
    the migration chain clean for new deployments.
    """
    pass


def downgrade() -> None:
    """No-op: nothing to reverse since upgrade does nothing."""
    pass

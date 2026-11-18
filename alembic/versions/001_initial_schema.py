"""Initial schema -- all tables for redesign_service.

Revision ID: 001
Revises: None
Create Date: 2026-02-23

Creates:
  - redesign_jobs
  - redesign_usage
  - redesign_variants
  - custom_styles
  - batch_jobs
  - webhook_delivery_log

Includes Phase 2 columns (html_validation_report, input_tokens,
output_tokens, estimated_cost, cancelled_at) in redesign_jobs from
the start so no follow-up ALTER TABLE is needed.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- redesign_jobs ----
    op.create_table(
        "redesign_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        # Input parameters
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("html_content", sa.Text(), nullable=True),
        sa.Column("scope", sa.String(length=20), nullable=False, server_default="full_page"),
        sa.Column("style", sa.String(length=50), nullable=False, server_default="modern"),
        sa.Column("page_type", sa.String(length=50), nullable=True),
        # Context data (JSON)
        sa.Column("critique_findings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("brand_info", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("site_analysis", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Feature 1: Prompt templates
        sa.Column("template_version", sa.String(length=20), nullable=True),
        # Feature 2: User context
        sa.Column("user_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Feature 4: A/B variants
        sa.Column("styles", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("variant_count", sa.Integer(), nullable=True),
        # Feature 5: Iteration / refinement
        sa.Column("parent_job_id", sa.String(length=36), nullable=True),
        sa.Column("root_job_id", sa.String(length=36), nullable=True),
        sa.Column("iteration_number", sa.Integer(), nullable=True),
        sa.Column("feedback_text", sa.Text(), nullable=True),
        # Feature 6: Component redesign
        sa.Column("component_target", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("component_html_path", sa.String(length=500), nullable=True),
        # Feature 7: Accessibility scoring
        sa.Column("accessibility_score", sa.Float(), nullable=True),
        sa.Column("accessibility_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Feature 8: Visual comparison
        sa.Column(
            "original_screenshot_paths", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("comparison_paths", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("diff_paths", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Feature 9: Webhooks
        sa.Column("webhook_url", sa.String(length=2048), nullable=True),
        sa.Column("webhook_secret", sa.String(length=512), nullable=True),
        # Feature 10: Batch processing
        sa.Column("batch_id", sa.String(length=36), nullable=True),
        sa.Column("priority_score", sa.Float(), nullable=True),
        # Output
        sa.Column("redesigned_html_path", sa.String(length=500), nullable=True),
        sa.Column("section_html_paths", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("screenshot_paths", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("concept_image_paths", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Phase 2 -- deterministic HTML validation (Enhancement 4)
        sa.Column("html_validation_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Phase 2 -- LLM token tracking (Enhancement 14)
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Float(), nullable=True),
        # Metadata
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("pages_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
    )
    # Indexes for redesign_jobs
    op.create_index("ix_redesign_jobs_job_id", "redesign_jobs", ["job_id"])
    op.create_index("ix_redesign_jobs_tenant_id", "redesign_jobs", ["tenant_id"])
    op.create_index("ix_redesign_jobs_status", "redesign_jobs", ["status"])
    op.create_index("ix_redesign_jobs_parent_job_id", "redesign_jobs", ["parent_job_id"])
    op.create_index("ix_redesign_jobs_root_job_id", "redesign_jobs", ["root_job_id"])
    op.create_index("ix_redesign_jobs_batch_id", "redesign_jobs", ["batch_id"])
    op.create_index("ix_redesign_jobs_status_created", "redesign_jobs", ["status", "created_at"])

    # ---- redesign_usage ----
    op.create_table(
        "redesign_usage",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pages_redesigned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("screenshots_rendered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("concept_images_generated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("llm_tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("variants_generated", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "date", name="uq_redesign_usage_tenant_date"),
    )
    op.create_index("ix_redesign_usage_tenant_id", "redesign_usage", ["tenant_id"])
    op.create_index("ix_redesign_usage_date", "redesign_usage", ["date"])

    # ---- redesign_variants ----
    op.create_table(
        "redesign_variants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("variant_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("style", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("redesigned_html_path", sa.String(length=500), nullable=True),
        sa.Column("screenshot_paths", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("concept_image_paths", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("variant_id"),
    )
    op.create_index("ix_redesign_variants_variant_id", "redesign_variants", ["variant_id"])
    op.create_index("ix_redesign_variants_job_id", "redesign_variants", ["job_id"])

    # ---- custom_styles ----
    op.create_table(
        "custom_styles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("style_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("color_palette", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("typography", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("layout", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("example_references", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("style_id"),
    )
    op.create_index("ix_custom_styles_style_id", "custom_styles", ["style_id"])
    op.create_index("ix_custom_styles_tenant_id", "custom_styles", ["tenant_id"])
    op.create_index("ix_custom_styles_tenant_slug", "custom_styles", ["tenant_id", "slug"])

    # ---- batch_jobs ----
    op.create_table(
        "batch_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("total_pages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_pages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_pages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shared_settings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id"),
    )
    op.create_index("ix_batch_jobs_batch_id", "batch_jobs", ["batch_id"])
    op.create_index("ix_batch_jobs_tenant_id", "batch_jobs", ["tenant_id"])

    # ---- webhook_delivery_log ----
    op.create_table(
        "webhook_delivery_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhook_delivery_log_job_id", "webhook_delivery_log", ["job_id"])


def downgrade() -> None:
    op.drop_table("webhook_delivery_log")
    op.drop_table("batch_jobs")
    op.drop_table("custom_styles")
    op.drop_table("redesign_variants")
    op.drop_table("redesign_usage")
    op.drop_table("redesign_jobs")

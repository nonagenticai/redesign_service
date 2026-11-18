"""SQLAlchemy ORM models for redesign_service."""

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all models."""


class RedesignJob(Base):
    """Redesign job tracking."""

    __tablename__ = "redesign_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), unique=True, nullable=False, index=True)
    tenant_id = Column(String(255), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="pending", index=True)

    # Input parameters
    url = Column(String(2048), nullable=False)
    html_content = Column(Text, nullable=True)
    scope = Column(String(20), nullable=False, default="full_page")
    style = Column(String(50), nullable=False, default="modern")
    page_type = Column(String(50), nullable=True)

    # Context data (JSON)
    critique_findings = Column(JSONB, nullable=True)
    brand_info = Column(JSONB, nullable=True)
    site_analysis = Column(JSONB, nullable=True)

    # Feature 1: Prompt templates
    template_version = Column(String(20), nullable=True)

    # Feature 2: User context
    user_context = Column(JSONB, nullable=True)

    # Feature 4: A/B variants
    styles = Column(JSONB, nullable=True)
    variant_count = Column(Integer, nullable=True)

    # Feature 5: Iteration/refinement
    parent_job_id = Column(String(36), nullable=True, index=True)
    root_job_id = Column(String(36), nullable=True, index=True)
    iteration_number = Column(Integer, nullable=True, default=0)
    feedback_text = Column(Text, nullable=True)

    # Feature 6: Component redesign
    component_target = Column(JSONB, nullable=True)
    component_html_path = Column(String(500), nullable=True)

    # Feature 7: Accessibility scoring
    accessibility_score = Column(Float, nullable=True)
    accessibility_report = Column(JSONB, nullable=True)

    # Feature 8: Visual comparison
    original_screenshot_paths = Column(JSONB, nullable=True)
    comparison_paths = Column(JSONB, nullable=True)
    diff_paths = Column(JSONB, nullable=True)

    # Feature 9: Webhooks
    webhook_url = Column(String(2048), nullable=True)
    webhook_secret = Column(String(512), nullable=True)

    # Feature 10: Batch processing
    batch_id = Column(String(36), nullable=True, index=True)
    priority_score = Column(Float, nullable=True)

    # Output
    redesigned_html_path = Column(String(500), nullable=True)
    section_html_paths = Column(JSONB, nullable=True)
    screenshot_paths = Column(JSONB, nullable=True)
    concept_image_paths = Column(JSONB, nullable=True)

    # Deterministic HTML validation (Enhancement 4)
    html_validation_report = Column(JSONB, nullable=True)

    # LLM token tracking (Enhancement 14)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    estimated_cost = Column(Float, nullable=True)

    # Metadata
    error_message = Column(Text, nullable=True)
    pages_count = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_redesign_jobs_status_created", "status", "created_at"),)


class RedesignUsage(Base):
    """Daily redesign usage aggregation per tenant."""

    __tablename__ = "redesign_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(255), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    request_count = Column(Integer, nullable=False, default=0)
    pages_redesigned = Column(Integer, nullable=False, default=0)
    screenshots_rendered = Column(Integer, nullable=False, default=0)
    concept_images_generated = Column(Integer, nullable=False, default=0)
    llm_tokens_used = Column(Integer, nullable=False, default=0)
    error_count = Column(Integer, nullable=False, default=0)
    variants_generated = Column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("tenant_id", "date", name="uq_redesign_usage_tenant_date"),)


class RedesignVariant(Base):
    """Individual style variant within an A/B test job."""

    __tablename__ = "redesign_variants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    variant_id = Column(String(36), unique=True, nullable=False, index=True)
    job_id = Column(String(36), nullable=False, index=True)
    style = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default="pending")

    redesigned_html_path = Column(String(500), nullable=True)
    screenshot_paths = Column(JSONB, nullable=True)
    concept_image_paths = Column(JSONB, nullable=True)

    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    estimated_cost = Column(Float, nullable=True)

    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


class CustomStyle(Base):
    """Tenant-scoped custom style definition."""

    __tablename__ = "custom_styles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    style_id = Column(String(36), unique=True, nullable=False, index=True)
    tenant_id = Column(String(255), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)

    color_palette = Column(JSONB, nullable=True)
    typography = Column(JSONB, nullable=True)
    layout = Column(JSONB, nullable=True)
    example_references = Column(JSONB, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())

    __table_args__ = (Index("ix_custom_styles_tenant_slug", "tenant_id", "slug"),)


class BatchJob(Base):
    """Batch redesign job for multi-page processing."""

    __tablename__ = "batch_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(36), unique=True, nullable=False, index=True)
    tenant_id = Column(String(255), nullable=False, index=True)
    status = Column(String(30), nullable=False, default="pending")

    total_pages = Column(Integer, nullable=False, default=0)
    completed_pages = Column(Integer, nullable=False, default=0)
    failed_pages = Column(Integer, nullable=False, default=0)
    shared_settings = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class WebhookDeliveryLog(Base):
    """Log of webhook delivery attempts."""

    __tablename__ = "webhook_delivery_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), nullable=False, index=True)
    attempt_number = Column(Integer, nullable=False)
    event_type = Column(String(50), nullable=False)
    request_payload = Column(JSONB, nullable=True)
    response_status = Column(Integer, nullable=True)
    response_text = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

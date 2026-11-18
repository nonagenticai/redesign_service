"""Request/response Pydantic models for redesign_service."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

# ============================================================================
# Shared Input Models
# ============================================================================


class CritiqueFindingInput(BaseModel):
    """A critique finding to address in the redesign."""

    severity: str = Field(
        default="medium", description="Finding severity: low, medium, high, critical"
    )
    title: str = Field(..., description="Short title of the finding")
    description: str = Field(..., description="Detailed description of the issue")
    recommendation: str | None = Field(default=None, description="Suggested fix")
    category: str | None = Field(
        default=None, description="Category: seo, security, a11y, performance, ux"
    )


class BrandInfoInput(BaseModel):
    """Brand identity data for consistent redesign."""

    name: str | None = Field(default=None, description="Brand/site name")
    primary_color: str = Field(default="#2563EB", description="Primary brand color (hex)")
    secondary_color: str = Field(default="#1E40AF", description="Secondary brand color (hex)")
    font_family: str | None = Field(default=None, description="Brand font family")
    logo_url: str | None = Field(default=None, description="URL to brand logo")


class SiteAnalysisInput(BaseModel):
    """Condensed site analysis context for the redesign."""

    description: str | None = Field(default=None, description="Site description")
    target_audience: list[str] = Field(default_factory=list, description="Target audience segments")
    tone: str | None = Field(default=None, description="Brand tone: professional, casual, etc.")
    visual_identity: dict | None = Field(default=None, description="Visual identity attributes")


# ============================================================================
# Feature 2: User Context
# ============================================================================


class FeaturePriorityInput(BaseModel):
    """Priority weighting for a specific feature or improvement area."""

    feature: str = Field(..., description="Feature name (e.g., 'navigation', 'search')")
    priority: str = Field(default="medium", description="Priority: low, medium, high, critical")
    notes: str | None = Field(default=None, description="Additional context")


class VisualPreferencesInput(BaseModel):
    """Visual design preferences from the user."""

    color_scheme: str | None = Field(default=None, description="light, dark, colorful, monochrome")
    layout_style: str | None = Field(default=None, description="card-based, list, grid, magazine")
    animation_level: str | None = Field(default=None, description="none, subtle, moderate, dynamic")
    image_style: str | None = Field(
        default=None, description="photography, illustration, abstract, minimal"
    )


class UserContextInput(BaseModel):
    """Rich user context for better redesign targeting."""

    description: str | None = Field(default=None, description="Site/business description")
    site_type: str | None = Field(
        default=None, description="ecommerce, saas, blog, portfolio, corporate, landing"
    )
    target_audience: list[str] | None = Field(default=None, description="Target audience segments")
    goals: list[str] | None = Field(
        default=None, description="Redesign goals (e.g., increase_conversions)"
    )
    focus_pages: list[str] | None = Field(default=None, description="URLs to prioritize in batch")
    exclude_pages: list[str] | None = Field(default=None, description="URLs to skip in batch")
    feature_priorities: list[FeaturePriorityInput] | None = Field(
        default=None, description="Feature priority list"
    )
    visual_preferences: VisualPreferencesInput | None = Field(
        default=None, description="Visual design preferences"
    )


# ============================================================================
# Feature 3: Custom Style Definitions
# ============================================================================


class ColorPaletteInput(BaseModel):
    """Color palette for a custom style."""

    primary: str | None = Field(default=None, description="Primary color hex")
    secondary: str | None = Field(default=None, description="Secondary color hex")
    accent: str | None = Field(default=None, description="Accent color hex")
    background: str | None = Field(default=None, description="Background color hex")
    text: str | None = Field(default=None, description="Text color hex")


class TypographyInput(BaseModel):
    """Typography settings for a custom style."""

    heading_font: str | None = Field(default=None, description="Heading font family")
    body_font: str | None = Field(default=None, description="Body text font family")
    scale: str | None = Field(default=None, description="Type scale: compact, default, spacious")


class LayoutPreferencesInput(BaseModel):
    """Layout preferences for a custom style."""

    max_width: str | None = Field(default=None, description="Max content width (e.g., '1200px')")
    spacing: str | None = Field(
        default=None, description="Spacing density: tight, normal, generous"
    )
    grid_columns: int | None = Field(default=None, description="Grid column count")
    border_radius: str | None = Field(
        default=None, description="Border radius: none, small, medium, large, pill"
    )


class CreateCustomStyleRequest(BaseModel):
    """Request to create a custom style definition."""

    name: str = Field(..., max_length=100, description="Style name")
    description: str | None = Field(default=None, max_length=500, description="Style description")
    color_palette: ColorPaletteInput | None = Field(default=None)
    typography: TypographyInput | None = Field(default=None)
    layout: LayoutPreferencesInput | None = Field(default=None)
    example_references: list[str] | None = Field(
        default=None, max_length=5, description="Reference site URLs"
    )


class UpdateCustomStyleRequest(BaseModel):
    """Request to update a custom style definition."""

    name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    color_palette: ColorPaletteInput | None = Field(default=None)
    typography: TypographyInput | None = Field(default=None)
    layout: LayoutPreferencesInput | None = Field(default=None)
    example_references: list[str] | None = Field(default=None, max_length=5)
    is_active: bool | None = Field(default=None)


class CustomStyleResponse(BaseModel):
    """Response for a custom style."""

    style_id: str
    name: str
    slug: str
    description: str | None = None
    color_palette: dict | None = None
    typography: dict | None = None
    layout: dict | None = None
    example_references: list[str] | None = None
    is_active: bool = True
    created_at: str | None = None


class StyleListResponse(BaseModel):
    """Response listing custom styles."""

    styles: list[CustomStyleResponse]
    count: int


class StylePreviewRequest(BaseModel):
    """Request to preview a style's effect."""

    html_snippet: str = Field(..., max_length=5000, description="HTML to preview the style on")


class StylePreviewResponse(BaseModel):
    """Response with styled HTML preview."""

    styled_html: str
    style_description: str


# ============================================================================
# Feature 6: Component Redesign
# ============================================================================


class ComponentTargetInput(BaseModel):
    """Target component for component-level redesign."""

    component_type: str = Field(
        ...,
        description="Component type: navbar, hero, footer, cta, pricing, testimonials, features, contact, sidebar",
    )
    component_selector: str | None = Field(default=None, description="Custom CSS selector override")


# ============================================================================
# Main Redesign Request (all features integrated)
# ============================================================================


class RedesignRequest(BaseModel):
    """Request body for a redesign job."""

    url: str = Field(..., description="URL of the page to redesign")
    html_content: str | None = Field(
        default=None, max_length=100000, description="Raw HTML content (if not fetching live)"
    )
    scope: str = Field(
        default="full_page",
        pattern=r"^(full_page|sections|component)$",
        description="Redesign scope",
    )
    style: str = Field(default="modern", max_length=100, description="Design style name or slug")
    page_type: str | None = Field(
        default=None, description="Page type: homepage, landing, product, etc."
    )
    critique_findings: list[CritiqueFindingInput] | None = Field(
        default=None, description="Critique findings to address"
    )
    brand: BrandInfoInput | None = Field(default=None, description="Brand identity data")
    site_analysis: SiteAnalysisInput | None = Field(
        default=None, description="Site analysis context"
    )
    generate_screenshots: bool = Field(
        default=True, description="Render screenshots of the redesign"
    )
    generate_concept_images: bool = Field(default=False, description="Generate AI concept images")

    # Feature 2: User context
    user_context: UserContextInput | None = Field(default=None, description="Rich user context")

    # Feature 4: A/B variants
    styles: list[str] | None = Field(
        default=None, description="Multiple styles for A/B variant generation (max 4)"
    )

    # Feature 6: Component redesign
    component_target: ComponentTargetInput | None = Field(
        default=None, description="Component target for scope=component"
    )

    # Feature 7: Accessibility
    run_accessibility_check: bool = Field(
        default=False, description="Run accessibility scoring after generation"
    )
    auto_fix_accessibility: bool = Field(default=False, description="Auto-fix accessibility issues")
    accessibility_threshold: float = Field(
        default=70.0, description="Minimum accessibility score (0-100)"
    )

    # Feature 9: Webhooks
    webhook_url: str | None = Field(
        default=None, max_length=2048, description="Webhook URL for job notifications"
    )
    webhook_secret: str | None = Field(
        default=None, max_length=512, description="Webhook HMAC secret"
    )

    @field_validator("styles")
    @classmethod
    def validate_styles(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            if len(v) > 4:
                raise ValueError("Maximum 4 style variants allowed")
            if len(v) != len(set(v)):
                raise ValueError("Duplicate styles not allowed")
        return v

    @model_validator(mode="after")
    def validate_component_scope(self) -> RedesignRequest:
        if self.scope == "component" and self.component_target is None:
            raise ValueError("component_target is required when scope is 'component'")
        return self


# ============================================================================
# Job Responses
# ============================================================================


class AsyncJobResponse(BaseModel):
    """Response when a redesign job is created."""

    job_id: str
    status: str = "pending"
    poll_url: str
    webhook_configured: bool = False


class ScreenshotInfo(BaseModel):
    """Screenshot file info."""

    viewport: str
    path: str
    width: int
    height: int


class AccessibilityFindingResponse(BaseModel):
    """A single accessibility finding."""

    category: str
    severity: str
    description: str
    element: str | None = None
    recommendation: str | None = None
    wcag_criterion: str | None = None


class AccessibilityCategoryResponse(BaseModel):
    """Score for an accessibility category."""

    category: str
    score: float
    findings: list[AccessibilityFindingResponse] = []


class AccessibilityScoreResponse(BaseModel):
    """Accessibility assessment results."""

    overall_score: float
    categories: list[AccessibilityCategoryResponse] = []
    findings: list[AccessibilityFindingResponse] = []
    html_was_fixed: bool = False


class VariantResult(BaseModel):
    """Result for a single A/B variant."""

    variant_id: str
    style: str
    status: str
    redesigned_html_path: str | None = None
    screenshot_paths: dict[str, str] | None = None
    error: str | None = None


class RedesignResultResponse(BaseModel):
    """Full result of a completed redesign job."""

    job_id: str
    url: str
    scope: str
    style: str
    redesigned_html_path: str | None = None
    section_html_paths: list[str] | None = None
    screenshots: dict[str, str] | None = None
    concept_image_paths: list[str] | None = None

    # Feature 4: Variants
    variants: list[VariantResult] | None = None

    # Feature 6: Component
    component_html_path: str | None = None

    # Feature 7: Accessibility
    accessibility: AccessibilityScoreResponse | None = None

    # Feature 8: Comparisons
    original_screenshots: dict[str, str] | None = None
    comparisons: dict[str, str] | None = None
    diffs: dict[str, str] | None = None

    # Enhancement 4: Deterministic HTML validation
    html_validation: dict | None = None


class IterationSummary(BaseModel):
    """Summary of a single iteration in the refinement chain."""

    job_id: str
    iteration_number: int
    status: str
    feedback: str | None = None
    created_at: str | None = None


class JobStatusResponse(BaseModel):
    """Response for job status polling."""

    job_id: str
    status: str
    url: str | None = None
    scope: str | None = None
    style: str | None = None
    created_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    result_url: str | None = None

    # Feature 5: Iteration
    iteration_number: int | None = None
    parent_job_id: str | None = None
    root_job_id: str | None = None
    refine_url: str | None = None

    # Feature 7: Accessibility
    accessibility_score: float | None = None

    # Feature 10: Batch
    batch_id: str | None = None


# ============================================================================
# Feature 4: Variant Comparison
# ============================================================================


class VariantComparisonResponse(BaseModel):
    """Side-by-side comparison of all variants for a job."""

    job_id: str
    variants: list[VariantResult]


# ============================================================================
# Feature 5: Iteration/Refinement
# ============================================================================


class RefineRequest(BaseModel):
    """Request to refine an existing redesign with feedback."""

    feedback: str = Field(..., max_length=2000, description="Textual feedback for refinement")
    generate_screenshots: bool = Field(default=True)
    generate_concept_images: bool = Field(default=False)
    focus_areas: list[str] | None = Field(
        default=None,
        description="Structured feedback areas: layout, colors, typography, content, spacing",
    )


class IterationHistoryResponse(BaseModel):
    """Full iteration history for a root job."""

    root_job_id: str
    iterations: list[IterationSummary]
    total_iterations: int


# ============================================================================
# Feature 9: Webhooks
# ============================================================================


class WebhookEventPayload(BaseModel):
    """Standard webhook event payload."""

    event: str
    job_id: str
    timestamp: str
    status: str | None = None
    error: str | None = None
    result_url: str | None = None
    batch_id: str | None = None
    variant_id: str | None = None
    accessibility_score: float | None = None


class WebhookDeliveryStatus(BaseModel):
    """Status of a webhook delivery attempt."""

    attempt_number: int
    event_type: str
    status: str
    response_status: int | None = None
    created_at: str | None = None


# ============================================================================
# Feature 10: Batch Processing
# ============================================================================


class BatchPageInput(BaseModel):
    """A single page in a batch redesign request."""

    url: str = Field(..., description="Page URL")
    page_type: str | None = Field(default=None, description="Page type")
    html_content: str | None = Field(default=None, max_length=100000)


class BatchRedesignRequest(BaseModel):
    """Request for batch multi-page redesign."""

    pages: list[BatchPageInput] = Field(
        ..., min_length=1, max_length=20, description="Pages to redesign"
    )
    style: str = Field(default="modern", max_length=100)
    scope: str = Field(default="full_page", pattern=r"^(full_page|sections)$")
    generate_screenshots: bool = Field(default=True)
    generate_concept_images: bool = Field(default=False)
    critique_findings: list[CritiqueFindingInput] | None = Field(default=None)
    brand: BrandInfoInput | None = Field(default=None)
    site_analysis: SiteAnalysisInput | None = Field(default=None)
    user_context: UserContextInput | None = Field(default=None)
    webhook_url: str | None = Field(default=None, max_length=2048)
    webhook_secret: str | None = Field(default=None, max_length=512)


class BatchPageJobInfo(BaseModel):
    """Info about a single page job within a batch."""

    job_id: str
    url: str
    page_type: str | None = None
    priority_score: float | None = None
    status: str = "pending"


class BatchJobResponse(BaseModel):
    """Response when a batch job is created."""

    batch_id: str
    status: str = "pending"
    total_pages: int
    page_jobs: list[BatchPageJobInfo]
    poll_url: str


class BatchPageStatusInfo(BaseModel):
    """Status of a single page within a batch."""

    job_id: str
    url: str
    status: str
    error: str | None = None


class BatchStatusResponse(BaseModel):
    """Status of a batch redesign job."""

    batch_id: str
    status: str
    total_pages: int
    completed_pages: int
    failed_pages: int
    page_statuses: list[BatchPageStatusInfo]


class BatchPageErrorInfo(BaseModel):
    """Error info for a failed page in a batch."""

    job_id: str
    url: str
    error: str


class BatchResultsResponse(BaseModel):
    """Results of a completed batch job."""

    batch_id: str
    status: str
    total_pages: int
    completed_pages: int
    failed_pages: int
    results: list[RedesignResultResponse]
    errors: list[BatchPageErrorInfo]


# ============================================================================
# Enhancement 2: Job Cancellation & Listing
# ============================================================================


class JobListItem(BaseModel):
    """Summary of a job in a listing."""

    job_id: str
    url: str
    status: str
    scope: str | None = None
    style: str | None = None
    page_type: str | None = None
    created_at: str | None = None
    completed_at: str | None = None


class JobListResponse(BaseModel):
    """Paginated list of jobs."""

    jobs: list[JobListItem]
    total: int
    limit: int
    offset: int


class CancelJobResponse(BaseModel):
    """Response when a job is cancelled."""

    job_id: str
    status: str = "cancelled"
    cancelled_at: str


# ============================================================================
# Enhancement 11: Batch Enhancements
# ============================================================================


class BatchListItem(BaseModel):
    """Summary of a batch in a listing."""

    batch_id: str
    status: str
    total_pages: int
    completed_pages: int
    failed_pages: int
    created_at: str | None = None


class BatchListResponse(BaseModel):
    """List of batches for a tenant."""

    batches: list[BatchListItem]
    total: int


class BatchRetryResponse(BaseModel):
    """Response when retrying failed batch pages."""

    batch_id: str
    retried_jobs: list[str]
    count: int

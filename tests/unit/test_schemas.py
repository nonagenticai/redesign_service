"""Unit tests for Pydantic request/response schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.api.schemas import (
    AccessibilityScoreResponse,
    AsyncJobResponse,
    BatchJobResponse,
    BatchListItem,
    BatchListResponse,
    BatchPageErrorInfo,
    BatchPageInput,
    BatchPageJobInfo,
    BatchPageStatusInfo,
    BatchRedesignRequest,
    BatchResultsResponse,
    BatchRetryResponse,
    BatchStatusResponse,
    BrandInfoInput,
    CancelJobResponse,
    ColorPaletteInput,
    ComponentTargetInput,
    CreateCustomStyleRequest,
    CritiqueFindingInput,
    CustomStyleResponse,
    IterationHistoryResponse,
    IterationSummary,
    JobListItem,
    JobListResponse,
    JobStatusResponse,
    LayoutPreferencesInput,
    RedesignRequest,
    RedesignResultResponse,
    RefineRequest,
    ScreenshotInfo,
    SiteAnalysisInput,
    StyleListResponse,
    StylePreviewRequest,
    StylePreviewResponse,
    TypographyInput,
    UpdateCustomStyleRequest,
    UserContextInput,
    VariantComparisonResponse,
    VariantResult,
    WebhookDeliveryStatus,
    WebhookEventPayload,
)


class TestCritiqueFindingInput:
    def test_valid(self) -> None:
        f = CritiqueFindingInput(title="Missing alt", description="Images lack alt text")
        assert f.severity == "medium"
        assert f.title == "Missing alt"

    def test_with_all_fields(self) -> None:
        f = CritiqueFindingInput(
            severity="critical",
            title="Bad contrast",
            description="Low contrast ratio",
            recommendation="Use darker text",
            category="a11y",
        )
        assert f.severity == "critical"
        assert f.category == "a11y"


class TestBrandInfoInput:
    def test_defaults(self) -> None:
        b = BrandInfoInput()
        assert b.primary_color == "#2563EB"
        assert b.secondary_color == "#1E40AF"
        assert b.name is None


class TestSiteAnalysisInput:
    def test_defaults(self) -> None:
        s = SiteAnalysisInput()
        assert s.target_audience == []
        assert s.description is None


class TestUserContextInput:
    def test_minimal(self) -> None:
        ctx = UserContextInput()
        assert ctx.site_type is None
        assert ctx.goals is None

    def test_full(self) -> None:
        ctx = UserContextInput(
            description="Online store",
            site_type="ecommerce",
            target_audience=["shoppers"],
            goals=["increase_conversions"],
            focus_pages=["https://example.com/"],
            exclude_pages=["https://example.com/admin"],
        )
        assert ctx.site_type == "ecommerce"
        assert len(ctx.target_audience) == 1


class TestRedesignRequest:
    def test_minimal_request(self) -> None:
        r = RedesignRequest(url="https://example.com")
        assert r.scope == "full_page"
        assert r.style == "modern"
        assert r.generate_screenshots is True

    def test_styles_max_4_exceeded(self) -> None:
        with pytest.raises(ValidationError, match="Maximum 4"):
            RedesignRequest(
                url="https://example.com",
                styles=["a", "b", "c", "d", "e"],
            )

    def test_styles_duplicates_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Duplicate"):
            RedesignRequest(
                url="https://example.com",
                styles=["modern", "modern"],
            )

    def test_component_scope_requires_target(self) -> None:
        with pytest.raises(ValidationError, match="component_target"):
            RedesignRequest(
                url="https://example.com",
                scope="component",
            )

    def test_component_scope_with_target(self) -> None:
        r = RedesignRequest(
            url="https://example.com",
            scope="component",
            component_target=ComponentTargetInput(component_type="navbar"),
        )
        assert r.scope == "component"
        assert r.component_target is not None
        assert r.component_target.component_type == "navbar"

    def test_invalid_scope_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RedesignRequest(url="https://example.com", scope="invalid_scope")

    def test_with_webhook(self) -> None:
        r = RedesignRequest(
            url="https://example.com",
            webhook_url="https://hooks.example.com/cb",
            webhook_secret="s3cret",  # pragma: allowlist secret
        )
        assert r.webhook_url is not None


class TestRefineRequest:
    def test_valid(self) -> None:
        r = RefineRequest(feedback="Make it bolder")
        assert r.feedback == "Make it bolder"
        assert r.generate_screenshots is True

    def test_with_focus_areas(self) -> None:
        r = RefineRequest(feedback="Improve", focus_areas=["layout", "colors"])
        assert len(r.focus_areas) == 2


class TestBatchRedesignRequest:
    def test_valid(self) -> None:
        r = BatchRedesignRequest(pages=[BatchPageInput(url="https://example.com/")])
        assert len(r.pages) == 1

    def test_empty_pages_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BatchRedesignRequest(pages=[])

    def test_sections_scope_valid(self) -> None:
        r = BatchRedesignRequest(
            pages=[BatchPageInput(url="https://example.com/")],
            scope="sections",
        )
        assert r.scope == "sections"


class TestResponseModels:
    def test_async_job_response(self) -> None:
        r = AsyncJobResponse(job_id="j1", poll_url="/api/v1/redesign/jobs/j1")
        assert r.status == "pending"
        assert r.webhook_configured is False

    def test_job_status_response(self) -> None:
        r = JobStatusResponse(job_id="j1", status="completed")
        assert r.result_url is None
        assert r.accessibility_score is None

    def test_redesign_result_response(self) -> None:
        r = RedesignResultResponse(
            job_id="j1", url="https://example.com", scope="full_page", style="modern"
        )
        assert r.variants is None
        assert r.accessibility is None

    def test_variant_result(self) -> None:
        v = VariantResult(variant_id="v1", style="bold", status="completed")
        assert v.redesigned_html_path is None

    def test_variant_comparison_response(self) -> None:
        r = VariantComparisonResponse(
            job_id="j1",
            variants=[VariantResult(variant_id="v1", style="bold", status="completed")],
        )
        assert len(r.variants) == 1

    def test_iteration_summary(self) -> None:
        s = IterationSummary(job_id="j1", iteration_number=1, status="completed")
        assert s.feedback is None

    def test_iteration_history_response(self) -> None:
        r = IterationHistoryResponse(
            root_job_id="j1",
            iterations=[IterationSummary(job_id="j1", iteration_number=0, status="completed")],
            total_iterations=1,
        )
        assert r.total_iterations == 1

    def test_cancel_job_response(self) -> None:
        r = CancelJobResponse(job_id="j1", cancelled_at="2024-01-01T00:00:00Z")
        assert r.status == "cancelled"

    def test_job_list_response(self) -> None:
        r = JobListResponse(
            jobs=[JobListItem(job_id="j1", url="https://example.com", status="completed")],
            total=1,
            limit=20,
            offset=0,
        )
        assert len(r.jobs) == 1

    def test_webhook_delivery_status(self) -> None:
        w = WebhookDeliveryStatus(attempt_number=1, event_type="job.completed", status="delivered")
        assert w.response_status is None

    def test_webhook_event_payload(self) -> None:
        p = WebhookEventPayload(
            event="job.completed", job_id="j1", timestamp="2024-01-01T00:00:00Z"
        )
        assert p.status is None

    def test_batch_job_response(self) -> None:
        r = BatchJobResponse(
            batch_id="b1",
            total_pages=2,
            page_jobs=[
                BatchPageJobInfo(job_id="j1", url="https://example.com/"),
            ],
            poll_url="/api/v1/redesign/batch/b1",
        )
        assert r.status == "pending"

    def test_batch_status_response(self) -> None:
        r = BatchStatusResponse(
            batch_id="b1",
            status="completed",
            total_pages=2,
            completed_pages=2,
            failed_pages=0,
            page_statuses=[
                BatchPageStatusInfo(job_id="j1", url="https://example.com/", status="completed")
            ],
        )
        assert r.completed_pages == 2

    def test_batch_results_response(self) -> None:
        r = BatchResultsResponse(
            batch_id="b1",
            status="completed_with_errors",
            total_pages=3,
            completed_pages=2,
            failed_pages=1,
            results=[],
            errors=[
                BatchPageErrorInfo(
                    job_id="j3", url="https://example.com/error", error="LLM timeout"
                )
            ],
        )
        assert len(r.errors) == 1

    def test_batch_list_response(self) -> None:
        r = BatchListResponse(
            batches=[
                BatchListItem(
                    batch_id="b1",
                    status="completed",
                    total_pages=3,
                    completed_pages=3,
                    failed_pages=0,
                )
            ],
            total=1,
        )
        assert r.total == 1

    def test_batch_retry_response(self) -> None:
        r = BatchRetryResponse(batch_id="b1", retried_jobs=["j1", "j2"], count=2)
        assert r.count == 2

    def test_accessibility_score_response(self) -> None:
        r = AccessibilityScoreResponse(overall_score=85.0)
        assert r.html_was_fixed is False
        assert r.categories == []

    def test_screenshot_info(self) -> None:
        s = ScreenshotInfo(
            viewport="desktop", path="/screenshots/desktop.png", width=1440, height=900
        )
        assert s.viewport == "desktop"


class TestCustomStyleSchemas:
    def test_create_custom_style_request(self) -> None:
        r = CreateCustomStyleRequest(name="My Bold Style")
        assert r.description is None
        assert r.color_palette is None

    def test_create_custom_style_with_all_fields(self) -> None:
        r = CreateCustomStyleRequest(
            name="Fancy",
            description="A fancy style",
            color_palette=ColorPaletteInput(primary="#FF0000"),
            typography=TypographyInput(heading_font="Georgia"),
            layout=LayoutPreferencesInput(max_width="1200px"),
            example_references=["https://example.com"],
        )
        assert r.color_palette is not None
        assert r.color_palette.primary == "#FF0000"

    def test_update_custom_style_request(self) -> None:
        r = UpdateCustomStyleRequest(name="Updated Name")
        assert r.name == "Updated Name"
        assert r.is_active is None

    def test_custom_style_response(self) -> None:
        r = CustomStyleResponse(style_id="s1", name="Bold", slug="bold", is_active=True)
        assert r.style_id == "s1"

    def test_style_list_response(self) -> None:
        r = StyleListResponse(styles=[], count=0)
        assert r.count == 0

    def test_style_preview_request(self) -> None:
        r = StylePreviewRequest(html_snippet="<div>Hello</div>")
        assert r.html_snippet == "<div>Hello</div>"

    def test_style_preview_response(self) -> None:
        r = StylePreviewResponse(
            styled_html="<div class='bold'>Hello</div>", style_description="Bold"
        )
        assert "bold" in r.styled_html.lower() or "bold" in r.style_description.lower()

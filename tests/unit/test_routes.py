"""Unit tests for API routes."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.api.routes import (
    _get_redesign_service,
    _get_session_factory,
    _get_storage,
    _get_tenant_id,
    _process_job_background,
    _process_refinement_background,
)

# ============================================================================
# Helper dependency tests
# ============================================================================


class TestHelperDependencies:
    def test_get_tenant_id_from_request_state(self) -> None:
        request = MagicMock()
        request.state.tenant_id = "my-tenant"
        assert _get_tenant_id(request) == "my-tenant"

    def test_get_tenant_id_missing_defaults_to_anonymous(self) -> None:
        request = MagicMock(spec=[])
        request.state = SimpleNamespace()
        assert _get_tenant_id(request) == "anonymous"

    def test_get_redesign_service(self) -> None:
        request = MagicMock()
        mock_service = MagicMock()
        request.app.state.redesign_service = mock_service
        assert _get_redesign_service(request) is mock_service

    def test_get_storage(self) -> None:
        request = MagicMock()
        mock_storage = MagicMock()
        request.app.state.storage_service = mock_storage
        assert _get_storage(request) is mock_storage

    def test_get_session_factory(self) -> None:
        request = MagicMock()
        mock_factory = MagicMock()
        request.app.state.session_factory = mock_factory
        assert _get_session_factory(request) is mock_factory


# ============================================================================
# Background task tests
# ============================================================================


class TestBackgroundTasks:
    @pytest.mark.asyncio
    async def test_process_job_background_success(self) -> None:
        service = AsyncMock()
        mock_session = AsyncMock()
        session_factory = MagicMock()
        session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        await _process_job_background(
            service, session_factory, "job-1", "tenant-1", generate_screenshots=True
        )

        service.process_job.assert_awaited_once_with(
            mock_session, "job-1", "tenant-1", generate_screenshots=True
        )

    @pytest.mark.asyncio
    async def test_process_job_background_exception_is_caught(self) -> None:
        service = AsyncMock()
        service.process_job.side_effect = RuntimeError("LLM failed")
        mock_session = AsyncMock()
        session_factory = MagicMock()
        session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        # Should not raise
        await _process_job_background(service, session_factory, "job-1", "tenant-1")

    @pytest.mark.asyncio
    async def test_process_refinement_background_success(self) -> None:
        service = AsyncMock()
        mock_session = AsyncMock()
        session_factory = MagicMock()
        session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        await _process_refinement_background(
            service, session_factory, "job-2", "tenant-1", focus_areas=["layout"]
        )

        service.process_refinement_job.assert_awaited_once_with(
            mock_session, "job-2", "tenant-1", focus_areas=["layout"]
        )

    @pytest.mark.asyncio
    async def test_process_refinement_background_exception_is_caught(self) -> None:
        service = AsyncMock()
        service.process_refinement_job.side_effect = ValueError("not found")
        mock_session = AsyncMock()
        session_factory = MagicMock()
        session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        # Should not raise
        await _process_refinement_background(service, session_factory, "job-2", "tenant-1")


# ============================================================================
# Route endpoint tests using direct function calls with mocked dependencies
# ============================================================================


class TestGetJobStatus:
    @pytest.mark.asyncio
    async def test_job_not_found(self, mock_db) -> None:
        from src.api.routes import get_job_status

        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=None):
            request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await get_job_status("nonexistent", request, mock_db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_job_found_completed(self, mock_db, sample_redesign_job) -> None:
        from src.api.routes import get_job_status

        job = sample_redesign_job(status="completed")
        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job):
            request = MagicMock()
            result = await get_job_status("test-job-123", request, mock_db)
            assert result.job_id == "test-job-123"
            assert result.status == "completed"
            assert result.result_url is not None
            assert result.refine_url is not None

    @pytest.mark.asyncio
    async def test_job_found_pending_no_result_url(self, mock_db, sample_redesign_job) -> None:
        from src.api.routes import get_job_status

        job = sample_redesign_job(status="pending")
        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job):
            request = MagicMock()
            result = await get_job_status("test-job-123", request, mock_db)
            assert result.status == "pending"
            assert result.result_url is None
            assert result.refine_url is None


class TestGetJobResult:
    @pytest.mark.asyncio
    async def test_job_not_found(self, mock_db) -> None:
        from src.api.routes import get_job_result

        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=None):
            request = MagicMock()
            request.app.state.cache_service = None
            with pytest.raises(HTTPException) as exc_info:
                await get_job_result("nonexistent", request, mock_db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_job_not_completed(self, mock_db, sample_redesign_job) -> None:
        from src.api.routes import get_job_result

        job = sample_redesign_job(status="processing")
        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job):
            request = MagicMock()
            request.app.state.cache_service = None
            with pytest.raises(HTTPException) as exc_info:
                await get_job_result("test-job-123", request, mock_db)
            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_job_completed_without_variants(self, mock_db, sample_redesign_job) -> None:
        from src.api.routes import get_job_result

        job = sample_redesign_job(
            status="completed",
            styles=None,
            accessibility_report=None,
        )
        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job):
            request = MagicMock()
            request.app.state.cache_service = None
            result = await get_job_result("test-job-123", request, mock_db)
            assert result.job_id == "test-job-123"
            assert result.variants is None
            assert result.accessibility is None

    @pytest.mark.asyncio
    async def test_job_completed_with_variants(
        self, mock_db, sample_redesign_job, sample_variant
    ) -> None:
        from src.api.routes import get_job_result

        job = sample_redesign_job(
            status="completed",
            styles=["modern", "bold"],
            accessibility_report=None,
        )
        variants = [
            sample_variant(style="modern"),
            sample_variant(variant_id="var-456", style="bold"),
        ]
        with (
            patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job),
            patch(
                "src.api.routes.JobManager.get_variants",
                new_callable=AsyncMock,
                return_value=variants,
            ),
        ):
            request = MagicMock()
            request.app.state.cache_service = None
            result = await get_job_result("test-job-123", request, mock_db)
            assert result.variants is not None
            assert len(result.variants) == 2

    @pytest.mark.asyncio
    async def test_job_completed_with_accessibility_report(
        self, mock_db, sample_redesign_job
    ) -> None:
        from src.api.routes import get_job_result

        a11y_report = {
            "overall_score": 85.0,
            "categories": [
                {
                    "category": "alt_text",
                    "score": 90.0,
                    "findings": [
                        {
                            "category": "alt_text",
                            "severity": "minor",
                            "description": "Decorative image has alt",
                        }
                    ],
                }
            ],
            "findings": [
                {
                    "category": "alt_text",
                    "severity": "minor",
                    "description": "Decorative image has alt",
                }
            ],
            "html_was_fixed": True,
        }
        job = sample_redesign_job(
            status="completed",
            styles=None,
            accessibility_report=a11y_report,
        )
        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job):
            request = MagicMock()
            request.app.state.cache_service = None
            result = await get_job_result("test-job-123", request, mock_db)
            assert result.accessibility is not None
            assert result.accessibility.overall_score == 85.0
            assert result.accessibility.html_was_fixed is True
            assert len(result.accessibility.categories) == 1

    @pytest.mark.asyncio
    async def test_job_result_from_cache(self, mock_db) -> None:
        from src.api.routes import get_job_result

        cached_result = {
            "job_id": "cached-job",
            "url": "https://example.com",
            "scope": "full_page",
            "style": "modern",
            "redesigned_html_path": "/path/to/redesign.html",
            "section_html_paths": None,
            "screenshot_paths": {"desktop": "/path/desktop.png"},
            "concept_image_paths": None,
            "component_html_path": None,
            "accessibility_score": None,
            "accessibility_report": None,
            "original_screenshot_paths": None,
            "comparison_paths": None,
            "diff_paths": None,
            "html_validation_report": None,
        }
        mock_cache = AsyncMock()
        mock_cache.get_cached_job_result = AsyncMock(return_value=cached_result)

        request = MagicMock()
        request.app.state.cache_service = mock_cache

        result = await get_job_result("cached-job", request, mock_db)
        assert result.job_id == "cached-job"
        assert result.url == "https://example.com"
        assert result.redesigned_html_path == "/path/to/redesign.html"
        assert result.screenshots == {"desktop": "/path/desktop.png"}
        mock_cache.get_cached_job_result.assert_awaited_once_with("cached-job")

    @pytest.mark.asyncio
    async def test_job_result_cache_miss_falls_through(self, mock_db, sample_redesign_job) -> None:
        from src.api.routes import get_job_result

        mock_cache = AsyncMock()
        mock_cache.get_cached_job_result = AsyncMock(return_value=None)

        job = sample_redesign_job(
            status="completed",
            styles=None,
            accessibility_report=None,
        )
        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job):
            request = MagicMock()
            request.app.state.cache_service = mock_cache
            result = await get_job_result("test-job-123", request, mock_db)
            assert result.job_id == "test-job-123"
            mock_cache.get_cached_job_result.assert_awaited_once()


class TestDownloadHtml:
    @pytest.mark.asyncio
    async def test_job_not_found(self, mock_db) -> None:
        from src.api.routes import download_html

        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=None):
            request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await download_html("nonexistent", request, mock_db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_job_not_completed(self, mock_db, sample_redesign_job) -> None:
        from src.api.routes import download_html

        job = sample_redesign_job(status="pending")
        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job):
            request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await download_html("test-job-123", request, mock_db)
            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_no_html_path(self, mock_db, sample_redesign_job) -> None:
        from src.api.routes import download_html

        job = sample_redesign_job(status="completed", redesigned_html_path=None)
        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job):
            request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await download_html("test-job-123", request, mock_db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_html_file_not_on_storage(self, mock_db, sample_redesign_job) -> None:
        from src.api.routes import download_html

        job = sample_redesign_job(status="completed")
        mock_storage = AsyncMock()
        mock_storage.retrieve_text = AsyncMock(return_value=None)

        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job):
            request = MagicMock()
            request.app.state.storage_service = mock_storage
            with pytest.raises(HTTPException) as exc_info:
                await download_html("test-job-123", request, mock_db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_html_download_success(self, mock_db, sample_redesign_job) -> None:
        from src.api.routes import download_html

        job = sample_redesign_job(status="completed")
        mock_storage = AsyncMock()
        mock_storage.retrieve_text = AsyncMock(return_value="<html>Hello</html>")

        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job):
            request = MagicMock()
            request.app.state.storage_service = mock_storage
            response = await download_html("test-job-123", request, mock_db)
            assert response.body == b"<html>Hello</html>"
            assert response.media_type == "text/html"


class TestDownloadScreenshot:
    @pytest.mark.asyncio
    async def test_job_not_found(self, mock_db) -> None:
        from src.api.routes import download_screenshot

        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=None):
            request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await download_screenshot("nonexistent", "desktop", request, mock_db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_screenshot_not_found_for_viewport(self, mock_db, sample_redesign_job) -> None:
        from src.api.routes import download_screenshot

        job = sample_redesign_job(status="completed", screenshot_paths={"mobile": "/m.png"})
        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job):
            request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await download_screenshot("test-job-123", "desktop", request, mock_db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_screenshot_download_success(self, mock_db, sample_redesign_job) -> None:
        from src.api.routes import download_screenshot

        job = sample_redesign_job(
            status="completed",
            screenshot_paths={"desktop": "/screenshots/desktop.png"},
        )
        mock_storage = AsyncMock()
        mock_storage.retrieve = AsyncMock(return_value=b"\x89PNG")

        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job):
            request = MagicMock()
            request.app.state.storage_service = mock_storage
            response = await download_screenshot("test-job-123", "desktop", request, mock_db)
            assert response.body == b"\x89PNG"
            assert response.media_type == "image/png"


class TestCompareVariants:
    @pytest.mark.asyncio
    async def test_job_not_found(self, mock_db) -> None:
        from src.api.routes import compare_variants

        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=None):
            request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await compare_variants("nonexistent", request, mock_db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_no_variants(self, mock_db, sample_redesign_job) -> None:
        from src.api.routes import compare_variants

        job = sample_redesign_job()
        with (
            patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job),
            patch(
                "src.api.routes.JobManager.get_variants",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await compare_variants("test-job-123", request, mock_db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_variants_returned(self, mock_db, sample_redesign_job, sample_variant) -> None:
        from src.api.routes import compare_variants

        job = sample_redesign_job()
        variants = [sample_variant(style="modern"), sample_variant(variant_id="v2", style="bold")]
        with (
            patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job),
            patch(
                "src.api.routes.JobManager.get_variants",
                new_callable=AsyncMock,
                return_value=variants,
            ),
        ):
            request = MagicMock()
            result = await compare_variants("test-job-123", request, mock_db)
            assert len(result.variants) == 2


class TestCancelJob:
    @pytest.mark.asyncio
    async def test_cancel_not_possible(self, mock_db) -> None:
        from src.api.routes import cancel_job

        with patch(
            "src.api.routes.JobManager.cancel_job", new_callable=AsyncMock, return_value=False
        ):
            request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await cancel_job("test-job-123", request, mock_db)
            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_cancel_success(self, mock_db, sample_redesign_job) -> None:
        from src.api.routes import cancel_job

        now = datetime(2024, 1, 15, tzinfo=UTC)
        job = sample_redesign_job(status="cancelled", cancelled_at=now)

        with (
            patch(
                "src.api.routes.JobManager.cancel_job", new_callable=AsyncMock, return_value=True
            ),
            patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job),
        ):
            request = MagicMock()
            result = await cancel_job("test-job-123", request, mock_db)
            assert result.status == "cancelled"
            assert result.job_id == "test-job-123"


class TestGetIterationHistory:
    @pytest.mark.asyncio
    async def test_job_not_found(self, mock_db) -> None:
        from src.api.routes import get_iteration_history

        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=None):
            request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await get_iteration_history("nonexistent", request, mock_db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_history_returned(self, mock_db, sample_redesign_job) -> None:
        from src.api.routes import get_iteration_history

        root_job = sample_redesign_job(root_job_id=None)
        iteration_jobs = [
            sample_redesign_job(job_id="j1", iteration_number=0, feedback_text=None),
            sample_redesign_job(job_id="j2", iteration_number=1, feedback_text="Make it bolder"),
        ]
        with (
            patch(
                "src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=root_job
            ),
            patch(
                "src.api.routes.JobManager.get_iteration_history",
                new_callable=AsyncMock,
                return_value=iteration_jobs,
            ),
        ):
            request = MagicMock()
            result = await get_iteration_history("test-job-123", request, mock_db)
            assert result.total_iterations == 2
            assert len(result.iterations) == 2


class TestDownloadComponentHtml:
    @pytest.mark.asyncio
    async def test_job_not_found(self, mock_db) -> None:
        from src.api.routes import download_component_html

        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=None):
            request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await download_component_html("nonexistent", request, mock_db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_no_component_html_path(self, mock_db, sample_redesign_job) -> None:
        from src.api.routes import download_component_html

        job = sample_redesign_job(status="completed", component_html_path=None)
        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job):
            request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await download_component_html("test-job-123", request, mock_db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_component_html_success(self, mock_db, sample_redesign_job) -> None:
        from src.api.routes import download_component_html

        job = sample_redesign_job(status="completed", component_html_path="/path/to/component.html")
        mock_storage = AsyncMock()
        mock_storage.retrieve_text = AsyncMock(return_value="<nav>Component</nav>")

        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job):
            request = MagicMock()
            request.app.state.storage_service = mock_storage
            response = await download_component_html("test-job-123", request, mock_db)
            assert response.body == b"<nav>Component</nav>"


class TestDownloadOriginalScreenshot:
    @pytest.mark.asyncio
    async def test_original_not_found(self, mock_db, sample_redesign_job) -> None:
        from src.api.routes import download_original_screenshot

        job = sample_redesign_job(original_screenshot_paths=None)
        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job):
            request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await download_original_screenshot("test-job-123", "desktop", request, mock_db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_original_screenshot_success(self, mock_db, sample_redesign_job) -> None:
        from src.api.routes import download_original_screenshot

        job = sample_redesign_job(original_screenshot_paths={"desktop": "/orig/desktop.png"})
        mock_storage = AsyncMock()
        mock_storage.retrieve = AsyncMock(return_value=b"\x89PNG")

        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job):
            request = MagicMock()
            request.app.state.storage_service = mock_storage
            response = await download_original_screenshot(
                "test-job-123", "desktop", request, mock_db
            )
            assert response.body == b"\x89PNG"


class TestDownloadComparison:
    @pytest.mark.asyncio
    async def test_comparison_not_found(self, mock_db, sample_redesign_job) -> None:
        from src.api.routes import download_comparison

        job = sample_redesign_job(comparison_paths=None)
        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job):
            request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await download_comparison("test-job-123", "desktop", request, mock_db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_comparison_success(self, mock_db, sample_redesign_job) -> None:
        from src.api.routes import download_comparison

        job = sample_redesign_job(comparison_paths={"desktop": "/comp/desktop.png"})
        mock_storage = AsyncMock()
        mock_storage.retrieve = AsyncMock(return_value=b"\x89PNG")

        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job):
            request = MagicMock()
            request.app.state.storage_service = mock_storage
            response = await download_comparison("test-job-123", "desktop", request, mock_db)
            assert response.body == b"\x89PNG"


class TestDownloadDiff:
    @pytest.mark.asyncio
    async def test_diff_not_found(self, mock_db, sample_redesign_job) -> None:
        from src.api.routes import download_diff

        job = sample_redesign_job(diff_paths=None)
        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job):
            request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await download_diff("test-job-123", "desktop", request, mock_db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_diff_success(self, mock_db, sample_redesign_job) -> None:
        from src.api.routes import download_diff

        job = sample_redesign_job(diff_paths={"desktop": "/diff/desktop.png"})
        mock_storage = AsyncMock()
        mock_storage.retrieve = AsyncMock(return_value=b"\x89DIFF")

        with patch("src.api.routes.JobManager.get_job", new_callable=AsyncMock, return_value=job):
            request = MagicMock()
            request.app.state.storage_service = mock_storage
            response = await download_diff("test-job-123", "desktop", request, mock_db)
            assert response.body == b"\x89DIFF"


class TestDownloadVariantHtml:
    @pytest.mark.asyncio
    async def test_variant_not_found(self, mock_db) -> None:
        from src.api.routes import download_variant_html

        with patch(
            "src.api.routes.JobManager.get_variants", new_callable=AsyncMock, return_value=[]
        ):
            request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await download_variant_html("job-1", "modern", request, mock_db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_variant_not_completed(self, mock_db, sample_variant) -> None:
        from src.api.routes import download_variant_html

        variant = sample_variant(status="processing", redesigned_html_path=None)
        with patch(
            "src.api.routes.JobManager.get_variants",
            new_callable=AsyncMock,
            return_value=[variant],
        ):
            request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await download_variant_html("job-1", "modern", request, mock_db)
            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_variant_html_success(self, mock_db, sample_variant) -> None:
        from src.api.routes import download_variant_html

        variant = sample_variant()
        mock_storage = AsyncMock()
        mock_storage.retrieve_text = AsyncMock(return_value="<html>Variant</html>")

        with patch(
            "src.api.routes.JobManager.get_variants",
            new_callable=AsyncMock,
            return_value=[variant],
        ):
            request = MagicMock()
            request.app.state.storage_service = mock_storage
            response = await download_variant_html("job-1", "modern", request, mock_db)
            assert response.body == b"<html>Variant</html>"


class TestListJobs:
    @pytest.mark.asyncio
    async def test_list_jobs(self, mock_db, sample_redesign_job) -> None:
        from src.api.routes import list_jobs

        jobs = [sample_redesign_job(job_id="j1"), sample_redesign_job(job_id="j2")]
        with patch(
            "src.api.routes.JobManager.list_jobs",
            new_callable=AsyncMock,
            return_value=(jobs, 2),
        ):
            request = MagicMock()
            request.state.tenant_id = "tenant-1"
            result = await list_jobs(
                request, mock_db, status=None, page_type=None, limit=20, offset=0
            )
            assert result.total == 2
            assert len(result.jobs) == 2


class TestGetBatchStatus:
    @pytest.mark.asyncio
    async def test_batch_not_found(self, mock_db) -> None:
        from src.api.routes import get_batch_status

        with patch(
            "src.services.batch_manager.BatchManager.get_batch",
            new_callable=AsyncMock,
            return_value=None,
        ):
            request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await get_batch_status("nonexistent", request, mock_db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_batch_status_returned(self, mock_db, sample_batch, sample_redesign_job) -> None:
        from src.api.routes import get_batch_status

        batch = sample_batch()
        jobs = [sample_redesign_job(job_id="j1"), sample_redesign_job(job_id="j2")]
        with (
            patch(
                "src.services.batch_manager.BatchManager.get_batch",
                new_callable=AsyncMock,
                return_value=batch,
            ),
            patch(
                "src.services.batch_manager.BatchManager.get_batch_jobs",
                new_callable=AsyncMock,
                return_value=jobs,
            ),
        ):
            request = MagicMock()
            result = await get_batch_status("batch-123", request, mock_db)
            assert result.batch_id == "batch-123"
            assert len(result.page_statuses) == 2


class TestGetBatchResults:
    @pytest.mark.asyncio
    async def test_batch_not_found(self, mock_db) -> None:
        from src.api.routes import get_batch_results

        with patch(
            "src.services.batch_manager.BatchManager.get_batch",
            new_callable=AsyncMock,
            return_value=None,
        ):
            request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await get_batch_results("nonexistent", request, mock_db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_batch_results_with_mixed_statuses(
        self, mock_db, sample_batch, sample_redesign_job
    ) -> None:
        from src.api.routes import get_batch_results

        batch = sample_batch()
        jobs = [
            sample_redesign_job(job_id="j1", status="completed"),
            sample_redesign_job(job_id="j2", status="failed", error_message="LLM timeout"),
            sample_redesign_job(job_id="j3", status="processing"),
        ]
        with (
            patch(
                "src.services.batch_manager.BatchManager.get_batch",
                new_callable=AsyncMock,
                return_value=batch,
            ),
            patch(
                "src.services.batch_manager.BatchManager.get_batch_jobs",
                new_callable=AsyncMock,
                return_value=jobs,
            ),
        ):
            request = MagicMock()
            result = await get_batch_results("batch-123", request, mock_db)
            assert len(result.results) == 1
            assert len(result.errors) == 1
            assert result.errors[0].error == "LLM timeout"

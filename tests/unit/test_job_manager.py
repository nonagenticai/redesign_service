"""Unit tests for JobManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.job_manager import JobManager


class TestJobManagerCreateJob:
    @pytest.mark.asyncio
    async def test_create_job_basic(self, mock_db) -> None:
        job = await JobManager.create_job(
            mock_db,
            tenant_id="tenant-1",
            url="https://example.com",
        )
        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()
        assert job.tenant_id == "tenant-1"
        assert job.url == "https://example.com"
        assert job.status == "pending"
        assert job.scope == "full_page"
        assert job.style == "modern"

    @pytest.mark.asyncio
    async def test_create_job_with_styles(self, mock_db) -> None:
        job = await JobManager.create_job(
            mock_db,
            tenant_id="tenant-1",
            url="https://example.com",
            styles=["modern", "bold"],
        )
        assert job.styles == ["modern", "bold"]
        assert job.variant_count == 2

    @pytest.mark.asyncio
    async def test_create_job_with_all_params(self, mock_db) -> None:
        job = await JobManager.create_job(
            mock_db,
            tenant_id="tenant-1",
            url="https://example.com",
            html_content="<html>Test</html>",
            scope="sections",
            style="bold",
            page_type="homepage",
            critique_findings=[
                {"title": "Bad contrast", "severity": "high", "description": "Low ratio"}
            ],
            brand_info={"primary_color": "#FF0000"},
            site_analysis={"tone": "professional"},
            user_context={"site_type": "ecommerce"},
            template_version="v2",
            component_target={"component_type": "navbar"},
            webhook_url="https://hooks.example.com",
            webhook_secret="secret123",  # pragma: allowlist secret
            batch_id="batch-1",
            priority_score=5.0,
        )
        assert job.scope == "sections"
        assert job.style == "bold"
        assert job.batch_id == "batch-1"
        assert job.priority_score == 5.0


class TestJobManagerCreateRefinementJob:
    @pytest.mark.asyncio
    async def test_create_refinement_job(self, mock_db, sample_redesign_job) -> None:
        sample_redesign_job(
            job_id="parent-1",
            root_job_id=None,
            iteration_number=0,
        )
        # Simulate the parent as having proper attributes for the refinement
        from src.database.models import RedesignJob

        mock_parent = MagicMock(spec=RedesignJob)
        mock_parent.job_id = "parent-1"
        mock_parent.root_job_id = None
        mock_parent.iteration_number = 0
        mock_parent.tenant_id = "tenant-1"
        mock_parent.url = "https://example.com"
        mock_parent.scope = "full_page"
        mock_parent.style = "modern"
        mock_parent.page_type = "homepage"
        mock_parent.critique_findings = None
        mock_parent.brand_info = None
        mock_parent.site_analysis = None
        mock_parent.user_context = None
        mock_parent.template_version = "v1"
        mock_parent.webhook_url = None
        mock_parent.webhook_secret = None

        job = await JobManager.create_refinement_job(
            mock_db,
            parent_job=mock_parent,
            feedback="Make it bolder",
        )
        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()
        assert job.parent_job_id == "parent-1"
        assert job.root_job_id == "parent-1"
        assert job.iteration_number == 1
        assert job.feedback_text == "Make it bolder"
        assert job.status == "pending"

    @pytest.mark.asyncio
    async def test_create_refinement_preserves_root_id(self, mock_db) -> None:
        from src.database.models import RedesignJob

        mock_parent = MagicMock(spec=RedesignJob)
        mock_parent.job_id = "child-2"
        mock_parent.root_job_id = "root-1"
        mock_parent.iteration_number = 2
        mock_parent.tenant_id = "tenant-1"
        mock_parent.url = "https://example.com"
        mock_parent.scope = "full_page"
        mock_parent.style = "modern"
        mock_parent.page_type = None
        mock_parent.critique_findings = None
        mock_parent.brand_info = None
        mock_parent.site_analysis = None
        mock_parent.user_context = None
        mock_parent.template_version = None
        mock_parent.webhook_url = None
        mock_parent.webhook_secret = None

        job = await JobManager.create_refinement_job(
            mock_db,
            parent_job=mock_parent,
            feedback="Refine more",
        )
        assert job.root_job_id == "root-1"
        assert job.iteration_number == 3


class TestJobManagerStaticMethods:
    @pytest.mark.asyncio
    async def test_get_job(self, mock_db, sample_redesign_job) -> None:
        job = sample_redesign_job()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = job
        mock_db.execute.return_value = mock_result

        result = await JobManager.get_job(mock_db, "test-job-123")
        assert result is job

    @pytest.mark.asyncio
    async def test_get_job_not_found(self, mock_db) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await JobManager.get_job(mock_db, "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_mark_processing(self, mock_db) -> None:
        await JobManager.mark_processing(mock_db, "job-1")
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mark_completed(self, mock_db) -> None:
        await JobManager.mark_completed(
            mock_db,
            "job-1",
            redesigned_html_path="/path/to/html",
            screenshot_paths={"desktop": "/d.png"},
            accessibility_score=85.0,
            accessibility_report={"overall_score": 85.0},
            original_screenshot_paths={"desktop": "/orig.png"},
            comparison_paths={"desktop": "/comp.png"},
            diff_paths={"desktop": "/diff.png"},
            component_html_path="/comp.html",
            html_validation_report={"valid": True},
            input_tokens=100,
            output_tokens=200,
            estimated_cost=0.018,
        )
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mark_completed_minimal(self, mock_db) -> None:
        await JobManager.mark_completed(mock_db, "job-1")
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mark_failed(self, mock_db) -> None:
        await JobManager.mark_failed(mock_db, "job-1", "LLM failed")
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancel_job_not_found(self, mock_db) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await JobManager.cancel_job(mock_db, "nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_job_already_completed(self, mock_db, sample_redesign_job) -> None:
        job = sample_redesign_job(status="completed")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = job
        mock_db.execute.return_value = mock_result

        result = await JobManager.cancel_job(mock_db, "test-job-123")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_job_success(self, mock_db, sample_redesign_job) -> None:
        job = sample_redesign_job(status="pending")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = job
        # First call returns the job (get_job), second is the update
        mock_db.execute = AsyncMock(side_effect=[mock_result, MagicMock()])

        result = await JobManager.cancel_job(mock_db, "test-job-123")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_cancelled_true(self, mock_db, sample_redesign_job) -> None:
        job = sample_redesign_job(status="cancelled")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = job
        mock_db.execute.return_value = mock_result

        result = await JobManager.is_cancelled(mock_db, "test-job-123")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_cancelled_false(self, mock_db, sample_redesign_job) -> None:
        job = sample_redesign_job(status="processing")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = job
        mock_db.execute.return_value = mock_result

        result = await JobManager.is_cancelled(mock_db, "test-job-123")
        assert result is False


class TestJobManagerVariants:
    @pytest.mark.asyncio
    async def test_create_variant(self, mock_db) -> None:
        variant = await JobManager.create_variant(mock_db, job_id="job-1", style="bold")
        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()
        assert variant.style == "bold"
        assert variant.status == "pending"

    @pytest.mark.asyncio
    async def test_get_variants(self, mock_db, sample_variant) -> None:
        variants = [sample_variant(style="modern"), sample_variant(variant_id="v2", style="bold")]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = variants
        mock_db.execute.return_value = mock_result

        result = await JobManager.get_variants(mock_db, "job-1")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_mark_variant_completed(self, mock_db) -> None:
        await JobManager.mark_variant_completed(
            mock_db,
            "var-1",
            redesigned_html_path="/path.html",
            screenshot_paths={"desktop": "/d.png"},
            input_tokens=50,
            output_tokens=100,
            estimated_cost=0.01,
        )
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mark_variant_failed(self, mock_db) -> None:
        await JobManager.mark_variant_failed(mock_db, "var-1", "Generation failed")
        mock_db.execute.assert_awaited_once()


class TestJobManagerListAndHistory:
    @pytest.mark.asyncio
    async def test_list_jobs(self, mock_db, sample_redesign_job) -> None:
        jobs = [sample_redesign_job(job_id="j1"), sample_redesign_job(job_id="j2")]
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 2
        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = jobs
        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_list_result])

        result_jobs, total = await JobManager.list_jobs(mock_db, "tenant-1")
        assert total == 2
        assert len(result_jobs) == 2

    @pytest.mark.asyncio
    async def test_list_jobs_with_filters(self, mock_db, sample_redesign_job) -> None:
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0
        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_list_result])

        result_jobs, total = await JobManager.list_jobs(
            mock_db, "tenant-1", status="completed", page_type="homepage", limit=10, offset=5
        )
        assert total == 0
        assert result_jobs == []

    @pytest.mark.asyncio
    async def test_get_iteration_history(self, mock_db, sample_redesign_job) -> None:
        jobs = [
            sample_redesign_job(job_id="j1", iteration_number=0),
            sample_redesign_job(job_id="j2", iteration_number=1),
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = jobs
        mock_db.execute.return_value = mock_result

        result = await JobManager.get_iteration_history(mock_db, "j1")
        assert len(result) == 2

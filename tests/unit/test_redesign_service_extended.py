"""Extended unit tests for RedesignService orchestration."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.redesign_service import RedesignService


def _make_service(
    storage=None,
    html_gen=None,
    concept_gen=None,
    a11y_scorer=None,
    webhook=None,
    component_extractor=None,
    cache_service=None,
) -> RedesignService:
    svc = RedesignService.__new__(RedesignService)
    svc._storage = storage or MagicMock()
    svc._html_gen = html_gen or AsyncMock()
    svc._concept_gen = concept_gen or AsyncMock()
    svc._a11y_scorer = a11y_scorer
    svc._webhook = webhook
    svc._component_extractor = component_extractor or MagicMock()
    svc._cache = cache_service
    return svc


def _make_job(**overrides):
    defaults = {
        "job_id": "job-1",
        "tenant_id": "tenant-1",
        "status": "pending",
        "url": "https://example.com",
        "html_content": "<html>Original</html>",
        "scope": "full_page",
        "style": "modern",
        "page_type": "homepage",
        "critique_findings": None,
        "brand_info": None,
        "site_analysis": None,
        "user_context": None,
        "template_version": "v1",
        "styles": None,
        "variant_count": None,
        "parent_job_id": None,
        "root_job_id": None,
        "iteration_number": 0,
        "feedback_text": None,
        "component_target": None,
        "component_html_path": None,
        "accessibility_score": None,
        "accessibility_report": None,
        "webhook_url": None,
        "webhook_secret": None,
        "batch_id": None,
        "priority_score": None,
        "redesigned_html_path": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestRedesignServiceInit:
    def test_init(self) -> None:
        storage = MagicMock()
        html_gen = MagicMock()
        concept_gen = MagicMock()
        svc = RedesignService(storage, html_gen, concept_gen)
        assert svc._storage is storage
        assert svc._html_gen is html_gen
        assert svc._concept_gen is concept_gen
        assert svc._webhook is None
        assert svc._a11y_scorer is None
        assert svc._cache is None


class TestCreateJob:
    @pytest.mark.asyncio
    async def test_create_job(self, mock_db) -> None:
        svc = _make_service()
        mock_job = _make_job(job_id="new-job")

        with patch(
            "src.services.redesign_service.JobManager.create_job",
            new_callable=AsyncMock,
            return_value=mock_job,
        ):
            job_id = await svc.create_job(
                mock_db,
                tenant_id="tenant-1",
                url="https://example.com",
                scope="full_page",
            )
            assert job_id == "new-job"


class TestProcessJobFullPage:
    @pytest.mark.asyncio
    async def test_full_page_basic(self, mock_db) -> None:
        from pathlib import Path

        from src.services.html_generator import LLMResult

        job = _make_job(scope="full_page")
        mock_storage = MagicMock()
        mock_storage.store_html = AsyncMock(return_value="/path/redesign.html")
        mock_storage.retrieve_text = AsyncMock(return_value="<html>Redesigned</html>")
        mock_storage.get_job_dir.return_value = Path("/tmp/job-1")

        llm_result = LLMResult(text="<html>Redesigned</html>", input_tokens=100, output_tokens=200)
        mock_html_gen = AsyncMock()
        mock_html_gen.generate_full_page = AsyncMock(return_value=llm_result)
        mock_html_gen._model = "claude-test"

        mock_concept_gen = AsyncMock()
        mock_concept_gen.is_available = AsyncMock(return_value=False)

        svc = _make_service(
            storage=mock_storage,
            html_gen=mock_html_gen,
            concept_gen=mock_concept_gen,
        )

        with (
            patch(
                "src.services.redesign_service.JobManager.get_job",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch(
                "src.services.redesign_service.JobManager.mark_processing", new_callable=AsyncMock
            ),
            patch(
                "src.services.redesign_service.JobManager.mark_completed", new_callable=AsyncMock
            ),
            patch("src.services.redesign_service.JobManager.record_usage", new_callable=AsyncMock),
            patch(
                "src.services.redesign_service.JobManager.is_cancelled",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch("src.services.redesign_service.resolve_context", return_value=MagicMock()),
            patch(
                "src.services.html_validator.HtmlValidator.validate",
                return_value=MagicMock(to_dict=MagicMock(return_value={})),
            ),
        ):
            await svc.process_job(
                mock_db,
                "job-1",
                "tenant-1",
                generate_screenshots=False,
                generate_concept_images=False,
            )
            mock_html_gen.generate_full_page.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_process_job_not_found(self, mock_db) -> None:
        svc = _make_service()
        with patch(
            "src.services.redesign_service.JobManager.get_job",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(ValueError, match="Job not found"):
                await svc.process_job(mock_db, "nonexistent", "tenant-1")

    @pytest.mark.asyncio
    async def test_process_job_cancelled_early(self, mock_db) -> None:
        from pathlib import Path

        job = _make_job()
        mock_storage = MagicMock()
        mock_storage.get_job_dir.return_value = Path("/tmp/job-1")

        svc = _make_service(storage=mock_storage)

        with (
            patch(
                "src.services.redesign_service.JobManager.get_job",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch(
                "src.services.redesign_service.JobManager.mark_processing", new_callable=AsyncMock
            ),
            patch(
                "src.services.redesign_service.JobManager.is_cancelled",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            # Should return early without error
            await svc.process_job(mock_db, "job-1", "tenant-1")

    @pytest.mark.asyncio
    async def test_process_job_with_html_from_cache(self, mock_db) -> None:
        from pathlib import Path

        from src.services.html_generator import LLMResult

        job = _make_job(html_content=None)
        mock_storage = MagicMock()
        mock_storage.store_html = AsyncMock(return_value="/path/redesign.html")
        mock_storage.retrieve_text = AsyncMock(return_value="<html>Cached</html>")
        mock_storage.get_job_dir.return_value = Path("/tmp/job-1")

        llm_result = LLMResult(text="<html>Redesigned</html>", input_tokens=50, output_tokens=100)
        mock_html_gen = AsyncMock()
        mock_html_gen.generate_full_page = AsyncMock(return_value=llm_result)
        mock_html_gen._model = "claude-test"

        mock_cache = AsyncMock()
        mock_cache.get_cached_html = AsyncMock(return_value="<html>Cached</html>")
        mock_cache.get_cached_style_description = AsyncMock(return_value=None)

        mock_concept_gen = AsyncMock()
        mock_concept_gen.is_available = AsyncMock(return_value=False)

        svc = _make_service(
            storage=mock_storage,
            html_gen=mock_html_gen,
            concept_gen=mock_concept_gen,
            cache_service=mock_cache,
        )

        with (
            patch(
                "src.services.redesign_service.JobManager.get_job",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch(
                "src.services.redesign_service.JobManager.mark_processing", new_callable=AsyncMock
            ),
            patch(
                "src.services.redesign_service.JobManager.mark_completed", new_callable=AsyncMock
            ),
            patch("src.services.redesign_service.JobManager.record_usage", new_callable=AsyncMock),
            patch(
                "src.services.redesign_service.JobManager.is_cancelled",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch("src.services.redesign_service.resolve_context", return_value=MagicMock()),
        ):
            await svc.process_job(mock_db, "job-1", "tenant-1", generate_screenshots=False)
            mock_cache.get_cached_html.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_process_job_error_marks_failed(self, mock_db) -> None:
        from pathlib import Path

        job = _make_job()
        mock_storage = MagicMock()
        mock_storage.get_job_dir.return_value = Path("/tmp/job-1")
        mock_html_gen = AsyncMock()
        mock_html_gen.generate_full_page = AsyncMock(side_effect=RuntimeError("LLM error"))
        mock_html_gen._model = "claude-test"
        mock_concept_gen = AsyncMock()
        mock_concept_gen.is_available = AsyncMock(return_value=False)

        svc = _make_service(
            storage=mock_storage,
            html_gen=mock_html_gen,
            concept_gen=mock_concept_gen,
        )

        with (
            patch(
                "src.services.redesign_service.JobManager.get_job",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch(
                "src.services.redesign_service.JobManager.mark_processing", new_callable=AsyncMock
            ),
            patch(
                "src.services.redesign_service.JobManager.mark_failed", new_callable=AsyncMock
            ) as mock_mark_failed,
            patch("src.services.redesign_service.JobManager.record_usage", new_callable=AsyncMock),
            patch(
                "src.services.redesign_service.JobManager.is_cancelled",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch("src.services.redesign_service.resolve_context", return_value=MagicMock()),
        ):
            with pytest.raises(RuntimeError):
                await svc.process_job(mock_db, "job-1", "tenant-1", generate_screenshots=False)
            mock_mark_failed.assert_awaited_once()


class TestProcessJobSections:
    @pytest.mark.asyncio
    async def test_sections_with_analysis(self, mock_db) -> None:
        from pathlib import Path

        job = _make_job(
            scope="sections",
            site_analysis={
                "content_sections": [
                    {"section_type": "hero", "heading": "Welcome"},
                    {"section_type": "cta", "heading": "Sign Up"},
                ]
            },
        )
        mock_storage = MagicMock()
        mock_storage.store_html = AsyncMock(return_value="/path/section.html")
        mock_storage.retrieve_text = AsyncMock(return_value="<html>Redesigned</html>")
        mock_storage.get_job_dir.return_value = Path("/tmp/job-1")

        mock_html_gen = AsyncMock()
        mock_html_gen.generate_sections = AsyncMock(
            return_value={"hero": "<section>Hero</section>", "cta": "<section>CTA</section>"}
        )
        mock_html_gen.compose_section_page = MagicMock(return_value="<html>Full</html>")
        mock_html_gen._model = "claude-test"

        mock_concept_gen = AsyncMock()
        mock_concept_gen.is_available = AsyncMock(return_value=False)

        svc = _make_service(
            storage=mock_storage,
            html_gen=mock_html_gen,
            concept_gen=mock_concept_gen,
        )

        with (
            patch(
                "src.services.redesign_service.JobManager.get_job",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch(
                "src.services.redesign_service.JobManager.mark_processing", new_callable=AsyncMock
            ),
            patch(
                "src.services.redesign_service.JobManager.mark_completed", new_callable=AsyncMock
            ),
            patch("src.services.redesign_service.JobManager.record_usage", new_callable=AsyncMock),
            patch(
                "src.services.redesign_service.JobManager.is_cancelled",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch("src.services.redesign_service.resolve_context", return_value=MagicMock()),
        ):
            await svc.process_job(mock_db, "job-1", "tenant-1", generate_screenshots=False)
            mock_html_gen.generate_sections.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sections_no_analysis_falls_back_to_full_page(self, mock_db) -> None:
        from pathlib import Path

        from src.services.html_generator import LLMResult

        job = _make_job(scope="sections", site_analysis=None)
        mock_storage = MagicMock()
        mock_storage.store_html = AsyncMock(return_value="/path/redesign.html")
        mock_storage.get_job_dir.return_value = Path("/tmp/job-1")

        llm_result = LLMResult(text="<html>Full Page</html>", input_tokens=50, output_tokens=100)
        mock_html_gen = AsyncMock()
        mock_html_gen.generate_full_page = AsyncMock(return_value=llm_result)
        mock_html_gen._model = "claude-test"

        mock_concept_gen = AsyncMock()
        mock_concept_gen.is_available = AsyncMock(return_value=False)

        svc = _make_service(
            storage=mock_storage,
            html_gen=mock_html_gen,
            concept_gen=mock_concept_gen,
        )

        with (
            patch(
                "src.services.redesign_service.JobManager.get_job",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch(
                "src.services.redesign_service.JobManager.mark_processing", new_callable=AsyncMock
            ),
            patch(
                "src.services.redesign_service.JobManager.mark_completed", new_callable=AsyncMock
            ),
            patch("src.services.redesign_service.JobManager.record_usage", new_callable=AsyncMock),
            patch(
                "src.services.redesign_service.JobManager.is_cancelled",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch("src.services.redesign_service.resolve_context", return_value=MagicMock()),
        ):
            await svc.process_job(mock_db, "job-1", "tenant-1", generate_screenshots=False)
            mock_html_gen.generate_full_page.assert_awaited_once()


class TestProcessJobComponent:
    @pytest.mark.asyncio
    async def test_component_scope(self, mock_db) -> None:
        from pathlib import Path

        from src.services.html_generator import LLMResult

        job = _make_job(
            scope="component",
            component_target={"component_type": "navbar", "component_selector": "nav.main"},
        )
        mock_storage = MagicMock()
        mock_storage.store_html = AsyncMock(return_value="/path/component.html")
        mock_storage.get_job_dir.return_value = Path("/tmp/job-1")

        llm_result = LLMResult(text="<nav>New Nav</nav>", input_tokens=50, output_tokens=100)
        mock_html_gen = AsyncMock()
        mock_html_gen.generate_component = AsyncMock(return_value=llm_result)
        mock_html_gen._model = "claude-test"

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = ("<nav>Old</nav>", "nav-id")
        mock_extractor.reinject.return_value = "<html><nav>New Nav</nav></html>"

        mock_concept_gen = AsyncMock()
        mock_concept_gen.is_available = AsyncMock(return_value=False)

        svc = _make_service(
            storage=mock_storage,
            html_gen=mock_html_gen,
            concept_gen=mock_concept_gen,
            component_extractor=mock_extractor,
        )

        with (
            patch(
                "src.services.redesign_service.JobManager.get_job",
                new_callable=AsyncMock,
                return_value=job,
            ),
            patch(
                "src.services.redesign_service.JobManager.mark_processing", new_callable=AsyncMock
            ),
            patch(
                "src.services.redesign_service.JobManager.mark_completed", new_callable=AsyncMock
            ),
            patch("src.services.redesign_service.JobManager.record_usage", new_callable=AsyncMock),
            patch(
                "src.services.redesign_service.JobManager.is_cancelled",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch("src.services.redesign_service.resolve_context", return_value=MagicMock()),
        ):
            await svc.process_job(mock_db, "job-1", "tenant-1", generate_screenshots=False)
            mock_html_gen.generate_component.assert_awaited_once()
            mock_extractor.reinject.assert_called_once()


class TestCreateRefinementJob:
    @pytest.mark.asyncio
    async def test_create_refinement_job_success(self, mock_db) -> None:
        parent = _make_job(job_id="parent-1", status="completed", root_job_id=None)
        child = _make_job(job_id="child-1")

        svc = _make_service()

        with (
            patch(
                "src.services.redesign_service.JobManager.get_job",
                new_callable=AsyncMock,
                return_value=parent,
            ),
            patch(
                "src.services.redesign_service.JobManager.get_iteration_history",
                new_callable=AsyncMock,
                return_value=[parent],
            ),
            patch(
                "src.services.redesign_service.JobManager.create_refinement_job",
                new_callable=AsyncMock,
                return_value=child,
            ),
        ):
            job_id = await svc.create_refinement_job(mock_db, "parent-1", "Make bolder")
            assert job_id == "child-1"

    @pytest.mark.asyncio
    async def test_create_refinement_parent_not_found(self, mock_db) -> None:
        svc = _make_service()
        with patch(
            "src.services.redesign_service.JobManager.get_job",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(ValueError, match="Parent job not found"):
                await svc.create_refinement_job(mock_db, "nonexistent", "Feedback")

    @pytest.mark.asyncio
    async def test_create_refinement_parent_not_completed(self, mock_db) -> None:
        parent = _make_job(status="processing")
        svc = _make_service()
        with patch(
            "src.services.redesign_service.JobManager.get_job",
            new_callable=AsyncMock,
            return_value=parent,
        ):
            with pytest.raises(ValueError, match="not completed"):
                await svc.create_refinement_job(mock_db, "parent-1", "Feedback")

    @pytest.mark.asyncio
    async def test_create_refinement_max_iterations(self, mock_db) -> None:
        parent = _make_job(status="completed", root_job_id=None)
        svc = _make_service()
        # Create 10 iterations to exceed the limit
        history = [_make_job(job_id=f"j{i}") for i in range(10)]

        with (
            patch(
                "src.services.redesign_service.JobManager.get_job",
                new_callable=AsyncMock,
                return_value=parent,
            ),
            patch(
                "src.services.redesign_service.JobManager.get_iteration_history",
                new_callable=AsyncMock,
                return_value=history,
            ),
        ):
            with pytest.raises(ValueError, match="Maximum iterations"):
                await svc.create_refinement_job(mock_db, "parent-1", "Feedback")


class TestProcessRefinementJob:
    @pytest.mark.asyncio
    async def test_process_refinement_success(self, mock_db) -> None:
        from pathlib import Path

        from src.services.html_generator import LLMResult

        job = _make_job(
            job_id="refine-1",
            parent_job_id="parent-1",
            feedback_text="Make it bolder",
        )
        parent = _make_job(
            job_id="parent-1",
            redesigned_html_path="/path/parent.html",
        )

        mock_storage = MagicMock()
        mock_storage.store_html = AsyncMock(return_value="/path/refined.html")
        mock_storage.retrieve_text = AsyncMock(return_value="<html>Previous</html>")
        mock_storage.get_job_dir.return_value = Path("/tmp/refine-1")

        llm_result = LLMResult(text="<html>Refined</html>", input_tokens=80, output_tokens=150)
        mock_html_gen = AsyncMock()
        mock_html_gen.refine_full_page = AsyncMock(return_value=llm_result)
        mock_html_gen._model = "claude-test"

        svc = _make_service(storage=mock_storage, html_gen=mock_html_gen)

        with (
            patch(
                "src.services.redesign_service.JobManager.get_job",
                new_callable=AsyncMock,
                side_effect=[job, parent],
            ),
            patch(
                "src.services.redesign_service.JobManager.mark_processing", new_callable=AsyncMock
            ),
            patch(
                "src.services.redesign_service.JobManager.mark_completed", new_callable=AsyncMock
            ),
            patch("src.services.redesign_service.JobManager.record_usage", new_callable=AsyncMock),
        ):
            await svc.process_refinement_job(
                mock_db, "refine-1", "tenant-1", generate_screenshots=False
            )
            mock_html_gen.refine_full_page.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_process_refinement_not_found(self, mock_db) -> None:
        svc = _make_service()
        with patch(
            "src.services.redesign_service.JobManager.get_job",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(ValueError, match="Job not found"):
                await svc.process_refinement_job(mock_db, "nonexistent", "tenant-1")

    @pytest.mark.asyncio
    async def test_process_refinement_error_marks_failed(self, mock_db) -> None:
        from pathlib import Path

        job = _make_job(
            job_id="refine-err",
            parent_job_id="parent-1",
            feedback_text="Fix it",
        )
        parent = _make_job(job_id="parent-1", redesigned_html_path="/path/parent.html")

        mock_storage = MagicMock()
        mock_storage.retrieve_text = AsyncMock(return_value="<html>Previous</html>")
        mock_storage.get_job_dir.return_value = Path("/tmp/refine-err")

        mock_html_gen = AsyncMock()
        mock_html_gen.refine_full_page = AsyncMock(side_effect=RuntimeError("LLM down"))
        mock_html_gen._model = "claude-test"

        svc = _make_service(storage=mock_storage, html_gen=mock_html_gen)

        with (
            patch(
                "src.services.redesign_service.JobManager.get_job",
                new_callable=AsyncMock,
                side_effect=[job, parent],
            ),
            patch(
                "src.services.redesign_service.JobManager.mark_processing", new_callable=AsyncMock
            ),
            patch(
                "src.services.redesign_service.JobManager.mark_failed", new_callable=AsyncMock
            ) as mock_failed,
            patch("src.services.redesign_service.JobManager.record_usage", new_callable=AsyncMock),
        ):
            with pytest.raises(RuntimeError):
                await svc.process_refinement_job(
                    mock_db, "refine-err", "tenant-1", generate_screenshots=False
                )
            mock_failed.assert_awaited_once()


class TestDispatchWebhook:
    @pytest.mark.asyncio
    async def test_no_dispatcher_returns(self, mock_db) -> None:
        svc = _make_service(webhook=None)
        job = _make_job()
        # Should return without error
        await svc._dispatch_webhook(mock_db, job, "job.completed")

    @pytest.mark.asyncio
    async def test_no_webhook_url_returns(self, mock_db) -> None:
        mock_dispatcher = AsyncMock()
        svc = _make_service(webhook=mock_dispatcher)
        job = _make_job(webhook_url=None)
        await svc._dispatch_webhook(mock_db, job, "job.completed")
        mock_dispatcher.dispatch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dispatch_success(self, mock_db) -> None:
        mock_dispatcher = AsyncMock()
        mock_dispatcher.dispatch = AsyncMock()
        svc = _make_service(webhook=mock_dispatcher)
        job = _make_job(webhook_url="https://hooks.example.com", webhook_secret="secret")
        await svc._dispatch_webhook(mock_db, job, "job.completed")
        mock_dispatcher.dispatch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatch_error_doesnt_raise(self, mock_db) -> None:
        mock_dispatcher = AsyncMock()
        mock_dispatcher.dispatch = AsyncMock(side_effect=Exception("Network error"))
        svc = _make_service(webhook=mock_dispatcher)
        job = _make_job(webhook_url="https://hooks.example.com")
        # Should not raise
        await svc._dispatch_webhook(mock_db, job, "job.completed")


class TestCheckCancelled:
    @pytest.mark.asyncio
    async def test_not_cancelled(self, mock_db) -> None:
        svc = _make_service()
        with patch(
            "src.services.redesign_service.JobManager.is_cancelled",
            new_callable=AsyncMock,
            return_value=False,
        ):
            assert await svc._check_cancelled(mock_db, "job-1") is False

    @pytest.mark.asyncio
    async def test_cancelled(self, mock_db) -> None:
        svc = _make_service()
        with patch(
            "src.services.redesign_service.JobManager.is_cancelled",
            new_callable=AsyncMock,
            return_value=True,
        ):
            assert await svc._check_cancelled(mock_db, "job-1") is True


class TestCreateBatch:
    @pytest.mark.asyncio
    async def test_create_batch(self, mock_db) -> None:
        svc = _make_service()
        mock_batch = SimpleNamespace(batch_id="batch-1")
        mock_job1 = _make_job(job_id="j1")
        mock_job2 = _make_job(job_id="j2")

        with (
            patch(
                "src.services.redesign_service.BatchManager.create_batch",
                new_callable=AsyncMock,
                return_value=mock_batch,
            ),
            patch(
                "src.services.redesign_service.JobManager.create_job",
                new_callable=AsyncMock,
                side_effect=[mock_job1, mock_job2],
            ),
            patch(
                "src.services.redesign_service.select_pages",
                return_value=[
                    {"url": "https://example.com/", "page_type": "homepage"},
                    {"url": "https://example.com/about", "page_type": "about"},
                ],
            ),
        ):
            batch_id, page_jobs = await svc.create_batch(
                mock_db,
                tenant_id="tenant-1",
                pages=[
                    {"url": "https://example.com/", "page_type": "homepage"},
                    {"url": "https://example.com/about", "page_type": "about"},
                ],
            )
            assert batch_id == "batch-1"
            assert len(page_jobs) == 2

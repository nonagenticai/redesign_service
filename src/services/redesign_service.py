"""Core redesign orchestration service."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import Settings, get_settings
from src.database.models import RedesignJob
from src.services.accessibility_scorer import AccessibilityScorer
from src.services.batch_manager import BatchManager
from src.services.cache_service import CacheService
from src.services.comparison_generator import generate_comparisons
from src.services.component_extractor import ComponentExtractor
from src.services.concept_image_generator import ConceptImageGenerator
from src.services.context_resolver import ResolvedContext, resolve_context
from src.services.html_generator import HtmlGenerator, estimate_cost
from src.services.job_manager import JobManager
from src.services.page_selector import select_pages
from src.services.screenshot_renderer import (
    capture_url_screenshots,
    render_from_html_string,
)
from src.services.storage_service import StorageService
from src.services.style_manager import StyleManager
from src.services.webhook_dispatcher import WebhookDispatcher

logger = logging.getLogger(__name__)


class RedesignService:
    """Orchestrates HTML redesign, screenshot rendering, and concept images."""

    def __init__(
        self,
        storage: StorageService,
        html_generator: HtmlGenerator,
        concept_generator: ConceptImageGenerator,
        accessibility_scorer: AccessibilityScorer | None = None,
        webhook_dispatcher: WebhookDispatcher | None = None,
        component_extractor: ComponentExtractor | None = None,
        cache_service: CacheService | None = None,
    ) -> None:
        self._storage = storage
        self._html_gen = html_generator
        self._concept_gen = concept_generator
        self._a11y_scorer = accessibility_scorer
        self._webhook = webhook_dispatcher
        self._component_extractor = component_extractor or ComponentExtractor()
        self._cache = cache_service

    async def create_job(
        self,
        db: AsyncSession,
        *,
        tenant_id: str,
        url: str,
        html_content: str | None = None,
        scope: str = "full_page",
        style: str = "modern",
        page_type: str | None = None,
        critique_findings: list[dict] | None = None,
        brand_info: dict | None = None,
        site_analysis: dict | None = None,
        user_context: dict | None = None,
        styles: list[str] | None = None,
        component_target: dict | None = None,
        webhook_url: str | None = None,
        webhook_secret: str | None = None,
    ) -> str:
        """Create an async redesign job, returns job_id."""
        settings = get_settings()
        job = await JobManager.create_job(
            db,
            tenant_id=tenant_id,
            url=url,
            html_content=html_content,
            scope=scope,
            style=style,
            page_type=page_type,
            critique_findings=critique_findings,
            brand_info=brand_info,
            site_analysis=site_analysis,
            user_context=user_context,
            template_version=settings.templates.version,
            styles=styles,
            component_target=component_target,
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
        )
        return job.job_id

    async def process_job(
        self,
        db: AsyncSession,
        job_id: str,
        tenant_id: str,
        *,
        run_accessibility_check: bool = False,
        auto_fix_accessibility: bool = False,
        accessibility_threshold: float = 70.0,
        generate_screenshots: bool = True,
        generate_concept_images: bool = False,
    ) -> None:
        """Process a pending redesign job."""
        job = await JobManager.get_job(db, job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")

        await JobManager.mark_processing(db, job_id)
        await db.commit()

        settings = get_settings()
        screenshots_count = 0
        concept_count = 0
        variants_count = 0
        total_input_tokens = 0
        total_output_tokens = 0

        try:
            # Dispatch job.started webhook
            await self._dispatch_webhook(db, job, "job.started")

            # Check cancellation
            if await self._check_cancelled(db, job_id):
                return

            # 1. Fetch HTML if not provided (check cache first)
            html = job.html_content
            if not html and self._cache:
                html = await self._cache.get_cached_html(job.url)
            if not html:
                html = await self._fetch_page_html(job.url)
                if self._cache:
                    await self._cache.cache_html(job.url, html)

            # 2. Resolve context
            resolved_ctx = resolve_context(
                user_context=job.user_context,
                site_analysis=job.site_analysis,
                brand=job.brand_info,
                html=html,
            )

            # 3. Resolve custom style description if needed (check cache first)
            style_description: str | None = None
            if job.style not in ("modern", "minimalist", "bold", "elegant"):
                if self._cache:
                    style_description = await self._cache.get_cached_style_description(job.style)
                if style_description is None:
                    custom_style = await StyleManager.get_style_by_slug(db, tenant_id, job.style)
                    if custom_style:
                        style_description = StyleManager.resolve_style_description(custom_style)
                        if self._cache and style_description:
                            await self._cache.cache_style_description(
                                custom_style.style_id, style_description
                            )

            # Check cancellation before LLM call
            if await self._check_cancelled(db, job_id):
                return

            # 4. Handle A/B variants
            if job.styles and len(job.styles) > 1:
                await self._process_variants(
                    db,
                    job,
                    html,
                    resolved_ctx,
                    settings,
                    generate_screenshots=generate_screenshots,
                )
                variants_count = len(job.styles)

                # Mark completed with first variant's outputs
                variants = await JobManager.get_variants(db, job_id)
                first_completed = next((v for v in variants if v.status == "completed"), None)
                await JobManager.mark_completed(
                    db,
                    job_id,
                    redesigned_html_path=first_completed.redesigned_html_path
                    if first_completed
                    else None,
                    screenshot_paths=first_completed.screenshot_paths if first_completed else None,
                    pages_count=1,
                )
                await JobManager.record_usage(
                    db,
                    tenant_id=tenant_id,
                    pages_redesigned=1,
                    variants_generated=variants_count,
                )
                await self._dispatch_webhook(db, job, "job.completed")

                # Cache completed variant job result in Redis
                await self._cache_job_result(
                    job_id,
                    url=job.url,
                    scope=job.scope,
                    style=job.style,
                    redesigned_html_path=first_completed.redesigned_html_path
                    if first_completed
                    else None,
                    screenshot_paths=first_completed.screenshot_paths if first_completed else None,
                )

                await db.commit()
                return

            # 5. Generate redesigned HTML
            job_dir = self._storage.get_job_dir(job_id)
            redesigned_html_path: str | None = None
            section_html_paths: list[str] | None = None
            component_html_path: str | None = None
            redesigned_html: str = ""

            if job.scope == "component" and job.component_target:
                # Component-level redesign
                component_type = job.component_target.get("component_type", "unknown")
                component_selector = job.component_target.get("component_selector")

                component_html, _component_id = self._component_extractor.extract(
                    html, component_type, component_selector
                )
                llm_result = await self._html_gen.generate_component(
                    url=job.url,
                    component_html=component_html,
                    component_type=component_type,
                    page_type=job.page_type,
                    style=job.style,
                    findings=job.critique_findings,
                    brand=job.brand_info,
                    site_analysis=job.site_analysis,
                    style_description=style_description,
                    context=resolved_ctx,
                )
                total_input_tokens += llm_result.input_tokens
                total_output_tokens += llm_result.output_tokens
                # Store component HTML separately
                component_html_path = await self._storage.store_html(
                    job_id, llm_result.text, "component.html"
                )
                # Reinject into full page
                composite = self._component_extractor.reinject(
                    html, component_type, llm_result.text, component_selector
                )
                redesigned_html_path = await self._storage.store_html(
                    job_id, composite, "redesign.html"
                )
                redesigned_html = composite

            elif job.scope == "full_page":
                llm_result = await self._html_gen.generate_full_page(
                    url=job.url,
                    html=html,
                    page_type=job.page_type,
                    style=job.style,
                    findings=job.critique_findings,
                    brand=job.brand_info,
                    site_analysis=job.site_analysis,
                    style_description=style_description,
                    context=resolved_ctx,
                )
                total_input_tokens += llm_result.input_tokens
                total_output_tokens += llm_result.output_tokens
                redesigned_html = llm_result.text
                redesigned_html_path = await self._storage.store_html(
                    job_id, redesigned_html, "redesign.html"
                )
            else:
                # Section-level redesign
                sections = (
                    job.site_analysis.get("content_sections", []) if job.site_analysis else []
                )
                if not sections:
                    llm_result = await self._html_gen.generate_full_page(
                        url=job.url,
                        html=html,
                        page_type=job.page_type,
                        style=job.style,
                        findings=job.critique_findings,
                        brand=job.brand_info,
                        site_analysis=job.site_analysis,
                        style_description=style_description,
                        context=resolved_ctx,
                    )
                    total_input_tokens += llm_result.input_tokens
                    total_output_tokens += llm_result.output_tokens
                    redesigned_html = llm_result.text
                    redesigned_html_path = await self._storage.store_html(
                        job_id, redesigned_html, "redesign.html"
                    )
                else:
                    section_results = await self._html_gen.generate_sections(
                        url=job.url,
                        html=html,
                        sections=sections,
                        page_type=job.page_type,
                        style=job.style,
                        findings=job.critique_findings,
                        brand=job.brand_info,
                        site_analysis=job.site_analysis,
                        style_description=style_description,
                        context=resolved_ctx,
                    )
                    paths: list[str] = []
                    for section_name, section_html in section_results.items():
                        path = await self._storage.store_html(
                            job_id, section_html, f"section_{section_name}.html"
                        )
                        paths.append(path)
                    section_html_paths = paths

                    composite = self._html_gen.compose_section_page(
                        section_results, title=job.url, style=job.style
                    )
                    redesigned_html_path = await self._storage.store_html(
                        job_id, composite, "redesign.html"
                    )
                    redesigned_html = composite

            # 5b. Deterministic HTML validation
            html_validation_report: dict | None = None
            if redesigned_html:
                try:
                    from src.services.html_validator import HtmlValidator

                    validation = HtmlValidator.validate(redesigned_html)
                    html_validation_report = validation.to_dict()
                except Exception as exc:
                    logger.warning("HTML validation failed: %s", exc)

            # Check cancellation before screenshots
            if await self._check_cancelled(db, job_id):
                return

            # 6. Accessibility scoring (optional)
            a11y_score: float | None = None
            a11y_report: dict | None = None
            if run_accessibility_check and self._a11y_scorer and redesigned_html_path:
                html_for_check = await self._storage.retrieve_text(redesigned_html_path)
                if html_for_check:
                    if auto_fix_accessibility:
                        fixed_html, report = await self._a11y_scorer.score_and_fix(
                            html_for_check,
                            threshold=accessibility_threshold,
                        )
                        if report.html_was_fixed:
                            redesigned_html_path = await self._storage.store_html(
                                job_id, fixed_html, "redesign.html"
                            )
                    else:
                        report = await self._a11y_scorer.score(html_for_check)
                    a11y_score = report.overall_score
                    a11y_report = report.to_dict()

            # 7. Capture original screenshots for comparison
            original_screenshot_paths: dict[str, str] | None = None
            if generate_screenshots and settings.screenshot.enabled:
                try:
                    orig_dir = job_dir / "original_screenshots"
                    original_screenshot_paths = await capture_url_screenshots(
                        job.url,
                        orig_dir,
                        settings.screenshot.viewports,
                        timeout_ms=settings.screenshot.timeout_ms,
                    )
                except Exception as exc:
                    logger.warning("Failed to capture original screenshots: %s", exc)

            # 8. Render redesigned screenshots
            screenshot_paths: dict[str, str] | None = None
            if generate_screenshots and settings.screenshot.enabled and redesigned_html_path:
                html_for_render = await self._storage.retrieve_text(redesigned_html_path)
                if html_for_render:
                    screenshots_dir = job_dir / "screenshots"
                    screenshot_paths = await render_from_html_string(
                        html_for_render,
                        screenshots_dir,
                        settings.screenshot.viewports,
                        timeout_ms=settings.screenshot.timeout_ms,
                    )
                    screenshots_count = len(screenshot_paths)

            # 9. Generate comparison images
            comparison_paths: dict[str, str] | None = None
            diff_paths: dict[str, str] | None = None
            if original_screenshot_paths and screenshot_paths:
                try:
                    comp_dir = job_dir / "comparisons"
                    comparison_paths, diff_paths = await generate_comparisons(
                        original_screenshot_paths, screenshot_paths, comp_dir
                    )
                except Exception as exc:
                    logger.warning("Failed to generate comparisons: %s", exc)

            # 10. Optional concept images
            concept_image_paths: list[str] | None = None
            if generate_concept_images and await self._concept_gen.is_available():
                sa = job.site_analysis or {}
                bi = job.brand_info or {}
                concept_dir = job_dir / "concept_images"
                concept_image_paths = await self._concept_gen.generate(
                    site_description=sa.get("description"),
                    target_audience=sa.get("target_audience"),
                    brand_name=bi.get("name"),
                    primary_color=bi.get("primary_color", "#2563EB"),
                    style=job.style,
                    count=settings.dalle.count,
                    output_dir=concept_dir,
                )
                concept_count = len(concept_image_paths) if concept_image_paths else 0

            # 11. Mark completed with token tracking
            job_cost = estimate_cost(total_input_tokens, total_output_tokens, self._html_gen._model)
            await JobManager.mark_completed(
                db,
                job_id,
                redesigned_html_path=redesigned_html_path,
                section_html_paths=section_html_paths,
                screenshot_paths=screenshot_paths,
                concept_image_paths=concept_image_paths,
                pages_count=1,
                accessibility_score=a11y_score,
                accessibility_report=a11y_report,
                original_screenshot_paths=original_screenshot_paths,
                comparison_paths=comparison_paths,
                diff_paths=diff_paths,
                component_html_path=component_html_path,
                html_validation_report=html_validation_report,
                input_tokens=total_input_tokens or None,
                output_tokens=total_output_tokens or None,
                estimated_cost=job_cost if job_cost > 0 else None,
            )

            await JobManager.record_usage(
                db,
                tenant_id=tenant_id,
                pages_redesigned=1,
                screenshots_rendered=screenshots_count,
                concept_images_generated=concept_count,
                llm_tokens_used=total_input_tokens + total_output_tokens,
            )

            await self._dispatch_webhook(
                db,
                job,
                "job.completed",
                accessibility_score=a11y_score,
            )

            # Cache completed job result in Redis
            await self._cache_job_result(
                job_id,
                url=job.url,
                scope=job.scope,
                style=job.style,
                redesigned_html_path=redesigned_html_path,
                section_html_paths=section_html_paths,
                screenshot_paths=screenshot_paths,
                concept_image_paths=concept_image_paths,
                component_html_path=component_html_path,
                accessibility_score=a11y_score,
                accessibility_report=a11y_report,
                original_screenshot_paths=original_screenshot_paths,
                comparison_paths=comparison_paths,
                diff_paths=diff_paths,
                html_validation_report=html_validation_report,
            )

        except Exception as exc:
            logger.error("Job %s failed: %s", job_id, exc, exc_info=True)
            await JobManager.mark_failed(db, job_id, str(exc))
            await JobManager.record_usage(
                db,
                tenant_id=tenant_id,
                is_error=True,
            )
            await self._dispatch_webhook(db, job, "job.failed", error=str(exc))
            await db.commit()
            raise

        await db.commit()

    # ========================================================================
    # Feature 4: A/B Variant Processing
    # ========================================================================

    async def _process_variants(
        self,
        db: AsyncSession,
        job: RedesignJob,
        html: str,
        resolved_ctx: ResolvedContext,
        settings: Settings,
        generate_screenshots: bool = True,
    ) -> None:
        """Process multiple style variants in parallel."""
        cfg = settings
        semaphore = asyncio.Semaphore(cfg.redesign.variant_concurrency)

        async def process_one(style: str) -> None:
            async with semaphore:
                await self._process_variant(
                    db, job, html, style, resolved_ctx, cfg, generate_screenshots
                )

        tasks = [process_one(s) for s in job.styles]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _process_variant(
        self,
        db: AsyncSession,
        job: RedesignJob,
        html: str,
        style: str,
        resolved_ctx: ResolvedContext,
        settings: Settings,
        generate_screenshots: bool = True,
    ) -> None:
        """Process a single variant."""
        variant = await JobManager.create_variant(
            db,
            job_id=job.job_id,
            style=style,
        )
        await db.flush()

        try:
            # Check cancellation
            if await self._check_cancelled(db, job.job_id):
                return

            # Resolve custom style
            style_description: str | None = None
            if style not in ("modern", "minimalist", "bold", "elegant"):
                custom_style = await StyleManager.get_style_by_slug(
                    db,
                    job.tenant_id,
                    style,
                )
                if custom_style:
                    style_description = StyleManager.resolve_style_description(custom_style)

            llm_result = await self._html_gen.generate_full_page(
                url=job.url,
                html=html,
                page_type=job.page_type,
                style=style,
                findings=job.critique_findings,
                brand=job.brand_info,
                site_analysis=job.site_analysis,
                style_description=style_description,
                context=resolved_ctx,
            )

            html_path = await self._storage.store_html(
                job.job_id,
                llm_result.text,
                f"variant_{style}.html",
            )

            screenshot_paths: dict[str, str] | None = None
            if generate_screenshots and settings.screenshot.enabled:
                job_dir = self._storage.get_job_dir(job.job_id)
                screenshots_dir = job_dir / f"screenshots_{style}"
                screenshot_paths = await render_from_html_string(
                    llm_result.text,
                    screenshots_dir,
                    settings.screenshot.viewports,
                    timeout_ms=settings.screenshot.timeout_ms,
                )

            await JobManager.mark_variant_completed(
                db,
                variant.variant_id,
                redesigned_html_path=html_path,
                screenshot_paths=screenshot_paths,
                input_tokens=llm_result.input_tokens,
                output_tokens=llm_result.output_tokens,
                estimated_cost=estimate_cost(llm_result.input_tokens, llm_result.output_tokens),
            )

            # Dispatch variant.completed webhook
            await self._dispatch_webhook(
                db,
                job,
                "variant.completed",
                variant_id=variant.variant_id,
            )

        except Exception as exc:
            logger.error("Variant %s (style=%s) failed: %s", variant.variant_id, style, exc)
            await JobManager.mark_variant_failed(db, variant.variant_id, str(exc))

    # ========================================================================
    # Feature 5: Refinement
    # ========================================================================

    async def create_refinement_job(
        self,
        db: AsyncSession,
        parent_job_id: str,
        feedback: str,
        generate_screenshots: bool = True,
        generate_concept_images: bool = False,
    ) -> str:
        """Create a refinement job from a completed parent."""
        settings = get_settings()
        parent = await JobManager.get_job(db, parent_job_id)
        if parent is None:
            raise ValueError(f"Parent job not found: {parent_job_id}")
        if parent.status != "completed":
            raise ValueError(f"Parent job is not completed (status: {parent.status})")

        root_id = parent.root_job_id or parent.job_id
        history = await JobManager.get_iteration_history(db, root_id)
        if len(history) >= settings.redesign.max_iterations:
            raise ValueError(f"Maximum iterations ({settings.redesign.max_iterations}) reached")

        job = await JobManager.create_refinement_job(
            db,
            parent_job=parent,
            feedback=feedback,
            generate_screenshots=generate_screenshots,
            generate_concept_images=generate_concept_images,
        )
        return job.job_id

    async def process_refinement_job(
        self,
        db: AsyncSession,
        job_id: str,
        tenant_id: str,
        generate_screenshots: bool = True,
        generate_concept_images: bool = False,
        focus_areas: list[str] | None = None,
    ) -> None:
        """Process a refinement job."""
        job = await JobManager.get_job(db, job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")

        await JobManager.mark_processing(db, job_id)
        await db.commit()

        settings = get_settings()
        screenshots_count = 0

        try:
            await self._dispatch_webhook(db, job, "job.started")

            # Retrieve parent's HTML
            parent = await JobManager.get_job(db, job.parent_job_id)
            if parent is None or not parent.redesigned_html_path:
                raise ValueError("Parent job HTML not found")

            previous_html = await self._storage.retrieve_text(parent.redesigned_html_path)
            if not previous_html:
                raise ValueError("Parent HTML file not found on storage")

            # Resolve custom style description for refinement
            style_description: str | None = None
            if job.style not in ("modern", "minimalist", "bold", "elegant"):
                custom_style = await StyleManager.get_style_by_slug(db, tenant_id, job.style)
                if custom_style:
                    style_description = StyleManager.resolve_style_description(custom_style)

            # Generate refined HTML
            llm_result = await self._html_gen.refine_full_page(
                url=job.url,
                previous_html=previous_html,
                feedback=job.feedback_text or "",
                page_type=job.page_type,
                style=job.style,
                brand=job.brand_info,
                site_analysis=job.site_analysis,
                style_description=style_description,
                focus_areas=focus_areas,
            )

            job_dir = self._storage.get_job_dir(job_id)
            redesigned_html_path = await self._storage.store_html(
                job_id, llm_result.text, "redesign.html"
            )

            # Render screenshots
            screenshot_paths: dict[str, str] | None = None
            if generate_screenshots and settings.screenshot.enabled:
                screenshots_dir = job_dir / "screenshots"
                screenshot_paths = await render_from_html_string(
                    llm_result.text,
                    screenshots_dir,
                    settings.screenshot.viewports,
                    timeout_ms=settings.screenshot.timeout_ms,
                )
                screenshots_count = len(screenshot_paths)

            job_cost = estimate_cost(
                llm_result.input_tokens, llm_result.output_tokens, self._html_gen._model
            )
            await JobManager.mark_completed(
                db,
                job_id,
                redesigned_html_path=redesigned_html_path,
                screenshot_paths=screenshot_paths,
                pages_count=1,
                input_tokens=llm_result.input_tokens or None,
                output_tokens=llm_result.output_tokens or None,
                estimated_cost=job_cost if job_cost > 0 else None,
            )

            await JobManager.record_usage(
                db,
                tenant_id=tenant_id,
                pages_redesigned=1,
                screenshots_rendered=screenshots_count,
                llm_tokens_used=llm_result.input_tokens + llm_result.output_tokens,
            )

            await self._dispatch_webhook(db, job, "job.completed")

            # Cache completed refinement result in Redis
            await self._cache_job_result(
                job_id,
                url=job.url,
                scope=job.scope,
                style=job.style,
                redesigned_html_path=redesigned_html_path,
                screenshot_paths=screenshot_paths,
            )

        except Exception as exc:
            logger.error("Refinement job %s failed: %s", job_id, exc, exc_info=True)
            await JobManager.mark_failed(db, job_id, str(exc))
            await JobManager.record_usage(db, tenant_id=tenant_id, is_error=True)
            await self._dispatch_webhook(db, job, "job.failed", error=str(exc))
            await db.commit()
            raise

        await db.commit()

    # ========================================================================
    # Feature 10: Batch Processing
    # ========================================================================

    async def create_batch(
        self,
        db: AsyncSession,
        *,
        tenant_id: str,
        pages: list[dict],
        style: str = "modern",
        scope: str = "full_page",
        generate_screenshots: bool = True,
        generate_concept_images: bool = False,
        critique_findings: list[dict] | None = None,
        brand_info: dict | None = None,
        site_analysis: dict | None = None,
        user_context: dict | None = None,
        webhook_url: str | None = None,
        webhook_secret: str | None = None,
    ) -> tuple[str, list[dict]]:
        """Create a batch job with child page jobs. Returns (batch_id, page_jobs)."""
        settings = get_settings()

        # Score and select pages
        focus_pages = user_context.get("focus_pages") if user_context else None
        exclude_pages = user_context.get("exclude_pages") if user_context else None

        scored_pages = select_pages(
            pages,
            critique_findings=critique_findings,
            max_pages=settings.redesign.max_pages,
            focus_pages=focus_pages,
            exclude_pages=exclude_pages,
        )

        batch = await BatchManager.create_batch(
            db,
            tenant_id=tenant_id,
            total_pages=len(scored_pages),
            shared_settings={
                "style": style,
                "scope": scope,
                "generate_screenshots": generate_screenshots,
                "generate_concept_images": generate_concept_images,
            },
        )

        page_jobs: list[dict] = []
        for i, page in enumerate(scored_pages):
            job = await JobManager.create_job(
                db,
                tenant_id=tenant_id,
                url=page["url"],
                html_content=page.get("html_content"),
                scope=scope,
                style=style,
                page_type=page.get("page_type"),
                critique_findings=critique_findings,
                brand_info=brand_info,
                site_analysis=site_analysis,
                user_context=user_context,
                batch_id=batch.batch_id,
                priority_score=len(scored_pages) - i,  # Higher score = earlier in list
                webhook_url=webhook_url,
                webhook_secret=webhook_secret,
            )
            page_jobs.append(
                {
                    "job_id": job.job_id,
                    "url": page["url"],
                    "page_type": page.get("page_type"),
                    "priority_score": len(scored_pages) - i,
                }
            )

        return batch.batch_id, page_jobs

    async def process_batch(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        batch_id: str,
        tenant_id: str,
    ) -> None:
        """Process all pages in a batch with concurrency control."""
        settings = get_settings()

        async with session_factory() as db:
            await BatchManager.mark_processing(db, batch_id)
            await db.commit()
            jobs = await BatchManager.get_batch_jobs(db, batch_id)

        semaphore = asyncio.Semaphore(settings.redesign.batch_max_concurrency)

        async def process_page(job_: RedesignJob) -> None:
            async with semaphore:
                async with session_factory() as page_db:
                    batch = await BatchManager.get_batch(page_db, batch_id)
                    if batch and batch.status == "cancelled":
                        return
                    try:
                        await self.process_job(
                            page_db,
                            job_.job_id,
                            tenant_id,
                            generate_screenshots=True,
                        )
                        await BatchManager.increment_completed(page_db, batch_id)
                    except Exception as exc:
                        logger.error("Batch page %s failed: %s", job_.job_id, exc)
                        await BatchManager.increment_failed(page_db, batch_id)

        tasks = [process_page(j) for j in jobs]
        await asyncio.gather(*tasks, return_exceptions=True)

        async with session_factory() as db:
            final_status = await BatchManager.finalize_batch(db, batch_id)
            await db.commit()

            # Dispatch batch-level webhooks
            if jobs:
                first_job = jobs[0]
                if final_status in ("completed", "completed_with_errors"):
                    await self._dispatch_webhook(
                        db, first_job, "batch.completed", batch_id=batch_id
                    )
                elif final_status == "failed":
                    await self._dispatch_webhook(db, first_job, "batch.failed", batch_id=batch_id)

    # ========================================================================
    # Helpers
    # ========================================================================

    async def _check_cancelled(self, db: AsyncSession, job_id: str) -> bool:
        """Check if the job has been cancelled. If so, log and return True."""
        if await JobManager.is_cancelled(db, job_id):
            logger.info("Job %s was cancelled, stopping processing", job_id)
            return True
        return False

    async def _fetch_page_html(self, url: str, timeout_ms: int = 30000) -> str:
        """Fetch live HTML via Playwright."""
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                html = await page.content()
            finally:
                await browser.close()
        return html

    async def _dispatch_webhook(
        self,
        db: AsyncSession,
        job: RedesignJob,
        event_type: str,
        error: str | None = None,
        batch_id: str | None = None,
        variant_id: str | None = None,
        accessibility_score: float | None = None,
    ) -> None:
        """Dispatch webhook notification if configured. Non-fatal on failure."""
        if not self._webhook:
            return
        webhook_url = getattr(job, "webhook_url", None)
        if not webhook_url:
            return
        try:
            payload = WebhookDispatcher.build_event_payload(
                event_type,
                job.job_id,
                status=job.status,
                error=error,
                result_url=f"/api/v1/redesign/jobs/{job.job_id}/result",
                batch_id=batch_id or getattr(job, "batch_id", None),
                variant_id=variant_id,
                accessibility_score=accessibility_score,
            )
            await self._webhook.dispatch(
                db,
                job_id=job.job_id,
                webhook_url=webhook_url,
                webhook_secret=getattr(job, "webhook_secret", None),
                event_type=event_type,
                payload=payload,
            )
        except Exception as exc:
            logger.warning("Webhook dispatch failed for job %s: %s", job.job_id, exc)

    async def _cache_job_result(
        self,
        job_id: str,
        *,
        url: str | None = None,
        scope: str | None = None,
        style: str | None = None,
        redesigned_html_path: str | None = None,
        section_html_paths: list[str] | None = None,
        screenshot_paths: dict[str, str] | None = None,
        concept_image_paths: list[str] | None = None,
        component_html_path: str | None = None,
        accessibility_score: float | None = None,
        accessibility_report: dict | None = None,
        original_screenshot_paths: dict[str, str] | None = None,
        comparison_paths: dict[str, str] | None = None,
        diff_paths: dict[str, str] | None = None,
        html_validation_report: dict | None = None,
    ) -> None:
        """Cache a completed job result in Redis. Non-fatal on failure."""
        if not self._cache:
            return
        result_data: dict = {
            "job_id": job_id,
            "url": url,
            "scope": scope,
            "style": style,
            "redesigned_html_path": redesigned_html_path,
            "section_html_paths": section_html_paths,
            "screenshot_paths": screenshot_paths,
            "concept_image_paths": concept_image_paths,
            "component_html_path": component_html_path,
            "accessibility_score": accessibility_score,
            "accessibility_report": accessibility_report,
            "original_screenshot_paths": original_screenshot_paths,
            "comparison_paths": comparison_paths,
            "diff_paths": diff_paths,
            "html_validation_report": html_validation_report,
        }
        try:
            await self._cache.cache_job_result(job_id, result_data)
        except Exception as exc:
            logger.warning("Failed to cache result for job %s: %s", job_id, exc)

"""Redesign job lifecycle management."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from datetime import date as date_type

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import RedesignJob, RedesignUsage, RedesignVariant

logger = logging.getLogger(__name__)


class JobManager:
    """Manages redesign job lifecycle."""

    @staticmethod
    async def create_job(
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
        template_version: str | None = None,
        styles: list[str] | None = None,
        component_target: dict | None = None,
        webhook_url: str | None = None,
        webhook_secret: str | None = None,
        batch_id: str | None = None,
        priority_score: float | None = None,
    ) -> RedesignJob:
        variant_count = len(styles) if styles else None
        job = RedesignJob(
            job_id=str(uuid.uuid4()),
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
            template_version=template_version,
            styles=styles,
            variant_count=variant_count,
            component_target=component_target,
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
            batch_id=batch_id,
            priority_score=priority_score,
            status="pending",
        )
        db.add(job)
        await db.flush()
        logger.info(
            "Created redesign job %s (url=%s, scope=%s, style=%s)", job.job_id, url, scope, style
        )
        return job

    @staticmethod
    async def create_refinement_job(
        db: AsyncSession,
        *,
        parent_job: RedesignJob,
        feedback: str,
        generate_screenshots: bool = True,
        generate_concept_images: bool = False,
    ) -> RedesignJob:
        """Create a refinement job linked to a parent."""
        root_id = parent_job.root_job_id or parent_job.job_id
        iteration = (parent_job.iteration_number or 0) + 1

        job = RedesignJob(
            job_id=str(uuid.uuid4()),
            tenant_id=parent_job.tenant_id,
            url=parent_job.url,
            scope=parent_job.scope,
            style=parent_job.style,
            page_type=parent_job.page_type,
            critique_findings=parent_job.critique_findings,
            brand_info=parent_job.brand_info,
            site_analysis=parent_job.site_analysis,
            user_context=parent_job.user_context,
            template_version=parent_job.template_version,
            parent_job_id=parent_job.job_id,
            root_job_id=root_id,
            iteration_number=iteration,
            feedback_text=feedback,
            webhook_url=parent_job.webhook_url,
            webhook_secret=parent_job.webhook_secret,
            status="pending",
        )
        db.add(job)
        await db.flush()
        logger.info(
            "Created refinement job %s (parent=%s, iteration=%d)",
            job.job_id,
            parent_job.job_id,
            iteration,
        )
        return job

    @staticmethod
    async def get_job(db: AsyncSession, job_id: str) -> RedesignJob | None:
        result = await db.execute(select(RedesignJob).where(RedesignJob.job_id == job_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def mark_processing(db: AsyncSession, job_id: str) -> None:
        await db.execute(
            update(RedesignJob)
            .where(RedesignJob.job_id == job_id)
            .values(status="processing", started_at=datetime.now(UTC))
        )

    @staticmethod
    async def mark_completed(
        db: AsyncSession,
        job_id: str,
        *,
        redesigned_html_path: str | None = None,
        section_html_paths: list[str] | None = None,
        screenshot_paths: dict[str, str] | None = None,
        concept_image_paths: list[str] | None = None,
        pages_count: int = 1,
        accessibility_score: float | None = None,
        accessibility_report: dict | None = None,
        original_screenshot_paths: dict[str, str] | None = None,
        comparison_paths: dict[str, str] | None = None,
        diff_paths: dict[str, str] | None = None,
        component_html_path: str | None = None,
        html_validation_report: dict | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        estimated_cost: float | None = None,
    ) -> None:
        values: dict = {
            "status": "completed",
            "redesigned_html_path": redesigned_html_path,
            "section_html_paths": section_html_paths,
            "screenshot_paths": screenshot_paths,
            "concept_image_paths": concept_image_paths,
            "pages_count": pages_count,
            "completed_at": datetime.now(UTC),
        }
        if accessibility_score is not None:
            values["accessibility_score"] = accessibility_score
        if accessibility_report is not None:
            values["accessibility_report"] = accessibility_report
        if original_screenshot_paths is not None:
            values["original_screenshot_paths"] = original_screenshot_paths
        if comparison_paths is not None:
            values["comparison_paths"] = comparison_paths
        if diff_paths is not None:
            values["diff_paths"] = diff_paths
        if component_html_path is not None:
            values["component_html_path"] = component_html_path
        if html_validation_report is not None:
            values["html_validation_report"] = html_validation_report
        if input_tokens is not None:
            values["input_tokens"] = input_tokens
        if output_tokens is not None:
            values["output_tokens"] = output_tokens
        if estimated_cost is not None:
            values["estimated_cost"] = estimated_cost

        await db.execute(update(RedesignJob).where(RedesignJob.job_id == job_id).values(**values))

    @staticmethod
    async def mark_failed(db: AsyncSession, job_id: str, error_message: str) -> None:
        await db.execute(
            update(RedesignJob)
            .where(RedesignJob.job_id == job_id)
            .values(
                status="failed",
                error_message=error_message,
                completed_at=datetime.now(UTC),
            )
        )

    @staticmethod
    async def cancel_job(db: AsyncSession, job_id: str) -> bool:
        """Cancel a job. Returns True if the job was cancellable."""
        job = await JobManager.get_job(db, job_id)
        if job is None:
            return False
        if job.status in ("completed", "failed", "cancelled"):
            return False
        now = datetime.now(UTC)
        await db.execute(
            update(RedesignJob)
            .where(RedesignJob.job_id == job_id)
            .values(status="cancelled", cancelled_at=now, completed_at=now)
        )
        return True

    @staticmethod
    async def list_jobs(
        db: AsyncSession,
        tenant_id: str,
        *,
        status: str | None = None,
        page_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[RedesignJob], int]:
        """List jobs for a tenant with optional filters. Returns (jobs, total_count)."""
        from sqlalchemy import func as sa_func

        conditions = [RedesignJob.tenant_id == tenant_id]
        if status:
            conditions.append(RedesignJob.status == status)
        if page_type:
            conditions.append(RedesignJob.page_type == page_type)

        count_result = await db.execute(
            select(sa_func.count()).select_from(RedesignJob).where(*conditions)
        )
        total = count_result.scalar() or 0

        result = await db.execute(
            select(RedesignJob)
            .where(*conditions)
            .order_by(RedesignJob.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        jobs = list(result.scalars().all())
        return jobs, total

    @staticmethod
    async def is_cancelled(db: AsyncSession, job_id: str) -> bool:
        """Check if a job has been cancelled."""
        job = await JobManager.get_job(db, job_id)
        return job is not None and job.status == "cancelled"

    @staticmethod
    async def get_iteration_history(db: AsyncSession, root_job_id: str) -> list[RedesignJob]:
        """Get all iterations for a root job, ordered by iteration number."""
        # Include the root job itself
        result = await db.execute(
            select(RedesignJob)
            .where((RedesignJob.job_id == root_job_id) | (RedesignJob.root_job_id == root_job_id))
            .order_by(RedesignJob.iteration_number.asc().nullsfirst())
        )
        return list(result.scalars().all())

    # ========================================================================
    # Variant Management
    # ========================================================================

    @staticmethod
    async def create_variant(
        db: AsyncSession,
        *,
        job_id: str,
        style: str,
    ) -> RedesignVariant:
        variant = RedesignVariant(
            variant_id=str(uuid.uuid4()),
            job_id=job_id,
            style=style,
            status="pending",
        )
        db.add(variant)
        await db.flush()
        return variant

    @staticmethod
    async def get_variants(db: AsyncSession, job_id: str) -> list[RedesignVariant]:
        result = await db.execute(
            select(RedesignVariant)
            .where(RedesignVariant.job_id == job_id)
            .order_by(RedesignVariant.created_at)
        )
        return list(result.scalars().all())

    @staticmethod
    async def mark_variant_completed(
        db: AsyncSession,
        variant_id: str,
        *,
        redesigned_html_path: str | None = None,
        screenshot_paths: dict[str, str] | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        estimated_cost: float = 0.0,
    ) -> None:
        await db.execute(
            update(RedesignVariant)
            .where(RedesignVariant.variant_id == variant_id)
            .values(
                status="completed",
                redesigned_html_path=redesigned_html_path,
                screenshot_paths=screenshot_paths,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost=estimated_cost,
                completed_at=datetime.now(UTC),
            )
        )

    @staticmethod
    async def mark_variant_failed(db: AsyncSession, variant_id: str, error_message: str) -> None:
        await db.execute(
            update(RedesignVariant)
            .where(RedesignVariant.variant_id == variant_id)
            .values(
                status="failed",
                error_message=error_message,
                completed_at=datetime.now(UTC),
            )
        )

    # ========================================================================
    # Usage Tracking
    # ========================================================================

    @staticmethod
    async def record_usage(
        db: AsyncSession,
        *,
        tenant_id: str,
        pages_redesigned: int = 0,
        screenshots_rendered: int = 0,
        concept_images_generated: int = 0,
        llm_tokens_used: int = 0,
        variants_generated: int = 0,
        is_error: bool = False,
    ) -> None:
        """Record usage for daily aggregation (upsert)."""
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        today = date_type.today()
        stmt = pg_insert(RedesignUsage).values(
            tenant_id=tenant_id,
            date=today,
            request_count=1,
            pages_redesigned=pages_redesigned,
            screenshots_rendered=screenshots_rendered,
            concept_images_generated=concept_images_generated,
            llm_tokens_used=llm_tokens_used,
            variants_generated=variants_generated,
            error_count=1 if is_error else 0,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_redesign_usage_tenant_date",
            set_={
                "request_count": RedesignUsage.request_count + 1,
                "pages_redesigned": RedesignUsage.pages_redesigned + pages_redesigned,
                "screenshots_rendered": RedesignUsage.screenshots_rendered + screenshots_rendered,
                "concept_images_generated": RedesignUsage.concept_images_generated
                + concept_images_generated,
                "llm_tokens_used": RedesignUsage.llm_tokens_used + llm_tokens_used,
                "variants_generated": RedesignUsage.variants_generated + variants_generated,
                "error_count": RedesignUsage.error_count + (1 if is_error else 0),
            },
        )
        await db.execute(stmt)

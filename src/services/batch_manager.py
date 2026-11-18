"""Batch job management for multi-page redesign processing."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import BatchJob, RedesignJob

logger = logging.getLogger(__name__)


class BatchManager:
    """Manages batch redesign job lifecycle."""

    @staticmethod
    async def create_batch(
        db: AsyncSession,
        *,
        tenant_id: str,
        total_pages: int,
        shared_settings: dict | None = None,
    ) -> BatchJob:
        batch = BatchJob(
            batch_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            status="pending",
            total_pages=total_pages,
            completed_pages=0,
            failed_pages=0,
            shared_settings=shared_settings,
        )
        db.add(batch)
        await db.flush()
        logger.info(
            "Created batch %s with %d pages for tenant %s", batch.batch_id, total_pages, tenant_id
        )
        return batch

    @staticmethod
    async def get_batch(db: AsyncSession, batch_id: str) -> BatchJob | None:
        result = await db.execute(select(BatchJob).where(BatchJob.batch_id == batch_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def mark_processing(db: AsyncSession, batch_id: str) -> None:
        await db.execute(
            update(BatchJob)
            .where(BatchJob.batch_id == batch_id)
            .values(status="processing", started_at=datetime.now(UTC))
        )

    @staticmethod
    async def increment_completed(db: AsyncSession, batch_id: str) -> None:
        await db.execute(
            update(BatchJob)
            .where(BatchJob.batch_id == batch_id)
            .values(completed_pages=BatchJob.completed_pages + 1)
        )

    @staticmethod
    async def increment_failed(db: AsyncSession, batch_id: str) -> None:
        await db.execute(
            update(BatchJob)
            .where(BatchJob.batch_id == batch_id)
            .values(failed_pages=BatchJob.failed_pages + 1)
        )

    @staticmethod
    async def finalize_batch(db: AsyncSession, batch_id: str) -> str:
        """Derive final status from page results and update batch."""
        batch = await BatchManager.get_batch(db, batch_id)
        if batch is None:
            raise ValueError(f"Batch not found: {batch_id}")

        if batch.failed_pages == batch.total_pages:
            status = "failed"
        elif batch.failed_pages > 0:
            status = "completed_with_errors"
        else:
            status = "completed"

        await db.execute(
            update(BatchJob)
            .where(BatchJob.batch_id == batch_id)
            .values(status=status, completed_at=datetime.now(UTC))
        )
        logger.info("Batch %s finalized: %s", batch_id, status)
        return status

    @staticmethod
    async def get_batch_jobs(db: AsyncSession, batch_id: str) -> list[RedesignJob]:
        """Get all child jobs for a batch."""
        result = await db.execute(
            select(RedesignJob)
            .where(RedesignJob.batch_id == batch_id)
            .order_by(RedesignJob.priority_score.desc().nullslast())
        )
        return list(result.scalars().all())

    @staticmethod
    async def cancel_batch(db: AsyncSession, batch_id: str) -> bool:
        """Cancel a batch and all its child jobs."""
        batch = await BatchManager.get_batch(db, batch_id)
        if batch is None:
            return False
        if batch.status in ("completed", "failed", "cancelled", "completed_with_errors"):
            return False

        now = datetime.now(UTC)
        await db.execute(
            update(BatchJob)
            .where(BatchJob.batch_id == batch_id)
            .values(status="cancelled", completed_at=now)
        )
        # Cancel all pending/processing child jobs
        await db.execute(
            update(RedesignJob)
            .where(
                RedesignJob.batch_id == batch_id,
                RedesignJob.status.in_(["pending", "processing"]),
            )
            .values(status="cancelled", cancelled_at=now, completed_at=now)
        )
        logger.info("Cancelled batch %s and its pending jobs", batch_id)
        return True

    @staticmethod
    async def list_batches(db: AsyncSession, tenant_id: str) -> list[BatchJob]:
        """List all batches for a tenant."""
        result = await db.execute(
            select(BatchJob)
            .where(BatchJob.tenant_id == tenant_id)
            .order_by(BatchJob.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_batch_progress(db: AsyncSession, batch_id: str) -> dict:
        """Get progress counts for a batch."""
        batch = await BatchManager.get_batch(db, batch_id)
        if batch is None:
            return {}
        jobs = await BatchManager.get_batch_jobs(db, batch_id)
        pending = sum(1 for j in jobs if j.status == "pending")
        processing = sum(1 for j in jobs if j.status == "processing")
        completed = sum(1 for j in jobs if j.status == "completed")
        failed = sum(1 for j in jobs if j.status == "failed")
        cancelled = sum(1 for j in jobs if j.status == "cancelled")
        return {
            "total": batch.total_pages,
            "pending": pending,
            "processing": processing,
            "completed": completed,
            "failed": failed,
            "cancelled": cancelled,
        }

    @staticmethod
    async def get_failed_jobs(db: AsyncSession, batch_id: str) -> list[RedesignJob]:
        """Get failed child jobs for retry."""
        result = await db.execute(
            select(RedesignJob).where(
                RedesignJob.batch_id == batch_id,
                RedesignJob.status == "failed",
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def reset_job_for_retry(db: AsyncSession, job_id: str) -> None:
        """Reset a failed job back to pending for retry."""
        await db.execute(
            update(RedesignJob)
            .where(RedesignJob.job_id == job_id)
            .values(
                status="pending",
                error_message=None,
                completed_at=None,
                started_at=None,
            )
        )

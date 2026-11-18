"""Data retention cleanup for expired jobs and orphan files."""

from __future__ import annotations

import logging
import shutil
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    BatchJob,
    RedesignJob,
    RedesignVariant,
    WebhookDeliveryLog,
)
from src.services.storage_service import StorageService

logger = logging.getLogger(__name__)


class CleanupService:
    """Handles data retention cleanup for old jobs and files."""

    def __init__(self, storage: StorageService) -> None:
        self._storage = storage

    async def cleanup_old_jobs(
        self,
        db: AsyncSession,
        retention_days: int = 30,
    ) -> int:
        """Delete jobs and associated data older than *retention_days*.

        Deletion order (to respect implicit foreign-key semantics):
          1. WebhookDeliveryLog rows linked to expired jobs
          2. RedesignVariant rows linked to expired jobs
          3. RedesignJob rows themselves
          4. BatchJob rows that have expired

        Associated storage directories are removed after the DB rows
        are deleted so a failed transaction does not leave dangling
        references.

        Returns the number of deleted RedesignJob rows.
        """
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        logger.info(
            "Starting cleanup for jobs older than %s (%d-day retention)",
            cutoff.isoformat(),
            retention_days,
        )

        # Collect job_ids that will be removed so we can clean storage.
        stmt = select(RedesignJob.job_id).where(
            RedesignJob.created_at < cutoff,
        )
        result = await db.execute(stmt)
        expired_job_ids: list[str] = list(result.scalars().all())

        if not expired_job_ids:
            logger.info("No expired jobs found — nothing to clean up")
            return 0

        # 1. Webhook delivery logs
        wh_result = await db.execute(
            delete(WebhookDeliveryLog).where(
                WebhookDeliveryLog.job_id.in_(expired_job_ids),
            )
        )
        logger.info("Deleted %d webhook delivery log(s)", wh_result.rowcount or 0)  # type: ignore[unresolved-attribute]

        # 2. Redesign variants
        var_result = await db.execute(
            delete(RedesignVariant).where(
                RedesignVariant.job_id.in_(expired_job_ids),
            )
        )
        logger.info("Deleted %d variant(s)", var_result.rowcount or 0)  # type: ignore[unresolved-attribute]

        # 3. Redesign jobs
        job_result = await db.execute(
            delete(RedesignJob).where(
                RedesignJob.created_at < cutoff,
            )
        )
        deleted_jobs: int = job_result.rowcount or 0  # type: ignore[unresolved-attribute]
        logger.info("Deleted %d redesign job(s)", deleted_jobs)

        # 4. Batch jobs
        batch_result = await db.execute(
            delete(BatchJob).where(BatchJob.created_at < cutoff),
        )
        logger.info("Deleted %d batch job(s)", batch_result.rowcount or 0)  # type: ignore[unresolved-attribute]

        await db.flush()

        # Remove storage directories for each expired job.
        for job_id in expired_job_ids:
            job_dir = self._storage.get_job_dir(job_id)
            if job_dir.exists():
                shutil.rmtree(job_dir)
                logger.debug("Removed storage dir: %s", job_dir)

        logger.info("Cleanup complete — %d job(s) removed", deleted_jobs)
        return deleted_jobs

    async def cleanup_orphan_files(self, db: AsyncSession) -> int:
        """Remove storage directories that have no matching DB record.

        Scans the local storage root, collects directory names (which
        correspond to job IDs), queries the database for known job IDs,
        and removes any directories whose name does not match a known job.

        Returns the number of orphan directories removed.
        """
        storage_root = self._storage._local_path
        if not storage_root.exists():
            return 0

        storage_dirs = [d for d in storage_root.iterdir() if d.is_dir()]
        if not storage_dirs:
            return 0

        # Get all known job_ids from DB
        result = await db.execute(select(RedesignJob.job_id))
        known_job_ids = {row[0] for row in result.all()}

        removed = 0
        for job_dir in storage_dirs:
            if job_dir.name not in known_job_ids:
                shutil.rmtree(job_dir)
                logger.info("Removed orphan storage dir: %s", job_dir)
                removed += 1

        logger.info("Orphan cleanup complete — %d dir(s) removed", removed)
        return removed

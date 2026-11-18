"""Unit tests for CleanupService (Phase 2 -- data retention cleanup)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.cleanup_service import CleanupService

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_storage() -> MagicMock:
    """Mock StorageService."""
    storage = MagicMock()
    # get_job_dir returns a Path-like object
    job_dir = MagicMock()
    job_dir.exists.return_value = True
    storage.get_job_dir.return_value = job_dir
    return storage


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock AsyncSession."""
    db = AsyncMock()
    return db


@pytest.fixture
def cleanup_service(mock_storage: MagicMock) -> CleanupService:
    return CleanupService(storage=mock_storage)


# ============================================================================
# cleanup_old_jobs
# ============================================================================


class TestCleanupOldJobs:
    @pytest.mark.asyncio
    async def test_no_expired_jobs_returns_zero(
        self, cleanup_service: CleanupService, mock_db: AsyncMock
    ) -> None:
        # The SELECT query returns an empty list of expired job IDs
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result_mock)

        deleted = await cleanup_service.cleanup_old_jobs(mock_db, retention_days=30)
        assert deleted == 0

    @pytest.mark.asyncio
    @patch("src.services.cleanup_service.shutil.rmtree")
    async def test_deletes_old_records(
        self,
        mock_rmtree: MagicMock,
        cleanup_service: CleanupService,
        mock_db: AsyncMock,
        mock_storage: MagicMock,
    ) -> None:
        expired_ids = ["job-001", "job-002"]

        # First execute call: SELECT expired job_ids
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = expired_ids

        # Subsequent execute calls: DELETE statements returning rowcount
        wh_result = MagicMock()
        wh_result.rowcount = 3
        var_result = MagicMock()
        var_result.rowcount = 4
        job_result = MagicMock()
        job_result.rowcount = 2
        batch_result = MagicMock()
        batch_result.rowcount = 1

        mock_db.execute = AsyncMock(
            side_effect=[select_result, wh_result, var_result, job_result, batch_result]
        )
        mock_db.flush = AsyncMock()

        deleted = await cleanup_service.cleanup_old_jobs(mock_db, retention_days=7)

        assert deleted == 2
        # Storage dirs should be checked for each expired job
        assert mock_storage.get_job_dir.call_count == len(expired_ids)
        # shutil.rmtree should be called for each expired job's dir
        assert mock_rmtree.call_count == len(expired_ids)


# ============================================================================
# cleanup_orphan_files
# ============================================================================


class TestCleanupOrphanFiles:
    @pytest.mark.asyncio
    @patch("src.services.cleanup_service.shutil.rmtree")
    async def test_cleanup_removes_orphan_dirs(
        self,
        mock_rmtree: MagicMock,
        cleanup_service: CleanupService,
        mock_db: AsyncMock,
        mock_storage: MagicMock,
    ) -> None:
        """Dirs not in DB are removed."""
        from pathlib import Path

        orphan_dir = MagicMock(spec=Path)
        orphan_dir.name = "orphan-job-1"
        orphan_dir.is_dir.return_value = True

        valid_dir = MagicMock(spec=Path)
        valid_dir.name = "valid-job-1"
        valid_dir.is_dir.return_value = True

        storage_root = MagicMock(spec=Path)
        storage_root.exists.return_value = True
        storage_root.iterdir.return_value = [orphan_dir, valid_dir]
        mock_storage._local_path = storage_root

        # DB knows about valid-job-1 but not orphan-job-1
        db_result = MagicMock()
        db_result.all.return_value = [("valid-job-1",)]
        mock_db.execute = AsyncMock(return_value=db_result)

        removed = await cleanup_service.cleanup_orphan_files(mock_db)
        assert removed == 1
        mock_rmtree.assert_called_once_with(orphan_dir)

    @pytest.mark.asyncio
    @patch("src.services.cleanup_service.shutil.rmtree")
    async def test_cleanup_preserves_valid_dirs(
        self,
        mock_rmtree: MagicMock,
        cleanup_service: CleanupService,
        mock_db: AsyncMock,
        mock_storage: MagicMock,
    ) -> None:
        """Dirs with matching DB records are kept."""
        from pathlib import Path

        valid_dir = MagicMock(spec=Path)
        valid_dir.name = "job-1"
        valid_dir.is_dir.return_value = True

        storage_root = MagicMock(spec=Path)
        storage_root.exists.return_value = True
        storage_root.iterdir.return_value = [valid_dir]
        mock_storage._local_path = storage_root

        db_result = MagicMock()
        db_result.all.return_value = [("job-1",)]
        mock_db.execute = AsyncMock(return_value=db_result)

        removed = await cleanup_service.cleanup_orphan_files(mock_db)
        assert removed == 0
        mock_rmtree.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_empty_storage_returns_zero(
        self,
        cleanup_service: CleanupService,
        mock_db: AsyncMock,
        mock_storage: MagicMock,
    ) -> None:
        """No dirs = no work."""
        from pathlib import Path

        storage_root = MagicMock(spec=Path)
        storage_root.exists.return_value = True
        storage_root.iterdir.return_value = []
        mock_storage._local_path = storage_root

        removed = await cleanup_service.cleanup_orphan_files(mock_db)
        assert removed == 0

    @pytest.mark.asyncio
    async def test_cleanup_missing_storage_returns_zero(
        self,
        cleanup_service: CleanupService,
        mock_db: AsyncMock,
        mock_storage: MagicMock,
    ) -> None:
        """If storage root doesn't exist, return 0."""
        from pathlib import Path

        storage_root = MagicMock(spec=Path)
        storage_root.exists.return_value = False
        mock_storage._local_path = storage_root

        removed = await cleanup_service.cleanup_orphan_files(mock_db)
        assert removed == 0

    @pytest.mark.asyncio
    @patch("src.services.cleanup_service.shutil.rmtree")
    async def test_cleanup_no_db_records_removes_all(
        self,
        mock_rmtree: MagicMock,
        cleanup_service: CleanupService,
        mock_db: AsyncMock,
        mock_storage: MagicMock,
    ) -> None:
        """If DB has no records, all storage dirs are orphans."""
        from pathlib import Path

        dir1 = MagicMock(spec=Path)
        dir1.name = "job-1"
        dir1.is_dir.return_value = True

        dir2 = MagicMock(spec=Path)
        dir2.name = "job-2"
        dir2.is_dir.return_value = True

        storage_root = MagicMock(spec=Path)
        storage_root.exists.return_value = True
        storage_root.iterdir.return_value = [dir1, dir2]
        mock_storage._local_path = storage_root

        db_result = MagicMock()
        db_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=db_result)

        removed = await cleanup_service.cleanup_orphan_files(mock_db)
        assert removed == 2
        assert mock_rmtree.call_count == 2

"""Unit tests for session isolation in background task functions (Phase 2).

Verify that each background processing function creates an independent
database session from the session_factory rather than reusing the
request-scoped session.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

# ============================================================================
# _process_job_background
# ============================================================================


class TestProcessJobBackground:
    @pytest.mark.asyncio
    async def test_creates_new_session_from_factory(self) -> None:
        from src.api.routes import _process_job_background

        mock_service = MagicMock()
        mock_service.process_job = AsyncMock()

        # session_factory() is an async context manager that yields a session
        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        await _process_job_background(
            service=mock_service,
            session_factory=mock_factory,
            job_id="job-123",
            tenant_id="tenant-abc",
        )

        # The factory must have been called to create a new session
        mock_factory.assert_called_once()
        # The service should have been invoked with the factory-created session
        mock_service.process_job.assert_awaited_once()
        call_args = mock_service.process_job.call_args
        assert call_args[0][0] is mock_session  # first positional arg = db session


# ============================================================================
# _process_refinement_background
# ============================================================================


class TestProcessRefinementBackground:
    @pytest.mark.asyncio
    async def test_creates_new_session_from_factory(self) -> None:
        from src.api.routes import _process_refinement_background

        mock_service = MagicMock()
        mock_service.process_refinement_job = AsyncMock()

        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        await _process_refinement_background(
            service=mock_service,
            session_factory=mock_factory,
            job_id="refine-456",
            tenant_id="tenant-abc",
        )

        mock_factory.assert_called_once()
        mock_service.process_refinement_job.assert_awaited_once()
        call_args = mock_service.process_refinement_job.call_args
        assert call_args[0][0] is mock_session


# ============================================================================
# _process_batch_background
# ============================================================================


class TestProcessBatchBackground:
    @pytest.mark.asyncio
    async def test_passes_session_factory_to_process_batch(self) -> None:
        from src.api.routes import _process_batch_background

        mock_service = MagicMock()
        mock_service.process_batch = AsyncMock()

        mock_factory = MagicMock()

        await _process_batch_background(
            service=mock_service,
            session_factory=mock_factory,
            batch_id="batch-789",
            tenant_id="tenant-abc",
        )

        # process_batch now receives the factory directly (not a session)
        mock_service.process_batch.assert_awaited_once()
        call_args = mock_service.process_batch.call_args
        assert call_args[0][0] is mock_factory

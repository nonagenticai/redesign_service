"""Extended tests for API routes covering styles, batch, and other endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.api.schemas import CreateCustomStyleRequest, UpdateCustomStyleRequest

# ============================================================================
# List Styles
# ============================================================================


class TestListStyles:
    @pytest.mark.asyncio
    async def test_list_styles(self, mock_db) -> None:
        from src.api.routes import list_styles

        mock_style = SimpleNamespace(
            style_id="s1",
            name="Bold",
            slug="bold",
            description="A bold style",
            color_palette=None,
            typography=None,
            layout=None,
            example_references=None,
            is_active=True,
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
        with patch(
            "src.api.routes.StyleManager.list_styles",
            new_callable=AsyncMock,
            return_value=[mock_style],
        ):
            request = MagicMock()
            request.state.tenant_id = "tenant-1"
            result = await list_styles(request, mock_db)
            assert result.count == 1
            assert result.styles[0].style_id == "s1"


# ============================================================================
# Create Style
# ============================================================================


class TestCreateStyle:
    @pytest.mark.asyncio
    async def test_create_style_success(self, mock_db) -> None:
        from src.api.routes import create_style

        mock_style = SimpleNamespace(
            style_id="s-new",
            name="Fresh",
            slug="fresh",
            description=None,
            color_palette=None,
            typography=None,
            layout=None,
            example_references=None,
            is_active=True,
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        with (
            patch(
                "src.api.routes.StyleManager.count_styles",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "src.api.routes.StyleManager.create_style",
                new_callable=AsyncMock,
                return_value=mock_style,
            ),
        ):
            request = MagicMock()
            request.state.tenant_id = "tenant-1"
            body = CreateCustomStyleRequest(name="Fresh")
            result = await create_style(body, request, mock_db)
            assert result.style_id == "s-new"
            assert result.name == "Fresh"

    @pytest.mark.asyncio
    async def test_create_style_max_reached(self, mock_db) -> None:
        from src.api.routes import create_style

        with patch(
            "src.api.routes.StyleManager.count_styles",
            new_callable=AsyncMock,
            return_value=20,
        ):
            request = MagicMock()
            request.state.tenant_id = "tenant-1"
            body = CreateCustomStyleRequest(name="One Too Many")
            with pytest.raises(HTTPException) as exc_info:
                await create_style(body, request, mock_db)
            assert exc_info.value.status_code == 409


# ============================================================================
# Get Style
# ============================================================================


class TestGetStyle:
    @pytest.mark.asyncio
    async def test_get_style_found(self, mock_db) -> None:
        from src.api.routes import get_style

        mock_style = SimpleNamespace(
            style_id="s1",
            name="Bold",
            slug="bold",
            description=None,
            color_palette=None,
            typography=None,
            layout=None,
            example_references=None,
            is_active=True,
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
        with patch(
            "src.api.routes.StyleManager.get_style",
            new_callable=AsyncMock,
            return_value=mock_style,
        ):
            request = MagicMock()
            result = await get_style("s1", request, mock_db)
            assert result.style_id == "s1"

    @pytest.mark.asyncio
    async def test_get_style_not_found(self, mock_db) -> None:
        from src.api.routes import get_style

        with patch(
            "src.api.routes.StyleManager.get_style",
            new_callable=AsyncMock,
            return_value=None,
        ):
            request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await get_style("nonexistent", request, mock_db)
            assert exc_info.value.status_code == 404


# ============================================================================
# Update Style
# ============================================================================


class TestUpdateStyle:
    @pytest.mark.asyncio
    async def test_update_style_success(self, mock_db) -> None:
        from src.api.routes import update_style

        existing = SimpleNamespace(
            style_id="s1",
            name="Old",
            slug="old",
            description=None,
            color_palette=None,
            typography=None,
            layout=None,
            example_references=None,
            is_active=True,
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
        updated = SimpleNamespace(
            style_id="s1",
            name="New Name",
            slug="new-name",
            description=None,
            color_palette=None,
            typography=None,
            layout=None,
            example_references=None,
            is_active=True,
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        with (
            patch(
                "src.api.routes.StyleManager.get_style",
                new_callable=AsyncMock,
                side_effect=[existing, updated],
            ),
            patch(
                "src.api.routes.StyleManager.update_style",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            request = MagicMock()
            request.app.state.cache_service = None
            body = UpdateCustomStyleRequest(name="New Name")
            result = await update_style("s1", body, request, mock_db)
            assert result.name == "New Name"

    @pytest.mark.asyncio
    async def test_update_style_not_found(self, mock_db) -> None:
        from src.api.routes import update_style

        with patch(
            "src.api.routes.StyleManager.get_style",
            new_callable=AsyncMock,
            return_value=None,
        ):
            request = MagicMock()
            body = UpdateCustomStyleRequest(name="New Name")
            with pytest.raises(HTTPException) as exc_info:
                await update_style("nonexistent", body, request, mock_db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_style_with_cache_invalidation(self, mock_db) -> None:
        from src.api.routes import update_style

        existing = SimpleNamespace(
            style_id="s1",
            name="Old",
            slug="old",
            description=None,
            color_palette=None,
            typography=None,
            layout=None,
            example_references=None,
            is_active=True,
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
        updated = SimpleNamespace(
            style_id="s1",
            name="Updated",
            slug="updated",
            description=None,
            color_palette=None,
            typography=None,
            layout=None,
            example_references=None,
            is_active=True,
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
        mock_cache = AsyncMock()
        mock_cache.invalidate_style = AsyncMock()

        with (
            patch(
                "src.api.routes.StyleManager.get_style",
                new_callable=AsyncMock,
                side_effect=[existing, updated],
            ),
            patch(
                "src.api.routes.StyleManager.update_style",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            request = MagicMock()
            request.app.state.cache_service = mock_cache
            body = UpdateCustomStyleRequest(name="Updated")
            await update_style("s1", body, request, mock_db)
            mock_cache.invalidate_style.assert_awaited_once_with("s1")


# ============================================================================
# Delete Style
# ============================================================================


class TestDeleteStyle:
    @pytest.mark.asyncio
    async def test_delete_style_success(self, mock_db) -> None:
        from src.api.routes import delete_style

        with patch(
            "src.api.routes.StyleManager.delete_style",
            new_callable=AsyncMock,
            return_value=True,
        ):
            request = MagicMock()
            request.app.state.cache_service = None
            result = await delete_style("s1", request, mock_db)
            assert result["deleted"] is True

    @pytest.mark.asyncio
    async def test_delete_style_not_found(self, mock_db) -> None:
        from src.api.routes import delete_style

        with patch(
            "src.api.routes.StyleManager.delete_style",
            new_callable=AsyncMock,
            return_value=False,
        ):
            request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await delete_style("nonexistent", request, mock_db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_style_with_cache(self, mock_db) -> None:
        from src.api.routes import delete_style

        mock_cache = AsyncMock()
        mock_cache.invalidate_style = AsyncMock()

        with patch(
            "src.api.routes.StyleManager.delete_style",
            new_callable=AsyncMock,
            return_value=True,
        ):
            request = MagicMock()
            request.app.state.cache_service = mock_cache
            await delete_style("s1", request, mock_db)
            mock_cache.invalidate_style.assert_awaited_once_with("s1")


# ============================================================================
# List Batches
# ============================================================================


class TestListBatches:
    @pytest.mark.asyncio
    async def test_list_batches(self, mock_db, sample_batch) -> None:
        from src.api.routes import list_batches

        batch = sample_batch()
        with patch(
            "src.services.batch_manager.BatchManager.list_batches",
            new_callable=AsyncMock,
            return_value=[batch],
        ):
            request = MagicMock()
            request.state.tenant_id = "tenant-1"
            result = await list_batches(request, mock_db)
            assert result.total == 1
            assert result.batches[0].batch_id == "batch-123"


# ============================================================================
# Cancel Batch
# ============================================================================


class TestCancelBatch:
    @pytest.mark.asyncio
    async def test_cancel_batch_success(self, mock_db) -> None:
        from src.api.routes import cancel_batch

        with patch(
            "src.services.batch_manager.BatchManager.cancel_batch",
            new_callable=AsyncMock,
            return_value=True,
        ):
            request = MagicMock()
            result = await cancel_batch("batch-1", request, mock_db)
            assert result["cancelled"] is True

    @pytest.mark.asyncio
    async def test_cancel_batch_not_possible(self, mock_db) -> None:
        from src.api.routes import cancel_batch

        with patch(
            "src.services.batch_manager.BatchManager.cancel_batch",
            new_callable=AsyncMock,
            return_value=False,
        ):
            request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await cancel_batch("batch-1", request, mock_db)
            assert exc_info.value.status_code == 409


# ============================================================================
# Webhook Deliveries
# ============================================================================


class TestGetWebhookDeliveries:
    @pytest.mark.asyncio
    async def test_get_webhook_deliveries(self, mock_db) -> None:
        from src.api.routes import get_webhook_deliveries

        mock_log = SimpleNamespace(
            attempt_number=1,
            event_type="job.completed",
            status="delivered",
            response_status=200,
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_log]
        mock_db.execute.return_value = mock_result

        request = MagicMock()
        result = await get_webhook_deliveries("job-1", request, mock_db)
        assert len(result) == 1
        assert result[0].status == "delivered"

    @pytest.mark.asyncio
    async def test_get_webhook_deliveries_empty(self, mock_db) -> None:
        from src.api.routes import get_webhook_deliveries

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        request = MagicMock()
        result = await get_webhook_deliveries("job-1", request, mock_db)
        assert len(result) == 0

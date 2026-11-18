"""Unit tests for health check endpoints."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import JSONResponse

from src.api.health import health_check, health_live, health_ready


def _make_mock_engine(should_fail: bool = False):
    """Create a mock engine with a working async context manager for connect()."""
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()

    @asynccontextmanager
    async def mock_connect():
        if should_fail:
            raise Exception("DB connection failed")
        yield mock_conn

    mock_engine = MagicMock()
    mock_engine.connect = mock_connect
    return mock_engine


class TestHealthLive:
    @pytest.mark.asyncio
    async def test_liveness_returns_ok(self) -> None:
        result = await health_live()
        assert result["status"] == "ok"


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy_when_all_ok(self) -> None:
        mock_engine = _make_mock_engine(should_fail=False)
        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with (
            patch("src.api.health.get_engine", new_callable=AsyncMock, return_value=mock_engine),
            patch("src.api.health.get_redis_client", return_value=mock_redis),
        ):
            result = await health_check()
            assert isinstance(result, dict)
            assert result["status"] == "healthy"
            components = result["components"]
            assert isinstance(components, dict)
            assert components["database"] == "healthy"
            assert components["redis"] == "healthy"
            assert components["api"] == "healthy"

    @pytest.mark.asyncio
    async def test_degraded_when_db_fails(self) -> None:
        mock_engine = _make_mock_engine(should_fail=True)
        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with (
            patch("src.api.health.get_engine", new_callable=AsyncMock, return_value=mock_engine),
            patch("src.api.health.get_redis_client", return_value=mock_redis),
        ):
            result = await health_check()
            assert isinstance(result, dict)
            assert result["status"] == "degraded"
            components = result["components"]
            assert isinstance(components, dict)
            assert "unhealthy" in components["database"]

    @pytest.mark.asyncio
    async def test_degraded_when_redis_fails(self) -> None:
        mock_engine = _make_mock_engine(should_fail=False)
        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock(side_effect=Exception("Redis down"))

        with (
            patch("src.api.health.get_engine", new_callable=AsyncMock, return_value=mock_engine),
            patch("src.api.health.get_redis_client", return_value=mock_redis),
        ):
            result = await health_check()
            assert isinstance(result, dict)
            assert result["status"] == "degraded"
            components = result["components"]
            assert isinstance(components, dict)
            assert "unhealthy" in components["redis"]

    @pytest.mark.asyncio
    async def test_redis_not_configured(self) -> None:
        mock_engine = _make_mock_engine(should_fail=False)

        with (
            patch("src.api.health.get_engine", new_callable=AsyncMock, return_value=mock_engine),
            patch("src.api.health.get_redis_client", return_value=None),
        ):
            result = await health_check()
            assert isinstance(result, dict)
            components = result["components"]
            assert isinstance(components, dict)
            assert components["redis"] == "not configured"

    @pytest.mark.asyncio
    async def test_degraded_when_both_fail(self) -> None:
        """Test that if both DB and Redis fail, status is degraded."""
        mock_engine = _make_mock_engine(should_fail=True)
        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock(side_effect=Exception("Redis down"))

        with (
            patch("src.api.health.get_engine", new_callable=AsyncMock, return_value=mock_engine),
            patch("src.api.health.get_redis_client", return_value=mock_redis),
        ):
            result = await health_check()
            assert isinstance(result, dict)
            assert result["status"] == "degraded"
            components = result["components"]
            assert isinstance(components, dict)
            assert "unhealthy" in components["database"]
            assert "unhealthy" in components["redis"]


class TestHealthReady:
    @pytest.mark.asyncio
    async def test_ready_when_db_ok(self) -> None:
        mock_engine = _make_mock_engine(should_fail=False)

        with patch("src.api.health.get_engine", new_callable=AsyncMock, return_value=mock_engine):
            result = await health_ready()
            assert isinstance(result, dict)
            assert result["ready"] is True

    @pytest.mark.asyncio
    async def test_not_ready_when_db_fails(self) -> None:
        mock_engine = _make_mock_engine(should_fail=True)

        with patch("src.api.health.get_engine", new_callable=AsyncMock, return_value=mock_engine):
            result = await health_ready()
            # Returns JSONResponse with 503 status
            assert isinstance(result, JSONResponse)
            assert result.status_code == 503

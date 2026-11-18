"""Unit tests for RateLimiterMiddleware (Phase 2 -- sliding window rate limiter)."""

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.middleware.rate_limiter import (
    RateLimiterMiddleware,
    _build_key,
    _resolve_limit,
)

# ============================================================================
# _resolve_limit
# ============================================================================


class TestResolveLimit:
    @patch("src.middleware.rate_limiter.get_settings")
    def test_redesign_endpoint(self, mock_settings: MagicMock) -> None:
        rl = MagicMock()
        rl.redesign_rpm = 10
        mock_settings.return_value.ratelimit = rl

        name, rpm = _resolve_limit("POST", "/api/v1/redesign")
        assert name == "redesign_rpm"
        assert rpm == 10

    @patch("src.middleware.rate_limiter.get_settings")
    def test_redesign_endpoint_with_trailing_slash(self, mock_settings: MagicMock) -> None:
        rl = MagicMock()
        rl.redesign_rpm = 10
        mock_settings.return_value.ratelimit = rl

        name, rpm = _resolve_limit("POST", "/api/v1/redesign/")
        assert name == "redesign_rpm"
        assert rpm == 10

    @patch("src.middleware.rate_limiter.get_settings")
    def test_batch_endpoint(self, mock_settings: MagicMock) -> None:
        rl = MagicMock()
        rl.batch_rpm = 5
        mock_settings.return_value.ratelimit = rl

        name, rpm = _resolve_limit("POST", "/api/v1/redesign/batch")
        assert name == "batch_rpm"
        assert rpm == 5

    @patch("src.middleware.rate_limiter.get_settings")
    def test_unknown_endpoint_returns_default(self, mock_settings: MagicMock) -> None:
        rl = MagicMock()
        rl.default_rpm = 60
        mock_settings.return_value.ratelimit = rl

        name, rpm = _resolve_limit("GET", "/api/v1/redesign/jobs/123")
        assert name == "default_rpm"
        assert rpm == 60


# ============================================================================
# _build_key
# ============================================================================


class TestBuildKey:
    def test_key_format(self) -> None:
        key = _build_key("tenant-abc", "redesign_rpm", 12345)
        assert key == "ratelimit:tenant-abc:redesign_rpm:12345"

    def test_key_with_different_values(self) -> None:
        key = _build_key("anon", "default_rpm", 0)
        assert key == "ratelimit:anon:default_rpm:0"


# ============================================================================
# Middleware dispatch
# ============================================================================


class TestRateLimiterMiddleware:
    @pytest.mark.asyncio
    @patch("src.middleware.rate_limiter.get_settings")
    async def test_allows_request_under_limit(self, mock_settings: MagicMock) -> None:
        rl = MagicMock()
        rl.enabled = True
        rl.redesign_rpm = 10
        rl.batch_rpm = 5
        rl.default_rpm = 60
        rl.burst_multiplier = 1.5
        mock_settings.return_value.ratelimit = rl

        middleware = RateLimiterMiddleware(app=MagicMock())

        # Mock request
        request = MagicMock()
        request.method = "POST"
        request.url.path = "/api/v1/redesign"
        request.state.tenant_id = "tenant-1"

        # Mock Redis -- current count = 1 (under limit)
        raw_redis = AsyncMock()
        raw_redis.incr = AsyncMock(return_value=1)
        raw_redis.expire = AsyncMock()
        request.app.state.redis_client._ensure_connected = MagicMock(return_value=raw_redis)

        # Mock call_next
        expected_response = MagicMock()
        expected_response.headers = {}
        call_next = AsyncMock(return_value=expected_response)

        response = await middleware.dispatch(request, call_next)
        call_next.assert_awaited_once_with(request)
        assert response.headers.get("X-RateLimit-Limit") == str(math.ceil(10 * 1.5))

    @pytest.mark.asyncio
    @patch("src.middleware.rate_limiter.get_settings")
    async def test_returns_429_when_limit_exceeded(self, mock_settings: MagicMock) -> None:
        rl = MagicMock()
        rl.enabled = True
        rl.redesign_rpm = 10
        rl.batch_rpm = 5
        rl.default_rpm = 60
        rl.burst_multiplier = 1.5
        mock_settings.return_value.ratelimit = rl

        middleware = RateLimiterMiddleware(app=MagicMock())

        request = MagicMock()
        request.method = "POST"
        request.url.path = "/api/v1/redesign"
        request.state.tenant_id = "tenant-1"

        # Redis returns a count that exceeds the burst limit (ceil(10 * 1.5) = 15)
        raw_redis = AsyncMock()
        raw_redis.incr = AsyncMock(return_value=16)
        request.app.state.redis_client._ensure_connected = MagicMock(return_value=raw_redis)

        call_next = AsyncMock()

        response = await middleware.dispatch(request, call_next)
        # Should NOT have called the next handler
        call_next.assert_not_awaited()
        assert response.status_code == 429

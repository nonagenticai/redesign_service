"""Unit tests for CacheService (Phase 2 -- application-level caching)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.cache_service import CacheService

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_redis_client() -> MagicMock:
    """Create a mock RedisClient with async helpers."""
    client = MagicMock()
    # The raw redis.Redis object returned by _ensure_connected
    raw = AsyncMock()
    client._ensure_connected = MagicMock(return_value=raw)
    # High-level RedisClient methods used by style caching
    client.set = AsyncMock(return_value=True)
    client.get = AsyncMock(return_value=None)
    client.delete = AsyncMock(return_value=True)
    return client


@pytest.fixture
def cache_service(mock_redis_client: MagicMock) -> CacheService:
    return CacheService(mock_redis_client)


# ============================================================================
# HTML caching
# ============================================================================


class TestCacheHtml:
    @pytest.mark.asyncio
    async def test_cache_html_stores_and_returns_true(
        self, cache_service: CacheService, mock_redis_client: MagicMock
    ) -> None:
        raw = mock_redis_client._ensure_connected()
        raw.setex = AsyncMock(return_value=True)

        result = await cache_service.cache_html("https://example.com", "<html>OK</html>")
        assert result is True
        raw.setex.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_cached_html_returns_value(
        self, cache_service: CacheService, mock_redis_client: MagicMock
    ) -> None:
        raw = mock_redis_client._ensure_connected()
        raw.get = AsyncMock(return_value="<html>cached</html>")

        result = await cache_service.get_cached_html("https://example.com")
        assert result == "<html>cached</html>"

    @pytest.mark.asyncio
    async def test_get_cached_html_returns_none_on_miss(
        self, cache_service: CacheService, mock_redis_client: MagicMock
    ) -> None:
        raw = mock_redis_client._ensure_connected()
        raw.get = AsyncMock(return_value=None)

        result = await cache_service.get_cached_html("https://example.com/missing")
        assert result is None


# ============================================================================
# Style description caching
# ============================================================================


class TestCacheStyleDescription:
    @pytest.mark.asyncio
    async def test_cache_style_description_success(
        self, cache_service: CacheService, mock_redis_client: MagicMock
    ) -> None:
        result = await cache_service.cache_style_description("modern", "A clean modern style")
        assert result is True
        mock_redis_client.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_cached_style_description_hit(
        self, cache_service: CacheService, mock_redis_client: MagicMock
    ) -> None:
        mock_redis_client.get = AsyncMock(return_value="A clean modern style")
        result = await cache_service.get_cached_style_description("modern")
        assert result == "A clean modern style"

    @pytest.mark.asyncio
    async def test_get_cached_style_description_miss(
        self, cache_service: CacheService, mock_redis_client: MagicMock
    ) -> None:
        mock_redis_client.get = AsyncMock(return_value=None)
        result = await cache_service.get_cached_style_description("unknown_style")
        assert result is None


# ============================================================================
# Invalidation
# ============================================================================


class TestInvalidateStyle:
    @pytest.mark.asyncio
    async def test_invalidate_style_success(
        self, cache_service: CacheService, mock_redis_client: MagicMock
    ) -> None:
        result = await cache_service.invalidate_style("modern")
        assert result is True
        mock_redis_client.delete.assert_awaited_once()


# ============================================================================
# Graceful failure
# ============================================================================


class TestGracefulRedisFailure:
    @pytest.mark.asyncio
    async def test_cache_html_returns_false_on_error(
        self, cache_service: CacheService, mock_redis_client: MagicMock
    ) -> None:
        mock_redis_client._ensure_connected.side_effect = RuntimeError("Redis down")
        result = await cache_service.cache_html("https://example.com", "<html>x</html>")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_cached_html_returns_none_on_error(
        self, cache_service: CacheService, mock_redis_client: MagicMock
    ) -> None:
        mock_redis_client._ensure_connected.side_effect = RuntimeError("Redis down")
        result = await cache_service.get_cached_html("https://example.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_style_returns_none_on_error(
        self, cache_service: CacheService, mock_redis_client: MagicMock
    ) -> None:
        mock_redis_client.get = AsyncMock(side_effect=RuntimeError("Redis down"))
        result = await cache_service.get_cached_style_description("modern")
        assert result is None

    @pytest.mark.asyncio
    async def test_invalidate_returns_false_on_error(
        self, cache_service: CacheService, mock_redis_client: MagicMock
    ) -> None:
        mock_redis_client.delete = AsyncMock(side_effect=RuntimeError("Redis down"))
        result = await cache_service.invalidate_style("modern")
        assert result is False

    @pytest.mark.asyncio
    async def test_cache_style_description_returns_false_on_error(
        self, cache_service: CacheService, mock_redis_client: MagicMock
    ) -> None:
        mock_redis_client.set = AsyncMock(side_effect=RuntimeError("Redis down"))
        result = await cache_service.cache_style_description("modern", "A style")
        assert result is False


# ============================================================================
# Job result caching
# ============================================================================


class TestCacheJobResult:
    @pytest.mark.asyncio
    async def test_cache_job_result_success(
        self, cache_service: CacheService, mock_redis_client: MagicMock
    ) -> None:
        result = await cache_service.cache_job_result("job-1", {"html": "<p>Done</p>"})
        assert result is True
        mock_redis_client.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_job_result_returns_false_on_error(
        self, cache_service: CacheService, mock_redis_client: MagicMock
    ) -> None:
        mock_redis_client.set = AsyncMock(side_effect=RuntimeError("Redis down"))
        result = await cache_service.cache_job_result("job-1", {"html": "<p>x</p>"})
        assert result is False

    @pytest.mark.asyncio
    async def test_get_cached_job_result_hit(
        self, cache_service: CacheService, mock_redis_client: MagicMock
    ) -> None:
        mock_redis_client.get = AsyncMock(return_value={"html": "<p>cached</p>"})
        result = await cache_service.get_cached_job_result("job-1")
        assert result == {"html": "<p>cached</p>"}

    @pytest.mark.asyncio
    async def test_get_cached_job_result_miss(
        self, cache_service: CacheService, mock_redis_client: MagicMock
    ) -> None:
        mock_redis_client.get = AsyncMock(return_value=None)
        result = await cache_service.get_cached_job_result("job-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_job_result_wrong_type(
        self, cache_service: CacheService, mock_redis_client: MagicMock
    ) -> None:
        mock_redis_client.get = AsyncMock(return_value="not-a-dict")
        result = await cache_service.get_cached_job_result("job-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_job_result_returns_none_on_error(
        self, cache_service: CacheService, mock_redis_client: MagicMock
    ) -> None:
        mock_redis_client.get = AsyncMock(side_effect=RuntimeError("Redis down"))
        result = await cache_service.get_cached_job_result("job-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_invalidate_job_result_success(
        self, cache_service: CacheService, mock_redis_client: MagicMock
    ) -> None:
        result = await cache_service.invalidate_job_result("job-1")
        assert result is True
        mock_redis_client.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalidate_job_result_returns_false_on_error(
        self, cache_service: CacheService, mock_redis_client: MagicMock
    ) -> None:
        mock_redis_client.delete = AsyncMock(side_effect=RuntimeError("Redis down"))
        result = await cache_service.invalidate_job_result("job-1")
        assert result is False


# ============================================================================
# HTML bytes decoding
# ============================================================================


class TestHtmlBytesDecoding:
    @pytest.mark.asyncio
    async def test_get_cached_html_decodes_bytes(
        self, cache_service: CacheService, mock_redis_client: MagicMock
    ) -> None:
        raw = mock_redis_client._ensure_connected()
        raw.get = AsyncMock(return_value=b"<html>bytes</html>")
        result = await cache_service.get_cached_html("https://example.com")
        assert result == "<html>bytes</html>"

"""Application-level caching service wrapping RedisClient."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from src.cache.redis_client import RedisClient

logger = logging.getLogger(__name__)

# Key prefix constants
_HTML_PREFIX = "redesign:html:"
_STYLE_PREFIX = "redesign:style:"
_RESULT_PREFIX = "redesign:result:"


def _url_hash(url: str) -> str:
    """Compute a SHA-256 hex digest of a URL for use as a cache key."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


class CacheService:
    """High-level caching facade for the redesign service.

    Wraps a ``RedisClient`` instance and provides typed helpers for
    caching fetched HTML pages and style descriptions with appropriate
    key patterns and TTLs.
    """

    def __init__(self, redis_client: RedisClient) -> None:
        self._redis = redis_client

    # ------------------------------------------------------------------
    # HTML caching
    # ------------------------------------------------------------------

    async def cache_html(
        self,
        url: str,
        html: str,
        ttl: int = 3600,
    ) -> bool:
        """Cache fetched HTML content keyed by the SHA-256 of *url*.

        HTML is stored as a raw string (not JSON-serialized) to avoid
        the overhead of encoding large payloads through ``json.dumps``.

        Returns ``True`` on success, ``False`` if the write fails.
        """
        key = f"{_HTML_PREFIX}{_url_hash(url)}"
        try:
            client = self._redis._ensure_connected()
            result = await client.setex(key, ttl, html)
            return bool(result)
        except Exception:
            logger.warning("Failed to cache HTML for url=%s", url, exc_info=True)
            return False

    async def get_cached_html(self, url: str) -> str | None:
        """Retrieve previously cached HTML for *url*.

        Returns the raw HTML string or ``None`` when the key is absent
        or a Redis error occurs.
        """
        key = f"{_HTML_PREFIX}{_url_hash(url)}"
        try:
            client = self._redis._ensure_connected()
            value = await client.get(key)
            if value is None:
                return None
            # When decode_responses is True the value is already a str;
            # otherwise it arrives as bytes.
            if isinstance(value, bytes):
                return value.decode("utf-8")
            return value  # type: ignore[return-value]
        except Exception:
            logger.warning(
                "Failed to retrieve cached HTML for url=%s",
                url,
                exc_info=True,
            )
            return None

    # ------------------------------------------------------------------
    # Style description caching
    # ------------------------------------------------------------------

    async def cache_style_description(
        self,
        style_id: str,
        description: str,
        ttl: int = 600,
    ) -> bool:
        """Cache a resolved style description.

        Uses the standard ``RedisClient.set`` path (JSON-serialized)
        which is fine for short textual descriptions.

        Returns ``True`` on success, ``False`` on failure.
        """
        key = f"{_STYLE_PREFIX}{style_id}"
        try:
            return await self._redis.set(key, description, ttl=ttl)
        except Exception:
            logger.warning(
                "Failed to cache style description for style_id=%s",
                style_id,
                exc_info=True,
            )
            return False

    async def get_cached_style_description(
        self,
        style_id: str,
    ) -> str | None:
        """Return a cached style description, or ``None`` on miss."""
        key = f"{_STYLE_PREFIX}{style_id}"
        try:
            value = await self._redis.get(key)
            if isinstance(value, str):
                return value
            return None
        except Exception:
            logger.warning(
                "Failed to retrieve cached style for style_id=%s",
                style_id,
                exc_info=True,
            )
            return None

    async def invalidate_style(self, style_id: str) -> bool:
        """Remove a cached style description.

        Returns ``True`` when the key existed and was deleted,
        ``False`` otherwise (including on Redis errors).
        """
        key = f"{_STYLE_PREFIX}{style_id}"
        try:
            return await self._redis.delete(key)
        except Exception:
            logger.warning(
                "Failed to invalidate style cache for style_id=%s",
                style_id,
                exc_info=True,
            )
            return False

    # ------------------------------------------------------------------
    # Job result caching
    # ------------------------------------------------------------------

    async def cache_job_result(
        self,
        job_id: str,
        result: dict[str, Any],
        ttl: int = 1800,
    ) -> bool:
        """Cache a completed job result.

        Uses the standard ``RedisClient.set`` path (JSON-serialized)
        which handles dict serialization via ``json.dumps``.

        Returns ``True`` on success, ``False`` on failure.
        """
        key = f"{_RESULT_PREFIX}{job_id}"
        try:
            return await self._redis.set(key, result, ttl=ttl)
        except Exception:
            logger.warning(
                "Failed to cache job result for job_id=%s",
                job_id,
                exc_info=True,
            )
            return False

    async def get_cached_job_result(
        self,
        job_id: str,
    ) -> dict[str, Any] | None:
        """Retrieve a cached job result, or ``None`` on miss."""
        key = f"{_RESULT_PREFIX}{job_id}"
        try:
            value = await self._redis.get(key)
            if isinstance(value, dict):
                return value
            return None
        except Exception:
            logger.warning(
                "Failed to retrieve cached result for job_id=%s",
                job_id,
                exc_info=True,
            )
            return None

    async def invalidate_job_result(self, job_id: str) -> bool:
        """Remove a cached job result.

        Returns ``True`` when the key existed and was deleted,
        ``False`` otherwise (including on Redis errors).
        """
        key = f"{_RESULT_PREFIX}{job_id}"
        try:
            return await self._redis.delete(key)
        except Exception:
            logger.warning(
                "Failed to invalidate result cache for job_id=%s",
                job_id,
                exc_info=True,
            )
            return False

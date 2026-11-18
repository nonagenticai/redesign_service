"""Redis-based sliding window rate limiter middleware for FastAPI."""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Awaitable, Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from src.config import get_settings

logger = logging.getLogger(__name__)

# Window size in seconds (1 minute for RPM-based limits).
_WINDOW_SECONDS = 60

# Endpoint path patterns mapped to their rate-limit setting names.
# Evaluated in order; first match wins.
_ENDPOINT_LIMITS: list[tuple[str, str, str]] = [
    # (method, path_prefix, settings_attr)
    ("POST", "/api/v1/redesign/batch", "batch_rpm"),
    ("POST", "/api/v1/redesign", "redesign_rpm"),
]


def _resolve_limit(method: str, path: str) -> tuple[str, int]:
    """Return (limit_name, requests_per_minute) for a request.

    Matches against known endpoint patterns. Falls back to the
    configured ``default_rpm`` for unrecognised routes.
    """
    settings = get_settings()
    rl = settings.ratelimit

    for ep_method, ep_prefix, attr in _ENDPOINT_LIMITS:
        if method == ep_method and path.rstrip("/").startswith(ep_prefix.rstrip("/")):
            rpm: int = getattr(rl, attr)
            return attr, rpm

    return "default_rpm", rl.default_rpm


def _build_key(tenant_id: str, endpoint: str, window: int) -> str:
    """Build the Redis key for a rate-limit counter.

    Pattern: ``ratelimit:{tenant_id}:{endpoint}:{window}``
    """
    return f"ratelimit:{tenant_id}:{endpoint}:{window}"


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter backed by Redis INCR + EXPIRE.

    When a tenant exceeds the configured RPM for an endpoint the
    middleware returns **429 Too Many Requests** with a ``Retry-After``
    header indicating how many seconds the caller should wait.

    The middleware degrades gracefully: if Redis is unavailable the
    request is allowed through without rate-limit enforcement.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        settings = get_settings()

        # Short-circuit when rate limiting is disabled globally.
        if not settings.ratelimit.enabled:
            return await call_next(request)

        # Resolve identity and target limit.
        tenant_id: str = getattr(request.state, "tenant_id", "anonymous")
        method = request.method
        path = request.url.path

        limit_name, rpm = _resolve_limit(method, path)
        burst_limit = math.ceil(rpm * settings.ratelimit.burst_multiplier)

        # Determine the current window bucket.
        now = time.time()
        window = int(now // _WINDOW_SECONDS)
        key = _build_key(tenant_id, limit_name, window)

        # Attempt to increment the counter in Redis.
        try:
            redis_client = request.app.state.redis_client
            raw = redis_client._ensure_connected()
            current: int = await raw.incr(key)
            if current == 1:
                # First request in this window -- set expiry so the
                # key is automatically cleaned up.
                await raw.expire(key, _WINDOW_SECONDS + 1)
        except Exception:
            # Redis unavailable -- allow the request through.
            logger.debug("Rate limiter: Redis unavailable, skipping enforcement")
            return await call_next(request)

        # Enforce the limit.
        if current > burst_limit:
            retry_after = _WINDOW_SECONDS - int(now % _WINDOW_SECONDS)
            logger.warning(
                "Rate limit exceeded for tenant=%s endpoint=%s current=%d limit=%d",
                tenant_id,
                limit_name,
                current,
                burst_limit,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "limit": burst_limit,
                    "window_seconds": _WINDOW_SECONDS,
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        # Attach rate-limit info as response headers for observability.
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(burst_limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, burst_limit - current))
        response.headers["X-RateLimit-Reset"] = str((window + 1) * _WINDOW_SECONDS)
        return response

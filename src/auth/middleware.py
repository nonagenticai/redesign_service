"""License token authentication middleware."""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from cachetools import TTLCache
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from .models import User

logger = logging.getLogger(__name__)

_license_cache: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=1000, ttl=300)

LICENSE_INTROSPECT_URL = os.getenv(
    "LICENSE_INTROSPECT_URL",
    "http://licenses.licenses:8544/license/introspect",
)

DEFAULT_TENANT_ID = os.getenv("DEFAULT_TENANT_ID", "n8n-dev")

_TRUSTED_CIDRS_RAW = os.getenv(
    "TRUSTED_CIDRS",
    "127.0.0.1/32,::1/128,192.168.0.0/16,172.16.0.0/12,10.0.0.0/8",
)
TRUSTED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network(cidr.strip(), strict=False)
    for cidr in _TRUSTED_CIDRS_RAW.split(",")
    if cidr.strip()
]

PUBLIC_ENDPOINTS: set[str] = {
    "/",
    "/health",
    "/health/ready",
    "/health/live",
    "/healthz",
    "/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/health",
    "/api/health/ready",
    "/api/health/live",
    "/favicon.ico",
}

PUBLIC_PREFIXES: tuple[str, ...] = (
    "/docs",
    "/redoc",
    "/health/",
    "/api/health/",
)


def _is_trusted_network(host: str | None) -> bool:
    if not host:
        return False
    try:
        addr = ipaddress.ip_address(host)
        return any(addr in net for net in TRUSTED_NETWORKS)
    except ValueError:
        return False


async def _introspect_license(token: str) -> dict[str, Any] | None:
    cache_key = f"lic:{hashlib.sha256(token.encode()).hexdigest()[:16]}"
    if cache_key in _license_cache:
        return _license_cache[cache_key]
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.post(LICENSE_INTROSPECT_URL, json={"token": token})
            if resp.status_code == 200:
                data: dict[str, Any] = resp.json()
                if data.get("active"):
                    _license_cache[cache_key] = data
                return data
    except Exception as e:
        logger.warning("License introspection failed: %s", e)
    return None


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to validate license tokens."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path.rstrip("/") or "/"

        if path in PUBLIC_ENDPOINTS or path.startswith(PUBLIC_PREFIXES):
            return await call_next(request)

        token = self._extract_license_token(request)

        if token:
            result = await _introspect_license(token)
            if not result or not result.get("active"):
                reason = result.get("reason", "invalid_token") if result else "invalid_token"
                return JSONResponse(
                    status_code=401,
                    content={"detail": f"Invalid or expired license token: {reason}"},
                )
            tenant_id = result.get("tenant_id", result.get("subject_id", ""))
            user = User(
                sub=tenant_id,
                preferred_username=result.get("subject_id", tenant_id),
                tenant_id=tenant_id,
            )
            request.state.user = user
            request.state.tenant_id = tenant_id
            request.state.license = result
            return await call_next(request)

        client_host = request.client.host if request.client else None
        if _is_trusted_network(client_host):
            x_tenant_id = request.headers.get("X-Tenant-Id")
            tenant_id = x_tenant_id.strip() if x_tenant_id else DEFAULT_TENANT_ID
            user = User(
                sub=tenant_id,
                preferred_username="internal",
                tenant_id=tenant_id,
            )
            request.state.user = user
            request.state.tenant_id = tenant_id
            request.state.license = None
            return await call_next(request)

        return JSONResponse(
            status_code=401,
            content={"detail": "Missing authentication token"},
        )

    def _extract_license_token(self, request: Request) -> str | None:
        x_tenant_id = request.headers.get("X-Tenant-Id")
        if x_tenant_id and x_tenant_id.lower().startswith("bearer "):
            return x_tenant_id[7:].strip()
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            return auth_header[7:].strip()
        return None

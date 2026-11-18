"""Unit tests for auth middleware."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.auth.middleware import (
    PUBLIC_ENDPOINTS,
    PUBLIC_PREFIXES,
    AuthMiddleware,
    _introspect_license,
    _is_trusted_network,
)
from src.auth.models import User

# ============================================================================
# User model
# ============================================================================


class TestUserModel:
    def test_user_creation(self) -> None:
        user = User(sub="tenant-1", preferred_username="admin", tenant_id="tenant-1")
        assert user.sub == "tenant-1"
        assert user.preferred_username == "admin"

    def test_effective_tenant_id_with_tenant(self) -> None:
        user = User(sub="sub-1", tenant_id="tenant-1")
        assert user.effective_tenant_id == "tenant-1"

    def test_effective_tenant_id_without_tenant(self) -> None:
        user = User(sub="sub-1", tenant_id=None)
        assert user.effective_tenant_id == "sub-1"

    def test_default_username(self) -> None:
        user = User(sub="sub-1")
        assert user.preferred_username == "anonymous"


# ============================================================================
# _is_trusted_network
# ============================================================================


class TestIsTrustedNetwork:
    def test_localhost_ipv4_is_trusted(self) -> None:
        assert _is_trusted_network("127.0.0.1") is True

    def test_localhost_ipv6_is_trusted(self) -> None:
        assert _is_trusted_network("::1") is True

    def test_private_network_192_168(self) -> None:
        assert _is_trusted_network("192.168.1.1") is True

    def test_private_network_172_16(self) -> None:
        assert _is_trusted_network("172.16.0.1") is True

    def test_private_network_10(self) -> None:
        assert _is_trusted_network("10.0.0.1") is True

    def test_public_ip_not_trusted(self) -> None:
        assert _is_trusted_network("8.8.8.8") is False

    def test_none_not_trusted(self) -> None:
        assert _is_trusted_network(None) is False

    def test_empty_string_not_trusted(self) -> None:
        assert _is_trusted_network("") is False

    def test_invalid_ip_not_trusted(self) -> None:
        assert _is_trusted_network("not-an-ip") is False


# ============================================================================
# Public endpoints
# ============================================================================


class TestPublicEndpoints:
    def test_health_is_public(self) -> None:
        assert "/health" in PUBLIC_ENDPOINTS

    def test_healthz_is_public(self) -> None:
        assert "/healthz" in PUBLIC_ENDPOINTS

    def test_docs_is_public(self) -> None:
        assert "/docs" in PUBLIC_ENDPOINTS

    def test_api_health_is_public(self) -> None:
        assert "/api/health" in PUBLIC_ENDPOINTS


class TestPublicPrefixes:
    def test_docs_prefix(self) -> None:
        assert "/docs" in PUBLIC_PREFIXES

    def test_health_prefix(self) -> None:
        assert "/health/" in PUBLIC_PREFIXES


# ============================================================================
# AuthMiddleware._extract_license_token
# ============================================================================


class TestExtractLicenseToken:
    def _make_middleware(self) -> AuthMiddleware:
        return AuthMiddleware(app=MagicMock())

    def test_bearer_in_authorization_header(self) -> None:
        middleware = self._make_middleware()
        request = MagicMock()
        request.headers = {"Authorization": "Bearer test-token-123"}
        token = middleware._extract_license_token(request)
        assert token == "test-token-123"

    def test_bearer_in_x_tenant_id_header(self) -> None:
        middleware = self._make_middleware()
        request = MagicMock()
        request.headers = {"X-Tenant-Id": "Bearer my-license-token"}
        token = middleware._extract_license_token(request)
        assert token == "my-license-token"

    def test_no_token_found(self) -> None:
        middleware = self._make_middleware()
        request = MagicMock()
        request.headers = {}
        token = middleware._extract_license_token(request)
        assert token is None

    def test_x_tenant_id_without_bearer_prefix(self) -> None:
        middleware = self._make_middleware()
        request = MagicMock()
        request.headers = {"X-Tenant-Id": "plain-tenant-id"}
        token = middleware._extract_license_token(request)
        assert token is None


# ============================================================================
# _introspect_license
# ============================================================================


class TestIntrospectLicense:
    @pytest.mark.asyncio
    async def test_cache_hit(self) -> None:
        from src.auth.middleware import _license_cache

        _license_cache.clear()
        import hashlib

        token = "cached-token"
        cache_key = f"lic:{hashlib.sha256(token.encode()).hexdigest()[:16]}"
        _license_cache[cache_key] = {"active": True, "tenant_id": "t1"}

        result = await _introspect_license(token)
        assert result is not None
        assert result["tenant_id"] == "t1"
        _license_cache.clear()

    @pytest.mark.asyncio
    async def test_successful_introspection(self) -> None:
        from src.auth.middleware import _license_cache

        _license_cache.clear()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"active": True, "tenant_id": "tenant-42"}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("src.auth.middleware.httpx.AsyncClient", return_value=mock_client):
            result = await _introspect_license("fresh-token")
            assert result is not None
            assert result["active"] is True
            assert result["tenant_id"] == "tenant-42"
        _license_cache.clear()

    @pytest.mark.asyncio
    async def test_introspection_failure(self) -> None:
        from src.auth.middleware import _license_cache

        _license_cache.clear()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))

        with patch("src.auth.middleware.httpx.AsyncClient", return_value=mock_client):
            result = await _introspect_license("bad-token")
            assert result is None
        _license_cache.clear()

    @pytest.mark.asyncio
    async def test_inactive_license_not_cached(self) -> None:
        from src.auth.middleware import _license_cache

        _license_cache.clear()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"active": False}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("src.auth.middleware.httpx.AsyncClient", return_value=mock_client):
            result = await _introspect_license("inactive-token")
            assert result is not None
            assert result["active"] is False
        # Inactive should not be cached
        assert len(_license_cache) == 0
        _license_cache.clear()


# ============================================================================
# AuthMiddleware.dispatch
# ============================================================================


class TestAuthMiddlewareDispatch:
    def _make_middleware(self) -> AuthMiddleware:
        return AuthMiddleware(app=MagicMock())

    @pytest.mark.asyncio
    async def test_public_endpoint_passes_through(self) -> None:
        middleware = self._make_middleware()
        request = MagicMock()
        request.url.path = "/health"
        call_next = AsyncMock(return_value=MagicMock())

        await middleware.dispatch(request, call_next)
        call_next.assert_awaited_once_with(request)

    @pytest.mark.asyncio
    async def test_public_prefix_passes_through(self) -> None:
        middleware = self._make_middleware()
        request = MagicMock()
        request.url.path = "/docs/swagger"
        call_next = AsyncMock(return_value=MagicMock())

        await middleware.dispatch(request, call_next)
        call_next.assert_awaited_once_with(request)

    @pytest.mark.asyncio
    async def test_valid_token_sets_state(self) -> None:
        middleware = self._make_middleware()
        request = MagicMock()
        request.url.path = "/api/v1/redesign"
        request.headers = {"Authorization": "Bearer valid-token"}
        request.state = MagicMock()
        call_next = AsyncMock(return_value=MagicMock())

        with patch(
            "src.auth.middleware._introspect_license",
            new_callable=AsyncMock,
            return_value={"active": True, "tenant_id": "t-1", "subject_id": "user-1"},
        ):
            await middleware.dispatch(request, call_next)
            assert request.state.tenant_id == "t-1"
            call_next.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self) -> None:
        middleware = self._make_middleware()
        request = MagicMock()
        request.url.path = "/api/v1/redesign"
        request.headers = {"Authorization": "Bearer bad-token"}
        request.client = MagicMock()
        request.client.host = "8.8.8.8"
        call_next = AsyncMock()

        with patch(
            "src.auth.middleware._introspect_license",
            new_callable=AsyncMock,
            return_value={"active": False, "reason": "expired"},
        ):
            response = await middleware.dispatch(request, call_next)
            assert response.status_code == 401
            call_next.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_trusted_network_without_token(self) -> None:
        middleware = self._make_middleware()
        request = MagicMock()
        request.url.path = "/api/v1/redesign"
        request.headers = {"X-Tenant-Id": "my-tenant"}
        request.state = MagicMock()
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        call_next = AsyncMock(return_value=MagicMock())

        await middleware.dispatch(request, call_next)
        assert request.state.tenant_id == "my-tenant"
        call_next.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_untrusted_network_without_token_returns_401(self) -> None:
        middleware = self._make_middleware()
        request = MagicMock()
        request.url.path = "/api/v1/redesign"
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "203.0.113.1"
        call_next = AsyncMock()

        response = await middleware.dispatch(request, call_next)
        assert response.status_code == 401
        call_next.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_client_host_returns_401(self) -> None:
        middleware = self._make_middleware()
        request = MagicMock()
        request.url.path = "/api/v1/redesign"
        request.headers = {}
        request.client = None
        call_next = AsyncMock()

        response = await middleware.dispatch(request, call_next)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_trusted_network_default_tenant(self) -> None:
        middleware = self._make_middleware()
        request = MagicMock()
        request.url.path = "/api/v1/redesign"
        request.headers = {}
        request.state = MagicMock()
        request.client = MagicMock()
        request.client.host = "10.0.0.5"
        call_next = AsyncMock(return_value=MagicMock())

        await middleware.dispatch(request, call_next)
        # Should use DEFAULT_TENANT_ID
        assert request.state.tenant_id is not None
        call_next.assert_awaited_once()

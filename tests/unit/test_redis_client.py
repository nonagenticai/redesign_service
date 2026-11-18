"""Unit tests for RedisClient."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.cache.redis_client import RedisClient


class TestRedisClientInit:
    def test_default_init(self) -> None:
        with patch("src.cache.redis_client.get_settings") as mock_settings:
            s = MagicMock()
            s.redis.url = "redis://localhost:6396/0"
            s.redis.max_connections = 10
            s.redis.socket_timeout = 5
            s.redis.socket_connect_timeout = 5
            s.redis.decode_responses = True
            mock_settings.return_value = s

            client = RedisClient()
            assert client._redis_url == "redis://localhost:6396/0"
            assert client._max_connections == 10
            assert client._pool is None
            assert client._client is None

    def test_custom_url(self) -> None:
        with patch("src.cache.redis_client.get_settings") as mock_settings:
            s = MagicMock()
            s.redis.url = "redis://default:6379/0"
            s.redis.max_connections = 5
            s.redis.socket_timeout = 3
            s.redis.socket_connect_timeout = 3
            s.redis.decode_responses = False
            mock_settings.return_value = s

            client = RedisClient(redis_url="redis://custom:9999/1")
            assert client._redis_url == "redis://custom:9999/1"


class TestRedisClientSerialization:
    def _make_client(self) -> RedisClient:
        with patch("src.cache.redis_client.get_settings") as mock_settings:
            s = MagicMock()
            s.redis.url = "redis://localhost:6396/0"
            s.redis.max_connections = 10
            s.redis.socket_timeout = 5
            s.redis.socket_connect_timeout = 5
            s.redis.decode_responses = True
            mock_settings.return_value = s
            return RedisClient()

    def test_serialize_dict(self) -> None:
        client = self._make_client()
        result = client._serialize({"key": "value"})
        assert json.loads(result) == {"key": "value"}

    def test_serialize_pydantic_model(self) -> None:
        client = self._make_client()
        mock_model = MagicMock()
        mock_model.model_dump.return_value = {"name": "test"}
        result = client._serialize(mock_model)
        assert json.loads(result) == {"name": "test"}

    def test_deserialize_valid_json(self) -> None:
        client = self._make_client()
        result = client._deserialize('{"key": "value"}')
        assert result == {"key": "value"}

    def test_deserialize_none(self) -> None:
        client = self._make_client()
        assert client._deserialize(None) is None

    def test_deserialize_invalid_json(self) -> None:
        client = self._make_client()
        assert client._deserialize("not-json{{") is None


class TestRedisClientEnsureConnected:
    def _make_client(self) -> RedisClient:
        with patch("src.cache.redis_client.get_settings") as mock_settings:
            s = MagicMock()
            s.redis.url = "redis://localhost:6396/0"
            s.redis.max_connections = 10
            s.redis.socket_timeout = 5
            s.redis.socket_connect_timeout = 5
            s.redis.decode_responses = True
            mock_settings.return_value = s
            return RedisClient()

    def test_not_connected_raises(self) -> None:
        client = self._make_client()
        with pytest.raises(RuntimeError, match="not connected"):
            client._ensure_connected()

    def test_connected_returns_client(self) -> None:
        client = self._make_client()
        mock_redis = MagicMock()
        client._client = mock_redis
        assert client._ensure_connected() is mock_redis


class TestRedisClientOperations:
    def _make_connected_client(self) -> tuple[RedisClient, AsyncMock]:
        with patch("src.cache.redis_client.get_settings") as mock_settings:
            s = MagicMock()
            s.redis.url = "redis://localhost:6396/0"
            s.redis.max_connections = 10
            s.redis.socket_timeout = 5
            s.redis.socket_connect_timeout = 5
            s.redis.decode_responses = True
            mock_settings.return_value = s
            client = RedisClient()
            mock_redis = AsyncMock()
            client._client = mock_redis
            return client, mock_redis

    @pytest.mark.asyncio
    async def test_get_existing_key(self) -> None:
        client, mock_redis = self._make_connected_client()
        mock_redis.get = AsyncMock(return_value='{"data": 42}')
        result = await client.get("my-key")
        assert result == {"data": 42}

    @pytest.mark.asyncio
    async def test_get_missing_key(self) -> None:
        client, mock_redis = self._make_connected_client()
        mock_redis.get = AsyncMock(return_value=None)
        result = await client.get("missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_error_returns_none(self) -> None:
        client, mock_redis = self._make_connected_client()
        mock_redis.get = AsyncMock(side_effect=Exception("Redis error"))
        result = await client.get("error-key")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_without_ttl(self) -> None:
        client, mock_redis = self._make_connected_client()
        mock_redis.set = AsyncMock(return_value=True)
        result = await client.set("key", {"value": 1})
        assert result is True
        mock_redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_set_with_ttl(self) -> None:
        client, mock_redis = self._make_connected_client()
        mock_redis.setex = AsyncMock(return_value=True)
        result = await client.set("key", {"value": 1}, ttl=300)
        assert result is True
        mock_redis.setex.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_set_error_returns_false(self) -> None:
        client, mock_redis = self._make_connected_client()
        mock_redis.set = AsyncMock(side_effect=Exception("Redis error"))
        result = await client.set("key", "value")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_success(self) -> None:
        client, mock_redis = self._make_connected_client()
        mock_redis.delete = AsyncMock(return_value=1)
        result = await client.delete("key")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_error(self) -> None:
        client, mock_redis = self._make_connected_client()
        mock_redis.delete = AsyncMock(side_effect=Exception("fail"))
        result = await client.delete("key")
        assert result is False

    @pytest.mark.asyncio
    async def test_exists_true(self) -> None:
        client, mock_redis = self._make_connected_client()
        mock_redis.exists = AsyncMock(return_value=1)
        result = await client.exists("key")
        assert result is True

    @pytest.mark.asyncio
    async def test_exists_false(self) -> None:
        client, mock_redis = self._make_connected_client()
        mock_redis.exists = AsyncMock(return_value=0)
        result = await client.exists("key")
        assert result is False

    @pytest.mark.asyncio
    async def test_exists_error(self) -> None:
        client, mock_redis = self._make_connected_client()
        mock_redis.exists = AsyncMock(side_effect=Exception("fail"))
        result = await client.exists("key")
        assert result is False

    @pytest.mark.asyncio
    async def test_ping_success(self) -> None:
        client, mock_redis = self._make_connected_client()
        mock_redis.ping = AsyncMock(return_value=True)
        result = await client.ping()
        assert result is True

    @pytest.mark.asyncio
    async def test_ping_error(self) -> None:
        client, mock_redis = self._make_connected_client()
        mock_redis.ping = AsyncMock(side_effect=Exception("fail"))
        result = await client.ping()
        assert result is False


class TestRedisClientContextManager:
    @pytest.mark.asyncio
    async def test_aenter_aexit(self) -> None:
        with patch("src.cache.redis_client.get_settings") as mock_settings:
            s = MagicMock()
            s.redis.url = "redis://localhost:6396/0"
            s.redis.max_connections = 10
            s.redis.socket_timeout = 5
            s.redis.socket_connect_timeout = 5
            s.redis.decode_responses = True
            mock_settings.return_value = s

            client = RedisClient()
            mock_connect = AsyncMock()
            mock_disconnect = AsyncMock()
            object.__setattr__(client, "connect", mock_connect)
            object.__setattr__(client, "disconnect", mock_disconnect)

            async with client as c:
                assert c is client
                mock_connect.assert_awaited_once()

            mock_disconnect.assert_awaited_once()


class TestRedisClientConnect:
    @pytest.mark.asyncio
    async def test_connect_success(self) -> None:
        with patch("src.cache.redis_client.get_settings") as mock_settings:
            s = MagicMock()
            s.redis.url = "redis://localhost:6396/0"
            s.redis.max_connections = 10
            s.redis.socket_timeout = 5
            s.redis.socket_connect_timeout = 5
            s.redis.decode_responses = True
            mock_settings.return_value = s

            client = RedisClient()

            mock_pool = MagicMock()
            mock_redis_instance = MagicMock()
            # Simulate ping returning an awaitable
            mock_redis_instance.ping.return_value = AsyncMock(return_value=True)()

            with (
                patch("src.cache.redis_client.ConnectionPool.from_url", return_value=mock_pool),
                patch("src.cache.redis_client.redis.Redis", return_value=mock_redis_instance),
            ):
                await client.connect()
                assert client._pool is mock_pool
                assert client._client is mock_redis_instance


class TestRedisClientDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect(self) -> None:
        with patch("src.cache.redis_client.get_settings") as mock_settings:
            s = MagicMock()
            s.redis.url = "redis://localhost:6396/0"
            s.redis.max_connections = 10
            s.redis.socket_timeout = 5
            s.redis.socket_connect_timeout = 5
            s.redis.decode_responses = True
            mock_settings.return_value = s

            client = RedisClient()
            mock_redis_instance = AsyncMock()
            mock_pool = AsyncMock()
            client._client = mock_redis_instance
            client._pool = mock_pool

            await client.disconnect()
            mock_redis_instance.aclose.assert_awaited_once()
            mock_pool.aclose.assert_awaited_once()
            assert client._client is None
            assert client._pool is None

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self) -> None:
        with patch("src.cache.redis_client.get_settings") as mock_settings:
            s = MagicMock()
            s.redis.url = "redis://localhost:6396/0"
            s.redis.max_connections = 10
            s.redis.socket_timeout = 5
            s.redis.socket_connect_timeout = 5
            s.redis.decode_responses = True
            mock_settings.return_value = s

            client = RedisClient()
            await client.disconnect()  # Should not raise

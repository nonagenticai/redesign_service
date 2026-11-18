"""Redis client for redesign_service caching."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool

from src.config import get_settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Async Redis client for caching operations."""

    def __init__(self, redis_url: str | None = None):
        settings = get_settings()
        self._redis_url = redis_url or settings.redis.url
        self._max_connections = settings.redis.max_connections
        self._socket_timeout = settings.redis.socket_timeout
        self._socket_connect_timeout = settings.redis.socket_connect_timeout
        self._decode_responses = settings.redis.decode_responses
        self._pool: ConnectionPool | None = None
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        if self._pool is None:
            self._pool = ConnectionPool.from_url(
                self._redis_url,
                max_connections=self._max_connections,
                socket_timeout=self._socket_timeout,
                socket_connect_timeout=self._socket_connect_timeout,
                decode_responses=self._decode_responses,
            )
            self._client = redis.Redis(connection_pool=self._pool)
            try:
                ping_result = self._client.ping()
                if hasattr(ping_result, "__await__"):
                    await ping_result
                logger.info("Redis connection successful")
            except Exception as e:
                logger.error("Redis connection failed: %s", e)
                raise

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._pool:
            await self._pool.aclose()
            self._pool = None

    async def __aenter__(self) -> RedisClient:
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.disconnect()

    def _ensure_connected(self) -> redis.Redis:
        if self._client is None:
            raise RuntimeError("RedisClient not connected. Call connect() first.")
        return self._client

    def _serialize(self, value: Any) -> str:
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        return json.dumps(value)

    def _deserialize(self, value: str | None) -> Any:
        if value is None:
            return None
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return None

    async def get(self, key: str) -> Any | None:
        client = self._ensure_connected()
        try:
            value = await client.get(key)
            return self._deserialize(value) if value else None
        except Exception as e:
            logger.error("Error getting key '%s': %s", key, e)
            return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        client = self._ensure_connected()
        try:
            serialized = self._serialize(value)
            if ttl is not None:
                result = await client.setex(key, ttl, serialized)
            else:
                result = await client.set(key, serialized)
            return bool(result)
        except Exception as e:
            logger.error("Error setting key '%s': %s", key, e)
            return False

    async def delete(self, key: str) -> bool:
        client = self._ensure_connected()
        try:
            result = await client.delete(key)
            return bool(result)
        except Exception as e:
            logger.error("Error deleting key '%s': %s", key, e)
            return False

    async def exists(self, key: str) -> bool:
        client = self._ensure_connected()
        try:
            result = await client.exists(key)
            return bool(result)
        except Exception as e:
            logger.error("Error checking key '%s': %s", key, e)
            return False

    async def ping(self) -> bool:
        client = self._ensure_connected()
        try:
            ping_result = client.ping()
            if hasattr(ping_result, "__await__"):
                result = await ping_result
            else:
                result = ping_result
            return bool(result)
        except Exception as e:
            logger.error("Redis ping failed: %s", e)
            return False


_redis_client: RedisClient | None = None


@lru_cache
def get_redis_client() -> RedisClient:
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client


async def init_redis() -> RedisClient:
    client = get_redis_client()
    await client.connect()
    return client


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.disconnect()
        _redis_client = None

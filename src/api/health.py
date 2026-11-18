"""Health check endpoints for redesign_service."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.cache.redis_client import get_redis_client
from src.database.connection import get_engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=None)
async def health_check() -> dict[str, Any] | JSONResponse:
    """Combined health check for all components."""
    try:
        db_status = "healthy"
        try:
            engine = await get_engine()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as e:
            db_status = f"unhealthy: {e}"

        redis_status = "healthy"
        try:
            redis_client = get_redis_client()
            if redis_client:
                await redis_client.ping()
            else:
                redis_status = "not configured"
        except Exception as e:
            redis_status = f"unhealthy: {e}"

        overall = "healthy" if db_status == "healthy" and redis_status == "healthy" else "degraded"

        return {
            "status": overall,
            "components": {
                "database": db_status,
                "redis": redis_status,
                "api": "healthy",
            },
        }
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "error": str(e)})


@router.get("/health/live", response_model=None)
async def health_live() -> dict[str, str]:
    """Kubernetes liveness probe."""
    return {"status": "ok"}


@router.get("/health/ready", response_model=None)
async def health_ready() -> dict[str, Any] | JSONResponse:
    """Kubernetes readiness probe -- checks database connectivity."""
    try:
        engine = await get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"ready": True, "checks": {"database": {"status": "up"}}}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"ready": False, "checks": {"database": {"status": "down", "error": str(e)}}},
        )

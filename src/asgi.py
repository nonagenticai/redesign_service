"""
ASGI application for redesign_service.

FastAPI REST API following skill_builder/tts_service pattern.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.cache.redis_client import close_redis, get_redis_client, init_redis
from src.config import get_settings
from src.database.connection import close_engine, get_engine
from src.database.session import get_session_maker
from src.services.accessibility_scorer import AccessibilityScorer
from src.services.concept_image_generator import ConceptImageGenerator
from src.services.html_generator import HtmlGenerator
from src.services.prompt_template import PromptTemplateLoader
from src.services.redesign_service import RedesignService
from src.services.storage_service import StorageService
from src.services.webhook_dispatcher import WebhookDispatcher

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()


# ============================================================================
# Health Check Logging Filter
# ============================================================================


class HealthCheckLoggingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not any(path in message for path in ["/health", "/health/ready", "/health/live"])


uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.addFilter(HealthCheckLoggingFilter())


# ============================================================================
# Lifespan
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan -- init DB, Redis, services."""
    logger.info("=" * 70)
    logger.info("Starting Redesign Service")
    logger.info("=" * 70)

    # Database
    try:
        db_engine = await get_engine()
        app.state.db_engine = db_engine
        app.state.session_factory = await get_session_maker()
        logger.info("Database connected: %s", settings.database.url)
    except Exception as e:
        logger.error("Failed to connect to database: %s", e, exc_info=True)
        raise

    # Schema is owned by alembic (alembic/versions), NOT by create_all.
    # create_all here left alembic_version empty while the tables already
    # existed, so a subsequent 'alembic upgrade head' hit 001_initial_schema's
    # CREATE TABLE and failed. Run migrations before starting the service.

    # Redis
    try:
        redis_client = await init_redis()
        await redis_client.ping()
        app.state.redis_client = get_redis_client()
        logger.info("Redis connected: %s", settings.redis.url)
    except Exception as e:
        logger.error("Failed to connect to Redis: %s", e, exc_info=True)
        logger.warning("Continuing without Redis -- caching will be disabled")

    # Cache service (wraps Redis)
    cache_svc = None
    try:
        from src.services.cache_service import CacheService

        cache_svc = CacheService(get_redis_client())
        logger.info("CacheService initialized")
    except Exception as e:
        logger.warning("CacheService not available: %s", e)
    app.state.cache_service = cache_svc

    # Storage
    storage = StorageService()
    await storage.initialize()
    app.state.storage_service = storage

    # Prompt template loader (Feature 1)
    template_loader = PromptTemplateLoader(
        version=settings.templates.version,
        template_dir=settings.templates.directory,
    )

    # Services
    html_gen = HtmlGenerator(template_loader=template_loader)
    concept_gen = ConceptImageGenerator(template_loader=template_loader)
    a11y_scorer = AccessibilityScorer()
    webhook_dispatcher = (
        WebhookDispatcher(
            max_retries=settings.webhook.max_retries,
            backoff_base=settings.webhook.backoff_base,
            timeout=settings.webhook.timeout,
        )
        if settings.webhook.enabled
        else None
    )

    app.state.redesign_service = RedesignService(
        storage=storage,
        html_generator=html_gen,
        concept_generator=concept_gen,
        accessibility_scorer=a11y_scorer,
        webhook_dispatcher=webhook_dispatcher,
        cache_service=cache_svc,
    )

    # Cleanup service (data retention)
    from src.services.cleanup_service import CleanupService

    cleanup_svc = CleanupService(storage=storage)
    app.state.cleanup_service = cleanup_svc

    cleanup_task = None
    if settings.retention.cleanup_enabled:

        async def _periodic_cleanup() -> None:
            """Run cleanup every 24 hours."""
            while True:
                await asyncio.sleep(86400)  # 24 hours
                try:
                    async with app.state.session_factory() as db:
                        removed = await cleanup_svc.cleanup_old_jobs(
                            db,
                            retention_days=settings.retention.retention_days,
                        )
                        await db.commit()
                        logger.info("Periodic cleanup removed %d jobs", removed)
                except Exception as exc:
                    logger.error("Periodic cleanup failed: %s", exc, exc_info=True)

        cleanup_task = asyncio.create_task(_periodic_cleanup())
        logger.info(
            "Periodic cleanup enabled (retention=%d days)", settings.retention.retention_days
        )

    logger.info("=" * 70)
    logger.info("Redesign Service started successfully")
    logger.info("Environment: %s", settings.environment)
    logger.info("API: %s:%d", settings.api.host, settings.api.port)
    logger.info("LLM model: %s", settings.llm.model)
    logger.info("Screenshots: %s", "enabled" if settings.screenshot.enabled else "disabled")
    logger.info("Concept images: %s", "enabled" if settings.dalle.enabled else "disabled")
    logger.info("=" * 70)

    yield

    # Shutdown
    logger.info("Shutting down Redesign Service")
    if cleanup_task is not None:
        cleanup_task.cancel()
    try:
        await close_redis()
    except Exception as e:
        logger.error("Error closing Redis: %s", e, exc_info=True)
    try:
        await close_engine()
    except Exception as e:
        logger.error("Error closing database: %s", e, exc_info=True)
    logger.info("Redesign Service shutdown complete")


# ============================================================================
# Create App
# ============================================================================

app = FastAPI(
    title=settings.app_name,
    description="AI-powered website redesign microservice with screenshot rendering",
    version=settings.app_version,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,  # type: ignore[arg-type]
    allow_origins=settings.api.cors_origins,
    allow_credentials=settings.api.cors_allow_credentials,
    allow_methods=settings.api.cors_allow_methods,
    allow_headers=settings.api.cors_allow_headers,
)

# Rate limiter middleware (Enhancement 3)
from src.middleware.rate_limiter import RateLimiterMiddleware  # noqa: E402

if settings.ratelimit.enabled:
    app.add_middleware(RateLimiterMiddleware)  # type: ignore[arg-type]
    logger.info("Rate limiting middleware enabled (default=%d rpm)", settings.ratelimit.default_rpm)

# Auth middleware
from src.auth.middleware import AuthMiddleware  # noqa: E402

if settings.auth.enabled:
    app.add_middleware(AuthMiddleware)  # type: ignore[arg-type]
    logger.info("Authentication middleware enabled")
else:
    logger.warning("Running WITHOUT authentication -- development mode only!")


# ============================================================================
# Root & Health Endpoints
# ============================================================================


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "description": "AI-powered website redesign microservice with screenshot rendering",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "redesign": "/api/v1/redesign",
            "jobs": "/api/v1/redesign/jobs/{job_id}",
        },
        "status": "running",
        "environment": settings.environment,
    }


# Mount routers
from src.api.health import router as health_router  # noqa: E402
from src.api.routes import router as api_router  # noqa: E402

app.include_router(health_router)
app.include_router(api_router)


# ============================================================================
# Error Handlers
# ============================================================================


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(
        "Unhandled exception in request %s: %s",
        request_id,
        exc,
        exc_info=True,
    )
    error_detail = str(exc) if settings.api.debug else "Internal server error"
    return JSONResponse(
        status_code=500,
        content={
            "detail": error_detail,
            "type": type(exc).__name__,
            "request_id": request_id,
        },
    )


# ============================================================================
# Main Entry Point
# ============================================================================


def main() -> None:
    """Main entry point for running the ASGI application."""
    import uvicorn

    uvicorn.run(
        "src.asgi:app",
        host=settings.api.host,
        port=settings.api.port,
        log_level=settings.logging.level.lower(),
        reload=settings.api.reload,
    )


if __name__ == "__main__":
    main()

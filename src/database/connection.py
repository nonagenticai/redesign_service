"""Database connection module with connection pooling and initialization."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from urllib.parse import urlparse, urlunparse

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5456/redesign_service",  # pragma: allowlist secret
)

parsed_url = urlparse(DATABASE_URL)
DB_HOST = parsed_url.hostname or "localhost"
DB_PORT = parsed_url.port or 5432
DB_NAME = parsed_url.path.lstrip("/") if parsed_url.path else "postgres"
DB_USER = parsed_url.username or "postgres"
DB_PASSWORD = parsed_url.password or ""

DB_POOL_MIN_SIZE = int(os.getenv("POSTGRES_POOL_MIN_SIZE", "2"))
DB_POOL_MAX_SIZE = int(os.getenv("POSTGRES_POOL_MAX_SIZE", "10"))
DB_POOL_TIMEOUT = int(os.getenv("POSTGRES_POOL_TIMEOUT", "30"))
DB_POOL_RECYCLE = int(os.getenv("POSTGRES_POOL_RECYCLE", "3600"))
DB_ADMIN_DB = os.getenv("POSTGRES_ADMIN_DB", "postgres")

_engine: AsyncEngine | None = None


async def _ensure_database_exists(max_retries: int = 3) -> None:
    """Ensure the target database exists, creating it if necessary."""
    if not re.fullmatch(r"[A-Za-z0-9_]+", DB_NAME):
        raise ValueError(
            f"Database name '{DB_NAME}' contains invalid characters; "
            f"only alphanumeric and underscore are supported."
        )

    admin_url_parts = list(urlparse(DATABASE_URL))
    admin_url_parts[2] = f"/{DB_ADMIN_DB}"
    admin_url = urlunparse(admin_url_parts)

    if admin_url.startswith("postgresql+psycopg://"):
        sync_admin_url = admin_url.replace("postgresql+psycopg://", "postgresql://")
    else:
        sync_admin_url = admin_url

    logger.info(
        "Ensuring PostgreSQL database '%s' exists using admin database '%s' at %s:%s",
        DB_NAME,
        DB_ADMIN_DB,
        DB_HOST,
        DB_PORT,
    )

    last_error = None
    for attempt in range(1, max_retries + 1):
        engine = None
        try:
            engine = create_engine(sync_admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
            with engine.connect() as conn:
                result = conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :db_name"),
                    {"db_name": DB_NAME},
                )
                if result.scalar() is not None:
                    logger.info("Database '%s' already exists", DB_NAME)
                    return
                try:
                    conn.execute(text(f"CREATE DATABASE {DB_NAME}"))
                    logger.info("Database '%s' created successfully", DB_NAME)
                    return
                except ProgrammingError as e:
                    if "already exists" in str(e).lower():
                        return
                    raise
        except (OperationalError, OSError, ConnectionRefusedError) as e:
            last_error = e
            if attempt < max_retries:
                await asyncio.sleep(attempt * 2)
        except Exception as e:
            logger.error("Unexpected error ensuring database exists: %s", e, exc_info=True)
            raise
        finally:
            if engine:
                try:
                    engine.dispose()
                except Exception as exc:
                    logger.warning("Failed to dispose engine during cleanup: %s", exc)

    raise ConnectionError(
        f"Failed to connect to admin database at {DB_HOST}:{DB_PORT} "
        f"after {max_retries} attempts. Last error: {last_error}"
    )


async def create_engine_with_retry(max_retries: int = 5, retry_delay: float = 2.0) -> AsyncEngine:
    """Create database engine with connection retry logic."""
    last_error = None
    current_delay = retry_delay

    for attempt in range(1, max_retries + 1):
        try:
            pool_config = {
                "poolclass": AsyncAdaptedQueuePool,
                "pool_size": DB_POOL_MIN_SIZE,
                "max_overflow": DB_POOL_MAX_SIZE - DB_POOL_MIN_SIZE,
                "pool_timeout": DB_POOL_TIMEOUT,
                "pool_recycle": DB_POOL_RECYCLE,
                "pool_pre_ping": True,
                "echo": os.getenv("SQL_ECHO", "false").lower() == "true",
            }
            engine = create_async_engine(DATABASE_URL, **pool_config)
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Successfully created engine on attempt %d", attempt)
            return engine

        except (OperationalError, ProgrammingError) as e:
            error_msg = str(e).lower()
            if "database" in error_msg and "does not exist" in error_msg:
                try:
                    await _ensure_database_exists()
                    pool_config = {
                        "poolclass": AsyncAdaptedQueuePool,
                        "pool_size": DB_POOL_MIN_SIZE,
                        "max_overflow": DB_POOL_MAX_SIZE - DB_POOL_MIN_SIZE,
                        "pool_timeout": DB_POOL_TIMEOUT,
                        "pool_recycle": DB_POOL_RECYCLE,
                        "pool_pre_ping": True,
                        "echo": os.getenv("SQL_ECHO", "false").lower() == "true",
                    }
                    engine = create_async_engine(DATABASE_URL, **pool_config)
                    async with engine.begin() as conn:
                        await conn.execute(text("SELECT 1"))
                    return engine
                except Exception as create_err:
                    last_error = create_err
            else:
                last_error = e
            if attempt < max_retries:
                await asyncio.sleep(current_delay)
                current_delay *= 2

        except (TimeoutError, OSError, ConnectionRefusedError) as e:
            last_error = e
            if attempt < max_retries:
                await asyncio.sleep(current_delay)
                current_delay *= 2

        except Exception as e:
            last_error = e
            if attempt < max_retries:
                await asyncio.sleep(current_delay)
                current_delay *= 2

    raise ConnectionError(
        f"Failed to connect to PostgreSQL at {DB_HOST}:{DB_PORT}/{DB_NAME} "
        f"after {max_retries} attempts. Last error: {last_error}"
    ) from last_error


async def get_engine() -> AsyncEngine:
    """Get or create the global database engine instance."""
    global _engine
    if _engine is None:
        _engine = await create_engine_with_retry()
    return _engine


async def health_check() -> bool:
    """Perform a health check on the database connection."""
    try:
        engine = await get_engine()
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("Database health check failed: %s", e, exc_info=True)
        return False


async def close_engine() -> None:
    """Close the global database engine."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        logger.info("Database engine closed successfully")

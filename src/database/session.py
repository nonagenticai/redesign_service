"""Database session management module."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .connection import get_engine

logger = logging.getLogger(__name__)

_async_session_maker: async_sessionmaker[AsyncSession] | None = None


async def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get or create the global async session maker."""
    global _async_session_maker
    if _async_session_maker is None:
        engine = await get_engine()
        _async_session_maker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _async_session_maker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions."""
    session_maker = await get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for manual database session management."""
    session_maker = await get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_session_maker() -> None:
    """Reset the global session maker instance."""
    global _async_session_maker
    _async_session_maker = None

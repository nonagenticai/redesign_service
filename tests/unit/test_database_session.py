"""Unit tests for database session management."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.database.session import close_session_maker, get_db, get_db_session, get_session_maker


class TestGetSessionMaker:
    @pytest.mark.asyncio
    async def test_creates_session_maker(self) -> None:
        import src.database.session as session_mod

        original = session_mod._async_session_maker
        session_mod._async_session_maker = None

        mock_engine = AsyncMock()
        with patch(
            "src.database.session.get_engine", new_callable=AsyncMock, return_value=mock_engine
        ):
            maker = await get_session_maker()
            assert maker is not None

        session_mod._async_session_maker = original

    @pytest.mark.asyncio
    async def test_returns_cached_session_maker(self) -> None:
        import src.database.session as session_mod

        original = session_mod._async_session_maker
        mock_maker = MagicMock()
        session_mod._async_session_maker = mock_maker

        result = await get_session_maker()
        assert result is mock_maker

        session_mod._async_session_maker = original


class TestCloseSessionMaker:
    @pytest.mark.asyncio
    async def test_close_resets_global(self) -> None:
        import src.database.session as session_mod

        original = session_mod._async_session_maker
        session_mod._async_session_maker = MagicMock()

        await close_session_maker()
        assert session_mod._async_session_maker is None

        session_mod._async_session_maker = original


class TestGetDb:
    @pytest.mark.asyncio
    async def test_get_db_yields_session(self) -> None:
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()

        mock_maker = MagicMock()
        mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.database.session.get_session_maker",
            new_callable=AsyncMock,
            return_value=mock_maker,
        ):
            gen = get_db()
            session = await gen.__anext__()
            assert session is mock_session
            # Complete the generator
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass


class TestGetDbSession:
    @pytest.mark.asyncio
    async def test_get_db_session_context_manager(self) -> None:
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()

        mock_maker = MagicMock()
        mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.database.session.get_session_maker",
            new_callable=AsyncMock,
            return_value=mock_maker,
        ):
            async with get_db_session() as session:
                assert session is mock_session

"""Extended unit tests for StyleManager CRUD and resolve_style_description."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.services.style_manager import StyleManager


class TestResolveStyleDescription:
    def test_description_only(self) -> None:
        style = SimpleNamespace(
            name="My Style",
            description="A bold, vibrant style",
            color_palette=None,
            typography=None,
            layout=None,
            example_references=None,
        )
        result = StyleManager.resolve_style_description(style)
        assert "A bold, vibrant style" in result

    def test_with_color_palette(self) -> None:
        style = SimpleNamespace(
            name="Colorful",
            description=None,
            color_palette={
                "primary": "#FF0000",
                "secondary": "#00FF00",
                "accent": "#0000FF",
                "background": "#FFFFFF",
                "text": "#000000",
            },
            typography=None,
            layout=None,
            example_references=None,
        )
        result = StyleManager.resolve_style_description(style)
        assert "primary=#FF0000" in result
        assert "secondary=#00FF00" in result
        assert "accent=#0000FF" in result
        assert "background=#FFFFFF" in result
        assert "text=#000000" in result

    def test_with_typography(self) -> None:
        style = SimpleNamespace(
            name="Typo",
            description=None,
            color_palette=None,
            typography={
                "heading_font": "Georgia",
                "body_font": "Arial",
                "scale": "spacious",
            },
            layout=None,
            example_references=None,
        )
        result = StyleManager.resolve_style_description(style)
        assert "Georgia" in result
        assert "Arial" in result
        assert "spacious" in result

    def test_with_layout(self) -> None:
        style = SimpleNamespace(
            name="Layout Style",
            description=None,
            color_palette=None,
            typography=None,
            layout={
                "max_width": "1200px",
                "spacing": "generous",
                "grid_columns": 12,
                "border_radius": "large",
            },
            example_references=None,
        )
        result = StyleManager.resolve_style_description(style)
        assert "1200px" in result
        assert "generous" in result
        assert "12-column" in result
        assert "large" in result

    def test_with_example_references(self) -> None:
        style = SimpleNamespace(
            name="Ref Style",
            description=None,
            color_palette=None,
            typography=None,
            layout=None,
            example_references=[
                "https://stripe.com",
                "https://linear.app",
                "https://vercel.com",
                "https://extra.com",  # Should be limited to 3
            ],
        )
        result = StyleManager.resolve_style_description(style)
        assert "stripe.com" in result
        assert "linear.app" in result
        assert "vercel.com" in result
        assert "extra.com" not in result

    def test_no_fields_fallback(self) -> None:
        style = SimpleNamespace(
            name="Empty Style",
            description=None,
            color_palette=None,
            typography=None,
            layout=None,
            example_references=None,
        )
        result = StyleManager.resolve_style_description(style)
        assert "Empty Style" in result

    def test_all_fields(self) -> None:
        style = SimpleNamespace(
            name="Full Style",
            description="A comprehensive style",
            color_palette={"primary": "#111"},
            typography={"heading_font": "Inter"},
            layout={"max_width": "960px"},
            example_references=["https://example.com"],
        )
        result = StyleManager.resolve_style_description(style)
        assert "comprehensive" in result
        assert "primary=#111" in result
        assert "Inter" in result
        assert "960px" in result
        assert "example.com" in result

    def test_empty_color_palette(self) -> None:
        style = SimpleNamespace(
            name="Empty Colors",
            description="Test",
            color_palette={},
            typography=None,
            layout=None,
            example_references=None,
        )
        result = StyleManager.resolve_style_description(style)
        assert "Color palette" not in result

    def test_partial_typography(self) -> None:
        style = SimpleNamespace(
            name="Partial Typo",
            description=None,
            color_palette=None,
            typography={"heading_font": "Roboto"},
            layout=None,
            example_references=None,
        )
        result = StyleManager.resolve_style_description(style)
        assert "Roboto" in result
        assert "body text" not in result

    def test_partial_layout(self) -> None:
        style = SimpleNamespace(
            name="Partial Layout",
            description=None,
            color_palette=None,
            typography=None,
            layout={"spacing": "tight"},
            example_references=None,
        )
        result = StyleManager.resolve_style_description(style)
        assert "tight" in result
        assert "max width" not in result


class TestStyleManagerCRUD:
    @pytest.mark.asyncio
    async def test_create_style(self, mock_db) -> None:
        style = await StyleManager.create_style(
            mock_db,
            tenant_id="tenant-1",
            name="My Bold Style",
            description="A bold style",
        )
        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()
        assert style.name == "My Bold Style"
        assert style.slug == "my-bold-style"
        assert style.is_active is True

    @pytest.mark.asyncio
    async def test_create_style_with_all_fields(self, mock_db) -> None:
        style = await StyleManager.create_style(
            mock_db,
            tenant_id="tenant-1",
            name="Full Style",
            description="Desc",
            color_palette={"primary": "#FF0000"},
            typography={"heading_font": "Georgia"},
            layout={"max_width": "1200px"},
            example_references=["https://example.com"],
        )
        assert style.color_palette == {"primary": "#FF0000"}
        assert style.typography == {"heading_font": "Georgia"}

    @pytest.mark.asyncio
    async def test_get_style(self, mock_db) -> None:
        mock_style = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_style
        mock_db.execute.return_value = mock_result

        result = await StyleManager.get_style(mock_db, "style-123")
        assert result is mock_style

    @pytest.mark.asyncio
    async def test_get_style_by_slug(self, mock_db) -> None:
        mock_style = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_style
        mock_db.execute.return_value = mock_result

        result = await StyleManager.get_style_by_slug(mock_db, "tenant-1", "my-bold-style")
        assert result is mock_style

    @pytest.mark.asyncio
    async def test_list_styles(self, mock_db) -> None:
        mock_styles = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_styles
        mock_db.execute.return_value = mock_result

        result = await StyleManager.list_styles(mock_db, "tenant-1")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_update_style_with_name(self, mock_db) -> None:
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        result = await StyleManager.update_style(mock_db, "style-123", name="New Name")
        assert result is True

    @pytest.mark.asyncio
    async def test_update_style_no_valid_fields(self, mock_db) -> None:
        result = await StyleManager.update_style(mock_db, "style-123", invalid_field="value")
        assert result is False

    @pytest.mark.asyncio
    async def test_update_style_none_values_excluded(self, mock_db) -> None:
        result = await StyleManager.update_style(mock_db, "style-123", name=None, description=None)
        assert result is False

    @pytest.mark.asyncio
    async def test_count_styles(self, mock_db) -> None:
        mock_result = MagicMock()
        mock_result.scalar.return_value = 5
        mock_db.execute.return_value = mock_result

        result = await StyleManager.count_styles(mock_db, "tenant-1")
        assert result == 5

    @pytest.mark.asyncio
    async def test_count_styles_none(self, mock_db) -> None:
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_db.execute.return_value = mock_result

        result = await StyleManager.count_styles(mock_db, "tenant-1")
        assert result == 0

    @pytest.mark.asyncio
    async def test_delete_style_success(self, mock_db) -> None:
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        result = await StyleManager.delete_style(mock_db, "style-123")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_style_not_found(self, mock_db) -> None:
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        result = await StyleManager.delete_style(mock_db, "nonexistent")
        assert result is False

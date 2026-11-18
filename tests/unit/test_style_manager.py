"""Unit tests for StyleManager helpers."""

from src.services.style_manager import slugify


class TestSlugify:
    def test_basic_slugify(self) -> None:
        assert slugify("Modern Clean") == "modern-clean"

    def test_special_characters(self) -> None:
        assert slugify("Bold & Vibrant!") == "bold-vibrant"

    def test_multiple_spaces(self) -> None:
        assert slugify("  Lots   of   Spaces  ") == "lots-of-spaces"

    def test_underscores_to_hyphens(self) -> None:
        assert slugify("my_custom_style") == "my-custom-style"

    def test_already_slug(self) -> None:
        assert slugify("already-a-slug") == "already-a-slug"

    def test_numbers(self) -> None:
        assert slugify("Style v2.0") == "style-v20"

    def test_empty_string(self) -> None:
        assert slugify("") == ""

    def test_unicode(self) -> None:
        result = slugify("Café Style")
        assert "caf" in result

"""Unit tests for PromptTemplateLoader."""

from pathlib import Path

import pytest

from src.services.prompt_template import PromptTemplateLoader


class TestPromptTemplateLoader:
    @pytest.fixture()
    def template_dir(self, tmp_path: Path) -> Path:
        """Create a temporary template directory structure."""
        v1_dir = tmp_path / "v1"
        v1_dir.mkdir()
        (v1_dir / "system_prompt.md.j2").write_text("You are a {{ role }} designer.")
        (v1_dir / "full_page.md.j2").write_text("Redesign {{ url }} in {{ style }} style.")
        return tmp_path

    def test_render_template(self, template_dir: Path) -> None:
        loader = PromptTemplateLoader(version="v1", template_dir=str(template_dir))
        result = loader.render("system_prompt.md.j2", role="senior")
        assert result is not None
        assert "senior designer" in result

    def test_render_with_variables(self, template_dir: Path) -> None:
        loader = PromptTemplateLoader(version="v1", template_dir=str(template_dir))
        result = loader.render("full_page.md.j2", url="https://example.com", style="modern")
        assert result is not None
        assert "https://example.com" in result
        assert "modern" in result

    def test_render_missing_template_returns_none(self, template_dir: Path) -> None:
        loader = PromptTemplateLoader(version="v1", template_dir=str(template_dir))
        result = loader.render("nonexistent.md.j2")
        assert result is None

    def test_render_or_fallback_uses_template(self, template_dir: Path) -> None:
        loader = PromptTemplateLoader(version="v1", template_dir=str(template_dir))
        result = loader.render_or_fallback("system_prompt.md.j2", "fallback text", role="expert")
        assert "expert designer" in result
        assert "fallback" not in result

    def test_render_or_fallback_uses_fallback(self, template_dir: Path) -> None:
        loader = PromptTemplateLoader(version="v1", template_dir=str(template_dir))
        result = loader.render_or_fallback("missing.md.j2", "fallback text")
        assert result == "fallback text"

    def test_has_template(self, template_dir: Path) -> None:
        loader = PromptTemplateLoader(version="v1", template_dir=str(template_dir))
        assert loader.has_template("system_prompt.md.j2") is True
        assert loader.has_template("nonexistent.md.j2") is False

    def test_list_templates(self, template_dir: Path) -> None:
        loader = PromptTemplateLoader(version="v1", template_dir=str(template_dir))
        templates = loader.list_templates()
        assert "system_prompt.md.j2" in templates
        assert "full_page.md.j2" in templates

    def test_version_property(self, template_dir: Path) -> None:
        loader = PromptTemplateLoader(version="v2", template_dir=str(template_dir))
        assert loader.version == "v2"

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        loader = PromptTemplateLoader(version="v1", template_dir=str(tmp_path / "nonexistent"))
        assert loader.render("anything.j2") is None
        assert loader.list_templates() == []

    def test_default_version(self, template_dir: Path) -> None:
        loader = PromptTemplateLoader(template_dir=str(template_dir))
        assert loader.version == "v1"

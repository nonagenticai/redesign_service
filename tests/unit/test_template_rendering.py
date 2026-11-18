"""Unit tests for PromptTemplateLoader and template rendering (Phase 2)."""

import pytest

from src.services.prompt_template import PromptTemplateLoader

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def loader() -> PromptTemplateLoader:
    """Create a PromptTemplateLoader using the default v1 templates."""
    return PromptTemplateLoader(version="v1")


# Sample context values used across multiple template tests.
_SAMPLE_CONTEXT = {
    "url": "https://example.com",
    "page_type": "homepage",
    "html_excerpt": "<html><body><h1>Hello</h1></body></html>",
    "audience": "small business owners",
    "primary_color": "#2563EB",
    "secondary_color": "#1E40AF",
    "tone": "professional",
    "findings_text": "- Image missing alt attribute",
    "style": "modern",
    "style_desc": "A clean, modern design with generous whitespace.",
    "context_block": "",
}


# ============================================================================
# Template availability
# ============================================================================


class TestTemplateAvailability:
    def test_full_page_template_exists(self, loader: PromptTemplateLoader) -> None:
        assert loader.has_template("full_page.md.j2")

    def test_section_template_exists(self, loader: PromptTemplateLoader) -> None:
        assert loader.has_template("section.md.j2")

    def test_system_prompt_template_exists(self, loader: PromptTemplateLoader) -> None:
        assert loader.has_template("system_prompt.md.j2")

    def test_component_template_exists(self, loader: PromptTemplateLoader) -> None:
        assert loader.has_template("component.md.j2")

    def test_refinement_template_exists(self, loader: PromptTemplateLoader) -> None:
        assert loader.has_template("refinement.md.j2")


# ============================================================================
# Rendering without errors
# ============================================================================


class TestFullPageRendering:
    def test_renders_without_error(self, loader: PromptTemplateLoader) -> None:
        result = loader.render("full_page.md.j2", **_SAMPLE_CONTEXT)
        assert result is not None
        assert len(result) > 0

    def test_contains_url(self, loader: PromptTemplateLoader) -> None:
        result = loader.render("full_page.md.j2", **_SAMPLE_CONTEXT)
        assert result is not None
        assert "https://example.com" in result

    def test_contains_style_description(self, loader: PromptTemplateLoader) -> None:
        result = loader.render("full_page.md.j2", **_SAMPLE_CONTEXT)
        assert result is not None
        assert "modern" in result.lower()


class TestSectionRendering:
    def test_renders_without_error(self, loader: PromptTemplateLoader) -> None:
        ctx = {
            **_SAMPLE_CONTEXT,
            "section_type": "hero",
            "heading": "Welcome",
            "text_preview": "Welcome to our site.",
        }
        result = loader.render("section.md.j2", **ctx)
        assert result is not None
        assert "hero" in result.lower()


class TestSystemPromptRendering:
    def test_renders_without_error(self, loader: PromptTemplateLoader) -> None:
        result = loader.render("system_prompt.md.j2")
        assert result is not None
        assert "HTML" in result or "html" in result


class TestComponentRendering:
    def test_renders_without_error(self, loader: PromptTemplateLoader) -> None:
        ctx = {
            **_SAMPLE_CONTEXT,
            "component_type": "navbar",
            "component_html": "<nav><a href='/'>Home</a></nav>",
            "design_tips": "",
        }
        result = loader.render("component.md.j2", **ctx)
        assert result is not None
        assert "navbar" in result.lower()


class TestRefinementRendering:
    def test_renders_without_error(self, loader: PromptTemplateLoader) -> None:
        ctx = {
            **_SAMPLE_CONTEXT,
            "feedback": "Make the hero section bigger",
            "focus_areas": ["hero", "CTA"],
        }
        result = loader.render("refinement.md.j2", **ctx)
        assert result is not None
        assert "feedback" in result.lower() or "Make the hero" in result


# ============================================================================
# render_or_fallback
# ============================================================================


class TestRenderOrFallback:
    def test_returns_fallback_for_missing_template(self, loader: PromptTemplateLoader) -> None:
        fallback = "This is the fallback text."
        result = loader.render_or_fallback("nonexistent_template.md.j2", fallback)
        assert result == fallback

    def test_returns_rendered_for_existing_template(self, loader: PromptTemplateLoader) -> None:
        result = loader.render_or_fallback("system_prompt.md.j2", "fallback")
        assert result != "fallback"
        assert len(result) > 0

"""Unit tests for HtmlGenerator prompt builders and LLM call logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.context_resolver import ResolvedContext
from src.services.html_generator import (
    HtmlGenerator,
    LLMResult,
    _format_context_block,
    estimate_cost,
)

# ============================================================================
# estimate_cost
# ============================================================================


class TestEstimateCost:
    def test_zero_tokens(self) -> None:
        assert estimate_cost(0, 0) == 0.0

    def test_nonzero_tokens(self) -> None:
        cost = estimate_cost(1000, 1000)
        assert cost > 0
        # 1000/1000 * 0.003 + 1000/1000 * 0.015 = 0.003 + 0.015 = 0.018
        assert abs(cost - 0.018) < 0.001

    def test_input_heavy(self) -> None:
        cost = estimate_cost(10000, 0)
        expected = 10000 / 1000 * 0.003
        assert abs(cost - expected) < 0.001

    def test_output_heavy(self) -> None:
        cost = estimate_cost(0, 10000)
        expected = 10000 / 1000 * 0.015
        assert abs(cost - expected) < 0.001


# ============================================================================
# LLMResult dataclass
# ============================================================================


class TestLLMResult:
    def test_default_values(self) -> None:
        result = LLMResult(text="Hello")
        assert result.text == "Hello"
        assert result.input_tokens == 0
        assert result.output_tokens == 0

    def test_with_tokens(self) -> None:
        result = LLMResult(text="Hi", input_tokens=100, output_tokens=200)
        assert result.input_tokens == 100
        assert result.output_tokens == 200


# ============================================================================
# _format_context_block
# ============================================================================


class TestFormatContextBlock:
    def test_none_context(self) -> None:
        assert _format_context_block(None) == ""

    def test_with_site_type(self) -> None:
        ctx = ResolvedContext(site_type="ecommerce")
        result = _format_context_block(ctx)
        assert "ecommerce" in result

    def test_with_goals(self) -> None:
        ctx = ResolvedContext(goals=["increase_conversions", "improve_seo"])
        result = _format_context_block(ctx)
        assert "increase_conversions" in result
        assert "improve_seo" in result

    def test_with_feature_priorities(self) -> None:
        ctx = ResolvedContext(
            feature_priorities=[
                {"feature": "navigation", "priority": "high"},
                {"feature": "search", "priority": "low"},
            ]
        )
        result = _format_context_block(ctx)
        assert "navigation" in result
        assert "high" in result

    def test_with_visual_preferences_dict(self) -> None:
        ctx = ResolvedContext(
            visual_preferences={"color_scheme": "dark", "layout_style": "card-based"}
        )
        result = _format_context_block(ctx)
        assert "dark" in result
        assert "card-based" in result

    def test_with_empty_visual_preferences(self) -> None:
        ctx = ResolvedContext(visual_preferences={})
        result = _format_context_block(ctx)
        # Should not contain "Visual preferences" since all values are falsy
        assert "Visual preferences" not in result


# ============================================================================
# HtmlGenerator prompt building
# ============================================================================


class TestHtmlGeneratorPromptBuilding:
    def _make_generator(self) -> HtmlGenerator:
        gen = HtmlGenerator.__new__(HtmlGenerator)
        gen._api_key = "test-key"  # pragma: allowlist secret
        gen._base_url = "https://api.deepseek.com"
        gen._model = "deepseek-chat"
        gen._max_tokens = 4096
        gen._timeout = 60.0
        gen._template_loader = None
        gen._generation_temperature = 0.7
        gen._refinement_temperature = 0.4
        return gen

    def test_build_full_page_prompt_basic(self) -> None:
        gen = self._make_generator()
        prompt = gen._build_full_page_prompt(
            url="https://example.com",
            html="<html><body>Hello</body></html>",
            page_type="homepage",
            style="modern",
            findings=None,
            brand=None,
            site_analysis=None,
        )
        assert "https://example.com" in prompt
        assert "homepage" in prompt
        assert "modern" in prompt
        assert "Hello" in prompt

    def test_build_full_page_prompt_with_context(self) -> None:
        gen = self._make_generator()
        ctx = ResolvedContext(
            site_type="ecommerce",
            target_audience=["developers", "designers"],
            tone="casual",
            primary_color="#FF0000",
            secondary_color="#00FF00",
        )
        prompt = gen._build_full_page_prompt(
            url="https://shop.example.com",
            html="<html>Shop</html>",
            page_type="product",
            style="bold",
            findings=None,
            brand=None,
            site_analysis=None,
            context=ctx,
        )
        assert "developers" in prompt
        assert "#FF0000" in prompt
        assert "casual" in prompt

    def test_build_full_page_prompt_with_brand_and_analysis(self) -> None:
        gen = self._make_generator()
        prompt = gen._build_full_page_prompt(
            url="https://example.com",
            html="<html>Test</html>",
            page_type=None,
            style="elegant",
            findings=None,
            brand={"primary_color": "#AABBCC", "secondary_color": "#DDEEFF"},
            site_analysis={
                "target_audience": ["enterprise users"],
                "tone": "formal",
                "visual_identity": {
                    "primary_color": "#112233",
                    "secondary_color": "#445566",
                },
            },
        )
        # Brand overrides site analysis colors
        assert "#AABBCC" in prompt
        assert "enterprise users" in prompt
        assert "formal" in prompt

    def test_build_full_page_prompt_with_template_loader(self) -> None:
        gen = self._make_generator()
        mock_loader = MagicMock()
        mock_loader.render.return_value = "Custom template prompt"
        gen._template_loader = mock_loader

        prompt = gen._build_full_page_prompt(
            url="https://example.com",
            html="<html>Test</html>",
            page_type="homepage",
            style="modern",
            findings=None,
            brand=None,
            site_analysis=None,
        )
        assert prompt == "Custom template prompt"

    def test_build_full_page_prompt_with_template_loader_returns_none(self) -> None:
        gen = self._make_generator()
        mock_loader = MagicMock()
        mock_loader.render.return_value = None
        gen._template_loader = mock_loader

        prompt = gen._build_full_page_prompt(
            url="https://example.com",
            html="<html>Test</html>",
            page_type="homepage",
            style="modern",
            findings=None,
            brand=None,
            site_analysis=None,
        )
        # Falls back to inline prompt
        assert "Redesign the following" in prompt

    def test_build_section_prompt(self) -> None:
        gen = self._make_generator()
        prompt = gen._build_section_prompt(
            url="https://example.com",
            html="<html>Page</html>",
            section={"section_type": "hero", "heading": "Welcome", "text_preview": "Hello world"},
            page_type="landing",
            style="bold",
            findings=None,
            brand=None,
            site_analysis=None,
        )
        assert "hero" in prompt
        assert "Welcome" in prompt
        assert "Hello world" in prompt

    def test_build_section_prompt_with_context(self) -> None:
        gen = self._make_generator()
        ctx = ResolvedContext(
            target_audience=["students"],
            primary_color="#123456",
            secondary_color="#654321",
        )
        prompt = gen._build_section_prompt(
            url="https://example.com",
            html="<html>Page</html>",
            section={"section_type": "cta"},
            page_type=None,
            style="modern",
            findings=None,
            brand=None,
            site_analysis=None,
            context=ctx,
        )
        assert "students" in prompt
        assert "#123456" in prompt

    def test_build_section_prompt_with_brand(self) -> None:
        gen = self._make_generator()
        prompt = gen._build_section_prompt(
            url="https://example.com",
            html="<html>Page</html>",
            section={"section_type": "footer"},
            page_type=None,
            style="modern",
            findings=None,
            brand={"primary_color": "#AABB00"},
            site_analysis={"target_audience": ["designers"]},
        )
        assert "#AABB00" in prompt
        assert "designers" in prompt

    def test_build_component_prompt(self) -> None:
        gen = self._make_generator()
        prompt = gen._build_component_prompt(
            url="https://example.com",
            component_html="<nav>Menu</nav>",
            component_type="navbar",
            page_type="homepage",
            style="modern",
            findings=None,
            brand=None,
            site_analysis=None,
        )
        assert "navbar" in prompt
        assert "Menu" in prompt

    def test_build_component_prompt_with_context(self) -> None:
        gen = self._make_generator()
        ctx = ResolvedContext(primary_color="#FF0000", secondary_color="#0000FF")
        prompt = gen._build_component_prompt(
            url="https://example.com",
            component_html="<nav>Menu</nav>",
            component_type="navbar",
            page_type="homepage",
            style="modern",
            findings=None,
            brand=None,
            site_analysis=None,
            context=ctx,
        )
        assert "#FF0000" in prompt

    def test_build_component_prompt_with_brand(self) -> None:
        gen = self._make_generator()
        prompt = gen._build_component_prompt(
            url="https://example.com",
            component_html="<nav>Menu</nav>",
            component_type="navbar",
            page_type="homepage",
            style="modern",
            findings=None,
            brand={"primary_color": "#ABCDEF"},
            site_analysis=None,
        )
        assert "#ABCDEF" in prompt

    def test_build_refinement_prompt(self) -> None:
        gen = self._make_generator()
        prompt = gen._build_refinement_prompt(
            url="https://example.com",
            previous_html="<html>Previous</html>",
            feedback="Make it more colorful",
            page_type="landing",
            style="bold",
            brand=None,
            site_analysis=None,
        )
        assert "Make it more colorful" in prompt
        assert "Previous" in prompt
        assert "bold" in prompt

    def test_build_refinement_prompt_with_focus_areas(self) -> None:
        gen = self._make_generator()
        prompt = gen._build_refinement_prompt(
            url="https://example.com",
            previous_html="<html>Previous</html>",
            feedback="Improve",
            page_type=None,
            style="modern",
            brand=None,
            site_analysis=None,
            focus_areas=["layout", "typography"],
        )
        assert "layout" in prompt
        assert "typography" in prompt
        assert "Focus Areas" in prompt

    def test_build_refinement_prompt_with_template_loader(self) -> None:
        gen = self._make_generator()
        mock_loader = MagicMock()
        mock_loader.render.return_value = "Refinement template"
        gen._template_loader = mock_loader

        prompt = gen._build_refinement_prompt(
            url="https://example.com",
            previous_html="<html>Previous</html>",
            feedback="Better",
            page_type=None,
            style="modern",
            brand=None,
            site_analysis=None,
        )
        assert prompt == "Refinement template"

    def test_build_refinement_prompt_with_brand(self) -> None:
        gen = self._make_generator()
        prompt = gen._build_refinement_prompt(
            url="https://example.com",
            previous_html="<html>Previous</html>",
            feedback="Better",
            page_type=None,
            style="modern",
            brand={"primary_color": "#FF00FF"},
            site_analysis=None,
        )
        assert "#FF00FF" in prompt


# ============================================================================
# HtmlGenerator async methods
# ============================================================================


class TestHtmlGeneratorAsync:
    def _make_generator(self) -> HtmlGenerator:
        gen = HtmlGenerator.__new__(HtmlGenerator)
        gen._api_key = "test-key"  # pragma: allowlist secret
        gen._base_url = "https://api.deepseek.com"
        gen._model = "deepseek-chat"
        gen._max_tokens = 4096
        gen._timeout = 60.0
        gen._template_loader = None
        gen._generation_temperature = 0.7
        gen._refinement_temperature = 0.4
        return gen

    @pytest.mark.asyncio
    async def test_generate_full_page(self) -> None:
        gen = self._make_generator()
        mock_result = LLMResult(
            text="```html\n<html>Redesigned</html>\n```",
            input_tokens=100,
            output_tokens=200,
        )
        object.__setattr__(gen, "_call_claude", AsyncMock(return_value=mock_result))

        result = await gen.generate_full_page(
            url="https://example.com",
            html="<html>Original</html>",
            style="modern",
        )
        assert result.text == "<html>Redesigned</html>"
        assert result.input_tokens == 100

    @pytest.mark.asyncio
    async def test_generate_sections(self) -> None:
        gen = self._make_generator()
        object.__setattr__(
            gen,
            "_call_claude",
            AsyncMock(
                side_effect=[
                    LLMResult(text="```html\n<section>Hero</section>\n```"),
                    LLMResult(text="```html\n<section>CTA</section>\n```"),
                ]
            ),
        )

        result = await gen.generate_sections(
            url="https://example.com",
            html="<html>Page</html>",
            sections=[
                {"section_type": "hero", "heading": "Welcome"},
                {"section_type": "cta", "heading": "Sign Up"},
            ],
            style="modern",
        )
        assert "hero" in result
        assert "cta" in result
        assert "Hero" in result["hero"]
        assert "CTA" in result["cta"]

    @pytest.mark.asyncio
    async def test_generate_component(self) -> None:
        gen = self._make_generator()
        mock_result = LLMResult(
            text="```html\n<nav>New Nav</nav>\n```",
            input_tokens=50,
            output_tokens=100,
        )
        object.__setattr__(gen, "_call_claude", AsyncMock(return_value=mock_result))

        result = await gen.generate_component(
            url="https://example.com",
            component_html="<nav>Old Nav</nav>",
            component_type="navbar",
            style="modern",
        )
        assert result.text == "<nav>New Nav</nav>"

    @pytest.mark.asyncio
    async def test_refine_full_page(self) -> None:
        gen = self._make_generator()
        mock_result = LLMResult(
            text="```html\n<html>Refined</html>\n```",
            input_tokens=80,
            output_tokens=150,
        )
        object.__setattr__(gen, "_call_claude", AsyncMock(return_value=mock_result))

        result = await gen.refine_full_page(
            url="https://example.com",
            previous_html="<html>Previous</html>",
            feedback="Make bolder",
            style="bold",
        )
        assert result.text == "<html>Refined</html>"

    @pytest.mark.asyncio
    async def test_call_claude(self) -> None:
        gen = self._make_generator()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "LLM response"}}],
            "usage": {"prompt_tokens": 42, "completion_tokens": 99},
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        gen._http_client = mock_client

        result = await gen._call_claude("Test prompt")
        assert result.text == "LLM response"
        assert result.input_tokens == 42
        assert result.output_tokens == 99

    @pytest.mark.asyncio
    async def test_call_claude_with_template_system_prompt(self) -> None:
        gen = self._make_generator()
        mock_loader = MagicMock()
        mock_loader.render.return_value = "Custom system prompt"
        gen._template_loader = mock_loader

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Response"}}],
            "usage": {},
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        gen._http_client = mock_client

        await gen._call_claude("Test prompt", temperature=0.5)
        call_args = mock_client.post.call_args
        json_body = call_args.kwargs["json"]
        # System prompt is now sent as a message, not a top-level field
        system_msg = json_body["messages"][0]
        assert system_msg["role"] == "system"
        assert system_msg["content"] == "Custom system prompt"
        assert json_body["temperature"] == 0.5

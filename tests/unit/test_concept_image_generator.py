"""Unit tests for ConceptImageGenerator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.concept_image_generator import ConceptImageGenerator


class TestConceptImageGeneratorInit:
    def test_init(self) -> None:
        with patch("src.services.concept_image_generator.get_settings") as mock_settings:
            s = MagicMock()
            s.dalle.api_key = "test-key"  # pragma: allowlist secret
            s.dalle.model = "dall-e-3"
            s.dalle.size = "1792x1024"
            s.dalle.quality = "hd"
            mock_settings.return_value = s

            gen = ConceptImageGenerator()
            assert gen._api_key == "test-key"  # pragma: allowlist secret
            assert gen._model == "dall-e-3"


class TestIsAvailable:
    @pytest.mark.asyncio
    async def test_available_when_enabled_and_key(self) -> None:
        with patch("src.services.concept_image_generator.get_settings") as mock_settings:
            s = MagicMock()
            s.dalle.api_key = "test-key"  # pragma: allowlist secret
            s.dalle.model = "dall-e-3"
            s.dalle.size = "1792x1024"
            s.dalle.quality = "hd"
            s.dalle.enabled = True
            mock_settings.return_value = s

            gen = ConceptImageGenerator()
            assert await gen.is_available() is True

    @pytest.mark.asyncio
    async def test_not_available_when_disabled(self) -> None:
        with patch("src.services.concept_image_generator.get_settings") as mock_settings:
            s = MagicMock()
            s.dalle.api_key = "test-key"  # pragma: allowlist secret
            s.dalle.model = "dall-e-3"
            s.dalle.size = "1792x1024"
            s.dalle.quality = "hd"
            s.dalle.enabled = False
            mock_settings.return_value = s

            gen = ConceptImageGenerator()
            assert await gen.is_available() is False

    @pytest.mark.asyncio
    async def test_not_available_when_no_key(self) -> None:
        with patch("src.services.concept_image_generator.get_settings") as mock_settings:
            s = MagicMock()
            s.dalle.api_key = ""
            s.dalle.model = "dall-e-3"
            s.dalle.size = "1792x1024"
            s.dalle.quality = "hd"
            s.dalle.enabled = True
            mock_settings.return_value = s

            gen = ConceptImageGenerator()
            assert await gen.is_available() is False


class TestBuildPrompt:
    def _make_gen(self) -> ConceptImageGenerator:
        gen = ConceptImageGenerator.__new__(ConceptImageGenerator)
        gen._api_key = "test-key"  # pragma: allowlist secret
        gen._model = "dall-e-3"
        gen._size = "1792x1024"
        gen._quality = "hd"
        gen._template_loader = None
        return gen

    def test_basic_prompt(self) -> None:
        gen = self._make_gen()
        prompt = gen._build_prompt(
            site_description="An online store",
            target_audience=["shoppers", "bargain hunters"],
            brand_name="ShopNow",
            primary_color="#FF0000",
            style="modern",
        )
        assert "ShopNow" in prompt
        assert "online store" in prompt
        assert "shoppers" in prompt
        assert "#FF0000" in prompt

    def test_defaults(self) -> None:
        gen = self._make_gen()
        prompt = gen._build_prompt(
            site_description=None,
            target_audience=None,
            brand_name=None,
            primary_color="#2563EB",
            style="minimalist",
        )
        assert "professional website" in prompt
        assert "general audience" in prompt
        assert "the website" in prompt

    def test_custom_style_description(self) -> None:
        gen = self._make_gen()
        prompt = gen._build_prompt(
            site_description=None,
            target_audience=None,
            brand_name=None,
            primary_color="#2563EB",
            style="custom",
            style_description="A futuristic neon aesthetic",
        )
        assert "futuristic neon" in prompt

    def test_with_template_loader(self) -> None:
        gen = self._make_gen()
        mock_loader = MagicMock()
        mock_loader.render.return_value = "Custom concept prompt"
        gen._template_loader = mock_loader

        prompt = gen._build_prompt(
            site_description="Test",
            target_audience=None,
            brand_name="Test",
            primary_color="#000",
            style="modern",
        )
        assert prompt == "Custom concept prompt"

    def test_with_template_loader_returns_none(self) -> None:
        gen = self._make_gen()
        mock_loader = MagicMock()
        mock_loader.render.return_value = None
        gen._template_loader = mock_loader

        prompt = gen._build_prompt(
            site_description=None,
            target_audience=None,
            brand_name=None,
            primary_color="#000",
            style="modern",
        )
        assert "professional website" in prompt


class TestGenerate:
    @pytest.mark.asyncio
    async def test_generate_success(self, tmp_path) -> None:
        gen = ConceptImageGenerator.__new__(ConceptImageGenerator)
        gen._api_key = "test-key"  # pragma: allowlist secret
        gen._model = "dall-e-3"
        gen._size = "1792x1024"
        gen._quality = "hd"
        gen._template_loader = None

        gen._call_dalle = AsyncMock(return_value="https://images.example.com/1.png")

        mock_response = MagicMock()
        mock_response.content = b"\x89PNG\r\n"
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        gen._http_client = mock_http_client

        paths = await gen.generate(
            site_description="Test",
            output_dir=tmp_path / "concepts",
            count=1,
        )
        assert len(paths) == 1
        assert "concept_01.png" in paths[0]

    @pytest.mark.asyncio
    async def test_generate_dalle_returns_none(self, tmp_path) -> None:
        gen = ConceptImageGenerator.__new__(ConceptImageGenerator)
        gen._api_key = "test-key"  # pragma: allowlist secret
        gen._model = "dall-e-3"
        gen._size = "1792x1024"
        gen._quality = "hd"
        gen._template_loader = None
        gen._http_client = AsyncMock()

        gen._call_dalle = AsyncMock(return_value=None)

        paths = await gen.generate(
            site_description="Test",
            output_dir=tmp_path / "concepts",
            count=1,
        )
        assert len(paths) == 0

    @pytest.mark.asyncio
    async def test_generate_handles_exception(self, tmp_path) -> None:
        gen = ConceptImageGenerator.__new__(ConceptImageGenerator)
        gen._api_key = "test-key"  # pragma: allowlist secret
        gen._model = "dall-e-3"
        gen._size = "1792x1024"
        gen._quality = "hd"
        gen._template_loader = None
        gen._http_client = AsyncMock()

        gen._call_dalle = AsyncMock(side_effect=Exception("API error"))

        paths = await gen.generate(
            site_description="Test",
            output_dir=tmp_path / "concepts",
            count=2,
        )
        assert len(paths) == 0

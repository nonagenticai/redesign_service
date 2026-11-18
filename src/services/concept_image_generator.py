"""Optional AI concept image generation for redesign mood boards."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from src.config import get_settings
from src.services.prompt_template import PromptTemplateLoader

logger = logging.getLogger(__name__)


class ConceptImageGenerator:
    """Generate concept images showing the redesign direction via DALL-E."""

    def __init__(self, template_loader: PromptTemplateLoader | None = None) -> None:
        settings = get_settings()
        self._api_key = settings.dalle.api_key
        self._model = settings.dalle.model
        self._size = settings.dalle.size
        self._quality = settings.dalle.quality
        self._template_loader = template_loader
        self._http_client = httpx.AsyncClient(timeout=120.0)

    async def is_available(self) -> bool:
        """Check if DALL-E concept generation is available."""
        settings = get_settings()
        return settings.dalle.enabled and bool(self._api_key)

    async def generate(
        self,
        *,
        site_description: str | None = None,
        target_audience: list[str] | None = None,
        brand_name: str | None = None,
        primary_color: str = "#2563EB",
        style: str = "modern",
        style_description: str | None = None,
        count: int = 2,
        output_dir: Path,
    ) -> list[str]:
        """Generate concept images and save them to output_dir.

        Returns a list of paths to the generated images.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        prompt = self._build_prompt(
            site_description=site_description,
            target_audience=target_audience,
            brand_name=brand_name,
            primary_color=primary_color,
            style=style,
            style_description=style_description,
        )
        paths: list[str] = []

        for i in range(count):
            try:
                image_url = await self._call_dalle(prompt)
                if not image_url:
                    logger.warning("DALL-E returned no URL for concept image %d", i + 1)
                    continue

                img_response = await self._http_client.get(image_url, timeout=60.0)
                img_response.raise_for_status()

                image_path = output_dir / f"concept_{i + 1:02d}.png"
                image_path.write_bytes(img_response.content)
                paths.append(str(image_path))
                logger.info("Concept image %d/%d saved: %s", i + 1, count, image_path)

            except Exception as exc:
                logger.warning("Failed to generate concept image %d: %s", i + 1, exc)

        return paths

    async def _call_dalle(self, prompt: str) -> str | None:
        """Call OpenAI DALL-E API."""
        response = await self._http_client.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model,
                "prompt": prompt,
                "size": self._size,
                "quality": self._quality,
                "n": 1,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data.get("data", [{}])[0].get("url")

    def _build_prompt(
        self,
        *,
        site_description: str | None,
        target_audience: list[str] | None,
        brand_name: str | None,
        primary_color: str,
        style: str,
        style_description: str | None = None,
    ) -> str:
        """Build a DALL-E prompt for concept image generation."""
        description = site_description or "a professional website"
        audience = ", ".join(target_audience[:3]) if target_audience else "general audience"
        name = brand_name or "the website"

        style_descriptions = {
            "modern": "clean, modern design with generous whitespace, subtle gradients, and crisp typography",
            "minimalist": "minimalist aesthetic with ample negative space, monochromatic palette, and elegant simplicity",
            "bold": "bold and vibrant design with strong colors, dynamic layouts, and impactful visual hierarchy",
            "elegant": "sophisticated and elegant design with refined typography, muted tones, and premium feel",
        }
        style_desc = style_description or style_descriptions.get(
            style, style_descriptions["modern"]
        )

        # Try Jinja2 template
        if self._template_loader and hasattr(self._template_loader, "render"):
            rendered = self._template_loader.render(
                "concept_image.md.j2",
                brand_name=name,
                description=description,
                audience=audience,
                style_desc=style_desc,
                primary_color=primary_color,
            )
            if rendered:
                return rendered

        return (
            f"A professional website redesign concept for {name}, "
            f"which is {description}. The target audience is {audience}. "
            f"Design direction: {style_desc}. "
            f"Primary brand color: {primary_color}. "
            f"Show a high-fidelity mockup of a modern, conversion-optimized web page "
            f"displayed on a laptop screen in an isometric view. "
            f"The design should look realistic and professional, suitable for a "
            f"client presentation. No text overlays or labels."
        )

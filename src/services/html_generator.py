"""Claude-powered HTML+Tailwind redesign generator."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx

from src.config import get_settings
from src.services.component_extractor import COMPONENT_DESIGN_TIPS
from src.services.context_resolver import GOAL_DESIGN_ACTIONS, ResolvedContext
from src.services.prompt_template import PromptTemplateLoader

logger = logging.getLogger(__name__)

REDESIGN_SYSTEM_PROMPT = (
    "You are a senior UX/UI designer and front-end developer specializing "
    "in conversion optimization and modern web design. You produce clean, "
    "self-contained HTML files using Tailwind CSS via CDN. You preserve "
    "the site's actual content and never invent placeholder text."
)

STYLE_DESCRIPTIONS: dict[str, str] = {
    "modern": (
        "Clean, modern design with generous whitespace, subtle gradients, "
        "card-based layouts, and crisp sans-serif typography. Use smooth "
        "transitions and a professional color palette."
    ),
    "minimalist": (
        "Minimalist aesthetic with ample negative space, monochromatic palette "
        "with one accent color, elegant simplicity, and refined typography. "
        "Every element should earn its place."
    ),
    "bold": (
        "Bold and vibrant design with strong colors, dynamic asymmetric layouts, "
        "large hero sections, and impactful visual hierarchy. Use strong contrast "
        "and confident typography."
    ),
    "elegant": (
        "Sophisticated and elegant design with refined serif/sans-serif pairings, "
        "muted tones, premium feel, subtle animations, and luxurious spacing. "
        "Think high-end brand presentation."
    ),
}


@dataclass
class LLMResult:
    """Result from an LLM call with token usage tracking."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0


def estimate_cost(input_tokens: int, output_tokens: int, model: str = "") -> float:
    """Estimate cost in USD based on token usage."""
    # Approximate pricing for Claude Sonnet
    input_cost_per_1k = 0.003
    output_cost_per_1k = 0.015
    return (input_tokens / 1000 * input_cost_per_1k) + (output_tokens / 1000 * output_cost_per_1k)


def _truncate_html(html: str, max_chars: int = 15000) -> str:
    """Truncate HTML to a reasonable size for the LLM prompt."""
    if len(html) <= max_chars:
        return html
    return html[:max_chars] + "\n<!-- ... truncated ... -->"


def _format_findings(findings: list[dict] | None) -> str:
    """Format critique findings into a concise summary for the prompt."""
    if not findings:
        return "No specific critique findings available."
    lines = []
    for f in findings[:15]:
        severity = f.get("severity", "medium")
        title = f.get("title", "")
        desc = f.get("description", "")
        lines.append(f"- [{severity}] {title}: {desc}")
        rec = f.get("recommendation")
        if rec:
            lines.append(f"  Recommendation: {rec}")
    return "\n".join(lines)


def _extract_html_block(response: str) -> str:
    """Extract HTML code block from LLM response."""
    pattern = r"```html\s*\n(.*?)```"
    match = re.search(pattern, response, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Try generic code block
    pattern = r"```\s*\n(.*?)```"
    match = re.search(pattern, response, re.DOTALL)
    if match:
        return match.group(1).strip()
    return response


def _format_context_block(context: ResolvedContext | None) -> str:
    """Format resolved context into a prompt section."""
    if context is None:
        return ""
    parts: list[str] = []
    if context.site_type:
        parts.append(f"- Site type: {context.site_type}")
    if context.goals:
        parts.append("- Goals:")
        for goal in context.goals:
            action = GOAL_DESIGN_ACTIONS.get(goal, goal)
            parts.append(f"  - {goal}: {action}")
    if context.feature_priorities:
        parts.append("- Feature priorities:")
        for fp in context.feature_priorities:
            parts.append(f"  - {fp.get('feature', '?')}: {fp.get('priority', 'medium')}")
    if context.visual_preferences:
        vp = context.visual_preferences
        if isinstance(vp, dict):
            prefs = [f"{k}={v}" for k, v in vp.items() if v]
            if prefs:
                parts.append(f"- Visual preferences: {', '.join(prefs)}")
    return "\n".join(parts)


class HtmlGenerator:
    """Generate redesigned HTML+Tailwind pages using an OpenAI-compatible LLM API."""

    def __init__(self, template_loader: PromptTemplateLoader | None = None) -> None:
        settings = get_settings()
        self._api_key = settings.llm.api_key
        self._base_url = settings.llm.base_url
        self._model = settings.llm.model
        self._max_tokens = settings.llm.max_tokens
        self._timeout = settings.llm.timeout
        self._template_loader = template_loader
        self._generation_temperature = 0.7
        self._refinement_temperature = 0.4
        self._http_client = httpx.AsyncClient(timeout=self._timeout)

    async def generate_full_page(
        self,
        *,
        url: str,
        html: str,
        page_type: str | None = None,
        style: str = "modern",
        findings: list[dict] | None = None,
        brand: dict | None = None,
        site_analysis: dict | None = None,
        style_description: str | None = None,
        context: ResolvedContext | None = None,
    ) -> LLMResult:
        """Generate a complete redesigned HTML page via Claude API.

        Returns LLMResult with extracted HTML text and token usage.
        """
        prompt = self._build_full_page_prompt(
            url=url,
            html=html,
            page_type=page_type,
            style=style,
            findings=findings,
            brand=brand,
            site_analysis=site_analysis,
            style_description=style_description,
            context=context,
        )
        result = await self._call_claude(prompt, temperature=self._generation_temperature)
        result.text = _extract_html_block(result.text)
        return result

    async def generate_sections(
        self,
        *,
        url: str,
        html: str,
        sections: list[dict],
        page_type: str | None = None,
        style: str = "modern",
        findings: list[dict] | None = None,
        brand: dict | None = None,
        site_analysis: dict | None = None,
        style_description: str | None = None,
        context: ResolvedContext | None = None,
    ) -> dict[str, str]:
        """Generate redesigned HTML for key sections of a page."""
        results: dict[str, str] = {}
        for section in sections:
            section_type = section.get("section_type", "unknown")
            prompt = self._build_section_prompt(
                url=url,
                html=html,
                section=section,
                page_type=page_type,
                style=style,
                findings=findings,
                brand=brand,
                site_analysis=site_analysis,
                style_description=style_description,
                context=context,
            )
            result = await self._call_claude(prompt, temperature=self._generation_temperature)
            results[section_type] = _extract_html_block(result.text)
        return results

    async def generate_component(
        self,
        *,
        url: str,
        component_html: str,
        component_type: str,
        page_type: str | None = None,
        style: str = "modern",
        findings: list[dict] | None = None,
        brand: dict | None = None,
        site_analysis: dict | None = None,
        style_description: str | None = None,
        context: ResolvedContext | None = None,
    ) -> LLMResult:
        """Generate a redesigned component. Returns LLMResult."""
        prompt = self._build_component_prompt(
            url=url,
            component_html=component_html,
            component_type=component_type,
            page_type=page_type,
            style=style,
            findings=findings,
            brand=brand,
            site_analysis=site_analysis,
            style_description=style_description,
            context=context,
        )
        result = await self._call_claude(prompt, temperature=self._generation_temperature)
        result.text = _extract_html_block(result.text)
        return result

    async def refine_full_page(
        self,
        *,
        url: str,
        previous_html: str,
        feedback: str,
        page_type: str | None = None,
        style: str = "modern",
        brand: dict | None = None,
        site_analysis: dict | None = None,
        style_description: str | None = None,
        focus_areas: list[str] | None = None,
    ) -> LLMResult:
        """Refine a previous redesign based on feedback. Returns LLMResult."""
        prompt = self._build_refinement_prompt(
            url=url,
            previous_html=previous_html,
            feedback=feedback,
            page_type=page_type,
            style=style,
            brand=brand,
            site_analysis=site_analysis,
            style_description=style_description,
            focus_areas=focus_areas,
        )
        result = await self._call_claude(prompt, temperature=self._refinement_temperature)
        result.text = _extract_html_block(result.text)
        return result

    def compose_section_page(
        self,
        sections: dict[str, str],
        title: str = "Redesign Concept",
        style: str = "modern",
    ) -> str:
        """Compose individual section HTML snippets into a full page."""
        style_desc = STYLE_DESCRIPTIONS.get(style, STYLE_DESCRIPTIONS["modern"])
        section_html = "\n\n".join(
            f"<!-- Section: {name} -->\n{html}" for name, html in sections.items()
        )
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} — Redesign Concept</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        /* {style_desc} */
        body {{ font-family: system-ui, -apple-system, sans-serif; }}
    </style>
</head>
<body class="bg-white text-gray-900">
{section_html}
</body>
</html>"""

    async def _call_claude(self, prompt: str, temperature: float | None = None) -> LLMResult:
        """Call LLM via OpenAI-compatible API. Returns LLMResult with token usage."""
        system_prompt = REDESIGN_SYSTEM_PROMPT
        if self._template_loader:
            rendered = self._template_loader.render("system_prompt.md.j2")
            if rendered:
                system_prompt = rendered

        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        request_json: dict = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": messages,
        }
        if temperature is not None:
            request_json["temperature"] = temperature

        response = await self._http_client.post(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=request_json,
        )
        response.raise_for_status()
        data = response.json()

        usage = data.get("usage", {})
        return LLMResult(
            text=data["choices"][0]["message"]["content"],
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )

    def _build_full_page_prompt(
        self,
        *,
        url: str,
        html: str,
        page_type: str | None,
        style: str,
        findings: list[dict] | None,
        brand: dict | None,
        site_analysis: dict | None,
        style_description: str | None = None,
        context: ResolvedContext | None = None,
    ) -> str:
        """Build the full-page redesign prompt."""
        settings = get_settings()
        style_desc = style_description or STYLE_DESCRIPTIONS.get(
            style, STYLE_DESCRIPTIONS["modern"]
        )
        findings_text = _format_findings(findings)
        html_excerpt = _truncate_html(html, settings.redesign.max_html_chars)

        audience = "general"
        tone = "professional"
        primary_color = "#2563EB"
        secondary_color = "#1E40AF"

        if context:
            audience = (
                ", ".join(context.target_audience[:5]) if context.target_audience else "general"
            )
            tone = context.tone
            primary_color = context.primary_color
            secondary_color = context.secondary_color
        else:
            if site_analysis:
                audience = ", ".join(site_analysis.get("target_audience", [])[:5]) or "general"
                tone = site_analysis.get("tone", "professional") or "professional"
                vis = site_analysis.get("visual_identity") or {}
                primary_color = vis.get("primary_color", primary_color)
                secondary_color = vis.get("secondary_color", secondary_color)
            if brand:
                primary_color = brand.get("primary_color", primary_color)
                secondary_color = brand.get("secondary_color", secondary_color)

        context_block = _format_context_block(context)

        # Try Jinja2 template first
        if self._template_loader:
            rendered = self._template_loader.render(
                "full_page.md.j2",
                url=url,
                page_type=page_type,
                html_excerpt=html_excerpt,
                audience=audience,
                primary_color=primary_color,
                secondary_color=secondary_color,
                tone=tone,
                context_block=context_block,
                findings_text=findings_text,
                style=style,
                style_desc=style_desc,
            )
            if rendered:
                return rendered

        # Inline fallback
        prompt = f"""Redesign the following web page to be more compelling, modern, and conversion-optimized.
Output a single self-contained HTML file using Tailwind CSS (via CDN).

## Original Page
- URL: {url}
- Page type: {page_type or "unknown"}
- Current HTML:
{html_excerpt}

## Site Context
- Audience: {audience}
- Brand colors: primary={primary_color}, secondary={secondary_color}
- Tone: {tone}
"""
        if context_block:
            prompt += f"""
## User Context
{context_block}
"""
        prompt += f"""
## Issues to Address
{findings_text}

## Design Direction: {style}
{style_desc}

## Requirements
1. Self-contained HTML with Tailwind CDN link
2. Preserve the site's actual content (don't invent text)
3. Use the brand's color palette
4. Improve: visual hierarchy, CTA placement, whitespace, typography, responsiveness
5. Address the critique findings above
6. Include <meta name="viewport"> for responsiveness

Output ONLY the HTML code in a ```html code block."""
        return prompt

    def _build_section_prompt(
        self,
        *,
        url: str,
        html: str,
        section: dict,
        page_type: str | None,
        style: str,
        findings: list[dict] | None,
        brand: dict | None,
        site_analysis: dict | None,
        style_description: str | None = None,
        context: ResolvedContext | None = None,
    ) -> str:
        """Build a section-level redesign prompt."""
        style_desc = style_description or STYLE_DESCRIPTIONS.get(
            style, STYLE_DESCRIPTIONS["modern"]
        )
        findings_text = _format_findings(findings)
        section_type = section.get("section_type", "unknown")
        heading = section.get("heading", "")
        text_preview = section.get("text_preview", "")

        audience = "general"
        primary_color = "#2563EB"
        secondary_color = "#1E40AF"

        if context:
            audience = (
                ", ".join(context.target_audience[:5]) if context.target_audience else "general"
            )
            primary_color = context.primary_color
            secondary_color = context.secondary_color
        else:
            if site_analysis:
                audience = ", ".join(site_analysis.get("target_audience", [])[:5]) or "general"
            if brand:
                primary_color = brand.get("primary_color", primary_color)
                secondary_color = brand.get("secondary_color", secondary_color)

        if self._template_loader:
            rendered = self._template_loader.render(
                "section.md.j2",
                url=url,
                page_type=page_type,
                section_type=section_type,
                heading=heading,
                text_preview=text_preview,
                audience=audience,
                primary_color=primary_color,
                secondary_color=secondary_color,
                findings_text=findings_text,
                style=style,
                style_desc=style_desc,
            )
            if rendered:
                return rendered

        return f"""Redesign the "{section_type}" section of this web page.
Output a self-contained HTML snippet using Tailwind CSS classes.

## Context
- Page: {url} ({page_type or "unknown"})
- Section: {section_type}
- Current heading: {heading}
- Current content preview: {text_preview}
- Audience: {audience}
- Brand colors: primary={primary_color}, secondary={secondary_color}
- Issues: {findings_text}

## Design Direction: {style}
{style_desc}

## Requirements
1. Output a single HTML section element with Tailwind classes
2. Preserve the actual content (don't invent text)
3. Make it visually compelling and conversion-optimized
4. Use the brand colors

Output ONLY the HTML in a ```html code block."""

    def _build_component_prompt(
        self,
        *,
        url: str,
        component_html: str,
        component_type: str,
        page_type: str | None,
        style: str,
        findings: list[dict] | None,
        brand: dict | None,
        site_analysis: dict | None,
        style_description: str | None = None,
        context: ResolvedContext | None = None,
    ) -> str:
        """Build a component-level redesign prompt."""
        style_desc = style_description or STYLE_DESCRIPTIONS.get(
            style, STYLE_DESCRIPTIONS["modern"]
        )
        findings_text = _format_findings(findings)

        primary_color = "#2563EB"
        secondary_color = "#1E40AF"

        if context:
            primary_color = context.primary_color
            secondary_color = context.secondary_color
        elif brand:
            primary_color = brand.get("primary_color", primary_color)
            secondary_color = brand.get("secondary_color", secondary_color)

        design_tips = COMPONENT_DESIGN_TIPS.get(component_type, "")
        tips_section = f"\n## Component-Specific Tips\n{design_tips}\n" if design_tips else ""

        return f"""Redesign the "{component_type}" component of this web page.
Output a self-contained HTML snippet using Tailwind CSS classes.
The redesigned component will replace the original in the page.

## Component to Redesign
Type: {component_type}
Current HTML:
```html
{_truncate_html(component_html, 5000)}
```

## Page Context
- Page: {url} ({page_type or "unknown"})
- Brand colors: primary={primary_color}, secondary={secondary_color}
- Issues: {findings_text}
{tips_section}
## Design Direction: {style}
{style_desc}

## Requirements
1. Output the redesigned component HTML with Tailwind classes
2. Preserve all content and links
3. Make it visually compelling and conversion-optimized
4. Use the brand colors
5. Ensure the component works standalone and when embedded in a page

Output ONLY the HTML in a ```html code block."""

    def _build_refinement_prompt(
        self,
        *,
        url: str,
        previous_html: str,
        feedback: str,
        page_type: str | None,
        style: str,
        brand: dict | None,
        site_analysis: dict | None,
        style_description: str | None = None,
        focus_areas: list[str] | None = None,
    ) -> str:
        """Build a refinement prompt with previous HTML and feedback."""
        settings = get_settings()
        style_desc = style_description or STYLE_DESCRIPTIONS.get(
            style, STYLE_DESCRIPTIONS["modern"]
        )
        html_excerpt = _truncate_html(previous_html, settings.redesign.max_html_chars)

        primary_color = "#2563EB"
        if brand:
            primary_color = brand.get("primary_color", primary_color)

        # Try Jinja2 template
        if self._template_loader:
            rendered = self._template_loader.render(
                "refinement.md.j2",
                url=url,
                page_type=page_type,
                style=style,
                style_desc=style_desc,
                primary_color=primary_color,
                html_excerpt=html_excerpt,
                feedback=feedback,
                focus_areas=focus_areas,
            )
            if rendered:
                return rendered

        focus_section = ""
        if focus_areas:
            focus_section = (
                "\n## Focus Areas (prioritize these)\n"
                + "\n".join(f"- {area}" for area in focus_areas)
                + "\n"
            )

        return f"""Refine the following redesigned web page based on user feedback.
Output an updated self-contained HTML file using Tailwind CSS (via CDN).

## Previous Redesign
- URL: {url}
- Page type: {page_type or "unknown"}
- Style: {style} - {style_desc}
- Primary color: {primary_color}
- HTML:
{html_excerpt}

## User Feedback
{feedback}
{focus_section}
## Requirements
1. Apply the feedback changes to the existing redesign
2. Keep the overall design direction ({style}) intact
3. Self-contained HTML with Tailwind CDN link
4. Preserve the site's actual content
5. Only change what the feedback asks for

Output ONLY the HTML code in a ```html code block."""

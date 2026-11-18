"""Extract and reinject individual page components for targeted redesign."""

from __future__ import annotations

import logging

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


class ComponentNotFoundError(Exception):
    """Raised when a target component cannot be found in the HTML."""


# CSS selectors for common component types (heuristic detection)
COMPONENT_SELECTORS: dict[str, list[str]] = {
    "navbar": [
        "nav",
        "header nav",
        "[role='navigation']",
        ".navbar",
        ".nav",
        "#navbar",
        "#nav",
        "header",
    ],
    "hero": [
        ".hero",
        "#hero",
        "[class*='hero']",
        "section:first-of-type",
        "main > section:first-child",
    ],
    "footer": [
        "footer",
        "[role='contentinfo']",
        ".footer",
        "#footer",
    ],
    "cta": [
        ".cta",
        "#cta",
        "[class*='cta']",
        "[class*='call-to-action']",
    ],
    "pricing": [
        ".pricing",
        "#pricing",
        "[class*='pricing']",
        "[class*='plans']",
    ],
    "testimonials": [
        ".testimonials",
        "#testimonials",
        "[class*='testimonial']",
        "[class*='reviews']",
    ],
    "features": [
        ".features",
        "#features",
        "[class*='features']",
        "[class*='benefits']",
    ],
    "contact": [
        ".contact",
        "#contact",
        "[class*='contact']",
        "form",
    ],
    "sidebar": [
        "aside",
        ".sidebar",
        "#sidebar",
        "[role='complementary']",
    ],
}

# Per-component design tips injected into LLM prompts
COMPONENT_DESIGN_TIPS: dict[str, str] = {
    "navbar": (
        "Make the navigation sticky, mobile-responsive with a hamburger menu, "
        "clear visual hierarchy between primary and secondary links, and prominent CTA button."
    ),
    "hero": (
        "Create a visually striking hero with a clear headline, supporting subtext, "
        "prominent CTA button, and compelling imagery or gradient background."
    ),
    "footer": (
        "Organize footer into clear columns with sitemap links, contact info, "
        "social media icons, and legal links. Keep it clean and well-structured."
    ),
    "cta": (
        "Design a compelling call-to-action section with contrasting background, "
        "persuasive headline, brief supporting text, and a large action button."
    ),
    "pricing": (
        "Use a card-based layout with clear tier differentiation, highlighted recommended plan, "
        "feature comparison, and prominent sign-up buttons."
    ),
    "testimonials": (
        "Display testimonials in cards with photos, names, roles, star ratings if applicable, "
        "and quotation marks. Use a carousel or grid layout."
    ),
    "features": (
        "Present features in a grid with icons, concise titles, and brief descriptions. "
        "Use visual hierarchy to highlight key differentiators."
    ),
    "contact": (
        "Create a clean contact form with clear labels, validation hints, "
        "a map or address section, and multiple contact methods."
    ),
    "sidebar": (
        "Keep sidebar content organized with clear sections, related links, "
        "and supplementary information that doesn't distract from main content."
    ),
}


class ComponentExtractor:
    """Extract and reinject individual components from/into HTML pages."""

    def extract(
        self,
        html: str,
        component_type: str,
        component_selector: str | None = None,
    ) -> tuple[str, str]:
        """Extract a component from the page HTML.

        Args:
            html: Full page HTML.
            component_type: Type of component (navbar, hero, footer, etc.).
            component_selector: Optional CSS selector override.

        Returns:
            Tuple of (component_html, component_id) where component_id is
            a marker used for reinjection.

        Raises:
            ComponentNotFoundError: If the component cannot be found.
        """
        soup = BeautifulSoup(html, "html.parser")

        element: Tag | None = None

        # Try explicit selector first
        if component_selector:
            element = soup.select_one(component_selector)

        # Fall back to heuristic selectors
        if element is None:
            selectors = COMPONENT_SELECTORS.get(component_type, [])
            for selector in selectors:
                try:
                    element = soup.select_one(selector)
                    if element is not None:
                        break
                except Exception:
                    continue

        if element is None:
            raise ComponentNotFoundError(
                f"Could not find component '{component_type}' "
                f"(selector={component_selector}) in the HTML."
            )

        # Mark the element for reinjection
        component_id = f"__redesign_component_{component_type}__"
        component_html = str(element)

        return component_html, component_id

    def reinject(
        self,
        original_html: str,
        component_type: str,
        new_component_html: str,
        component_selector: str | None = None,
    ) -> str:
        """Replace a component in the original HTML with the redesigned version.

        Args:
            original_html: Full page HTML.
            component_type: Type of component being replaced.
            new_component_html: Redesigned component HTML.
            component_selector: Optional CSS selector for finding the component.

        Returns:
            Full page HTML with the component replaced.

        Raises:
            ComponentNotFoundError: If the component cannot be found for replacement.
        """
        soup = BeautifulSoup(original_html, "html.parser")

        element: Tag | None = None

        if component_selector:
            element = soup.select_one(component_selector)

        if element is None:
            selectors = COMPONENT_SELECTORS.get(component_type, [])
            for selector in selectors:
                try:
                    element = soup.select_one(selector)
                    if element is not None:
                        break
                except Exception:
                    continue

        if element is None:
            raise ComponentNotFoundError(
                f"Could not find component '{component_type}' for reinjection."
            )

        # Parse the new component and replace
        new_soup = BeautifulSoup(new_component_html, "html.parser")
        new_element = new_soup.find()
        if new_element is None:
            # Wrap in a div if it's not a single element
            new_element = BeautifulSoup(f"<div>{new_component_html}</div>", "html.parser").find()

        if new_element is not None:
            element.replace_with(new_element)

        return str(soup)

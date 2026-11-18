"""Unit tests for ComponentExtractor."""

import pytest

from src.services.component_extractor import (
    COMPONENT_DESIGN_TIPS,
    COMPONENT_SELECTORS,
    ComponentExtractor,
    ComponentNotFoundError,
)


class TestComponentExtractor:
    @pytest.fixture()
    def extractor(self) -> ComponentExtractor:
        return ComponentExtractor()

    @pytest.fixture()
    def sample_html(self) -> str:
        return """<!DOCTYPE html>
<html>
<body>
<nav class="navbar">
  <a href="/">Home</a>
  <a href="/about">About</a>
</nav>
<section class="hero">
  <h1>Welcome to Our Site</h1>
  <p>We build great things.</p>
</section>
<footer>
  <p>Copyright 2024</p>
</footer>
</body>
</html>"""

    def test_extract_navbar(self, extractor: ComponentExtractor, sample_html: str) -> None:
        component_html, component_id = extractor.extract(sample_html, "navbar")
        assert "navbar" in component_html
        assert "Home" in component_html
        assert "__redesign_component_navbar__" in component_id

    def test_extract_hero(self, extractor: ComponentExtractor, sample_html: str) -> None:
        component_html, _ = extractor.extract(sample_html, "hero")
        assert "Welcome" in component_html

    def test_extract_footer(self, extractor: ComponentExtractor, sample_html: str) -> None:
        component_html, _ = extractor.extract(sample_html, "footer")
        assert "Copyright" in component_html

    def test_extract_with_custom_selector(
        self, extractor: ComponentExtractor, sample_html: str
    ) -> None:
        component_html, _ = extractor.extract(sample_html, "custom", ".hero")
        assert "Welcome" in component_html

    def test_extract_not_found_raises(self, extractor: ComponentExtractor) -> None:
        html = "<html><body><p>No components here</p></body></html>"
        with pytest.raises(ComponentNotFoundError):
            extractor.extract(html, "pricing")

    def test_reinject_component(self, extractor: ComponentExtractor, sample_html: str) -> None:
        new_nav = '<nav class="redesigned"><a href="/">New Home</a></nav>'
        result = extractor.reinject(sample_html, "navbar", new_nav)
        assert "redesigned" in result
        assert "New Home" in result
        # Original content should be gone
        assert 'class="navbar"' not in result

    def test_reinject_preserves_other_content(
        self, extractor: ComponentExtractor, sample_html: str
    ) -> None:
        new_footer = "<footer><p>New Footer 2025</p></footer>"
        result = extractor.reinject(sample_html, "footer", new_footer)
        assert "New Footer 2025" in result
        # Hero should be untouched
        assert "Welcome to Our Site" in result

    def test_reinject_not_found_raises(self, extractor: ComponentExtractor) -> None:
        html = "<html><body><p>No components</p></body></html>"
        with pytest.raises(ComponentNotFoundError):
            extractor.reinject(html, "pricing", "<div>New</div>")


class TestComponentSelectors:
    def test_all_types_have_selectors(self) -> None:
        expected = [
            "navbar",
            "hero",
            "footer",
            "cta",
            "pricing",
            "testimonials",
            "features",
            "contact",
            "sidebar",
        ]
        for comp in expected:
            assert comp in COMPONENT_SELECTORS, f"Missing selectors for {comp}"

    def test_all_types_have_design_tips(self) -> None:
        for comp in COMPONENT_SELECTORS:
            assert comp in COMPONENT_DESIGN_TIPS, f"Missing design tips for {comp}"

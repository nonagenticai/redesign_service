"""Unit tests for redesign_service."""

import pytest

from src.services.html_generator import (
    STYLE_DESCRIPTIONS,
    HtmlGenerator,
    _extract_html_block,
    _format_findings,
    _truncate_html,
)
from src.services.page_selector import (
    _PAGE_TYPE_PRIORITY,
    _SEVERITY_BOOST,
    select_pages,
)
from src.services.screenshot_renderer import VIEWPORT_SIZES
from src.services.storage_service import StorageService

# ============================================================================
# Page Selector Tests
# ============================================================================


class TestPageSelector:
    def test_empty_pages(self) -> None:
        result = select_pages([], None)
        assert result == []

    def test_single_page(self) -> None:
        pages = [{"url": "https://example.com/", "page_type": "homepage"}]
        result = select_pages(pages)
        assert len(result) == 1
        assert result[0]["url"] == "https://example.com/"

    def test_priority_ordering(self) -> None:
        pages = [
            {"url": "https://example.com/blog", "page_type": "blog_post"},
            {"url": "https://example.com/", "page_type": "homepage"},
            {"url": "https://example.com/pricing", "page_type": "pricing"},
        ]
        result = select_pages(pages)
        assert result[0]["page_type"] == "homepage"
        assert result[1]["page_type"] == "pricing"
        assert result[2]["page_type"] == "blog_post"

    def test_max_pages_limit(self) -> None:
        pages = [{"url": f"https://example.com/{i}", "page_type": "landing"} for i in range(10)]
        result = select_pages(pages, max_pages=3)
        assert len(result) == 3

    def test_critique_findings_boost(self) -> None:
        pages = [
            {"url": "https://example.com/about", "page_type": "about"},
            {"url": "https://example.com/blog", "page_type": "blog_post"},
        ]
        findings = [
            {"url": "https://example.com/blog", "severity": "critical", "title": "Issue"},
            {"url": "https://example.com/blog", "severity": "high", "title": "Issue2"},
        ]
        result = select_pages(pages, critique_findings=findings)
        # blog_post(20) + critical(40) + high(25) = 85 > about(60)
        assert result[0]["page_type"] == "blog_post"
        assert result[1]["page_type"] == "about"

    def test_unknown_page_type_gets_lowest_priority(self) -> None:
        pages = [
            {"url": "https://example.com/a", "page_type": "unknown"},
            {"url": "https://example.com/b", "page_type": "login"},
        ]
        result = select_pages(pages)
        assert result[0]["page_type"] == "login"
        assert result[1]["page_type"] == "unknown"

    def test_findings_without_url_ignored(self) -> None:
        pages = [{"url": "https://example.com/", "page_type": "homepage"}]
        findings = [{"severity": "critical", "title": "No URL finding"}]
        result = select_pages(pages, critique_findings=findings)
        assert len(result) == 1

    def test_all_page_types_have_priority(self) -> None:
        expected_types = [
            "homepage",
            "landing",
            "product",
            "pricing",
            "about",
            "product_listing",
            "contact",
            "blog_index",
            "form",
            "faq",
            "gallery",
            "blog_post",
            "dashboard",
            "documentation",
            "login",
            "unknown",
        ]
        for pt in expected_types:
            assert pt in _PAGE_TYPE_PRIORITY, f"Missing page type: {pt}"

    def test_all_severities_have_boost(self) -> None:
        for sev in ["critical", "high", "medium", "low", "info"]:
            assert sev in _SEVERITY_BOOST, f"Missing severity: {sev}"


# ============================================================================
# HTML Generator Tests
# ============================================================================


class TestHtmlGeneratorHelpers:
    def test_truncate_html_short(self) -> None:
        html = "<html>Hello</html>"
        assert _truncate_html(html) == html

    def test_truncate_html_long(self) -> None:
        html = "x" * 20000
        result = _truncate_html(html, max_chars=100)
        assert len(result) < 20000
        assert "truncated" in result

    def test_format_findings_none(self) -> None:
        result = _format_findings(None)
        assert "No specific" in result

    def test_format_findings_empty(self) -> None:
        result = _format_findings([])
        assert "No specific" in result

    def test_format_findings_with_data(self) -> None:
        findings = [
            {"severity": "high", "title": "Missing Alt", "description": "Images lack alt text"},
            {
                "severity": "medium",
                "title": "Color Contrast",
                "description": "Low contrast",
                "recommendation": "Use darker text",
            },
        ]
        result = _format_findings(findings)
        assert "[high] Missing Alt" in result
        assert "Color Contrast" in result
        assert "Recommendation:" in result

    def test_format_findings_max_15(self) -> None:
        findings = [
            {"severity": "low", "title": f"Finding {i}", "description": f"Desc {i}"}
            for i in range(25)
        ]
        result = _format_findings(findings)
        assert "Finding 14" in result
        assert "Finding 15" not in result

    def test_extract_html_block(self) -> None:
        response = 'Here is the redesign:\n```html\n<div class="hero">Hello</div>\n```\nDone.'
        result = _extract_html_block(response)
        assert result == '<div class="hero">Hello</div>'

    def test_extract_html_block_generic(self) -> None:
        response = "Here:\n```\n<div>Generic</div>\n```"
        result = _extract_html_block(response)
        assert result == "<div>Generic</div>"

    def test_extract_html_block_no_block(self) -> None:
        response = "<div>Just HTML no block</div>"
        result = _extract_html_block(response)
        assert result == response

    def test_all_styles_have_description(self) -> None:
        for style in ["modern", "minimalist", "bold", "elegant"]:
            assert style in STYLE_DESCRIPTIONS

    def test_compose_section_page(self) -> None:
        gen = HtmlGenerator.__new__(HtmlGenerator)
        sections = {"hero": "<section>Hero</section>", "cta": "<section>CTA</section>"}
        result = gen.compose_section_page(sections, title="Test Page", style="modern")
        assert "<!DOCTYPE html>" in result
        assert "Test Page" in result
        assert "Hero</section>" in result
        assert "CTA</section>" in result
        assert "tailwindcss" in result


# ============================================================================
# Screenshot Renderer Tests
# ============================================================================


class TestScreenshotRenderer:
    def test_viewport_sizes(self) -> None:
        assert "desktop" in VIEWPORT_SIZES
        assert "tablet" in VIEWPORT_SIZES
        assert "mobile" in VIEWPORT_SIZES

    def test_desktop_is_largest(self) -> None:
        assert VIEWPORT_SIZES["desktop"]["width"] > VIEWPORT_SIZES["tablet"]["width"]
        assert VIEWPORT_SIZES["tablet"]["width"] > VIEWPORT_SIZES["mobile"]["width"]

    def test_viewport_dimensions(self) -> None:
        for name, size in VIEWPORT_SIZES.items():
            assert "width" in size, f"Missing width for {name}"
            assert "height" in size, f"Missing height for {name}"
            assert size["width"] > 0
            assert size["height"] > 0


# ============================================================================
# Storage Service Tests
# ============================================================================


class TestStorageService:
    @pytest.fixture()
    def storage(self, tmp_path, monkeypatch) -> StorageService:
        """Create a storage service with a temp directory."""
        from src.config import clear_settings_cache

        clear_settings_cache()

        monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path / "storage"))
        monkeypatch.setenv("API_PORT", "6306")
        clear_settings_cache()

        svc = StorageService.__new__(StorageService)
        svc._backend = "local"
        svc._local_path = tmp_path / "storage"
        svc._local_path.mkdir(parents=True, exist_ok=True)
        return svc

    @pytest.mark.asyncio
    async def test_store_and_retrieve_html(self, storage) -> None:
        path = await storage.store_html("job-1", "<html>Hello</html>")
        content = await storage.retrieve_text(path)
        assert content == "<html>Hello</html>"

    @pytest.mark.asyncio
    async def test_store_and_retrieve_bytes(self, storage) -> None:
        data = b"\x89PNG\r\n\x1a\n"
        path = await storage.store_bytes("job-1", data, "screenshot.png")
        retrieved = await storage.retrieve(path)
        assert retrieved == data

    @pytest.mark.asyncio
    async def test_retrieve_missing_returns_none(self, storage) -> None:
        result = await storage.retrieve("/nonexistent/path.html")
        assert result is None

    @pytest.mark.asyncio
    async def test_retrieve_text_missing_returns_none(self, storage) -> None:
        result = await storage.retrieve_text("/nonexistent/path.html")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_existing(self, storage) -> None:
        path = await storage.store_html("job-2", "<p>test</p>")
        assert await storage.delete(path) is True

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, storage) -> None:
        assert await storage.delete("/nonexistent/file.html") is False

    @pytest.mark.asyncio
    async def test_get_job_dir_creates_directory(self, storage) -> None:
        job_dir = storage.get_job_dir("my-job")
        assert job_dir.exists()
        assert job_dir.is_dir()

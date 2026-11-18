"""Unit tests for BatchManager and related batch processing logic."""

from src.services.page_selector import select_pages


class TestBatchPageSelection:
    """Test page selection logic used in batch processing."""

    def test_focus_pages_boost(self) -> None:
        pages = [
            {"url": "https://example.com/blog", "page_type": "blog_post"},
            {"url": "https://example.com/about", "page_type": "about"},
        ]
        result = select_pages(
            pages,
            focus_pages=["https://example.com/blog"],
        )
        # blog_post(20) + focus(50) = 70 > about(60)
        assert result[0]["url"] == "https://example.com/blog"

    def test_exclude_pages_filter(self) -> None:
        pages = [
            {"url": "https://example.com/", "page_type": "homepage"},
            {"url": "https://example.com/secret", "page_type": "landing"},
        ]
        result = select_pages(
            pages,
            exclude_pages=["https://example.com/secret"],
        )
        assert len(result) == 1
        assert result[0]["url"] == "https://example.com/"

    def test_focus_and_exclude_combined(self) -> None:
        pages = [
            {"url": "https://example.com/a", "page_type": "blog_post"},
            {"url": "https://example.com/b", "page_type": "blog_post"},
            {"url": "https://example.com/c", "page_type": "blog_post"},
        ]
        result = select_pages(
            pages,
            focus_pages=["https://example.com/a"],
            exclude_pages=["https://example.com/b"],
        )
        assert len(result) == 2
        assert result[0]["url"] == "https://example.com/a"  # Boosted
        assert result[1]["url"] == "https://example.com/c"

    def test_empty_focus_and_exclude(self) -> None:
        pages = [
            {"url": "https://example.com/", "page_type": "homepage"},
        ]
        result = select_pages(pages, focus_pages=[], exclude_pages=[])
        assert len(result) == 1

    def test_max_pages_with_focus(self) -> None:
        pages = [{"url": f"https://example.com/{i}", "page_type": "blog_post"} for i in range(10)]
        result = select_pages(
            pages,
            max_pages=2,
            focus_pages=["https://example.com/5"],
        )
        assert len(result) == 2
        assert result[0]["url"] == "https://example.com/5"

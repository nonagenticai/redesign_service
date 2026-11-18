"""Unit tests for context_resolver section detection and site-type inference (Phase 2)."""

from src.services.context_resolver import detect_sections, infer_site_type

# ============================================================================
# infer_site_type -- HTML content patterns
# ============================================================================


class TestInferSiteTypeFromHtml:
    def test_ecommerce_patterns(self) -> None:
        html = """
        <html>
        <body>
            <div class="product-grid">
                <button>Add to Cart</button>
                <span class="product-price">$29.99</span>
                <a href="/checkout">Checkout</a>
            </div>
        </body>
        </html>
        """
        result = infer_site_type(html)
        assert result == "ecommerce"

    def test_blog_patterns(self) -> None:
        html = """
        <html>
        <body>
            <article>
                <h1>Blog Post Title</h1>
                <span>Published on 2024-01-01</span>
                <p>Author: Jane Doe</p>
                <a href="/more">Read More</a>
            </article>
        </body>
        </html>
        """
        result = infer_site_type(html)
        assert result == "blog"

    def test_saas_patterns(self) -> None:
        html = """
        <html>
        <body>
            <div class="pricing-table">
                <h2>Pricing Plan</h2>
                <button>Sign Up</button>
                <a href="/trial">Free Trial</a>
                <a href="/start">Get Started</a>
            </div>
        </body>
        </html>
        """
        result = infer_site_type(html)
        assert result == "saas"

    def test_empty_html_returns_none(self) -> None:
        assert infer_site_type("") is None

    def test_no_matching_patterns_returns_none(self) -> None:
        html = "<html><body><p>Hello World</p></body></html>"
        result = infer_site_type(html)
        assert result is None


# ============================================================================
# infer_site_type -- URL patterns
# ============================================================================


class TestInferSiteTypeFromUrl:
    def test_blog_url(self) -> None:
        html = "<html><body><p>Some content</p></body></html>"
        result = infer_site_type(html, url="https://example.com/blog/my-post")
        assert result == "blog"

    def test_ecommerce_url(self) -> None:
        html = "<html><body><p>Some content</p></body></html>"
        result = infer_site_type(html, url="https://example.com/shop/items")
        assert result == "ecommerce"

    def test_saas_url(self) -> None:
        html = "<html><body><p>Some content</p></body></html>"
        result = infer_site_type(html, url="https://example.com/pricing")
        assert result == "saas"


# ============================================================================
# infer_site_type -- meta tag patterns
# ============================================================================


class TestInferSiteTypeFromMeta:
    def test_shopify_meta(self) -> None:
        html = (
            '<html><head><meta name="generator" content="Shopify"></head><body>store</body></html>'
        )
        result = infer_site_type(html)
        assert result == "ecommerce"

    def test_wordpress_meta(self) -> None:
        html = '<html><head><meta name="generator" content="WordPress 6.0"></head><body>blog</body></html>'
        result = infer_site_type(html)
        assert result == "blog"


# ============================================================================
# detect_sections
# ============================================================================


class TestDetectSections:
    def test_finds_landmark_elements(self) -> None:
        html = """
        <html>
        <body>
            <header><h1>Site Title</h1></header>
            <nav><a href="/">Home</a></nav>
            <main><h2>Content</h2><p>Body text</p></main>
            <footer><p>Copyright 2025</p></footer>
        </body>
        </html>
        """
        sections = detect_sections(html)
        tags = [s["tag"] for s in sections]
        assert "header" in tags
        assert "nav" in tags
        assert "main" in tags
        assert "footer" in tags

    def test_identifies_section_types_from_classes(self) -> None:
        html = """
        <html>
        <body>
            <section class="hero-section" id="hero"><h1>Welcome</h1></section>
            <section class="features"><h2>Features</h2></section>
            <section class="pricing"><h2>Pricing</h2></section>
            <section class="testimonials"><h2>What people say</h2></section>
        </body>
        </html>
        """
        sections = detect_sections(html)
        types = [s["section_type"] for s in sections]
        assert "hero" in types
        assert "features" in types
        assert "pricing" in types
        assert "testimonials" in types

    def test_captures_heading_text(self) -> None:
        html = "<html><body><section><h2>About Us</h2><p>Info</p></section></body></html>"
        sections = detect_sections(html)
        assert len(sections) == 1
        assert sections[0]["heading"] == "About Us"

    def test_empty_html_returns_empty_list(self) -> None:
        sections = detect_sections("<html><body></body></html>")
        assert sections == []

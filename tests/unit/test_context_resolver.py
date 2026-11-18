"""Unit tests for context_resolver."""

from src.services.context_resolver import (
    GOAL_DESIGN_ACTIONS,
    ResolvedContext,
    infer_site_type,
    resolve_context,
)


class TestInferSiteType:
    def test_ecommerce_patterns(self) -> None:
        html = (
            '<button class="add-to-cart">Add to Cart</button><div class="product-price">$29</div>'
        )
        assert infer_site_type(html) == "ecommerce"

    def test_saas_patterns(self) -> None:
        html = '<a href="/sign-up">Sign Up</a><div class="pricing-plan">Free Trial</div>'
        assert infer_site_type(html) == "saas"

    def test_blog_patterns(self) -> None:
        html = '<article class="blog-post"><span>Published on 2024-01-01</span><a>Read More</a></article>'
        assert infer_site_type(html) == "blog"

    def test_empty_html_returns_none(self) -> None:
        assert infer_site_type("") is None

    def test_no_patterns_returns_none(self) -> None:
        assert infer_site_type("<html><body>Hello World</body></html>") is None


class TestResolveContext:
    def test_empty_context(self) -> None:
        ctx = resolve_context()
        assert isinstance(ctx, ResolvedContext)
        assert ctx.primary_color == "#2563EB"
        assert ctx.tone == "professional"

    def test_brand_overrides_defaults(self) -> None:
        ctx = resolve_context(brand={"primary_color": "#FF0000", "name": "TestBrand"})
        assert ctx.primary_color == "#FF0000"
        assert ctx.brand_name == "TestBrand"

    def test_site_analysis_layer(self) -> None:
        ctx = resolve_context(
            site_analysis={
                "description": "A test site",
                "target_audience": ["developers"],
                "tone": "casual",
            }
        )
        assert ctx.description == "A test site"
        assert ctx.target_audience == ["developers"]
        assert ctx.tone == "casual"

    def test_user_context_highest_priority(self) -> None:
        ctx = resolve_context(
            site_analysis={"description": "From analysis", "target_audience": ["users"]},
            user_context={
                "description": "From user",
                "target_audience": ["developers", "designers"],
                "goals": ["increase_conversions"],
            },
        )
        assert ctx.description == "From user"
        assert ctx.target_audience == ["developers", "designers"]
        assert ctx.goals == ["increase_conversions"]

    def test_html_inference(self) -> None:
        html = '<button class="add-to-cart">Buy Now</button>'
        ctx = resolve_context(html=html)
        assert ctx.site_type == "ecommerce"

    def test_user_context_overrides_inference(self) -> None:
        html = '<button class="add-to-cart">Buy Now</button>'
        ctx = resolve_context(html=html, user_context={"site_type": "saas"})
        assert ctx.site_type == "saas"

    def test_visual_preferences(self) -> None:
        ctx = resolve_context(
            user_context={
                "visual_preferences": {"color_scheme": "dark", "animation_level": "subtle"}
            }
        )
        assert ctx.visual_preferences["color_scheme"] == "dark"

    def test_focus_and_exclude_pages(self) -> None:
        ctx = resolve_context(
            user_context={
                "focus_pages": ["/pricing", "/features"],
                "exclude_pages": ["/blog"],
            }
        )
        assert "/pricing" in ctx.focus_pages
        assert "/blog" in ctx.exclude_pages


class TestGoalDesignActions:
    def test_all_goals_have_actions(self) -> None:
        expected = [
            "increase_conversions",
            "improve_engagement",
            "reduce_bounce_rate",
            "build_trust",
            "generate_leads",
            "boost_sales",
            "improve_seo",
            "enhance_accessibility",
        ]
        for goal in expected:
            assert goal in GOAL_DESIGN_ACTIONS

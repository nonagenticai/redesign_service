"""Resolve and merge user context from multiple sources for redesign prompts."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ResolvedContext:
    """Merged context from user input, site analysis, brand, and inference."""

    description: str | None = None
    site_type: str | None = None
    target_audience: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    focus_pages: list[str] = field(default_factory=list)
    exclude_pages: list[str] = field(default_factory=list)
    feature_priorities: list[dict] = field(default_factory=list)
    visual_preferences: dict = field(default_factory=dict)
    tone: str = "professional"
    primary_color: str = "#2563EB"
    secondary_color: str = "#1E40AF"
    brand_name: str | None = None
    font_family: str | None = None
    logo_url: str | None = None


# Patterns for inferring site type from HTML content
_SITE_TYPE_PATTERNS: dict[str, list[str]] = {
    "ecommerce": [
        r"add[- ]to[- ]cart",
        r"shopping[- ]cart",
        r"checkout",
        r"product[- ]price",
        r"buy[- ]now",
    ],
    "saas": [
        r"sign[- ]up",
        r"free[- ]trial",
        r"pricing[- ]plan",
        r"get[- ]started",
        r"dashboard",
    ],
    "blog": [
        r"blog[- ]post",
        r"article",
        r"published[- ]on",
        r"read[- ]more",
        r"author",
    ],
    "portfolio": [
        r"portfolio",
        r"my[- ]work",
        r"projects",
        r"case[- ]stud",
    ],
    "corporate": [
        r"about[- ]us",
        r"our[- ]team",
        r"careers",
        r"investor",
        r"annual[- ]report",
    ],
    "landing": [
        r"hero[- ]section",
        r"call[- ]to[- ]action",
        r"cta",
        r"landing",
    ],
}


_URL_PATH_PATTERNS: dict[str, list[str]] = {
    "blog": [r"/blog", r"/posts", r"/articles", r"/news"],
    "ecommerce": [r"/product", r"/shop", r"/store", r"/cart", r"/collection"],
    "saas": [r"/pricing", r"/features", r"/integrations", r"/docs"],
    "portfolio": [r"/portfolio", r"/work", r"/projects", r"/gallery"],
    "corporate": [r"/about", r"/careers", r"/investor", r"/press"],
    "landing": [r"/lp/", r"/promo/", r"/offer/"],
}

_META_TAG_PATTERNS: dict[str, list[str]] = {
    "ecommerce": [r"og:type.*product", r"shopify", r"woocommerce", r"magento"],
    "blog": [r"og:type.*article", r"wordpress", r"ghost"],
    "saas": [r"og:type.*website", r"intercom", r"hubspot"],
}


def infer_site_type(html: str, url: str | None = None) -> str | None:
    """Infer site type from HTML content and URL using heuristic pattern matching."""
    if not html:
        return None

    scores: dict[str, int] = {}

    # URL path patterns
    if url:
        url_lower = url.lower()
        for site_type, patterns in _URL_PATH_PATTERNS.items():
            for p in patterns:
                if re.search(p, url_lower):
                    scores[site_type] = scores.get(site_type, 0) + 2

    html_lower = html.lower()

    # Meta tag analysis
    for site_type, patterns in _META_TAG_PATTERNS.items():
        for p in patterns:
            if re.search(p, html_lower):
                scores[site_type] = scores.get(site_type, 0) + 2

    # DOM structure patterns
    for site_type, patterns in _SITE_TYPE_PATTERNS.items():
        score = sum(1 for p in patterns if re.search(p, html_lower))
        if score > 0:
            scores[site_type] = scores.get(site_type, 0) + score

    # DOM structure signatures
    if re.search(r'class="[^"]*product[- ]grid', html_lower):
        scores["ecommerce"] = scores.get("ecommerce", 0) + 3
    if re.search(r"<article", html_lower):
        scores["blog"] = scores.get("blog", 0) + 2
    if re.search(r'class="[^"]*pricing[- ]table', html_lower):
        scores["saas"] = scores.get("saas", 0) + 3

    if not scores:
        return None
    return max(scores, key=scores.get)  # type: ignore[arg-type]


def detect_sections(html: str) -> list[dict]:
    """Detect semantic sections from HTML using heading and landmark analysis."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    sections: list[dict] = []

    # Find landmark elements
    for landmark in soup.find_all(["header", "nav", "main", "footer", "aside", "section"]):
        section_type = landmark.name
        heading = landmark.find(re.compile(r"^h[1-6]$"))
        heading_text = heading.get_text(strip=True) if heading else None
        role = landmark.get("role", "")
        aria_label = landmark.get("aria-label", "")

        # Try to determine purpose from class/id
        classes = " ".join(landmark.get("class") or [])
        section_id = landmark.get("id", "")
        identifier = f"{classes} {section_id}".lower()

        detected_type = section_type
        for known_type in [
            "hero",
            "features",
            "pricing",
            "testimonials",
            "cta",
            "faq",
            "contact",
            "about",
            "team",
        ]:
            if known_type in identifier:
                detected_type = known_type
                break

        sections.append(
            {
                "section_type": detected_type,
                "heading": heading_text,
                "role": role or None,
                "aria_label": aria_label or None,
                "tag": landmark.name,
            }
        )

    return sections


def resolve_context(
    *,
    user_context: dict | None = None,
    site_analysis: dict | None = None,
    brand: dict | None = None,
    html: str | None = None,
) -> ResolvedContext:
    """Merge context from multiple sources. Priority: user_context > site_analysis > brand > inferred."""
    ctx = ResolvedContext()

    # Layer 1: Inferred defaults from HTML
    if html:
        inferred_type = infer_site_type(html)
        if inferred_type:
            ctx.site_type = inferred_type

    # Layer 2: Brand info
    if brand:
        ctx.primary_color = brand.get("primary_color", ctx.primary_color)
        ctx.secondary_color = brand.get("secondary_color", ctx.secondary_color)
        ctx.brand_name = brand.get("name", ctx.brand_name)
        ctx.font_family = brand.get("font_family", ctx.font_family)
        ctx.logo_url = brand.get("logo_url", ctx.logo_url)

    # Layer 3: Site analysis
    if site_analysis:
        ctx.description = site_analysis.get("description", ctx.description)
        if site_analysis.get("target_audience"):
            ctx.target_audience = site_analysis["target_audience"]
        ctx.tone = site_analysis.get("tone", ctx.tone) or ctx.tone
        vis = site_analysis.get("visual_identity") or {}
        if vis.get("primary_color"):
            ctx.primary_color = vis["primary_color"]
        if vis.get("secondary_color"):
            ctx.secondary_color = vis["secondary_color"]

    # Layer 4: User context (highest priority)
    if user_context:
        if user_context.get("description"):
            ctx.description = user_context["description"]
        if user_context.get("site_type"):
            ctx.site_type = user_context["site_type"]
        if user_context.get("target_audience"):
            ctx.target_audience = user_context["target_audience"]
        if user_context.get("goals"):
            ctx.goals = user_context["goals"]
        if user_context.get("focus_pages"):
            ctx.focus_pages = user_context["focus_pages"]
        if user_context.get("exclude_pages"):
            ctx.exclude_pages = user_context["exclude_pages"]
        if user_context.get("feature_priorities"):
            ctx.feature_priorities = user_context["feature_priorities"]
        if user_context.get("visual_preferences"):
            ctx.visual_preferences = user_context["visual_preferences"]

    return ctx


# Mapping of user goals to design actions for prompt injection
GOAL_DESIGN_ACTIONS: dict[str, str] = {
    "increase_conversions": "Optimize CTA placement, use contrasting button colors, add urgency elements",
    "improve_engagement": "Add interactive elements, improve content hierarchy, use compelling visuals",
    "reduce_bounce_rate": "Improve above-the-fold content, speed up perceived load time, clear value proposition",
    "build_trust": "Add testimonials, trust badges, clear contact info, professional imagery",
    "generate_leads": "Prominent lead capture forms, compelling offer, clear benefits list",
    "boost_sales": "Product highlights, social proof, easy checkout flow, urgency indicators",
    "improve_seo": "Semantic HTML, proper heading hierarchy, image alt text, structured data",
    "enhance_accessibility": "WCAG compliance, keyboard navigation, screen reader support, color contrast",
}

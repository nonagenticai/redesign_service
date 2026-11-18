"""Deterministic HTML validator using BeautifulSoup for a11y, SEO, and performance checks."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Severity levels
# ---------------------------------------------------------------------------
SEVERITY_CRITICAL = "critical"
SEVERITY_MAJOR = "major"
SEVERITY_MINOR = "minor"

# ---------------------------------------------------------------------------
# Validation categories
# ---------------------------------------------------------------------------
CATEGORY_A11Y = "a11y"
CATEGORY_SEO = "seo"
CATEGORY_PERFORMANCE = "performance"

# Threshold (bytes) for total inline-style size considered problematic.
INLINE_STYLE_SIZE_THRESHOLD = 5 * 1024  # 5 KB

# Expected heading levels in order (h1 through h6).
_HEADING_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]
_HEADING_LEVEL_MAP: dict[str, int] = {tag: idx + 1 for idx, tag in enumerate(_HEADING_TAGS)}

# ARIA landmark roles we expect at least one of.
_LANDMARK_ROLES = {"main", "navigation", "contentinfo"}

# Corresponding HTML5 semantic elements that imply a landmark role.
_LANDMARK_ELEMENTS = {"main", "nav", "footer"}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class ValidationFinding:
    """A single validation issue found during HTML analysis."""

    category: str
    severity: str
    description: str
    element: str | None = None
    recommendation: str | None = None


@dataclass
class ValidationReport:
    """Complete validation report for an HTML document."""

    findings: list[ValidationFinding] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialise the report to a plain dictionary."""
        return {
            "findings": [
                {
                    "category": f.category,
                    "severity": f.severity,
                    "description": f.description,
                    "element": f.element,
                    "recommendation": f.recommendation,
                }
                for f in self.findings
            ],
            "summary": dict(self.summary),
        }


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------
class HtmlValidator:
    """Deterministic HTML validator that checks a11y, SEO, and performance.

    All checks are static and run synchronously -- no network calls, no LLM.
    Uses BeautifulSoup with the built-in ``html.parser`` backend.
    """

    @staticmethod
    def validate(html: str) -> ValidationReport:
        """Run every registered check against *html* and return a report.

        Args:
            html: Raw HTML string to validate.

        Returns:
            A ``ValidationReport`` containing all findings and a per-category
            summary count.
        """
        soup = BeautifulSoup(html, "html.parser")
        findings: list[ValidationFinding] = []

        # -- Accessibility checks -------------------------------------------
        findings.extend(_check_images_missing_alt(soup))
        findings.extend(_check_empty_links(soup))
        findings.extend(_check_heading_level_skips(soup))
        findings.extend(_check_missing_lang(soup))
        findings.extend(_check_missing_aria_landmarks(soup))

        # -- SEO checks -----------------------------------------------------
        findings.extend(_check_missing_title(soup))
        findings.extend(_check_missing_meta_description(soup))
        findings.extend(_check_missing_h1(soup))
        findings.extend(_check_duplicate_h1(soup))

        # -- Performance checks ---------------------------------------------
        findings.extend(_check_inline_style_size(soup))
        findings.extend(_check_images_missing_lazy(soup))

        # Build the category summary
        summary: dict[str, int] = {}
        for finding in findings:
            summary[finding.category] = summary.get(finding.category, 0) + 1

        report = ValidationReport(findings=findings, summary=summary)

        logger.debug(
            "HTML validation complete: %d finding(s) across %d category(ies)",
            len(findings),
            len(summary),
        )
        return report


# ---------------------------------------------------------------------------
# Accessibility checks
# ---------------------------------------------------------------------------
def _check_images_missing_alt(soup: BeautifulSoup) -> list[ValidationFinding]:
    """Flag <img> tags that lack an ``alt`` attribute."""
    findings: list[ValidationFinding] = []
    for img in soup.find_all("img"):
        if not isinstance(img, Tag):
            continue
        alt = img.get("alt")
        if alt is None:
            src = img.get("src", "<unknown>")
            findings.append(
                ValidationFinding(
                    category=CATEGORY_A11Y,
                    severity=SEVERITY_CRITICAL,
                    description="Image missing alt attribute",
                    element=f'<img src="{src}">',
                    recommendation=(
                        'Add a descriptive alt attribute, or alt="" for purely decorative images.'
                    ),
                )
            )
    return findings


def _check_empty_links(soup: BeautifulSoup) -> list[ValidationFinding]:
    """Flag <a> tags that contain no visible text content."""
    findings: list[ValidationFinding] = []
    for link in soup.find_all("a"):
        if not isinstance(link, Tag):
            continue
        text = link.get_text(strip=True)
        # Also accept an aria-label as accessible text
        aria_label = link.get("aria-label", "")
        if not text and not aria_label:
            href = link.get("href", "")
            findings.append(
                ValidationFinding(
                    category=CATEGORY_A11Y,
                    severity=SEVERITY_MAJOR,
                    description="Anchor element has no accessible text",
                    element=f'<a href="{href}">',
                    recommendation=(
                        "Add visible text content or an aria-label attribute "
                        "to describe the link purpose."
                    ),
                )
            )
    return findings


def _check_heading_level_skips(soup: BeautifulSoup) -> list[ValidationFinding]:
    """Detect heading-level jumps (e.g. h1 followed directly by h3)."""
    findings: list[ValidationFinding] = []
    headings = soup.find_all(_HEADING_TAGS)
    previous_level: int | None = None

    for heading in headings:
        if not isinstance(heading, Tag):
            continue
        current_level = _HEADING_LEVEL_MAP.get(heading.name, 0)
        if previous_level is not None and current_level > previous_level + 1:
            findings.append(
                ValidationFinding(
                    category=CATEGORY_A11Y,
                    severity=SEVERITY_MAJOR,
                    description=(f"Heading level skip from h{previous_level} to h{current_level}"),
                    element=f"<{heading.name}>",
                    recommendation=(
                        "Use sequential heading levels without skipping (e.g. h1 -> h2 -> h3)."
                    ),
                )
            )
        previous_level = current_level

    return findings


def _check_missing_lang(soup: BeautifulSoup) -> list[ValidationFinding]:
    """Flag missing ``lang`` attribute on the <html> element."""
    html_tag = soup.find("html")
    if html_tag is None or not isinstance(html_tag, Tag):
        # If there is no <html> wrapper at all, still flag it.
        return [
            ValidationFinding(
                category=CATEGORY_A11Y,
                severity=SEVERITY_MAJOR,
                description="No <html> element with lang attribute found",
                element=None,
                recommendation=(
                    'Add a lang attribute to the root <html> tag, e.g. <html lang="en">.'
                ),
            )
        ]

    lang = html_tag.get("lang", "")
    if not lang:
        return [
            ValidationFinding(
                category=CATEGORY_A11Y,
                severity=SEVERITY_MAJOR,
                description="<html> element missing lang attribute",
                element="<html>",
                recommendation=('Specify the document language, e.g. <html lang="en">.'),
            )
        ]
    return []


def _check_missing_aria_landmarks(soup: BeautifulSoup) -> list[ValidationFinding]:
    """Flag when the page lacks any ARIA landmark roles or equivalent elements."""
    findings: list[ValidationFinding] = []

    for role in _LANDMARK_ROLES:
        # Check for explicit role="..." attribute
        has_role = soup.find(attrs={"role": role}) is not None

        # Check for the corresponding semantic HTML5 element
        matching_elements = _LANDMARK_ELEMENTS & {
            el
            for el in _LANDMARK_ELEMENTS
            if (role == "main" and el == "main")
            or (role == "navigation" and el == "nav")
            or (role == "contentinfo" and el == "footer")
        }
        has_element = any(soup.find(element) is not None for element in matching_elements)

        if not has_role and not has_element:
            readable = {
                "main": "main content",
                "navigation": "navigation",
                "contentinfo": "footer / content info",
            }
            findings.append(
                ValidationFinding(
                    category=CATEGORY_A11Y,
                    severity=SEVERITY_MINOR,
                    description=(f"Missing ARIA landmark for {readable.get(role, role)}"),
                    element=None,
                    recommendation=(
                        f"Add a <{next(iter(matching_elements))}> element or "
                        f'role="{role}" to an appropriate container.'
                    ),
                )
            )

    return findings


# ---------------------------------------------------------------------------
# SEO checks
# ---------------------------------------------------------------------------
def _check_missing_title(soup: BeautifulSoup) -> list[ValidationFinding]:
    """Flag when no <title> tag is present inside <head>."""
    title_tag = soup.find("title")
    if title_tag is None or not title_tag.get_text(strip=True):
        return [
            ValidationFinding(
                category=CATEGORY_SEO,
                severity=SEVERITY_CRITICAL,
                description="Page is missing a <title> tag",
                element=None,
                recommendation=(
                    "Add a descriptive <title> inside the <head> element. "
                    "Keep it under 60 characters for optimal display in SERPs."
                ),
            )
        ]
    return []


def _check_missing_meta_description(soup: BeautifulSoup) -> list[ValidationFinding]:
    """Flag when no meta description tag is present."""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta is None:
        return [
            ValidationFinding(
                category=CATEGORY_SEO,
                severity=SEVERITY_MAJOR,
                description="Page is missing a meta description",
                element=None,
                recommendation=(
                    'Add <meta name="description" content="..."> in the '
                    "<head>. Aim for 150-160 characters."
                ),
            )
        ]
    # Also flag an empty content attribute
    if isinstance(meta, Tag) and not str(meta.get("content") or "").strip():
        return [
            ValidationFinding(
                category=CATEGORY_SEO,
                severity=SEVERITY_MAJOR,
                description="Meta description has empty content",
                element='<meta name="description">',
                recommendation="Provide a meaningful description of the page content.",
            )
        ]
    return []


def _check_missing_h1(soup: BeautifulSoup) -> list[ValidationFinding]:
    """Flag when the page has no <h1> element."""
    if not soup.find("h1"):
        return [
            ValidationFinding(
                category=CATEGORY_SEO,
                severity=SEVERITY_CRITICAL,
                description="Page is missing an <h1> element",
                element=None,
                recommendation=("Add exactly one <h1> that summarises the page's primary topic."),
            )
        ]
    return []


def _check_duplicate_h1(soup: BeautifulSoup) -> list[ValidationFinding]:
    """Flag when the page contains more than one <h1> element."""
    h1_tags = soup.find_all("h1")
    if len(h1_tags) > 1:
        return [
            ValidationFinding(
                category=CATEGORY_SEO,
                severity=SEVERITY_MAJOR,
                description=f"Page has {len(h1_tags)} <h1> elements (expected 1)",
                element=None,
                recommendation=(
                    "Use a single <h1> per page. Demote additional headings to <h2> or lower."
                ),
            )
        ]
    return []


# ---------------------------------------------------------------------------
# Performance checks
# ---------------------------------------------------------------------------
def _check_inline_style_size(soup: BeautifulSoup) -> list[ValidationFinding]:
    """Flag when the combined size of all inline ``style`` attributes exceeds the threshold."""
    total_bytes = 0
    for tag in soup.find_all(attrs={"style": True}):
        if isinstance(tag, Tag):
            style_value = tag.get("style", "")
            if isinstance(style_value, str):
                total_bytes += len(style_value.encode("utf-8"))

    if total_bytes > INLINE_STYLE_SIZE_THRESHOLD:
        size_kb = total_bytes / 1024
        return [
            ValidationFinding(
                category=CATEGORY_PERFORMANCE,
                severity=SEVERITY_MAJOR,
                description=(
                    f"Total inline style size is {size_kb:.1f} KB "
                    f"(threshold: {INLINE_STYLE_SIZE_THRESHOLD / 1024:.0f} KB)"
                ),
                element=None,
                recommendation=(
                    "Move inline styles to a <style> block or external CSS "
                    "file to reduce HTML payload and enable browser caching."
                ),
            )
        ]
    return []


def _check_images_missing_lazy(soup: BeautifulSoup) -> list[ValidationFinding]:
    """Flag <img> tags that lack a ``loading=\"lazy\"`` attribute."""
    findings: list[ValidationFinding] = []
    for img in soup.find_all("img"):
        if not isinstance(img, Tag):
            continue
        loading = img.get("loading", "")
        if loading != "lazy":
            src = img.get("src", "<unknown>")
            findings.append(
                ValidationFinding(
                    category=CATEGORY_PERFORMANCE,
                    severity=SEVERITY_MINOR,
                    description='Image missing loading="lazy" attribute',
                    element=f'<img src="{src}">',
                    recommendation=(
                        'Add loading="lazy" to defer off-screen image loading '
                        "and improve initial page load time."
                    ),
                )
            )
    return findings

"""Select which pages to redesign based on priority and critique severity."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Higher number = higher priority for redesign
_PAGE_TYPE_PRIORITY: dict[str, int] = {
    "homepage": 100,
    "landing": 90,
    "product": 80,
    "pricing": 70,
    "about": 60,
    "product_listing": 55,
    "contact": 50,
    "blog_index": 40,
    "form": 35,
    "faq": 30,
    "gallery": 25,
    "blog_post": 20,
    "dashboard": 15,
    "documentation": 10,
    "login": 5,
    "unknown": 1,
}

_SEVERITY_BOOST: dict[str, int] = {
    "critical": 40,
    "high": 25,
    "medium": 10,
    "low": 5,
    "info": 0,
}


def select_pages(
    pages: list[dict],
    critique_findings: list[dict] | None = None,
    max_pages: int = 5,
    focus_pages: list[str] | None = None,
    exclude_pages: list[str] | None = None,
) -> list[dict]:
    """Select and rank pages for redesign.

    Pages are scored by their type priority and boosted by the severity
    of any critique findings that reference them.  Returns up to
    *max_pages* pages, sorted by score descending.

    Args:
        pages: List of page dicts with url and page_type.
        critique_findings: Optional critique findings to boost scores.
        max_pages: Maximum number of pages to return.
        focus_pages: URLs to boost priority (+50 score).
        exclude_pages: URLs to filter out entirely.
    """
    if not pages:
        return []

    # Filter excluded pages
    exclude_set = set(exclude_pages or [])
    if exclude_set:
        pages = [p for p in pages if p.get("url", "") not in exclude_set]

    focus_set = set(focus_pages or [])

    # Build URL -> findings lookup
    findings_by_url: dict[str, list[dict]] = {}
    for finding in critique_findings or []:
        url = finding.get("url")
        if url:
            findings_by_url.setdefault(url, []).append(finding)

    scored: list[tuple[float, dict]] = []
    for page in pages:
        page_type = page.get("page_type", "unknown")
        base_score = _PAGE_TYPE_PRIORITY.get(str(page_type), 1)

        # Boost from critique findings
        boost = 0
        page_url = page.get("url", "")
        for finding in findings_by_url.get(page_url, []):
            boost += _SEVERITY_BOOST.get(str(finding.get("severity", "medium")), 0)

        # Boost focus pages
        if page_url in focus_set:
            boost += 50

        scored.append((base_score + boost, page))

    scored.sort(key=lambda x: x[0], reverse=True)

    selected = [page for _, page in scored[:max_pages]]
    logger.info(
        "Selected %d/%d pages for redesign",
        len(selected),
        len(pages),
    )
    return selected

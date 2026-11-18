"""Render redesigned HTML files in Playwright and capture screenshots."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

VIEWPORT_SIZES: dict[str, dict[str, int]] = {
    "desktop": {"width": 1440, "height": 900},
    "tablet": {"width": 768, "height": 1024},
    "mobile": {"width": 390, "height": 844},
}


async def render_screenshots(
    html_path: Path,
    output_dir: Path,
    viewports: list[str],
    timeout_ms: int = 30000,
) -> dict[str, str]:
    """Render an HTML file at multiple viewport sizes and save screenshots.

    Args:
        html_path: Path to the self-contained HTML file.
        output_dir: Directory to write screenshot PNGs into.
        viewports: List of viewport names (desktop, tablet, mobile).
        timeout_ms: Page load timeout in milliseconds.

    Returns:
        Mapping of viewport name to screenshot path string.
    """
    from playwright.async_api import async_playwright

    output_dir.mkdir(parents=True, exist_ok=True)
    screenshots: dict[str, str] = {}

    file_url = f"file://{html_path.resolve()}"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            for viewport_name in viewports:
                size = VIEWPORT_SIZES.get(viewport_name)
                if not size:
                    logger.warning("Unknown viewport '%s', skipping", viewport_name)
                    continue

                page = await browser.new_page(
                    viewport={"width": size["width"], "height": size["height"]}
                )
                try:
                    await page.goto(file_url, wait_until="networkidle", timeout=timeout_ms)
                    screenshot_path = output_dir / f"{viewport_name}.png"
                    await page.screenshot(path=str(screenshot_path), full_page=True)
                    screenshots[viewport_name] = str(screenshot_path)
                    logger.debug("Screenshot saved: %s", screenshot_path)
                finally:
                    await page.close()
        finally:
            await browser.close()

    return screenshots


async def render_from_html_string(
    html: str,
    output_dir: Path,
    viewports: list[str],
    filename_prefix: str = "screenshot",
    timeout_ms: int = 30000,
) -> dict[str, str]:
    """Render HTML from a string (write temp file, then screenshot).

    Args:
        html: HTML content string.
        output_dir: Directory to write screenshot PNGs into.
        viewports: List of viewport names.
        filename_prefix: Prefix for screenshot filenames.
        timeout_ms: Page load timeout.

    Returns:
        Mapping of viewport name to screenshot path string.
    """
    import tempfile

    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
        f.write(html)
        temp_path = Path(f.name)

    try:
        return await render_screenshots(temp_path, output_dir, viewports, timeout_ms)
    finally:
        temp_path.unlink(missing_ok=True)


async def capture_url_screenshots(
    url: str,
    output_dir: Path,
    viewports: list[str],
    timeout_ms: int = 30000,
) -> dict[str, str]:
    """Capture screenshots of a live URL at multiple viewports.

    Args:
        url: HTTP(S) URL to screenshot.
        output_dir: Directory to write screenshot PNGs into.
        viewports: List of viewport names (desktop, tablet, mobile).
        timeout_ms: Page load timeout in milliseconds.

    Returns:
        Mapping of viewport name to screenshot path string.
    """
    from playwright.async_api import async_playwright

    output_dir.mkdir(parents=True, exist_ok=True)
    screenshots: dict[str, str] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            for viewport_name in viewports:
                size = VIEWPORT_SIZES.get(viewport_name)
                if not size:
                    logger.warning("Unknown viewport '%s', skipping", viewport_name)
                    continue

                page = await browser.new_page(
                    viewport={"width": size["width"], "height": size["height"]}
                )
                try:
                    await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                    screenshot_path = output_dir / f"original_{viewport_name}.png"
                    await page.screenshot(path=str(screenshot_path), full_page=True)
                    screenshots[viewport_name] = str(screenshot_path)
                    logger.debug("Original screenshot saved: %s", screenshot_path)
                finally:
                    await page.close()
        finally:
            await browser.close()

    return screenshots


async def render_component_screenshot(
    full_page_html: str,
    component_selector: str,
    output_path: Path,
    viewport: str = "desktop",
    timeout_ms: int = 30000,
) -> str | None:
    """Render a screenshot of a specific component on the page.

    Returns the screenshot path or None on failure.
    """
    import tempfile

    from playwright.async_api import async_playwright

    size = VIEWPORT_SIZES.get(viewport, VIEWPORT_SIZES["desktop"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
        f.write(full_page_html)
        temp_path = Path(f.name)

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            try:
                page = await browser.new_page(
                    viewport={"width": size["width"], "height": size["height"]}
                )
                try:
                    file_url = f"file://{temp_path.resolve()}"
                    await page.goto(file_url, wait_until="networkidle", timeout=timeout_ms)
                    element = await page.query_selector(component_selector)
                    if element:
                        await element.screenshot(path=str(output_path))
                        return str(output_path)
                    else:
                        logger.warning("Component selector '%s' not found", component_selector)
                        return None
                finally:
                    await page.close()
            finally:
                await browser.close()
    finally:
        temp_path.unlink(missing_ok=True)

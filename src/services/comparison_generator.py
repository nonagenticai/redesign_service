"""Visual before/after comparison image generation."""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


def generate_side_by_side(
    original_path: str,
    redesigned_path: str,
    output_path: str,
    label_original: str = "BEFORE",
    label_redesigned: str = "AFTER",
) -> str:
    """Generate a labeled side-by-side comparison image.

    Returns the output path.
    """
    original = Image.open(original_path)
    redesigned = Image.open(redesigned_path)

    # Normalize heights
    max_height = max(original.height, redesigned.height)
    if original.height != max_height:
        ratio = max_height / original.height
        original = original.resize(
            (int(original.width * ratio), max_height), Image.Resampling.LANCZOS
        )
    if redesigned.height != max_height:
        ratio = max_height / redesigned.height
        redesigned = redesigned.resize(
            (int(redesigned.width * ratio), max_height), Image.Resampling.LANCZOS
        )

    # Create composite with labels
    label_height = 40
    gap = 4
    total_width = original.width + gap + redesigned.width
    total_height = max_height + label_height

    composite = Image.new("RGB", (total_width, total_height), (255, 255, 255))
    draw = ImageDraw.Draw(composite)

    # Draw labels
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    except OSError:
        font = ImageFont.load_default()

    # Original label (red background)
    draw.rectangle(
        [(0, 0), (original.width, label_height)],
        fill=(220, 53, 69),
    )
    bbox = font.getbbox(label_original)
    text_w = bbox[2] - bbox[0]
    draw.text(
        ((original.width - text_w) // 2, 8),
        label_original,
        fill=(255, 255, 255),
        font=font,
    )

    # Redesigned label (green background)
    draw.rectangle(
        [(original.width + gap, 0), (total_width, label_height)],
        fill=(40, 167, 69),
    )
    bbox = font.getbbox(label_redesigned)
    text_w = bbox[2] - bbox[0]
    draw.text(
        (original.width + gap + (redesigned.width - text_w) // 2, 8),
        label_redesigned,
        fill=(255, 255, 255),
        font=font,
    )

    # Paste images
    composite.paste(original, (0, label_height))
    composite.paste(redesigned, (original.width + gap, label_height))

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    composite.save(output_path, "PNG")
    logger.info("Side-by-side comparison saved: %s", output_path)
    return output_path


def generate_pixel_diff(
    original_path: str,
    redesigned_path: str,
    output_path: str,
    threshold: int = 30,
) -> str:
    """Generate a pixel diff image highlighting changed areas in red.

    Returns the output path.
    """
    original = Image.open(original_path).convert("RGB")
    redesigned = Image.open(redesigned_path).convert("RGB")

    # Resize to match dimensions
    width = min(original.width, redesigned.width)
    height = min(original.height, redesigned.height)
    original = original.resize((width, height), Image.Resampling.LANCZOS)
    redesigned = redesigned.resize((width, height), Image.Resampling.LANCZOS)

    # Create diff image
    diff = Image.new("RGB", (width, height), (255, 255, 255))
    orig_pixels = original.load()
    new_pixels = redesigned.load()
    diff_pixels = diff.load()

    if orig_pixels is None or new_pixels is None or diff_pixels is None:
        # Fallback: just return a blank image
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        diff.save(output_path, "PNG")
        return output_path

    for y in range(height):
        for x in range(width):
            r1, g1, b1 = orig_pixels[x, y]  # type: ignore[misc]
            r2, g2, b2 = new_pixels[x, y]  # type: ignore[misc]
            pixel_diff = abs(r1 - r2) + abs(g1 - g2) + abs(b1 - b2)
            if pixel_diff > threshold:
                # Highlight changed pixels in red overlay
                diff_pixels[x, y] = (
                    min(255, r2 + 100),
                    max(0, g2 - 50),
                    max(0, b2 - 50),
                )
            else:
                # Show original pixel dimmed
                diff_pixels[x, y] = (
                    (r2 + 200) // 2,
                    (g2 + 200) // 2,
                    (b2 + 200) // 2,
                )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    diff.save(output_path, "PNG")
    logger.info("Pixel diff saved: %s", output_path)
    return output_path


async def generate_comparisons(
    original_screenshots: dict[str, str],
    redesigned_screenshots: dict[str, str],
    output_dir: Path,
) -> tuple[dict[str, str], dict[str, str]]:
    """Generate side-by-side comparisons and pixel diffs for all viewports.

    Returns (comparison_paths, diff_paths) dicts keyed by viewport name.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    comparisons: dict[str, str] = {}
    diffs: dict[str, str] = {}

    for viewport in original_screenshots:
        if viewport not in redesigned_screenshots:
            continue

        orig_path = original_screenshots[viewport]
        new_path = redesigned_screenshots[viewport]

        try:
            comp_path = str(output_dir / f"comparison_{viewport}.png")
            comparisons[viewport] = generate_side_by_side(orig_path, new_path, comp_path)
        except Exception as exc:
            logger.warning("Failed to generate comparison for %s: %s", viewport, exc)

        try:
            diff_path = str(output_dir / f"diff_{viewport}.png")
            diffs[viewport] = generate_pixel_diff(orig_path, new_path, diff_path)
        except Exception as exc:
            logger.warning("Failed to generate diff for %s: %s", viewport, exc)

    return comparisons, diffs

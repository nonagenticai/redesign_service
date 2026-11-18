"""Unit tests for comparison_generator."""

from pathlib import Path

import pytest

from src.services.comparison_generator import (
    generate_pixel_diff,
    generate_side_by_side,
)


@pytest.fixture()
def sample_images(tmp_path: Path) -> tuple[str, str]:
    """Create two small test PNG images."""
    from PIL import Image

    img1 = Image.new("RGB", (100, 100), (255, 0, 0))
    path1 = tmp_path / "original.png"
    img1.save(str(path1))

    img2 = Image.new("RGB", (100, 100), (0, 0, 255))
    path2 = tmp_path / "redesigned.png"
    img2.save(str(path2))

    return str(path1), str(path2)


class TestSideBySide:
    def test_generates_composite(self, sample_images: tuple[str, str], tmp_path: Path) -> None:
        orig, redesigned = sample_images
        output = str(tmp_path / "comparison.png")
        result = generate_side_by_side(orig, redesigned, output)
        assert result == output
        assert Path(output).exists()

    def test_composite_dimensions(self, sample_images: tuple[str, str], tmp_path: Path) -> None:
        from PIL import Image

        orig, redesigned = sample_images
        output = str(tmp_path / "comparison.png")
        generate_side_by_side(orig, redesigned, output)
        composite = Image.open(output)
        # Width = original + gap + redesigned = 100 + 4 + 100 = 204
        assert composite.width == 204
        # Height = max_height + label_height = 100 + 40 = 140
        assert composite.height == 140


class TestPixelDiff:
    def test_generates_diff(self, sample_images: tuple[str, str], tmp_path: Path) -> None:
        orig, redesigned = sample_images
        output = str(tmp_path / "diff.png")
        result = generate_pixel_diff(orig, redesigned, output)
        assert result == output
        assert Path(output).exists()

    def test_identical_images(self, tmp_path: Path) -> None:
        from PIL import Image

        img = Image.new("RGB", (50, 50), (100, 100, 100))
        path1 = str(tmp_path / "a.png")
        path2 = str(tmp_path / "b.png")
        img.save(path1)
        img.save(path2)
        output = str(tmp_path / "diff.png")
        generate_pixel_diff(path1, path2, output, threshold=0)
        assert Path(output).exists()

    def test_diff_dimensions(self, sample_images: tuple[str, str], tmp_path: Path) -> None:
        from PIL import Image

        orig, redesigned = sample_images
        output = str(tmp_path / "diff.png")
        generate_pixel_diff(orig, redesigned, output)
        diff = Image.open(output)
        assert diff.width == 100
        assert diff.height == 100

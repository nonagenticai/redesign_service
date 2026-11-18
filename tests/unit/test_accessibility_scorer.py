"""Unit tests for AccessibilityScorer."""

from src.services.accessibility_scorer import (
    ACCESSIBILITY_CATEGORIES,
    AccessibilityFinding,
    AccessibilityReport,
    AccessibilityScorer,
    CategoryScore,
)


class TestAccessibilityReport:
    def test_empty_report(self) -> None:
        report = AccessibilityReport(overall_score=50.0)
        d = report.to_dict()
        assert d["overall_score"] == 50.0
        assert d["categories"] == []
        assert d["findings"] == []
        assert d["html_was_fixed"] is False

    def test_report_with_findings(self) -> None:
        finding = AccessibilityFinding(
            category="alt_text",
            severity="major",
            description="Image missing alt text",
            element="<img src='logo.png'>",
            recommendation="Add descriptive alt text",
            wcag_criterion="1.1.1",
        )
        cat = CategoryScore(
            category="alt_text",
            score=60.0,
            findings=[finding],
        )
        report = AccessibilityReport(
            overall_score=75.0,
            categories=[cat],
            findings=[finding],
        )
        d = report.to_dict()
        assert d["overall_score"] == 75.0
        assert len(d["categories"]) == 1
        assert d["categories"][0]["category"] == "alt_text"
        assert len(d["categories"][0]["findings"]) == 1
        assert d["findings"][0]["wcag_criterion"] == "1.1.1"


class TestAccessibilityCategories:
    def test_all_categories_defined(self) -> None:
        expected = [
            "color_contrast",
            "alt_text",
            "heading_hierarchy",
            "keyboard_navigation",
            "aria_labels",
            "form_labels",
        ]
        for cat in expected:
            assert cat in ACCESSIBILITY_CATEGORIES


class TestAccessibilityScorerParsing:
    def test_parse_valid_json(self) -> None:
        scorer = AccessibilityScorer.__new__(AccessibilityScorer)
        response = """```json
{
  "overall_score": 85,
  "categories": [
    {
      "category": "alt_text",
      "score": 90,
      "findings": [
        {
          "severity": "minor",
          "description": "Decorative image has empty alt",
          "element": "<img src='bg.png' alt=''>",
          "recommendation": "Use alt='' for decorative images",
          "wcag_criterion": "1.1.1"
        }
      ]
    }
  ]
}
```"""
        report = scorer._parse_report(response)
        assert report.overall_score == 85
        assert len(report.categories) == 1
        assert report.categories[0].score == 90
        assert len(report.findings) == 1

    def test_parse_invalid_json(self) -> None:
        scorer = AccessibilityScorer.__new__(AccessibilityScorer)
        report = scorer._parse_report("not json at all")
        assert report.overall_score == 50.0

    def test_extract_html(self) -> None:
        scorer = AccessibilityScorer.__new__(AccessibilityScorer)
        response = "Here:\n```html\n<div>Fixed</div>\n```"
        result = scorer._extract_html(response)
        assert result == "<div>Fixed</div>"

    def test_extract_html_no_block(self) -> None:
        scorer = AccessibilityScorer.__new__(AccessibilityScorer)
        result = scorer._extract_html("No code block here")
        assert result is None

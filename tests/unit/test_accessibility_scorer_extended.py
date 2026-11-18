"""Extended unit tests for AccessibilityScorer parsing and prompt building."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.services.accessibility_scorer import (
    ACCESSIBILITY_CATEGORIES,
    AccessibilityFinding,
    AccessibilityReport,
    AccessibilityScorer,
    CategoryScore,
)


class TestAccessibilityReport:
    def test_to_dict(self) -> None:
        finding = AccessibilityFinding(
            category="alt_text",
            severity="critical",
            description="Missing alt text",
            element="<img>",
            recommendation="Add alt attribute",
            wcag_criterion="1.1.1",
        )
        cat = CategoryScore(
            category="alt_text",
            score=50.0,
            findings=[finding],
        )
        report = AccessibilityReport(
            overall_score=60.0,
            categories=[cat],
            findings=[finding],
            html_was_fixed=False,
        )
        d = report.to_dict()
        assert d["overall_score"] == 60.0
        assert len(d["categories"]) == 1
        assert d["categories"][0]["category"] == "alt_text"
        assert d["categories"][0]["score"] == 50.0
        assert len(d["categories"][0]["findings"]) == 1
        assert d["findings"][0]["severity"] == "critical"
        assert d["html_was_fixed"] is False

    def test_to_dict_empty(self) -> None:
        report = AccessibilityReport(overall_score=100.0)
        d = report.to_dict()
        assert d["overall_score"] == 100.0
        assert d["categories"] == []
        assert d["findings"] == []


class TestAccessibilityCategories:
    def test_all_categories_present(self) -> None:
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


class TestParseReport:
    def _make_scorer(self) -> AccessibilityScorer:
        scorer = AccessibilityScorer.__new__(AccessibilityScorer)
        scorer._api_key = "test"  # pragma: allowlist secret
        scorer._base_url = "https://api.deepseek.com"
        scorer._model = "test"
        scorer._timeout = 10.0
        return scorer

    def test_parse_valid_json(self) -> None:
        scorer = self._make_scorer()
        data = {
            "overall_score": 85,
            "categories": [
                {
                    "category": "alt_text",
                    "score": 90,
                    "findings": [
                        {
                            "severity": "minor",
                            "description": "Decorative image has alt",
                            "element": "<img>",
                            "recommendation": "Use empty alt",
                            "wcag_criterion": "1.1.1",
                        }
                    ],
                }
            ],
        }
        report = scorer._parse_report(json.dumps(data))
        assert report.overall_score == 85.0
        assert len(report.categories) == 1
        assert report.categories[0].category == "alt_text"
        assert len(report.findings) == 1

    def test_parse_json_in_code_block(self) -> None:
        scorer = self._make_scorer()
        response = '```json\n{"overall_score": 90, "categories": []}\n```'
        report = scorer._parse_report(response)
        assert report.overall_score == 90.0

    def test_parse_json_in_generic_code_block(self) -> None:
        scorer = self._make_scorer()
        response = '```\n{"overall_score": 75, "categories": []}\n```'
        report = scorer._parse_report(response)
        assert report.overall_score == 75.0

    def test_parse_invalid_json(self) -> None:
        scorer = self._make_scorer()
        report = scorer._parse_report("Not valid JSON at all")
        assert report.overall_score == 50.0

    def test_parse_missing_fields(self) -> None:
        scorer = self._make_scorer()
        data = {"categories": []}
        report = scorer._parse_report(json.dumps(data))
        assert report.overall_score == 50.0


class TestBuildFixPrompt:
    def _make_scorer(self) -> AccessibilityScorer:
        scorer = AccessibilityScorer.__new__(AccessibilityScorer)
        scorer._api_key = "test"  # pragma: allowlist secret
        scorer._base_url = "https://api.deepseek.com"
        scorer._model = "test"
        scorer._timeout = 10.0
        return scorer

    def test_build_fix_prompt_with_findings(self) -> None:
        scorer = self._make_scorer()
        report = AccessibilityReport(
            overall_score=40.0,
            findings=[
                AccessibilityFinding(
                    category="alt_text",
                    severity="critical",
                    description="Missing alt text on hero image",
                    recommendation="Add descriptive alt text",
                ),
                AccessibilityFinding(
                    category="color_contrast",
                    severity="major",
                    description="Low contrast on body text",
                    recommendation="Use darker text color",
                ),
                AccessibilityFinding(
                    category="aria_labels",
                    severity="minor",
                    description="Decorative icon missing aria-hidden",
                ),
            ],
        )
        prompt = scorer._build_fix_prompt("<html>Test</html>", report)
        assert "Missing alt text" in prompt
        assert "Low contrast" in prompt
        assert "Decorative icon" not in prompt  # minor is excluded
        assert "Add descriptive alt text" in prompt

    def test_build_fix_prompt_no_critical_findings(self) -> None:
        scorer = self._make_scorer()
        report = AccessibilityReport(
            overall_score=80.0,
            findings=[
                AccessibilityFinding(
                    category="heading_hierarchy",
                    severity="minor",
                    description="Skip from h1 to h3",
                ),
            ],
        )
        prompt = scorer._build_fix_prompt("<html>Test</html>", report)
        assert "No critical issues found" in prompt


class TestExtractHtml:
    def _make_scorer(self) -> AccessibilityScorer:
        scorer = AccessibilityScorer.__new__(AccessibilityScorer)
        scorer._api_key = "test"  # pragma: allowlist secret
        scorer._base_url = "https://api.deepseek.com"
        scorer._model = "test"
        scorer._timeout = 10.0
        return scorer

    def test_extract_html_block(self) -> None:
        scorer = self._make_scorer()
        response = "```html\n<div>Fixed</div>\n```"
        assert scorer._extract_html(response) == "<div>Fixed</div>"

    def test_extract_no_html_block(self) -> None:
        scorer = self._make_scorer()
        assert scorer._extract_html("No code block here") is None


class TestScoreAndFix:
    @pytest.mark.asyncio
    async def test_score_above_threshold_no_fix(self) -> None:
        scorer = AccessibilityScorer.__new__(AccessibilityScorer)
        scorer._api_key = "test"  # pragma: allowlist secret
        scorer._base_url = "https://api.deepseek.com"
        scorer._model = "test"
        scorer._timeout = 10.0

        report = AccessibilityReport(overall_score=80.0)
        scorer.score = AsyncMock(return_value=report)

        html, final_report = await scorer.score_and_fix("<html>Good</html>", threshold=70.0)
        assert html == "<html>Good</html>"
        assert final_report.overall_score == 80.0
        assert final_report.html_was_fixed is False

    @pytest.mark.asyncio
    async def test_score_below_threshold_max_attempts_1(self) -> None:
        scorer = AccessibilityScorer.__new__(AccessibilityScorer)
        scorer._api_key = "test"  # pragma: allowlist secret
        scorer._base_url = "https://api.deepseek.com"
        scorer._model = "test"
        scorer._timeout = 10.0

        report = AccessibilityReport(overall_score=50.0)
        scorer.score = AsyncMock(return_value=report)

        html, final_report = await scorer.score_and_fix(
            "<html>Bad</html>", max_attempts=1, threshold=70.0
        )
        assert html == "<html>Bad</html>"
        assert final_report.overall_score == 50.0

    @pytest.mark.asyncio
    async def test_score_fix_succeeds(self) -> None:
        scorer = AccessibilityScorer.__new__(AccessibilityScorer)
        scorer._api_key = "test"  # pragma: allowlist secret
        scorer._base_url = "https://api.deepseek.com"
        scorer._model = "test"
        scorer._timeout = 10.0

        bad_report = AccessibilityReport(
            overall_score=50.0,
            findings=[
                AccessibilityFinding(
                    category="alt_text", severity="critical", description="Missing alt"
                )
            ],
        )
        good_report = AccessibilityReport(overall_score=80.0)

        scorer.score = AsyncMock(side_effect=[bad_report, good_report])
        scorer._call_llm = AsyncMock(return_value="```html\n<html>Fixed</html>\n```")

        html, final_report = await scorer.score_and_fix(
            "<html>Bad</html>", max_attempts=2, threshold=70.0
        )
        assert html == "<html>Fixed</html>"
        assert final_report.overall_score == 80.0
        assert final_report.html_was_fixed is True

    @pytest.mark.asyncio
    async def test_score_fix_extract_fails(self) -> None:
        scorer = AccessibilityScorer.__new__(AccessibilityScorer)
        scorer._api_key = "test"  # pragma: allowlist secret
        scorer._base_url = "https://api.deepseek.com"
        scorer._model = "test"
        scorer._timeout = 10.0

        bad_report = AccessibilityReport(overall_score=50.0, findings=[])
        scorer.score = AsyncMock(return_value=bad_report)
        scorer._call_llm = AsyncMock(return_value="No code block at all")

        html, final_report = await scorer.score_and_fix(
            "<html>Bad</html>", max_attempts=2, threshold=70.0
        )
        # Should return original since extraction fails
        assert html == "<html>Bad</html>"

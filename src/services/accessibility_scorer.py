"""LLM-based accessibility scoring and auto-fix for generated HTML."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import httpx

from src.config import get_settings

logger = logging.getLogger(__name__)

ACCESSIBILITY_CATEGORIES = [
    "color_contrast",
    "alt_text",
    "heading_hierarchy",
    "keyboard_navigation",
    "aria_labels",
    "form_labels",
]


@dataclass
class AccessibilityFinding:
    """A single accessibility issue."""

    category: str
    severity: str  # critical, major, minor
    description: str
    element: str | None = None
    recommendation: str | None = None
    wcag_criterion: str | None = None


@dataclass
class CategoryScore:
    """Score for a single accessibility category."""

    category: str
    score: float  # 0-100
    findings: list[AccessibilityFinding] = field(default_factory=list)


@dataclass
class AccessibilityReport:
    """Complete accessibility assessment report."""

    overall_score: float
    categories: list[CategoryScore] = field(default_factory=list)
    findings: list[AccessibilityFinding] = field(default_factory=list)
    html_was_fixed: bool = False

    def to_dict(self) -> dict:
        return {
            "overall_score": self.overall_score,
            "categories": [
                {
                    "category": c.category,
                    "score": c.score,
                    "findings": [
                        {
                            "category": f.category,
                            "severity": f.severity,
                            "description": f.description,
                            "element": f.element,
                            "recommendation": f.recommendation,
                            "wcag_criterion": f.wcag_criterion,
                        }
                        for f in c.findings
                    ],
                }
                for c in self.categories
            ],
            "findings": [
                {
                    "category": f.category,
                    "severity": f.severity,
                    "description": f.description,
                    "element": f.element,
                    "recommendation": f.recommendation,
                    "wcag_criterion": f.wcag_criterion,
                }
                for f in self.findings
            ],
            "html_was_fixed": self.html_was_fixed,
        }


_SCORING_PROMPT = """Evaluate the following HTML for WCAG 2.1 AA accessibility compliance.

Analyze these 6 categories and return a JSON object:

1. **color_contrast**: Text/background contrast ratios
2. **alt_text**: Image alt attributes
3. **heading_hierarchy**: Proper h1-h6 nesting
4. **keyboard_navigation**: Focus management, tab order, skip links
5. **aria_labels**: ARIA attributes on interactive elements
6. **form_labels**: Form input labels and associations

Return ONLY a JSON object in this exact format:
```json
{{
  "overall_score": <0-100>,
  "categories": [
    {{
      "category": "<category_name>",
      "score": <0-100>,
      "findings": [
        {{
          "severity": "<critical|major|minor>",
          "description": "<issue description>",
          "element": "<the problematic HTML element or selector>",
          "recommendation": "<how to fix>",
          "wcag_criterion": "<WCAG criterion, e.g. 1.1.1>"
        }}
      ]
    }}
  ]
}}
```

HTML to evaluate:
```html
{html}
```"""


class AccessibilityScorer:
    """LLM-based WCAG 2.1 AA accessibility evaluator."""

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.llm.api_key
        self._base_url = settings.llm.base_url
        self._model = settings.llm.model
        self._timeout = settings.llm.timeout

    async def score(self, html: str) -> AccessibilityReport:
        """Score HTML for accessibility compliance."""
        prompt = _SCORING_PROMPT.format(html=html[:12000])
        response_text = await self._call_llm(prompt)
        return self._parse_report(response_text)

    async def score_and_fix(
        self,
        html: str,
        max_attempts: int = 2,
        threshold: float = 70.0,
    ) -> tuple[str, AccessibilityReport]:
        """Score and optionally fix accessibility issues.

        Returns the (potentially fixed) HTML and the final report.
        """
        report = await self.score(html)

        if report.overall_score >= threshold or max_attempts <= 1:
            return html, report

        # Attempt auto-fix
        for attempt in range(1, max_attempts):
            fix_prompt = self._build_fix_prompt(html, report)
            fixed_response = await self._call_llm(fix_prompt)
            fixed_html = self._extract_html(fixed_response)
            if not fixed_html:
                break

            html = fixed_html
            report = await self.score(html)
            report.html_was_fixed = True

            if report.overall_score >= threshold:
                logger.info(
                    "Accessibility auto-fix succeeded on attempt %d (score: %.1f)",
                    attempt,
                    report.overall_score,
                )
                break

        return html, report

    async def _call_llm(self, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "max_tokens": 4096,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    def _parse_report(self, response_text: str) -> AccessibilityReport:
        """Parse LLM JSON response into an AccessibilityReport."""
        try:
            # Extract JSON from response (may be wrapped in code blocks)
            json_str = response_text
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]

            data = json.loads(json_str.strip())
        except (json.JSONDecodeError, IndexError):
            logger.warning("Failed to parse accessibility report JSON")
            return AccessibilityReport(overall_score=50.0)

        categories: list[CategoryScore] = []
        all_findings: list[AccessibilityFinding] = []

        for cat_data in data.get("categories", []):
            findings = []
            for f_data in cat_data.get("findings", []):
                finding = AccessibilityFinding(
                    category=cat_data.get("category", "unknown"),
                    severity=f_data.get("severity", "minor"),
                    description=f_data.get("description", ""),
                    element=f_data.get("element"),
                    recommendation=f_data.get("recommendation"),
                    wcag_criterion=f_data.get("wcag_criterion"),
                )
                findings.append(finding)
                all_findings.append(finding)

            categories.append(
                CategoryScore(
                    category=cat_data.get("category", "unknown"),
                    score=float(cat_data.get("score", 50)),
                    findings=findings,
                )
            )

        return AccessibilityReport(
            overall_score=float(data.get("overall_score", 50)),
            categories=categories,
            findings=all_findings,
        )

    def _build_fix_prompt(self, html: str, report: AccessibilityReport) -> str:
        """Build a prompt to fix accessibility issues."""
        issues = []
        for f in report.findings:
            if f.severity in ("critical", "major"):
                issues.append(f"- [{f.severity}] {f.description}")
                if f.recommendation:
                    issues.append(f"  Fix: {f.recommendation}")

        issues_text = "\n".join(issues) if issues else "No critical issues found."

        return f"""Fix the following accessibility issues in this HTML while preserving its visual design and content.

## Accessibility Issues to Fix
{issues_text}

## HTML to Fix
```html
{html[:12000]}
```

Output the FIXED HTML in a ```html code block. Only fix accessibility issues, do not change the design."""

    def _extract_html(self, response: str) -> str | None:
        """Extract HTML code block from LLM response."""
        import re

        pattern = r"```html\s*\n(.*?)```"
        match = re.search(pattern, response, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

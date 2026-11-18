"""Unit tests for HtmlValidator (Phase 2 -- deterministic HTML validation)."""

from src.services.html_validator import (
    CATEGORY_A11Y,
    CATEGORY_PERFORMANCE,
    CATEGORY_SEO,
    SEVERITY_CRITICAL,
    SEVERITY_MAJOR,
    SEVERITY_MINOR,
    HtmlValidator,
    ValidationReport,
)

# ============================================================================
# Helper: minimal valid HTML skeleton
# ============================================================================

_VALID_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="description" content="Test page for validation.">
    <title>Test Page</title>
</head>
<body>
    <header role="navigation"><nav><a href="/">Home</a></nav></header>
    <main>
        <h1>Main heading</h1>
        <h2>Sub heading</h2>
        <img src="logo.png" alt="Logo" loading="lazy">
    </main>
    <footer role="contentinfo">&copy; 2025</footer>
</body>
</html>"""


class TestHtmlValidatorCleanDocument:
    """Validate that a well-formed document produces zero findings."""

    def test_valid_html_no_findings(self) -> None:
        report = HtmlValidator.validate(_VALID_HTML)
        assert isinstance(report, ValidationReport)
        assert len(report.findings) == 0
        assert report.summary == {}


# ============================================================================
# Accessibility checks
# ============================================================================


class TestImagesMissingAlt:
    def test_image_without_alt(self) -> None:
        html = '<html lang="en"><body><main><h1>Hi</h1><img src="pic.jpg"></main></body></html>'
        report = HtmlValidator.validate(html)
        a11y = [f for f in report.findings if f.description == "Image missing alt attribute"]
        assert len(a11y) >= 1
        assert a11y[0].category == CATEGORY_A11Y
        assert a11y[0].severity == SEVERITY_CRITICAL

    def test_image_with_alt_ok(self) -> None:
        html = '<html lang="en"><body><main><h1>Hi</h1><img src="pic.jpg" alt="A photo"></main></body></html>'
        report = HtmlValidator.validate(html)
        alt_findings = [f for f in report.findings if "alt attribute" in f.description]
        assert len(alt_findings) == 0


class TestEmptyLinks:
    def test_anchor_with_no_text(self) -> None:
        html = '<html lang="en"><body><main><h1>Hi</h1><a href="/page"></a></main></body></html>'
        report = HtmlValidator.validate(html)
        link_findings = [f for f in report.findings if "no accessible text" in f.description]
        assert len(link_findings) == 1
        assert link_findings[0].severity == SEVERITY_MAJOR

    def test_anchor_with_aria_label_ok(self) -> None:
        html = '<html lang="en"><body><main><h1>Hi</h1><a href="/" aria-label="Home"></a></main></body></html>'
        report = HtmlValidator.validate(html)
        link_findings = [f for f in report.findings if "no accessible text" in f.description]
        assert len(link_findings) == 0


class TestHeadingLevelSkips:
    def test_h1_then_h3_skips(self) -> None:
        html = '<html lang="en"><body><main><h1>Title</h1><h3>Sub</h3></main></body></html>'
        report = HtmlValidator.validate(html)
        skip_findings = [f for f in report.findings if "Heading level skip" in f.description]
        assert len(skip_findings) == 1
        assert "h1" in skip_findings[0].description and "h3" in skip_findings[0].description

    def test_sequential_headings_ok(self) -> None:
        html = '<html lang="en"><body><main><h1>T</h1><h2>S</h2><h3>U</h3></main></body></html>'
        report = HtmlValidator.validate(html)
        skip_findings = [f for f in report.findings if "Heading level skip" in f.description]
        assert len(skip_findings) == 0


class TestMissingLang:
    def test_no_lang_attribute(self) -> None:
        html = "<html><head><title>T</title></head><body><main><h1>Hi</h1></main></body></html>"
        report = HtmlValidator.validate(html)
        lang_findings = [f for f in report.findings if "lang" in f.description.lower()]
        assert len(lang_findings) >= 1


class TestMissingAriaLandmarks:
    def test_no_landmarks(self) -> None:
        html = '<html lang="en"><head><title>T</title></head><body><h1>Hi</h1></body></html>'
        report = HtmlValidator.validate(html)
        lm_findings = [f for f in report.findings if "ARIA landmark" in f.description]
        assert len(lm_findings) >= 1
        assert all(f.severity == SEVERITY_MINOR for f in lm_findings)


# ============================================================================
# SEO checks
# ============================================================================


class TestMissingTitle:
    def test_no_title_tag(self) -> None:
        html = '<html lang="en"><head></head><body><main><h1>Hi</h1></main></body></html>'
        report = HtmlValidator.validate(html)
        title_findings = [f for f in report.findings if "missing a <title>" in f.description]
        assert len(title_findings) == 1
        assert title_findings[0].category == CATEGORY_SEO
        assert title_findings[0].severity == SEVERITY_CRITICAL


class TestMissingMetaDescription:
    def test_no_meta_description(self) -> None:
        html = '<html lang="en"><head><title>T</title></head><body><main><h1>Hi</h1></main></body></html>'
        report = HtmlValidator.validate(html)
        meta_findings = [f for f in report.findings if "meta description" in f.description.lower()]
        assert len(meta_findings) == 1


class TestMissingH1:
    def test_no_h1(self) -> None:
        html = '<html lang="en"><head><title>T</title><meta name="description" content="ok"></head><body><main><h2>Sub</h2></main></body></html>'
        report = HtmlValidator.validate(html)
        h1_findings = [f for f in report.findings if "missing an <h1>" in f.description]
        assert len(h1_findings) == 1
        assert h1_findings[0].severity == SEVERITY_CRITICAL


class TestDuplicateH1:
    def test_multiple_h1(self) -> None:
        html = '<html lang="en"><head><title>T</title></head><body><main><h1>One</h1><h1>Two</h1></main></body></html>'
        report = HtmlValidator.validate(html)
        dup_findings = [f for f in report.findings if "2 <h1> elements" in f.description]
        assert len(dup_findings) == 1
        assert dup_findings[0].severity == SEVERITY_MAJOR


# ============================================================================
# Performance checks
# ============================================================================


class TestInlineStyleSize:
    def test_large_inline_styles_flagged(self) -> None:
        # Create inline styles exceeding the 5 KB threshold
        big_style = "color: red; " * 500  # ~6 KB
        html = f'<html lang="en"><head><title>T</title></head><body><main><h1>Hi</h1><div style="{big_style}">x</div></main></body></html>'
        report = HtmlValidator.validate(html)
        style_findings = [
            f for f in report.findings if "inline style size" in f.description.lower()
        ]
        assert len(style_findings) == 1
        assert style_findings[0].category == CATEGORY_PERFORMANCE

    def test_small_inline_styles_ok(self) -> None:
        html = '<html lang="en"><head><title>T</title></head><body><main><h1>Hi</h1><div style="color:red">x</div></main></body></html>'
        report = HtmlValidator.validate(html)
        style_findings = [
            f for f in report.findings if "inline style size" in f.description.lower()
        ]
        assert len(style_findings) == 0


class TestImagesMissingLazy:
    def test_img_without_lazy_loading(self) -> None:
        html = '<html lang="en"><body><main><h1>Hi</h1><img src="photo.jpg" alt="Photo"></main></body></html>'
        report = HtmlValidator.validate(html)
        lazy_findings = [f for f in report.findings if 'loading="lazy"' in f.description]
        assert len(lazy_findings) == 1
        assert lazy_findings[0].category == CATEGORY_PERFORMANCE
        assert lazy_findings[0].severity == SEVERITY_MINOR

    def test_img_with_lazy_loading_ok(self) -> None:
        html = '<html lang="en"><body><main><h1>Hi</h1><img src="photo.jpg" alt="Photo" loading="lazy"></main></body></html>'
        report = HtmlValidator.validate(html)
        lazy_findings = [f for f in report.findings if 'loading="lazy"' in f.description]
        assert len(lazy_findings) == 0


# ============================================================================
# Serialisation
# ============================================================================


class TestValidationReportSerialization:
    def test_to_dict_structure(self) -> None:
        report = HtmlValidator.validate(
            '<html lang="en"><head><title>T</title></head><body><main><h1>H</h1></main></body></html>'
        )
        d = report.to_dict()
        assert "findings" in d
        assert "summary" in d
        assert isinstance(d["findings"], list)
        assert isinstance(d["summary"], dict)
        # Each finding dict should have the expected keys
        for finding in d["findings"]:
            assert set(finding.keys()) == {
                "category",
                "severity",
                "description",
                "element",
                "recommendation",
            }

    def test_empty_report_to_dict(self) -> None:
        report = HtmlValidator.validate(_VALID_HTML)
        d = report.to_dict()
        assert d["findings"] == []
        assert d["summary"] == {}

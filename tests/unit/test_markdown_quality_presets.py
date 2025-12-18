"""Tests for markdown quality presets.

This test ensures that quality presets control post-processing correctly:
- enhanced: applies all post-processing (fixes, sanitize, language detection)
- pure_crawl4ai: bypasses all post-processing, returns markdown unchanged
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from web_scraper.content import postprocess_markdown


def test_enhanced_preset_applies_all_postprocessing() -> None:
    """Assert that enhanced preset applies all post-processing steps in correct order."""
    call_order: list[str] = []

    def track_apply_fixes(*args: object, **kwargs: object) -> str:
        call_order.append("apply_fixes")
        return "fixed_markdown"

    def track_sanitize_markdown(*args: object, **kwargs: object) -> str:
        call_order.append("sanitize_markdown")
        return "sanitized_markdown"

    def track_detect_language(*args: object, **kwargs: object) -> dict[str, object]:
        call_order.append("detect_language")
        return {"content": "final_markdown", "language": "en", "confidence": 0.9, "action": "none"}

    # Patch the functions to track calls
    with patch("web_scraper.content.apply_fixes", side_effect=track_apply_fixes), patch(
        "web_scraper.content.sanitize_markdown", side_effect=track_sanitize_markdown
    ), patch("web_scraper.content.detect_language", side_effect=track_detect_language):
        result = postprocess_markdown(
            "raw_markdown",
            raw_html="<html>test</html>",
            config=MagicMock(),
            preset="enhanced",
        )

    # Assert correct order: fixes -> sanitize -> language detection
    assert call_order == ["apply_fixes", "sanitize_markdown", "detect_language"], (
        f"Expected order: ['apply_fixes', 'sanitize_markdown', 'detect_language'], "
        f"got: {call_order}"
    )

    # Verify return values
    assert result.markdown == "final_markdown"
    assert result.language["language"] == "en"


def test_pure_crawl4ai_preset_bypasses_all_postprocessing() -> None:
    """Assert that pure_crawl4ai preset bypasses all post-processing."""
    call_order: list[str] = []

    def track_apply_fixes(*args: object, **kwargs: object) -> str:
        call_order.append("apply_fixes")
        return "fixed_markdown"

    def track_sanitize_markdown(*args: object, **kwargs: object) -> str:
        call_order.append("sanitize_markdown")
        return "sanitized_markdown"

    def track_detect_language(*args: object, **kwargs: object) -> dict[str, object]:
        call_order.append("detect_language")
        return {"content": "final_markdown", "language": "en", "confidence": 0.9, "action": "none"}

    # Patch the functions to track calls
    with patch("web_scraper.content.apply_fixes", side_effect=track_apply_fixes), patch(
        "web_scraper.content.sanitize_markdown", side_effect=track_sanitize_markdown
    ), patch("web_scraper.content.detect_language", side_effect=track_detect_language):
        input_markdown = "raw_markdown_from_crawl4ai"
        result = postprocess_markdown(
            input_markdown,
            raw_html="<html>test</html>",
            config=MagicMock(),
            preset="pure_crawl4ai",
        )

    # Assert no post-processing functions were called
    assert call_order == [], (
        f"Expected no post-processing calls for pure_crawl4ai preset, got: {call_order}"
    )

    # Verify markdown is returned unchanged
    assert result.markdown == input_markdown
    assert result.language["language"] == "unknown"
    assert result.language["action"] == "none"


def test_default_preset_is_enhanced() -> None:
    """Assert that default preset (when not specified) is enhanced."""
    call_order: list[str] = []

    def track_sanitize_markdown(*args: object, **kwargs: object) -> str:
        call_order.append("sanitize_markdown")
        return "sanitized_markdown"

    def track_detect_language(*args: object, **kwargs: object) -> dict[str, object]:
        call_order.append("detect_language")
        return {"content": "final_markdown", "language": "en", "confidence": 0.9, "action": "none"}

    # Patch functions to track calls (no raw_html so fixes won't run)
    with patch("web_scraper.content.sanitize_markdown", side_effect=track_sanitize_markdown), patch(
        "web_scraper.content.detect_language", side_effect=track_detect_language
    ):
        result = postprocess_markdown("raw_markdown", raw_html=None, config=None)

    # Assert default behaviour (enhanced) applies post-processing
    assert "sanitize_markdown" in call_order, "Default preset should apply sanitization"
    assert "detect_language" in call_order, "Default preset should apply language detection"
    assert result.markdown == "final_markdown"

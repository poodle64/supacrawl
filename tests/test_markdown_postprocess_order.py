"""Test to lock the markdown post-processing pipeline order.

This test ensures that the post-processing pipeline applies steps in the
correct order: fixes -> sanitize -> language detection.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from web_scraper.content import postprocess_markdown


def test_postprocess_markdown_order() -> None:
    """Assert that post-processing functions are called in the correct order."""
    call_order: list[str] = []

    # Create mocks that track call order
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
        result_markdown, result_lang_info = postprocess_markdown(
            "raw_markdown", raw_html="<html>test</html>", config=MagicMock()
        )

    # Assert correct order: fixes -> sanitize -> language detection
    assert call_order == ["apply_fixes", "sanitize_markdown", "detect_language"], (
        f"Expected order: ['apply_fixes', 'sanitize_markdown', 'detect_language'], "
        f"got: {call_order}"
    )

    # Verify return values
    assert result_markdown == "final_markdown"
    assert result_lang_info["language"] == "en"


def test_postprocess_markdown_skips_fixes_when_no_html() -> None:
    """Assert that fixes are skipped when raw_html is not provided."""
    call_order: list[str] = []

    def track_sanitize_markdown(*args: object, **kwargs: object) -> str:
        call_order.append("sanitize_markdown")
        return "sanitized_markdown"

    def track_detect_language(*args: object, **kwargs: object) -> dict[str, object]:
        call_order.append("detect_language")
        return {"content": "final_markdown", "language": "en", "confidence": 0.9, "action": "none"}

    # Patch only sanitize and language detection (fixes should not be called)
    with patch("web_scraper.content.sanitize_markdown", side_effect=track_sanitize_markdown), patch(
        "web_scraper.content.detect_language", side_effect=track_detect_language
    ):
        result_markdown, _ = postprocess_markdown("raw_markdown", raw_html=None, config=None)

    # Assert fixes are skipped when no raw_html
    assert call_order == ["sanitize_markdown", "detect_language"], (
        f"Expected order: ['sanitize_markdown', 'detect_language'], got: {call_order}"
    )
    assert result_markdown == "final_markdown"

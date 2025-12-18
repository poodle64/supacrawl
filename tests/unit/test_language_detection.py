"""Tests for lightweight language detection and filtering."""

from __future__ import annotations

from web_scraper.content import detect_language


def test_detect_language_flags_english() -> None:
    """English-heavy text should be marked en with high confidence."""
    text = """
    # Title

    This is an English paragraph with the words and of the to in it.
    """
    result = detect_language(text)
    assert result["language"] == "en"
    assert result["confidence"] >= 0.2
    assert result["action"] == "none"


def test_detect_language_filters_non_english_paragraphs() -> None:
    """Mixed-language content should filter non-English paragraphs."""
    text = """
    # Título

    Este es un párrafo en español que no debe permanecer.

    This is the English paragraph that should stay in the result.
    """
    result = detect_language(text)
    assert result["language"] in {"mixed", "en"}
    assert "English paragraph" in result["content"]
    assert "español" not in result["content"]

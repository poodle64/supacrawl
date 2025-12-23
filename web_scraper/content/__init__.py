"""Content processing utilities for web scraping.

This package provides focused modules for:
- URL normalisation and canonical extraction
- Main content extraction using DOM scoring
- Markdown sanitisation
- Language detection
"""

from __future__ import annotations

from web_scraper.content.extraction import (
    extract_main_content,
    extract_main_content_html,
)
from web_scraper.content.language import detect_language
from web_scraper.content.markdown import sanitize_markdown
from web_scraper.content.postprocess import MarkdownPostprocessResult
from web_scraper.content.url import (
    extract_canonical_url,
    normalise_url,
    strip_tracking_params,
)

__all__ = [
    # URL utilities
    "normalise_url",
    "strip_tracking_params",
    "extract_canonical_url",
    # Content extraction
    "extract_main_content",
    "extract_main_content_html",
    # Markdown utilities
    "sanitize_markdown",
    # Language detection
    "detect_language",
    # Post-processing pipeline
    "postprocess_markdown",
    "MarkdownPostprocessResult",
]


def postprocess_markdown(
    markdown: str,
) -> MarkdownPostprocessResult:
    """
    Apply markdown post-processing pipeline in the correct order.

    Processing order:
    1. Sanitize markdown (remove nav blocks, link-heavy content)
    2. Language detection and filtering

    Args:
        markdown: Raw markdown content.

    Returns:
        MarkdownPostprocessResult with processed markdown and language info.
    """
    # Step 1: Sanitize markdown
    markdown = sanitize_markdown(markdown)

    # Step 2: Language detection
    lang_info = detect_language(markdown)
    # Type-narrow: detect_language returns dict[str, Any], but "content" is always str
    content_value = lang_info.get("content", markdown)
    markdown = content_value if isinstance(content_value, str) else markdown

    return MarkdownPostprocessResult(markdown=markdown, language=lang_info)

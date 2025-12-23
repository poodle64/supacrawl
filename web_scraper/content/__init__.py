"""Content processing utilities for web scraping.

This package provides focused modules for:
- URL normalisation and canonical extraction
- Main content extraction using DOM scoring
- Markdown sanitisation
"""

from __future__ import annotations

from web_scraper.content.extraction import (
    extract_main_content,
    extract_main_content_html,
)
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
    # Post-processing pipeline
    "postprocess_markdown",
    "MarkdownPostprocessResult",
]


def postprocess_markdown(
    markdown: str,
) -> MarkdownPostprocessResult:
    """
    Apply markdown post-processing pipeline.

    Processing:
    1. Sanitize markdown (remove nav blocks, link-heavy content)

    Args:
        markdown: Raw markdown content.

    Returns:
        MarkdownPostprocessResult with processed markdown.
    """
    # Sanitize markdown
    markdown = sanitize_markdown(markdown)

    return MarkdownPostprocessResult(markdown=markdown, language={})

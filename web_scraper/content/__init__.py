"""Content processing utilities for web scraping.

This package provides focused modules for:
- URL normalisation and canonical extraction
- Main content extraction using DOM scoring
- Markdown sanitisation
- Language detection
- Content statistics
"""

from __future__ import annotations

from typing import Any

from web_scraper.content.extraction import (
    extract_main_content,
    extract_main_content_html,
)
from web_scraper.content.language import detect_language
from web_scraper.content.markdown import sanitize_markdown
from web_scraper.content.postprocess import MarkdownPostprocessResult
from web_scraper.content.stats import content_stats
from web_scraper.content.fixes import apply_fixes
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
    # Statistics
    "content_stats",
    # Post-processing pipeline
    "postprocess_markdown",
    "MarkdownPostprocessResult",
]


def postprocess_markdown(
    markdown: str,
    raw_html: str | None = None,
    config: Any = None,
    correlation_id: str | None = None,
    preset: str = "enhanced",
) -> MarkdownPostprocessResult:
    """
    Apply markdown post-processing pipeline in the correct order.

    Processing order (enhanced preset):
    1. Apply markdown fix plugins (if raw_html provided)
    2. Sanitize markdown (remove nav blocks, link-heavy content)
    3. Language detection and filtering

    Presets:
    - "enhanced": Apply all post-processing steps (default, current behaviour)
    - "pure_crawl4ai": Return markdown unchanged (bypass all post-processing)

    Args:
        markdown: Raw markdown content from Crawl4AI.
        raw_html: Optional raw HTML (required for fixes).
        config: Optional SiteConfig (required for fixes).
        correlation_id: Optional correlation ID (required for fixes).
        preset: Quality preset ("enhanced" or "pure_crawl4ai").

    Returns:
        MarkdownPostprocessResult with processed markdown and language info.
    """
    # Pure Crawl4AI preset: return markdown unchanged
    if preset == "pure_crawl4ai":
        # Return minimal language info (no detection performed)
        lang_info = {
            "language": "unknown",
            "confidence": 0.0,
            "action": "none",
            "content": markdown,
        }
        return MarkdownPostprocessResult(markdown=markdown, language=lang_info)

    # Enhanced preset: apply all post-processing steps
    # Step 1: Apply markdown fix plugins (if raw_html exists)
    if raw_html and config:
        if correlation_id is None:
            from web_scraper.exceptions import generate_correlation_id

            correlation_id = generate_correlation_id()
        markdown = apply_fixes(
            str(markdown), raw_html, correlation_id=correlation_id, config=config
        )

    # Step 2: Sanitize markdown
    markdown = sanitize_markdown(markdown)

    # Step 3: Language detection
    lang_info = detect_language(markdown)
    markdown = lang_info.get("content", markdown)

    return MarkdownPostprocessResult(markdown=markdown, language=lang_info)


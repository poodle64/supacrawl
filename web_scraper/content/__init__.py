"""Content processing utilities for web scraping.

This package provides focused modules for:
- URL normalisation and canonical extraction
- Main content extraction using DOM scoring
- Markdown sanitisation
- Language detection
- Content statistics
"""

from web_scraper.content.extraction import (
    extract_main_content,
    extract_main_content_html,
)
from web_scraper.content.language import detect_language
from web_scraper.content.markdown import sanitize_markdown
from web_scraper.content.stats import content_stats
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
]


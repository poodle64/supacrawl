"""
Link Discovery Workaround for Crawl4AI Deep Crawl Issue.

This module provides a workaround where Crawl4AI's deep crawl strategies
discover links but don't follow them, even with correct URLPatternFilter
configuration.

WORKAROUND: This code can be removed when Crawl4AI deep crawl correctly
follows discovered links. Issue #1176 is closed but may not have fixed
this specific deep crawl behavior.
See: https://github.com/unclecode/crawl4ai/issues/1176

The workaround:
1. Extracts links from scraped pages
2. Filters them by include/exclude patterns
3. Adds matching links as new entrypoints
4. Iteratively crawls until no new links are found
"""

from __future__ import annotations

import fnmatch
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from web_scraper.models import Page, SiteConfig

LOGGER = logging.getLogger(__name__)


def extract_and_filter_links(
    pages: list[Page], config: SiteConfig, seen_urls: set[str]
) -> set[str]:
    """
    Extract links from pages and filter by include/exclude patterns.

    Workaround for Crawl4AI issue where deep crawl strategies discover links
    but don't follow them, even with correct filter configuration.

    Args:
        pages: List of scraped pages to extract links from.
        config: Site configuration with include/exclude patterns.
        seen_urls: Set of URLs already crawled (to avoid duplicates).

    Returns:
        Set of new URLs that match patterns and haven't been seen.
    """
    new_urls: set[str] = set()

    for page in pages:
        # Extract links from page metadata
        links = page.extra.get("links", {})
        internal_links = links.get("internal", []) if isinstance(links, dict) else []

        for link in internal_links:
            if not isinstance(link, dict):
                continue
            href = link.get("href", "")
            if not href or not isinstance(href, str):
                continue

            # Skip if already seen
            if href in seen_urls:
                continue

            # Check include patterns
            if config.include:
                matches_include = any(
                    fnmatch.fnmatch(href, pattern) for pattern in config.include
                )
                if not matches_include:
                    continue

            # Check exclude patterns
            if config.exclude:
                matches_exclude = any(
                    fnmatch.fnmatch(href, pattern) for pattern in config.exclude
                )
                if matches_exclude:
                    continue

            new_urls.add(href)

    return new_urls

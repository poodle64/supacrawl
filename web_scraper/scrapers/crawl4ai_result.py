"""Helpers to transform Crawl4AI results into Page models.

This module orchestrates the page extraction process using focused
modules from web_scraper.content for URL handling, content extraction,
markdown conversion, language detection, and statistics.
"""

from __future__ import annotations

from typing import Any

from web_scraper.content import (
    content_stats,
    normalise_url,
    postprocess_markdown,
)
from web_scraper.exceptions import generate_correlation_id
from web_scraper.models import Page, SiteConfig
from web_scraper.utils import content_hash, url_path


def extract_pages_from_result(
    result: Any,
    entrypoint: str,
    config: SiteConfig,
    provider_name: str,
) -> list[Page]:
    """
    Transform Crawl4AI results into Page models.

    Args:
        result: Crawl4AI result object or list of results.
        entrypoint: The URL that was crawled.
        config: Site configuration.
        provider_name: Name of the provider (e.g., "crawl4ai").

    Returns:
        List of Page objects with extracted and cleaned content.

    Raises:
        ValueError: If all crawl results failed or no pages with content.
    """
    # Crawl4AI 0.7.8+ with deep_crawl_strategy and stream=False returns a list
    if not isinstance(result, list):
        result = [result]

    if not result or all(getattr(r, "success", False) is False for r in result):
        raise ValueError("All crawl results failed or no results returned")

    pages: list[Page] = []
    for crawl_result in result:
        if getattr(crawl_result, "success", True) is False:
            continue

        page = _process_crawl_result(crawl_result, entrypoint, config, provider_name)
        if page is not None:
            pages.append(page)

    if not pages:
        raise ValueError("No pages with content returned from crawl")

    return pages


def _process_crawl_result(
    crawl_result: Any,
    entrypoint: str,
    config: SiteConfig,
    provider_name: str,
) -> Page | None:
    """
    Process a single crawl result into a Page.

    Args:
        crawl_result: Single Crawl4AI result object.
        entrypoint: The URL that was crawled.
        config: Site configuration.
        provider_name: Name of the provider.

    Returns:
        Page object or None if no content.
    """
    raw_html = (
        getattr(crawl_result, "cleaned_html", None)
        or getattr(crawl_result, "html", None)
        or None
    )
    url = (
        getattr(crawl_result, "url", None)
        or getattr(crawl_result, "source_url", None)
        or entrypoint
    )
    url = normalise_url(url, html=raw_html, entrypoint=entrypoint)

    # Extract markdown from Crawl4AI result
    markdown = _extract_markdown(crawl_result, config, raw_html)
    if not markdown or not markdown.strip():
        return None

    # Apply markdown post-processing pipeline (fixes, sanitize, language detection)
    correlation_id = generate_correlation_id()
    markdown, lang_info = postprocess_markdown(
        markdown, raw_html=raw_html, config=config, correlation_id=correlation_id
    )

    # Get title
    title = _extract_title(crawl_result, markdown)

    # Extract HTML content if available and requested
    content_html = _extract_html(crawl_result, config)

    # Build extra metadata
    extra = _build_extra_metadata(crawl_result, markdown, lang_info)

    return Page(
        site_id=config.id,
        url=url,
        title=title,
        path=url_path(url),
        content_markdown=markdown,
        content_html=content_html,
        content_hash=content_hash(markdown),
        provider=provider_name,
        extra=extra,
    )


def _extract_html(crawl_result: Any, config: SiteConfig) -> str | None:
    """
    Extract cleaned HTML content if HTML format is requested.

    Args:
        crawl_result: Crawl4AI result object.
        config: Site configuration.

    Returns:
        Cleaned HTML string or None.
    """
    # Only extract HTML if it's in the requested formats
    if "html" not in config.formats:
        return None

    # Prefer cleaned_html, fallback to raw html
    html = getattr(crawl_result, "cleaned_html", None)
    if not html:
        html = getattr(crawl_result, "html", None)

    if html and isinstance(html, str):
        return html.strip()

    return None


def _extract_markdown(
    crawl_result: Any, config: SiteConfig, raw_html: str | None
) -> str:
    """
    Extract markdown content from crawl result.

    Prefers fit_markdown when only_main_content is true,
    falls back to raw_markdown. Returns empty string if Crawl4AI
    provides no markdown.
    """
    markdown_obj = getattr(crawl_result, "markdown", None)
    raw_md = getattr(markdown_obj, "raw_markdown", None) if markdown_obj else None

    if markdown_obj and config.only_main_content:
        # Try fit_markdown first (cleaned content with filters applied)
        fit_md = getattr(markdown_obj, "fit_markdown", None)
        if fit_md and str(fit_md).strip():
            return str(fit_md)
        # Fallback to raw_markdown
        return str(raw_md) if raw_md else ""
    elif markdown_obj:
        # Use raw_markdown when only_main_content is false
        return str(raw_md) if raw_md else ""
    else:
        # No markdown from Crawl4AI - return empty string
        return ""


def _extract_title(crawl_result: Any, markdown: str) -> str:
    """Extract title from crawl result or markdown."""
    # Try result title
    if getattr(crawl_result, "title", None):
        return crawl_result.title

    # Try metadata
    if hasattr(crawl_result, "metadata"):
        metadata = crawl_result.metadata
        if isinstance(metadata, dict):
            for key in ("title", "og:title", "twitter:title"):
                if key in metadata and metadata[key]:
                    return metadata[key]

    # Fallback to first heading in markdown
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()

    return "Untitled"


def _build_extra_metadata(
    crawl_result: Any, markdown: str, lang_info: dict[str, Any]
) -> dict[str, Any]:
    """Build extra metadata dictionary for Page."""
    extra: dict[str, Any] = {}

    # Add metadata from crawl result
    if hasattr(crawl_result, "metadata"):
        metadata = crawl_result.metadata
        if isinstance(metadata, dict):
            extra["metadata"] = metadata

    # Add links
    if hasattr(crawl_result, "links"):
        links = crawl_result.links
        if isinstance(links, (dict, list)):
            extra["links"] = links

    # Add status code
    if hasattr(crawl_result, "status_code"):
        extra["status_code"] = crawl_result.status_code

    # Add content stats
    stats = content_stats(markdown)
    extra["content_stats"] = stats

    # Add language info
    extra["language"] = lang_info.get("language", "unknown")
    extra["language_confidence"] = lang_info.get("confidence", 0.0)
    extra["language_action"] = lang_info.get("action", "none")

    return extra

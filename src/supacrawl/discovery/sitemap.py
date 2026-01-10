"""Sitemap discovery and parsing utilities.

This module provides functionality to discover and parse XML sitemaps,
including auto-discovery from robots.txt and common locations.
"""

import gzip
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit
from xml.etree import ElementTree

import httpx

LOGGER = logging.getLogger(__name__)

# Common sitemap locations to check
COMMON_SITEMAP_PATHS = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemaps/sitemap.xml",
    "/sitemap/sitemap.xml",
]

# XML namespace for sitemaps
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


@dataclass
class SitemapURL:
    """
    Represents a URL entry from a sitemap.

    Attributes:
        loc: The URL location.
        lastmod: Last modification date (optional).
        changefreq: Change frequency hint (optional).
        priority: Priority hint 0.0-1.0 (optional).
    """

    loc: str
    lastmod: datetime | None = None
    changefreq: str | None = None
    priority: float | None = None


@dataclass
class SitemapConfig:
    """
    Configuration for sitemap-based discovery.

    Attributes:
        enabled: Whether to use sitemap discovery.
        urls: Explicit sitemap URLs to use (optional).
        only: If True, only crawl URLs from sitemaps (no link following).
        filter_by_lastmod: Only include URLs modified after this date.
    """

    enabled: bool = False
    urls: list[str] = field(default_factory=list)
    only: bool = False
    filter_by_lastmod: datetime | None = None


async def discover_sitemaps(base_url: str) -> list[str]:
    """
    Discover sitemap URLs for a given base URL.

    Checks robots.txt for Sitemap: directives, then falls back to
    common sitemap locations.

    Args:
        base_url: The base URL of the site (e.g., "https://example.com").

    Returns:
        List of discovered sitemap URLs.
    """
    parsed = urlsplit(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    sitemaps: list[str] = []

    # Check robots.txt first
    robots_url = f"{origin}/robots.txt"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(robots_url, follow_redirects=True)
            if response.status_code == 200:
                sitemaps.extend(_parse_robots_for_sitemaps(response.text))
                LOGGER.debug(
                    "Found %d sitemaps in robots.txt for %s",
                    len(sitemaps),
                    origin,
                )
    except Exception as e:
        LOGGER.debug("Could not fetch robots.txt from %s: %s", origin, e)

    # If no sitemaps found in robots.txt, check common locations
    if not sitemaps:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for path in COMMON_SITEMAP_PATHS:
                sitemap_url = f"{origin}{path}"
                try:
                    response = await client.head(sitemap_url, follow_redirects=True)
                    if response.status_code == 200:
                        sitemaps.append(sitemap_url)
                        LOGGER.debug("Found sitemap at %s", sitemap_url)
                        break  # Found one, stop checking
                except Exception:
                    continue

    return sitemaps


def _parse_robots_for_sitemaps(robots_content: str) -> list[str]:
    """
    Extract Sitemap URLs from robots.txt content.

    Args:
        robots_content: The content of robots.txt.

    Returns:
        List of sitemap URLs found.
    """
    sitemaps: list[str] = []
    for line in robots_content.splitlines():
        line = line.strip()
        if line.lower().startswith("sitemap:"):
            sitemap_url = line.split(":", 1)[1].strip()
            if sitemap_url:
                sitemaps.append(sitemap_url)
    return sitemaps


async def parse_sitemap(
    sitemap_url: str,
    max_urls: int = 10000,
    max_depth: int = 3,
) -> list[SitemapURL]:
    """
    Parse a sitemap XML, handling sitemap indexes recursively.

    Args:
        sitemap_url: URL of the sitemap to parse.
        max_urls: Maximum number of URLs to return (safety limit).
        max_depth: Maximum depth for nested sitemap indexes.

    Returns:
        List of SitemapURL objects extracted from the sitemap.
    """
    return await _parse_sitemap_recursive(sitemap_url, max_urls, max_depth, depth=0)


async def _parse_sitemap_recursive(
    sitemap_url: str,
    max_urls: int,
    max_depth: int,
    depth: int,
) -> list[SitemapURL]:
    """Recursively parse sitemaps, handling indexes."""
    if depth >= max_depth:
        LOGGER.warning("Max sitemap depth reached at %s", sitemap_url)
        return []

    urls: list[SitemapURL] = []

    try:
        content = await _fetch_sitemap_content(sitemap_url)
        if not content:
            return urls

        root = ElementTree.fromstring(content)
        tag_name = _strip_namespace(root.tag)

        if tag_name == "sitemapindex":
            # This is a sitemap index - parse nested sitemaps
            for sitemap_elem in root.findall("sm:sitemap", SITEMAP_NS):
                loc_elem = sitemap_elem.find("sm:loc", SITEMAP_NS)
                if loc_elem is not None and loc_elem.text:
                    nested_urls = await _parse_sitemap_recursive(
                        loc_elem.text.strip(),
                        max_urls - len(urls),
                        max_depth,
                        depth + 1,
                    )
                    urls.extend(nested_urls)
                    if len(urls) >= max_urls:
                        break
        elif tag_name == "urlset":
            # This is a regular sitemap - extract URLs
            for url_elem in root.findall("sm:url", SITEMAP_NS):
                if len(urls) >= max_urls:
                    break
                sitemap_url_obj = _parse_url_element(url_elem)
                if sitemap_url_obj:
                    urls.append(sitemap_url_obj)
        else:
            LOGGER.warning("Unknown sitemap root element: %s", tag_name)

    except Exception as e:
        LOGGER.error("Failed to parse sitemap %s: %s", sitemap_url, e)

    return urls


async def _fetch_sitemap_content(sitemap_url: str) -> bytes | None:
    """Fetch sitemap content, handling gzip compression."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(sitemap_url, follow_redirects=True)
            if response.status_code != 200:
                LOGGER.warning(
                    "Sitemap returned status %d: %s",
                    response.status_code,
                    sitemap_url,
                )
                return None

            content = response.content

            # Handle gzipped sitemaps
            if sitemap_url.endswith(".gz") or response.headers.get("content-encoding") == "gzip":
                try:
                    content = gzip.decompress(content)
                except gzip.BadGzipFile:
                    # Not actually gzipped, use as-is
                    pass

            return content

    except Exception as e:
        LOGGER.error("Failed to fetch sitemap %s: %s", sitemap_url, e)
        return None


def _parse_url_element(url_elem: ElementTree.Element) -> SitemapURL | None:
    """Parse a single <url> element into a SitemapURL."""
    loc_elem = url_elem.find("sm:loc", SITEMAP_NS)
    if loc_elem is None or not loc_elem.text:
        return None

    loc = loc_elem.text.strip()

    # Parse optional fields
    lastmod = None
    lastmod_elem = url_elem.find("sm:lastmod", SITEMAP_NS)
    if lastmod_elem is not None and lastmod_elem.text:
        lastmod = _parse_lastmod(lastmod_elem.text.strip())

    changefreq = None
    changefreq_elem = url_elem.find("sm:changefreq", SITEMAP_NS)
    if changefreq_elem is not None and changefreq_elem.text:
        changefreq = changefreq_elem.text.strip()

    priority = None
    priority_elem = url_elem.find("sm:priority", SITEMAP_NS)
    if priority_elem is not None and priority_elem.text:
        try:
            priority = float(priority_elem.text.strip())
        except ValueError:
            pass

    return SitemapURL(
        loc=loc,
        lastmod=lastmod,
        changefreq=changefreq,
        priority=priority,
    )


def _parse_lastmod(lastmod_str: str) -> datetime | None:
    """Parse lastmod date string in various formats."""
    formats = [
        "%Y-%m-%dT%H:%M:%S%z",  # Full ISO format with timezone
        "%Y-%m-%dT%H:%M:%SZ",  # ISO format with Z
        "%Y-%m-%dT%H:%M:%S",  # ISO format without timezone
        "%Y-%m-%d",  # Date only
    ]

    for fmt in formats:
        try:
            return datetime.strptime(lastmod_str, fmt)
        except ValueError:
            continue

    # Try parsing with regex for timezone offsets like +00:00
    try:
        # Handle ISO format with colon in timezone
        cleaned = re.sub(r"([+-]\d{2}):(\d{2})$", r"\1\2", lastmod_str)
        return datetime.strptime(cleaned, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        pass

    LOGGER.debug("Could not parse lastmod: %s", lastmod_str)
    return None


def _strip_namespace(tag: str) -> str:
    """Remove XML namespace from tag name."""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def filter_urls_by_lastmod(
    urls: list[SitemapURL],
    since: datetime,
) -> list[SitemapURL]:
    """
    Filter sitemap URLs to only those modified after a given date.

    Args:
        urls: List of SitemapURL objects.
        since: Only include URLs with lastmod after this date.

    Returns:
        Filtered list of SitemapURL objects.
    """
    return [url for url in urls if url.lastmod and url.lastmod >= since]


def filter_urls_by_patterns(
    urls: list[SitemapURL],
    include_patterns: list[str],
    exclude_patterns: list[str],
) -> list[SitemapURL]:
    """
    Filter sitemap URLs by include/exclude patterns.

    Args:
        urls: List of SitemapURL objects.
        include_patterns: URL patterns that must match (glob-style).
        exclude_patterns: URL patterns to exclude (glob-style).

    Returns:
        Filtered list of SitemapURL objects.
    """
    import fnmatch

    filtered: list[SitemapURL] = []
    for url in urls:
        loc = url.loc

        # Check include patterns
        if include_patterns:
            if not any(fnmatch.fnmatch(loc, p) for p in include_patterns):
                continue

        # Check exclude patterns
        if exclude_patterns:
            if any(fnmatch.fnmatch(loc, p) for p in exclude_patterns):
                continue

        filtered.append(url)

    return filtered

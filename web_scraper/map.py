"""URL mapping and discovery for deterministic site exploration.

This module provides functionality to discover and map all URLs that would
be crawled for a given site configuration, without actually crawling.
"""

from __future__ import annotations

import fnmatch
import logging
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from web_scraper.content.url import normalise_url
from web_scraper.discovery import (
    discover_sitemaps,
    fetch_robots,
    filter_urls_by_patterns,
    is_url_allowed,
    parse_sitemap,
)
from web_scraper.models import SiteConfig

LOGGER = logging.getLogger(__name__)


def normalise_url_for_map(url: str) -> str:
    """
    Normalise URL for map output (deduplication and sorting).
    
    Args:
        url: URL to normalise.
        
    Returns:
        Normalised URL string.
    """
    # Use existing normalise_url but without HTML/entrypoint context
    return normalise_url(url, html=None, entrypoint=None)


def _extract_domain(url: str) -> str:
    """Extract domain from URL."""
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _is_same_domain(url1: str, url2: str, include_subdomains: bool) -> bool:
    """
    Check if two URLs are on the same domain.
    
    Args:
        url1: First URL.
        url2: Second URL.
        include_subdomains: Whether to include subdomains.
        
    Returns:
        True if same domain.
    """
    domain1 = _extract_domain(url1)
    domain2 = _extract_domain(url2)
    
    if domain1 == domain2:
        return True
    
    if not include_subdomains:
        return False
    
    # Extract netloc (host) for subdomain comparison
    parsed1 = urlsplit(url1)
    parsed2 = urlsplit(url2)
    
    # Get base domain (last two parts: example.com)
    parts1 = parsed1.netloc.split(".")
    parts2 = parsed2.netloc.split(".")
    
    if len(parts1) < 2 or len(parts2) < 2:
        return False
    
    # Compare base domain (last two parts)
    base1 = ".".join(parts1[-2:])
    base2 = ".".join(parts2[-2:])
    
    return base1 == base2


def _check_include_exclude(url: str, config: SiteConfig) -> tuple[bool, str | None]:
    """
    Check if URL matches include/exclude patterns.
    
    Args:
        url: URL to check.
        config: Site configuration.
        
    Returns:
        Tuple of (included, excluded_reason).
        included: True if URL should be included.
        excluded_reason: None if included, or reason string if excluded.
    """
    # Check exclude patterns first
    if config.exclude:
        for pattern in config.exclude:
            if fnmatch.fnmatch(url, pattern):
                return False, "exclude_pattern"
    
    # Check include patterns
    if config.include:
        if not any(fnmatch.fnmatch(url, pattern) for pattern in config.include):
            return False, "not_in_include"
    
    return True, None


def _apply_filters(
    url: str,
    config: SiteConfig,
    robots_config: Any | None,
) -> tuple[bool, bool, str | None]:
    """
    Apply all filters (robots, include/exclude) to a URL.
    
    Args:
        url: URL to filter.
        config: Site configuration.
        robots_config: Parsed robots.txt config (or None).
        
    Returns:
        Tuple of (allowed, included, excluded_reason).
        allowed: True if robots.txt allows (if robots enabled).
        included: True if include/exclude patterns allow.
        excluded_reason: None if included, or reason string if excluded.
    """
    # Check robots.txt if enabled
    allowed = True
    if robots_config and config.robots.respect:
        allowed = is_url_allowed(url, robots_config)
        if not allowed:
            return False, False, "robots_disallow"
    
    # Check include/exclude patterns
    included, excluded_reason = _check_include_exclude(url, config)
    
    return allowed, included, excluded_reason


async def _extract_html_links(url: str, timeout: float = 10.0) -> list[str]:
    """
    Extract absolute URLs from HTML links (one hop only).
    
    Args:
        url: URL to fetch and extract links from.
        timeout: HTTP timeout in seconds.
        
    Returns:
        List of absolute URLs found in the page.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url)
            if response.status_code != 200:
                LOGGER.debug("Failed to fetch %s: status %d", url, response.status_code)
                return []
            
            soup = BeautifulSoup(response.text, "html.parser")
            links: list[str] = []
            
            # Extract all href attributes
            for tag in soup.find_all("a", href=True):
                href_attr = tag.get("href")
                if not href_attr:
                    continue
                
                # Convert to str (BeautifulSoup can return Sequence[str])
                href = str(href_attr)
                
                # Resolve relative URLs
                absolute_url = urljoin(url, href)
                
                # Normalise and add
                normalised = normalise_url_for_map(absolute_url)
                if normalised:
                    links.append(normalised)
            
            return links
    except Exception as e:
        LOGGER.debug("Failed to extract links from %s: %s", url, e)
        return []


async def map_site(
    config: SiteConfig,
    max_urls: int = 200,
    include_entrypoints_only: bool = False,
    use_sitemap: bool | None = None,
    use_robots: bool | None = None,
) -> list[dict[str, Any]]:
    """
    Map a site to discover all URLs that would be crawled.
    
    Args:
        config: Site configuration.
        max_urls: Maximum number of URLs to return.
        include_entrypoints_only: If True, only return entrypoints.
        use_sitemap: Override config.sitemap.enabled (None = use config).
        use_robots: Override config.robots.respect (None = use config).
        
    Returns:
        List of URL dictionaries with metadata.
    """
    # Determine sitemap and robots usage
    sitemap_enabled = use_sitemap if use_sitemap is not None else config.sitemap.enabled
    robots_enabled = use_robots if use_robots is not None else config.robots.respect
    
    # Fetch robots.txt if enabled
    robots_config = None
    if robots_enabled and config.entrypoints:
        base_url = config.entrypoints[0]
        try:
            robots_config = await fetch_robots(base_url)
        except Exception as e:
            LOGGER.debug("Failed to fetch robots.txt: %s", e)
            robots_config = None
    
    # Collect URLs from all sources
    url_entries: dict[str, dict[str, Any]] = {}
    
    # 1. Entrypoints (always included)
    for entrypoint in config.entrypoints:
        normalised = normalise_url_for_map(entrypoint)
        allowed, included, excluded_reason = _apply_filters(normalised, config, robots_config)
        
        url_entries[normalised] = {
            "url": normalised,
            "source": "entrypoint",
            "depth": 0,
            "allowed": allowed,
            "included": included,
            "excluded_reason": excluded_reason if not included else None,
        }
    
    # If entrypoints only, return now
    if include_entrypoints_only:
        return sorted(url_entries.values(), key=lambda x: x["url"])[:max_urls]
    
    # 2. Sitemap URLs (if enabled)
    if sitemap_enabled and config.entrypoints:
        base_url = config.entrypoints[0]
        sitemap_urls = await discover_sitemaps(base_url)
        
        if not sitemap_urls and config.sitemap.urls:
            sitemap_urls = config.sitemap.urls
        
        for sitemap_url in sitemap_urls:
            sitemap_entries = await parse_sitemap(sitemap_url, max_urls=max_urls * 2)
            
            # Filter by include/exclude patterns
            filtered = filter_urls_by_patterns(
                sitemap_entries, config.include, config.exclude
            )
            
            for sitemap_entry in filtered[:max_urls]:
                url = normalise_url_for_map(sitemap_entry.loc)
                if url in url_entries:
                    continue  # Already have this URL
                
                allowed, included, excluded_reason = _apply_filters(url, config, robots_config)
                
                url_entries[url] = {
                    "url": url,
                    "source": "sitemap",
                    "depth": 0,  # Sitemap URLs are at depth 0
                    "allowed": allowed,
                    "included": included,
                    "excluded_reason": excluded_reason if not included else None,
                }
    
    # 3. HTML link extraction (one hop from entrypoints)
    if not include_entrypoints_only and len(url_entries) < max_urls:
        for entrypoint in config.entrypoints:
            if len(url_entries) >= max_urls:
                break
            
            links = await _extract_html_links(entrypoint)
            
            for link in links:
                if len(url_entries) >= max_urls:
                    break
                
                # Check if same domain (respect include_subdomains)
                if not _is_same_domain(link, entrypoint, config.include_subdomains):
                    continue
                
                normalised = normalise_url_for_map(link)
                if normalised in url_entries:
                    continue  # Already have this URL
                
                allowed, included, excluded_reason = _apply_filters(normalised, config, robots_config)
                
                url_entries[normalised] = {
                    "url": normalised,
                    "source": "html_links",
                    "depth": 1,
                    "allowed": allowed,
                    "included": included,
                    "excluded_reason": excluded_reason if not included else None,
                }
    
    # Sort by URL and return
    sorted_entries = sorted(url_entries.values(), key=lambda x: x["url"])
    return sorted_entries[:max_urls]

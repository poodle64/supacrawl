"""Site discovery utilities for web scraping.

This package provides URL discovery from sitemaps and robots.txt.
"""

from web_scraper.discovery.robots import (
    RobotsConfig,
    RobotsEnforcement,
    fetch_robots,
    filter_urls_by_robots,
    is_url_allowed,
    parse_robots_txt,
)
from web_scraper.discovery.sitemap import (
    SitemapConfig,
    SitemapURL,
    discover_sitemaps,
    filter_urls_by_patterns,
    parse_sitemap,
)

__all__ = [
    # Robots
    "RobotsConfig",
    "RobotsEnforcement",
    "fetch_robots",
    "filter_urls_by_robots",
    "is_url_allowed",
    "parse_robots_txt",
    # Sitemap
    "SitemapConfig",
    "SitemapURL",
    "discover_sitemaps",
    "filter_urls_by_patterns",
    "parse_sitemap",
]


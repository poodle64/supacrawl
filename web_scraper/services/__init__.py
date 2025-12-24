"""Service layer for web-scraper.

This module provides the core services:
- BrowserManager: Playwright browser lifecycle management
- MarkdownConverter: HTML to Markdown conversion
- ScrapeService: Single URL scraping
- CrawlService: Multi-URL crawling with URL discovery
- MapService: URL discovery and mapping
- BatchService: Parallel batch scraping
"""

from web_scraper.services.batch import BatchService
from web_scraper.services.browser import BrowserManager
from web_scraper.services.converter import MarkdownConverter
from web_scraper.services.crawl import CrawlService
from web_scraper.services.map import MapService
from web_scraper.services.scrape import ScrapeService

__all__ = [
    "BatchService",
    "BrowserManager",
    "CrawlService",
    "MapService",
    "MarkdownConverter",
    "ScrapeService",
]

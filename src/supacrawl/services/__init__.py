"""Service layer for supacrawl.

This module provides the core services:
- BrowserManager: Playwright browser lifecycle management
- MarkdownConverter: HTML to Markdown conversion
- ScrapeService: Single URL scraping
- CrawlService: Multi-URL crawling with URL discovery
- MapService: URL discovery and mapping
- SearchService: Web search with optional scraping
- ExtractService: LLM-powered structured data extraction
- AgentService: Autonomous web agent for data gathering
"""

from supacrawl.services.agent import AgentService
from supacrawl.services.browser import BrowserManager
from supacrawl.services.converter import MarkdownConverter
from supacrawl.services.crawl import CrawlService
from supacrawl.services.extract import ExtractService
from supacrawl.services.map import MapService
from supacrawl.services.scrape import ScrapeService
from supacrawl.services.search import SearchService

__all__ = [
    "AgentService",
    "BrowserManager",
    "CrawlService",
    "ExtractService",
    "MapService",
    "MarkdownConverter",
    "ScrapeService",
    "SearchService",
]

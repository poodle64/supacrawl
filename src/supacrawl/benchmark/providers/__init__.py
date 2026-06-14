"""Scraper provider adapters for the benchmark.

The ``ScraperProvider`` Protocol defines the interface any provider must
satisfy. ``SupacrawlProvider`` implements it using supacrawl's own pipeline.
Additional providers (Firecrawl, Crawl4AI, etc.) follow the same Protocol.
"""

from supacrawl.benchmark.providers.base import ProviderOutput, ScraperProvider
from supacrawl.benchmark.providers.supacrawl import SupacrawlProvider

__all__ = ["ProviderOutput", "ScraperProvider", "SupacrawlProvider"]

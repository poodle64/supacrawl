"""Command-line interface for supacrawl.

This package provides the CLI commands for supacrawl. Commands are organized
into modules by functionality:

- scrape: Single URL scraping (scrape-url)
- crawl: Website crawling (crawl-url, crawl)
- map: URL discovery and mapping (map-url, map)
- agent: Search, extraction, and agent commands (search, llm-extract, agent)
- cache: Cache management subcommands (cache stats/clear/prune)
"""

from supacrawl.cli._common import app

# Import all command modules to register them with the app
# The order doesn't matter - Click handles command registration
from supacrawl.cli import agent  # noqa: F401
from supacrawl.cli import cache  # noqa: F401
from supacrawl.cli import crawl  # noqa: F401
from supacrawl.cli import map  # noqa: F401
from supacrawl.cli import scrape  # noqa: F401

__all__ = ["app"]

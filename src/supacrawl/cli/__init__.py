"""Command-line interface for supacrawl.

This package provides the CLI commands for supacrawl. Commands are organized
into modules by functionality:

- scrape: Single URL scraping
- crawl: Website crawling with URL discovery
- map: URL discovery and mapping
- agent: Search, extraction, and agent commands (search, llm-extract, agent)
- cache: Cache management subcommands (cache stats/clear/prune)
"""

# Import all command modules to register them with the app
# The order doesn't matter - Click handles command registration
from supacrawl.cli import (
    agent,  # noqa: F401
    cache,  # noqa: F401
    crawl,  # noqa: F401
    map,  # noqa: F401
    scrape,  # noqa: F401
)
from supacrawl.cli._common import app

__all__ = ["app"]

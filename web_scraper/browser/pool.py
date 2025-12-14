"""Browser pool for efficient browser reuse.

This module provides a pool of reusable browser instances to reduce
startup overhead and enable efficient concurrent crawling.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

from crawl4ai import AsyncWebCrawler, BrowserConfig  # type: ignore[import-untyped]

from web_scraper.scrapers.crawl4ai_config import build_browser_config

LOGGER = logging.getLogger(__name__)


@dataclass
class BrowserPoolConfig:
    """Configuration for browser pool.

    Attributes:
        pool_size: Number of browsers to maintain in pool.
        reuse_sessions: Whether to preserve cookies/cache across pages.
        restart_on_crash: Whether to restart crashed browsers.
        max_pages_per_browser: Maximum pages before recycling browser.
        warmup_url: URL to load on browser init (optional).
    """

    pool_size: int = 3
    reuse_sessions: bool = True
    restart_on_crash: bool = True
    max_pages_per_browser: int = 100
    warmup_url: str | None = None

    @classmethod
    def from_env(cls) -> BrowserPoolConfig:
        """Create config from environment variables."""
        return cls(
            pool_size=int(os.getenv("CRAWL4AI_BROWSER_POOL_SIZE", "3")),
            reuse_sessions=os.getenv("CRAWL4AI_BROWSER_REUSE_SESSIONS", "true").lower()
            == "true",
            restart_on_crash=os.getenv("CRAWL4AI_BROWSER_RESTART_ON_CRASH", "true").lower()
            == "true",
            max_pages_per_browser=int(
                os.getenv("CRAWL4AI_BROWSER_MAX_PAGES", "100")
            ),
        )


class PooledBrowser:
    """Wrapper around AsyncWebCrawler tracking usage stats."""

    def __init__(
        self,
        crawler: AsyncWebCrawler,
        browser_config: BrowserConfig,
        browser_id: int,
    ) -> None:
        self.crawler = crawler
        self.browser_config = browser_config
        self.browser_id = browser_id
        self.pages_crawled: int = 0
        self.is_healthy: bool = True
        self.last_error: str | None = None

    async def start(self) -> None:
        """Start the browser."""
        await self.crawler.__aenter__()
        LOGGER.debug("Browser %d started", self.browser_id)

    async def close(self) -> None:
        """Close the browser."""
        try:
            await self.crawler.__aexit__(None, None, None)
            LOGGER.debug("Browser %d closed", self.browser_id)
        except Exception as e:
            LOGGER.warning("Error closing browser %d: %s", self.browser_id, e)

    def mark_used(self) -> None:
        """Mark browser as having completed a page."""
        self.pages_crawled += 1

    def mark_error(self, error: str) -> None:
        """Mark browser as having encountered an error."""
        self.is_healthy = False
        self.last_error = error


class BrowserPool:
    """
    Pool of reusable browser instances.

    Usage:
        pool = BrowserPool(config)
        await pool.start()
        try:
            async with pool.acquire() as browser:
                result = await browser.crawler.arun(url, config)
        finally:
            await pool.close()
    """

    def __init__(
        self,
        config: BrowserPoolConfig | None = None,
        browser_config: BrowserConfig | None = None,
    ) -> None:
        """
        Initialise browser pool.

        Args:
            config: Pool configuration.
            browser_config: Browser configuration for each browser.
        """
        self._config = config or BrowserPoolConfig.from_env()
        self._browser_config = browser_config or build_browser_config()
        self._pool: asyncio.Queue[PooledBrowser] = asyncio.Queue()
        self._all_browsers: list[PooledBrowser] = []
        self._next_id: int = 0
        self._started: bool = False
        self._lock = asyncio.Lock()

        # Statistics
        self._total_acquisitions: int = 0
        self._total_releases: int = 0
        self._browsers_recycled: int = 0

    async def start(self) -> None:
        """Initialise browser pool with configured number of browsers."""
        if self._started:
            return

        LOGGER.info("Starting browser pool with %d browsers", self._config.pool_size)

        for _ in range(self._config.pool_size):
            browser = await self._create_browser()
            await self._pool.put(browser)

        self._started = True
        LOGGER.info("Browser pool started successfully")

    async def _create_browser(self) -> PooledBrowser:
        """Create a new pooled browser."""
        browser_id = self._next_id
        self._next_id += 1

        crawler = AsyncWebCrawler(config=self._browser_config)
        pooled = PooledBrowser(crawler, self._browser_config, browser_id)
        await pooled.start()
        self._all_browsers.append(pooled)

        return pooled

    async def _recycle_browser(self, browser: PooledBrowser) -> PooledBrowser:
        """Recycle a browser (close and create new)."""
        LOGGER.debug("Recycling browser %d", browser.browser_id)
        await browser.close()
        self._all_browsers.remove(browser)
        self._browsers_recycled += 1

        return await self._create_browser()

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[PooledBrowser]:
        """
        Acquire a browser from the pool.

        Yields:
            PooledBrowser instance ready for use.
        """
        if not self._started:
            await self.start()

        browser = await self._pool.get()
        self._total_acquisitions += 1

        try:
            yield browser
            browser.mark_used()
        except Exception as e:
            browser.mark_error(str(e))
            raise
        finally:
            # Check if browser needs recycling
            needs_recycle = (
                not browser.is_healthy
                or browser.pages_crawled >= self._config.max_pages_per_browser
            )

            if needs_recycle and self._config.restart_on_crash:
                async with self._lock:
                    browser = await self._recycle_browser(browser)

            await self._pool.put(browser)
            self._total_releases += 1

    async def close(self) -> None:
        """Close all browsers in pool."""
        if not self._started:
            return

        LOGGER.info("Closing browser pool")

        for browser in self._all_browsers:
            await browser.close()

        self._all_browsers.clear()
        self._started = False
        LOGGER.info(
            "Browser pool closed: %d acquisitions, %d recycled",
            self._total_acquisitions,
            self._browsers_recycled,
        )

    @property
    def stats(self) -> dict[str, int]:
        """Get pool statistics."""
        return {
            "pool_size": self._config.pool_size,
            "active_browsers": len(self._all_browsers),
            "available": self._pool.qsize(),
            "total_acquisitions": self._total_acquisitions,
            "total_releases": self._total_releases,
            "browsers_recycled": self._browsers_recycled,
        }

    @property
    def is_started(self) -> bool:
        """Check if pool is started."""
        return self._started


def create_browser_pool(
    pool_size: int | None = None,
    browser_config: BrowserConfig | None = None,
) -> BrowserPool:
    """
    Create a browser pool with optional overrides.

    Args:
        pool_size: Number of browsers in pool.
        browser_config: Browser configuration.

    Returns:
        Configured BrowserPool instance.
    """
    config = BrowserPoolConfig.from_env()
    if pool_size is not None:
        config.pool_size = pool_size

    return BrowserPool(config=config, browser_config=browser_config)


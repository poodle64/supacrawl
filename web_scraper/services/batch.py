"""Batch service for parallel URL scraping (Firecrawl-compatible)."""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

from web_scraper.models import BatchEvent, BatchItem, BatchResult
from web_scraper.services.browser import BrowserManager
from web_scraper.services.scrape import ScrapeService

LOGGER = logging.getLogger(__name__)


class BatchService:
    """Scrape multiple URLs concurrently (Firecrawl-compatible).

    Usage:
        service = BatchService()
        async for event in service.batch_scrape(urls, concurrency=5):
            if event.type == "item":
                print(f"Scraped: {event.url} - success: {event.item.success}")
    """

    def __init__(self):
        """Initialize batch service."""
        pass

    async def batch_scrape(
        self,
        urls: list[str],
        concurrency: int = 5,
        only_main_content: bool = True,
        timeout: int = 30000,
    ) -> AsyncGenerator[BatchEvent, None]:
        """Scrape multiple URLs concurrently.

        Args:
            urls: List of URLs to scrape
            concurrency: Maximum concurrent requests
            only_main_content: Extract main content only
            timeout: Per-page timeout in ms

        Yields:
            BatchEvent for each completed URL and progress updates
        """
        total = len(urls)
        completed = 0
        successful = 0
        failed = 0
        results: list[BatchItem] = []

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(concurrency)

        async def scrape_one(url: str) -> BatchItem:
            """Scrape a single URL with semaphore control."""
            async with semaphore:
                try:
                    async with BrowserManager(timeout_ms=timeout) as browser:
                        service = ScrapeService(browser=browser)
                        result = await service.scrape(
                            url=url,
                            only_main_content=only_main_content,
                        )

                        if result.success:
                            return BatchItem(
                                url=url,
                                success=True,
                                data=result.data,
                            )
                        else:
                            return BatchItem(
                                url=url,
                                success=False,
                                error=result.error,
                            )

                except Exception as e:
                    LOGGER.error(f"Batch scrape failed for {url}: {e}")
                    return BatchItem(
                        url=url,
                        success=False,
                        error=str(e),
                    )

        # Initial progress event
        yield BatchEvent(
            type="progress",
            completed=0,
            total=total,
        )

        # Create tasks for all URLs
        tasks = [asyncio.create_task(scrape_one(url)) for url in urls]

        # Process results as they complete
        for coro in asyncio.as_completed(tasks):
            item = await coro
            results.append(item)
            completed += 1

            if item.success:
                successful += 1
            else:
                failed += 1

            yield BatchEvent(
                type="item",
                url=item.url,
                item=item,
                completed=completed,
                total=total,
            )

            yield BatchEvent(
                type="progress",
                completed=completed,
                total=total,
            )

        # Final complete event
        yield BatchEvent(
            type="complete",
            completed=completed,
            total=total,
        )

    async def batch_scrape_to_result(
        self,
        urls: list[str],
        concurrency: int = 5,
        **kwargs,
    ) -> BatchResult:
        """Scrape multiple URLs and return final result.

        Args:
            urls: List of URLs to scrape
            concurrency: Maximum concurrent requests
            **kwargs: Additional arguments for scrape

        Returns:
            BatchResult with all scraped data
        """
        items: list[BatchItem] = []
        successful = 0
        failed = 0

        async for event in self.batch_scrape(urls, concurrency, **kwargs):
            if event.type == "item" and event.item:
                items.append(event.item)
                if event.item.success:
                    successful += 1
                else:
                    failed += 1

        return BatchResult(
            success=failed == 0,
            completed=len(items),
            total=len(urls),
            successful=successful,
            failed=failed,
            data=items,
        )

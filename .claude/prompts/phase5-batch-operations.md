# Phase 5: Batch Operations Implementation

## Context

You are implementing Phase 5 of the Firecrawl-parity rebuild for the web-scraper project. This phase creates the `batch-scrape` command for parallel URL processing.

**Branch:** `refactor/firecrawl-parity-v2`
**Issues:** #21, #22
**Depends On:** Phase 3 (ScrapeService)

## Prerequisites

Before starting, ensure Phase 3 components are available:
```bash
python -c "from web_scraper.scrape_service import ScrapeService; print('OK')"
```

**IMPORTANT:** Sonnet placed services in `web_scraper/` root (not `web_scraper/services/`):
- `web_scraper/map_service.py` - MapService class
- `web_scraper/scrape_service.py` - ScrapeService class
- `web_scraper/models.py` - All Firecrawl-compatible models

Follow this pattern for consistency.

## Phase 5 Goals

Build a `batch-scrape` command that:
1. Processes multiple URLs in parallel
2. Configurable concurrency limit
3. Per-URL error handling (failures don't stop batch)
4. Streams results as they complete
5. Outputs Firecrawl-compatible JSON format

## Task Breakdown by Issue

### Issue #21: BatchService with concurrent URL processing
Create `web_scraper/batch_service.py` for parallel scraping.

### Issue #22: Per-URL error handling
Handle errors gracefully without stopping the batch.

---

## Implementation Guide

### Data Models (add to `web_scraper/models.py`)

```python
"""Batch command data models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from web_scraper.models import ScrapeData


class BatchItem(BaseModel):
    """Result for a single URL in a batch."""
    url: str
    success: bool
    data: ScrapeData | None = None
    error: str | None = None


class BatchEvent(BaseModel):
    """Event emitted during batch processing."""
    type: Literal["progress", "item", "complete"]
    url: str | None = None
    item: BatchItem | None = None
    completed: int = 0
    total: int = 0


class BatchResult(BaseModel):
    """Final result of a batch operation."""
    success: bool
    completed: int
    total: int
    successful: int
    failed: int
    data: list[BatchItem]
```

### BatchService Interface (`web_scraper/batch_service.py`)

```python
"""Batch service for parallel URL scraping."""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

from web_scraper.browser import BrowserManager
from web_scraper.converter import MarkdownConverter
from web_scraper.models import BatchEvent, BatchItem, BatchResult, ScrapeData
from web_scraper.scrape_service import ScrapeService

LOGGER = logging.getLogger(__name__)


class BatchService:
    """Scrape multiple URLs concurrently.

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
```

### CLI Integration (`web_scraper/cli.py`)

Add a new `batch-scrape` command:

```python
@cli.command("batch-scrape")
@click.argument("urls_file", type=click.Path(exists=True))
@click.option("--concurrency", "-c", default=5, help="Maximum concurrent requests")
@click.option("--only-main-content/--no-only-main-content", default=True)
@click.option("--timeout", default=30000, help="Per-page timeout in ms")
@click.option("--output", "-o", type=click.Path(), help="Output directory for results")
def batch_scrape(urls_file: str, concurrency: int, only_main_content: bool, timeout: int, output: str | None):
    """Scrape multiple URLs from a file.

    URLs should be one per line in the input file.

    Examples:
        web-scraper batch-scrape urls.txt --concurrency 10
        web-scraper batch-scrape urls.txt --output results/
    """
    import asyncio
    import json
    from pathlib import Path
    from web_scraper.batch_service import BatchService

    # Read URLs from file
    with open(urls_file) as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    click.echo(f"Loaded {len(urls)} URLs from {urls_file}")

    async def run():
        service = BatchService()
        async for event in service.batch_scrape(
            urls=urls,
            concurrency=concurrency,
            only_main_content=only_main_content,
            timeout=timeout,
        ):
            if event.type == "item" and event.item:
                status = "✓" if event.item.success else "✗"
                click.echo(f"[{event.completed}/{event.total}] {status} {event.url}")

                # Save to output directory
                if output and event.item.success and event.item.data:
                    output_dir = Path(output)
                    output_dir.mkdir(parents=True, exist_ok=True)

                    from urllib.parse import urlparse
                    import hashlib

                    parsed = urlparse(event.url)
                    path = parsed.path.strip("/").replace("/", "_") or "index"
                    url_hash = hashlib.sha256(event.url.encode()).hexdigest()[:8]
                    filename = f"{path}_{url_hash}.md"

                    with open(output_dir / filename, "w") as f:
                        f.write("---\n")
                        f.write(f"source_url: {event.url}\n")
                        if event.item.data.metadata and event.item.data.metadata.title:
                            f.write(f"title: {event.item.data.metadata.title}\n")
                        f.write("---\n\n")
                        f.write(event.item.data.markdown or "")

            elif event.type == "complete":
                click.echo(f"\nComplete: {event.completed}/{event.total}")

    asyncio.run(run())
```

---

## Alternative: Batch from stdin

Also support piped URLs:

```python
@cli.command("batch-scrape")
@click.argument("urls_file", type=click.Path(exists=True), required=False)
@click.option("--stdin", is_flag=True, help="Read URLs from stdin")
# ... rest of options ...
def batch_scrape(urls_file: str | None, stdin: bool, ...):
    if stdin:
        import sys
        urls = [line.strip() for line in sys.stdin if line.strip()]
    elif urls_file:
        with open(urls_file) as f:
            urls = [line.strip() for line in f if line.strip()]
    else:
        raise click.UsageError("Either provide urls_file or use --stdin")
    # ... rest of implementation
```

---

## Unit Tests (`tests/unit/test_batch_service.py`)

```python
"""Tests for batch service."""

import pytest
from web_scraper.batch_service import BatchService
from web_scraper.models import BatchEvent, BatchItem, BatchResult


class TestBatchService:
    """Tests for BatchService."""

    @pytest.mark.asyncio
    async def test_batch_scrape_yields_events(self):
        """Test that batch_scrape yields events."""
        service = BatchService()
        urls = ["https://example.com", "https://example.org"]
        events = []

        async for event in service.batch_scrape(urls, concurrency=2):
            events.append(event)

        assert len(events) > 0
        assert any(e.type == "item" for e in events)
        assert any(e.type == "complete" for e in events)

    @pytest.mark.asyncio
    async def test_batch_scrape_respects_concurrency(self):
        """Test that batch_scrape respects concurrency limit."""
        service = BatchService()
        urls = ["https://example.com"] * 5
        events = []

        async for event in service.batch_scrape(urls, concurrency=2):
            events.append(event)

        # Should have completed all URLs
        complete_events = [e for e in events if e.type == "complete"]
        assert len(complete_events) == 1
        assert complete_events[0].completed == 5

    @pytest.mark.asyncio
    async def test_batch_scrape_handles_errors(self):
        """Test that batch_scrape handles errors gracefully."""
        service = BatchService()
        urls = ["https://example.com", "https://invalid-url-that-does-not-exist.example"]

        result = await service.batch_scrape_to_result(urls, concurrency=2)

        assert isinstance(result, BatchResult)
        assert result.completed == 2
        # At least one should succeed
        assert result.successful >= 1
        # Invalid URL should fail
        assert result.failed >= 1

    @pytest.mark.asyncio
    async def test_batch_scrape_to_result(self):
        """Test batch_scrape_to_result returns BatchResult."""
        service = BatchService()
        urls = ["https://example.com"]

        result = await service.batch_scrape_to_result(urls, concurrency=1)

        assert isinstance(result, BatchResult)
        assert result.completed == 1
        assert result.total == 1
        assert len(result.data) == 1
```

---

## Verification Checklist

After implementation, verify:

- [ ] `python -c "from web_scraper.batch_service import BatchService"` works
- [ ] `pytest tests/unit/test_batch_service.py -v` passes
- [ ] No `crawl4ai` imports in new files
- [ ] CLI command works with file: `echo "https://example.com" > /tmp/urls.txt && web-scraper batch-scrape /tmp/urls.txt`
- [ ] Concurrency actually limits parallel requests

---

## Commit Message

When complete, commit with:

```
feat: add batch-scrape command for parallel URL processing

- Add BatchService for concurrent URL scraping (#21)
- Implement per-URL error handling (#22)
- Support configurable concurrency limit
- Stream results as AsyncGenerator
- Save results to output directory
- Add unit tests

🤖 Generated with [Claude Code](https://claude.ai/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Completion

After Phase 5 is complete, the core Firecrawl CLI parity is achieved:

| Command | Status |
|---------|--------|
| `map` | ✅ Phase 2 |
| `scrape` | ✅ Phase 3 |
| `crawl` | ✅ Phase 4 |
| `batch-scrape` | ✅ Phase 5 |

### Optional Future Phases

- **Phase 6**: API Server (FastAPI with Firecrawl-compatible endpoints)
- **Phase 7**: Advanced features (extract, search, agent)

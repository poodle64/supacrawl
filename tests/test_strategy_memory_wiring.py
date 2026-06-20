"""Strategy-memory and telemetry wiring for crawl and batch (#130, #137).

The single-scrape entry points already thread per-domain strategy memory and the
telemetry sink into ``ScrapeService``. These tests pin the same wiring for the
multi-page paths — a crawl and a batch that own their browser must pass the
store and telemetry into the ``ScrapeService`` they build internally, so a crawl
learns each domain on the first page and seeds the rest, and per-page quality is
recorded. The browser, map, and scrape collaborators are mocked: this is a pure
wiring assertion, not a network test.
"""

from __future__ import annotations

from typing import AsyncGenerator, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from supacrawl.models import (
    MapEvent,
    MapResult,
    ScrapeData,
    ScrapeMetadata,
    ScrapeResult,
)
from supacrawl.services.batch import run_batch_scrape
from supacrawl.services.crawl import CrawlService
from supacrawl.services.strategy_memory import StrategyStore
from supacrawl.telemetry import MetricsSink

# Opaque sentinels: the tests assert these exact objects are threaded through to
# ScrapeService, not that they behave as a real store/sink (ScrapeService is
# mocked). cast keeps the type checker honest without a real instance.
_STORE = cast(StrategyStore, object())
_TELEMETRY = cast(MetricsSink, object())


def _async_cm(instance: MagicMock) -> MagicMock:
    """Make ``instance`` usable as an async context manager returning itself."""
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=None)
    return instance


@pytest.mark.unit
@pytest.mark.asyncio
async def test_crawl_owns_browser_threads_store_and_telemetry() -> None:
    """A crawl that owns its browser passes the store + telemetry to ScrapeService."""

    async def fake_map(**_: object) -> AsyncGenerator[MapEvent, None]:
        # No URLs discovered: the crawl finishes immediately after construction,
        # which is all this wiring test needs to exercise.
        yield MapEvent(type="complete", discovered=0, result=MapResult(success=True, links=[]))

    with (
        patch("supacrawl.services.crawl.BrowserManager") as mock_bm,
        patch("supacrawl.services.crawl.MapService") as mock_map_cls,
        patch("supacrawl.services.crawl.ScrapeService") as mock_scrape_cls,
    ):
        _async_cm(mock_bm.return_value)
        mock_map_cls.return_value.map = fake_map

        service = CrawlService(strategy_store=_STORE, telemetry=_TELEMETRY)
        async for _ in service.crawl(url="https://example.com", limit=10, formats=["markdown"]):
            pass

        mock_scrape_cls.assert_called_once()
        kwargs = mock_scrape_cls.call_args.kwargs
        assert kwargs["strategy_store"] is _STORE
        assert kwargs["telemetry"] is _TELEMETRY


@pytest.mark.unit
@pytest.mark.asyncio
async def test_crawl_without_store_passes_none() -> None:
    """Default crawl construction threads None through (memory off, identical to before)."""

    async def fake_map(**_: object) -> AsyncGenerator[MapEvent, None]:
        yield MapEvent(type="complete", discovered=0, result=MapResult(success=True, links=[]))

    with (
        patch("supacrawl.services.crawl.BrowserManager") as mock_bm,
        patch("supacrawl.services.crawl.MapService") as mock_map_cls,
        patch("supacrawl.services.crawl.ScrapeService") as mock_scrape_cls,
    ):
        _async_cm(mock_bm.return_value)
        mock_map_cls.return_value.map = fake_map

        service = CrawlService()
        async for _ in service.crawl(url="https://example.com", limit=10, formats=["markdown"]):
            pass

        kwargs = mock_scrape_cls.call_args.kwargs
        assert kwargs["strategy_store"] is None
        assert kwargs["telemetry"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_batch_owns_browser_threads_store_and_telemetry() -> None:
    """A batch that owns its browser passes the store + telemetry to ScrapeService."""
    with (
        patch("supacrawl.services.batch.BrowserManager") as mock_bm,
        patch("supacrawl.services.batch.ScrapeService") as mock_scrape_cls,
    ):
        _async_cm(mock_bm.return_value)
        mock_scrape_cls.return_value.scrape = AsyncMock(
            return_value=ScrapeResult(
                success=True,
                data=ScrapeData(markdown="ok", metadata=ScrapeMetadata(source_url="https://x")),
            )
        )

        await run_batch_scrape(
            ["https://x"],
            strategy_store=_STORE,
            telemetry=_TELEMETRY,
        )

        mock_scrape_cls.assert_called_once()
        kwargs = mock_scrape_cls.call_args.kwargs
        assert kwargs["strategy_store"] is _STORE
        assert kwargs["telemetry"] is _TELEMETRY

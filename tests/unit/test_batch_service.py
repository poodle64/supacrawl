"""Tests for batch service."""

from __future__ import annotations

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

    @pytest.mark.asyncio
    async def test_batch_scrape_item_structure(self):
        """Test that batch items have correct structure."""
        service = BatchService()
        urls = ["https://example.com"]
        items = []

        async for event in service.batch_scrape(urls, concurrency=1):
            if event.type == "item" and event.item:
                items.append(event.item)

        assert len(items) == 1
        item = items[0]
        assert isinstance(item, BatchItem)
        assert item.url == "https://example.com"
        assert isinstance(item.success, bool)

        if item.success:
            assert item.data is not None
            assert item.data.markdown is not None
            assert item.error is None
        else:
            assert item.data is None
            assert item.error is not None

    @pytest.mark.asyncio
    async def test_batch_scrape_progress_events(self):
        """Test that batch_scrape emits progress events."""
        service = BatchService()
        urls = ["https://example.com", "https://example.org"]
        progress_events = []

        async for event in service.batch_scrape(urls, concurrency=2):
            if event.type == "progress":
                progress_events.append(event)

        # Should have initial progress (0/2) + 2 intermediate progress + final is complete
        assert len(progress_events) >= 3
        # Check first progress event
        assert progress_events[0].completed == 0
        assert progress_events[0].total == 2

    @pytest.mark.asyncio
    async def test_batch_scrape_with_only_main_content(self):
        """Test batch_scrape with only_main_content option."""
        service = BatchService()
        urls = ["https://example.com"]

        result = await service.batch_scrape_to_result(
            urls, concurrency=1, only_main_content=True
        )

        assert result.successful == 1
        assert len(result.data) == 1
        assert result.data[0].data is not None

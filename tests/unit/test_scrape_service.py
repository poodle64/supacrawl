"""Tests for scrape service."""

from __future__ import annotations

import pytest

from web_scraper.models import ScrapeResult
from web_scraper.scrape_service import ScrapeService


class TestScrapeService:
    """Tests for ScrapeService."""

    @pytest.mark.asyncio
    async def test_scrape_returns_markdown(self):
        """Test that scrape returns markdown content."""
        service = ScrapeService()
        result = await service.scrape("https://example.com")
        assert isinstance(result, ScrapeResult)
        assert result.success
        assert result.data is not None
        assert result.data.markdown is not None
        assert len(result.data.markdown) > 0

    @pytest.mark.asyncio
    async def test_scrape_extracts_metadata(self):
        """Test that scrape extracts page metadata."""
        service = ScrapeService()
        result = await service.scrape("https://example.com")
        assert result.success
        assert result.data is not None
        assert result.data.metadata is not None
        assert result.data.metadata.title is not None
        assert result.data.metadata.source_url == "https://example.com"

    @pytest.mark.asyncio
    async def test_scrape_returns_html_when_requested(self):
        """Test that scrape returns HTML when requested."""
        service = ScrapeService()
        result = await service.scrape("https://example.com", formats=["html"])
        assert result.success
        assert result.data is not None
        assert result.data.html is not None

    @pytest.mark.asyncio
    async def test_scrape_returns_raw_html_when_requested(self):
        """Test that scrape returns raw HTML when requested."""
        service = ScrapeService()
        result = await service.scrape("https://example.com", formats=["rawHtml"])
        assert result.success
        assert result.data is not None
        assert result.data.raw_html is not None

    @pytest.mark.asyncio
    async def test_scrape_returns_links_when_requested(self):
        """Test that scrape returns links when requested."""
        service = ScrapeService()
        result = await service.scrape("https://example.com", formats=["links"])
        assert result.success
        assert result.data is not None
        assert result.data.links is not None
        assert isinstance(result.data.links, list)

    @pytest.mark.asyncio
    async def test_scrape_returns_multiple_formats(self):
        """Test that scrape can return multiple formats."""
        service = ScrapeService()
        result = await service.scrape(
            "https://example.com", formats=["markdown", "html", "links"]
        )
        assert result.success
        assert result.data is not None
        assert result.data.markdown is not None
        assert result.data.html is not None
        assert result.data.links is not None

    @pytest.mark.asyncio
    async def test_scrape_handles_error(self):
        """Test that scrape handles errors gracefully."""
        service = ScrapeService()
        result = await service.scrape("https://invalid-url-that-does-not-exist.example")
        assert not result.success
        assert result.error is not None

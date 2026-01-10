"""Tests for scrape service."""

import pytest

from supacrawl.models import ScrapeResult
from supacrawl.services.scrape import ScrapeService


@pytest.mark.e2e
class TestScrapeService:
    """Tests for ScrapeService (E2E - require browser/network)."""

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
        result = await service.scrape("https://example.com", formats=["markdown", "html", "links"])
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

    @pytest.mark.asyncio
    async def test_scrape_returns_json_with_prompt(self):
        """Test that scrape returns JSON data when json format requested with prompt."""
        service = ScrapeService()
        result = await service.scrape(
            "https://example.com",
            formats=["json"],
            json_prompt="Extract the page title and domain name",
        )
        assert result.success
        assert result.data is not None
        # JSON extraction may fail if Ollama is not running, but should not crash
        # We just check the structure is correct
        if result.data.llm_extraction is not None:
            assert isinstance(result.data.llm_extraction, dict)

    @pytest.mark.asyncio
    async def test_scrape_returns_json_with_schema(self):
        """Test that scrape returns JSON data when json format requested with schema."""
        schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "domain": {"type": "string"},
            },
            "required": ["title", "domain"],
        }
        service = ScrapeService()
        result = await service.scrape(
            "https://example.com",
            formats=["json"],
            json_schema=schema,
        )
        assert result.success
        assert result.data is not None
        # JSON extraction may fail if Ollama is not running, but should not crash
        # We just check the structure is correct
        if result.data.llm_extraction is not None:
            assert isinstance(result.data.llm_extraction, dict)

    @pytest.mark.asyncio
    async def test_scrape_returns_multiple_formats_including_json(self):
        """Test that scrape can return multiple formats including JSON."""
        service = ScrapeService()
        result = await service.scrape(
            "https://example.com",
            formats=["markdown", "json"],
            json_prompt="Extract page info",
        )
        assert result.success
        assert result.data is not None
        assert result.data.markdown is not None
        # JSON may be None if extraction fails, but shouldn't crash
        assert result.data.llm_extraction is None or isinstance(result.data.llm_extraction, dict)

    @pytest.mark.asyncio
    async def test_scrape_returns_images_when_requested(self):
        """Test that scrape returns images when requested."""
        service = ScrapeService()
        result = await service.scrape("https://example.com", formats=["images"])
        assert result.success
        assert result.data is not None
        assert result.data.images is not None
        assert isinstance(result.data.images, list)

    @pytest.mark.asyncio
    async def test_scrape_returns_images_with_other_formats(self):
        """Test that scrape can return images alongside other formats."""
        service = ScrapeService()
        result = await service.scrape("https://example.com", formats=["markdown", "images"])
        assert result.success
        assert result.data is not None
        assert result.data.markdown is not None
        assert result.data.images is not None
        assert isinstance(result.data.images, list)

    @pytest.mark.asyncio
    async def test_scrape_returns_branding_when_requested(self):
        """Test that scrape returns branding information when requested."""
        service = ScrapeService()
        result = await service.scrape("https://example.com", formats=["branding"])
        assert result.success
        assert result.data is not None
        assert result.data.branding is not None
        # Branding should have at least color_scheme
        assert result.data.branding.color_scheme is not None

    @pytest.mark.asyncio
    async def test_scrape_returns_summary_when_requested(self):
        """Test that scrape returns LLM-generated summary when requested."""
        service = ScrapeService()
        result = await service.scrape("https://example.com", formats=["summary"])
        assert result.success
        assert result.data is not None
        # Summary may be None if Ollama is not running, but should not crash
        if result.data.summary is not None:
            assert isinstance(result.data.summary, str)
            assert len(result.data.summary) <= 500  # Max 500 chars per spec

    @pytest.mark.asyncio
    async def test_scrape_returns_summary_with_other_formats(self):
        """Test that scrape can return summary alongside other formats."""
        service = ScrapeService()
        result = await service.scrape("https://example.com", formats=["markdown", "summary"])
        assert result.success
        assert result.data is not None
        assert result.data.markdown is not None
        # Summary may be None if Ollama is not running
        if result.data.summary is not None:
            assert isinstance(result.data.summary, str)

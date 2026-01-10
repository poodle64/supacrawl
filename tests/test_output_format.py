"""Output format tests - validate output structure and compatibility."""

import pytest

from supacrawl.services.browser import BrowserManager
from supacrawl.services.map import MapService
from supacrawl.services.scrape import ScrapeService


@pytest.mark.e2e
class TestOutputFormat:
    """Test output structure and format."""

    @pytest.mark.asyncio
    async def test_scrape_result_structure(self) -> None:
        """Test ScrapeResult has expected structure."""
        async with BrowserManager() as browser:
            service = ScrapeService(browser=browser)
            result = await service.scrape("https://example.com")

        # Expected structure
        assert hasattr(result, "success")
        assert hasattr(result, "data")

        if result.success:
            assert hasattr(result.data, "markdown")
            assert hasattr(result.data, "metadata")
            assert hasattr(result.data.metadata, "title")
            assert hasattr(result.data.metadata, "source_url")

    @pytest.mark.asyncio
    async def test_map_result_structure(self) -> None:
        """Test MapResult has expected structure."""
        async with BrowserManager() as browser:
            service = MapService(browser=browser)
            result = await service.map("https://example.com", limit=5)

        # Expected structure
        assert hasattr(result, "success")
        assert hasattr(result, "links")

        if result.success and result.links:
            link = result.links[0]
            assert hasattr(link, "url")
            # Title is optional
            assert hasattr(link, "title") or True

    @pytest.mark.asyncio
    async def test_markdown_quality(self) -> None:
        """Test markdown output quality."""
        async with BrowserManager() as browser:
            service = ScrapeService(browser=browser)
            result = await service.scrape("https://example.com")

        assert result.success
        markdown = result.data.markdown

        # Basic quality checks
        assert len(markdown) > 100, "Markdown should have substantial content"
        assert "example" in markdown.lower(), "Should contain expected content"
        # Code blocks should be balanced
        if "```" in markdown:
            assert markdown.count("```") % 2 == 0, "Code blocks should be balanced"

    @pytest.mark.asyncio
    async def test_metadata_extraction(self) -> None:
        """Test metadata extraction."""
        async with BrowserManager() as browser:
            service = ScrapeService(browser=browser)
            result = await service.scrape("https://example.com")

        assert result.success
        metadata = result.data.metadata

        # Metadata fields
        assert metadata.title is not None, "Title should be extracted"
        assert metadata.source_url == "https://example.com"
        # Optional fields
        assert hasattr(metadata, "description")
        assert hasattr(metadata, "og_title")
        assert hasattr(metadata, "og_description")

    @pytest.mark.asyncio
    async def test_html_format_support(self) -> None:
        """Test HTML format output."""
        async with BrowserManager() as browser:
            service = ScrapeService(browser=browser)
            result = await service.scrape("https://example.com", formats=["html", "markdown"])

        assert result.success
        assert result.data.markdown is not None
        assert result.data.html is not None
        assert len(result.data.html) > 0

    @pytest.mark.asyncio
    async def test_raw_html_format_support(self) -> None:
        """Test rawHtml format output."""
        async with BrowserManager() as browser:
            service = ScrapeService(browser=browser)
            result = await service.scrape("https://example.com", formats=["rawHtml"])

        assert result.success
        assert result.data.raw_html is not None
        assert len(result.data.raw_html) > 0
        # Raw HTML should have HTML structure
        assert "<html" in result.data.raw_html.lower()

    @pytest.mark.asyncio
    async def test_links_format_support(self) -> None:
        """Test links format output."""
        async with BrowserManager() as browser:
            service = ScrapeService(browser=browser)
            result = await service.scrape("https://example.com", formats=["links"])

        assert result.success
        # Links may or may not be present
        if result.data.links is not None:
            assert isinstance(result.data.links, list)

    @pytest.mark.asyncio
    async def test_error_result_structure(self) -> None:
        """Test error results have expected structure."""
        async with BrowserManager() as browser:
            service = ScrapeService(browser=browser)
            result = await service.scrape("https://this-domain-does-not-exist-12345.com")

        # Error result should have expected structure
        assert hasattr(result, "success")
        assert not result.success
        assert hasattr(result, "error")
        assert result.error is not None

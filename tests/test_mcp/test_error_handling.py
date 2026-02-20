"""Tests for Supacrawl MCP error handling."""

from unittest.mock import AsyncMock

import pytest

from supacrawl.mcp.exceptions import SupacrawlValidationError


class TestValidationErrors:
    """Test validation error handling across tools."""

    @pytest.mark.asyncio
    async def test_search_rejects_empty_query(self, mock_api_client):
        """Search should reject empty query with clear error."""
        from supacrawl.mcp.tools.search import supacrawl_search

        with pytest.raises(SupacrawlValidationError) as exc_info:
            await supacrawl_search(
                api_client=mock_api_client,
                query="",
            )

        assert "query" in str(exc_info.value).lower()
        assert exc_info.value.field == "query"

    @pytest.mark.asyncio
    async def test_search_rejects_none_query(self, mock_api_client):
        """Search should reject None query with clear error."""
        from supacrawl.mcp.tools.search import supacrawl_search

        with pytest.raises(SupacrawlValidationError) as exc_info:
            await supacrawl_search(
                api_client=mock_api_client,
                query=None,
            )

        assert "query" in str(exc_info.value).lower()
        assert "required" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_scrape_rejects_invalid_url(self, mock_api_client):
        """Scrape should reject invalid URLs."""
        from supacrawl.mcp.tools.scrape import supacrawl_scrape

        with pytest.raises(SupacrawlValidationError) as exc_info:
            await supacrawl_scrape(
                api_client=mock_api_client,
                url="not-a-valid-url",
            )

        assert "url" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_scrape_rejects_empty_url(self, mock_api_client):
        """Scrape should reject empty URL."""
        from supacrawl.mcp.tools.scrape import supacrawl_scrape

        with pytest.raises(SupacrawlValidationError) as exc_info:
            await supacrawl_scrape(
                api_client=mock_api_client,
                url="",
            )

        assert "url" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_extract_rejects_empty_urls(self, mock_api_client):
        """Extract should reject empty URL list."""
        from supacrawl.mcp.tools.extract import supacrawl_extract

        with pytest.raises(SupacrawlValidationError) as exc_info:
            await supacrawl_extract(
                api_client=mock_api_client,
                urls=[],
                prompt="Extract data",
            )

        assert "urls" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_extract_rejects_too_many_urls(self, mock_api_client):
        """Extract should reject more than 10 URLs."""
        from supacrawl.mcp.tools.extract import supacrawl_extract

        urls = [f"https://example.com/{i}" for i in range(15)]

        with pytest.raises(SupacrawlValidationError) as exc_info:
            await supacrawl_extract(
                api_client=mock_api_client,
                urls=urls,
                prompt="Extract data",
            )

        assert "urls" in str(exc_info.value).lower()
        assert "10" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_map_rejects_invalid_url(self, mock_api_client):
        """Map should reject invalid URL."""
        from supacrawl.mcp.tools.map import supacrawl_map

        with pytest.raises(SupacrawlValidationError) as exc_info:
            await supacrawl_map(
                api_client=mock_api_client,
                url="not-valid",
            )

        assert "url" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_crawl_rejects_invalid_url(self, mock_api_client):
        """Crawl should reject invalid URL."""
        from supacrawl.mcp.tools.crawl import supacrawl_crawl

        with pytest.raises(SupacrawlValidationError) as exc_info:
            await supacrawl_crawl(
                api_client=mock_api_client,
                url="invalid",
            )

        assert "url" in str(exc_info.value).lower()


class TestServiceErrors:
    """Test error handling when services fail."""

    @pytest.mark.asyncio
    async def test_scrape_handles_service_exception(self, mock_api_client):
        """Scrape should wrap service exceptions."""
        from supacrawl.mcp.exceptions import SupacrawlMCPError
        from supacrawl.mcp.tools.scrape import supacrawl_scrape

        mock_api_client.scrape_service.scrape = AsyncMock(side_effect=Exception("Connection timeout"))

        with pytest.raises(SupacrawlMCPError):
            await supacrawl_scrape(
                api_client=mock_api_client,
                url="https://example.com",
            )

    @pytest.mark.asyncio
    async def test_search_handles_service_exception(self, mock_api_client):
        """Search should wrap service exceptions."""
        from supacrawl.mcp.exceptions import SupacrawlMCPError
        from supacrawl.mcp.tools.search import supacrawl_search

        mock_api_client.search_service.search = AsyncMock(side_effect=Exception("Rate limited"))

        with pytest.raises(SupacrawlMCPError):
            await supacrawl_search(
                api_client=mock_api_client,
                query="test query",
            )


class TestExceptionAttributes:
    """Test that exceptions have proper attributes for debugging."""

    @pytest.mark.asyncio
    async def test_validation_error_has_field(self, mock_api_client):
        """Validation errors should include field name."""
        from supacrawl.mcp.tools.search import supacrawl_search

        with pytest.raises(SupacrawlValidationError) as exc_info:
            await supacrawl_search(
                api_client=mock_api_client,
                query=None,
            )

        assert exc_info.value.field == "query"

    @pytest.mark.asyncio
    async def test_validation_error_has_value(self, mock_api_client):
        """Validation errors should include invalid value."""
        from supacrawl.mcp.tools.search import supacrawl_search

        with pytest.raises(SupacrawlValidationError) as exc_info:
            await supacrawl_search(
                api_client=mock_api_client,
                query=None,
            )

        assert exc_info.value.value is None

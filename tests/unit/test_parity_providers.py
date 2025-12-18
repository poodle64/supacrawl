"""Unit tests for Firecrawl provider abstraction."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.parity.providers import (
    APIFirecrawlProvider,
    get_firecrawl_provider,
)


class TestAPIFirecrawlProvider:
    """Tests for API Firecrawl provider."""

    def test_is_available_without_api_key(self) -> None:
        """Test that API provider reports unavailable without API key."""
        with patch.dict(os.environ, {}, clear=True):
            provider = APIFirecrawlProvider()
            assert provider.is_available() is False

    def test_is_available_with_api_key(self) -> None:
        """Test that API provider reports available with API key."""
        with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test-key"}):
            provider = APIFirecrawlProvider()
            assert provider.is_available() is True

    @pytest.mark.asyncio
    async def test_scrape_markdown_without_api_key(self) -> None:
        """Test that API provider returns None without API key."""
        with patch.dict(os.environ, {}, clear=True):
            provider = APIFirecrawlProvider()
            result = await provider.scrape_markdown("https://example.com")
            assert result is None

    @pytest.mark.asyncio
    async def test_scrape_markdown_success(self) -> None:
        """Test successful API scrape."""
        with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test-key"}):
            provider = APIFirecrawlProvider()
            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {"markdown": "# Test Content"}}
            mock_response.raise_for_status = MagicMock()

            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    return_value=mock_response
                )
                result = await provider.scrape_markdown("https://example.com")
                assert result == "# Test Content"

    @pytest.mark.asyncio
    async def test_scrape_markdown_api_error(self) -> None:
        """Test API error handling."""
        with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test-key"}):
            provider = APIFirecrawlProvider()
            import httpx

            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    side_effect=httpx.HTTPError("API Error")
                )
                result = await provider.scrape_markdown("https://example.com")
                assert result is None


class TestProviderSelection:
    """Tests for provider selection logic."""

    def test_get_firecrawl_provider_uses_api_when_available(self) -> None:
        """Test that API provider is used when API key is set."""
        with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test-key"}):
            provider = get_firecrawl_provider()
            assert isinstance(provider, APIFirecrawlProvider)

    def test_get_firecrawl_provider_returns_none_when_none_available(self) -> None:
        """Test that None is returned when no provider available."""
        with patch.dict(os.environ, {}, clear=True):
            provider = get_firecrawl_provider()
            assert provider is None


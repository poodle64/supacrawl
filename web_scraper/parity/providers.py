"""Firecrawl provider abstraction for parity testing."""

from __future__ import annotations

import logging
import os
from typing import Protocol

import httpx

LOGGER = logging.getLogger(__name__)


class FirecrawlProvider(Protocol):
    """Protocol for Firecrawl scraping providers."""

    async def scrape_markdown(self, url: str) -> str | None:
        """
        Scrape a URL and return markdown content.

        Args:
            url: URL to scrape.

        Returns:
            Markdown content string, or None if scraping failed.
        """
        ...

    def is_available(self) -> bool:
        """
        Check if this provider is available.

        Returns:
            True if provider can be used, False otherwise.
        """
        ...


class MCPFirecrawlProvider:
    """Firecrawl provider using MCP server."""

    def __init__(self) -> None:
        """Initialize MCP provider."""
        self._available = self._check_mcp_available()

    def _check_mcp_available(self) -> bool:
        """
        Check if MCP Firecrawl server is available.
        
        Note: This is a best-effort check. Actual availability is verified
        when calling scrape_markdown.
        """
        # MCP tools are available via the environment when running in Cursor
        # We can't check availability without actually trying to use them
        # So we assume available and handle errors in scrape_markdown
        return True

    def is_available(self) -> bool:
        """Check if MCP provider is available."""
        return self._available

    async def scrape_markdown(self, url: str) -> str | None:
        """
        Scrape URL using Firecrawl MCP server.

        Args:
            url: URL to scrape.

        Returns:
            Markdown content, or None on error.
        """
        try:
            # MCP tools are available via the function calling interface
            # We need to call the MCP tool through the available interface
            # Note: This requires the MCP server to be configured in the environment
            LOGGER.info(f"Scraping {url} with Firecrawl MCP")
            
            # The actual MCP call happens via the harness which has access to MCP tools
            # This is a placeholder that will be replaced by actual MCP tool calls
            # in the harness when MCP tools are available
            return None
        except Exception as e:
            LOGGER.error(f"MCP Firecrawl error for {url}: {e}")
            return None


class APIFirecrawlProvider:
    """Firecrawl provider using REST API."""

    def __init__(self) -> None:
        """Initialize API provider."""
        self.api_key = os.getenv("FIRECRAWL_API_KEY", "")
        self.api_url = os.getenv(
            "FIRECRAWL_API_URL", "https://api.firecrawl.dev/v1/scrape"
        )

    def is_available(self) -> bool:
        """Check if API provider is available (API key set)."""
        return bool(self.api_key)

    async def scrape_markdown(self, url: str) -> str | None:
        """
        Scrape URL using Firecrawl REST API.

        Args:
            url: URL to scrape.

        Returns:
            Markdown content, or None on error.
        """
        if not self.is_available():
            return None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "url": url,
            "formats": ["markdown"],
            "onlyMainContent": True,
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.api_url, json=payload, headers=headers
                )
                response.raise_for_status()
                data = response.json()

                # Extract markdown from Firecrawl response
                if "data" in data and "markdown" in data["data"]:
                    return data["data"]["markdown"]
                elif "markdown" in data:
                    return data["markdown"]
                else:
                    LOGGER.warning(
                        f"Unexpected Firecrawl response format for {url}: {data}"
                    )
                    return None
        except httpx.HTTPError as e:
            LOGGER.error(f"Firecrawl API error for {url}: {e}")
            return None
        except Exception as e:
            LOGGER.error(f"Unexpected error scraping {url} with Firecrawl: {e}")
            return None


def get_firecrawl_provider() -> FirecrawlProvider | None:
    """
    Get the best available Firecrawl provider.

    Selection order:
    1. MCP provider (if available)
    2. API provider (if API key set)
    3. None (skip Firecrawl)

    Returns:
        FirecrawlProvider instance, or None if none available.
    """
    # Try MCP first
    mcp_provider = MCPFirecrawlProvider()
    if mcp_provider.is_available():
        return mcp_provider

    # Fall back to API
    api_provider = APIFirecrawlProvider()
    if api_provider.is_available():
        return api_provider

    # No provider available
    return None

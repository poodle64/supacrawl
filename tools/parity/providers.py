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
    Get the available Firecrawl provider.

    Uses API provider if FIRECRAWL_API_KEY is set, otherwise returns None.

    Returns:
        FirecrawlProvider instance, or None if API key not set.
    """
    api_provider = APIFirecrawlProvider()
    if api_provider.is_available():
        return api_provider

    # No provider available
    return None

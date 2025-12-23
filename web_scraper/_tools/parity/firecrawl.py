"""Firecrawl API client for parity testing."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

LOGGER = logging.getLogger(__name__)

# Firecrawl API configuration
FIRECRAWL_API_URL = os.getenv("FIRECRAWL_API_URL", "https://api.firecrawl.dev/v1/scrape")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")


async def scrape_with_firecrawl(url: str) -> dict[str, Any] | None:
    """
    Scrape a URL using Firecrawl API.

    Args:
        url: URL to scrape.

    Returns:
        Firecrawl response dictionary with markdown content, or None on error.
    """
    if not FIRECRAWL_API_KEY:
        LOGGER.warning("FIRECRAWL_API_KEY not set, skipping Firecrawl scrape")
        return None

    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "url": url,
        "formats": ["markdown"],
        "onlyMainContent": True,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(FIRECRAWL_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

            # Extract markdown from Firecrawl response
            if "data" in data and "markdown" in data["data"]:
                return {
                    "markdown": data["data"]["markdown"],
                    "url": url,
                    "success": True,
                }
            elif "markdown" in data:
                return {
                    "markdown": data["markdown"],
                    "url": url,
                    "success": True,
                }
            else:
                LOGGER.warning(f"Unexpected Firecrawl response format for {url}: {data}")
                return {
                    "markdown": "",
                    "url": url,
                    "success": False,
                    "error": "Unexpected response format",
                }
    except httpx.HTTPError as e:
        LOGGER.error(f"Firecrawl API error for {url}: {e}")
        return {
            "markdown": "",
            "url": url,
            "success": False,
            "error": str(e),
        }
    except Exception as e:
        LOGGER.error(f"Unexpected error scraping {url} with Firecrawl: {e}")
        return {
            "markdown": "",
            "url": url,
            "success": False,
            "error": str(e),
        }


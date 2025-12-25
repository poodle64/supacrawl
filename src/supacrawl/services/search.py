"""
Web search service for supacrawl.

Provides search functionality using DuckDuckGo (free, no API key)
or Brave Search (requires API key for higher limits).
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import httpx
from bs4 import BeautifulSoup

from supacrawl.exceptions import ProviderError, generate_correlation_id
from supacrawl.models import SearchResult, SearchResultItem, ScrapeMetadata
from supacrawl.utils import log_with_correlation

if TYPE_CHECKING:
    from supacrawl.services.scrape import ScrapeService

LOGGER = logging.getLogger(__name__)


@dataclass
class ScrapeOptions:
    """Options for scraping search results."""

    formats: list[Literal["markdown", "html"]] | None = None
    only_main_content: bool = True


class SearchService:
    """
    Web search with optional content scraping.

    Supports DuckDuckGo (default, free) and Brave Search (requires API key).

    Example usage:
        >>> service = SearchService()
        >>> result = await service.search("python web scraping", limit=5)
        >>> for item in result.data:
        ...     print(item.title, item.url)
    """

    def __init__(
        self,
        scrape_service: "ScrapeService | None" = None,
        provider: Literal["duckduckgo", "brave"] = "duckduckgo",
        brave_api_key: str | None = None,
    ):
        """
        Initialise search service.

        Args:
            scrape_service: Optional ScrapeService for scraping results.
            provider: Search provider ("duckduckgo" or "brave").
            brave_api_key: API key for Brave Search (required if using brave).
        """
        self._scrape_service = scrape_service
        self._provider = provider
        self._brave_api_key = brave_api_key or os.getenv("BRAVE_API_KEY")
        self._http_client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": "Supacrawl/1.0"},
            )
        return self._http_client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def search(
        self,
        query: str,
        limit: int = 5,
        scrape_options: ScrapeOptions | None = None,
    ) -> SearchResult:
        """
        Search the web and optionally scrape results.

        Args:
            query: Search query string. Supports search operators:
                - "quotes" for exact match
                - -word to exclude
                - site:example.com to limit to domain
            limit: Maximum number of results (1-10).
            scrape_options: Options for scraping result pages.

        Returns:
            SearchResult with search results and optional scraped content.
        """
        correlation_id = generate_correlation_id()
        limit = max(1, min(limit, 10))  # Clamp to 1-10

        try:
            log_with_correlation(
                LOGGER,
                logging.DEBUG,
                f"Searching with {self._provider}",
                correlation_id=correlation_id,
                query=query,
                limit=limit,
            )

            if self._provider == "brave" and self._brave_api_key:
                results = await self._search_brave(query, limit, correlation_id)
            else:
                results = await self._search_duckduckgo(query, limit, correlation_id)

            # Optionally scrape results
            if scrape_options and self._scrape_service:
                results = await self._scrape_results(results, scrape_options, correlation_id)

            log_with_correlation(
                LOGGER,
                logging.INFO,
                f"Search completed with {len(results)} results",
                correlation_id=correlation_id,
            )

            return SearchResult(success=True, data=results)

        except Exception as e:
            log_with_correlation(
                LOGGER,
                logging.ERROR,
                f"Search failed: {e}",
                correlation_id=correlation_id,
                error=str(e),
            )
            return SearchResult(success=False, data=[], error=str(e))

    async def _search_duckduckgo(
        self,
        query: str,
        limit: int,
        correlation_id: str,
    ) -> list[SearchResultItem]:
        """
        Search using DuckDuckGo HTML interface.

        Uses DuckDuckGo Lite for simpler HTML parsing.
        """
        client = await self._get_client()

        params = {"q": query, "kl": "au-en"}  # Australian English locale
        response = await client.get("https://lite.duckduckgo.com/lite/", params=params)
        response.raise_for_status()

        html = response.text
        results = self._parse_ddg_results(html, limit)

        log_with_correlation(
            LOGGER,
            logging.DEBUG,
            f"DuckDuckGo returned {len(results)} results",
            correlation_id=correlation_id,
            query=query,
        )
        return results

    def _parse_ddg_results(self, html: str, limit: int) -> list[SearchResultItem]:
        """Parse DuckDuckGo Lite HTML results."""
        soup = BeautifulSoup(html, "html.parser")
        results: list[SearchResultItem] = []

        # DDG Lite uses a table-based layout
        for link_cell in soup.select("a.result-link"):
            if len(results) >= limit:
                break

            href = link_cell.get("href", "")
            if not href or href.startswith("//duckduckgo.com"):
                continue

            title = link_cell.get_text(strip=True)

            # Get snippet from the next row
            description = ""
            parent_tr = link_cell.find_parent("tr")
            if parent_tr:
                next_tr = parent_tr.find_next_sibling("tr")
                if next_tr:
                    snippet_td = next_tr.find("td", class_="result-snippet")
                    if snippet_td:
                        description = snippet_td.get_text(strip=True)

            if href and title:
                results.append(
                    SearchResultItem(
                        url=str(href),
                        title=title,
                        description=description,
                    )
                )

        return results

    async def _search_brave(
        self,
        query: str,
        limit: int,
        correlation_id: str,
    ) -> list[SearchResultItem]:
        """
        Search using Brave Search API.

        Requires BRAVE_API_KEY environment variable or constructor parameter.
        """
        if not self._brave_api_key:
            raise ProviderError(
                "Brave API key not configured",
                provider="brave",
                correlation_id=correlation_id,
            )

        client = await self._get_client()

        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self._brave_api_key,
        }
        params = {"q": query, "count": limit}

        response = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers=headers,
            params=params,
        )
        response.raise_for_status()

        data = response.json()
        results: list[SearchResultItem] = []

        for item in data.get("web", {}).get("results", [])[:limit]:
            results.append(
                SearchResultItem(
                    url=item.get("url", ""),
                    title=item.get("title", ""),
                    description=item.get("description", ""),
                )
            )

        log_with_correlation(
            LOGGER,
            logging.DEBUG,
            f"Brave returned {len(results)} results",
            correlation_id=correlation_id,
            query=query,
        )
        return results

    async def _scrape_results(
        self,
        results: list[SearchResultItem],
        options: ScrapeOptions,
        correlation_id: str,
    ) -> list[SearchResultItem]:
        """
        Scrape content from search result URLs.

        Args:
            results: Search results to scrape.
            options: Scrape options.
            correlation_id: Correlation ID for logging.

        Returns:
            Results with scraped content added.
        """
        if not self._scrape_service:
            return results

        formats = options.formats or ["markdown"]

        async def scrape_one(item: SearchResultItem) -> SearchResultItem:
            try:
                result = await self._scrape_service.scrape(
                    url=item.url,
                    formats=formats,
                    only_main_content=options.only_main_content,
                )
                if result.success and result.data:
                    item.markdown = result.data.markdown
                    item.html = result.data.html
                    item.metadata = result.data.metadata
            except Exception as e:
                log_with_correlation(
                    LOGGER,
                    logging.WARNING,
                    f"Failed to scrape {item.url}: {e}",
                    correlation_id=correlation_id,
                )
            return item

        # Scrape all results concurrently
        scraped = await asyncio.gather(*[scrape_one(r) for r in results])
        return list(scraped)

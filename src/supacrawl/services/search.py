"""
Web search service for supacrawl.

Provides search functionality using DuckDuckGo (free, no API key)
or Brave Search (requires API key for higher limits).

Supports multiple search source types:
- web: Standard web search (default)
- images: Image search results
- news: News article search
"""

import asyncio
import logging
import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

from supacrawl.exceptions import ProviderError, generate_correlation_id
from supacrawl.models import SearchResult, SearchResultItem, SearchSourceType
from supacrawl.utils import log_with_correlation

if TYPE_CHECKING:
    from supacrawl.services.scrape import ScrapeService

LOGGER = logging.getLogger(__name__)

# Type alias for source types
type SourceType = Literal["web", "images", "news"]


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

    async def __aenter__(self) -> "SearchService":
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object) -> bool:
        """Exit async context manager, ensuring cleanup."""
        await self.close()
        return False

    async def search(
        self,
        query: str,
        limit: int = 5,
        sources: list[SourceType] | None = None,
        scrape_options: ScrapeOptions | None = None,
    ) -> SearchResult:
        """
        Search the web and optionally scrape results.

        Args:
            query: Search query string. Supports search operators:
                - "quotes" for exact match
                - -word to exclude
                - site:example.com to limit to domain
            limit: Maximum number of results (1-10) per source type.
            sources: List of source types to search. Defaults to ["web"].
                Supported: "web", "images", "news".
            scrape_options: Options for scraping result pages (web only).

        Returns:
            SearchResult with search results and optional scraped content.
        """
        correlation_id = generate_correlation_id()
        limit = max(1, min(limit, 10))  # Clamp to 1-10

        # Default to web search
        if sources is None:
            sources = ["web"]

        try:
            log_with_correlation(
                LOGGER,
                logging.DEBUG,
                f"Searching with {self._provider}",
                correlation_id=correlation_id,
                query=query,
                limit=limit,
                sources=sources,
            )

            all_results: list[SearchResultItem] = []

            # Search each source type
            for source in sources:
                if source == "web":
                    if self._provider == "brave" and self._brave_api_key:
                        results = await self._search_brave(query, limit, correlation_id)
                    else:
                        results = await self._search_duckduckgo(query, limit, correlation_id)
                elif source == "images":
                    if self._provider == "brave" and self._brave_api_key:
                        results = await self._search_brave_images(query, limit, correlation_id)
                    else:
                        results = await self._search_duckduckgo_images(query, limit, correlation_id)
                elif source == "news":
                    if self._provider == "brave" and self._brave_api_key:
                        results = await self._search_brave_news(query, limit, correlation_id)
                    else:
                        results = await self._search_duckduckgo_news(query, limit, correlation_id)
                else:
                    log_with_correlation(
                        LOGGER,
                        logging.WARNING,
                        f"Unknown source type: {source}",
                        correlation_id=correlation_id,
                    )
                    continue

                all_results.extend(results)

            # Optionally scrape results (web results only)
            if scrape_options and self._scrape_service:
                web_results = [r for r in all_results if r.source_type == SearchSourceType.WEB]
                other_results = [r for r in all_results if r.source_type != SearchSourceType.WEB]
                if web_results:
                    web_results = await self._scrape_results(web_results, scrape_options, correlation_id)
                all_results = web_results + other_results

            log_with_correlation(
                LOGGER,
                logging.INFO,
                f"Search completed with {len(all_results)} results",
                correlation_id=correlation_id,
            )

            return SearchResult(success=True, data=all_results)

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

            href_attr = link_cell.get("href", "")
            href = href_attr[0] if isinstance(href_attr, list) else href_attr
            if not href or not isinstance(href, str):
                continue

            # DDG Lite uses redirect URLs like //duckduckgo.com/l/?uddg=<encoded_url>
            # Extract the actual URL from the uddg parameter
            if href.startswith("//duckduckgo.com"):
                parsed = urlparse(href)
                params = parse_qs(parsed.query)
                if "uddg" in params:
                    href = params["uddg"][0]
                else:
                    # Skip if we can't extract the actual URL
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
                        source_type=SearchSourceType.WEB,
                    )
                )

        return results

    async def _search_duckduckgo_images(
        self,
        query: str,
        limit: int,
        correlation_id: str,
    ) -> list[SearchResultItem]:
        """
        Search for images using DuckDuckGo.

        Uses DuckDuckGo's image search API endpoint.
        """
        client = await self._get_client()

        # First, we need to get a vqd token from the main search
        token_params = {"q": query}
        token_response = await client.get(
            "https://duckduckgo.com/",
            params=token_params,
        )

        # Extract vqd token from response
        vqd_match = re.search(r'vqd=["\']([^"\']+)["\']', token_response.text)
        if not vqd_match:
            # Fallback: try to find vqd in a different format
            vqd_match = re.search(r"vqd=([a-zA-Z0-9_-]+)", token_response.text)

        if not vqd_match:
            log_with_correlation(
                LOGGER,
                logging.WARNING,
                "Could not extract DuckDuckGo vqd token for image search",
                correlation_id=correlation_id,
            )
            return []

        vqd = vqd_match.group(1)

        # Now make the image search request
        params = {
            "q": query,
            "vqd": vqd,
            "l": "au-en",
            "o": "json",
            "f": ",,,",
            "p": "1",
        }

        response = await client.get(
            "https://duckduckgo.com/i.js",
            params=params,
        )

        results: list[SearchResultItem] = []

        try:
            data = response.json()
            for item in data.get("results", [])[:limit]:
                image_url = item.get("image", "")
                if not image_url:
                    continue

                results.append(
                    SearchResultItem(
                        url=image_url,
                        title=item.get("title", ""),
                        description=item.get("source", ""),
                        source_type=SearchSourceType.IMAGES,
                        thumbnail=item.get("thumbnail", ""),
                        image_width=item.get("width"),
                        image_height=item.get("height"),
                    )
                )
        except Exception as e:
            log_with_correlation(
                LOGGER,
                logging.WARNING,
                f"Failed to parse DuckDuckGo image results: {e}",
                correlation_id=correlation_id,
            )

        log_with_correlation(
            LOGGER,
            logging.DEBUG,
            f"DuckDuckGo images returned {len(results)} results",
            correlation_id=correlation_id,
            query=query,
        )
        return results

    async def _search_duckduckgo_news(
        self,
        query: str,
        limit: int,
        correlation_id: str,
    ) -> list[SearchResultItem]:
        """
        Search for news using DuckDuckGo.

        Uses DuckDuckGo's news search API endpoint.
        """
        client = await self._get_client()

        # First, we need to get a vqd token from the main search
        token_params = {"q": query}
        token_response = await client.get(
            "https://duckduckgo.com/",
            params=token_params,
        )

        # Extract vqd token from response
        vqd_match = re.search(r'vqd=["\']([^"\']+)["\']', token_response.text)
        if not vqd_match:
            vqd_match = re.search(r"vqd=([a-zA-Z0-9_-]+)", token_response.text)

        if not vqd_match:
            log_with_correlation(
                LOGGER,
                logging.WARNING,
                "Could not extract DuckDuckGo vqd token for news search",
                correlation_id=correlation_id,
            )
            return []

        vqd = vqd_match.group(1)

        # Now make the news search request
        params = {
            "q": query,
            "vqd": vqd,
            "l": "au-en",
            "o": "json",
            "noamp": "1",
            "df": "",
        }

        response = await client.get(
            "https://duckduckgo.com/news.js",
            params=params,
        )

        results: list[SearchResultItem] = []

        try:
            data = response.json()
            for item in data.get("results", [])[:limit]:
                url = item.get("url", "")
                if not url:
                    continue

                # Parse date from Unix timestamp if available
                published_at = None
                if "date" in item:
                    try:
                        from datetime import datetime, timezone

                        timestamp = item["date"]
                        if isinstance(timestamp, int):
                            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                            published_at = dt.isoformat()
                    except Exception:
                        pass

                results.append(
                    SearchResultItem(
                        url=url,
                        title=item.get("title", ""),
                        description=item.get("excerpt", item.get("body", "")),
                        source_type=SearchSourceType.NEWS,
                        published_at=published_at,
                        source_name=item.get("source", ""),
                    )
                )
        except Exception as e:
            log_with_correlation(
                LOGGER,
                logging.WARNING,
                f"Failed to parse DuckDuckGo news results: {e}",
                correlation_id=correlation_id,
            )

        log_with_correlation(
            LOGGER,
            logging.DEBUG,
            f"DuckDuckGo news returned {len(results)} results",
            correlation_id=correlation_id,
            query=query,
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
        params: dict[str, str | int] = {"q": query, "count": limit}

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
                    source_type=SearchSourceType.WEB,
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

    async def _search_brave_images(
        self,
        query: str,
        limit: int,
        correlation_id: str,
    ) -> list[SearchResultItem]:
        """
        Search for images using Brave Search API.

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
        params: dict[str, str | int] = {"q": query, "count": limit}

        response = await client.get(
            "https://api.search.brave.com/res/v1/images/search",
            headers=headers,
            params=params,
        )
        response.raise_for_status()

        data = response.json()
        results: list[SearchResultItem] = []

        for item in data.get("results", [])[:limit]:
            results.append(
                SearchResultItem(
                    url=item.get("url", ""),
                    title=item.get("title", ""),
                    description=item.get("source", ""),
                    source_type=SearchSourceType.IMAGES,
                    thumbnail=item.get("thumbnail", {}).get("src", ""),
                    image_width=item.get("properties", {}).get("width"),
                    image_height=item.get("properties", {}).get("height"),
                )
            )

        log_with_correlation(
            LOGGER,
            logging.DEBUG,
            f"Brave images returned {len(results)} results",
            correlation_id=correlation_id,
            query=query,
        )
        return results

    async def _search_brave_news(
        self,
        query: str,
        limit: int,
        correlation_id: str,
    ) -> list[SearchResultItem]:
        """
        Search for news using Brave Search API.

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
        params: dict[str, str | int] = {"q": query, "count": limit}

        response = await client.get(
            "https://api.search.brave.com/res/v1/news/search",
            headers=headers,
            params=params,
        )
        response.raise_for_status()

        data = response.json()
        results: list[SearchResultItem] = []

        for item in data.get("results", [])[:limit]:
            # Brave news returns age as relative time (e.g., "2 hours ago")
            # and page_age as ISO 8601 timestamp
            published_at = item.get("page_age")

            results.append(
                SearchResultItem(
                    url=item.get("url", ""),
                    title=item.get("title", ""),
                    description=item.get("description", ""),
                    source_type=SearchSourceType.NEWS,
                    published_at=published_at,
                    source_name=item.get("meta_url", {}).get("hostname", ""),
                )
            )

        log_with_correlation(
            LOGGER,
            logging.DEBUG,
            f"Brave news returned {len(results)} results",
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

        # Capture service reference for closure
        scrape_service = self._scrape_service
        formats = options.formats or ["markdown"]

        async def scrape_one(item: SearchResultItem) -> SearchResultItem:
            try:
                result = await scrape_service.scrape(
                    url=item.url,
                    formats=list(formats),  # type: ignore[arg-type]
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

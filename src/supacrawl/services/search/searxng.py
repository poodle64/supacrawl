"""SearXNG search provider implementation.

SearXNG is a free, self-hosted metasearch engine. It aggregates results
from multiple search engines without tracking users.

Configuration:
    Set SEARXNG_URL environment variable to your instance URL.
    Example: SEARXNG_URL=http://192.168.5.17:8080
"""

import logging
import os

import httpx

from supacrawl.models import SearchResultItem, SearchSourceType
from supacrawl.utils import log_with_correlation

LOGGER = logging.getLogger(__name__)


class SearXNGProvider:
    """SearXNG metasearch engine provider.

    Requires a SEARXNG_URL pointing to a running SearXNG instance.
    Supports web, image, and news search via SearXNG categories.
    """

    def __init__(
        self,
        url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = (url or os.getenv("SEARXNG_URL", "")).rstrip("/")
        self._owns_client = http_client is None
        self._http_client = http_client

    @property
    def name(self) -> str:
        return "searxng"

    def is_available(self) -> bool:
        return bool(self._url)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
            self._owns_client = True
        return self._http_client

    async def _search(
        self,
        query: str,
        limit: int,
        categories: str,
        correlation_id: str,
    ) -> list[dict]:
        """Execute a search against the SearXNG JSON API."""
        client = await self._get_client()
        params: dict[str, str | int] = {
            "q": query,
            "format": "json",
            "categories": categories,
        }
        response = await client.get(
            f"{self._url}/search",
            params=params,
        )
        response.raise_for_status()

        data = response.json()
        return data.get("results", [])[:limit]

    async def search_web(self, query: str, limit: int, correlation_id: str) -> list[SearchResultItem]:
        raw_results = await self._search(query, limit, "general", correlation_id)
        results: list[SearchResultItem] = []
        for item in raw_results:
            results.append(
                SearchResultItem(
                    url=item.get("url", ""),
                    title=item.get("title", ""),
                    description=item.get("content", ""),
                    source_type=SearchSourceType.WEB,
                )
            )

        log_with_correlation(
            LOGGER,
            logging.DEBUG,
            f"SearXNG returned {len(results)} web results",
            correlation_id=correlation_id,
            query=query,
        )
        return results

    async def search_images(self, query: str, limit: int, correlation_id: str) -> list[SearchResultItem]:
        raw_results = await self._search(query, limit, "images", correlation_id)
        results: list[SearchResultItem] = []
        for item in raw_results:
            results.append(
                SearchResultItem(
                    url=item.get("url", item.get("img_src", "")),
                    title=item.get("title", ""),
                    description=item.get("content", item.get("source", "")),
                    source_type=SearchSourceType.IMAGES,
                    thumbnail=item.get("thumbnail_src", item.get("img_src", "")),
                    image_width=item.get("img_format", {}).get("width") if isinstance(item.get("img_format"), dict) else None,
                    image_height=item.get("img_format", {}).get("height") if isinstance(item.get("img_format"), dict) else None,
                )
            )

        log_with_correlation(
            LOGGER,
            logging.DEBUG,
            f"SearXNG returned {len(results)} image results",
            correlation_id=correlation_id,
            query=query,
        )
        return results

    async def search_news(self, query: str, limit: int, correlation_id: str) -> list[SearchResultItem]:
        raw_results = await self._search(query, limit, "news", correlation_id)
        results: list[SearchResultItem] = []
        for item in raw_results:
            results.append(
                SearchResultItem(
                    url=item.get("url", ""),
                    title=item.get("title", ""),
                    description=item.get("content", ""),
                    source_type=SearchSourceType.NEWS,
                    published_at=item.get("publishedDate"),
                    source_name=item.get("engine", ""),
                )
            )

        log_with_correlation(
            LOGGER,
            logging.DEBUG,
            f"SearXNG returned {len(results)} news results",
            correlation_id=correlation_id,
            query=query,
        )
        return results

    async def close(self) -> None:
        if self._http_client and self._owns_client:
            await self._http_client.aclose()
            self._http_client = None

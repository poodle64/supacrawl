"""Tavily Search provider implementation."""

import logging
import os

import httpx

from supacrawl.exceptions import ProviderError
from supacrawl.models import SearchFilters, SearchResultItem, SearchSourceType
from supacrawl.utils import log_with_correlation

LOGGER = logging.getLogger(__name__)


class TavilyProvider:
    """Tavily Search API provider.

    Requires TAVILY_API_KEY. Supports web search. Images/news use web search
    with topic filters.
    """

    API_BASE = "https://api.tavily.com"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.getenv("TAVILY_API_KEY")
        self._http_client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return "tavily"

    def is_available(self) -> bool:
        return bool(self._api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    def _require_api_key(self) -> str:
        if not self._api_key:
            raise ProviderError("Tavily API key not configured", provider="tavily")
        return self._api_key

    async def _search(
        self,
        query: str,
        limit: int,
        correlation_id: str,
        *,
        topic: str = "general",
        filters: SearchFilters | None = None,
    ) -> list[SearchResultItem]:
        client = await self._get_client()

        effective_topic = filters.topic if (filters and filters.topic) else topic

        payload: dict[str, object] = {
            "api_key": self._require_api_key(),
            "query": query,
            "max_results": limit,
            "topic": effective_topic,
            "include_answer": False,
            "include_raw_content": False,
        }

        if filters and not filters.is_empty():
            if filters.time_range:
                payload["time_range"] = filters.time_range
            if filters.start_date:
                payload["start_date"] = filters.start_date
            if filters.end_date:
                payload["end_date"] = filters.end_date
            if filters.include_domains:
                payload["include_domains"] = filters.include_domains
            if filters.exclude_domains:
                payload["exclude_domains"] = filters.exclude_domains

        response = await client.post(f"{self.API_BASE}/search", json=payload)
        response.raise_for_status()

        data = response.json()
        results: list[SearchResultItem] = []

        source_type = SearchSourceType.NEWS if effective_topic == "news" else SearchSourceType.WEB

        for item in data.get("results", [])[:limit]:
            results.append(
                SearchResultItem(
                    url=item.get("url", ""),
                    title=item.get("title", ""),
                    description=item.get("content", ""),
                    source_type=source_type,
                    published_at=item.get("published_date") if effective_topic == "news" else None,
                )
            )

        log_with_correlation(
            LOGGER,
            logging.DEBUG,
            f"Tavily returned {len(results)} results (topic={effective_topic})",
            correlation_id=correlation_id,
            query=query,
        )
        return results

    async def search_web(
        self, query: str, limit: int, correlation_id: str, filters: SearchFilters | None = None
    ) -> list[SearchResultItem]:
        return await self._search(query, limit, correlation_id, topic="general", filters=filters)

    async def search_images(
        self, query: str, limit: int, correlation_id: str, filters: SearchFilters | None = None
    ) -> list[SearchResultItem]:
        raise NotImplementedError("Tavily does not support image search")

    async def search_news(
        self, query: str, limit: int, correlation_id: str, filters: SearchFilters | None = None
    ) -> list[SearchResultItem]:
        return await self._search(query, limit, correlation_id, topic="news", filters=filters)

    async def close(self) -> None:
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

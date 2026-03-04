"""Exa.ai search provider implementation."""

import logging
import os

import httpx

from supacrawl.exceptions import ProviderError
from supacrawl.models import SearchResultItem, SearchSourceType
from supacrawl.utils import log_with_correlation

LOGGER = logging.getLogger(__name__)


class ExaProvider:
    """Exa.ai neural search provider.

    Requires EXA_API_KEY. Supports web and news search.
    Image search is not supported.
    """

    API_BASE = "https://api.exa.ai"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.getenv("EXA_API_KEY")
        self._http_client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return "exa"

    def is_available(self) -> bool:
        return bool(self._api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    def _require_api_key(self) -> str:
        if not self._api_key:
            raise ProviderError("Exa API key not configured", provider="exa")
        return self._api_key

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._require_api_key(),
            "Content-Type": "application/json",
        }

    async def search_web(self, query: str, limit: int, correlation_id: str) -> list[SearchResultItem]:
        client = await self._get_client()

        payload = {
            "query": query,
            "numResults": limit,
            "type": "auto",
        }

        response = await client.post(
            f"{self.API_BASE}/search",
            headers=self._headers(),
            json=payload,
        )
        response.raise_for_status()

        data = response.json()
        results: list[SearchResultItem] = []

        for item in data.get("results", [])[:limit]:
            results.append(
                SearchResultItem(
                    url=item.get("url", ""),
                    title=item.get("title", ""),
                    description=item.get("text", item.get("snippet", "")),
                    source_type=SearchSourceType.WEB,
                    published_at=item.get("publishedDate"),
                )
            )

        log_with_correlation(
            LOGGER,
            logging.DEBUG,
            f"Exa returned {len(results)} results",
            correlation_id=correlation_id,
            query=query,
        )
        return results

    async def search_images(self, query: str, limit: int, correlation_id: str) -> list[SearchResultItem]:
        raise NotImplementedError("Exa does not support image search")

    async def search_news(self, query: str, limit: int, correlation_id: str) -> list[SearchResultItem]:
        client = await self._get_client()

        payload = {
            "query": query,
            "numResults": limit,
            "type": "auto",
            "category": "news",
        }

        response = await client.post(
            f"{self.API_BASE}/search",
            headers=self._headers(),
            json=payload,
        )
        response.raise_for_status()

        data = response.json()
        results: list[SearchResultItem] = []

        for item in data.get("results", [])[:limit]:
            results.append(
                SearchResultItem(
                    url=item.get("url", ""),
                    title=item.get("title", ""),
                    description=item.get("text", item.get("snippet", "")),
                    source_type=SearchSourceType.NEWS,
                    published_at=item.get("publishedDate"),
                )
            )

        log_with_correlation(
            LOGGER,
            logging.DEBUG,
            f"Exa news returned {len(results)} results",
            correlation_id=correlation_id,
            query=query,
        )
        return results

    async def close(self) -> None:
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

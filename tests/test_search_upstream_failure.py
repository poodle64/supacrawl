"""A broken SearXNG must say WHY, not hand back a silent empty set (#161).

These drive the REAL SearchService and the REAL health probe against a SearXNG
whose engines are all down (a 200 response with an empty result set and a full
``unresponsive_engines`` list — exactly the instance state the field report hit
under six concurrent agents). The point is to prove the failure surfaces as a
typed error the caller reads AND turns the health probe red — the inverse of
the "healthy + []" the report saw. Strict-provider mode is on so no DuckDuckGo
fallback is appended: this file isolates the no-fallback "say why" behaviour;
the fallback path is covered in test_search_fallback.py.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from supacrawl.mcp.tools.health import _run_search_health_probe, supacrawl_health
from supacrawl.services.search.searxng import SearXNGProvider
from supacrawl.services.search.service import SearchService

pytestmark = pytest.mark.mcp

# All four general-category engines down — the real instance-config failure.
_BROKEN_BODY = {
    "results": [],
    "unresponsive_engines": [
        ["brave", "timeout"],
        ["wolframalpha", "error"],
        ["wikibooks", "error"],
        ["wikinews", "error"],
    ],
}


def _broken_searxng_client() -> httpx.AsyncClient:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_BROKEN_BODY)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _broken_searxng_service() -> tuple[SearchService, httpx.AsyncClient]:
    """A real SearchService whose only provider is a SearXNG with dead engines."""
    with patch.dict(
        os.environ,
        {
            "SEARXNG_URL": "http://searxng.invalid",
            "SUPACRAWL_SEARCH_PROVIDERS": "searxng",
            # No DuckDuckGo safety net: isolate the "say why" failure path.
            "SUPACRAWL_SEARCH_STRICT_PROVIDERS": "1",
        },
    ):
        service = SearchService(providers=["searxng"])

    broken_client = _broken_searxng_client()
    for provider in service.provider_chain.providers:
        if isinstance(provider, SearXNGProvider):
            provider._http_client = broken_client
    return service, broken_client


class _StubServices:
    """Minimal SupacrawlServices stand-in carrying a real SearchService."""

    def __init__(self, search_service: SearchService) -> None:
        self.search_service = search_service
        self.browser_manager = None  # no shared engine to move the top-line status

    def get_service_status(self) -> dict[str, bool]:
        return {"scrape": True, "crawl": True, "map": True, "search": True}


class TestBrokenSearxngSurfacesTheCause:
    @pytest.mark.asyncio
    async def test_search_returns_typed_failure_naming_the_engines(self) -> None:
        service, client = _broken_searxng_service()
        try:
            result = await service.search("open source software", limit=5)

            assert result.success is False, "a dead backend returned success — the exact #161 lie"
            assert result.data == []
            assert result.error and "unresponsive" in result.error.lower()
            engines = {e.engine for e in result.unresponsive_engines}
            assert {"brave", "wikibooks", "wikinews"} <= engines, (
                f"the result must carry the dead engines, got: {engines}"
            )
        finally:
            await service.close()
            await client.aclose()

    @pytest.mark.asyncio
    async def test_health_probe_goes_red(self) -> None:
        """The task's demand: prove the probe FAILS when search is genuinely broken."""
        service, client = _broken_searxng_service()
        try:
            probe = await _run_search_health_probe(service)

            assert probe is not None
            assert probe["ok"] is False, "the probe passed against a SearXNG whose engines are all down"
            assert probe["result_count"] == 0
        finally:
            await service.close()
            await client.aclose()

    @pytest.mark.asyncio
    async def test_top_level_health_is_degraded(self) -> None:
        service, client = _broken_searxng_service()
        try:
            with patch.dict(os.environ, {"SEARXNG_URL": "http://searxng.invalid"}):
                result: dict[str, Any] = await supacrawl_health(_StubServices(service))  # type: ignore[arg-type]

            assert result["status"] == "degraded", f"health said {result['status']!r} while the search backend was down"
            assert result["components"]["search"]["live_probe"]["ok"] is False
        finally:
            await service.close()
            await client.aclose()

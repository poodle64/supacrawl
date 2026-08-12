"""The opt-in DuckDuckGo fallback behind a failing configured backend (#161).

A self-hosted SearXNG is chosen to keep queries in-house, so this fallback is
deliberately OFF by default — a SearXNG failure surfaces as a loud typed error
(see test_search_upstream_failure.py), never a silent leak to a public engine.
With SUPACRAWL_SEARCH_PUBLIC_FALLBACK on, an operator who would rather have
degraded-but-answering search gets DuckDuckGo behind the configured backend.

These drive the real registry, service, and health surfaces: the fallback
engages on a SearXNG whose engines are all down, the caller is told a fallback
answered, and health reports degraded rather than pretending the configured
backend is fine.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from supacrawl.mcp.tools.health import supacrawl_health
from supacrawl.services.search.duckduckgo import DuckDuckGoProvider
from supacrawl.services.search.providers import ProviderChain
from supacrawl.services.search.registry import build_provider_chain
from supacrawl.services.search.searxng import SearXNGProvider
from supacrawl.services.search.service import SearchService

pytestmark = pytest.mark.mcp

_BROKEN_SEARXNG = {
    "results": [],
    "unresponsive_engines": [["brave", "timeout"], ["wikibooks", "error"], ["wikinews", "error"]],
}

# Minimal DuckDuckGo-lite HTML the DuckDuckGoProvider knows how to parse.
_DDG_HTML = """
<table>
  <tr><td><a class="result-link" href="https://example.org/ddg1">DDG One</a></td></tr>
  <tr><td class="result-snippet">snippet one</td></tr>
  <tr><td><a class="result-link" href="https://example.org/ddg2">DDG Two</a></td></tr>
  <tr><td class="result-snippet">snippet two</td></tr>
  <tr><td><a class="result-link" href="https://example.org/ddg3">DDG Three</a></td></tr>
  <tr><td class="result-snippet">snippet three</td></tr>
</table>
"""


def _routing_client() -> httpx.AsyncClient:
    """One client: SearXNG's host is down, DuckDuckGo's answers."""

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if "searxng" in host:
            return httpx.Response(200, json=_BROKEN_SEARXNG)
        if "duckduckgo" in host:
            return httpx.Response(200, text=_DDG_HTML, headers={"content-type": "text/html"})
        return httpx.Response(500, text="unexpected host")

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _searxng_service_with_public_fallback() -> tuple[SearchService, httpx.AsyncClient]:
    with patch.dict(
        os.environ,
        {
            "SEARXNG_URL": "http://searxng.invalid",
            "SUPACRAWL_SEARCH_PROVIDERS": "searxng",
            "SUPACRAWL_SEARCH_PUBLIC_FALLBACK": "1",
            "SUPACRAWL_SEARCH_STRICT_PROVIDERS": "",
        },
    ):
        service = SearchService(providers=["searxng"])

    client = _routing_client()
    for provider in service.provider_chain.providers:
        if isinstance(provider, (SearXNGProvider, DuckDuckGoProvider)):
            provider._http_client = client
    return service, client


class _StubServices:
    def __init__(self, search_service: SearchService) -> None:
        self.search_service = search_service
        self.browser_manager = None

    def get_service_status(self) -> dict[str, bool]:
        return {"scrape": True, "crawl": True, "map": True, "search": True}


# ---------------------------------------------------------------------------
# Registry: when the fallback is appended, and when it is refused
# ---------------------------------------------------------------------------


class TestPublicFallbackAppend:
    def _names(self, **env: str) -> list[str]:
        with patch.dict(os.environ, {"SEARXNG_URL": "http://searxng.invalid", **env}, clear=False):
            chain = build_provider_chain("searxng")
        return [p.name for p in chain.providers]

    def test_off_by_default_searxng_serves_alone(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SUPACRAWL_SEARCH_PUBLIC_FALLBACK", None)
            assert self._names() == ["searxng"], "a self-hosted backend must not gain a silent public fallback"

    def test_opt_in_appends_duckduckgo_behind_searxng(self) -> None:
        assert self._names(SUPACRAWL_SEARCH_PUBLIC_FALLBACK="1") == ["searxng", "duckduckgo"]

    def test_strict_overrides_the_opt_in(self) -> None:
        names = self._names(SUPACRAWL_SEARCH_PUBLIC_FALLBACK="1", SUPACRAWL_SEARCH_STRICT_PROVIDERS="1")
        assert names == ["searxng"], "strict mode must refuse the fallback even when opt-in is on"

    def test_opt_in_does_not_double_add_configured_duckduckgo(self) -> None:
        with patch.dict(
            os.environ,
            {"SEARXNG_URL": "http://searxng.invalid", "SUPACRAWL_SEARCH_PUBLIC_FALLBACK": "1"},
            clear=False,
        ):
            chain = build_provider_chain("searxng,duckduckgo")
        assert [p.name for p in chain.providers] == ["searxng", "duckduckgo"]


# ---------------------------------------------------------------------------
# The fallback actually engages, end to end
# ---------------------------------------------------------------------------


class TestFallbackEngages:
    @pytest.mark.asyncio
    async def test_search_falls_back_to_duckduckgo_and_flags_it(self) -> None:
        service, client = _searxng_service_with_public_fallback()
        try:
            result = await service.search("open source software", limit=5)

            assert result.success is True, "the fallback did not rescue a failed configured backend"
            assert result.data, "fallback returned no results"
            assert result.provider == "duckduckgo"
            assert result.provider_fallback is True, "the caller cannot tell a fallback answered"
            assert service.provider_chain.fallback_serving is True
        finally:
            await service.close()
            await client.aclose()

    @pytest.mark.asyncio
    async def test_health_reports_fallback_active_and_degraded(self) -> None:
        service, client = _searxng_service_with_public_fallback()
        try:
            with patch.dict(os.environ, {"SEARXNG_URL": "http://searxng.invalid"}):
                result: dict[str, Any] = await supacrawl_health(_StubServices(service))  # type: ignore[arg-type]

            search = result["components"]["search"]
            # The probe is answered by DDG, so it returns results — but serving
            # from an unconfigured fallback is still degraded, not healthy.
            assert search["provider_fallback_active"] is True, "health hid an active fallback"
            assert result["status"] == "degraded"
            assert "duckduckgo" in (search.get("warning", "").lower() + search.get("effective_provider", ""))
        finally:
            await service.close()
            await client.aclose()


# ---------------------------------------------------------------------------
# fallback_serving vs unconfigured_fallback_active
# ---------------------------------------------------------------------------


class _StubProvider:
    def __init__(self, name: str, *, available: bool = True, results: bool = True) -> None:
        self._name = name
        self._available = available
        self._results = results

    @property
    def name(self) -> str:
        return self._name

    def is_available(self) -> bool:
        return self._available

    async def search_web(self, *_a: object, **_k: object) -> list:
        from supacrawl.models import SearchResultItem

        if not self._results:
            # A fallback-eligible failure, so the chain moves to the next provider.
            raise TimeoutError("engines down")
        return [SearchResultItem(url="https://x/", title=f"{self._name}")]

    async def search_images(self, *_a: object, **_k: object) -> list:
        raise NotImplementedError

    async def search_news(self, *_a: object, **_k: object) -> list:
        raise NotImplementedError

    async def close(self) -> None:
        return None


class TestFallbackServingSignal:
    def test_false_before_any_search(self) -> None:
        chain = ProviderChain(configured_names=["searxng"])
        chain.add(_StubProvider("searxng"))
        chain.add(_StubProvider("duckduckgo"))
        assert chain.fallback_serving is False

    @pytest.mark.asyncio
    async def test_true_once_an_unconfigured_provider_answers(self) -> None:
        chain = ProviderChain(configured_names=["searxng"])
        chain.add(_StubProvider("searxng", available=True, results=False))  # raises, forcing fallback
        chain.add(_StubProvider("duckduckgo"))

        await chain.search("web", "q", 1, "corr")

        assert chain.last_provider == "duckduckgo"
        assert chain.fallback_serving is True

    @pytest.mark.asyncio
    async def test_false_when_the_configured_provider_answers(self) -> None:
        chain = ProviderChain(configured_names=["searxng"])
        chain.add(_StubProvider("searxng"))
        chain.add(_StubProvider("duckduckgo"))

        await chain.search("web", "q", 1, "corr")

        assert chain.last_provider == "searxng"
        assert chain.fallback_serving is False

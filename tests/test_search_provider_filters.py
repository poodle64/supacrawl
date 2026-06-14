"""Per-provider request-building tests for search filters (#122).

Each provider builds its API request from a SearchFilters; these tests inject a
fake httpx client that captures the outgoing request and assert the exact params
or payload, per the verified provider-API mapping.
"""

from typing import Any

import pytest

from supacrawl.models import SearchFilters
from supacrawl.services.search.brave import BraveProvider
from supacrawl.services.search.duckduckgo import DuckDuckGoProvider
from supacrawl.services.search.exa import ExaProvider
from supacrawl.services.search.serper import SerperProvider
from supacrawl.services.search.tavily import TavilyProvider


class _FakeResponse:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data
        self.status_code = 200
        self.text = ""

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        return self._data


class _FakeClient:
    """Captures the last request and returns a canned JSON body."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data
        self.last: dict[str, Any] = {}

    async def post(self, url: str, *, json: Any = None, headers: Any = None) -> _FakeResponse:
        self.last = {"url": url, "json": json, "headers": headers}
        return _FakeResponse(self._data)

    async def get(self, url: str, *, params: Any = None, headers: Any = None) -> _FakeResponse:
        self.last = {"url": url, "params": params, "headers": headers}
        return _FakeResponse(self._data)

    async def aclose(self) -> None:
        pass


@pytest.mark.asyncio
class TestTavilyFilters:
    async def test_native_filters_in_payload(self) -> None:
        provider = TavilyProvider(api_key="k")
        fake = _FakeClient({"results": []})
        provider._http_client = fake  # type: ignore[assignment]
        await provider.search_web(
            "ai",
            5,
            "cid",
            SearchFilters(
                time_range="week",
                start_date="2026-01-01",
                end_date="2026-02-01",
                topic="finance",
                include_domains=["a.com"],
                exclude_domains=["b.com"],
            ),
        )
        payload = fake.last["json"]
        assert payload["time_range"] == "week"
        assert payload["start_date"] == "2026-01-01"
        assert payload["end_date"] == "2026-02-01"
        assert payload["topic"] == "finance"  # filters.topic overrides the web default
        assert payload["include_domains"] == ["a.com"]
        assert payload["exclude_domains"] == ["b.com"]

    async def test_no_filters_leaves_payload_clean(self) -> None:
        provider = TavilyProvider(api_key="k")
        fake = _FakeClient({"results": []})
        provider._http_client = fake  # type: ignore[assignment]
        await provider.search_web("ai", 5, "cid")
        payload = fake.last["json"]
        assert payload["topic"] == "general"
        assert "time_range" not in payload
        assert "include_domains" not in payload


@pytest.mark.asyncio
class TestBraveFilters:
    async def test_freshness_and_domain_operators(self) -> None:
        fake = _FakeClient({"web": {"results": []}})
        provider = BraveProvider(api_key="k", http_client=fake)  # type: ignore[arg-type]
        await provider.search_web(
            "ai",
            5,
            "cid",
            SearchFilters(time_range="day", include_domains=["a.com"], exclude_domains=["b.com"]),
        )
        params = fake.last["params"]
        assert params["freshness"] == "pd"
        assert params["q"] == "ai site:a.com -site:b.com"

    async def test_absolute_date_range_freshness(self) -> None:
        fake = _FakeClient({"web": {"results": []}})
        provider = BraveProvider(api_key="k", http_client=fake)  # type: ignore[arg-type]
        await provider.search_web("ai", 5, "cid", SearchFilters(start_date="2026-01-01", end_date="2026-03-31"))
        assert fake.last["params"]["freshness"] == "2026-01-01to2026-03-31"

    async def test_no_filters_leaves_params_clean(self) -> None:
        fake = _FakeClient({"web": {"results": []}})
        provider = BraveProvider(api_key="k", http_client=fake)  # type: ignore[arg-type]
        await provider.search_web("ai", 5, "cid")
        assert "freshness" not in fake.last["params"]
        assert fake.last["params"]["q"] == "ai"


@pytest.mark.asyncio
class TestSerperFilters:
    async def test_relative_tbs_and_domains(self) -> None:
        provider = SerperProvider(api_key="k")
        fake = _FakeClient({"organic": []})
        provider._http_client = fake  # type: ignore[assignment]
        await provider.search_web("ai", 5, "cid", SearchFilters(time_range="month", include_domains=["a.com"]))
        payload = fake.last["json"]
        assert payload["tbs"] == "qdr:m"
        assert payload["q"] == "ai site:a.com"

    async def test_absolute_cdr_tbs(self) -> None:
        provider = SerperProvider(api_key="k")
        fake = _FakeClient({"organic": []})
        provider._http_client = fake  # type: ignore[assignment]
        await provider.search_web("ai", 5, "cid", SearchFilters(start_date="2026-01-01", end_date="2026-02-15"))
        assert fake.last["json"]["tbs"] == "cdr:1,cd_min:1/1/2026,cd_max:2/15/2026"


@pytest.mark.asyncio
class TestExaFilters:
    async def test_dates_domains_and_category(self) -> None:
        provider = ExaProvider(api_key="k")
        fake = _FakeClient({"results": []})
        provider._http_client = fake  # type: ignore[assignment]
        await provider.search_web(
            "ai",
            5,
            "cid",
            SearchFilters(
                start_date="2026-01-01",
                end_date="2026-02-01",
                include_domains=["a.com"],
                exclude_domains=["b.com"],
                topic="news",
            ),
        )
        payload = fake.last["json"]
        assert payload["startPublishedDate"] == "2026-01-01T00:00:00.000Z"
        assert payload["endPublishedDate"] == "2026-02-01T00:00:00.000Z"
        assert payload["includeDomains"] == ["a.com"]
        assert payload["excludeDomains"] == ["b.com"]
        assert payload["category"] == "news"

    async def test_relative_time_range_becomes_start_date(self) -> None:
        provider = ExaProvider(api_key="k")
        fake = _FakeClient({"results": []})
        provider._http_client = fake  # type: ignore[assignment]
        await provider.search_web("ai", 5, "cid", SearchFilters(time_range="week"))
        # Exa has no relative range; time_range is converted to an absolute start date.
        assert fake.last["json"]["startPublishedDate"].endswith("T00:00:00.000Z")


class _DDGResponse:
    """A DDG response carrying both a vqd token (in text) and a JSON body."""

    def __init__(self) -> None:
        self.text = 'vqd="tok123"'
        self.status_code = 200

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        return {"results": []}


class _DDGClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def get(self, url: str, *, params: Any = None, headers: Any = None) -> _DDGResponse:
        self.calls.append({"url": url, "params": params})
        return _DDGResponse()

    async def aclose(self) -> None:
        pass


@pytest.mark.asyncio
class TestDuckDuckGoNewsFilters:
    """Regression: DuckDuckGo news must apply filters like web, not ignore them."""

    async def test_news_applies_df_and_domain_operators(self) -> None:
        fake = _DDGClient()
        provider = DuckDuckGoProvider(http_client=fake)  # type: ignore[arg-type]
        await provider.search_news("ai", 5, "cid", SearchFilters(time_range="day", include_domains=["bbc.com"]))
        news_call = next(c for c in fake.calls if "news.js" in c["url"])
        assert news_call["params"]["df"] == "d"
        assert "site:bbc.com" in news_call["params"]["q"]

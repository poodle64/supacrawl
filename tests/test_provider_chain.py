"""Tests for multi-provider search chain with automatic fallback."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from supacrawl.exceptions import ProviderError
from supacrawl.models import SearchResultItem, SearchSourceType
from supacrawl.services.search import SearchService
from supacrawl.services.search.providers import (
    ProviderChain,
    ProviderHealth,
    ProviderStatus,
    is_fallback_error,
)
from supacrawl.services.search.registry import SUPPORTED_PROVIDERS, build_provider_chain

# ---------------------------------------------------------------------------
# Helpers: mock providers
# ---------------------------------------------------------------------------


class MockProvider:
    """Test double implementing the SearchProvider protocol."""

    def __init__(self, provider_name: str, *, available: bool = True, fail_with: Exception | None = None):
        self._name = provider_name
        self._available = available
        self._fail_with = fail_with
        self._calls: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    def is_available(self) -> bool:
        return self._available

    async def search_web(self, query: str, limit: int, correlation_id: str) -> list[SearchResultItem]:
        self._calls.append(f"web:{query}")
        if self._fail_with:
            raise self._fail_with
        return [
            SearchResultItem(
                url=f"https://{self._name}.com/1", title=f"{self._name} result", source_type=SearchSourceType.WEB
            )
        ]

    async def search_images(self, query: str, limit: int, correlation_id: str) -> list[SearchResultItem]:
        self._calls.append(f"images:{query}")
        if self._fail_with:
            raise self._fail_with
        return [
            SearchResultItem(
                url=f"https://{self._name}.com/img", title=f"{self._name} image", source_type=SearchSourceType.IMAGES
            )
        ]

    async def search_news(self, query: str, limit: int, correlation_id: str) -> list[SearchResultItem]:
        self._calls.append(f"news:{query}")
        if self._fail_with:
            raise self._fail_with
        return [
            SearchResultItem(
                url=f"https://{self._name}.com/news", title=f"{self._name} news", source_type=SearchSourceType.NEWS
            )
        ]

    async def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Provider health tracking
# ---------------------------------------------------------------------------


class TestProviderHealth:
    """Tests for ProviderHealth status tracking."""

    def test_initial_state_is_healthy(self):
        health = ProviderHealth()
        assert health.status == ProviderStatus.HEALTHY
        assert health.consecutive_failures == 0
        assert not health.should_skip

    def test_success_resets_failures(self):
        health = ProviderHealth()
        health.record_failure("error 1")
        health.record_failure("error 2")
        assert health.status == ProviderStatus.DEGRADED
        health.record_success()
        assert health.status == ProviderStatus.HEALTHY
        assert health.consecutive_failures == 0

    def test_three_failures_marks_unavailable(self):
        health = ProviderHealth()
        health.record_failure("error 1")
        health.record_failure("error 2")
        assert health.status == ProviderStatus.DEGRADED
        health.record_failure("error 3")
        assert health.status == ProviderStatus.UNAVAILABLE
        assert health.should_skip  # Should skip until cooldown

    def test_to_dict_serialisation(self):
        health = ProviderHealth()
        health.record_success()
        d = health.to_dict()
        assert d["status"] == "healthy"
        assert d["requests_made"] == 1
        assert d["consecutive_failures"] == 0


# ---------------------------------------------------------------------------
# Fallback error detection
# ---------------------------------------------------------------------------


class TestFallbackErrorDetection:
    """Tests for is_fallback_error()."""

    def test_http_429_is_fallback(self):
        response = httpx.Response(429, request=httpx.Request("GET", "https://api.example.com"))
        error = httpx.HTTPStatusError("rate limited", request=response.request, response=response)
        assert is_fallback_error(error)

    def test_http_402_is_fallback(self):
        response = httpx.Response(402, request=httpx.Request("GET", "https://api.example.com"))
        error = httpx.HTTPStatusError("payment required", request=response.request, response=response)
        assert is_fallback_error(error)

    def test_http_403_without_quota_body_is_not_fallback(self):
        response = httpx.Response(403, request=httpx.Request("GET", "https://api.example.com"))
        error = httpx.HTTPStatusError("forbidden", request=response.request, response=response)
        assert not is_fallback_error(error)

    def test_http_403_with_quota_body_is_fallback(self):
        response = httpx.Response(
            403,
            request=httpx.Request("GET", "https://api.example.com"),
            content=b'{"error": "Quota exceeded for this API key"}',
        )
        error = httpx.HTTPStatusError("forbidden", request=response.request, response=response)
        assert is_fallback_error(error)

    def test_http_400_is_not_fallback(self):
        response = httpx.Response(400, request=httpx.Request("GET", "https://api.example.com"))
        error = httpx.HTTPStatusError("bad request", request=response.request, response=response)
        assert not is_fallback_error(error)

    def test_http_500_is_not_fallback(self):
        response = httpx.Response(500, request=httpx.Request("GET", "https://api.example.com"))
        error = httpx.HTTPStatusError("server error", request=response.request, response=response)
        assert not is_fallback_error(error)

    def test_captcha_provider_error_is_fallback(self):
        error = ProviderError("CAPTCHA challenge detected", provider="duckduckgo")
        assert is_fallback_error(error)

    def test_quota_provider_error_is_fallback(self):
        error = ProviderError("Quota exceeded", provider="brave")
        assert is_fallback_error(error)

    def test_generic_provider_error_is_not_fallback(self):
        error = ProviderError("API key not configured", provider="brave")
        assert not is_fallback_error(error)

    def test_connect_timeout_is_fallback(self):
        error = httpx.ConnectTimeout("connection timed out")
        assert is_fallback_error(error)

    def test_value_error_is_not_fallback(self):
        error = ValueError("bad argument")
        assert not is_fallback_error(error)


# ---------------------------------------------------------------------------
# Provider chain: search delegation
# ---------------------------------------------------------------------------


class TestProviderChain:
    """Tests for ProviderChain fallback logic."""

    @pytest.mark.asyncio
    async def test_uses_first_available_provider(self):
        p1 = MockProvider("brave")
        p2 = MockProvider("tavily")
        chain = ProviderChain(providers=[p1, p2])

        results = await chain.search("web", "test", 5, "corr-1")
        assert len(results) == 1
        assert results[0].url == "https://brave.com/1"
        assert p1._calls == ["web:test"]
        assert p2._calls == []

    @pytest.mark.asyncio
    async def test_falls_back_on_quota_error(self):
        """HTTP 429 on first provider should try second."""
        response = httpx.Response(429, request=httpx.Request("GET", "https://api.brave.com"))
        error = httpx.HTTPStatusError("rate limited", request=response.request, response=response)

        p1 = MockProvider("brave", fail_with=error)
        p2 = MockProvider("tavily")
        chain = ProviderChain(providers=[p1, p2])

        results = await chain.search("web", "test", 5, "corr-1")
        assert len(results) == 1
        assert results[0].url == "https://tavily.com/1"
        assert len(p1._calls) == 1
        assert len(p2._calls) == 1

    @pytest.mark.asyncio
    async def test_falls_back_on_captcha(self):
        """CAPTCHA error should trigger fallback."""
        error = ProviderError("CAPTCHA challenge detected", provider="duckduckgo")
        p1 = MockProvider("duckduckgo", fail_with=error)
        p2 = MockProvider("brave")
        chain = ProviderChain(providers=[p1, p2])

        results = await chain.search("web", "test", 5, "corr-1")
        assert results[0].url == "https://brave.com/1"

    @pytest.mark.asyncio
    async def test_does_not_fallback_on_non_fallback_error(self):
        """ValueError (malformed query) should NOT trigger fallback."""
        p1 = MockProvider("brave", fail_with=ValueError("bad query"))
        p2 = MockProvider("tavily")
        chain = ProviderChain(providers=[p1, p2])

        with pytest.raises(ValueError, match="bad query"):
            await chain.search("web", "test", 5, "corr-1")

        # Second provider should not have been called
        assert p2._calls == []

    @pytest.mark.asyncio
    async def test_all_providers_fail_raises_last_error(self):
        """If all providers fail with fallback errors, raises the last one."""
        response_429 = httpx.Response(429, request=httpx.Request("GET", "https://api.brave.com"))
        error1 = httpx.HTTPStatusError("rate limited", request=response_429.request, response=response_429)
        error2 = ProviderError("CAPTCHA detected", provider="duckduckgo")

        p1 = MockProvider("brave", fail_with=error1)
        p2 = MockProvider("duckduckgo", fail_with=error2)
        chain = ProviderChain(providers=[p1, p2])

        with pytest.raises(ProviderError, match="CAPTCHA"):
            await chain.search("web", "test", 5, "corr-1")

    @pytest.mark.asyncio
    async def test_skips_unavailable_providers(self):
        p1 = MockProvider("brave", available=False)
        p2 = MockProvider("tavily")
        chain = ProviderChain(providers=[p1, p2])

        results = await chain.search("web", "test", 5, "corr-1")
        assert results[0].url == "https://tavily.com/1"
        assert p1._calls == []

    @pytest.mark.asyncio
    async def test_no_available_providers_raises(self):
        p1 = MockProvider("brave", available=False)
        chain = ProviderChain(providers=[p1])

        with pytest.raises(RuntimeError, match="No search providers available"):
            await chain.search("web", "test", 5, "corr-1")

    @pytest.mark.asyncio
    async def test_skips_provider_not_supporting_source(self):
        """NotImplementedError should skip to next provider silently."""

        class ImagesOnlyProvider(MockProvider):
            async def search_web(self, query, limit, correlation_id):
                raise NotImplementedError("No web search")

        p1 = ImagesOnlyProvider("images-only")
        p2 = MockProvider("brave")
        chain = ProviderChain(providers=[p1, p2])

        results = await chain.search("web", "test", 5, "corr-1")
        assert results[0].url == "https://brave.com/1"

    @pytest.mark.asyncio
    async def test_health_tracking(self):
        response = httpx.Response(429, request=httpx.Request("GET", "https://api.brave.com"))
        error = httpx.HTTPStatusError("rate limited", request=response.request, response=response)

        p1 = MockProvider("brave", fail_with=error)
        p2 = MockProvider("tavily")
        chain = ProviderChain(providers=[p1, p2])

        await chain.search("web", "test", 5, "corr-1")

        health = chain.get_health()
        assert health["brave"]["status"] == "degraded"
        assert health["brave"]["consecutive_failures"] == 1
        assert health["tavily"]["status"] == "healthy"
        assert health["tavily"]["requests_made"] == 1

    @pytest.mark.asyncio
    async def test_close_closes_all_providers(self):
        p1 = MockProvider("brave")
        p2 = MockProvider("tavily")
        p1.close = AsyncMock()
        p2.close = AsyncMock()
        chain = ProviderChain(providers=[p1, p2])

        await chain.close()
        p1.close.assert_called_once()
        p2.close.assert_called_once()


# ---------------------------------------------------------------------------
# Registry: provider chain builder
# ---------------------------------------------------------------------------


class TestProviderRegistry:
    """Tests for build_provider_chain() factory."""

    def test_supported_providers_list(self):
        assert "brave" in SUPPORTED_PROVIDERS
        assert "tavily" in SUPPORTED_PROVIDERS
        assert "serper" in SUPPORTED_PROVIDERS
        assert "serpapi" in SUPPORTED_PROVIDERS
        assert "exa" in SUPPORTED_PROVIDERS
        assert "duckduckgo" in SUPPORTED_PROVIDERS

    def test_default_chain_is_brave(self):
        chain = build_provider_chain(brave_api_key="test-key")
        assert len(chain.providers) == 1
        assert chain.providers[0].name == "brave"

    def test_brave_without_key_adds_ddg_fallback(self):
        with patch.dict("os.environ", {"BRAVE_API_KEY": ""}, clear=False):
            chain = build_provider_chain(brave_api_key=None)
            names = [p.name for p in chain.providers]
            assert "brave" in names
            assert "duckduckgo" in names

    def test_comma_separated_string(self):
        chain = build_provider_chain("brave,tavily,duckduckgo", brave_api_key="key")
        names = [p.name for p in chain.providers]
        assert names == ["brave", "tavily", "duckduckgo"]

    def test_list_of_providers(self):
        chain = build_provider_chain(["serper", "exa"], brave_api_key="key")
        names = [p.name for p in chain.providers]
        assert names == ["serper", "exa"]

    def test_deduplicates_providers(self):
        chain = build_provider_chain("brave,brave,tavily", brave_api_key="key")
        names = [p.name for p in chain.providers]
        assert names == ["brave", "tavily"]

    def test_unknown_provider_skipped_with_warning(self):
        chain = build_provider_chain("brave,nonexistent,tavily", brave_api_key="key")
        names = [p.name for p in chain.providers]
        assert names == ["brave", "tavily"]

    def test_env_var_config(self):
        with patch.dict("os.environ", {"SUPACRAWL_SEARCH_PROVIDERS": "tavily,serper"}):
            chain = build_provider_chain(brave_api_key="key")
            names = [p.name for p in chain.providers]
            assert names == ["tavily", "serper"]


# ---------------------------------------------------------------------------
# SearchService: multi-provider integration
# ---------------------------------------------------------------------------


class TestSearchServiceMultiProvider:
    """Tests for SearchService with multi-provider configuration."""

    def test_providers_parameter_creates_chain(self):
        service = SearchService(providers="brave,tavily", brave_api_key="key")
        names = [p.name for p in service.provider_chain.providers]
        assert names == ["brave", "tavily"]

    def test_legacy_provider_parameter_still_works(self):
        service = SearchService(provider="brave", brave_api_key="key")
        assert service._provider == "brave"
        assert len(service.provider_chain.providers) == 1

    @pytest.mark.asyncio
    async def test_search_uses_chain_fallback(self):
        """Verify that search() uses the provider chain (not direct methods)."""
        service = SearchService(providers="brave,tavily", brave_api_key="key")

        # Mock the chain's search method
        mock_results = [
            SearchResultItem(url="https://tavily.com/1", title="Fallback result", source_type=SearchSourceType.WEB)
        ]
        service._chain.search = AsyncMock(return_value=mock_results)

        result = await service.search("test query", limit=5)
        assert result.success
        assert len(result.data) == 1
        assert result.data[0].url == "https://tavily.com/1"

        service._chain.search.assert_called_once()
        await service.close()

    def test_provider_chain_property(self):
        service = SearchService(providers="serper,exa", brave_api_key="key")
        chain = service.provider_chain
        assert len(chain.providers) == 2
        assert chain.providers[0].name == "serper"

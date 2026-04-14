"""
Web search service for supacrawl.

Provides search functionality using a configurable chain of search providers
with automatic fallback. Supports web, image, and news search.

Provider chain can be configured via:
- SUPACRAWL_SEARCH_PROVIDERS env var (comma-separated, e.g. "brave,tavily,serper")
- Constructor parameter
- Defaults to Brave Search only (backwards compatible)
"""

import asyncio
import logging
import os
import time
import warnings
from dataclasses import dataclass
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Literal

import httpx

from supacrawl.exceptions import generate_correlation_id
from supacrawl.models import LocaleConfig, SearchResult, SearchResultItem, SearchSourceType
from supacrawl.services.search.providers import ProviderChain
from supacrawl.services.search.registry import build_provider_chain
from supacrawl.utils import log_with_correlation

if TYPE_CHECKING:
    from supacrawl.services.scrape import ScrapeService

LOGGER = logging.getLogger(__name__)

# Type alias for source types
type SourceType = Literal["web", "images", "news"]

# Browser-like User-Agent to avoid bot detection on search engines
_SEARCH_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Complete browser header profile matching a real Chrome session.
_DEFAULT_ACCEPT_LANGUAGE = "en-US,en;q=0.9"

_BROWSER_HEADERS: dict[str, str] = {
    "User-Agent": _SEARCH_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": _DEFAULT_ACCEPT_LANGUAGE,
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Ch-Ua": '"Chromium";v="131", "Google Chrome";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Connection": "keep-alive",
}

# Default rate limits per provider (requests per second)
_PROVIDER_RATE_LIMITS: dict[str, float] = {
    "duckduckgo": 1.0,  # Aggressive bot detection — keep it slow
    "brave": 10.0,  # Well under Brave's 50 QPS limit
    "tavily": 5.0,
    "serper": 10.0,
    "serpapi": 5.0,
    "exa": 5.0,
}

# Maximum time a request will wait in the rate limit queue before failing
_RATE_LIMIT_QUEUE_TIMEOUT = 30.0  # seconds


class _RateLimiter:
    """Async rate limiter using token bucket with concurrency control."""

    def __init__(
        self,
        requests_per_second: float,
        burst: int = 3,
        queue_timeout: float = _RATE_LIMIT_QUEUE_TIMEOUT,
    ):
        self._interval = 1.0 / requests_per_second if requests_per_second > 0 else 0
        self._semaphore = asyncio.Semaphore(burst)
        self._lock = asyncio.Lock()
        self._last_request_time = 0.0
        self.requests_per_second = requests_per_second
        self.burst = burst
        self.queue_timeout = queue_timeout

    async def acquire(self, timeout: float | None = None) -> None:
        effective_timeout = timeout if timeout is not None else self.queue_timeout
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=effective_timeout)
        except TimeoutError:
            raise asyncio.TimeoutError(
                f"Search rate limit queue timeout ({effective_timeout}s). Too many concurrent search requests."
            ) from None

        try:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_request_time
                if elapsed < self._interval:
                    wait_time = self._interval - elapsed
                    await asyncio.sleep(wait_time)
                self._last_request_time = time.monotonic()
        except BaseException:
            self._semaphore.release()
            raise

    def release(self) -> None:
        self._semaphore.release()

    async def __aenter__(self) -> "_RateLimiter":
        await self.acquire()
        return self

    async def __aexit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object) -> bool:
        self.release()
        return False


@dataclass
class ScrapeOptions:
    """Options for scraping search results."""

    formats: list[Literal["markdown", "html"]] | None = None
    only_main_content: bool = True


class SearchService:
    """Web search with multi-provider fallback and optional content scraping.

    Supports configuring multiple search providers in priority order.
    On failure (quota exhausted, rate limited, CAPTCHA), automatically
    falls back to the next provider.

    Configuration:
        # Comma-separated provider priority order
        SUPACRAWL_SEARCH_PROVIDERS=brave,tavily,serper,duckduckgo

        # Each provider's API key
        BRAVE_API_KEY=xxx
        TAVILY_API_KEY=xxx
        SERPER_API_KEY=xxx

    Backwards compatible: if only ``provider`` is set (no chain), behaves
    exactly like the old single-provider mode.
    """

    def __init__(
        self,
        scrape_service: "ScrapeService | None" = None,
        provider: Literal["duckduckgo", "brave"] | None = None,
        providers: str | list[str] | None = None,
        brave_api_key: str | None = None,
        rate_limit: float | None = None,
        locale_config: LocaleConfig | None = None,
    ):
        """Initialise search service.

        Args:
            scrape_service: Optional ScrapeService for scraping results.
            provider: Legacy single provider name. If set without ``providers``,
                creates a single-provider chain (backwards compatible).
            providers: Comma-separated or list of provider names for the chain.
                Takes precedence over ``provider``. Also reads from
                SUPACRAWL_SEARCH_PROVIDERS env var.
            brave_api_key: API key for Brave Search. Also read from
                BRAVE_API_KEY environment variable.
            rate_limit: Requests per second (overrides provider default).
            locale_config: Optional locale configuration for Accept-Language.
        """
        self._scrape_service = scrape_service
        self._brave_api_key = brave_api_key or os.getenv("BRAVE_API_KEY")
        self._locale_config = locale_config

        # Build the provider chain
        if providers is not None:
            # Explicit multi-provider chain
            self._chain = build_provider_chain(providers, brave_api_key=self._brave_api_key)
        elif provider is not None:
            # Legacy single-provider mode
            if provider == "duckduckgo":
                warnings.warn(
                    "DuckDuckGo search is deprecated due to unreliable bot detection. "
                    "Switch to Brave Search (set BRAVE_API_KEY) for reliable results.",
                    DeprecationWarning,
                    stacklevel=2,
                )
            self._chain = build_provider_chain([provider], brave_api_key=self._brave_api_key)
        else:
            # Auto-detect from env or defaults
            self._chain = build_provider_chain(brave_api_key=self._brave_api_key)

        # Resolve effective provider name (for backwards compat)
        active = self._chain.active_providers
        if active:
            self._provider = active[0].name
        elif self._chain.providers:
            self._provider = self._chain.providers[0].name
        else:
            self._provider = "none"

        # Resolve rate limit
        if rate_limit is not None:
            effective_rate = rate_limit
        else:
            env_rate = os.getenv("SUPACRAWL_SEARCH_RATE_LIMIT")
            if env_rate:
                try:
                    effective_rate = float(env_rate)
                except ValueError:
                    LOGGER.warning(f"Invalid SUPACRAWL_SEARCH_RATE_LIMIT={env_rate!r}, using provider default")
                    effective_rate = _PROVIDER_RATE_LIMITS.get(self._provider, 10.0)
            else:
                effective_rate = _PROVIDER_RATE_LIMITS.get(self._provider, 10.0)

        self._rate_limiter = _RateLimiter(effective_rate)
        self._http_client: httpx.AsyncClient | None = None

        LOGGER.debug(
            f"Search rate limit: {effective_rate} req/s (primary={self._provider}, burst={self._rate_limiter.burst})"
        )

    @property
    def provider_chain(self) -> ProviderChain:
        """Access the provider chain (for health reporting)."""
        return self._chain

    def _build_headers(self) -> dict[str, str]:
        """Build browser-realistic HTTP headers."""
        headers = dict(_BROWSER_HEADERS)

        locale = self._locale_config
        if locale is None:
            env_locale = os.getenv("SUPACRAWL_LOCALE")
            if env_locale:
                locale = LocaleConfig(language=env_locale)

        if locale is not None:
            headers["Accept-Language"] = locale.get_accept_language_header()

        return headers

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with realistic browser headers."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                headers=self._build_headers(),
            )
        return self._http_client

    async def close(self) -> None:
        """Close HTTP client and all providers."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        await self._chain.close()

    async def __aenter__(self) -> "SearchService":
        return self

    async def __aexit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object) -> bool:
        await self.close()
        return False

    async def search(
        self,
        query: str,
        limit: int = 5,
        sources: list[SourceType] | None = None,
        scrape_options: ScrapeOptions | None = None,
        progress_callback: Callable[[int, int, str], Awaitable[None]] | None = None,
    ) -> SearchResult:
        """Search the web using the provider chain with automatic fallback.

        Args:
            query: Search query string.
            limit: Maximum number of results (1-10) per source type.
            sources: List of source types to search. Defaults to ["web"].
            scrape_options: Options for scraping result pages (web only).

        Returns:
            SearchResult with search results and optional scraped content.
        """
        correlation_id = generate_correlation_id()
        limit = max(1, min(limit, 10))

        if sources is None:
            sources = ["web"]

        try:
            log_with_correlation(
                LOGGER,
                logging.DEBUG,
                f"Searching with provider chain ({len(self._chain.providers)} providers)",
                correlation_id=correlation_id,
                query=query,
                limit=limit,
                sources=sources,
            )

            all_results: list[SearchResultItem] = []

            for source in sources:
                try:
                    async with self._rate_limiter:
                        results = await self._chain.search(
                            source=source,
                            query=query,
                            limit=limit,
                            correlation_id=correlation_id,
                        )
                except asyncio.TimeoutError as e:
                    log_with_correlation(
                        LOGGER,
                        logging.WARNING,
                        f"Rate limit queue timeout for source={source}",
                        correlation_id=correlation_id,
                    )
                    return SearchResult(success=False, data=[], error=str(e))

                all_results.extend(results)

            # Optionally scrape results (web results only)
            if scrape_options and self._scrape_service:
                web_results = [r for r in all_results if r.source_type == SearchSourceType.WEB]
                other_results = [r for r in all_results if r.source_type != SearchSourceType.WEB]
                if web_results:
                    web_results = await self._scrape_results(web_results, scrape_options, correlation_id, progress_callback)
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

    async def _scrape_results(
        self,
        results: list[SearchResultItem],
        options: ScrapeOptions,
        correlation_id: str,
        progress_callback: Callable[[int, int, str], Awaitable[None]] | None = None,
    ) -> list[SearchResultItem]:
        """Scrape content from search result URLs."""
        if not self._scrape_service:
            return results

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

        total = len(results)

        # Create indexed tasks to preserve original ordering
        async def scrape_indexed(idx: int, item: SearchResultItem) -> tuple[int, SearchResultItem]:
            return idx, await scrape_one(item)

        completed = 0
        indexed_results: dict[int, SearchResultItem] = {}
        tasks = [scrape_indexed(i, r) for i, r in enumerate(results)]

        for coro in asyncio.as_completed(tasks):
            idx, result_item = await coro
            indexed_results[idx] = result_item
            completed += 1
            if progress_callback:
                try:
                    await progress_callback(completed, total, result_item.url)
                except Exception:
                    pass  # Don't let callback errors break scraping

        return [indexed_results[i] for i in range(total)]

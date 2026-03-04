"""
Web search service for supacrawl.

Provides search functionality using Brave Search (recommended, requires API key)
or DuckDuckGo (deprecated fallback, unreliable due to bot detection).

Supports multiple search source types:
- web: Standard web search (default)
- images: Image search results
- news: News article search
"""

import asyncio
import logging
import os
import re
import time
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

from supacrawl.exceptions import ProviderError, generate_correlation_id
from supacrawl.models import LocaleConfig, SearchResult, SearchResultItem, SearchSourceType
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
# Missing headers beyond User-Agent are a strong fingerprinting signal
# for bot detection systems.
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
}

# Maximum time a request will wait in the rate limit queue before failing
_RATE_LIMIT_QUEUE_TIMEOUT = 30.0  # seconds


class _RateLimiter:
    """
    Async rate limiter using token bucket with concurrency control.

    Limits both concurrency (max simultaneous requests) and throughput
    (requests per second). Requests that cannot be served within the
    queue timeout raise asyncio.TimeoutError.
    """

    def __init__(
        self,
        requests_per_second: float,
        burst: int = 3,
        queue_timeout: float = _RATE_LIMIT_QUEUE_TIMEOUT,
    ):
        """
        Args:
            requests_per_second: Sustained rate limit.
            burst: Maximum concurrent requests allowed (burst capacity).
            queue_timeout: Max seconds to wait in queue before failing.
        """
        self._interval = 1.0 / requests_per_second if requests_per_second > 0 else 0
        self._semaphore = asyncio.Semaphore(burst)
        self._lock = asyncio.Lock()
        self._last_request_time = 0.0
        self.requests_per_second = requests_per_second
        self.burst = burst
        self.queue_timeout = queue_timeout

    async def acquire(self, timeout: float | None = None) -> None:
        """
        Acquire permission to make a request.

        Blocks until the rate limit allows the request, or raises
        asyncio.TimeoutError if the queue timeout is exceeded.
        """
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
        """Release the semaphore after a request completes."""
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
    """
    Web search with optional content scraping.

    Supports Brave Search (recommended, requires API key) and DuckDuckGo
    (deprecated fallback — unreliable due to aggressive bot detection).

    Example usage:
        >>> service = SearchService(brave_api_key="your-key")
        >>> result = await service.search("python web scraping", limit=5)
        >>> for item in result.data:
        ...     print(item.title, item.url)
    """

    def __init__(
        self,
        scrape_service: "ScrapeService | None" = None,
        provider: Literal["duckduckgo", "brave"] = "brave",
        brave_api_key: str | None = None,
        rate_limit: float | None = None,
        locale_config: LocaleConfig | None = None,
    ):
        """
        Initialise search service.

        Args:
            scrape_service: Optional ScrapeService for scraping results.
            provider: Search provider ("brave" or "duckduckgo").
                Defaults to "brave". If Brave is selected but no API key
                is available, falls back to DuckDuckGo with a warning.
            brave_api_key: API key for Brave Search. Also read from
                BRAVE_API_KEY environment variable.
            rate_limit: Requests per second (overrides provider default).
                Also configurable via SUPACRAWL_SEARCH_RATE_LIMIT env var.
            locale_config: Optional locale configuration. Sets
                Accept-Language header to match the configured locale
                (e.g., "en-AU,en;q=0.9"). Falls back to SUPACRAWL_LOCALE
                env var, then "en-US,en;q=0.9".
        """
        self._scrape_service = scrape_service
        self._brave_api_key = brave_api_key or os.getenv("BRAVE_API_KEY")
        self._locale_config = locale_config

        # Resolve effective provider: fall back to DDG if Brave requested but no key
        if provider == "brave" and not self._brave_api_key:
            LOGGER.warning(
                "Brave Search selected but BRAVE_API_KEY not set. "
                "Falling back to DuckDuckGo (deprecated, unreliable). "
                "Set BRAVE_API_KEY for reliable search — "
                "see https://brave.com/search/api/"
            )
            self._provider: Literal["duckduckgo", "brave"] = "duckduckgo"
        elif provider == "duckduckgo":
            warnings.warn(
                "DuckDuckGo search is deprecated due to unreliable bot detection. "
                "Switch to Brave Search (set BRAVE_API_KEY) for reliable results.",
                DeprecationWarning,
                stacklevel=2,
            )
            self._provider = "duckduckgo"
        else:
            self._provider = provider

        # Resolve rate limit: explicit > env var > provider default
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
            f"Search rate limit: {effective_rate} req/s (provider={self._provider}, burst={self._rate_limiter.burst})"
        )

    def _build_headers(self) -> dict[str, str]:
        """Build browser-realistic HTTP headers.

        Uses locale config (if provided) or SUPACRAWL_LOCALE env var
        to set Accept-Language. Falls back to en-US.
        """
        headers = dict(_BROWSER_HEADERS)

        # Resolve Accept-Language from locale config or env var
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

            # Search each source type (rate-limited per request)
            for source in sources:
                try:
                    async with self._rate_limiter:
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

        Raises:
            ProviderError: If DuckDuckGo returns a CAPTCHA challenge.
        """
        client = await self._get_client()

        params = {"q": query, "kl": "au-en"}  # Australian English locale
        response = await client.get("https://lite.duckduckgo.com/lite/", params=params)
        response.raise_for_status()

        html = response.text

        # Detect CAPTCHA/bot challenge: DDG returns HTTP 202 with an anomaly modal
        if response.status_code == 202 or "anomaly-modal" in html:
            raise ProviderError(
                "DuckDuckGo returned a CAPTCHA challenge (bot detection). Search results are unavailable.",
                provider="duckduckgo",
                correlation_id=correlation_id,
            )

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

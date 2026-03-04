"""
Search provider protocol and provider chain with automatic fallback.

Defines the interface all search providers must implement and the chain
that orchestrates fallback between providers on failure.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

from supacrawl.models import SearchResultItem

LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider status tracking
# ---------------------------------------------------------------------------


class ProviderStatus(str, Enum):
    """Runtime health status of a search provider."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"  # Intermittent errors, still trying
    UNAVAILABLE = "unavailable"  # Quota exhausted or hard failure


@dataclass
class ProviderHealth:
    """In-memory health state for a single provider within a session."""

    # After this many consecutive failures, mark unavailable
    UNAVAILABLE_THRESHOLD: int = 3
    # Re-check an unavailable provider after this many seconds
    COOLDOWN_SECONDS: float = 300.0  # 5 minutes

    status: ProviderStatus = ProviderStatus.HEALTHY
    consecutive_failures: int = 0
    last_failure_time: float = 0.0
    last_error: str | None = None
    requests_made: int = 0

    def record_success(self) -> None:
        """Record a successful request."""
        self.consecutive_failures = 0
        self.status = ProviderStatus.HEALTHY
        self.last_error = None
        self.requests_made += 1

    def record_failure(self, error: str) -> None:
        """Record a failed request and update status."""
        self.consecutive_failures += 1
        self.last_failure_time = time.monotonic()
        self.last_error = error
        self.requests_made += 1

        if self.consecutive_failures >= self.UNAVAILABLE_THRESHOLD:
            self.status = ProviderStatus.UNAVAILABLE
        else:
            self.status = ProviderStatus.DEGRADED

    @property
    def should_skip(self) -> bool:
        """Whether this provider should be skipped (unavailable and not cooled down)."""
        if self.status != ProviderStatus.UNAVAILABLE:
            return False
        elapsed = time.monotonic() - self.last_failure_time
        return elapsed < self.COOLDOWN_SECONDS

    def to_dict(self) -> dict:
        """Serialise to dict for health endpoint."""
        return {
            "status": self.status.value,
            "requests_made": self.requests_made,
            "consecutive_failures": self.consecutive_failures,
            "last_error": self.last_error,
        }


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class SearchProvider(Protocol):
    """Interface that all search providers must implement."""

    @property
    def name(self) -> str:
        """Provider identifier (e.g. 'brave', 'tavily')."""
        ...

    def is_available(self) -> bool:
        """Whether this provider has required credentials/config to operate."""
        ...

    async def search_web(self, query: str, limit: int, correlation_id: str) -> list[SearchResultItem]:
        """Search for web pages."""
        ...

    async def search_images(self, query: str, limit: int, correlation_id: str) -> list[SearchResultItem]:
        """Search for images. May raise NotImplementedError if unsupported."""
        ...

    async def search_news(self, query: str, limit: int, correlation_id: str) -> list[SearchResultItem]:
        """Search for news articles. May raise NotImplementedError if unsupported."""
        ...

    async def close(self) -> None:
        """Release resources (HTTP clients, etc.)."""
        ...


# ---------------------------------------------------------------------------
# Fallback triggers
# ---------------------------------------------------------------------------

# HTTP status codes that always indicate provider exhaustion (should fallback)
FALLBACK_HTTP_CODES = frozenset(
    {
        429,  # Too Many Requests / rate limited / quota exhausted
        402,  # Payment Required
    }
)

# 403 is ambiguous (could be invalid key or quota exceeded).
# Only fallback on 403 if the response body suggests quota exhaustion.
_403_FALLBACK_PATTERNS = ("quota", "rate limit", "exceeded", "too many")

# Strings in error messages that indicate provider exhaustion
FALLBACK_ERROR_PATTERNS = (
    "quota",
    "rate limit",
    "too many requests",
    "captcha",
    "bot detection",
    "payment required",
    "subscription",
)


def is_fallback_error(error: BaseException) -> bool:
    """Determine whether an error should trigger fallback to next provider.

    Returns True for quota/rate-limit/CAPTCHA errors.
    Returns False for malformed queries, network-wide outages, etc.
    """
    import httpx

    from supacrawl.exceptions import ProviderError

    # Check httpx HTTP status errors
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status in FALLBACK_HTTP_CODES:
            return True
        # 403 is ambiguous — only fallback if response suggests quota exhaustion
        if status == 403:
            body = error.response.text.lower()
            if any(p in body for p in _403_FALLBACK_PATTERNS):
                return True

    # Check ProviderError messages (e.g. CAPTCHA detection)
    if isinstance(error, ProviderError):
        msg = str(error).lower()
        return any(pattern in msg for pattern in FALLBACK_ERROR_PATTERNS)

    # Connection timeouts should fallback (provider may be down)
    if isinstance(error, (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.PoolTimeout)):
        return True

    # Generic timeout
    if isinstance(error, TimeoutError):
        return True

    return False


# ---------------------------------------------------------------------------
# Provider chain
# ---------------------------------------------------------------------------


@dataclass
class ProviderChain:
    """Ordered list of search providers with automatic fallback.

    Tries each provider in order. On fallback-eligible errors, moves to
    the next provider. Tracks per-provider health in memory.
    """

    providers: list[SearchProvider] = field(default_factory=list)
    _health: dict[str, ProviderHealth] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for p in self.providers:
            if p.name not in self._health:
                self._health[p.name] = ProviderHealth()

    def add(self, provider: SearchProvider) -> None:
        """Add a provider to the chain."""
        self.providers.append(provider)
        if provider.name not in self._health:
            self._health[provider.name] = ProviderHealth()

    @property
    def active_providers(self) -> list[SearchProvider]:
        """Providers that are available and not currently skipped."""
        return [p for p in self.providers if p.is_available() and not self._health[p.name].should_skip]

    def get_health(self) -> dict[str, dict]:
        """Get health status for all providers (for health endpoint)."""
        result = {}
        for p in self.providers:
            health = self._health[p.name].to_dict()
            health["available"] = p.is_available()
            result[p.name] = health
        return result

    async def search(
        self,
        source: str,
        query: str,
        limit: int,
        correlation_id: str,
    ) -> list[SearchResultItem]:
        """Search using the provider chain with fallback.

        Args:
            source: Source type ('web', 'images', 'news').
            query: Search query.
            limit: Max results.
            correlation_id: Correlation ID for logging.

        Returns:
            Search results from the first successful provider.

        Raises:
            The last error if all providers fail.
        """
        active = self.active_providers
        if not active:
            # Try all providers including cooled-down ones as last resort
            active = [p for p in self.providers if p.is_available()]

        if not active:
            raise RuntimeError(
                "No search providers available. Configure at least one provider with valid API credentials."
            )

        last_error: BaseException | None = None

        for provider in active:
            health = self._health[provider.name]
            try:
                LOGGER.debug(f"Trying provider {provider.name} for {source} search [correlation_id={correlation_id}]")

                if source == "web":
                    results = await provider.search_web(query, limit, correlation_id)
                elif source == "images":
                    results = await provider.search_images(query, limit, correlation_id)
                elif source == "news":
                    results = await provider.search_news(query, limit, correlation_id)
                else:
                    LOGGER.warning(f"Unknown source type: {source} [correlation_id={correlation_id}]")
                    return []

                health.record_success()
                return results

            except NotImplementedError:
                # Provider doesn't support this source type — skip silently
                LOGGER.debug(f"Provider {provider.name} does not support {source} search, skipping")
                continue

            except Exception as e:
                last_error = e
                error_msg = str(e)
                health.record_failure(error_msg)

                if is_fallback_error(e):
                    LOGGER.warning(
                        f"Provider {provider.name} failed ({error_msg}), "
                        f"falling back to next provider "
                        f"[correlation_id={correlation_id}]"
                    )
                    continue
                else:
                    # Non-fallback error (e.g. malformed query) — don't try other providers
                    LOGGER.error(
                        f"Provider {provider.name} failed with non-fallback error: {error_msg} "
                        f"[correlation_id={correlation_id}]"
                    )
                    raise

        # All providers failed with fallback-eligible errors
        if last_error is None:
            raise RuntimeError("All providers exhausted with no error recorded")
        raise last_error

    async def close(self) -> None:
        """Close all providers."""
        for p in self.providers:
            try:
                await p.close()
            except Exception as e:
                LOGGER.warning(f"Error closing provider {p.name}: {e}")

"""Rate limiting and politeness controls for web crawling.

This module provides rate limiting to ensure polite crawling behavior
and prevent overwhelming target servers.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import urlsplit

LOGGER = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """
    Configuration for rate limiting.

    Attributes:
        requests_per_second: Maximum requests per second (global).
        per_domain_delay: Minimum seconds between requests to same domain.
        max_concurrent: Maximum concurrent requests.
        respect_crawl_delay: Whether to respect robots.txt Crawl-delay.
        adaptive: Whether to slow down on 429 responses.
        backoff_factor: Multiplier for adaptive backoff.
        max_backoff: Maximum backoff delay in seconds.
    """

    requests_per_second: float = 2.0
    per_domain_delay: float = 1.0
    max_concurrent: int = 5
    respect_crawl_delay: bool = True
    adaptive: bool = True
    backoff_factor: float = 2.0
    max_backoff: float = 60.0


class RateLimiter:
    """
    Rate limiter for polite web crawling.

    Enforces:
    - Global requests-per-second limit
    - Per-domain delay between requests
    - Maximum concurrent requests
    - Adaptive backoff on rate limit responses
    """

    def __init__(self, config: RateLimitConfig | None = None):
        """
        Initialise rate limiter.

        Args:
            config: Rate limit configuration. Uses defaults if not provided.
        """
        self._config = config or RateLimitConfig()
        self._semaphore = asyncio.Semaphore(self._config.max_concurrent)
        self._domain_last_request: dict[str, float] = defaultdict(float)
        self._domain_delays: dict[str, float] = defaultdict(
            lambda: self._config.per_domain_delay
        )
        self._global_last_request: float = 0.0
        self._lock = asyncio.Lock()

        # Statistics
        self._total_requests: int = 0
        self._total_wait_time: float = 0.0
        self._rate_limit_hits: int = 0

    def set_domain_delay(self, domain: str, delay: float) -> None:
        """
        Set custom delay for a domain (e.g., from robots.txt Crawl-delay).

        Args:
            domain: Domain to set delay for.
            delay: Delay in seconds.
        """
        # Use the maximum of configured delay and provided delay
        self._domain_delays[domain] = max(
            delay, self._config.per_domain_delay
        )
        LOGGER.debug("Set delay for %s: %.2fs", domain, self._domain_delays[domain])

    async def acquire(self, url: str) -> None:
        """
        Wait until a request to the URL is allowed.

        This method:
        1. Acquires the concurrency semaphore
        2. Waits for global rate limit
        3. Waits for per-domain delay

        Args:
            url: URL to request.
        """
        # Wait for concurrency slot
        await self._semaphore.acquire()

        domain = urlsplit(url).netloc
        now = time.monotonic()

        async with self._lock:
            wait_time = 0.0

            # Check global rate limit
            global_interval = 1.0 / self._config.requests_per_second
            global_wait = self._global_last_request + global_interval - now
            if global_wait > 0:
                wait_time = max(wait_time, global_wait)

            # Check per-domain delay
            domain_delay = self._domain_delays[domain]
            domain_wait = self._domain_last_request[domain] + domain_delay - now
            if domain_wait > 0:
                wait_time = max(wait_time, domain_wait)

            if wait_time > 0:
                self._total_wait_time += wait_time
                LOGGER.debug("Rate limiting: waiting %.2fs for %s", wait_time, domain)

        # Wait outside the lock
        if wait_time > 0:
            await asyncio.sleep(wait_time)

        # Update timestamps
        async with self._lock:
            now = time.monotonic()
            self._global_last_request = now
            self._domain_last_request[domain] = now
            self._total_requests += 1

    def release(self, url: str) -> None:
        """
        Release rate limiter after request complete.

        Args:
            url: URL that was requested.
        """
        self._semaphore.release()

    def report_rate_limit(self, url: str) -> None:
        """
        Report a 429 rate limit response for adaptive backoff.

        Args:
            url: URL that returned 429.
        """
        if not self._config.adaptive:
            return

        domain = urlsplit(url).netloc
        current_delay = self._domain_delays[domain]
        new_delay = min(
            current_delay * self._config.backoff_factor,
            self._config.max_backoff,
        )
        self._domain_delays[domain] = new_delay
        self._rate_limit_hits += 1
        LOGGER.warning(
            "Rate limited by %s, increasing delay to %.2fs",
            domain,
            new_delay,
        )

    def report_success(self, url: str) -> None:
        """
        Report a successful response (for adaptive rate limiting).

        Gradually reduces backoff after successful requests.

        Args:
            url: URL that succeeded.
        """
        if not self._config.adaptive:
            return

        domain = urlsplit(url).netloc
        current_delay = self._domain_delays[domain]
        if current_delay > self._config.per_domain_delay:
            # Gradually reduce delay on success
            new_delay = max(
                current_delay / 1.1,  # Slow reduction
                self._config.per_domain_delay,
            )
            self._domain_delays[domain] = new_delay

    @property
    def stats(self) -> dict[str, float | int]:
        """Get rate limiting statistics."""
        return {
            "total_requests": self._total_requests,
            "total_wait_time": self._total_wait_time,
            "rate_limit_hits": self._rate_limit_hits,
            "avg_wait_time": (
                self._total_wait_time / self._total_requests
                if self._total_requests > 0
                else 0.0
            ),
        }


class RateLimitContext:
    """
    Async context manager for rate-limited requests.

    Usage:
        async with rate_limiter.context(url):
            response = await fetch(url)
    """

    def __init__(self, limiter: RateLimiter, url: str):
        self._limiter = limiter
        self._url = url

    async def __aenter__(self) -> RateLimitContext:
        await self._limiter.acquire(self._url)
        return self

    async def __aexit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: object) -> None:
        self._limiter.release(self._url)
        if exc_val is None:
            self._limiter.report_success(self._url)


def create_rate_limiter(
    requests_per_second: float | None = None,
    per_domain_delay: float | None = None,
    max_concurrent: int | None = None,
    crawl_delays: dict[str, float] | None = None,
) -> RateLimiter:
    """
    Create a rate limiter with optional overrides.

    Args:
        requests_per_second: Global RPS limit.
        per_domain_delay: Per-domain delay.
        max_concurrent: Max concurrent requests.
        crawl_delays: Domain-specific delays from robots.txt.

    Returns:
        Configured RateLimiter instance.
    """
    config = RateLimitConfig(
        requests_per_second=requests_per_second or 2.0,
        per_domain_delay=per_domain_delay or 1.0,
        max_concurrent=max_concurrent or 5,
    )
    limiter = RateLimiter(config)

    # Apply robots.txt Crawl-delay values
    if crawl_delays:
        for domain, delay in crawl_delays.items():
            limiter.set_domain_delay(domain, delay)

    return limiter


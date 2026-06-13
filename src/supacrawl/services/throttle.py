"""Per-host courtesy throttling for polite crawling.

When a crawl runs from a personal IP, firing requests back-to-back at a single
origin is the quickest way to get that IP rate-limited or banned. This module
enforces a minimum gap between requests to the same host, honouring a robots.txt
``Crawl-delay`` when the site declares one.
"""

import asyncio
import logging
import time
from urllib.parse import urlparse

LOGGER = logging.getLogger(__name__)


def host_of(url: str) -> str:
    """Return the lowercased ``host[:port]`` of a URL for throttle bucketing.

    Args:
        url: Absolute URL.

    Returns:
        The network location (host and optional port), lowercased; empty string
        when the URL has no netloc.
    """
    return (urlparse(url).netloc or "").lower()


class HostRateLimiter:
    """Enforce a minimum gap between requests to the same host.

    The gap is ``min_delay`` by default and can be raised per host (e.g. from a
    robots.txt ``Crawl-delay``). Hosts are tracked against the monotonic clock.
    A host that has never been seen has *no* recorded timestamp (``None``), so
    the first request to each host is never delayed — including on a freshly
    booted machine where ``time.monotonic()`` starts near zero.
    """

    def __init__(self, min_delay: float = 0.0) -> None:
        """Initialise the limiter.

        Args:
            min_delay: Minimum seconds between requests to any single host.
        """
        self._min_delay = max(0.0, min_delay)
        self._host_delay: dict[str, float] = {}
        self._last_request: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def set_host_delay(self, host: str, delay: float | None) -> None:
        """Record a host-specific minimum delay (e.g. from robots Crawl-delay).

        The effective delay for a host is the larger of ``min_delay`` and this
        host-specific value, so a polite site's declared delay is always honoured.

        Args:
            host: Host key as returned by :func:`host_of`.
            delay: Declared delay in seconds, or None to leave unset.
        """
        if delay and delay > 0:
            self._host_delay[host] = delay

    def _effective_delay(self, host: str) -> float:
        """Return the larger of the global minimum and any host-specific delay."""
        return max(self._min_delay, self._host_delay.get(host, 0.0))

    async def acquire(self, url: str) -> float:
        """Block until a request to *url*'s host is permitted.

        Args:
            url: The URL about to be requested.

        Returns:
            Seconds actually slept (``0.0`` when no wait was needed), for
            observability and testing.
        """
        host = host_of(url)
        delay = self._effective_delay(host)
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            if delay <= 0:
                self._last_request[host] = time.monotonic()
                return 0.0

            last = self._last_request.get(host)  # None => host never requested
            slept = 0.0
            if last is not None:
                wait = delay - (time.monotonic() - last)
                if wait > 0:
                    LOGGER.debug("Throttling %s: sleeping %.2fs (delay=%.2fs)", host, wait, delay)
                    await asyncio.sleep(wait)
                    slept = wait
            self._last_request[host] = time.monotonic()
            return slept

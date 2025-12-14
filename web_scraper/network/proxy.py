"""Proxy management and rotation for web scraping.

This module provides proxy pool management with rotation strategies,
health tracking, and failover support.
"""

from __future__ import annotations

import logging
import os
import random
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

LOGGER = logging.getLogger(__name__)


class ProxyProtocol(str, Enum):
    """Supported proxy protocols."""

    HTTP = "http"
    HTTPS = "https"
    SOCKS5 = "socks5"


class RotationStrategy(str, Enum):
    """Proxy rotation strategies."""

    ROUND_ROBIN = "round_robin"
    RANDOM = "random"
    HEALTH_BASED = "health_based"


@dataclass
class Proxy:
    """
    A proxy server configuration.

    Attributes:
        host: Proxy hostname or IP.
        port: Proxy port number.
        protocol: Proxy protocol (http, https, socks5).
        username: Optional authentication username.
        password: Optional authentication password.
    """

    host: str
    port: int
    protocol: ProxyProtocol = ProxyProtocol.HTTP
    username: str | None = None
    password: str | None = None

    @property
    def url(self) -> str:
        """Get full proxy URL."""
        auth = f"{self.username}:{self.password}@" if self.username else ""
        return f"{self.protocol.value}://{auth}{self.host}:{self.port}"

    @classmethod
    def from_url(cls, url: str) -> Proxy:
        """
        Parse proxy from URL string.

        Supports formats:
            - host:port
            - protocol://host:port
            - protocol://user:pass@host:port
        """
        from urllib.parse import urlparse

        # Handle simple host:port format
        if "://" not in url:
            url = f"http://{url}"

        parsed = urlparse(url)

        protocol = ProxyProtocol.HTTP
        if parsed.scheme:
            try:
                protocol = ProxyProtocol(parsed.scheme.lower())
            except ValueError:
                protocol = ProxyProtocol.HTTP

        host = parsed.hostname or ""
        port = parsed.port or 8080

        return cls(
            host=host,
            port=port,
            protocol=protocol,
            username=parsed.username,
            password=parsed.password,
        )

    def __str__(self) -> str:
        """String representation (without credentials)."""
        return f"{self.protocol.value}://{self.host}:{self.port}"


@dataclass
class ProxyHealth:
    """Health statistics for a proxy."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    last_error: str | None = None
    consecutive_failures: int = 0

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_requests == 0:
            return 1.0  # Assume healthy until proven otherwise
        return self.successful_requests / self.total_requests


@dataclass
class ProxyConfig:
    """
    Configuration for proxy rotation.

    Attributes:
        enabled: Whether proxy rotation is enabled.
        rotation: Rotation strategy.
        proxies: List of proxy configurations.
        min_success_rate: Minimum success rate to keep proxy active.
        fallback_direct: Whether to fall back to direct connection.
    """

    enabled: bool = False
    rotation: RotationStrategy = RotationStrategy.ROUND_ROBIN
    proxies: list[Proxy] = field(default_factory=list)
    min_success_rate: float = 0.5
    fallback_direct: bool = True

    @classmethod
    def from_env(cls) -> ProxyConfig:
        """Create config from environment variables."""
        proxy_list = os.getenv("CRAWL4AI_PROXY_LIST", "")
        proxy_file = os.getenv("CRAWL4AI_PROXY_FILE", "")
        rotation_str = os.getenv("CRAWL4AI_PROXY_ROTATION", "round_robin")

        proxies: list[Proxy] = []

        # Parse proxy list from environment
        if proxy_list:
            for url in proxy_list.split(","):
                url = url.strip()
                if url:
                    try:
                        proxies.append(Proxy.from_url(url))
                    except Exception as e:
                        LOGGER.warning("Failed to parse proxy URL %s: %s", url, e)

        # Load from file if specified
        if proxy_file:
            file_path = Path(proxy_file)
            if file_path.exists():
                proxies.extend(load_proxies_from_file(file_path))

        # Parse single proxy env var as fallback
        single_proxy = os.getenv("CRAWL4AI_PROXY", "")
        if single_proxy and not proxies:
            try:
                proxies.append(Proxy.from_url(single_proxy))
            except Exception as e:
                LOGGER.warning("Failed to parse CRAWL4AI_PROXY: %s", e)

        try:
            rotation = RotationStrategy(rotation_str.lower())
        except ValueError:
            rotation = RotationStrategy.ROUND_ROBIN

        return cls(
            enabled=bool(proxies),
            rotation=rotation,
            proxies=proxies,
            min_success_rate=float(os.getenv("CRAWL4AI_PROXY_MIN_SUCCESS_RATE", "0.5")),
            fallback_direct=os.getenv("CRAWL4AI_PROXY_FALLBACK_DIRECT", "true").lower()
            == "true",
        )


def load_proxies_from_file(path: Path) -> list[Proxy]:
    """
    Load proxies from a file (one per line).

    Args:
        path: Path to proxy list file.

    Returns:
        List of Proxy objects.
    """
    proxies: list[Proxy] = []

    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    try:
                        proxies.append(Proxy.from_url(line))
                    except Exception as e:
                        LOGGER.warning("Failed to parse proxy line '%s': %s", line, e)
    except Exception as e:
        LOGGER.error("Failed to load proxies from %s: %s", path, e)

    LOGGER.info("Loaded %d proxies from %s", len(proxies), path)
    return proxies


class ProxyRotator:
    """
    Proxy pool with rotation and health tracking.

    Supports multiple rotation strategies:
    - round_robin: Cycle through proxies in order
    - random: Select proxies randomly
    - health_based: Prefer proxies with higher success rates
    """

    def __init__(self, config: ProxyConfig | None = None) -> None:
        """
        Initialise proxy rotator.

        Args:
            config: Proxy configuration.
        """
        self._config = config or ProxyConfig.from_env()
        self._proxies = list(self._config.proxies)
        self._health: dict[str, ProxyHealth] = {
            p.url: ProxyHealth() for p in self._proxies
        }
        self._index = 0

        if self._proxies:
            LOGGER.info(
                "Proxy rotator initialised with %d proxies, strategy=%s",
                len(self._proxies),
                self._config.rotation.value,
            )

    @property
    def is_enabled(self) -> bool:
        """Check if proxy rotation is enabled and has proxies."""
        return self._config.enabled and bool(self._proxies)

    def get_proxy(self) -> Proxy | None:
        """
        Get next proxy based on rotation strategy.

        Returns:
            Next proxy to use, or None if no healthy proxies.
        """
        if not self._proxies:
            return None

        active_proxies = self._get_active_proxies()
        if not active_proxies:
            if self._config.fallback_direct:
                LOGGER.warning("All proxies unhealthy, falling back to direct connection")
                return None
            # Reset health and try again
            self._reset_health()
            active_proxies = self._proxies

        if self._config.rotation == RotationStrategy.ROUND_ROBIN:
            return self._round_robin(active_proxies)
        elif self._config.rotation == RotationStrategy.RANDOM:
            return self._random(active_proxies)
        elif self._config.rotation == RotationStrategy.HEALTH_BASED:
            return self._health_based(active_proxies)
        else:
            return self._round_robin(active_proxies)

    def _get_active_proxies(self) -> list[Proxy]:
        """Get proxies above minimum success rate."""
        return [
            p
            for p in self._proxies
            if self._health[p.url].success_rate >= self._config.min_success_rate
        ]

    def _round_robin(self, proxies: list[Proxy]) -> Proxy:
        """Select proxy using round robin."""
        self._index = self._index % len(proxies)
        proxy = proxies[self._index]
        self._index += 1
        return proxy

    def _random(self, proxies: list[Proxy]) -> Proxy:
        """Select proxy randomly."""
        return random.choice(proxies)

    def _health_based(self, proxies: list[Proxy]) -> Proxy:
        """Select proxy based on health (weighted random)."""
        # Weight by success rate
        weights = [self._health[p.url].success_rate for p in proxies]
        total = sum(weights)
        if total == 0:
            return random.choice(proxies)

        # Weighted random selection
        r = random.random() * total
        cumulative = 0.0
        for proxy, weight in zip(proxies, weights):
            cumulative += weight
            if r <= cumulative:
                return proxy
        return proxies[-1]

    def report_success(self, proxy: Proxy) -> None:
        """
        Report successful request through proxy.

        Args:
            proxy: Proxy that succeeded.
        """
        health = self._health.get(proxy.url)
        if health:
            health.total_requests += 1
            health.successful_requests += 1
            health.consecutive_failures = 0
            LOGGER.debug("Proxy %s success (rate: %.2f)", proxy, health.success_rate)

    def report_failure(self, proxy: Proxy, error: str) -> None:
        """
        Report failed request through proxy.

        Args:
            proxy: Proxy that failed.
            error: Error message.
        """
        health = self._health.get(proxy.url)
        if health:
            health.total_requests += 1
            health.failed_requests += 1
            health.consecutive_failures += 1
            health.last_error = error
            LOGGER.warning(
                "Proxy %s failed: %s (rate: %.2f, consecutive: %d)",
                proxy,
                error,
                health.success_rate,
                health.consecutive_failures,
            )

    def _reset_health(self) -> None:
        """Reset health stats for all proxies."""
        for url in self._health:
            self._health[url] = ProxyHealth()
        LOGGER.info("Reset proxy health stats")

    @property
    def stats(self) -> dict[str, list[dict] | int]:
        """Get proxy pool statistics."""
        return {
            "proxies": [
                {
                    "proxy": str(p),
                    "success_rate": self._health[p.url].success_rate,
                    "total_requests": self._health[p.url].total_requests,
                    "consecutive_failures": self._health[p.url].consecutive_failures,
                }
                for p in self._proxies
            ],
            "total_proxies": len(self._proxies),
            "active_proxies": len(self._get_active_proxies()),
        }


def create_proxy_rotator(
    proxies: list[str] | None = None,
    rotation: str = "round_robin",
) -> ProxyRotator:
    """
    Create a proxy rotator with optional overrides.

    Args:
        proxies: List of proxy URLs.
        rotation: Rotation strategy.

    Returns:
        Configured ProxyRotator instance.
    """
    config = ProxyConfig.from_env()

    if proxies:
        config.proxies = [Proxy.from_url(url) for url in proxies]
        config.enabled = True

    try:
        config.rotation = RotationStrategy(rotation.lower())
    except ValueError:
        pass

    return ProxyRotator(config)


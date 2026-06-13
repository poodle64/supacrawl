"""Tests for the per-host courtesy throttle (#119)."""

import asyncio

import pytest

from supacrawl.services.throttle import HostRateLimiter, host_of


class TestHostOf:
    """Host-key extraction for throttle bucketing."""

    def test_lowercases_host(self) -> None:
        assert host_of("https://Example.COM/path") == "example.com"

    def test_keeps_port(self) -> None:
        assert host_of("https://example.com:8080/x") == "example.com:8080"

    def test_no_netloc(self) -> None:
        assert host_of("/relative/path") == ""


@pytest.mark.asyncio
class TestHostRateLimiter:
    """Minimum-gap enforcement, with no sleep on a host's first request."""

    @staticmethod
    def _capture_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
        """Patch asyncio.sleep to record requested durations without waiting."""
        slept: list[float] = []

        async def fake_sleep(delay: float) -> None:
            slept.append(delay)

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        return slept

    async def test_first_request_never_delayed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The first request to a host is never delayed, even with a large gap.

        Regression guard for the monotonic-sentinel bug: a never-seen host has no
        recorded timestamp, so a freshly booted machine (low monotonic clock)
        must not be made to wait.
        """
        slept = self._capture_sleep(monkeypatch)
        limiter = HostRateLimiter(min_delay=10.0)

        slept_secs = await limiter.acquire("https://example.com/a")

        assert slept_secs == 0.0
        assert slept == []

    async def test_second_request_to_same_host_waits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        slept = self._capture_sleep(monkeypatch)
        limiter = HostRateLimiter(min_delay=5.0)

        await limiter.acquire("https://example.com/a")
        slept_secs = await limiter.acquire("https://example.com/b")

        assert slept_secs > 0
        assert slept and slept[0] > 0

    async def test_different_hosts_do_not_delay_each_other(self, monkeypatch: pytest.MonkeyPatch) -> None:
        slept = self._capture_sleep(monkeypatch)
        limiter = HostRateLimiter(min_delay=5.0)

        await limiter.acquire("https://a.example/x")
        slept_secs = await limiter.acquire("https://b.example/x")

        assert slept_secs == 0.0
        assert slept == []

    async def test_zero_delay_never_sleeps(self, monkeypatch: pytest.MonkeyPatch) -> None:
        slept = self._capture_sleep(monkeypatch)
        limiter = HostRateLimiter(min_delay=0.0)

        await limiter.acquire("https://example.com/a")
        slept_secs = await limiter.acquire("https://example.com/b")

        assert slept_secs == 0.0
        assert slept == []

    async def test_host_delay_raises_effective_gap(self) -> None:
        limiter = HostRateLimiter(min_delay=1.0)
        limiter.set_host_delay("example.com", 5.0)

        assert limiter._effective_delay("example.com") == 5.0
        # Other hosts keep the global minimum.
        assert limiter._effective_delay("other.example") == 1.0

    async def test_set_host_delay_ignores_none_and_zero(self) -> None:
        limiter = HostRateLimiter(min_delay=2.0)
        limiter.set_host_delay("example.com", None)
        limiter.set_host_delay("example.com", 0.0)

        # Neither call lowers the effective gap below the global minimum.
        assert limiter._effective_delay("example.com") == 2.0

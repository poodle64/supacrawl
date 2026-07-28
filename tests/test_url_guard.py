"""Outbound SSRF guard, driven rather than asserted about (#152).

These tests do not check that a guard function exists or that it "validates".
Each one attempts a real fetch through a real ``httpx.AsyncClient`` built the
way supacrawl builds its clients, against a real local listener, with DNS
stubbed so a hostname can be made to answer with an internal address. What is
observed is whether the fetch was refused or completed — the outcome, not the
control's own report.
"""

from __future__ import annotations

import asyncio
import socket
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from supacrawl.services.url_guard import (
    UnsafeUrlError,
    assert_safe_url,
    guarded_async_client,
    resolve_and_pin,
    strict_mode,
)

pytestmark = pytest.mark.unit


def _stub_resolver(mapping: dict[str, list[str]]):
    """A resolver that answers from a fixed table, so no real DNS is used."""

    def resolve(host: str, port: int) -> list[tuple]:
        try:
            addresses = mapping[host]
        except KeyError as exc:  # pragma: no cover - a test asked for an unmapped host
            raise OSError(f"unmapped host {host!r}") from exc
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, port)) for addr in addresses]

    return resolve


class _Handler(BaseHTTPRequestHandler):
    """Serves a page, and a /redirect-internal that pivots to a metadata address."""

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path == "/redirect-internal":
            self.send_response(302)
            self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
            self.end_headers()
            return
        if self.path == "/redirect-rebound":
            self.send_response(302)
            self.send_header("Location", "http://rebound.test/secret")
            self.end_headers()
            return
        body = b"<html><body>public page</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return None


@pytest.fixture
def listener() -> Iterator[int]:
    """A real HTTP server on loopback; yields its port."""
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture(autouse=True)
def default_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default (non-strict) policy unless a test opts in."""
    monkeypatch.delenv("SUPACRAWL_BLOCK_PRIVATE_NETWORKS", raising=False)


# ---------------------------------------------------------------------------
# Resolved-address checking, not URL-string checking
# ---------------------------------------------------------------------------


class TestResolvedAddressIsWhatCounts:
    def test_hostname_resolving_to_metadata_address_is_refused(self) -> None:
        """The URL contains no IP literal at all — only DNS reveals the target."""
        resolver = _stub_resolver({"metadata.example.com": ["169.254.169.254"]})

        # The cheap string check passes: nothing about this URL looks internal.
        assert_safe_url("http://metadata.example.com/latest/meta-data/")

        with pytest.raises(UnsafeUrlError) as excinfo:
            resolve_and_pin("http://metadata.example.com/latest/meta-data/", resolver)
        assert "169.254.169.254" in str(excinfo.value)

    def test_split_answer_is_refused_not_filtered(self) -> None:
        """A name answering with one public and one internal address is an attack."""
        resolver = _stub_resolver({"rebind.example.com": ["93.184.216.34", "169.254.169.254"]})

        with pytest.raises(UnsafeUrlError):
            resolve_and_pin("http://rebind.example.com/", resolver)

    def test_public_hostname_pins_to_its_address(self) -> None:
        resolver = _stub_resolver({"example.com": ["93.184.216.34"]})

        address, host = resolve_and_pin("https://example.com/page", resolver)

        assert address == "93.184.216.34"
        assert host == "example.com", "the real hostname must survive for Host and SNI"

    def test_non_http_scheme_is_refused(self) -> None:
        with pytest.raises(UnsafeUrlError):
            assert_safe_url("file:///etc/passwd")


# ---------------------------------------------------------------------------
# Driven end to end: a real client, a real socket
# ---------------------------------------------------------------------------


class TestGuardedClientRefusesAtConnectTime:
    @pytest.mark.asyncio
    async def test_fetch_of_hostname_resolving_to_metadata_never_connects(self) -> None:
        resolver = _stub_resolver({"metadata.example.com": ["169.254.169.254"]})

        async with guarded_async_client(resolver=resolver, timeout=5.0) as client:
            with pytest.raises(UnsafeUrlError):
                await client.get("http://metadata.example.com/latest/meta-data/")

    @pytest.mark.asyncio
    async def test_redirect_to_internal_address_is_refused_on_the_second_hop(self, listener: int) -> None:
        """Hop one is a legitimate public page; hop two pivots to metadata."""
        resolver = _stub_resolver({"public.test": ["127.0.0.1"]})

        async with guarded_async_client(resolver=resolver, timeout=5.0, follow_redirects=True) as client:
            # Sanity: the first hop on its own completes, so the refusal below is
            # attributable to the redirect and not to the host being unreachable.
            ok = await client.get(f"http://public.test:{listener}/")
            assert ok.status_code == 200

            with pytest.raises(UnsafeUrlError) as excinfo:
                await client.get(f"http://public.test:{listener}/redirect-internal")

        assert "169.254.169.254" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_redirect_to_a_rebinding_hostname_is_refused(self, listener: int) -> None:
        """A redirect to a *name* that resolves internally is the same attack in a hat."""
        resolver = _stub_resolver({"public.test": ["127.0.0.1"], "rebound.test": ["169.254.169.254"]})

        async with guarded_async_client(resolver=resolver, timeout=5.0, follow_redirects=True) as client:
            with pytest.raises(UnsafeUrlError):
                await client.get(f"http://public.test:{listener}/redirect-rebound")

    @pytest.mark.asyncio
    async def test_normal_public_fetch_still_succeeds(self, listener: int) -> None:
        """The guard must not break ordinary crawling."""
        resolver = _stub_resolver({"public.test": ["127.0.0.1"]})

        async with guarded_async_client(resolver=resolver, timeout=5.0) as client:
            response = await client.get(f"http://public.test:{listener}/")

        assert response.status_code == 200
        assert b"public page" in response.content


# ---------------------------------------------------------------------------
# Private targets: reachable by default, refused under the switch
# ---------------------------------------------------------------------------


class TestPrivateNetworkPolicy:
    @pytest.mark.asyncio
    async def test_private_target_reachable_by_default(self, listener: int) -> None:
        """Crawling an internal docs site is a first-class use of a self-hosted tool."""
        assert strict_mode() is False

        async with guarded_async_client(timeout=5.0) as client:
            response = await client.get(f"http://127.0.0.1:{listener}/")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_private_target_refused_under_the_switch(
        self, listener: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SUPACRAWL_BLOCK_PRIVATE_NETWORKS", "1")
        assert strict_mode() is True

        async with guarded_async_client(timeout=5.0) as client:
            with pytest.raises(UnsafeUrlError):
                await client.get(f"http://127.0.0.1:{listener}/")

    def test_rfc1918_hostname_refused_only_under_the_switch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        resolver = _stub_resolver({"internal.docs": ["10.1.2.3"]})

        address, _ = resolve_and_pin("http://internal.docs/", resolver)
        assert address == "10.1.2.3"

        monkeypatch.setenv("SUPACRAWL_BLOCK_PRIVATE_NETWORKS", "1")
        with pytest.raises(UnsafeUrlError):
            resolve_and_pin("http://internal.docs/", resolver)

    def test_metadata_stays_blocked_even_in_default_policy(self) -> None:
        """The always-blocked set is not softened by the default policy."""
        with pytest.raises(UnsafeUrlError):
            assert_safe_url("http://169.254.169.254/latest/meta-data/")


# ---------------------------------------------------------------------------
# The supacrawl fetch path itself, not just the guard module
# ---------------------------------------------------------------------------


class TestHttpFetchPathIsGuarded:
    def test_fetch_static_refuses_a_metadata_target_loudly(self) -> None:
        """Drive the real scrape fast path, not the guard in isolation.

        The refusal must RAISE, not return None: returning None disqualifies the
        fast path and hands the same blocked URL to the browser, which cannot be
        pinned — the guard would have refused nothing.
        """
        from supacrawl.services.http_fetch import fetch_static

        with pytest.raises(UnsafeUrlError):
            asyncio.run(fetch_static("http://169.254.169.254/latest/meta-data/", timeout_ms=5000))

    def test_fetch_static_refuses_an_rfc1918_target_under_the_switch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from supacrawl.services.http_fetch import fetch_static

        monkeypatch.setenv("SUPACRAWL_BLOCK_PRIVATE_NETWORKS", "1")
        with pytest.raises(UnsafeUrlError):
            asyncio.run(fetch_static("http://10.1.2.3/internal", timeout_ms=5000))

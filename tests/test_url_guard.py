"""Tests for the outbound URL safety guard (SSRF hardening, #152).

Covers:
- Non-http(s) schemes are rejected.
- Cloud-metadata / link-local IP literals are rejected (169.254.x.x, fe80::).
- Normal public URLs are allowed.
- RFC1918 private ranges are allowed by default, refused under the strict switch.
- A hostname resolving to a blocked address is refused at connect time, not
  just when the URL contains an IP literal (the rebinding window #152 exists
  to close).
- guarded_request/guarded_stream pin every redirect hop, refusing a 3xx pivot
  to an internal address exactly like a direct request to it.

Uses a stubbed resolver (patching socket.getaddrinfo) and a fake httpx client
so no real network egress or DNS is needed, per #152's test requirements.
"""

from __future__ import annotations

import os
import socket
from unittest.mock import MagicMock, patch

import pytest

from supacrawl.exceptions import ValidationError
from supacrawl.services.url_guard import (
    _is_blocked_ip,
    assert_safe_url,
    guarded_request,
    is_blocked_address,
    pinned_url,
    resolve_and_pin,
)


class TestAssertSafeUrl:
    """assert_safe_url raises ValidationError for unsafe URLs, passes safe ones."""

    def test_http_allowed(self) -> None:
        assert_safe_url("http://docs.example.com/guide")

    def test_https_allowed(self) -> None:
        assert_safe_url("https://docs.example.com/guide")

    def test_file_scheme_rejected(self) -> None:
        with pytest.raises(ValidationError, match="file"):
            assert_safe_url("file:///etc/passwd")

    def test_ftp_scheme_rejected(self) -> None:
        with pytest.raises(ValidationError, match="ftp"):
            assert_safe_url("ftp://files.example.com/data.csv")

    def test_data_scheme_rejected(self) -> None:
        with pytest.raises(ValidationError, match="data"):
            assert_safe_url("data:text/html,<h1>Hi</h1>")

    def test_javascript_scheme_rejected(self) -> None:
        with pytest.raises(ValidationError, match="javascript"):
            assert_safe_url("javascript:alert(1)")

    def test_aws_metadata_ip_rejected(self) -> None:
        with pytest.raises(ValidationError, match="blocked"):
            assert_safe_url("http://169.254.169.254/latest/meta-data/")

    def test_link_local_other_rejected(self) -> None:
        with pytest.raises(ValidationError, match="blocked"):
            assert_safe_url("http://169.254.0.1/resource")

    def test_ipv6_link_local_rejected(self) -> None:
        with pytest.raises(ValidationError, match="blocked"):
            assert_safe_url("http://[fe80::1]/resource")

    def test_public_ip_allowed(self) -> None:
        assert_safe_url("https://8.8.8.8/dns-query")

    def test_rfc1918_192168_allowed_by_default(self) -> None:
        assert_safe_url("http://192.168.1.10/docs/")

    def test_rfc1918_10_allowed_by_default(self) -> None:
        assert_safe_url("http://10.0.1.2:8080/api/")

    def test_rfc1918_172_allowed_by_default(self) -> None:
        assert_safe_url("http://172.16.0.5/internal/")

    def test_loopback_allowed_by_default(self) -> None:
        assert_safe_url("http://127.0.0.1:8080/")

    def test_hostname_allowed(self) -> None:
        """Plain hostnames are not resolved by this check; caught later by resolve_and_pin."""
        assert_safe_url("https://internal.corp/docs/")

    def test_rfc1918_ip_literal_rejected_in_strict_mode(self) -> None:
        with patch.dict(os.environ, {"SUPACRAWL_BLOCK_PRIVATE_NETWORKS": "1"}):
            with pytest.raises(ValidationError, match="blocked"):
                assert_safe_url("http://192.168.1.10/docs/")

    def test_metadata_still_rejected_in_strict_mode(self) -> None:
        with patch.dict(os.environ, {"SUPACRAWL_BLOCK_PRIVATE_NETWORKS": "1"}):
            with pytest.raises(ValidationError, match="blocked"):
                assert_safe_url("http://169.254.169.254/latest/meta-data/")


class TestIsBlockedIp:
    """_is_blocked_ip correctly classifies IP literals; non-IP hosts pass through."""

    def test_metadata_ip_blocked(self) -> None:
        assert _is_blocked_ip("169.254.169.254") is True

    def test_link_local_subnet_blocked(self) -> None:
        assert _is_blocked_ip("169.254.1.1") is True

    def test_public_ip_not_blocked(self) -> None:
        assert _is_blocked_ip("1.1.1.1") is False

    def test_rfc1918_not_blocked_by_default(self) -> None:
        assert _is_blocked_ip("10.0.0.1") is False

    def test_hostname_not_blocked(self) -> None:
        assert _is_blocked_ip("docs.example.com") is False

    def test_ipv6_link_local_blocked(self) -> None:
        assert _is_blocked_ip("fe80::1") is True

    def test_ipv6_public_not_blocked(self) -> None:
        assert _is_blocked_ip("2001:db8::1") is False


class TestIsBlockedAddress:
    """is_blocked_address checks a parsed address against the current policy."""

    def test_metadata_address_blocked(self) -> None:
        import ipaddress

        assert is_blocked_address(ipaddress.ip_address("169.254.169.254")) is True

    def test_rfc1918_address_not_blocked_by_default(self) -> None:
        import ipaddress

        assert is_blocked_address(ipaddress.ip_address("192.168.1.1")) is False

    def test_rfc1918_address_blocked_in_strict_mode(self) -> None:
        import ipaddress

        with patch.dict(os.environ, {"SUPACRAWL_BLOCK_PRIVATE_NETWORKS": "true"}):
            assert is_blocked_address(ipaddress.ip_address("192.168.1.1")) is True


class TestResolveAndPin:
    """resolve_and_pin closes the DNS-rebinding window (#152)."""

    @staticmethod
    def _stub_resolver(*addresses: str):
        """Patch getaddrinfo to answer with the given addresses."""
        infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, 443)) for a in addresses]
        return patch("supacrawl.services.url_guard.socket.getaddrinfo", return_value=infos)

    def test_public_host_returns_its_pinned_address(self) -> None:
        with self._stub_resolver("93.184.216.34"):
            address, host = resolve_and_pin("https://docs.example.com/guide")

        assert address == "93.184.216.34"
        assert host == "docs.example.com"

    def test_hostname_resolving_to_metadata_is_refused(self) -> None:
        """The attack the IP-literal check cannot see: a name pointing at IMDS."""
        with self._stub_resolver("169.254.169.254"):
            with pytest.raises(ValidationError, match="169.254.169.254"):
                resolve_and_pin("http://totally-innocent.example.com/latest/meta-data/")

    def test_hostname_resolving_to_ipv6_link_local_is_refused(self) -> None:
        infos = [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fe80::1", 443, 0, 0))]
        with patch("supacrawl.services.url_guard.socket.getaddrinfo", return_value=infos):
            with pytest.raises(ValidationError, match="link-local"):
                resolve_and_pin("http://evil.example.com/")

    def test_any_blocked_address_refuses_the_whole_fetch(self) -> None:
        """A name answering with both a public and an internal address is refused.

        Picking the address that passes would be exactly the rebinding attack:
        the resolver is free to hand the connection the other one.
        """
        with self._stub_resolver("93.184.216.34", "169.254.169.254"):
            with pytest.raises(ValidationError, match="169.254.169.254"):
                resolve_and_pin("https://rebind.example.com/")

    def test_unresolvable_host_is_refused(self) -> None:
        with patch(
            "supacrawl.services.url_guard.socket.getaddrinfo",
            side_effect=socket.gaierror("nodename nor servname"),
        ):
            with pytest.raises(ValidationError, match="Cannot resolve"):
                resolve_and_pin("https://nx.example.com/")

    def test_private_address_allowed_by_default(self) -> None:
        """Internal documentation sites stay crawlable: RFC1918 is not blocked by default."""
        with self._stub_resolver("192.168.1.10"):
            address, _host = resolve_and_pin("http://docs.internal.corp/")

        assert address == "192.168.1.10"

    def test_private_address_refused_in_strict_mode(self) -> None:
        with self._stub_resolver("192.168.1.10"), patch.dict(os.environ, {"SUPACRAWL_BLOCK_PRIVATE_NETWORKS": "1"}):
            with pytest.raises(ValidationError, match="private / loopback"):
                resolve_and_pin("http://docs.internal.corp/")

    def test_loopback_refused_in_strict_mode(self) -> None:
        with self._stub_resolver("127.0.0.1"), patch.dict(os.environ, {"SUPACRAWL_BLOCK_PRIVATE_NETWORKS": "1"}):
            with pytest.raises(ValidationError, match="private / loopback"):
                resolve_and_pin("http://localhost:8080/")

    def test_metadata_still_refused_in_strict_mode(self) -> None:
        """Strict mode adds ranges; it never drops the always-blocked ones."""
        with self._stub_resolver("169.254.169.254"), patch.dict(os.environ, {"SUPACRAWL_BLOCK_PRIVATE_NETWORKS": "1"}):
            with pytest.raises(ValidationError, match="link-local"):
                resolve_and_pin("http://evil.example.com/")

    def test_bad_scheme_refused_before_any_resolution(self) -> None:
        with patch("supacrawl.services.url_guard.socket.getaddrinfo") as mock_resolve:
            with pytest.raises(ValidationError, match="scheme"):
                resolve_and_pin("file:///etc/passwd")

        mock_resolve.assert_not_called()

    def test_no_usable_address_is_refused(self) -> None:
        """getaddrinfo answering with no parseable address is refused, not silently passed."""
        infos = [(socket.AF_UNIX, socket.SOCK_STREAM, 0, "", "/tmp/weird.sock")]
        with patch("supacrawl.services.url_guard.socket.getaddrinfo", return_value=infos):
            with pytest.raises(ValidationError, match="no usable address"):
                resolve_and_pin("https://odd.example.com/")


class TestPinnedUrl:
    """pinned_url rewrites the authority without disturbing the rest."""

    def test_replaces_host_keeping_path_and_query(self) -> None:
        assert pinned_url("https://example.com/a/b?x=1", "93.184.216.34") == "https://93.184.216.34/a/b?x=1"

    def test_preserves_explicit_port(self) -> None:
        assert pinned_url("http://example.com:8080/docs", "10.0.0.5") == "http://10.0.0.5:8080/docs"

    def test_brackets_ipv6_literal(self) -> None:
        assert pinned_url("https://example.com/x", "2606:2800:220:1::1") == "https://[2606:2800:220:1::1]/x"


class TestGuardedRequestRedirectChain:
    """guarded_request/guarded_stream guard and pin every redirect hop (#152)."""

    @staticmethod
    def _client(responses):
        """Build a fake httpx.AsyncClient whose .send() replays *responses* in order.

        Each entry is (status_code, headers dict).
        """
        calls: list[dict[str, object]] = []

        async def mock_send(request, *, stream, follow_redirects):
            status, headers = responses[len(calls)]
            calls.append(
                {
                    "url": str(request.url),
                    "headers": dict(request.headers),
                    "extensions": request.extensions,
                }
            )
            resp = MagicMock()
            resp.is_redirect = 300 <= status < 400
            resp.headers = headers
            resp.status_code = status
            resp.aclose = _async_noop
            resp.aread = _async_noop
            return resp

        class FakeClient:
            """Fake httpx.AsyncClient exposing only build_request/send."""

            def build_request(self, method, url, *, headers=None, extensions=None):
                import httpx

                return httpx.Request(method, url, headers=headers, extensions=extensions)

            send = staticmethod(mock_send)

        return FakeClient(), calls

    async def test_connects_to_the_pinned_address_with_the_real_host(self) -> None:
        client, calls = self._client([(200, {})])

        with patch(
            "supacrawl.services.url_guard.resolve_and_pin",
            return_value=("93.184.216.34", "example.com"),
        ):
            response = await guarded_request(client, "GET", "https://example.com/report.pdf")

        assert response.status_code == 200
        assert calls[0]["url"] == "https://93.184.216.34/report.pdf"
        assert calls[0]["headers"]["host"] == "example.com"
        assert calls[0]["extensions"]["sni_hostname"] == "example.com"

    async def test_redirect_to_an_internal_address_is_refused(self) -> None:
        """A 30x pivot to the metadata endpoint is refused like a direct request."""
        client, _calls = self._client([(302, {"location": "http://169.254.169.254/latest/meta-data/"})])

        def fake_resolve(url):
            if "169.254.169.254" in url:
                raise ValidationError("blocked range (link-local / cloud-metadata)", field="url", value=url)
            return ("93.184.216.34", "example.com")

        with patch("supacrawl.services.url_guard.resolve_and_pin", side_effect=fake_resolve):
            with pytest.raises(ValidationError, match="link-local"):
                await guarded_request(client, "GET", "https://example.com/report.pdf")

    async def test_each_hop_is_revalidated(self) -> None:
        """Every hop is resolved and validated, not just the first."""
        client, calls = self._client(
            [
                (302, {"location": "https://cdn.example.com/real.pdf"}),
                (200, {}),
            ]
        )
        seen = []

        def fake_resolve(url):
            seen.append(url)
            return ("93.184.216.34", "cdn.example.com" if "cdn" in url else "example.com")

        with patch("supacrawl.services.url_guard.resolve_and_pin", side_effect=fake_resolve):
            response = await guarded_request(client, "GET", "https://example.com/report.pdf")

        assert response.status_code == 200
        assert seen == ["https://example.com/report.pdf", "https://cdn.example.com/real.pdf"]
        assert len(calls) == 2

    async def test_too_many_redirects_is_refused(self) -> None:
        """A redirect chain deeper than max_redirects is refused, not followed forever."""
        client, _calls = self._client([(302, {"location": "https://example.com/next"})] * 3)

        with patch(
            "supacrawl.services.url_guard.resolve_and_pin",
            return_value=("93.184.216.34", "example.com"),
        ):
            with pytest.raises(ValidationError, match="Too many redirects"):
                await guarded_request(client, "GET", "https://example.com/start", max_redirects=2)

    async def test_redirect_with_no_location_header_is_refused(self) -> None:
        client, _calls = self._client([(302, {})])

        with patch(
            "supacrawl.services.url_guard.resolve_and_pin",
            return_value=("93.184.216.34", "example.com"),
        ):
            with pytest.raises(ValidationError, match="no Location header"):
                await guarded_request(client, "GET", "https://example.com/report.pdf")


async def _async_noop(*args, **kwargs) -> None:
    return None

"""Outbound SSRF guard for every fetch supacrawl owns (#152).

A crawler is an SSRF engine by construction: it fetches whatever URL it is
handed. Supacrawl owns the socket, so only supacrawl can refuse a target or pin
the address it connects to — a consumer that hands it URLs cannot.

Two properties matter, and neither is achieved by checking the URL string:

1. **The resolved address is what counts.** Owning a DNS record is enough to
   defeat an IP-literal check, so the guard resolves the host and refuses the
   fetch if *any* returned address is blocked — not the first that passes. A
   name answering with both a public and an internal address is a rebinding
   attack, not a fallback list.
2. **Validated is what gets connected to.** The check and the connection must
   not be separated by a window in which DNS can change its answer, so the
   validated address is pinned into the connection with the real hostname
   carried in ``Host`` and TLS SNI.

Redirects get the same treatment for free: the check lives in an httpx
transport, and httpx re-enters the transport for every hop, so a 3xx pivot to
an internal address is validated exactly like the first request was.

Policy mirrors ragify's ``RAGIFY_BLOCK_PRIVATE_NETWORKS`` so the two libraries
agree: link-local and cloud-metadata ranges are **always** refused (nobody
legitimately crawls an instance metadata endpoint), while private/RFC1918 and
loopback targets stay reachable by default — crawling an internal documentation
site is a first-class use of a self-hosted tool. A consumer accepting untrusted
URLs sets ``SUPACRAWL_BLOCK_PRIVATE_NETWORKS=1`` to refuse those too.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from collections.abc import Callable, Sequence
from urllib.parse import urlparse

import httpx

type IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
type IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

# Always refused, in every configuration. Cloud instance-metadata endpoints live
# here (169.254.169.254 on AWS/GCP/Azure) and there is no legitimate crawl of one.
_BLOCKED_NETWORKS: tuple[IPNetwork, ...] = (
    ipaddress.IPv4Network("169.254.0.0/16"),  # Link-local / IMDS
    ipaddress.IPv6Network("fe80::/10"),  # IPv6 link-local
)

# Refused only under SUPACRAWL_BLOCK_PRIVATE_NETWORKS: everything an untrusted
# URL could use to reach the host or the network it sits on.
_PRIVATE_NETWORKS: tuple[IPNetwork, ...] = (
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
    ipaddress.IPv4Network("127.0.0.0/8"),  # Loopback
    ipaddress.IPv4Network("0.0.0.0/8"),  # "This host on this network"
    ipaddress.IPv4Network("100.64.0.0/10"),  # Carrier-grade NAT
    ipaddress.IPv6Network("::1/128"),  # IPv6 loopback
    ipaddress.IPv6Network("fc00::/7"),  # IPv6 unique-local
)

_ALLOWED_SCHEMES = frozenset({"http", "https"})

STRICT_ENV = "SUPACRAWL_BLOCK_PRIVATE_NETWORKS"

# Injectable so tests can drive the guard with a stubbed resolver instead of
# real DNS. Signature matches the subset of socket.getaddrinfo used here.
type Resolver = Callable[[str, int], Sequence[tuple]]


class UnsafeUrlError(ValueError):
    """Raised when a URL, or an address it resolves to, must not be fetched.

    Subclasses ``ValueError`` so existing call sites that catch broad request
    errors keep behaving sensibly rather than crashing a crawl.
    """


def strict_mode() -> bool:
    """Whether private and loopback ranges are refused as well.

    Read at call time, not import time, so a consumer can set the switch during
    application startup without import order mattering.
    """
    return os.environ.get(STRICT_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _blocked_networks() -> tuple[IPNetwork, ...]:
    """The networks refused under the policy currently in force."""
    if strict_mode():
        return _BLOCKED_NETWORKS + _PRIVATE_NETWORKS
    return _BLOCKED_NETWORKS


def _describe(addr: IPAddress) -> str:
    """A short reason an address is refused, for the error message."""
    if any(addr in net for net in _BLOCKED_NETWORKS):
        return "link-local / cloud-metadata"
    return "private / loopback"


def is_blocked_address(addr: IPAddress) -> bool:
    """Whether an address is refused under the policy currently in force."""
    return any(addr in net for net in _blocked_networks())


def _parse_ip(host: str) -> IPAddress | None:
    """Parse a host as an IP literal, tolerating bracketed IPv6."""
    candidate = host.strip("[]")
    try:
        return ipaddress.ip_address(candidate)
    except ValueError:
        return None


def assert_safe_url(url: str) -> None:
    """Refuse a URL on scheme or on an IP literal, before any DNS lookup.

    This is the cheap half of the guard. It is not sufficient on its own — a
    hostname is enough to defeat it — which is why every fetch also goes through
    :func:`resolve_and_pin`.

    Raises:
        UnsafeUrlError: On a non-HTTP(S) scheme, a missing host, or a host that
            is an IP literal in a blocked range.
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"URL scheme {scheme!r} is not allowed (http/https only). Got: {url!r}")

    host = parsed.hostname
    if not host:
        raise UnsafeUrlError(f"URL has no host: {url!r}")

    addr = _parse_ip(host)
    if addr is not None and is_blocked_address(addr):
        raise UnsafeUrlError(f"URL host {host!r} is in a blocked range ({_describe(addr)}). Got: {url!r}")


def _resolve(host: str, port: int, resolver: Resolver | None = None) -> list[IPAddress]:
    """Resolve a hostname to every address it answers with.

    Every answer is returned, deliberately: the guard refuses if *any* of them
    is blocked rather than picking one that passes.

    Raises:
        UnsafeUrlError: When the host cannot be resolved at all.
    """
    literal = _parse_ip(host)
    if literal is not None:
        return [literal]

    lookup = resolver or (lambda h, p: socket.getaddrinfo(h, p, proto=socket.IPPROTO_TCP))
    try:
        infos = lookup(host, port)
    except OSError as exc:
        raise UnsafeUrlError(f"Could not resolve host {host!r}: {exc}") from exc

    addresses: list[IPAddress] = []
    for info in infos:
        sockaddr = info[4]
        try:
            addresses.append(ipaddress.ip_address(sockaddr[0]))
        except ValueError:
            continue

    if not addresses:
        raise UnsafeUrlError(f"Host {host!r} resolved to no usable address")
    return addresses


def resolve_and_pin(url: str, resolver: Resolver | None = None) -> tuple[str, str]:
    """Validate *url*, resolve it, and return an address safe to connect to.

    Args:
        url: The URL about to be fetched.
        resolver: Optional resolver override (tests inject a stub here).

    Returns:
        Tuple of (pinned address, host) — the literal address to connect to and
        the original hostname the caller must still send as ``Host`` and SNI so
        virtual hosting and certificate validation keep working.

    Raises:
        UnsafeUrlError: On a disallowed scheme, an unresolvable host, or any
            resolved address in a blocked range.
    """
    assert_safe_url(url)

    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)

    addresses = _resolve(host, port, resolver)
    for addr in addresses:
        if is_blocked_address(addr):
            raise UnsafeUrlError(
                f"URL host {host!r} resolves to {addr}, which is in a blocked range ({_describe(addr)}). Got: {url!r}"
            )

    return str(addresses[0]), host


class GuardedAsyncTransport(httpx.AsyncHTTPTransport):
    """httpx transport that validates and pins every request, redirects included.

    Sitting at the transport rather than at the call site is what makes redirect
    coverage structural: httpx re-enters the transport for each hop, so hop two
    is checked by the same code that checked hop one, with no call site able to
    forget.

    The outgoing request is a *copy* aimed at the pinned address; the caller's
    request object is left untouched so ``response.url`` keeps the real hostname
    and httpx resolves the next redirect against it correctly.
    """

    def __init__(self, *args: object, resolver: Resolver | None = None, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._resolver = resolver

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        address, host = resolve_and_pin(str(request.url), self._resolver)

        if request.url.host == address:
            # Already an IP literal, validated above; nothing to pin.
            return await super().handle_async_request(request)

        headers = httpx.Headers(request.headers)
        headers["Host"] = request.url.netloc.decode("ascii")

        pinned = httpx.Request(
            method=request.method,
            url=request.url.copy_with(host=address),
            headers=headers,
            stream=request.stream,
            extensions={**request.extensions, "sni_hostname": host},
        )
        return await super().handle_async_request(pinned)


def guarded_async_client(
    *,
    resolver: Resolver | None = None,
    **kwargs: object,
) -> httpx.AsyncClient:
    """Build an ``httpx.AsyncClient`` whose every request passes the guard.

    Every outbound HTTP fetch supacrawl owns is built through here, so adding a
    client is not a way to accidentally opt out of the guard.

    Args:
        resolver: Optional resolver override (tests inject a stub here).
        **kwargs: Passed straight through to ``httpx.AsyncClient``.

    Returns:
        A client that refuses blocked targets and connects only to addresses it
        validated, on the first request and on every redirect hop.
    """
    verify = kwargs.pop("verify", True)
    return httpx.AsyncClient(transport=GuardedAsyncTransport(verify=verify, resolver=resolver), **kwargs)  # type: ignore[arg-type]

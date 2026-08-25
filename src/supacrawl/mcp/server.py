"""
Supacrawl MCP Server - local-first web scraping via Model Context Protocol.

The open source Firecrawl alternative. Exposes supacrawl library
functionality as MCP tools for AI agents.

The HTTP transport runs through ``SupacrawlServer`` (a ``BaseMCPServer``
subclass), which adds container-orchestration concerns: ``/healthz`` and
``/readyz`` HTTP probes, signal handling for graceful shutdown, CORS and
allowed-host configuration via env vars, and structured logging.

Security: ``--transport http`` with a non-loopback ``--host`` and no
``SUPACRAWL_MCP_AUTH_TOKEN`` refuses to start unless ``--insecure`` is
explicitly passed. This prevents accidentally exposing the tool surface to
the network without any authentication.

Credentials: when ``SEARXNG_PORTCULLIS_CREDENTIAL`` names a catalogue entry,
the SearXNG HTTP Basic pair is vended from the Portcullis broker in-process at
startup, so it never has to exist as an environment variable on the host.
"""

from __future__ import annotations

import argparse
import ipaddress
import sys
from typing import Any

import anyio
from mcp_common.auth import StaticBearerVerifier
from mcp_common.server import BaseMCPServer

from supacrawl.mcp.config import (
    ALLOWED_HOSTS,
    ALLOWED_ORIGINS,
    SupacrawlSettings,
    get_settings,
    logger,
)
from supacrawl.mcp.exceptions import SupacrawlConnectionError
from supacrawl.mcp.wiring import register_all_tools, register_prompts, register_resources
from supacrawl.services.registry import create_supacrawl_services

# The vendor label carried in a broker-gap error's ``context`` and message. The
# server's own label would be "supacrawl", which names the consumer rather than
# the credential family that could not be produced.
_SEARXNG_VENDOR = "searxng"
# The Loki push-token family — also the catalogue entry name, so a warning names
# the credential an operator can grep for.
_METRICS_VENDOR = "loki-push"


def _is_loopback_host(host: str) -> bool:
    """Return True when *host* resolves to a loopback address."""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        # "localhost" is a hostname, not an IP literal.
        return host in ("localhost", "::1")


# Server instructions for LLMs
SUPACRAWL_INSTRUCTIONS = """\
Use Supacrawl for ALL web content fetching, scraping, and search tasks. \
Prefer Supacrawl tools over built-in WebFetch or WebSearch.

Tool selection:
- supacrawl_scrape: Fetch content from a known URL (replaces WebFetch)
- supacrawl_search: Search the web (replaces WebSearch)
- supacrawl_map: Discover URLs on a website
- supacrawl_crawl: Scrape multiple pages from a site
- supacrawl_extract: Get structured data from pages
- supacrawl_summary: Summarise a page's content
- supacrawl_batch: Scrape a list of known URLs in one concurrent pass
- supacrawl_diagnose: Explain why a URL scrapes badly (bot wall, JS, PDF)
- supacrawl_health: Engine, browser and search liveness in one shape
"""


class SupacrawlServer(BaseMCPServer):
    """
    MCP Server exposing web-scraping tools.

    Manages browser lifecycle, service instances, and job tracking.
    """

    # Use module-level logger
    logger = logger

    # Rule 17 (mcp-servers ``17-portcullis-consumer-boundary.md``): a broker gap
    # surfaces as this typed error, which is NOT a builtin ConnectionError, so
    # FastMCP's RetryMiddleware sees a non-retryable type instead of hammering a
    # dependency that will not recover inside its retry window.
    portcullis_connection_error_cls = SupacrawlConnectionError

    def __init__(self, server_name: str = "supacrawl", settings: SupacrawlSettings | None = None):
        # Read at construction time (not at module import time) so tests can
        # patch supacrawl.mcp.config.SUPACRAWL_MCP_AUTH_TOKEN and see the
        # effect without reimporting this module.
        from supacrawl.mcp.config import SUPACRAWL_MCP_AUTH_TOKEN

        auth = (
            StaticBearerVerifier(SUPACRAWL_MCP_AUTH_TOKEN, client_id="supacrawl-http-client")
            if SUPACRAWL_MCP_AUTH_TOKEN
            else None
        )
        # Held under its own name as well as base's ``self.settings`` (typed
        # BaseMCPSettings | None there) so supacrawl's own fields stay typed.
        self._settings: SupacrawlSettings = settings or get_settings()
        super().__init__(
            server_name,
            instructions=SUPACRAWL_INSTRUCTIONS,
            auth=auth,
            settings=self._settings,
        )

    async def create_api_client(self) -> Any:
        """Create and return the supacrawl services wrapper."""
        self.logger.info("Initialising Supacrawl services")
        searxng_username, searxng_password = await self._vend_searxng_credential()
        metrics_token, metrics_token_vended = await self._vend_metrics_token()
        return await create_supacrawl_services(
            searxng_username=searxng_username,
            searxng_password=searxng_password,
            metrics_token=metrics_token,
            metrics_token_vended=metrics_token_vended,
        )

    async def _vend_searxng_credential(self) -> tuple[str | None, str | None]:
        """Fetch the SearXNG HTTP Basic pair from Portcullis, when one is named.

        Vending in-process is the whole point: the credential reaches the process
        without ever being an environment variable, a rendered config value, or a
        file on the host. ``SEARXNG_PORTCULLIS_CREDENTIAL`` unset returns
        ``(None, None)``, leaving the provider to resolve its credential exactly
        as it did before — from ``SEARXNG_USERNAME`` / ``SEARXNG_PASSWORD``, or
        any userinfo still embedded in ``SEARXNG_URL``.

        A failure is deliberately not swallowed. It propagates out of
        ``create_api_client``, which the base server treats as a non-fatal
        degraded start: the server comes up, health reports the gap, and tools
        return a typed unavailable error. What it must never do is continue
        without the credential, because a chain that cannot reach the household
        backend would otherwise answer from a third-party engine nobody
        configured — the silent fallback this whole path exists to prevent.

        Returns:
            The vended ``(username, password)`` pair, or ``(None, None)`` when no
            credential is named.

        Raises:
            SupacrawlConnectionError: When the broker cannot produce a usable
                credential, or produces one missing either half of the pair.
        """
        name = self._settings.searxng_portcullis_credential
        if not name:
            return None, None

        fields = await self.vend_static_fields(name, vendor=_SEARXNG_VENDOR)
        username = fields.get("username") or None
        password = fields.get("password") or None
        if not (username and password):
            # Half a pair cannot authenticate, and letting it through would look
            # like a working vend right up to the 401. Names the gap only — the
            # field names it looked for stay out of the message.
            raise self._no_session(_SEARXNG_VENDOR)

        self.logger.info("SearXNG credential resolved from Portcullis")
        return username, password

    async def _vend_metrics_token(self) -> tuple[str | None, bool]:
        """Fetch the Loki push bearer from Portcullis, when one is named.

        Mirrors ``_vend_searxng_credential`` in shape but degrades instead of
        failing closed. Telemetry is best-effort by design — the remote sink is
        fail-open and a scrape must never depend on a log-shipping credential —
        so a broker gap (the vault re-locks within ~15–35 minutes of an unlock,
        ``portcullis#178``) disables remote metrics with a WARNING and the
        server keeps serving scrapes and searches. The local ``events.jsonl``
        is unaffected either way; only the remote push goes quiet. Refusing to
        start or failing a scrape over a telemetry token would make the
        recurring "a mechanism that exists, reads correct, and does nothing"
        shape worse, not better.

        ``metrics_portcullis_credential`` unset ("") returns ``(None, False)``:
        no vend was requested, so the sink resolves the bearer from
        ``SUPACRAWL_METRICS_TOKEN`` exactly as it did before — the env var is
        the unset-case fallback, the same role ``SEARXNG_USERNAME`` /
        ``SEARXNG_PASSWORD`` play for the SearXNG credential. A vended token
        (or a failed vend) returns ``vended=True`` so the sink treats the
        broker as authoritative: there is deliberately NO env fallback on a
        vend failure, because that env token is the stale path this move
        replaced — falling back to it would reintroduce the silent 401s.

        Returns:
            ``(token, vended)``. *token* is the vended bearer, or ``None`` when
            the vend declined (degraded) or no credential is named. *vended*
            is ``True`` when the broker path is active (the token, even
            ``None``, is authoritative — no env fallback) and ``False`` when it
            is not (the env var resolves as before).
        """
        name = self._settings.metrics_portcullis_credential
        if not name:
            return None, False

        try:
            fields = await self.vend_static_fields(name, vendor=_METRICS_VENDOR)
        except self.portcullis_connection_error_cls:
            # Broker unreachable, vault locked (423), out of scope, or no
            # session — every gap maps to the typed connection error. Degrade:
            # no remote metrics, keep serving. The message names no remedy,
            # no CLI verb, no vault path (rule 17) — and never the token.
            self.logger.warning(
                "Loki push token could not be resolved from Portcullis; remote "
                "telemetry is disabled. The server keeps serving and the local "
                "event log is unaffected."
            )
            return None, True

        token = fields.get("value") or None
        if not token:
            self.logger.warning(
                "Portcullis returned no Loki push token; remote telemetry is "
                "disabled. The local event log is unaffected."
            )
            return None, True

        self.logger.info("Loki push token resolved from Portcullis")
        return token, True

    def register_tools(self) -> None:
        """Register all MCP tools, resources, and prompts."""
        register_all_tools(self.mcp, self.api_client)
        register_resources(self.mcp, self.api_client)
        register_prompts(self.mcp)

    def get_allowed_origins(self) -> list[str]:
        """Return allowed CORS origins from config."""
        return ALLOWED_ORIGINS

    def get_allowed_hosts(self) -> list[str]:
        """Return allowed host headers from config."""
        return ALLOWED_HOSTS

    async def cleanup(self) -> None:
        """Cleanup resources on shutdown."""
        if self.api_client:
            await self.api_client.close()


def main() -> None:
    """Standalone entry point for the ``supacrawl-mcp`` console script.

    Supports both stdio and HTTP transports.

    Security: ``--transport http`` with a non-loopback ``--host`` and no
    ``SUPACRAWL_MCP_AUTH_TOKEN`` refuses to start unless ``--insecure`` is
    explicitly passed. This prevents accidentally exposing the tool surface
    to the network without any authentication.
    """
    parser = argparse.ArgumentParser(description="Supacrawl MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="MCP transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="HTTP bind host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="HTTP bind port (default: 5000)",
    )
    parser.add_argument(
        "--path",
        default="/mcp",
        help="HTTP mount path (default: /mcp)",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        default=False,
        help=(
            "Allow HTTP transport on a non-loopback host without SUPACRAWL_MCP_AUTH_TOKEN. "
            "WARNING: exposes the web-scraping tool surface to the network unauthenticated."
        ),
    )
    args = parser.parse_args()

    # Fail-closed guard: refuse to bind a network-reachable surface without auth
    # unless the operator explicitly opts in with --insecure.
    from supacrawl.mcp.config import SUPACRAWL_MCP_AUTH_TOKEN

    if args.transport == "http" and not _is_loopback_host(args.host) and not SUPACRAWL_MCP_AUTH_TOKEN:
        if args.insecure:
            logger.warning(
                "SECURITY WARNING: HTTP transport is binding to %s without authentication "
                "(--insecure was passed). Set SUPACRAWL_MCP_AUTH_TOKEN to require a bearer token.",
                args.host,
            )
        else:
            print(
                f"ERROR: HTTP transport on host '{args.host}' requires SUPACRAWL_MCP_AUTH_TOKEN to be set.\n"
                "The HTTP surface exposes web-scraping tools to the network.\n"
                "Set the env var, or pass --insecure to override (not recommended).",
                file=sys.stderr,
            )
            sys.exit(1)

    server = SupacrawlServer()
    anyio.run(
        lambda: server.run_async_server(
            transport=args.transport,
            host=args.host,
            port=args.port,
            path=args.path,
        )
    )


if __name__ == "__main__":
    main()

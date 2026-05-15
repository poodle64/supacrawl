"""Transport setup and middleware for MCP servers."""

import argparse
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, Literal

from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


def register_http_probes(
    mcp: FastMCP,
    *,
    readiness_predicate: Callable[[], Awaitable[bool]] | None = None,
    readiness_reason: Callable[[], Awaitable[str]] | None = None,
) -> None:
    """Register `/healthz` and `/readyz` HTTP routes on a FastMCP server.

    These are non-MCP HTTP endpoints intended for container orchestrators
    (Docker healthchecks, Kubernetes liveness/readiness probes) that need a
    plain HTTP probe rather than an MCP JSON-RPC round trip.

    `/healthz` always returns 200 with a small JSON envelope while the
    process is alive. It performs no I/O; suitable for liveness probes
    that fire every few seconds.

    `/readyz` returns 200 only when the server is ready to serve tool
    calls. By default a server is ready as soon as the FastMCP instance
    starts listening; servers that perform asynchronous startup (LST
    derivation, database connections, etc.) should pass a
    `readiness_predicate` that returns False until that work completes.
    Returns 503 with a structured envelope while not ready.

    Args:
        mcp: FastMCP server instance.
        readiness_predicate: Optional async callable returning ``True`` when
            the server is ready. If omitted, readiness is reported as
            ``True`` from the moment the route is registered.
        readiness_reason: Optional async callable returning a short human-
            readable description of why the server is not ready, surfaced
            in the 503 response body. Ignored when readiness is ``True``.
    """

    @mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)
    async def healthz(_request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    @mcp.custom_route("/readyz", methods=["GET"], include_in_schema=False)
    async def readyz(_request: Request) -> JSONResponse:
        if readiness_predicate is None:
            return JSONResponse({"status": "ready"})
        try:
            ready = await readiness_predicate()
        except Exception as exc:
            return JSONResponse(
                {
                    "status": "not_ready",
                    "reason": f"readiness predicate raised: {exc}",
                },
                status_code=503,
            )
        if ready:
            return JSONResponse({"status": "ready"})
        reason = "server is starting up"
        if readiness_reason is not None:
            try:
                reason = await readiness_reason()
            except Exception as exc:
                reason = f"readiness reason failed: {exc}"
        return JSONResponse(
            {"status": "not_ready", "reason": reason},
            status_code=503,
        )


def create_middleware(
    allowed_origins: list[str],
    allowed_hosts: list[str],
) -> list[Middleware]:
    """Create middleware stack for HTTP transport.

    Args:
        allowed_origins: List of allowed CORS origins (or ["*"] for all)
        allowed_hosts: List of allowed host headers (or ["*"] for all)

    Returns:
        List of middleware instances
    """
    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        ),
        Middleware(
            TrustedHostMiddleware,
            allowed_hosts=allowed_hosts,
        ),
    ]
    return middleware


async def setup_transport(
    mcp: FastMCP,
    transport: Literal["stdio", "http"] = "http",
    host: str = "0.0.0.0",
    port: int = 5000,
    path: str = "/mcp",
    allowed_origins: list[str] | None = None,
    allowed_hosts: list[str] | None = None,
) -> None:
    """Setup and run the appropriate transport.

    Args:
        mcp: FastMCP server instance
        transport: Transport type ("stdio" or "http")
        host: Host to bind to (HTTP only)
        port: Port to bind to (HTTP only)
        path: Path for HTTP transport
        allowed_origins: List of allowed CORS origins (default: ["*"])
        allowed_hosts: List of allowed host headers (default: ["*"])
    """
    transport_kwargs: dict[str, Any] = {}

    if transport == "stdio":
        logger.info(f"Starting MCP server via {transport}...")
        # No additional kwargs for stdio
    elif transport == "http":
        # Setup middleware if not provided
        if allowed_origins is None:
            allowed_origins = ["*"]
        if allowed_hosts is None:
            allowed_hosts = ["*"]

        middleware = create_middleware(allowed_origins, allowed_hosts)
        transport_kwargs = {
            "host": host,
            "port": port,
            "path": path,
            "middleware": middleware,
        }
        logger.info(f"Starting MCP server via {transport} on {host}:{port}{path}...")
    else:
        logger.error(f"Unsupported transport type: {transport}")
        raise ValueError(f"Unsupported transport: {transport}")

    # Use run_async() for async contexts (not run() which creates its own event loop)
    await mcp.run_async(transport=transport, **transport_kwargs)


def create_argument_parser(
    description: str,
    default_transport: str = "http",
    include_api_version: bool = False,
) -> argparse.ArgumentParser:
    """Create standard argument parser for MCP servers.

    Provides consistent CLI interface across all MCP servers with:
    - Transport selection (stdio or http)
    - HTTP transport configuration (host, port, path)
    - Optional API version override

    Args:
        description: Server description for argument parser
        default_transport: Default transport type (default: "http")
        include_api_version: If True, add --api-version argument (default: False)

    Returns:
        Configured ArgumentParser instance

    Examples:
        >>> parser = create_argument_parser("My MCP Server")
        >>> args = parser.parse_args(['--transport', 'stdio'])

        >>> parser = create_argument_parser("My MCP Server", include_api_version=True)
        >>> args = parser.parse_args(['--api-version', 'v2'])
    """
    parser = argparse.ArgumentParser(description=description)

    parser.add_argument(
        "--transport",
        type=str,
        default=default_transport,
        choices=["stdio", "http"],
        help=f"MCP transport protocol (stdio or http). Default: {default_transport}.",
    )

    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host for HTTP transport. Default: 0.0.0.0.",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port for HTTP transport. Default: 5000. Use 8000+ for local macOS dev.",
    )

    parser.add_argument(
        "--path",
        type=str,
        default="/mcp",
        help="Path for HTTP transport (default: /mcp)",
    )

    if include_api_version:
        parser.add_argument(
            "--api-version",
            help="Override API version",
        )

    return parser


def register_basic_health_check(
    mcp: FastMCP,
    api_version: str,
    api_client: Any | None = None,
    test_connection: Callable[[], Awaitable[bool]] | None = None,
) -> None:
    """Register a basic health check tool for container orchestration.

    Provides a minimal health check that can be extended with server-specific
    information. The basic check includes:
    - Status (healthy/degraded)
    - Timestamp
    - API version
    - API client status

    Optionally tests API connection if test_connection callback is provided.

    Args:
        mcp: FastMCP server instance
        api_version: API version string (e.g., "v2", "v24.0")
        api_client: API client instance (optional, used to determine connection status)
        test_connection: Optional async callable that returns bool indicating connection health

    Examples:
        >>> # Basic health check
        >>> register_basic_health_check(mcp, "v2", api_client)

        >>> # With connection testing
        >>> async def test_conn():
        ...     return await api_client.test_connection()
        >>> register_basic_health_check(mcp, "v2", api_client, test_conn)
    """

    @mcp.tool()
    async def health_check() -> dict[str, Any]:
        """Health check endpoint for container orchestration.

        Returns basic health status. Servers can extend this with additional
        metrics by creating their own health check function.
        """
        status: dict[str, Any] = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": api_version,
            "api_client_status": "connected" if api_client else "disconnected",
        }

        # Test connection if callback provided
        if api_client and test_connection:
            try:
                connection_ok = await test_connection()
                status["api_connection"] = "ok" if connection_ok else "failed"
                if not connection_ok:
                    status["status"] = "degraded"
            except Exception as e:
                status["api_connection"] = f"error: {e!s}"
                status["status"] = "degraded"

        return status

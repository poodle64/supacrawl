"""
Server utilities for MCP servers.

Provides transport setup, CLI argument parsing, health check registration,
and BaseMCPServer base class for unified server lifecycle management.

Usage:
    >>> from mcp_common.server import BaseMCPServer, create_argument_parser
    >>> class MyServer(BaseMCPServer):
    ...     async def create_api_client(self):
    ...         return MyApiClient()
    ...     def register_tools(self):
    ...         register_my_tools(self.mcp, self.api_client)
"""

import argparse
import asyncio
import json
import logging
import signal
import sys
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from functools import partial
from types import FrameType
from typing import Any, Literal

import anyio
from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

_MCP_COMMON_VERSION = "2026.1.0"  # Vendored version; update when syncing from mcp-servers


def create_middleware(
    allowed_origins: list[str],
    allowed_hosts: list[str],
) -> list[Middleware]:
    """
    Create middleware stack for HTTP transport.

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
    """
    Setup and run the appropriate transport.

    Args:
        mcp: FastMCP server instance
        transport: Transport type ("stdio" or "http")
        host: Host to bind to (HTTP only)
        port: Port to bind to (HTTP only)
        path: Path for HTTP transport
        allowed_origins: List of allowed CORS origins (default: ["*"])
        allowed_hosts: List of allowed host headers (default: ["*"])
    """
    logger = logging.getLogger(__name__)

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
    """
    Create standard argument parser for MCP servers.

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
    """
    Register a basic health check tool for container orchestration.

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
        """
        Health check endpoint for container orchestration.

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


class BaseMCPServer:
    """
    Base class for MCP servers with unified lifecycle management.

    Provides:
    - Signal handling for graceful shutdown
    - API client initialisation with connection testing
    - Extra services hook for additional async initialisation
    - Transport setup with customisable middleware
    - Cleanup handling
    - Standard main() entry point

    Subclasses MUST implement:
    - create_api_client() -> Any: Create and return the API client
    - register_tools(): Register MCP tools, resources, and prompts

    Subclasses MAY override:
    - validate_credentials(): Validate credentials before client creation (can raise)
    - initialize_extra_services(): Initialise additional async services (e.g., metadata)
    - get_transport_runner(): Return custom transport runner for custom middleware
    - cleanup(): Cleanup resources on shutdown
    - get_allowed_origins() / get_allowed_hosts(): Override CORS/host settings

    Example:
        >>> class MyServer(BaseMCPServer):
        ...     async def create_api_client(self):
        ...         return MyApiClient(base_url=MY_BASE_URL, api_key=MY_API_KEY)
        ...
        ...     def register_tools(self):
        ...         from wiring import register_tools
        ...         register_tools(self.mcp, self.api_client)
        ...
        >>> if __name__ == "__main__":
        ...     MyServer.main("My MCP Server")
    """

    # Class-level logger - subclasses should override with their own
    logger: logging.Logger

    def __init__(
        self,
        server_name: str,
        api_version: str | None = None,
        instructions: str | None = None,
        server_version: str | None = None,
    ):
        """
        Initialise base server.

        Args:
            server_name: Name of the server (e.g., "authentik_server")
            api_version: API version string (e.g., "v3", "v24.0")
            instructions: Instructions for LLMs on when/how to use this server's tools
            server_version: Server package version (e.g., "2026.1.0"). If not provided,
                attempts to read from importlib.metadata using server_name.
        """
        self.server_name = server_name
        self.mcp = FastMCP(server_name, instructions=instructions)
        self.api_version = api_version
        self.server_version = server_version or self._get_server_version()
        self.api_client: Any = None
        self.shutdown_event: asyncio.Event | None = None
        self._start_time = datetime.now(timezone.utc)
        self._setup_signal_handlers()
        self._register_health_endpoint()
        self._register_server_info_resource()

        # Get logger from subclass or use default
        if not hasattr(self, "logger") or self.logger is None:
            self.logger = logging.getLogger(__name__)

        self.logger.info(f"Initialising {server_name}...")

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum: int, frame: FrameType | None) -> None:
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        if self.shutdown_event:
            self.shutdown_event.set()

    def _register_health_endpoint(self) -> None:
        """Register HTTP /health endpoint for container orchestration."""
        server = self  # Capture reference for closure

        @self.mcp.custom_route("/health", methods=["GET"])
        async def health_endpoint(request: Request) -> JSONResponse:
            """HTTP health check endpoint for container orchestration."""
            uptime = (datetime.now(timezone.utc) - server._start_time).total_seconds()
            return JSONResponse(
                {
                    "status": "healthy",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "server": server.server_name,
                    "uptime_seconds": round(uptime, 1),
                }
            )

    def _get_server_version(self) -> str:
        """
        Attempt to get server version from importlib.metadata.

        Tries common package naming conventions:
        - server_name with underscores replaced by hyphens (e.g., "n8n_server" -> "n8n-server")
        - server_name with "_server" suffix removed (e.g., "n8n_server" -> "n8n-mcp")

        Returns:
            Version string if found, "unknown" otherwise
        """
        from importlib.metadata import PackageNotFoundError, version

        # Try different package name patterns
        base_name = self.server_name.replace("_server", "").replace("_", "-")
        patterns = [
            f"{base_name}-mcp",  # e.g., "n8n-mcp"
            f"mcp-{base_name}",  # e.g., "mcp-n8n"
            base_name,  # e.g., "n8n"
            self.server_name.replace("_", "-"),  # e.g., "n8n-server"
        ]

        for pattern in patterns:
            try:
                return version(pattern)
            except PackageNotFoundError:
                continue

        return "unknown"

    def _register_server_info_resource(self) -> None:
        """
        Register MCP resource exposing server version and metadata.

        Provides a standard way for MCP clients to query server information:
        - Server name and version
        - mcp-common library version
        - Python version
        - Server start time

        This helps clients verify which version is loaded after updates
        and aids debugging.
        """
        server = self  # Capture reference for closure

        @self.mcp.resource("server://info")
        def server_info() -> str:
            """
            Server version and metadata.

            Returns JSON with server name, version, mcp-common version,
            Python version, and server start time.
            """
            uptime = (datetime.now(timezone.utc) - server._start_time).total_seconds()
            return json.dumps(
                {
                    "name": server.server_name,
                    "version": server.server_version,
                    "mcp_common_version": _MCP_COMMON_VERSION,
                    "python_version": sys.version.split()[0],
                    "started_at": server._start_time.isoformat(),
                    "uptime_seconds": round(uptime, 1),
                },
                indent=2,
            )

    # =========================================================================
    # REQUIRED: Subclasses MUST implement these
    # =========================================================================

    async def create_api_client(self) -> Any:
        """
        Create and return the API client.

        Subclasses MUST implement this to create their specific API client.
        The returned client will be stored in self.api_client.

        Returns:
            API client instance

        Raises:
            Any exception if client creation fails
        """
        raise NotImplementedError("Subclasses must implement create_api_client()")

    def register_tools(self) -> None:
        """
        Register MCP tools, resources, and prompts.

        Subclasses MUST implement this to register their tools.
        Called after initialize_client() and initialize_extra_services().
        self.api_client is guaranteed to be initialised when this is called.
        """
        raise NotImplementedError("Subclasses must implement register_tools()")

    # =========================================================================
    # OPTIONAL: Subclasses MAY override these hooks
    # =========================================================================

    def validate_credentials(self) -> None:
        """
        Validate credentials before client creation.

        Override to add strict credential validation that fails startup.
        Default behaviour: no validation (servers start with warnings).

        Raises:
            Exception: If credentials are invalid and server should not start

        Example:
            >>> def validate_credentials(self):
            ...     if not API_TOKEN and not (API_EMAIL and API_KEY):
            ...         raise ConnectionError("Missing authentication credentials")
        """
        pass

    async def initialize_extra_services(self) -> None:
        """
        Initialise additional async services beyond the API client.

        Override to initialise metadata services, connection pools, etc.
        Called after create_api_client() but before register_tools().

        Example:
            >>> async def initialize_extra_services(self):
            ...     self.metadata_service = NodeMetadataService(...)
            ...     await self.metadata_service.load_metadata()
        """
        pass

    async def get_transport_runner(
        self,
        transport: str,
        host: str,
        port: int,
        path: str,
    ) -> Callable[[], Awaitable[None]] | None:
        """
        Return custom transport runner for custom middleware needs.

        Override to provide custom transport setup (e.g., OAuth middleware).
        Return None to use the default setup_transport().

        Args:
            transport: Transport type ("stdio" or "http")
            host: Host to bind to
            port: Port to bind to
            path: Path for HTTP transport

        Returns:
            Async callable to run transport, or None for default behaviour

        Example:
            >>> async def get_transport_runner(self, transport, host, port, path):
            ...     if transport == "http":
            ...         return partial(run_with_oauth_middleware, self.mcp, host, port, path)
            ...     return None
        """
        return None

    async def cleanup(self) -> None:
        """
        Cleanup resources on shutdown.

        Override to cleanup server-specific resources.
        Called in finally block, so always runs.
        """
        if self.api_client and hasattr(self.api_client, "close"):
            try:
                await self.api_client.close()
                self.logger.info("API client closed")
            except Exception as e:
                self.logger.error(f"Error closing API client: {e}", exc_info=True)
            finally:
                self.api_client = None
        self.logger.info("Cleanup complete")

    def get_allowed_origins(self) -> list[str]:
        """Return allowed CORS origins. Override to customise."""
        return ["*"]

    def get_allowed_hosts(self) -> list[str]:
        """Return allowed host headers. Override to customise."""
        return ["*"]

    # =========================================================================
    # CORE: Lifecycle methods (generally don't override)
    # =========================================================================

    async def initialize_client(self) -> None:
        """
        Full client initialisation sequence.

        1. Validate credentials (may raise)
        2. Create API client
        3. Test connection (warn on failure, don't fail startup)
        4. Initialise extra services

        Generally don't override - override the hooks instead.
        """
        if self.api_client is not None:
            self.logger.info("API client already initialised.")
            return

        try:
            # 1. Validate credentials (may raise to fail startup)
            self.validate_credentials()

            # 2. Create API client
            self.logger.info(f"Creating API client for {self.server_name}...")
            self.api_client = await self.create_api_client()
            self.logger.info("API client created successfully.")

            # 3. Test connection (warn on failure, don't fail startup)
            await self._test_connection()

            # 4. Initialise extra services
            await self.initialize_extra_services()

        except Exception as e:
            self.logger.error(f"Failed to initialise API client: {e}", exc_info=True)
            self.api_client = None
            raise

    async def _test_connection(self) -> None:
        """Test API connection - warn on failure, don't fail startup."""
        if not self.api_client or not hasattr(self.api_client, "test_connection"):
            return

        self.logger.info("Testing API connection...")
        try:
            connection_ok = await self.api_client.test_connection()
            if connection_ok:
                self.logger.info("✓ Connection test passed - API is reachable and authenticated")
        except Exception as e:
            self.logger.warning(
                f"⚠ Connection test failed - API may be temporarily unavailable: {e}. "
                f"Server will start but operations may fail until connection is restored."
            )

    async def run_async_server(
        self,
        transport: Literal["stdio", "http"] = "http",
        host: str = "0.0.0.0",
        port: int = 5000,
        path: str = "/mcp",
    ) -> None:
        """
        Initialise client, register tools, and run the MCP server.

        This method should be the target for anyio.run().

        Args:
            transport: Transport type ("stdio" or "http")
            host: Host to bind to (HTTP only)
            port: Port to bind to (HTTP only)
            path: Path for HTTP transport
        """
        self.shutdown_event = asyncio.Event()

        try:
            # 1. Initialise client (includes extra services)
            await self.initialize_client()

            # 2. Register tools
            if self.api_client is None:
                raise RuntimeError("API client must be initialised before registering tools.")
            self.register_tools()

            # 3. Run transport (custom or default)
            custom_runner = await self.get_transport_runner(transport, host, port, path)
            if custom_runner:
                await custom_runner()
            else:
                await setup_transport(
                    self.mcp,
                    transport=transport,
                    host=host,
                    port=port,
                    path=path,
                    allowed_origins=self.get_allowed_origins(),
                    allowed_hosts=self.get_allowed_hosts(),
                )

        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt, shutting down...")
        except Exception as e:
            self.logger.error(f"Server error: {e}", exc_info=True)
            raise
        finally:
            await self.cleanup()

    # =========================================================================
    # ENTRY POINT: Standard main() method
    # =========================================================================

    @classmethod
    def main(
        cls,
        description: str,
        default_transport: str = "http",
        include_api_version: bool = False,
        **server_kwargs: Any,
    ) -> None:
        """
        Standard main entry point for MCP servers.

        Handles argument parsing, server creation, and async execution.

        Args:
            description: Server description for CLI help
            default_transport: Default transport (default: "http")
            include_api_version: Whether to include --api-version argument
            **server_kwargs: Additional kwargs passed to server __init__

        Example:
            >>> if __name__ == "__main__":
            ...     MyServer.main("My MCP Server")

            >>> # With API version support
            >>> if __name__ == "__main__":
            ...     MyServer.main("My MCP Server", include_api_version=True)
        """
        parser = create_argument_parser(
            description,
            default_transport=default_transport,
            include_api_version=include_api_version,
        )
        args = parser.parse_args()

        # Pass api_version if included
        if include_api_version and hasattr(args, "api_version") and args.api_version:
            server_kwargs["api_version"] = args.api_version

        server = cls(**server_kwargs)
        exit_code = 0

        try:
            anyio.run(
                partial(
                    server.run_async_server,
                    transport=args.transport,
                    host=args.host,
                    port=args.port,
                    path=args.path,
                )
            )
            server.logger.info("Server finished gracefully.")
        except KeyboardInterrupt:
            server.logger.info("Server execution interrupted by user.")
        except Exception as e:
            server.logger.critical(f"Server failed: {e}", exc_info=True)
            exit_code = 1
        finally:
            server.logger.info(f"Server exiting with code {exit_code}.")
            if exit_code != 0:
                sys.exit(exit_code)

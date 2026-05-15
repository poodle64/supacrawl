"""Base class for MCP servers with unified lifecycle management."""

import asyncio
import inspect
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

# Detect FastMCP 3.x at import time by checking for a 3.x-only constructor kwarg.
# Cached so the inspect call runs once per process, not on every server construction.
_FASTMCP_3X: bool = "on_duplicate" in inspect.signature(FastMCP.__init__).parameters

from .lifecycle import (  # noqa: E402  - imports follow runtime version detection
    cleanup,
    get_server_version,
    initialize_client,
    register_health_endpoint,
    register_server_info_resource,
)
from .transport import (  # noqa: E402  - imports follow runtime version detection
    create_argument_parser,
    register_http_probes,
    setup_transport,
)


class BaseMCPServer:
    """Base class for MCP servers with unified lifecycle management.

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
        *,
        strict_input_validation: bool = True,
        mask_error_details: bool | None = None,
        on_duplicate: str = "error",
    ):
        """Initialise base server.

        Args:
            server_name: Name of the server (e.g., "authentik_server")
            api_version: API version string (e.g., "v3", "v24.0")
            instructions: Instructions for LLMs on when/how to use this server's tools
            server_version: Server package version (e.g., "2026.1.0"). If not provided,
                attempts to read from importlib.metadata using server_name.
            strict_input_validation: If True (default), FastMCP validates tool inputs
                against the full Pydantic schema and rejects extra fields. Catches
                LLM-side hallucinations before they reach the upstream API. Highly
                recommended for servers that touch real-world state (trading,
                payments, infra). FastMCP 3.x feature; ignored on 2.x.
            mask_error_details: If True, exception messages and tracebacks are
                stripped from tool error responses before they reach the client.
                Pairs with structured error envelopes that already classify errors
                with stable codes. FastMCP 3.x feature; pass None to use FastMCP's
                env-var default.
            on_duplicate: Behaviour when two tools share a name. "error" (default)
                raises immediately; "warn" logs; "replace" silently overwrites.
                Production-safe default is "error" so module refactors do not
                silently drop tools. FastMCP 3.x feature.
        """
        self.server_name = server_name
        self.api_version = api_version
        self.server_version = server_version or get_server_version(server_name)
        fastmcp_kwargs: dict[str, Any] = {
            "instructions": instructions,
            "version": self.server_version,
        }
        if _FASTMCP_3X:
            fastmcp_kwargs["strict_input_validation"] = strict_input_validation
            fastmcp_kwargs["on_duplicate"] = on_duplicate
            if mask_error_details is not None:
                fastmcp_kwargs["mask_error_details"] = mask_error_details
        self.mcp = FastMCP(server_name, **fastmcp_kwargs)
        self.api_client: Any = None
        self.shutdown_event: asyncio.Event | None = None
        self._start_time = datetime.now(timezone.utc)
        self._setup_signal_handlers()
        register_health_endpoint(self.mcp, server_name, self._start_time)
        register_server_info_resource(self.mcp, server_name, self.server_version, self._start_time)
        register_http_probes(
            self.mcp,
            readiness_predicate=self._default_readiness_predicate,
            readiness_reason=self._default_readiness_reason,
        )

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

    async def create_api_client(self) -> Any:
        """Create and return the API client.

        Subclasses MUST implement this to create their specific API client.
        The returned client will be stored in self.api_client.

        Returns:
            API client instance

        Raises:
            Any exception if client creation fails
        """
        raise NotImplementedError("Subclasses must implement create_api_client()")

    def register_tools(self) -> None:
        """Register MCP tools, resources, and prompts.

        Subclasses MUST implement this to register their tools.
        Called after initialize_client() and initialize_extra_services().
        self.api_client is guaranteed to be initialised when this is called.
        """
        raise NotImplementedError("Subclasses must implement register_tools()")

    def validate_credentials(self) -> None:
        """Validate credentials before client creation.

        Override to add strict credential validation that fails startup.
        Default behaviour: no validation (servers start with warnings).

        Raises:
            Exception: If credentials are invalid and server should not start

        Example:
            >>> def validate_credentials(self):
            ...     if not API_TOKEN and not (API_EMAIL and API_KEY):
            ...         raise ConnectionError("Missing authentication credentials")
        """

    async def initialize_extra_services(self) -> None:
        """Initialise additional async services beyond the API client.

        Override to initialise metadata services, connection pools, etc.
        Called after create_api_client() but before register_tools().

        Example:
            >>> async def initialize_extra_services(self):
            ...     self.metadata_service = NodeMetadataService(...)
            ...     await self.metadata_service.load_metadata()
        """

    async def get_transport_runner(
        self,
        transport: str,
        host: str,
        port: int,
        path: str,
    ) -> Callable[[], Awaitable[None]] | None:
        """Return custom transport runner for custom middleware needs.

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
        """Cleanup resources on shutdown.

        Override to cleanup server-specific resources.
        Called in finally block, so always runs.
        """
        await cleanup(self.api_client)
        self.api_client = None

    async def _default_readiness_predicate(self) -> bool:
        """Default `/readyz` readiness check.

        Reports ready when the API client has been constructed. Servers that
        do additional async startup (e.g. background LST derivation in the
        IBKR SDK) commonly expose an `asyncio.Event` named ``ready`` and a
        ``connect_error`` attribute on the API client; we honour those when
        present so /readyz reflects real startup state without per-server
        wiring. Subclasses can override for richer logic.
        """
        client = self.api_client
        if client is None:
            return False
        ready_event = getattr(client, "ready", None)
        if ready_event is not None and hasattr(ready_event, "is_set"):
            if not ready_event.is_set():
                return False
        if getattr(client, "connect_error", None) is not None:
            return False
        return True

    async def _default_readiness_reason(self) -> str:
        """Short human-readable description of why /readyz is 503."""
        client = self.api_client
        if client is None:
            return "API client has not been constructed yet"
        ready_event = getattr(client, "ready", None)
        if ready_event is not None and hasattr(ready_event, "is_set") and not ready_event.is_set():
            return "API client is still completing async startup"
        connect_error = getattr(client, "connect_error", None)
        if connect_error is not None:
            return f"API client startup failed: {connect_error}"
        return "server is starting up"

    def get_allowed_origins(self) -> list[str]:
        """Return allowed CORS origins. Override to customise."""
        return ["*"]

    def get_allowed_hosts(self) -> list[str]:
        """Return allowed host headers. Override to customise."""
        return ["*"]

    async def initialize_client(self) -> None:
        """Full client initialisation sequence.

        1. Validate credentials (may raise)
        2. Create API client
        3. Test connection (warn on failure, don't fail startup)
        4. Initialise extra services

        Generally don't override - override the hooks instead.
        """
        self.api_client = await initialize_client(
            self.api_client,
            self.server_name,
            self.validate_credentials,
            self.create_api_client,
            self.initialize_extra_services,
        )

    async def run_async_server(
        self,
        transport: Literal["stdio", "http"] = "http",
        host: str = "0.0.0.0",
        port: int = 5000,
        path: str = "/mcp",
    ) -> None:
        """Initialise client, register tools, and run the MCP server.

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

    @classmethod
    def main(
        cls,
        description: str,
        default_transport: str = "http",
        include_api_version: bool = False,
        **server_kwargs: Any,
    ) -> None:
        """Standard main entry point for MCP servers.

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

"""Server lifecycle management including initialisation and cleanup."""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


def _get_mcp_common_version() -> str:
    """Read mcp_common.__version__ lazily to avoid circular imports.

    Vendored sub-package layouts (e.g. supacrawl.mcp.mcp_common) cannot
    do a top-level relative import of __version__ from the parent
    package because lifecycle.py is imported during the parent's own
    __init__ execution. Reading it inside the function defers the
    lookup until after package initialisation completes.
    """
    import importlib

    parent_package = __package__.rsplit(".", 1)[0]
    return getattr(importlib.import_module(parent_package), "__version__", "unknown")


def register_health_endpoint(mcp: FastMCP, server_name: str, start_time: datetime) -> None:
    """Register HTTP /health endpoint for container orchestration.

    Args:
        mcp: FastMCP server instance
        server_name: Name of the server
        start_time: Server start timestamp
    """

    @mcp.custom_route("/health", methods=["GET"])
    async def health_endpoint(request: Request) -> JSONResponse:
        """HTTP health check endpoint for container orchestration."""
        uptime = (datetime.now(timezone.utc) - start_time).total_seconds()
        return JSONResponse(
            {
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "server": server_name,
                "uptime_seconds": round(uptime, 1),
            }
        )


def get_server_version(server_name: str) -> str:
    """Attempt to get server version from importlib.metadata.

    Tries common package naming conventions:
    - server_name with underscores replaced by hyphens (e.g., "n8n_server" -> "n8n-server")
    - server_name with "_server" suffix removed (e.g., "n8n_server" -> "n8n-mcp")

    Args:
        server_name: Name of the server

    Returns:
        Version string if found, "unknown" otherwise
    """
    from importlib.metadata import PackageNotFoundError, version

    # Try different package name patterns
    base_name = server_name.replace("_server", "").replace("_", "-")
    patterns = [
        f"{base_name}-mcp",  # e.g., "n8n-mcp"
        f"mcp-{base_name}",  # e.g., "mcp-n8n"
        base_name,  # e.g., "n8n"
        server_name.replace("_", "-"),  # e.g., "n8n-server"
    ]

    for pattern in patterns:
        try:
            return version(pattern)
        except PackageNotFoundError:
            continue

    return "unknown"


def register_server_info_resource(
    mcp: FastMCP,
    server_name: str,
    server_version: str,
    start_time: datetime,
) -> None:
    """Register MCP resource exposing server version and metadata.

    Provides a standard way for MCP clients to query server information:
    - Server name and version
    - mcp-common library version
    - Python version
    - Server start time

    This helps clients verify which version is loaded after updates
    and aids debugging.

    Args:
        mcp: FastMCP server instance
        server_name: Name of the server
        server_version: Server version string
        start_time: Server start timestamp
    """

    @mcp.resource("server://info")
    def server_info() -> str:
        """Server version and metadata.

        Returns JSON with server name, version, mcp-common version,
        Python version, and server start time.
        """
        uptime = (datetime.now(timezone.utc) - start_time).total_seconds()
        return json.dumps(
            {
                "name": server_name,
                "version": server_version,
                "mcp_common_version": _get_mcp_common_version(),
                "python_version": sys.version.split()[0],
                "started_at": start_time.isoformat(),
                "uptime_seconds": round(uptime, 1),
            },
            indent=2,
        )


async def initialize_client(
    api_client: Any,
    server_name: str,
    validate_credentials: Any,
    create_api_client: Any,
    initialize_extra_services: Any,
) -> Any:
    """Full client initialisation sequence.

    1. Validate credentials (may raise)
    2. Create API client
    3. Test connection (warn on failure, don't fail startup)
    4. Initialise extra services

    Args:
        api_client: Current API client (None if not initialised)
        server_name: Name of the server
        validate_credentials: Callable to validate credentials
        create_api_client: Callable to create API client
        initialize_extra_services: Callable to initialise extra services

    Returns:
        Initialised API client

    Raises:
        Exception: If initialisation fails
    """
    if api_client is not None:
        logger.info("API client already initialised.")
        return api_client

    try:
        # 1. Validate credentials (may raise to fail startup)
        validate_credentials()

        # 2. Create API client
        logger.info(f"Creating API client for {server_name}...")
        api_client = await create_api_client()
        logger.info("API client created successfully.")

        # 3. Test connection (warn on failure, don't fail startup)
        await _test_connection(api_client)

        # 4. Initialise extra services
        await initialize_extra_services()

        return api_client

    except Exception as e:
        logger.error(f"Failed to initialise API client: {e}", exc_info=True)
        raise


async def _test_connection(api_client: Any) -> None:
    """Test API connection; warn on failure, don't fail startup.

    Args:
        api_client: API client instance
    """
    if not api_client or not hasattr(api_client, "test_connection"):
        return

    logger.info("Testing API connection...")
    try:
        connection_ok = await api_client.test_connection()
        if connection_ok:
            logger.info("Connection test passed - API is reachable and authenticated")
    except Exception as e:
        logger.warning(
            f"Connection test failed - API may be temporarily unavailable: {e}. "
            f"Server will start but operations may fail until connection is restored."
        )


async def cleanup(api_client: Any) -> None:
    """Cleanup resources on shutdown.

    Args:
        api_client: API client instance to clean up
    """
    if api_client and hasattr(api_client, "close"):
        try:
            await api_client.close()
            logger.info("API client closed")
        except Exception as e:
            logger.error(f"Error closing API client: {e}", exc_info=True)
    logger.info("Cleanup complete")

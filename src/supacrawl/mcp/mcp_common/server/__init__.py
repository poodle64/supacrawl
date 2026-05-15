"""Server utilities for MCP servers.

Provides transport setup, CLI argument parsing, health check registration,
and BaseMCPServer base class for unified server lifecycle management.
"""

from .base import BaseMCPServer
from .transport import (
    create_argument_parser,
    create_middleware,
    register_basic_health_check,
    setup_transport,
)

__all__ = [
    # Base server
    "BaseMCPServer",
    # Transport
    "setup_transport",
    "create_middleware",
    "create_argument_parser",
    "register_basic_health_check",
]

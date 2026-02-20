"""
MCP Common - Shared utilities for MCP servers.

This package provides common utilities used across all MCP servers:
- Correlation ID generation and tracking
- Input validation utilities
- Base exception hierarchy
- Structured logging setup
- Configuration validation
- Server utilities (transport, CLI, health checks)
- Tool registration with metadata preservation
"""

from .config import parse_comma_separated, validate_base_url
from .correlation import (
    clear_correlation_id,
    generate_correlation_id,
    get_correlation_id,
    set_correlation_id,
)
from .exceptions import (
    MCPClientError,
    MCPConnectionError,
    MCPError,
    MCPForbiddenError,
    MCPNotFoundError,
    MCPRateLimitError,
    MCPServerError,
    MCPTimeoutError,
    MCPUnauthorizedError,
    MCPValidationError,
    log_tool_exception,
    map_status_to_exception,
)
from .logging import (
    SENSITIVE_KEYS,
    SENSITIVE_PATTERNS,
    JSONFormatter,
    redact_sensitive_data,
    setup_server_logging,
)
from .server import (
    BaseMCPServer,
    create_argument_parser,
    create_middleware,
    register_basic_health_check,
    setup_transport,
)
from .tool_registration import (
    create_tool_wrapper,
    remove_parameters_from_signature,
)
from .validation import (
    sanitize_string,
    validate_boolean,
    validate_date,
    validate_email,
    validate_enum,
    validate_id,
    validate_limit,
    validate_list,
    validate_number,
    validate_positive_int,
    validate_required_field,
    validate_url,
)

__all__ = [
    # Correlation ID
    "generate_correlation_id",
    "get_correlation_id",
    "set_correlation_id",
    "clear_correlation_id",
    # Exceptions
    "MCPError",
    "MCPClientError",
    "MCPServerError",
    "MCPValidationError",
    "MCPNotFoundError",
    "MCPUnauthorizedError",
    "MCPForbiddenError",
    "MCPRateLimitError",
    "MCPConnectionError",
    "MCPTimeoutError",
    "map_status_to_exception",
    "log_tool_exception",
    # Logging
    "SENSITIVE_PATTERNS",
    "SENSITIVE_KEYS",
    "JSONFormatter",
    "redact_sensitive_data",
    "setup_server_logging",
    # Config
    "validate_base_url",
    "parse_comma_separated",
    # Validation
    "validate_id",
    "validate_limit",
    "validate_url",
    "validate_enum",
    "validate_boolean",
    "validate_required_field",
    "validate_positive_int",
    "validate_list",
    "validate_email",
    "validate_date",
    "validate_number",
    "sanitize_string",
    # Server
    "BaseMCPServer",
    "create_middleware",
    "setup_transport",
    "create_argument_parser",
    "register_basic_health_check",
    # Tool Registration
    "create_tool_wrapper",
    "remove_parameters_from_signature",
]

__version__ = "2026.1.0"

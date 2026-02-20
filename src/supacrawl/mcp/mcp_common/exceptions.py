"""
Base exception hierarchy for MCP servers.

Provides a standard exception hierarchy with context that all MCP servers can use
or extend with service-specific exceptions.

Usage:
    >>> from mcp_common.exceptions import MCPNotFoundError
    >>> raise MCPNotFoundError(
    ...     message="User not found",
    ...     endpoint="/users/123",
    ...     correlation_id="a1b2c3d4",
    ... )
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MCPError(Exception):
    """
    Base exception for all MCP errors.

    All MCP exceptions should inherit from this class to provide
    consistent error handling and context.

    Attributes:
        message: Human-readable error message
        endpoint: API endpoint that caused the error
        status_code: HTTP status code (if applicable)
        correlation_id: Request correlation ID for tracing
        response_body: Raw response body from API
        context: Additional context for debugging
    """

    def __init__(
        self,
        message: str,
        *,
        endpoint: str | None = None,
        status_code: int | None = None,
        correlation_id: str | None = None,
        response_body: dict[str, Any] | str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialise MCP error.

        Args:
            message: Human-readable error message
            endpoint: API endpoint that caused the error
            status_code: HTTP status code (if applicable)
            correlation_id: Request correlation ID for tracing
            response_body: Raw response body from API
            context: Additional context for debugging
        """
        self.message = message
        self.endpoint = endpoint
        self.status_code = status_code
        self.correlation_id = correlation_id
        self.response_body = response_body
        self.context = context or {}

        # Build detailed message
        parts = [message]
        if correlation_id:
            parts.append(f"[cid={correlation_id}]")
        if endpoint:
            parts.append(f"(endpoint={endpoint})")
        if status_code:
            parts.append(f"(status={status_code})")

        super().__init__(" ".join(parts))

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"message={self.message!r}, "
            f"endpoint={self.endpoint!r}, "
            f"status_code={self.status_code!r}, "
            f"correlation_id={self.correlation_id!r}"
            f")"
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for logging and serialisation."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "endpoint": self.endpoint,
            "status_code": self.status_code,
            "correlation_id": self.correlation_id,
            "context": self.context,
        }


class MCPClientError(MCPError):
    """
    Client error (4xx) - invalid request from client.

    Raised when the API returns a 4xx status code indicating a client error.
    These errors should NOT be retried as they indicate a problem with the request.
    """

    pass


class MCPServerError(MCPError):
    """
    Server error (5xx) - problem with API server.

    Raised when the API returns a 5xx status code indicating a server error.
    These errors SHOULD be retried with exponential backoff.
    """

    pass


class MCPValidationError(MCPError):
    """
    Validation error - invalid input data.

    Raised when input validation fails before making an API call.
    These errors should NOT be retried.

    Attributes:
        field: Name of the invalid field
        value: The invalid value
    """

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        value: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.field = field
        self.value = value


class MCPNotFoundError(MCPClientError):
    """
    Resource not found (404).

    Raised when the requested resource does not exist.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        # Remove status_code from kwargs if present to avoid duplicate
        kwargs.pop("status_code", None)
        super().__init__(message, status_code=404, **kwargs)


class MCPUnauthorizedError(MCPClientError):
    """
    Unauthorized (401) - invalid or missing credentials.

    Raised when authentication fails or credentials are missing.
    """

    def __init__(self, message: str = "Unauthorized - invalid or missing credentials", **kwargs: Any) -> None:
        # Remove status_code from kwargs if present to avoid duplicate
        kwargs.pop("status_code", None)
        super().__init__(message, status_code=401, **kwargs)


class MCPForbiddenError(MCPClientError):
    """
    Forbidden (403) - insufficient permissions.

    Raised when the user does not have permission to access the resource.
    """

    def __init__(self, message: str = "Forbidden - insufficient permissions", **kwargs: Any) -> None:
        # Remove status_code from kwargs if present to avoid duplicate
        kwargs.pop("status_code", None)
        super().__init__(message, status_code=403, **kwargs)


class MCPRateLimitError(MCPClientError):
    """
    Rate limit exceeded (429).

    Raised when API rate limits are exceeded. Check `retry_after` for
    the number of seconds to wait before retrying.

    Attributes:
        retry_after: Seconds to wait before retrying (from Retry-After header)
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        *,
        retry_after: int | None = None,
        **kwargs: Any,
    ) -> None:
        # Remove status_code from kwargs if present to avoid duplicate
        kwargs.pop("status_code", None)
        super().__init__(message, status_code=429, **kwargs)
        self.retry_after = retry_after


class MCPConnectionError(MCPError):
    """
    Connection error - cannot reach API server.

    Raised when the API server cannot be reached due to network issues.
    These errors SHOULD be retried with exponential backoff.
    """

    pass


class MCPTimeoutError(MCPError):
    """
    Timeout error - request timed out.

    Raised when a request times out. These errors SHOULD be retried
    with exponential backoff.
    """

    pass


def map_status_to_exception(
    status_code: int,
    message: str,
    *,
    endpoint: str | None = None,
    correlation_id: str | None = None,
    response_body: dict[str, Any] | str | None = None,
    retry_after: int | None = None,
) -> MCPError:
    """
    Map HTTP status code to appropriate exception type.

    Args:
        status_code: HTTP status code
        message: Error message
        endpoint: API endpoint that caused the error
        correlation_id: Request correlation ID
        response_body: Raw response body from API
        retry_after: Retry-After header value (for 429 responses)

    Returns:
        Appropriate exception instance based on status code
    """
    if status_code == 404:
        return MCPNotFoundError(
            message,
            endpoint=endpoint,
            correlation_id=correlation_id,
            response_body=response_body,
        )
    elif status_code == 401:
        return MCPUnauthorizedError(
            message,
            endpoint=endpoint,
            correlation_id=correlation_id,
            response_body=response_body,
        )
    elif status_code == 403:
        return MCPForbiddenError(
            message,
            endpoint=endpoint,
            correlation_id=correlation_id,
            response_body=response_body,
        )
    elif status_code == 429:
        return MCPRateLimitError(
            message,
            retry_after=retry_after,
            endpoint=endpoint,
            correlation_id=correlation_id,
            response_body=response_body,
        )
    elif 400 <= status_code < 500:
        return MCPClientError(
            message,
            endpoint=endpoint,
            status_code=status_code,
            correlation_id=correlation_id,
            response_body=response_body,
        )
    elif 500 <= status_code < 600:
        return MCPServerError(
            message,
            endpoint=endpoint,
            status_code=status_code,
            correlation_id=correlation_id,
            response_body=response_body,
        )
    else:
        return MCPError(
            message,
            endpoint=endpoint,
            status_code=status_code,
            correlation_id=correlation_id,
            response_body=response_body,
        )


def log_tool_exception(
    tool_name: str,
    exception: Exception,
    correlation_id: str | None = None,
) -> None:
    """
    Log tool exception with appropriate level based on exception type.

    Logs client errors (4xx) at WARNING level since they are expected and
    handled gracefully. Logs server errors (5xx) and connection errors at
    ERROR level since they indicate unexpected problems.

    Args:
        tool_name: Name of the tool that raised the exception
        exception: Exception that was raised
        correlation_id: Optional correlation ID for request tracking
    """
    correlation_msg = f"[{correlation_id}] " if correlation_id else ""

    # Determine log level based on exception type
    if isinstance(exception, (MCPClientError, MCPValidationError)):
        # Client errors (4xx) - expected and handled gracefully
        logger.warning(f"{correlation_msg}TOOL ERROR: {tool_name} failed: {exception}")
    elif isinstance(exception, (MCPServerError, MCPConnectionError, MCPTimeoutError)):
        # Server errors (5xx) and connection errors - unexpected
        logger.error(
            f"{correlation_msg}TOOL ERROR: {tool_name} failed: {exception}",
            exc_info=True,
        )
    else:
        # Unknown exceptions - log as error with traceback
        logger.error(
            f"{correlation_msg}TOOL ERROR: {tool_name} failed: {exception}",
            exc_info=True,
        )

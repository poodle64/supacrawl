"""
Correlation ID generation and tracking utilities.

Provides correlation ID generation (8 characters, UUID-based) for request tracking
as required by master error handling rules.

Usage:
    >>> from mcp_common.correlation import generate_correlation_id
    >>> corr_id = generate_correlation_id()
    >>> len(corr_id)
    8
"""

import contextvars
import uuid

# Context variable for correlation ID tracking across async contexts
_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("correlation_id", default=None)


def generate_correlation_id() -> str:
    """
    Generate a correlation ID for request tracking.

    Returns an 8-character UUID-based correlation ID as required by
    master error handling rules. The generated ID is automatically
    stored in the context variable for the current async context.

    Returns:
        8-character correlation ID (first 8 characters of UUID hex)

    Example:
        >>> corr_id = generate_correlation_id()
        >>> len(corr_id)
        8
        >>> get_correlation_id() == corr_id
        True
    """
    corr_id = uuid.uuid4().hex[:8]
    _correlation_id.set(corr_id)
    return corr_id


def get_correlation_id() -> str | None:
    """
    Get the current correlation ID from context.

    Returns the correlation ID for the current async context, or None
    if no correlation ID has been set.

    Returns:
        Current correlation ID or None

    Example:
        >>> generate_correlation_id()
        'a1b2c3d4'
        >>> get_correlation_id()
        'a1b2c3d4'
    """
    return _correlation_id.get()


def set_correlation_id(corr_id: str) -> None:
    """
    Set a correlation ID in the current context.

    Useful for propagating correlation IDs from parent contexts or
    external sources (e.g., incoming request headers).

    Args:
        corr_id: Correlation ID to set (should be 8 characters for consistency)

    Example:
        >>> set_correlation_id('abc12345')
        >>> get_correlation_id()
        'abc12345'
    """
    _correlation_id.set(corr_id)


def clear_correlation_id() -> None:
    """
    Clear the correlation ID from the current context.

    Useful for cleanup after request handling.

    Example:
        >>> generate_correlation_id()
        'a1b2c3d4'
        >>> clear_correlation_id()
        >>> get_correlation_id() is None
        True
    """
    _correlation_id.set(None)

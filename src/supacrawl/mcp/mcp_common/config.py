"""
Configuration validation utilities for MCP servers.

Provides Pydantic field validators for common configuration patterns.

Usage:
    >>> from mcp_common.config import validate_base_url, parse_comma_separated
    >>> validate_base_url("https://api.example.com")
    'https://api.example.com'
    >>> parse_comma_separated("a, b, c")
    ['a', 'b', 'c']
"""

from urllib.parse import urlparse


def parse_comma_separated(v: str | list[str]) -> list[str]:
    """
    Parse comma-separated string into list.

    Common validator for ALLOWED_ORIGINS, ALLOWED_HOSTS, and similar fields.
    Can be used as a Pydantic field_validator with mode="before".

    Args:
        v: Either a comma-separated string or already a list of strings

    Returns:
        List of trimmed strings

    Examples:
        >>> parse_comma_separated("http://localhost,http://example.com")
        ['http://localhost', 'http://example.com']

        >>> parse_comma_separated(["a", "b"])
        ['a', 'b']

        >>> parse_comma_separated("  spaced , values  ")
        ['spaced', 'values']
    """
    if isinstance(v, str):
        return [item.strip() for item in v.split(",") if item.strip()]
    return v


def validate_base_url(
    v: str,
    field_name: str = "base_url",
    strip_trailing_slash: bool = False,
) -> str:
    """
    Validate base URL format - reusable across all MCP servers.

    Validates:
    - URL is not empty
    - URL has valid format (scheme and netloc)
    - URL scheme is http or https

    Args:
        v: The URL value to validate
        field_name: Name of the field for error messages (default: "base_url")
        strip_trailing_slash: If True, strip trailing slash from URL (default: False)

    Returns:
        Validated URL (with trailing slash stripped if requested)

    Raises:
        ValueError: If URL is invalid

    Examples:
        >>> validate_base_url("https://api.example.com")
        'https://api.example.com'

        >>> validate_base_url("https://api.example.com/", strip_trailing_slash=True)
        'https://api.example.com'
    """
    if not v:
        raise ValueError(f"{field_name.upper()} cannot be empty")

    try:
        parsed = urlparse(v)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid URL format: {v}")
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"URL scheme must be http or https: {v}")
    except Exception as e:
        if isinstance(e, ValueError) and (
            "cannot be empty" in str(e) or "Invalid URL" in str(e) or "scheme must be" in str(e)
        ):
            raise
        raise ValueError(f"Invalid {field_name} format: {e}") from e

    return v.rstrip("/") if strip_trailing_slash else v

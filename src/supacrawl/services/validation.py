"""Portable URL validation shared by the REST API and the MCP layer.

Raises ``supacrawl.exceptions.ValidationError`` (no fastmcp/mcp-common
dependency) so an api-only install can import it. The remaining MCP-only
validators (``validate_query``, ``validate_timeout``, etc.) stay in
``supacrawl.mcp.validators``; they are used only by MCP-only tool modules
never imported by the API layer.
"""

from typing import Any
from urllib.parse import urlparse

from supacrawl.exceptions import ValidationError
from supacrawl.services.url_guard import assert_safe_url


def validate_url(
    value: Any,
    field_name: str = "url",
    allow_none: bool = False,
) -> str | None:
    """
    Validate that a value is a valid URL.

    Args:
        value: The value to validate
        field_name: Name of the field for error messages
        allow_none: If True, allow None values

    Returns:
        Validated URL as string or None

    Raises:
        ValidationError: If value is not a valid URL
    """
    if value is None:
        if allow_none:
            return None
        raise ValidationError(
            f"{field_name} is required",
            field=field_name,
            value=value,
        )

    if not isinstance(value, str):
        raise ValidationError(
            f"{field_name} must be a string, got {type(value).__name__}",
            field=field_name,
            value=value,
        )

    url = value.strip()
    if not url:
        if allow_none:
            return None
        raise ValidationError(
            f"{field_name} cannot be empty",
            field=field_name,
            value=value,
        )

    # Check URL scheme
    if not url.startswith(("http://", "https://")):
        raise ValidationError(
            f"{field_name} must start with http:// or https://, got '{url[:20]}...'",
            field=field_name,
            value=value,
        )

    # Parse and validate URL structure. Only the urlparse call is wrapped:
    # a genuinely unparseable URL becomes "is not a valid URL", while a
    # parseable-but-hostless URL keeps its specific "must have a valid host"
    # message instead of being re-wrapped by the broad except.
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValidationError(
            f"{field_name} is not a valid URL: {e}",
            field=field_name,
            value=value,
        ) from e

    if not parsed.netloc:
        raise ValidationError(
            f"{field_name} must have a valid host, got '{url}'",
            field=field_name,
            value=value,
        )

    # Cheap, offline SSRF check (#152): scheme already verified above, so this
    # only adds the blocked-IP-literal check. It cannot catch a hostname that
    # *resolves* to a blocked address — the connection-layer guard
    # (supacrawl.services.url_guard.resolve_and_pin / guarded_request) is what
    # closes that window at the point each URL is actually fetched.
    try:
        assert_safe_url(url)
    except ValidationError as e:
        raise ValidationError(e.message, field=field_name, value=value, context=e.context) from e

    return url


__all__ = ["validate_url"]

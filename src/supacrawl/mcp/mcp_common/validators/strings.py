"""String validation utilities.

Provides validators for IDs, URLs, emails, dates, and string sanitisation.
All validators raise MCPValidationError on invalid input.
"""

import re
from typing import Any
from urllib.parse import urlsplit

from ..exceptions import MCPValidationError

# Common ID patterns
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
ALPHANUMERIC_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+$")
NUMERIC_PATTERN = re.compile(r"^[0-9]+$")


def validate_id(
    value: str | None,
    field_name: str,
    *,
    allow_none: bool = False,
    require_uuid: bool = False,
    require_numeric: bool = False,
    min_length: int = 1,
    max_length: int = 255,
    correlation_id: str | None = None,
) -> str | None:
    """Validate an ID value.

    Args:
        value: The ID value to validate
        field_name: Name of the field (for error messages)
        allow_none: Whether None is a valid value
        require_uuid: Whether the ID must be a valid UUID
        require_numeric: Whether the ID must be numeric
        min_length: Minimum length for the ID
        max_length: Maximum length for the ID
        correlation_id: Correlation ID for error context

    Returns:
        The validated ID value

    Raises:
        MCPValidationError: If validation fails
    """
    if value is None:
        if allow_none:
            return None
        raise MCPValidationError(
            message=f"{field_name} is required",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    if not isinstance(value, str):
        raise MCPValidationError(
            message=f"{field_name} must be a string, got {type(value).__name__}",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    value = value.strip()

    if len(value) < min_length:
        raise MCPValidationError(
            message=f"{field_name} must be at least {min_length} character(s), got {len(value)}",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    if len(value) > max_length:
        raise MCPValidationError(
            message=f"{field_name} must be at most {max_length} characters, got {len(value)}",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    if require_uuid and not UUID_PATTERN.match(value):
        raise MCPValidationError(
            message=f"{field_name} must be a valid UUID, got '{value}'",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    if require_numeric and not NUMERIC_PATTERN.match(value):
        raise MCPValidationError(
            message=f"{field_name} must be numeric, got '{value}'",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    # General check for alphanumeric with dashes/underscores if not UUID or numeric
    if not require_uuid and not require_numeric and not ALPHANUMERIC_PATTERN.match(value):
        # Allow UUIDs even if not required
        if not UUID_PATTERN.match(value):
            raise MCPValidationError(
                message=f"{field_name} contains invalid characters, got '{value}'",
                field=field_name,
                value=value,
                correlation_id=correlation_id,
            )

    return value


def validate_url(
    value: str | None,
    field_name: str = "url",
    *,
    allow_none: bool = False,
    require_https: bool = False,
    allowed_schemes: set[str] | None = None,
    correlation_id: str | None = None,
) -> str | None:
    """Validate a URL value.

    Args:
        value: The URL to validate
        field_name: Name of the field (for error messages)
        allow_none: Whether None is a valid value
        require_https: Whether to require HTTPS scheme
        allowed_schemes: Set of allowed schemes (default: {'http', 'https'})
        correlation_id: Correlation ID for error context

    Returns:
        The validated URL (with trailing slash removed)

    Raises:
        MCPValidationError: If validation fails
    """
    if value is None:
        if allow_none:
            return None
        raise MCPValidationError(
            message=f"{field_name} is required",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    if not isinstance(value, str):
        raise MCPValidationError(
            message=f"{field_name} must be a string, got {type(value).__name__}",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    value = value.strip()

    if not value:
        raise MCPValidationError(
            message=f"{field_name} cannot be empty",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    # Parse URL
    parsed = urlsplit(value)

    # Determine allowed schemes
    if allowed_schemes is None:
        if require_https:
            allowed_schemes = {"https"}
        else:
            allowed_schemes = {"http", "https"}

    # Check scheme
    if parsed.scheme not in allowed_schemes:
        schemes_str = sorted(allowed_schemes)
        raise MCPValidationError(
            message=f"{field_name} must use scheme {schemes_str}, got '{parsed.scheme}'",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    # Check netloc (host)
    if not parsed.netloc:
        raise MCPValidationError(
            message=f"{field_name} must include a host, got '{value}'",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    # Return URL with trailing slash removed for consistency
    return value.rstrip("/")


def sanitize_string(
    value: Any,
    field_name: str,
    *,
    allow_none: bool = True,
    allow_empty: bool = True,
    max_length: int | None = None,
    correlation_id: str | None = None,
) -> str | None:
    """Sanitise a string value (strip whitespace, validate length).

    Args:
        value: Value to sanitise
        field_name: Name of field for error messages
        allow_none: Whether None is a valid value (returns None)
        allow_empty: Whether to allow empty strings (returns None if empty)
        max_length: Maximum length of string
        correlation_id: Correlation ID for error context

    Returns:
        Sanitised string or None
    """
    if value is None:
        if allow_none:
            return None
        raise MCPValidationError(
            message=f"{field_name} is required",
            field=field_name,
            correlation_id=correlation_id,
        )

    if not isinstance(value, str):
        value = str(value)

    sanitised: str = value.strip()

    if not sanitised:
        if allow_empty:
            return None
        raise MCPValidationError(
            message=f"{field_name} cannot be empty",
            field=field_name,
            correlation_id=correlation_id,
        )

    if max_length and len(sanitised) > max_length:
        raise MCPValidationError(
            message=f"{field_name} exceeds maximum length of {max_length}, got {len(sanitised)} characters",
            field=field_name,
            value=sanitised[:50] + "..." if len(sanitised) > 50 else sanitised,
            correlation_id=correlation_id,
        )

    return sanitised


def validate_email(
    value: str | None,
    field_name: str = "email",
    *,
    allow_none: bool = False,
    correlation_id: str | None = None,
) -> str | None:
    """Validate that a value is a valid email address format.

    Args:
        value: Value to validate
        field_name: Name of field for error messages
        allow_none: Whether None is a valid value
        correlation_id: Correlation ID for error context

    Returns:
        Validated email as string or None

    Raises:
        MCPValidationError: If email format is invalid
    """
    if value is None:
        if allow_none:
            return None
        raise MCPValidationError(
            message=f"{field_name} is required",
            field=field_name,
            correlation_id=correlation_id,
        )

    if not isinstance(value, str):
        raise MCPValidationError(
            message=f"{field_name} must be a string, got {type(value).__name__}",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    email_str = value.strip()

    if not email_str:
        if allow_none:
            return None
        raise MCPValidationError(
            message=f"{field_name} cannot be empty",
            field=field_name,
            correlation_id=correlation_id,
        )

    # Basic email regex pattern (RFC 5322 simplified)
    email_pattern = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

    if not email_pattern.match(email_str):
        raise MCPValidationError(
            message=f"{field_name} must be a valid email address, got '{email_str}'",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    return email_str


def validate_date(
    value: str | None,
    field_name: str = "date",
    *,
    allow_none: bool = False,
    date_format: str = "%Y-%m-%d",
    correlation_id: str | None = None,
) -> str | None:
    """Validate that a value is a valid date in the specified format.

    Args:
        value: Value to validate
        field_name: Name of field for error messages
        allow_none: Whether None is a valid value
        date_format: Expected date format (default: ISO format '%Y-%m-%d')
        correlation_id: Correlation ID for error context

    Returns:
        Validated date string or None

    Raises:
        MCPValidationError: If date format is invalid
    """
    from datetime import datetime

    if value is None:
        if allow_none:
            return None
        raise MCPValidationError(
            message=f"{field_name} is required",
            field=field_name,
            correlation_id=correlation_id,
        )

    if not isinstance(value, str):
        raise MCPValidationError(
            message=f"{field_name} must be a string, got {type(value).__name__}",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    date_str = value.strip()

    if not date_str:
        if allow_none:
            return None
        raise MCPValidationError(
            message=f"{field_name} cannot be empty",
            field=field_name,
            correlation_id=correlation_id,
        )

    try:
        datetime.strptime(date_str, date_format)
    except ValueError as e:
        # Format error message based on common formats
        format_examples = {
            "%Y-%m-%d": "YYYY-MM-DD (e.g., 2024-01-15)",
            "%Y-%m-%dT%H:%M:%S": "YYYY-MM-DDTHH:MM:SS",
            "%Y-%m-%d %H:%M:%S": "YYYY-MM-DD HH:MM:SS",
        }
        format_name = format_examples.get(date_format, date_format)

        raise MCPValidationError(
            message=f"{field_name} must be a valid date in format {format_name}, got '{date_str}'",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        ) from e

    return date_str

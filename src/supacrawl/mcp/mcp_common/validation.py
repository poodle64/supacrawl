"""
Input validation utilities for MCP servers.

Provides common validators for IDs, limits, enums, URLs, and other input types.
All validators raise MCPValidationError on invalid input.

Usage:
    >>> from mcp_common.validation import validate_id, validate_limit
    >>> validate_id("abc123", "user_id")  # OK
    >>> validate_limit(100, "page_size", max_value=1000)  # OK
"""

import re
from typing import Any, TypeVar
from urllib.parse import urlsplit

from .exceptions import MCPValidationError

T = TypeVar("T")

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
    """
    Validate an ID value.

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


def validate_limit(
    value: int | None,
    field_name: str,
    *,
    allow_none: bool = False,
    min_value: int = 1,
    max_value: int = 1000,
    default: int | None = None,
    correlation_id: str | None = None,
) -> int | None:
    """
    Validate a limit/pagination value.

    Args:
        value: The limit value to validate
        field_name: Name of the field (for error messages)
        allow_none: Whether None is a valid value
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        default: Default value to return if value is None and allow_none is True
        correlation_id: Correlation ID for error context

    Returns:
        The validated limit value

    Raises:
        MCPValidationError: If validation fails
    """
    if value is None:
        if allow_none:
            return default
        raise MCPValidationError(
            message=f"{field_name} is required",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    if not isinstance(value, int):
        raise MCPValidationError(
            message=f"{field_name} must be an integer, got {type(value).__name__}",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    if value < min_value:
        raise MCPValidationError(
            message=f"{field_name} must be at least {min_value}, got {value}",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    if value > max_value:
        raise MCPValidationError(
            message=f"{field_name} must be at most {max_value}, got {value}",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    return value


def validate_enum(
    value: T | None,
    field_name: str,
    allowed_values: set[T] | frozenset[T] | list[T] | tuple[T, ...],
    *,
    allow_none: bool = False,
    case_insensitive: bool = False,
    correlation_id: str | None = None,
) -> T | None:
    """
    Validate an enum/choice value.

    Args:
        value: The value to validate
        field_name: Name of the field (for error messages)
        allowed_values: Set of allowed values
        allow_none: Whether None is a valid value
        case_insensitive: Whether to do case-insensitive matching (for strings)
        correlation_id: Correlation ID for error context

    Returns:
        The validated value (possibly normalised if case_insensitive)

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

    allowed_set = set(allowed_values)

    # Handle case-insensitive matching for strings
    if case_insensitive and isinstance(value, str):
        value_lower = value.lower()
        for allowed in allowed_set:
            if isinstance(allowed, str) and allowed.lower() == value_lower:
                return allowed  # type: ignore[return-value]
        allowed_str = sorted(str(x) for x in allowed_set)
        raise MCPValidationError(
            message=f"{field_name} must be one of {allowed_str}, got '{value}'",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    if value not in allowed_set:
        allowed_str = sorted(str(x) for x in allowed_set)
        raise MCPValidationError(
            message=f"{field_name} must be one of {allowed_str}, got '{value}'",
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
    """
    Validate a URL value.

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


def validate_boolean(
    value: Any,
    field_name: str,
    *,
    allow_none: bool = False,
    default: bool | None = None,
    correlation_id: str | None = None,
) -> bool | None:
    """
    Validate and normalise a boolean value.

    Accepts bool, int (0/1), and string ("true"/"false", "1"/"0", "yes"/"no").

    Args:
        value: The value to validate
        field_name: Name of the field (for error messages)
        allow_none: Whether None is a valid value
        default: Default value if value is None
        correlation_id: Correlation ID for error context

    Returns:
        The normalised boolean value

    Raises:
        MCPValidationError: If validation fails
    """
    if value is None:
        if allow_none:
            return default
        raise MCPValidationError(
            message=f"{field_name} is required",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        if value == 0:
            return False
        if value == 1:
            return True
        raise MCPValidationError(
            message=f"{field_name} must be 0 or 1 when integer, got {value}",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    if isinstance(value, str):
        value_lower = value.lower().strip()
        if value_lower in ("true", "1", "yes", "on"):
            return True
        if value_lower in ("false", "0", "no", "off"):
            return False
        raise MCPValidationError(
            message=f"{field_name} must be a boolean string, got '{value}'",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    raise MCPValidationError(
        message=f"{field_name} must be a boolean, got {type(value).__name__}",
        field=field_name,
        value=value,
        correlation_id=correlation_id,
    )


def validate_required_field(
    data: dict[str, Any],
    field_name: str,
    field_type: type | None = None,
    *,
    correlation_id: str | None = None,
) -> Any:
    """
    Validate that a required field exists in data.

    Args:
        data: Dictionary to check
        field_name: Name of required field
        field_type: Optional type to validate against
        correlation_id: Correlation ID for error context

    Returns:
        Field value

    Raises:
        MCPValidationError: If field is missing or wrong type
    """
    if field_name not in data:
        raise MCPValidationError(
            message=f"Required field '{field_name}' is missing",
            field=field_name,
            correlation_id=correlation_id,
        )

    value = data[field_name]

    if value is None:
        raise MCPValidationError(
            message=f"Required field '{field_name}' cannot be None",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    if field_type and not isinstance(value, field_type):
        expected = field_type.__name__
        actual = type(value).__name__
        raise MCPValidationError(
            message=f"Field '{field_name}' must be {expected}, got {actual}",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    return value


def validate_positive_int(
    value: Any,
    field_name: str,
    *,
    allow_none: bool = False,
    allow_zero: bool = False,
    max_value: int | None = None,
    correlation_id: str | None = None,
) -> int | None:
    """
    Validate that a value is a positive integer.

    Useful for integer IDs (e.g., PocketSmith, Authentik user pks).

    Args:
        value: The value to validate
        field_name: Name of the field (for error messages)
        allow_none: Whether None is a valid value
        allow_zero: Whether 0 is allowed (default: False, must be > 0)
        max_value: Maximum allowed value (optional)
        correlation_id: Correlation ID for error context

    Returns:
        The validated integer value

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

    # Convert string to int if needed
    if isinstance(value, str):
        value = value.strip()
        if not value:
            if allow_none:
                return None
            raise MCPValidationError(
                message=f"{field_name} cannot be empty",
                field=field_name,
                value=value,
                correlation_id=correlation_id,
            )
        try:
            value = int(value)
        except ValueError as e:
            raise MCPValidationError(
                message=f"{field_name} must be a valid integer, got '{value}'",
                field=field_name,
                value=value,
                correlation_id=correlation_id,
            ) from e

    if not isinstance(value, int) or isinstance(value, bool):
        raise MCPValidationError(
            message=f"{field_name} must be an integer, got {type(value).__name__}",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    min_val = 0 if allow_zero else 1
    if value < min_val:
        raise MCPValidationError(
            message=f"{field_name} must be {'non-negative' if allow_zero else 'positive'}, got {value}",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    if max_value is not None and value > max_value:
        raise MCPValidationError(
            message=f"{field_name} must be at most {max_value}, got {value}",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    return value


def validate_list(
    value: Any,
    field_name: str,
    *,
    allow_none: bool = False,
    min_length: int = 0,
    max_length: int | None = None,
    item_type: type | None = None,
    correlation_id: str | None = None,
) -> list[Any] | None:
    """
    Validate that a value is a list with optional constraints.

    Args:
        value: Value to validate
        field_name: Name of field for error messages
        allow_none: Whether None is a valid value
        min_length: Minimum length of list (default: 0)
        max_length: Maximum length of list (optional)
        item_type: Optional type for list items
        correlation_id: Correlation ID for error context

    Returns:
        Validated list or None

    Raises:
        MCPValidationError: If value is not a valid list
    """
    if value is None:
        if allow_none:
            return None
        raise MCPValidationError(
            message=f"{field_name} is required",
            field=field_name,
            correlation_id=correlation_id,
        )

    if not isinstance(value, list):
        raise MCPValidationError(
            message=f"{field_name} must be a list, got {type(value).__name__}",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    if len(value) < min_length:
        raise MCPValidationError(
            message=f"{field_name} must have at least {min_length} item(s), got {len(value)}",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    if max_length is not None and len(value) > max_length:
        raise MCPValidationError(
            message=f"{field_name} must have at most {max_length} item(s), got {len(value)}",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    if item_type:
        for i, item in enumerate(value):
            if not isinstance(item, item_type):
                raise MCPValidationError(
                    message=f"{field_name}[{i}] must be {item_type.__name__}, got {type(item).__name__}",
                    field=f"{field_name}[{i}]",
                    value=item,
                    correlation_id=correlation_id,
                )

    return value


def sanitize_string(
    value: Any,
    field_name: str,
    *,
    allow_none: bool = True,
    allow_empty: bool = True,
    max_length: int | None = None,
    correlation_id: str | None = None,
) -> str | None:
    """
    Sanitise a string value (strip whitespace, validate length).

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

    value = value.strip()

    if not value:
        if allow_empty:
            return None
        raise MCPValidationError(
            message=f"{field_name} cannot be empty",
            field=field_name,
            correlation_id=correlation_id,
        )

    if max_length and len(value) > max_length:
        raise MCPValidationError(
            message=f"{field_name} exceeds maximum length of {max_length}, got {len(value)} characters",
            field=field_name,
            value=value[:50] + "..." if len(value) > 50 else value,
            correlation_id=correlation_id,
        )

    return value


def validate_email(
    value: str | None,
    field_name: str = "email",
    *,
    allow_none: bool = False,
    correlation_id: str | None = None,
) -> str | None:
    """
    Validate that a value is a valid email address format.

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
    """
    Validate that a value is a valid date in the specified format.

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


def validate_number(
    value: Any,
    field_name: str,
    *,
    allow_none: bool = False,
    min_value: float | None = None,
    max_value: float | None = None,
    correlation_id: str | None = None,
) -> float | None:
    """
    Validate that a value is a valid number (int or float).

    Useful for currency amounts, percentages, etc.

    Args:
        value: Value to validate
        field_name: Name of field for error messages
        allow_none: Whether None is a valid value
        min_value: Minimum allowed value (optional)
        max_value: Maximum allowed value (optional)
        correlation_id: Correlation ID for error context

    Returns:
        Validated number as float or None

    Raises:
        MCPValidationError: If value is not a valid number
    """
    if value is None:
        if allow_none:
            return None
        raise MCPValidationError(
            message=f"{field_name} is required",
            field=field_name,
            correlation_id=correlation_id,
        )

    try:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                if allow_none:
                    return None
                raise MCPValidationError(
                    message=f"{field_name} cannot be empty",
                    field=field_name,
                    correlation_id=correlation_id,
                )
            number = float(value)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            number = float(value)
        else:
            raise ValueError()
    except (ValueError, TypeError) as e:
        raise MCPValidationError(
            message=f"{field_name} must be a valid number, got {type(value).__name__} '{value}'",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        ) from e

    if min_value is not None and number < min_value:
        raise MCPValidationError(
            message=f"{field_name} must be at least {min_value}, got {number}",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    if max_value is not None and number > max_value:
        raise MCPValidationError(
            message=f"{field_name} must be at most {max_value}, got {number}",
            field=field_name,
            value=value,
            correlation_id=correlation_id,
        )

    return number

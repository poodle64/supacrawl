"""Base validation utilities.

Provides core validation functions for required fields, field types, and enums.
All validators raise MCPValidationError on invalid input.
"""

from typing import Any

from ..exceptions import MCPValidationError


def validate_required_field(
    data: dict[str, Any],
    field_name: str,
    field_type: type | None = None,
    *,
    correlation_id: str | None = None,
) -> Any:
    """Validate that a required field exists in data.

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


def validate_enum[T](
    value: T | None,
    field_name: str,
    allowed_values: set[T] | frozenset[T] | list[T] | tuple[T, ...],
    *,
    allow_none: bool = False,
    case_insensitive: bool = False,
    correlation_id: str | None = None,
) -> T | None:
    """Validate an enum/choice value.

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


def validate_boolean(
    value: Any,
    field_name: str,
    *,
    allow_none: bool = False,
    default: bool | None = None,
    correlation_id: str | None = None,
) -> bool | None:
    """Validate and normalise a boolean value.

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
    """Validate that a value is a list with optional constraints.

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

"""Numeric validation utilities.

Provides validators for limits, positive integers, and general numbers.
All validators raise MCPValidationError on invalid input.
"""

from typing import Any

from ..exceptions import MCPValidationError


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
    """Validate a limit/pagination value.

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


def validate_positive_int(
    value: Any,
    field_name: str,
    *,
    allow_none: bool = False,
    allow_zero: bool = False,
    max_value: int | None = None,
    correlation_id: str | None = None,
) -> int | None:
    """Validate that a value is a positive integer.

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


def validate_number(
    value: Any,
    field_name: str,
    *,
    allow_none: bool = False,
    min_value: float | None = None,
    max_value: float | None = None,
    correlation_id: str | None = None,
) -> float | None:
    """Validate that a value is a valid number (int or float).

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
            raise ValueError
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

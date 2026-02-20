"""
Structured JSON logging utilities for MCP servers.

Provides JSON formatter with correlation ID support and sensitive data redaction.

Usage:
    >>> from mcp_common.logging import JSONFormatter, setup_logging
    >>> formatter = JSONFormatter("my-service", "1.0.0")
    >>> setup_logging(formatter)
"""

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

from .correlation import generate_correlation_id, get_correlation_id

# Patterns for sensitive data that should be redacted (enhanced from api-clients)
SENSITIVE_PATTERNS = [
    # API keys and tokens
    re.compile(
        r"(api[_-]?key|token|secret|password|auth|bearer|authorization)"
        r"[\"']?\s*[:=]\s*[\"']?([^\"'\s,}\]]+)",
        re.IGNORECASE,
    ),
    # Email addresses
    re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    # Common token patterns (JWT, etc.)
    re.compile(r"eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*"),
]

# Keys that should have their values redacted
SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "api-key",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "password",
        "passwd",
        "authorization",
        "auth",
        "bearer",
        "credentials",
        "private_key",
        "secret_key",
    }
)


def redact_sensitive_data(message: str, replacement: str = "[REDACTED]") -> str:
    """
    Redact sensitive data from a string.

    This function redacts sensitive patterns like API keys, tokens,
    passwords, JWT tokens, email addresses, and other credentials.

    Args:
        message: The message to redact
        replacement: String to replace sensitive data with

    Returns:
        Message with sensitive data redacted

    Example:
        >>> redact_sensitive_data("api_key=secret123")
        'api_key=[REDACTED]'
        >>> redact_sensitive_data("email: user@example.com")
        'email: [REDACTED]'
    """
    if not isinstance(message, str):
        return str(message)

    redacted = message

    # Apply comprehensive patterns
    for pattern in SENSITIVE_PATTERNS:
        redacted = pattern.sub(replacement, redacted)

    # Apply simple key=value patterns for broader coverage
    sensitive_keys = [
        "api_key",
        "api-key",
        "apikey",
        "password",
        "passwd",
        "pwd",
        "token",
        "secret",
        "credential",
        "authorization",
        "auth",
        "access_token",
        "auth_token",
        "oauth_consumer_key",
    ]
    for key in sensitive_keys:
        escaped_key = re.escape(key)
        regex = re.compile(
            rf'\b{escaped_key}\s*[=:]\s*["\']?([^"\'\s,}}]+)["\']?',
            re.IGNORECASE,
        )
        redacted = regex.sub(f"{key}={replacement}", redacted)

    return redacted


class JSONFormatter(logging.Formatter):
    """
    Structured JSON formatter for logs with correlation IDs and service metadata.

    Features:
    - Automatic correlation ID generation/extraction
    - Sensitive data redaction (tokens, passwords, API keys)
    - Log type detection (request, error, startup, etc.)
    - Service metadata (name, version)
    - Exception formatting
    - Extra fields support
    """

    # Patterns to redact from log messages (case-insensitive)
    SENSITIVE_PATTERNS = [
        "api_key",
        "api-key",
        "apikey",
        "password",
        "passwd",
        "pwd",
        "token",
        "secret",
        "credential",
        "authorization",
        "auth",
        "access_token",
        "auth_token",
    ]

    def __init__(
        self,
        service_name: str,
        service_version: str,
        include_module: bool = False,
        include_function: bool = False,
        include_line: bool = False,
    ):
        """
        Initialise JSON formatter.

        Args:
            service_name: Name of the service (e.g., "meta-mcp")
            service_version: Version of the service (e.g., "v24.0")
            include_module: Include module name in log entries
            include_function: Include function name in log entries
            include_line: Include line number in log entries
        """
        super().__init__()
        self.service_name = service_name
        self.service_version = service_version
        self.include_module = include_module
        self.include_function = include_function
        self.include_line = include_line

    def _redact_sensitive_data(self, message: str) -> str:
        """Redact sensitive data from log messages."""
        if not isinstance(message, str):
            return str(message)

        # Redact API keys (look for patterns like "key=value" or "key: value")
        redacted = message
        for pattern in self.SENSITIVE_PATTERNS:
            # Match patterns like "api_key=xxx", "api_key: xxx", "api_key": "xxx"
            escaped_pattern = re.escape(pattern)
            regex = re.compile(
                rf'\b{escaped_pattern}\s*[=:]\s*["\']?([^"\'\s,}}]+)["\']?',
                re.IGNORECASE,
            )
            redacted = regex.sub(f"{pattern}=[REDACTED]", redacted)

        # Also use the simpler regex pattern for broader coverage
        redacted = re.sub(
            r"(?i)(token|password|api[_-]?key|secret|auth[_-]?token|access[_-]?token)\s*[=:]\s*[^\s]+",
            r"\1=***REDACTED***",
            redacted,
        )

        return redacted

    def _extract_correlation_id(self, record: logging.LogRecord) -> str | None:
        """Extract correlation ID from log record if present."""
        # Check if correlation ID is in the record
        if hasattr(record, "correlation_id"):
            cid = record.correlation_id
            if isinstance(cid, str):
                return cid

        # Check context variable
        corr_id = get_correlation_id()
        if corr_id:
            return corr_id

        # Try to extract from message (format: [correlation_id])
        match = re.search(r"\[([a-f0-9]{8})\]", record.getMessage())
        if match:
            return match.group(1)

        return None

    def _detect_log_type(self, record: logging.LogRecord) -> str:
        """Detect log type from record attributes and message."""
        # Check for explicit log_type in extra_fields
        if hasattr(record, "extra_fields"):
            extra_fields = record.extra_fields
            if isinstance(extra_fields, dict) and "log_type" in extra_fields:
                log_type = extra_fields["log_type"]
                if isinstance(log_type, str):
                    return log_type

        # Check log level first (most reliable indicator)
        if record.levelname in ("ERROR", "CRITICAL"):
            return "error"

        # Infer from message content (only if level is not ERROR)
        message = record.getMessage().lower()
        if "request" in message or "api request" in message:
            return "request"
        elif "startup" in message or "initializ" in message:
            return "startup"
        elif "health" in message:
            return "health_check"
        elif "shutdown" in message or "cleanup" in message:
            return "shutdown"
        else:
            return "application"

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Extract correlation ID
        correlation_id = self._extract_correlation_id(record)
        if not correlation_id:
            correlation_id = generate_correlation_id()

        # Build log entry
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": self._redact_sensitive_data(record.getMessage()),
            "correlation_id": correlation_id,
            "service_name": self.service_name,
            "service_version": self.service_version,
            "log_type": self._detect_log_type(record),
        }

        # Add optional fields
        if self.include_module and record.module:
            log_entry["module"] = record.module
        if self.include_function and record.funcName and record.funcName != "<module>":
            log_entry["function"] = record.funcName
        if self.include_line and record.lineno:
            log_entry["line"] = record.lineno

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add extra fields from record
        if hasattr(record, "extra_fields"):
            extra_fields = record.extra_fields
            if isinstance(extra_fields, dict):
                log_entry.update(extra_fields)

        # Add any other extra attributes (excluding standard logging attributes)
        standard_attrs = {
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "message",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "thread",
            "threadName",
            "exc_info",
            "exc_text",
            "stack_info",
            "correlation_id",
        }
        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                log_entry[key] = value

        # Return as JSON string (single line for better parsing)
        return json.dumps(log_entry, ensure_ascii=False)


class CorrelationIdFilter(logging.Filter):
    """
    Logging filter that ensures correlation_id is always present in records.

    If no correlation_id is provided, adds a configurable default. This ensures
    consistent log formatting even when correlation ID is not available.

    Usage:
        >>> handler.addFilter(CorrelationIdFilter())
        >>> handler.addFilter(CorrelationIdFilter(default_value="no-correlation-id"))
    """

    def __init__(self, default_value: str = "-") -> None:
        """
        Initialise the filter.

        Args:
            default_value: Value to use when correlation_id is not present
        """
        super().__init__()
        self.default_value = default_value

    def filter(self, record: logging.LogRecord) -> bool:
        """Add correlation ID to record if not already present."""
        if not hasattr(record, "correlation_id") or record.correlation_id is None:
            corr_id = get_correlation_id()
            record.correlation_id = corr_id if corr_id else self.default_value
        return True


class SensitiveDataFilter(logging.Filter):
    """
    Logging filter that redacts sensitive data from log records.

    Redacts:
    - API keys, tokens, and passwords
    - Email addresses
    - JWT tokens
    - Values for keys in SENSITIVE_KEYS

    Usage:
        >>> handler.addFilter(SensitiveDataFilter())
    """

    def __init__(self, replacement: str = "[REDACTED]") -> None:
        """
        Initialise the filter.

        Args:
            replacement: String to replace sensitive data with
        """
        super().__init__()
        self.replacement = replacement

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter a log record, redacting sensitive data.

        Args:
            record: The log record to filter

        Returns:
            Always True (record is always allowed, just modified)
        """
        # Redact message
        if record.msg:
            record.msg = self._redact_string(str(record.msg))

        # Redact args if present
        if record.args:
            if isinstance(record.args, dict):
                record.args = self._redact_dict(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(self._redact_value(arg) for arg in record.args)

        # Redact extra fields
        for key in list(vars(record).keys()):
            if key in SENSITIVE_KEYS:
                setattr(record, key, self.replacement)
            elif isinstance(getattr(record, key, None), str):
                value = getattr(record, key)
                if self._is_extra_field(key, record):
                    setattr(record, key, self._redact_string(value))

        return True

    def _is_extra_field(self, key: str, record: logging.LogRecord) -> bool:
        """Check if a key is an extra field (not a standard LogRecord field)."""
        standard_fields = {
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "exc_info",
            "exc_text",
            "thread",
            "threadName",
            "taskName",
            "message",
        }
        return key not in standard_fields

    def _redact_string(self, value: str) -> str:
        """Redact sensitive patterns from a string."""
        return redact_sensitive_data(value, self.replacement)

    def _redact_value(self, value: Any) -> Any:
        """Redact a single value."""
        if isinstance(value, str):
            return self._redact_string(value)
        elif isinstance(value, dict):
            return self._redact_dict(value)
        elif isinstance(value, (list, tuple)):
            return type(value)(self._redact_value(v) for v in value)
        return value

    def _redact_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Redact sensitive keys and values from a dictionary."""
        result = {}
        for key, value in data.items():
            key_lower = key.lower().replace("-", "_")
            if key_lower in SENSITIVE_KEYS:
                result[key] = self.replacement
            else:
                result[key] = self._redact_value(value)
        return result


def setup_logging(
    formatter: JSONFormatter,
    level: int = logging.DEBUG,
    stream: Any = None,
) -> logging.Logger:
    """
    Setup logging with JSON formatter.

    Args:
        formatter: JSONFormatter instance
        level: Logging level (default: DEBUG)
        stream: Output stream (default: sys.stdout for 12-factor compliance)

    Returns:
        Root logger instance
    """
    if stream is None:
        stream = sys.stdout

    # Get root logger and remove existing handlers
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create handler with formatter
    handler = logging.StreamHandler(stream)
    handler.setLevel(level)
    handler.setFormatter(formatter)
    handler.addFilter(CorrelationIdFilter())
    root_logger.addHandler(handler)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Named logger instance
    """
    return logging.getLogger(name)


def setup_logger(
    name: str,
    *,
    level: int = logging.INFO,
    format_string: str | None = None,
    add_sensitive_filter: bool = True,
    add_correlation_filter: bool = True,
) -> logging.Logger:
    """
    Set up a logger with standard configuration.

    Creates a logger with:
    - Structured format including correlation ID
    - Sensitive data redaction filter
    - Correlation ID filter (ensures field is always present)

    Args:
        name: Logger name (usually __name__ or service name)
        level: Logging level (default: INFO)
        format_string: Custom format string (optional)
        add_sensitive_filter: Whether to add sensitive data filter
        add_correlation_filter: Whether to add correlation ID filter

    Returns:
        Configured logger instance

    Example:
        >>> logger = setup_logger("my_service")
        >>> logger.info("Request", extra={"correlation_id": "abc12345"})
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Don't add handlers if they already exist
    if logger.handlers:
        return logger

    # Default format with correlation ID
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - [%(correlation_id)s] %(message)s"

    # Create handler and formatter
    handler = logging.StreamHandler()
    handler.setLevel(level)
    formatter = logging.Formatter(format_string)
    handler.setFormatter(formatter)

    # Add filters
    if add_correlation_filter:
        handler.addFilter(CorrelationIdFilter())
    if add_sensitive_filter:
        handler.addFilter(SensitiveDataFilter())

    logger.addHandler(handler)

    return logger


def get_log_level_from_env() -> int:
    """
    Get log level from LOG_LEVEL environment variable.

    Supports: DEBUG, INFO, WARNING, ERROR, CRITICAL (case-insensitive)
    Default: INFO

    Returns:
        Logging level constant
    """
    import os

    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "WARN": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return level_map.get(level_name, logging.INFO)


def setup_server_logging(
    service_name: str,
    service_version: str,
    level: int | None = None,
) -> logging.Logger:
    """
    Setup JSON logging for an MCP server and return a named logger.

    This is a convenience function that combines JSONFormatter creation,
    logging setup, and logger retrieval into a single call.

    Args:
        service_name: Name of the MCP service (e.g., "n8n-mcp", "authentik-mcp")
        service_version: Version of the API (e.g., "v1", "v3", "v24.0")
        level: Logging level (default: from LOG_LEVEL env var, or INFO)

    Returns:
        Named logger instance for the service

    Example:
        >>> from mcp_common.logging import setup_server_logging
        >>> logger = setup_server_logging("n8n-mcp", "v1")
        >>> logger.info("Server starting...")

    Environment:
        LOG_LEVEL: Set to DEBUG, INFO, WARNING, ERROR, or CRITICAL
    """
    if level is None:
        level = get_log_level_from_env()
    formatter = JSONFormatter(service_name=service_name, service_version=service_version)
    setup_logging(formatter, level=level, stream=sys.stdout)
    return logging.getLogger(service_name)

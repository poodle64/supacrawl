"""Utility functions for web-scraper."""

from __future__ import annotations

import hashlib
import logging
from typing import Any
from urllib.parse import urlparse

from web_scraper.exceptions import generate_correlation_id

LOGGER = logging.getLogger(__name__)


def log_with_correlation(
    logger: logging.Logger,
    level: int,
    message: str,
    correlation_id: str | None = None,
    **kwargs: Any,
) -> None:
    """
    Log a message with correlation ID and additional context.

    Args:
        logger: Logger instance to use.
        level: Logging level (e.g., logging.INFO, logging.ERROR).
        message: Log message format string.
        correlation_id: Optional correlation ID. If None, generates a new one.
        **kwargs: Additional context to include in log extra fields.
    """
    corr_id = correlation_id or generate_correlation_id()
    extra = {"correlation_id": corr_id, **kwargs}
    logger.log(level, message, extra=extra)


def content_hash(text: str, url: str | None = None) -> str:
    """
    Return a deterministic SHA-256 hash for page content.

    Args:
        text: Page content to hash.
        url: Optional URL to include for extra stability.

    Returns:
        Hexadecimal hash string.
    """
    basis = (url or "") + "||" + text
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def url_path(url: str) -> str:
    """
    Extract a path component from a URL with a sensible default.

    Args:
        url: URL string.

    Returns:
        Path portion or "/" when absent.
    """
    parsed = urlparse(url)
    return parsed.path or "/"

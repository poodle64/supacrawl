"""Retry/backoff helpers for Crawl4AI operations."""

from __future__ import annotations

import os
import re


def retry_attempts() -> int:
    """Return max retry attempts for crawl operations."""
    try:
        return max(1, int(os.getenv("CRAWL4AI_RETRY_ATTEMPTS", "3")))
    except ValueError:
        return 3


def retry_base_delay() -> float:
    """Return base delay (seconds) for exponential backoff."""
    try:
        return max(0.1, float(os.getenv("CRAWL4AI_RETRY_BASE_DELAY", "1.0")))
    except ValueError:
        return 1.0


def retry_backoff() -> float:
    """Return multiplier for exponential backoff."""
    try:
        return max(1.0, float(os.getenv("CRAWL4AI_RETRY_BACKOFF", "2.0")))
    except ValueError:
        return 2.0


def retry_jitter() -> float:
    """Return jitter factor (0-1) to randomize backoff."""
    try:
        raw = float(os.getenv("CRAWL4AI_RETRY_JITTER", "0.3"))
        return max(0.0, min(raw, 1.0))
    except ValueError:
        return 0.3


def is_client_error(exc: Exception) -> bool:
    """Heuristic to avoid retrying on 4xx client errors."""
    status_candidates: list[int] = []
    for attr in ("status_code", "status", "code"):
        val = getattr(exc, attr, None)
        if isinstance(val, int):
            status_candidates.append(val)

    response = getattr(exc, "response", None)
    if response is not None:
        for attr in ("status_code", "status"):
            val = getattr(response, attr, None)
            if isinstance(val, int):
                status_candidates.append(val)

    for status in status_candidates:
        if 400 <= status < 500:
            return True

    msg = str(exc)
    match = re.search(r"\b4\d\d\b", msg) if msg else None
    if match:
        code = int(match.group(0))
        if 400 <= code < 500:
            return True

    return False

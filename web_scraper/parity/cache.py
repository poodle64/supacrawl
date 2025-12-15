"""Caching layer for Firecrawl artefacts."""

from __future__ import annotations

import hashlib
from pathlib import Path

import logging

LOGGER = logging.getLogger(__name__)


def _url_hash(url: str, provider: str) -> str:
    """
    Generate cache key hash for URL and provider.

    Args:
        url: URL to hash.
        provider: Provider name (mcp or api).

    Returns:
        Hex hash string.
    """
    key = f"{provider}:{url}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def get_cache_path(cache_dir: Path, url: str, provider: str) -> Path:
    """
    Get cache file path for a URL and provider.

    Args:
        cache_dir: Cache directory root.
        provider: Provider name (mcp or api).

    Returns:
        Path to cache file.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = _url_hash(url, provider)
    return cache_dir / f"{cache_key}.md"


def read_cache(cache_path: Path) -> str | None:
    """
    Read markdown content from cache.

    Args:
        cache_path: Path to cache file.

    Returns:
        Cached markdown content, or None if not found.
    """
    if not cache_path.exists():
        return None

    try:
        return cache_path.read_text(encoding="utf-8")
    except Exception as e:
        LOGGER.warning(f"Failed to read cache {cache_path}: {e}")
        return None


def write_cache(cache_path: Path, markdown: str) -> None:
    """
    Write markdown content to cache.

    Args:
        cache_path: Path to cache file.
        markdown: Markdown content to cache.
    """
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(markdown, encoding="utf-8")
    except Exception as e:
        LOGGER.warning(f"Failed to write cache {cache_path}: {e}")


def load_urls_from_file(urls_file: Path) -> list[str]:
    """
    Load URLs from a text file (one URL per line).

    Args:
        urls_file: Path to URLs file.

    Returns:
        List of URLs.
    """
    urls = []
    with urls_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


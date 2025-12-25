"""Configuration helpers for supacrawl."""

from __future__ import annotations

from pathlib import Path


def default_sites_dir(base_path: Path | None = None) -> Path:
    """
    Return the sites directory, defaulting to the current working directory.

    Args:
        base_path: Optional base path. If None, uses current working directory.

    Returns:
        Path to the sites directory.
    """
    root = base_path or Path.cwd()
    return root / "sites"


def default_corpora_dir(base_path: Path | None = None) -> Path:
    """
    Return the corpora directory, defaulting to the current working directory.

    Args:
        base_path: Optional base path. If None, uses current working directory.

    Returns:
        Path to the corpora directory.
    """
    root = base_path or Path.cwd()
    return root / "corpora"

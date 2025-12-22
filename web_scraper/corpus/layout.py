"""Filesystem layout helpers for corpora snapshots."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def new_snapshot_id(now: datetime | None = None) -> str:
    """
    Return a timestamped snapshot identifier.

    Args:
        now: Optional datetime to use. If None, uses current time in Australia/Brisbane.

    Returns:
        Snapshot ID string in format YYYY-MM-DD_HHMM (e.g., 2025-12-12_2238).
    """
    current = now or datetime.now(ZoneInfo("Australia/Brisbane"))
    return current.strftime("%Y-%m-%d_%H%M")


def snapshot_root(site_id: str, corpora_root: Path, snapshot_id: str) -> Path:
    """
    Return the root directory for a snapshot.

    Args:
        site_id: Site identifier.
        corpora_root: Root directory for all corpora.
        snapshot_id: Snapshot identifier.

    Returns:
        Path to the snapshot root directory.
    """
    return corpora_root / site_id / snapshot_id


def pages_dir(snapshot_path: Path) -> Path:
    """
    Return the pages directory under a snapshot.

    Args:
        snapshot_path: Path to the snapshot root directory.

    Returns:
        Path to the pages subdirectory.
    """
    return snapshot_path / "pages"

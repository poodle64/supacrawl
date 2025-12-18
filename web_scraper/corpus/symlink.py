"""Symlink utilities for corpus snapshot management."""

from __future__ import annotations

import logging
from pathlib import Path

LOGGER = logging.getLogger(__name__)

LATEST_SYMLINK_NAME = "latest"


def update_latest_symlink(site_dir: Path, snapshot_id: str) -> Path:
    """
    Create or update the 'latest' symlink to point to a snapshot.

    Args:
        site_dir: Site directory containing snapshots (e.g., corpora/my-site/).
        snapshot_id: Snapshot directory name to link to.

    Returns:
        Path to the created symlink.
    """
    symlink_path = site_dir / LATEST_SYMLINK_NAME
    target = Path(snapshot_id)  # Relative target

    # Remove existing symlink if present
    if symlink_path.is_symlink():
        symlink_path.unlink()
    elif symlink_path.exists():
        # If it's a regular file/directory (shouldn't happen), log warning
        LOGGER.warning("Removing non-symlink at %s", symlink_path)
        if symlink_path.is_dir():
            symlink_path.rmdir()
        else:
            symlink_path.unlink()

    symlink_path.symlink_to(target)
    LOGGER.debug("Updated symlink: %s -> %s", symlink_path, target)
    return symlink_path


def resolve_latest_snapshot(site_dir: Path) -> Path | None:
    """
    Resolve the 'latest' symlink to its target snapshot directory.

    Args:
        site_dir: Site directory containing snapshots.

    Returns:
        Path to the snapshot directory, or None if symlink doesn't exist.
    """
    symlink_path = site_dir / LATEST_SYMLINK_NAME
    if not symlink_path.is_symlink():
        return None

    # Resolve relative to site_dir
    target = symlink_path.resolve()
    if target.exists() and target.is_dir():
        return target
    return None


def remove_symlink_if_exists(symlink_path: Path) -> None:
    """
    Remove a symlink if it exists.

    Args:
        symlink_path: Path to the symlink to remove.
    """
    if symlink_path.is_symlink():
        symlink_path.unlink()


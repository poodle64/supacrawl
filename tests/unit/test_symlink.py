"""Unit tests for symlink utilities."""

from __future__ import annotations

from pathlib import Path


from web_scraper.corpus.symlink import (
    LATEST_SYMLINK_NAME,
    remove_symlink_if_exists,
    resolve_latest_snapshot,
    update_latest_symlink,
)


def test_update_latest_symlink_creates_symlink(tmp_path: Path) -> None:
    """Test that update_latest_symlink creates a symlink."""
    site_dir = tmp_path / "my-site"
    site_dir.mkdir()
    snapshot_dir = site_dir / "2025-12-18_1430"
    snapshot_dir.mkdir()

    result = update_latest_symlink(site_dir, "2025-12-18_1430")

    assert result == site_dir / LATEST_SYMLINK_NAME
    assert result.is_symlink()
    assert result.resolve() == snapshot_dir


def test_update_latest_symlink_replaces_existing(tmp_path: Path) -> None:
    """Test that update_latest_symlink replaces an existing symlink."""
    site_dir = tmp_path / "my-site"
    site_dir.mkdir()
    old_snapshot = site_dir / "2025-12-17_0900"
    old_snapshot.mkdir()
    new_snapshot = site_dir / "2025-12-18_1430"
    new_snapshot.mkdir()

    # Create initial symlink
    update_latest_symlink(site_dir, "2025-12-17_0900")

    # Update to new snapshot
    result = update_latest_symlink(site_dir, "2025-12-18_1430")

    assert result.is_symlink()
    assert result.resolve() == new_snapshot


def test_resolve_latest_snapshot_returns_path(tmp_path: Path) -> None:
    """Test that resolve_latest_snapshot returns the target path."""
    site_dir = tmp_path / "my-site"
    site_dir.mkdir()
    snapshot_dir = site_dir / "2025-12-18_1430"
    snapshot_dir.mkdir()
    update_latest_symlink(site_dir, "2025-12-18_1430")

    result = resolve_latest_snapshot(site_dir)

    assert result == snapshot_dir


def test_resolve_latest_snapshot_returns_none_when_missing(tmp_path: Path) -> None:
    """Test that resolve_latest_snapshot returns None when symlink is missing."""
    site_dir = tmp_path / "my-site"
    site_dir.mkdir()

    result = resolve_latest_snapshot(site_dir)

    assert result is None


def test_remove_symlink_if_exists_removes_symlink(tmp_path: Path) -> None:
    """Test that remove_symlink_if_exists removes a symlink."""
    site_dir = tmp_path / "my-site"
    site_dir.mkdir()
    snapshot_dir = site_dir / "2025-12-18_1430"
    snapshot_dir.mkdir()
    symlink_path = update_latest_symlink(site_dir, "2025-12-18_1430")

    remove_symlink_if_exists(symlink_path)

    assert not symlink_path.exists()


def test_remove_symlink_if_exists_no_error_when_missing(tmp_path: Path) -> None:
    """Test that remove_symlink_if_exists does not error when symlink is missing."""
    symlink_path = tmp_path / "nonexistent"

    # Should not raise
    remove_symlink_if_exists(symlink_path)


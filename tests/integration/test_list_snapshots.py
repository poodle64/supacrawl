"""Integration tests for list-snapshots command."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from web_scraper.cli import app


def _create_snapshot_with_manifest(
    base_path: Path,
    site_name: str,
    snapshot_id: str,
    status: str = "completed",
    total_pages: int = 10,
    created_at: str = "2025-12-18T14:30:00+10:00",
    with_chunks: bool = False,
) -> Path:
    """Create a snapshot directory with manifest.json."""
    snapshot_path = base_path / "corpora" / site_name / snapshot_id
    snapshot_path.mkdir(parents=True, exist_ok=True)
    
    manifest = {
        "site_id": site_name,
        "status": status,
        "total_pages": total_pages,
        "created_at": created_at,
        "pages": [],
    }
    (snapshot_path / "manifest.json").write_text(json.dumps(manifest))
    
    if with_chunks:
        # Create dummy chunks file
        chunks_content = "\n".join([
            json.dumps({"page_url": f"https://example.com/{i}", "chunk_index": 0, "content": "test"})
            for i in range(5)
        ])
        (snapshot_path / "chunks.jsonl").write_text(chunks_content)
    
    return snapshot_path


def test_list_snapshots_shows_snapshot_metadata(tmp_path: Path) -> None:
    """List-snapshots command should show snapshot metadata."""
    _create_snapshot_with_manifest(
        tmp_path,
        "test-site",
        "2025-12-18_1430",
        status="completed",
        total_pages=42,
        created_at="2025-12-18T14:30:00+10:00",
        with_chunks=True,
    )
    
    runner = CliRunner()
    result = runner.invoke(
        app, ["list-snapshots", "test-site", "--base-path", str(tmp_path)]
    )
    
    assert result.exit_code == 0
    assert "2025-12-18_1430" in result.output
    assert "completed" in result.output
    assert "42 pages" in result.output
    assert "5 chunks" in result.output


def test_list_snapshots_sorts_newest_first(tmp_path: Path) -> None:
    """List-snapshots should sort snapshots newest first."""
    _create_snapshot_with_manifest(tmp_path, "test-site", "2025-12-17_0900")
    _create_snapshot_with_manifest(tmp_path, "test-site", "2025-12-18_1430")
    _create_snapshot_with_manifest(tmp_path, "test-site", "2025-12-16_2100")
    
    runner = CliRunner()
    result = runner.invoke(
        app, ["list-snapshots", "test-site", "--base-path", str(tmp_path)]
    )
    
    assert result.exit_code == 0
    lines = result.output.strip().split("\n")
    # Should have 3 snapshot lines
    assert len(lines) == 3
    # Check order (newest first)
    assert "2025-12-18_1430" in lines[0]
    assert "2025-12-17_0900" in lines[1]
    assert "2025-12-16_2100" in lines[2]


def test_list_snapshots_handles_missing_site(tmp_path: Path) -> None:
    """List-snapshots should handle missing site directory gracefully."""
    runner = CliRunner()
    result = runner.invoke(
        app, ["list-snapshots", "nonexistent-site", "--base-path", str(tmp_path)]
    )
    
    assert result.exit_code == 0
    assert "No snapshots found" in result.output


def test_list_snapshots_handles_empty_site_directory(tmp_path: Path) -> None:
    """List-snapshots should handle empty site directory."""
    site_dir = tmp_path / "corpora" / "test-site"
    site_dir.mkdir(parents=True, exist_ok=True)
    
    runner = CliRunner()
    result = runner.invoke(
        app, ["list-snapshots", "test-site", "--base-path", str(tmp_path)]
    )
    
    assert result.exit_code == 0
    assert "No snapshots found" in result.output


def test_list_snapshots_ignores_latest_symlink(tmp_path: Path) -> None:
    """List-snapshots should ignore the 'latest' symlink."""
    _create_snapshot_with_manifest(tmp_path, "test-site", "2025-12-18_1430")
    
    # Create latest symlink
    site_dir = tmp_path / "corpora" / "test-site"
    latest_symlink = site_dir / "latest"
    latest_symlink.symlink_to("2025-12-18_1430")
    
    runner = CliRunner()
    result = runner.invoke(
        app, ["list-snapshots", "test-site", "--base-path", str(tmp_path)]
    )
    
    assert result.exit_code == 0
    lines = result.output.strip().split("\n")
    # Should have only 1 snapshot line (not 2)
    assert len(lines) == 1
    assert "2025-12-18_1430" in lines[0]


def test_list_snapshots_shows_dash_for_missing_chunks(tmp_path: Path) -> None:
    """List-snapshots should show '-' for snapshots without chunks."""
    _create_snapshot_with_manifest(
        tmp_path,
        "test-site",
        "2025-12-18_1430",
        with_chunks=False,
    )
    
    runner = CliRunner()
    result = runner.invoke(
        app, ["list-snapshots", "test-site", "--base-path", str(tmp_path)]
    )
    
    assert result.exit_code == 0
    assert "   - chunks" in result.output


def test_list_snapshots_handles_invalid_manifest(tmp_path: Path) -> None:
    """List-snapshots should skip snapshots with invalid manifests."""
    # Create valid snapshot
    _create_snapshot_with_manifest(tmp_path, "test-site", "2025-12-18_1430")
    
    # Create snapshot with invalid manifest
    invalid_snapshot = tmp_path / "corpora" / "test-site" / "2025-12-17_0900"
    invalid_snapshot.mkdir(parents=True, exist_ok=True)
    (invalid_snapshot / "manifest.json").write_text("invalid json {")
    
    runner = CliRunner()
    result = runner.invoke(
        app, ["list-snapshots", "test-site", "--base-path", str(tmp_path)]
    )
    
    assert result.exit_code == 0
    # Should only show the valid snapshot
    assert "2025-12-18_1430" in result.output
    assert "2025-12-17_0900" not in result.output


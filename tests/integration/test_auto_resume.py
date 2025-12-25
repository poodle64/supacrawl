"""Integration tests for auto-resume behaviour."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from supacrawl.cli import app
from supacrawl.corpus.state import CrawlState, save_state


def _write_site_config(base_path: Path) -> None:
    """Write a minimal site config for testing."""
    sites_dir = base_path / "sites"
    sites_dir.mkdir(parents=True, exist_ok=True)
    (sites_dir / "test-site.yaml").write_text(
        "id: test-site\n"
        "name: Test Site\n"
        "entrypoints:\n"
        "  - https://example.com\n"
        "include:\n"
        "  - https://example.com/**\n"
        "exclude: []\n"
        "max_pages: 10\n"
        "formats:\n"
        "  - markdown\n"
        "only_main_content: true\n"
        "include_subdomains: false\n",
        encoding="utf-8",
    )


def _create_incomplete_snapshot(base_path: Path, site_id: str) -> Path:
    """Create an incomplete snapshot with in_progress state."""
    snapshot_path = base_path / "corpora" / site_id / "2025-12-18_1430"
    snapshot_path.mkdir(parents=True, exist_ok=True)
    meta_dir = snapshot_path / ".meta"
    meta_dir.mkdir(exist_ok=True)
    
    # Create in_progress state
    state = CrawlState(status="in_progress", checkpoint_page=5)
    state.completed_urls.add("https://example.com")
    save_state(state, snapshot_path)
    
    # Create minimal manifest
    manifest = {
        "site_id": site_id,
        "status": "in_progress",
        "pages": [],
    }
    (snapshot_path / "manifest.json").write_text(json.dumps(manifest))
    
    return snapshot_path


def test_auto_resume_detects_incomplete_snapshot(tmp_path: Path) -> None:
    """Crawl should auto-resume when incomplete snapshot exists."""
    _write_site_config(tmp_path)
    _create_incomplete_snapshot(tmp_path, "test-site")
    
    runner = CliRunner()
    # Note: This will fail to actually crawl without mocking the scraper,
    # but we can check the output message before the failure
    result = runner.invoke(
        app, ["crawl", "test-site", "--base-path", str(tmp_path)],
    )
    
    # Should mention resuming in the output (even if crawl fails later)
    assert "Resuming" in result.output


def test_fresh_flag_ignores_incomplete_snapshot(tmp_path: Path) -> None:
    """--fresh flag should start new crawl even with incomplete snapshot."""
    _write_site_config(tmp_path)
    _create_incomplete_snapshot(tmp_path, "test-site")
    
    runner = CliRunner()
    result = runner.invoke(
        app, ["crawl", "test-site", "--fresh", "--base-path", str(tmp_path)],
    )
    
    # Should mention ignoring incomplete or starting fresh
    assert "fresh" in result.output.lower() or "ignoring" in result.output.lower()


"""Integration tests for Phase 9 output improvements."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from web_scraper.cli import app


def test_crawl_output_shows_latest_path(monkeypatch, tmp_path: Path) -> None:
    """Test that crawl output shows corpora/<site_id>/latest/ path."""
    from tests.integration.test_cli import FakeScraper, _write_site_config
    
    base_path = tmp_path
    _write_site_config(base_path)
    
    monkeypatch.setattr("web_scraper.cli.Crawl4AIScraper", FakeScraper)
    
    runner = CliRunner()
    result = runner.invoke(
        app, ["crawl", "example", "--base-path", str(base_path)]
    )
    
    assert result.exit_code == 0
    # With --base-path, should show base_path/corpora/...
    assert f"Output: {base_path}/corpora/example/latest/" in result.output
    assert "Crawled 1 pages" in result.output


def test_crawl_output_without_base_path(monkeypatch, tmp_path: Path) -> None:
    """Test that crawl without --base-path shows relative corpora/ path."""
    from tests.integration.test_cli import FakeScraper
    
    # Create config in current working directory pattern
    sites_dir = tmp_path / "sites"
    sites_dir.mkdir(parents=True)
    (sites_dir / "example.yaml").write_text(
        "name: Example Site\n"
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
    
    monkeypatch.setattr("web_scraper.cli.Crawl4AIScraper", FakeScraper)
    # Change to tmp_path so relative paths work
    monkeypatch.chdir(tmp_path)
    
    runner = CliRunner()
    result = runner.invoke(app, ["crawl", "example"])
    
    assert result.exit_code == 0
    # Without --base-path, should show relative corpora/ path
    assert "Output: corpora/example/latest/" in result.output


def test_crawl_with_chunks_shows_chunk_count(monkeypatch, tmp_path: Path) -> None:
    """Test that crawl --chunks shows chunk count in output."""
    from tests.integration.test_cli import FakeScraper, _write_site_config
    
    base_path = tmp_path
    _write_site_config(base_path)
    
    monkeypatch.setattr("web_scraper.cli.Crawl4AIScraper", FakeScraper)
    
    runner = CliRunner()
    result = runner.invoke(
        app, ["crawl", "example", "--chunks", "--base-path", str(base_path)]
    )
    
    assert result.exit_code == 0
    assert "generated" in result.output.lower()
    assert "chunks" in result.output.lower()


def test_dry_run_output_is_clean(tmp_path: Path) -> None:
    """Test that --dry-run shows clean URL list and summary."""
    from tests.integration.test_cli import _write_site_config
    
    base_path = tmp_path
    _write_site_config(base_path)
    
    # Mock map_site to return test URLs
    async def mock_map_site(config, max_urls=None):
        return [
            {"url": "https://example.com"},
            {"url": "https://example.com/page1"},
            {"url": "https://example.com/page2"},
        ]
    
    with patch("web_scraper.map.map_site", mock_map_site):
        runner = CliRunner()
        result = runner.invoke(
            app, ["crawl", "example", "--dry-run", "--base-path", str(base_path)]
        )
        
        assert result.exit_code == 0
        # Should show URLs
        assert "https://example.com" in result.output
        # Should show summary
        assert "URLs would be crawled" in result.output
        # Should NOT mention snapshots or corpora
        assert "snapshot" not in result.output.lower()
        assert "corpora" not in result.output.lower()


def test_resume_message_shows_progress(tmp_path: Path) -> None:
    """Test that resume message shows completed and pending counts."""
    from tests.integration.test_auto_resume import (
        _write_site_config,
        _create_incomplete_snapshot,
    )
    
    _write_site_config(tmp_path)
    _create_incomplete_snapshot(tmp_path, "test-site")
    
    runner = CliRunner()
    result = runner.invoke(
        app, ["crawl", "test-site", "--base-path", str(tmp_path)],
    )
    
    # Should show resuming with progress
    assert "Resuming" in result.output
    assert "completed" in result.output
    assert "pending" in result.output


def test_fresh_message_is_concise(tmp_path: Path) -> None:
    """Test that --fresh message is concise and user-friendly."""
    from tests.integration.test_auto_resume import (
        _write_site_config,
        _create_incomplete_snapshot,
    )
    
    _write_site_config(tmp_path)
    _create_incomplete_snapshot(tmp_path, "test-site")
    
    runner = CliRunner()
    result = runner.invoke(
        app, ["crawl", "test-site", "--fresh", "--base-path", str(tmp_path)],
    )
    
    # Should mention fresh or starting
    assert "fresh" in result.output.lower() or "Starting" in result.output


def test_chunk_command_respects_base_path(monkeypatch, tmp_path: Path) -> None:
    """Test that chunk command output respects --base-path."""
    from tests.integration.test_cli import FakeScraper, _write_site_config
    
    base_path = tmp_path
    _write_site_config(base_path)
    corpora_dir = base_path / "corpora"
    
    monkeypatch.setattr("web_scraper.cli.Crawl4AIScraper", FakeScraper)
    
    # First crawl to create a snapshot
    runner = CliRunner()
    crawl_result = runner.invoke(
        app, ["crawl", "example", "--base-path", str(base_path)]
    )
    assert crawl_result.exit_code == 0
    
    # Get snapshot ID
    site_dir = corpora_dir / "example"
    snapshots = [d for d in site_dir.iterdir() if d.is_dir() and d.name != "latest"]
    assert len(snapshots) == 1
    snapshot_id = snapshots[0].name
    
    # Now chunk it
    chunk_result = runner.invoke(
        app,
        [
            "chunk",
            "example",
            snapshot_id,
            "--base-path",
            str(base_path),
        ],
    )
    
    assert chunk_result.exit_code == 0
    # Should show base_path in output
    assert f"{base_path}/corpora/example/{snapshot_id}/chunks.jsonl" in chunk_result.output



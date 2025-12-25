"""Tests for corpus snapshot writing."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from supacrawl.corpus.writer import write_snapshot
from supacrawl.models import Page, SiteConfig


def _site_config() -> SiteConfig:
    return SiteConfig(
        id="site",
        name="Site",
        entrypoints=["https://example.com"],
        include=["https://example.com"],
        exclude=[],
        max_pages=5,
        formats=["markdown"],
        only_main_content=True,
        include_subdomains=False,
    )


def _page_with_special_path() -> Page:
    return Page(
        site_id="site",
        url="https://example.com/about",
        title="About Us",
        path="/about us/contact page",
        content_markdown="About content",
        content_hash="hash-about",
        provider="crawl4ai",
    )


def test_write_snapshot_writes_manifest_with_correlation_id(tmp_path: Path) -> None:
    """Snapshot manifest includes correlation ID and metadata."""
    site = _site_config()
    pages = [_page_with_special_path()]

    snapshot_path = asyncio.run(write_snapshot(site, pages, tmp_path))

    manifest = json.loads((snapshot_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["site_id"] == "site"
    assert manifest["total_pages"] == 1
    assert manifest["provider"] == "crawl4ai"
    assert manifest["entrypoints"] == ["https://example.com"]
    assert "correlation_id" in manifest
    assert manifest["created_at"].endswith("+10:00")


def test_write_snapshot_slug_sanitises_paths(tmp_path: Path) -> None:
    """Page paths preserve URL hierarchy in format-based directories."""
    site = _site_config()
    pages = [_page_with_special_path()]

    snapshot_path = asyncio.run(write_snapshot(site, pages, tmp_path))

    # URL is https://example.com/about -> markdown/about.md
    page_file = snapshot_path / "markdown" / "about.md"
    assert page_file.exists(), f"Expected markdown/about.md but found: {list((snapshot_path / 'markdown').iterdir())}"

    manifest = json.loads((snapshot_path / "manifest.json").read_text(encoding="utf-8"))
    stored_path = manifest["pages"][0]["path"]
    assert stored_path == "markdown/about.md"


def test_write_snapshot_empty_pages_list(tmp_path: Path) -> None:
    """Writing snapshot with empty pages list should create manifest with zero pages."""
    site = _site_config()
    pages: list[Page] = []

    snapshot_path = asyncio.run(write_snapshot(site, pages, tmp_path))

    manifest = json.loads((snapshot_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["total_pages"] == 0
    assert manifest["pages"] == []


def test_write_snapshot_multiple_pages(tmp_path: Path) -> None:
    """Writing snapshot with multiple pages should include all pages in manifest."""
    site = _site_config()
    pages = [
        Page(
            site_id="site",
            url="https://example.com/page1",
            title="Page 1",
            path="/page1",
            content_markdown="Content 1",
            content_hash="hash1",
            provider="crawl4ai",
        ),
        Page(
            site_id="site",
            url="https://example.com/page2",
            title="Page 2",
            path="/page2",
            content_markdown="Content 2",
            content_hash="hash2",
            provider="crawl4ai",
        ),
    ]

    snapshot_path = asyncio.run(write_snapshot(site, pages, tmp_path))

    manifest = json.loads((snapshot_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["total_pages"] == 2
    assert len(manifest["pages"]) == 2
    assert manifest["pages"][0]["url"] == "https://example.com/page1"
    assert manifest["pages"][1]["url"] == "https://example.com/page2"


def test_write_snapshot_id_format(tmp_path: Path) -> None:
    """Snapshot ID should be in YYYY-MM-DD_HHMM format."""
    from supacrawl.corpus.layout import new_snapshot_id
    import re

    snapshot_id = new_snapshot_id()
    pattern = r"^\d{4}-\d{2}-\d{2}_\d{4}$"
    assert re.match(pattern, snapshot_id) is not None, (
        f"Snapshot ID {snapshot_id} does not match format YYYY-MM-DD_HHMM"
    )

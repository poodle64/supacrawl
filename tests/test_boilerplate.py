"""Boilerplate fingerprinting integration tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from web_scraper.corpus.writer import IncrementalSnapshotWriter
from web_scraper.models import Page, SiteConfig
from web_scraper.utils import content_hash


def _site() -> SiteConfig:
    return SiteConfig(
        id="example",
        name="Example",
        entrypoints=["https://example.com"],
        include=["https://example.com/**"],
        exclude=[],
        max_pages=5,
        formats=["markdown"],
        only_main_content=True,
        include_subdomains=False,
    )


def _page(url: str, title: str, markdown: str) -> Page:
    return Page(
        site_id="example",
        url=url,
        title=title,
        path="/",
        content_markdown=markdown,
        content_hash=content_hash(markdown, url=url),
        provider="crawl4ai",
        extra={},
    )


def test_boilerplate_is_removed_and_manifest_records_hashes(tmp_path: Path) -> None:
    """Shared header/footer blocks should be removed and logged."""
    header = "Top Nav Link"
    footer = "Footer CTA"
    body1 = "Unique article content one " * 3
    body2 = "Unique article content two " * 3
    body_small = "Tiny body text."

    page1 = _page("https://example.com/1", "One", f"# One\n\n{header}\n\n{body1}\n\n{footer}")
    page2 = _page("https://example.com/2", "Two", f"# Two\n\n{header}\n\n{body2}\n\n{footer}")
    page3 = _page("https://example.com/3", "Three", f"# Three\n\n{header}\n\n{body_small}\n\n{footer}")

    writer = IncrementalSnapshotWriter(_site(), tmp_path)
    asyncio.run(writer.add_pages([page1]))
    asyncio.run(writer.add_pages([page2, page3]))
    asyncio.run(writer.complete())

    filtered = writer.get_filtered_pages()
    assert header not in filtered[0].content_markdown
    assert header not in filtered[1].content_markdown
    # Guardrail cap should keep boilerplate on the tiny page
    assert header in filtered[2].content_markdown

    manifest_path = tmp_path / _site().id / writer.snapshot_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest.get("boilerplate_hashes")

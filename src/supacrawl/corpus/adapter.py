"""Output adapters for crawl results.

Provides a Protocol for output adapters and a CorpusOutputAdapter implementation
that wraps IncrementalSnapshotWriter for full corpus output with manifests.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from supacrawl.corpus.state import find_resumable_snapshot, load_state
from supacrawl.corpus.writer import IncrementalSnapshotWriter
from supacrawl.models import Page, ScrapeResult, SiteConfig

LOGGER = logging.getLogger(__name__)


def _url_path(url: str) -> str:
    """Extract path component from URL for Page model."""
    parsed = urlparse(url)
    return parsed.path or "/"


def _content_hash(content: str) -> str:
    """Generate SHA256 hash of content."""
    return hashlib.sha256(content.encode()).hexdigest()


class OutputAdapter(Protocol):
    """Protocol for output adapters that receive crawl results."""

    async def start(self) -> None:
        """Initialize the output destination."""
        ...

    async def write_page(self, url: str, result: ScrapeResult) -> None:
        """Write a single scraped page.

        Args:
            url: Source URL
            result: ScrapeResult with content and metadata
        """
        ...

    async def complete(self) -> Path | None:
        """Finalize output and return path (if applicable)."""
        ...

    async def abort(self, error: str | None = None) -> None:
        """Abort output due to error."""
        ...

    def get_resume_urls(self) -> set[str]:
        """Return set of URLs already scraped (for resume support)."""
        ...


class CorpusOutputAdapter:
    """Output adapter that writes to corpus with manifest and resume support.

    Wraps IncrementalSnapshotWriter to provide the simplified OutputAdapter interface
    while maintaining full corpus functionality including:
    - Manifest generation
    - Directory structure
    - Resume state
    - Latest symlink

    Usage:
        adapter = CorpusOutputAdapter(site_config, corpora_dir, resume=True)
        await adapter.start()
        for url, result in scrape_results:
            await adapter.write_page(url, result)
        snapshot_path = await adapter.complete()
    """

    def __init__(
        self,
        site_config: SiteConfig,
        corpora_dir: Path,
        resume: bool = False,
    ):
        """Initialize corpus output adapter.

        Args:
            site_config: Site configuration
            corpora_dir: Root corpora directory
            resume: Whether to resume from previous incomplete crawl
        """
        self._site_config = site_config
        self._corpora_dir = corpora_dir
        self._resume = resume
        self._writer: IncrementalSnapshotWriter | None = None
        self._resume_snapshot: Path | None = None
        self._resume_urls: set[str] = set()

        # Find resumable snapshot if requested
        if resume:
            assert site_config.id is not None
            self._resume_snapshot = find_resumable_snapshot(corpora_dir, site_config.id)
            if self._resume_snapshot:
                state = load_state(self._resume_snapshot)
                if state:
                    self._resume_urls = set(state.completed_urls)
                    LOGGER.info(
                        f"Found resumable snapshot with {len(self._resume_urls)} completed URLs"
                    )

    async def start(self) -> None:
        """Initialize the corpus writer."""
        self._writer = IncrementalSnapshotWriter(
            site=self._site_config,
            corpora_root=self._corpora_dir,
            resume_snapshot=self._resume_snapshot,
        )
        await self._writer.start()
        LOGGER.info(f"Started corpus output: {self._writer.snapshot_path}")

    async def write_page(self, url: str, result: ScrapeResult) -> None:
        """Write a scraped page to corpus.

        Converts ScrapeResult to Page model for IncrementalSnapshotWriter.

        Args:
            url: Source URL
            result: ScrapeResult with content and metadata
        """
        if not self._writer:
            await self.start()

        if not result.success or not result.data:
            LOGGER.warning(f"Skipping failed scrape for {url}: {result.error}")
            return

        # After start(), _writer is guaranteed to be set
        writer = self._writer
        if writer is None:
            raise RuntimeError("Writer not initialized after start()")

        # Convert ScrapeResult to Page model
        markdown = result.data.markdown or ""
        page = Page(
            site_id=self._site_config.id or "unknown",
            url=url,
            title=result.data.metadata.title or "",
            path=_url_path(url),
            content_markdown=markdown,
            content_html=result.data.html,
            content_hash=_content_hash(markdown),
            provider="playwright",
            extra={
                "status_code": result.data.metadata.status_code,
                "language": result.data.metadata.language,
            },
        )

        await writer.add_pages([page])

    async def complete(self) -> Path | None:
        """Finalize corpus and return snapshot path."""
        if not self._writer:
            return None

        await self._writer.complete()
        LOGGER.info(f"Completed corpus output: {self._writer.snapshot_path}")
        return self._writer.snapshot_path

    async def abort(self, error: str | None = None) -> None:
        """Abort corpus output."""
        if self._writer:
            await self._writer.abort(error)
            LOGGER.warning(f"Aborted corpus output: {error}")

    def get_resume_urls(self) -> set[str]:
        """Return URLs already scraped from resume state."""
        return self._resume_urls

    @property
    def snapshot_path(self) -> Path | None:
        """Return current snapshot path if started."""
        return self._writer.snapshot_path if self._writer else None

    @property
    def snapshot_id(self) -> str | None:
        """Return current snapshot ID if started."""
        return self._writer.snapshot_id if self._writer else None

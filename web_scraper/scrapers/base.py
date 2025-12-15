"""Base scraper abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from web_scraper.models import Page, SiteConfig


class Scraper(ABC):
    """Abstract scraper interface."""

    provider_name: str

    @abstractmethod
    def crawl(
        self,
        config: SiteConfig,
        corpora_dir: Path | None = None,
        resume_snapshot: Path | None = None,
        target_urls: list[str] | None = None,
    ) -> tuple[list[Page], Path]:
        """
        Crawl a site configuration and return scraped pages.

        Args:
            config: Site configuration to crawl.
            corpora_dir: Base directory for corpus output.
                Defaults to cwd/corpora if None.
            resume_snapshot: Optional path to a snapshot to resume.
            target_urls: Optional explicit list of URLs to crawl.
                If provided, only crawl these URLs (no link discovery).

        Returns:
            Tuple of:
                - List of scraped Page objects.
                - Path to the snapshot directory.
        """
        pass

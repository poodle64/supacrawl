"""Progress reporting for web crawling operations.

This module provides progress tracking and reporting for long-running
crawl operations, with support for TTY and non-TTY environments.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TextIO

import click


@dataclass
class CrawlStats:
    """
    Statistics for a crawl operation.

    Attributes:
        total_pages: Expected total pages (if known from sitemap).
        completed_pages: Successfully crawled pages.
        failed_pages: Failed page requests.
        skipped_pages: Skipped pages (robots.txt, duplicates, etc.).
        total_bytes: Total content bytes downloaded.
        start_time: When the crawl started.
        errors_by_type: Count of errors by type.
    """

    total_pages: int | None = None
    completed_pages: int = 0
    failed_pages: int = 0
    skipped_pages: int = 0
    total_bytes: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    errors_by_type: dict[str, int] = field(default_factory=dict)

    @property
    def elapsed(self) -> timedelta:
        """Time elapsed since start."""
        return datetime.now() - self.start_time

    @property
    def elapsed_seconds(self) -> float:
        """Elapsed time in seconds."""
        return self.elapsed.total_seconds()

    @property
    def pages_per_second(self) -> float:
        """Average pages per second."""
        if self.elapsed_seconds <= 0:
            return 0.0
        return self.completed_pages / self.elapsed_seconds

    @property
    def eta(self) -> timedelta | None:
        """Estimated time remaining (if total known)."""
        if not self.total_pages or self.pages_per_second <= 0:
            return None
        remaining = self.total_pages - self.completed_pages
        if remaining <= 0:
            return timedelta(seconds=0)
        return timedelta(seconds=remaining / self.pages_per_second)

    @property
    def success_rate(self) -> float:
        """Percentage of successful pages."""
        total = self.completed_pages + self.failed_pages
        if total <= 0:
            return 100.0
        return (self.completed_pages / total) * 100


class ProgressReporter:
    """
    Report crawl progress to console.

    Supports both TTY (with live updates) and non-TTY (line-by-line) output.
    """

    def __init__(
        self,
        verbose: bool = False,
        show_progress: bool = True,
        output: TextIO | None = None,
    ):
        """
        Initialise progress reporter.

        Args:
            verbose: Show per-page details.
            show_progress: Show progress updates at all.
            output: Output stream (defaults to stderr).
        """
        self.verbose = verbose
        self.show_progress = show_progress
        self.output = output or sys.stderr
        self.stats = CrawlStats()
        self.current_url: str | None = None
        self._last_update = 0.0
        self._update_interval = 0.5  # Minimum seconds between updates
        self._is_tty = hasattr(self.output, "isatty") and self.output.isatty()

    def start(self, total_pages: int | None = None, site_name: str = "") -> None:
        """
        Start progress reporting.

        Args:
            total_pages: Expected total pages (if known).
            site_name: Name of site being crawled.
        """
        self.stats = CrawlStats(total_pages=total_pages)
        self.stats.start_time = datetime.now()

        if self.show_progress:
            total_str = str(total_pages) if total_pages else "?"
            click.echo(
                f"Starting crawl: {site_name} (max {total_str} pages)",
                file=self.output,
            )

    def update(
        self,
        url: str,
        status: str = "ok",
        error: str | None = None,
        content_size: int = 0,
        response_time: float = 0.0,
    ) -> None:
        """
        Update progress with a crawled page.

        Args:
            url: URL that was processed.
            status: Status of the request (ok, error, skipped).
            error: Error message if status is error.
            content_size: Size of content in bytes.
            response_time: Time to fetch page in seconds.
        """
        self.current_url = url

        if status == "ok":
            self.stats.completed_pages += 1
            self.stats.total_bytes += content_size
        elif status == "error":
            self.stats.failed_pages += 1
            if error:
                error_type = error.split(":")[0] if ":" in error else error
                self.stats.errors_by_type[error_type] = (
                    self.stats.errors_by_type.get(error_type, 0) + 1
                )
        elif status == "skipped":
            self.stats.skipped_pages += 1

        if not self.show_progress:
            return

        # Verbose mode: show each page
        if self.verbose:
            timestamp = datetime.now().strftime("%H:%M:%S")
            icon = "✓" if status == "ok" else "✗" if status == "error" else "○"
            time_str = f"({response_time:.1f}s)" if response_time > 0 else ""
            error_str = f" - {error}" if error else ""
            click.echo(
                f"[{timestamp}] {icon} {url} {time_str}{error_str}",
                file=self.output,
            )
        else:
            # Rate-limited progress bar updates
            now = time.time()
            if now - self._last_update >= self._update_interval:
                self._render_progress()
                self._last_update = now

    def _render_progress(self) -> None:
        """Render progress bar to output."""
        stats = self.stats
        completed = stats.completed_pages
        total = stats.total_pages

        # Build progress string
        if total:
            pct = min(completed / total * 100, 100)
            bar_width = 20
            filled = int(bar_width * pct / 100)
            bar = "█" * filled + "░" * (bar_width - filled)
            progress = f"[{bar}] {completed}/{total}"
        else:
            progress = f"{completed} pages"

        # Add rate
        rate = stats.pages_per_second
        rate_str = f" | {rate:.1f} p/s" if rate > 0 else ""

        # Add ETA
        eta = stats.eta
        eta_str = ""
        if eta:
            minutes, seconds = divmod(int(eta.total_seconds()), 60)
            eta_str = f" | ETA: {minutes:02d}:{seconds:02d}"

        # Add error count if any
        error_str = ""
        if stats.failed_pages > 0:
            error_str = f" | {stats.failed_pages} errors"

        line = f"Crawling: {progress}{rate_str}{eta_str}{error_str}"

        if self._is_tty:
            # Overwrite line in TTY
            click.echo(f"\r{line}".ljust(80), nl=False, file=self.output)
        else:
            # Print new line in non-TTY
            click.echo(line, file=self.output)

    def finish(self) -> None:
        """
        Finish progress reporting and show summary.
        """
        if not self.show_progress:
            return

        # Clear progress line if TTY
        if self._is_tty and not self.verbose:
            click.echo("\r" + " " * 80 + "\r", nl=False, file=self.output)

        stats = self.stats

        # Format elapsed time
        elapsed = stats.elapsed
        hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            elapsed_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            elapsed_str = f"{minutes:02d}:{seconds:02d}"

        # Format content size
        if stats.total_bytes >= 1024 * 1024:
            size_str = f"{stats.total_bytes / (1024 * 1024):.1f} MB"
        elif stats.total_bytes >= 1024:
            size_str = f"{stats.total_bytes / 1024:.1f} KB"
        else:
            size_str = f"{stats.total_bytes} bytes"

        # Print summary
        click.echo("\nCrawl Complete", file=self.output)
        click.echo("=" * 40, file=self.output)
        click.echo(f"Duration:     {elapsed_str}", file=self.output)
        click.echo(f"Total Pages:  {stats.completed_pages}", file=self.output)
        if stats.failed_pages > 0:
            click.echo(f"Failed:       {stats.failed_pages}", file=self.output)
        if stats.skipped_pages > 0:
            click.echo(f"Skipped:      {stats.skipped_pages}", file=self.output)
        click.echo(f"Content Size: {size_str}", file=self.output)
        if stats.pages_per_second > 0:
            click.echo(f"Avg Speed:    {stats.pages_per_second:.1f} pages/sec", file=self.output)

        # Show error breakdown if any
        if stats.errors_by_type:
            click.echo("\nErrors by type:", file=self.output)
            for error_type, count in sorted(
                stats.errors_by_type.items(), key=lambda x: -x[1]
            ):
                click.echo(f"  {error_type}: {count}", file=self.output)


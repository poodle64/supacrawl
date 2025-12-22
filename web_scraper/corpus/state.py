"""Crawl state management for resumption support.

This module provides state tracking and persistence to enable
resuming interrupted crawls.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

LOGGER = logging.getLogger(__name__)

# State file name within snapshot directory
STATE_FILE = ".meta/crawl_state.json"


def _brisbane_now() -> datetime:
    """Return current time in Australia/Brisbane timezone."""
    return datetime.now(ZoneInfo("Australia/Brisbane"))


@dataclass
class FailedURL:
    """A URL that failed to crawl."""

    url: str
    error: str
    attempts: int = 1
    last_attempt: datetime = field(default_factory=_brisbane_now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "url": self.url,
            "error": self.error,
            "attempts": self.attempts,
            "last_attempt": self.last_attempt.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FailedURL:
        """Create from dict."""
        last_attempt = data.get("last_attempt")
        if isinstance(last_attempt, str):
            last_attempt = datetime.fromisoformat(last_attempt)
        else:
            last_attempt = _brisbane_now()
        return cls(
            url=data["url"],
            error=data.get("error", "unknown"),
            attempts=data.get("attempts", 1),
            last_attempt=last_attempt,
        )


@dataclass
class CrawlState:
    """
    State of a crawl for resumption.

    Attributes:
        status: Current status (in_progress, completed, aborted).
        completed_urls: Set of successfully crawled URLs.
        pending_urls: Queue of URLs to crawl.
        failed_urls: URLs that failed with error details.
        last_updated: Timestamp of last state update.
        checkpoint_page: Number of pages successfully saved.
        config_hash: Hash of site config to detect changes.
    """

    status: str = "in_progress"
    completed_urls: set[str] = field(default_factory=set)
    pending_urls: list[str] = field(default_factory=list)
    failed_urls: list[FailedURL] = field(default_factory=list)
    last_updated: datetime = field(default_factory=_brisbane_now)
    checkpoint_page: int = 0
    config_hash: str = ""

    def mark_completed(self, url: str) -> None:
        """Mark a URL as successfully crawled."""
        self.completed_urls.add(url)
        self.checkpoint_page = len(self.completed_urls)
        self.last_updated = _brisbane_now()

    def mark_failed(self, url: str, error: str) -> None:
        """Mark a URL as failed."""
        # Check if already failed
        for failed in self.failed_urls:
            if failed.url == url:
                failed.attempts += 1
                failed.error = error
                failed.last_attempt = _brisbane_now()
                return
        self.failed_urls.append(FailedURL(url=url, error=error))
        self.last_updated = _brisbane_now()

    def add_pending(self, urls: list[str]) -> None:
        """Add URLs to pending queue (deduplicating)."""
        existing = self.completed_urls | set(self.pending_urls)
        for url in urls:
            if url not in existing:
                self.pending_urls.append(url)
        self.last_updated = _brisbane_now()

    def get_next_pending(self) -> str | None:
        """Get next URL to crawl from pending queue."""
        if self.pending_urls:
            return self.pending_urls.pop(0)
        return None

    def is_completed(self, url: str) -> bool:
        """Check if URL was already crawled."""
        return url in self.completed_urls

    def finish(self, status: str = "completed") -> None:
        """Mark crawl as finished."""
        self.status = status
        self.last_updated = _brisbane_now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "status": self.status,
            "completed_urls": list(self.completed_urls),
            "pending_urls": self.pending_urls,
            "failed_urls": [f.to_dict() for f in self.failed_urls],
            "last_updated": self.last_updated.isoformat(),
            "checkpoint_page": self.checkpoint_page,
            "config_hash": self.config_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CrawlState:
        """Create from dict."""
        last_updated = data.get("last_updated")
        if isinstance(last_updated, str):
            last_updated = datetime.fromisoformat(last_updated)
        else:
            last_updated = _brisbane_now()

        return cls(
            status=data.get("status", "in_progress"),
            completed_urls=set(data.get("completed_urls", [])),
            pending_urls=list(data.get("pending_urls", [])),
            failed_urls=[
                FailedURL.from_dict(f) for f in data.get("failed_urls", [])
            ],
            last_updated=last_updated,
            checkpoint_page=data.get("checkpoint_page", 0),
            config_hash=data.get("config_hash", ""),
        )


def save_state(state: CrawlState, snapshot_path: Path) -> None:
    """
    Save crawl state to snapshot directory.

    Args:
        state: CrawlState to save.
        snapshot_path: Path to snapshot directory.
    """
    state_file = snapshot_path / STATE_FILE
    state_file.parent.mkdir(parents=True, exist_ok=True)  # Creates .meta/ if needed

    try:
        with state_file.open("w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, indent=2)
        LOGGER.debug("Saved crawl state to %s", state_file)
    except Exception as e:
        LOGGER.error("Failed to save crawl state: %s", e)


def load_state(snapshot_path: Path) -> CrawlState | None:
    """
    Load crawl state from snapshot directory.

    Args:
        snapshot_path: Path to snapshot directory.

    Returns:
        CrawlState if found and valid, None otherwise.
    """
    state_file = snapshot_path / STATE_FILE

    # Backward compatibility: check old location
    old_state_file = snapshot_path / "crawl_state.json"
    if not state_file.exists() and old_state_file.exists():
        state_file = old_state_file
        LOGGER.debug("Using legacy state file location: %s", old_state_file)

    if not state_file.exists():
        return None

    try:
        with state_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        state = CrawlState.from_dict(data)
        LOGGER.info(
            "Loaded crawl state: %d completed, %d pending, %d failed",
            len(state.completed_urls),
            len(state.pending_urls),
            len(state.failed_urls),
        )
        return state
    except Exception as e:
        LOGGER.error("Failed to load crawl state: %s", e)
        return None


def find_latest_snapshot(corpora_dir: Path, site_id: str) -> Path | None:
    """
    Find the most recent snapshot for a site.

    Args:
        corpora_dir: Base corpora directory.
        site_id: Site identifier.

    Returns:
        Path to latest snapshot, or None if no snapshots exist.
    """
    site_dir = corpora_dir / site_id
    if not site_dir.exists():
        return None

    snapshots = sorted(
        [d for d in site_dir.iterdir() if d.is_dir()],
        key=lambda p: p.name,
        reverse=True,
    )

    if snapshots:
        return snapshots[0]
    return None


def find_resumable_snapshot(corpora_dir: Path, site_id: str) -> Path | None:
    """
    Find a resumable (in-progress) snapshot for a site.

    Args:
        corpora_dir: Base corpora directory.
        site_id: Site identifier.

    Returns:
        Path to resumable snapshot, or None if none found.
    """
    latest = find_latest_snapshot(corpora_dir, site_id)
    if not latest:
        return None

    state = load_state(latest)
    if state and state.status == "in_progress":
        return latest

    return None


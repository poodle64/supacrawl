"""Corpus writing utilities."""

from web_scraper.corpus.compress import compress_snapshot, extract_archive
from web_scraper.corpus.layout import new_snapshot_id, pages_dir, snapshot_root
from web_scraper.corpus.state import CrawlState, load_state, save_state
from web_scraper.corpus.writer import IncrementalSnapshotWriter, write_snapshot

__all__ = [
    "compress_snapshot",
    "extract_archive",
    "new_snapshot_id",
    "pages_dir",
    "snapshot_root",
    "CrawlState",
    "load_state",
    "save_state",
    "IncrementalSnapshotWriter",
    "write_snapshot",
]

"""Tests for change tracking feature."""

from pathlib import Path

from supacrawl.cache import CacheEntry, CacheManager
from supacrawl.models import ChangeTrackingData, ChangeTrackingDiff, ScrapeData
from supacrawl.services.scrape import (
    _build_change_tracking,
    _compute_content_hash,
    _generate_unified_diff,
)


class TestComputeContentHash:
    """Tests for _compute_content_hash."""

    def test_hash_of_none(self):
        result = _compute_content_hash(None)
        assert isinstance(result, str)
        assert len(result) == 64  # SHA256 hex digest

    def test_hash_of_empty_string(self):
        result = _compute_content_hash("")
        assert result == _compute_content_hash(None)  # Both hash empty bytes

    def test_hash_deterministic(self):
        assert _compute_content_hash("hello") == _compute_content_hash("hello")

    def test_hash_different_content(self):
        assert _compute_content_hash("hello") != _compute_content_hash("world")

    def test_hash_is_sha256(self):
        import hashlib

        expected = hashlib.sha256(b"test content").hexdigest()
        assert _compute_content_hash("test content") == expected


class TestBuildChangeTracking:
    """Tests for _build_change_tracking."""

    def test_new_status_when_no_previous(self):
        ct = _build_change_tracking(None, "abc123", "hello")
        assert ct.change_status == "new"
        assert ct.content_hash == "abc123"
        assert ct.previous_scrape_at is None
        assert ct.diff is None

    def test_same_status_when_hashes_match(self):
        entry = CacheEntry(
            url="http://example.com",
            cached_at="2026-03-01T10:00:00Z",
            expires_at="2026-03-02T10:00:00Z",
            content_hash="abc123",
            response={},
        )
        ct = _build_change_tracking(entry, "abc123", "hello")
        assert ct.change_status == "same"
        assert ct.previous_scrape_at == "2026-03-01T10:00:00Z"

    def test_changed_status_when_hashes_differ(self):
        entry = CacheEntry(
            url="http://example.com",
            cached_at="2026-03-01T10:00:00Z",
            expires_at="2026-03-02T10:00:00Z",
            content_hash="abc123",
            response={},
        )
        ct = _build_change_tracking(entry, "def456", "world")
        assert ct.change_status == "changed"
        assert ct.diff is None  # No diff mode requested

    def test_changed_status_when_no_previous_hash(self):
        """When previous entry has no content_hash (old cache format), treat as changed."""
        entry = CacheEntry(
            url="http://example.com",
            cached_at="2026-03-01T10:00:00Z",
            expires_at="2026-03-02T10:00:00Z",
            content_hash=None,
            response={},
        )
        ct = _build_change_tracking(entry, "abc123", "hello")
        assert ct.change_status == "changed"

    def test_git_diff_mode_generates_diff(self):
        entry = CacheEntry(
            url="http://example.com",
            cached_at="2026-03-01T10:00:00Z",
            expires_at="2026-03-02T10:00:00Z",
            content_hash="abc123",
            response={"data": {"markdown": "Hello World\nLine 2\n"}},
        )
        ct = _build_change_tracking(
            entry, "def456", "Hello World\nLine 2 changed\n", change_tracking_modes=["git-diff"]
        )
        assert ct.change_status == "changed"
        assert ct.diff is not None
        assert "--- previous" in ct.diff.text
        assert "+++ current" in ct.diff.text
        assert "-Line 2" in ct.diff.text
        assert "+Line 2 changed" in ct.diff.text

    def test_git_diff_not_generated_when_same(self):
        entry = CacheEntry(
            url="http://example.com",
            cached_at="2026-03-01T10:00:00Z",
            expires_at="2026-03-02T10:00:00Z",
            content_hash="abc123",
            response={"data": {"markdown": "same content"}},
        )
        ct = _build_change_tracking(entry, "abc123", "same content", change_tracking_modes=["git-diff"])
        assert ct.change_status == "same"
        assert ct.diff is None  # No diff when content is the same


class TestGenerateUnifiedDiff:
    """Tests for _generate_unified_diff."""

    def test_generates_diff(self):
        entry = CacheEntry(
            url="http://example.com",
            cached_at="2026-03-01T10:00:00Z",
            expires_at="2026-03-02T10:00:00Z",
            response={"data": {"markdown": "line 1\nline 2\n"}},
        )
        diff = _generate_unified_diff(entry, "line 1\nline 3\n")
        assert diff is not None
        assert "-line 2" in diff.text
        assert "+line 3" in diff.text

    def test_returns_none_when_identical(self):
        entry = CacheEntry(
            url="http://example.com",
            cached_at="2026-03-01T10:00:00Z",
            expires_at="2026-03-02T10:00:00Z",
            response={"data": {"markdown": "same\n"}},
        )
        diff = _generate_unified_diff(entry, "same\n")
        assert diff is None

    def test_handles_missing_previous_markdown(self):
        entry = CacheEntry(
            url="http://example.com",
            cached_at="2026-03-01T10:00:00Z",
            expires_at="2026-03-02T10:00:00Z",
            response={"data": {}},
        )
        diff = _generate_unified_diff(entry, "new content\n")
        assert diff is not None
        assert "+new content" in diff.text

    def test_handles_none_current_markdown(self):
        entry = CacheEntry(
            url="http://example.com",
            cached_at="2026-03-01T10:00:00Z",
            expires_at="2026-03-02T10:00:00Z",
            response={"data": {"markdown": "old content\n"}},
        )
        diff = _generate_unified_diff(entry, None)
        assert diff is not None
        assert "-old content" in diff.text


class TestCacheManagerGetPrevious:
    """Tests for CacheManager.get_previous."""

    def test_returns_none_when_no_cache(self, tmp_path: Path):
        cache = CacheManager(cache_dir=tmp_path / "cache")
        result = cache.get_previous("http://example.com")
        assert result is None

    def test_returns_entry_ignoring_expiry(self, tmp_path: Path):
        cache = CacheManager(cache_dir=tmp_path / "cache")
        # Store an entry with very short max_age (already expired)
        cache.set("http://example.com", {"success": True}, max_age=1, content_hash="abc123")

        # get() would return None (expired), but get_previous should return it
        entry = cache.get_previous("http://example.com")
        assert entry is not None
        assert entry.content_hash == "abc123"
        assert entry.url == "http://example.com"

    def test_stores_and_retrieves_content_hash(self, tmp_path: Path):
        cache = CacheManager(cache_dir=tmp_path / "cache")
        cache.set("http://example.com", {"success": True}, max_age=3600, content_hash="sha256test")

        entry = cache.get_previous("http://example.com")
        assert entry is not None
        assert entry.content_hash == "sha256test"

    def test_backwards_compatible_with_no_hash(self, tmp_path: Path):
        """Old cache entries without content_hash should still work."""
        cache = CacheManager(cache_dir=tmp_path / "cache")
        cache.set("http://example.com", {"success": True}, max_age=3600)

        entry = cache.get_previous("http://example.com")
        assert entry is not None
        assert entry.content_hash is None


class TestChangeTrackingModels:
    """Tests for change tracking Pydantic models."""

    def test_change_tracking_data_serialisation(self):
        ct = ChangeTrackingData(
            previous_scrape_at="2026-03-01T10:00:00Z",
            change_status="changed",
            content_hash="abc123",
        )
        data = ct.model_dump()
        assert data["change_status"] == "changed"
        assert data["visibility"] == "visible"
        assert data["diff"] is None

    def test_change_tracking_with_diff(self):
        ct = ChangeTrackingData(
            change_status="changed",
            diff=ChangeTrackingDiff(text="--- a\n+++ b\n@@ -1 +1 @@\n-old\n+new"),
        )
        data = ct.model_dump()
        assert data["diff"]["text"].startswith("--- a")

    def test_scrape_data_includes_change_tracking(self):
        from supacrawl.models import ScrapeMetadata

        sd = ScrapeData(
            metadata=ScrapeMetadata(),
            change_tracking=ChangeTrackingData(change_status="new", content_hash="abc"),
        )
        data = sd.model_dump()
        assert data["change_tracking"]["change_status"] == "new"

    def test_scrape_data_change_tracking_default_none(self):
        from supacrawl.models import ScrapeMetadata

        sd = ScrapeData(metadata=ScrapeMetadata())
        assert sd.change_tracking is None

    def test_all_change_statuses_valid(self):
        for status in ("new", "same", "changed", "removed"):
            ct = ChangeTrackingData(change_status=status)
            assert ct.change_status == status

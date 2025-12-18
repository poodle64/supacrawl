"""Unit tests for parity cache functionality."""

from __future__ import annotations

from pathlib import Path

from tools.parity.cache import (
    get_cache_path,
    load_urls_from_file,
    read_cache,
    write_cache,
)


class TestCacheOperations:
    """Tests for cache read/write operations."""

    def test_write_and_read_cache(self, tmp_path: Path) -> None:
        """Test writing and reading cache."""
        cache_dir = tmp_path / "cache"
        url = "https://example.com"
        provider = "mcp"
        content = "# Test Markdown Content"

        cache_path = get_cache_path(cache_dir, url, provider)
        write_cache(cache_path, content)

        assert cache_path.exists()
        assert read_cache(cache_path) == content

    def test_read_cache_missing(self, tmp_path: Path) -> None:
        """Test reading non-existent cache."""
        cache_path = tmp_path / "missing.md"
        assert read_cache(cache_path) is None

    def test_get_cache_path_creates_directory(self, tmp_path: Path) -> None:
        """Test that get_cache_path creates directory structure."""
        cache_dir = tmp_path / "cache"
        url = "https://example.com"
        provider = "api"

        cache_path = get_cache_path(cache_dir, url, provider)
        assert cache_dir.exists()
        assert cache_path.parent == cache_dir

    def test_cache_path_deterministic(self, tmp_path: Path) -> None:
        """Test that cache path is deterministic for same URL/provider."""
        cache_dir = tmp_path / "cache"
        url = "https://example.com"
        provider = "mcp"

        path1 = get_cache_path(cache_dir, url, provider)
        path2 = get_cache_path(cache_dir, url, provider)

        assert path1 == path2

    def test_cache_path_different_for_different_providers(self, tmp_path: Path) -> None:
        """Test that cache paths differ for different providers."""
        cache_dir = tmp_path / "cache"
        url = "https://example.com"

        path_mcp = get_cache_path(cache_dir, url, "mcp")
        path_api = get_cache_path(cache_dir, url, "api")

        assert path_mcp != path_api


class TestLoadURLsFromFile:
    """Tests for loading URLs from file."""

    def test_load_urls_from_file(self, tmp_path: Path) -> None:
        """Test loading URLs from file."""
        urls_file = tmp_path / "urls.txt"
        urls_file.write_text(
            "https://example.com/page1\n"
            "https://example.com/page2\n"
            "# Comment line\n"
            "https://example.com/page3\n"
        )

        urls = load_urls_from_file(urls_file)
        assert urls == [
            "https://example.com/page1",
            "https://example.com/page2",
            "https://example.com/page3",
        ]

    def test_load_urls_from_file_empty(self, tmp_path: Path) -> None:
        """Test loading from empty file."""
        urls_file = tmp_path / "empty.txt"
        urls_file.write_text("")

        urls = load_urls_from_file(urls_file)
        assert urls == []

    def test_load_urls_from_file_skips_comments(self, tmp_path: Path) -> None:
        """Test that comment lines are skipped."""
        urls_file = tmp_path / "urls.txt"
        urls_file.write_text(
            "# All comments\n"
            "# No URLs\n"
        )

        urls = load_urls_from_file(urls_file)
        assert urls == []

    def test_load_urls_from_file_skips_blank_lines(self, tmp_path: Path) -> None:
        """Test that blank lines are skipped."""
        urls_file = tmp_path / "urls.txt"
        urls_file.write_text(
            "https://example.com/page1\n"
            "\n"
            "https://example.com/page2\n"
        )

        urls = load_urls_from_file(urls_file)
        assert urls == [
            "https://example.com/page1",
            "https://example.com/page2",
        ]


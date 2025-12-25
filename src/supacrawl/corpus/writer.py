"""Snapshot writer utilities."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import aiofiles
import yaml

from supacrawl.corpus.layout import new_snapshot_id, snapshot_root
from supacrawl.corpus.state import CrawlState, load_state, save_state
from supacrawl.exceptions import generate_correlation_id
from supacrawl.models import OutputFormat, Page, SiteConfig

LOGGER = logging.getLogger(__name__)

# Schema version constant - single source of truth for manifest schema version
SCHEMA_VERSION = "1.0"


def _url_to_slug(url: str) -> str:
    """
    Convert a URL path to a filesystem-safe slug.

    Args:
        url: Full URL to convert.

    Returns:
        Filesystem-safe slug derived from URL path.
    """
    parsed = urlparse(url)
    path = parsed.path.strip("/")

    if not path:
        return "index"

    # Remove common file extensions
    path = re.sub(r"\.(html?|php|aspx?|jsp)$", "", path, flags=re.IGNORECASE)

    # Replace path separators and special chars with hyphens
    slug = re.sub(r"[/\\]+", "-", path)
    slug = re.sub(r"[^a-zA-Z0-9\-]", "-", slug)

    # Collapse multiple hyphens and strip
    slug = re.sub(r"-+", "-", slug).strip("-")

    # Truncate to reasonable length
    if len(slug) > 80:
        slug = slug[:80].rsplit("-", 1)[0]

    return slug.lower() or "page"


def _url_to_path_structure(url: str) -> tuple[Path, str]:
    """
    Convert a URL to a directory path structure preserving hierarchy.

    Args:
        url: Full URL to convert.

    Returns:
        Tuple of (directory_path, filename) where directory_path preserves URL hierarchy.
        For root URLs, returns (Path("."), "index").
    """
    parsed = urlparse(url)
    path = parsed.path.strip("/")

    if not path:
        return Path("."), "index"

    # Remove common file extensions from the last segment
    path_parts = path.split("/")
    if path_parts:
        last_part = path_parts[-1]
        last_part = re.sub(
            r"\.(html?|php|aspx?|jsp)$", "", last_part, flags=re.IGNORECASE
        )
        path_parts[-1] = last_part

    # Sanitise each path segment
    sanitised_parts: list[str] = []
    for part in path_parts:
        if not part:
            continue
        # Replace special chars with hyphens, keep alphanumeric and hyphens
        sanitised = re.sub(r"[^a-zA-Z0-9\-]", "-", part)
        sanitised = re.sub(r"-+", "-", sanitised).strip("-")
        # Truncate individual segments to reasonable length
        if len(sanitised) > 80:
            sanitised = sanitised[:80].rsplit("-", 1)[0]
        if sanitised:  # Only add non-empty parts
            sanitised_parts.append(sanitised.lower())

    if not sanitised_parts:
        return Path("."), "index"

    # Last part is the filename, rest is directory structure
    filename = sanitised_parts[-1] or "index"
    dir_parts = sanitised_parts[:-1] if len(sanitised_parts) > 1 else []

    dir_path = Path(*dir_parts) if dir_parts else Path(".")

    return dir_path, filename


def _safe_path_structure(
    page: Page, used_paths: dict[Path, set[str]] | None = None
) -> tuple[Path, str]:
    """
    Return a filesystem-safe path structure for a page based on URL.

    Args:
        page: Page object to generate path for.
        used_paths: Optional dict mapping directory paths to sets of used filenames.

    Returns:
        Tuple of (directory_path, filename) where directory_path preserves URL hierarchy.
        Filename may include collision suffix if needed.
    """
    dir_path, filename = _url_to_path_structure(page.url)

    # Handle collisions if tracking used paths
    if used_paths is not None:
        if dir_path not in used_paths:
            used_paths[dir_path] = set()
        used_filenames = used_paths[dir_path]

        base_filename = filename
        counter = 1
        while filename in used_filenames:
            filename = f"{base_filename}-{counter}"
            counter += 1
        used_filenames.add(filename)

    return dir_path, filename


def _page_manifest_entry(
    page: Page, files: dict[str, Path], snapshot_path: Path
) -> dict[str, Any]:
    """
    Return manifest metadata for a page.

    Args:
        page: Page object.
        files: Dictionary of format -> file path.
        snapshot_path: Root snapshot path for relative paths.

    Returns:
        Dictionary containing page metadata for the manifest.
    """
    entry: dict[str, Any] = {
        "url": page.url,
        "title": page.title,
        "content_hash": page.content_hash,
        "formats": {},
    }

    # Add file paths for each format
    for fmt, file_path in files.items():
        entry["formats"][fmt] = str(file_path.relative_to(snapshot_path))

    # Primary path (first format, usually markdown)
    if files:
        first_path = next(iter(files.values()))
        entry["path"] = str(first_path.relative_to(snapshot_path))

    if page.extra:
        status_code = page.extra.get("status_code")
        if status_code is not None:
            entry["status_code"] = status_code
        language = page.extra.get("language")
        if language:
            entry["language"] = language
        fetch_stats = page.extra.get("fetch_stats")
        if fetch_stats:
            entry["fetch_stats"] = fetch_stats
    return entry


async def _write_page(page: Page, file_path: Path, snapshot_id: str = "") -> None:
    """
    Write a single page to disk (markdown format with frontmatter).

    Args:
        page: Page object to write.
        file_path: Path where the page should be written.
        snapshot_id: ID of the snapshot (used for frontmatter).
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = _build_frontmatter_from_page(page, snapshot_id)
    content = f"{frontmatter}\n\n{page.content_markdown}"
    async with aiofiles.open(file_path, "w", encoding="utf-8") as handle:
        await handle.write(content)


def _build_frontmatter_from_page(page: Page, snapshot_id: str) -> str:
    """
    Build YAML frontmatter for a markdown file using unified ScrapeMetadata.

    Args:
        page: Page object with metadata.
        snapshot_id: ID of the snapshot this page belongs to.

    Returns:
        YAML frontmatter string including opening and closing delimiters.
    """
    from supacrawl.models import ScrapeMetadata

    # Build ScrapeMetadata from Page fields
    metadata = ScrapeMetadata(
        title=page.title,
        source_url=page.url,
        language=page.extra.get("language") if page.extra else None,
        status_code=page.extra.get("status_code") if page.extra else None,
    )

    # Use unified frontmatter generation with corpus fields
    return metadata.to_frontmatter(
        url=page.url,
        site_id=page.site_id,
        snapshot_id=snapshot_id,
        content_hash=page.content_hash,
        provider=page.provider,
        scraped_at=page.scraped_at,
    )


async def _write_page_format(
    page: Page,
    snapshot_path: Path,
    dir_path: Path,
    filename: str,
    fmt: OutputFormat,
    snapshot_id: str = "",
) -> Path:
    """
    Write a page in the specified format using format-based directory structure.

    Args:
        page: Page object to write.
        snapshot_path: Root snapshot directory.
        dir_path: Directory path relative to format directory (preserves URL hierarchy).
        filename: Base filename (without extension).
        fmt: Output format.
        snapshot_id: ID of the snapshot (used for frontmatter).

    Returns:
        Path to the written file.
    """
    # Format-based directory: {format}/{url_hierarchy}/
    format_dir = snapshot_path / fmt.value
    file_path = format_dir / dir_path / f"{filename}{fmt.extension}"
    file_path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == OutputFormat.MARKDOWN:
        frontmatter = _build_frontmatter_from_page(page, snapshot_id)
        content = f"{frontmatter}\n\n{page.content_markdown}"
    elif fmt == OutputFormat.HTML:
        # Use stored HTML or wrap markdown in basic HTML
        if page.content_html:
            content = _wrap_html(page.title, page.url, page.content_html)
        else:
            # Convert markdown to basic HTML structure
            content = _markdown_to_html(page.title, page.url, page.content_markdown)
    elif fmt == OutputFormat.TEXT:
        # Plain text with header
        text_content = page.get_text_content()
        content = f"{page.title}\n\nSource: {page.url}\n\n{text_content}"
    elif fmt == OutputFormat.JSON:
        # Structured JSON
        json_data: dict[str, Any] = {
            "url": page.url,
            "title": page.title,
            "path": page.path,
            "content": page.content_markdown,
            "content_hash": page.content_hash,
            "scraped_at": page.scraped_at.isoformat(),
            "provider": page.provider,
            "site_id": page.site_id,
        }
        if page.extra:
            json_data["extra"] = page.extra
        content = json.dumps(json_data, indent=2, ensure_ascii=False)
    else:
        # Fallback to markdown
        content = f"# {page.title}\n\nSource: {page.url}\n\n{page.content_markdown}"

    async with aiofiles.open(file_path, "w", encoding="utf-8") as handle:
        await handle.write(content)

    return file_path


def _wrap_html(title: str, url: str, html_content: str) -> str:
    """Wrap HTML content in a complete document."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="source-url" content="{url}">
    <title>{title}</title>
</head>
<body>
{html_content}
</body>
</html>"""


def _markdown_to_html(title: str, url: str, markdown: str) -> str:
    """Convert markdown to basic HTML structure."""
    import re

    html_lines: list[str] = []

    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            html_lines.append("")
            continue

        # Headers
        if stripped.startswith("# "):
            html_lines.append(f"<h1>{_escape_html(stripped[2:])}</h1>")
        elif stripped.startswith("## "):
            html_lines.append(f"<h2>{_escape_html(stripped[3:])}</h2>")
        elif stripped.startswith("### "):
            html_lines.append(f"<h3>{_escape_html(stripped[4:])}</h3>")
        # Lists
        elif stripped.startswith("- ") or stripped.startswith("* "):
            html_lines.append(f"<li>{_escape_html(stripped[2:])}</li>")
        # Code blocks (simplified)
        elif stripped.startswith("```"):
            pass  # Skip code fences
        # Regular paragraphs
        else:
            # Convert links
            text = re.sub(
                r"\[([^\]]+)\]\(([^)]+)\)",
                r'<a href="\2">\1</a>',
                stripped,
            )
            # Convert bold
            text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
            # Convert italic
            text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
            html_lines.append(f"<p>{text}</p>")

    body = "\n".join(html_lines)
    return _wrap_html(title, url, body)


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _get_git_commit() -> str | None:
    """
    Get the current git commit hash.

    Returns:
        Git commit hash (short, 7 characters) or None if unavailable.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return result.stdout.strip() or None
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return None


def _get_scraper_version() -> str | None:
    """
    Get scraper version if available.

    Returns:
        Version string or None if unavailable.
    """
    # Returns playwright version from the installed package
    try:
        import playwright

        if hasattr(playwright, "__version__"):
            return str(playwright.__version__)
    except (ImportError, AttributeError):
        pass
    return None


def _hash_site_config(config: SiteConfig, config_path: Path | None = None) -> str:
    """
    Generate a deterministic SHA-256 hash of the site configuration.

    If config_path is provided, hashes the raw file content.
    Otherwise, serializes the SiteConfig to YAML and hashes that.

    Args:
        config: Site configuration.
        config_path: Optional path to the original config file.

    Returns:
        SHA-256 hash as hexadecimal string.
    """
    if config_path and config_path.exists():
        # Hash raw file content for exact match
        content = config_path.read_bytes()
    else:
        # Fallback: serialize config to YAML and hash
        # Convert to dict, then to YAML
        config_dict = config.model_dump(mode="json", exclude_none=False)
        content = yaml.dump(
            config_dict, default_flow_style=False, sort_keys=True
        ).encode("utf-8")

    return hashlib.sha256(content).hexdigest()


def _build_metadata(
    snapshot_id: str,
    site: SiteConfig,
    config_path: Path | None = None,
) -> dict[str, Any]:
    """
    Build metadata object for manifest.

    Args:
        snapshot_id: Snapshot identifier.
        site: Site configuration.
        config_path: Optional path to the original config file.

    Returns:
        Metadata dictionary.
    """
    return {
        "snapshot_id": snapshot_id,
        "site_id": site.id,
        "created_at": datetime.now(UTC).isoformat(),
        "git_commit": _get_git_commit(),
        "site_config_hash": _hash_site_config(site, config_path),
        "crawl_engine": "playwright",
        "crawl_engine_version": _get_scraper_version(),
        "schema_version": SCHEMA_VERSION,
    }


async def write_snapshot(
    site: SiteConfig,
    pages: list[Page],
    corpora_root: Path,
    config_path: Path | None = None,
) -> Path:
    """
    Create a snapshot for the given site and pages.

    Args:
        site: Site configuration.
        pages: List of scraped pages to include in the snapshot.
        corpora_root: Root directory for all corpora.
        config_path: Optional path to the original site config file (for hashing).

    Returns:
        Path to the created snapshot directory.
    """
    correlation_id = generate_correlation_id()
    snapshot_id = new_snapshot_id()
    assert site.id is not None, "site.id must be set after validation"
    snapshot_path = snapshot_root(site.id, corpora_root, snapshot_id)
    snapshot_path.mkdir(parents=True, exist_ok=True)

    # Parse formats from config
    formats = [OutputFormat.from_string(f) for f in site.formats]
    if not formats:
        formats = [OutputFormat.MARKDOWN]

    # Track used paths to avoid collisions (format -> dir_path -> set of filenames)
    used_paths: dict[Path, set[str]] = {}

    manifest_pages = []
    for page in pages:
        dir_path, filename = _safe_path_structure(page, used_paths)
        files: dict[str, Path] = {}

        for fmt in formats:
            file_path = await _write_page_format(
                page, snapshot_path, dir_path, filename, fmt, snapshot_id
            )
            files[fmt.value] = file_path

        manifest_pages.append(_page_manifest_entry(page, files, snapshot_path))

    manifest = {
        "site_id": site.id,
        "site_name": site.name,
        "snapshot_id": snapshot_id,
        "created_at": datetime.now(ZoneInfo("Australia/Brisbane")).isoformat(),
        "provider": "playwright",
        "entrypoints": site.entrypoints,
        "total_pages": len(pages),
        "formats": site.formats,
        "pages": manifest_pages,
        "correlation_id": correlation_id,
        "metadata": _build_metadata(snapshot_id, site, config_path),
    }

    manifest_path = snapshot_path / "manifest.json"
    async with aiofiles.open(manifest_path, "w", encoding="utf-8") as handle:
        await handle.write(json.dumps(manifest, indent=2))

    return snapshot_path


class IncrementalSnapshotWriter:
    """
    Incremental snapshot writer that saves pages as they arrive and keeps manifest in sync.

    This enables partial progress to be persisted even if a crawl is interrupted.
    """

    def __init__(
        self,
        site: SiteConfig,
        corpora_root: Path,
        snapshot_id: str | None = None,
        resume_snapshot: Path | None = None,
        config_path: Path | None = None,
    ) -> None:
        self.site = site
        self.corpora_root = corpora_root
        self.config_path = config_path

        # Handle resumption
        if resume_snapshot and resume_snapshot.exists():
            self.snapshot_id = resume_snapshot.name
            self.snapshot_path = resume_snapshot
            self._state = load_state(resume_snapshot) or CrawlState()
        else:
            self.snapshot_id = snapshot_id or new_snapshot_id()
            assert site.id is not None, "site.id must be set after validation"
            self.snapshot_path = snapshot_root(site.id, corpora_root, self.snapshot_id)
            self._state = CrawlState()

        self.manifest_path = self.snapshot_path / "manifest.json"
        self.manifest_pages: list[dict[str, Any]] = []
        self.pages: list[Page] = []  # Track pages for return value
        self.started = False
        self.correlation_id = generate_correlation_id()
        self.crawl_settings: dict[str, Any] = {}
        self.used_paths: dict[Path, set[str]] = (
            {}
        )  # Track used paths for collision detection

        # Parse formats from config
        self.formats = [OutputFormat.from_string(f) for f in site.formats]
        if not self.formats:
            self.formats = [OutputFormat.MARKDOWN]

    async def start(self) -> None:
        """Initialise snapshot directories and write an in-progress manifest."""
        self.snapshot_path.mkdir(parents=True, exist_ok=True)
        (self.snapshot_path / ".meta").mkdir(exist_ok=True)  # Create .meta/ directory
        await self._write_manifest(status="in_progress")
        self.started = True

    async def add_pages(self, pages: list[Page]) -> None:
        """
        Write pages and update manifest incrementally.

        Detects duplicate content by comparing content_hash values across all pages
        (both previously written and newly added). Logs warnings when different URLs
        have identical content, which may indicate:
        - Pages with naturally identical content (expected)
        - JavaScript rendering issues (pages not fully loaded)
        - Error pages or redirects being cached

        Args:
            pages: List of pages to write to the snapshot.
        """
        if not self.started:
            await self.start()

        # Track content_hash to URL mapping for duplicate detection
        # Check both new pages and existing pages in manifest
        hash_to_url: dict[str, str] = {}

        # First, load existing hashes from manifest
        for existing_page in self.manifest_pages:
            existing_hash = existing_page.get("content_hash", "")
            existing_url = existing_page.get("url", "")
            if existing_hash:
                hash_to_url[existing_hash] = existing_url

        # Now check new pages for duplicates
        duplicate_count = 0
        for page in pages:
            if page.content_hash in hash_to_url:
                first_url = hash_to_url[page.content_hash]
                if first_url != page.url:  # Don't warn about same URL
                    LOGGER.warning(
                        "Duplicate content detected: '%s' has identical content to '%s' "
                        "(content_hash: %s...)",
                        page.url,
                        first_url,
                        page.content_hash[:16],  # Show first 16 chars of hash
                    )
                    duplicate_count += 1
            else:
                hash_to_url[page.content_hash] = page.url

        if duplicate_count > 0:
            LOGGER.warning(
                "Found %d page(s) with duplicate content. This may indicate: "
                "(1) Pages with identical content (expected), "
                "(2) JavaScript rendering issues (pages not fully loaded), "
                "(3) Error pages or redirects being cached.",
                duplicate_count,
            )

        for page in pages:
            dir_path, filename = _safe_path_structure(page, self.used_paths)
            files: dict[str, Path] = {}

            # Write all requested formats
            for fmt in self.formats:
                file_path = await _write_page_format(
                    page, self.snapshot_path, dir_path, filename, fmt, self.snapshot_id
                )
                files[fmt.value] = file_path

            self.manifest_pages.append(
                _page_manifest_entry(page, files, self.snapshot_path)
            )
            self.pages.append(page)  # Track for return

            # Update crawl state
            self._state.mark_completed(page.url)

        save_state(self._state, self.snapshot_path)
        await self._write_manifest(status="in_progress")

    async def complete(self) -> None:
        """Mark manifest as completed and update latest symlink."""
        await self._write_manifest(status="completed")
        self._state.finish("completed")
        save_state(self._state, self.snapshot_path)

        # Update latest symlink to point to this snapshot
        from supacrawl.corpus.symlink import update_latest_symlink

        site_dir = self.snapshot_path.parent
        update_latest_symlink(site_dir, self.snapshot_id)

    async def abort(self, error: str | None = None) -> None:
        """Mark manifest as aborted."""
        await self._write_manifest(status="aborted", error=error)
        self._state.finish("aborted")
        save_state(self._state, self.snapshot_path)

    @property
    def state(self) -> CrawlState:
        """Return current crawl state."""
        return self._state

    def is_url_completed(self, url: str) -> bool:
        """Check if URL was already completed."""
        return self._state.is_completed(url)

    def _compute_stats(self) -> dict[str, Any]:
        """Compute aggregate statistics including duplicate detection."""
        # Note: We no longer have Page objects stored, so stats are limited
        # to what we can extract from manifest entries
        total_pages = len(self.manifest_pages)
        languages: dict[str, int] = {}
        status_codes: dict[str, int] = {}

        for page_entry in self.manifest_pages:
            # Extract language and status_code from manifest if available
            if "language" in page_entry:
                lang = page_entry["language"]
                languages[lang] = languages.get(lang, 0) + 1
            if "status_code" in page_entry:
                code = str(page_entry["status_code"])
                status_codes[code] = status_codes.get(code, 0) + 1

        # Detect content duplicates across all pages
        hash_to_urls: dict[str, list[str]] = {}
        for page_entry in self.manifest_pages:
            content_hash = page_entry.get("content_hash", "")
            url = page_entry.get("url", "")
            if content_hash:
                if content_hash not in hash_to_urls:
                    hash_to_urls[content_hash] = []
                hash_to_urls[content_hash].append(url)

        # Count duplicate groups (groups with 2+ URLs)
        duplicate_groups = {
            h: urls for h, urls in hash_to_urls.items() if len(urls) > 1
        }
        total_duplicates = sum(len(urls) - 1 for urls in duplicate_groups.values())

        # Build stats dictionary
        stats: dict[str, Any] = {
            "total_pages": total_pages,
            "languages": languages,
            "status_codes": status_codes,
        }

        # Add duplicate stats if any found
        if duplicate_groups:
            stats["duplicate_content"] = {
                "duplicate_groups": len(duplicate_groups),
                "total_duplicated_pages": total_duplicates,
            }

        return stats

    async def _write_manifest(self, status: str, error: str | None = None) -> None:
        """Write manifest to disk with current state."""
        self.snapshot_path.mkdir(parents=True, exist_ok=True)

        # Compute stats
        stats = self._compute_stats() if self.manifest_pages else {}

        manifest = {
            "site_id": self.site.id,
            "site_name": self.site.name,
            "snapshot_id": self.snapshot_id,
            "created_at": datetime.now(ZoneInfo("Australia/Brisbane")).isoformat(),
            "provider": "playwright",
            "entrypoints": self.site.entrypoints,
            "total_pages": len(self.manifest_pages),
            "formats": self.site.formats,
            "pages": self.manifest_pages,
            "correlation_id": self.correlation_id,
            "status": status,
            "crawl_settings": self.crawl_settings,
            "stats": stats,
            "metadata": _build_metadata(self.snapshot_id, self.site, self.config_path),
        }
        if error:
            manifest["error"] = error
        async with aiofiles.open(self.manifest_path, "w", encoding="utf-8") as handle:
            await handle.write(json.dumps(manifest, indent=2))

    def snapshot_root(self) -> Path:
        """Return snapshot root path."""
        return self.snapshot_path

    def get_pages(self) -> list[Page]:
        """Return all pages written to this snapshot."""
        return self.pages

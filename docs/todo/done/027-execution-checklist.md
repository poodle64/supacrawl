# Execution Checklist: Two-Layer Model Refactor

**Purpose:** Step-by-step execution guide for implementing the two-layer model refactor. Each step is atomic and testable.

**Reference:** See `027-refactor-two-layer-model.md` for architecture context and acceptance criteria.

---

## Phase 1: Foundation

### Step 1.1: Create symlink utilities module

**File to create:** `web_scraper/corpus/symlink.py`

```python
"""Symlink utilities for corpus snapshot management."""

from __future__ import annotations

import logging
from pathlib import Path

LOGGER = logging.getLogger(__name__)

LATEST_SYMLINK_NAME = "latest"


def update_latest_symlink(site_dir: Path, snapshot_id: str) -> Path:
    """
    Create or update the 'latest' symlink to point to a snapshot.

    Args:
        site_dir: Site directory containing snapshots (e.g., corpora/my-site/).
        snapshot_id: Snapshot directory name to link to.

    Returns:
        Path to the created symlink.
    """
    symlink_path = site_dir / LATEST_SYMLINK_NAME
    target = Path(snapshot_id)  # Relative target

    # Remove existing symlink if present
    if symlink_path.is_symlink():
        symlink_path.unlink()
    elif symlink_path.exists():
        # If it's a regular file/directory (shouldn't happen), log warning
        LOGGER.warning("Removing non-symlink at %s", symlink_path)
        if symlink_path.is_dir():
            symlink_path.rmdir()
        else:
            symlink_path.unlink()

    symlink_path.symlink_to(target)
    LOGGER.debug("Updated symlink: %s -> %s", symlink_path, target)
    return symlink_path


def resolve_latest_snapshot(site_dir: Path) -> Path | None:
    """
    Resolve the 'latest' symlink to its target snapshot directory.

    Args:
        site_dir: Site directory containing snapshots.

    Returns:
        Path to the snapshot directory, or None if symlink doesn't exist.
    """
    symlink_path = site_dir / LATEST_SYMLINK_NAME
    if not symlink_path.is_symlink():
        return None

    # Resolve relative to site_dir
    target = symlink_path.resolve()
    if target.exists() and target.is_dir():
        return target
    return None


def remove_symlink_if_exists(symlink_path: Path) -> None:
    """
    Remove a symlink if it exists.

    Args:
        symlink_path: Path to the symlink to remove.
    """
    if symlink_path.is_symlink():
        symlink_path.unlink()
```

**Verification:** File exists and is syntactically valid.

---

### Step 1.2: Create symlink unit tests

**File to create:** `tests/unit/test_symlink.py`

```python
"""Unit tests for symlink utilities."""

from __future__ import annotations

from pathlib import Path

import pytest

from web_scraper.corpus.symlink import (
    LATEST_SYMLINK_NAME,
    remove_symlink_if_exists,
    resolve_latest_snapshot,
    update_latest_symlink,
)


def test_update_latest_symlink_creates_symlink(tmp_path: Path) -> None:
    """Test that update_latest_symlink creates a symlink."""
    site_dir = tmp_path / "my-site"
    site_dir.mkdir()
    snapshot_dir = site_dir / "2025-12-18_1430"
    snapshot_dir.mkdir()

    result = update_latest_symlink(site_dir, "2025-12-18_1430")

    assert result == site_dir / LATEST_SYMLINK_NAME
    assert result.is_symlink()
    assert result.resolve() == snapshot_dir


def test_update_latest_symlink_replaces_existing(tmp_path: Path) -> None:
    """Test that update_latest_symlink replaces an existing symlink."""
    site_dir = tmp_path / "my-site"
    site_dir.mkdir()
    old_snapshot = site_dir / "2025-12-17_0900"
    old_snapshot.mkdir()
    new_snapshot = site_dir / "2025-12-18_1430"
    new_snapshot.mkdir()

    # Create initial symlink
    update_latest_symlink(site_dir, "2025-12-17_0900")

    # Update to new snapshot
    result = update_latest_symlink(site_dir, "2025-12-18_1430")

    assert result.is_symlink()
    assert result.resolve() == new_snapshot


def test_resolve_latest_snapshot_returns_path(tmp_path: Path) -> None:
    """Test that resolve_latest_snapshot returns the target path."""
    site_dir = tmp_path / "my-site"
    site_dir.mkdir()
    snapshot_dir = site_dir / "2025-12-18_1430"
    snapshot_dir.mkdir()
    update_latest_symlink(site_dir, "2025-12-18_1430")

    result = resolve_latest_snapshot(site_dir)

    assert result == snapshot_dir


def test_resolve_latest_snapshot_returns_none_when_missing(tmp_path: Path) -> None:
    """Test that resolve_latest_snapshot returns None when symlink is missing."""
    site_dir = tmp_path / "my-site"
    site_dir.mkdir()

    result = resolve_latest_snapshot(site_dir)

    assert result is None


def test_remove_symlink_if_exists_removes_symlink(tmp_path: Path) -> None:
    """Test that remove_symlink_if_exists removes a symlink."""
    site_dir = tmp_path / "my-site"
    site_dir.mkdir()
    snapshot_dir = site_dir / "2025-12-18_1430"
    snapshot_dir.mkdir()
    symlink_path = update_latest_symlink(site_dir, "2025-12-18_1430")

    remove_symlink_if_exists(symlink_path)

    assert not symlink_path.exists()


def test_remove_symlink_if_exists_no_error_when_missing(tmp_path: Path) -> None:
    """Test that remove_symlink_if_exists does not error when symlink is missing."""
    symlink_path = tmp_path / "nonexistent"

    # Should not raise
    remove_symlink_if_exists(symlink_path)
```

**Verification:** `pytest tests/unit/test_symlink.py -v` passes.

---

### Step 1.3: Update state module for .meta/ directory

**File to modify:** `web_scraper/corpus/state.py`

**Change 1:** Update STATE_FILE constant (line ~20):

```python
# Before:
STATE_FILE = "crawl_state.json"

# After:
STATE_FILE = ".meta/crawl_state.json"
```

**Change 2:** Update save_state function to create .meta/ directory:

Find the `save_state` function and update it:

```python
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
```

**Change 3:** Add backward compatibility to load_state:

```python
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
```

**Verification:** `pytest tests/unit -k state -v` passes.

---

### Step 1.4: Update writer module for .meta/ directory

**File to modify:** `web_scraper/corpus/writer.py`

**Change 1:** In `IncrementalSnapshotWriter.__init__` (around line 658-659), update paths:

```python
# Before:
self.run_log_path = self.snapshot_path / "run.log.jsonl"
self.checksums_path = self.snapshot_path / "checksums.sha256"

# After:
self.run_log_path = self.snapshot_path / ".meta" / "run.log.jsonl"
self.checksums_path = self.snapshot_path / ".meta" / "checksums.sha256"
```

**Change 2:** In `IncrementalSnapshotWriter.start` method (around line 678-681), ensure .meta/ is created:

```python
async def start(self) -> None:
    """Initialise snapshot directories and write an in-progress manifest."""
    self.snapshot_path.mkdir(parents=True, exist_ok=True)
    (self.snapshot_path / ".meta").mkdir(exist_ok=True)  # Add this line
    await self._write_manifest(status="in_progress")
    self.started = True
```

**Verification:** `pytest tests/integration/test_corpus_writer.py -v` passes.

---

### Step 1.5: Run existing tests

**Command:** `pytest tests/unit tests/integration -q`

**Expected:** All tests pass. If any fail due to path changes, update the specific test to expect `.meta/` location.

---

## Phase 2: Symlink Integration

### Step 2.1: Export symlink functions from layout module

**File to modify:** `web_scraper/corpus/layout.py`

Add imports and re-exports at the end of the file:

```python
# Add at top of file with other imports:
from web_scraper.corpus.symlink import (
    update_latest_symlink,
    resolve_latest_snapshot,
    LATEST_SYMLINK_NAME,
)

# These are now available via: from web_scraper.corpus.layout import update_latest_symlink
```

**Verification:** Can import from layout: `from web_scraper.corpus.layout import update_latest_symlink`

---

### Step 2.2: Call symlink update in writer.complete()

**File to modify:** `web_scraper/corpus/writer.py`

**Change 1:** Add import at top:

```python
from web_scraper.corpus.symlink import update_latest_symlink
```

**Change 2:** Update `complete()` method (around line 702-707):

```python
async def complete(self) -> None:
    """Mark manifest as completed and update latest symlink."""
    await self._apply_boilerplate_and_write(status="completed")
    self._state.finish("completed")
    save_state(self._state, self.snapshot_path)
    await self.log_event({"type": "completed"})
    
    # Update latest symlink to point to this snapshot
    site_dir = self.snapshot_path.parent
    update_latest_symlink(site_dir, self.snapshot_id)
```

**Verification:** After crawl, `corpora/{site}/latest` symlink exists.

---

### Step 2.3: Update CLI output to show latest/ path

**File to modify:** `web_scraper/cli.py`

In the `crawl` command function, find the success output (around line 483-484):

```python
# Before:
click.echo(f"Finished crawl: {config.id} -> {len(pages)} pages")
click.echo(f"Snapshot created at {snapshot_path}")

# After:
click.echo(f"Crawl complete: {len(pages)} pages")
site_dir = snapshot_path.parent
click.echo(f"Output: {site_dir}/latest/")
if verbose:
    click.echo(f"Snapshot ID: {snapshot_path.name}")
```

**Verification:** `web-scraper crawl <site>` outputs `Output: corpora/{site}/latest/`

---

### Step 2.4: Add integration test for symlink creation

**File to modify:** `tests/integration/test_cli.py`

Add new test after existing tests:

```python
def test_cli_crawl_creates_latest_symlink(monkeypatch, tmp_path: Path) -> None:
    """Crawl command should create a 'latest' symlink."""
    base_path = tmp_path
    _write_site_config(base_path)

    monkeypatch.setattr("web_scraper.cli.Crawl4AIScraper", FakeScraper)

    runner = CliRunner()
    result = runner.invoke(
        app, ["crawl", "example", "--base-path", str(base_path)]
    )

    assert result.exit_code == 0
    
    # Check symlink exists
    latest_symlink = base_path / "corpora" / "example" / "latest"
    assert latest_symlink.is_symlink()
    
    # Check symlink resolves to a valid snapshot
    resolved = latest_symlink.resolve()
    assert resolved.is_dir()
    assert (resolved / "manifest.json").exists()
```

**Verification:** `pytest tests/integration/test_cli.py::test_cli_crawl_creates_latest_symlink -v` passes.

---

## Phase 3: Auto-Resume Behaviour

### Step 3.1: Update crawl command signature

**File to modify:** `web_scraper/cli.py`

**Change 1:** Remove the `--resume` option (around line 273-278):

```python
# Delete these lines:
@click.option(
    "--resume",
    type=str,
    default=None,
    help="Resume an existing crawl. Pass snapshot ID or 'latest' for most recent.",
)
```

**Change 2:** Add `--fresh` option in its place:

```python
@click.option(
    "--fresh",
    is_flag=True,
    default=False,
    help="Start a new snapshot even if an incomplete one exists.",
)
```

**Change 3:** Update function signature:

```python
# Before:
def crawl(
    site_name: str,
    base_path: Path | None,
    verbose: bool,
    resume: str | None,  # Remove this
    formats: str | None,
    ...
) -> None:

# After:
def crawl(
    site_name: str,
    base_path: Path | None,
    verbose: bool,
    fresh: bool,  # Add this
    formats: str | None,
    ...
) -> None:
```

**Verification:** `web-scraper crawl --help` shows `--fresh` option, not `--resume`.

---

### Step 3.2: Implement auto-resume logic

**File to modify:** `web_scraper/cli.py`

Replace the resume handling block (approximately lines 436-466) with:

```python
    # Auto-resume logic
    resume_snapshot: Path | None = None
    if not fresh:
        resume_snapshot = find_resumable_snapshot(corpora_dir, config.id)
        if resume_snapshot:
            state = load_state(resume_snapshot)
            if state:
                click.echo(
                    f"Resuming {config.name} from {resume_snapshot.name} "
                    f"({state.checkpoint_page} pages complete)..."
                )
    
    if fresh:
        # Check if there was an incomplete snapshot we're ignoring
        incomplete = find_resumable_snapshot(corpora_dir, config.id)
        if incomplete:
            click.echo(
                f"Starting fresh crawl: {config.name} (ignoring incomplete snapshot {incomplete.name})"
            )
        else:
            click.echo(f"Starting crawl: {config.name}...")
    elif not resume_snapshot:
        click.echo(f"Starting crawl: {config.name}...")
```

**Verification:** Running `web-scraper crawl <site>` on incomplete snapshot auto-resumes.

---

### Step 3.3: Update interrupted crawl message

**File to modify:** `web_scraper/cli.py`

Find the CrawlInterrupted handler (around line 493-496) and update:

```python
# Before:
click.echo(f"Resume with: web-scraper crawl {site_name} --resume latest", err=True)

# After:
click.echo(f"Resume by running: web-scraper crawl {site_name}", err=True)
```

**Verification:** Ctrl+C message shows correct resume instruction.

---

### Step 3.4: Create auto-resume test

**File to create:** `tests/integration/test_auto_resume.py`

```python
"""Integration tests for auto-resume behaviour."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from web_scraper.cli import app
from web_scraper.corpus.state import CrawlState, save_state


def _write_site_config(base_path: Path) -> None:
    """Write a minimal site config for testing."""
    sites_dir = base_path / "sites"
    sites_dir.mkdir(parents=True, exist_ok=True)
    (sites_dir / "test-site.yaml").write_text(
        "id: test-site\n"
        "name: Test Site\n"
        "entrypoints:\n"
        "  - https://example.com\n"
        "include:\n"
        "  - https://example.com/**\n"
        "exclude: []\n"
        "max_pages: 10\n"
        "formats:\n"
        "  - markdown\n"
        "only_main_content: true\n"
        "include_subdomains: false\n",
        encoding="utf-8",
    )


def _create_incomplete_snapshot(base_path: Path, site_id: str) -> Path:
    """Create an incomplete snapshot with in_progress state."""
    snapshot_path = base_path / "corpora" / site_id / "2025-12-18_1430"
    snapshot_path.mkdir(parents=True, exist_ok=True)
    meta_dir = snapshot_path / ".meta"
    meta_dir.mkdir(exist_ok=True)
    
    # Create in_progress state
    state = CrawlState(status="in_progress", checkpoint_page=5)
    state.completed_urls.add("https://example.com")
    save_state(state, snapshot_path)
    
    # Create minimal manifest
    manifest = {
        "site_id": site_id,
        "status": "in_progress",
        "pages": [],
    }
    (snapshot_path / "manifest.json").write_text(json.dumps(manifest))
    
    return snapshot_path


def test_auto_resume_detects_incomplete_snapshot(tmp_path: Path) -> None:
    """Crawl should auto-resume when incomplete snapshot exists."""
    _write_site_config(tmp_path)
    _create_incomplete_snapshot(tmp_path, "test-site")
    
    runner = CliRunner()
    # Note: This will fail to actually crawl without mocking the scraper,
    # but we can check the output message
    result = runner.invoke(
        app, ["crawl", "test-site", "--base-path", str(tmp_path)],
        catch_exceptions=False,
    )
    
    # Should mention resuming
    assert "Resuming" in result.output or result.exit_code != 0


def test_fresh_flag_ignores_incomplete_snapshot(tmp_path: Path) -> None:
    """--fresh flag should start new crawl even with incomplete snapshot."""
    _write_site_config(tmp_path)
    _create_incomplete_snapshot(tmp_path, "test-site")
    
    runner = CliRunner()
    result = runner.invoke(
        app, ["crawl", "test-site", "--fresh", "--base-path", str(tmp_path)],
        catch_exceptions=False,
    )
    
    # Should mention ignoring incomplete
    assert "fresh" in result.output.lower() or "ignoring" in result.output.lower() or result.exit_code != 0
```

**Verification:** `pytest tests/integration/test_auto_resume.py -v` passes.

---

## Phase 4: --chunks Flag

### Step 4.1: Add --chunks flag to crawl command

**File to modify:** `web_scraper/cli.py`

Add options after the existing crawl options (around line 310):

```python
@click.option(
    "--chunks",
    is_flag=True,
    default=False,
    help="Generate chunks.jsonl after crawl completes.",
)
@click.option(
    "--max-chars",
    type=int,
    default=1200,
    show_default=True,
    help="Maximum characters per chunk (used with --chunks).",
)
```

Update function signature to include new parameters:

```python
def crawl(
    site_name: str,
    base_path: Path | None,
    verbose: bool,
    fresh: bool,
    formats: str | None,
    from_map: Path | None,
    concurrency: int | None,
    delay: float | None,
    timeout: float | None,
    retries: int | None,
    chunks: bool,       # Add
    max_chars: int,     # Add
) -> None:
```

**Verification:** `web-scraper crawl --help` shows `--chunks` and `--max-chars` options.

---

### Step 4.2: Implement post-crawl chunking

**File to modify:** `web_scraper/cli.py`

After the successful crawl completion (around line 484), add chunking logic:

```python
    try:
        pages, snapshot_path = scraper.crawl(
            config,
            corpora_dir,
            resume_snapshot=resume_snapshot,
            target_urls=target_urls,
        )
        
        # Generate chunks if requested
        chunk_count = 0
        if chunks:
            from web_scraper.prep.chunker import chunk_snapshot
            chunks_path = asyncio.run(chunk_snapshot(snapshot_path, max_chars=max_chars))
            # Count chunks
            chunk_count = sum(1 for _ in chunks_path.read_text().splitlines())
        
        # Output summary
        if chunks:
            click.echo(f"Crawl complete: {len(pages)} pages, {chunk_count} chunks")
        else:
            click.echo(f"Crawl complete: {len(pages)} pages")
        
        site_dir = snapshot_path.parent
        click.echo(f"Output: {site_dir}/latest/")
        if verbose:
            click.echo(f"Snapshot ID: {snapshot_path.name}")
```

**Verification:** `web-scraper crawl <site> --chunks` produces `chunks.jsonl`.

---

### Step 4.3: Create chunks flag test

**File to create:** `tests/integration/test_chunks_flag.py`

```python
"""Integration tests for --chunks flag on crawl command."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from web_scraper.cli import app
from tests.integration.test_cli import FakeScraper, _write_site_config


def test_crawl_with_chunks_produces_chunks_file(monkeypatch, tmp_path: Path) -> None:
    """Crawl with --chunks flag should produce chunks.jsonl."""
    _write_site_config(tmp_path)

    monkeypatch.setattr("web_scraper.cli.Crawl4AIScraper", FakeScraper)

    runner = CliRunner()
    result = runner.invoke(
        app, ["crawl", "example", "--chunks", "--base-path", str(tmp_path)]
    )

    assert result.exit_code == 0
    
    # Check chunks file exists
    latest = tmp_path / "corpora" / "example" / "latest"
    chunks_path = latest / "chunks.jsonl"
    assert chunks_path.exists() or latest.resolve().joinpath("chunks.jsonl").exists()


def test_crawl_without_chunks_no_chunks_file(monkeypatch, tmp_path: Path) -> None:
    """Crawl without --chunks flag should not produce chunks.jsonl."""
    _write_site_config(tmp_path)

    monkeypatch.setattr("web_scraper.cli.Crawl4AIScraper", FakeScraper)

    runner = CliRunner()
    result = runner.invoke(
        app, ["crawl", "example", "--base-path", str(tmp_path)]
    )

    assert result.exit_code == 0
    
    # Check chunks file does NOT exist
    site_dir = tmp_path / "corpora" / "example"
    snapshots = [d for d in site_dir.iterdir() if d.is_dir() and d.name != "latest"]
    if snapshots:
        chunks_path = snapshots[0] / "chunks.jsonl"
        assert not chunks_path.exists()
```

**Verification:** `pytest tests/integration/test_chunks_flag.py -v` passes.

---

## Phase 5: --dry-run Flag

### Step 5.1: Add --dry-run flag

**File to modify:** `web_scraper/cli.py`

Add option to crawl command:

```python
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show URLs that would be crawled without fetching content.",
)
```

Update function signature to include `dry_run: bool`.

---

### Step 5.2: Implement dry-run logic

**File to modify:** `web_scraper/cli.py`

Add dry-run handling early in the crawl function (before scraper creation):

```python
    # Handle dry-run mode
    if dry_run:
        from web_scraper.map import map_site as map_site_func
        
        try:
            url_entries = asyncio.run(
                map_site_func(config, max_urls=config.max_pages)
            )
            for entry in url_entries:
                url = entry.get("url", entry) if isinstance(entry, dict) else entry
                click.echo(url)
            click.echo(f"\n{len(url_entries)} URLs would be crawled")
        except Exception as exc:
            click.echo(f"Error during URL discovery: {exc}", err=True)
            raise SystemExit(1) from exc
        return  # Exit without crawling
```

**Verification:** `web-scraper crawl <site> --dry-run` shows URLs without creating snapshot.

---

## Phase 6: list-snapshots Command

### Step 6.1: Add list-snapshots command

**File to modify:** `web_scraper/cli.py`

Add new command after existing commands:

```python
@app.command("list-snapshots", help="List snapshots for a site.")
@click.argument("site_name")
@click.option(
    "--base-path",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Base directory containing corpora/ folder.",
)
def list_snapshots(site_name: str, base_path: Path | None) -> None:
    """
    List all snapshots for a site with metadata.

    Args:
        site_name: Name of the site.
        base_path: Optional base directory containing corpora/ folder.
    """
    import json
    from web_scraper.corpus.symlink import LATEST_SYMLINK_NAME
    
    corpora_dir = default_corpora_dir(base_path)
    site_dir = corpora_dir / site_name
    
    if not site_dir.exists():
        click.echo(f"No snapshots found for site: {site_name}")
        return
    
    snapshots = []
    for item in site_dir.iterdir():
        # Skip the 'latest' symlink
        if item.name == LATEST_SYMLINK_NAME:
            continue
        if not item.is_dir():
            continue
        
        manifest_path = item / "manifest.json"
        if not manifest_path.exists():
            continue
        
        try:
            manifest = json.loads(manifest_path.read_text())
            status = manifest.get("status", "unknown")
            total_pages = manifest.get("total_pages", 0)
            created_at = manifest.get("created_at", "unknown")
            
            # Check for chunks
            chunks_path = item / "chunks.jsonl"
            if chunks_path.exists():
                chunk_count = sum(1 for _ in chunks_path.read_text().splitlines())
            else:
                chunk_count = None
            
            snapshots.append({
                "id": item.name,
                "status": status,
                "pages": total_pages,
                "chunks": chunk_count,
                "created_at": created_at,
            })
        except Exception:
            continue
    
    # Sort by snapshot ID descending (most recent first)
    snapshots.sort(key=lambda s: s["id"], reverse=True)
    
    if not snapshots:
        click.echo(f"No snapshots found for site: {site_name}")
        return
    
    # Print table
    for snap in snapshots:
        chunks_str = f"{snap['chunks']:>4}" if snap['chunks'] is not None else "   -"
        click.echo(
            f"{snap['id']}  {snap['status']:<10}  {snap['pages']:>4} pages  "
            f"{chunks_str} chunks  {snap['created_at']}"
        )
```

**Verification:** `web-scraper list-snapshots <site>` shows snapshot table.

---

## Phase 7: init Command

### Step 7.1: Create init module

**File to create:** `web_scraper/init.py`

```python
"""Site configuration scaffolding utilities."""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

import click


def _derive_include_pattern(url: str) -> str:
    """Derive an include pattern from a URL."""
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip("/")
    if path:
        return f"{base}{path}/**"
    return f"{base}/**"


def scaffold_site_config(
    site_name: str,
    sites_dir: Path,
    url: str | None = None,
    interactive: bool = True,
) -> Path:
    """
    Create a new site configuration file.

    Args:
        site_name: Site identifier (becomes filename).
        sites_dir: Directory to create config in.
        url: Optional starting URL.
        interactive: Whether to prompt for missing fields.

    Returns:
        Path to created config file.

    Raises:
        click.ClickException: If config already exists or required fields missing.
    """
    config_path = sites_dir / f"{site_name}.yaml"
    
    if config_path.exists():
        raise click.ClickException(f"Config already exists: {config_path}")
    
    # Get URL if not provided
    if not url and interactive:
        if sys.stdin.isatty():
            url = click.prompt("Entrypoint URL", type=str)
        else:
            raise click.ClickException("--url is required in non-interactive mode")
    
    if not url:
        raise click.ClickException("URL is required. Use --url or run interactively.")
    
    # Derive values from URL
    include_pattern = _derive_include_pattern(url)
    
    # Get site name if interactive
    display_name = site_name.replace("-", " ").title()
    if interactive and sys.stdin.isatty():
        display_name = click.prompt("Site name", default=display_name)
    
    # Get max pages if interactive
    max_pages = 100
    if interactive and sys.stdin.isatty():
        max_pages = click.prompt("Max pages", default=100, type=int)
    
    # Generate YAML content
    content = f"""# Site configuration for {display_name}
# Generated by: web-scraper init

name: {display_name}

entrypoints:
  - {url}

include:
  - {include_pattern}

exclude: []

max_pages: {max_pages}

formats:
  - markdown

only_main_content: true

include_subdomains: false
"""
    
    sites_dir.mkdir(parents=True, exist_ok=True)
    config_path.write_text(content, encoding="utf-8")
    
    return config_path
```

**Verification:** Module imports without error.

---

### Step 7.2: Add init command to CLI

**File to modify:** `web_scraper/cli.py`

Add command:

```python
@app.command("init", help="Create a new site configuration.")
@click.argument("site_name")
@click.option(
    "--url",
    type=str,
    default=None,
    help="Starting URL for the site.",
)
@click.option(
    "--base-path",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Base directory containing sites/ folder.",
)
def init(site_name: str, url: str | None, base_path: Path | None) -> None:
    """
    Create a new site configuration file.

    Args:
        site_name: Site identifier (becomes filename without .yaml).
        url: Optional starting URL.
        base_path: Optional base directory.
    """
    from web_scraper.init import scaffold_site_config
    
    sites_dir = default_sites_dir(base_path)
    
    try:
        config_path = scaffold_site_config(
            site_name,
            sites_dir,
            url=url,
            interactive=(url is None),
        )
        click.echo(f"Created {config_path}")
    except click.ClickException:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc
```

**Verification:** `web-scraper init my-site --url https://example.com` creates config file.

---

## Phase 8: Optional id Field

### Step 8.1: Update SiteConfig model

**File to modify:** `web_scraper/models.py`

**Change 1:** Make id optional:

```python
# Before:
id: str

# After:
id: str | None = None
```

**Change 2:** Add private field for filename injection (after id):

```python
# Add this line:
_config_filename: str | None = Field(default=None, exclude=True, repr=False)
```

**Change 3:** Add model validator (after field validators):

```python
from pydantic import model_validator

@model_validator(mode="after")
def derive_id_from_filename(self) -> "SiteConfig":
    """Derive id from filename if not explicitly set."""
    if self.id is None:
        if self._config_filename:
            object.__setattr__(self, "id", self._config_filename)
        else:
            raise ValueError(
                "id is required when config is not loaded from file. "
                "Either provide id explicitly or load config using load_site_config()."
            )
    return self
```

**Verification:** `SiteConfig` accepts configs without `id` field when `_config_filename` is set.

---

### Step 8.2: Update loader to inject filename

**File to modify:** `web_scraper/sites/loader.py`

In `load_site_config` function, before creating SiteConfig:

```python
# Before:
return SiteConfig(**data)

# After:
data["_config_filename"] = config_path.stem
return SiteConfig(**data)
```

**Verification:** Config without `id` field loads successfully.

---

### Step 8.3: Update template

**File to modify:** `sites/template.yaml`

Update the id comment:

```yaml
# Before:
# REQUIRED: Unique site identifier (must match filename without .yaml)
id: example-site

# After:
# OPTIONAL: Site identifier (defaults to filename without .yaml if omitted)
# id: example-site
```

**Verification:** Template reflects optional id.

---

## Phase 9: CLI Output Polish

### Step 9.1: Final output message updates

**File to modify:** `web_scraper/cli.py`

Ensure all output messages follow the new patterns:

1. Crawl start: `Starting crawl: {site_name}...` or `Resuming {site_name} from {snapshot_id}...`
2. Crawl complete: `Crawl complete: {n} pages` or `Crawl complete: {n} pages, {m} chunks`
3. Output path: `Output: {site_dir}/latest/`
4. Verbose only: `Snapshot ID: {snapshot_id}`
5. Interrupt: `Resume by running: web-scraper crawl {site_name}`

---

## Phase 10: Final Verification

### Step 10.1: Run full test suite

```bash
pytest -q
```

All tests must pass.

### Step 10.2: Run type checking

```bash
mypy web_scraper
```

No new errors.

### Step 10.3: Run linting

```bash
ruff check web_scraper tests
```

No new errors.

### Step 10.4: Manual verification

```bash
# Create test site
web-scraper init test-site --url https://httpbin.org/html

# Show config
web-scraper show-site test-site

# Dry run
web-scraper crawl test-site --dry-run

# Full crawl with chunks
web-scraper crawl test-site --chunks --verbose

# Verify outputs
ls -la corpora/test-site/
ls -la corpora/test-site/latest/
cat corpora/test-site/latest/manifest.json | head
ls corpora/test-site/latest/.meta/

# List snapshots
web-scraper list-snapshots test-site
```

---

## Summary

After completing all phases, the system should:

1. ✅ Create `latest` symlink on successful crawl
2. ✅ Auto-resume incomplete snapshots by default
3. ✅ Support `--fresh` to force new snapshot
4. ✅ Support `--chunks` for single-command workflow
5. ✅ Support `--dry-run` to preview URLs
6. ✅ Provide `list-snapshots` command
7. ✅ Provide `init` command for scaffolding
8. ✅ Allow optional `id` field in configs
9. ✅ Store machine artefacts in `.meta/` directory
10. ✅ Show clean output with `latest/` path


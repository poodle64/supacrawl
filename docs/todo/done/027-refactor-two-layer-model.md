# Implementation Plan: Two-Layer Model Refactor

**Document Purpose:** Step-by-step implementation plan for refactoring web-scraper into a two-layer model: human-optimised CLI workflow + machine contract preserved.

**Date:** 2025-12-18

---

## A. Architecture Summary

### A.1 Updated Mental Model for Humans

**Before (current):**
```
User → YAML config → crawl command → snapshot ID → chunk command → filesystem navigation
```

**After (target):**
```
User → YAML config (or URL quick start) → crawl command [--chunks] → "Output: corpora/{site}/latest/"
```

**Key changes:**
1. Snapshot IDs are internal; users see `latest/` symlink
2. `--chunks` flag on `crawl` enables single-command workflow
3. Auto-resume by default when incomplete snapshot exists
4. `init` command scaffolds configs interactively
5. `--dry-run` on `crawl` shows planned URLs without fetching
6. Machine artefacts (crawl state, checksums, logs) move to `.meta/` directory

### A.2 Updated Contract for Machines

**Guaranteed paths (stable):**
| Path | Purpose |
|------|---------|
| `corpora/{site}/latest/manifest.json` | Current snapshot manifest (via symlink) |
| `corpora/{site}/latest/chunks.jsonl` | Current chunks (if generated) |
| `corpora/{site}/latest/markdown/` | Markdown files |
| `corpora/{site}/{snapshot_id}/manifest.json` | Pinned snapshot manifest |

**Manifest schema (unchanged):**
- `site_id`, `site_name`, `provider`, `snapshot_id`, `created_at`
- `status`: `completed`, `in_progress`, `aborted`
- `total_pages`, `formats`, `pages[]`, `stats`, `metadata`

**Internal artefacts (hidden in `.meta/`):**
- `crawl_state.json` → `.meta/crawl_state.json`
- `checksums.sha256` → `.meta/checksums.sha256`
- `run.log.jsonl` → `.meta/run.log.jsonl`

### A.3 Symlink Implementation

**Platform approach:**
- Use `Path.symlink_to()` which works on macOS and Linux
- Symlink target is relative: `latest -> 2025-12-18_1430`
- If symlink already exists, remove and recreate (atomic update)
- Windows is out of scope (project targets macOS/Linux developer environments)

**Symlink location:**
- `corpora/{site}/latest` → `{snapshot_id}/`
- Updated after successful crawl completion
- Not updated for aborted/in-progress snapshots

---

## B. File-Level Change Inventory

### B.1 Files to Modify

| File | Change Type | Summary |
|------|-------------|---------|
| `web_scraper/cli.py` | **Edit** | Add `--chunks`, `--fresh`, `--dry-run` flags to `crawl`; add `init` and `list-snapshots` commands; change default resume behaviour; update output messages |
| `web_scraper/corpus/writer.py` | **Edit** | Move artefacts to `.meta/`; add `update_latest_symlink()` function; update paths for checksums/logs |
| `web_scraper/corpus/state.py` | **Edit** | Change `STATE_FILE` to `.meta/crawl_state.json`; update `save_state`/`load_state` paths |
| `web_scraper/corpus/layout.py` | **Edit** | Add `latest_symlink_path()`, `update_latest_symlink()`, `resolve_latest_snapshot()` functions |
| `web_scraper/sites/loader.py` | **Edit** | Support optional `id` field (derive from filename if missing) |
| `web_scraper/models.py` | **Edit** | Make `id` optional in `SiteConfig` with `@model_validator` to derive from filename |
| `web_scraper/scrapers/crawl4ai.py` | **Edit** | Update writer instantiation for `.meta/` paths; call `update_latest_symlink()` on completion |
| `web_scraper/prep/chunker.py` | **Edit** | No changes required (already reads from snapshot path) |
| `sites/template.yaml` | **Edit** | Mark `id` as optional, update documentation comment |

### B.2 Files to Add

| File | Purpose |
|------|---------|
| `web_scraper/init.py` | Site config scaffolding logic for `init` command |
| `web_scraper/corpus/symlink.py` | Symlink management utilities (portable, testable) |
| `tests/unit/test_symlink.py` | Unit tests for symlink utilities |
| `tests/integration/test_init_command.py` | Integration tests for `init` command |
| `tests/integration/test_list_snapshots.py` | Integration tests for `list-snapshots` command |
| `tests/integration/test_auto_resume.py` | Integration tests for auto-resume behaviour |
| `tests/integration/test_chunks_flag.py` | Integration tests for `--chunks` flag on crawl |

### B.3 Files to Delete

None. All changes are additive or in-place modifications.

---

## C. Step-by-Step Execution Checklist

### Phase 1: Foundation (symlink utilities, .meta directory)

**Checkpoint:** Symlink utilities work independently; state files write to `.meta/`

- [ ] **Step 1.1:** Create `web_scraper/corpus/symlink.py` with symlink utilities
  - Function `update_latest_symlink(site_dir: Path, snapshot_id: str) -> Path`
  - Function `resolve_latest_snapshot(site_dir: Path) -> Path | None`
  - Function `remove_symlink_if_exists(symlink_path: Path) -> None`
  - Handle symlink creation with relative target
  - Handle existing symlink removal and recreation

- [ ] **Step 1.2:** Create `tests/unit/test_symlink.py` with unit tests
  - Test `update_latest_symlink` creates correct symlink
  - Test `update_latest_symlink` replaces existing symlink
  - Test `resolve_latest_snapshot` returns None for missing symlink
  - Test `resolve_latest_snapshot` returns path for valid symlink

- [ ] **Step 1.3:** Update `web_scraper/corpus/state.py` to use `.meta/` directory
  - Change `STATE_FILE = "crawl_state.json"` to `STATE_FILE = ".meta/crawl_state.json"`
  - Update `save_state` to create `.meta/` directory if needed
  - Update `load_state` to read from `.meta/crawl_state.json`
  - Add backward compatibility: check old location, migrate if found

- [ ] **Step 1.4:** Update `web_scraper/corpus/writer.py` to use `.meta/` directory
  - Change `self.run_log_path` from `snapshot_path / "run.log.jsonl"` to `snapshot_path / ".meta" / "run.log.jsonl"`
  - Change `self.checksums_path` from `snapshot_path / "checksums.sha256"` to `snapshot_path / ".meta" / "checksums.sha256"`
  - Ensure `.meta/` directory is created in `start()` method
  - Keep `manifest.json` in snapshot root (machine contract)

- [ ] **Step 1.5:** Run existing tests to verify no regressions
  - Command: `pytest tests/unit tests/integration -q`

### Phase 2: Symlink integration in crawl flow

**Checkpoint:** Completed crawls create `latest` symlink automatically

- [ ] **Step 2.1:** Update `web_scraper/corpus/layout.py` to export symlink functions
  - Add import from `web_scraper/corpus/symlink.py`
  - Re-export `update_latest_symlink`, `resolve_latest_snapshot`

- [ ] **Step 2.2:** Update `web_scraper/corpus/writer.py` to call symlink update
  - Import `update_latest_symlink` from `web_scraper.corpus.symlink`
  - In `IncrementalSnapshotWriter.complete()`: after writing manifest, call `update_latest_symlink(self.snapshot_path.parent, self.snapshot_id)`
  - Do NOT call symlink update in `abort()` method

- [ ] **Step 2.3:** Update CLI output to show `latest/` path
  - In `web_scraper/cli.py`, `crawl` command: change output message from `Snapshot created at {snapshot_path}` to `Output: {site_dir}/latest/`
  - Keep snapshot ID visible only with `--verbose`

- [ ] **Step 2.4:** Add integration test for symlink creation
  - In `tests/integration/test_cli.py`: add test that verifies `latest` symlink exists after successful crawl
  - Verify symlink resolves to correct snapshot directory

### Phase 3: Auto-resume behaviour

**Checkpoint:** `crawl` auto-resumes incomplete snapshots by default; `--fresh` forces new

- [ ] **Step 3.1:** Update `crawl` command signature in `web_scraper/cli.py`
  - Remove `--resume` option
  - Add `--fresh` flag: `@click.option("--fresh", is_flag=True, default=False, help="Force a new snapshot even if an incomplete one exists.")`

- [ ] **Step 3.2:** Implement auto-resume logic in `crawl` command
  - Check for resumable snapshot: `resume_snapshot = find_resumable_snapshot(corpora_dir, config.id)`
  - If `--fresh` flag: set `resume_snapshot = None`
  - If resumable snapshot found and not `--fresh`: print `Resuming from {snapshot_id}: {n} pages completed` and use it
  - If no resumable snapshot or `--fresh`: start new crawl

- [ ] **Step 3.3:** Update resume output messages
  - When resuming: `Resuming {site_name} from {snapshot_id} ({n} pages complete)...`
  - When starting fresh: `Starting crawl: {site_name}...`
  - When `--fresh` forces new: `Starting fresh crawl: {site_name} (ignoring incomplete snapshot)...`

- [ ] **Step 3.4:** Create `tests/integration/test_auto_resume.py`
  - Test: incomplete snapshot triggers auto-resume without flag
  - Test: `--fresh` flag starts new snapshot even with incomplete one
  - Test: completed snapshot starts new snapshot (no resume)

### Phase 4: `--chunks` flag on crawl command

**Checkpoint:** Single command `crawl --chunks` produces both pages and chunks.jsonl

- [ ] **Step 4.1:** Add `--chunks` flag to `crawl` command
  - Add option: `@click.option("--chunks", is_flag=True, default=False, help="Generate chunks.jsonl after crawl completes.")`
  - Add chunking options: `--max-chars` (default 1200), pass through to chunker

- [ ] **Step 4.2:** Implement post-crawl chunking
  - After successful crawl completion (pages returned, snapshot created):
  - If `--chunks` flag is set: call `chunk_snapshot(snapshot_path, max_chars=max_chars)`
  - Print: `Chunks written to {snapshot_path}/chunks.jsonl`

- [ ] **Step 4.3:** Update CLI output for combined workflow
  - Single-line summary: `Crawl complete: {n} pages, {m} chunks` (if `--chunks`)
  - Single-line summary: `Crawl complete: {n} pages` (if no `--chunks`)
  - Final line: `Output: corpora/{site}/latest/`

- [ ] **Step 4.4:** Create `tests/integration/test_chunks_flag.py`
  - Test: `crawl --chunks` produces chunks.jsonl in snapshot
  - Test: `crawl` without `--chunks` does not produce chunks.jsonl
  - Test: `--max-chars` parameter is passed through correctly

### Phase 5: `--dry-run` flag (map integration)

**Checkpoint:** `crawl --dry-run` shows planned URLs without fetching content

- [ ] **Step 5.1:** Add `--dry-run` flag to `crawl` command
  - Add option: `@click.option("--dry-run", is_flag=True, default=False, help="Show URLs that would be crawled without fetching content.")`

- [ ] **Step 5.2:** Implement dry-run logic
  - If `--dry-run` is set:
    - Import `map_site` function from `web_scraper.map`
    - Call `map_site(config, max_urls=config.max_pages)` to get URL list
    - Print each URL to stdout (one per line)
    - Print summary: `{n} URLs would be crawled`
    - Exit without starting actual crawl

- [ ] **Step 5.3:** Add test for dry-run behaviour
  - In `tests/integration/test_cli.py`: test that `--dry-run` prints URLs without creating snapshot

### Phase 6: `list-snapshots` command

**Checkpoint:** Users can list snapshots with status, date, and page count

- [ ] **Step 6.1:** Add `list-snapshots` command to CLI
  - Command: `@app.command("list-snapshots", help="List snapshots for a site.")`
  - Argument: `site_name` (required)
  - Option: `--base-path` (optional, same as other commands)

- [ ] **Step 6.2:** Implement snapshot listing logic
  - Get site directory: `corpora_dir / site_name`
  - List all subdirectories (exclude `latest` symlink)
  - For each directory, read `manifest.json` to get: `status`, `created_at`, `total_pages`
  - Check if `chunks.jsonl` exists for chunk count
  - Sort by snapshot_id descending (most recent first)

- [ ] **Step 6.3:** Format output as compact table
  - Format: `{snapshot_id}  {status:10}  {pages:>4} pages  {chunks:>4} chunks  {created_at}`
  - Example:
    ```
    2025-12-18_1430  completed      127 pages   342 chunks  2025-12-18 14:32:15
    2025-12-17_0915  aborted         42 pages     - chunks  2025-12-17 09:18:03
    ```

- [ ] **Step 6.4:** Create `tests/integration/test_list_snapshots.py`
  - Test: command lists snapshots with correct metadata
  - Test: command handles empty corpora directory
  - Test: command handles missing site directory

### Phase 7: `init` command

**Checkpoint:** Users can scaffold site configs interactively or from URL

- [ ] **Step 7.1:** Create `web_scraper/init.py` with scaffolding logic
  - Function `scaffold_site_config(site_name: str, url: str | None, sites_dir: Path, interactive: bool = True) -> Path`
  - If `url` provided: derive entrypoint and include pattern from URL
  - If `interactive`: prompt for missing required fields (name, url if not provided)
  - Generate YAML content with sensible defaults
  - Write to `sites/{site_name}.yaml`
  - Return path to created file

- [ ] **Step 7.2:** Add `init` command to CLI
  - Command: `@app.command("init", help="Create a new site configuration.")`
  - Argument: `site_name` (required)
  - Option: `--url` (optional): starting URL to derive config from
  - Option: `--base-path` (optional, same as other commands)

- [ ] **Step 7.3:** Implement `init` command logic
  - Check if config already exists; if so, error with message
  - If `--url` provided: derive entrypoint and include pattern, create non-interactively
  - If no `--url`: prompt for site name, URL, max_pages
  - Call `scaffold_site_config()` to create the file
  - Print: `Created sites/{site_name}.yaml`

- [ ] **Step 7.4:** Add URL quick-start to `crawl` command
  - Add option to `crawl`: `--init` (takes site_name as value)
  - If first positional arg looks like a URL (starts with `http`):
    - Treat it as URL, require `--init <site_name>`
    - Call `scaffold_site_config(site_name, url, sites_dir, interactive=False)`
    - Then proceed with crawl
  - This enables: `web-scraper crawl https://example.com --init my-site`

- [ ] **Step 7.5:** Create `tests/integration/test_init_command.py`
  - Test: `init my-site --url https://example.com` creates valid config
  - Test: `init` with existing config shows error
  - Test: `crawl https://example.com --init my-site` creates config and crawls

### Phase 8: Optional `id` field in SiteConfig

**Checkpoint:** Users can omit `id` field; it's derived from filename

- [ ] **Step 8.1:** Update `web_scraper/models.py` SiteConfig
  - Change `id: str` to `id: str | None = None`
  - Add `_config_filename: str | None = Field(default=None, exclude=True)` private field for filename injection

- [ ] **Step 8.2:** Add model validator to derive `id` from filename
  - Add `@model_validator(mode="after")` to `SiteConfig`
  - If `id` is None and `_config_filename` is set: derive `id` from filename (strip `.yaml`)
  - If `id` is None and `_config_filename` is not set: raise ValidationError

- [ ] **Step 8.3:** Update `web_scraper/sites/loader.py` to inject filename
  - In `load_site_config()`: before calling `SiteConfig(**data)`:
  - Inject `_config_filename` into data dict: `data["_config_filename"] = config_path.stem`

- [ ] **Step 8.4:** Update `sites/template.yaml`
  - Change comment for `id` from "REQUIRED" to "OPTIONAL (defaults to filename)"
  - Keep example `id: example-site` but add comment that it can be omitted

- [ ] **Step 8.5:** Add unit test for optional `id`
  - In `tests/unit/test_loader.py`: test config without `id` field loads successfully
  - Verify `config.id` equals filename stem

### Phase 9: Update CLI output messaging

**Checkpoint:** CLI output is cleaner, focuses on human-readable paths

- [ ] **Step 9.1:** Update `crawl` command output
  - Remove: `Snapshot created at corpora/site/2025-12-18_1430`
  - Add: `Output: corpora/{site}/latest/`
  - With `--verbose`: also show `Snapshot ID: 2025-12-18_1430`

- [ ] **Step 9.2:** Update `chunk` command output
  - Change: `Chunks written to {path}` to include chunk count: `Wrote {n} chunks to {path}`

- [ ] **Step 9.3:** Remove manifest mentions from user output
  - Never mention `manifest.json` in CLI output (it's a machine artefact)
  - Keep manifest documentation for tool authors only

- [ ] **Step 9.4:** Update interrupted crawl message
  - Change: `Resume with: web-scraper crawl {site} --resume latest`
  - To: `Resume by running: web-scraper crawl {site}`

### Phase 10: Final verification and cleanup

**Checkpoint:** All tests pass, documentation updated

- [ ] **Step 10.1:** Run full test suite
  - Command: `pytest -q`
  - All tests must pass

- [ ] **Step 10.2:** Run type checking
  - Command: `mypy web_scraper`
  - No new errors

- [ ] **Step 10.3:** Run linting
  - Command: `ruff check web_scraper tests`
  - No new errors

- [ ] **Step 10.4:** Update existing test fixtures
  - Update any tests that expect `crawl_state.json` in snapshot root
  - Update any tests that check for `checksums.sha256` in snapshot root
  - Update any tests that use `--resume` flag (now `--fresh`)

- [ ] **Step 10.5:** Manual verification
  - Run: `web-scraper init test-site --url https://example.com`
  - Run: `web-scraper crawl test-site --chunks --verbose`
  - Verify: `corpora/test-site/latest/` symlink exists
  - Verify: `corpora/test-site/latest/chunks.jsonl` exists
  - Verify: `corpora/test-site/latest/.meta/crawl_state.json` exists

---

## D. Acceptance Criteria

### D.1 CLI Behaviour Examples

**`web-scraper crawl my-site --chunks`:**
```
Starting crawl: my-site...
  ├── https://example.com (42 pages)
  └── Completed in 1m 23s

Crawl complete: 42 pages, 127 chunks
Output: corpora/my-site/latest/
```

**`web-scraper crawl my-site` (with incomplete snapshot):**
```
Resuming my-site from 2025-12-18_1430 (15 pages complete)...
  └── Completed in 0m 48s

Crawl complete: 42 pages
Output: corpora/my-site/latest/
```

**`web-scraper crawl my-site --fresh`:**
```
Starting fresh crawl: my-site (ignoring incomplete snapshot)...
  └── Completed in 1m 25s

Crawl complete: 42 pages
Output: corpora/my-site/latest/
```

**`web-scraper crawl my-site --dry-run`:**
```
https://example.com
https://example.com/page1
https://example.com/page2
...
42 URLs would be crawled
```

**`web-scraper list-snapshots my-site`:**
```
2025-12-18_1430  completed      42 pages   127 chunks  2025-12-18 14:32:15
2025-12-17_0915  aborted        15 pages     - chunks  2025-12-17 09:18:03
```

**`web-scraper init my-site --url https://example.com`:**
```
Created sites/my-site.yaml
```

### D.2 Filesystem Outcomes

**After successful crawl:**
```
corpora/
└── my-site/
    ├── latest -> 2025-12-18_1430/    # Symlink
    └── 2025-12-18_1430/
        ├── manifest.json              # Machine contract (root)
        ├── chunks.jsonl               # If --chunks used
        ├── markdown/
        │   └── ...
        └── .meta/                     # Hidden artefacts
            ├── crawl_state.json
            ├── checksums.sha256
            └── run.log.jsonl
```

### D.3 Machine Contract Assertions

**Test: `corpora/{site}/latest/manifest.json` is accessible:**
```python
def test_latest_manifest_accessible(tmp_path):
    # After crawl completes
    latest_manifest = tmp_path / "corpora" / "my-site" / "latest" / "manifest.json"
    assert latest_manifest.exists()
    manifest = json.loads(latest_manifest.read_text())
    assert manifest["status"] == "completed"
```

**Test: Manifest schema unchanged:**
```python
def test_manifest_schema_has_required_fields(manifest):
    assert "site_id" in manifest
    assert "snapshot_id" in manifest
    assert "status" in manifest
    assert "created_at" in manifest
    assert "pages" in manifest
    assert "metadata" in manifest
    assert "schema_version" in manifest["metadata"]
```

### D.4 Test Updates Required

| Test File | Update Required |
|-----------|-----------------|
| `tests/integration/test_cli.py` | Update to use `--fresh` instead of `--resume`; verify `latest` symlink |
| `tests/integration/test_corpus_writer.py` | Verify `.meta/` directory for state/checksums/logs |
| `tests/e2e/test_manifest_metadata.py` | No changes (manifest still in root) |
| `tests/e2e/test_manifest_schema_validation.py` | No changes |

---

## E. Risk Register

### E.1 Cross-Platform Issues

| Risk | Mitigation |
|------|------------|
| Windows symlinks require admin | Out of scope; document macOS/Linux only |
| Symlink on network filesystem | Use relative symlinks; test locally first |
| Symlink in tar archive | Use `tarfile` with `follow_symlinks=False` |

### E.2 Edge Cases

| Edge Case | Handling |
|-----------|----------|
| Aborted snapshot | Do NOT update `latest` symlink for aborted snapshots |
| Concurrent crawls | Existing snapshot lock prevents concurrent writes; symlink update is atomic |
| Missing chunks.jsonl | `list-snapshots` shows `-` for chunk count |
| Incomplete manifest | Skip snapshot in `list-snapshots`, log warning |
| `latest` symlink missing | `resolve_latest_snapshot` returns None; commands fall back to explicit paths |
| Old snapshot format | Backward compatibility: check old state location, migrate if found |

### E.3 Rollback Strategy

If issues arise during implementation:
1. Each phase is independently testable and reversible
2. Git commits should be made after each phase checkpoint
3. If phase fails: revert commits for that phase, debug, retry
4. Symlink functionality is additive; removing it requires only deleting symlink code

---

## F. Explicit Non-Goals

The following are **not** being done in this phase:

1. **API server mode** — No HTTP API; CLI-only
2. **Database/indexing** — No SQLite or search index for corpora
3. **Major Crawl4AI changes** — No changes to scraping logic or Crawl4AI integration
4. **Windows support** — Symlinks are macOS/Linux only
5. **GUI or TUI** — No graphical interface
6. **Configuration format changes** — YAML format unchanged (only `id` becomes optional)
7. **Manifest schema changes** — Schema version unchanged; only file locations change
8. **Removing existing commands** — `chunk`, `compress`, `extract` commands remain unchanged
9. **Interactive prompts in non-tty** — `init` without `--url` requires TTY; fails gracefully otherwise
10. **Migration tooling for old snapshots** — Old snapshots work but don't have `.meta/` layout

---

## G. Implementation Order Summary

```
Phase 1: Foundation (.meta/, symlink utilities)     → Checkpoint: pytest passes
Phase 2: Symlink integration                        → Checkpoint: latest/ created on crawl
Phase 3: Auto-resume behaviour                      → Checkpoint: --fresh flag works
Phase 4: --chunks flag                              → Checkpoint: single-command chunking
Phase 5: --dry-run flag                             → Checkpoint: URL preview works
Phase 6: list-snapshots command                     → Checkpoint: snapshot listing works
Phase 7: init command                               → Checkpoint: config scaffolding works
Phase 8: Optional id field                          → Checkpoint: id can be omitted
Phase 9: CLI output polish                          → Checkpoint: output is clean
Phase 10: Final verification                        → Checkpoint: all tests pass
```

Each phase can be implemented in a single PR. Phases 1-4 are the core changes; phases 5-10 are enhancements.


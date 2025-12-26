# Supacrawl CLI Simplification Plan

## Overview

Refactor supacrawl from a dual-paradigm CLI (site-config + URL-based) to a pure Firecrawl-aligned CLI (URL-only).

**Target CLI:**
```bash
supacrawl scrape       # one page → stdout/file
supacrawl crawl        # discover + scrape → directory
supacrawl map          # discover URLs → stdout/file
supacrawl search       # web search
supacrawl llm-extract  # structured extraction
supacrawl agent        # autonomous agent
supacrawl cache        # cache management
```

---

## Final Command Signatures

### `scrape` (renamed from `scrape-url`)
```
supacrawl scrape <url> [OPTIONS]
  -f, --format          markdown|html|json|screenshot|pdf|links|images|branding|summary
  -o, --output          Output file
  --only-main-content   Extract main content [default: true]
  --timeout             Page timeout ms [default: 30000]
  --wait-for            Wait after load ms
  --stealth             Enhanced stealth mode
  --proxy               Proxy URL
  # All other existing scrape-url options retained
```

### `crawl` (merged from `crawl-url`, site-config version removed)
```
supacrawl crawl <url> [OPTIONS]
  -o, --output          Output directory [required]
  --limit               Max pages [default: 100]
  --depth               Max depth [default: 3]
  --include             URL patterns to include (glob)
  --exclude             URL patterns to exclude (glob)
  -f, --format          Output formats [default: markdown]
  --resume              Resume from previous crawl
  --stealth             Enhanced stealth mode
  --proxy               Proxy URL
```

### `map` (merged from `map-url`, site-config version removed)
```
supacrawl map <url> [OPTIONS]
  -o, --output          Output file (or stdout)
  -f, --format          json|text [default: text]
  --limit               Max URLs [default: 200]
  --depth               Max depth [default: 3]
  --sitemap             include|skip|only [default: include]
  --include-subdomains  Include subdomains
  --search              Filter URLs by text
  --stealth             Enhanced stealth mode
  --proxy               Proxy URL
```

---

## Crawl Output Format (Without Corpus)

Simple directory structure (already implemented in `crawl-url`):
```
output_dir/
  manifest.json          # Simple URL tracking for resume
  index.md              # Content files with YAML frontmatter
  about.md
  blog_post-1.md
  blog_post-1_a1b2c3d4.md  # Hash suffix for duplicates
```

**manifest.json:**
```json
{"scraped_urls": ["https://example.com/", "https://example.com/about"]}
```

**Markdown files include frontmatter:**
```markdown
---
source_url: https://example.com/about
title: About Us
---
# About Us
...
```

Resume works via manifest.json - no corpus state needed.

---

## Systems to Remove

### Site Config System
| Component | Location |
|-----------|----------|
| Site loader | `src/supacrawl/sites/` (DELETE directory) |
| Scaffold | `src/supacrawl/init.py` (DELETE file) |
| Models | `SiteConfig`, `SitemapConfigModel`, `RobotsConfigModel`, `CrawlPolitenessConfig` from models.py |
| Config helper | `default_sites_dir()` from config.py |
| YAML configs | `sites/` directory |
| CLI commands | `init`, `list-sites`, `show-site` |

### Corpus System
| Component | Location |
|-----------|----------|
| Corpus package | `src/supacrawl/corpus/` (DELETE directory) |
| Chunker | `src/supacrawl/prep/chunker.py` (DELETE file) |
| Config helper | `default_corpora_dir()` from config.py |
| Data directory | `corpora/` |
| CLI commands | `list-snapshots`, `chunk`, `compress`, `extract` |

### Other Removals
| Component | Reason |
|-----------|--------|
| `batch-scrape` command | Use shell loop or crawl |
| `OutputAdapter` protocol | No corpus output needed |
| `BatchService` | batch-scrape removed |

---

## Implementation Phases

### Phase 1: Branch and Baseline
- [x] Create branch `refactor/cli-simplification`
- [x] Run test suite, record baseline
- [x] Verify current CLI works

### Phase 2: Delete CLI Commands (sites.py, corpus.py)
- [x] Delete `src/supacrawl/cli/sites.py`
- [x] Delete `src/supacrawl/cli/corpus.py`
- [x] Update `src/supacrawl/cli/__init__.py` (remove imports)

### Phase 3: Delete Site Config System
- [x] Delete `src/supacrawl/sites/` directory
- [x] Delete `src/supacrawl/init.py`
- [x] Remove from models.py: `SiteConfig`, `SitemapConfigModel`, `RobotsConfigModel`, `CrawlPolitenessConfig`, `OutputFormat`
- [x] Remove `default_sites_dir()` from config.py

### Phase 4: Delete Corpus System
- [x] Delete `src/supacrawl/corpus/` directory
- [x] Delete `src/supacrawl/prep/chunker.py`
- [x] Remove `default_corpora_dir()` from config.py
- [x] Delete or empty `src/supacrawl/services/batch.py`

### Phase 5: Simplify CrawlService
- [x] Remove `output_adapter` parameter from `crawl()` method
- [x] Remove OutputAdapter imports and TYPE_CHECKING block
- [x] Keep simple file output (`_save_page`, `_load_resume_state`)

### Phase 6: Merge/Rename CLI Commands
- [x] In `crawl.py`: Delete site-config `crawl` (lines 208-605), rename `crawl-url` → `crawl`
- [x] In `map.py`: Delete site-config `map` (lines 148-270), rename `map-url` → `map`
- [x] In `scrape.py`: Rename `scrape-url` → `scrape`, delete `batch-scrape`

### Phase 7: Delete Tests
- [x] Delete unit tests: `test_loader.py`, `test_site_config_id.py`, `test_symlink.py`, `test_models.py`
- [x] Delete integration tests: `test_init_command.py`, `test_corpus_writer.py`, `test_corpus_and_chunker.py`, `test_auto_resume.py`, `test_list_snapshots.py`, `test_loader_optional_id.py`, `test_chunker.py`, `test_chunks_flag.py`
- [x] Delete e2e: `test_resume.py` (if corpus-dependent)
- [x] Delete `tests/fixtures/sites/` directory

### Phase 8: Update Remaining Tests
- [x] Update `test_cli.py` for new command names
- [x] Update `test_map_command.py` for `map` command
- [x] Fix any broken imports in remaining tests
- [x] Run test suite

### Phase 9: Delete Documentation
- [x] Delete `docs/40-usage/creating-site-configs-supacrawl.md`
- [x] Delete `docs/30-architecture/site-configuration-supacrawl.md`
- [x] Delete `docs/30-architecture/corpus-layout-supacrawl.md`

### Phase 10: Delete Cursor Rules
- [x] Delete `.cursor/rules/50-site-config-patterns-supacrawl.mdc`
- [x] Delete `.cursor/rules/50-corpus-layout-patterns-supacrawl.mdc`

### Phase 11: Rewrite Documentation
- [x] Rewrite `README.md` for URL-only CLI
- [x] Rewrite `docs/40-usage/cli-usage-supacrawl.md`
- [x] Update `.claude/CLAUDE.md`
- [x] Update `.cursor/rules/00-project-foundations-supacrawl.mdc`
- [x] Update `.cursor/rules/20-cli-patterns-supacrawl.mdc`

### Phase 12: Cleanup Pass 1 - Dead Code
- [x] Remove unused imports across all files
- [x] Remove any orphaned functions/classes
- [x] Run `ruff check --fix`

### Phase 13: Cleanup Pass 2 - Consistency
- [x] Verify command help text is consistent
- [x] Verify docstrings match new behaviour
- [x] Check for stale comments

### Phase 14: Cleanup Pass 3 - Quality
- [x] Run `mypy src/supacrawl`
- [x] Run full test suite
- [x] Manual smoke test of all commands

### Phase 15: Release
- [x] Update CHANGELOG.md (breaking changes!)
- [x] Bump version (major change)
- [x] Merge to main
- [x] Tag release (v2025.12.5)

### Phase 16: Red Team Pass 1 (v2025.12.6)
- [x] Fix stale `scrape-url` references in cli/cache.py, cli/__init__.py, services/captcha.py
- [x] Rewrite docs/README.md for simplified CLI
- [x] Rewrite docs/40-usage/USAGE_GUIDE.md (remove site config/corpus)
- [x] Rewrite docs/70-reliability/testing-supacrawl.md for new service patterns
- [x] Rewrite docs/30-architecture/snapshot-contract.md for crawl output format

### Phase 17: Red Team Pass 2
- [x] Delete obsolete test_phase9_output.py (imported from deleted tests)
- [x] Add e2e markers to slow network tests (test_map_service, test_scrape_service, test_crawl_service)

### Phase 18: Red Team Pass 3
- [x] Fix captcha.py docstring (second occurrence of scrape-url)
- [x] Fix cli/_common.py app docstring
- [x] Fix 20-cli-patterns-supacrawl.mdc (remove list-sites example)
- [x] Fix 50-scraper-provider-patterns-supacrawl.mdc (remove BatchService)
- [x] Fix error-handling-supacrawl.md (remove SiteConfig example)
- [x] Delete .claude/skills/rule-corpus-dev/ (obsolete skill)
- [x] Rewrite .claude/skills/rule-cli-dev/SKILL.md
- [x] Fix .claude/skills/rule-scraper-dev/SKILL.md (SupacrawlError, remove BatchService)

### Phase 19: Dead Code Cleanup
- [x] Remove BatchItem, BatchEvent, BatchResult models from models.py

---

## Files Summary

### DELETE (Source - 12 files/dirs)
- `src/supacrawl/cli/sites.py`
- `src/supacrawl/cli/corpus.py`
- `src/supacrawl/sites/` (directory)
- `src/supacrawl/corpus/` (directory)
- `src/supacrawl/init.py`
- `src/supacrawl/prep/chunker.py`
- `src/supacrawl/services/batch.py`

### DELETE (Tests - 13 files)
- `tests/unit/test_loader.py`
- `tests/unit/test_site_config_id.py`
- `tests/unit/test_symlink.py`
- `tests/unit/test_models.py`
- `tests/integration/test_init_command.py`
- `tests/integration/test_corpus_writer.py`
- `tests/integration/test_corpus_and_chunker.py`
- `tests/integration/test_auto_resume.py`
- `tests/integration/test_list_snapshots.py`
- `tests/integration/test_loader_optional_id.py`
- `tests/integration/test_chunker.py`
- `tests/integration/test_chunks_flag.py`
- `tests/fixtures/sites/` (directory)

### DELETE (Docs - 5 files)
- `docs/40-usage/creating-site-configs-supacrawl.md`
- `docs/30-architecture/site-configuration-supacrawl.md`
- `docs/30-architecture/corpus-layout-supacrawl.md`
- `.cursor/rules/50-site-config-patterns-supacrawl.mdc`
- `.cursor/rules/50-corpus-layout-patterns-supacrawl.mdc`

### MODIFY (Source - 6 files)
- `src/supacrawl/cli/__init__.py` - Remove imports
- `src/supacrawl/cli/crawl.py` - Delete site-config command, rename
- `src/supacrawl/cli/map.py` - Delete site-config command, rename
- `src/supacrawl/cli/scrape.py` - Rename command, delete batch-scrape
- `src/supacrawl/services/crawl.py` - Remove OutputAdapter
- `src/supacrawl/models.py` - Remove SiteConfig models
- `src/supacrawl/config.py` - Remove helpers (may become empty)

### REWRITE (Docs - 5 files)
- `README.md`
- `docs/40-usage/cli-usage-supacrawl.md`
- `.claude/CLAUDE.md`
- `.cursor/rules/00-project-foundations-supacrawl.mdc`
- `.cursor/rules/20-cli-patterns-supacrawl.mdc`

### UPDATE (Tests - 2 files)
- `tests/integration/test_cli.py`
- `tests/integration/test_map_command.py`

---

## Data Directories

| Directory | Action |
|-----------|--------|
| `sites/` | DELETE entirely |
| `corpora/` | Add to `.gitignore`, leave existing data |

---

## Skills to Update

| Skill | Action |
|-------|--------|
| `.claude/skills/rule-corpus-dev/` | DELETED - corpus system removed |
| `.claude/skills/rule-cli-dev/` | UPDATED - rewritten for simplified CLI |
| `.claude/skills/rule-scraper-dev/` | UPDATED - removed BatchService references |

---

## Design Decisions (User Confirmed)

1. **No backwards compatibility aliases** - Old command names (`scrape-url`, `crawl-url`, `map-url`) will not work after refactor. Clean break.
2. **Delete sites/ entirely** - No need to keep example YAML configs for reference.
3. **Update skills** - Rewrite `.claude/skills/` to reflect new simplified CLI rather than deleting them.

---

## Breaking Changes (for CHANGELOG)

1. **Removed commands:** `init`, `list-sites`, `show-site`, `list-snapshots`, `chunk`, `compress`, `extract`, `batch-scrape`
2. **Renamed commands:** `scrape-url` → `scrape`, `crawl-url` → `crawl`, `map-url` → `map` (no aliases)
3. **Removed site config system:** No more `sites/*.yaml` files
4. **Removed corpus system:** No more structured corpus output with manifests
5. **Simplified crawl output:** Simple directory of markdown files with basic manifest.json

---

*Status: COMPLETED - Released as v2025.12.5 (initial), v2025.12.6 (red team fixes)*

*Additional cleanup commits after v2025.12.6 for red team passes 2-3 and dead code removal.*

# Phase 6: Crawl4AI Cleanup

## Context

You are implementing Phase 6 of the Firecrawl-parity rebuild for the web-scraper project. This phase removes all Crawl4AI dependencies, code, documentation, and references now that the Playwright-based stack is complete.

**Branch:** `refactor/firecrawl-parity-v2`
**Depends On:** Phases 1-5 (all complete)

## Phase 6 Goals

Remove all traces of Crawl4AI from the codebase:
1. Delete Crawl4AI source files
2. Remove Crawl4AI from dependencies
3. Update all documentation
4. Clean up cursor rules
5. Remove obsolete env vars and config options

---

## Task 1: Delete Crawl4AI Source Files

Delete these files completely:

```bash
# Main scraper files (replaced by browser.py, converter.py, *_service.py)
rm web_scraper/scrapers/crawl4ai.py
rm web_scraper/scrapers/crawl4ai_config.py
rm web_scraper/scrapers/crawl4ai_result.py

# Tests for deleted code
rm tests/e2e/test_crawl4ai_quality.py
rm tests/fixtures/test_crawl4ai_quality_results.json

# Documentation for deleted code
rm docs/40-usage/crawl4ai-quality-best-practices.md

# Working docs (no longer needed)
rm SPA_DELAY_IMPLEMENTATION.md
```

After deletion, check for broken imports:
```bash
grep -r "from web_scraper.scrapers.crawl4ai" --include="*.py"
grep -r "from web_scraper.scrapers import crawl4ai" --include="*.py"
```

---

## Task 2: Remove Crawl4AI Dependency

Update `pyproject.toml`:

**Find and remove:**
```toml
"crawl4ai>=0.7.8",
```

**Also check for optional dependencies referencing crawl4ai.**

Run to verify:
```bash
grep -i crawl4ai pyproject.toml
# Should return nothing
```

---

## Task 3: Update Environment Variables

### Files to update:

1. **`.env.example`** - Remove all `CRAWL4AI_*` variables:
   - `CRAWL4AI_SPA_EXTRA_DELAY`
   - `CRAWL4AI_WAIT_UNTIL`
   - Any other `CRAWL4AI_*` entries

2. **`web_scraper/map.py`** - Replace CRAWL4AI env vars with WEB_SCRAPER equivalents:
   ```python
   # OLD:
   os.getenv("CRAWL4AI_SPA_EXTRA_DELAY", "2.0")

   # NEW:
   os.getenv("WEB_SCRAPER_SPA_DELAY", "2.0")
   ```

3. **Any other files** referencing `CRAWL4AI_*`:
   ```bash
   grep -r "CRAWL4AI_" --include="*.py" --include="*.md" --include="*.mdc"
   ```

---

## Task 4: Clean Up Models and Services

### `web_scraper/models.py`

Remove comments referencing Crawl4AI:
- Find: `# Crawl4AI` comments
- Find: `Maps to Crawl4AI` comments
- Replace with generic descriptions or remove

### `web_scraper/corpus/writer.py`

Remove Crawl4AI version checks if present:
```python
# REMOVE any code like:
try:
    import crawl4ai
    crawl4ai_version = crawl4ai.__version__
except ImportError:
    crawl4ai_version = None
```

### `web_scraper/content/fixes.py`

This file contains markdown fixes for Crawl4AI output issues. Review and either:
- Keep if fixes are still useful for general markdown cleaning
- Remove if fixes are Crawl4AI-specific

The `_check_crawl4ai_version()` function should be removed entirely.

Update `FixSpec` to remove `min_crawl4ai_version` field.

---

## Task 5: Update Cursor Rules

Update these `.cursor/rules/*.mdc` files to remove Crawl4AI references:

### Files to check:

```bash
grep -l "crawl4ai\|Crawl4AI\|CRAWL4AI" .cursor/rules/*.mdc
```

Expected files needing updates:
- `20-cli-patterns-web-scraper.mdc`
- `50-corpus-layout-patterns-web-scraper.mdc`
- `50-scraper-provider-patterns-web-scraper.mdc`
- `70-error-handling-web-scraper.mdc`
- `73-verification-web-scraper.mdc`

For each file:
1. Replace `crawl4ai` references with `playwright` or generic terms
2. Replace `CRAWL4AI_*` env vars with `WEB_SCRAPER_*`
3. Update any Crawl4AI-specific patterns to use new stack
4. Remove references to deleted files

---

## Task 6: Update Project Documentation

### `CLAUDE.md`

Remove any Crawl4AI mentions and update technology stack section.

### `README.md`

Update:
- Technology stack (Playwright instead of Crawl4AI)
- Installation instructions (no crawl4ai pip install)
- Any feature descriptions mentioning Crawl4AI

### `ROADMAP.md`

Update to reflect completed migration.

### `docs/` folder

Search and update any markdown files:
```bash
grep -r "crawl4ai\|Crawl4AI" docs/ --include="*.md"
```

---

## Task 7: Update Tools and Utilities

### `tools/parity/harness.py`

This file may reference Crawl4AI for comparison. Update to:
- Remove Crawl4AI scraper integration
- Keep Firecrawl comparison (that's the parity target)
- Update comments and docstrings

---

## Verification Checklist

After all cleanup, run these verification commands:

```bash
# No crawl4ai imports
grep -r "import crawl4ai" --include="*.py"
grep -r "from crawl4ai" --include="*.py"
# Should return nothing

# No crawl4ai references in source
grep -r "crawl4ai" --include="*.py" web_scraper/
# Should return nothing (or only false positives in comments explaining migration)

# No CRAWL4AI env vars
grep -r "CRAWL4AI_" --include="*.py" --include="*.md" --include="*.mdc"
# Should return nothing

# Dependency removed
grep -i crawl4ai pyproject.toml
# Should return nothing

# Tests still pass
pytest tests/unit/ -v
# Should pass

# CLI works
web-scraper --help
web-scraper map-url --help
web-scraper scrape-url --help
web-scraper crawl-url --help
web-scraper batch-scrape --help
# All should work

# Imports work
python -c "from web_scraper.browser import BrowserManager; print('OK')"
python -c "from web_scraper.map_service import MapService; print('OK')"
python -c "from web_scraper.scrape_service import ScrapeService; print('OK')"
python -c "from web_scraper.crawl_service import CrawlService; print('OK')"
python -c "from web_scraper.batch_service import BatchService; print('OK')"
# All should print OK
```

---

## Commit Message

When complete, commit with:

```
refactor: remove Crawl4AI dependency and all references

- Delete web_scraper/scrapers/crawl4ai*.py files
- Remove crawl4ai from pyproject.toml dependencies
- Replace CRAWL4AI_* env vars with WEB_SCRAPER_*
- Update cursor rules for Playwright-based stack
- Clean up documentation and comments
- Remove obsolete test files and fixtures

This completes the migration to Playwright-based scraping.
The new stack provides:
- BrowserManager for page rendering
- MarkdownConverter for content extraction
- MapService, ScrapeService, CrawlService, BatchService

🤖 Generated with [Claude Code](https://claude.ai/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Completion

After Phase 6, the codebase should be completely free of Crawl4AI. The new Playwright-based stack is:

| Component | File | Purpose |
|-----------|------|---------|
| BrowserManager | `web_scraper/browser.py` | Playwright browser automation |
| MarkdownConverter | `web_scraper/converter.py` | HTML to markdown conversion |
| MapService | `web_scraper/map_service.py` | URL discovery |
| ScrapeService | `web_scraper/scrape_service.py` | Single page scraping |
| CrawlService | `web_scraper/crawl_service.py` | Multi-page crawling |
| BatchService | `web_scraper/batch_service.py` | Parallel batch processing |

Proceed to Phase 7 for E2E testing.

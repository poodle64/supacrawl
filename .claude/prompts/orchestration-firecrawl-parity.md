# Firecrawl Parity Implementation - Orchestration Guide

## Overview

This document orchestrates the complete implementation of Firecrawl-parity features for the web-scraper project. Each phase should be completed in order, with verification before moving to the next.

**Branch:** `refactor/firecrawl-parity-v2`
**Architecture Doc:** `docs/architecture-firecrawl-parity.md`

## Phase Sequence

### Phase 1: Core Infrastructure ✅ COMPLETE
**Issues:** #15, #16
**Prompt:** `.claude/prompts/phase1-core-infrastructure.md`
**Deliverables:**
- `web_scraper/browser.py` - BrowserManager class ✅
- `web_scraper/converter.py` - MarkdownConverter class ✅
- `tests/unit/test_browser.py` ✅ (7 tests)
- `tests/unit/test_converter.py` ✅ (16 tests)

**Verification Results:**
- All 23 unit tests passed
- No crawl4ai imports
- No CRAWL4AI_* env vars
- Imports work correctly

---

### Phase 2: Map Command ✅ COMPLETE
**Issues:** #4, #5, #6, #7, #8, #9, #10, #11, #12, #14
**Prompt:** `.claude/prompts/phase2-map-command.md`
**Deliverables:**
- `web_scraper/map_service.py` - MapService class ✅
- `web_scraper/models.py` - MapLink, MapResult models ✅
- `web_scraper/cli.py` - `map-url` command ✅
- `tests/unit/test_map_service.py` ✅ (9 tests)

**Verification Results:**
- All 9 unit tests passed
- CLI command works: `web-scraper map-url https://example.com --limit 5`
- No crawl4ai imports

---

### Phase 3: Scrape Command ✅ COMPLETE
**Issues:** #17, #18
**Prompt:** `.claude/prompts/phase3-scrape-command.md`
**Deliverables:**
- `web_scraper/scrape_service.py` - ScrapeService class ✅
- `web_scraper/models.py` - ScrapeResult, ScrapeData, ScrapeMetadata ✅
- `web_scraper/cli.py` - `scrape-url` command ✅
- `tests/unit/test_scrape_service.py` ✅ (7 tests)

**Verification Results:**
- All 7 unit tests passed
- CLI command works: `web-scraper scrape-url https://example.com`
- No crawl4ai imports

---

### Phase 4: Crawl Command ✅ COMPLETE
**Issues:** #19, #20
**Prompt:** `.claude/prompts/phase4-crawl-command.md`
**Deliverables:**
- `web_scraper/crawl_service.py` - CrawlService class ✅
- `web_scraper/models.py` - CrawlEvent, CrawlResult, CrawlStatus ✅
- `web_scraper/cli.py` - `crawl-url` command ✅
- `tests/unit/test_crawl_service.py` ✅

**Verification Results:**
- CLI command exists: `web-scraper crawl-url --help`
- Imports work correctly
- No crawl4ai imports

---

### Phase 5: Batch Operations ✅ COMPLETE
**Issues:** #21, #22
**Prompt:** `.claude/prompts/phase5-batch-operations.md`
**Deliverables:**
- `web_scraper/batch_service.py` - BatchService class ✅
- `web_scraper/models.py` - BatchEvent, BatchItem, BatchResult ✅
- `web_scraper/cli.py` - `batch-scrape` command ✅
- `tests/unit/test_batch_service.py` ✅

**Verification Results:**
- CLI command exists: `web-scraper batch-scrape --help`
- Imports work correctly
- No crawl4ai imports

---

### Phase 6: Crawl4AI Cleanup ⏳ NEXT
**Prompt:** `.claude/prompts/phase6-crawl4ai-cleanup.md`
**Deliverables:**
- Delete all Crawl4AI source files
- Remove crawl4ai from dependencies
- Update all documentation
- Clean up cursor rules
- Remove obsolete env vars

**Files to Delete:**
- `web_scraper/scrapers/crawl4ai.py`
- `web_scraper/scrapers/crawl4ai_config.py`
- `web_scraper/scrapers/crawl4ai_result.py`
- `tests/e2e/test_crawl4ai_quality.py`
- `docs/40-usage/crawl4ai-quality-best-practices.md`
- `SPA_DELAY_IMPLEMENTATION.md`

**Verification:**
```bash
grep -r "crawl4ai" --include="*.py" web_scraper/
# Should return nothing
```

---

### Phase 7: E2E Testing
**Prompt:** `.claude/prompts/phase7-e2e-testing.md`
**Deliverables:**
- `tests/e2e/test_cli_commands.py` - CLI E2E tests
- `tests/e2e/test_firecrawl_parity.py` - Parity tests
- `tests/e2e/test_pipeline.py` - Integration tests
- `tests/e2e/test_error_handling.py` - Error handling tests
- `tests/e2e/test_resume.py` - Resume/recovery tests

**Verification:**
```bash
pytest tests/e2e/ -v --timeout=120
# All tests should pass
```

---

## Implementation Guidelines

### Code Style
- Use `from __future__ import annotations`
- Type hints on all functions
- Docstrings with Args/Returns
- Named loggers: `LOGGER = logging.getLogger(__name__)`

### No Crawl4AI
- Never import from `crawl4ai`
- Use `WEB_SCRAPER_*` env vars, not `CRAWL4AI_*`
- Use our BrowserManager, not AsyncWebCrawler

### Testing
- Unit tests for each service
- Integration tests against real URLs
- Parity tests comparing to Firecrawl output

### Git Workflow
- Commit after each issue completion
- Use conventional commits: `feat:`, `fix:`, `refactor:`
- Reference issue numbers: `(#15)`

## Progress Tracking

After completing each phase, update the GitHub issues:
```bash
gh issue close 15 --comment "Implemented in [commit hash]"
```

## Troubleshooting

### Playwright not installed
```bash
playwright install chromium
```

### Import errors
```bash
pip install markdownify beautifulsoup4 httpx
```

### Tests failing
Check that you're using the correct env vars (WEB_SCRAPER_*, not CRAWL4AI_*)

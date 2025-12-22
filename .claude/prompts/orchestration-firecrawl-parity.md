# Firecrawl Parity Implementation - Orchestration Guide

## Overview

This document orchestrates the complete implementation of Firecrawl-parity features for the web-scraper project. Each phase should be completed in order, with verification before moving to the next.

**Branch:** `refactor/firecrawl-parity-v2`
**Architecture Doc:** `docs/architecture-firecrawl-parity.md`

## Phase Sequence

### Phase 1: Core Infrastructure
**Issues:** #15, #16
**Prompt:** `.claude/prompts/phase1-core-infrastructure.md`
**Deliverables:**
- `web_scraper/browser.py` - BrowserManager class
- `web_scraper/converter.py` - MarkdownConverter class
- `tests/unit/test_browser.py`
- `tests/unit/test_converter.py`

**Verification:**
```bash
pytest tests/unit/test_browser.py tests/unit/test_converter.py -v
python -c "from web_scraper.browser import BrowserManager; from web_scraper.converter import MarkdownConverter; print('Phase 1 OK')"
```

---

### Phase 2: Map Command
**Issues:** #4, #5, #6, #7, #11, #12, #14
**Deliverables:**
- `web_scraper/services/map.py` - MapService class
- `web_scraper/models/map.py` - MapLink, MapResult models
- Updated CLI in `web_scraper/cli.py`
- `tests/unit/test_map_service.py`

**Key Requirements:**
1. Standalone `map_url(url)` function (no SiteConfig)
2. Multi-hop BFS discovery with depth control
3. Sitemap integration (include/skip/only modes)
4. Title and description extraction
5. Firecrawl-compatible JSON output
6. No Crawl4AI dependency

**Verification:**
```bash
# Test against Firecrawl baseline
web-scraper map https://portfolio.sharesight.com/api --limit 20 --output /tmp/our-map.json
# Should find 14+ URLs including /api/2/* and /api/3/*

# Compare structure
python -c "import json; d=json.load(open('/tmp/our-map.json')); print(f'Found {len(d[\"links\"])} URLs')"
```

---

### Phase 3: Scrape Command
**Issues:** #17, #18
**Deliverables:**
- `web_scraper/services/scrape.py` - ScrapeService class
- `web_scraper/models/scrape.py` - ScrapeResult model
- Updated CLI in `web_scraper/cli.py`
- `tests/unit/test_scrape_service.py`

**Key Requirements:**
1. Standalone `scrape_url(url)` function
2. Returns markdown, html, metadata
3. Uses BrowserManager and MarkdownConverter
4. Firecrawl-compatible JSON output

**Verification:**
```bash
web-scraper scrape https://example.com --format json
# Should return {"success": true, "data": {"markdown": "...", "metadata": {...}}}
```

---

### Phase 4: Crawl Command
**Issues:** #19, #20
**Deliverables:**
- `web_scraper/services/crawl.py` - CrawlService class
- Updated CLI in `web_scraper/cli.py`
- `tests/unit/test_crawl_service.py`

**Key Requirements:**
1. Combines map + scrape into pipeline
2. AsyncGenerator for streaming results
3. Progress reporting
4. Resume capability

**Verification:**
```bash
web-scraper crawl https://example.com --limit 10 --output /tmp/corpus/
# Should create /tmp/corpus/ with markdown files
```

---

### Phase 5: Batch Operations
**Issues:** #21, #22
**Deliverables:**
- `web_scraper/services/batch.py` - BatchService class
- Updated CLI in `web_scraper/cli.py`
- `tests/unit/test_batch_service.py`

**Key Requirements:**
1. Concurrent URL processing
2. Configurable concurrency
3. Per-URL error handling

**Verification:**
```bash
echo -e "https://example.com\nhttps://example.org" > /tmp/urls.txt
web-scraper batch-scrape /tmp/urls.txt --concurrency 2 --output /tmp/batch/
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

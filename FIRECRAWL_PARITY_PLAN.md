# Firecrawl Parity Plan

## CONTEXT

Audit supacrawl against Firecrawl v2 API to ensure drop-in replacement compatibility. Compare CLI commands, service interfaces, and output formats against Firecrawl's documented endpoints (Scrape, Crawl, Map, Search, Extract, Agent, Batch Scrape). Identify gaps and propose additions to achieve full Firecrawl parity.

## HARD CONSTRAINTS

- Minimal, reversible changes: add new features without breaking existing functionality
- No broad refactors: extend existing services rather than rewriting them
- No user interaction required beyond running this prompt
- Preserve existing YAML-based site configuration workflow (supacrawl's primary use case)
- Maintain Playwright-based scraping (local-first, no API key required)

---

## PHASED WORK (with stop points)

### Phase 0: Inventory and Current State

Enumerate the following and produce an Inventory table:

| Firecrawl v2 Endpoint | supacrawl Equivalent | Status | Gap Description |
|-----------------------|---------------------|--------|-----------------|

**Firecrawl v2 Endpoints to audit:**

1. POST /scrape - Single URL scraping with formats (markdown, html, rawHtml, links, screenshot, pdf, json)
2. POST /batch-scrape - Parallel batch scraping with concurrency
3. GET /batch-scrape/{id} - Batch scrape status
4. POST /search - Web search with optional scraping
5. POST /map - URL discovery from sitemap/crawling
6. POST /crawl - Multi-URL crawling with depth/limit
7. GET /crawl/{id} - Crawl status with pagination
8. POST /agent - Autonomous web data gathering
9. GET /agent/{id} - Agent status
10. POST /extract - LLM-powered structured data extraction
11. GET /extract/{id} - Extract status

**supacrawl files to check:**

- `src/supacrawl/cli.py` - CLI commands
- `src/supacrawl/services/scrape.py` - ScrapeService
- `src/supacrawl/services/crawl.py` - CrawlService
- `src/supacrawl/services/map.py` - MapService
- `src/supacrawl/services/batch.py` - BatchService
- `src/supacrawl/services/search.py` - SearchService
- `src/supacrawl/services/extract.py` - ExtractService
- `src/supacrawl/services/agent.py` - AgentService
- `src/supacrawl/models.py` - Data models

**Audit criteria per endpoint:**

- CLI command exists? (command name, options)
- Service method exists? (async method signature)
- Output format matches Firecrawl? (JSON structure, field names)
- All Firecrawl options supported? (formats, actions, timeout, etc.)

**STOP** if inventory table is incomplete or files cannot be read.

---

### Phase 1: Findings and Plan

Based on Phase 0 inventory, produce:

1. **Gap Summary Table:**

   | Priority | Gap | Impact | Effort |
   |----------|-----|--------|--------|

2. **Numbered Implementation Plan:**
   Each item must reference specific files and symbols.

3. **Assumptions:**
   - Supacrawl's Playwright backend can support all Firecrawl features locally
   - Some features (e.g., Actions) may require Playwright-specific implementation
   - Search endpoint may require external search API or be marked as "requires configuration"

4. **Out of Scope:**
   - API server implementation (supacrawl is CLI-only)
   - Credit/token usage endpoints (local tool, no billing)
   - Webhooks (async notification, not needed for CLI)
   - Rate limiting (local tool, self-imposed politeness only)

**STOP** after plan is documented.

---

### Phase 2: Implementation

For each gap identified in Phase 1:

1. **Add missing CLI commands** to `src/supacrawl/cli.py`:
   - Match Firecrawl command names where possible
   - Ensure `--format` options match Firecrawl: markdown, html, rawHtml, links, screenshot, pdf, json
   - Support `--actions` for page interactions

2. **Add missing service methods** with Firecrawl-compatible signatures:
   - Return types must match Firecrawl response structures
   - Include `success: bool`, `data: object`, `error: string` pattern

3. **Add/update models** in `src/supacrawl/models.py`:
   - Match Firecrawl field names (sourceURL, statusCode, metadata, etc.)
   - Support all output formats

4. **Add tests** in `tests/unit/` for each new/modified service.

For each file change, include a rollback note.

---

### Phase 3: Verification

Run these commands:

```bash
conda activate supacrawl
ruff check src/supacrawl
mypy src/supacrawl
pytest -q -m "not e2e"
```

**Expected outcomes:**

- All linting passes
- All type checks pass
- All unit/integration tests pass

**Failure criteria:**

- Any linting errors
- Type check failures
- Test failures
- Breaking changes to existing CLI commands

---

## ACCEPTANCE CRITERIA

- [ ] `supacrawl scrape-url` supports all Firecrawl formats: markdown, html, rawHtml, links, screenshot, pdf, json
- [ ] `supacrawl scrape-url --actions` supports page interactions (click, type, wait, scroll, screenshot)
- [ ] `supacrawl batch-scrape` supports Firecrawl-compatible concurrency and output
- [ ] `supacrawl map-url` output matches Firecrawl map response structure
- [ ] `supacrawl crawl-url` supports all Firecrawl crawl options (limit, depth, include/exclude patterns)
- [ ] `supacrawl search` command exists (may require external API configuration)
- [ ] `supacrawl extract` command exists for LLM-powered extraction (may require Ollama)
- [ ] All services return Firecrawl-compatible JSON structures
- [ ] All unit tests pass
- [ ] All existing functionality preserved

---

## MODEL GUIDANCE

**Model:** Opus

**Justification:** This task requires cross-file analysis comparing external API documentation against multiple service implementations, identifying subtle interface mismatches, and planning coordinated changes across CLI, services, and models. The multi-endpoint audit with compatibility assessment benefits from enhanced reasoning capabilities.

---

## STOP

Do not continue analysis or refactoring beyond this plan.


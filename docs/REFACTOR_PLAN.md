# Crawl4AI Reset Refactor Plan

## Brief Findings Summary

1. **Heavy custom wrapper**: `web_scraper/scrapers/crawl4ai.py` wraps Crawl4AI with extensive custom logic (link discovery workaround, iterative crawling, custom markdown cleaning, heading restoration)
2. **Custom markdown pipeline**: `web_scraper/content/markdown.py` and `web_scraper/content/cleaner.py` implement custom HTML→Markdown conversion and cleaning that duplicates Crawl4AI's built-in markdown generation
3. **Custom content extraction**: `web_scraper/content/extraction.py` implements DOM scoring heuristics that Crawl4AI's `only_main_content` and content filters already handle
4. **Workaround code**: `web_scraper/scrapers/crawl4ai_link_discovery_workaround.py` exists to work around Crawl4AI issue #1176 (should be removed if fixed)
5. **Custom rate limiting**: `web_scraper/rate_limit.py` implements rate limiting that Crawl4AI may handle natively (needs verification)
6. **Custom browser pool**: `web_scraper/browser/pool.py` wraps Crawl4AI browsers, but Crawl4AI may support pooling natively
7. **Custom discovery**: `web_scraper/discovery/` (sitemap, robots) is custom but may be replaceable with Crawl4AI's URL seeding
8. **Stock Crawl4AI usage**: Browser config (`crawl4ai_config.py`), deep crawl strategies (`crawl4ai_deep.py`), and result extraction (`crawl4ai_result.py`) use stock Crawl4AI APIs correctly
9. **Corpus/storage layer**: `web_scraper/corpus/` is project-specific and should remain (snapshot layout, manifest generation, incremental writes)
10. **CLI layer**: `web_scraper/cli.py` is project-specific and should remain (site config management, corpus operations)

---

## Inventory Table

| Area | File(s) | Purpose | "Custom" vs "Crawl4AI stock" vs "Glue" | Risk if removed | Suggested action |
|------|---------|---------|----------------------------------------|------------------|------------------|
| **Crawler** | `web_scraper/scrapers/crawl4ai.py` | Main crawler wrapper with iterative link discovery, markdown cleaning, heading restoration | Custom (heavy wrapper) | High - core crawling logic | Replace with stock Crawl4AI patterns |
| **Crawler** | `web_scraper/scrapers/crawl4ai_config.py` | Browser config, LLM config, markdown generator config | Glue (wraps stock APIs) | Low - configuration only | Keep, simplify |
| **Crawler** | `web_scraper/scrapers/crawl4ai_deep.py` | Deep crawl strategy builders (BFS, BestFirst) | Glue (uses stock APIs) | Low - strategy config | Keep |
| **Crawler** | `web_scraper/scrapers/crawl4ai_result.py` | Transform Crawl4AI results to Page models | Glue (data transformation) | Medium - result mapping | Keep, simplify |
| **Crawler** | `web_scraper/scrapers/crawl4ai_retry.py` | Retry logic helpers | Custom (retry wrapper) | Low - can use tenacity | Replace with tenacity or stock retry |
| **Crawler** | `web_scraper/scrapers/crawl4ai_link_discovery_workaround.py` | Workaround for Crawl4AI issue #1176 | Custom (temporary fix) | Low - documented workaround | Delete if Crawl4AI fixed |
| **Fetch** | `web_scraper/browser/pool.py` | Browser instance pooling | Custom (pool wrapper) | Medium - performance optimization | Verify if Crawl4AI supports pooling natively, else keep |
| **Fetch** | `web_scraper/network/proxy.py` | Proxy rotation | Custom (proxy management) | Low - Crawl4AI has ProxyConfig | Replace with Crawl4AI ProxyConfig |
| **Fetch** | `web_scraper/rate_limit.py` | Rate limiting and politeness | Custom (rate limiter) | Medium - politeness controls | Verify if Crawl4AI handles this, else keep as glue |
| **Parsing** | `web_scraper/content/markdown.py` | HTML→Markdown conversion, sanitization | Custom (duplicates Crawl4AI) | High - used for fallback | Delete, use Crawl4AI markdown only |
| **Parsing** | `web_scraper/content/cleaner.py` | Markdown cleaning (trackers, nav, stop markers) | Custom (post-processing) | Medium - quality improvement | Keep as optional post-process, make configurable |
| **Parsing** | `web_scraper/content/extraction.py` | DOM scoring for main content | Custom (duplicates Crawl4AI) | Low - fallback only | Delete, use Crawl4AI `only_main_content` |
| **Parsing** | `web_scraper/content/language.py` | Language detection | Custom (lang detection) | Low - metadata only | Keep if needed for corpus metadata |
| **Parsing** | `web_scraper/content/fixes/` | Markdown fix plugins (missing link text, etc.) | Custom (quality fixes) | Low - optional improvements | Keep as optional post-process |
| **Markdown** | `web_scraper/content/markdown.py` (sanitize_markdown) | Markdown sanitization (nav blocks, link density) | Custom (post-processing) | Medium - quality improvement | Keep as optional post-process |
| **Markdown** | `web_scraper/content/cleaner.py` (clean_markdown) | Pattern-based cleaning (trackers, stop markers) | Custom (post-processing) | Medium - quality improvement | Keep as optional post-process |
| **Storage** | `web_scraper/corpus/writer.py` | Snapshot writer, manifest generation | Custom (project-specific) | High - core output format | Keep |
| **Storage** | `web_scraper/corpus/layout.py` | Snapshot directory structure | Custom (project-specific) | High - core output format | Keep |
| **Storage** | `web_scraper/corpus/state.py` | Crawl state/resumption | Custom (project-specific) | Medium - resume feature | Keep |
| **Storage** | `web_scraper/corpus/compress.py` | Snapshot compression | Custom (project-specific) | Low - utility | Keep |
| **CLI/API** | `web_scraper/cli.py` | CLI commands (list-sites, crawl, chunk) | Custom (project-specific) | High - user interface | Keep |
| **CLI/API** | `web_scraper/sites/loader.py` | Site config loading | Custom (project-specific) | High - configuration | Keep |
| **CLI/API** | `web_scraper/config.py` | Default paths, directories | Custom (project-specific) | Low - configuration | Keep |
| **Discovery** | `web_scraper/discovery/sitemap.py` | Sitemap discovery/parsing | Custom (standalone) | Medium - URL seeding | Replace with Crawl4AI URL seeding if supported |
| **Discovery** | `web_scraper/discovery/robots.py` | robots.txt parsing | Custom (standalone) | Medium - politeness | Keep if Crawl4AI doesn't handle robots.txt |
| **Tests** | `tests/test_*.py` | Test suite | Custom (project-specific) | High - quality assurance | Keep, update for refactor |
| **Config** | `web_scraper/models.py` | Pydantic models (SiteConfig, Page, etc.) | Custom (project-specific) | High - data contracts | Keep |
| **Prep** | `web_scraper/prep/chunker.py` | LLM chunking (JSONL output) | Custom (project-specific) | Medium - downstream processing | Keep |
| **Prep** | `web_scraper/prep/ollama_client.py` | Ollama client for chunking | Custom (project-specific) | Low - optional feature | Keep |

---

## Data Flow Diagram

```
CLI (cli.py)
  ↓
Site Config (sites/loader.py) → SiteConfig model
  ↓
Crawl4AIScraper.crawl() (scrapers/crawl4ai.py)
  ├─→ Browser Pool (browser/pool.py) [optional]
  ├─→ Rate Limiter (rate_limit.py) [optional]
  ├─→ Proxy Rotator (network/proxy.py) [optional]
  ├─→ Sitemap Discovery (discovery/sitemap.py) [optional]
  ├─→ Robots.txt (discovery/robots.py) [optional]
  ↓
AsyncWebCrawler.arun() [Crawl4AI SDK]
  ├─→ BrowserConfig (scrapers/crawl4ai_config.py)
  ├─→ CrawlerRunConfig (scrapers/crawl4ai_config.py)
  ├─→ DeepCrawlStrategy (scrapers/crawl4ai_deep.py)
  ├─→ MarkdownGenerator (scrapers/crawl4ai_config.py)
  └─→ LLMExtractionStrategy (scrapers/crawl4ai_config.py)
  ↓
Crawl4AI Result (Crawl4AI SDK)
  ↓
extract_pages_from_result() (scrapers/crawl4ai_result.py)
  ├─→ extract_markdown() → Uses Crawl4AI result.markdown
  ├─→ extract_html() → Uses Crawl4AI result.cleaned_html
  ├─→ extract_title() → Uses Crawl4AI result.title/metadata
  ├─→ html_to_markdown() [FALLBACK - custom] (content/markdown.py)
  ├─→ extract_main_content() [FALLBACK - custom] (content/extraction.py)
  ├─→ sanitize_markdown() [POST-PROCESS] (content/markdown.py)
  ├─→ apply_fixes() [POST-PROCESS] (content/fixes/)
  └─→ clean_markdown() [POST-PROCESS] (content/cleaner.py)
  ↓
Page model (models.py)
  ↓
IncrementalSnapshotWriter (corpus/writer.py)
  ├─→ Write pages to filesystem (corpora/{site_id}/{snapshot_id}/)
  ├─→ Generate manifest.json
  └─→ Save crawl state (corpus/state.py)
  ↓
chunk_snapshot() [OPTIONAL] (prep/chunker.py)
  └─→ JSONL output for LLM
```

---

## Current Markdown Pipeline Critique

### Strengths
- **Deterministic output**: Snapshot-based layout ensures reproducible results
- **Configurable cleaning**: `CleaningConfig` allows site-specific rules
- **Fix plugins**: Extensible markdown fix system for quality improvements
- **Multiple formats**: Supports markdown, HTML, text, JSON output

### Weaknesses
1. **Duplication**: Custom HTML→Markdown conversion (`html_to_markdown`) duplicates Crawl4AI's markdown generation
2. **Fallback complexity**: Multiple fallback paths (Crawl4AI markdown → custom HTML extraction → custom markdown) add complexity
3. **Post-processing overhead**: Multiple cleaning passes (sanitize → fixes → clean) may be redundant
4. **Non-deterministic cleaning**: Pattern-based cleaning may produce different results if patterns change
5. **Heading restoration hack**: Logic to restore headings removed by cleaning is fragile

### Recommendations
- **Use Crawl4AI markdown only**: Remove custom HTML→Markdown conversion, rely on Crawl4AI's `DefaultMarkdownGenerator`
- **Simplify post-processing**: Combine cleaning steps into single configurable pipeline
- **Make cleaning optional**: Allow disabling post-processing for raw Crawl4AI output
- **Improve determinism**: Use stable, versioned cleaning rules

---

## 3-PR Plan

### PR1: Safe Deletions and Wiring Changes (No Behaviour Change)

**Goal**: Remove dead code, workarounds, and simplify wiring without changing crawl behaviour.

**Files to edit/remove/add**:

**Delete**:
- `web_scraper/scrapers/crawl4ai_link_discovery_workaround.py` (workaround module)
- `web_scraper/scrapers/REMOVE_WORKAROUND.md` (documentation)
- `web_scraper/content/extraction.py` (DOM scoring - unused fallback)

**Edit**:
- `web_scraper/scrapers/crawl4ai.py`:
  - Remove link discovery workaround import and logic
  - Remove iterative crawling loop (lines 186-361)
  - Simplify to single entrypoint loop
  - Remove heading restoration logic (lines 294-318)
- `web_scraper/scrapers/crawl4ai_result.py`:
  - Remove `html_to_markdown()` fallback (lines 187-191)
  - Remove `extract_main_content()` fallback (line 189)
  - Simplify `_extract_markdown()` to use Crawl4AI markdown only
- `web_scraper/models.py`:
  - Remove `LinkDiscoveryWorkaroundConfigModel` class
  - Remove `link_discovery_workaround` field from `SiteConfig`
- `web_scraper/cli.py`:
  - Remove workaround status display in `show-site` command
- `sites/*.yaml`:
  - Remove `link_discovery_workaround:` sections from all site configs

**What changes**:
- Removes workaround code for Crawl4AI issue #1176
- Removes unused fallback HTML extraction
- Simplifies crawler to use Crawl4AI deep crawl strategies directly
- No behaviour change: assumes Crawl4AI deep crawl works correctly

**How we verify**:
- Run existing test suite: `pytest -q`
- Test crawl on sample site: `web-scraper crawl example-site --verbose`
- Verify deep crawl follows links correctly
- Verify markdown output quality unchanged
- Check that site configs load without `link_discovery_workaround` field

**Acceptance criteria**:
- ✅ All tests pass
- ✅ Sample crawl produces same or better results
- ✅ No workaround code remains
- ✅ Site configs load successfully

---

### PR2: Replace Custom Logic with Crawl4AI Primitives

**Goal**: Replace custom implementations with stock Crawl4AI features where possible.

**Files to edit/remove/add**:

**Delete**:
- `web_scraper/content/markdown.py` (custom HTML→Markdown - replaced by Crawl4AI)
- `web_scraper/network/proxy.py` (custom proxy rotation - use Crawl4AI ProxyConfig)

**Edit**:
- `web_scraper/scrapers/crawl4ai_config.py`:
  - Use Crawl4AI `ProxyConfig` directly instead of custom proxy rotator
  - Simplify markdown generator config (remove custom content filter logic if Crawl4AI handles it)
- `web_scraper/scrapers/crawl4ai.py`:
  - Remove custom proxy rotator integration
  - Use Crawl4AI's native proxy support via `BrowserConfig.proxy_config`
  - Remove custom rate limiter integration (if Crawl4AI handles rate limiting)
  - Simplify browser pool usage (verify if Crawl4AI supports pooling natively)
- `web_scraper/scrapers/crawl4ai_result.py`:
  - Remove all fallback HTML extraction paths
  - Use `result.markdown` directly (no custom conversion)
  - Use `result.cleaned_html` directly (no custom extraction)
- `web_scraper/browser/pool.py`:
  - Verify if Crawl4AI supports browser pooling natively
  - If yes, remove custom pool wrapper
  - If no, simplify to minimal wrapper
- `web_scraper/rate_limit.py`:
  - Verify if Crawl4AI handles rate limiting natively
  - If yes, remove custom rate limiter
  - If no, keep as glue layer for politeness controls

**What changes**:
- Removes custom HTML→Markdown conversion (uses Crawl4AI markdown only)
- Replaces custom proxy rotation with Crawl4AI `ProxyConfig`
- Simplifies result extraction to use Crawl4AI outputs directly
- Removes redundant content extraction (uses Crawl4AI `only_main_content`)

**How we verify**:
- Run test suite: `pytest -q`
- Test crawl with proxy: `web-scraper crawl example-site --proxy http://proxy:8080`
- Test crawl with rate limiting: `web-scraper crawl example-site --rps 1.0`
- Compare markdown output quality before/after
- Verify no regression in content extraction

**Acceptance criteria**:
- ✅ All tests pass
- ✅ Markdown output quality matches or exceeds previous
- ✅ Proxy rotation works via Crawl4AI
- ✅ Rate limiting works (if kept) or is removed if Crawl4AI handles it
- ✅ No custom HTML→Markdown conversion remains

---

### PR3: Firecrawl Parity Features for Markdown Quality

**Goal**: Achieve Firecrawl-quality deterministic Markdown output using Crawl4AI primitives.

**Files to edit/remove/add**:

**Edit**:
- `web_scraper/scrapers/crawl4ai_config.py`:
  - Tune `DefaultMarkdownGenerator` options for Firecrawl-quality output
  - Configure content filters (PruningContentFilter, BM25ContentFilter, LLMContentFilter) optimally
  - Set markdown generator options (body_width, ignore_links, ignore_images, single_line_break)
- `web_scraper/content/cleaner.py`:
  - Make cleaning optional (config flag)
  - Improve determinism (version cleaning rules, stable patterns)
  - Add Firecrawl-style cleaning patterns if needed
- `web_scraper/scrapers/crawl4ai.py`:
  - Configure `CrawlerRunConfig` for optimal markdown quality:
    - `magic=True` (already set)
    - `scan_full_page=True` (already set)
    - `wait_until` timing
    - `js_code` for dynamic content expansion
  - Remove or simplify post-processing if Crawl4AI markdown is sufficient
- `web_scraper/models.py`:
  - Add `CleaningConfig.enabled` flag to disable post-processing
  - Add markdown quality presets (firecrawl, minimal, aggressive)

**What changes**:
- Optimizes Crawl4AI markdown generation for Firecrawl-quality output
- Makes post-processing optional/configurable
- Improves determinism of cleaning rules
- Adds quality presets for different use cases

**How we verify**:
- Compare markdown output with Firecrawl on same URLs
- Test with sample sites: `web-scraper crawl sharesight-api --formats markdown`
- Verify deterministic output (same URL → same markdown)
- Check markdown quality metrics (heading preservation, table formatting, link accuracy)
- Test with/without post-processing to measure impact

**Acceptance criteria**:
- ✅ Markdown output quality matches or exceeds Firecrawl
- ✅ Deterministic output (same URL → same markdown)
- ✅ Post-processing is optional and configurable
- ✅ Quality presets work correctly
- ✅ No regression in content extraction

---

## Crawl4AI Examples Mapping

### Findings Summary

1. **Firecrawl comparison**: `crawlai_vs_firecrawl.py` shows simple `AsyncWebCrawler.arun()` usage - we should simplify to this pattern
2. **Website-to-API**: `website-to-api/` shows LLM extraction patterns we already use correctly
3. **Deep crawl**: `deepcrawl_example.py` shows deep crawl strategies we already use correctly
4. **Markdown generation**: Crawl4AI examples show `DefaultMarkdownGenerator` usage we already implement
5. **URL seeding**: Need to verify if Crawl4AI supports sitemap-based URL seeding natively
6. **Rate limiting**: No clear examples of native rate limiting in Crawl4AI
7. **Browser pooling**: No clear examples of native browser pooling in Crawl4AI
8. **Proxy rotation**: Examples show `ProxyConfig` usage we should adopt
9. **Content filters**: Examples show `PruningContentFilter`, `BM25ContentFilter`, `LLMContentFilter` we already use
10. **Deterministic output**: No examples of deterministic markdown generation - we need to implement this ourselves

### Detailed Mapping

| Need | Crawl4AI Example(s) | How it translates | Gaps |
|------|---------------------|-------------------|------|
| **Simple crawling** | `crawlai_vs_firecrawl.py`, `hello_world.py` | Use `AsyncWebCrawler.arun()` directly, no custom wrapper | None - we over-engineer this |
| **Firecrawl comparison** | `crawlai_vs_firecrawl.py` | Shows simple `arun()` call with `result.markdown` - we should use this pattern | None - we already have this, just need to simplify |
| **Deep crawling** | `deepcrawl_example.py` | Uses `BFSDeepCrawlStrategy`, `BestFirstCrawlingStrategy` - we already use these | None - we use this correctly |
| **Markdown generation** | `markdown/` examples | Shows `DefaultMarkdownGenerator` with content filters - we already use this | None - we use this correctly |
| **LLM extraction** | `llm_extraction_*.py`, `website-to-api/` | Shows `LLMExtractionStrategy` usage - we already use this | None - we use this correctly |
| **Content filtering** | Various examples | Shows `PruningContentFilter`, `BM25ContentFilter`, `LLMContentFilter` - we already use these | None - we use this correctly |
| **Proxy support** | `proxy_rotation_demo.py`, `nst_proxy/` | Shows `ProxyConfig` usage - we should replace custom proxy rotator | None - Crawl4AI has this |
| **Browser config** | `browser_optimization_example.py`, `stealth_mode_example.py` | Shows `BrowserConfig` usage - we already use this | None - we use this correctly |
| **URL seeding** | `url_seeder/` | Need to check if this supports sitemap-based seeding | **Gap**: May need to keep custom sitemap discovery |
| **Rate limiting** | No clear examples | Need to verify if Crawl4AI handles this natively | **Gap**: May need to keep custom rate limiter |
| **Browser pooling** | No clear examples | Need to verify if Crawl4AI supports pooling | **Gap**: May need to keep custom browser pool |
| **Deterministic markdown** | No examples | Need to implement deterministic cleaning ourselves | **Gap**: We need to implement this |
| **Sitemap discovery** | No examples | Need to keep custom sitemap discovery or use URL seeding | **Gap**: May need to keep custom discovery |
| **Robots.txt** | No examples | Need to keep custom robots.txt parsing | **Gap**: May need to keep custom robots.txt |

### Translation Examples

**Current (Custom Wrapper)**:
```python
# web_scraper/scrapers/crawl4ai.py
async def _crawl_entrypoint(self, crawler, entrypoint, config, correlation_id):
    # ... complex config building ...
    result = await crawler.arun(url=entrypoint, config=run_config)
    pages = extract_pages_from_result(result, entrypoint, config, self.provider_name)
    # ... custom cleaning, heading restoration ...
    return pages
```

**Target (Stock Crawl4AI)**:
```python
# web_scraper/scrapers/crawl4ai.py
async def _crawl_entrypoint(self, crawler, entrypoint, config, correlation_id):
    run_config = CrawlerRunConfig(
        deep_crawl_strategy=build_deep_crawl_strategy(config, filter_chain),
        markdown_generator=build_markdown_generator(llm_config, correlation_id, config),
        # ... minimal config ...
    )
    result = await crawler.arun(url=entrypoint, config=run_config)
    # Use Crawl4AI markdown directly, minimal post-processing
    return extract_pages_from_result(result, entrypoint, config, self.provider_name)
```

**Current (Custom HTML→Markdown)**:
```python
# web_scraper/content/markdown.py
def html_to_markdown(html: str) -> str:
    # Custom BeautifulSoup-based conversion
    ...
```

**Target (Crawl4AI Markdown)**:
```python
# web_scraper/scrapers/crawl4ai_result.py
def _extract_markdown(crawl_result, config, raw_html):
    # Use Crawl4AI markdown directly
    markdown_obj = getattr(crawl_result, "markdown", None)
    if markdown_obj:
        return str(markdown_obj.fit_markdown if config.only_main_content else markdown_obj.raw_markdown)
    return ""
```

---

## Next Steps

1. **Verify Crawl4AI capabilities**: Test if Crawl4AI handles rate limiting, browser pooling, and URL seeding natively
2. **Test workaround removal**: Verify that removing link discovery workaround doesn't break deep crawling
3. **Benchmark markdown quality**: Compare current output with Firecrawl on sample sites
4. **Implement PR1**: Start with safe deletions and wiring changes
5. **Measure impact**: After each PR, measure crawl quality, performance, and code complexity

---

**Document Status**: Planning complete, ready for implementation review.

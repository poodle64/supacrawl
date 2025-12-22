# Implementation Plan: Firecrawl-Parity Map Command

## Goal

Build a `map` command that produces Firecrawl-equivalent output: given a URL, return all discoverable URLs on that website with optional title/description metadata.

## Firecrawl Map API Reference

**Input:**
- `url` (required): Starting URL
- `limit`: Max URLs to return (default varies)
- `search`: Filter URLs by search term (returns ordered by relevance)
- `sitemap`: "include" | "skip" | "only"
- `includeSubdomains`: Include subdomains in results
- `ignoreQueryParameters`: Dedupe URLs ignoring query strings
- `location`: Country/language settings for geo-targeting

**Output:**
```json
{
  "success": true,
  "links": [
    {
      "url": "https://example.com/page",
      "title": "Page Title",
      "description": "Meta description"
    }
  ]
}
```

## Current State Analysis

Our current `map.py` has:
- ✅ Sitemap discovery and parsing
- ✅ robots.txt respect
- ✅ Include/exclude pattern filtering
- ✅ HTML link extraction (httpx)
- ✅ Browser link extraction (Playwright)
- ❌ Only one-hop discovery (not multi-hop crawl)
- ❌ No title/description extraction
- ❌ No search/relevance filtering
- ❌ No subdomain handling
- ❌ No query parameter deduplication
- ❌ Tied to SiteConfig (not standalone URL input)

## Architecture Decision: Remove Crawl4AI

The map command should use:
1. **httpx** - Fast HTTP for sitemap fetching, robots.txt, static HTML
2. **Playwright** - Browser rendering for JS-heavy sites
3. **BeautifulSoup** - HTML parsing and link extraction

No Crawl4AI dependency. Clean, simple, ownable.

## Implementation Steps

### Phase 1: Core Map Functionality (Issues #1-4)

#### Issue #1: Standalone URL-based map function
**Remove SiteConfig dependency, accept raw URL input**

- New function signature: `map_url(url: str, **options) -> MapResult`
- Accept URL directly, not SiteConfig
- Return structured result with `links: list[MapLink]`
- MapLink model: `url`, `title`, `description`, `source`

#### Issue #2: Multi-hop browser-based link discovery
**Crawl discovered links to find more links**

- Add `max_depth` parameter (default 2-3)
- BFS/queue-based crawl from entrypoint
- Respect same-domain/subdomain rules
- Track visited URLs to avoid cycles
- Use Playwright for JavaScript-rendered pages

#### Issue #3: Title and description extraction
**Extract metadata during link discovery**

- Parse `<title>` tag
- Parse `<meta name="description">`
- Store in MapLink result
- Efficient: extract during page fetch, not separate requests

#### Issue #4: Sitemap integration
**Use sitemap as primary URL source when available**

- `sitemap` param: "include" | "skip" | "only"
- "include" (default): sitemap + crawl
- "skip": crawl only
- "only": sitemap only (fast mode)
- Parse sitemap.xml, sitemap index files

### Phase 2: Filtering and Deduplication (Issues #5-7)

#### Issue #5: Search/relevance filtering
**Filter URLs by search term**

- `search` parameter filters results
- Simple: substring match on URL, title, description
- Advanced: TF-IDF or BM25 ranking
- Return ordered by relevance score

#### Issue #6: Query parameter deduplication
**Dedupe URLs that differ only by query params**

- `ignoreQueryParameters` flag
- Normalise URLs before deduplication
- Keep first occurrence (or canonical if available)

#### Issue #7: Subdomain handling
**Include or exclude subdomains**

- `includeSubdomains` flag
- Domain extraction and comparison
- Apply to all discovery sources

### Phase 3: CLI and Output (Issues #8-9)

#### Issue #8: CLI command implementation
**`web-scraper map URL` command**

```bash
web-scraper map https://example.com \
  --limit 100 \
  --search "api" \
  --sitemap include \
  --include-subdomains \
  --output map.json
```

- Standalone command (no site config required)
- JSON output to stdout or file
- Progress reporting for multi-hop crawl

#### Issue #9: Firecrawl-compatible output format
**Match Firecrawl's JSON structure**

```json
{
  "success": true,
  "links": [
    {"url": "...", "title": "...", "description": "..."}
  ]
}
```

- Optional: Add our own metadata (source, depth)
- Ensure output can be piped to scrape command

### Phase 4: Performance and Polish (Issues #10-11)

#### Issue #10: Concurrent crawling
**Parallel page fetching for speed**

- asyncio.gather for concurrent requests
- Configurable concurrency limit
- Rate limiting per domain
- Connection pooling

#### Issue #11: Caching layer
**Cache discovered URLs for resume/speed**

- File-based cache keyed by URL + options
- TTL-based expiration
- Optional cache bypass flag

## Files to Modify/Create

### New Files
- `web_scraper/map_v2.py` - New map implementation
- `web_scraper/models/map.py` - MapLink, MapResult models

### Modified Files
- `web_scraper/cli.py` - Add new map command
- `pyproject.toml` - Add any new dependencies

### Files to Eventually Remove (after migration)
- `web_scraper/map.py` - Old implementation
- `web_scraper/map_io.py` - Old IO utilities
- Crawl4AI-specific code

## Success Criteria

1. `web-scraper map https://portfolio.sharesight.com/api` discovers all 14+ URLs that Firecrawl finds
2. Output includes title/description for each URL
3. Search filtering works: `--search api` returns relevant URLs
4. Performance: Complete map in <30 seconds for typical sites
5. No Crawl4AI dependency in map codepath

## Testing Strategy

1. **Unit tests**: URL normalisation, deduplication, filtering
2. **Integration tests**: Map known sites, compare to Firecrawl baseline
3. **Parity tests**: Run both Firecrawl and our map, diff results

## Order of Implementation

1. Issue #1 (standalone function) - Foundation
2. Issue #4 (sitemap) - Quick wins for many sites
3. Issue #2 (multi-hop) - Core discovery capability
4. Issue #3 (metadata) - Complete the output
5. Issue #8 (CLI) - Make it usable
6. Issue #9 (output format) - Firecrawl compatibility
7. Issues #5-7 (filtering) - Polish
8. Issues #10-11 (performance) - Optimisation

# Architecture: Firecrawl-Parity Web Scraper

## Executive Summary

This document defines the complete pathway to build a production-quality web scraper that can serve as a drop-in replacement for Firecrawl, with zero dependency on Crawl4AI.

## Firecrawl API Surface (v2)

### Core Endpoints (Must Have)

| Endpoint | Purpose | Priority |
|----------|---------|----------|
| `POST /scrape` | Single URL → markdown/html/json | P0 |
| `POST /map` | URL → list of all site URLs | P0 |
| `POST /crawl` | URL → async job scraping entire site | P0 |
| `GET /crawl/{id}` | Get crawl status/results | P0 |
| `POST /batch-scrape` | List of URLs → scraped content | P1 |
| `GET /batch-scrape/{id}` | Get batch status/results | P1 |

### Extended Endpoints (Nice to Have)

| Endpoint | Purpose | Priority |
|----------|---------|----------|
| `POST /search` | Web search + scrape results | P2 |
| `POST /extract` | LLM-powered structured extraction | P2 |
| `POST /agent` | Agentic browsing tasks | P3 |

## Technology Stack (No Crawl4AI)

### Core Dependencies

```
httpx          - Async HTTP client (fast, static pages)
playwright     - Browser automation (JavaScript rendering)
beautifulsoup4 - HTML parsing
markdownify    - HTML → Markdown conversion
pydantic       - Data models and validation
click          - CLI framework
```

### What Each Replaces from Crawl4AI

| Crawl4AI Feature | Our Replacement |
|------------------|-----------------|
| AsyncWebCrawler | Playwright + httpx |
| BrowserConfig | Our own config (env vars + models) |
| CrawlerRunConfig | Function parameters |
| DefaultMarkdownGenerator | markdownify + BeautifulSoup |
| PruningContentFilter | BeautifulSoup selectors |
| LLMContentFilter | Optional Ollama integration |
| CacheMode | File-based cache layer |
| deep_crawl_strategy | BFS queue + visited set |

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                         CLI Layer                            │
│  web-scraper map|scrape|crawl|batch-scrape URL [options]    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      API Layer (Future)                      │
│  FastAPI server with Firecrawl-compatible endpoints         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Service Layer                            │
│  MapService | ScrapeService | CrawlService | BatchService   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Core Layer                               │
│  Browser | Fetcher | Parser | Converter | Cache             │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Browser Manager (`web_scraper/browser.py`)

Manages Playwright browser lifecycle and page operations.

```python
class BrowserManager:
    """Manages browser instances for JavaScript rendering."""

    async def fetch_page(
        self,
        url: str,
        wait_for_spa: bool = True,
        timeout_ms: int = 30000,
    ) -> PageContent:
        """Fetch page with browser rendering."""

    async def extract_links(self, url: str) -> list[str]:
        """Extract all links from rendered page."""

    async def batch_fetch(
        self,
        urls: list[str],
        concurrency: int = 5,
    ) -> list[PageContent]:
        """Fetch multiple pages concurrently."""
```

**Key Features:**
- Fresh context per URL (fixes SPA routing issues)
- SPA content stability detection
- Configurable timeouts and delays
- Connection pooling for performance

### 2. HTTP Fetcher (`web_scraper/fetcher.py`)

Fast HTTP client for static pages and sitemaps.

```python
class Fetcher:
    """Fast HTTP client for static content."""

    async def fetch(self, url: str) -> FetchResult:
        """Fetch URL with httpx."""

    async def fetch_sitemap(self, url: str) -> list[SitemapEntry]:
        """Fetch and parse sitemap.xml."""

    async def fetch_robots(self, url: str) -> RobotsConfig:
        """Fetch and parse robots.txt."""
```

### 3. HTML Parser (`web_scraper/parser.py`)

Extracts content and metadata from HTML.

```python
class HTMLParser:
    """Parse HTML and extract content."""

    def extract_main_content(self, html: str) -> str:
        """Extract main content area."""

    def extract_links(self, html: str, base_url: str) -> list[str]:
        """Extract and resolve all links."""

    def extract_metadata(self, html: str) -> PageMetadata:
        """Extract title, description, og tags."""
```

### 4. Markdown Converter (`web_scraper/converter.py`)

Converts HTML to clean markdown.

```python
class MarkdownConverter:
    """Convert HTML to Firecrawl-compatible markdown."""

    def convert(
        self,
        html: str,
        only_main_content: bool = True,
        remove_boilerplate: bool = True,
    ) -> str:
        """Convert HTML to markdown."""
```

**Firecrawl Parity Checklist:**
- [ ] ATX-style headings (`#`, `##`, etc.)
- [ ] Dash bullets for lists
- [ ] Preserved code blocks with language hints
- [ ] Tables converted properly
- [ ] Links preserved with text
- [ ] Images with alt text
- [ ] Minimal whitespace

### 5. Cache Layer (`web_scraper/cache.py`)

File-based caching for performance.

```python
class Cache:
    """File-based cache for fetched pages."""

    def get(self, url: str) -> CacheEntry | None:
        """Get cached content if fresh."""

    def set(self, url: str, content: PageContent, ttl: int):
        """Cache content with TTL."""

    def invalidate(self, url: str):
        """Remove from cache."""
```

## Service Layer

### MapService (`web_scraper/services/map.py`)

```python
class MapService:
    """Discover all URLs on a website."""

    async def map(
        self,
        url: str,
        limit: int = 200,
        max_depth: int = 3,
        sitemap: Literal["include", "skip", "only"] = "include",
        include_subdomains: bool = False,
        search: str | None = None,
    ) -> MapResult:
        """Map a website and return discovered URLs."""
```

### ScrapeService (`web_scraper/services/scrape.py`)

```python
class ScrapeService:
    """Scrape a single URL."""

    async def scrape(
        self,
        url: str,
        formats: list[str] = ["markdown"],
        only_main_content: bool = True,
        wait_for: int = 0,
        timeout: int = 30000,
    ) -> ScrapeResult:
        """Scrape a URL and return content."""
```

### CrawlService (`web_scraper/services/crawl.py`)

```python
class CrawlService:
    """Crawl entire websites."""

    async def crawl(
        self,
        url: str,
        limit: int = 100,
        max_depth: int = 3,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> AsyncGenerator[CrawlEvent, None]:
        """Crawl a website, yielding events as pages complete."""
```

### BatchService (`web_scraper/services/batch.py`)

```python
class BatchService:
    """Batch scrape multiple URLs."""

    async def batch_scrape(
        self,
        urls: list[str],
        concurrency: int = 5,
        **scrape_options,
    ) -> AsyncGenerator[BatchEvent, None]:
        """Scrape multiple URLs concurrently."""
```

## Data Models

### Core Models (`web_scraper/models/`)

```python
# map.py
class MapLink(BaseModel):
    url: str
    title: str | None = None
    description: str | None = None

class MapResult(BaseModel):
    success: bool
    links: list[MapLink]

# scrape.py
class ScrapeResult(BaseModel):
    success: bool
    markdown: str | None = None
    html: str | None = None
    metadata: dict[str, Any]

# crawl.py
class CrawlResult(BaseModel):
    success: bool
    status: Literal["scraping", "completed", "failed", "cancelled"]
    completed: int
    total: int
    data: list[ScrapeResult]
```

## CLI Commands

```bash
# Map - discover URLs
web-scraper map https://example.com --limit 100 --output urls.json

# Scrape - single URL
web-scraper scrape https://example.com/page --format markdown

# Crawl - entire site
web-scraper crawl https://example.com --limit 50 --output corpus/

# Batch - multiple URLs
web-scraper batch-scrape urls.txt --concurrency 10 --output results/
```

## API Server (Future)

FastAPI server with Firecrawl-compatible endpoints:

```python
# POST /v1/scrape
@app.post("/v1/scrape")
async def scrape(request: ScrapeRequest) -> ScrapeResponse:
    result = await scrape_service.scrape(request.url, **request.options)
    return ScrapeResponse(success=True, data=result)

# POST /v1/map
@app.post("/v1/map")
async def map(request: MapRequest) -> MapResponse:
    result = await map_service.map(request.url, **request.options)
    return MapResponse(success=True, links=result.links)
```

## Implementation Phases

### Phase 1: Core Infrastructure (Issues #4, #14)
**Goal:** Foundation without Crawl4AI

- [ ] Browser manager with Playwright
- [ ] HTTP fetcher with httpx
- [ ] HTML parser with BeautifulSoup
- [ ] Markdown converter with markdownify
- [ ] Remove all CRAWL4AI_* env vars, use WEB_SCRAPER_*

### Phase 2: Map Command (Issues #5-13)
**Goal:** Firecrawl-parity map

- [ ] Multi-hop BFS discovery
- [ ] Sitemap integration
- [ ] Metadata extraction
- [ ] CLI command
- [ ] Output format parity

### Phase 3: Scrape Command (New Issues)
**Goal:** Single URL scraping

- [ ] Standalone scrape function
- [ ] Output formats (markdown, html, json)
- [ ] CLI command
- [ ] Firecrawl output parity

### Phase 4: Crawl Command (New Issues)
**Goal:** Full site crawling

- [ ] Map + Scrape pipeline
- [ ] Async job management
- [ ] Progress reporting
- [ ] Resume capability

### Phase 5: Batch Operations (New Issues)
**Goal:** Parallel scraping

- [ ] Concurrent URL processing
- [ ] Rate limiting
- [ ] Error handling per URL

### Phase 6: API Server (Future)
**Goal:** HTTP API

- [ ] FastAPI server
- [ ] Firecrawl-compatible endpoints
- [ ] Authentication
- [ ] Rate limiting

## Quality Gates

### Functional Parity Tests

For each command, run against the same URLs with both Firecrawl and our tool:

```bash
# Compare map results
firecrawl map https://example.com > firecrawl-map.json
web-scraper map https://example.com > our-map.json
diff firecrawl-map.json our-map.json

# Compare scrape results
firecrawl scrape https://example.com/page > firecrawl-scrape.md
web-scraper scrape https://example.com/page > our-scrape.md
diff firecrawl-scrape.md our-scrape.md
```

### Performance Benchmarks

- Map: <30s for typical site (100 URLs)
- Scrape: <5s per page (including browser render)
- Crawl: 10 pages/minute with politeness delays

### Edge Case Handling

- [ ] SPA with client-side routing
- [ ] Infinite scroll pages
- [ ] Login-protected content
- [ ] Rate-limited sites
- [ ] Large pages (>1MB HTML)
- [ ] Non-UTF8 encodings
- [ ] Malformed HTML

## Migration Path

### From Crawl4AI

1. Replace `AsyncWebCrawler` → `BrowserManager`
2. Replace `CrawlerRunConfig` → function parameters
3. Replace `DefaultMarkdownGenerator` → `MarkdownConverter`
4. Remove all `crawl4ai` imports
5. Update env vars from `CRAWL4AI_*` → `WEB_SCRAPER_*`

### Gradual Rollout

1. New `map` command uses new stack (Phase 2)
2. New `scrape` command uses new stack (Phase 3)
3. `crawl` command updated to use new services (Phase 4)
4. Remove old Crawl4AI-based code
5. Remove `crawl4ai` from dependencies

## Success Criteria

1. **Zero Crawl4AI dependency** - `pip uninstall crawl4ai` works
2. **CLI parity** - Same commands, same options, same output
3. **Output parity** - Markdown quality matches Firecrawl
4. **Performance parity** - Within 2x of Firecrawl speed
5. **Reliability** - Handles SPAs, rate limits, errors gracefully

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Playwright complexity | Thorough testing, error handling |
| SPA detection | Content stability check, configurable delays |
| Rate limiting | Respect robots.txt, configurable delays |
| Large sites | Streaming output, chunked processing |
| Memory usage | Process pages one at a time, don't hold all in memory |

## Timeline Estimate

| Phase | Effort | Dependencies |
|-------|--------|--------------|
| Phase 1: Core | 2-3 days | None |
| Phase 2: Map | 3-4 days | Phase 1 |
| Phase 3: Scrape | 2-3 days | Phase 1 |
| Phase 4: Crawl | 2-3 days | Phase 2, 3 |
| Phase 5: Batch | 1-2 days | Phase 3 |
| Phase 6: API | 3-4 days | Phase 1-5 |

**Total: ~15-20 days to full Firecrawl parity**

## Conclusion

This architecture provides a clear pathway from our current state to a production-quality Firecrawl replacement:

1. **Complete independence** from Crawl4AI
2. **Full API parity** with Firecrawl v2
3. **Better SPA handling** through fresh browser contexts
4. **Local-first** design with optional API server
5. **Incremental migration** path from current code

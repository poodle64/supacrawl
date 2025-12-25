# Data Flow: Map → Crawl → Scrape → Extract → Output

## Content Extraction Strategy

**Primary method: Playwright + markdownify** (browser rendering + pattern-based extraction)

This approach treats each page like an actual browser:
1. Playwright renders the page fully (JavaScript execution, SPA content loading)
2. BeautifulSoup cleans the HTML (removes boilerplate)
3. markdownify converts to markdown (preserves tables and structure)

---

## High-Level Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           USER COMMAND                                   │
│  supacrawl crawl https://example.com --output ./corpus                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         1. MAP PHASE                                     │
│                       (MapService.map)                                   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Input: Starting URL                                             │   │
│  │  ├── Fetch sitemap.xml (if exists)                              │   │
│  │  ├── BFS crawl with Playwright                                   │   │
│  │  │   ├── Extract links from each page                           │   │
│  │  │   └── Respect max_depth and domain boundaries                │   │
│  │  └── Extract metadata (title, description) per URL              │   │
│  │                                                                   │   │
│  │  Output: MapResult { links: [MapLink(url, title, description)] } │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ list of URLs
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      2. CRAWL ORCHESTRATION                              │
│                       (CrawlService.crawl)                               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  For each URL in map results:                                    │   │
│  │    ├── Apply include/exclude patterns                           │   │
│  │    ├── Check resume state (skip already scraped)                │   │
│  │    └── Call ScrapeService.scrape(url)  ─────────────────────┐   │   │
│  │                                                              │   │   │
│  │  Output: Stream of CrawlEvent (progress, page, error)        │   │   │
│  └──────────────────────────────────────────────────────────────┼───┘   │
└──────────────────────────────────────────────────────────────────┼───────┘
                                                                   │
                    ┌──────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        3. SCRAPE PHASE                                   │
│                      (ScrapeService.scrape)                              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Input: Single URL                                               │   │
│  │                                                                   │   │
│  │  Step 1: Fetch Page with Playwright                             │   │
│  │    └── Render page fully (JavaScript execution)                 │   │
│  │    └── Wait for SPA content to stabilize                        │   │
│  │    └── Returns: raw HTML (post-JavaScript)                      │   │
│  │                                                                   │   │
│  │  Step 2: Extract Metadata                                        │   │
│  │    └── Parse <title>, <meta>, OpenGraph tags                    │   │
│  │                                                                   │   │
│  │  Step 3: Convert to Markdown                                     │   │
│  │    └── MarkdownConverter.convert(html, url)                     │   │
│  │                                                                   │   │
│  │  Output: ScrapeResult { markdown, html, metadata }               │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ calls converter
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    4. MARKDOWN CONVERSION                                │
│                    (MarkdownConverter.convert)                           │
│                                                                          │
│  Pure Playwright + markdownify approach:                                │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Step 1: Clean HTML                                              │   │
│  │    └── Remove boilerplate tags (script, style, svg, etc.)       │   │
│  │    └── Remove structural boilerplate (nav, footer, header)      │   │
│  │    └── Remove CSS-matched junk (ads, popups, tracking pixels)   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Step 2: Find Main Content                                       │   │
│  │    └── Try framework-specific selectors first:                  │   │
│  │        #documentation_body_pagelet (Facebook)                   │   │
│  │        #mw-content-text (Wikipedia)                             │   │
│  │        .markdown-body (GitHub)                                  │   │
│  │        .rst-content (ReadTheDocs)                               │   │
│  │    └── Fall back to semantic elements:                          │   │
│  │        main, article, [role=main], #content, .content           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Step 3: Convert to Markdown                                     │   │
│  │    └── markdownify with AbsoluteUrlConverter                    │   │
│  │    └── Resolves relative URLs to absolute                       │   │
│  │    └── Preserves table structure                                │   │
│  │    └── Clean up whitespace                                      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  Output: Clean markdown string with preserved structure                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ markdown + metadata
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        5. OUTPUT PHASE                                   │
│                      (CrawlService._save_page)                           │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  For each scraped page:                                          │   │
│  │    ├── Generate filename from URL path                          │   │
│  │    ├── Write .md file with YAML frontmatter                     │   │
│  │    ├── Write .html file (if requested)                          │   │
│  │    ├── Write .json file (if requested)                          │   │
│  │    └── Update manifest.json with scraped URLs                   │   │
│  │                                                                   │   │
│  │  Output: Corpus on disk                                          │   │
│  │    output_dir/                                                   │   │
│  │      ├── manifest.json                                           │   │
│  │      ├── page-1.md                                               │   │
│  │      ├── page-2.md                                               │   │
│  │      └── ...                                                     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Why This Approach

### Playwright for JavaScript Rendering
- SPAs don't work with static HTTP fetches
- JavaScript must execute to load content
- Playwright waits for content stability before extraction

### markdownify for Conversion
- Preserves table structure correctly
- Handles nested elements properly
- No ML model overhead or API costs

### Pattern Matching for Content Detection
- Framework-specific selectors work reliably
- Falls back through multiple selector patterns
- More robust than DOM skeleton analysis

---

## Extraction Quality

| Site Type | Result |
|-----------|--------|
| Facebook Developer Docs | ✅ Clean tables, proper structure |
| Python Documentation | ✅ Full content, preserved formatting |
| GitHub READMEs | ✅ Markdown preserved |
| SPAs (React, Vue) | ✅ JavaScript-rendered content captured |
| Static sites | ✅ Clean extraction |

---

## Cost

**$0** - Everything runs locally:
- Playwright (bundled with the tool)
- BeautifulSoup (Python library)
- markdownify (Python library)

---

## Sequence Diagram

```
User         CLI          CrawlService    MapService    ScrapeService    Converter
 │            │                │               │              │              │
 │──crawl────▶│                │               │              │              │
 │            │───crawl()─────▶│               │              │              │
 │            │                │──map()───────▶│              │              │
 │            │                │               │──sitemap────▶│              │
 │            │                │               │◀─urls────────│              │
 │            │                │               │──bfs_crawl──▶│              │
 │            │                │               │◀─urls────────│              │
 │            │                │◀──MapResult───│              │              │
 │            │                │                              │              │
 │            │                │  for each URL:               │              │
 │            │                │──────scrape()───────────────▶│              │
 │            │                │                              │──fetch_page─▶│
 │            │                │                              │  (Playwright)│
 │            │                │                              │◀─HTML────────│
 │            │                │                              │──convert()──▶│
 │            │                │                              │              │
 │            │                │                              │   clean HTML │
 │            │                │                              │   find main  │
 │            │                │                              │   markdownify│
 │            │                │                              │              │
 │            │                │                              │◀─markdown────│
 │            │                │◀─────ScrapeResult────────────│              │
 │            │                │──save_page()                 │              │
 │            │◀──CrawlEvent───│                              │              │
 │◀─output────│                │                              │              │
```

---

## Key Insights

1. **Playwright is essential** - JavaScript rendering must happen before extraction
2. **markdownify preserves structure** - Tables, links, and formatting stay intact
3. **Pattern matching is reliable** - Framework-specific selectors work better than ML
4. **Cost is $0** - All extraction runs locally, no API calls needed

# 018: Add Sitemap Discovery and Parsing

## Status

✅ DONE (2025-12-13)

## Problem Summary

Currently the scraper only crawls pages it discovers through links starting from entrypoints. This misses:

1. Pages not linked from navigation
2. Deep pages that exceed max_depth
3. Recently added pages
4. Pages only accessible via sitemap

Firecrawl and other professional scrapers parse sitemaps to:
- Get a complete list of URLs upfront
- Prioritise recently modified pages
- Estimate crawl scope
- Plan crawl budget

## Solution Overview

Add sitemap discovery and parsing:

1. Auto-discover sitemaps (`/sitemap.xml`, `/sitemap_index.xml`, `robots.txt`)
2. Parse sitemap XML including nested sitemaps
3. Extract URLs with metadata (lastmod, changefreq, priority)
4. Use sitemap as additional URL source alongside link crawling
5. Optional sitemap-only mode for known complete sitemaps

## Implementation Steps

### Create Sitemap Module

- [ ] Create `web_scraper/discovery/sitemap.py`:

```python
@dataclass
class SitemapURL:
    loc: str
    lastmod: datetime | None = None
    changefreq: str | None = None
    priority: float | None = None

async def discover_sitemaps(base_url: str) -> list[str]:
    """Find sitemap URLs from robots.txt and common locations."""
    ...

async def parse_sitemap(sitemap_url: str) -> list[SitemapURL]:
    """Parse a sitemap XML, handling sitemap indexes."""
    ...
```

### Auto-Discovery Logic

- [ ] Check robots.txt for `Sitemap:` directives
- [ ] Try common sitemap locations:
  - `/sitemap.xml`
  - `/sitemap_index.xml`
  - `/sitemaps/sitemap.xml`
- [ ] Handle sitemap indexes (nested sitemaps)
- [ ] Handle gzipped sitemaps (`.xml.gz`)

### Integrate with Crawling

- [ ] Add `use_sitemap` option to SiteConfig:

```yaml
sitemap:
  enabled: true
  urls: []  # Optional explicit sitemap URLs
  only: false  # If true, only crawl sitemap URLs
  filter_by_lastmod: null  # Only URLs modified after date
```

- [ ] Merge sitemap URLs with discovered links
- [ ] Prioritise sitemap URLs with recent lastmod

### CLI Updates

- [ ] Add `map` command to show discovered URLs without crawling:

```bash
web-scraper map example-site  # Shows all discoverable URLs
web-scraper map example-site --sitemap  # Uses sitemap
```

- [ ] Add `--use-sitemap` flag to crawl command

### Crawl Budget Estimation

- [ ] Before crawling, show estimated page count
- [ ] Warn if sitemap URLs exceed max_pages
- [ ] Allow confirmation before large crawls

## Files to Modify

- Create `web_scraper/discovery/__init__.py`
- Create `web_scraper/discovery/sitemap.py`
- Update `web_scraper/models.py` - Add sitemap config
- Update `web_scraper/scrapers/crawl4ai.py` - Integrate sitemap URLs
- Update `web_scraper/cli.py` - Add map command
- Update `docs/40-usage/cli-usage-web-scraper.md`

## Testing Considerations

- Test with real sitemaps (Wikipedia, documentation sites)
- Test sitemap index parsing (nested sitemaps)
- Test gzipped sitemap handling
- Test robots.txt sitemap discovery
- Test integration with existing crawl flow
- Mock sitemap responses for unit tests

## Success Criteria

- [ ] Sitemaps are auto-discovered from robots.txt
- [ ] Common sitemap locations are checked
- [ ] Sitemap indexes are recursively parsed
- [ ] Sitemap URLs are merged with link discovery
- [ ] `map` command shows crawlable URLs
- [ ] `--use-sitemap` flag works on crawl
- [ ] Documentation covers sitemap options

## References

- Sitemap protocol: https://www.sitemaps.org/protocol.html
- robots.txt specification


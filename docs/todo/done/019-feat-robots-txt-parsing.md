# 019: Add robots.txt Parsing and Compliance

## Status

✅ DONE (2025-12-13)

## Problem Summary

The scraper currently ignores robots.txt entirely, which:

1. May cause the scraper to be blocked by websites
2. Could violate website terms of service
3. Ignores `Crawl-delay` directives (politeness)
4. Misses `Sitemap` directives
5. Could crawl pages explicitly disallowed

Professional scrapers respect robots.txt to:
- Be good internet citizens
- Avoid getting IP banned
- Follow website's crawling preferences
- Discover sitemaps

## Solution Overview

Implement robots.txt parsing and enforcement:

1. Fetch and parse robots.txt before crawling
2. Filter URLs against disallow rules
3. Respect Crawl-delay directives
4. Extract Sitemap URLs (feeds into TODO 018)
5. Configurable enforcement level (strict, warn, ignore)

## Implementation Steps

### Create Robots Module

- [ ] Create `web_scraper/discovery/robots.py`:

```python
from urllib.robotparser import RobotFileParser

@dataclass
class RobotsConfig:
    user_agent: str = "*"
    crawl_delay: float | None = None
    sitemaps: list[str] = field(default_factory=list)
    disallow_patterns: list[str] = field(default_factory=list)
    allow_patterns: list[str] = field(default_factory=list)

async def fetch_robots(base_url: str) -> RobotsConfig:
    """Fetch and parse robots.txt for a domain."""
    ...

def is_url_allowed(url: str, robots: RobotsConfig, user_agent: str = "*") -> bool:
    """Check if URL is allowed by robots.txt rules."""
    ...
```

### Integrate with Crawling

- [ ] Fetch robots.txt at crawl start
- [ ] Store parsed rules in crawl context
- [ ] Check each URL before fetching
- [ ] Apply Crawl-delay between requests

### Add Configuration Options

- [ ] Add `robots` section to SiteConfig:

```yaml
robots:
  respect: true  # Whether to respect robots.txt
  enforcement: "warn"  # strict|warn|ignore
  user_agent: "WebScraperBot/1.0"  # User agent for robots.txt matching
  min_delay: 0.5  # Minimum delay between requests (seconds)
```

### Handle Edge Cases

- [ ] 404 robots.txt = allow all
- [ ] 5xx robots.txt = retry or assume allow
- [ ] Multiple User-agent sections
- [ ] Wildcard patterns in rules
- [ ] URL encoding in paths

### Logging and Reporting

- [ ] Log when URLs are skipped due to robots.txt
- [ ] Include robots.txt info in manifest
- [ ] Warn when Crawl-delay would significantly slow crawl

## Files to Modify

- Create `web_scraper/discovery/robots.py`
- Update `web_scraper/models.py` - Add robots config
- Update `web_scraper/scrapers/crawl4ai.py` - URL filtering
- Update `web_scraper/corpus/writer.py` - Manifest metadata
- Update config docs

## Testing Considerations

- Test with various robots.txt formats
- Test disallow pattern matching
- Test Crawl-delay application
- Test sitemap extraction
- Test strict vs warn vs ignore modes
- Mock robots.txt responses for unit tests

## Success Criteria

- [ ] robots.txt is fetched before crawling
- [ ] Disallowed URLs are skipped
- [ ] Crawl-delay is respected
- [ ] Sitemaps are extracted
- [ ] Enforcement is configurable
- [ ] Skipped URLs are logged
- [ ] Documentation covers robots options

## References

- robots.txt specification: https://www.robotstxt.org/
- Python robotparser module


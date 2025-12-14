# 021: Add Rate Limiting and Politeness Controls

## Status

📋 PLANNING

## Problem Summary

The scraper currently has no rate limiting:

1. Can overwhelm target servers
2. May trigger anti-bot measures
3. Ignores robots.txt Crawl-delay
4. No concurrent request limits
5. No per-domain politeness

This leads to:
- IP bans
- Incomplete crawls
- Poor content quality (blocked pages)
- Being a bad internet citizen

## Solution Overview

Implement comprehensive rate limiting:

1. Global requests-per-second limiter
2. Per-domain delay enforcement
3. Concurrent request limits
4. robots.txt Crawl-delay integration
5. Adaptive rate limiting based on response times

## Implementation Steps

### Create Rate Limiter Module

- [ ] Create `web_scraper/rate_limit.py`:

```python
import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

@dataclass
class RateLimitConfig:
    requests_per_second: float = 2.0
    per_domain_delay: float = 1.0  # Seconds between requests to same domain
    max_concurrent: int = 5
    respect_crawl_delay: bool = True
    adaptive: bool = True  # Slow down on 429s

class RateLimiter:
    def __init__(self, config: RateLimitConfig):
        self._semaphore = asyncio.Semaphore(config.max_concurrent)
        self._domain_last_request: dict[str, datetime] = {}
        self._config = config
    
    async def acquire(self, url: str) -> None:
        """Wait until request is allowed."""
        ...
    
    def release(self, url: str) -> None:
        """Release after request complete."""
        ...
    
    def report_429(self, url: str) -> None:
        """Report rate limit response for adaptive adjustment."""
        ...
```

### Add Configuration

- [ ] Add rate limit options to SiteConfig:

```yaml
rate_limit:
  requests_per_second: 2.0
  per_domain_delay: 1.0
  max_concurrent: 5
  respect_crawl_delay: true
  adaptive: true
```

- [ ] Add environment variable overrides:
  - `CRAWL4AI_RATE_LIMIT_RPS`
  - `CRAWL4AI_RATE_LIMIT_DELAY`
  - `CRAWL4AI_MAX_CONCURRENT`

### Integrate with Crawling

- [ ] Wrap all fetch operations with rate limiter
- [ ] Apply per-domain delays
- [ ] Handle 429 responses with backoff
- [ ] Log rate limiting activity

### Adaptive Rate Limiting

- [ ] Track response times per domain
- [ ] Slow down if response times increase
- [ ] Back off on 429 responses
- [ ] Resume normal rate after successful requests

### CLI Updates

- [ ] Add `--rps` flag to crawl command (override config)
- [ ] Add `--delay` flag for per-request delay
- [ ] Show rate limiting statistics in output

## Files to Modify

- Create `web_scraper/rate_limit.py`
- Update `web_scraper/models.py` - Add RateLimitConfig
- Update `web_scraper/scrapers/crawl4ai.py` - Apply rate limiting
- Update `web_scraper/cli.py` - Add flags
- Update `.env.example` - Add rate limit vars
- Update docs

## Testing Considerations

- Test requests-per-second limiting
- Test per-domain delays
- Test concurrent request limits
- Test 429 response handling
- Test adaptive backoff
- Mock time for unit tests

## Success Criteria

- [ ] Requests respect configured RPS limit
- [ ] Per-domain delays are enforced
- [ ] Concurrent requests are limited
- [ ] 429 responses trigger adaptive backoff
- [ ] robots.txt Crawl-delay is integrated
- [ ] Rate limiting is logged
- [ ] Documentation covers rate limit options

## References

- robots.txt Crawl-delay
- TODO 019 (robots.txt integration)


# 023: Implement Browser Pool for Performance

## Status

📋 PLANNING

## Problem Summary

Currently a new browser context is created for each entrypoint/page, which:

1. Adds startup overhead (~1-3 seconds per browser)
2. Wastes memory (multiple browser processes)
3. Prevents session reuse (cookies, cache)
4. Makes concurrent crawling inefficient

For a 200-page crawl, this overhead significantly impacts total crawl time.

## Solution Overview

Implement a browser pool:

1. Pre-create a pool of browser contexts
2. Reuse browsers across pages
3. Handle browser crashes gracefully
4. Support concurrent page loading
5. Clean up browsers properly

## Implementation Steps

### Create Browser Pool Module

- [ ] Create `web_scraper/browser/pool.py`:

```python
from asyncio import Queue, Semaphore
from contextlib import asynccontextmanager
from crawl4ai import AsyncWebCrawler, BrowserConfig

class BrowserPool:
    """Pool of reusable browser instances."""
    
    def __init__(
        self,
        size: int = 3,
        config: BrowserConfig | None = None,
    ):
        self._size = size
        self._config = config or build_browser_config()
        self._pool: Queue[AsyncWebCrawler] = Queue()
        self._active: set[AsyncWebCrawler] = set()
    
    async def start(self) -> None:
        """Initialise browser pool."""
        for _ in range(self._size):
            browser = AsyncWebCrawler(config=self._config)
            await browser.__aenter__()
            await self._pool.put(browser)
    
    @asynccontextmanager
    async def acquire(self):
        """Get a browser from the pool."""
        browser = await self._pool.get()
        self._active.add(browser)
        try:
            yield browser
        finally:
            self._active.remove(browser)
            await self._pool.put(browser)
    
    async def close(self) -> None:
        """Close all browsers in pool."""
        while not self._pool.empty():
            browser = await self._pool.get()
            await browser.__aexit__(None, None, None)
```

### Add Configuration

- [ ] Add pool options to environment/config:

```yaml
browser:
  pool_size: 3
  reuse_sessions: true
  restart_on_crash: true
```

- [ ] Environment variables:
  - `CRAWL4AI_BROWSER_POOL_SIZE`
  - `CRAWL4AI_BROWSER_REUSE_SESSIONS`

### Integrate with Crawling

- [ ] Use pool in `Crawl4AIScraper`
- [ ] Acquire browser for each page
- [ ] Release back to pool after page complete
- [ ] Handle browser crashes (restart, requeue page)

### Session Management

- [ ] Option to share cookies across pages (login persistence)
- [ ] Option to clear cookies between pages (isolation)
- [ ] Handle session expiry

### Concurrent Crawling

- [ ] Process multiple pages concurrently
- [ ] Respect max_concurrent limit
- [ ] Handle rate limiting per-domain (see TODO 021)

### Health Monitoring

- [ ] Track browser health (memory, responsiveness)
- [ ] Replace unhealthy browsers
- [ ] Log pool statistics

## Files to Modify

- Create `web_scraper/browser/__init__.py`
- Create `web_scraper/browser/pool.py`
- Update `web_scraper/scrapers/crawl4ai.py` - Use pool
- Update `web_scraper/scrapers/crawl4ai_config.py` - Pool config
- Update config and docs

## Testing Considerations

- Test pool initialisation and cleanup
- Test concurrent browser acquisition
- Test browser crash recovery
- Test session persistence
- Benchmark with/without pool

## Success Criteria

- [ ] Browser pool reduces crawl time by 30%+
- [ ] Browsers are properly reused
- [ ] Crashes are handled gracefully
- [ ] Concurrent crawling works
- [ ] Memory usage is stable
- [ ] Documentation covers pool options

## References

- Crawl4AI managed browser feature
- asyncio Queue patterns


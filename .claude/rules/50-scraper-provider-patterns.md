---
paths: "**/*.py"
---

# Scraping Service Patterns

## Core Principles

The scraping services (ScrapeService, CrawlService, MapService) in `supacrawl/services/` provide the core scraping functionality with consistent patterns for error handling and browser management.

## Service Architecture

```
supacrawl/services/
├── browser.py      # BrowserManager - Playwright lifecycle management
├── converter.py    # MarkdownConverter - HTML to Markdown conversion
├── scrape.py       # ScrapeService - Single URL scraping
├── crawl.py        # CrawlService - Full site crawling (uses MapService + ScrapeService)
└── map.py          # MapService - URL discovery
```

## Mandatory Requirements

### Service Implementation

- **Must** use `BrowserManager` for Playwright browser lifecycle
- **Must** use `MarkdownConverter` for HTML→Markdown conversion
- **Must** return Pydantic models (`ScrapeResult`, `CrawlEvent`, `MapResult`, etc.)
- **Must** implement async methods for all I/O operations
- **Must NOT** manage Playwright directly - always use `BrowserManager`

### Import Pattern

```python
# Correct - use services package
from supacrawl.services.browser import BrowserManager
from supacrawl.services.converter import MarkdownConverter
from supacrawl.services.scrape import ScrapeService
from supacrawl.services.crawl import CrawlService
from supacrawl.services.map import MapService

# Or use the package exports
from supacrawl.services import ScrapeService, CrawlService
```

### Error Handling

- **Must** catch Playwright exceptions and wrap in `ProviderError`
- **Must** include correlation ID in all errors
- **Must** log errors with correlation ID before raising
- **Must** provide user-friendly error messages (not raw SDK errors)
- **Must NOT** expose Playwright-specific error details to users

**Example:**
```python
try:
    result = await browser.fetch_page(url)
except PlaywrightError as e:
    correlation_id = generate_correlation_id()
    LOGGER.error(
        "Browser fetch failed: %s",
        str(e),
        extra={"correlation_id": correlation_id, "url": url},
    )
    raise ProviderError(
        f"Failed to fetch {url}",
        correlation_id=correlation_id,
        context={"url": url, "error": str(e)},
    ) from e
```

### Configuration

- **Must** read configuration from environment variables (not hardcoded)
- **Must** support optional configuration overrides via parameters
- **Must** validate required configuration (Playwright browsers) before use
- **Must** provide clear error messages for missing configuration
- **Must** use constructor parameters for dependency injection (testing)

### Retry Logic

- **Must** implement retry logic for transient failures (5xx errors, timeouts)
- **Must** use exponential backoff with jitter for retries
- **Must** retry on connection errors and timeouts
- **Must NOT** retry on client errors (4xx) - fail immediately
- **Must** log retry attempts with correlation IDs
- **Must** respect maximum retry attempts (typically 3)

**Note**: See `.claude/rules/master/70-reliability.md` for universal retry requirements.

### Browser Management

- **Must** use `BrowserManager` as async context manager
- **Must** share browser context across multiple page fetches
- **Must** properly close browser resources on exit

**Example:**
```python
async with BrowserManager() as browser:
    content = await browser.fetch_page(url)
    # Browser is automatically closed when exiting context
```

## Key Directives

- **Service architecture**: Use services in `supacrawl/services/` for all scraping
- **Browser management**: Always use `BrowserManager`, never raw Playwright
- **Error handling**: Wrap Playwright errors in `ProviderError` with correlation IDs
- **Retry logic**: Retry on 5xx/timeouts, not on 4xx errors
- **Configuration**: Read from environment variables, support overrides
- **Testing**: Support dependency injection for testability

## References

- `.claude/rules/master/70-reliability.md` - Universal error handling and retry requirements
- `.claude/rules/70-error-handling.md` - Supacrawl-specific error handling patterns
- `docs/30-architecture/data-flow-llm.md` - Complete data flow documentation

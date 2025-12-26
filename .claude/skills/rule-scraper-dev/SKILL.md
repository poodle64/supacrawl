---
name: rule-scraper-dev
description: Scraping service development with error handling and retry patterns
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# Scraping service development with error handling and retry patterns

This skill is auto-generated from cursor rules. Follow these development standards:

# Source: 50-scraper-provider-patterns-supacrawl.mdc

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

- ✅ **Must** use `BrowserManager` for Playwright browser lifecycle
- ✅ **Must** use `MarkdownConverter` for HTML→Markdown conversion
- ✅ **Must** return Pydantic models (`ScrapeResult`, `CrawlEvent`, `MapResult`, etc.)
- ✅ **Must** implement async methods for all I/O operations
- ❌ **Must NOT** manage Playwright directly - always use `BrowserManager`

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

- ✅ **Must** catch Playwright exceptions and wrap in `ScraperError`
- ✅ **Must** include correlation ID in all errors
- ✅ **Must** log errors with correlation ID before raising
- ✅ **Must** provide user-friendly error messages (not raw SDK errors)
- ❌ **Must NOT** expose Playwright-specific error details to users

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
    raise ScraperError(
        f"Failed to fetch {url}",
        correlation_id=correlation_id,
        context={"url": url, "error": str(e)},
    ) from e
```

### Configuration

- ✅ **Must** read configuration from environment variables (not hardcoded)
- ✅ **Must** support optional configuration overrides via parameters
- ✅ **Must** validate required configuration (Playwright browsers) before use
- ✅ **Must** provide clear error messages for missing configuration
- ✅ **Must** use constructor parameters for dependency injection (testing)

### Retry Logic

- ✅ **Must** implement retry logic for transient failures (5xx errors, timeouts)
- ✅ **Must** use exponential backoff with jitter for retries
- ✅ **Must** retry on connection errors and timeouts
- ✅ **Must** NOT retry on client errors (4xx) - fail immediately
- ✅ **Must** log retry attempts with correlation IDs
- ✅ **Must** respect maximum retry attempts (typically 3)

**Note**: See `.cursor/rules/master/70-error-handling-basics.mdc` for universal retry requirements.

### Browser Management

- ✅ **Must** use `BrowserManager` as async context manager
- ✅ **Must** share browser context across multiple page fetches
- ✅ **Must** properly close browser resources on exit

**Example:**
```python
async with BrowserManager() as browser:
    content = await browser.fetch_page(url)
    # Browser is automatically closed when exiting context
```

## Key Directives

- **Service architecture**: Use services in `supacrawl/services/` for all scraping
- **Browser management**: Always use `BrowserManager`, never raw Playwright
- **Error handling**: Wrap Playwright errors in `ScraperError` with correlation IDs
- **Retry logic**: Retry on 5xx/timeouts, not on 4xx errors
- **Configuration**: Read from environment variables, support overrides
- **Testing**: Support dependency injection for testability

## References

- `.cursor/rules/master/70-error-handling-basics.mdc` - Universal error handling and retry requirements
- `.cursor/rules/70-error-handling-supacrawl.mdc` - Supacrawl-specific error handling patterns
- `docs/30-architecture/data-flow-llm.md` - Complete data flow documentation

---

# Source: 70-error-handling-supacrawl.mdc

# Error Handling

**Note**: Universal error handling principles (custom exceptions with context, correlation IDs, retry logic, input validation) are covered in `.cursor/rules/master/70-error-handling-basics.mdc`.

This rule documents project-specific error handling practice and relies on master rules for requirements.

## Core Principles

All supacrawl code must implement comprehensive error handling with supacrawl-specific patterns for exception hierarchy, correlation IDs, and error mapping.

## Mandatory Requirements

### Exception Hierarchy

- ✅ **Must** use `SupacrawlError` as base exception class
- ✅ **Must** use specific exception types: `ValidationError`, `ConfigurationError`, `ScraperError`
- ✅ **Must** include correlation ID in all exceptions
- ✅ **Must** include context dictionary for debugging
- ✅ **Must** provide user-friendly error messages

**Exception hierarchy:**
```
SupacrawlError (base)
├── ValidationError (input validation failures)
├── ConfigurationError (config loading/validation failures)
└── ScraperError (scraping operation failures)
```

### Correlation IDs

- ✅ **Must** generate correlation IDs using `generate_correlation_id()` function
- ✅ **Must** use 8-character UUID-based correlation IDs
- ✅ **Must** include correlation ID in all exception messages
- ✅ **Must** include correlation ID in all log messages
- ✅ **Must** pass correlation IDs through call chains (don't regenerate unnecessarily)

**Note**: See `.cursor/rules/master/70-error-handling-basics.mdc` for universal correlation ID requirements.

### CLI Error Presentation

- ✅ **Must** catch `SupacrawlError` exceptions in CLI commands
- ✅ **Must** display user-friendly error messages (not stack traces)
- ✅ **Must** display correlation IDs in error messages for debugging
- ✅ **Must** use `click.echo(..., err=True)` for error output
- ✅ **Must** exit with non-zero exit code on errors
- ❌ **Must NOT** expose stack traces to users (log internally)

### Logging Best Practices

- ✅ **Must** log errors with correlation IDs before raising exceptions
- ✅ **Must** use named loggers (`logging.getLogger(__name__)`)
- ✅ **Must** log scraper errors at ERROR level
- ✅ **Must** log validation errors at WARNING level
- ✅ **Must** log configuration errors at WARNING level
- ✅ **Must** include correlation ID in all log messages

## Key Directives

- **Exception hierarchy**: Use `SupacrawlError` base with specific exception types
- **Correlation IDs**: Include in all exceptions and log messages
- **Scraper errors**: Wrap Playwright exceptions in `ScraperError` with context
- **User-friendly**: Show friendly messages to users, log details internally
- **CLI errors**: Catch exceptions, show friendly messages with correlation IDs

## References

- `.cursor/rules/master/70-error-handling-basics.mdc` - Universal error handling principles
- `.cursor/rules/50-scraper-provider-patterns-supacrawl.mdc` - Scraper service patterns
- `.cursor/rules/20-cli-patterns-supacrawl.mdc` - CLI error presentation patterns

---
*Generated: 2025-12-24*
*Source rules: 50-scraper-provider-patterns-supacrawl.mdc, 70-error-handling-supacrawl.mdc*

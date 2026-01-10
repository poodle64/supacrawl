---
paths: "**/*.py"
---

# Error Handling

**Note**: Universal error handling principles (custom exceptions with context, correlation IDs, retry logic, input validation) are covered in `.claude/rules/master/70-reliability.md`.

This rule documents project-specific error handling practice and relies on master rules for requirements.

## Core Principles

All supacrawl code must implement comprehensive error handling with supacrawl-specific patterns for exception hierarchy, correlation IDs, and scraper error handling.

## Mandatory Requirements

### Exception Hierarchy

- **Must** use `SupacrawlError` as base exception class
- **Must** use specific exception types: `ValidationError`, `ConfigurationError`, `ProviderError`, `FileNotFoundError`
- **Must** include correlation ID in all exceptions
- **Must** include context dictionary for debugging
- **Must** provide user-friendly error messages

**Exception hierarchy:**
```
SupacrawlError (base)
├── ValidationError (input validation failures)
├── ConfigurationError (config loading/validation failures)
├── FileNotFoundError (missing files)
└── ProviderError (scraper/browser operation failures)
```

### Correlation IDs

- **Must** generate correlation IDs using `generate_correlation_id()` function
- **Must** use 8-character UUID-based correlation IDs
- **Must** include correlation ID in all exception messages
- **Must** include correlation ID in all log messages
- **Must** pass correlation IDs through call chains (don't regenerate unnecessarily)

**Note**: See `.claude/rules/master/70-reliability.md` for universal correlation ID requirements.

### Scraper Error Handling

- **Must** catch Playwright/browser exceptions and wrap in `ProviderError`
- **Must** include operation context in `ProviderError` context
- **Must** include original error details in context (not in message)
- **Must** log scraper errors with correlation ID before raising
- **Must** provide user-friendly messages (not raw Playwright errors)
- **Must NOT** expose Playwright-specific error details to users (log internally)

**Note**: `ProviderError` is used for all scraper/browser-related failures (Playwright timeouts, navigation errors, etc.).

**Example:**
```python
from playwright.async_api import Error as PlaywrightError

try:
    content = await browser.fetch_page(url)
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

### Configuration Error Handling

- **Must** raise `ConfigurationError` when configuration loading fails
- **Must** include config details in `ConfigurationError` context
- **Must** include validation errors in context
- **Must** provide helpful error messages with examples

### Validation Error Handling

- **Must** raise `ValidationError` when input validation fails
- **Must** include field name and value in `ValidationError` context
- **Must** include helpful examples in context
- **Must** provide actionable error messages

**Example:**
```python
if not value:
    correlation_id = generate_correlation_id()
    raise ValidationError(
        "At least one entrypoint is required.",
        field="entrypoints",
        value=value,
        correlation_id=correlation_id,
        context={"example": "entrypoints: ['https://example.com']"},
    )
```

### CLI Error Presentation

- **Must** catch `SupacrawlError` exceptions in CLI commands
- **Must** display user-friendly error messages (not stack traces)
- **Must** display correlation IDs in error messages for debugging
- **Must** use `click.echo(..., err=True)` for error output
- **Must** exit with non-zero exit code on errors
- **Must NOT** expose stack traces to users (log internally)

### Logging Best Practices

- **Must** log errors with correlation IDs before raising exceptions
- **Must** use `log_with_correlation()` helper for structured logging
- **Must** log scraper errors at ERROR level
- **Must** log validation errors at WARNING level
- **Must** log configuration errors at WARNING level
- **Must** include correlation ID in all log messages

## Key Directives

- **Exception hierarchy**: Use `SupacrawlError` base with specific exception types
- **Correlation IDs**: Include in all exceptions and log messages
- **Scraper errors**: Wrap Playwright/browser exceptions in `ProviderError` with context
- **User-friendly**: Show friendly messages to users, log details internally
- **CLI errors**: Catch exceptions, show friendly messages with correlation IDs

## References

- `.claude/rules/master/70-reliability.md` - Universal error handling principles
- `.claude/rules/50-scraper-provider-patterns.md` - Provider error handling patterns
- `.claude/rules/20-cli-patterns.md` - CLI error presentation patterns

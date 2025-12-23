---
name: rule-scraper-dev
description: Playwright scraper development with provider patterns, retry logic, and
  error handling
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# Playwright scraper development with provider patterns, retry logic, and error handling

This skill is auto-generated from cursor rules. Follow these development standards:

# Source: 50-scraper-provider-patterns-web-scraper.mdc

# Playwright Scraper Patterns

## Core Principles

The Playwright scraper implements the `Scraper` base class interface and follows consistent patterns for error handling and retry logic.

## Mandatory Requirements

### Scraper Implementation

- ✅ **Must** inherit from `Scraper` base class
- ✅ **Must** implement `crawl(config: SiteConfig) -> list[Page]` method
- ✅ **Must** set `provider_name` class attribute to `"playwright"`
- ✅ **Must** use `@override` decorator when overriding base class methods
- ✅ **Must** return `list[Page]` from `crawl()` method
- ❌ **Must NOT** implement scraping logic directly in web-scraper (use Playwright SDK)

### Error Handling

- ✅ **Must** catch Playwright SDK exceptions and wrap in `ProviderError`
- ✅ **Must** include provider name in `ProviderError` context
- ✅ **Must** include correlation ID in all provider errors
- ✅ **Must** log provider errors with correlation ID before raising
- ✅ **Must** provide user-friendly error messages (not raw SDK errors)
- ❌ **Must NOT** expose SDK-specific error details to users (log internally)

**Example:**
```python
try:
    result = crawler.arun(...)
except Exception as e:
    correlation_id = generate_correlation_id()
    log_with_correlation(
        LOGGER,
        logging.ERROR,
        "Playwright SDK crawl failed: %s",
        correlation_id=correlation_id,
        entrypoint=entrypoint,
        provider=self.provider_name,
        error=str(e),
    )
    raise ProviderError(
        f"Playwright SDK crawl failed for {entrypoint}.",
        provider=self.provider_name,
        correlation_id=correlation_id,
        context={"entrypoint": entrypoint, "error": str(e)},
    ) from e
```

### Configuration

- ✅ **Must** read configuration from environment variables (not hardcoded)
- ✅ **Must** support optional configuration overrides (base URLs, timeouts)
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
- ✅ **Must** use appropriate backoff intervals (1s, 2s, 4s recommended)

**Note**: See `.cursor/rules/master/70-error-handling-basics.mdc` for universal retry requirements.

### Initialization

- ✅ **Must** support dependency injection for testing (accept crawler parameter)
- ✅ **Must** build default crawler if not provided (for production use)
- ✅ **Must** read environment variables in `__init__` if not provided as parameters

## Key Directives

- **Scraper interface**: Always inherit from `Scraper` base class
- **Error handling**: Wrap SDK errors in `ProviderError` with correlation IDs
- **Retry logic**: Retry on 5xx/timeouts, not on 4xx errors
- **Configuration**: Read from environment variables, support overrides
- **Testing**: Support dependency injection for testability

## References

- `.cursor/rules/master/70-error-handling-basics.mdc` - Universal error handling and retry requirements
- `.cursor/rules/70-error-handling-web-scraper.mdc` - Web-scraper-specific error handling patterns

---

# Source: 70-error-handling-web-scraper.mdc

# Error Handling

**Note**: Universal error handling principles (custom exceptions with context, correlation IDs, retry logic, input validation) are covered in `.cursor/rules/master/70-error-handling-basics.mdc`.

This rule documents project-specific error handling practice and relies on master rules for requirements.

## Core Principles

All web-scraper code must implement comprehensive error handling with web-scraper-specific patterns for exception hierarchy, correlation IDs, and provider error mapping.

## Mandatory Requirements

### Exception Hierarchy

- ✅ **Must** use `WebScrapeError` as base exception class
- ✅ **Must** use specific exception types: `ValidationError`, `ConfigurationError`, `ProviderError`, `FileNotFoundError`
- ✅ **Must** include correlation ID in all exceptions
- ✅ **Must** include context dictionary for debugging
- ✅ **Must** provide user-friendly error messages

**Exception hierarchy:**
```
WebScrapeError (base)
├── ValidationError (input validation failures)
├── ConfigurationError (config loading/validation failures)
├── FileNotFoundError (missing files)
└── ProviderError (provider operation failures)
```

### Correlation IDs

- ✅ **Must** generate correlation IDs using `generate_correlation_id()` function
- ✅ **Must** use 8-character UUID-based correlation IDs
- ✅ **Must** include correlation ID in all exception messages
- ✅ **Must** include correlation ID in all log messages
- ✅ **Must** pass correlation IDs through call chains (don't regenerate unnecessarily)

**Note**: See `.cursor/rules/master/70-error-handling-basics.mdc` for universal correlation ID requirements.

### Provider Error Mapping

- ✅ **Must** catch provider-specific exceptions and wrap in `ProviderError`
- ✅ **Must** include provider name in `ProviderError` context
- ✅ **Must** include original error details in context (not in message)
- ✅ **Must** log provider errors with correlation ID before raising
- ✅ **Must** provide user-friendly messages (not raw provider errors)
- ❌ **Must NOT** expose provider-specific error details to users (log internally)

**Example:**
```python
try:
    result = provider_client.crawl(...)
except ProviderSpecificError as e:
    correlation_id = generate_correlation_id()
    log_with_correlation(
        LOGGER,
        "error",
        f"Provider {self.provider_name} failed: {e}",
        correlation_id,
        {"provider": self.provider_name, "error": str(e)},
    )
    raise ProviderError(
        f"Failed to crawl site using {self.provider_name}",
        provider=self.provider_name,
        correlation_id=correlation_id,
        context={"original_error": str(e)},
    ) from e
```

### Configuration Error Handling

- ✅ **Must** raise `ConfigurationError` when site configuration loading fails
- ✅ **Must** include config path in `ConfigurationError` context
- ✅ **Must** include validation errors in context
- ✅ **Must** provide helpful error messages with examples

### Validation Error Handling

- ✅ **Must** raise `ValidationError` when input validation fails
- ✅ **Must** include field name and value in `ValidationError` context
- ✅ **Must** include helpful examples in context
- ✅ **Must** provide actionable error messages

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

- ✅ **Must** catch `WebScrapeError` exceptions in CLI commands
- ✅ **Must** display user-friendly error messages (not stack traces)
- ✅ **Must** display correlation IDs in error messages for debugging
- ✅ **Must** use `click.echo(..., err=True)` for error output
- ✅ **Must** exit with non-zero exit code on errors
- ❌ **Must NOT** expose stack traces to users (log internally)

### Logging Best Practices

- ✅ **Must** log errors with correlation IDs before raising exceptions
- ✅ **Must** use `log_with_correlation()` helper for structured logging
- ✅ **Must** log provider errors at ERROR level
- ✅ **Must** log validation errors at WARNING level
- ✅ **Must** log configuration errors at WARNING level
- ✅ **Must** include correlation ID in all log messages

## Key Directives

- **Exception hierarchy**: Use `WebScrapeError` base with specific exception types
- **Correlation IDs**: Include in all exceptions and log messages
- **Provider errors**: Wrap provider exceptions in `ProviderError` with context
- **User-friendly**: Show friendly messages to users, log details internally
- **CLI errors**: Catch exceptions, show friendly messages with correlation IDs

## References

- `.cursor/rules/master/70-error-handling-basics.mdc` - Universal error handling principles
- `.cursor/rules/50-scraper-provider-patterns-web-scraper.mdc` - Provider error handling patterns
- `.cursor/rules/20-cli-patterns-web-scraper.mdc` - CLI error presentation patterns

---
*Generated: 2025-12-22 21:05:15 UTC*
*Source rules: 50-scraper-provider-patterns-web-scraper.mdc, 70-error-handling-web-scraper.mdc*

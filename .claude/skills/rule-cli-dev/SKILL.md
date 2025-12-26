---
name: rule-cli-dev
description: Click CLI development with command patterns, error presentation, and
  output formatting
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# Click CLI development with command patterns, error presentation, and output formatting

This skill is auto-generated from cursor rules. Follow these development standards:

# Source: 20-cli-patterns-supacrawl.mdc

# CLI Patterns

## Core Principles

All CLI commands must follow consistent Click patterns for command structure, error handling, and output formatting.

## Available Commands

Supacrawl provides 7 Firecrawl-aligned commands:

- `scrape` - Scrape a single URL to markdown/HTML/JSON
- `crawl` - Crawl a website with URL discovery
- `map` - Discover URLs without scraping
- `search` - Web search with optional scraping
- `llm-extract` - LLM-powered structured data extraction
- `agent` - Autonomous web agent for data gathering
- `cache` - Cache management subcommands

## Mandatory Requirements

### Command Structure

- ✅ **Must** use `@click.group()` for main application entry point
- ✅ **Must** use `@app.command()` for subcommands
- ✅ **Must** use descriptive command names (kebab-case: `llm-extract`)
- ✅ **Must** provide `help` parameter for all commands and options
- ✅ **Must** use docstrings for command functions (explains what command does)

### Option and Argument Patterns

- ✅ **Must** use `@click.option()` for optional parameters
- ✅ **Must** use `@click.argument()` for required positional parameters
- ✅ **Must** use `click.Path` for file/directory path options
- ✅ **Must** specify `type` parameter for path options (`path_type=Path`)
- ✅ **Must** use appropriate Click types (`str`, `int`, `bool`, `click.Path`)
- ✅ **Must** provide default values when appropriate

### Error Handling in CLI

- ✅ **Must** catch `SupacrawlError` exceptions and display user-friendly messages
- ✅ **Must** display correlation IDs in error messages for debugging
- ✅ **Must** use `click.echo()` for normal output (stdout)
- ✅ **Must** use `click.echo(..., err=True)` for error messages (stderr)
- ✅ **Must** exit with appropriate exit codes (0 for success, 1 for errors)
- ❌ **Must NOT** expose stack traces to users (log internally, show friendly messages)
- ❌ **Must NOT** use `print()` statements (use `click.echo()`)

### Output Formatting

- ✅ **Must** use consistent output format across commands
- ✅ **Must** use `click.echo()` for all output (not `print()`)
- ✅ **Must** format lists and tables consistently
- ✅ **Must** provide clear success/error messages
- ✅ **Must** use structured output when appropriate (JSON for machine-readable)

### Command Examples

**Good command structure:**
```python
@app.command("scrape", help="Scrape a single URL to markdown.")
@click.argument("url")
@click.option(
    "--format",
    "formats",
    type=click.Choice(["markdown", "html", "rawHtml", "links"]),
    multiple=True,
    default=["markdown"],
    help="Output format(s).",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    help="Output file path. If omitted, prints to stdout.",
)
def scrape(url: str, formats: tuple[str, ...], output: Path | None) -> None:
    """
    Scrape a single URL and output content.

    Args:
        url: The URL to scrape.
        formats: Output format(s) to generate.
        output: Optional output file path.
    """
    try:
        result = asyncio.run(scrape_service.scrape(url, formats=list(formats)))
        if output:
            output.write_text(result.markdown)
            click.echo(f"Scraped to {output}")
        else:
            click.echo(result.markdown)
    except SupacrawlError as e:
        click.echo(f"Error: {e.message} [correlation_id={e.correlation_id}]", err=True)
        raise SystemExit(1)
```

## Key Directives

- **Consistent structure**: Use Click group/command pattern throughout
- **User-friendly errors**: Catch exceptions, show friendly messages with correlation IDs
- **Click output**: Always use `click.echo()`, never `print()`
- **Path handling**: Use `click.Path` with `path_type=Path` for file/directory options
- **Help text**: Provide help for all commands and options

## References

- `.cursor/rules/70-error-handling-supacrawl.mdc` - Error handling patterns for CLI commands

---

# Source: 70-error-handling-supacrawl.mdc

# Error Handling

**Note**: Universal error handling principles (custom exceptions with context, correlation IDs, retry logic, input validation) are covered in `.cursor/rules/master/70-error-handling-basics.mdc`.

This rule documents project-specific error handling practice and relies on master rules for requirements.

## Core Principles

All supacrawl code must implement comprehensive error handling with supacrawl-specific patterns for exception hierarchy, correlation IDs, and provider error mapping.

## Mandatory Requirements

### Exception Hierarchy

- ✅ **Must** use `SupacrawlError` as base exception class
- ✅ **Must** use specific exception types: `ValidationError`, `ConfigurationError`, `ProviderError`, `FileNotFoundError`
- ✅ **Must** include correlation ID in all exceptions
- ✅ **Must** include context dictionary for debugging
- ✅ **Must** provide user-friendly error messages

**Exception hierarchy:**
```
SupacrawlError (base)
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
    result = await scrape_service.scrape(url)
except PlaywrightError as e:
    correlation_id = generate_correlation_id()
    log_with_correlation(
        LOGGER,
        "error",
        f"Browser failed: {e}",
        correlation_id,
        {"url": url, "error": str(e)},
    )
    raise ProviderError(
        f"Failed to scrape {url}",
        provider="playwright",
        correlation_id=correlation_id,
        context={"original_error": str(e)},
    ) from e
```

### Validation Error Handling

- ✅ **Must** raise `ValidationError` when input validation fails
- ✅ **Must** include field name and value in `ValidationError` context
- ✅ **Must** include helpful examples in context
- ✅ **Must** provide actionable error messages

**Example:**
```python
if not url:
    correlation_id = generate_correlation_id()
    raise ValidationError(
        "URL is required.",
        field="url",
        value=url,
        correlation_id=correlation_id,
        context={"example": "https://example.com"},
    )
```

### CLI Error Presentation

- ✅ **Must** catch `SupacrawlError` exceptions in CLI commands
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
- ✅ **Must** include correlation ID in all log messages

## Key Directives

- **Exception hierarchy**: Use `SupacrawlError` base with specific exception types
- **Correlation IDs**: Include in all exceptions and log messages
- **Provider errors**: Wrap provider exceptions in `ProviderError` with context
- **User-friendly**: Show friendly messages to users, log details internally
- **CLI errors**: Catch exceptions, show friendly messages with correlation IDs

## References

- `.cursor/rules/master/70-error-handling-basics.mdc` - Universal error handling principles
- `.cursor/rules/20-cli-patterns-supacrawl.mdc` - CLI error presentation patterns

---
*Generated: 2025-12-26*
*Source rules: 20-cli-patterns-supacrawl.mdc, 70-error-handling-supacrawl.mdc*

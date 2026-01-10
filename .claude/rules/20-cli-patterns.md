---
paths: "**/*.py"
---

# CLI Patterns

## Core Principles

All CLI commands must follow consistent Click patterns for command structure, error handling, and output formatting.

## Mandatory Requirements

### Command Structure

- **Must** use `@click.group()` for main application entry point
- **Must** use `@app.command()` for subcommands
- **Must** use descriptive command names (kebab-case: `llm-extract`)
- **Must** provide `help` parameter for all commands and options
- **Must** use docstrings for command functions (explains what command does)

### Option and Argument Patterns

- **Must** use `@click.option()` for optional parameters
- **Must** use `@click.argument()` for required positional parameters
- **Must** use `click.Path` for file/directory path options
- **Must** specify `type` parameter for path options (`path_type=Path`)
- **Must** use appropriate Click types (`str`, `int`, `bool`, `click.Path`)
- **Must** provide default values when appropriate

### Error Handling in CLI

- **Must** catch `SupacrawlError` exceptions and display user-friendly messages
- **Must** display correlation IDs in error messages for debugging
- **Must** use `click.echo()` for normal output (stdout)
- **Must** use `click.echo(..., err=True)` for error messages (stderr)
- **Must** exit with appropriate exit codes (0 for success, 1 for errors)
- **Must NOT** expose stack traces to users (log internally, show friendly messages)
- **Must NOT** use `print()` statements (use `click.echo()`)

### Output Formatting

- **Must** use consistent output format across commands
- **Must** use `click.echo()` for all output (not `print()`)
- **Must** format lists and tables consistently
- **Must** provide clear success/error messages
- **Must** use structured output when appropriate (JSON for machine-readable)

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

- `.claude/rules/70-error-handling.md` - Error handling patterns for CLI commands

---
paths:
  - '**/cli/**/*.py'
---

# CLI Patterns

Click command conventions for `src/supacrawl/cli/`. Generic Click usage (groups, options, help text, docstrings) is assumed — this file carries only what differs or has bitten.

## Conventions

- **Must** use `click.echo()` for all output, never `print()` — `err=True` sends to stderr.
- **Must** emit JSON for machine-readable output (the default consumer is a pipeline).
- **Must** use `click.Path(path_type=Path)` for file/directory options.
- **Must** use kebab-case subcommand names (`llm-extract`).

## Error presentation

The CLI is where `SupacrawlError` surfaces to a human; error _raising_ and the exception hierarchy are `70-error-handling.md`'s.

- **Must** catch `SupacrawlError`, print a friendly message with its `correlation_id` to stderr, and `raise SystemExit(1)` — never leak a stack trace to the user.

```python
try:
    result = asyncio.run(scrape_service.scrape(url, formats=list(formats)))
    click.echo(result.markdown) if not output else output.write_text(result.markdown)
except SupacrawlError as e:
    click.echo(f"Error: {e.message} [correlation_id={e.correlation_id}]", err=True)
    raise SystemExit(1)
```

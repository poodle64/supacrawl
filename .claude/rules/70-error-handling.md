---
paths:
  - '**/src/**/*.py'
---

# Error Handling

Supacrawl's exception and correlation-ID conventions. Universal reliability principles (custom exceptions with context, retry logic, input validation) are in the master reliability rule; detail and worked examples in `docs/development/error-handling.md`.

## Exception hierarchy

- **Must** raise from the `SupacrawlError` base, using the specific subtype: `ValidationError`, `ConfigurationError`, `FileNotFoundError`, `ProviderError` (all scraper/browser failures).
- **Must** carry a `correlation_id` and a `context` dict on every exception; keep the raw underlying error in `context`, not in the user-facing `message`.

## Correlation IDs

- **Must** mint IDs with `generate_correlation_id()` (8-char, UUID-based) and thread the same ID through a call chain — do not regenerate mid-chain.
- **Must** log with `log_with_correlation()` _before_ raising, so the ID appears in both the log and the exception.

## Wrapping provider errors

```python
try:
    content = await browser.fetch_page(url)
except PlaywrightError as e:
    cid = generate_correlation_id()
    LOGGER.error("Browser fetch failed: %s", e, extra={"correlation_id": cid, "url": url})
    raise ProviderError(f"Failed to fetch {url}", correlation_id=cid,
                        context={"url": url, "error": str(e)}) from e
```

CLI presentation of these errors (friendly message, exit code) is `20-cli-patterns.md`'s.

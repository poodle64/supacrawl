# CLI Usage Guide

This guide covers using the web-scraper command-line interface.

## Command Overview

The `web-scraper` CLI provides commands for managing site configurations, running crawls, and processing corpus output.

### Available Commands

- `list-sites` - List available site configurations
- `show-site` - Show site configuration summary
- `crawl` - Run a crawl for a site
- `chunk` - Chunk an existing snapshot

## Command Reference

### list-sites

List all available site configuration files.

**Usage:**
```bash
web-scraper list-sites [--base-path PATH]
```

**Options:**
- `--base-path PATH` - Base directory containing `sites/` folder (optional)

**Example:**
```bash
$ web-scraper list-sites
example-site
meta
another-site
```

### show-site

Display a summary of a site configuration.

**Usage:**
```bash
web-scraper show-site SITE_NAME [--base-path PATH]
```

**Arguments:**
- `SITE_NAME` - Site identifier (filename without `.yaml`)

**Options:**
- `--base-path PATH` - Base directory containing `sites/` folder (optional)

**Example:**
```bash
$ web-scraper show-site example-site
Site: example-site
Name: Example Site
Provider: crawl4ai
Entrypoints:
  - https://example.com
Max Pages: 100
Formats: html
```

### crawl

Run a crawl for a site configuration, creating a new corpus snapshot.

**Usage:**
```bash
web-scraper crawl SITE_NAME [--base-path PATH]
```

**Arguments:**
- `SITE_NAME` - Site identifier (filename without `.yaml`)

**Options:**
- `--base-path PATH` - Base directory containing `sites/` and `corpora/` folders (optional)

**Example:**
```bash
$ web-scraper crawl example-site
Starting crawl for example-site...
Crawl completed: 42 pages
Snapshot created: corpora/example-site/2025-01-15_1430/
```

**Output:**
- Creates snapshot directory: `corpora/{site_id}/{snapshot_id}/`
- Writes manifest: `corpora/{site_id}/{snapshot_id}/manifest.json`
- Writes pages: `corpora/{site_id}/{snapshot_id}/pages/*`

### chunk

Chunk an existing snapshot into JSONL format for LLM consumption.

**Usage:**
```bash
web-scraper chunk SITE_NAME SNAPSHOT_ID [--base-path PATH]
```

**Arguments:**
- `SITE_NAME` - Site identifier
- `SNAPSHOT_ID` - Snapshot identifier (timestamp format: `YYYY-MM-DD_HHMM`)

**Options:**
- `--base-path PATH` - Base directory containing `corpora/` folder (optional)

**Example:**
```bash
$ web-scraper chunk example-site 2025-01-15_1430
Chunking snapshot 2025-01-15_1430...
Chunks written: corpora/example-site/2025-01-15_1430/chunks.jsonl
```

**Output:**
- Creates chunks file: `corpora/{site_id}/{snapshot_id}/chunks.jsonl`


## Common Workflows

### Initial Setup

1. **List available sites:**
   ```bash
   web-scraper list-sites
   ```

2. **View site configuration:**
   ```bash
   web-scraper show-site example-site
   ```

3. **Run test crawl:**
   ```bash
   web-scraper crawl example-site
   ```

4. **Check corpus output:**
   ```bash
   ls corpora/example-site/
   ```

### Production Crawl

1. **Verify configuration:**
   ```bash
   web-scraper show-site production-site
   ```

2. **Run crawl:**
   ```bash
   web-scraper crawl production-site
   ```

3. **Note snapshot ID from output** (e.g., `2025-01-15_1430`)

4. **Chunk snapshot:**
   ```bash
   web-scraper chunk production-site 2025-01-15_1430
   ```

### Processing Multiple Sites

```bash
for site in $(web-scraper list-sites); do
  echo "Crawling $site..."
  web-scraper crawl "$site"
done
```

## Error Handling

### Common Errors

**Configuration Not Found:**
```
Error: Site configuration not found: sites/example-site.yaml [correlation_id=abc12345]
```

**Solution:** Check filename matches site name, verify file exists in `sites/` directory.

**Validation Error:**
```
Error: At least one entrypoint is required. [correlation_id=abc12345]
```

**Solution:** Check site configuration YAML, ensure all required fields are present.

**Provider Error:**
```
Error: Failed to crawl site using crawl4ai [correlation_id=abc12345]
```

**Solution:** Check Crawl4AI installation (`crawl4ai-doctor`), review provider logs.

**Missing Snapshot:**
```
Error: Snapshot not found: corpora/example-site/2025-01-15_1430 [correlation_id=abc12345]
```

**Solution:** Verify snapshot ID is correct, check snapshot directory exists.

### Debugging with Correlation IDs

All errors include correlation IDs for debugging:

1. Note correlation ID from error message
2. Check logs for entries with same correlation ID
3. Review error context in logs

## Output Interpretation

### Crawl Output

```
Starting crawl for example-site...
Crawl completed: 42 pages
Snapshot created: corpora/example-site/2025-01-15_1430/
```

- **Pages**: Number of pages scraped
- **Snapshot**: Snapshot directory path

### Chunk Output

```
Chunking snapshot 2025-01-15_1430...
Chunks written: corpora/example-site/2025-01-15_1430/chunks.jsonl
```

- **Chunks**: JSONL file path containing chunked content

## Environment Variables

### Crawl4AI Provider

- `CRAWL4AI_BASE_URL` - Optional base URL override (default: `https://crawl4ai.godswood.au`)

## Best Practices

1. **Validate First**: Use `show-site` to validate configurations before crawling
2. **Test Crawls**: Start with small `max_pages` limits for testing
3. **Check Output**: Verify corpus output after each crawl
4. **Use Correlation IDs**: Use correlation IDs from errors for debugging
5. **Monitor Logs**: Check logs for provider-specific issues
6. **Version Control**: Track site configurations in git

## References

- `.cursor/rules/20-cli-patterns-web-scraper.mdc` - CLI pattern requirements
- `.cursor/rules/70-error-handling-web-scraper.mdc` - Error handling patterns
- `docs/40-usage/creating-site-configs-web-scraper.md` - Site configuration guide

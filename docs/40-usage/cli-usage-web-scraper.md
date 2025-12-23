# CLI Usage Guide

This guide covers using the web-scraper command-line interface.

## Command Overview

The `web-scraper` CLI provides commands for managing site configurations, running crawls, and processing corpus output.

### Available Commands

**Site Configuration-based:**
- `list-sites` - List available site configurations
- `show-site` - Show site configuration summary
- `map` - Map site URLs that would be crawled (config-based)
- `crawl` - Run a crawl for a site (config-based)
- `list-snapshots` - List snapshots for a site
- `init` - Create a new site configuration
- `chunk` - Chunk an existing snapshot
- `compress` - Compress a snapshot for archival
- `extract` - Extract a compressed snapshot archive

**URL-based (Firecrawl-compatible):**
- `scrape-url` - Scrape a single URL
- `batch-scrape` - Scrape multiple URLs concurrently
- `crawl-url` - Crawl a website from a starting URL
- `map-url` - Map URLs from a website

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
Entrypoints:
  - https://example.com
Max Pages: 100
Formats: html
```

### map

Map a site to discover all URLs that would be crawled, without actually crawling.

**Usage:**
```bash
web-scraper map SITE_NAME [OPTIONS]
```

**Arguments:**
- `SITE_NAME` - Site identifier (filename without `.yaml`)

**Options:**
- `--base-path PATH` - Base directory containing `sites/` folder (optional)
- `--max-urls INT` - Maximum number of URLs to return (default: 200)
- `--format FORMAT` - Output format: `json` or `jsonl` (default: `jsonl`)
- `--output PATH` - Output file path (default: stdout)
- `--use-sitemap/--no-sitemap` - Override config.sitemap.enabled
- `--use-robots/--no-robots` - Override config.robots.respect
- `--include-entrypoints-only` - Return only entrypoints, no discovery

**Example:**
```bash
$ web-scraper map example-site --format jsonl --output urls.jsonl
Mapped 42 URLs to urls.jsonl
```

**Output Format:**
Each URL entry contains:
- `url` - Normalised URL
- `source` - Discovery source (`entrypoint`, `sitemap`, or `html_links`)
- `depth` - Crawl depth (0 for entrypoints/sitemap, 1 for HTML links)
- `allowed` - Whether robots.txt allows this URL
- `included` - Whether URL matches include/exclude patterns
- `excluded_reason` - Reason if excluded (`robots_disallow`, `exclude_pattern`, `not_in_include`, or `null`)

### crawl

Run a crawl for a site configuration, creating a new corpus snapshot.

**Usage:**
```bash
web-scraper crawl SITE_NAME [OPTIONS]
```

**Arguments:**
- `SITE_NAME` - Site identifier (filename without `.yaml`)

**Options:**
- `--base-path PATH` - Base directory containing `sites/` and `corpora/` folders (optional)
- `--verbose/--no-verbose` - Show crawl progress logs (default: false)
- `--fresh` - Start a fresh crawl (ignore incomplete snapshots)
- `--dry-run` - Show URLs that would be crawled without fetching content
- `--chunks` - Generate chunks.jsonl after crawl completes
- `--formats FORMATS` - Comma-separated output formats (markdown, html, text, json). Overrides config.
- `--from-map PATH` - Crawl only the URLs in a map output file (json or jsonl). URLs are filtered to include only entries where `included=true` and `allowed=true` (if present).
- `--concurrency INT` - Maximum concurrent page crawls (1-20). Overrides config.politeness.max_concurrent.
- `--delay FLOAT` - Minimum delay between requests in seconds. Overrides config.politeness.delay_between_requests.
- `--timeout FLOAT` - Page timeout in seconds (5-600). Overrides config.politeness.page_timeout.
- `--retries INT` - Maximum retry attempts (0-10). Overrides config.politeness.max_retries.

**Example:**
```bash
$ web-scraper crawl example-site
Starting crawl for example-site...
Crawled 42 pages
Output: corpora/example-site/latest/
```

**Auto-Resume:**
Crawls automatically resume from incomplete snapshots. If a previous crawl was interrupted, running the same command will continue from where it left off. Use `--fresh` to force a new snapshot instead.

**With Politeness Overrides:**
```bash
# Slower, more polite crawl
$ web-scraper crawl example-site --concurrency 2 --delay 3.0 --timeout 180

# Faster crawl for known-safe targets
$ web-scraper crawl example-site --concurrency 10 --delay 0.5
```

**Crawl from Map:**
```bash
# Step 1: Generate map
web-scraper map example-site --format jsonl --output urls.jsonl

# Step 2: Crawl using map
web-scraper crawl example-site --from-map urls.jsonl
```

**Output:**
- Creates snapshot directory: `corpora/{site_id}/{snapshot_id}/`
- Writes manifest: `corpora/{site_id}/{snapshot_id}/manifest.json`
- Writes pages by format: `corpora/{site_id}/{snapshot_id}/{format}/*`
- Updates symlink: `corpora/{site_id}/latest/` → `{snapshot_id}/`

### list-snapshots

List all snapshots for a site with status and metadata.

**Usage:**
```bash
web-scraper list-snapshots SITE_NAME [--base-path PATH]
```

**Arguments:**
- `SITE_NAME` - Site identifier (same as used for crawl)

**Options:**
- `--base-path PATH` - Base directory containing `corpora/` folder (optional)

**Example:**
```bash
$ web-scraper list-snapshots meta
2025-12-15_0847  completed   42 pages    15 chunks  2025-12-15T08:47:00+10:00
2025-12-14_1200  aborted     12 pages     - chunks  2025-12-14T12:00:00+10:00
```

**Output columns:**
- Snapshot ID (timestamp format)
- Status (completed, in_progress, aborted)
- Page count
- Chunk count (or `-` if no chunks)
- Created timestamp

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

## URL-Based Commands (Firecrawl-compatible)

These commands work with raw URLs instead of site configuration files, providing Firecrawl-compatible APIs for ad-hoc scraping.

### scrape-url

Scrape a single URL and output content.

**Usage:**
```bash
web-scraper scrape-url URL [OPTIONS]
```

**Arguments:**
- `URL` - The URL to scrape

**Options:**
- `--format FORMAT` - Output format: `json` or `markdown` (default: `json`)
- `--output PATH` - Output file path (default: stdout)
- `--timeout INT` - Page timeout in seconds (default: 30)

**Example:**
```bash
$ web-scraper scrape-url https://example.com --format markdown
# Outputs markdown content to stdout

$ web-scraper scrape-url https://example.com --output result.json
# Writes JSON to file
```

### batch-scrape

Scrape multiple URLs concurrently from a file.

**Usage:**
```bash
web-scraper batch-scrape URLS_FILE [OPTIONS]
```

**Arguments:**
- `URLS_FILE` - File containing URLs (one per line, or JSON/JSONL format)

**Options:**
- `--concurrency INT` - Maximum concurrent requests (default: 5)
- `--output PATH` - Output file path (default: stdout)
- `--format FORMAT` - Output format: `json` or `jsonl` (default: `jsonl`)

**Example:**
```bash
$ echo -e "https://example.com\nhttps://example.org" > urls.txt
$ web-scraper batch-scrape urls.txt --concurrency 3
```

### crawl-url

Crawl a website starting from a URL.

**Usage:**
```bash
web-scraper crawl-url URL [OPTIONS]
```

**Arguments:**
- `URL` - The starting URL for the crawl

**Options:**
- `--limit INT` - Maximum pages to crawl (default: 100)
- `--output PATH` - Output directory or file
- `--format FORMAT` - Output format: `json` or `jsonl` (default: `jsonl`)
- `--depth INT` - Maximum crawl depth (default: 3)

**Example:**
```bash
$ web-scraper crawl-url https://docs.example.com --limit 50
```

### map-url

Map URLs from a website without scraping content.

**Usage:**
```bash
web-scraper map-url URL [OPTIONS]
```

**Arguments:**
- `URL` - The starting URL to map

**Options:**
- `--limit INT` - Maximum URLs to discover (default: 200)
- `--output PATH` - Output file path (default: stdout)
- `--format FORMAT` - Output format: `text` or `json` (default: `text`)
- `--depth INT` - Maximum discovery depth (default: 3)
- `--sitemap` - Sitemap mode: `include`, `skip`, or `only` (default: `include`)
- `--include-subdomains` - Include subdomains in mapping

**Example:**
```bash
$ web-scraper map-url https://example.com --limit 100 --format json
```

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

### Map Then Crawl Workflow

1. **Generate map:**
   ```bash
   web-scraper map example-site --format jsonl --output urls.jsonl
   ```

2. **Review mapped URLs:**
   ```bash
   cat urls.jsonl | jq '.url, .included, .excluded_reason'
   ```

3. **Crawl using map:**
   ```bash
   web-scraper crawl example-site --from-map urls.jsonl
   ```

This workflow provides deterministic URL discovery and crawling, useful for:
- Reproducible crawls (same URLs every time)
- Pre-filtering URLs before crawling
- Separating discovery from crawling phases

### Processing Multiple Sites

```bash
for site in $(web-scraper list-sites); do
  echo "Crawling $site..."
  web-scraper crawl "$site"
done
```

## Interruption Handling

If you interrupt a crawl with Ctrl+C, web-scraper handles it gracefully:

1. **Progress is saved**: All pages crawled so far are written to the snapshot
2. **Manifest is updated**: The manifest shows `status: aborted`
3. **State is preserved**: Crawl state file is saved for resumption

**Resuming an interrupted crawl:**

Crawls automatically resume from incomplete snapshots. Simply run the same command again:

```bash
# Run again to resume from where it left off
$ web-scraper crawl example-site
Resuming Example Site (42 completed, 58 pending)...
```

The resumed crawl will skip already-completed URLs and continue from where it left off. Use `--fresh` to start a new snapshot instead.

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

**Scraper Error:**
```
Error: Failed to crawl site [correlation_id=abc12345]
```

**Solution:** Check Playwright installation (`playwright install chromium`), review error logs.

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

### Playwright Configuration

See `.env.example` for available browser configuration options.

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

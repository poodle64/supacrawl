# Documentation Index

## Architecture

- **`30-architecture/corpus-layout-web-scraper.md`** - Snapshot directory structure and layout patterns
- **`30-architecture/site-configuration-web-scraper.md`** - Site configuration system and schema
- **`30-architecture/snapshot-contract.md`** - Snapshot manifest contract and schema versioning

## Usage

- **`40-usage/cli-usage-web-scraper.md`** - Complete CLI command reference (config-based and URL-based commands)
- **`40-usage/USAGE_GUIDE.md`** - Operator-focused guide: defaults, environment variables, troubleshooting
- **`40-usage/creating-site-configs-web-scraper.md`** - How to create and configure site YAML files

## Reliability

- **`70-reliability/error-handling-web-scraper.md`** - Error handling patterns and exception hierarchy
- **`70-reliability/retry-logic-web-scraper.md`** - Retry logic implementation and patterns
- **`70-reliability/testing-web-scraper.md`** - Testing strategies and patterns

## Schemas

- **`web_scraper/schemas/snapshot-manifest.schema.json`** - JSON schema for snapshot manifest validation

## Quick Reference

### Site Configuration Workflow (Recommended)

```bash
# List sites, create config, crawl, chunk
web-scraper list-sites
web-scraper init my-site
web-scraper crawl my-site
web-scraper chunk my-site latest
```

### URL-Based Workflow (Firecrawl-compatible)

```bash
# Single URL
web-scraper scrape-url https://example.com

# Multiple URLs
web-scraper batch-scrape urls.txt

# Crawl from URL
web-scraper crawl-url https://example.com --limit 50

# Map URLs
web-scraper map-url https://example.com
```

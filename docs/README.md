# Documentation Index

## Architecture

- **`30-architecture/corpus-layout-supacrawl.md`** - Snapshot directory structure and layout patterns
- **`30-architecture/site-configuration-supacrawl.md`** - Site configuration system and schema
- **`30-architecture/snapshot-contract.md`** - Snapshot manifest contract and schema versioning

## Usage

- **`40-usage/cli-usage-supacrawl.md`** - Complete CLI command reference (config-based and URL-based commands)
- **`40-usage/USAGE_GUIDE.md`** - Operator-focused guide: defaults, environment variables, troubleshooting
- **`40-usage/creating-site-configs-supacrawl.md`** - How to create and configure site YAML files

## Reliability

- **`70-reliability/error-handling-supacrawl.md`** - Error handling patterns and exception hierarchy
- **`70-reliability/retry-logic-supacrawl.md`** - Retry logic implementation and patterns
- **`70-reliability/testing-supacrawl.md`** - Testing strategies and patterns

## Schemas

- **`supacrawl/schemas/snapshot-manifest.schema.json`** - JSON schema for snapshot manifest validation

## Quick Reference

### Site Configuration Workflow (Recommended)

```bash
# List sites, create config, crawl, chunk
supacrawl list-sites
supacrawl init my-site
supacrawl crawl my-site
supacrawl chunk my-site latest
```

### URL-Based Workflow (Firecrawl-compatible)

```bash
# Single URL
supacrawl scrape-url https://example.com

# Multiple URLs
supacrawl batch-scrape urls.txt

# Crawl from URL
supacrawl crawl-url https://example.com --limit 50

# Map URLs
supacrawl map-url https://example.com
```

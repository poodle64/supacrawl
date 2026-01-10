# Documentation Index

## Architecture

- **`30-architecture/data-flow-llm.md`** - Data flow and LLM integration patterns
- **`30-architecture/snapshot-contract.md`** - Output manifest contract

## Usage

- **`40-usage/cli-usage-supacrawl.md`** - Complete CLI command reference with environment variables and troubleshooting

## Reliability

- **`70-reliability/error-handling-supacrawl.md`** - Error handling patterns and exception hierarchy
- **`70-reliability/retry-logic-supacrawl.md`** - Retry logic implementation and patterns
- **`70-reliability/testing-supacrawl.md`** - Testing strategies and patterns

## Quick Reference

### Core Commands

```bash
# Scrape a single URL
supacrawl scrape https://example.com

# Crawl a website (with URL discovery)
supacrawl crawl https://example.com --output corpus/ --limit 50

# Map URLs (discover without scraping)
supacrawl map https://example.com

# Web search
supacrawl search "query" --limit 10

# LLM-based extraction
supacrawl llm-extract https://example.com --prompt "Extract product info"

# Autonomous agent
supacrawl agent "Find pricing information for Product X"
```

### Cache Management

```bash
supacrawl cache stats   # Show cache statistics
supacrawl cache clear   # Clear all cached entries
supacrawl cache prune   # Remove expired entries
```

# Supacrawl Usage Guide

This guide explains how to run the scraper with quality-focused defaults and tune behaviour via environment variables.

## Quick Start

1) Install and set up browsers:
```bash
pip install -e .
playwright install chromium
```

2) Copy and edit `.env` if needed:
```bash
cp .env.example .env
```

3) Scrape a URL:
```bash
supacrawl scrape https://example.com
```

4) Crawl a website:
```bash
supacrawl crawl https://example.com --output corpus/ --limit 50
```

## Defaults That Maximise Quality

- **Stealth + realistic headers** with Chrome 131 user agent and realistic browser headers (Accept, Accept-Encoding, DNT, Connection, Upgrade-Insecure-Requests).
- **Smart wait strategies**: `networkidle` wait for JavaScript-heavy pages to ensure content is fully loaded.
- **Main content extraction**: Removes navigation, headers, footers with `--only-main-content` (default: true).
- **Markdown fidelity**: Preserves links, tables, code blocks using markdownify converter.
- **Retry/backoff** on transient errors; skips retries on 4xx failures.

## Key Environment Variables

### Browser Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `SUPACRAWL_HEADLESS` | `true` | Visible browser when `false` (good for debugging) |
| `SUPACRAWL_USER_AGENT` | Chrome 131 | Custom user agent string |
| `SUPACRAWL_ACCEPT_LANGUAGE` | `en-US,en;q=0.8` | Accept-Language header |
| `SUPACRAWL_PROXY` | _unset_ | Proxy URL for geo/anti-bot |
| `SUPACRAWL_USE_MANAGED_BROWSER` | `false` | Reuse a persistent profile |
| `SUPACRAWL_VIEWPORT_WIDTH` / `SUPACRAWL_VIEWPORT_HEIGHT` | `1280` / `720` | Viewport sizing |

### Wait Strategies

| Variable | Default | Purpose |
| --- | --- | --- |
| `SUPACRAWL_WAIT_UNTIL` | `networkidle` | Wait strategy: `domcontentloaded`, `networkidle`, `load` |

### Cache Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `SUPACRAWL_CACHE_DIR` | `~/.supacrawl/cache` | Cache directory location |

### Retry Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `SUPACRAWL_RETRY_ATTEMPTS` | `3` | Number of retry attempts |
| `SUPACRAWL_RETRY_BASE_DELAY` | `1.0` | Base delay in seconds |
| `SUPACRAWL_RETRY_BACKOFF` | `2.0` | Backoff multiplier |
| `SUPACRAWL_RETRY_JITTER` | `0.1` | Jitter factor |

## Crawl Output

The `crawl` command writes markdown files to the output directory:

```
output/
  manifest.json    # Tracks scraped URLs for resume
  index.md         # Content with YAML frontmatter
  about.md
  blog_post-1.md
```

Each markdown file includes YAML frontmatter with metadata:
```markdown
---
source_url: https://example.com/about
title: About Us
---
# About Us
...
```

Use `--resume` to continue an interrupted crawl.

## Content Extraction

When `--only-main-content` is enabled (default), the scraper:
- Extracts main content only (removes boilerplate)
- Removes navigation, headers, footers
- Preserves headings, code blocks, tables, examples

Use `--no-only-main-content` to keep full page content.

## Using Cache

Enable caching for repeated requests:
```bash
supacrawl scrape https://example.com --max-age 3600
```

Manage cache:
```bash
supacrawl cache stats   # Show statistics
supacrawl cache clear   # Clear all entries
supacrawl cache prune   # Remove expired entries
```

## Troubleshooting

- Run `playwright install chromium` to verify Playwright browsers are installed.
- For 4xx client errors, fix cookies/auth/proxy; retries are skipped by design.
- For rate limits, adjust `SUPACRAWL_RETRY_*` environment variables.
- Use `--stealth` for bot-protected sites (requires `pip install supacrawl[stealth]`).
- Use `--solve-captcha` for CAPTCHA-protected sites (requires `pip install supacrawl[captcha]` and `CAPTCHA_API_KEY`).

# Web-Scraper Usage Guide

This guide explains how to run the crawler with the quality-focused defaults and how to tune behavior via environment variables.

## Quick Start

1) Install and set up browsers once:
```bash
pip install -e .
playwright install chromium
```
2) Copy and edit `.env` if needed:
```bash
cp .env.example .env
```
3) Run a crawl from a site YAML (e.g., `sites/meta.yaml`):
```bash
web-scraper crawl meta
```
Snapshots are written to `corpora/<site_id>/<snapshot_id>/`.

## Defaults That Maximise Quality

- **Stealth + realistic headers** with Chrome 131 user agent and realistic browser headers (Accept, Accept-Encoding, DNT, Connection, Upgrade-Insecure-Requests).
- **Smart wait strategies**: `networkidle` wait for JavaScript-heavy pages to ensure content is fully loaded.
- **Main content extraction**: Removes navigation, headers, footers when `only_main_content: true`.
- **Markdown fidelity**: Preserves links, tables, code blocks using markdownify converter.
- **Retry/backoff** on transient errors; skips retries on 4xx failures.
- **Snapshot versioning**: Each crawl creates a timestamped snapshot for reproducibility.

## Key Environment Toggles

### Browser Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `WEB_SCRAPER_HEADLESS` | `true` | Visible browser when `false` (good for debugging) |
| `WEB_SCRAPER_USER_AGENT` | Chrome 131 | Custom user agent string (default: Chrome 131) |
| `WEB_SCRAPER_ACCEPT_LANGUAGE` | `en-US,en;q=0.8` | Accept-Language header |
| `WEB_SCRAPER_PROXY` | _unset_ | Proxy URL for geo/anti-bot |
| `WEB_SCRAPER_USE_MANAGED_BROWSER` | `false` | Reuse a persistent profile (set `WEB_SCRAPER_USER_DATA_DIR`) |
| `WEB_SCRAPER_VIEWPORT_WIDTH` / `WEB_SCRAPER_VIEWPORT_HEIGHT` | `1280` / `720` | Viewport sizing |

### Wait Strategies

| Variable | Default | Purpose |
| --- | --- | --- |
| `WEB_SCRAPER_WAIT_UNTIL` | `networkidle` | Wait strategy: `domcontentloaded`, `networkidle`, `load` (default: `networkidle` for better JavaScript handling) |

### Other Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `WEB_SCRAPER_CACHE_ENABLED` | `false` | Enable cache when content is stable |
| `WEB_SCRAPER_RETRY_ATTEMPTS` | `3` | Crawl retries; base delay/backoff/jitter via `WEB_SCRAPER_RETRY_BASE_DELAY`, `WEB_SCRAPER_RETRY_BACKOFF`, `WEB_SCRAPER_RETRY_JITTER` |

## Running the Meta Docs Example

```bash
# optional: persistent profile for authenticated or strict sites
WEB_SCRAPER_USE_MANAGED_BROWSER=true \
WEB_SCRAPER_USER_DATA_DIR=/path/to/profile \
web-scraper crawl meta
```

Tips:
- Leave cache off for changing docs; enable it for stable references.
- If pages are blocked, set `WEB_SCRAPER_PROXY` and/or use a managed profile.
- Use `only_main_content: true` in site config to extract main content and remove boilerplate.

## Snapshot Layout

Each run writes a manifest and markdown pages under `corpora/<site_id>/<snapshot_id>/`. Use `web-scraper chunk <site_id> <snapshot_id>` to produce JSONL chunks for downstream LLM consumption.

## Content Extraction

When `only_main_content: true` in site configuration, the scraper extracts main content only (cleaned content with boilerplate removed). When `only_main_content: false`, it uses full page content. The extraction process removes navigation, headers, footers, and other boilerplate while preserving main content (headings, code blocks, tables, examples).

## Markdown Fix Plugins

Web-scraper includes a plugin-based system for fixing markdown quality issues that arise from upstream markdown conversion missing certain patterns. Each fix is a separate, independently configurable plugin.

**List all fixes**: `web-scraper list-fixes`

**Enable/disable fixes**: Configure in site YAML (see `sites/template.yaml` for example)

**Current fixes**:
- `missing-link-text-in-lists`: Fixes missing link text in nested `<strong><a>` structures

See `docs/40-usage/markdown-fixes.md` for complete documentation on the fix plugin system, including how to add new fixes and periodically review if they're still needed.

## Troubleshooting

- Run `playwright install chromium` to verify Playwright browsers are installed.
- For 4xx client errors, fix cookies/auth/proxy; retries are skipped by design.
- For rate limits, adjust `WEB_SCRAPER_RETRY_*` environment variables for crawl retries.

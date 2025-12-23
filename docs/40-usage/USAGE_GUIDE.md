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

## Defaults That Maximize Quality

- **Stealth + realistic headers** with Chrome 131 user agent and realistic browser headers (Accept, Accept-Encoding, DNT, Connection, Upgrade-Insecure-Requests).
- **Smart wait strategies**: `networkidle` wait for JavaScript-heavy pages, `wait_for_images` when extracting main content.
- **Content filters**: PruningContentFilter enabled by default to remove boilerplate (nav, footer, ads).
- **Markdown fidelity**: keeps links, tables, code; uses `fit_markdown` when `only_main_content: true`; optional LLM content filter.
- **Best-first crawling** with keyword scoring derived from YAML `include` + entrypoints; falls back to BFS.
- **Retry/backoff** on transient errors; skips retries on detected 4xx failures.
- **Cache** defaults to BYPASS to stay fresh; opt-in when sources are stable.

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

### Content Filters

| Variable | Default | Purpose |
| --- | --- | --- |
| `WEB_SCRAPER_CONTENT_FILTER` | `pruning` | Content filter type: `pruning` (default), `bm25`, `none` |
| `WEB_SCRAPER_PRUNING_THRESHOLD` | `0.5` | PruningContentFilter threshold (0.0-1.0) |
| `WEB_SCRAPER_PRUNING_THRESHOLD_TYPE` | `dynamic` | Pruning threshold type: `fixed` or `dynamic` |
| `WEB_SCRAPER_PRUNING_MIN_WORDS` | `20` | Minimum words per block for PruningContentFilter |
| `WEB_SCRAPER_BM25_THRESHOLD` | `1.2` | BM25ContentFilter relevance threshold (higher = stricter) |

### LLM Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `WEB_SCRAPER_LLM_PROVIDER` | _unset_ | e.g., `openai/gpt-4o-mini`, `ollama/llama3.2` (uses `WEB_SCRAPER_LLM_API_TOKEN`/`WEB_SCRAPER_LLM_BASE_URL` if set) |
| `WEB_SCRAPER_LLM_FILTER` | `false` | Apply LLM content filter to keep only main docs |
| `WEB_SCRAPER_LLM_FILTER_INSTRUCTION` | _(default)_ | Custom instruction for LLM content filter |
| `WEB_SCRAPER_LLM_FILTER_CHUNK_TOKENS` | `1000` | Chunk token threshold for LLM filter (default: 1000, increased from 800) |
| `WEB_SCRAPER_LLM_FILTER_VERBOSE` | `false` | Enable verbose logging for LLM filter |

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
- Content filters are enabled by default (PruningContentFilter) to remove boilerplate.
- For query-focused scraping, set `WEB_SCRAPER_CONTENT_FILTER=bm25` to use BM25ContentFilter.
- If results are still noisy, enable `WEB_SCRAPER_LLM_FILTER=true` for advanced LLM-based filtering.

## Snapshot Layout

Each run writes a manifest and markdown pages under `corpora/<site_id>/<snapshot_id>/`. Use `web-scraper chunk <site_id> <snapshot_id>` to produce JSONL chunks for downstream LLM consumption.

## Markdown Types

When `only_main_content: true` in site configuration, the scraper uses `fit_markdown` (cleaned content with content filters applied). When `only_main_content: false`, it uses `raw_markdown` (full page content). Content filters (PruningContentFilter or BM25ContentFilter) are applied during markdown generation to remove boilerplate while preserving main content (headings, code blocks, tables, examples).

## Markdown Fix Plugins

Web-scraper includes a plugin-based system for fixing markdown quality issues that arise from upstream markdown conversion missing certain patterns. Each fix is a separate, independently configurable plugin.

**List all fixes**: `web-scraper list-fixes`

**Enable/disable fixes**: Configure in site YAML (see `sites/template.yaml` for example)

**Current fixes**:
- `missing-link-text-in-lists`: Fixes missing link text in nested `<strong><a>` structures

See `docs/40-usage/markdown-fixes.md` for complete documentation on the fix plugin system, including how to add new fixes and periodically review if they're still needed.

## Content Filter Strategies

### PruningContentFilter (Default)

Removes boilerplate content (navigation, footers, ads) based on content density and link density analysis. Enabled by default via `WEB_SCRAPER_CONTENT_FILTER=pruning`.

**When to use:** General-purpose scraping where you want clean content without specific query focus.

### BM25ContentFilter (Optional)

Focuses on content relevant to extracted keywords from site configuration (name and entrypoints). Use `WEB_SCRAPER_CONTENT_FILTER=bm25` to enable.

**When to use:** Query-focused scraping (e.g., documentation sites, API references) where you have specific content focus.

### LLMContentFilter (Advanced)

Uses LLM to intelligently filter content based on natural language instructions. Enable with `WEB_SCRAPER_LLM_FILTER=true` and configure LLM provider.

**When to use:** When you need sophisticated content filtering and have an LLM provider configured. Works alongside content filters (LLM filter takes precedence if both enabled).

## Troubleshooting

- Run `playwright install chromium` to verify Playwright browsers are installed.
- For 4xx client errors, fix cookies/auth/proxy; retries are skipped by design.
- For rate limits, adjust `WEB_SCRAPER_RETRY_*` environment variables for crawl retries.

# Web-Scraper Usage Guide

This guide explains how to run the crawler with the quality-focused defaults baked into `Crawl4AIScraper` and how to tune behavior via environment variables. It is written so future operators (including LLMs) can run effective scrapes without deep Crawl4AI knowledge.

## Quick Start

1) Install and set up browsers once:
```bash
pip install -e .
crawl4ai-setup
crawl4ai-doctor
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
| `CRAWL4AI_HEADLESS` | `true` | Visible browser when `false` (good for debugging) |
| `CRAWL4AI_USER_AGENT` | Chrome 131 | Custom user agent string (default: Chrome 131) |
| `CRAWL4AI_ACCEPT_LANGUAGE` | `en-US,en;q=0.8` | Accept-Language header |
| `CRAWL4AI_PROXY` | _unset_ | Proxy URL for geo/anti-bot |
| `CRAWL4AI_USE_MANAGED_BROWSER` | `false` | Reuse a persistent profile (set `CRAWL4AI_USER_DATA_DIR`) |
| `CRAWL4AI_VIEWPORT_WIDTH` / `CRAWL4AI_VIEWPORT_HEIGHT` | `1280` / `720` | Viewport sizing |

### Wait Strategies

| Variable | Default | Purpose |
| --- | --- | --- |
| `CRAWL4AI_WAIT_UNTIL` | `networkidle` | Wait strategy: `domcontentloaded`, `networkidle`, `load` (default: `networkidle` for better JavaScript handling) |

### Content Filters

| Variable | Default | Purpose |
| --- | --- | --- |
| `CRAWL4AI_CONTENT_FILTER` | `pruning` | Content filter type: `pruning` (default), `bm25`, `none` |
| `CRAWL4AI_PRUNING_THRESHOLD` | `0.5` | PruningContentFilter threshold (0.0-1.0) |
| `CRAWL4AI_PRUNING_THRESHOLD_TYPE` | `dynamic` | Pruning threshold type: `fixed` or `dynamic` |
| `CRAWL4AI_PRUNING_MIN_WORDS` | `20` | Minimum words per block for PruningContentFilter |
| `CRAWL4AI_BM25_THRESHOLD` | `1.2` | BM25ContentFilter relevance threshold (higher = stricter) |

### LLM Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `CRAWL4AI_LLM_PROVIDER` | _unset_ | e.g., `openai/gpt-4o-mini`, `ollama/llama3.2` (uses `CRAWL4AI_LLM_API_TOKEN`/`CRAWL4AI_LLM_BASE_URL` if set) |
| `CRAWL4AI_LLM_FILTER` | `false` | Apply LLM content filter to keep only main docs |
| `CRAWL4AI_LLM_FILTER_INSTRUCTION` | _(default)_ | Custom instruction for LLM content filter |
| `CRAWL4AI_LLM_FILTER_CHUNK_TOKENS` | `1000` | Chunk token threshold for LLM filter (default: 1000, increased from 800) |
| `CRAWL4AI_LLM_FILTER_VERBOSE` | `false` | Enable verbose logging for LLM filter |

### Other Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `CRAWL4AI_CACHE_ENABLED` | `false` | Enable cache when content is stable |
| `CRAWL4AI_RETRY_ATTEMPTS` | `3` | Crawl retries; base delay/backoff/jitter via `CRAWL4AI_RETRY_BASE_DELAY`, `CRAWL4AI_RETRY_BACKOFF`, `CRAWL4AI_RETRY_JITTER` |

## Running the Meta Docs Example

```bash
# optional: persistent profile for authenticated or strict sites
CRAWL4AI_USE_MANAGED_BROWSER=true \
CRAWL4AI_USER_DATA_DIR=/path/to/profile \
web-scraper crawl meta
```

Tips:
- Leave cache off for changing docs; enable it for stable references.
- If pages are blocked, set `CRAWL4AI_PROXY` and/or use a managed profile.
- Content filters are enabled by default (PruningContentFilter) to remove boilerplate.
- For query-focused scraping, set `CRAWL4AI_CONTENT_FILTER=bm25` to use BM25ContentFilter.
- If results are still noisy, enable `CRAWL4AI_LLM_FILTER=true` for advanced LLM-based filtering.

## Snapshot Layout

Each run writes a manifest and markdown pages under `corpora/<site_id>/<snapshot_id>/`. Use `web-scraper chunk <site_id> <snapshot_id>` to produce JSONL chunks for downstream LLM consumption.

## Markdown Types

When `only_main_content: true` in site configuration, the scraper uses `fit_markdown` (cleaned content with content filters applied). When `only_main_content: false`, it uses `raw_markdown` (full page content). Content filters (PruningContentFilter or BM25ContentFilter) are applied during markdown generation to remove boilerplate while preserving main content (headings, code blocks, tables, examples).

## Markdown Fix Plugins

Web-scraper includes a plugin-based system for fixing markdown quality issues that arise from upstream tools (like Crawl4AI) missing certain patterns. Each fix is a separate, independently configurable plugin.

**List all fixes**: `web-scraper list-fixes`

**Enable/disable fixes**: Configure in site YAML (see `sites/template.yaml` for example)

**Current fixes**:
- `missing-link-text-in-lists`: Fixes missing link text in nested `<strong><a>` structures

See `docs/40-usage/markdown-fixes.md` for complete documentation on the fix plugin system, including how to add new fixes and periodically review if they're still needed.

## Content Filter Strategies

### PruningContentFilter (Default)

Removes boilerplate content (navigation, footers, ads) based on content density and link density analysis. Enabled by default via `CRAWL4AI_CONTENT_FILTER=pruning`.

**When to use:** General-purpose scraping where you want clean content without specific query focus.

### BM25ContentFilter (Optional)

Focuses on content relevant to extracted keywords from site configuration (name and entrypoints). Use `CRAWL4AI_CONTENT_FILTER=bm25` to enable.

**When to use:** Query-focused scraping (e.g., documentation sites, API references) where you have specific content focus.

### LLMContentFilter (Advanced)

Uses LLM to intelligently filter content based on natural language instructions. Enable with `CRAWL4AI_LLM_FILTER=true` and configure LLM provider.

**When to use:** When you need sophisticated content filtering and have an LLM provider configured. Works alongside content filters (LLM filter takes precedence if both enabled).

## Troubleshooting

- Run `crawl4ai-doctor` to verify Playwright browsers.
- For 4xx client errors, fix cookies/auth/proxy; retries are skipped by design.
- For rate limits, increase `CRAWL4AI_LLM_BACKOFF_*` (if using LLM extraction) or `CRAWL4AI_RETRY_*` for crawl retries.

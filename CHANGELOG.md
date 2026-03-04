# Changelog

All notable changes to supacrawl will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to calendar-based versioning (YYYY.MM.x format).

## [Unreleased]

## [2026.3.0] - 2026-03-04

### Features

- **Multi-provider search with automatic fallback** (Closes #101): Refactored monolithic search into a pluggable provider architecture. Supports 6 providers (Brave, Tavily, Serper, SerpAPI, Exa, DuckDuckGo) with automatic fallback on quota exhaustion, rate limiting, or CAPTCHA detection. Configure via `SUPACRAWL_SEARCH_PROVIDERS` env var or `--provider` CLI flag
- **Configurable search rate limiting** (Closes #99): New `SUPACRAWL_SEARCH_RATE_LIMIT` env var. Enhanced health endpoint shows per-provider status and rate limit configuration
- **Brave Search as default provider** (Closes #95): Brave Search replaces DuckDuckGo as the default. DuckDuckGo is deprecated but remains as a last-resort fallback
- **Realistic browser headers for search** (Closes #96): Search requests use full browser-like headers (User-Agent, Sec-CH-UA, Accept-Language) to avoid bot detection. Locale-aware via `SUPACRAWL_LOCALE`
- **Camoufox anti-detection engine** (Closes #80): New `--engine camoufox` option provides Tier 3 anti-bot protection using patched Firefox. Effective against Akamai Bot Manager and advanced TLS fingerprinting. Install: `pip install supacrawl[camoufox]`
- **Change tracking** (Closes #81): New `-f changeTracking` format detects content changes between scrapes by comparing against cached previous versions. Supports `--change-tracking-modes git-diff` for unified diffs
- **PDF URL parsing** (Closes #82): Auto-detects `.pdf` URLs and extracts text directly, bypassing the browser. OCR fallback available via `pip install supacrawl[pdf-ocr]`. Controlled with `--parse-pdf [auto|fast|ocr|off]`
- **Mobile device emulation** (Closes #83): New `--mobile` and `--device TEXT` flags for scraping as mobile devices using Playwright device descriptors. Use `--list-devices` to see available presets
- **Iframe content extraction** (Closes #85): New `--expand-iframes [none|same-origin|all]` option (default: same-origin) expands iframe content inline during scraping
- **JSON comparison mode for change tracking** (Closes #87): `--change-tracking-modes json` compares structured extracted fields between scrapes
- **Change tracking in crawl** (Closes #88): `-f changeTracking` now works in the `crawl` command with `--change-tracking-modes` and `--cache-dir` support
- **Per-request engine in MCP tools** (Closes #90): `engine` parameter on `supacrawl_scrape` and `supacrawl_crawl` MCP tools allows per-request engine selection. Server default configurable via `SUPACRAWL_ENGINE` environment variable

### Fixed

- **DuckDuckGo CAPTCHA detection** (Closes #97): Detect and report CAPTCHA challenges from DuckDuckGo instead of returning empty results
- **ERR_HTTP2_PROTOCOL_ERROR automatic fallback** (Closes #92): Two-stage auto-retry chain (Chromium to Camoufox to Camoufox + HTTP/1.1) handles servers that reject Chromium's TLS fingerprint
- **Camoufox async wrapper** (Closes #91): Use correct `AsyncCamoufox` context manager instead of `AsyncNewBrowser`
- **CLI ScrapeService resource leak**: ScrapeService is now properly closed in the CLI search command's finally block

### Performance

- **Reduced scrape overhead by ~1.7s per page** (Closes #89): Removed unnecessary PDF HEAD request from the scrape hot path

## [2026.2.3] - 2026-02-26

### Fixed

- **Playwright version constraint** (Closes #79): Relaxed from `>=1.49.0` to `>=1.40.0,<2.0.0`. Supacrawl only uses stable core Playwright APIs, so the previous lower bound was unnecessarily restrictive. This allows distributions like NixOS and Guix to pair supacrawl with their system-provided Playwright browser binaries

### Documentation

- Added "System-Managed Playwright Browsers" section to README for users with distro-provided Playwright binaries

### Internal

- CI: use reusable auto-label workflow from master project

## [2026.2.2] - 2026-02-22

### Features

- **CSS background-image extraction**: Extract image URLs from CSS `background-image` and `background` shorthand properties, improving image discovery on sites that use CSS for hero images and backgrounds
- **Improved logo detection**: Better logo identification for site builders (Wix `<wow-image>`, Squarespace `data-section-type`, Framer `data-framer-name`) and nested `<img>` elements inside `role="img"` containers
- **Correlation IDs in MCP responses**: All MCP tool responses now include `correlation_id` for request tracing and debugging
- **WordPress and CSS counter preprocessors**: New site-specific preprocessors for WordPress content and CSS counter-based ordered lists, producing cleaner markdown output
- **MCP map `ignore_cache` parameter**: New parameter to bypass cached URL discovery results
- **MCP map title fallback and timezone detection**: Map results include `<title>` tag fallback for pages without `<meta>` titles, and automatic timezone detection from page content

### Fixed

- **MCP headless browser windows** (Closes #78): Browser windows no longer flash visibly during MCP operations. The `headless` parameter now propagates to all internal `BrowserManager` instances, including CAPTCHA solving and stealth retry paths
- **Screenshot cache key collision**: `screenshot_full_page` setting is now included in the cache key, preventing incorrect cache hits when the same URL is scraped with different screenshot settings
- **CrawlService browser lifecycle**: CrawlService now accepts an injected `BrowserManager`, avoiding duplicate browser instances when used from the MCP server

### Internal

- Remove Docker MCP files (`Dockerfile.mcp`, `docker-compose.mcp.yaml`); MCP server now runs natively via `supacrawl-mcp`
- Add MCP server section to README with installation and configuration instructions

## [2026.2.1] - 2026-02-21

### Features

- **Embedded MCP server**: the MCP server is now bundled as an optional extra (`pip install supacrawl[mcp]`), replacing the standalone server in `mcp-servers`. Includes all tools (scrape, crawl, map, search, extract, summary, diagnose, health), prompts, resources, structured logging, correlation IDs, exception mapping, and input validation. Install and run with `supacrawl-mcp --transport stdio`.
- Docker support for running the MCP server (`Dockerfile.mcp`, `docker-compose.mcp.yaml`)

### Fixed

- Remove duplicate `supacrawl_health` tool registration in MCP server
- MCP exception mapping gap: internal errors now correctly map to JSON-RPC error codes (Closes #69)

## [2026.2.0] - 2026-02-16

### Fixed

- Strip `javascript:` pseudo-protocol links completely during HTML to markdown conversion. These UI controls (print, share, email buttons) are now removed entirely following industry best practice from Readability.js, Newspaper3k, and Trafilatura. Fixes #67.

### Internal

- Add auto-label workflow for GitHub issues with AI-powered classification
- Ignore issue archive directories in git

## [2026.1.0] - 2026-01-12

Initial public release.

### Features

- **scrape** - Extract content from a single URL as markdown, HTML, or JSON
- **crawl** - Crawl websites with URL discovery, resume support, and parallel processing
- **map** - Discover URLs from sitemaps and page links with streaming progress
- **search** - Web search via DuckDuckGo or Brave with optional scraping
- **llm-extract** - LLM-powered structured data extraction
- **agent** - Autonomous web agent for multi-step data gathering
- **cache** - Local caching with statistics and pruning

### Capabilities

- Playwright-based browser automation with anti-bot evasion
- Optional enhanced stealth mode via Patchright (`pip install supacrawl[stealth]`)
- Optional CAPTCHA solving via 2Captcha (`pip install supacrawl[captcha]`)
- Page actions: click, scroll, wait, type, screenshot, JavaScript execution
- Multiple output formats: markdown, HTML, rawHtml, links, images, screenshot, PDF, JSON
- LLM integration: Ollama (local), OpenAI, Anthropic
- Site-specific preprocessors for improved markdown output (MkDocs Material, etc.)
- Proxy support with authentication
- Locale settings: country, language, timezone
- Python 3.12+ support

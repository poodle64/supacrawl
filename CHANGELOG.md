# Changelog

All notable changes to supacrawl will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to calendar-based versioning (YYYY.MM.x format).

## [Unreleased]

## [2026.1.7] - 2026-01-10

### Features

- **Site preprocessor registry for improved markdown output** - Added extensible registry system for site-specific HTML preprocessing. Includes MkDocs Material handler that auto-detects and improves output for documentation sites using this popular theme (FastAPI, Pydantic, etc.). Fixes: permalink anchors in headings, line-numbered code tables, admonition blocks, and tabbed content panels (#63, #64)

### Internal

- **17 new converter tests** - Comprehensive test coverage for MkDocs preprocessing (8 tests) and registry mechanics (9 tests)

## [2026.1.6] - 2026-01-04

### Bug Fixes

- **Improve CAPTCHA warning message clarity** - When CAPTCHA elements are detected but content is extracted successfully (≥50 words), now logs at INFO level: "CAPTCHA element detected (content extracted successfully)". Only shows WARNING with solve hints when content extraction may have failed. Resolves misleading warnings on sites that embed CAPTCHA elements without blocking access (#56)
- **Add mypy config for twocaptcha stubs** - Ignore missing type stubs for twocaptcha package

### Documentation

- **README refresh** - New centred header with shields.io badges, "Why Supacrawl?" value proposition, updated architecture diagram featuring ragify as downstream processor

### Internal

- **Apply PEP 758 simplified except syntax** - Use modern `except ExceptionGroup:` syntax throughout codebase (#51)
- **Standardise .gitignore** - Align with master project template
- **Enhance logging with Rich** - Improved log formatting and removed outdated documentation
- **Simplify .envrc** - Hybrid Nix/conda configuration with cleaner logic
- **Remove VERSION file** - Use pyproject.toml as single source of truth for version

## [2026.1.5] - 2026-01-02

### Features

- **Python 3.14 native annotation support** - Removed `from __future__ import annotations` from all 42 Python files, leveraging PEP 649's deferred annotation evaluation. The project now requires Python 3.14+ (#53)

### Bug Fixes

- **Fix Python 2 exception syntax in llm/config.py** - Corrected `except A, B:` to `except (A, B):`
- **Fix mypy type error in llm/client.py** - Added type narrowing for api_key parameter

## [2026.1.4] - 2026-01-01

### Bug Fixes

- **Change default page load strategy to 'load'** - The default wait strategy is now `load` instead of `domcontentloaded`, which waits for all resources (images, CSS, scripts) to finish loading. This dramatically improves URL discovery on JS-heavy sites without requiring users to know about `--wait-until`. Testing showed 175 vs 300 URLs discovered on Facebook developer docs (#50)

## [2026.1.3] - 2026-01-01

### Bug Fixes

- **Fix missing stealth scripts in map command** - `extract_links()` now injects basic stealth scripts (webdriver hiding, plugins, WebGL spoofing) like `fetch_page()` does, reducing bot detection on protected sites when using `supacrawl map` (#48)
- **Use browser defaults to reduce fingerprint mismatch** - When no locale config or user agent is explicitly set, supacrawl now uses Playwright's browser defaults instead of forcing a Windows user agent and custom headers. This reduces bot detection on sites that detect OS/user-agent mismatches (#48)
- **Skip SPA polling when using networkidle** - When `--wait-until networkidle` is specified, skip the SPA stability check and fixed delay that can trigger bot detection. The networkidle strategy already waits for JavaScript to finish, making extra polling redundant and detectable (#49)

## [2026.1.2] - 2026-01-01

### Features

- **Page load strategy option** - Added `--wait-until` CLI option to `scrape`, `map`, and `crawl` commands for controlling page load strategy (commit, domcontentloaded, load, networkidle). Falls back to `SUPACRAWL_WAIT_UNTIL` env var if not specified (#47)

## [2026.1.1] - 2026-01-01

### Features

- **Parallel URL processing** - MapService now processes URLs concurrently during BFS crawl and metadata extraction, providing up to 5x faster mapping for typical websites (#46)
- **Concurrency control** - New `concurrency` parameter in MapService and CrawlService (default: 10) controls max parallel requests
- **CLI concurrency option** - Added `-c/--concurrency` flag to both `supacrawl map` and `supacrawl crawl` commands

## [2026.1.0] - 2026-01-01

### Features

- **map_all() convenience method** - Added `MapService.map_all()` that returns `MapResult` directly, providing a simple await-able interface for callers who don't need streaming progress events (#45)

### Breaking Changes

- **MapService.map() is now an async generator** - The `map()` method yields `MapEvent` objects for streaming progress. Callers using `await map_service.map()` must migrate to `await map_service.map_all()` for the previous behaviour

## [2025.12.1] - 2025-12-30

### Features

- **Streaming map progress** - `MapService.map()` now yields progress events during URL discovery, providing real-time feedback during sitemap fetch, BFS crawl, and metadata extraction phases (#43)
- **CrawlEvent mapping type** - `CrawlService.crawl()` translates map progress to `CrawlEvent(type="mapping")`, giving consumers visibility during the potentially long mapping phase
- **save_files parameter** - New `save_files` parameter in `crawl()` allows manifest tracking for resume capability without saving content files to disk (#44)

### Models

- Added `MapEvent` model for streaming progress during map operations
- Extended `CrawlEvent` with `type="mapping"` and `message` field

## [2025.12.0] - 2025-12-27

Initial release.

### Features

- **scrape** - Extract content from a single URL as markdown, HTML, or JSON
- **crawl** - Crawl websites with URL discovery and resume support
- **map** - Discover URLs from sitemaps and page links
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
- Proxy support with authentication
- Locale settings: country, language, timezone

# Changelog

All notable changes to supacrawl will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to calendar-based versioning (YYYY.MM.x format).

## [Unreleased]

## [2025.12.4] - 2025-12-26

### Changed

- **CLI modularised**: Split monolithic `cli.py` (2274 lines) into `cli/` package with separate modules for each command group (scrape, crawl, map, sites, corpus, agent, cache)
- **LLM client extracted**: Moved `ollama_client.py` to dedicated `llm/` package with separate config module

### Internal

- Services updated to use new `llm.client` module
- Preparation for CLI simplification (removing dual command pattern)

## [2025.12.3] - 2025-12-26

### Added

- **Cache service**: Local caching for scraped content with configurable expiry, statistics, and pruning. Use `--max-age` with `scrape-url` to enable caching, manage with `supacrawl cache` subcommands
- **Actions service**: Page interaction actions for complex scraping workflows (click, scroll, wait, screenshot, form filling)
- **Branding extraction**: Extract brand identity (colours, fonts, logos, typography) from pages with `--format branding`
- **CAPTCHA solving**: Optional 2Captcha integration for solving reCAPTCHA, hCaptcha, and Turnstile. Install with `pip install supacrawl[captcha]`
- **Stealth mode**: Patchright-based stealth browsing for bot-protected sites. Install with `pip install supacrawl[stealth]`
- **New CLI commands**: `search`, `llm-extract`, `agent`, `cache` for Firecrawl-compatible workflows

### Changed

- **Dynamic version loading**: Package version now read from `pyproject.toml` via `importlib.metadata`, eliminating version drift between files

### Fixed

- Fixed 23 mypy type errors across cache, captcha, branding, browser, and scrape services
- Fixed `.claude/CLAUDE.md` references to use correct `.cursor/rules/` path
- Fixed `docs/README.md` schema reference path
- Fixed CLI documentation to include all Firecrawl-compatible commands

### Internal

- Removed completed `FIRECRAWL_PARITY_PLAN.md`
- Enhanced test coverage for new services
- Improved type annotations throughout

## [2025.12.2] - 2025-12-25

### Breaking Changes

- **Project renamed from `web_scraper` to `supacrawl`**: Complete package rename affecting all imports, CLI commands, and references. Users must update:
  - All imports from `from web_scraper import ...` to `from supacrawl import ...`
  - CLI commands from `web_scraper` to `supacrawl`
  - Any configuration or scripts referencing the old package name
- **Package structure relocated**: Source code moved from `web_scraper/` to `src/supacrawl/` following modern Python packaging layout

### Added

- **Firecrawl parity services**: New `agent`, `extract`, and `search` services for enhanced web scraping capabilities
- **Firecrawl parity plan**: Documentation outlining roadmap for Firecrawl API compatibility

### Internal

- All cursor rules renamed from `*-web-scraper.mdc` to `*-supacrawl.mdc`
- All documentation renamed from `*-web-scraper.md` to `*-supacrawl.md`
- Updated all test imports to use new package name
- Updated environment configuration and examples for new package name

## [2025.12.1] - 2025-12-25

### Breaking Changes

- **Removed Crawl4AI dependency**: Complete migration from Crawl4AI to native Playwright implementation. All Crawl4AI-specific code, configuration, and dependencies have been removed. Users must update any custom code that relied on Crawl4AI-specific features.
- **Removed markdown fixes framework**: The custom markdown fixes system has been removed in favour of markdownify's built-in conversion. Any site configurations referencing markdown fixes will need to be updated.
- **Removed language detection**: Language detection that was stripping code blocks has been removed. Content extraction now preserves all code blocks by default.
- **Service architecture refactoring**: Major refactoring of the service layer. Internal service interfaces have changed, though CLI commands remain compatible.

### Added

- **New CLI commands**: Added `map`, `scrape`, `crawl`, and `batch-scrape` commands for comprehensive website ingestion workflows
- **LLM-assisted content identification**: Experimental feature for using local LLMs (via Ollama) to identify and extract main content
- **Progress bars**: Visual progress indicators for long-running crawl operations
- **Format options**: `--format` option for `crawl-url` command to specify output formats
- **Auto-resume functionality**: Interrupted crawls automatically resume from the last checkpoint
- **Snapshot listing**: New commands to list and inspect corpus snapshots
- **Firecrawl parity features**: Enhanced compatibility with Firecrawl output format and behaviour
- **Batch processing**: Parallel URL processing with `batch-scrape` command
- **URL discovery**: `map` command for discovering URLs before crawling
- **Enhanced frontmatter metadata**: Improved metadata extraction and preservation in output

### Fixed

- Fixed duplicate asyncio import causing UnboundLocalError
- Fixed markdown table preservation during content filtering
- Fixed benchmark.yaml to match current SiteConfig schema
- Fixed various CLI command edge cases and error handling

### Internal

- Complete removal of Crawl4AI codebase and references
- Unified service architecture through CrawlService
- Enhanced corpus writer with improved manifest generation
- Comprehensive test suite reorganization (unit, integration, e2e)
- Major documentation updates aligning with Playwright-based architecture
- Improved error handling and correlation ID tracking throughout

## [2025.12.0] - 2025-12-15

### Added

- Initial project scaffold with core functionality
- Site configuration loader with YAML support
- Playwright-based scraper implementation
- Corpus snapshot writer with manifest generation
- Content chunking utilities for LLM-ready output
- CLI interface with commands: list-sites, show-site, crawl, chunk
- Custom exception classes with context and correlation IDs
- Async file I/O operations using aiofiles
- Pre-commit hooks configuration
- Git attributes for line ending normalisation
- Documentation structure with TODO planning support
- Symlinks to master rules, commands, and documentation

### Internal

- Comprehensive error handling with correlation IDs
- Structured logging with correlation tracking
- Input validation for site configurations
- Modern Python 3.12+ type hints throughout
- Pydantic v2 models for configuration and page data

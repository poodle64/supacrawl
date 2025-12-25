# Changelog

All notable changes to web-scraper will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to calendar-based versioning (YYYY.MM.x format).

## [Unreleased]

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

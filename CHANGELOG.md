# Changelog

All notable changes to web-scraper will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to calendar-based versioning (YYYY.MM.x format).

## [Unreleased]

## [2025.12.0] - 2025-12-15

### Added

- Initial project scaffold with core functionality
- Site configuration loader with YAML support
- Crawl4AI scraper implementation
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

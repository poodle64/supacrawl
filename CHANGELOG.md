# Changelog

All notable changes to supacrawl will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to calendar-based versioning (YYYY.MM.x format).

## [Unreleased]

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

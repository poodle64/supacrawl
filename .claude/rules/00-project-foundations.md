---
paths: "**/*"
---

# Supacrawl Project Foundations

## Purpose

Zero-infrastructure CLI web scraper with LLM extraction. Designed for individual developers who want to scrape from the terminal without Docker, databases, or infrastructure.

## Project Scope

### What This Project Does

- Provides CLI commands for web scraping (scrape, crawl, map, search, llm-extract, agent)
- Uses Playwright for web scraping with high-quality markdown output
- Supports multiple LLM providers (Ollama, OpenAI, Anthropic) for extraction
- Provides local caching for scraped content
- Offers autonomous web agent for complex data gathering tasks

### What This Project Does NOT Do

- Does NOT provide web UI or REST API (CLI-only)
- Does NOT store scraped content in databases (outputs to stdout/files)
- Does NOT handle authentication/authorization (Playwright browser-level only)
- Does NOT provide a hosted service (local execution only)

## Authority Note

This rule documents project-specific practice and relies on master rules for requirements. Master rules define universal principles; this rule describes how supacrawl implements them.

## Project Context

### Technology Stack

- **Language**: Python 3.14+
- **CLI Framework**: Click
- **Data Validation**: Pydantic v2 only
- **Dependencies**: `pyproject.toml` (PEP 621) - NOT requirements.txt
- **Scraping**: Playwright, httpx, BeautifulSoup, markdownify
- **LLM Providers**: Ollama (local), OpenAI, Anthropic
- **Cache**: Local filesystem (`.supacrawl/cache/`)

### Architecture

```
CLI Command → Service Layer → Playwright/httpx → Content Processing → Output
                  ↓
             LLM Provider (optional) → Structured Extraction
```

Supacrawl **uses** the Playwright SDK for browser automation and content extraction.

### Core Philosophy

Supacrawl is designed around **zero-infrastructure local execution**.

- **URL-based**: Commands operate on URLs directly, no configuration files required
- **Local-first**: All processing happens locally, with optional local LLM support
- **Cached**: Scraped content is cached locally to avoid redundant requests
- **Pipeline-ready**: Clean markdown output integrates with LangChain, LlamaIndex, and vector stores

## Non-Negotiable Constraints

### Design Constraints

- All commands must support both stdout and file output
- LLM extraction must support multiple providers (not locked to one)
- Cache must be user-controllable (clear, prune, stats)
- Stealth mode must use Patchright for anti-bot evasion

### Technology Constraints

- Python 3.14+
- Click for CLI
- Pydantic v2 only
- `pyproject.toml` for dependencies (NOT requirements.txt)
- JSON for structured output

### Output Contract

Commands produce:
- **scrape**: Markdown content (or HTML/links as requested)
- **crawl**: JSONL of scraped pages
- **map**: List of discovered URLs
- **search**: Search results with optional content scraping
- **llm-extract**: Structured JSON data extracted by LLM
- **agent**: JSON result from autonomous agent execution

## Sources of Truth

- **Master rules**: `.claude/rules/master/` (via symlink) - Universal principles
- **CLI modules**: `src/supacrawl/cli/` - Command implementations
- **Services**: `src/supacrawl/services/` - Business logic

## Rule Interpretation Notes

- Scraping is handled by Playwright SDK via service layer
- Universal restrictions are covered in master 90-code-quality
- Project-specific behavioural rules are defined in numbered rule files (10+, 20+, 30+, etc.)

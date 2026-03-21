# Supacrawl

Zero-infrastructure CLI web scraper with LLM extraction.

## Dev Environment

- Environment: `supacrawl` (conda)
- CLI tool: `supacrawl` command
- Python: 3.12

## Stack

- **Backend**: Python 3.12, Click (CLI), Pydantic, asyncio
- **REST API**: FastAPI + uvicorn (optional, `supacrawl[api]`), port 8308
- **Scraping**: Playwright, httpx, BeautifulSoup, markdownify
- **LLM**: Ollama, OpenAI, Anthropic (configurable providers)
- **Storage**: Local cache (`.supacrawl/cache/`)

## Key Reminders

- Local-first: pip install and go, no Docker/databases/infrastructure
- CLI-first: designed for terminal workflows and pipelines
- Quality first: maintain high-quality markdown output
- **Playwright/Patchright lower bound is `>=1.40.0` intentionally** (NixOS compatibility; see #79, #104). Do NOT bump it unless new Playwright APIs are actually used.

## Sources of Truth

- **Rules**: `.claude/rules/`
- **Docs**: `docs/`

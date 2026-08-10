---
paths:
  - '**/services/**/*.py'
---

# Scraping Service Patterns

Conventions for the scraping services in `src/supacrawl/services/` (`scrape`, `crawl`, `map`, `browser`, `converter`, `search/`).

## Conventions

- **Must** drive Playwright only through `BrowserManager` (used as an async context manager) — never instantiate or manage a Playwright browser directly. Share one browser context across page fetches within a run.
- **Must** convert HTML→Markdown through `MarkdownConverter`, and return Pydantic result models (`ScrapeResult`, `CrawlEvent`, `MapResult`).
- **Must** wrap Playwright/browser failures in `ProviderError` with a correlation ID (see `70-error-handling.md`) — never surface a raw Playwright error.
- **Must** read runtime config from the `SUPACRAWL_*` environment (`docs/configuration.md`), not hardcoded values; accept constructor overrides for dependency injection in tests.

## Anti-bot escalation (hard-won)

The engine ladder `playwright → patchright → camoufox`, `escalate`/`stealth` semantics, and per-domain strategy memory are documented in `docs/configuration.md`. Do not silently change escalation behaviour — it is tuned against real bot-walled sites and covered by the `debug-scraping` and `improve-supacrawl` skills.

## Verification

- **Must** smoke-test a real scrape against a live URL after changing scraper/browser behaviour — a passing unit test over mocked browser I/O does not prove a scrape still works (core `verification.md` §Behaviour vs Appearance).

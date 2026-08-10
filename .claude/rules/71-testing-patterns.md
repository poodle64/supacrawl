---
paths:
  - '**/tests/**/*.py'
---

# Testing Patterns

Supacrawl test conventions. Universal testing patterns are in the master testing rule; fixtures, markers, and worked examples in `docs/development/testing.md`.

## Conventions

- **Must** keep unit tests off the network: inject a mock browser into the services (constructor DI) and mock LLM providers; only tests marked `@pytest.mark.e2e` may hit live URLs or real providers (`pytest -q -m "not e2e"` is the default gate).
- **Must** invoke CLI commands through Click's `CliRunner`, asserting on exit code, stdout vs stderr, and friendly error output.
- **Must** cover each service's public entry point — `ScrapeService`, `CrawlService`, `MapService`, `ExtractService`, `SearchService` — including its error path, not just the happy path.

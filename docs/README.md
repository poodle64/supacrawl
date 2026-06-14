# Supacrawl Documentation

Zero-infrastructure web scraping for the terminal and AI assistants. This directory holds the user-facing references and contributor guides.

## User References

| Doc                               | Purpose                                               |
| --------------------------------- | ----------------------------------------------------- |
| [CLI Reference](cli-reference.md) | Commands, options, and examples                       |
| [API Reference](api-reference.md) | The optional local REST API (Firecrawl v2 compatible) |

## Contributor Guides

| Doc | Purpose |
| --- | --- |
| [Data Flow (LLM)](development/data-flow-llm.md) | The map-to-markdown pipeline phases |
| [Snapshot Contract](development/snapshot-contract.md) | Crawl output layout and manifest format |
| [Retry Logic](development/retry-logic.md) | What is retried, what is not, and backoff |
| [Error Handling](development/error-handling.md) | Exception hierarchy, correlation IDs, recovery chains |
| [Testing](development/testing.md) | Test tiers and how to run the suites |

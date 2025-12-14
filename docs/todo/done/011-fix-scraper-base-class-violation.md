# 011: Fix Scraper Base Class Signature Violation

## Status

✅ DONE - 2025-12-12

## Problem Summary

The `Crawl4AIScraper.crawl()` method violates the Liskov Substitution Principle by having a different signature and return type than its base class:

```python
# Base class (base.py line 16)
def crawl(self, config: SiteConfig) -> list[Page]:

# Actual implementation (crawl4ai.py line 64)
def crawl(self, config: SiteConfig, corpora_dir: Path | None = None) -> tuple[list[Page], Path]:
```

This is a fundamental design flaw that:
- Breaks polymorphism (can't substitute scrapers)
- Causes mypy errors
- Makes the abstraction useless

## Solution Overview

Redesign the scraper interface to properly separate concerns:
1. Scraping (fetching pages) - returns `list[Page]`
2. Corpus writing (persisting pages) - handled by caller or separate writer

Two approaches:

**Option A (Recommended)**: Keep `crawl()` pure, move writing to CLI
- `crawl()` returns `list[Page]` only
- CLI handles `IncrementalSnapshotWriter` orchestration

**Option B**: Add `crawl_to_snapshot()` as a separate method
- Keep `crawl()` returning pages only
- Add convenience method for CLI use

## Implementation Steps

### Chosen Approach: Update Base Class

Rather than refactoring the entire architecture, we updated the base class to match the actual implementation. This is valid because:
- The current interface is more useful (returns snapshot path)
- Corpus writing is tightly coupled with scraping in this project
- The interface can be extended later if needed

- [x] Update `Scraper.crawl()` in `base.py` to match actual signature:
  - Added `corpora_dir: Path | None = None` parameter
  - Changed return type to `tuple[list[Page], Path]`
- [x] Added required `Path` import to `base.py`
- [x] Updated test mocks to match new signature

### Interface Redesign

```python
# base.py - Pure scraping interface
class Scraper(ABC):
    provider_name: str

    @abstractmethod
    async def crawl(self, config: SiteConfig) -> AsyncGenerator[Page, None]:
        """Yield pages as they are scraped."""
        pass

# Or simpler synchronous version:
class Scraper(ABC):
    provider_name: str

    @abstractmethod
    def crawl(self, config: SiteConfig) -> list[Page]:
        """Crawl and return all pages."""
        pass
```

## Files to Modify

- `web_scraper/scrapers/base.py` - Update abstract interface
- `web_scraper/scrapers/crawl4ai.py` - Refactor to match interface
- `web_scraper/cli.py` - Handle corpus writing
- `tests/test_providers.py` - Update mocks and assertions
- `tests/test_cli.py` - Update integration tests

## Testing Considerations

- Ensure scrapers can be substituted (future providers)
- Test that corpus writing works independently of scraping
- Verify incremental writing still works through CLI

## Success Criteria

- [x] `Crawl4AIScraper` properly implements `Scraper` interface
- [x] mypy signature incompatibility error is resolved
- [x] Tests pass with updated interface
- [x] CLI still produces correct corpus output
- [x] Future scrapers can be added with consistent interface

## References

- `.cursor/rules/50-scraper-provider-patterns-web-scraper.mdc` - Scraper patterns
- Liskov Substitution Principle


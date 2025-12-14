# 013: Refactor crawl4ai_result.py into Focused Modules

## Status

✅ DONE (2025-12-13)

## Problem Summary

`web_scraper/scrapers/crawl4ai_result.py` is a 555-line monolith that violates single responsibility principle. It handles:

1. URL normalisation and canonical extraction
2. Main content extraction with DOM scoring
3. HTML to markdown conversion
4. Markdown sanitisation
5. Language detection
6. Content statistics

This makes the code hard to test, maintain, and reuse.

## Solution Overview

Split into focused modules under `web_scraper/content/`:

```
web_scraper/content/
├── __init__.py
├── url.py           # URL normalisation, canonical extraction
├── extraction.py    # Main content extraction, DOM scoring
├── markdown.py      # HTML→markdown conversion, sanitisation
├── language.py      # Language detection and filtering
└── stats.py         # Content statistics
```

Keep `crawl4ai_result.py` as a thin orchestrator that imports from these modules.

## Implementation Steps

### Create New Module Structure

- [ ] Create `web_scraper/content/` directory
- [ ] Create `web_scraper/content/__init__.py` with public exports

### Extract URL Module (`url.py`)

- [ ] Move `normalise_url()`
- [ ] Move `_strip_fragment()`
- [ ] Move `strip_tracking_params()`
- [ ] Move `extract_canonical_url()`

### Extract Content Extraction Module (`extraction.py`)

- [ ] Move `extract_main_content()`
- [ ] Move `extract_main_content_html()`
- [ ] Move `_is_block_tag()`
- [ ] Move `_score_node()`

### Extract Markdown Module (`markdown.py`)

- [ ] Move `html_to_markdown()`
- [ ] Move `_table_to_markdown()`
- [ ] Move `sanitize_markdown()`
- [ ] Move `_link_density()`
- [ ] Move `_is_nav_marker()`
- [ ] Move `_collapse_blank_lines()`

### Extract Language Module (`language.py`)

- [ ] Move `detect_language()`
- [ ] Make stopwords configurable
- [ ] Add support for more languages in future

### Extract Stats Module (`stats.py`)

- [ ] Move `content_stats()`
- [ ] Add more useful statistics (word count, sentence count, etc.)

### Update crawl4ai_result.py

- [ ] Import from new modules
- [ ] Keep `extract_pages_from_result()` as the main orchestrator
- [ ] Simplify the function to use extracted helpers

### Update Imports

- [ ] Update imports in `web_scraper/scrapers/crawl4ai.py`
- [ ] Update imports in `web_scraper/corpus/writer.py`

## Files to Modify

- Create `web_scraper/content/*.py` (6 new files)
- Refactor `web_scraper/scrapers/crawl4ai_result.py`
- Update `web_scraper/scrapers/crawl4ai.py`
- Update `web_scraper/corpus/writer.py`

## Testing Considerations

- Move relevant tests to test new modules
- Create `tests/test_url.py` for URL functions
- Create `tests/test_extraction.py` for content extraction
- Create `tests/test_markdown.py` for markdown functions
- Create `tests/test_language.py` for language detection
- Ensure all existing tests still pass

## Success Criteria

- [ ] `crawl4ai_result.py` is under 100 lines
- [ ] Each new module has single responsibility
- [ ] All functions have clear docstrings
- [ ] New modules are independently testable
- [ ] All existing tests pass
- [ ] No circular imports

## References

- Single Responsibility Principle
- `.cursor/rules/master/90-code-quality-principles.mdc`


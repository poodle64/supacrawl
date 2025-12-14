# Content Filters for Boilerplate Removal

## ✅ STATUS: DONE

**Created**: 2025-12-12  
**Completed**: 2025-12-12  
**Type**: feat

### Outcome

- Implemented PruningContentFilter as default content filter for boilerplate removal
- Added BM25ContentFilter option for query-focused filtering
- Created extract_keywords_from_config() helper function
- Content filters integrated into markdown generator configuration
- Filters work alongside LLM filters when enabled
- Note: Documentation update pending (USAGE_GUIDE.md)

## Problem Summary

Current implementation uses basic markdown generation without content filtering, resulting in boilerplate content (navigation, footers, ads) being included in scrapes. This reduces content quality and increases noise in downstream processing. Firecrawl achieves 80.9% success rate partly through intelligent content extraction.

## Solution Overview

Implement Crawl4AI content filters (`PruningContentFilter` and `BM25ContentFilter`) to remove boilerplate and focus on main content. Default to `PruningContentFilter` for general use, with optional `BM25ContentFilter` for query-focused scraping. Integrate filters into markdown generator configuration.

## Implementation Steps

### 1. Add Content Filter Support to Markdown Generator

**File**: `web_scraper/scrapers/crawl4ai_config.py`

- Import `PruningContentFilter` and `BM25ContentFilter` from `crawl4ai.content_filter_strategy`
- Update `build_markdown_generator()` to accept optional `content_filter_type` parameter
- Implement filter selection logic:
  - Default: `PruningContentFilter(threshold=0.5, threshold_type="dynamic", min_word_threshold=20)`
  - Optional: `BM25ContentFilter` when query keywords are available
- Pass selected filter to `DefaultMarkdownGenerator(content_filter=...)`
- Remove any redundant filtering logic (keep it clean and focused)

### 2. Extract Keywords for BM25 Filtering

**File**: `web_scraper/scrapers/crawl4ai_config.py`

- Create helper function `extract_keywords_from_config(config: SiteConfig) -> str | None`
- Extract keywords from `config.name` and `config.entrypoints` URLs
- Use keywords for BM25 query when `only_main_content: true` and content filter type is "bm25"
- Keep keyword extraction simple and focused (no over-engineering)

### 3. Update SiteConfig Model (Optional Enhancement)

**File**: `web_scraper/models.py`

- Add optional `content_filter` field to `SiteConfig` (default: `None` which means "pruning")
- Values: `None` (pruning), `"pruning"`, `"bm25"`, `"none"`
- This allows per-site configuration, but defaults should work well for most cases

### 4. Clean Up Existing Code

**File**: `web_scraper/scrapers/crawl4ai_config.py`

- Review `build_markdown_generator()` for any redundant or non-effectual code
- Remove any manual filtering logic that content filters now handle
- Ensure LLM filter (if enabled) works alongside content filters (they complement each other)

## Files to Modify

1. `web_scraper/scrapers/crawl4ai_config.py` - Add content filter support
2. `web_scraper/models.py` - Optional: Add `content_filter` field to `SiteConfig`
3. `docs/40-usage/USAGE_GUIDE.md` - Document content filter options

## Testing Considerations

- Test `PruningContentFilter` on existing site configs (e.g., `meta.yaml`)
- Verify boilerplate removal (nav, footer, ads) while preserving main content
- Test `BM25ContentFilter` on documentation sites with clear focus
- Ensure filters don't remove important content (code blocks, tables, examples)
- Compare before/after content quality metrics

## Success Criteria

- Content filters are enabled by default (PruningContentFilter)
- Boilerplate content (nav, footer, ads) is removed from scrapes
- Main content (headings, code, tables, examples) is preserved
- Optional BM25 filter available for query-focused scraping
- Code is clean, focused, and removes redundant filtering logic

## References

- `docs/40-usage/crawl4ai-quality-best-practices.md` - Section 1.1
- `web_scraper/scrapers/crawl4ai_config.py` - Current markdown generator implementation
- Crawl4AI docs: Content Filter Strategies

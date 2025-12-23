# Markdown Fix Plugins - Status

## Current Status: Not Needed

As of the migration to **markdownify** (replacing Crawl4AI), the markdown fix plugins are **no longer needed**. Markdownify correctly handles both edge cases that the fixes were designed to address:

1. **Nested `<strong><a>` structures** → Markdownify produces `**[Link Text](/url)**` correctly
2. **Table links** → Markdownify preserves `[Link](/url)` in table cells correctly

### Test Results

```python
from markdownify import markdownify

# Test: Nested <strong><a> structure
html = '<li><strong><a href="/api/v2">The V2 API</a></strong> is where...</li>'
markdownify(html)
# Output: "* **[The V2 API](/api/v2)** is where..." ✅

# Test: Table with links
html = '<td><a href="/api/users">List Users</a></td>'
markdownify(html)
# Output: "[List Users](/api/users)" ✅
```

## Recommendation

**Keep fixes disabled** (the default). The fix framework is retained for potential future edge cases but the current fixes are unnecessary with markdownify.

If you have `markdown_fixes.enabled: true` in your site configs, you can safely remove it or set it to `false`.

## Legacy Fixes (No Longer Needed)

### missing-link-text-in-lists

**Original Issue**: Crawl4AI's markdown extraction missed link text in nested `<strong><a>` structures, producing `* is where...` instead of `* **[Link](url)** is where...`

**Status**: ✅ Fixed by markdownify - no longer needed

### table-link-preservation

**Original Issue**: Crawl4AI's content filtering stripped links from table cells, leaving empty cells.

**Status**: ✅ Fixed by markdownify - no longer needed

## Framework Retention

The fix framework (`web_scraper/content/fixes.py`) is retained because:

1. Future site-specific edge cases may need fixes
2. Fixes are disabled by default (no performance impact)
3. The pattern is useful for extensibility

To add new fixes in the future, see `docs/40-usage/markdown-fixes.md`.

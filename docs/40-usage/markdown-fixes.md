# Markdown Fix Plugins

Web-scraper includes a plugin-based system for fixing markdown quality issues. Each fix is a separate, independently configurable plugin.

## Current Status

> **Note**: With the migration to **markdownify** (replacing Crawl4AI), the existing fixes are **no longer needed**. Markdownify correctly handles the edge cases these fixes were designed to address. See `REMOVE_MARKDOWN_FIXES.md` for details.

The fix framework is retained for potential future site-specific edge cases.

## Overview

The markdown fix system allows you to:
- **Enable/disable fixes individually** via site configuration
- **Review all fixes** to see what workarounds are in place
- **Add new fixes** without modifying core code

## How It Works

1. Each fix is a function registered in `web_scraper/content/fixes.py`
2. Fixes are applied in sequence after markdown extraction
3. Fixes are **disabled by default** and must be explicitly enabled in site configuration

## Registered Fixes

### missing-link-text-in-lists

**Status**: ✅ No longer needed (markdownify handles this correctly)

**Original Issue**: Crawl4AI missed link text in nested `<strong><a>` structures

### table-link-preservation

**Status**: ✅ No longer needed (markdownify handles this correctly)

**Original Issue**: Crawl4AI stripped links from table cells

## Configuration

### Enable/Disable Fixes

Fixes are controlled via site configuration YAML files. **Fixes are disabled by default**.

```yaml
# Enable all fixes (not recommended - they're not needed with markdownify)
markdown_fixes:
  enabled: true

# Or enable specific fixes only
markdown_fixes:
  enabled: true
  fixes:
    missing-link-text-in-lists: true
```

**Default Behaviour**: If `markdown_fixes` section is omitted, all fixes are disabled.

**Recommendation**: Leave fixes disabled unless you encounter a specific edge case that requires a fix.

## Adding New Fixes

If you encounter a site-specific edge case that markdownify doesn't handle correctly:

1. Add a new fix function to `web_scraper/content/fixes.py`
2. Register it in the `FIXES` list
3. Document the fix in this file
4. Enable it in your site config

Example fix function:

```python
def _fix_my_edge_case(markdown: str, html: str) -> str:
    """Fix description here."""
    # Fix logic
    return fixed_markdown

# Add to FIXES list
FIXES.append(FixSpec(
    name="my-edge-case",
    description="What this fix does",
    upstream_issue="Why this is needed",
    apply_fn=_fix_my_edge_case,
))
```

## Related Documentation

- `REMOVE_MARKDOWN_FIXES.md` - Status of legacy fixes and test results
- `USAGE_GUIDE.md` - General usage information

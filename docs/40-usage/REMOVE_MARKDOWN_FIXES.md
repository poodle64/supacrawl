# Removing Markdown Fix Plugins

This document explains how to remove markdown fix plugins when upstream tools fix the underlying issues.

## Overview

Markdown fix plugins are workarounds for issues in upstream tools. When those tools are updated and fix the issues, the corresponding fix plugins should be removed.

## Current Fixes

### missing-link-text-in-lists

**Upstream Issue**: Markdown extraction misses link text in nested `<strong><a>` structures

**When to Remove**: When markdown extraction correctly preserves link text in nested formatting structures

**How to Test**: 
1. Ensure `markdown_fixes.enabled: false` in site config (or omit the section)
2. Run a crawl: `web-scraper crawl sharesight-api`
3. Check if markdown correctly includes link text (e.g., `**The [V2 API](url)** is where...`)
4. If correct, the fix is no longer needed

## Removal Process

### 1. Delete Fix Module

- **File**: `web_scraper/content/fixes/missing_link_text.py`
- **Action**: Delete this entire file

### 2. Remove from Registry

- **File**: `web_scraper/content/fixes/__init__.py`
- **Action**: Remove the import: `from web_scraper.content.fixes import missing_link_text  # noqa: F401`

### 3. Update Documentation

- **File**: `docs/40-usage/markdown-fixes.md`
- **Action**: Remove the fix from the "Current Fixes" section

- **File**: `docs/40-usage/REMOVE_MARKDOWN_FIXES.md`
- **Action**: Remove the fix from this document

### 4. Update CLI

- **File**: `web_scraper/cli.py`
- **Action**: Remove the import in `list_fixes()` command: `from web_scraper.content.fixes import missing_link_text  # noqa: F401`

## Testing After Removal

After removing a fix:

1. **Run test crawl**: `web-scraper crawl <site>`
2. **Verify markdown quality**: Check that markdown no longer has the issue the fix addressed
3. **Check logs**: Ensure no errors related to the removed fix
4. **Update changelog**: Document that the fix was removed because upstream issue was resolved

## Pattern for New Fixes

When adding new fixes, follow this pattern:

1. Create fix module in `web_scraper/content/fixes/`
2. Document in `docs/40-usage/markdown-fixes.md`
3. Add removal instructions to this document
4. Include upstream issue reference
5. Document in site config template (`sites/template.yaml`)

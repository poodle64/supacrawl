# Markdown Fix Plugins

Web-scraper includes a plugin-based system for fixing markdown quality issues that arise from upstream markdown conversion missing certain patterns. Each fix is a separate, independently configurable plugin.

## Overview

The markdown fix system allows you to:
- **Enable/disable fixes individually** via site configuration
- **Review all fixes** to see what workarounds are in place
- **Easily remove fixes** when upstream tools are updated
- **Add new fixes** without modifying core code

## How It Works

1. Each fix is a plugin class that inherits from `MarkdownFix`
2. Fixes are automatically registered when their modules are imported
3. All enabled fixes are applied in sequence after markdown extraction
4. Fixes are **disabled by default** and must be explicitly enabled in site configuration

## Current Fixes

### missing-link-text-in-lists

**Description**: Injects missing link text in list items that start with verbs (e.g., 'is where...' -> '**The [V2 API](url)** is where...')

**Issue Pattern**: List items starting with verbs (is, are, endpoints) that are missing link text at the beginning

**Upstream Issue**: Markdown conversion misses link text in nested `<strong><a>` structures

**Configuration**: Enable via `markdown_fixes.enabled: true` in site YAML (disabled by default)

**Example**:
- **Before**: `* is where you will find the bulk of our endpoints.`
- **After**: `* **The [V2 API](/api/2/overview)** is where you will find the bulk of our endpoints.`

## Configuration

### Enable/Disable Fixes

Fixes are controlled via site configuration YAML files. **Fixes are disabled by default** and must be explicitly enabled.

#### Site Configuration

Add a `markdown_fixes` section to your site YAML:

```yaml
# Enable all fixes
markdown_fixes:
  enabled: true

# Or enable specific fixes only
markdown_fixes:
  enabled: true
  fixes:
    missing-link-text-in-lists: true
    # Other fixes default to disabled when not listed
```

**Example** (`sites/sharesight-api.yaml`):
```yaml
id: sharesight-api
name: Sharesight API Documentation
# ... other config ...

# Enable markdown fixes
markdown_fixes:
  enabled: true
  fixes:
    missing-link-text-in-lists: true
```

**Default Behaviour**: If `markdown_fixes` section is omitted, all fixes are disabled.

**See Template**: For a complete example of all available configuration options, see `sites/template.yaml`.

### List All Fixes

View all registered fixes and their status:

```bash
python -m web_scraper.content.fixes.index
```

Or programmatically:

```python
from web_scraper.content.fixes.index import get_fix_index

for fix in get_fix_index():
    print(f"{fix['name']}: {fix['enabled']}")
```

## Adding New Fixes

1. Create a new file in `web_scraper/content/fixes/` (e.g., `my_fix.py`)
2. Create a class inheriting from `MarkdownFix`
3. Implement required methods (`name`, `description`, `issue_pattern`, `upstream_issue`, `fix`)
4. Register the fix: `register_fix(MyFix())`
5. Import the module in `web_scraper/content/fixes/__init__.py`

Example:

```python
from web_scraper.content.fixes.base import MarkdownFix
from web_scraper.content.fixes.registry import register_fix

class MyFix(MarkdownFix):
    @property
    def name(self) -> str:
        return "my-fix-name"
    
    @property
    def description(self) -> str:
        return "What this fix does"
    
    @property
    def issue_pattern(self) -> str:
        return "Pattern this fixes"
    
    @property
    def upstream_issue(self) -> str:
        return "Upstream issue description"
    
    def fix(self, markdown: str, html: str) -> str:
        # Fix logic here
        return markdown
    
    @property
    def enabled(self) -> bool:
        # Fixes are controlled via site config, not environment variables
        return True

# Auto-register
register_fix(MyFix())
```

## Periodic Review

Periodically review fixes to determine if they're still needed:

1. **Check upstream issues**: Review the upstream tool's changelog/issue tracker
2. **Test with fixes disabled**: Omit `markdown_fixes` section or set `enabled: false` in site config
3. **Remove obsolete fixes**: If upstream is fixed, remove the fix plugin
4. **Update documentation**: Keep this document current

## Related Documentation

- See `USAGE_GUIDE.md` for general usage information

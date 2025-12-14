# 016: Remove Site-Specific Hardcoding

## Status

✅ DONE (2025-12-13)

## Problem Summary

The `_clean_page_markdown()` function in `crawl4ai.py` contains hardcoded logic specifically for Meta/Facebook developer docs:

```python
def _clean_page_markdown(markdown: str, url: str) -> str:
    """Site-specific cleaning for Meta developer docs..."""
    netloc = urlsplit(url).netloc
    if not (
        netloc.endswith("developers.facebook.com")
        or netloc.endswith("developers.meta.com")
    ):
        return markdown  # Only cleans Meta docs!

    tracker_substrings = [
        "googleads.g.doubleclick.net",
        "doubleclick.net",
        ...
    ]
```

This is an anti-pattern for a "world-class generic scraper" as it:
- Only works for one website
- Requires code changes to support new sites
- Isn't discoverable or configurable

## Solution Overview

Make content cleaning configurable per-site via YAML configuration:

1. Add `cleaning_rules` section to SiteConfig
2. Support configurable patterns for:
   - Tracker URL filtering
   - Strip prefixes (e.g., `![]()` patterns)
   - Stop markers (footer detection)
   - Navigation patterns
3. Provide sensible defaults that work for most sites
4. Allow site-specific overrides in YAML

## Implementation Steps

### Update SiteConfig Model

- [ ] Add optional `cleaning` field to SiteConfig:

```yaml
# sites/meta.yaml
cleaning:
  tracker_patterns:
    - "doubleclick.net"
    - "google-analytics.com"
    - "facebook.com/tr"
  strip_prefixes:
    - "![]("
    - "[![]("
  stop_markers:
    - "Build with Meta"
    - "Terms and policies"
  nav_markers:
    - "On This Page"
    - "Table of Contents"
```

### Create Cleaning Configuration

- [ ] Add `CleaningConfig` model in `web_scraper/models.py`:

```python
class CleaningConfig(BaseModel):
    tracker_patterns: list[str] = []
    strip_prefixes: list[str] = []
    stop_markers: list[str] = []
    nav_markers: list[str] = []
    skip_until_heading: bool = True
```

### Implement Generic Cleaner

- [ ] Create `web_scraper/content/cleaner.py`
- [ ] Implement `clean_markdown(markdown, config)` function
- [ ] Use patterns from config, not hardcoded values
- [ ] Provide default patterns that work broadly

### Provide Default Patterns

- [ ] Common tracker patterns (analytics, ads, pixels)
- [ ] Common nav/footer patterns
- [ ] Common social media patterns
- [ ] Document in `.env.example` or config reference

### Migrate Existing Meta Config

- [ ] Add cleaning section to `sites/meta.yaml`
- [ ] Remove hardcoded Meta logic from `crawl4ai.py`

## Files to Modify

- `web_scraper/models.py` - Add CleaningConfig
- Create `web_scraper/content/cleaner.py`
- `web_scraper/scrapers/crawl4ai.py` - Remove hardcoded function
- `sites/meta.yaml` - Add cleaning configuration
- `docs/40-usage/creating-site-configs-web-scraper.md` - Document cleaning options

## Testing Considerations

- Test with default config (no cleaning rules)
- Test with explicit cleaning rules
- Verify Meta docs still clean correctly with YAML config
- Test stop marker detection
- Test tracker pattern filtering

## Success Criteria

- [ ] No hardcoded domain checks in Python code
- [ ] Cleaning is configurable per site
- [ ] Default patterns work for most sites
- [ ] Meta docs configuration migrated to YAML
- [ ] Documentation explains cleaning options
- [ ] All existing tests pass

## References

- `.cursor/rules/50-site-config-patterns-web-scraper.mdc`
- `.cursor/rules/00-project-foundations-web-scraper.mdc`


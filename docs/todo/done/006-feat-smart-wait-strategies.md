# Smart Wait Strategies for Dynamic Content

## ✅ STATUS: DONE

**Created**: 2025-12-12  
**Completed**: 2025-12-12  
**Type**: feat

### Outcome

- Changed default wait_until from "domcontentloaded" to "networkidle" for better JavaScript handling
- Added wait_for_images=True when only_main_content: true
- Fixed wait_until reference in _crawl_settings_summary()
- Note: Documentation update pending (USAGE_GUIDE.md)
- Note: Optional wait_for selectors not implemented (can be added later if needed)

## Problem Summary

Current implementation uses `wait_until="domcontentloaded"` which may miss dynamic content loaded via JavaScript. This results in incomplete scrapes for modern JavaScript-heavy websites. Firecrawl uses smart wait strategies to ensure all dynamic content is captured.

## Solution Overview

Update default wait strategy from `"domcontentloaded"` to `"networkidle"` for better JavaScript handling. Add support for `wait_for` CSS selectors in site config. Enable `wait_for_images` by default when `only_main_content: true`. Clean up redundant wait-related configuration.

## Implementation Steps

### 1. Update Default Wait Strategy

**File**: `web_scraper/scrapers/crawl4ai.py`

- Change default `wait_until` from `"domcontentloaded"` to `"networkidle"`
- Update environment variable default: `CRAWL4AI_WAIT_UNTIL` defaults to `"networkidle"`
- Keep environment variable override for flexibility
- Remove any redundant wait configuration

### 2. Add Wait for Images Support

**File**: `web_scraper/scrapers/crawl4ai.py`

- Add `wait_for_images=True` to `CrawlerRunConfig` when `config.only_main_content: true`
- This ensures lazy-loaded images are fully loaded before extraction
- Keep it simple: enable when main content extraction is requested

### 3. Add Wait For Selectors Support (Optional Enhancement)

**File**: `web_scraper/models.py`, `web_scraper/scrapers/crawl4ai.py`

- Add optional `wait_for` field to `SiteConfig` (list of CSS selectors)
- Pass `wait_for` to `CrawlerRunConfig` when provided
- This allows per-site configuration for specific content selectors
- Keep it optional (most sites don't need it)

### 4. Clean Up Wait Configuration

**File**: `web_scraper/scrapers/crawl4ai.py`

- Review all wait-related configuration for redundancy
- Remove any non-effectual wait settings
- Ensure `delay_before_return_html` is appropriate (current: 0.25s is reasonable)
- Keep configuration clean and focused

## Files to Modify

1. `web_scraper/scrapers/crawl4ai.py` - Update wait strategy defaults
2. `web_scraper/models.py` - Optional: Add `wait_for` field to `SiteConfig`
3. `docs/40-usage/USAGE_GUIDE.md` - Document wait strategies

## Testing Considerations

- Test on JavaScript-heavy sites (e.g., React/Vue documentation)
- Verify dynamic content is captured with `networkidle` wait
- Test image loading on image-heavy sites
- Compare before/after completeness metrics
- Ensure wait strategies don't significantly slow down crawls

## Success Criteria

- Default wait strategy is `"networkidle"` (better JavaScript handling)
- Images are waited for when `only_main_content: true`
- Optional `wait_for` selectors supported for per-site configuration
- Dynamic content is captured reliably
- Configuration is clean and removes redundant wait settings

## References

- `docs/40-usage/crawl4ai-quality-best-practices.md` - Section 2.1, 2.2
- `web_scraper/scrapers/crawl4ai.py` - Current wait configuration (line 323)

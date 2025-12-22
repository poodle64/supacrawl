# Crawl4AI SPA Bug Report: React Router Content Mismatch

## Summary

Crawl4AI captures incorrect content for React Single Page Applications (SPAs) with client-side routing. When crawling multiple URLs in an SPA, different URLs return identical content (the first page loaded), despite successful navigation to the correct URLs.

## Environment

- **Crawl4AI Version**: 0.7.8
- **Python Version**: 3.12
- **Browser**: Chromium (via Playwright)
- **OS**: macOS 25.1.0 (Darwin)

## Test Site

- **URL**: https://portfolio.sharesight.com/api
- **Framework**: React with client-side routing
- **Issue**: 13 URLs crawled, only 3 unique content hashes (70% duplicates)

## Expected Behavior

Each URL should return its specific content:
- `/api/3/codes` → "Market codes" tables (2916 lines)
- `/api/3/overview` → "User API V3 - Overview" (292 lines)
- `/api/3/authentication_flow` → "Authentication Flow" content
- etc.

## Actual Behavior

All URLs in a route group return identical "Overview" content:

```
URL                                          Content Hash        Actual Content
https://portfolio.sharesight.com/api/3/codes 81367851ee63766c    "User API V3 - Overview" ❌
https://portfolio.sharesight.com/api/3/overview 81367851ee63766c "User API V3 - Overview" ✓
https://portfolio.sharesight.com/api/3/authentication_flow 81367851ee63766c "User API V3 - Overview" ❌
https://portfolio.sharesight.com/api/3/usage_limits 81367851ee63766c "User API V3 - Overview" ❌
```

## Verification

**Server returns correct content:**
```bash
$ curl -s "https://portfolio.sharesight.com/api/3/codes" | grep -i "market codes"
<h2><a id="market">Market codes</a></h2>

$ curl -s "https://portfolio.sharesight.com/api/3/codes" | wc -l
2916
```

**Crawl4AI captures wrong content:**
```bash
$ wc -l corpora/sharesight-api/latest/html/api/3/codes.html
292

$ grep -i "market codes\|User API V3" corpora/sharesight-api/latest/html/api/3/codes.html
<h1>User API V3 - Overview</h1>
```

**Direct Playwright works:**
```python
async with async_playwright() as p:
    browser = await p.chromium.launch()
    page = await browser.new_page()
    await page.goto("https://portfolio.sharesight.com/api/3/codes", wait_until="domcontentloaded")
    content = await page.content()
    # Returns 2916 lines with correct "Market codes" content ✓
```

## Reproduction Steps

### Minimal Example

```python
import asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy

async def test_spa_crawl():
    browser_config = BrowserConfig(headless=True, verbose=True)

    # Crawl SPA with deep crawl strategy
    deep_crawl_strategy = BFSDeepCrawlStrategy(max_depth=2, max_pages=13)

    config = CrawlerRunConfig(
        deep_crawl_strategy=deep_crawl_strategy,
        wait_until="networkidle",
        delay_before_return_html=2.0,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        results = await crawler.arun(
            url="https://portfolio.sharesight.com/api",
            config=config
        )

        # Check for duplicates
        for result in results:
            print(f"{result.url}: {result.cleaned_html[:100]}")

asyncio.run(test_spa_crawl())
```

**Expected output**: Each URL shows different content
**Actual output**: Multiple URLs show identical "Overview" content

## Root Cause Analysis

After extensive debugging, the issue appears to be:

1. **Deep Crawl uses `arun_many()`** which processes multiple URLs
2. **Browser session/context is reused** across URL navigations
3. **React Router doesn't re-render** when navigating to new URLs in the same session
4. **Crawl4AI captures cached/stale content** before React updates the DOM

### Evidence

**Test 1: Fresh browser contexts (FAILED)**
- Modified code to create new browser context per URL using `async with crawler:` inside loop
- Still got 10 duplicates
- Proves browser context isolation alone doesn't fix it

**Test 2: Manual URL list without deep_crawl (FAILED)**
- Created config with 13 URLs as entrypoints, sitemap disabled
- Forced fresh browser contexts per URL
- Still got duplicates
- Proves issue isn't specific to deep_crawl_strategy

**Test 3: JavaScript wait_for (TIMED OUT)**
- Added `wait_for="js:..."` to detect when heading content changes
- Timed out after 57 seconds
- Proves React never re-renders the content

**Test 4: Direct Playwright navigation (SUCCESS)**
- Standalone script using raw Playwright
- Direct `page.goto()` calls
- Correct content captured every time
- Proves server and React work correctly

## Configuration Attempts

All failed to resolve the issue:

```python
# Attempt 1: Increased SPA delay
CrawlerRunConfig(delay_before_return_html=10.0)  # FAILED

# Attempt 2: Changed wait strategy
CrawlerRunConfig(wait_until="domcontentloaded")  # FAILED

# Attempt 3: Used raw HTML instead of cleaned_html
raw_html = getattr(result, "html", None)  # FAILED - HTML is already wrong

# Attempt 4: Disabled content filters
os.environ["CRAWL4AI_CONTENT_FILTER"] = "none"  # FAILED

# Attempt 5: Added React Router forcing JavaScript
js_code = """
window.dispatchEvent(new PopStateEvent('popstate'));
window.dispatchEvent(new Event('hashchange'));
"""  # FAILED

# Attempt 6: Content stability wait_for
wait_for = """js:() => {
    const headings = document.querySelectorAll('h1, h2');
    if (headings.length === 0) return false;
    if (!window.__spa_first_heading) {
        window.__spa_first_heading = headings[0].textContent.trim();
        return false;
    }
    return headings[0].textContent.trim() !== window.__spa_first_heading;
}"""  # TIMED OUT after 57s
```

## Impact

This bug makes Crawl4AI **unusable for React/Vue SPAs** with client-side routing, which represents a significant portion of modern web applications.

**Affected patterns:**
- React Router
- Vue Router
- Any SPA that uses `pushState`/`replaceState` for navigation
- Sites where content changes without full page reloads

## Comparison: Firecrawl vs Crawl4AI

**Firecrawl** (tested via MCP):
- ✅ 13 URLs → 13 unique content hashes
- ✅ `/api/3/codes` → Correct "Market codes" content (500+ lines)
- ✅ All pages have correct content

**Crawl4AI**:
- ❌ 13 URLs → 3 unique content hashes (70% duplicates)
- ❌ `/api/3/codes` → Wrong "Overview" content (22 lines)
- ❌ Multiple pages show identical wrong content

## Suggested Fix

Based on Crawl4AI's own documentation on session management, the issue likely requires:

1. **Force full page reload for each URL** in deep_crawl, not just navigation
2. **OR** properly implement `js_only=True` with custom navigation JS for SPAs
3. **OR** detect SPAs and use different navigation strategy
4. **OR** add `wait_for` that detects when URL content has actually changed

Example from Crawl4AI docs that works:

```python
# This WORKS for multi-page crawl within same SPA
for page in range(3):
    config = CrawlerRunConfig(
        session_id="my_session",
        js_code=click_next_button if page > 0 else None,
        wait_for="js:() => /* wait for content change */" if page > 0 else None,
        js_only=page > 0,  # Key: Don't re-navigate, just run JS
    )
    result = await crawler.arun(url=base_url, config=config)
```

The difference: This uses `session_id` + `js_only` + custom navigation JS. But `deep_crawl_strategy` doesn't have this level of control.

## Workaround

Currently the only workaround is to:
1. Disable deep_crawl_strategy
2. Manually discover URLs (e.g., from sitemap)
3. Crawl each URL individually with separate browser contexts
4. **BUT** this still fails (tested) - suggests deeper Playwright integration issue

## Request

Please investigate why Crawl4AI's browser/Playwright integration doesn't properly handle SPA navigation in `arun_many()` or `deep_crawl_strategy` contexts.

## Additional Context

- Manual Playwright script with same navigation pattern works perfectly
- Issue persists across different browser configs
- Issue persists with/without caching
- Issue persists with different wait strategies
- Duplicate detection correctly identifies the issue (added in our codebase)

## Files for Reproduction

- Site config: https://github.com/user/web-scraper/blob/main/sites/sharesight-api.yaml
- Test report: /tmp/sharesight-test-report.md
- Debug script: debug_sharesight.py

## Related Issues

This may be related to how Crawl4AI's `arun_many()` dispatcher reuses browser contexts/tabs across multiple URLs without properly resetting SPA state.

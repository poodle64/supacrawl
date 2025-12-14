# Crawl4AI Quality Best Practices: Achieving Firecrawl-Level Scrape Quality

This document synthesises research on best practices for using Crawl4AI to produce high-quality scrapes comparable to Firecrawl. It provides actionable recommendations specific to the web-scraper project.

## Executive Summary

**Firecrawl Quality Characteristics:**
- 80.9% success rate (vs Crawl4AI's 58.0% in benchmarks)
- Smart wait for JavaScript-heavy pages
- Stealth proxy mode for anti-bot protection
- Intelligent content extraction (main content focus)
- Caching for performance (500% faster with cache)

**Key Quality Gaps to Address:**
1. Content extraction quality (boilerplate removal, main content focus)
2. Dynamic content handling (JavaScript rendering, lazy loading)
3. Anti-bot evasion (stealth mode, proxy rotation)
4. Error handling and retry strategies
5. Content filtering and cleaning

## 1. Content Extraction Quality

### 1.1 Use Content Filters for Boilerplate Removal

**Current State:** Basic markdown generation without content filtering.

**Recommendation:** Implement content filters to remove navigation, footers, ads, and boilerplate.

**Implementation Options:**

#### Option A: PruningContentFilter (Recommended for General Use)
```python
from crawl4ai.content_filter_strategy import PruningContentFilter

pruning_filter = PruningContentFilter(
    threshold=0.5,  # Adjust based on site structure
    threshold_type="dynamic",  # Adaptive threshold based on content density
    min_word_threshold=20  # Minimum words per block to retain
)
```

**When to Use:** General-purpose scraping where you want clean content without specific query focus.

#### Option B: BM25ContentFilter (Recommended for Query-Focused Scraping)
```python
from crawl4ai.content_filter_strategy import BM25ContentFilter

bm25_filter = BM25ContentFilter(
    user_query="documentation API reference",  # Derived from site config or entrypoints
    bm25_threshold=1.2,  # Higher = stricter filtering
    language="en"  # For stemming/tokenization
)
```

**When to Use:** When you have specific content focus (e.g., documentation sites, API references).

#### Option C: Two-Pass Filtering (Best Quality)
```python
# First pass: Remove boilerplate
pruning_filter = PruningContentFilter(threshold=0.5, min_word_threshold=20)

# Second pass: Focus on relevant content
bm25_filter = BM25ContentFilter(
    user_query=extract_keywords_from_config(config),
    bm25_threshold=1.2
)
```

**When to Use:** Maximum quality when you can afford the processing overhead.

**Action Items:**
- [ ] Add `content_filter` parameter to `SiteConfig` (optional, defaults to "pruning")
- [ ] Implement filter selection in `build_markdown_generator()`
- [ ] Extract keywords from site config `name` and `entrypoints` for BM25 queries
- [ ] Test filter effectiveness on existing site configs

### 1.2 Use Fit Markdown for Main Content Extraction

**Current State:** Using `raw_markdown` primarily.

**Recommendation:** Prefer `fit_markdown` when `only_main_content: true` in site config.

**Implementation:**
```python
# In build_markdown_generator()
if config.only_main_content:
    # Use fit_markdown (automatically applies content filters)
    # This is already handled by DefaultMarkdownGenerator with content_filter
    pass
```

**Action Items:**
- [ ] Verify `fit_markdown` is being used when `only_main_content: true`
- [ ] Document the difference between `raw_markdown` and `fit_markdown` in usage guide

### 1.3 LLM Content Filtering (Advanced)

**Current State:** LLM filter available via `CRAWL4AI_LLM_FILTER=true` but not optimised.

**Recommendation:** Optimise LLM filter configuration for better quality.

**Best Practices:**
- Use `fit_markdown` as input format (reduces tokens by ~60-80%)
- Set appropriate `chunk_token_threshold` (800-1200 tokens)
- Use clear, specific instructions
- Monitor token usage and costs

**Implementation:**
```python
# Current implementation is good, but consider:
content_filter = LLMContentFilter(
    llm_config=llm_config,
    instruction=(
        "Extract main documentation content. Keep: headings, code blocks, "
        "tables, parameter lists, examples. Remove: navigation menus, footers, "
        "cookie banners, advertisements, social media widgets, related articles."
    ),
    chunk_token_threshold=1000,  # Larger chunks for better context
    input_format="fit_markdown"  # Use cleaned content (if available)
)
```

**Action Items:**
- [ ] Update default LLM filter instruction to be more specific
- [ ] Add `input_format` parameter support (use `fit_markdown` when available)
- [ ] Document LLM filter best practices in usage guide

## 2. Dynamic Content Handling

### 2.1 Smart Wait for JavaScript Rendering

**Current State:** Using `wait_until="domcontentloaded"` which may miss dynamic content.

**Recommendation:** Implement smart wait strategies for JavaScript-heavy pages.

**Implementation Options:**

#### Option A: Network Idle (Recommended)
```python
run_config = CrawlerRunConfig(
    wait_until="networkidle",  # Wait for network to be idle
    delay_before_return_html=0.5,  # Additional delay for dynamic content
    # ... other config
)
```

**When to Use:** Most modern websites with dynamic content.

#### Option B: Wait for Specific Elements
```python
run_config = CrawlerRunConfig(
    wait_for="css:.main-content, css:.article-body",  # Wait for specific selectors
    wait_until="domcontentloaded",
    # ... other config
)
```

**When to Use:** When you know the specific content selectors.

#### Option C: Custom JavaScript Execution
```python
run_config = CrawlerRunConfig(
    js_code="""
        // Wait for content to load
        await new Promise(resolve => {
            if (document.querySelector('.main-content')) {
                resolve();
            } else {
                const observer = new MutationObserver(() => {
                    if (document.querySelector('.main-content')) {
                        observer.disconnect();
                        resolve();
                    }
                });
                observer.observe(document.body, { childList: true, subtree: true });
                setTimeout(resolve, 5000); // Max wait 5s
            }
        });
    """,
    # ... other config
)
```

**When to Use:** Complex sites with custom loading patterns.

**Action Items:**
- [ ] Add `wait_until` option to `SiteConfig` (default: "networkidle")
- [ ] Add `wait_for` option to `SiteConfig` (optional CSS selectors)
- [ ] Update default `wait_until` to "networkidle" for better dynamic content handling
- [ ] Document wait strategies in usage guide

### 2.2 Handle Lazy-Loaded Images and Content

**Current State:** `scan_full_page=True` handles scrolling, but images may not be fully loaded.

**Recommendation:** Ensure images and lazy-loaded content are fully loaded.

**Implementation:**
```python
run_config = CrawlerRunConfig(
    wait_for_images=True,  # Wait for all images to load
    scan_full_page=True,  # Scroll to trigger lazy loading
    scroll_delay=0.3,  # Slightly longer delay for image loading
    # ... other config
)
```

**Action Items:**
- [ ] Add `wait_for_images` parameter (default: `True` when `only_main_content: true`)
- [ ] Test on sites with heavy image content

### 2.3 Viewport Adjustment for Dynamic Content

**Current State:** Fixed viewport (1280x720).

**Recommendation:** Adjust viewport dynamically for content that loads based on viewport size.

**Implementation:**
```python
run_config = CrawlerRunConfig(
    adjust_viewport_to_content=True,  # Resize viewport to content height
    # ... other config
)
```

**Action Items:**
- [ ] Add `adjust_viewport_to_content` option to `SiteConfig` (default: `False`)
- [ ] Test on sites that load content based on viewport

## 3. Anti-Bot Evasion

### 3.1 Stealth Mode Configuration

**Current State:** `enable_stealth=True` is already enabled.

**Status:** ✅ Already implemented correctly.

**Recommendation:** Keep stealth mode enabled. Consider additional stealth features if available.

### 3.2 User Agent and Headers

**Current State:** Fixed user agent and Accept-Language header.

**Recommendation:** Use realistic, up-to-date user agents and headers.

**Implementation:**
```python
# Update default user agent to more recent version
user_agent = os.getenv(
    "CRAWL4AI_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"  # Updated version
)

# Add more realistic headers
headers = {
    "Accept-Language": accept_language,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}
```

**Action Items:**
- [ ] Update default user agent to recent Chrome version
- [ ] Add more realistic browser headers
- [ ] Document header customisation options

### 3.3 Proxy Support

**Current State:** Proxy support exists but not optimised.

**Recommendation:** Document proxy best practices and consider proxy rotation.

**Action Items:**
- [ ] Document proxy configuration in usage guide
- [ ] Consider proxy rotation for large-scale crawls (future enhancement)

## 4. Error Handling and Retry Strategies

### 4.1 Retry Logic Optimisation

**Current State:** Retry logic exists but may not be optimal.

**Recommendation:** Implement context-aware retry strategies.

**Best Practices:**
- Retry on 5xx errors, timeouts, connection errors
- Don't retry on 4xx errors (client errors)
- Use exponential backoff with jitter
- Respect `Retry-After` headers
- Limit retries (2-3 attempts recommended)

**Current Implementation:** ✅ Already follows best practices.

**Action Items:**
- [ ] Verify retry logic handles `Retry-After` headers (if Crawl4AI supports it)
- [ ] Document retry behaviour in usage guide

### 4.2 Error Classification

**Current State:** Basic error handling.

**Recommendation:** Classify errors for better observability.

**Action Items:**
- [ ] Add error classification (DNS errors, timeouts, HTTP errors, content extraction failures)
- [ ] Log error categories for monitoring
- [ ] Consider alerting on persistent error patterns

## 5. Performance Optimisation

### 5.1 Caching Strategy

**Current State:** Cache disabled by default (`CRAWL4AI_CACHE_ENABLED=false`).

**Recommendation:** Enable cache for stable content sources.

**Best Practices:**
- Use cache for documentation sites, API references (content changes infrequently)
- Bypass cache for news sites, dynamic content (content changes frequently)
- Set appropriate `maxAge` for cached content (Firecrawl uses 2 days default)

**Action Items:**
- [ ] Add `cache_enabled` option to `SiteConfig` (default: `false`)
- [ ] Document when to enable caching
- [ ] Consider cache TTL configuration (future enhancement)

### 5.2 Resource Blocking

**Current State:** Basic resource blocking via `_blocked_resource_patterns()`.

**Recommendation:** Optimise resource blocking for performance.

**Best Practices:**
- Block ads, analytics, social media widgets
- Block fonts, images (if not needed for content extraction)
- Block videos, iframes (unless needed)

**Action Items:**
- [ ] Review and optimise blocked resource patterns
- [ ] Add resource blocking configuration to `SiteConfig` (optional)
- [ ] Document resource blocking impact on performance

## 6. Extraction Strategies

### 6.1 Choose Appropriate Extraction Strategy

**Current State:** Using LLM extraction when LLM is configured, otherwise basic extraction.

**Recommendation:** Use appropriate extraction strategy based on content type.

**Best Practices:**
- **RegexExtractionStrategy**: Emails, phones, URLs, dates (fastest)
- **JsonCssExtractionStrategy**: Well-structured HTML with consistent patterns
- **LLMExtractionStrategy**: Complex, unstructured content requiring reasoning (most expensive)
- **CosineStrategy**: Content similarity and clustering

**Guideline:** Start with non-LLM strategies, use LLM only when necessary.

**Action Items:**
- [ ] Document extraction strategy selection in usage guide
- [ ] Consider adding extraction strategy option to `SiteConfig` (future enhancement)

### 6.2 Schema-Based Extraction

**Current State:** Not using schema-based extraction.

**Recommendation:** Consider schema-based extraction for structured content.

**Best Practices:**
- Define clear schemas for consistent data extraction
- Use `generate_schema()` before manual schema creation
- Test schemas on sample pages before full crawl

**Action Items:**
- [ ] Document schema-based extraction patterns (future enhancement)
- [ ] Consider adding schema support to `SiteConfig` (future enhancement)

## 7. Content Cleaning and Normalisation

### 7.1 Post-Processing Cleaning

**Current State:** Basic markdown cleaning via `_clean_page_markdown()`.

**Recommendation:** Enhance content cleaning for better quality.

**Best Practices:**
- Remove excessive whitespace
- Normalise line breaks
- Clean up malformed markdown
- Preserve important formatting (code blocks, tables, lists)

**Action Items:**
- [ ] Review and enhance `_clean_page_markdown()` function
- [ ] Test cleaning on various content types
- [ ] Document cleaning behaviour

## 8. Monitoring and Observability

### 8.1 Quality Metrics

**Current State:** Basic logging and correlation IDs.

**Recommendation:** Add quality metrics for monitoring.

**Metrics to Track:**
- Success rate per site
- Average content quality score (word count, content density)
- Error rates by category
- Cache hit rates
- Extraction quality (if using LLM)

**Action Items:**
- [ ] Add quality metrics to run logs
- [ ] Consider adding quality score calculation
- [ ] Document monitoring best practices

## Implementation Priority

### High Priority (Immediate Impact on Quality)

1. **Content Filters** (Section 1.1)
   - Implement PruningContentFilter as default
   - Add BM25ContentFilter option
   - Impact: Significant improvement in content quality

2. **Smart Wait Strategies** (Section 2.1)
   - Change default `wait_until` to "networkidle"
   - Add `wait_for` option support
   - Impact: Better handling of dynamic content

3. **Image Loading** (Section 2.2)
   - Enable `wait_for_images` by default
   - Impact: Complete content extraction

### Medium Priority (Quality Improvements)

4. **Enhanced Headers** (Section 3.2)
   - Update user agent and add realistic headers
   - Impact: Better anti-bot evasion

5. **LLM Filter Optimisation** (Section 1.3)
   - Improve LLM filter configuration
   - Impact: Better content extraction when using LLM

6. **Content Cleaning** (Section 7.1)
   - Enhance markdown cleaning
   - Impact: Cleaner output

### Low Priority (Future Enhancements)

7. **Caching Strategy** (Section 5.1)
   - Add per-site cache configuration
   - Impact: Performance improvement

8. **Extraction Strategies** (Section 6.1)
   - Add extraction strategy selection
   - Impact: Better extraction for specific content types

9. **Quality Metrics** (Section 8.1)
   - Add monitoring and metrics
   - Impact: Better observability

## References

- [Crawl4AI Documentation](https://docs.crawl4ai.com/)
- [Crawl4AI Best Practices Blog](https://www.crawl4.com/blog/)
- [Firecrawl Quality Benchmarks](https://www.firecrawl.dev/blog/introducing-scrape-evals)
- [Crawl4AI vs Firecrawl Comparison](https://blog.apify.com/crawl4ai-vs-firecrawl/)

## Testing Recommendations

1. **Test on Diverse Sites:**
   - Documentation sites (e.g., Facebook Graph API docs)
   - News sites (dynamic content)
   - E-commerce sites (product pages)
   - Blog sites (article content)

2. **Quality Metrics to Measure:**
   - Content completeness (main content vs boilerplate ratio)
   - Dynamic content capture rate
   - Error rates
   - Extraction accuracy

3. **Compare Before/After:**
   - Run same site configs with old vs new settings
   - Compare content quality scores
   - Measure success rates

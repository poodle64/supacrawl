# 015: Document All Environment Variables

## Status

✅ DONE (2025-12-13)

## Problem Summary

There are 20+ environment variables scattered across the codebase with incomplete documentation. The `.env.example` file exists but doesn't cover all variables. Users can't effectively configure the scraper without reading source code.

### Currently Undocumented/Poorly Documented Variables

**Browser Configuration:**
- `CRAWL4AI_HEADLESS` - Run browser in headless mode
- `CRAWL4AI_BROWSER_TYPE` - Browser to use (chromium, firefox, webkit)
- `CRAWL4AI_VIEWPORT_WIDTH`, `CRAWL4AI_VIEWPORT_HEIGHT` - Browser viewport size
- `CRAWL4AI_USER_AGENT` - Custom user agent string
- `CRAWL4AI_ACCEPT_LANGUAGE` - Accept-Language header
- `CRAWL4AI_USE_MANAGED_BROWSER` - Use managed browser instance
- `CRAWL4AI_USER_DATA_DIR` - Browser user data directory
- `CRAWL4AI_PROXY` - Proxy server URL
- `CRAWL4AI_BROWSER_VERBOSE` - Enable browser verbose logging

**Crawl Behavior:**
- `CRAWL4AI_WAIT_UNTIL` - Page load wait condition
- `CRAWL4AI_ENTRYPOINT_TIMEOUT_MS` - Timeout per entrypoint
- `CRAWL4AI_CACHE_ENABLED` - Enable response caching
- `CRAWL4AI_LOCALE` - Browser locale
- `CRAWL4AI_TIMEZONE` - Browser timezone

**Retry Configuration:**
- `CRAWL4AI_RETRY_ATTEMPTS` - Max retry attempts
- `CRAWL4AI_RETRY_BASE_DELAY` - Base delay for backoff
- `CRAWL4AI_RETRY_BACKOFF` - Backoff multiplier
- `CRAWL4AI_RETRY_JITTER` - Jitter factor

**LLM Configuration:**
- `CRAWL4AI_LLM_PROVIDER` - LLM provider string
- `CRAWL4AI_LLM_API_TOKEN` - LLM API token
- `CRAWL4AI_LLM_BASE_URL` - LLM API base URL
- `CRAWL4AI_LLM_BACKOFF_*` - LLM retry settings
- `CRAWL4AI_LLM_FILTER` - Enable LLM content filter
- `CRAWL4AI_LLM_FILTER_INSTRUCTION` - Custom filter instruction
- `CRAWL4AI_LLM_FILTER_CHUNK_TOKENS` - Token limit per chunk
- `CRAWL4AI_USE_OLLAMA` - Use local Ollama

**Content Filtering:**
- `CRAWL4AI_CONTENT_FILTER` - Filter type (pruning, bm25, none)
- `CRAWL4AI_PRUNING_THRESHOLD` - Pruning filter threshold
- `CRAWL4AI_PRUNING_THRESHOLD_TYPE` - Threshold type
- `CRAWL4AI_PRUNING_MIN_WORDS` - Minimum words per block
- `CRAWL4AI_BM25_THRESHOLD` - BM25 relevance threshold

**Ollama:**
- `OLLAMA_HOST` - Ollama server URL
- `OLLAMA_MODEL` - Default Ollama model

## Solution Overview

1. Create comprehensive `.env.example` with all variables
2. Group variables by category with clear descriptions
3. Add environment variables section to README
4. Update USAGE_GUIDE.md with full reference

## Implementation Steps

### Update .env.example

- [ ] Add all browser configuration variables
- [ ] Add all crawl behavior variables
- [ ] Add all retry configuration variables
- [ ] Add all LLM configuration variables
- [ ] Add all content filtering variables
- [ ] Add all Ollama variables
- [ ] Group by category with comment headers
- [ ] Include default values in comments
- [ ] Add brief description for each variable

### Update README.md

- [ ] Add "Environment Variables" section under Quick Start
- [ ] List essential variables (the must-configure ones)
- [ ] Reference USAGE_GUIDE.md for full list

### Update USAGE_GUIDE.md

- [ ] Create comprehensive environment variable reference table
- [ ] Document each variable: name, type, default, description
- [ ] Add examples for common configurations
- [ ] Add troubleshooting section for common env issues

### Fix Inconsistencies

- [ ] Fix timezone typo: "America/Brisbane" → "Australia/Brisbane"
- [ ] Ensure all defaults match between code and docs

## Files to Modify

- `.env.example` - Complete rewrite with all variables
- `README.md` - Add environment variables section
- `docs/40-usage/USAGE_GUIDE.md` - Add full reference
- `web_scraper/scrapers/crawl4ai.py` - Fix timezone default

## Testing Considerations

- Verify all documented variables actually work
- Test with minimal .env (only required vars)
- Test with full .env (all vars set)

## Success Criteria

- [ ] `.env.example` contains all 30+ environment variables
- [ ] Variables grouped by category with descriptions
- [ ] README has quick reference section
- [ ] USAGE_GUIDE.md has complete reference table
- [ ] No undocumented environment variables in code
- [ ] Timezone inconsistency fixed

## References

- `.cursor/rules/20-development-environment-web-scraper.mdc`
- `.cursor/rules/master/20-development-environment-basics.mdc`


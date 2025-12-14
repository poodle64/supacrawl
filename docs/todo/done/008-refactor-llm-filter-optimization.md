# LLM Content Filter Optimization

## ✅ STATUS: DONE

**Created**: 2025-12-12  
**Completed**: 2025-12-12  
**Type**: refactor

### Outcome

- Enhanced default LLM filter instruction (more specific and actionable)
- Increased chunk token threshold from 800 to 1000
- Improved instruction clarity for better filtering quality
- Note: input_format parameter not set (Crawl4AI may not support this parameter)
- Note: Documentation update pending (USAGE_GUIDE.md)

## Problem Summary

Current LLM content filter configuration is basic and not optimised. Default instruction is generic, chunk token threshold is low (800), and `input_format` is not set to use cleaned content. This reduces filter effectiveness and increases token costs unnecessarily.

## Solution Overview

Optimise LLM filter configuration: improve default instruction, increase chunk token threshold (1000-1200), set `input_format` to `"fit_markdown"` when available (reduces tokens by 60-80%), and enhance instruction specificity. Remove any redundant or non-effectual LLM filter code.

## Implementation Steps

### 1. Enhance Default LLM Filter Instruction

**File**: `web_scraper/scrapers/crawl4ai_config.py`

- Update default instruction to be more specific:
  ```
  "Extract main documentation content. Keep: headings, code blocks, tables, 
  parameter lists, examples, API references. Remove: navigation menus, 
  footers, cookie banners, advertisements, social media widgets, related 
  articles, site navigation, breadcrumbs."
  ```
- Make instruction actionable and specific (not generic)
- Allow customisation via `CRAWL4AI_LLM_FILTER_INSTRUCTION` env var

### 2. Optimise Chunk Token Threshold

**File**: `web_scraper/scrapers/crawl4ai_config.py`

- Increase default `chunk_token_threshold` from 800 to 1000-1200
- Larger chunks provide better context for LLM filtering
- Balance between context quality and token costs
- Keep environment variable override

### 3. Use Fit Markdown as Input Format

**File**: `web_scraper/scrapers/crawl4ai_config.py`

- Set `input_format="fit_markdown"` when creating `LLMContentFilter`
- This uses cleaned content (reduces tokens by 60-80%)
- Fallback to `"markdown"` if `fit_markdown` is not available
- Check Crawl4AI SDK support for this parameter

### 4. Clean Up LLM Filter Code

**File**: `web_scraper/scrapers/crawl4ai_config.py`

- Review LLM filter configuration for redundancy
- Remove any non-effectual LLM filter settings
- Ensure filter works alongside content filters (complementary)
- Keep code clean and focused

## Files to Modify

1. `web_scraper/scrapers/crawl4ai_config.py` - Optimise LLM filter configuration
2. `docs/40-usage/USAGE_GUIDE.md` - Document LLM filter best practices

## Testing Considerations

- Test LLM filter with optimised settings on existing site configs
- Verify token usage reduction with `fit_markdown` input format
- Compare content quality before/after optimisation
- Test fallback when `fit_markdown` is not available
- Monitor token costs and filter effectiveness

## Success Criteria

- LLM filter instruction is specific and actionable
- Chunk token threshold is optimised (1000-1200)
- `fit_markdown` input format is used when available (reduces tokens)
- Token costs are reduced while maintaining quality
- Code is clean and removes redundant LLM filter configuration

## References

- `docs/40-usage/crawl4ai-quality-best-practices.md` - Section 1.3
- `web_scraper/scrapers/crawl4ai_config.py` - Current LLM filter implementation (lines 136-166)

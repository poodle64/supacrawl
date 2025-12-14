# 014: Extract Magic Numbers into Configuration

## Status

✅ DONE (2025-12-13)

## Problem Summary

The codebase contains numerous hardcoded magic numbers that should be configurable:

```python
if i >= 5:  # Skip first 5 lines (definitely navigation)
if len(raw_headings) >= 15:  # Stop after 15 headings
if text_len < 120 and link_density > 0.3:  # Arbitrary thresholds
if word_count < 120 and density > 0.5:  # More thresholds
headings_to_add = raw_headings[:10]  # Why 10?
score += min(text_len / 500, 6)  # Magic scoring values
```

These make the code hard to tune and understand.

## Solution Overview

1. Create a configuration dataclass for content extraction settings
2. Replace magic numbers with named constants or config values
3. Allow environment variable overrides for key thresholds
4. Document what each threshold does

## Implementation Steps

### Create Configuration Module

- [ ] Create `web_scraper/content/config.py` with extraction settings

```python
from dataclasses import dataclass

@dataclass
class ExtractionConfig:
    """Configuration for content extraction."""
    
    # Navigation detection
    nav_skip_lines: int = 5  # Lines to skip at start (likely nav)
    max_headings_to_extract: int = 15  # Max headings to collect
    max_headings_to_restore: int = 10  # Max headings to prepend
    
    # Block scoring
    min_text_length_for_link_penalty: int = 120
    link_density_threshold: float = 0.3
    nav_block_link_density: float = 0.5
    text_length_score_divisor: int = 500
    max_text_length_score: float = 6.0
    
    # Sanitisation
    min_block_word_count: int = 120
    
    @classmethod
    def from_env(cls) -> "ExtractionConfig":
        """Load config with environment variable overrides."""
        ...
```

### Replace Magic Numbers

- [ ] `crawl4ai_result.py:74-87` - heading extraction thresholds
- [ ] `crawl4ai_result.py:125-126` - heading restoration
- [ ] `crawl4ai_result.py:296-297` - block scoring values
- [ ] `crawl4ai_result.py:316-317` - text length penalties
- [ ] `crawl4ai_result.py:432-434` - sanitisation thresholds
- [ ] `crawl4ai.py:218-219` - heading restoration

### Add Environment Variable Overrides

- [ ] `CRAWL4AI_NAV_SKIP_LINES` - lines to skip at start
- [ ] `CRAWL4AI_MIN_BLOCK_WORDS` - minimum words per block
- [ ] `CRAWL4AI_LINK_DENSITY_THRESHOLD` - link density for nav detection

### Document Thresholds

- [ ] Add docstrings explaining each threshold
- [ ] Add to `.env.example` with descriptions
- [ ] Document in `docs/40-usage/USAGE_GUIDE.md`

## Files to Modify

- Create `web_scraper/content/config.py`
- Refactor `web_scraper/scrapers/crawl4ai_result.py`
- Refactor `web_scraper/scrapers/crawl4ai.py`
- Update `.env.example`
- Update `docs/40-usage/USAGE_GUIDE.md`

## Testing Considerations

- Test default values work correctly
- Test environment variable overrides
- Test edge cases with different threshold values

## Success Criteria

- [ ] No unexplained numeric literals in extraction code
- [ ] All thresholds documented in config dataclass
- [ ] Environment variable overrides work
- [ ] Existing tests pass with default values
- [ ] Documentation updated

## References

- `.cursor/rules/master/90-code-quality-principles.mdc`


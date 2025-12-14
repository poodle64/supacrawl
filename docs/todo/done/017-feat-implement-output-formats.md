# 017: Implement All Declared Output Formats

## Status

📋 PLANNING

## Problem Summary

The SiteConfig model declares a `formats` field that accepts values like `["markdown", "html"]`, but:

1. Only markdown (`.md`) output is actually implemented
2. HTML format is accepted in config but ignored
3. The corpus writer always writes `.md` files regardless of config
4. Users expect their configured formats to be produced

```yaml
# This config accepts html but it's never produced
formats:
  - markdown
  - html
```

## Solution Overview

Implement proper format support:

1. **Markdown** (current) - Clean markdown from content
2. **HTML** - Cleaned HTML from Crawl4AI
3. **Plain text** - Stripped text content
4. **JSON** - Structured page data with metadata

Each format produces its own file(s) in the corpus.

## Implementation Steps

### Define Supported Formats

- [ ] Create `Format` enum in models.py:

```python
from enum import Enum

class OutputFormat(str, Enum):
    MARKDOWN = "markdown"
    HTML = "html"
    TEXT = "text"
    JSON = "json"
```

### Update Corpus Writer

- [ ] Modify `_write_page()` to accept format parameter
- [ ] Implement format-specific writing:
  - `markdown`: Current `.md` output
  - `html`: Write `.html` with cleaned HTML
  - `text`: Write `.txt` with plain text
  - `json`: Write `.json` with structured data

### Update Page Model

- [ ] Add `content_html` field to Page model (optional)
- [ ] Add `content_text` field to Page model (optional)
- [ ] Populate these fields in `extract_pages_from_result()`

### Update Manifest

- [ ] Include format in page entry
- [ ] Track which formats were produced per page

### Update Crawl4AI Result Extraction

- [ ] Extract `cleaned_html` from Crawl4AI result
- [ ] Store HTML content alongside markdown
- [ ] Generate plain text from markdown if needed

### CLI Updates

- [ ] Add `--formats` option to crawl command (override config)
- [ ] Validate format values

## Files to Modify

- `web_scraper/models.py` - Add OutputFormat enum, update Page
- `web_scraper/corpus/writer.py` - Multi-format writing
- `web_scraper/scrapers/crawl4ai_result.py` - Extract HTML content
- `web_scraper/cli.py` - Add format option
- `docs/40-usage/cli-usage-web-scraper.md` - Document formats

## Testing Considerations

- Test each output format individually
- Test multiple formats in single crawl
- Verify manifest reflects produced formats
- Test format validation in config loading

## Success Criteria

- [ ] All four formats (markdown, html, text, json) are implemented
- [ ] Config `formats` field is respected
- [ ] Each format produces appropriate file extension
- [ ] Manifest tracks which formats were produced
- [ ] CLI allows format override
- [ ] Documentation updated

## References

- `.cursor/rules/40-corpus-layout-patterns-web-scraper.mdc`
- `.cursor/rules/50-site-config-patterns-web-scraper.mdc`


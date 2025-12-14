# 025: Advanced Content Extraction Strategies

## Status

📋 PLANNING

## Problem Summary

Current content extraction relies on:
1. Crawl4AI's default extraction
2. PruningContentFilter/BM25 filters
3. Simple DOM scoring heuristics

This works for many sites but fails on:
- Complex JavaScript-rendered content
- Sites with non-standard layouts
- Pages with multiple content areas
- API documentation with code examples
- E-commerce product pages

## Solution Overview

Implement pluggable extraction strategies:

1. **Readability** - Mozilla-style article extraction
2. **CSS Selector** - User-defined selectors per site
3. **XPath** - More powerful selector for complex DOM
4. **Schema.org** - Extract structured data
5. **Custom** - Site-specific extraction rules

Users can configure which strategy to use per site.

## Implementation Steps

### Create Extraction Strategy Interface

- [ ] Create `web_scraper/extraction/base.py`:

```python
from abc import ABC, abstractmethod

class ExtractionStrategy(ABC):
    """Base class for content extraction strategies."""
    
    @abstractmethod
    async def extract(
        self,
        html: str,
        url: str,
        config: SiteConfig,
    ) -> ExtractionResult:
        """Extract content from HTML."""
        pass

@dataclass
class ExtractionResult:
    title: str
    content: str  # Main content
    metadata: dict[str, Any] = field(default_factory=dict)
    structured_data: dict[str, Any] | None = None
```

### Implement Strategies

- [ ] **ReadabilityStrategy** (`extraction/readability.py`):
  - Port Mozilla Readability algorithm
  - Focus on article content
  - Remove boilerplate

- [ ] **CSSStrategy** (`extraction/css.py`):
  - User-defined CSS selectors
  - Support multiple selectors with priority
  - Handle missing elements gracefully

- [ ] **XPathStrategy** (`extraction/xpath.py`):
  - XPath expressions for complex DOM
  - Support text and attribute extraction

- [ ] **SchemaStrategy** (`extraction/schema.py`):
  - Extract JSON-LD structured data
  - Parse Schema.org types
  - Extract OpenGraph/meta tags

- [ ] **CompositeStrategy** (`extraction/composite.py`):
  - Chain multiple strategies
  - Fallback on failure

### Configuration

- [ ] Add extraction config to SiteConfig:

```yaml
extraction:
  strategy: "css"  # readability, css, xpath, schema, composite
  
  # CSS strategy options
  css:
    content: "article.main, .content-body, main"
    title: "h1.title, head title"
    remove: ".sidebar, .comments, .ads"
  
  # XPath strategy options
  xpath:
    content: "//article | //main"
    title: "//h1[@class='title']/text()"
  
  # Composite strategy
  composite:
    - strategy: "schema"
      fallback: true
    - strategy: "css"
      fallback: true
    - strategy: "readability"
```

### Integration

- [ ] Use configured strategy in `extract_pages_from_result()`
- [ ] Support per-entrypoint strategy override
- [ ] Log which strategy was used

### Pre-built Configurations

- [ ] Create strategy presets for common sites:
  - Documentation sites (ReadTheDocs, GitBook, Docusaurus)
  - News sites
  - E-commerce (product pages)
  - Social media (Twitter, LinkedIn)

## Files to Modify

- Create `web_scraper/extraction/` module
- Create strategy implementations
- Update `web_scraper/models.py` - ExtractionConfig
- Update `web_scraper/scrapers/crawl4ai_result.py`
- Create preset configs in `presets/`
- Update docs

## Testing Considerations

- Test each strategy on representative HTML
- Test CSS selector edge cases
- Test XPath expressions
- Test schema.org extraction
- Test composite fallback behavior
- Create test fixtures for each site type

## Success Criteria

- [ ] 4+ extraction strategies implemented
- [ ] Strategies are configurable per site
- [ ] CSS and XPath selectors work
- [ ] Schema.org data is extracted
- [ ] Composite strategy with fallback works
- [ ] Presets available for common sites
- [ ] Documentation covers all strategies

## References

- Mozilla Readability: https://github.com/mozilla/readability
- Schema.org: https://schema.org/
- BeautifulSoup CSS selectors
- lxml XPath


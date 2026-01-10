---
paths: "**/test_*.py"
---

# Testing Patterns

**Note**: Universal testing patterns (error handling tests, input validation tests, retry logic tests) are covered in `.claude/rules/master/71-testing-patterns.md`.

This rule documents project-specific testing practice and relies on master rules for requirements.

## Core Principles

All supacrawl code must have comprehensive test coverage with supacrawl-specific patterns for service testing, LLM extraction testing, and cache testing.

## Mandatory Requirements

### Scraping Service Testing

- **Must** test `ScrapeService.scrape()` method with valid URLs
- **Must** test `CrawlService.crawl()` async generator with valid URLs
- **Must** test service error handling (network errors, timeouts)
- **Must** test service configuration (browser settings, formats)
- **Must** use dependency injection for testing (mock browser)

**Example:**
```python
async def test_scrape_service_success():
    """Test ScrapeService successfully scrapes URL."""
    service = ScrapeService()
    result = await service.scrape(
        url="https://example.com",
        formats=["markdown", "html"],
    )
    assert result.success
    assert result.data is not None
    assert result.data.markdown
    assert result.data.metadata.source_url == "https://example.com"
```

### LLM Extraction Testing

- **Must** test LLM extraction with valid prompts
- **Must** test LLM extraction with JSON schema validation
- **Must** test LLM provider configuration (Ollama, OpenAI, Anthropic)
- **Must** test LLM extraction error handling (provider unavailable)
- **Must** mock LLM providers for unit tests

**Example:**
```python
async def test_llm_extract_success(mock_ollama):
    """Test LLM extraction returns structured data."""
    service = ExtractService(provider="ollama")
    result = await service.extract(
        urls=["https://example.com"],
        prompt="Extract product names and prices",
    )
    assert result.success
    assert result.data is not None
```

### Cache Testing

- **Must** test cache read/write operations
- **Must** test cache expiration behaviour
- **Must** test cache clearing (all entries, by URL)
- **Must** test cache statistics reporting

**Example:**
```python
def test_cache_stores_scraped_content(tmp_path):
    """Test cache stores scraped content."""
    cache = Cache(cache_dir=tmp_path)
    cache.set("https://example.com", {"markdown": "# Test"})

    result = cache.get("https://example.com")
    assert result is not None
    assert result["markdown"] == "# Test"
```

### CLI Testing

- **Must** test CLI commands with Click test client
- **Must** test CLI error handling (exceptions show friendly messages)
- **Must** test CLI output format (stdout vs stderr)
- **Must** test CLI exit codes (0 for success, 1 for errors)

**Example:**
```python
def test_scrape_command(runner):
    """Test scrape command."""
    result = runner.invoke(app, ["scrape", "https://example.com"])
    assert result.exit_code == 0
    assert "# " in result.output  # Markdown header
```

### Integration Testing

- **Must** test end-to-end scrape flow (URL → ScrapeService → output)
- **Must** test crawl flow (URL → CrawlService → JSONL)
- **Must** test LLM extraction flow (URL → scrape → LLM → structured output)
- **Must** use test fixtures for common test data

## Key Directives

- **Service testing**: Test ScrapeService, CrawlService, MapService, ExtractService, SearchService
- **LLM testing**: Test extraction, provider switching, error handling
- **Cache testing**: Test storage, expiration, clearing
- **CLI testing**: Test commands, error handling, output format
- **Integration testing**: Test end-to-end workflows

## References

- `.claude/rules/master/71-testing-patterns.md` - Universal testing requirements
- `.claude/rules/70-error-handling.md` - Error handling patterns to test
- `docs/70-reliability/testing-supacrawl.md` - Comprehensive testing strategies

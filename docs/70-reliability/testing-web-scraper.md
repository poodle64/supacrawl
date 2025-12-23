# Testing Strategies

This document explains testing strategies for web-scraper.

## Testing Overview

Web-scraper uses pytest for testing with patterns for:

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test component interactions
- **Scraper Tests**: Test scraper services and error handling
- **CLI Tests**: Test command-line interface

## Test Categories

Tests are organised into directories with automatic marker assignment:

- **`tests/unit/`**: Pure logic tests, no I/O or browser (marker: `unit`)
- **`tests/integration/`**: Filesystem operations, mocks, local HTTP server (marker: `integration`)
- **`tests/e2e/`**: Real Playwright browser tests, slow (marker: `e2e`)

Run specific categories:

```bash
# Fast tests only (unit + integration)
pytest -q -m "not e2e"

# End-to-end tests only
pytest -q -m "e2e"

# All tests
pytest -q
```

### Live Network Tests

Two e2e baseline quality tests require live internet access to external websites. These tests are automatically skipped unless the `WEB_SCRAPER_TEST_ENABLED=1` environment variable is set:

```bash
# Run all tests including live network tests
WEB_SCRAPER_TEST_ENABLED=1 pytest -q

# Skip live network tests (default)
pytest -q
```

All other tests are fully offline-safe and use local fixtures only.

## Unit Testing Patterns

### Testing Service Classes

Test service initialization and error handling:

```python
def test_scrape_service_initialization():
    """Test scrape service initialization."""
    service = ScrapeService()
    assert service is not None
```

### Testing Site Configuration Loading

Test configuration loading and validation:

```python
def test_load_site_config_valid(tmp_path):
    """Test loading valid site configuration."""
    config_file = tmp_path / "test-site.yaml"
    config_file.write_text("""
id: test-site
name: Test Site
entrypoints:
  - https://example.com
include:
  - https://example.com/**
exclude: []
max_pages: 10
formats:
  - html
only_main_content: true
include_subdomains: false
""")
    config = load_site_config(config_file)
    assert config.id == "test-site"
```

### Testing Validation

Test validation rules:

```python
def test_site_config_empty_entrypoints():
    """Test site configuration rejects empty entrypoints."""
    with pytest.raises(ValidationError) as exc_info:
        SiteConfig(
            id="test-site",
            name="Test Site",
            entrypoints=[],  # Empty entrypoints
            include=["https://example.com/**"],
            exclude=[],
            max_pages=10,
            formats=["html"],
            only_main_content=True,
            include_subdomains=False,
        )
    assert exc_info.value.field == "entrypoints"
    assert exc_info.value.correlation_id is not None
```

## Integration Testing Patterns

### Testing End-to-End Crawl Flow

Test complete crawl workflow:

```python
def test_crawl_flow(tmp_path, mock_provider_client):
    """Test end-to-end crawl flow."""
    # Setup
    sites_dir = tmp_path / "sites"
    sites_dir.mkdir()
    config_file = sites_dir / "test-site.yaml"
    config_file.write_text("...")
    
    corpora_dir = tmp_path / "corpora"
    
    # Execute
    config = load_site_config(config_file)
    scrape_service = ScrapeService()
    pages = await scrape_service.scrape_urls(config.entrypoints)
    snapshot_id = write_snapshot(corpora_dir, config, pages)
    
    # Verify
    manifest_path = corpora_dir / config.id / snapshot_id / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["total_pages"] == len(pages)
```

### Testing Corpus Writer

Test snapshot creation and manifest structure:

```python
def test_write_snapshot_creates_manifest(tmp_path):
    """Test writing snapshot creates manifest.json."""
    corpora_dir = tmp_path / "corpora"
    config = SiteConfig(...)
    pages = [Page(...), Page(...)]
    
    snapshot_id = write_snapshot(corpora_dir, config, pages)
    
    manifest_path = corpora_dir / config.id / snapshot_id / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["site_id"] == config.id
    assert manifest["total_pages"] == len(pages)
    assert len(manifest["pages"]) == len(pages)
```

## Service Testing Patterns

### Mocking Browser Clients

Use dependency injection for testability:

```python
@pytest.fixture
def mock_browser_context():
    """Mock browser context for testing."""
    context = AsyncMock()
    page = AsyncMock()
    page.content = AsyncMock(return_value="<html><body>Test</body></html>")
    page.goto = AsyncMock()
    context.new_page = AsyncMock(return_value=page)
    return context


async def test_scrape_service_success(mock_browser_context):
    """Test scrape service successfully scrapes page."""
    service = ScrapeService(browser_context=mock_browser_context)
    result = await service.scrape("https://example.com")
    assert result.success
    assert result.content is not None
```

### Testing Service Error Handling

Test error wrapping:

```python
async def test_scrape_service_error_handling():
    """Test scrape service error handling."""
    service = ScrapeService()

    with pytest.raises(ScraperError) as exc_info:
        await service.scrape("invalid://url")

    assert exc_info.value.correlation_id is not None
    assert "original_error" in exc_info.value.context
```

### Testing Retry Logic

Test retry behavior:

```python
async def test_scrape_service_retry_logic(mock_browser_retry):
    """Test scrape service retry logic."""
    # First two calls fail, third succeeds
    call_count = 0
    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise TimeoutError("Transient error")
        return "<html><body>Success</body></html>"

    mock_browser_retry.new_page().goto = AsyncMock(side_effect=side_effect)

    service = ScrapeService(browser_context=mock_browser_retry)
    result = await service.scrape("https://example.com")

    assert result.success
    assert call_count == 3
```

## CLI Testing Patterns

### Testing CLI Commands

Use Click test client:

```python
from click.testing import CliRunner

def test_list_sites_command(tmp_path):
    """Test list-sites command."""
    runner = CliRunner()
    sites_dir = tmp_path / "sites"
    sites_dir.mkdir()
    (sites_dir / "test-site.yaml").write_text("...")
    
    result = runner.invoke(app, ["list-sites", "--base-path", str(tmp_path)])
    assert result.exit_code == 0
    assert "test-site" in result.output
```

### Testing CLI Error Handling

Test error messages and exit codes:

```python
def test_crawl_command_invalid_site(tmp_path):
    """Test crawl command with invalid site."""
    runner = CliRunner()
    
    result = runner.invoke(app, ["crawl", "nonexistent-site", "--base-path", str(tmp_path)])
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "correlation_id=" in result.output
```

## Test Fixtures

### Common Fixtures

Create reusable test fixtures:

```python
@pytest.fixture
def sample_site_config():
    """Sample site configuration for testing."""
    return SiteConfig(
        id="test-site",
        name="Test Site",
        entrypoints=["https://example.com"],
        include=["https://example.com/**"],
        exclude=[],
        max_pages=10,
        formats=["html"],
        only_main_content=True,
        include_subdomains=False,
    )


@pytest.fixture
def sample_pages():
    """Sample pages for testing."""
    return [
        Page(
            url="https://example.com/page1",
            title="Page 1",
            content="Content 1",
            content_hash="hash1",
            path="/page1",
        ),
        Page(
            url="https://example.com/page2",
            title="Page 2",
            content="Content 2",
            content_hash="hash2",
            path="/page2",
        ),
    ]
```

## Best Practices

1. **Isolation**: Each test should be independent
2. **Fixtures**: Use fixtures for common test data
3. **Mocking**: Mock external dependencies (providers, file system)
4. **Coverage**: Test error paths, not just happy paths
5. **Correlation IDs**: Verify correlation IDs in error tests
6. **Cleanup**: Clean up test artifacts (temp files, directories)

## Running Tests

### Run All Tests

```bash
pytest -q
```

### Run Specific Test File

```bash
pytest tests/test_scrapers.py -q
```

### Run with Coverage

```bash
pytest --cov=web_scraper --cov-report=html
```

## References

- `.cursor/rules/71-testing-patterns-web-scraper.mdc` - Testing pattern requirements
- `.cursor/rules/master/71-testing-patterns-basics.mdc` - Universal testing requirements
- `docs/70-reliability/error-handling-web-scraper.md` - Error handling patterns

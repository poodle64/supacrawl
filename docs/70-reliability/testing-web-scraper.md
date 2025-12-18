# Testing Strategies

This document explains testing strategies for web-scraper.

## Testing Overview

Web-scraper uses pytest for testing with patterns for:

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test component interactions
- **Scraper Tests**: Test Crawl4AI scraper and error handling
- **CLI Tests**: Test command-line interface

## Test Categories

Tests are organised into directories with automatic marker assignment:

- **`tests/unit/`**: Pure logic tests, no I/O or browser (marker: `unit`)
- **`tests/integration/`**: Filesystem operations, mocks, local HTTP server (marker: `integration`)
- **`tests/e2e/`**: Real Crawl4AI/Playwright, slow (marker: `e2e`)

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

Two e2e baseline quality tests require live internet access to external websites. These tests are automatically skipped unless the `CRAWL4AI_TEST_ENABLED=1` environment variable is set:

```bash
# Run all tests including live network tests
CRAWL4AI_TEST_ENABLED=1 pytest -q

# Skip live network tests (default)
pytest -q
```

All other tests are fully offline-safe and use local fixtures only.

## Unit Testing Patterns

### Testing Provider Classes

Test provider initialization and error handling:

```python
def test_crawl4ai_scraper_initialization():
    """Test Crawl4AI scraper initialization."""
    scraper = Crawl4AIScraper()
    assert scraper.provider_name == "crawl4ai"
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
provider: crawl4ai
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
    assert config.provider == "crawl4ai"
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
            provider="crawl4ai",
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
    scraper = Crawl4AIScraper(crawler=mock_provider_client)
    pages = scraper.crawl(config)
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

## Provider Testing Patterns

### Mocking Provider Clients

Use dependency injection for testability:

```python
@pytest.fixture
def mock_crawl4ai_client():
    """Mock Crawl4AI client for testing."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.arun = AsyncMock(return_value=[
        Mock(url="https://example.com", title="Example", markdown="...", success=True)
    ])
    return client


def test_crawl4ai_scraper_crawl_success(mock_crawl4ai_client):
    """Test Crawl4AI scraper successfully crawls site."""
    scraper = Crawl4AIScraper(crawler=mock_crawl4ai_client)
    config = SiteConfig(...)
    pages = scraper.crawl(config)
    assert len(pages) > 0
    assert all(isinstance(page, Page) for page in pages)
```

### Testing Provider Error Handling

Test provider error wrapping:

```python
def test_crawl4ai_scraper_error_handling(mock_crawl4ai_client_error):
    """Test Crawl4AI scraper error handling."""
    mock_crawl4ai_client_error.__aenter__ = AsyncMock(side_effect=RuntimeError("API error"))
    
    scraper = Crawl4AIScraper(crawler=mock_crawl4ai_client_error)
    config = SiteConfig(...)
    
    with pytest.raises(ProviderError) as exc_info:
        scraper.crawl(config)
    
    assert exc_info.value.provider == "crawl4ai"
    assert exc_info.value.correlation_id is not None
    assert "original_error" in exc_info.value.context
```

### Testing Provider Retry Logic

Test retry behavior:

```python
def test_crawl4ai_scraper_retry_logic(mock_crawl4ai_client_retry):
    """Test Crawl4AI scraper retry logic."""
    # First two calls fail, third succeeds
    call_count = 0
    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError("Transient error")
        return [Mock(url="https://example.com", title="Example", markdown="...", success=True)]
    
    mock_crawl4ai_client_retry.__aenter__ = AsyncMock(return_value=mock_crawl4ai_client_retry)
    mock_crawl4ai_client_retry.__aexit__ = AsyncMock(return_value=None)
    mock_crawl4ai_client_retry.arun = AsyncMock(side_effect=side_effect)
    
    scraper = Crawl4AIScraper(crawler=mock_crawl4ai_client_retry)
    config = SiteConfig(...)
    pages = scraper.crawl(config)
    
    assert len(pages) > 0
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
        provider="crawl4ai",
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

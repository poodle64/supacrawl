# 026: Export Integrations

## Status

📋 PLANNING

## Problem Summary

Currently all output goes to local filesystem only:
- `corpora/{site_id}/{snapshot_id}/`

This limits use cases:
- No cloud storage support
- No database integration
- No streaming to external systems
- No webhook notifications
- Can't feed directly to LLM pipelines

## Solution Overview

Add export integrations:

1. **Cloud Storage** - S3, GCS, Azure Blob
2. **Database** - SQLite, PostgreSQL
3. **Webhooks** - HTTP callbacks per page/crawl
4. **Message Queue** - Redis, RabbitMQ
5. **Direct LLM** - Stream to embedding pipeline

## Implementation Steps

### Create Exporter Interface

- [ ] Create `web_scraper/export/base.py`:

```python
from abc import ABC, abstractmethod

class Exporter(ABC):
    """Base class for export destinations."""
    
    @abstractmethod
    async def export_page(self, page: Page, snapshot_id: str) -> None:
        """Export a single page."""
        pass
    
    @abstractmethod
    async def export_manifest(self, manifest: dict, snapshot_id: str) -> None:
        """Export crawl manifest."""
        pass
    
    async def on_crawl_start(self, config: SiteConfig) -> None:
        """Called when crawl starts."""
        pass
    
    async def on_crawl_complete(self, stats: CrawlStats) -> None:
        """Called when crawl completes."""
        pass
```

### Implement Exporters

- [ ] **S3Exporter** (`export/s3.py`):
  - Upload pages to S3 bucket
  - Configurable paths and prefixes
  - Support presigned URLs

- [ ] **DatabaseExporter** (`export/database.py`):
  - SQLite for local use
  - PostgreSQL for production
  - Schema for pages, chunks, metadata

- [ ] **WebhookExporter** (`export/webhook.py`):
  - POST each page to webhook URL
  - Configurable batch size
  - Retry on failure

- [ ] **FilesystemExporter** (`export/filesystem.py`):
  - Current behavior as explicit exporter
  - Make it the default

### Configuration

- [ ] Add export config to SiteConfig:

```yaml
export:
  # Local filesystem (default)
  filesystem:
    enabled: true
    path: "corpora/"
  
  # S3 storage
  s3:
    enabled: false
    bucket: "my-scraper-bucket"
    prefix: "corpora/"
    region: "us-east-1"
  
  # Database
  database:
    enabled: false
    url: "postgresql://user:pass@localhost/scraper"
  
  # Webhook
  webhook:
    enabled: false
    url: "https://api.example.com/ingest"
    batch_size: 10
    headers:
      Authorization: "Bearer ${WEBHOOK_TOKEN}"
```

### Multi-Export Support

- [ ] Support multiple exporters simultaneously
- [ ] Export to filesystem AND S3
- [ ] Configure per-exporter settings

### CLI Updates

- [ ] Add `--export` flag to crawl command:

```bash
web-scraper crawl meta --export s3
web-scraper crawl meta --export webhook --webhook-url https://...
```

### Environment Variables

- [ ] AWS credentials for S3
- [ ] Database connection strings
- [ ] Webhook tokens

## Files to Modify

- Create `web_scraper/export/` module
- Create exporter implementations
- Update `web_scraper/models.py` - ExportConfig
- Update `web_scraper/scrapers/crawl4ai.py` - Use exporters
- Update `web_scraper/cli.py` - Export flags
- Update `pyproject.toml` - Optional deps (boto3, psycopg2)
- Update docs

## Testing Considerations

- Test each exporter independently
- Use moto for S3 mocking
- Use test database for DB exporter
- Use httpx mock for webhook testing
- Test multi-export scenarios

## Success Criteria

- [ ] Filesystem exporter works (current behavior)
- [ ] S3 exporter uploads correctly
- [ ] Database exporter stores pages
- [ ] Webhook exporter calls URLs
- [ ] Multiple exporters can run together
- [ ] Documentation covers all exporters
- [ ] Optional dependencies are handled

## References

- boto3 for AWS S3
- SQLAlchemy for database
- httpx for webhooks


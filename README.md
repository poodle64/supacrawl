# supacrawl

**A local-first, CLI-driven website ingestion tool for building LLM-ready corpora.**

Supacrawl is a Python CLI that uses Playwright to produce snapshot-based, filesystem-first website archives. It's designed for developers who need clean, versioned website content for LLM consumption without relying on SaaS scraping services. Produces Firecrawl-compatible markdown output format, running entirely on your machine with no API keys, rate limits, or external dependencies.

## What This Tool Is

- **Local-first**: Runs entirely on your machine using Playwright
- **Snapshot-oriented**: Each crawl creates a timestamped, immutable corpus with manifest metadata
- **LLM-focused**: Produces markdown, HTML, and optional JSONL chunks suitable for LLM ingestion
- **Configuration-driven**: YAML site configs define crawl parameters, no code required
- **Quality-first**: Uses Playwright for JS rendering, content pruning, and anti-bot bypass
- **Archival-ready**: Versioned snapshots with checksums, compression, and resumable crawls

## What This Tool Is Not

- **Not a SaaS replacement**: No hosted service, no API endpoints, no multi-tenancy
- **Not a custom crawler**: Uses Playwright for browser automation, focuses on corpus building
- **Not for live data**: Snapshots are point-in-time archives, not real-time feeds
- **Not lightweight**: Uses Playwright browsers, trades speed for quality and JS support
- **Not a database**: Writes to filesystem, no query layer or indexing
- **Not for high-frequency scraping**: Designed for periodic, polite crawls (hours/days, not seconds)

## Comparison to Firecrawl

Supacrawl produces **Firecrawl-compatible markdown output** (same format: clean markdown, structured manifests, LLM-ready chunks) but with a **different deployment model** (local CLI vs hosted API):

| Feature | supacrawl | Firecrawl |
|---------|-------------|-----------|
| **Deployment** | Local CLI | Hosted SaaS |
| **Cost** | Free (local compute) | Paid API credits |
| **Rate limits** | None (self-imposed politeness) | API tier limits |
| **Setup** | Install Python + Playwright | API key |
| **Use case** | Periodic corpus building | On-demand scraping |
| **Output format** | Snapshot directories | API responses |
| **Customisation** | Configure via YAML + env vars | API parameters only |

**When to use supacrawl**: You need versioned, archival website corpora for LLM training/RAG, you want full control over crawl behaviour, and you're comfortable running local infrastructure.

**When to use Firecrawl**: You need on-demand scraping via API, you want zero infrastructure management, or you're building a production service that requires SLA-backed uptime guarantees.

## Quality Status

**Current State**: ✅ **Production Ready**

Supacrawl produces Firecrawl-compatible markdown output with excellent quality on prose content. The tool has been tested against Firecrawl's output format and achieves high similarity scores.

**Output formats**: markdown, HTML, and optional JSONL chunks for LLM consumption.

## Core Workflow

```
1. Create YAML site config (sites/example.yaml)
2. Run crawl: supacrawl crawl example
3. Get output: corpora/example/latest/
   ├── manifest.json       (metadata, checksums, URLs)
   ├── .meta/              (internal: crawl state, logs, checksums)
   ├── markdown/           (clean markdown content)
   └── html/               (original HTML)
4. Optional: Chunk for LLM: supacrawl crawl example --chunks
   └── chunks.jsonl        (LLM-ready chunks with metadata)
```

**Key features:**
- **latest/ symlink**: Always points to the most recent snapshot
- **Versioned snapshots**: Each crawl creates a timestamped snapshot (e.g., `2025-01-18_1430`)
- **Auto-resume**: Interrupted crawls resume automatically (use `--fresh` to start over)
- **Immutable**: Snapshots are never overwritten
- **Ctrl+C safe**: Progress is saved, resume by running the same command again

## Quick Start

### Prerequisites

- Python 3.12+
- Conda (recommended) or Python virtual environment
- ~2GB disk space for Playwright browsers

### Installation

1. **Create conda environment**:
   ```bash
   conda env create -f environment.yaml
   conda activate supacrawl
   ```

2. **Install dependencies**:
   ```bash
   pip install -e .
   ```

3. **Install Playwright browsers** (one-time setup):
   ```bash
   playwright install chromium
   ```

4. **Verify installation**:
   ```bash
   supacrawl list-sites
   ```

### First Crawl

```bash
# List example site configs
supacrawl list-sites

# Show config details
supacrawl show-site meta

# Run crawl (creates corpora/meta/latest/)
supacrawl crawl meta

# Chunk for LLM consumption (creates corpora/meta/latest/chunks.jsonl)
supacrawl crawl meta --chunks

# Or chunk an existing snapshot
supacrawl chunk meta latest
```

## Quick Start from URL

Create a site config and crawl in one command:

```bash
# Initialize from URL and start crawling immediately
supacrawl crawl https://example.com --init my-site

# Or create config first, then crawl
supacrawl init my-site --url https://example.com
supacrawl crawl my-site
```

## CLI Commands

| Command | Purpose |
|---------|---------|
| `supacrawl list-sites` | List available site configuration files |
| `supacrawl show-site <name>` | Show site configuration details |
| `supacrawl init <name>` | Create a new site configuration interactively |
| `supacrawl list-snapshots <name>` | List all snapshots for a site |
| `supacrawl map <name>` | Discover URLs from sitemap without crawling |
| `supacrawl crawl <name>` | Run a crawl and create a snapshot |
| `supacrawl chunk <site> <snapshot>` | Chunk snapshot into JSONL for LLM consumption |
| `supacrawl compress <site> <snapshot>` | Compress a snapshot for archival |
| `supacrawl extract <archive>` | Extract a compressed snapshot archive |

### Crawl Options

```bash
supacrawl crawl <site-name> [OPTIONS]
  --verbose          Show crawl progress logs and snapshot IDs
  --fresh            Start a fresh crawl (ignore incomplete snapshots)
  --chunks           Generate chunks.jsonl after crawling
  --max-chars <int>  Maximum characters per chunk (default: 1200)
  --dry-run          Preview URLs without fetching content
  --init <name>      Create config from URL (use with URL as site argument)
  --formats <list>   Output formats: markdown, html, text, json
  --from-map <file>  Crawl only URLs listed in a map file (json or jsonl)
  --concurrency <n>  Override max concurrent pages (1-20)
  --delay <secs>     Override delay between requests (seconds)
  --timeout <secs>   Override page load timeout (seconds)
  --retries <n>      Override max retry attempts
```

**Note:** Crawls automatically resume from incomplete snapshots. Use `--fresh` to start over.

### Chunk Options

```bash
supacrawl chunk <site-id> <snapshot-id> [OPTIONS]
  --max-chars <int>    Maximum characters per chunk (default: 1200)
  --use-ollama         Enable Ollama for AI processing
  --ollama-summarize   Add AI-generated summaries to chunks
  --ollama-model <m>   Override Ollama model (default: llama3.2)
```

## Site Configuration

Create YAML files in `sites/` directory. The filename (without `.yaml`) becomes the site identifier.

**Minimal example** (`sites/example.yaml`):
```yaml
name: Example Site
entrypoints:
  - https://example.com
include:
  - https://example.com/**
exclude: []
max_pages: 100
formats:
  - markdown
  - html
only_main_content: true
include_subdomains: false
```

**Note:** The `id` field is optional and will be automatically derived from the filename. If you include an explicit `id`, it must match the filename stem (e.g., `example.yaml` requires `id: example`).

**With politeness controls**:
```yaml
name: Example Site
entrypoints:
  - https://example.com
include:
  - https://example.com/docs/**
exclude:
  - https://example.com/admin/**
max_pages: 500
formats:
  - markdown
  - html
only_main_content: true
include_subdomains: false
politeness:
  max_concurrent: 3              # Concurrent page crawls (1-20)
  delay_between_requests: [2.0, 4.0]  # Random delay range (seconds)
  page_timeout: 120              # Page load timeout (seconds)
  max_retries: 3                 # Retry attempts for failed requests
```

See [Creating Site Configurations](docs/40-usage/creating-site-configs-supacrawl.md) for detailed documentation.

## Quality-Focused Defaults

Supacrawl is pre-configured for quality over speed. Most users don't need to change anything.

**Built-in defaults**:
- **Stealth mode**: Random user agents, realistic viewport (1280x720), magic mode for anti-bot bypass
- **Content extraction**: Pruning filter removes boilerplate, keeps main content
- **Retry logic**: 3 attempts with exponential backoff for transient failures
- **Politeness**: 1-2 second delay between requests, max 5 concurrent pages
- **JS rendering**: Full Playwright browser (not lightweight HTTP)

**When to override**:
- Slow sites: Increase `page_timeout` via CLI or YAML
- Aggressive crawling: Increase `max_concurrent` (not recommended for public sites)
- Debugging: Set `SUPACRAWL_HEADLESS=false` to see browser

See `.env.example` for optional configuration overrides.

## Graceful Interruption and Resumption

Press Ctrl+C during a crawl to stop gracefully:
- Manifest is updated with `status: aborted`
- Crawl state is saved to `.meta/crawl_state.json`
- Resume by running the same command again

Crawls automatically resume from incomplete snapshots. Resumption skips already-crawled URLs and continues from where you left off. Use `--fresh` to start a new snapshot instead.

## Optional Ollama Integration

Enable local LLM processing for content enhancement (requires Ollama running on `localhost:11434`).

**During chunking** (AI-generated summaries):
```bash
supacrawl chunk <site-id> <snapshot-id> --use-ollama --ollama-summarize
```

**Configuration**:
- `OLLAMA_HOST`: Ollama server URL (default: `http://localhost:11434`)
- `OLLAMA_MODEL`: Model to use (default: `llama3.2`)

See [Ollama documentation](https://ollama.com/) for installation and model management.

## Environment Variables

All configuration is optional. Sensible defaults are built in. Copy `.env.example` to `.env` only if you need to change settings.

### Commonly Changed Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SUPACRAWL_HEADLESS` | `true` | Set to `false` to see the browser for debugging |
| `SUPACRAWL_TIMEOUT` | `30000` | Timeout per page in milliseconds (increase for slow sites) |

### Ollama Integration (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3.2` | Model to use for summaries |

See `.env.example` for advanced settings (content filtering thresholds, LLM configuration).

## Output Structure

Each crawl creates a snapshot directory: `corpora/<site_id>/<snapshot_id>/`

**Snapshot contents**:
```
corpora/example/2025-12-18_1430/
├── manifest.json         # Metadata, URLs, checksums, status
├── .meta/                # Internal artefacts
│   ├── crawl_state.json  # Resumable crawl state
│   ├── checksums.sha256  # SHA256 checksums for all files
│   └── run.log.jsonl     # Structured crawl logs
├── markdown/             # Clean markdown content
│   ├── page1.md
│   └── page2.md
├── html/                 # Original HTML
│   ├── page1.html
│   └── page2.html
└── chunks.jsonl          # Optional LLM-ready chunks
```

**Snapshot ID format**: `YYYY-MM-DD_HHMM` (timezone: `Australia/Brisbane`)

See [Corpus Layout](docs/30-architecture/corpus-layout-supacrawl.md) for detailed documentation.

## Development

### Dependency Management

- ✅ Use `pyproject.toml` for all dependencies
- ✅ Install from `pyproject.toml` using `pip install -e .`
- ❌ Do NOT use `requirements.txt` files

### Quality Checks

```bash
# Linting
ruff check supacrawl tools

# Type checking
mypy supacrawl

# Fast local testing (excludes browser-based e2e tests)
pytest -q -m "not e2e"

# Parallel testing (recommended for local development)
pytest -q -m "not e2e" -n auto

# Full CI suite (includes all e2e tests)
pytest -q
```

### Test Categories

Tests are organised into directories with automatic marker assignment:

| Directory | Marker | Description | Typical Runtime |
|-----------|--------|-------------|-----------------|
| `tests/unit/` | `unit` | Pure logic, no I/O or browser | ~1.5s |
| `tests/integration/` | `integration` | Filesystem, mocks, local HTTP | ~3s |
| `tests/e2e/` | `e2e` | Real Playwright browser tests | ~5 minutes |

**Live Network Tests**: Two e2e baseline tests require live internet access to external sites. These tests are automatically skipped in CI unless `SUPACRAWL_TEST_ENABLED=1` is set. All other tests are fully offline-safe and use local fixtures only.

Use `pytest -m "not e2e"` for fast feedback during development.

## Versioning

- **Version format**: `YYYY.MM.x` (e.g., `2025.12.0`)
- **Location**: `VERSION` file and `pyproject.toml`
- **Git tags**: `v{YYYY}.{MM}.{x}` (e.g., `v2025.12.0`)

```bash
# Check version
cat VERSION
python -c "from supacrawl import __version__; print(__version__)"
```

## Standards

All code in this project follows these standards:

- **Python**: 3.12+ (modern type hints, async/await patterns)
- **CLI Framework**: Click (consistent command structure and error handling)
- **Data Validation**: Pydantic v2 only (no deprecated features)
- **Dependencies**: `pyproject.toml` (PEP 621), NOT requirements.txt
- **Code Style**: Australian English spelling, comprehensive type hints
- **Configuration**: YAML files in `sites/` directory
- **Output**: Corpus snapshots in `corpora/` directory with snapshot-based layout
- **Secrets**: Environment variables via `.env` file (never commit `.env`)

## Contributing

1. Follow the standards defined in `.cursor/rules/`
2. Use conventional commits (see `.cursor/rules/master/10-git-workflow.mdc`)
3. Ensure all quality checks pass (`ruff check`, `mypy`, `pytest`)
4. Update documentation as needed
5. Keep changes focused and well-documented

## Resources

### Documentation
- **CLI Usage**: [CLI Usage Guide](docs/40-usage/cli-usage-supacrawl.md)
- **Site Configuration**: [Creating Site Configurations](docs/40-usage/creating-site-configs-supacrawl.md)
- **Architecture**: [Corpus Layout](docs/30-architecture/corpus-layout-supacrawl.md), [Site Configuration](docs/30-architecture/site-configuration-supacrawl.md)
- **Reliability**: [Error Handling](docs/70-reliability/error-handling-supacrawl.md), [Retry Logic](docs/70-reliability/retry-logic-supacrawl.md), [Testing](docs/70-reliability/testing-supacrawl.md)

### Development
- **Development Rules**: [.cursor/rules/](.cursor/rules/)
- **GitHub Issues**: [Issue Tracker](https://github.com/poodle64/supacrawl/issues)

### External
- **Playwright Documentation**: https://playwright.dev/python/
- **Ollama Documentation**: https://ollama.com/

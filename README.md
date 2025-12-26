# supacrawl

A local-first, Firecrawl-compatible web scraper CLI. Uses Playwright for JavaScript rendering and produces clean markdown output.

## Installation

### Prerequisites

- Python 3.12+
- Conda (recommended) or Python virtual environment
- ~2GB disk space for Playwright browsers

### Setup

```bash
# Create and activate conda environment
conda env create -f environment.yaml
conda activate supacrawl

# Install package
pip install -e .

# Install Playwright browsers (one-time)
playwright install chromium

# Verify installation
supacrawl --help
```

## Quick Start

```bash
# Scrape a single page to markdown
supacrawl scrape https://example.com

# Crawl a website (saves to output directory)
supacrawl crawl https://example.com -o ./output

# Discover all URLs on a site
supacrawl map https://example.com

# Web search
supacrawl search "python web scraping"

# Extract structured data with LLM
supacrawl llm-extract https://example.com/pricing --prompt "Extract pricing tiers"

# Autonomous agent for complex tasks
supacrawl agent "Find the documentation for API authentication"

# Manage cache
supacrawl cache clear
```

## Command Reference

| Command | Description |
|---------|-------------|
| `supacrawl scrape <url>` | Scrape a single page and output markdown |
| `supacrawl crawl <url>` | Crawl website, following links within domain |
| `supacrawl map <url>` | Discover URLs from sitemap/links without fetching content |
| `supacrawl search <query>` | Web search and return results |
| `supacrawl llm-extract <urls>` | Extract structured data using LLM |
| `supacrawl agent <prompt>` | Autonomous agent for complex scraping tasks |
| `supacrawl cache` | Cache management (clear, stats) |

## Command Examples

### Scrape a Single Page

```bash
# Basic scrape - outputs markdown to stdout
supacrawl scrape https://docs.python.org/3/tutorial/

# Save to file
supacrawl scrape https://docs.python.org/3/tutorial/ -o tutorial.md

# Include HTML output
supacrawl scrape https://example.com --formats markdown,html

# Extract only main content (skip navigation, footers)
supacrawl scrape https://example.com --only-main-content
```

### Crawl a Website

```bash
# Crawl and save to directory
supacrawl crawl https://docs.python.org/3/ -o ./python-docs

# Limit pages crawled
supacrawl crawl https://example.com -o ./output --max-pages 50

# Control concurrency and delay
supacrawl crawl https://example.com -o ./output --concurrency 3 --delay 2.0

# Include subdomains
supacrawl crawl https://example.com -o ./output --include-subdomains
```

### Map URLs

```bash
# Discover URLs from sitemap
supacrawl map https://example.com

# Output as JSON
supacrawl map https://example.com --format json

# Limit discovery depth
supacrawl map https://example.com --max-depth 2
```

### LLM Extract

```bash
# Extract structured data
supacrawl llm-extract https://example.com/pricing \
  --prompt "Extract all pricing tiers with features and costs"

# Extract from multiple pages
supacrawl llm-extract https://example.com/team https://example.com/about \
  --prompt "Extract team member names and roles"

# Use specific schema
supacrawl llm-extract https://example.com/product \
  --schema '{"name": "string", "price": "number", "features": ["string"]}'
```

### Agent

```bash
# Autonomous research agent
supacrawl agent "Find the API rate limits for this service" \
  --url https://api.example.com/docs

# Multi-step task
supacrawl agent "Navigate to the pricing page and extract all plan details"
```

### Cache Management

```bash
# Show cache statistics
supacrawl cache stats

# Clear all cached content
supacrawl cache clear

# Clear cache older than 7 days
supacrawl cache clear --older-than 7d
```

## Output Formats

Supacrawl produces Firecrawl-compatible output:

- **Markdown**: Clean, readable content with preserved structure
- **HTML**: Original HTML for reference
- **JSON**: Structured metadata and content

### Crawl Output Structure

```
output/
├── index.md              # Main page
├── about.md              # Subpage
├── docs/
│   ├── getting-started.md
│   └── api-reference.md
└── manifest.json         # Crawl metadata
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SUPACRAWL_HEADLESS` | `true` | Set `false` to see browser window |
| `SUPACRAWL_TIMEOUT` | `30000` | Page load timeout (ms) |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server for LLM features |
| `OLLAMA_MODEL` | `qwen3:8b` | Model for extraction/agent |

Copy `.env.example` to `.env` to customise settings.

## Development

### Running Tests

```bash
# Fast tests (excludes browser-based e2e)
pytest -q -m "not e2e"

# Parallel testing
pytest -q -m "not e2e" -n auto

# Full test suite including e2e
pytest -q

# Linting and type checking
ruff check src/supacrawl
mypy src/supacrawl
```

### Test Categories

| Directory | Marker | Description |
|-----------|--------|-------------|
| `tests/unit/` | `unit` | Pure logic tests |
| `tests/integration/` | `integration` | Filesystem and HTTP tests |
| `tests/e2e/` | `e2e` | Full Playwright browser tests |

## How It Works

1. **Playwright-based**: Full browser rendering for JavaScript-heavy sites
2. **Content extraction**: Intelligent removal of navigation, ads, and boilerplate
3. **Markdown conversion**: Clean markdown preserving document structure
4. **Polite crawling**: Configurable delays and concurrency to respect servers

## Comparison to Firecrawl

| Feature | supacrawl | Firecrawl |
|---------|-----------|-----------|
| **Deployment** | Local CLI | Hosted SaaS |
| **Cost** | Free | Paid API |
| **Rate limits** | Self-managed | API tier limits |
| **Output format** | Firecrawl-compatible | Native |
| **JS rendering** | Playwright | Cloud browsers |

## Licence

MIT

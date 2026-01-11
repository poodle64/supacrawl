# CLI Usage Guide

This guide covers using the supacrawl command-line interface.

## Command Overview

The `supacrawl` CLI provides commands for web scraping, URL mapping, search, and LLM-based data extraction.

### Available Commands

- `scrape` - Scrape a single URL to markdown
- `crawl` - Crawl a website from a starting URL
- `map` - Map URLs from a website
- `search` - Search the web using DuckDuckGo or Brave
- `llm-extract` - Extract structured data using LLM
- `agent` - Run autonomous web agent
- `cache` - Manage the local scrape cache

## Command Reference

### scrape

Scrape a single URL and output content.

**Usage:**
```bash
supacrawl scrape URL [OPTIONS]
```

**Arguments:**
- `URL` - The URL to scrape

**Options:**
- `-f, --format FORMAT` - Output formats: `markdown`, `html`, `rawHtml`, `links`, `images`, `screenshot`, `pdf`, `json`, `branding`, `summary` (default: `markdown`, can specify multiple)
- `--schema PATH` - Path to JSON schema file (for json format)
- `-p, --prompt TEXT` - Extraction prompt (for json format)
- `--only-main-content/--no-only-main-content` - Extract main content area only (default: true)
- `--wait-for INT` - Additional wait time in milliseconds after page load (default: 0)
- `--timeout INT` - Page load timeout in milliseconds (default: 30000)
- `-o, --output PATH` - Output file path (default: stdout). Use `.md`, `.json`, `.html`, `.png`, or `.pdf`
- `--full-page/--no-full-page` - Capture full scrollable page for screenshots (default: true)
- `-a, --actions PATH` - Path to JSON file containing page actions
- `--include-tags TEXT` - CSS selectors for elements to include (can be repeated)
- `--exclude-tags TEXT` - CSS selectors for elements to exclude (can be repeated)
- `--country CODE` - ISO country code for locale settings (e.g., AU, US, DE)
- `--language CODE` - Browser language/locale code (e.g., en-AU, de-DE)
- `--timezone TZ` - IANA timezone (e.g., Australia/Sydney)
- `--max-age INT` - Cache freshness in seconds (0=no cache, default: 0)
- `--cache-dir PATH` - Cache directory (default: `~/.supacrawl/cache`)
- `--stealth/--no-stealth` - Enhanced stealth mode via Patchright (requires: `pip install supacrawl[stealth]`)
- `--proxy URL` - Proxy URL (e.g., `http://user:pass@host:port`, `socks5://host:port`)
- `--solve-captcha/--no-solve-captcha` - Enable CAPTCHA solving via 2Captcha (requires: `pip install supacrawl[captcha]` and `CAPTCHA_API_KEY`)
- `--wait-until STRATEGY` - Page load strategy: `commit`, `domcontentloaded`, `load`, `networkidle` (default: load)

**Example:**
```bash
$ supacrawl scrape https://example.com --format markdown
# Outputs markdown content to stdout

$ supacrawl scrape https://example.com --output result.json
# Writes JSON result to file

$ supacrawl scrape https://example.com --format markdown --format html --output page.md
# Scrapes both formats, writes markdown to file

$ supacrawl scrape https://example.com --format screenshot --output page.png
# Capture full page screenshot

$ supacrawl scrape https://example.com --format pdf --output page.pdf
# Generate PDF of page

$ supacrawl scrape https://example.com --format images --output images.json
# Extract all image URLs

$ supacrawl scrape https://example.com --format branding --output branding.json
# Extract brand identity (colours, fonts, logo)

$ supacrawl scrape https://example.com --format summary
# Generate LLM summary of page content

$ supacrawl scrape https://example.com --format json --prompt "Extract product name and price"
# LLM-based structured extraction

$ supacrawl scrape https://example.com --no-only-main-content --wait-for 2000
# Scrapes full page, waits 2 seconds after load

$ supacrawl scrape https://protected-site.com --stealth
# Use enhanced stealth mode for bot-protected sites

$ supacrawl scrape https://captcha-site.com --stealth --solve-captcha
# Solve CAPTCHAs automatically (costs ~$0.002-0.003 each)
```

### crawl

Crawl a website starting from a URL.

**Usage:**
```bash
supacrawl crawl URL [OPTIONS]
```

**Arguments:**
- `URL` - The starting URL for the crawl

**Options:**
- `--limit INT` - Maximum pages to crawl (default: 100)
- `--depth INT` - Maximum crawl depth (default: 3)
- `--include TEXT` - URL patterns to include (glob patterns, can specify multiple)
- `--exclude TEXT` - URL patterns to exclude (glob patterns, can specify multiple)
- `-o, --output DIRECTORY` - Output directory for scraped content (required)
- `--resume` - Resume from previous crawl
- `-f, --format FORMAT` - Output format: `markdown`, `html`, or `json` (default: `markdown`, can specify multiple)
- `--deduplicate-similar-urls` - Deduplicate URLs that differ only by tracking parameters or fragments
- `--allow-external-links` - Follow and scrape links to external domains
- `--country CODE` - ISO country code for locale settings (e.g., AU, US, DE)
- `--language CODE` - Browser language/locale code (e.g., en-AU, de-DE)
- `--timezone TZ` - IANA timezone (e.g., Australia/Sydney)
- `--stealth/--no-stealth` - Enhanced stealth mode via Patchright
- `--proxy URL` - Proxy URL (e.g., `http://user:pass@host:port`)
- `-c, --concurrency INT` - Max concurrent requests (default: 10)
- `--wait-until STRATEGY` - Page load strategy: `commit`, `domcontentloaded`, `load`, `networkidle`

**Example:**
```bash
$ supacrawl crawl https://docs.example.com -o ./docs --limit 50
# Crawl up to 50 pages to ./docs directory

$ supacrawl crawl https://example.com -o ./output --depth 2
# Crawl with limited depth

$ supacrawl crawl https://example.com -o ./output --include "/docs/*" --exclude "/api/*"
# Crawl with URL pattern filtering

$ supacrawl crawl https://example.com -o ./output --deduplicate-similar-urls
# Remove duplicate URLs with different query params

$ supacrawl crawl https://example.com -o ./output --country AU
# Set browser locale to Australia
```

### map

Map URLs from a website without scraping content.

**Usage:**
```bash
supacrawl map URL [OPTIONS]
```

**Arguments:**
- `URL` - The starting URL to map

**Options:**
- `--limit INT` - Maximum number of URLs to discover (default: 200)
- `--depth INT` - Maximum BFS crawl depth (default: 3)
- `--sitemap CHOICE` - Sitemap handling: `include` (default), `skip`, or `only`
- `--include-subdomains` - Include subdomain URLs (flag)
- `--search TEXT` - Filter URLs containing this text
- `-o, --output PATH` - Output file path (default: stdout)
- `--format FORMAT` - Output format: `json` (full result) or `text` (URLs only) (default: `text`)
- `--ignore-query-params` - Remove query parameters from URLs
- `--stealth/--no-stealth` - Enhanced stealth mode via Patchright
- `--proxy URL` - Proxy URL
- `-c, --concurrency INT` - Max concurrent requests (default: 5)
- `--wait-until STRATEGY` - Page load strategy

**Example:**
```bash
$ supacrawl map https://example.com --limit 100 --format json
# Output full JSON result with link metadata

$ supacrawl map https://example.com --search about --output urls.txt
# Find all URLs containing "about", output as text list

$ supacrawl map https://example.com --sitemap only --format json --output sitemap.json
# Extract only sitemap URLs in JSON format

$ supacrawl map https://docs.example.com --depth 5 --include-subdomains
# Deep crawl including subdomains

$ supacrawl map https://example.com --ignore-query-params
# Deduplicate URLs that differ only by query params
```

### search

Search the web using DuckDuckGo or Brave.

**Usage:**
```bash
supacrawl search QUERY [OPTIONS]
```

**Arguments:**
- `QUERY` - Search query string

**Options:**
- `-l, --limit INT` - Maximum results per source type (1-10, default: 5)
- `-s, --source TYPE` - Source types: `web`, `images`, `news`, or `all` (default: `web`, can specify multiple)
- `--scrape/--no-scrape` - Scrape content from result pages (default: no-scrape)
- `--provider PROVIDER` - Search provider: `duckduckgo` or `brave` (default: `duckduckgo`)
- `-o, --output PATH` - Output file (JSON). If omitted, prints to stdout

**Example:**
```bash
$ supacrawl search "python web scraping" --limit 5 --source web
# Search web for Python scraping content

$ supacrawl search "AI news 2025" --source news --scrape --output results.json
# Search news and scrape content from result pages

$ supacrawl search "machine learning tutorials" --provider brave --limit 10
# Use Brave search provider (requires BRAVE_API_KEY)

$ supacrawl search "tech updates" --source all
# Search web, images, and news simultaneously
```

### llm-extract

Extract structured data from URLs using an LLM.

**Usage:**
```bash
supacrawl llm-extract URLS... [OPTIONS]
```

**Arguments:**
- `URLS` - One or more URLs to extract data from

**Options:**
- `-p, --prompt TEXT` - Extraction prompt describing what to extract (required)
- `-s, --schema FILE` - Path to JSON schema file for structured output
- `-o, --output PATH` - Output file (JSON). If omitted, prints to stdout

**Environment Variables (required):**
- `SUPACRAWL_LLM_PROVIDER` - LLM provider: `ollama`, `openai`, or `anthropic`
- `SUPACRAWL_LLM_MODEL` - Model name (e.g., `qwen3:8b`, `gpt-4o-mini`)
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` - API key for cloud providers

**Example:**
```bash
$ supacrawl llm-extract https://example.com/products --prompt "Extract product names and prices"
# Extract product data from a page

$ supacrawl llm-extract https://example.com/about --prompt "Extract company info" --schema schema.json
# Extract structured data according to a schema

$ supacrawl llm-extract https://a.com https://b.com --prompt "Extract titles" -o results.json
# Extract from multiple URLs
```

### agent

Run an autonomous web agent that searches, navigates, and extracts data.

**Usage:**
```bash
supacrawl agent PROMPT [OPTIONS]
```

**Arguments:**
- `PROMPT` - Natural language description of data to find

**Options:**
- `-u, --url URL` - Starting URLs (can specify multiple). If omitted, agent searches first
- `-s, --schema FILE` - Path to JSON schema for structured output
- `--max-steps INT` - Maximum pages to visit (default: 10)
- `-o, --output PATH` - Output file (JSON). If omitted, prints to stdout
- `-q, --quiet` - Suppress progress output, only show final result

**Environment Variables (required):**
- `SUPACRAWL_LLM_PROVIDER` - LLM provider: `ollama`, `openai`, or `anthropic`
- `SUPACRAWL_LLM_MODEL` - Model name
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` - API key for cloud providers

**Example:**
```bash
$ supacrawl agent "Find the pricing plans for Anthropic Claude API"
# Agent will search and navigate to find pricing info

$ supacrawl agent "Extract all team member names and roles" --url https://example.com/about
# Start from a specific URL

$ supacrawl agent "Find Python tutorial websites" --max-steps 5 --quiet
# Limit steps and suppress progress output
```

### cache

Manage the local scrape cache.

**Usage:**
```bash
supacrawl cache COMMAND [OPTIONS]
```

**Subcommands:**
- `stats` - Show cache statistics (entry count, size, directory)
- `clear` - Clear cached entries (all or by URL)
- `prune` - Remove expired cache entries

**Options (all subcommands):**
- `--cache-dir PATH` - Cache directory (default: `~/.supacrawl/cache`)

**Options (clear only):**
- `--url URL` - Clear cache for specific URL only
- `-y, --yes` - Skip confirmation prompt

**Example:**
```bash
$ supacrawl cache stats
# Show cache statistics

$ supacrawl cache clear
# Clear all cached entries (prompts for confirmation)

$ supacrawl cache clear --url https://example.com
# Clear cache for a specific URL

$ supacrawl cache clear -y
# Clear all without confirmation

$ supacrawl cache prune
# Remove expired entries
```

## Common Patterns

### Scraping Documentation Sites

Documentation sites often have structured URLs and sitemaps. Use `map` to discover pages, then `crawl` with filters.

```bash
# Map the site to see available URLs
supacrawl map https://docs.example.com --limit 100

# Filter to specific sections
supacrawl map https://docs.example.com --search "/api/" --limit 50

# Crawl only API documentation
supacrawl crawl https://docs.example.com -o ./api-docs \
  --include "/api/*" \
  --limit 100

# Exclude changelog and release notes
supacrawl crawl https://docs.example.com -o ./docs \
  --exclude "/changelog/*" \
  --exclude "/releases/*" \
  --limit 200
```

### Handling JS-Heavy SPAs

Single-page applications load content dynamically. Use wait strategies to ensure content is rendered.

```bash
# Wait until all network requests complete
supacrawl scrape https://spa.example.com --wait-until networkidle

# Add extra wait time for slow JavaScript
supacrawl scrape https://spa.example.com --wait-until networkidle --wait-for 3000
```

For interactive content, use actions:

```bash
cat > actions.json << 'EOF'
[
  {"type": "wait", "milliseconds": 2000},
  {"type": "scroll", "direction": "down"},
  {"type": "click", "selector": "button.load-more"},
  {"type": "wait", "milliseconds": 2000}
]
EOF

supacrawl scrape https://spa.example.com --actions actions.json
```

### Bot-Protected Sites

When sites block automated access, use stealth mode and CAPTCHA solving.

```bash
# Install stealth extras
pip install supacrawl[stealth]

# Scrape with stealth mode
supacrawl scrape https://protected.example.com --stealth

# Debug with visible browser
SUPACRAWL_HEADLESS=false supacrawl scrape https://protected.example.com --stealth

# Capture screenshot to see what browser sees
supacrawl scrape https://protected.example.com -f screenshot -o debug.png
```

For CAPTCHA-protected sites:

```bash
pip install supacrawl[captcha]
export CAPTCHA_API_KEY=your-2captcha-api-key
supacrawl scrape https://captcha-site.example.com --stealth --solve-captcha
```

### Extracting Structured Data

Use LLM extraction to get structured data from pages.

```bash
# Extract with a prompt
supacrawl scrape https://shop.example.com/product \
  -f json \
  --prompt "Extract product name, price, and availability"

# Extract from multiple pages
supacrawl llm-extract \
  https://shop.example.com/product/1 \
  https://shop.example.com/product/2 \
  --prompt "Extract product name and price" \
  -o products.json

# Autonomous agent for complex tasks
supacrawl agent "Find the pricing plans for Acme Corp" -o pricing.json
```

### Caching

Use caching to avoid re-fetching unchanged pages.

```bash
# Cache for 1 hour
supacrawl scrape https://example.com --max-age 3600

# Check cache status
supacrawl cache stats

# Clear expired entries
supacrawl cache prune
```

### Locale and Timezone

Set browser locale for region-specific content:

```bash
supacrawl scrape https://example.com --country AU
supacrawl scrape https://example.com --language en-AU --timezone Australia/Sydney
```

## Environment Variables

### LLM Configuration

- `SUPACRAWL_LLM_PROVIDER` - LLM provider: `ollama`, `openai`, or `anthropic`
- `SUPACRAWL_LLM_MODEL` - Model name (e.g., `qwen3:8b`, `gpt-4o-mini`, `claude-sonnet-4-20250514`)
- `OLLAMA_HOST` - Ollama server URL (default: `http://localhost:11434`)
- `OPENAI_API_KEY` - API key for OpenAI
- `ANTHROPIC_API_KEY` - API key for Anthropic

### Search Configuration

- `BRAVE_API_KEY` - Brave Search API key (for `--provider brave`)

### Browser Configuration

- `SUPACRAWL_HEADLESS` - Run headless (default: `true`)
- `SUPACRAWL_TIMEOUT` - Page load timeout in ms (default: `30000`)
- `SUPACRAWL_WAIT_UNTIL` - Default page load strategy (`commit`, `domcontentloaded`, `load`, `networkidle`)
- `SUPACRAWL_PROXY` - Proxy URL (http/socks5)
- `SUPACRAWL_CACHE_DIR` - Cache directory (default: `~/.supacrawl/cache`)

### CAPTCHA Configuration

- `CAPTCHA_API_KEY` - 2Captcha API key for automatic CAPTCHA solving

See `.env.example` for additional browser configuration options.

## Error Handling

### Common Errors

**URL Not Reachable:**
```
Error: Failed to fetch URL: https://example.com [correlation_id=abc12345]
```

**Solution:** Check the URL is correct and accessible. The site may be blocking automated requests. Try `--stealth` mode.

**LLM Provider Error:**
```
Error: LLM extraction failed: Connection refused [correlation_id=abc12345]
```

**Solution:** Ensure Ollama is running (`ollama serve`) or check API keys for cloud providers. Verify `SUPACRAWL_LLM_PROVIDER` and `SUPACRAWL_LLM_MODEL` are set.

**Timeout Error:**
```
Error: Page load timeout exceeded [correlation_id=abc12345]
```

**Solution:** Increase timeout with `--timeout` option or use `--wait-until networkidle` for JS-heavy sites.

### Debugging with Correlation IDs

All errors include correlation IDs for debugging:

1. Note correlation ID from error message
2. Check logs for entries with same correlation ID
3. Review error context in logs

## Troubleshooting

- Run `playwright install chromium` to verify Playwright browsers are installed
- For 4xx client errors, fix cookies/auth/proxy; retries are skipped by design
- For rate limits, use `--wait-for` to add delays between requests or reduce crawl `--limit`
- Use `--stealth` for bot-protected sites (requires `pip install supacrawl[stealth]`)
- Use `--solve-captcha` for CAPTCHA-protected sites (requires `pip install supacrawl[captcha]` and `CAPTCHA_API_KEY`)
- Set `SUPACRAWL_HEADLESS=false` to see what the browser sees during debugging

## Best Practices

1. **Start with map**: Use `map` to discover URLs before crawling large sites
2. **Start small**: Use `--limit` and `--depth` to control crawl scope
3. **Use caching**: The cache reduces redundant requests; use `cache stats` to monitor
4. **Test with limits**: Start with low `--limit` values when exploring new sites
5. **Choose the right provider**: Use Ollama for local/private data, cloud providers for better quality

# CLI Usage Guide

This guide covers using the supacrawl command-line interface.

## Command Overview

The `supacrawl` CLI provides Firecrawl-compatible commands for web scraping, URL mapping, search, and LLM-based data extraction.

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
- `--format FORMAT` - Output format: `markdown`, `html`, `rawHtml`, or `links` (default: `markdown`, can specify multiple)
- `--only-main-content/--no-only-main-content` - Extract main content area only (default: true)
- `--wait-for INT` - Additional wait time in milliseconds after page load (default: 0)
- `--timeout INT` - Page load timeout in milliseconds (default: 30000)
- `--output PATH` - Output file path (default: stdout). Use `.md` for markdown, `.json` for full result, `.html` for HTML

**Example:**
```bash
$ supacrawl scrape https://example.com --format markdown
# Outputs markdown content to stdout

$ supacrawl scrape https://example.com --output result.json
# Writes JSON result to file

$ supacrawl scrape https://example.com --format markdown --format html --output page.md
# Scrapes both formats, writes markdown to file

$ supacrawl scrape https://example.com --no-only-main-content --wait-for 2000
# Scrapes full page, waits 2 seconds after load
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
- `--output PATH` - Output directory or file
- `--format FORMAT` - Output format: `json` or `jsonl` (default: `jsonl`)
- `--depth INT` - Maximum crawl depth (default: 3)
- `--concurrency INT` - Maximum concurrent requests (default: 5)
- `--delay FLOAT` - Delay between requests in seconds (default: 0.5)

**Example:**
```bash
$ supacrawl crawl https://docs.example.com --limit 50
# Crawl up to 50 pages

$ supacrawl crawl https://example.com --output results.jsonl --depth 2
# Crawl with limited depth, output to file

$ supacrawl crawl https://example.com --concurrency 3 --delay 1.0
# Slower, more polite crawl
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
- `--output PATH` - Output file path (default: stdout)
- `--format FORMAT` - Output format: `json` (full result) or `text` (URLs only) (default: `text`)

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
- `-s, --source TYPE` - Source types: `web`, `images`, `news`, or `all` (default: `web`)
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
# Use Brave search provider
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
- `--provider PROVIDER` - LLM provider: `ollama`, `openai`, or `anthropic` (default: `ollama`)
- `--model TEXT` - Model name (defaults to provider's default)
- `-o, --output PATH` - Output file (JSON). If omitted, prints to stdout

**Example:**
```bash
$ supacrawl llm-extract https://example.com/products --prompt "Extract product names and prices"
# Extract product data from a page

$ supacrawl llm-extract https://example.com/about --prompt "Extract company info" --schema schema.json
# Extract structured data according to a schema

$ supacrawl llm-extract https://example.com --prompt "Get main topics" --provider openai --model gpt-4
# Use OpenAI instead of Ollama
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
- `--provider PROVIDER` - LLM provider: `ollama`, `openai`, or `anthropic` (default: `ollama`)
- `--model TEXT` - Model name (defaults to provider's default)
- `-o, --output PATH` - Output file (JSON). If omitted, prints to stdout
- `-q, --quiet` - Suppress progress output, only show final result

**Example:**
```bash
$ supacrawl agent "Find the pricing for Firecrawl API"
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

**Example:**
```bash
$ supacrawl cache stats
# Show cache statistics

$ supacrawl cache clear
# Clear all cached entries

$ supacrawl cache clear --url https://example.com
# Clear cache for a specific URL

$ supacrawl cache prune
# Remove expired entries
```

## Common Workflows

### Quick Scrape

Scrape a single page to markdown:

```bash
supacrawl scrape https://example.com/article
```

### Discover and Crawl

1. **Map the site first:**
   ```bash
   supacrawl map https://docs.example.com --format text --output urls.txt
   ```

2. **Review discovered URLs:**
   ```bash
   cat urls.txt | head -20
   ```

3. **Crawl the site:**
   ```bash
   supacrawl crawl https://docs.example.com --limit 50 --output docs.jsonl
   ```

### Search and Extract

1. **Search for relevant pages:**
   ```bash
   supacrawl search "company pricing page" --limit 5
   ```

2. **Extract structured data:**
   ```bash
   supacrawl llm-extract https://example.com/pricing --prompt "Extract pricing tiers and features"
   ```

### Autonomous Research

Let the agent find and extract information:

```bash
supacrawl agent "Find the top 5 Python web frameworks and their GitHub stars" --output frameworks.json
```

## Environment Variables

### LLM Configuration

- `OLLAMA_HOST` - Ollama server URL (default: `http://localhost:11434`)
- `OPENAI_API_KEY` - OpenAI API key (for `--provider openai`)
- `ANTHROPIC_API_KEY` - Anthropic API key (for `--provider anthropic`)

### Search Configuration

- `BRAVE_API_KEY` - Brave Search API key (for `--provider brave`)

### Browser Configuration

See `.env.example` for available Playwright browser configuration options.

## Error Handling

### Common Errors

**URL Not Reachable:**
```
Error: Failed to fetch URL: https://example.com [correlation_id=abc12345]
```

**Solution:** Check the URL is correct and accessible. The site may be blocking automated requests.

**LLM Provider Error:**
```
Error: LLM extraction failed: Connection refused [correlation_id=abc12345]
```

**Solution:** Ensure Ollama is running (`ollama serve`) or check API keys for cloud providers.

**Timeout Error:**
```
Error: Page load timeout exceeded [correlation_id=abc12345]
```

**Solution:** Increase timeout with `--timeout` option or check if the page is slow to load.

### Debugging with Correlation IDs

All errors include correlation IDs for debugging:

1. Note correlation ID from error message
2. Check logs for entries with same correlation ID
3. Review error context in logs

## Best Practices

1. **Start with map**: Use `map` to discover URLs before crawling large sites
2. **Respect rate limits**: Use `--delay` and `--concurrency` for polite crawling
3. **Use caching**: The cache reduces redundant requests; use `cache stats` to monitor
4. **Test with limits**: Start with low `--limit` values when exploring new sites
5. **Choose the right provider**: Use Ollama for local/private data, cloud providers for better quality

## References

- `.cursor/rules/20-cli-patterns-supacrawl.mdc` - CLI pattern requirements
- `.cursor/rules/70-error-handling-supacrawl.mdc` - Error handling patterns

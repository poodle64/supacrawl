<div align="center">

[![Python](https://img.shields.io/badge/Python-3.14+-3776ab?logo=python&logoColor=white)](https://python.org) [![Playwright](https://img.shields.io/badge/Playwright-2ea44f?logo=playwright&logoColor=white)](https://playwright.dev) [![MCP](https://img.shields.io/badge/MCP-Compatible-8A2BE2)](https://modelcontextprotocol.io) [![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

<h1>Supacrawl</h1>

<em>Zero-infrastructure web scraping for the terminal and AI assistants.</em>

</div>

## Why Supacrawl?

There are excellent web scraping tools available. Supacrawl takes a different approach: a CLI tool designed for individual developers who want to scrape from the terminal.

- **Zero infrastructure**: `pip install` and go, no Docker/databases/Redis
- **Terminal-first**: Designed for shell workflows and pipelines
- **MCP server**: Give AI assistants direct access to web scraping
- **Fast by default**: HTTP-first fetch skips the browser for static pages, escalating only when JavaScript or a bot challenge needs it
- **Clean markdown**: Renders JS when needed, outputs readable markdown with a precision/recall extraction dial
- **Structured data, no LLM**: Pull schema.org JSON-LD, microdata, and OpenGraph as JSON, deterministically
- **LLM-ready**: Built-in extraction with Ollama, OpenAI, or Anthropic
- **Anti-bot protection**: Three-tier engine system (Playwright, Patchright, Camoufox) with automatic HTTP/2 fallback
- **Web search**: Multi-provider search with fallback and recency/topic/domain filters
- **PDF parsing**: Auto-detect PDF URLs, extract text with optional OCR
- **Mobile emulation**: Scrape as any mobile device using Playwright device descriptors

```bash
pip install supacrawl
playwright install chromium
```

## Quick Start

```bash
# Scrape a page to markdown
supacrawl scrape https://example.com

# Crawl a website
supacrawl crawl https://docs.python.org/3/ -o ./python-docs --limit 50

# Discover URLs without fetching
supacrawl map https://example.com

# Web search
supacrawl search "python web scraping 2024"

# LLM extraction (requires LLM config)
supacrawl llm-extract https://example.com/pricing -p "Extract pricing tiers"

# Autonomous agent for complex tasks
supacrawl agent "Find the pricing for all plans on example.com"
```

**Get maximum value on first run:**

- Set `BRAVE_API_KEY` to enable web search (free tier at [brave.com/search/api](https://brave.com/search/api/))
- Quality signal, auto-escalation, and per-domain memory all work with zero extra config
- Install `supacrawl[stealth]` and `supacrawl[camoufox]` to let the escalation ladder reach the hardest bot-protected sites

See [Configuration](#configuration) for `.env.example` setup.

## MCP Server

Supacrawl includes an embedded [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server, giving AI assistants like Claude, Cursor, and VS Code Copilot direct access to web scraping.

### Install

```bash
pip install supacrawl[mcp]
playwright install chromium
```

### Add to your MCP client

**Claude Desktop**: edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "supacrawl": {
      "command": "supacrawl-mcp",
      "args": ["--transport", "stdio"]
    }
  }
}
```

**Claude Code**: add to `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "supacrawl": {
      "command": "supacrawl-mcp",
      "args": ["--transport", "stdio"]
    }
  }
}
```

**Cursor / VS Code**: add to your editor's MCP settings with the same config.

### Available Tools

| Tool                 | Description                                         |
| -------------------- | --------------------------------------------------- |
| `supacrawl_scrape`   | Scrape a URL to markdown, HTML, screenshot, or PDF  |
| `supacrawl_crawl`    | Crawl multiple pages from a site                    |
| `supacrawl_map`      | Discover URLs on a website without fetching content |
| `supacrawl_search`   | Web search with multi-provider fallback             |
| `supacrawl_extract`  | Scrape pages for LLM-powered structured extraction  |
| `supacrawl_summary`  | Scrape a page for LLM-powered summarisation         |
| `supacrawl_diagnose` | Diagnose scraping issues (CDN, bot detection, etc.) |
| `supacrawl_health`   | Server health check and capability report           |

The CLI's `agent` command is intentionally omitted. When used via MCP, your LLM orchestrates the primitives directly; it _is_ the agent. For standalone agentic workflows, use `supacrawl agent` from the CLI.

The server also exposes MCP **resources** (format references, search providers, capabilities) and **prompts** (workflow guides for scraping, extraction, research, and error handling).

### Environment Variables

Pass environment variables via your MCP client config to customise behaviour:

```json
{
  "mcpServers": {
    "supacrawl": {
      "command": "supacrawl-mcp",
      "args": ["--transport", "stdio"],
      "env": {
        "BRAVE_API_KEY": "your-key-here",
        "SUPACRAWL_ENGINE": "camoufox",
        "SUPACRAWL_STEALTH": "true",
        "SUPACRAWL_LOCALE": "en-AU",
        "SUPACRAWL_TIMEZONE": "Australia/Sydney",
        "TAVILY_API_KEY": "your-key-here",
        "SUPACRAWL_SEARCH_PROVIDERS": "brave,tavily"
      }
    }
  }
}
```

> **`BRAVE_API_KEY` is required for search to work.** Without it, supacrawl falls back to DuckDuckGo, which is aggressively bot-walled; a keyless search that returns nothing fails loudly with an actionable error instead of returning an empty list. Get a free key (1,000 searches/month) at [brave.com/search/api](https://brave.com/search/api/).

All [configuration](#configuration) environment variables apply. The MCP server also supports `SUPACRAWL_LOG_LEVEL` (default: `INFO`). Search providers fall back automatically when one hits a rate limit or quota.

### Quality Signal

Every scrape result includes a `quality` field with a `verdict` (`ok`, `thin`, `js_shell`, `paywall`, `bot_challenge`, `captcha`, `error_status`, `garbled_pdf`, `empty`), a 0-100 score, and a `suggestion` when the result is not clean. `success` is honest: bot blocks, CAPTCHAs, HTTP errors, and empty pages are reported `success=False`. Read `quality.verdict` before consuming the result.

### Adaptive Anti-bot

Supacrawl auto-escalates through stealth engines (Patchright, then Camoufox, then Camoufox+HTTP/1.1) on a poor quality verdict — no per-request engine or stealth flags needed. Hard sites just work on defaults within a bounded number of attempts. Install the extras to unlock the full ladder:

```bash
pip install supacrawl[mcp,stealth]    # Tier 2: Patchright
pip install supacrawl[mcp,camoufox]   # Tier 3: Camoufox (Akamai/Cloudflare)
```

### Per-Domain Memory

Supacrawl remembers the strategy (engine, wait time, stealth) that produced a clean result for each domain and seeds subsequent requests with it — on by default, no configuration needed. Inspect or reset it with:

```bash
supacrawl strategy list                # every learned domain
supacrawl strategy show example.com    # one domain's strategy
supacrawl strategy forget example.com  # reset one domain
supacrawl strategy clear               # reset all
```

Disable with `SUPACRAWL_STRATEGY_MEMORY=0`.

### Troubleshooting

If scrapes return empty or minimal content, use `supacrawl_diagnose` to identify the cause (CDN protection, JS framework, bot detection). Common fixes: set `wait_for=3000` for JS-heavy sites (enables SPA stability polling), use `wait_until="load"` or `"networkidle"` if resources must fully load, enable `SUPACRAWL_STEALTH=true` for bot-protected sites, or try `only_main_content=false` if the wrong content is extracted.

### Optional Extras

```bash
pip install supacrawl[mcp,stealth]    # Patchright anti-bot evasion (Tier 2)
pip install supacrawl[mcp,camoufox]   # Camoufox for Akamai/Cloudflare (Tier 3)
pip install supacrawl[mcp,captcha]    # 2Captcha CAPTCHA solving
```

## Agent Skill

Agents that drive the CLI (rather than MCP) can self-onboard from a single concise [`SKILL.md`](src/supacrawl/resources/SKILL.md) — command selection, flags, and failure recovery — plus a root [`llms.txt`](llms.txt). Register the skill in one command:

```bash
supacrawl install-skill            # into ./.claude/skills/supacrawl/
supacrawl install-skill --user     # into ~/.claude/skills/supacrawl/
supacrawl install-skill --dir PATH # for Cursor, Codex, or any other runtime
```

## REST API

Supacrawl includes an optional REST API server compatible with the [Firecrawl v2](https://docs.firecrawl.dev) protocol. Any tool that already integrates with Firecrawl (n8n, LangChain, LlamaIndex) can use Supacrawl as a self-hosted drop-in backend.

```bash
pip install supacrawl[api]
supacrawl serve
```

The server starts on port 8308 by default. Test it:

```bash
curl -X POST http://localhost:8308/scrape \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

### Endpoints

| Endpoint              | Method | Description                               |
| --------------------- | ------ | ----------------------------------------- |
| `/scrape`             | POST   | Scrape a single URL (synchronous)         |
| `/crawl`              | POST   | Start a crawl job (async, returns job ID) |
| `/crawl/{id}`         | GET    | Poll crawl job status and results         |
| `/map`                | POST   | Discover URLs on a site (synchronous)     |
| `/search`             | POST   | Web search (synchronous)                  |
| `/extract`            | POST   | LLM extraction (async, returns job ID)    |
| `/batch/scrape`       | POST   | Batch scrape multiple URLs (async)        |
| `/supacrawl/health`   | GET    | Server health and version                 |
| `/supacrawl/diagnose` | POST   | Pre-scrape diagnostics                    |
| `/supacrawl/summary`  | POST   | Summarise a page                          |

Authentication is optional. Set `SUPACRAWL_API_KEY` to require a Bearer token; leave it unset for open access.

See [docs/api-reference.md](docs/api-reference.md) for full endpoint documentation, request/response examples, and n8n integration guide.

## Commands

| Command             | Description                                            |
| ------------------- | ------------------------------------------------------ |
| `scrape <url>`      | Scrape single page to markdown                         |
| `crawl <url>`       | Crawl website, save to directory                       |
| `map <url>`         | Discover URLs from sitemap/links                       |
| `search <query>`    | Web search with multi-provider fallback                |
| `llm-extract <url>` | Extract structured data with LLM                       |
| `agent <prompt>`    | Autonomous agent for complex tasks                     |
| `serve`             | Start the REST API server                              |
| `cache`             | Cache management (clear, stats, prune)                 |
| `strategy`          | Per-domain strategy memory (list, show, forget, clear) |

Run `supacrawl <command> --help` for options.

## Output

Crawl produces a flat directory of markdown files:

```text
output/
├── manifest.json          # URLs crawled (for resume)
├── index.md
├── about.md
└── docs_getting-started.md
```

Each markdown file includes YAML frontmatter with source URL and metadata.

## Configuration

### Core Settings

| Variable             | Default      | Description                                            |
| -------------------- | ------------ | ------------------------------------------------------ |
| `SUPACRAWL_HEADLESS` | `true`       | Set `false` to see browser                             |
| `SUPACRAWL_TIMEOUT`  | `30000`      | Page load timeout (ms)                                 |
| `SUPACRAWL_ENGINE`   | `playwright` | Browser engine: `playwright`, `patchright`, `camoufox` |
| `SUPACRAWL_PROXY`    | -            | Proxy URL (http/socks5)                                |

### LLM Features

Required for `llm-extract`, `agent`, and `--summarize`:

| Variable                 | Description                             |
| ------------------------ | --------------------------------------- |
| `SUPACRAWL_LLM_PROVIDER` | `ollama`, `openai`, or `anthropic`      |
| `SUPACRAWL_LLM_MODEL`    | Model name (e.g., `qwen3:8b`)           |
| `OPENAI_API_KEY`         | For OpenAI provider                     |
| `ANTHROPIC_API_KEY`      | For Anthropic provider                  |
| `OLLAMA_HOST`            | Ollama URL (default: `localhost:11434`) |

### Search

**Search requires a provider API key.** Brave is recommended (free tier: ~1,000 searches/month). Without any key, supacrawl falls back to DuckDuckGo, which is aggressively bot-walled; a keyless search that returns nothing fails loudly with an actionable error. Copy `.env.example` to `.env` and set `BRAVE_API_KEY`.

```bash
# Get a free key at https://brave.com/search/api/
BRAVE_API_KEY=BSA...
```

If the primary provider hits a rate limit or quota, the next provider in the chain is tried automatically.

| Variable | Default | Description |
| --- | --- | --- |
| `BRAVE_API_KEY` | - | **Required for reliable search.** Free tier: ~1,000 searches/month. Get one at [brave.com/search/api](https://brave.com/search/api/) |
| `TAVILY_API_KEY` | - | [Tavily](https://tavily.com/) API key. Supports web and news search |
| `SERPER_API_KEY` | - | [Serper.dev](https://serper.dev/) API key. Google Search results |
| `SERPAPI_API_KEY` | - | [SerpAPI](https://serpapi.com/) API key. Google Search results |
| `EXA_API_KEY` | - | [Exa.ai](https://exa.ai/) API key. Neural search for web and news |
| `SUPACRAWL_SEARCH_PROVIDERS` | `brave` | Comma-separated provider chain with fallback order (e.g., `brave,tavily,serper`) |
| `SUPACRAWL_SEARCH_RATE_LIMIT` | - | Override default rate limit (requests/second). Provider defaults: Brave 1/s, DuckDuckGo 0.5/s |

Providers are tried in order; providers without keys are skipped. DuckDuckGo is a last-resort fallback only — it has no official API and is aggressively bot-walled.

### Caching

Supacrawl caches scraped content locally for faster repeated requests. Enable with `--max-age`:

```bash
# Cache for 1 hour
supacrawl scrape https://example.com --max-age 3600
```

| Variable              | Default              | Description     |
| --------------------- | -------------------- | --------------- |
| `SUPACRAWL_CACHE_DIR` | `~/.supacrawl/cache` | Cache directory |

**Cache Management:**

```bash
supacrawl cache stats   # View cache size and entry count
supacrawl cache prune   # Remove expired entries
supacrawl cache clear   # Clear all cache (with confirmation)
```

**Cache Behaviour:**

- No automatic eviction; run `cache prune` periodically to clean expired entries
- No size limits; cache grows unbounded, use `cache clear` if disk space is a concern
- Files stored as `<hash>.json` where hash is SHA256 of normalised URL

### Optional Extras

```bash
pip install supacrawl[stealth]    # Patchright for anti-bot evasion (Tier 2)
pip install supacrawl[camoufox]   # Camoufox for Akamai/Cloudflare bypass (Tier 3)
pip install supacrawl[captcha]    # 2Captcha for CAPTCHA solving
pip install supacrawl[pdf-ocr]    # OCR support for scanned PDFs
```

Select the browser engine with `--engine` (playwright, patchright, camoufox) or set `SUPACRAWL_ENGINE` as a default. Use `--stealth` for Tier 2, `--engine camoufox` for Tier 3, and `--solve-captcha` for CAPTCHA-protected sites. CAPTCHA solving requires `CAPTCHA_API_KEY` environment variable.

Copy `.env.example` to `.env` to configure.

### System-Managed Playwright Browsers

Distributions like NixOS and Guix provide pre-built Playwright browser binaries. To use them, pin the Python package to match your system's browser version and set `PLAYWRIGHT_BROWSERS_PATH`:

```bash
pip install 'supacrawl' 'playwright==1.52.0'  # match your distro's version
export PLAYWRIGHT_BROWSERS_PATH=/nix/store/...-playwright-driver-browsers
```

Skip `playwright install`; your system already provides the binaries.

## Development

```bash
# From source (direnv runs `uv sync --all-extras` automatically on cd)
uv sync --all-extras
playwright install chromium

# Quality checks
ruff check src/ && mypy src/
pytest -q -m "not e2e"
```

## Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Where Supacrawl Fits                                │
├─────────────────┬─────────────────┬─────────────────┬───────────────────────┤
│   Collection    │   Processing    │    Storage      │        Query          │
├─────────────────┼─────────────────┼─────────────────┼───────────────────────┤
│                 │                 │                 │                       │
│   supacrawl ────┼──► ragify ──────┼──► Qdrant ──────┼──► Claude Code        │
│                 │    LangChain    │    Chroma       │    Custom Agents      │
│   • scrape      │    LlamaIndex   │    Pinecone     │    RAG Apps           │
│   • crawl       │                 │    Weaviate     │                       │
│   • search      │   • chunk       │                 │                       │
│   • extract     │   • embed       │   • store       │   • retrieve          │
│                 │                 │   • index       │   • generate          │
│                 │                 │                 │                       │
└─────────────────┴─────────────────┴─────────────────┴───────────────────────┘

Supacrawl does one thing well: get clean markdown from the web.
```

## Comparison

|  | Supacrawl | crawl4ai | Firecrawl (self-hosted) | Firecrawl (cloud) |
| --- | --- | --- | --- | --- |
| **Infrastructure** | `pip install` | `pip install` | Docker + PostgreSQL + Redis | Hosted API |
| **MCP Server** | Built-in (`[mcp]` extra) | Not included | Not included | Yes |
| **Web Search** | Built-in (6 providers with fallback) | Not included | Via SearXNG | Yes |
| **LLM Providers** | Ollama, OpenAI, Anthropic | Any via LiteLLM | OpenAI (Ollama experimental) | OpenAI |
| **Intelligent Crawling** | Yes (agent command) | Yes (adaptive crawling) | No | Yes (/agent) |
| **Stealth/Anti-bot** | Yes (3-tier: Patchright + Camoufox) | Yes (undetected browser) | No (Fire-engine is cloud-only) | Yes (Fire-engine) |
| **PDF Parsing** | Yes (text + OCR) | No | No | No |
| **CAPTCHA Solving** | Yes (2Captcha) | Optional (CapSolver) | No | No |
| **Caching** | Local files | Built-in | PostgreSQL | Managed |
| **Licence** | MIT | Apache-2.0 | AGPL-3.0 | AGPL-3.0 |
| **Cost** | Free | Free | Free | Pay-per-use |

**Supacrawl** is minimal and focused. **crawl4ai** is a feature-rich framework with adaptive crawling and chunking. **Firecrawl** is an API server for applications needing a scraping backend.

## Licence

MIT

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.12+-3776ab?logo=python&logoColor=white)](https://python.org)
[![Playwright](https://img.shields.io/badge/Playwright-2ea44f?logo=playwright&logoColor=white)](https://playwright.dev)
[![MCP](https://img.shields.io/badge/MCP-Compatible-8A2BE2)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

<h1>Supacrawl</h1>

<em>Zero-infrastructure web scraping for the terminal and AI assistants.</em>

</div>

## Why Supacrawl?

There are excellent web scraping tools available. Supacrawl takes a different approach: a CLI tool designed for individual developers who want to scrape from the terminal.

- **Zero infrastructure**: `pip install` and go, no Docker/databases/Redis
- **Terminal-first**: Designed for shell workflows and pipelines
- **MCP server**: Give AI assistants direct access to web scraping
- **Clean markdown**: Playwright renders JS, outputs readable markdown
- **LLM-ready**: Built-in extraction with Ollama, OpenAI, or Anthropic
- **Stealth mode**: Patchright for anti-bot evasion, 2Captcha for CAPTCHAs

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

| Tool                 | Description                                          |
| -------------------- | ---------------------------------------------------- |
| `supacrawl_scrape`   | Scrape a URL to markdown, HTML, screenshot, or PDF   |
| `supacrawl_crawl`    | Crawl multiple pages from a site                     |
| `supacrawl_map`      | Discover URLs on a website without fetching content   |
| `supacrawl_search`   | Web search (DuckDuckGo or Brave)                     |
| `supacrawl_extract`  | Scrape pages for LLM-powered structured extraction   |
| `supacrawl_summary`  | Scrape a page for LLM-powered summarisation          |
| `supacrawl_diagnose` | Diagnose scraping issues (CDN, bot detection, etc.)  |
| `supacrawl_health`   | Server health check and capability report            |

The CLI's `agent` command is intentionally omitted. When used via MCP, your LLM orchestrates the primitives directly; it *is* the agent. For standalone agentic workflows, use `supacrawl agent` from the CLI.

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
        "SUPACRAWL_STEALTH": "true",
        "SUPACRAWL_LOCALE": "en-AU",
        "SUPACRAWL_TIMEZONE": "Australia/Sydney",
        "BRAVE_API_KEY": "your-key-here"
      }
    }
  }
}
```

All [configuration](#configuration) environment variables apply. The MCP server also supports `SUPACRAWL_LOG_LEVEL` (default: `INFO`).

### Troubleshooting

If scrapes return empty or minimal content, use `supacrawl_diagnose` to identify the cause (CDN protection, JS framework, bot detection). Common fixes: increase `wait_for` for JS-heavy sites, enable `SUPACRAWL_STEALTH=true` for bot-protected sites, or try `only_main_content=false` if the wrong content is extracted.

### Optional Extras

```bash
pip install supacrawl[mcp,stealth]   # Add anti-bot evasion
pip install supacrawl[mcp,captcha]   # Add CAPTCHA solving
```

## Commands

| Command             | Description                                     |
| ------------------- | ----------------------------------------------- |
| `scrape <url>`      | Scrape single page to markdown                  |
| `crawl <url>`       | Crawl website, save to directory                |
| `map <url>`         | Discover URLs from sitemap/links                |
| `search <query>`    | Web search (DuckDuckGo default, Brave optional) |
| `llm-extract <url>` | Extract structured data with LLM                |
| `agent <prompt>`    | Autonomous agent for complex tasks              |
| `cache`             | Cache management (clear, stats, prune)          |

Run `supacrawl <command> --help` for options.

## Output

Crawl produces a flat directory of markdown files:

```
output/
├── manifest.json          # URLs crawled (for resume)
├── index.md
├── about.md
└── docs_getting-started.md
```

Each markdown file includes YAML frontmatter with source URL and metadata.

## Configuration

### Core Settings

| Variable             | Default | Description                |
| -------------------- | ------- | -------------------------- |
| `SUPACRAWL_HEADLESS` | `true`  | Set `false` to see browser |
| `SUPACRAWL_TIMEOUT`  | `30000` | Page load timeout (ms)     |
| `SUPACRAWL_PROXY`    | -       | Proxy URL (http/socks5)    |

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

| Variable        | Description                                      |
| --------------- | ------------------------------------------------ |
| `BRAVE_API_KEY` | Optional: use Brave Search instead of DuckDuckGo |

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
pip install supacrawl[stealth]   # Patchright for anti-bot evasion
pip install supacrawl[captcha]   # 2Captcha for CAPTCHA solving
```

Use `--stealth` and `--solve-captcha` flags when scraping protected sites. Stealth mode automatically runs headful (visible browser) for better anti-detection. CAPTCHA solving requires `CAPTCHA_API_KEY` environment variable.

Copy `.env.example` to `.env` to configure.

## Development

```bash
# From source
conda env create -f environment.yaml && conda activate supacrawl
pip install -e .[dev]
playwright install chromium

# Quality checks
ruff check src/ && mypy src/
pytest -q -m "not e2e"
```

## Architecture

```
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

|                          | Supacrawl                 | crawl4ai                  | Firecrawl (self-hosted)        | Firecrawl (cloud) |
| ------------------------ | ------------------------- | ------------------------- | ------------------------------ | ----------------- |
| **Infrastructure**       | `pip install`             | `pip install`             | Docker + PostgreSQL + Redis    | Hosted API        |
| **MCP Server**           | Built-in (`[mcp]` extra)  | Not included              | Not included                   | Yes               |
| **Web Search**           | Built-in (DuckDuckGo)     | Not included              | Via SearXNG                    | Yes               |
| **LLM Providers**        | Ollama, OpenAI, Anthropic | Any via LiteLLM           | OpenAI (Ollama experimental)   | OpenAI            |
| **Intelligent Crawling** | Yes (agent command)       | Yes (adaptive crawling)   | No                             | Yes (/agent)      |
| **Stealth/Anti-bot**     | Yes (Patchright)          | Yes (undetected browser)  | No (Fire-engine is cloud-only) | Yes (Fire-engine) |
| **CAPTCHA Solving**      | Yes (2Captcha)            | Optional (CapSolver)      | No                             | No                |
| **Caching**              | Local files               | Built-in                  | PostgreSQL                     | Managed           |
| **Licence**              | MIT                       | Apache-2.0                | AGPL-3.0                       | AGPL-3.0          |
| **Cost**                 | Free                      | Free                      | Free                           | Pay-per-use       |

**Supacrawl** is minimal and focused. **crawl4ai** is a feature-rich framework with adaptive crawling and chunking. **Firecrawl** is an API server for applications needing a scraping backend.

## Licence

MIT

# Supacrawl Project Instructions

These instructions provide runtime context, defaults, and environment assumptions only.
See `.cursor/rules/` for constraints and requirements. See `docs/` for implementation patterns.

## Project Goal

**Firecrawl-compatible local web scraping CLI tool.**

**What This Means**:
- **API Compatibility**: Mirrors Firecrawl's API commands (scrape, crawl, map, search, extract)
- **Deployment Model**: Local CLI tool with optional local LLM support
- **Quality Target**: High-quality markdown extraction matching Firecrawl output
- **Key Features**: Caching, LLM extraction, autonomous agent, web search

**Current Status**: Full Firecrawl-compatible CLI with Playwright + markdownify

## Development Environment

- Conda environment: `supacrawl`
- Python: 3.12
- CLI tool: `supacrawl` command

## Technology Stack

- **Backend**: Python 3.12, Click (CLI), Pydantic, asyncio
- **Scraping**: Playwright, httpx, BeautifulSoup, markdownify
- **LLM**: Ollama, OpenAI, Anthropic (configurable providers)
- **Storage**: Local cache (`.supacrawl/cache/`)

## CLI Commands

The CLI provides Firecrawl-compatible commands:
- `scrape` - Scrape a single URL
- `crawl` - Crawl a website from a starting URL
- `map` - Map URLs from a website
- `search` - Search the web
- `llm-extract` - Extract structured data using LLM
- `agent` - Autonomous web agent
- `cache` - Manage local cache

## Key Reminders

- Do NOT create summary markdown documents
- Do NOT create deprecated or legacy code
- **Quality First**: Maintain high-quality markdown output

## Task Tracking

- **All tasks MUST be tracked as GitHub Issues**
- Use GitHub MCP tools for programmatic issue management:
  - `mcp_github_issue_write` - Create/update issues
  - `mcp_github_list_issues` - List and filter issues
  - `mcp_github_search_issues` - Search issues
  - `mcp_github_issue_read` - Get issue details
- Every issue requires minimum labels: `type:*` + `priority:*`
- Update issue status as work progresses
- Link PRs to issues with "Closes #123" in PR description
- See master docs for detailed MCP usage

## Development Rules

All detailed development rules are organized in `.cursor/rules/` and automatically loaded by editors.

Key rule files include:
- **00-project-foundations-supacrawl.mdc** - Project foundations and non-negotiable constraints
- **20-development-environment-supacrawl.mdc** - Development environment standards
- **20-cli-patterns-supacrawl.mdc** - CLI patterns and conventions
- **70-error-handling-supacrawl.mdc** - Error handling patterns

See `.cursor/rules/` for complete reference.

## Sources of Truth

- **Rules**: `.cursor/rules/` - Detailed development rules and constraints
- **Documentation**: `docs/` - Implementation patterns and guides
- **Master Docs**: `docs/master/` - Conceptual explanations (via symlink)


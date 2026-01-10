# Supacrawl Project Instructions

These instructions provide runtime context, defaults, and environment assumptions only.
See `.claude/rules/` for constraints and requirements. See `docs/` for implementation patterns.

## Mission

**Zero-infrastructure CLI web scraper with LLM extraction.**

- **Local-first**: pip install and go, no Docker/databases/infrastructure
- **CLI-first**: Designed for terminal workflows and pipelines
- **LLM-ready**: Multi-provider support (Ollama, OpenAI, Anthropic)
- **Key Features**: Web search, intelligent agent, stealth mode, CAPTCHA solving

## Development Environment

- Conda environment: `supacrawl`
- Python: 3.12
- CLI tool: `supacrawl` command

## Technology Stack

- **Backend**: Python 3.12, Click (CLI), Pydantic, asyncio
- **Scraping**: Playwright, httpx, BeautifulSoup, markdownify
- **LLM**: Ollama, OpenAI, Anthropic (configurable providers)
- **Storage**: Local cache (`.supacrawl/cache/`)

## Key Reminders

- Do NOT create summary markdown documents
- Do NOT create deprecated or legacy code
- **Quality First**: Maintain high-quality markdown output

## Task Tracking

- **All tasks MUST be tracked as GitHub Issues**
- Use GitHub CLI (`gh`) for issue management
- Every issue requires minimum labels: `type:*` + `priority:*`
- Link PRs to issues with "Closes #123" in PR description

## Sources of Truth

- **Rules**: `.claude/rules/` - Detailed development rules and constraints
- **Documentation**: `docs/` - Implementation patterns and guides
- **Master Rules**: `.claude/rules/master/` - Universal principles (via symlink)

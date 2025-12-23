# Web-Scraper Project Instructions

These instructions provide runtime context, defaults, and environment assumptions only.
See `.claude/rules/` for constraints and requirements. See `docs/` for implementation patterns.

## Project Goal

**Build a local-first web scraper that produces Firecrawl-compatible markdown output.**

**What This Means**:
- **Output Format**: Same markdown structure as Firecrawl (clean markdown, manifests, chunks)
- **Deployment Model**: Local CLI tool (NOT a SaaS API replacement)
- **Quality Target**: 95%+ similarity to Firecrawl on all page types
- **Unique Features**: Snapshot versioning, auto-resume, local execution

**Current Status**: Firecrawl-compatible output using Playwright + markdownify

## Development Environment

- Conda environment: `web-scraper`
- Python: 3.12
- CLI tool: `web-scraper` command

## Technology Stack

- **Backend**: Python 3.12, Click (CLI), Pydantic, asyncio
- **Scraping**: Playwright, httpx, BeautifulSoup, markdownify
- **LLM**: Ollama (local models)
- **Storage**: Filesystem-based (corpora/ directory)

## Key Reminders

- Do NOT create summary markdown documents
- Do NOT create deprecated or legacy code
- **Quality First**: Maintain 95%+ parity with Firecrawl output

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

All detailed development rules are organized in `.claude/rules/` and automatically loaded by Claude Code.

Key rule files include:
- **00-project-foundations-web-scraper.mdc** - Project foundations and non-negotiable constraints
- **20-python-backend-web-scraper.mdc** - Python backend development standards (if exists)
- **30-architecture-web-scraper.mdc** - System architecture and design patterns (if exists)

See `.claude/rules/README.md` for complete reference and `.claude/rules/master/` for universal principles.

## Sources of Truth

- **Rules**: `.claude/rules/` - Detailed development rules and constraints
- **Documentation**: `docs/` - Implementation patterns and guides
- **Master Rules**: `.claude/rules/master/` - Universal principles (via symlink)
- **Master Docs**: `docs/master/` - Conceptual explanations (via symlink)


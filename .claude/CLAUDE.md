# Supacrawl Project Instructions

These instructions provide runtime context, defaults, and environment assumptions only.
See `.cursor/rules/` for constraints and requirements. See `docs/` for implementation patterns.

## Project Goal

**Build a local-first web scraper that produces Firecrawl-compatible markdown output.**

**What This Means**:
- **Output Format**: Same markdown structure as Firecrawl (clean markdown, manifests, chunks)
- **Deployment Model**: Local CLI tool (NOT a SaaS API replacement)
- **Quality Target**: 95%+ similarity to Firecrawl on all page types
- **Unique Features**: Snapshot versioning, auto-resume, local execution

**Current Status**: Firecrawl-compatible output using Playwright + markdownify

## Development Environment

- Conda environment: `supacrawl`
- Python: 3.12
- CLI tool: `supacrawl` command

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

All detailed development rules are organized in `.cursor/rules/` and automatically loaded by editors.

Key rule files include:
- **00-project-foundations-supacrawl.mdc** - Project foundations and non-negotiable constraints
- **20-development-environment-supacrawl.mdc** - Development environment standards
- **50-corpus-layout-patterns-supacrawl.mdc** - Corpus layout patterns
- **70-error-handling-supacrawl.mdc** - Error handling patterns

See `.cursor/rules/` for complete reference.

## Sources of Truth

- **Rules**: `.cursor/rules/` - Detailed development rules and constraints
- **Documentation**: `docs/` - Implementation patterns and guides
- **Master Docs**: `docs/master/` - Conceptual explanations (via symlink)


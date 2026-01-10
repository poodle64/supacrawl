---
paths: "**/*"
---

# Development Environment

This rule extends `.claude/rules/master/20-development-environment.md` with supacrawl-specific patterns. Universal conda environment and environment variable patterns are covered in the master rule.

## Conda Environment

- Use `supacrawl` conda environment (see `.claude/rules/master/20-development-environment.md` for activation requirements)
- Activate conda environment before running CLI commands, tests, or installing packages
- Install all dependencies using `conda env create -f environment.yaml` (includes dev, stealth, captcha extras)
- Use conda environment for all development work (ruff, mypy, pytest)

## Directory Structure

- Keep CLI modules in `src/supacrawl/cli/` directory
- Keep service modules in `src/supacrawl/services/` directory
- Keep LLM provider modules in `src/supacrawl/llm/` directory
- Use cache directory at `.supacrawl/cache/` for scraped content

## Environment Variables

- Use `.env` file for local development configuration
- Document all required environment variables in README
- May set `SUPACRAWL_*` environment variables to configure browser behaviour (headless mode, locale, timezone, user agent, wait conditions, proxy)
- May set `SUPACRAWL_LLM_PROVIDER` to select LLM provider (`ollama`, `openai`, or `anthropic`)
- May set `SUPACRAWL_LLM_MODEL` for model name (e.g., `qwen3:8b`, `gpt-4o-mini`)
- May set `OLLAMA_HOST` for Ollama server URL (default: `http://localhost:11434`)
- May set `OPENAI_API_KEY` for OpenAI API access
- May set `ANTHROPIC_API_KEY` for Anthropic API access
- May set `BRAVE_API_KEY` for Brave Search API access
- **Must NOT** commit `.env` files to version control
- **Must NOT** hardcode API keys or URLs in code

## References

- `.claude/rules/master/20-development-environment.md` - Universal development environment mechanics
- `.claude/rules/50-scraper-provider-patterns.md` - Playwright scraper patterns

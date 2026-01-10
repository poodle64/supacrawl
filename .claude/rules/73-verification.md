---
paths: "**/*"
---

# Verification

**Note**: Universal verification principles (checklist structure, runbook requirements, troubleshooting documentation) are covered in master 73-verification.

This rule documents project-specific verification practice and relies on master rules for requirements.

## Pre-Delivery Verification Checklist

Before considering supacrawl changes complete:

- [ ] All tests pass (`pytest -q`)
- [ ] Quality checks pass (`ruff check supacrawl`, `mypy supacrawl`)
- [ ] Playwright scraper executes successfully (test scrape)
- [ ] CLI commands work correctly (test all commands)
- [ ] LLM providers are correctly configured (if applicable)
- [ ] Cache operations work correctly
- [ ] Error handling works (test error paths)

**Note**: This checklist serves as a reminder only. See `.claude/rules/master/73-verification.md` for universal verification checklist structure. See `.claude/rules/master/70-reliability.md` for error handling verification requirements. See `.claude/rules/master/71-testing-patterns.md` for test coverage verification requirements.

## Playwright Scraper Verification

### Scraper Execution

- Test Playwright scraper with valid URLs
- Verify scraper returns structured content (markdown, HTML, links)
- Verify scraper error handling works (test invalid URLs)
- Verify scraper retry logic works (test transient failures)

### Scraper Configuration

- Verify Playwright installation (`playwright-doctor`)
- Verify Playwright browsers are installed (`playwright-setup`)
- Verify required environment variables are documented
- Verify optional environment variables have defaults
- Test scraper initialization with dependency injection (for testing)

## LLM Provider Verification

### Provider Configuration

- Verify Ollama connection works (default provider)
- Verify OpenAI API key configuration (if used)
- Verify Anthropic API key configuration (if used)
- Verify provider switching works correctly

### Extraction Verification

- Test LLM extraction with simple prompts
- Test LLM extraction with JSON schema
- Verify extraction error handling (provider unavailable)
- Verify structured output matches schema

## Cache Verification

### Cache Operations

- Verify cache directory is created correctly
- Verify cache stores scraped content
- Verify cache retrieves stored content
- Verify cache expiration works

### Cache Management

- Test `cache stats` command shows correct statistics
- Test `cache clear` removes all entries
- Test `cache clear --url` removes specific URL
- Test `cache prune` removes expired entries

## CLI Verification

### Command Execution

- Test all CLI commands: `scrape`, `crawl`, `map`, `search`, `llm-extract`, `agent`, `cache`
- Verify commands produce expected output
- Verify commands handle errors gracefully (show friendly messages)
- Verify commands exit with correct codes (0 for success, 1 for errors)

### Error Handling

- Test invalid URLs (show appropriate errors)
- Test LLM provider failures (show provider errors)
- Test network failures (show connection errors)
- Verify correlation IDs appear in error messages

## Verification Practices

Supacrawl verification typically includes:

- **Runbook**: Provide copy-paste commands for conda activation, installing dependencies, running quality checks, testing providers
- **Scraper testing**: Verify Playwright scraper executes correctly
- **LLM testing**: Verify LLM providers connect and extract correctly
- **Cache testing**: Verify cache operations work correctly
- **CLI testing**: Verify all commands work correctly

**Note**: See `.claude/rules/master/73-verification.md` for universal runbook requirements.

## Troubleshooting

### Scraper Issues

- Verify Playwright installation (`playwright-doctor`)
- Verify Playwright browsers are installed (`playwright-setup`)
- Verify scraper initializes correctly
- Check scraper logs for correlation IDs

### LLM Provider Issues

- Verify Ollama is running (`ollama serve`)
- Verify API keys are set correctly for cloud providers
- Check provider-specific error messages
- Verify model names are correct

### Cache Issues

- Verify cache directory exists and is writable
- Check cache file permissions
- Verify cache is not corrupted (clear and retry)

## References

- `.claude/rules/master/73-verification.md` - Universal verification principles
- `.claude/rules/20-development-environment.md` - Conda environment and setup
- `.claude/rules/50-scraper-provider-patterns.md` - Playwright scraper patterns to verify
- `.claude/rules/71-testing-patterns.md` - Testing tools and patterns

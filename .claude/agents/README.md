# Claude Code Agents

## Important: Agent Format Clarification

**Claude Code does NOT use JSON agent configuration files.**

The previous `.claude/agents/*.json` files were archived to `_archived/` because they used a custom format that Claude Code doesn't recognise.

## How Claude Code Agents Work

Claude Code uses the **Task tool** with `subagent_type` parameter for spawning specialised agents. These are built-in agent types, not custom configurations.

### Available Subagent Types

From the Claude Code system:
- `general-purpose` - Multi-step tasks, code search, research
- `Explore` - Fast codebase exploration
- `Plan` - Software architecture and implementation planning
- `claude-code-guide` - Questions about Claude Code features

### How to Use Subagents

Agents are invoked through the Task tool, not through configuration files:

```
Task tool with subagent_type='Explore' for codebase exploration
Task tool with subagent_type='Plan' for architecture planning
```

## Skills vs Agents

- **Skills** (`.claude/skills/*/SKILL.md`): Auto-loaded context based on description matching. Generated from cursor rules with `agentMapping` frontmatter.
- **Agents** (subagents): Invoked explicitly via Task tool. Built-in types, not configurable.

## Domain Knowledge

For domain-specific knowledge (scraper patterns, corpus layout, CLI patterns), use **Skills** with embedded rule content, not agents. Skills are auto-generated from cursor rules with `agentMapping` frontmatter.

See `.cursor/rules/AGENT-MAPPING-SCHEMA.md` for how to add domain knowledge to skills.

## Archived Agents

The `_archived/` folder contains previous JSON agent configs that were created before understanding Claude Code's actual architecture. They're kept for reference but are not functional.

## Future Considerations

If you need workflow orchestration beyond what skills provide, consider:
1. Custom slash commands (`.claude/commands/*.md`)
2. Hooks for automation (`.claude/settings.json`)
3. The Plan subagent for complex multi-step tasks

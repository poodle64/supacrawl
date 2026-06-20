# Configuration

supacrawl runs with no configuration out of the box. When you do want to change a default — pin a browser engine, set your locale, throttle search — there is one typed settings model, one local store, and a clear precedence order. The same model emits a machine-readable schema so a separate control-plane GUI can render a settings form and tune supacrawl without touching the CLI.

## Precedence

Settings resolve in three layers, each overriding the one before:

1. **Built-in defaults** — sensible values baked into the model.
2. **The stored file** — `~/.supacrawl/config.toml` (override the location with `SUPACRAWL_CONFIG_PATH`). Human-readable TOML; only values that differ from the default are written, so the file stays small.
3. **Environment variables** — `SUPACRAWL_<NAME>` (e.g. `SUPACRAWL_TIMEOUT`, `SUPACRAWL_ENGINE`). An environment variable always wins over the stored file.

On top of all three, a **per-command flag** (`supacrawl scrape --engine camoufox`) overrides the standing baseline for that one invocation.

```text
default  <  stored file  <  environment  <  per-command flag
```

## Managing settings from the CLI

```bash
supacrawl config get                 # effective values (environment applied)
supacrawl config get --stored        # only the file + defaults, env ignored
supacrawl config get engine          # a single value
supacrawl config set engine camoufox # persist a default to the store
supacrawl config unset engine        # revert to the default
supacrawl config path                # where the store lives
```

`config set` validates the value against the field's type and range before writing, so a bad value is rejected at the point of entry rather than at scrape time.

## Runtime adoption status

The settings schema, the store, and the `config` CLI are complete. Runtime consumption is being adopted incrementally: the **`strategy_memory`, `metrics`, and `metrics_full_url`** toggles are read from the resolved config (store + environment) on every CLI and MCP run today. The remaining knobs (browser, anti-bot, search, locale, cache) are exposed in the schema and persisted in the store for a control-plane GUI; their adoption into each command's option resolution is rolling out. Until then, set those via their environment variables or per-command flags.

## Settings

Every setting is a standing default; a per-request flag or API argument still overrides it. Grouped as the GUI renders them:

| Group | Setting | Env var | Default | Notes |
| --- | --- | --- | --- | --- |
| browser | `timeout` | `SUPACRAWL_TIMEOUT` | `30000` | Page load timeout (ms), 1000–300000. |
| browser | `headless` | `SUPACRAWL_HEADLESS` | `true` | Run without a visible window. |
| browser | `wait_until` | `SUPACRAWL_WAIT_UNTIL` | `domcontentloaded` | `domcontentloaded` / `load` / `networkidle`. |
| browser | `user_agent` | `SUPACRAWL_USER_AGENT` | _(engine default)_ | Override the User-Agent string. |
| locale | `locale` | `SUPACRAWL_LOCALE` | `en-US` | Maps to Accept-Language. |
| locale | `timezone` | `SUPACRAWL_TIMEZONE` | `UTC` | e.g. `Australia/Brisbane`. |
| anti_bot | `engine` | `SUPACRAWL_ENGINE` | _(auto)_ | `playwright` / `patchright` / `camoufox`. Leave unset to auto-escalate. |
| anti_bot | `stealth` | `SUPACRAWL_STEALTH` | `false` | Start with Patchright. Usually unnecessary. |
| anti_bot | `escalate` | `SUPACRAWL_ESCALATE` | `true` | Auto-climb the engine/stealth ladder on a poor result. |
| anti_bot | `solve_captcha` | `SUPACRAWL_SOLVE_CAPTCHA` | `false` | Needs a CAPTCHA API key; each solve costs money. |
| content | `only_main_content` | `SUPACRAWL_ONLY_MAIN_CONTENT` | `true` | Strip nav/header/footer. |
| search | `search_providers` | `SUPACRAWL_SEARCH_PROVIDERS` | _(none)_ | Ordered fallback chain, e.g. `brave,tavily,serper`. |
| search | `search_provider` | `SUPACRAWL_SEARCH_PROVIDER` | `brave` | Legacy single provider. |
| search | `search_rate_limit` | `SUPACRAWL_SEARCH_RATE_LIMIT` | _(provider default)_ | Requests per second. |
| memory | `strategy_memory` | `SUPACRAWL_STRATEGY_MEMORY` | `true` | Per-domain strategy learning. |
| telemetry | `metrics` | `SUPACRAWL_METRICS` | `true` | Record one quality/usage event per scrape/search. |
| telemetry | `metrics_full_url` | `SUPACRAWL_METRICS_FULL_URL` | `false` | Log full URLs, not just the domain. Off for privacy. |
| cache | `cache_dir` | `SUPACRAWL_CACHE_DIR` | _(default location)_ | Where cached content lives. |

## Secrets

Credentials are **environment-only**. They are never written to the store and never appear in the GUI schema — a dashboard can see _whether_ each is set, never its value.

```bash
supacrawl config secrets   # presence only, never the value
```

Honoured: `CAPTCHA_API_KEY`, `BRAVE_API_KEY`, `TAVILY_API_KEY`, `SERPER_API_KEY`, `SERPAPI_API_KEY`, `EXA_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and `SUPACRAWL_PROXY` (treated as a secret because a proxy URL can carry credentials).

## The settings schema (for a GUI)

`supacrawl config schema` emits the JSON schema of the settings model. Each field carries `x-ui` render metadata so a control-plane dashboard can build a settings form directly from it:

```json
{
  "properties": {
    "timeout": {
      "type": "integer",
      "default": 30000,
      "minimum": 1000,
      "maximum": 300000,
      "x-ui": {
        "group": "browser",
        "order": 10,
        "widget": "slider",
        "help": "How long to wait for a page to load..."
      }
    }
  }
}
```

The `x-ui` keys are `group`, `order`, `widget`, `help`, and an optional `visible_when` (conditional visibility, e.g. `metrics_full_url` is shown only when `metrics` is on). A GUI reads the schema for layout, reads and writes values through the same store the CLI uses, and reads `config secrets` for credential presence. The CLI emits; a GUI consumes — they share one source of truth.

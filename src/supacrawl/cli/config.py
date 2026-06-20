"""Configuration commands (#138).

supacrawl resolves a standing baseline config from model defaults, a local TOML
store, and the environment (in that order of increasing precedence). These
commands inspect and edit the stored layer and emit the GUI settings schema. The
schema and the store are the seam a separate control-plane dashboard consumes;
this is the terminal-native view of the same surface.
"""

import json

import click
from pydantic import ValidationError

from supacrawl.cli._common import app
from supacrawl.config import (
    SupacrawlConfig,
    SupacrawlSecrets,
    config_path,
    config_schema,
    load_config,
    set_config_value,
    stored_config,
)


@app.group()
def config() -> None:
    """Inspect and edit supacrawl's settings.

    Precedence (lowest to highest): built-in default, the stored TOML file, then
    environment variables (SUPACRAWL_<NAME>). A per-command flag overrides all
    three for that one invocation. Secrets (API keys, proxy) are environment-only
    and never written to the store.

    Examples:
        supacrawl config get                 # effective values (env applied)
        supacrawl config get --stored        # only the stored file + defaults
        supacrawl config set engine camoufox # persist a default to the store
        supacrawl config schema              # the GUI settings schema (JSON)
        supacrawl config path                # where the store lives
        supacrawl config secrets             # which credentials are set (no values)
    """


@config.command("path")
def config_path_cmd() -> None:
    """Print the path to the config store."""
    click.echo(config_path())


@config.command("get")
@click.argument("key", required=False)
@click.option("--stored", is_flag=True, help="Show only the stored file + defaults, ignoring the environment.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def config_get(key: str | None, stored: bool, as_json: bool) -> None:
    """Show the effective config, or a single KEY.

    By default this is the resolved value (environment applied). Use --stored to
    see what the file alone would yield.
    """
    cfg = stored_config() if stored else load_config()

    if key is not None:
        if key not in SupacrawlConfig.model_fields:
            click.echo(f"Unknown config key: {key}", err=True)
            raise SystemExit(1)
        value = getattr(cfg, key)
        click.echo(json.dumps(value) if as_json else value)
        return

    data = cfg.model_dump()
    if as_json:
        click.echo(json.dumps(data, indent=2))
        return
    for name, value in data.items():
        click.echo(f"{name} = {value}")


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Persist KEY=VALUE to the stored config.

    The value is validated and coerced to the field's type. Writes only the
    stored layer; the environment is never baked into the file.
    """
    try:
        set_config_value(key, value)
    except KeyError:
        click.echo(f"Unknown config key: {key}", err=True)
        raise SystemExit(1) from None
    except ValidationError as e:
        click.echo(f"Invalid value for {key}: {e.errors()[0]['msg']}", err=True)
        raise SystemExit(1) from None
    click.echo(f"Set {key} = {value} in {config_path()}")


@config.command("unset")
@click.argument("key")
def config_unset(key: str) -> None:
    """Remove KEY from the stored config, reverting it to the default."""
    if key not in SupacrawlConfig.model_fields:
        click.echo(f"Unknown config key: {key}", err=True)
        raise SystemExit(1)
    from supacrawl.config import _read_stored, save_config

    stored = _read_stored()
    if key not in stored:
        click.echo(f"{key} is not set in the store; nothing to do.")
        return
    del stored[key]
    save_config(SupacrawlConfig.model_validate(stored))
    click.echo(f"Unset {key}; reverted to default.")


@config.command("schema")
def config_schema_cmd() -> None:
    """Print the GUI settings schema (JSON, with x-ui metadata)."""
    click.echo(json.dumps(config_schema(), indent=2))


@config.command("secrets")
def config_secrets() -> None:
    """Show which credentials are configured in the environment (never the values)."""
    configured = SupacrawlSecrets.from_env().configured()
    for name, present in configured.items():
        mark = "set" if present else "-"
        click.echo(f"{name}: {mark}")

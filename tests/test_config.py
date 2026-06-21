"""Tests for the config seam (#138): the GUI schema, the secrets split, the TOML
store, and env > stored > default precedence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from supacrawl.config import (
    SupacrawlConfig,
    SupacrawlSecrets,
    config_schema,
    load_config,
    save_config,
    set_config_value,
    stored_config,
)

# The x-ui keys every tunable field must carry, mirroring the ragify convention.
_REQUIRED_UI_KEYS = {"group", "order", "widget", "help"}


# ---------------------------------------------------------------------------
# x-ui schema contract — the dashboard renders the form from this
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_every_config_field_has_complete_x_ui() -> None:
    """Each tunable field must expose x-ui metadata with all required keys."""
    schema = config_schema()
    props = schema["properties"]
    assert set(props) == set(SupacrawlConfig.model_fields), "schema must cover every field"
    for name, prop in props.items():
        assert "x-ui" in prop, f"{name} is missing x-ui metadata"
        ui = prop["x-ui"]
        missing = _REQUIRED_UI_KEYS - set(ui)
        assert not missing, f"{name} x-ui missing keys: {missing}"
        assert isinstance(ui["order"], int)
        assert ui["help"], f"{name} has empty help text"


@pytest.mark.unit
def test_x_ui_survives_into_json_schema() -> None:
    """A representative field's widget hint reaches the emitted schema verbatim."""
    schema = config_schema()
    assert schema["properties"]["timeout"]["x-ui"]["widget"] == "slider"
    assert schema["properties"]["metrics_full_url"]["x-ui"]["visible_when"] == {"metrics": True}


@pytest.mark.unit
def test_secrets_model_carries_no_x_ui() -> None:
    """Secrets must be structurally absent from anything a GUI would render."""
    schema = SupacrawlSecrets.model_json_schema()
    for name, prop in schema["properties"].items():
        assert "x-ui" not in prop, f"secret {name} leaked x-ui metadata into the schema"


@pytest.mark.unit
def test_no_secret_field_appears_in_config_schema() -> None:
    """Credential names must never appear in the GUI config schema."""
    config_fields = set(config_schema()["properties"])
    secret_fields = set(SupacrawlSecrets.model_fields)
    assert config_fields.isdisjoint(secret_fields)


# ---------------------------------------------------------------------------
# Store round-trip
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_save_writes_only_non_defaults(tmp_path: Path) -> None:
    """The store stays minimal — only values that differ from the default."""
    path = tmp_path / "config.toml"
    save_config(SupacrawlConfig(engine="camoufox", timeout=60000), path=path)

    import tomllib

    with path.open("rb") as f:
        written = tomllib.load(f)
    assert written == {"engine": "camoufox", "timeout": 60000}


@pytest.mark.unit
def test_round_trip_preserves_values(tmp_path: Path) -> None:
    """A saved config reloads (from the file alone) with the same values."""
    path = tmp_path / "config.toml"
    save_config(SupacrawlConfig(headless=False, locale="en-AU", search_rate_limit=5.0), path=path)

    reloaded = stored_config(path=path)
    assert reloaded.headless is False
    assert reloaded.locale == "en-AU"
    assert reloaded.search_rate_limit == 5.0
    # Untouched fields fall back to the model default.
    assert reloaded.timeout == 30000


# ---------------------------------------------------------------------------
# Precedence: default < stored < env
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_default_when_nothing_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPACRAWL_TIMEOUT", raising=False)
    cfg = load_config(path=tmp_path / "absent.toml")
    assert cfg.timeout == 30000


@pytest.mark.unit
def test_stored_overrides_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPACRAWL_TIMEOUT", raising=False)
    path = tmp_path / "config.toml"
    save_config(SupacrawlConfig(timeout=12345), path=path)
    assert load_config(path=path).timeout == 12345


@pytest.mark.unit
def test_env_overrides_stored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "config.toml"
    save_config(SupacrawlConfig(timeout=12345, engine="patchright"), path=path)
    monkeypatch.setenv("SUPACRAWL_TIMEOUT", "99000")
    cfg = load_config(path=path)
    assert cfg.timeout == 99000  # env wins
    assert cfg.engine == "patchright"  # stored still applies where env is absent


@pytest.mark.unit
def test_env_bool_coercion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A string env value coerces to the field's bool type."""
    monkeypatch.setenv("SUPACRAWL_HEADLESS", "false")
    monkeypatch.setenv("SUPACRAWL_STRATEGY_MEMORY", "0")
    cfg = load_config(path=tmp_path / "absent.toml")
    assert cfg.headless is False
    assert cfg.strategy_memory is False


# ---------------------------------------------------------------------------
# set_config_value
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_set_config_value_coerces_and_persists(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    set_config_value("timeout", "45000", path=path)  # string in, int out
    assert stored_config(path=path).timeout == 45000


@pytest.mark.unit
def test_set_config_value_rejects_unknown_key(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        set_config_value("not_a_field", "x", path=tmp_path / "config.toml")


@pytest.mark.unit
def test_set_config_value_rejects_invalid_value(tmp_path: Path) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        set_config_value("timeout", "not-a-number", path=tmp_path / "config.toml")


@pytest.mark.unit
def test_set_config_value_rejects_out_of_range(tmp_path: Path) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        set_config_value("timeout", "10", path=tmp_path / "config.toml")  # below ge=1000


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_secrets_configured_reports_presence_not_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRAVE_API_KEY", "super-secret-value")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    secrets = SupacrawlSecrets.from_env()
    configured = secrets.configured()
    assert configured["brave_api_key"] is True
    assert configured["tavily_api_key"] is False
    # The presence map must never carry the value itself.
    assert "super-secret-value" not in str(configured)


@pytest.mark.unit
def test_metrics_password_reported_in_secrets_presence(monkeypatch: pytest.MonkeyPatch) -> None:
    """metrics_password presence is reported by configured(); its value never leaks."""
    monkeypatch.setenv("SUPACRAWL_METRICS_PASSWORD", "hunter2")
    monkeypatch.delenv("SUPACRAWL_METRICS_TOKEN", raising=False)
    secrets = SupacrawlSecrets.from_env()
    configured = secrets.configured()
    assert configured["metrics_password"] is True
    assert configured["metrics_token"] is False
    assert "hunter2" not in str(configured)


# ---------------------------------------------------------------------------
# New telemetry config fields
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_metrics_remote_username_in_config_schema() -> None:
    """metrics_remote_username must appear in the GUI schema with x-ui metadata."""
    schema = config_schema()
    assert "metrics_remote_username" in schema["properties"]
    ui = schema["properties"]["metrics_remote_username"]["x-ui"]
    assert ui["group"] == "telemetry"
    assert ui["widget"] == "text"
    assert "help" in ui


@pytest.mark.unit
def test_metrics_remote_tenant_in_config_schema() -> None:
    """metrics_remote_tenant must appear in the GUI schema with x-ui metadata."""
    schema = config_schema()
    assert "metrics_remote_tenant" in schema["properties"]
    ui = schema["properties"]["metrics_remote_tenant"]["x-ui"]
    assert ui["group"] == "telemetry"
    assert ui["widget"] == "text"


@pytest.mark.unit
def test_new_telemetry_fields_not_in_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """metrics_remote_username and metrics_remote_tenant live in config, not secrets."""
    secret_fields = set(SupacrawlSecrets.model_fields)
    assert "metrics_remote_username" not in secret_fields
    assert "metrics_remote_tenant" not in secret_fields

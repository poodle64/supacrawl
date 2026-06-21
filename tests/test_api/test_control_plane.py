"""Tests for the read-only control-plane REST endpoints.

GET /supacrawl/config/schema  — JSON schema for the settings form.
GET /supacrawl/config         — effective non-secret config + secrets presence map.
GET /supacrawl/metrics/summary — telemetry headline rollup.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from supacrawl.api.app import create_app
from supacrawl.config import SupacrawlSecrets


@pytest.fixture()
def app() -> FastAPI:
    """Create the FastAPI app without triggering lifespan services."""
    return create_app()


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    """Return a ``TestClient`` wired to the app."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /supacrawl/config/schema
# ---------------------------------------------------------------------------


class TestConfigSchema:
    """Schema endpoint returns the full GUI-renderable JSON schema."""

    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/supacrawl/config/schema")
        assert resp.status_code == 200

    def test_response_is_object_schema(self, client: TestClient) -> None:
        data = client.get("/supacrawl/config/schema").json()
        assert data["type"] == "object"
        assert "properties" in data

    def test_includes_telemetry_fields(self, client: TestClient) -> None:
        props = client.get("/supacrawl/config/schema").json()["properties"]
        assert "metrics_remote_url" in props
        assert "metrics_remote_username" in props
        assert "metrics_remote_tenant" in props

    def test_x_ui_metadata_present(self, client: TestClient) -> None:
        """Every property must carry x-ui metadata (dashboard renders from this)."""
        props = client.get("/supacrawl/config/schema").json()["properties"]
        for name, prop in props.items():
            assert "x-ui" in prop, f"{name} is missing x-ui metadata"

    def test_no_secret_fields_in_schema(self, client: TestClient) -> None:
        """Secret fields must never appear in the config schema endpoint."""
        props = set(client.get("/supacrawl/config/schema").json()["properties"])
        secret_fields = set(SupacrawlSecrets.model_fields)
        assert props.isdisjoint(secret_fields)


# ---------------------------------------------------------------------------
# GET /supacrawl/config
# ---------------------------------------------------------------------------


class TestConfigEffective:
    """Effective config endpoint never leaks secret values."""

    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/supacrawl/config")
        assert resp.status_code == 200

    def test_response_has_config_and_secrets_keys(self, client: TestClient) -> None:
        data = client.get("/supacrawl/config").json()
        assert "config" in data
        assert "secrets" in data

    def test_secrets_object_contains_only_booleans(self, client: TestClient) -> None:
        """Secrets presence map must contain only booleans, never values."""
        secrets = client.get("/supacrawl/config").json()["secrets"]
        for key, val in secrets.items():
            assert isinstance(val, bool), f"secrets[{key!r}] is {type(val).__name__}, expected bool"

    def test_secrets_presence_reflects_env(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        """Setting SUPACRAWL_METRICS_PASSWORD must flip metrics_password to True."""
        with patch.dict("os.environ", {"SUPACRAWL_METRICS_PASSWORD": "sekret"}):
            resp = client.get("/supacrawl/config")
        data = resp.json()
        assert data["secrets"]["metrics_password"] is True

    def test_secret_value_never_in_response(self, client: TestClient) -> None:
        """Secret values must not appear anywhere in the serialised response."""
        secret_val = "super-secret-token-xyz"
        with patch.dict("os.environ", {"SUPACRAWL_METRICS_TOKEN": secret_val}):
            resp = client.get("/supacrawl/config")
        assert secret_val not in resp.text

    def test_config_contains_known_fields(self, client: TestClient) -> None:
        config = client.get("/supacrawl/config").json()["config"]
        assert "timeout" in config
        assert "metrics" in config
        assert "metrics_remote_url" in config


# ---------------------------------------------------------------------------
# GET /supacrawl/metrics/summary
# ---------------------------------------------------------------------------


class TestMetricsSummary:
    """Metrics summary endpoint returns the expected aggregation keys."""

    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/supacrawl/metrics/summary")
        assert resp.status_code == 200

    def test_response_has_expected_keys(self, client: TestClient) -> None:
        data = client.get("/supacrawl/metrics/summary").json()
        assert "scrapes" in data
        assert "searches" in data
        assert "success_rate" in data
        assert "escalation_rate" in data
        assert "by_verdict" in data
        assert "top_domains" in data

    def test_days_parameter_accepted(self, client: TestClient) -> None:
        resp = client.get("/supacrawl/metrics/summary?days=30")
        assert resp.status_code == 200

    def test_days_validation_rejects_zero(self, client: TestClient) -> None:
        resp = client.get("/supacrawl/metrics/summary?days=0")
        assert resp.status_code == 400

    def test_summary_returns_integer_counts(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        """Summary values must be integers (or None for rates when no scrapes)."""
        # Point the reader at a temp dir with no events so the result is deterministic.
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            monkeypatch.setenv("SUPACRAWL_METRICS_DIR", td)
            resp = client.get("/supacrawl/metrics/summary?days=1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["scrapes"] == 0
        assert data["searches"] == 0
        assert data["success_rate"] is None
        assert data["escalation_rate"] is None


class TestConfigCredentialMasking:
    """Credentials embedded in metrics_remote_url must never reach the response."""

    def test_url_embedded_password_is_stripped(self, client: TestClient) -> None:
        with patch("supacrawl.config.load_config") as mock_load:
            mock_load.return_value.model_dump.return_value = {
                "metrics_remote_url": "https://user:sup3rsecret@loki.example.com/loki/api/v1/push",
                "metrics": True,
            }
            resp = client.get("/supacrawl/config")
        assert resp.status_code == 200
        assert "sup3rsecret" not in resp.text
        # Host preserved so a GUI can still display/edit the endpoint.
        assert resp.json()["config"]["metrics_remote_url"] == "https://loki.example.com/loki/api/v1/push"

"""Tests for API key authentication dependency."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from supacrawl.api.auth import get_api_key


def _make_app() -> FastAPI:
    """Create a minimal FastAPI app with a protected route."""
    app = FastAPI()

    @app.get("/protected")
    async def protected(api_key: str | None = Depends(get_api_key)):
        return {"authenticated": True, "key": api_key}

    return app


# -- Auth disabled (SUPACRAWL_API_KEY not set) ---------------------------


class TestAuthDisabled:
    """When SUPACRAWL_API_KEY is not in the environment, all requests pass."""

    @pytest.fixture(autouse=True)
    def _unset_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("SUPACRAWL_API_KEY", raising=False)

    def test_no_header_passes(self):
        client = TestClient(_make_app())
        resp = client.get("/protected")
        assert resp.status_code == 200
        assert resp.json()["authenticated"] is True
        assert resp.json()["key"] is None

    def test_arbitrary_header_passes(self):
        client = TestClient(_make_app())
        resp = client.get("/protected", headers={"Authorization": "Bearer whatever"})
        assert resp.status_code == 200


# -- Auth enabled (SUPACRAWL_API_KEY set) --------------------------------


class TestAuthEnabled:
    """When SUPACRAWL_API_KEY is set, only matching Bearer tokens pass."""

    SECRET = "test-secret-key-123"

    @pytest.fixture(autouse=True)
    def _set_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SUPACRAWL_API_KEY", self.SECRET)

    def test_valid_key_passes(self):
        client = TestClient(_make_app())
        resp = client.get("/protected", headers={"Authorization": f"Bearer {self.SECRET}"})
        assert resp.status_code == 200
        assert resp.json()["key"] == self.SECRET

    def test_invalid_key_rejected(self):
        client = TestClient(_make_app())
        resp = client.get("/protected", headers={"Authorization": "Bearer wrong-key"})
        assert resp.status_code == 401

    def test_missing_header_rejected(self):
        client = TestClient(_make_app())
        resp = client.get("/protected")
        assert resp.status_code == 401

    def test_malformed_header_rejected(self):
        client = TestClient(_make_app())
        resp = client.get("/protected", headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert resp.status_code == 401

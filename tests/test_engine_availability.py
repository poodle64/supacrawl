"""#144 — per-engine availability reported WITHOUT launching a browser.

``supacrawl_diagnose`` reports, per stealth tier (playwright / patchright /
camoufox), whether the engine is usable and why not — cheaply and safely, with
no browser process started. The launch-truth backstop that an "available"
verdict is honest (not a confident liar, the supacrawl#158 class) lives in
``test_engine_smoke.py`` (#145), which actually launches each engine.
"""

from __future__ import annotations

from typing import Any

import pytest

from supacrawl.services import browser as browser_mod
from supacrawl.services.browser import (
    ENGINE_REASON_BROWSER_NOT_INSTALLED,
    ENGINE_REASON_NOT_INSTALLED,
    BrowserManager,
    all_engine_availability,
    engine_availability,
)


class TestEngineAvailability:
    def test_every_stealth_tier_has_a_verdict(self) -> None:
        report = all_engine_availability()
        assert set(report) == {"playwright", "patchright", "camoufox"}
        for engine, verdict in report.items():
            assert set(verdict) >= {"installed", "available", "reason"}, engine
            assert isinstance(verdict["available"], bool)

    def test_a_missing_package_is_reported_not_installed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Mask camoufox's package as absent without touching the others.
        real = browser_mod._package_installed
        monkeypatch.setattr(
            browser_mod,
            "_package_installed",
            lambda pkg: False if pkg == "camoufox" else real(pkg),
        )
        verdict = engine_availability("camoufox")
        assert verdict["installed"] is False
        assert verdict["available"] is False
        assert verdict["reason"] == ENGINE_REASON_NOT_INSTALLED
        assert "install" in verdict  # actionable hint present

    def test_package_present_but_binary_missing_is_reported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(browser_mod, "_package_installed", lambda pkg: True)
        monkeypatch.setattr(browser_mod, "_chromium_browser_installed", lambda: False)
        verdict = engine_availability("patchright")
        assert verdict["installed"] is True
        assert verdict["available"] is False
        assert verdict["reason"] == ENGINE_REASON_BROWSER_NOT_INSTALLED

    def test_a_fully_present_engine_is_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(browser_mod, "_package_installed", lambda pkg: True)
        monkeypatch.setattr(browser_mod, "_chromium_browser_installed", lambda: True)
        monkeypatch.setattr(browser_mod, "_camoufox_browser_installed", lambda: True)
        for engine in ("playwright", "patchright", "camoufox"):
            verdict = engine_availability(engine)
            assert verdict == {"installed": True, "available": True, "reason": None}, engine

    def test_availability_never_launches_a_browser(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The observable proof for #144: computing availability starts no engine."""

        def _boom(*_a: Any, **_k: Any) -> None:
            raise AssertionError("availability check must not launch/start a browser")

        # Poison every launch/start seam.
        monkeypatch.setattr(BrowserManager, "start", _boom)
        monkeypatch.setattr(BrowserManager, "_start_playwright", _boom)
        monkeypatch.setattr(BrowserManager, "_start_camoufox", _boom)

        report = all_engine_availability()  # must not raise
        assert set(report) == {"playwright", "patchright", "camoufox"}


class TestDiagnoseEngines:
    @pytest.mark.asyncio
    async def test_diagnose_reports_engines_without_launching(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from supacrawl.services import diagnose as diagnose_mod

        # Stub the network probe so the test is offline and deterministic.
        async def _fake_request(client: Any, method: str, url: str) -> Any:
            raise RuntimeError("network disabled in test")

        monkeypatch.setattr(diagnose_mod, "guarded_request", _fake_request)

        def _boom(*_a: Any, **_k: Any) -> None:
            raise AssertionError("diagnose must not launch a browser")

        monkeypatch.setattr(BrowserManager, "start", _boom)
        monkeypatch.setattr(BrowserManager, "_start_playwright", _boom)
        monkeypatch.setattr(BrowserManager, "_start_camoufox", _boom)

        result = await diagnose_mod.supacrawl_diagnose(api_client=None, url="https://example.com")  # type: ignore[arg-type]

        engines = result["diagnosis"]["engines"]
        assert set(engines) == {"playwright", "patchright", "camoufox"}
        for verdict in engines.values():
            assert set(verdict) >= {"installed", "available", "reason"}

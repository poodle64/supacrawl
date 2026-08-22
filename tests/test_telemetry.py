"""Tests for the field telemetry sink (#137).

Deterministic: a temp metrics dir, no network. They lock the versioned event
schema, the privacy default (domain-only), the full-URL opt-in, the reader's
aggregation, prune, and the "disabled sink == no file" guarantee.
"""

from __future__ import annotations

import json
import types
from datetime import datetime, timedelta, timezone

import pytest

from supacrawl.models import QualityAssessment, QualityVerdict, ScrapeData, ScrapeMetadata, ScrapeResult
from supacrawl.remote_sink import LokiSink
from supacrawl.telemetry import SCHEMA_VERSION, MetricsReader, MetricsSink

pytestmark = pytest.mark.unit


def _scrape_result(
    verdict: QualityVerdict = QualityVerdict.OK, score: int = 85, *, success: bool = True
) -> ScrapeResult:
    return ScrapeResult(
        success=success,
        data=ScrapeData(
            markdown="x " * score, metadata=ScrapeMetadata(source_url="https://x", word_count=score, status_code=200)
        ),
        quality=QualityAssessment(verdict=verdict, score=score, attempts=2, escalated=True),
    )


def test_scrape_event_has_versioned_schema_and_domain_only(tmp_path) -> None:
    sink = MetricsSink(metrics_dir=tmp_path)
    sink.record_scrape(url="https://www.qantas.com/au/en/flight", result=_scrape_result(), latency_ms=1234)

    lines = (tmp_path / "events.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["schema"] == SCHEMA_VERSION
    assert event["kind"] == "scrape"
    assert event["domain"] == "qantas.com"  # www stripped, path dropped
    assert "url" not in event  # full URL not logged by default
    assert event["verdict"] == "ok"
    assert event["score"] == 85
    assert event["attempts"] == 2
    assert event["escalated"] is True
    assert event["latency_ms"] == 1234
    assert "ts" in event


def test_full_url_opt_in_logs_url(tmp_path) -> None:
    sink = MetricsSink(metrics_dir=tmp_path, full_url=True)
    sink.record_scrape(url="https://x.example/secret/path", result=_scrape_result(), latency_ms=10)
    event = json.loads((tmp_path / "events.jsonl").read_text().strip())
    assert event["url"] == "https://x.example/secret/path"


def test_search_event_hashes_query_by_default(tmp_path) -> None:
    sink = MetricsSink(metrics_dir=tmp_path)
    sink.record_search(
        query="my private trading query", provider="serper", result_count=5, success=True, latency_ms=800
    )
    event = json.loads((tmp_path / "events.jsonl").read_text().strip())
    assert event["kind"] == "search"
    assert event["provider"] == "serper"
    assert event["result_count"] == 5
    assert "query" not in event  # text not stored by default
    assert event["query_hash"] and len(event["query_hash"]) == 12


def test_disabled_sink_writes_nothing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SUPACRAWL_METRICS", "0")
    monkeypatch.setenv("SUPACRAWL_METRICS_DIR", str(tmp_path))
    assert MetricsSink.default() is None
    assert not (tmp_path / "events.jsonl").exists()


def test_default_enabled_with_full_url_env(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SUPACRAWL_METRICS", raising=False)
    monkeypatch.setenv("SUPACRAWL_METRICS_DIR", str(tmp_path))
    monkeypatch.setenv("SUPACRAWL_METRICS_FULL_URL", "1")
    sink = MetricsSink.default()
    assert sink is not None and sink._full_url is True


def test_reader_aggregates(tmp_path) -> None:
    sink = MetricsSink(metrics_dir=tmp_path)
    sink.record_scrape(url="https://a.example", result=_scrape_result(QualityVerdict.OK, 90), latency_ms=10)
    sink.record_scrape(url="https://a.example", result=_scrape_result(QualityVerdict.OK, 80), latency_ms=10)
    sink.record_scrape(
        url="https://b.example", result=_scrape_result(QualityVerdict.BOT_CHALLENGE, 10, success=False), latency_ms=10
    )
    sink.record_search(query="q", provider="brave", result_count=3, success=True, latency_ms=5)

    summary = MetricsReader(metrics_dir=tmp_path).summary()
    assert summary["scrapes"] == 3
    assert summary["searches"] == 1
    assert summary["success_rate"] == round(2 / 3, 3)
    assert summary["escalation_rate"] == 1.0  # all three are escalated in the fixture
    assert summary["by_verdict"] == {"ok": 2, "bot_challenge": 1}
    assert summary["top_domains"]["a.example"] == 2


def test_reader_since_filter(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    old = {
        "schema": 1,
        "kind": "scrape",
        "ts": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
        "domain": "old.example",
        "verdict": "ok",
        "success": True,
    }
    new = {
        "schema": 1,
        "kind": "scrape",
        "ts": datetime.now(timezone.utc).isoformat(),
        "domain": "new.example",
        "verdict": "ok",
        "success": True,
    }
    path.write_text(json.dumps(old) + "\n" + json.dumps(new) + "\n")
    recent = list(MetricsReader(metrics_dir=tmp_path).events(since=datetime.now(timezone.utc) - timedelta(days=1)))
    assert [e["domain"] for e in recent] == ["new.example"]


def test_prune_bounds_the_log(tmp_path) -> None:
    sink = MetricsSink(metrics_dir=tmp_path)
    for _ in range(10):
        sink.record_scrape(url="https://x.example", result=_scrape_result(), latency_ms=1)
    removed = MetricsReader(metrics_dir=tmp_path).prune(keep_last=3)
    assert removed == 7
    assert len(list(MetricsReader(metrics_dir=tmp_path).events())) == 3


def test_corrupt_line_is_skipped_not_fatal(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(
        '{"schema":1,"kind":"scrape","ts":"'
        + datetime.now(timezone.utc).isoformat()
        + '","domain":"ok.example","verdict":"ok","success":true}\n{not valid json}\n'
    )
    events = list(MetricsReader(metrics_dir=tmp_path).events())
    assert len(events) == 1 and events[0]["domain"] == "ok.example"


def test_reader_missing_file_is_empty(tmp_path) -> None:
    reader = MetricsReader(metrics_dir=tmp_path / "nope")
    assert list(reader.events()) == []
    assert reader.summary()["scrapes"] == 0
    assert reader.prune(keep_last=1) == 0


class TestDefaultTokenResolution:
    """`MetricsSink.default` resolves the Loki bearer one way per mode (#184).

    Driven against the live broker on 2026-08-22: a declined vend used to build
    a `LokiSink` carrying no `Authorization` header, which 401s on every batch
    and whose failure warning names `SUPACRAWL_METRICS_TOKEN` — the env var the
    broker replaced. "Remote telemetry is disabled" has to mean no sink.
    """

    @staticmethod
    def _config(monkeypatch, tmp_path, **overrides):
        from supacrawl import telemetry

        fields = {
            "metrics": True,
            "metrics_full_url": False,
            "metrics_remote_url": "https://loki.example/loki/api/v1/push",
            "metrics_remote_username": None,
            "metrics_remote_tenant": None,
            "metrics_job": "supacrawl",
        }
        fields.update(overrides)
        cfg = types.SimpleNamespace(**fields)
        monkeypatch.setattr(telemetry, "load_config", lambda: cfg, raising=False)
        monkeypatch.setattr("supacrawl.config.load_config", lambda: cfg)
        monkeypatch.setenv("SUPACRAWL_METRICS_DIR", str(tmp_path))
        return cfg

    def test_broker_path_declined_builds_no_remote_sink(self, monkeypatch, tmp_path) -> None:
        """The env token must not resurface — not as a bearer, not as a bare sink."""
        self._config(monkeypatch, tmp_path)
        monkeypatch.setenv("SUPACRAWL_METRICS_TOKEN", "stale-env-token")
        monkeypatch.delenv("SUPACRAWL_METRICS_PASSWORD", raising=False)

        sink = MetricsSink.default(metrics_token=None, metrics_token_vended=True)

        assert sink is not None, "the local event log must survive a broker gap"
        assert sink._remote is None

    def test_broker_path_vended_builds_a_remote_sink(self, monkeypatch, tmp_path) -> None:
        self._config(monkeypatch, tmp_path)
        monkeypatch.delenv("SUPACRAWL_METRICS_TOKEN", raising=False)

        sink = MetricsSink.default(metrics_token="vended", metrics_token_vended=True)

        remote = sink._remote if sink is not None else None
        assert isinstance(remote, LokiSink)
        assert "Authorization" in remote._build_headers()

    def test_env_path_is_unaffected(self, monkeypatch, tmp_path) -> None:
        """No vend requested (CLI/REST): the env var resolves exactly as before."""
        self._config(monkeypatch, tmp_path)
        monkeypatch.setenv("SUPACRAWL_METRICS_TOKEN", "env-token")

        sink = MetricsSink.default(metrics_token=None, metrics_token_vended=False)

        remote = sink._remote if sink is not None else None
        assert isinstance(remote, LokiSink)
        assert "Authorization" in remote._build_headers()

    def test_basic_auth_survives_a_declined_vend(self, monkeypatch, tmp_path) -> None:
        """Basic auth is a separate credential the broker never gated."""
        self._config(monkeypatch, tmp_path, metrics_remote_username="12345")
        monkeypatch.setenv("SUPACRAWL_METRICS_PASSWORD", "basic-pw")
        monkeypatch.delenv("SUPACRAWL_METRICS_TOKEN", raising=False)

        sink = MetricsSink.default(metrics_token=None, metrics_token_vended=True)

        remote = sink._remote if sink is not None else None
        assert isinstance(remote, LokiSink)
        assert remote._build_headers()["Authorization"].startswith("Basic ")

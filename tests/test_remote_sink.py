"""Tests for remote telemetry shipping: Loki payload shape, auth, fail-open
behaviour, and the MetricsSink buffer/flush wiring.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from supacrawl.remote_sink import LokiSink, build_remote_sink
from supacrawl.telemetry import MetricsSink


class _FakeRemote:
    """Captures pushed batches so MetricsSink wiring can be asserted."""

    def __init__(self) -> None:
        self.batches: list[list[dict]] = []

    def push(self, events: list[dict]) -> None:
        self.batches.append(list(events))


# ---------------------------------------------------------------------------
# build_remote_sink
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_remote_sink_none_when_no_url() -> None:
    assert build_remote_sink(None) is None
    assert build_remote_sink("") is None


@pytest.mark.unit
def test_build_remote_sink_returns_loki_sink() -> None:
    sink = build_remote_sink("https://host/loki/api/v1/push", token="tok")
    assert isinstance(sink, LokiSink)


# ---------------------------------------------------------------------------
# LokiSink payload shape — the canonical Loki modelling rules
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_loki_push_groups_by_kind_with_low_cardinality_labels() -> None:
    events = [
        {"kind": "scrape", "ts": "2026-06-20T07:00:00+00:00", "domain": "a.com", "verdict": "ok", "score": 90},
        {"kind": "scrape", "ts": "2026-06-20T07:00:01+00:00", "domain": "b.com", "verdict": "thin", "score": 40},
        {"kind": "search", "ts": "2026-06-20T07:00:02+00:00", "provider": "brave", "result_count": 5},
    ]
    with patch("supacrawl.remote_sink.httpx.post") as post:
        post.return_value = MagicMock(status_code=204)
        LokiSink("https://host/loki/api/v1/push").push(events)

    payload = post.call_args.kwargs["json"]
    streams = {s["stream"]["kind"]: s for s in payload["streams"]}
    # One stream per kind; labels are ONLY job + kind (low cardinality).
    assert set(streams) == {"scrape", "search"}
    for s in payload["streams"]:
        assert set(s["stream"]) == {"job", "kind"}
        assert s["stream"]["job"] == "supacrawl"
    # High-cardinality fields ride in the log line, never as labels.
    scrape_lines = "".join(v[1] for v in streams["scrape"]["values"])
    assert "domain" in scrape_lines and "verdict" in scrape_lines
    # Values are [ns_timestamp_string, line] and sorted by timestamp.
    ts = [v[0] for v in streams["scrape"]["values"]]
    assert ts == sorted(ts)
    assert all(t.isdigit() for t in ts)


@pytest.mark.unit
def test_loki_push_sets_bearer_header_when_token_present() -> None:
    with patch("supacrawl.remote_sink.httpx.post") as post:
        post.return_value = MagicMock(status_code=204)
        LokiSink("https://host/loki/api/v1/push", token="s3cret").push(
            [{"kind": "scrape", "ts": "2026-06-20T07:00:00+00:00"}]
        )
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer s3cret"


@pytest.mark.unit
def test_loki_push_no_auth_header_without_token() -> None:
    with patch("supacrawl.remote_sink.httpx.post") as post:
        post.return_value = MagicMock(status_code=204)
        LokiSink("https://host/loki/api/v1/push").push([{"kind": "scrape", "ts": "2026-06-20T07:00:00+00:00"}])
    assert "Authorization" not in post.call_args.kwargs["headers"]


@pytest.mark.unit
def test_loki_push_empty_is_noop() -> None:
    with patch("supacrawl.remote_sink.httpx.post") as post:
        LokiSink("https://host/loki/api/v1/push").push([])
    post.assert_not_called()


@pytest.mark.unit
def test_loki_push_fails_open_on_network_error() -> None:
    with patch("supacrawl.remote_sink.httpx.post", side_effect=OSError("connection refused")):
        # Must not raise — telemetry can never break a scrape.
        LokiSink("https://host/loki/api/v1/push").push([{"kind": "scrape", "ts": "2026-06-20T07:00:00+00:00"}])


@pytest.mark.unit
def test_loki_push_fails_open_on_4xx() -> None:
    with patch("supacrawl.remote_sink.httpx.post") as post:
        post.return_value = MagicMock(status_code=400, text="bad request")
        LokiSink("https://host/loki/api/v1/push").push(
            [{"kind": "scrape", "ts": "2026-06-20T07:00:00+00:00"}]
        )  # no raise


# ---------------------------------------------------------------------------
# MetricsSink buffer / flush wiring
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_metricssink_writes_jsonl_and_buffers_for_remote(tmp_path: Path) -> None:
    remote = _FakeRemote()
    sink = MetricsSink(metrics_dir=tmp_path, remote=remote)
    sink.record_search(query="q", provider="brave", result_count=3, success=True, latency_ms=10)

    # Local JSONL is written immediately (durable record).
    assert sink.path.exists()
    assert sink.path.read_text().strip()
    # Nothing shipped yet (below threshold); a flush ships the buffer and clears it.
    assert remote.batches == []
    sink.flush()
    assert len(remote.batches) == 1 and len(remote.batches[0]) == 1
    assert sink._buffer == []


@pytest.mark.unit
def test_metricssink_flushes_at_threshold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("supacrawl.telemetry._REMOTE_FLUSH_THRESHOLD", 3)
    remote = _FakeRemote()
    sink = MetricsSink(metrics_dir=tmp_path, remote=remote)
    for _ in range(3):
        sink.record_search(query="q", provider="brave", result_count=1, success=True, latency_ms=1)
    assert len(remote.batches) == 1 and len(remote.batches[0]) == 3
    assert sink._buffer == []


@pytest.mark.unit
def test_metricssink_no_buffer_without_remote(tmp_path: Path) -> None:
    sink = MetricsSink(metrics_dir=tmp_path)
    sink.record_search(query="q", provider="brave", result_count=1, success=True, latency_ms=1)
    assert sink._buffer == []
    sink.flush()  # no-op, no remote


@pytest.mark.unit
def test_default_builds_remote_sink_from_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPACRAWL_METRICS", "1")
    monkeypatch.setenv("SUPACRAWL_METRICS_DIR", str(tmp_path))
    monkeypatch.setenv("SUPACRAWL_METRICS_REMOTE_URL", "https://host/loki/api/v1/push")
    monkeypatch.setenv("SUPACRAWL_METRICS_TOKEN", "tok")
    monkeypatch.setenv("SUPACRAWL_CONFIG_PATH", str(tmp_path / "none.toml"))
    sink = MetricsSink.default()
    assert sink is not None
    assert isinstance(sink._remote, LokiSink)

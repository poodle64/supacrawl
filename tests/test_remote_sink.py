"""Tests for remote telemetry shipping: Loki payload shape, auth, fail-open
behaviour, check() probing, and the MetricsSink buffer/flush wiring.
"""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from supacrawl.remote_sink import (
    LokiSink,
    RemoteProbeResult,
    _safe_endpoint,
    build_remote_sink,
    strip_url_credentials,
)
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


# ---------------------------------------------------------------------------
# Auth header precedence
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_basic_auth_header_correct_encoding() -> None:
    """Basic auth header must be correctly base64-encoded 'user:pass'."""
    with patch("supacrawl.remote_sink.httpx.post") as post:
        post.return_value = MagicMock(status_code=204)
        LokiSink("https://host/loki/api/v1/push", username="myuser", password="mypass").push(
            [{"kind": "scrape", "ts": "2026-06-20T07:00:00+00:00"}]
        )
    auth = post.call_args.kwargs["headers"]["Authorization"]
    assert auth.startswith("Basic ")
    decoded = base64.b64decode(auth[len("Basic ") :]).decode()
    assert decoded == "myuser:mypass"


@pytest.mark.unit
def test_basic_auth_beats_bearer_when_both_set() -> None:
    """When username+password AND token are set, basic auth takes precedence."""
    with patch("supacrawl.remote_sink.httpx.post") as post:
        post.return_value = MagicMock(status_code=204)
        LokiSink(
            "https://host/loki/api/v1/push",
            username="user",
            password="pass",
            token="bearer-tok",
        ).push([{"kind": "scrape", "ts": "2026-06-20T07:00:00+00:00"}])
    auth = post.call_args.kwargs["headers"]["Authorization"]
    assert auth.startswith("Basic ")


@pytest.mark.unit
def test_no_auth_header_when_neither_set() -> None:
    """No Authorization header when neither token nor username+password are set."""
    with patch("supacrawl.remote_sink.httpx.post") as post:
        post.return_value = MagicMock(status_code=204)
        LokiSink("https://host/loki/api/v1/push").push([{"kind": "scrape", "ts": "2026-06-20T07:00:00+00:00"}])
    assert "Authorization" not in post.call_args.kwargs["headers"]


@pytest.mark.unit
def test_tenant_header_added_independently_of_auth() -> None:
    """X-Scope-OrgID is set regardless of which auth scheme (or none) is used."""
    with patch("supacrawl.remote_sink.httpx.post") as post:
        post.return_value = MagicMock(status_code=204)
        LokiSink("https://host/loki/api/v1/push", token="tok", tenant="my-org").push(
            [{"kind": "scrape", "ts": "2026-06-20T07:00:00+00:00"}]
        )
    headers = post.call_args.kwargs["headers"]
    assert headers["X-Scope-OrgID"] == "my-org"
    assert headers["Authorization"] == "Bearer tok"


@pytest.mark.unit
def test_tenant_header_without_auth() -> None:
    """X-Scope-OrgID is added even when no auth is configured."""
    with patch("supacrawl.remote_sink.httpx.post") as post:
        post.return_value = MagicMock(status_code=204)
        LokiSink("https://host/loki/api/v1/push", tenant="ops").push(
            [{"kind": "scrape", "ts": "2026-06-20T07:00:00+00:00"}]
        )
    headers = post.call_args.kwargs["headers"]
    assert headers["X-Scope-OrgID"] == "ops"
    assert "Authorization" not in headers


# ---------------------------------------------------------------------------
# check() connectivity probe
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_check_ok_on_2xx() -> None:
    """check() returns ok=True and the status code on a 204 response."""
    with patch("supacrawl.remote_sink.httpx.post") as post:
        post.return_value = MagicMock(status_code=204)
        result = LokiSink("https://host/loki/api/v1/push").check()
    assert isinstance(result, RemoteProbeResult)
    assert result.ok is True
    assert result.status == 204
    assert result.detail == "ok"
    assert result.endpoint == "https://host"


@pytest.mark.unit
def test_check_not_ok_on_401() -> None:
    """check() returns ok=False with an auth hint on 401."""
    with patch("supacrawl.remote_sink.httpx.post") as post:
        post.return_value = MagicMock(status_code=401)
        result = LokiSink("https://host/loki/api/v1/push", token="bad").check()
    assert result.ok is False
    assert result.status == 401
    assert "authentication" in result.detail


@pytest.mark.unit
def test_check_not_ok_on_connection_error() -> None:
    """check() returns ok=False with a summary when the connection fails."""
    with patch("supacrawl.remote_sink.httpx.post", side_effect=OSError("connection refused")):
        result = LokiSink("https://host/loki/api/v1/push").check()
    assert result.ok is False
    assert result.status is None
    assert "connection refused" in result.detail


@pytest.mark.unit
def test_check_endpoint_never_leaks_credentials() -> None:
    """check() endpoint field must not contain path, token, or password."""
    with patch("supacrawl.remote_sink.httpx.post") as post:
        post.return_value = MagicMock(status_code=204)
        result = LokiSink(
            "https://host/loki/api/v1/push",
            username="user",
            password="s3cr3t",
        ).check()
    assert "s3cr3t" not in result.endpoint
    assert "user" not in result.endpoint
    assert "loki/api" not in result.endpoint
    assert result.endpoint == "https://host"


# ---------------------------------------------------------------------------
# _build_payload — parity with pre-refactor push() body
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_payload_groups_by_kind() -> None:
    """_build_payload must produce the same group-by-kind structure as push()."""
    events = [
        {"kind": "scrape", "ts": "2026-06-20T07:00:00+00:00", "domain": "a.com"},
        {"kind": "scrape", "ts": "2026-06-20T07:00:01+00:00", "domain": "b.com"},
        {"kind": "search", "ts": "2026-06-20T07:00:02+00:00", "provider": "brave"},
    ]
    sink = LokiSink("https://host/loki/api/v1/push")
    payload = sink._build_payload(events)
    streams = {s["stream"]["kind"]: s for s in payload["streams"]}
    assert set(streams) == {"scrape", "search"}
    # Labels must be low-cardinality only.
    for s in payload["streams"]:
        assert set(s["stream"]) == {"job", "kind"}
    # Values are sorted by nanosecond timestamp within each stream.
    ts = [v[0] for v in streams["scrape"]["values"]]
    assert ts == sorted(ts)


@pytest.mark.unit
def test_build_payload_parity_with_push() -> None:
    """push() must produce the identical payload body as _build_payload()."""
    events = [
        {"kind": "scrape", "ts": "2026-06-20T08:00:00+00:00", "domain": "x.com"},
        {"kind": "search", "ts": "2026-06-20T08:00:01+00:00", "provider": "serper"},
    ]
    sink = LokiSink("https://host/loki/api/v1/push")
    expected = sink._build_payload(events)

    with patch("supacrawl.remote_sink.httpx.post") as post:
        post.return_value = MagicMock(status_code=204)
        sink.push(events)
    assert post.call_args.kwargs["json"] == expected


# ---------------------------------------------------------------------------
# send_checked
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_send_checked_ok_on_204() -> None:
    """send_checked returns ok=True and HTTP 204 on success."""
    with patch("supacrawl.remote_sink.httpx.post") as post:
        post.return_value = MagicMock(status_code=204)
        result = LokiSink("https://host/loki/api/v1/push").send_checked(
            [{"kind": "scrape", "ts": "2026-06-20T07:00:00+00:00"}]
        )
    assert isinstance(result, RemoteProbeResult)
    assert result.ok is True
    assert result.status == 204
    assert result.detail == "ok"
    assert result.endpoint == "https://host"


@pytest.mark.unit
def test_send_checked_not_ok_on_401() -> None:
    """send_checked returns ok=False with the auth hint on 401."""
    with patch("supacrawl.remote_sink.httpx.post") as post:
        post.return_value = MagicMock(status_code=401)
        result = LokiSink("https://host/loki/api/v1/push", token="bad").send_checked(
            [{"kind": "scrape", "ts": "2026-06-20T07:00:00+00:00"}]
        )
    assert result.ok is False
    assert result.status == 401
    assert "authentication" in result.detail


@pytest.mark.unit
def test_send_checked_not_ok_on_404() -> None:
    """send_checked returns ok=False with the URL hint on 404."""
    with patch("supacrawl.remote_sink.httpx.post") as post:
        post.return_value = MagicMock(status_code=404)
        result = LokiSink("https://host/loki/api/v1/push").send_checked(
            [{"kind": "scrape", "ts": "2026-06-20T07:00:00+00:00"}]
        )
    assert result.ok is False
    assert result.status == 404
    assert "not found" in result.detail


@pytest.mark.unit
def test_send_checked_not_ok_on_connection_error() -> None:
    """send_checked returns ok=False/status=None on a connection error — never raises."""
    with patch("supacrawl.remote_sink.httpx.post", side_effect=OSError("connection refused")):
        result = LokiSink("https://host/loki/api/v1/push").send_checked(
            [{"kind": "scrape", "ts": "2026-06-20T07:00:00+00:00"}]
        )
    assert result.ok is False
    assert result.status is None
    assert "connection refused" in result.detail


@pytest.mark.unit
def test_send_checked_never_raises_on_unexpected_exception() -> None:
    """send_checked absorbs any exception and returns a failing result."""
    with patch("supacrawl.remote_sink.httpx.post", side_effect=RuntimeError("boom")):
        result = LokiSink("https://host/loki/api/v1/push").send_checked(
            [{"kind": "scrape", "ts": "2026-06-20T07:00:00+00:00"}]
        )
    assert result.ok is False
    assert result.status is None


@pytest.mark.unit
def test_send_checked_empty_events_is_noop() -> None:
    """send_checked with an empty list returns ok=True without a network call."""
    with patch("supacrawl.remote_sink.httpx.post") as post:
        result = LokiSink("https://host/loki/api/v1/push").send_checked([])
    post.assert_not_called()
    assert result.ok is True
    assert result.status is None
    assert result.detail == "nothing to send"


@pytest.mark.unit
def test_send_checked_endpoint_never_leaks_credentials() -> None:
    """send_checked endpoint field must not contain path, token, or password."""
    with patch("supacrawl.remote_sink.httpx.post") as post:
        post.return_value = MagicMock(status_code=204)
        result = LokiSink(
            "https://host/loki/api/v1/push",
            username="user",
            password="s3cr3t",
        ).send_checked([{"kind": "scrape", "ts": "2026-06-20T07:00:00+00:00"}])
    assert "s3cr3t" not in result.endpoint
    assert "user" not in result.endpoint
    assert "loki/api" not in result.endpoint
    assert result.endpoint == "https://host"


# ---------------------------------------------------------------------------
# replay-remote CLI (CliRunner, no network)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_replay_remote_no_endpoint_configured(tmp_path: Path) -> None:
    """replay-remote exits 0 with a friendly message when no endpoint is set."""
    from click.testing import CliRunner

    from supacrawl.cli._common import app

    runner = CliRunner()
    # load_config and SupacrawlSecrets are lazy-imported inside the command body,
    # so patch at their canonical source module paths.
    with (
        patch("supacrawl.config.load_config") as mock_cfg,
        patch("supacrawl.config.SupacrawlSecrets") as mock_sec,
    ):
        cfg = MagicMock()
        cfg.metrics_remote_url = None
        mock_cfg.return_value = cfg
        mock_sec.from_env.return_value = MagicMock(metrics_token=None, metrics_password=None)
        result = runner.invoke(app, ["metrics", "replay-remote"])

    assert result.exit_code == 0
    assert "No remote telemetry endpoint configured" in result.output


@pytest.mark.unit
def test_replay_remote_no_local_events(tmp_path: Path) -> None:
    """replay-remote exits 0 with a 'no events' message when the log is empty."""
    from click.testing import CliRunner

    from supacrawl.cli._common import app

    runner = CliRunner()
    with (
        patch("supacrawl.config.load_config") as mock_cfg,
        patch("supacrawl.config.SupacrawlSecrets") as mock_sec,
        patch("supacrawl.cli.metrics.MetricsReader") as mock_reader,
        patch("supacrawl.remote_sink.httpx.post") as post,
    ):
        cfg = MagicMock()
        cfg.metrics_remote_url = "https://host/loki/api/v1/push"
        cfg.metrics_remote_username = None
        cfg.metrics_remote_tenant = None
        mock_cfg.return_value = cfg
        mock_sec.from_env.return_value = MagicMock(metrics_token="tok", metrics_password=None)
        mock_reader.return_value.events.return_value = iter([])
        post.return_value = MagicMock(status_code=204)

        result = runner.invoke(app, ["metrics", "replay-remote"])

    assert result.exit_code == 0
    assert "No local events to replay" in result.output


@pytest.mark.unit
def test_replay_remote_dry_run_sends_nothing(tmp_path: Path) -> None:
    """--dry-run reports counts and endpoint without making any HTTP call."""
    from click.testing import CliRunner

    from supacrawl.cli._common import app

    events = [
        {"kind": "scrape", "ts": "2026-06-20T07:00:00+00:00", "domain": "a.com"},
        {"kind": "search", "ts": "2026-06-20T07:00:01+00:00", "provider": "brave"},
        {"kind": "scrape", "ts": "2026-06-20T07:00:02+00:00", "domain": "b.com"},
    ]
    runner = CliRunner()
    with (
        patch("supacrawl.config.load_config") as mock_cfg,
        patch("supacrawl.config.SupacrawlSecrets") as mock_sec,
        patch("supacrawl.cli.metrics.MetricsReader") as mock_reader,
        patch("supacrawl.remote_sink.httpx.post") as post,
    ):
        cfg = MagicMock()
        cfg.metrics_remote_url = "https://host/loki/api/v1/push"
        cfg.metrics_remote_username = None
        cfg.metrics_remote_tenant = None
        mock_cfg.return_value = cfg
        mock_sec.from_env.return_value = MagicMock(metrics_token="tok", metrics_password=None)
        mock_reader.return_value.events.return_value = iter(events)

        result = runner.invoke(app, ["metrics", "replay-remote", "--dry-run"])

    post.assert_not_called()
    assert result.exit_code == 0
    assert "3 events" in result.output
    assert "nothing sent" in result.output


@pytest.mark.unit
def test_replay_remote_success(tmp_path: Path) -> None:
    """replay-remote replays all events and prints the success summary."""
    from click.testing import CliRunner

    from supacrawl.cli._common import app

    events = [
        {"kind": "scrape", "ts": "2026-06-20T07:00:00+00:00", "domain": "a.com"},
        {"kind": "scrape", "ts": "2026-06-20T07:00:01+00:00", "domain": "b.com"},
    ]
    runner = CliRunner()
    with (
        patch("supacrawl.config.load_config") as mock_cfg,
        patch("supacrawl.config.SupacrawlSecrets") as mock_sec,
        patch("supacrawl.cli.metrics.MetricsReader") as mock_reader,
        patch("supacrawl.remote_sink.httpx.post") as post,
    ):
        cfg = MagicMock()
        cfg.metrics_remote_url = "https://host/loki/api/v1/push"
        cfg.metrics_remote_username = None
        cfg.metrics_remote_tenant = None
        mock_cfg.return_value = cfg
        mock_sec.from_env.return_value = MagicMock(metrics_token="tok", metrics_password=None)
        mock_reader.return_value.events.return_value = iter(events)
        post.return_value = MagicMock(status_code=204)

        result = runner.invoke(app, ["metrics", "replay-remote"])

    assert result.exit_code == 0
    assert "✓" in result.output
    assert "2 events" in result.output
    assert "https://host" in result.output


@pytest.mark.unit
def test_replay_remote_failure_exits_1(tmp_path: Path) -> None:
    """replay-remote exits 1 and prints a failure summary when the endpoint rejects."""
    from click.testing import CliRunner

    from supacrawl.cli._common import app

    events = [{"kind": "scrape", "ts": "2026-06-20T07:00:00+00:00", "domain": "a.com"}]
    runner = CliRunner()
    with (
        patch("supacrawl.config.load_config") as mock_cfg,
        patch("supacrawl.config.SupacrawlSecrets") as mock_sec,
        patch("supacrawl.cli.metrics.MetricsReader") as mock_reader,
        patch("supacrawl.remote_sink.httpx.post") as post,
    ):
        cfg = MagicMock()
        cfg.metrics_remote_url = "https://host/loki/api/v1/push"
        cfg.metrics_remote_username = None
        cfg.metrics_remote_tenant = None
        mock_cfg.return_value = cfg
        mock_sec.from_env.return_value = MagicMock(metrics_token="bad", metrics_password=None)
        mock_reader.return_value.events.return_value = iter(events)
        post.return_value = MagicMock(status_code=401, text="Unauthorized")

        result = runner.invoke(app, ["metrics", "replay-remote"])

    assert result.exit_code == 1
    # CliRunner mixes stderr into output by default; the ✗ character is there.
    combined = result.output + (result.stderr if hasattr(result, "stderr") and result.stderr else "")
    assert "✗" in combined


# ---------------------------------------------------------------------------
# Credential safety: endpoints/probe output must never carry secrets
# ---------------------------------------------------------------------------


def test_safe_endpoint_strips_embedded_credentials() -> None:
    """A password embedded in the URL must never survive into the endpoint string."""
    endpoint = _safe_endpoint("https://user:p4ssword@loki.example.com/loki/api/v1/push")
    assert "p4ssword" not in endpoint
    assert endpoint == "https://loki.example.com"


def test_strip_url_credentials_keeps_everything_but_userinfo() -> None:
    out = strip_url_credentials("https://user:p4ssword@loki.example.com:3100/loki/api/v1/push")
    assert "p4ssword" not in out
    assert out == "https://loki.example.com:3100/loki/api/v1/push"


def test_build_headers_warns_on_half_configured_basic_auth(caplog: pytest.LogCaptureFixture) -> None:
    """A username with no password must warn, not silently fall through to bearer."""
    import logging

    sink = LokiSink("https://host/loki/api/v1/push", username="user-only", token="tok")
    with caplog.at_level(logging.WARNING):
        headers = sink._build_headers()
    assert "Basic auth requires both" in caplog.text
    assert headers["Authorization"] == "Bearer tok"  # falls back to bearer


def test_metrics_sink_flushes_on_time_interval(tmp_path: Path) -> None:
    """Buffered events ship once the flush interval elapses, even below the count threshold.

    This is what makes a long-running MCP server's telemetry visible promptly rather
    than only every 25 events.
    """
    import supacrawl.telemetry as telemetry_mod

    remote = _FakeRemote()
    sink = MetricsSink(metrics_dir=tmp_path, remote=remote)
    sink.record_search(query="q", provider="brave", result_count=1, success=True, latency_ms=1)
    assert remote.batches == []  # below threshold and timer just reset → buffered
    # Simulate the flush interval elapsing, then record again → time-based flush fires.
    sink._last_flush -= telemetry_mod._REMOTE_FLUSH_INTERVAL_S + 1
    sink.record_search(query="q", provider="brave", result_count=1, success=True, latency_ms=1)
    assert len(remote.batches) == 1
    assert len(remote.batches[0]) == 2  # both buffered events shipped together


def test_push_surfaces_first_failure_then_stays_quiet(caplog: pytest.LogCaptureFixture) -> None:
    """A silent fail-open drop is now visible: the first failure warns (with a fix hint),
    repeats stay quiet, and recovery logs once."""
    import logging

    sink = LokiSink("https://host/loki/api/v1/push", token="tok")
    events = [{"kind": "scrape", "ts": "2026-06-21T00:00:00+00:00"}]
    with patch.object(sink, "_post") as post, caplog.at_level(logging.INFO):
        post.return_value = MagicMock(status_code=401, text="no auth")
        sink.push(events)
        assert caplog.text.count("is failing") == 1  # first failure is visible
        assert "SUPACRAWL_METRICS_TOKEN" in caplog.text  # points at the fix
        sink.push(events)
        assert caplog.text.count("is failing") == 1  # repeat failure does not spam
        post.return_value = MagicMock(status_code=204, text="")
        sink.push(events)
        assert "recovered" in caplog.text


def test_job_label_defaults_to_supacrawl_and_is_configurable() -> None:
    """The Loki stream `job` label defaults to 'supacrawl' but can be overridden."""
    events = [{"kind": "scrape", "ts": "2026-06-21T00:00:00+00:00"}]
    default_payload = LokiSink("https://h/loki/api/v1/push")._build_payload(events)
    assert default_payload["streams"][0]["stream"]["job"] == "supacrawl"
    custom_payload = LokiSink("https://h/loki/api/v1/push", job="my-scraper")._build_payload(events)
    assert custom_payload["streams"][0]["stream"]["job"] == "my-scraper"

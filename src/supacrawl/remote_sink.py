"""Remote telemetry sinks: ship field-telemetry events to an external log store
so a central dashboard (e.g. Grafana reading Loki) can see them.

supacrawl runs locally and writes ``events.jsonl`` as the durable record; this
layer *also* pushes each event to a configured endpoint when one is set. It is
the "log to wherever you're told" seam — give it a URL (and an optional token)
and it ships. Loki is the first backend; the ``RemoteSink`` protocol leaves room
for OTLP or others without touching the call sites.

Two rules are load-bearing here:

- **Fail-open, always.** A scrape must never hang or fail because the log
  endpoint is slow or down. Every push is best-effort with a short timeout; on
  any error it is dropped, and the local JSONL remains the source of truth.
- **Low-cardinality labels.** Loki streams are keyed by labels; high-cardinality
  values (domain, verdict, score, url) go in the log *line* — queried with
  ``| json`` — never as labels. This is the canonical Loki data-modelling rule;
  domain-as-a-label would explode the index.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx

LOGGER = logging.getLogger(__name__)

# Best-effort ceiling: a telemetry push must never delay a scrape for long.
_PUSH_TIMEOUT_S = 3.0


class RemoteSink(Protocol):
    """A best-effort shipper of telemetry events to an external store."""

    def push(self, events: list[dict[str, Any]]) -> None:
        """Ship a batch of events. Implementations must never raise (fail-open)."""
        ...


def _event_ns(event: dict[str, Any]) -> str:
    """Unix-nanosecond timestamp string (Loki's value format) from the event ts."""
    ts = event.get("ts")
    try:
        dt = datetime.fromisoformat(ts) if ts else datetime.now(timezone.utc)
    except TypeError, ValueError:
        dt = datetime.now(timezone.utc)
    return str(int(dt.timestamp() * 1_000_000_000))


class LokiSink:
    """Push events to a Grafana Loki ``/loki/api/v1/push`` endpoint.

    Events are grouped into one stream per ``kind`` (scrape/search) under the
    low-cardinality labels ``{job="supacrawl", kind="..."}``; every other field
    (domain, verdict, score, latency, ...) travels in the JSON log line for
    LogQL ``| json`` queries. Authentication, when configured, is a bearer token.
    """

    def __init__(self, url: str, *, token: str | None = None, timeout: float = _PUSH_TIMEOUT_S) -> None:
        """Initialise the sink.

        Args:
            url: Full Loki push URL (e.g. ``https://host/loki/api/v1/push``).
            token: Optional bearer token sent as ``Authorization: Bearer <token>``.
            timeout: Per-push timeout in seconds.
        """
        self._url = url
        self._token = token
        self._timeout = timeout

    def push(self, events: list[dict[str, Any]]) -> None:
        """Ship a batch to Loki, grouped into one stream per ``kind``. Fail-open.

        Args:
            events: Telemetry event dicts (as written to the local JSONL).
        """
        if not events:
            return
        streams: dict[str, list[list[str]]] = {}
        for event in events:
            kind = str(event.get("kind", "event"))
            line = json.dumps(event, separators=(",", ":"))
            streams.setdefault(kind, []).append([_event_ns(event), line])
        payload = {
            "streams": [
                {"stream": {"job": "supacrawl", "kind": kind}, "values": sorted(values, key=lambda v: v[0])}
                for kind, values in streams.items()
            ]
        }
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            resp = httpx.post(self._url, json=payload, headers=headers, timeout=self._timeout)
            if resp.status_code >= 400:
                # Loki's error body is safe to log (it does not echo the token).
                LOGGER.debug("Loki push rejected (%s): %s", resp.status_code, resp.text[:200])
        except Exception as exc:  # noqa: BLE001 — fail-open: telemetry must never break a scrape
            LOGGER.debug("Loki push failed: %s", exc)


def build_remote_sink(url: str | None, *, token: str | None = None) -> RemoteSink | None:
    """Construct the configured remote sink, or ``None`` when no URL is set.

    Currently only Loki's push API is supported; ``url`` points straight at it
    (e.g. ``https://loki-push.example/loki/api/v1/push``). The return type is the
    ``RemoteSink`` protocol so an OTLP (or other) backend can be added later
    without changing callers.

    Args:
        url: Configured remote endpoint, or ``None``/empty to disable.
        token: Optional bearer token for the endpoint.

    Returns:
        A ``RemoteSink`` when a URL is configured, else ``None``.
    """
    if not url:
        return None
    return LokiSink(url, token=token)

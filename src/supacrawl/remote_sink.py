"""Remote telemetry sinks: ship field-telemetry events to an external log store
so a central dashboard (e.g. Grafana reading Loki) can see them.

supacrawl runs locally and writes ``events.jsonl`` as the durable record; this
layer *also* pushes each event to a configured endpoint when one is set. It is
the "log to wherever you're told" seam — give it a URL and credentials and it
ships. Loki is the first backend; the ``RemoteSink`` protocol leaves room for
OTLP or others without touching the call sites.

Auth resolution follows Grafana Alloy's ``loki.write`` / Promtail ``client``
convention so supacrawl can push to any Loki:

- Grafana Cloud: basic auth (numeric user ID + Access Policy token).
- Self-hosted multi-tenant: ``X-Scope-OrgID`` header (with or without auth).
- Self-hosted single-tenant with bearer token: the original path.
- Unauthenticated: no ``Authorization`` header (local / dev Loki).

Three rules are load-bearing here:

- **Fail-open, always.** A scrape must never hang or fail because the log
  endpoint is slow or down. Every push is best-effort with a short timeout; on
  any error it is dropped, and the local JSONL remains the source of truth.
- **Low-cardinality labels.** Loki streams are keyed by labels; high-cardinality
  values (domain, verdict, score, url) go in the log *line* — queried with
  ``| json`` — never as labels. This is the canonical Loki data-modelling rule;
  domain-as-a-label would explode the index.
- **No credentials in logs or endpoints.** The ``check()`` result's ``endpoint``
  field carries only scheme + host; tokens and passwords never appear in any
  log line or returned value.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

LOGGER = logging.getLogger(__name__)

# Best-effort ceiling: a telemetry push must never delay a scrape for long.
_PUSH_TIMEOUT_S = 3.0

# Hint strings surfaced by check() for common failure codes.
_STATUS_HINTS: dict[int, str] = {
    401: "authentication rejected — check token/password",
    403: "authentication rejected — check token/password",
    404: "not found — check the URL ends in /loki/api/v1/push",
}


class RemoteSink(Protocol):
    """A best-effort shipper of telemetry events to an external store."""

    def push(self, events: list[dict[str, Any]]) -> None:
        """Ship a batch of events. Implementations must never raise (fail-open)."""
        ...


@dataclass(frozen=True)
class RemoteProbeResult:
    """Outcome of a connectivity probe sent by ``LokiSink.check()``.

    Attributes:
        ok: True when the endpoint accepted the probe (2xx response).
        status: HTTP status code returned, or ``None`` on a connection error.
        detail: Human-readable outcome: "ok" on success, or a hint describing
            the failure (e.g. "authentication rejected — check token/password").
        endpoint: Scheme and host of the probed URL only — never includes
            credentials, auth tokens, or query parameters.
    """

    ok: bool
    status: int | None
    detail: str
    endpoint: str


def _event_ns(event: dict[str, Any]) -> str:
    """Unix-nanosecond timestamp string (Loki's value format) from the event ts."""
    ts = event.get("ts")
    try:
        dt = datetime.fromisoformat(ts) if ts else datetime.now(timezone.utc)
    except TypeError, ValueError:
        dt = datetime.now(timezone.utc)
    return str(int(dt.timestamp() * 1_000_000_000))


def strip_url_credentials(url: str) -> str:
    """Strip userinfo (``user:pass@``) from a URL, preserving everything else.

    The result is safe to display in a GUI or API response: the scheme, host,
    port, path, and query are all kept; only the embedded credentials are removed.

    Args:
        url: A URL that may contain embedded basic-auth credentials.

    Returns:
        The URL with any ``user:pass@`` or ``user@`` prefix removed from the
        authority component.
    """
    parsed = urlparse(url)
    # urlparse stores credentials in netloc as "user:pass@host[:port]".
    # Replace the netloc with one that has no userinfo.
    host_port = parsed.hostname or ""
    if parsed.port:
        host_port = f"{host_port}:{parsed.port}"
    clean = parsed._replace(netloc=host_port)
    return clean.geturl()


def _safe_endpoint(url: str) -> str:
    """Return scheme + host only, stripping path, credentials, and query.

    Used so failure messages and ``RemoteProbeResult.endpoint`` never leak
    tokens or passwords that may be embedded in a URL.  When ``urlparse``
    cannot extract a hostname (scheme-less or malformed URL), credentials are
    still stripped via ``strip_url_credentials`` before the raw input is returned.
    """
    parsed = urlparse(url)
    if parsed.hostname:
        return f"{parsed.scheme}://{parsed.hostname}"
    # Fallback for scheme-less / malformed URLs: strip any embedded credentials
    # so the raw input is never returned with user:pass@ intact.
    return strip_url_credentials(url)


class LokiSink:
    """Push events to a Grafana Loki ``/loki/api/v1/push`` endpoint.

    Events are grouped into one stream per ``kind`` (scrape/search) under the
    low-cardinality labels ``{job="supacrawl", kind="..."}``; every other field
    (domain, verdict, score, latency, ...) travels in the JSON log line for
    LogQL ``| json`` queries.

    Auth precedence (mirrors Grafana Alloy / Promtail):

    1. Basic auth when *both* ``username`` and ``password`` are supplied.
    2. Bearer token when only ``token`` is supplied.
    3. No ``Authorization`` header otherwise.

    ``tenant``, when set, adds ``X-Scope-OrgID`` for self-hosted multi-tenant
    Loki. This is independent of the auth scheme.
    """

    def __init__(
        self,
        url: str,
        *,
        token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        tenant: str | None = None,
        timeout: float = _PUSH_TIMEOUT_S,
    ) -> None:
        """Initialise the sink.

        Args:
            url: Full Loki push URL (e.g. ``https://host/loki/api/v1/push``).
            token: Bearer token sent as ``Authorization: Bearer <token>``.
                Ignored when ``username`` and ``password`` are both set.
            username: HTTP basic-auth username. For Grafana Cloud this is the
                numeric Loki/Logs user (instance) ID.
            password: HTTP basic-auth password. For Grafana Cloud this is the
                Access Policy API token.
            tenant: Value for the ``X-Scope-OrgID`` header used by self-hosted
                multi-tenant Loki. Leave ``None`` for single-tenant or Grafana
                Cloud deployments.
            timeout: Per-push timeout in seconds.
        """
        self._url = url
        self._token = token
        self._username = username
        self._password = password
        self._tenant = tenant
        self._timeout = timeout
        self._endpoint = _safe_endpoint(url)
        self._healthy = True

    @property
    def endpoint(self) -> str:
        """Scheme and host of the configured endpoint; never carries credentials."""
        return self._endpoint

    def _build_headers(self) -> dict[str, str]:
        """Compute request headers once per push/check call.

        Basic auth takes precedence over bearer when both are configured.
        ``X-Scope-OrgID`` is always added when a tenant is set.
        """
        headers: dict[str, str] = {"Content-Type": "application/json"}
        # Warn when exactly one of username/password is set — basic auth needs both.
        if bool(self._username) != bool(self._password):
            missing = "password" if self._username else "username"
            LOGGER.warning(
                "Basic auth requires both username and password; %s is missing. Falling back to %s.",
                missing,
                "bearer token" if self._token else "unauthenticated",
            )
        if self._username and self._password:
            encoded = base64.b64encode(f"{self._username}:{self._password}".encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
        elif self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if self._tenant:
            headers["X-Scope-OrgID"] = self._tenant
        return headers

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        """Send one Loki push payload and return the response.

        This is the single HTTP call site; both ``push()`` and ``check()``
        go through here so auth header construction is not duplicated.

        Args:
            payload: The Loki push body (``streams`` array).

        Returns:
            The raw ``httpx.Response``.

        Raises:
            httpx.HTTPError: On any network or transport error (callers decide
                whether to fail-open or propagate).
        """
        return httpx.post(self._url, json=payload, headers=self._build_headers(), timeout=self._timeout)

    def _build_payload(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        """Build the Loki push body from a list of events.

        Groups events into one stream per ``kind`` under low-cardinality labels
        ``{job="supacrawl", kind="..."}``. Values within each stream are sorted
        by nanosecond timestamp so Loki's out-of-order ingestion window is not
        required.

        Args:
            events: Telemetry event dicts (as written to the local JSONL).

        Returns:
            A ``{"streams": [...]}`` dict ready to POST as JSON.
        """
        streams: dict[str, list[list[str]]] = {}
        for event in events:
            kind = str(event.get("kind", "event"))
            line = json.dumps(event, separators=(",", ":"))
            streams.setdefault(kind, []).append([_event_ns(event), line])
        return {
            "streams": [
                {"stream": {"job": "supacrawl", "kind": kind}, "values": sorted(values, key=lambda v: v[0])}
                for kind, values in streams.items()
            ]
        }

    def push(self, events: list[dict[str, Any]]) -> None:
        """Ship a batch to Loki, grouped into one stream per ``kind``. Fail-open.

        Args:
            events: Telemetry event dicts (as written to the local JSONL).
        """
        if not events:
            return
        payload = self._build_payload(events)
        try:
            resp = self._post(payload)
            # Loki's error body is safe to log (it does not echo credentials).
            if resp.status_code >= 400:
                self._note_failure(f"HTTP {resp.status_code}: {resp.text[:120]}")
            else:
                self._note_success()
        except Exception as exc:  # noqa: BLE001 — fail-open: telemetry must never break a scrape
            self._note_failure(str(exc)[:160])

    def _note_failure(self, detail: str) -> None:
        """Surface a push failure once (then stay quiet) so silent drops are visible.

        The fail-open design means a misconfigured endpoint would otherwise drop
        every event without a trace. The first failure — and any later recovery —
        is logged at WARNING/INFO with the endpoint and a pointer to the fix;
        repeated failures stay at DEBUG to avoid log spam. No credential appears here.
        """
        if self._healthy:
            LOGGER.warning(
                "Loki telemetry push to %s is failing (%s). Events are recorded locally but "
                "not shipped — check the URL and SUPACRAWL_METRICS_TOKEN, then run "
                "`supacrawl metrics test-remote`.",
                self._endpoint,
                detail,
            )
        else:
            LOGGER.debug("Loki push still failing (%s): %s", self._endpoint, detail)
        self._healthy = False

    def _note_success(self) -> None:
        """Log recovery once when pushes start succeeding again after a failure."""
        if not self._healthy:
            LOGGER.info("Loki telemetry push to %s recovered.", self._endpoint)
        self._healthy = True

    def send_checked(self, events: list[dict[str, Any]]) -> RemoteProbeResult:
        """POST a batch of events and return a structured result — never raises.

        Unlike ``push()``, this method returns a ``RemoteProbeResult`` the caller
        can inspect to decide whether to continue or abort a replay. It applies the
        same status-to-hint mapping as ``check()``.

        An empty ``events`` list is a no-op: returns ``ok=True`` with
        ``detail="nothing to send"`` without making a network call.

        Args:
            events: Telemetry event dicts to ship.

        Returns:
            A ``RemoteProbeResult`` describing the outcome. ``endpoint`` is
            scheme + host only — never includes credentials or the path.
        """
        if not events:
            return RemoteProbeResult(ok=True, status=None, detail="nothing to send", endpoint=self._endpoint)
        payload = self._build_payload(events)
        try:
            resp = self._post(payload)
        except Exception as exc:  # noqa: BLE001 — must never raise
            return RemoteProbeResult(ok=False, status=None, detail=str(exc)[:200], endpoint=self._endpoint)

        if resp.status_code < 300:
            return RemoteProbeResult(ok=True, status=resp.status_code, detail="ok", endpoint=self._endpoint)

        hint = _STATUS_HINTS.get(resp.status_code)
        if hint is None:
            if resp.status_code >= 500:
                hint = "server/proxy error"
            else:
                hint = f"unexpected status {resp.status_code}"
        return RemoteProbeResult(ok=False, status=resp.status_code, detail=hint, endpoint=self._endpoint)

    def check(self) -> RemoteProbeResult:
        """Probe the endpoint with a synthetic diagnostic event.

        Unlike ``push()``, this method does **not** fail open — it returns a
        structured result the caller can surface to the user. It never raises.

        The probe sends one event with ``kind="diagnostic"`` so it is easy to
        filter out of real dashboards.

        Returns:
            A ``RemoteProbeResult`` describing the outcome. ``endpoint`` is
            scheme + host only — never includes credentials or the path.
        """
        probe_payload = {
            "streams": [
                {
                    "stream": {"job": "supacrawl", "kind": "diagnostic"},
                    "values": [
                        [
                            str(int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)),
                            json.dumps(
                                {
                                    "kind": "diagnostic",
                                    "ts": datetime.now(timezone.utc).isoformat(),
                                    "note": "supacrawl connectivity probe",
                                },
                                separators=(",", ":"),
                            ),
                        ]
                    ],
                }
            ]
        }
        try:
            resp = self._post(probe_payload)
        except Exception as exc:  # noqa: BLE001 — check() must never raise
            return RemoteProbeResult(ok=False, status=None, detail=str(exc)[:200], endpoint=self._endpoint)

        if resp.status_code < 300:
            return RemoteProbeResult(ok=True, status=resp.status_code, detail="ok", endpoint=self._endpoint)

        hint = _STATUS_HINTS.get(resp.status_code)
        if hint is None:
            if resp.status_code >= 500:
                hint = "server/proxy error"
            else:
                hint = f"unexpected status {resp.status_code}"
        return RemoteProbeResult(ok=False, status=resp.status_code, detail=hint, endpoint=self._endpoint)


def build_remote_sink(
    url: str | None,
    *,
    token: str | None = None,
    username: str | None = None,
    password: str | None = None,
    tenant: str | None = None,
) -> RemoteSink | None:
    """Construct the configured remote sink, or ``None`` when no URL is set.

    Currently only Loki's push API is supported; ``url`` points straight at it
    (e.g. ``https://loki.example.com/loki/api/v1/push``). The return type is the
    ``RemoteSink`` protocol so an OTLP (or other) backend can be added later
    without changing callers.

    Auth precedence mirrors ``LokiSink``: basic auth (``username`` + ``password``)
    beats bearer (``token``) when both are supplied.

    Args:
        url: Configured remote endpoint, or ``None``/empty to disable.
        token: Optional bearer token for the endpoint.
        username: Optional HTTP basic-auth username (e.g. Grafana Cloud user ID).
        password: Optional HTTP basic-auth password (e.g. Grafana Cloud API token).
        tenant: Optional ``X-Scope-OrgID`` value for multi-tenant Loki.

    Returns:
        A ``RemoteSink`` when a URL is configured, else ``None``.
    """
    if not url:
        return None
    return LokiSink(url, token=token, username=username, password=password, tenant=tenant)

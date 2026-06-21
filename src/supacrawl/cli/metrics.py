"""Field telemetry commands (#137).

supacrawl records a small event per scrape and search so quality, escalation, and
usage can be tracked over time. These commands inspect and bound that local event
log. The log is the seam a separate dashboard would consume; this is the
terminal-native view of the same data.
"""

import json
import time

import click

from supacrawl.cli._common import app
from supacrawl.telemetry import MetricsReader


@app.group()
def metrics() -> None:
    """Inspect the local field telemetry log.

    supacrawl appends one event per scrape/search to ~/.supacrawl/metrics/events.jsonl
    (on by default for the CLI and MCP server; disable with SUPACRAWL_METRICS=0,
    log full URLs with SUPACRAWL_METRICS_FULL_URL=1). It is local, append-only, and
    the data foundation for a future dashboard.

    Examples:
        supacrawl metrics summary            # headline quality/usage rollup
        supacrawl metrics summary --days 7   # last 7 days only
        supacrawl metrics tail -n 20         # the most recent events
        supacrawl metrics path               # where the log lives
        supacrawl metrics prune --keep-days 90
    """


@metrics.command("path")
def metrics_path() -> None:
    """Print the path to the event log."""
    click.echo(MetricsReader().path)


@metrics.command("summary")
@click.option("--days", type=int, default=None, help="Only summarise events from the last N days.")
def metrics_summary(days: int | None) -> None:
    """Show a headline rollup: scrape/search counts, success and escalation rates,
    verdict mix, and the busiest domains."""
    from datetime import datetime, timedelta, timezone

    since = datetime.now(timezone.utc) - timedelta(days=days) if days else None
    s = MetricsReader().summary(since=since)
    if not s["scrapes"] and not s["searches"]:
        click.echo("No telemetry recorded yet. Scrape or search and supacrawl will start tracking quality over time.")
        return
    window = f" (last {days}d)" if days else ""
    click.echo(f"Field telemetry{window}:")
    click.echo(f"  scrapes:         {s['scrapes']}")
    click.echo(f"  searches:        {s['searches']}")
    if s["success_rate"] is not None:
        click.echo(f"  success rate:    {s['success_rate']:.0%}")
    if s["escalation_rate"] is not None:
        click.echo(f"  escalation rate: {s['escalation_rate']:.0%}")
    if s["by_verdict"]:
        click.echo("  verdicts:        " + ", ".join(f"{k}={v}" for k, v in s["by_verdict"].items()))
    if s["top_domains"]:
        click.echo("  top domains:")
        for domain, count in s["top_domains"].items():
            click.echo(f"    {domain}: {count}")


@metrics.command("tail")
@click.option("-n", "--count", type=int, default=10, show_default=True, help="Number of recent events to show.")
@click.option(
    "--kind",
    type=click.Choice(["scrape", "search"], case_sensitive=False),
    default=None,
    help="Only show events of this kind.",
)
def metrics_tail(count: int, kind: str | None) -> None:
    """Print the most recent events as JSON lines."""
    events = list(MetricsReader().events(kind=kind))
    if not events:
        click.echo("No telemetry recorded yet.")
        return
    for event in events[-count:]:
        click.echo(json.dumps(event))


@metrics.command("prune")
@click.option("--keep-days", type=int, default=None, help="Keep only events newer than this many days.")
@click.option("--keep-last", type=int, default=None, help="Keep only the most recent N events.")
def metrics_prune(keep_days: int | None, keep_last: int | None) -> None:
    """Bound the event log by age and/or count."""
    if keep_days is None and keep_last is None:
        click.echo("Specify --keep-days and/or --keep-last.", err=True)
        raise SystemExit(1)
    removed = MetricsReader().prune(keep_days=keep_days, keep_last=keep_last)
    click.echo(f"Pruned {removed} event{'s' if removed != 1 else ''}.")


@metrics.command("replay-remote")
@click.option(
    "--since",
    "since_days",
    type=int,
    default=None,
    help="Only replay events newer than N days. Omit to replay all events.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Report what would be sent without actually sending anything.",
)
def metrics_replay_remote(since_days: int | None, dry_run: bool) -> None:
    """Backfill the local telemetry log to the configured remote Loki endpoint.

    Events that were recorded while the remote endpoint was unset or
    unreachable are replayed in batches. Loki de-duplicates identical events
    by timestamp so re-running the command is safe.

    Note: Loki rejects events older than its ingestion window
    (``reject_old_samples_max_age``, often ~168h), so very old events may be
    dropped server-side. Use ``--since`` to replay only a recent window.

    Examples:
        supacrawl metrics replay-remote
        supacrawl metrics replay-remote --since 7
        supacrawl metrics replay-remote --dry-run
    """
    from datetime import datetime, timedelta, timezone

    from supacrawl.config import SupacrawlSecrets, load_config
    from supacrawl.remote_sink import LokiSink, build_remote_sink

    config = load_config()
    secrets = SupacrawlSecrets.from_env()
    sink = build_remote_sink(
        config.metrics_remote_url,
        token=secrets.metrics_token,
        username=config.metrics_remote_username,
        password=secrets.metrics_password,
        tenant=config.metrics_remote_tenant,
        job=config.metrics_job,
    )

    if sink is None:
        click.echo(
            "No remote telemetry endpoint configured. "
            "Set one with: supacrawl config set metrics_remote_url <loki-push-url>"
        )
        return

    if not isinstance(sink, LokiSink):
        click.echo("Remote sink type does not support replay.", err=True)
        raise SystemExit(1)

    since: datetime | None = datetime.now(timezone.utc) - timedelta(days=since_days) if since_days is not None else None
    events = list(MetricsReader().events(since=since))

    if not events:
        click.echo("No local events to replay.")
        return

    # Per-kind counts for reporting.
    kind_counts: dict[str, int] = {}
    for ev in events:
        k = str(ev.get("kind", "event"))
        kind_counts[k] = kind_counts.get(k, 0) + 1

    if dry_run:
        kind_summary = ", ".join(f"{v} {k}" for k, v in sorted(kind_counts.items()))
        click.echo(
            f"Dry run: {len(events)} event{'s' if len(events) != 1 else ''} "
            f"({kind_summary}) would be sent to {sink.endpoint} — nothing sent."
        )
        return

    _BATCH_SIZE = 500
    batches_sent = 0
    events_accepted = 0
    last_status: int | None = None

    for batch_start in range(0, len(events), _BATCH_SIZE):
        batch = events[batch_start : batch_start + _BATCH_SIZE]
        result = sink.send_checked(batch)
        if not result.ok:
            total_batches = (len(events) + _BATCH_SIZE - 1) // _BATCH_SIZE
            status_str = str(result.status) if result.status is not None else "-"
            click.echo(
                f"✗ Replay failed at batch {batches_sent + 1}/{total_batches}: "
                f"{result.detail} (HTTP {status_str}). "
                f"{events_accepted} event{'s' if events_accepted != 1 else ''} were accepted before the failure.",
                err=True,
            )
            raise SystemExit(1)
        batches_sent += 1
        events_accepted += len(batch)
        last_status = result.status

    kind_summary = ", ".join(f"{v} {k}" for k, v in sorted(kind_counts.items()))
    status_note = f" (HTTP {last_status})" if last_status is not None else ""
    click.echo(
        f"✓ Replayed {len(events)} event{'s' if len(events) != 1 else ''} "
        f"({kind_summary}) to {sink.endpoint} "
        f"in {batches_sent} batch{'es' if batches_sent != 1 else ''} — all accepted{status_note}. "
        "Re-running is safe; Loki de-duplicates identical events."
    )


@metrics.command("test-remote")
def metrics_test_remote() -> None:
    """Probe the configured remote telemetry endpoint.

    Sends one synthetic diagnostic event and reports whether the endpoint
    accepted it. Exits 0 on success, 1 on failure.

    Examples:
        supacrawl metrics test-remote
    """
    from supacrawl.config import SupacrawlSecrets, load_config
    from supacrawl.remote_sink import LokiSink, build_remote_sink

    config = load_config()
    secrets = SupacrawlSecrets.from_env()
    sink = build_remote_sink(
        config.metrics_remote_url,
        token=secrets.metrics_token,
        username=config.metrics_remote_username,
        password=secrets.metrics_password,
        tenant=config.metrics_remote_tenant,
        job=config.metrics_job,
    )

    if sink is None:
        click.echo(
            "No remote telemetry endpoint configured. "
            "Set one with: supacrawl config set metrics_remote_url <loki-push-url>"
        )
        return

    if not isinstance(sink, LokiSink):
        click.echo("Remote sink type does not support connectivity checks.", err=True)
        raise SystemExit(1)

    start = time.monotonic()
    result = sink.check()
    elapsed_ms = round((time.monotonic() - start) * 1000)

    if result.ok:
        status_str = str(result.status) if result.status is not None else "-"
        click.echo(f"✓ Reached {result.endpoint} (HTTP {status_str}, {elapsed_ms} ms) — telemetry is shipping.")
    else:
        status_str = str(result.status) if result.status is not None else "-"
        click.echo(f"✗ {result.endpoint}: {result.detail} (HTTP {status_str})", err=True)
        raise SystemExit(1)

"""Per-domain strategy memory commands (#130).

supacrawl learns, per domain, the cheapest scrape strategy that produced a clean
result, and seeds the next hit to that domain with it. These commands let a user
inspect, reset, and understand that local memory.
"""

import click

from supacrawl.cli._common import app
from supacrawl.services.strategy_memory import StrategyStore


@app.group()
def strategy() -> None:
    """Inspect and reset the per-domain strategy memory.

    supacrawl remembers which engine/wait/stealth produced a clean result for each
    domain you visit and seeds the next hit with it, so defaults quietly become
    excellent for the sites you actually use. It is local and optional; disable it
    with SUPACRAWL_STRATEGY_MEMORY=0.

    Examples:
        supacrawl strategy list            # Every learned domain and its champion
        supacrawl strategy show example-airline.com # The learned strategy for one domain
        supacrawl strategy forget example-airline.com
        supacrawl strategy clear           # Forget everything
    """


def _engine_label(engine: str | None, stealth: bool) -> str:
    if engine and engine != "playwright":
        return engine
    return "patchright" if stealth else "playwright"


@strategy.command("list")
def strategy_list() -> None:
    """List every learned domain and its champion strategy."""
    store = StrategyStore()
    domains = store.list_domains()
    if not domains:
        click.echo("No learned strategies yet. Scrape some sites and supacrawl will remember what works.")
        return
    click.echo(f"Learned strategies ({len(domains)}):")
    for domain, s in sorted(domains.items()):
        engine = _engine_label(s.engine, s.stealth)
        click.echo(
            f"  {domain}: {engine}, wait={s.wait_for}ms, "
            f"quality~{s.ewma_score:.0f} (n={s.samples}, updated {s.updated_at[:10]})"
        )


@strategy.command("show")
@click.argument("domain")
def strategy_show(domain: str) -> None:
    """Show the learned strategy for a single DOMAIN (e.g. example-airline.com)."""
    store = StrategyStore()
    s = store.get(domain.lower())
    if s is None:
        click.echo(f"No learned strategy for {domain!r}.")
        raise SystemExit(1)
    click.echo(f"Strategy for {domain}:")
    click.echo(f"  engine:            {_engine_label(s.engine, s.stealth)}")
    click.echo(f"  stealth:           {s.stealth}")
    click.echo(f"  wait_for:          {s.wait_for}ms")
    click.echo(f"  only_main_content: {s.only_main_content}")
    click.echo(f"  quality (EWMA):    {s.ewma_score:.1f}")
    click.echo(f"  samples:           {s.samples}")
    click.echo(f"  last verdict:      {s.last_verdict}")
    click.echo(f"  updated:           {s.updated_at}")


@strategy.command("forget")
@click.argument("domain")
def strategy_forget(domain: str) -> None:
    """Forget the learned strategy for a single DOMAIN."""
    store = StrategyStore()
    if store.forget(domain.lower()):
        click.echo(f"Forgot strategy for {domain}.")
    else:
        click.echo(f"No learned strategy for {domain!r}.")


@strategy.command("clear")
def strategy_clear() -> None:
    """Forget every learned strategy."""
    store = StrategyStore()
    count = store.clear()
    click.echo(f"Cleared {count} learned {'strategy' if count == 1 else 'strategies'}.")

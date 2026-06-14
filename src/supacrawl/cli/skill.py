"""``supacrawl install-skill`` — register Supacrawl as a discoverable agent skill."""

from importlib.resources import files
from pathlib import Path

import click

from supacrawl.cli._common import app


def _packaged_skill() -> str:
    """Return the bundled SKILL.md text."""
    return (files("supacrawl.resources") / "SKILL.md").read_text(encoding="utf-8")


@app.command("install-skill", help="Install the Supacrawl agent skill (SKILL.md) for an agent runtime.")
@click.option(
    "--user",
    is_flag=True,
    default=False,
    help="Install for the current user (~/.claude/skills) instead of the current project (./.claude/skills).",
)
@click.option(
    "--dir",
    "target_dir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Install into this directory instead of a Claude Code skills folder (for Codex, Cursor, or other runtimes).",
)
def install_skill(user: bool, target_dir: Path | None) -> None:
    """Write the bundled SKILL.md so an agent can self-onboard to Supacrawl.

    With no options this installs the Claude Code skill into the current
    project's ``.claude/skills/supacrawl/``. Use ``--user`` for the home
    directory, or ``--dir`` to write the file anywhere (e.g. a Cursor rules
    folder, or a path your own agent runtime reads).
    """
    if target_dir is not None:
        skill_dir = target_dir
    elif user:
        skill_dir = Path.home() / ".claude" / "skills" / "supacrawl"
    else:
        skill_dir = Path.cwd() / ".claude" / "skills" / "supacrawl"

    skill_dir.mkdir(parents=True, exist_ok=True)
    destination = skill_dir / "SKILL.md"
    destination.write_text(_packaged_skill(), encoding="utf-8")

    click.echo(f"Installed Supacrawl skill to {destination}")
    click.echo(
        "Claude Code discovers it automatically. For Codex, Cursor, or another runtime, "
        "point your agent config at this file (or re-run with --dir <your skills folder>)."
    )

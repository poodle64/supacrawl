"""Tests for the ``supacrawl install-skill`` command (#124)."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from supacrawl.cli import app


def test_install_skill_to_explicit_dir(tmp_path: Path) -> None:
    target = tmp_path / "skills"
    result = CliRunner().invoke(app, ["install-skill", "--dir", str(target)])
    assert result.exit_code == 0

    skill = target / "SKILL.md"
    assert skill.exists()
    text = skill.read_text(encoding="utf-8")
    # The packaged skill carries Claude Code frontmatter and the command guide.
    assert "name: supacrawl" in text
    assert "## Choosing a command" in text
    assert "supacrawl scrape" in text


def test_install_skill_project_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["install-skill"])
    assert result.exit_code == 0
    assert (tmp_path / ".claude" / "skills" / "supacrawl" / "SKILL.md").exists()


def test_install_skill_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "skills"
    runner = CliRunner()
    first = runner.invoke(app, ["install-skill", "--dir", str(target)])
    second = runner.invoke(app, ["install-skill", "--dir", str(target)])
    assert first.exit_code == 0
    assert second.exit_code == 0
    assert (target / "SKILL.md").exists()

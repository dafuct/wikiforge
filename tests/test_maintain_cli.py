"""wiki maintain: one entry point, silent in hook mode, never fatal."""

from __future__ import annotations

import asyncio
from pathlib import Path

from typer.testing import CliRunner

from wikiforge.cli.app import app
from wikiforge.services import init_wiki

runner = CliRunner()


def test_dry_run_prints_the_plan(tmp_path: Path) -> None:
    """The visibility --dry-run exists for."""
    home = tmp_path / "wiki"
    asyncio.run(init_wiki("w", home))
    result = runner.invoke(app, ["maintain", "--dry-run", "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert "wiki maintain" in result.output
    assert "budget:" in result.output


def test_force_renders_unlimited_not_a_huge_number(tmp_path: Path) -> None:
    """--force widens the budget internally to (10**9, inf) — the rendered
    budget line must say so in words, not print the raw placeholder numbers."""
    home = tmp_path / "wiki"
    asyncio.run(init_wiki("w", home))
    result = runner.invoke(app, ["maintain", "--dry-run", "--force", "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert "unlimited" in result.output
    assert "1000000000" not in result.output


def test_without_force_the_budget_line_is_unchanged(tmp_path: Path) -> None:
    """The non-forced rendering keeps reporting the real call count left."""
    home = tmp_path / "wiki"
    asyncio.run(init_wiki("w", home))
    result = runner.invoke(app, ["maintain", "--dry-run", "--home", str(home)])
    assert result.exit_code == 0, result.output
    assert "unlimited" not in result.output
    assert "call(s) left in the window" in result.output


def test_hook_mode_prints_nothing(tmp_path: Path) -> None:
    """Whether SessionStart stdout reaches the model is undocumented, so the
    hook writes nothing and records to the activity log instead (spec §8.6)."""
    home = tmp_path / "wiki"
    asyncio.run(init_wiki("w", home))
    result = runner.invoke(app, ["maintain", "--hook", "--home", str(home)])
    assert result.exit_code == 0
    assert result.output.strip() == ""


def test_hook_mode_survives_a_broken_home(tmp_path: Path) -> None:
    """A hook must never fail a session."""
    result = runner.invoke(app, ["maintain", "--hook", "--home", str(tmp_path / "nope")])
    assert result.exit_code == 0


def test_disabled_maintain_is_a_noop(tmp_path: Path) -> None:
    """[maintain] enabled = false switches the whole thing off."""
    home = tmp_path / "wiki"
    asyncio.run(init_wiki("w", home))
    cfg = (home / "config.toml").read_text(encoding="utf-8")
    (home / "config.toml").write_text(
        cfg.replace("[maintain]\nenabled = true", "[maintain]\nenabled = false"),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["maintain", "--home", str(home)])
    assert result.exit_code == 0
    assert "disabled" in result.output.lower()


def test_activity_log_records_the_run(tmp_path: Path) -> None:
    """The run summary must be retrievable after a silent hook run."""
    home = tmp_path / "wiki"
    asyncio.run(init_wiki("w", home))
    runner.invoke(app, ["maintain", "--hook", "--home", str(home)])
    context = runner.invoke(app, ["context", "--home", str(home)])
    assert "maintain" in context.output

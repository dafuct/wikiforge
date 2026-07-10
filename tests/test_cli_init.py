"""`wiki init` scaffolds a home directory, config, and database."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from wikiforge.cli.app import app


def test_init_creates_home_config_and_db(tmp_path: Path) -> None:
    home = tmp_path / "brain"
    result = CliRunner().invoke(app, ["init", "brain", "--home", str(home)])
    assert result.exit_code == 0, result.stdout
    assert (home / "config.toml").exists()
    assert (home / "wiki.db").exists()
    assert (home / "topics").is_dir()


def test_init_is_idempotent(tmp_path: Path) -> None:
    home = tmp_path / "brain"
    runner = CliRunner()
    runner.invoke(app, ["init", "brain", "--home", str(home)])
    # mutate config, re-run init, confirm it is not clobbered
    cfg = home / "config.toml"
    cfg.write_text(cfg.read_text() + "\n# user edit\n", encoding="utf-8")
    result = runner.invoke(app, ["init", "brain", "--home", str(home)])
    assert result.exit_code == 0
    assert "# user edit" in cfg.read_text()

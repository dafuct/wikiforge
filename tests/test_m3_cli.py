"""M3 CLI wiring: compile-nothing and related-unknown paths (no network)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from wikiforge.cli.app import app
from wikiforge.services import slugify


def test_slugify() -> None:
    assert slugify("Rust  Async I/O!") == "rust-async-i-o"


def test_compile_with_no_topics(tmp_path: Path) -> None:
    home = tmp_path / "w"
    CliRunner().invoke(app, ["init", "demo", "--home", str(home)])
    result = CliRunner().invoke(app, ["compile", "--home", str(home)])
    assert result.exit_code == 0
    assert "othing to compile" in result.stdout or "0 " in result.stdout


def test_related_unknown_topic(tmp_path: Path) -> None:
    home = tmp_path / "w"
    CliRunner().invoke(app, ["init", "demo", "--home", str(home)])
    result = CliRunner().invoke(app, ["related", "nonexistent", "--home", str(home)])
    assert result.exit_code != 0 or "not found" in result.stdout.lower()

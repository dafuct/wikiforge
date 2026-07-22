"""Smoke test: the Typer app is importable and reports its version."""

from __future__ import annotations

from typer.testing import CliRunner

from wikiforge.cli.app import app


def test_version_command_prints_version() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "0.3.0"

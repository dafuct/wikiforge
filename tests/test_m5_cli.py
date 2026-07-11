"""M5 CLI wiring: stats/context/generate/export/serve-mcp help, all offline."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from wikiforge.cli.app import app


def test_cli_query_subscription_without_claude_errors_cleanly(tmp_path: Path, monkeypatch) -> None:
    # With the subscription backend but no `claude` on PATH, the factory raises a
    # clear ValueError; the CLI must render it as an error + non-zero exit, not a traceback.
    home = tmp_path / "w"
    CliRunner().invoke(app, ["init", "demo", "--home", str(home)])
    cfg = home / "config.toml"
    cfg.write_text(
        cfg.read_text(encoding="utf-8").replace('backend = "api"', 'backend = "subscription"'),
        encoding="utf-8",
    )
    monkeypatch.setattr("wikiforge.llm.factory.shutil.which", lambda _: None)
    result = CliRunner().invoke(app, ["query", "anything", "--home", str(home)])
    assert result.exit_code != 0
    assert "claude" in result.output.lower()


def test_cli_stats_on_empty_wiki(tmp_path: Path) -> None:
    home = tmp_path / "w"
    CliRunner().invoke(app, ["init", "demo", "--home", str(home)])
    result = CliRunner().invoke(app, ["stats", "--home", str(home)])
    assert result.exit_code == 0
    assert "Topics: 0" in result.stdout


def test_cli_context_on_empty_wiki(tmp_path: Path) -> None:
    home = tmp_path / "w"
    CliRunner().invoke(app, ["init", "demo", "--home", str(home)])
    result = CliRunner().invoke(app, ["context", "--home", str(home)])
    assert result.exit_code == 0
    assert "recent activity" in result.stdout.lower()


def test_cli_export_json_on_empty_wiki(tmp_path: Path) -> None:
    home = tmp_path / "w"
    CliRunner().invoke(app, ["init", "demo", "--home", str(home)])
    out = tmp_path / "exp"
    result = CliRunner().invoke(app, ["export", "json", "--home", str(home), "--out", str(out)])
    assert result.exit_code == 0
    assert (out / "wiki.json").exists()


def test_cli_export_invalid_target_fails(tmp_path: Path) -> None:
    home = tmp_path / "w"
    CliRunner().invoke(app, ["init", "demo", "--home", str(home)])
    result = CliRunner().invoke(app, ["export", "bogus", "--home", str(home)])
    assert result.exit_code != 0


def test_cli_generate_unknown_topic_fails(tmp_path: Path) -> None:
    home = tmp_path / "w"
    CliRunner().invoke(app, ["init", "demo", "--home", str(home)])
    result = CliRunner().invoke(app, ["generate", "summary", "nope", "--home", str(home)])
    assert result.exit_code != 0  # unknown topic -> ValueError -> exit 1 (no network)


def test_serve_mcp_is_registered() -> None:
    result = CliRunner().invoke(app, ["serve-mcp", "--help"])
    assert result.exit_code == 0
    assert "stdio" in result.stdout.lower() or "model context protocol" in result.stdout.lower()

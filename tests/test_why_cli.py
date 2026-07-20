"""wiki why: path arg parsing, summaries, CLI output, embedder-free guarantee."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from wikiforge.cli.app import app
from wikiforge.models.domain import RawSource
from wikiforge.models.enums import SourceType
from wikiforge.ops.why import event_summary, format_events, parse_path_arg

_NOW = datetime(2026, 7, 20, 9, 0, 0, tzinfo=UTC)


def _event(files: str, ts: str, *, summary: str | None = None,
           request: str = "fix the deadlock in the bridge") -> RawSource:
    prov = {"ts": ts, "type": "bugfix", "files": files}
    if summary:
        prov["summary"] = summary
    text = (
        f"# Dev event — {ts} — bugfix\n\n## Request (why)\n{request}\n\n"
        f"## What changed\n- {files}\n\n## Type: bugfix"
    )
    return RawSource(content_hash=f"h-{ts}", source_type=SourceType.DEV_EVENT,
                     title=f"Dev event {ts}", text=text, fetched_at=_NOW, provenance=prov)


def test_parse_path_arg_strips_line_suffix() -> None:
    assert parse_path_arg("wikiforge/ops/recall.py") == ("wikiforge/ops/recall.py", None)
    path, note = parse_path_arg("wikiforge/ops/recall.py:52")
    assert path == "wikiforge/ops/recall.py"
    assert note is not None and "file-level" in note
    # a colon with non-digits is part of the path, not a line ref
    assert parse_path_arg("odd:name.py") == ("odd:name.py", None)


def test_event_summary_prefers_digest_then_request() -> None:
    assert event_summary(_event("/r/a.py", "2026-07-19T10:00:00Z",
                                summary="Fixed the deadlock.")) == "Fixed the deadlock."
    assert event_summary(_event("/r/a.py", "2026-07-19T10:00:00Z")).startswith(
        "fix the deadlock in the bridge"
    )


def test_format_events_renders_newest_first_with_markers() -> None:
    consolidated = _event("/r/a.py", "2026-07-01T10:00:00Z")
    consolidated.provenance["consolidated"] = "2026-W27"
    out = format_events("a.py", [_event("/r/a.py", "2026-07-19T10:00:00Z"), consolidated])
    assert "2026-07-19" in out and "bugfix" in out
    assert "consolidated: 2026-W27" in out


def test_cli_why_end_to_end_without_embedder(tmp_path: Path, monkeypatch) -> None:
    import asyncio

    from wikiforge.config.settings import write_default_config
    from wikiforge.ops.capture import capture_event
    from wikiforge.storage.db import Database
    from wikiforge.storage.repository import Repository

    home = tmp_path / "wiki"
    home.mkdir()
    (home / "topics").mkdir()
    write_default_config(home, wiki_name="T")

    async def seed() -> None:
        from wikiforge.config.settings import load_config

        db = await Database.open(home, dim=4)
        await db.init_schema()
        try:
            await capture_event(
                Repository(db), request="fix the deadlock in the bridge",
                files=[str(tmp_path / "proj" / "bridge.py")], event_type=None,
                default_type="change", origin="hook", cfg=load_config(home), llm=None,
                now=_NOW, git_runner=lambda argv: "",
            )
        finally:
            await db.close()

    asyncio.run(seed())

    import wikiforge.services as services

    def boom(*a, **k):  # the why path must never build an embedder
        raise AssertionError("embedder constructed on a why path")

    monkeypatch.setattr(services, "build_embedding_provider", boom)
    result = CliRunner().invoke(app, ["why", "bridge.py", "--home", str(home)])
    assert result.exit_code == 0
    assert "deadlock" in result.stdout and "bugfix" in result.stdout

    missing = CliRunner().invoke(app, ["why", "nope.py", "--home", str(home)])
    assert missing.exit_code == 0
    assert "No recorded decisions" in missing.stdout

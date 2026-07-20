"""PreToolUse guardrail: parsing, type filter, session dedup, sealed output, fail-safety."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from wikiforge.cli.app import app
from wikiforge.config.settings import load_config, write_default_config
from wikiforge.ops.capture import capture_event
from wikiforge.ops.why import WHY_HEADER, parse_pretool_stdin
from wikiforge.services import run_why_hook
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository

_NOW = datetime(2026, 7, 20, 9, 0, 0, tzinfo=UTC)


def test_parse_pretool_stdin_variants() -> None:
    payload = {"session_id": "s1", "tool_input": {"file_path": "/r/a.py"}}
    assert parse_pretool_stdin(json.dumps(payload)) == ("/r/a.py", "s1")
    nb = {"tool_input": {"notebook_path": "/r/n.ipynb"}}
    assert parse_pretool_stdin(json.dumps(nb)) == ("/r/n.ipynb", None)
    assert parse_pretool_stdin("not json") == (None, None)
    assert parse_pretool_stdin(json.dumps({"tool_input": {}})) == (None, None)


async def _seeded_home(tmp_path: Path, *, event_type: str | None = None,
                       request: str = "fix the deadlock in the bridge") -> Path:
    home = tmp_path / "wiki"
    home.mkdir(parents=True)
    (home / "topics").mkdir()
    write_default_config(home, wiki_name="T")
    db = await Database.open(home, dim=4)
    await db.init_schema()
    try:
        await capture_event(
            Repository(db), request=request, files=["/proj/bridge.py"],
            event_type=event_type, default_type="change", origin="hook", cfg=load_config(home),
            llm=None, now=_NOW, git_runner=lambda argv: "",
        )
    finally:
        await db.close()
    return home


def _payload(session: str = "s1", path: str = "/proj/bridge.py") -> str:
    return json.dumps({"session_id": session, "tool_input": {"file_path": path}})


async def test_hook_warns_once_per_file_per_session(tmp_path: Path) -> None:
    home = await _seeded_home(tmp_path)  # request infers type=bugfix (decision-carrying)
    first = await run_why_hook(home, _payload())
    assert first.startswith(WHY_HEADER)
    assert "<source_data" in first and "deadlock" in first
    assert await run_why_hook(home, _payload()) == ""            # deduped
    assert await run_why_hook(home, _payload(session="s2")) != ""  # new session warns


async def test_hook_ignores_non_decision_types_and_respects_config(tmp_path: Path) -> None:
    home = await _seeded_home(tmp_path, event_type="chore", request="bump deps")
    assert await run_why_hook(home, _payload()) == ""            # chore filtered out

    off_home = await _seeded_home(tmp_path / "w2")               # bugfix event, would warn…
    toml = (off_home / "config.toml").read_text()
    (off_home / "config.toml").write_text(toml.replace("guardrail = true", "guardrail = false"))
    assert await run_why_hook(off_home, _payload()) == ""        # …but guardrail=false wins
    assert await run_why_hook(off_home, "not json") == ""        # bad stdin safe too


async def test_hook_missing_session_id_still_warns(tmp_path: Path) -> None:
    home = await _seeded_home(tmp_path)
    payload = json.dumps({"tool_input": {"file_path": "/proj/bridge.py"}})
    assert (await run_why_hook(home, payload)).startswith(WHY_HEADER)


def test_cli_hook_is_failsafe(monkeypatch, tmp_path: Path) -> None:
    import wikiforge.services as services

    async def boom(home, stdin):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(services, "run_why_hook", boom)
    result = CliRunner().invoke(
        app, ["why", "--hook", "--home", str(tmp_path)], input="{}"
    )
    assert result.exit_code == 0


async def test_zero_max_events_yields_no_warning_and_no_dedup_row(tmp_path: Path) -> None:
    home = await _seeded_home(tmp_path)  # request infers type=bugfix (decision-carrying)
    # Set guardrail_max_events = 0 upfront
    toml = (home / "config.toml").read_text()
    toml = toml.replace("guardrail_max_events = 2", "guardrail_max_events = 0")
    (home / "config.toml").write_text(toml)

    # First call with max_events=0 should not warn and should not write dedup row
    result = await run_why_hook(home, _payload())
    assert result == ""

    # Now change back to guardrail_max_events = 2
    toml = (home / "config.toml").read_text()
    toml = toml.replace("guardrail_max_events = 0", "guardrail_max_events = 2")
    (home / "config.toml").write_text(toml)

    # Same payload should now warn (dedup row was not written when max_events=0)
    second = await run_why_hook(home, _payload())
    assert second.startswith(WHY_HEADER)


async def test_render_warning_empty_when_capped_to_zero() -> None:
    from datetime import UTC, datetime

    from wikiforge.models.domain import RawSource
    from wikiforge.models.enums import SourceType
    from wikiforge.ops.why import render_warning

    event = RawSource(
        id=1,
        title="test event",
        text="test content",
        content_hash="hash123",
        source_type=SourceType.DEV_EVENT,
        provenance={"type": "bugfix"},
        fetched_at=datetime.now(UTC),
    )

    # With max_events=0, should return ""
    result = render_warning([event], max_events=0)
    assert result == ""

"""wiki why across wikis: the 43/7 split, labelled and merged by date."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from wikiforge.federation.fanout import Sourced
from wikiforge.federation.registry import PeerRef, save_registry
from wikiforge.models.domain import RawSource
from wikiforge.ops.why import WHY_HEADER, event_ts, format_events, render_warning
from wikiforge.services import init_wiki, run_why, run_why_hook
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository

_HASHES = iter(range(1, 10_000))


def _event(ident: int, *, ts: str, summary: str) -> RawSource:
    """A dev event as capture stores one.

    ``content_hash`` and ``fetched_at`` are required by the real model (no
    defaults) even for an in-memory instance never written to a database —
    verified against ``wikiforge/models/domain.py`` during plan review. There
    is no ``url`` field; the model's name for it is ``canonical_url``.
    """
    return RawSource(
        id=ident,
        content_hash=f"why-fixture-{next(_HASHES)}",
        source_type="dev_event",
        title=summary,
        text=f"## Request (why)\n{summary}\n",
        fetched_at=datetime.fromisoformat(ts),
        provenance={"ts": ts, "type": "design", "summary": summary},
    )


async def _wiki_with_event(home: Path, name: str, *, path: str, ts: str, summary: str) -> None:
    """A wiki holding exactly one dev event that touched ``path``.

    ``Repository.ingest_raw_source`` is the real write path (verified against
    ``wikiforge/storage/repository.py``) and returns ``(id, is_new)``, not the
    source itself — the returned id is what ``dev_event_files`` references.
    """
    await init_wiki(name, home)
    db = await Database.open(home, dim=384)
    try:
        repo = Repository(db)
        await repo.ensure_dev_event_files()
        source_id, _ = await repo.ingest_raw_source(_event(0, ts=ts, summary=summary))
        await db.conn.execute(
            "INSERT INTO dev_event_files (source_id, path) VALUES (:sid, :p)",
            {"sid": source_id, "p": path},
        )
        await db.conn.commit()
    finally:
        await db.close()


def test_event_ts_prefers_provenance() -> None:
    """Cross-wiki ordering needs a full timestamp, not just a date."""
    ev = _event(1, ts="2026-07-18T09:00:00+00:00", summary="s")
    assert event_ts(ev).startswith("2026-07-18T09")


def test_format_events_labels_only_peers() -> None:
    """Local lines stay exactly as they were; peer lines carry [alias]."""
    local = Sourced("", _event(1, ts="2026-07-20T10:00:00+00:00", summary="local work"))
    peer = Sourced("global", _event(2, ts="2026-07-18T10:00:00+00:00", summary="peer work"))
    out = format_events("a.py", [local, peer])
    lines = out.splitlines()
    assert "[global]" not in lines[1]
    assert "[global]" in lines[2]


def test_render_warning_keeps_alias_outside_the_seal() -> None:
    """The alias is locally-generated trusted metadata; event text is sealed."""
    peer = Sourced("global", _event(2, ts="2026-07-18T10:00:00+00:00", summary="peer work"))
    out = render_warning([peer], max_events=2)
    assert "[global]" in out
    assert out.index("[global]") < out.index("<source_data")


@pytest.mark.asyncio
async def test_run_why_merges_peers_newest_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The measured 43/7 split: history in another wiki becomes visible here."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    target = "/repo/wikiforge/services.py"
    local = tmp_path / "local"
    peer = tmp_path / "peer"
    await _wiki_with_event(
        local, "local", path=target, ts="2026-07-18T10:00:00+00:00", summary="local decision"
    )
    await _wiki_with_event(
        peer, "global", path=target, ts="2026-07-20T10:00:00+00:00", summary="peer decision"
    )
    save_registry([PeerRef("global", peer)])

    events, _ = await run_why(local, target, limit=10)

    assert [(s.origin, s.item.provenance["summary"]) for s in events] == [
        ("global", "peer decision"),
        ("", "local decision"),
    ]


@pytest.mark.asyncio
async def test_disabled_federation_returns_local_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[federation] enabled = false restores exactly the pre-cycle-4 behaviour."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    target = "/repo/a.py"
    local = tmp_path / "local"
    peer = tmp_path / "peer"
    await _wiki_with_event(
        local, "local", path=target, ts="2026-07-18T10:00:00+00:00", summary="local decision"
    )
    await _wiki_with_event(
        peer, "global", path=target, ts="2026-07-20T10:00:00+00:00", summary="peer decision"
    )
    save_registry([PeerRef("global", peer)])
    cfg = (local / "config.toml").read_text(encoding="utf-8")
    (local / "config.toml").write_text(
        cfg.replace("[federation]\nenabled = true", "[federation]\nenabled = false"),
        encoding="utf-8",
    )

    events, _ = await run_why(local, target, limit=10)

    assert [s.origin for s in events] == [""]


@pytest.mark.asyncio
async def test_unreachable_peer_does_not_break_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A registry entry can outlive its wiki; why must still answer."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    target = "/repo/a.py"
    local = tmp_path / "local"
    await _wiki_with_event(
        local, "local", path=target, ts="2026-07-18T10:00:00+00:00", summary="local decision"
    )
    save_registry([PeerRef("gone", tmp_path / "gone")])

    events, _ = await run_why(local, target, limit=10)

    assert [s.origin for s in events] == [""]


@pytest.mark.asyncio
async def test_run_why_answers_from_peer_only_when_local_has_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Local history isn't a gate: a file untouched locally still gets an answer.

    The brief's merge test (above) always has *some* local event, so it can't
    tell a real merge from a bug where the peer branch never runs. This pins
    the harder case directly: zero local rows for the path, one peer row.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    target = "/repo/only-on-peer.py"
    local = tmp_path / "local"
    peer = tmp_path / "peer"
    await init_wiki("local", local)  # local wiki exists but never saw this path
    await _wiki_with_event(
        peer, "global", path=target, ts="2026-07-20T10:00:00+00:00", summary="peer-only decision"
    )
    save_registry([PeerRef("global", peer)])

    events, fell_back = await run_why(local, target, limit=10)

    assert [(s.origin, s.item.provenance["summary"]) for s in events] == [
        ("global", "peer-only decision"),
    ]
    assert fell_back is False  # fell_back describes the local suffix-match, not a peer answer


@pytest.mark.asyncio
async def test_hook_warns_from_peer_only_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guardrail's 'nothing to warn about' exit must not gate on local alone.

    Local has zero history for the file; only a peer does. The warning must
    still fire, and the peer's alias must sit outside the sealed event line.
    """
    import json

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    target = "/repo/only-on-peer.py"
    local = tmp_path / "local"
    peer = tmp_path / "peer"
    await init_wiki("local", local)  # local wiki exists but never saw this path
    await _wiki_with_event(
        peer, "global", path=target, ts="2026-07-20T10:00:00+00:00", summary="peer-only decision"
    )
    save_registry([PeerRef("global", peer)])
    payload = json.dumps({"session_id": "s1", "tool_input": {"file_path": target}})

    warning = await run_why_hook(local, payload)

    assert warning.startswith(WHY_HEADER)
    assert "<source_data" in warning
    assert "[global]" in warning
    assert warning.index("[global]") < warning.index("<source_data")
    assert "peer-only decision" in warning

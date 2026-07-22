"""Changelog coverage must never conflate two wikis' memories."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from wikiforge.federation.registry import PeerRef, save_registry
from wikiforge.models.domain import RawSource
from wikiforge.ops.changelog import Changelog, ChangelogEntry, Range, format_changelog
from wikiforge.services import init_wiki, run_changelog
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository

_HASHES = iter(range(1, 10_000))


def _event(summary: str, *, origin_hint: str = "") -> RawSource:
    """A dev event, shaped like Task 9's fixture (content_hash/fetched_at required)."""
    return RawSource(
        id=1,
        content_hash=f"changelog-fixture-{origin_hint}-{next(_HASHES)}",
        source_type="dev_event",
        title=summary,
        text=f"## Request (why)\n{summary}\n",
        fetched_at=datetime.fromisoformat("2026-07-21T10:00:00+00:00"),
        provenance={"type": "feature", "summary": summary},
    )


def _range() -> Range:
    return Range(
        base="aaaaaaa1",
        head="bbbbbbb2",
        base_iso="2026-07-20T00:00:00Z",
        head_iso="2026-07-21T00:00:00Z",
        commits=3,
        paths=["a.py", "b.py", "c.py", "d.py"],
    )


def test_footer_reports_per_origin() -> None:
    """A coverage number must say how much came from elsewhere."""
    log = Changelog(
        rng=_range(),
        root="/repo",
        entries=[
            ChangelogEntry(event=_event("local"), matched_by="files", origin=""),
            ChangelogEntry(event=_event("peer"), matched_by="files", origin="global"),
        ],
        files_with_history=2,
        excluded=0,
        by_origin={"": 1, "global": 1},
    )
    out = format_changelog(log)
    assert "from global" in out


def test_no_peer_contributions_leaves_the_footer_unchanged() -> None:
    """Local-only output must be byte-identical to the pre-federation render."""
    log = Changelog(
        rng=_range(),
        root="/repo",
        entries=[ChangelogEntry(event=_event("local"), matched_by="files", origin="")],
        files_with_history=1,
        excluded=0,
        by_origin={"": 1},
    )
    assert "from" not in format_changelog(log).rsplit("---", 1)[1]


def test_peer_entries_are_labelled_in_the_body() -> None:
    """A reader must see which project remembered which decision."""
    log = Changelog(
        rng=_range(),
        root="/repo",
        entries=[ChangelogEntry(event=_event("peer"), matched_by="files", origin="global")],
        files_with_history=0,
        excluded=0,
        by_origin={"global": 1},
    )
    assert "[global]" in format_changelog(log)


async def _wiki_with_event(
    home: Path, name: str, *, files: list[str], when: str, summary: str, kind: str
) -> None:
    """A wiki holding exactly one dev event, optionally file-indexed (Task 9's pattern).

    ``files=[]`` yields a genuine window-arm-only event: no ``dev_event_files``
    row, findable only by :meth:`Repository.dev_events_fileless_in_window`.
    """
    await init_wiki(name, home)
    db = await Database.open(home, dim=384)
    try:
        repo = Repository(db)
        await repo.ensure_dev_event_files()
        source_id, _ = await repo.ingest_raw_source(
            RawSource(
                content_hash=f"changelog-federated-fixture-{next(_HASHES)}",
                source_type="dev_event",
                title=summary,
                text=f"## Request (why)\n{summary}\n",
                fetched_at=datetime.fromisoformat(when),
                provenance={"type": kind, "summary": summary},
            )
        )
        if files:
            await repo.add_dev_event_files(source_id, files)
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_run_changelog_keeps_a_peers_window_arm_entry_file_less(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real two-wiki reproduction of the select_peer_events bug.

    Before the fix, ``select_peer_events`` returned bare ``RawSource`` and
    ``run_changelog``'s merge unconditionally stamped every peer entry
    ``matched_by="files"`` — mislabelling the peer's genuine file-less
    ("window") decision. That corrupted two things at once: the render
    placed it under a type heading instead of "## Decisions without file
    changes", and the footer's derived split reported "2 ... matched by
    file, 0 ... by time window" instead of the true 1/1 split.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    from wikiforge import services
    from wikiforge.ops import changelog as changelog_ops

    local = tmp_path / "local"
    peer = tmp_path / "peer"
    await _wiki_with_event(
        local,
        "local",
        files=["/repo/a.py"],
        when="2026-07-20T10:00:00+00:00",
        summary="local files-arm decision",
        kind="feature",
    )
    await _wiki_with_event(
        peer,
        "global",
        files=[],
        when="2026-07-20T12:00:00+00:00",
        summary="peer window-arm decision",
        kind="design",
    )
    save_registry([PeerRef("global", peer)])

    monkeypatch.setattr(services, "repo_root", lambda **kw: "/repo")
    monkeypatch.setattr(
        changelog_ops,
        "resolve_range",
        lambda spec, runner=None: changelog_ops.Range(
            base="aaaa",
            head="bbbb",
            base_iso="2026-07-20T00:00:00.000000+00:00",
            head_iso="2026-07-20T23:59:59.999999+00:00",
            commits=2,
            paths=["a.py"],
        ),
    )

    out = await run_changelog(local, "a..b", limit=50)

    assert "## Decisions without file changes" in out
    fileless_section = out.split("## Decisions without file changes", 1)[1]
    assert "peer window-arm decision" in fileless_section
    assert "[global]" in fileless_section
    assert "## Design" not in out  # never promoted to a type heading
    footer = out.rsplit("---", 1)[1]
    assert "1 events matched by file, 1 by time window." in footer

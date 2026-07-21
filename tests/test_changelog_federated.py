"""Changelog coverage must never conflate two wikis' memories."""

from __future__ import annotations

from datetime import datetime

from wikiforge.models.domain import RawSource
from wikiforge.ops.changelog import Changelog, ChangelogEntry, Range, format_changelog

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

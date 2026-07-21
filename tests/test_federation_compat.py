"""Compatibility verdicts: three states, and never a guess from config."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.federation.peers import PeerStatus, compat_verdict, fix_hint, peer_status
from wikiforge.federation.registry import PeerRef
from wikiforge.services import init_wiki
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


def test_compat_verdict_states() -> None:
    """Same stamp is ok, a different stamp is mismatch, no stamp is unknown."""
    assert compat_verdict("e5", "e5") == "ok"
    assert compat_verdict("bge", "e5") == "mismatch"
    assert compat_verdict(None, "e5") == "unknown"


@pytest.mark.asyncio
async def test_unstamped_peer_is_unknown_not_mismatch(tmp_path: Path) -> None:
    """The real state of every project wiki on the author's machine (spec §1.1):
    a wiki_meta table exists, but embedding_model was never stamped."""
    home = tmp_path / "peer"
    await init_wiki("peer", home)  # stamps embedding_dim only
    status = await peer_status(PeerRef("peer", home), local_model="e5", dim=384)
    assert status.reachable is True
    assert status.model is None
    assert status.compat == "unknown"
    assert fix_hint(status) is not None
    assert "reindex" in (fix_hint(status) or "")


@pytest.mark.asyncio
async def test_stamped_matching_peer_is_ok(tmp_path: Path) -> None:
    """A stamped peer on the same model joins the vector paths."""
    home = tmp_path / "peer"
    await init_wiki("peer", home)
    db = await Database.open(home, dim=384)
    try:
        await Repository(db).set_meta("embedding_model", "e5")
    finally:
        await db.close()
    status = await peer_status(PeerRef("peer", home), local_model="e5", dim=384)
    assert status.compat == "ok"
    assert fix_hint(status) is None


@pytest.mark.asyncio
async def test_unreachable_peer_reports_instead_of_raising(tmp_path: Path) -> None:
    """A moved or deleted peer is a status, not an exception."""
    status = await peer_status(PeerRef("gone", tmp_path / "gone"), local_model="e5", dim=384)
    assert status.reachable is False
    assert status.compat == "unknown"
    assert status.error is not None


@pytest.mark.asyncio
async def test_missing_file_index_is_reported(tmp_path: Path) -> None:
    """rss and nimbus lack dev_event_files today (spec §1.1 fact 4); such a peer
    can only be reported, never repaired from here."""
    home = tmp_path / "peer"
    await init_wiki("peer", home)
    db = await Database.open(home, dim=384)
    try:
        await db.conn.execute("DROP TABLE IF EXISTS dev_event_files")
        await db.conn.commit()
    finally:
        await db.close()
    status = await peer_status(PeerRef("peer", home), local_model="e5", dim=384)
    assert status.has_file_index is False
    hint = fix_hint(status) or ""
    assert "wiki maintain" in hint


def test_fix_hint_is_single_line() -> None:
    """Hints are rendered into terminal tables and hook-adjacent output."""
    status = PeerStatus(
        peer=PeerRef("p", Path("/p")),
        reachable=True,
        model="bge",
        compat="mismatch",
        has_file_index=True,
        error=None,
    )
    hint = fix_hint(status) or ""
    assert "\n" not in hint

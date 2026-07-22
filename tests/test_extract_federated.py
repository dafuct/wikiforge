"""Explicit search sees peers, with the same labels recall uses."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.federation.fanout import Sourced
from wikiforge.federation.registry import PeerRef, save_registry


@pytest.mark.asyncio
async def test_extract_returns_sourced_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The element type changed; every caller must handle origins.

    Isolates ``XDG_CONFIG_HOME`` like every other federation-aware test in this
    suite (its own sibling below included) — without it, this test reads
    whatever peer registry is actually on the machine running it, rather than
    the empty one its "no peers registered" premise requires.
    """
    # Build a single-wiki fixture with one indexed chunk (reuse the helper from
    # tests/test_federation_probe.py — import it rather than copying).
    from tests.test_federation_probe import _build_wiki
    from wikiforge.services import run_extract

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    home = tmp_path / "local"
    await _build_wiki(home, text="alpha beta", vector=[0.1] * 384)
    got = await run_extract(home, "alpha", depth="standard", scope="all")
    assert all(isinstance(item, Sourced) for item in got)
    assert all(item.origin == "" for item in got)


@pytest.mark.asyncio
async def test_incompatible_peer_contributes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unstamped peer is skipped on the vector path (spec §5.2)."""
    from tests.test_federation_probe import _build_wiki
    from wikiforge.services import run_extract

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    local = tmp_path / "local"
    peer = tmp_path / "peer"
    await _build_wiki(local, text="alpha beta", vector=[0.1] * 384)
    await _build_wiki(peer, text="alpha gamma", vector=[0.1] * 384)
    save_registry([PeerRef("peer", peer)])

    got = await run_extract(local, "alpha", depth="standard", scope="all")

    assert {item.origin for item in got} == {""}

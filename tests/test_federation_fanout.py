"""Fan-out: run one read across local and peers, isolating every failure."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from wikiforge.federation.fanout import Sourced, fan_out, safe_origin
from wikiforge.federation.registry import PeerRef
from wikiforge.services import init_wiki
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


async def _wiki(tmp_path: Path, name: str, *, model: str | None) -> Path:
    """A wiki with one meta value, optionally stamped with an embedding model."""
    home = tmp_path / name
    await init_wiki(name, home)
    db = await Database.open(home, dim=384)
    try:
        repo = Repository(db)
        await repo.set_meta("marker", name)
        if model is not None:
            await repo.set_meta("embedding_model", model)
    finally:
        await db.close()
    return home


def test_safe_origin_clamps_to_one_line() -> None:
    """Aliases reach hook contracts that break on newlines (cycle-1 lesson)."""
    assert safe_origin("global") == "global"
    assert "\n" not in safe_origin("a\nb")
    assert safe_origin("x" * 200) == "x" * 40
    assert safe_origin("") == "peer"


@pytest.mark.asyncio
async def test_local_first_then_peers_in_registry_order(tmp_path: Path) -> None:
    """Deterministic ordering; local results carry the empty origin."""
    local = await _wiki(tmp_path, "local", model="e5")
    a = await _wiki(tmp_path, "a", model="e5")
    b = await _wiki(tmp_path, "b", model="e5")

    async def read(repo: Repository) -> list[str]:
        return [await repo.get_meta("marker") or ""]

    db = await Database.open(local, dim=384)
    try:
        got = await fan_out(
            [PeerRef("a", a), PeerRef("b", b)],
            read,
            local=Repository(db),
            dim=384,
            timeout_ms=2000,
        )
    finally:
        await db.close()
    assert [(s.origin, s.item) for s in got] == [
        ("", "local"),
        ("a", "a"),
        ("b", "b"),
    ]


@pytest.mark.asyncio
async def test_unreachable_peer_is_skipped(tmp_path: Path) -> None:
    """A dead peer contributes nothing and never propagates."""
    local = await _wiki(tmp_path, "local", model="e5")

    async def read(repo: Repository) -> list[str]:
        return [await repo.get_meta("marker") or ""]

    db = await Database.open(local, dim=384)
    try:
        got = await fan_out(
            [PeerRef("gone", tmp_path / "gone")],
            read,
            local=Repository(db),
            dim=384,
            timeout_ms=2000,
        )
    finally:
        await db.close()
    assert [s.origin for s in got] == [""]


@pytest.mark.asyncio
async def test_slow_peer_is_dropped_at_the_timeout(tmp_path: Path) -> None:
    """peer_timeout_ms is a wall clock, not a suggestion."""
    local = await _wiki(tmp_path, "local", model="e5")
    slow = await _wiki(tmp_path, "slow", model="e5")

    async def read(repo: Repository) -> list[str]:
        marker = await repo.get_meta("marker") or ""
        if marker == "slow":
            await asyncio.sleep(1.0)
        return [marker]

    db = await Database.open(local, dim=384)
    try:
        got = await fan_out(
            [PeerRef("slow", slow)],
            read,
            local=Repository(db),
            dim=384,
            timeout_ms=50,
        )
    finally:
        await db.close()
    assert [s.origin for s in got] == [""]


@pytest.mark.asyncio
async def test_require_compat_skips_unstamped_peers(tmp_path: Path) -> None:
    """Vector paths federate only across proven-compatible peers (spec §5.2)."""
    local = await _wiki(tmp_path, "local", model="e5")
    same = await _wiki(tmp_path, "same", model="e5")
    other = await _wiki(tmp_path, "other", model="bge")
    unstamped = await _wiki(tmp_path, "unstamped", model=None)

    async def read(repo: Repository) -> list[str]:
        return [await repo.get_meta("marker") or ""]

    db = await Database.open(local, dim=384)
    try:
        got = await fan_out(
            [
                PeerRef("same", same),
                PeerRef("other", other),
                PeerRef("unstamped", unstamped),
            ],
            read,
            local=Repository(db),
            dim=384,
            timeout_ms=2000,
            require_compat=True,
            local_model="e5",
        )
    finally:
        await db.close()
    assert [s.origin for s in got] == ["", "same"]


@pytest.mark.asyncio
async def test_raising_reader_drops_only_that_peer(tmp_path: Path) -> None:
    """One peer whose schema is too old must not cost the others."""
    local = await _wiki(tmp_path, "local", model="e5")
    broken = await _wiki(tmp_path, "broken", model="e5")
    good = await _wiki(tmp_path, "good", model="e5")

    async def read(repo: Repository) -> list[str]:
        marker = await repo.get_meta("marker") or ""
        if marker == "broken":
            raise RuntimeError("no such table: dev_event_files")
        return [marker]

    db = await Database.open(local, dim=384)
    try:
        got = await fan_out(
            [PeerRef("broken", broken), PeerRef("good", good)],
            read,
            local=Repository(db),
            dim=384,
            timeout_ms=2000,
        )
    finally:
        await db.close()
    assert [s.origin for s in got] == ["", "good"]


def test_sourced_is_frozen() -> None:
    """Origin is metadata about a result, never mutated after the fact."""
    import dataclasses

    s = Sourced(origin="a", item=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.origin = "b"  # type: ignore[misc]

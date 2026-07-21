"""Run one read across the local wiki and its peers.

The central rule (spec §6.2): a rowid never leaves its repository. ``fn``
receives a ``Repository`` and must finish everything that depends on database
identity — retrieval, vector loading, scoring — before returning. Only
already-resolved values cross the boundary, tagged with the origin they came
from.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from wikiforge.config.settings import Config
from wikiforge.federation.peers import PeerUnavailable, ReadOnlyDatabase, compat_verdict
from wikiforge.federation.registry import PeerRef, load_registry
from wikiforge.storage.repository import Repository

T = TypeVar("T")

_ALIAS_MAX = 40
_ALIAS_UNSAFE = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class Sourced(Generic[T]):  # noqa: UP046 -- classic Generic[T], matching llm.provider.ParsedResult
    """A value plus the wiki it came from. ``origin=""`` is the local wiki."""

    origin: str
    item: T


def safe_origin(alias: str) -> str:
    """A one-line, control-character-free, bounded alias fit for rendering.

    Aliases come from a user-authored config file and are rendered into hook
    contracts that are newline-sensitive — the same class of bug cycle 1 fixed
    with ``safe_event_type``.
    """
    cleaned = _ALIAS_UNSAFE.sub("", alias.replace("\n", " ").replace("\r", " ")).strip()
    return cleaned[:_ALIAS_MAX] or "peer"


def active_peers(cfg: Config) -> list[PeerRef]:
    """Registered peers, or ``[]`` when this wiki has federation switched off."""
    if not cfg.federation.enabled:
        return []
    return load_registry()


async def fan_out(  # noqa: UP047 -- classic TypeVar T, matching Sourced[T] above
    peers: Sequence[PeerRef],
    fn: Callable[[Repository], Awaitable[list[T]]],
    *,
    local: Repository | None,
    dim: int,
    timeout_ms: int,
    require_compat: bool = False,
    local_model: str = "",
) -> list[Sourced[T]]:
    """Run ``fn`` against the local repository and each peer, in order.

    Peers run sequentially: a SQLite open costs milliseconds, and determinism
    plus per-peer isolation is worth more here than parallelism that would be
    lost in the noise. Every peer is bounded by ``timeout_ms`` and wrapped in
    its own ``try`` — unreachable, locked, corrupt, schema-drifted and merely
    slow peers all contribute nothing and never propagate.

    With ``require_compat`` a peer joins only when its stamped embedding model
    equals ``local_model``; this is what earns the right to compare scores
    across wikis.
    """
    out: list[Sourced[T]] = []
    if local is not None:
        out.extend(Sourced(origin="", item=item) for item in await fn(local))
    for peer in peers:
        for item in await _read_peer(
            peer,
            fn,
            dim=dim,
            timeout_ms=timeout_ms,
            require_compat=require_compat,
            local_model=local_model,
        ):
            out.append(Sourced(origin=safe_origin(peer.alias), item=item))
    return out


async def _read_peer(  # noqa: UP047 -- classic TypeVar T, matching Sourced[T] above
    peer: PeerRef,
    fn: Callable[[Repository], Awaitable[list[T]]],
    *,
    dim: int,
    timeout_ms: int,
    require_compat: bool,
    local_model: str,
) -> list[T]:
    """One peer's contribution, or ``[]`` for any reason whatsoever."""
    try:
        db = await ReadOnlyDatabase.open(peer.home, dim=dim)
    except PeerUnavailable:
        return []
    try:
        repo = Repository(db)  # type: ignore[arg-type]
        if require_compat:
            stamped = await repo.get_meta("embedding_model")
            if compat_verdict(stamped, local_model) != "ok":
                return []
        return await asyncio.wait_for(fn(repo), timeout_ms / 1000)
    except Exception:  # noqa: BLE001 -- a bad peer (incl. TimeoutError) is never fatal
        return []
    finally:
        await db.close()


async def peer_candidates(
    repo: Repository,
    query: str,
    *,
    query_vec: list[float],
    owner_types: list[str],
    limit: int,
) -> list[int]:
    """Candidate chunk rowids from one wiki: FTS always, vectors when available.

    Vector KNN over a read-only connection is probed in
    ``tests/test_federation_probe.py``. Should a future sqlite-vec refuse it,
    this degrades to FTS-only candidates — a reduction in breadth, never a
    wrong number, because admission is decided later by cosine against the
    stored vectors (spec §5.3).
    """
    import sqlite3

    from wikiforge.search.ftsquery import to_fts_match_query

    ids: list[int] = []
    match = to_fts_match_query(query)
    if match:
        try:
            ids.extend(await repo.fts_search(match, owner_types, limit))
        except sqlite3.OperationalError:
            pass
    try:
        ids.extend(await repo.vec_search(query_vec, owner_types, limit))
    except sqlite3.OperationalError:
        pass
    return list(dict.fromkeys(ids))

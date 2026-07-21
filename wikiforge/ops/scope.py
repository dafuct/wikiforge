"""Repository scoping for path-addressed queries over the dev log.

``wiki why``, ``wiki changelog`` and ``wiki impact`` all address the dev log by
file path, and capture stores paths absolutely. In a wiki shared by several
projects — the default ``~/wiki`` is one — matching a bare relative path by
suffix attributes another project's decisions to this one; measured at 103 of
159 indexed paths on the author's wiki. This module is the single place that
turns a repo-relative path into the absolute form the index holds.

Rendering lives in :mod:`wikiforge.ops.why`; this module deliberately holds
only what changelog, impact and why all three need.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from wikiforge.models.domain import RawSource
from wikiforge.ops.capture import GitRunner, default_git_runner
from wikiforge.storage.repository import Repository


def repo_root(*, runner: GitRunner = default_git_runner, cwd: Path | None = None) -> str:
    """Absolute root of the enclosing git worktree, or "" when there is none.

    Best-effort: any git failure yields "" so callers degrade to unanchored
    behaviour rather than erroring.
    """
    argv = ["git", "rev-parse", "--show-toplevel"]
    if cwd is not None:
        argv = ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"]
    try:
        return runner(argv).strip()
    except Exception:
        return ""


def anchor_paths(root: str, relpaths: Iterable[str]) -> list[str]:
    """Join repo-relative paths onto ``root``, giving the form the index stores.

    Absolute inputs pass through untouched; an empty ``root`` is identity.
    """
    if not root:
        return list(relpaths)
    prefix = root.rstrip("/")
    return [p if p.startswith("/") else f"{prefix}/{p}" for p in relpaths]


@dataclass(frozen=True)
class PathEvents:
    """Events for a path set, the paths that matched, and how they were found.

    ``fell_back`` is carried here rather than left for a caller to infer: only
    this module knows whether the anchored lookup or the suffix fallback
    answered, and ``wiki why`` must *label* a cross-project answer rather than
    present it as local history.
    """

    events: list[RawSource]
    matched: set[str]
    fell_back: bool


async def _prepare(repo: Repository, *, read_only: bool) -> None:
    """Ensure the file index locally; on a peer, leave the database untouched.

    A peer that predates the index simply has nothing to contribute (rss and
    nimbus are in exactly that state today) — and building it there would be a
    cross-wiki write, which the design forbids outright.
    """
    if not read_only:
        await repo.ensure_dev_event_files()


async def events_for_absolute(
    repo: Repository, path: str, *, limit: int, read_only: bool = False
) -> list[RawSource]:
    """Dev events for an absolute path; ``[]`` when this wiki has no file index."""
    await _prepare(repo, read_only=read_only)
    try:
        return await repo.dev_events_for_path(path, limit=limit)
    except sqlite3.OperationalError:
        return []


async def events_for_paths(
    repo: Repository,
    relpaths: list[str],
    *,
    root: str,
    limit: int,
    read_only: bool = False,
) -> PathEvents:
    """Dev events touching any of ``relpaths``, newest first, deduped by id.

    ``matched`` holds the *input* paths — mapped back from the absolute form the
    query matched — so a caller can report coverage without re-deriving the
    anchoring.

    Anchored lookup first: when ``root`` is non-empty the paths are anchored and
    matched exactly. Only if that yields nothing does it fall back to the
    ``/``-anchored suffix match, so a wiki whose index predates repo anchoring —
    or was captured from a different absolute prefix, e.g. a worktree — still
    answers. The fallback is all-or-nothing per call, never per path: topping up
    a partial anchored hit with suffix matches would silently reintroduce
    cross-project contamination for whichever paths happened to miss.

    ``fell_back`` is True only when a repo root was known, anchoring found
    nothing, and the fallback found something — an empty result is not a
    cross-project answer, and outside a repo there is nothing to fall back from.

    ``read_only`` is for peer wikis: the index is not ensured and a wiki that
    lacks ``dev_event_files`` yields an empty result rather than an error.
    """
    if not relpaths:
        return PathEvents(events=[], matched=set(), fell_back=False)
    await _prepare(repo, read_only=read_only)

    try:
        if root:
            anchored = anchor_paths(root, relpaths)
            back = dict(zip(anchored, relpaths, strict=True))
            events = await repo.dev_events_for_paths(anchored, limit=limit)
            if events:
                matched_abs = await repo.matched_dev_event_paths(anchored)
                return PathEvents(
                    events=events,
                    matched={back.get(p, p) for p in matched_abs},
                    fell_back=False,
                )

        seen: set[int] = set()
        found: list[RawSource] = []
        matched: set[str] = set()
        for rel in relpaths:
            for event in await repo.dev_events_for_path(rel, limit=limit):
                matched.add(rel)
                if event.id is not None and event.id not in seen:
                    seen.add(event.id)
                    found.append(event)
        found.sort(key=lambda e: e.id or 0, reverse=True)
        return PathEvents(
            events=found[:limit], matched=matched, fell_back=bool(root) and bool(found)
        )
    except sqlite3.OperationalError:
        return PathEvents(events=[], matched=set(), fell_back=False)

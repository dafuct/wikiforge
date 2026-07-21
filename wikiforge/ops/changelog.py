"""wiki changelog: a why-annotated changelog for a git range.

The dev log already holds the request behind each change; this module joins it
to a git range and renders it. Zero LLM unless the caller asks for prose.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from wikiforge.models.domain import RawSource
from wikiforge.ops.capture import GitRunner, default_git_runner
from wikiforge.ops.scope import events_for_paths
from wikiforge.ops.why import safe_event_type
from wikiforge.storage.repository import Repository


@dataclass(frozen=True)
class Range:
    """A resolved git range plus everything the selection needs from git."""

    base: str
    head: str
    base_iso: str
    head_iso: str
    commits: int
    paths: list[str]


def _bound(git_iso: str, *, upper: bool) -> str:
    """Normalize a git committer date to fetched_at's stored format.

    ``fetched_at`` is stored as UTC with microseconds (2026-07-20T18:52:10.561928+00:00);
    git's %cI emits the committer's local offset. Comparing those as SQL strings
    compares text, not instants. Converting to UTC and widening to the whole
    second makes lexical comparison chronological and inclusive at both ends.
    """
    moment = datetime.fromisoformat(git_iso.strip()).astimezone(UTC)
    moment = moment.replace(microsecond=999999 if upper else 0)
    return moment.isoformat(timespec="microseconds")


def resolve_range(spec: str | None, *, runner: GitRunner = default_git_runner) -> Range:
    """Resolve ``spec`` (or infer a default) into a fully-resolved :class:`Range`.

    Accepts ``A..B``, ``A...B`` (merge-base expanded here rather than delegated
    to git's dotted-diff semantics, so the behaviour is explicit and testable),
    a bare ref (ranged to HEAD), or None. With None the base ref is the first
    of: the branch's upstream, origin/HEAD, ``main``, ``master``.
    """
    def git(*argv: str) -> str:
        return runner(["git", *argv]).strip()

    def verify(ref: str) -> str:
        try:
            return git("rev-parse", "--verify", f"{ref}^{{commit}}")
        except Exception:
            raise ValueError(f"unknown git ref: {ref}") from None

    if spec is None:
        base_ref = _infer_base_ref(git)
        if base_ref is None:
            raise ValueError(
                'cannot infer a range — pass one explicitly, e.g. "wiki changelog main..HEAD"'
            )
        base = git("merge-base", base_ref, "HEAD")
        head = verify("HEAD")
    elif "..." in spec:
        left, _, right = spec.partition("...")
        head = verify(right or "HEAD")
        base = git("merge-base", verify(left), head)
    elif ".." in spec:
        left, _, right = spec.partition("..")
        base = verify(left)
        head = verify(right or "HEAD")
    else:
        base = verify(spec)
        head = verify("HEAD")

    return Range(
        base=base,
        head=head,
        base_iso=_bound(git("log", "-1", "--format=%cI", base), upper=False),
        head_iso=_bound(git("log", "-1", "--format=%cI", head), upper=True),
        commits=int(git("rev-list", "--count", f"{base}..{head}") or 0),
        paths=[p for p in git("diff", "--name-only", base, head).splitlines() if p],
    )


def _infer_base_ref(git: Callable[..., str]) -> str | None:
    """First resolvable default base: upstream, origin/HEAD, main, master."""
    for argv in (
        ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"),
        ("symbolic-ref", "--short", "refs/remotes/origin/HEAD"),
    ):
        try:
            found = git(*argv)
        except Exception:
            continue
        if found:
            return found
    for candidate in ("main", "master"):
        try:
            git("rev-parse", "--verify", f"{candidate}^{{commit}}")
        except Exception:
            continue
        return candidate
    return None


@dataclass(frozen=True)
class ChangelogEntry:
    """One dev event in the range, plus which arm of the selection found it."""

    event: RawSource
    matched_by: Literal["files", "window"]


@dataclass(frozen=True)
class Changelog:
    """Everything the render needs, including the numbers behind the coverage line."""

    rng: Range
    root: str
    entries: list[ChangelogEntry]
    files_with_history: int
    excluded: int


async def build_changelog(
    repo: Repository,
    rng: Range,
    *,
    root: str,
    limit: int,
    exclude_types: frozenset[str],
) -> Changelog:
    """Select the dev events belonging to ``rng``, newest first.

    Two arms, unioned and deduped by event id:

    * **files** — the range's changed paths, anchored to ``root``, looked up in
      the file index. This works retroactively: only 1 of 43 events on the
      author's wiki carries a head_sha, so joining on commits is not an option.
    * **window** — events with no files at all, captured between the two
      commits' timestamps. These are the design discussions the PreCompact hook
      exists to save, and the file arm cannot see them by construction.

    A file-less event is kept when its ``repo`` provenance matches ``root`` or
    is absent. Absent means *unknown*, not *mismatched*: every event captured
    before that key existed has none, and excluding them would make the window
    arm return nothing on any existing wiki. The imprecision is bounded to
    file-less events and self-heals as new events carry the key.
    """
    found = await events_for_paths(repo, rng.paths, root=root, limit=limit)
    entries = [ChangelogEntry(event=event, matched_by="files") for event in found.events]
    seen = {event.id for event in found.events}

    for event in await repo.dev_events_fileless_in_window(
        rng.base_iso, rng.head_iso, limit=limit
    ):
        if event.id in seen:
            continue
        if event.provenance.get("repo", "") not in ("", root):
            continue
        seen.add(event.id)
        entries.append(ChangelogEntry(event=event, matched_by="window"))

    kept: list[ChangelogEntry] = []
    excluded = 0
    for entry in entries:
        if safe_event_type(entry.event.provenance.get("type")) in exclude_types:
            excluded += 1
            continue
        kept.append(entry)
    kept.sort(key=lambda entry: entry.event.fetched_at, reverse=True)

    return Changelog(
        rng=rng, root=root, entries=kept,
        files_with_history=len(found.matched), excluded=excluded,
    )

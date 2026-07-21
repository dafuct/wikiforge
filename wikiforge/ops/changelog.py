"""wiki changelog: a why-annotated changelog for a git range.

The dev log already holds the request behind each change; this module joins it
to a git range and renders it. Zero LLM unless the caller asks for prose.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from wikiforge.ops.capture import GitRunner, default_git_runner


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

"""Git-range resolution for wiki changelog, including timestamp normalization."""

from __future__ import annotations

import pytest

from wikiforge.ops.changelog import resolve_range


def _runner(mapping: dict[tuple[str, ...], str], *, missing: set[str] = frozenset()):
    def run(argv: list[str]) -> str:
        key = tuple(argv[1:])
        if any(m in argv for m in missing):
            raise OSError("unknown revision")
        if key in mapping:
            return mapping[key]
        raise OSError(f"unexpected argv: {argv}")

    return run


_BASE_LOG = ("log", "-1", "--format=%cI", "aaaa")
_HEAD_LOG = ("log", "-1", "--format=%cI", "bbbb")


def _common(extra: dict[tuple[str, ...], str]) -> dict[tuple[str, ...], str]:
    base = {
        _BASE_LOG: "2026-07-20T14:30:39+03:00\n",
        _HEAD_LOG: "2026-07-21T09:00:00+03:00\n",
        ("rev-list", "--count", "aaaa..bbbb"): "23\n",
        ("diff", "--name-only", "aaaa", "bbbb"): "a.py\nb.py\n",
    }
    base.update(extra)
    return base


def test_two_dot_range_uses_both_endpoints() -> None:
    run = _runner(_common({
        ("rev-parse", "--verify", "x^{commit}"): "aaaa\n",
        ("rev-parse", "--verify", "y^{commit}"): "bbbb\n",
    }))

    rng = resolve_range("x..y", runner=run)

    assert (rng.base, rng.head, rng.commits, rng.paths) == ("aaaa", "bbbb", 23, ["a.py", "b.py"])


def test_three_dot_range_resolves_the_merge_base() -> None:
    run = _runner(_common({
        ("rev-parse", "--verify", "x^{commit}"): "xxxx\n",
        ("rev-parse", "--verify", "y^{commit}"): "bbbb\n",
        ("merge-base", "xxxx", "bbbb"): "aaaa\n",
    }))

    assert resolve_range("x...y", runner=run).base == "aaaa"


def test_bare_ref_ranges_to_head() -> None:
    run = _runner(_common({
        ("rev-parse", "--verify", "x^{commit}"): "aaaa\n",
        ("rev-parse", "--verify", "HEAD^{commit}"): "bbbb\n",
    }))

    rng = resolve_range("x", runner=run)

    assert (rng.base, rng.head) == ("aaaa", "bbbb")


def test_default_range_prefers_the_upstream() -> None:
    run = _runner(_common({
        ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/main\n",
        ("merge-base", "origin/main", "HEAD"): "aaaa\n",
        ("rev-parse", "--verify", "HEAD^{commit}"): "bbbb\n",
    }))

    assert resolve_range(None, runner=run).base == "aaaa"


def test_default_range_falls_back_to_main() -> None:
    mapping = _common({
        ("rev-parse", "--verify", "main^{commit}"): "mmmm\n",
        ("merge-base", "main", "HEAD"): "aaaa\n",
        ("rev-parse", "--verify", "HEAD^{commit}"): "bbbb\n",
    })

    def run(argv: list[str]) -> str:
        key = tuple(argv[1:])
        if key in mapping:
            return mapping[key]
        raise OSError("no such thing")

    assert resolve_range(None, runner=run).base == "aaaa"


def test_unresolvable_default_range_says_how_to_fix_it() -> None:
    def run(argv: list[str]) -> str:
        raise OSError("nope")

    with pytest.raises(ValueError, match="pass one explicitly"):
        resolve_range(None, runner=run)


def test_unknown_ref_is_named_in_the_error() -> None:
    def run(argv: list[str]) -> str:
        raise OSError("bad rev")

    with pytest.raises(ValueError, match="unknown git ref: nope"):
        resolve_range("nope..HEAD", runner=run)


def test_bounds_are_normalized_to_utc_and_widened_to_the_whole_second() -> None:
    """Git emits a local offset; fetched_at is stored in UTC.

    Comparing the two as strings is not comparing instants — 20:00+03:00 sorts
    after 18:52+00:00 while actually preceding it — so the window would drop
    events near either boundary.
    """
    run = _runner(_common({
        ("rev-parse", "--verify", "x^{commit}"): "aaaa\n",
        ("rev-parse", "--verify", "y^{commit}"): "bbbb\n",
    }))

    rng = resolve_range("x..y", runner=run)

    assert rng.base_iso == "2026-07-20T11:30:39.000000+00:00"
    assert rng.head_iso == "2026-07-21T06:00:00.999999+00:00"
    assert rng.base_iso < "2026-07-20T18:52:10.561928+00:00" < rng.head_iso

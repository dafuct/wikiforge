"""The changelog's exact output contract, including the coverage footer.

The footer is not decoration: a three-line changelog for a 23-commit range is
the honest output on a wiki whose feed was thin, and without the footer that
reads as a broken feature.
"""

from __future__ import annotations

from datetime import datetime

from wikiforge.models.domain import RawSource
from wikiforge.models.enums import SourceType
from wikiforge.ops.changelog import Changelog, ChangelogEntry, Range, format_changelog

_RANGE = Range(
    base="aaaaaaaaaa", head="bbbbbbbbbb",
    base_iso="2026-07-20T00:00:00.000000+00:00",
    head_iso="2026-07-20T23:59:59.999999+00:00",
    commits=23, paths=["a.py", "b.py", "c.py"],
)


def _event(title: str, *, kind: str, files: list[str], request: str | None = None) -> RawSource:
    return RawSource(
        id=1, content_hash=title, canonical_url=None, source_type=SourceType.DEV_EVENT,
        title=title,
        text=f"## Request (why)\n{request}\n" if request else title,
        fetched_at=datetime.fromisoformat("2026-07-20T10:00:00+00:00"),
        provenance={"files": ",".join(files), "type": kind, "ts": "2026-07-20T10:00:00Z"},
    )


def _log(
    entries: list[ChangelogEntry], *, files_with_history: int = 2, excluded: int = 0
) -> Changelog:
    return Changelog(rng=_RANGE, root="/r", entries=entries,
                     files_with_history=files_with_history, excluded=excluded)


def test_header_reports_commits_and_files() -> None:
    out = format_changelog(_log([]))

    assert out.splitlines()[0] == "# Changelog: aaaaaaa..bbbbbbb — 23 commits, 3 files"


def test_sections_follow_the_fixed_type_order() -> None:
    entries = [
        ChangelogEntry(event=_event("d", kind="docs", files=["/r/a.py"]), matched_by="files"),
        ChangelogEntry(event=_event("f", kind="bugfix", files=["/r/b.py"]), matched_by="files"),
    ]

    out = format_changelog(_log(entries))

    assert out.index("## Bugfix") < out.index("## Docs")


def test_unknown_types_sort_after_the_known_ones() -> None:
    entries = [
        ChangelogEntry(event=_event("z", kind="zebra", files=["/r/a.py"]), matched_by="files"),
        ChangelogEntry(event=_event("f", kind="bugfix", files=["/r/b.py"]), matched_by="files"),
    ]

    out = format_changelog(_log(entries))

    assert out.index("## Bugfix") < out.index("## Zebra")


def test_files_are_repo_relative_and_capped_at_five() -> None:
    files = [f"/r/f{i}.py" for i in range(7)]
    entries = [ChangelogEntry(event=_event("x", kind="change", files=files), matched_by="files")]

    out = format_changelog(_log(entries))

    assert "`f0.py`, `f1.py`, `f2.py`, `f3.py`, `f4.py` … (+2 more)" in out
    assert "/r/f0.py" not in out


def test_paths_outside_the_root_stay_absolute() -> None:
    entries = [
        ChangelogEntry(event=_event("x", kind="change", files=["/other/z.py"]), matched_by="files")
    ]

    assert "`/other/z.py`" in format_changelog(_log(entries))


def test_file_less_entries_get_their_own_section_with_date_and_type() -> None:
    entries = [
        ChangelogEntry(event=_event("talk", kind="design", files=[]), matched_by="window")
    ]

    out = format_changelog(_log(entries))

    assert "## Decisions without file changes" in out
    assert "- **2026-07-20 · design · talk**" in out


def test_a_multi_line_request_is_collapsed_to_one_line() -> None:
    entries = [
        ChangelogEntry(
            event=_event("x", kind="change", files=["/r/a.py"], request="first\n\nsecond"),
            matched_by="files",
        )
    ]

    body = format_changelog(_log(entries))

    assert "- **first second**" in body


def test_coverage_footer_reports_both_arms() -> None:
    entries = [
        ChangelogEntry(event=_event("a", kind="change", files=["/r/a.py"]), matched_by="files"),
        ChangelogEntry(event=_event("b", kind="design", files=[]), matched_by="window"),
    ]

    out = format_changelog(_log(entries))

    assert out.rstrip().endswith(
        "Coverage: 2 of 3 changed files have recorded decisions; "
        "1 events matched by file, 1 by time window."
    )


def test_hidden_entries_are_reported_not_silently_dropped() -> None:
    out = format_changelog(_log([], excluded=4))

    assert "4 entries hidden by --exclude-types." in out


def test_empty_sections_are_omitted() -> None:
    out = format_changelog(_log([]))

    assert "##" not in out

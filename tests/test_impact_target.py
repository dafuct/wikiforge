"""Target classification for wiki impact — deterministic, with an explicit override."""

from __future__ import annotations

import pytest

from wikiforge.ops.impact import classify_target


@pytest.mark.parametrize(
    ("arg", "expected"),
    [
        ("https://example.com/a", "source"),
        ("http://example.com/a", "source"),
        ("a" * 64, "source"),
        ("12", "source"),
        ("#12", "source"),
        ("wikiforge/services.py", "file"),
        ("README.md", "file"),
        ("sqlite-wal", "topic"),
        ("development-log", "topic"),
    ],
)
def test_classification_rules(arg: str, expected: str) -> None:
    assert classify_target(arg) == expected


def test_forced_kind_wins_over_every_rule() -> None:
    assert classify_target("https://example.com/a", forced="topic") == "topic"
    assert classify_target("README.md", forced="topic") == "topic"

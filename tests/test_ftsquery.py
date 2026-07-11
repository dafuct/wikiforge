"""Free text is sanitized into a safe FTS5 MATCH expression (no parser crashes)."""

from __future__ import annotations

from wikiforge.search.ftsquery import to_fts_match_query


def test_quotes_each_word_as_phrase_joined_by_or() -> None:
    assert to_fts_match_query("rust async") == '"rust" OR "async"'


def test_drops_fts5_special_characters() -> None:
    # Bound raw, each of these would raise sqlite3.OperationalError from FTS5.
    assert to_fts_match_query("what is the GIL?") == '"what" OR "is" OR "the" OR "GIL"'
    assert to_fts_match_query("C++ vs Rust") == '"C" OR "vs" OR "Rust"'
    assert to_fts_match_query("co-operative") == '"co" OR "operative"'
    assert to_fts_match_query('unterminated " quote') == '"unterminated" OR "quote"'


def test_empty_or_punctuation_only_yields_empty_string() -> None:
    assert to_fts_match_query("") == ""
    assert to_fts_match_query("???") == ""

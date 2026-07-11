"""Turn free-form user text into a safe FTS5 ``MATCH`` expression.

SQLite parses the string bound to ``MATCH`` as a *query expression*, so raw user
input containing ``?``, ``+``, ``:``, ``-``, or an unbalanced quote raises
``sqlite3.OperationalError`` (e.g. the everyday ``"what is the GIL?"`` fails on the
trailing ``?``). We tokenize the text into word runs and quote each token as a
literal phrase joined by ``OR``: punctuation is dropped, every term becomes a
harmless phrase literal, and a chunk matching any term stays retrievable — BM25
still ranks rarer terms higher, and the vector arm plus RRF cover recall.
"""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def to_fts_match_query(text: str) -> str:
    """Convert free text into an ``OR``-of-quoted-terms FTS5 ``MATCH`` expression.

    Each word run in ``text`` becomes a quoted phrase literal, so FTS5 special
    characters can never reach the query parser. Returns an empty string when
    ``text`` has no word characters (e.g. ``"???"``); callers must treat that as
    "no FTS match" rather than binding it, since an empty ``MATCH`` string is
    itself an FTS5 syntax error.
    """
    tokens = _WORD_RE.findall(text)
    return " OR ".join(f'"{token}"' for token in tokens)

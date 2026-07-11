"""Prompt-safety helpers: neutralize <source_data> envelope delimiters in untrusted text."""

from __future__ import annotations

import re

_ENVELOPE_TAG_RE = re.compile(r"<(/?)source_data", re.IGNORECASE)


def seal_source_data(text: str) -> str:
    """Neutralize any literal ``<source_data>`` envelope delimiters in untrusted text.

    Text that will be wrapped in a ``<source_data>…</source_data>`` envelope (retrieved
    chunks, or an LLM-synthesized article body derived from raw sources) may itself
    contain a literal ``</source_data>``, which would close the envelope early and let
    following text be read as instructions. We defang the delimiter by swapping its
    ``<`` for U+2039 (‹) so the token stays readable but can no longer be parsed as the
    envelope tag; ordinary angle brackets (e.g. ``<div>`` in a code snippet) are untouched.
    """
    return _ENVELOPE_TAG_RE.sub(lambda m: "‹" + m.group(0)[1:], text)

"""Decision memory: file→dev-event lookup helpers (pure SQL — no LLM, no embeddings)."""

from __future__ import annotations

import re

from wikiforge.models.domain import RawSource

_LINE_SUFFIX = re.compile(r"^(?P<path>.+):(?P<line>\d+)$")
_LINE_NOTE = "(line-level attribution arrives with hunk capture; showing file-level history)"
_SUMMARY_CAP = 200


def parse_path_arg(arg: str) -> tuple[str, str | None]:
    """Split a ``path[:line]`` argument; the line part is stripped with a note.

    v1 attribution is file-level (capture stores no hunk ranges), so ``:52`` is
    accepted for forward-compatibility and honestly ignored.
    """
    match = _LINE_SUFFIX.match(arg)
    if match is None:
        return arg, None
    return match.group("path"), _LINE_NOTE


def event_summary(event: RawSource) -> str:
    """One line for an event: digest summary if present, else the request text.

    The request is parsed from the note's ``## Request (why)`` section; the
    event title is the last-resort fallback. Capped at 200 chars.
    """
    digest = event.provenance.get("summary")
    if digest:
        return digest[:_SUMMARY_CAP]
    marker = "## Request (why)\n"
    if marker in event.text:
        request = event.text.split(marker, 1)[1].split("\n\n## ", 1)[0].strip()
        if request and request != "(none)":
            return request[:_SUMMARY_CAP]
    return event.title[:_SUMMARY_CAP]


def _event_date(event: RawSource) -> str:
    ts = event.provenance.get("ts") or event.fetched_at.isoformat()
    return ts[:10]


def format_events(path: str, events: list[RawSource]) -> str:
    """Human-facing ``wiki why`` output (newest first; unsealed — not model-bound)."""
    lines = [f"Decision history for {path}:"]
    for event in events:
        marker = event.provenance.get("consolidated")
        suffix = f"  [consolidated: {marker}]" if marker else ""
        kind = event.provenance.get("type", "change")
        lines.append(f"  {_event_date(event)} · {kind} · {event_summary(event)}{suffix}")
    return "\n".join(lines)

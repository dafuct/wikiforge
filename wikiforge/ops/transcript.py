"""Transcript parsing shared by every capture surface (Stop, SubagentStop, PreCompact).

Claude Code writes a JSONL transcript per session. Not every ``user`` message is
something the human said: slash commands, skill preambles, local-command output
and harness reminders all arrive as user messages. Treating those as "the
request" is what put skill boilerplate into the dev log's ``## Request (why)``
section, so classification lives here, once, for all surfaces.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

# Paired tags whose whole span (tags + content) is harness scaffolding, not user words.
_PAIRED_ENVELOPES = (
    "command-message",
    "command-name",
    "local-command-caveat",
    "local-command-stdout",
    "system-reminder",
)
_PAIRED_RE = [
    re.compile(rf"<{tag}>.*?</{tag}>", re.DOTALL | re.IGNORECASE) for tag in _PAIRED_ENVELOPES
]
# `<command-args>` is the exception: its CONTENT is the user's actual instruction.
_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.DOTALL | re.IGNORECASE)
# A skill preamble is injected as a bare line plus the whole skill body after it.
_SKILL_PREAMBLE_RE = re.compile(r"Base directory for this skill:.*", re.DOTALL)
# A skill preamble ends with `ARGUMENTS: <the user's actual request>`. Measured on
# ~3000 real user messages on 2026-07-20: 29 carry exactly one ARGUMENTS line,
# 0 carry more than one. An earlier ARGUMENTS: line inside a skill body must not
# hijack the capture, so the LAST occurrence is used. Non-greedy (.*?) with $ ensures
# each line is captured independently.
_ARGUMENTS_TAIL_RE = re.compile(r"^ARGUMENTS:[ \t]*(.*?)$", re.MULTILINE)


def strip_envelopes(text: str) -> str:
    """Remove harness scaffolding, keeping the user's own words.

    ``<command-args>`` content is preserved and promoted: when a slash command
    carries arguments, those arguments *are* the request. A skill preamble's
    trailing ``ARGUMENTS:`` line is the same shape in different clothing — for
    61% of measured skill-invocation messages it is the ONLY place the request
    survives — so it is captured and promoted the same way before the preamble
    body (and the ``ARGUMENTS:`` marker itself) is dropped.
    """
    args = [m.group(1).strip() for m in _ARGS_RE.finditer(text)]
    cleaned = _ARGS_RE.sub(" ", text)
    # Use only the LAST ARGUMENTS: line to avoid hijacking by an earlier one
    # inside the skill body. Measured on ~3000 real user messages on 2026-07-20:
    # 29 carry exactly one ARGUMENTS line; 0 carry more than one.
    tail_matches = list(_ARGUMENTS_TAIL_RE.finditer(cleaned))
    arguments_tail = [tail_matches[-1].group(1).strip()] if tail_matches else []
    cleaned = _ARGUMENTS_TAIL_RE.sub(" ", cleaned)
    for pattern in _PAIRED_RE:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = _SKILL_PREAMBLE_RE.sub(" ", cleaned)
    remainder = " ".join(cleaned.split())
    parts = [p for p in (*args, *arguments_tail, remainder) if p]
    return "\n".join(parts)


def _blocks(content: object) -> list[dict[str, Any]]:
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _text_of(content: object) -> str:
    if isinstance(content, str):
        return content
    parts = [b.get("text", "") for b in _blocks(content) if b.get("type") == "text"]
    return "\n".join(p for p in parts if p)


def is_human_request(content: object) -> bool:
    """Whether a ``user`` message carries words the human actually typed."""
    if not isinstance(content, str) and any(
        b.get("type") == "tool_result" for b in _blocks(content)
    ):
        return False
    text = _text_of(content)
    if not text:
        return False
    return bool(strip_envelopes(text).strip())


@dataclass
class Turn:
    """One human request and everything that happened until the next one."""

    request: str
    files: list[str] = field(default_factory=list)
    assistant_text: str = ""
    uuid: str | None = None
    ts: str | None = None


def read_transcript(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL transcript into a list of dicts, tolerating blank/bad lines."""
    try:
        raw_bytes = path.read_bytes()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line_bytes in raw_bytes.split(b"\n"):
        try:
            line = line_bytes.decode("utf-8").strip()
        except UnicodeDecodeError:
            continue
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def iter_turns(entries: list[dict[str, Any]]) -> list[Turn]:
    """Split a transcript into turns, one per genuine human request."""
    turns: list[Turn] = []
    for entry in entries:
        message = entry.get("message")
        message = message if isinstance(message, dict) else {}
        role = message.get("role") or entry.get("type")
        content = message.get("content", entry.get("content"))
        if role == "user" and is_human_request(content):
            turns.append(
                Turn(
                    request=strip_envelopes(_text_of(content)),
                    uuid=entry.get("uuid"),
                    ts=entry.get("timestamp"),
                )
            )
        elif role == "assistant" and turns:
            current = turns[-1]
            prose = _text_of(content)
            if prose:
                current.assistant_text = f"{current.assistant_text}\n{prose}".strip()
            for block in _blocks(content):
                if block.get("type") == "tool_use" and block.get("name") in EDIT_TOOLS:
                    inp = block.get("input", {})
                    fp = inp.get("file_path") or inp.get("notebook_path")
                    if isinstance(fp, str) and fp and fp not in current.files:
                        current.files.append(fp)
    return turns


def last_entry_uuid(entries: list[dict[str, Any]]) -> str | None:
    """The uuid of the final transcript entry — the watermark to store."""
    for entry in reversed(entries):
        uuid = entry.get("uuid")
        if isinstance(uuid, str) and uuid:
            return uuid
    return None


def turns_since(entries: list[dict[str, Any]], last_uuid: str | None) -> list[Turn]:
    """Turns that begin after ``last_uuid``.

    An unknown watermark (a rotated or replaced transcript) returns every turn
    rather than silently dropping the session's history.
    """
    if last_uuid is None:
        return iter_turns(entries)
    seen = [i for i, e in enumerate(entries) if e.get("uuid") == last_uuid]
    if not seen:
        return iter_turns(entries)
    return iter_turns(entries[seen[0] + 1 :])

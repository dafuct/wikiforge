"""Development-cycle capture: parse a Claude Code turn into a searchable dev event."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{12,}"),
    re.compile(r"\b[A-Fa-f0-9]{32,}\b"),
]


def redact_secrets(text: str) -> str:
    """Best-effort masking of obvious secret shapes in free text."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("***", text)
    return text


def parse_hook_stdin(raw: str) -> str | None:
    """Return the ``transcript_path`` from Claude Code Stop-hook JSON, or None."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    path = data.get("transcript_path") if isinstance(data, dict) else None
    return path if isinstance(path, str) and path else None


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


@dataclass
class Turn:
    """The triggering request and the files edited during the latest human turn."""

    request: str
    files: list[str]


def _blocks(content: object) -> list[dict[str, Any]]:
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _is_human_text(content: object) -> bool:
    if isinstance(content, str):
        return True
    blocks = _blocks(content)
    if any(b.get("type") == "tool_result" for b in blocks):
        return False
    return any(b.get("type") == "text" for b in blocks)


def _text_of(content: object) -> str:
    if isinstance(content, str):
        return content
    parts = [b.get("text", "") for b in _blocks(content) if b.get("type") == "text"]
    return "\n".join(p for p in parts if p)


def extract_turn(entries: list[dict[str, Any]]) -> Turn:
    """Extract the last human request and the files edited after it.

    A new human user message resets the collected file list, so edits from
    earlier turns are not re-attributed. ``tool_result`` user messages are not
    human turns and do not reset.
    """
    request = ""
    files: list[str] = []
    for entry in entries:
        message = entry.get("message")
        message = message if isinstance(message, dict) else {}
        role = message.get("role") or entry.get("type")
        content = message.get("content", entry.get("content"))
        if role == "user" and _is_human_text(content):
            request = _text_of(content)
            files = []
        elif role == "assistant":
            for block in _blocks(content):
                if block.get("type") == "tool_use" and block.get("name") in EDIT_TOOLS:
                    inp = block.get("input", {})
                    fp = inp.get("file_path") or inp.get("notebook_path")
                    if isinstance(fp, str) and fp and fp not in files:
                        files.append(fp)
    return Turn(request=request, files=files)
